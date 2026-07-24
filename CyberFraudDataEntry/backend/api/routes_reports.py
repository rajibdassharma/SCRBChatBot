"""PDF report routes — mounted at `/api/v1/reports/...`.

Each endpoint streams a generated PDF as `application/pdf` with a
content-disposition header so the browser triggers a download.

Authorization model (DSR):
  - unit_user, admin   : own PS only (ps_id parameter ignored / forced)
  - super_admin        : any single PS, or all PSes (ps_id=None / "all")
"""
from __future__ import annotations

import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import Integer, cast, func as sql_func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from api.deps import get_current_user, CurrentUser
from reports.dsr_aggregator import aggregate_dsr
from reports.dsr_pdf import render_dsr_pdf
from reports.mule_pdf import render_mule_pdf
from reports.case_pdf import render_case_pdf
from reports.submission_status_pdf import render_submission_status_pdf
from reports.fir_ps_performance_pdf import render_fir_ps_performance_pdf
from reports.fir_ps_performance_xlsx import render_fir_ps_performance_xlsx
from reports.accounts_ps_comparison_pdf import render_accounts_ps_comparison_pdf
from reports.accounts_ps_comparison_xlsx import render_accounts_ps_comparison_xlsx
from reports.portals_dsr_daily_pdf import render_portals_dsr_daily_pdf
from reports.portals_dsr_daily_xlsx import render_portals_dsr_daily_xlsx
from reports.daily_work_daily_pdf import render_daily_work_daily_pdf
from reports.daily_work_daily_xlsx import render_daily_work_daily_xlsx
from models.portals_dsr_entry import PortalsDsrEntry
from models.daily_work_entry import DailyWorkEntry
from models.unit import Unit
from api.routes_dashboard import (
    compute_submission_status,
    compute_fir_ps_performance,
    _resolve_fir_perf_window,
    compute_accounts_comparison,
)
from api.deps import require_admin
from models.mule_report import MuleReport
from models.case import Case
from models.arrest import Arrest
from models.user import User
from models.police_station import PoliceStation


router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def _pdf_response(content: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _xlsx_response(content: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _resolve_dsr_scope(
    current: CurrentUser,
    *,
    requested_ps_id: int | None,
    requested_district: str | None,
) -> tuple[int | None, str | None]:
    """Decide the effective (ps_id, district) tuple for the report.

    Rules:
      - Non-super_admin (unit_user, admin): always forced to their own
        PS. Any `district` or `ps_id` query is ignored unless it matches
        their own PS — otherwise 403.
      - super_admin: free choice.
          * ps_id=N (>0)   → that PS
          * ps_id=0        → all PSes (district ignored)
          * district=X     → all PSes in district X
          * neither        → defaults to super_admin's own PS

    Returns: `(ps_id, district)` — at most one of the two is non-None.
    """
    if current.role != "super_admin":
        if not current.ps_id:
            raise HTTPException(status_code=403, detail="Account is not assigned to a police station")
        if requested_district is not None:
            raise HTTPException(status_code=403, detail="Only super admins can request district-wide reports")
        if requested_ps_id is not None and requested_ps_id != current.ps_id:
            raise HTTPException(status_code=403, detail="You can only download reports for your own police station")
        return current.ps_id, None

    # ── super_admin ──
    if requested_ps_id is not None and requested_ps_id != 0:
        return requested_ps_id, None
    if requested_ps_id == 0:
        return None, None  # all PSes (district ignored)
    if requested_district:
        return None, requested_district
    # No filter specified — default to own PS
    if not current.ps_id:
        raise HTTPException(status_code=403, detail="Account is not assigned to a police station")
    return current.ps_id, None


@router.get("/dsr.pdf")
async def get_dsr_pdf(
    date_from: date = Query(..., alias="from", description="Start date (inclusive)"),
    date_to: date = Query(..., alias="to", description="End date (inclusive)"),
    ps_id: int | None = Query(None, description="Police station id; 0 = all PSes (super_admin only)"),
    district: str | None = Query(None, description="District name — aggregate every PS in the district (super_admin only)"),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate the DSR PDF aggregated from real operational tables
    (cases, arrests, petitions, lien_accounts, refunds, mule_reports)
    over the requested date range, filtered by `created_at`.

    Scope precedence (super_admin only):
      * ps_id=N (>0)  → that single PS
      * ps_id=0       → all PSes (district ignored)
      * district=X    → all PSes in district X
      * neither       → super_admin's own PS

    Other roles are always forced to their own PS.
    """
    if date_to < date_from:
        raise HTTPException(status_code=400, detail="`to` must be on or after `from`")

    effective_ps_id, effective_district = _resolve_dsr_scope(
        current, requested_ps_id=ps_id, requested_district=district,
    )

    rows = await aggregate_dsr(
        db,
        date_from=date_from,
        date_to=date_to,
        ps_id=effective_ps_id,
        district=effective_district,
    )

    is_multi_ps = effective_ps_id is None
    pdf_bytes = render_dsr_pdf(
        rows=rows,
        date_from=date_from,
        date_to=date_to,
        requested_by_username=current.username,
        is_all_ps=is_multi_ps,
    )

    # Filename
    if effective_ps_id is None:
        scope_part = (
            f"District-{effective_district.replace(' ', '_')}"
            if effective_district else "AllPS"
        )
    else:
        scope_part = (rows[0].ps_label if rows else f"PS{effective_ps_id}").replace(" ", "_").replace("/", "-")
    if date_from == date_to:
        date_part = date_from.isoformat()
    else:
        date_part = f"{date_from.isoformat()}_to_{date_to.isoformat()}"
    filename = f"DSR_{scope_part}_{date_part}.pdf"
    return _pdf_response(pdf_bytes, filename)


# ── Mule Report PDF ──────────────────────────────────────────────────


@router.get("/mule.pdf")
async def get_mule_pdf(
    ack_no: str = Query(..., description="Bank acknowledgement number"),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Render one mule report (looked up by acknowledgement number) plus
    all six related transaction tables.

    Authorization: PS-scoped via the report's `submitted_by` user.
    super_admin can pull any report; admin / unit_user only within their
    own PS.
    """
    # Eager-load all six relationships in one query so the PDF builder
    # never has to lazy-load (which would fail under async).
    report = (await db.execute(
        select(MuleReport)
        .where(MuleReport.acknowledgement_no == ack_no)
        .options(
            selectinload(MuleReport.money_transfers),
            selectinload(MuleReport.other_transactions),
            selectinload(MuleReport.transactions_on_hold),
            selectinload(MuleReport.others_less_than_500),
            selectinload(MuleReport.aeps_transactions),
            selectinload(MuleReport.atm_withdrawals),
        )
    )).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail=f"No mule report found for acknowledgement '{ack_no}'")

    # Resolve the submitter's PS to enforce authz + show in the header
    submitter = None
    submitter_ps_id = None
    submitter_username = None
    if report.submitted_by:
        sub_row = (await db.execute(
            select(User.id, User.username, User.ps_id).where(User.id == report.submitted_by)
        )).first()
        if sub_row:
            submitter, submitter_username, submitter_ps_id = sub_row

    # Authorization
    if current.role != "super_admin":
        if not current.ps_id:
            raise HTTPException(status_code=403, detail="Account is not assigned to a police station")
        if submitter_ps_id != current.ps_id:
            raise HTTPException(status_code=403, detail="This mule report belongs to a different police station")

    # PS label for the header
    ps_label = None
    target_ps_id = submitter_ps_id or current.ps_id
    if target_ps_id:
        ps_row = (await db.execute(
            select(PoliceStation.station_name, PoliceStation.district_name)
            .where(PoliceStation.id == target_ps_id)
        )).first()
        if ps_row:
            ps_label = f"{ps_row[0]} ({ps_row[1]})"

    pdf_bytes = render_mule_pdf(
        report=report,
        ps_label=ps_label,
        submitted_by_username=submitter_username,
        requested_by_username=current.username,
    )

    safe_ack = ack_no.replace("/", "-").replace(" ", "_")
    filename = f"MuleReport_{safe_ack}.pdf"
    return _pdf_response(pdf_bytes, filename)


# ── Case File PDF ────────────────────────────────────────────────────


@router.get("/case.pdf")
async def get_case_pdf(
    fir_no: str | None = Query(None, description="FIR number (preferred lookup)"),
    petition_no: str | None = Query(None, description="Petition number (alternate lookup)"),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Render a full case file (header + arrests with sub-tables +
    petitions + lien accounts + unfreezes + refunds).

    Lookup by `fir_no` (preferred) or `petition_no`. Authorization:
    PS-scoped via the case's `submitted_by` user; super_admin can pull
    any case.
    """
    if not fir_no and not petition_no:
        raise HTTPException(status_code=400, detail="Provide either fir_no or petition_no")

    q = (
        select(Case)
        .options(
            selectinload(Case.arrests).selectinload(Arrest.accomplices),
            selectinload(Case.arrests).selectinload(Arrest.accused_details),
            selectinload(Case.petitions),
            selectinload(Case.lien_accounts),
            selectinload(Case.unfreeze_details),
            selectinload(Case.refunds),
        )
    )
    if fir_no:
        q = q.where(Case.fir_no == fir_no)
    else:
        q = q.where(Case.petition_no == petition_no)

    case = (await db.execute(q)).scalar_one_or_none()
    if not case:
        ident = fir_no or petition_no
        raise HTTPException(status_code=404, detail=f"No case found for '{ident}'")

    # Resolve submitter + PS for authz + header
    submitter_username = None
    submitter_ps_id = None
    if case.submitted_by:
        sub_row = (await db.execute(
            select(User.username, User.ps_id).where(User.id == case.submitted_by)
        )).first()
        if sub_row:
            submitter_username, submitter_ps_id = sub_row

    if current.role != "super_admin":
        if not current.ps_id:
            raise HTTPException(status_code=403, detail="Account is not assigned to a police station")
        if submitter_ps_id != current.ps_id:
            raise HTTPException(status_code=403, detail="This case belongs to a different police station")

    ps_label = None
    target_ps_id = submitter_ps_id or current.ps_id
    if target_ps_id:
        ps_row = (await db.execute(
            select(PoliceStation.station_name, PoliceStation.district_name)
            .where(PoliceStation.id == target_ps_id)
        )).first()
        if ps_row:
            ps_label = f"{ps_row[0]} ({ps_row[1]})"

    pdf_bytes = render_case_pdf(
        case=case,
        ps_label=ps_label,
        submitted_by_username=submitter_username,
        requested_by_username=current.username,
    )

    safe_id = (case.fir_no or case.petition_no or case.id).replace("/", "-").replace(" ", "_")
    filename = f"CaseFile_{safe_id}.pdf"
    return _pdf_response(pdf_bytes, filename)


@router.get("/submission-status.pdf")
async def get_submission_status_pdf(
    target_date: date = Query(..., alias="date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """PDF version of the Dashboard → Overview → Submission Status table.

    Same data the on-screen table renders for `target_date`. Auth is
    aligned with the JSON route: admin sees their own PS only,
    super_admin sees every (unit, PS) pair.
    """
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")
    rows = await compute_submission_status(
        db,
        target_date,
        unit_id_filter=admin.unit_id if admin.role != "super_admin" else None,
        ps_id_filter=admin.ps_id if admin.role != "super_admin" else None,
    )
    pdf_bytes = render_submission_status_pdf(rows, target_date=target_date)
    filename = f"SubmissionStatus_{target_date.isoformat()}.pdf"
    return _pdf_response(pdf_bytes, filename)


# ── FIR Dashboard exports ────────────────────────────────────────────
# Both routes share the same aggregation + scoping as the JSON
# /dashboard/fir-ps-performance endpoint so the download always
# matches what's on screen (before any client-side re-sort).

def _fir_perf_filename(ext: str, date_from: date, date_to: date) -> str:
    if date_from == date_to:
        return f"FIR_PS_Performance_{date_from.isoformat()}.{ext}"
    return f"FIR_PS_Performance_{date_from.isoformat()}_to_{date_to.isoformat()}.{ext}"


@router.get("/fir-ps-performance.pdf")
async def get_fir_ps_performance_pdf(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """PDF export of the FIR Dashboard PS-performance table."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")
    date_from, date_to = _resolve_fir_perf_window(date_from, date_to)
    rows = await compute_fir_ps_performance(db, date_from=date_from, date_to=date_to, admin=admin)
    pdf_bytes = render_fir_ps_performance_pdf(rows, date_from=date_from, date_to=date_to)
    return _pdf_response(pdf_bytes, _fir_perf_filename("pdf", date_from, date_to))


@router.get("/fir-ps-performance.xlsx")
async def get_fir_ps_performance_xlsx(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Excel export of the FIR Dashboard PS-performance table."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")
    date_from, date_to = _resolve_fir_perf_window(date_from, date_to)
    rows = await compute_fir_ps_performance(db, date_from=date_from, date_to=date_to, admin=admin)
    xlsx_bytes = render_fir_ps_performance_xlsx(rows, date_from=date_from, date_to=date_to)
    return _xlsx_response(xlsx_bytes, _fir_perf_filename("xlsx", date_from, date_to))


# ── Account Details PS-comparison exports ────────────────────────────
# Both routes share the same aggregation as the JSON
# /dashboard/accounts-comparison endpoint so the download always
# matches what's on screen.

def _accounts_ps_filename(ext: str, target_date: date) -> str:
    return f"Accounts_PS_Comparison_{target_date.isoformat()}.{ext}"


@router.get("/accounts-ps-comparison.pdf")
async def get_accounts_ps_comparison_pdf(
    target_date: date = Query(..., alias="date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """PDF export of the Account Details Dashboard PS-comparison table."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")
    rows = await compute_accounts_comparison(db, target_date=target_date, admin=admin)
    pdf_bytes = render_accounts_ps_comparison_pdf(rows, target_date=target_date)
    return _pdf_response(pdf_bytes, _accounts_ps_filename("pdf", target_date))


@router.get("/accounts-ps-comparison.xlsx")
async def get_accounts_ps_comparison_xlsx(
    target_date: date = Query(..., alias="date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Excel export of the Account Details Dashboard PS-comparison table."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")
    rows = await compute_accounts_comparison(db, target_date=target_date, admin=admin)
    xlsx_bytes = render_accounts_ps_comparison_xlsx(rows, target_date=target_date)
    return _xlsx_response(xlsx_bytes, _accounts_ps_filename("xlsx", target_date))


# ── Portals DSR daily report + Daily Work Done daily report ────────
# Both are Police-Station-wise for a single calendar date. Defaults
# to yesterday on the client so the operator hits Download on the
# next morning with no fiddling. Server accepts any date.


async def _all_active_ps_roster(db: AsyncSession) -> list[dict]:
    """Return the fixed 45-PS roster sorted district, PS name. Both
    reports need every PS to render (blank for non-submitters), so
    we drive the row list off this — not off whatever rows the day
    happened to produce."""
    q = (
        select(
            PoliceStation.id,
            PoliceStation.district_name,
            PoliceStation.station_name,
        )
        .where(PoliceStation.is_active == True)  # noqa: E712
        .order_by(PoliceStation.district_name, PoliceStation.station_name)
    )
    result = await db.execute(q)
    return [
        {"ps_id": pid, "district": dn, "ps_name": sn}
        for pid, dn, sn in result.all()
    ]


def _portals_metric_cols() -> list[str]:
    """25 PortalsDsrEntry columns in the render order."""
    return [
        "ncrp_received", "ncrp_disposed", "ncrp_pending",
        "samanvaya_request_received", "samanvaya_actions",
        "samanvaya_action_pending", "samanvaya_request_sent",
        "samanvaya_reply_received", "samanvaya_replies_pending",
        "sahayog_unlawful_content_removal", "sahayog_intermediary_requests",
        "sahayog_crypto_requests",
        "grm_request_received", "grm_action", "grm_pending",
        "mrm_request_received", "mrm_action", "mrm_pending",
        "bharatpol_request_received",
        "ocwc_received", "ocwc_disposed", "ocwc_pending",
        "ncmec_received", "ncmec_disposed", "ncmec_pending",
    ]


async def compute_portals_dsr_daily(
    db: AsyncSession, *, target_date: date,
) -> list[dict]:
    """One row per active PS. Metric values are the SUM of every
    submitted PortalsDsrEntry for that PS on target_date. PSes with
    no submission come back with None for every metric (renderers
    render blank)."""
    metric_cols = _portals_metric_cols()
    agg_cols = [
        sql_func.coalesce(sql_func.sum(getattr(PortalsDsrEntry, c)), 0).label(c)
        for c in metric_cols
    ]
    q = (
        select(PortalsDsrEntry.ps_id, *agg_cols)
        .where(
            PortalsDsrEntry.report_date == target_date,
            PortalsDsrEntry.status == "submitted",
        )
        .group_by(PortalsDsrEntry.ps_id)
    )
    result = await db.execute(q)
    by_ps: dict[int, dict] = {}
    for row in result.all():
        rd = row._mapping
        by_ps[rd["ps_id"]] = {c: int(rd[c] or 0) for c in metric_cols}

    roster = await _all_active_ps_roster(db)
    out: list[dict] = []
    for ps in roster:
        entry = {"ps_id": ps["ps_id"], "ps_name": ps["ps_name"], "district": ps["district"]}
        m = by_ps.get(ps["ps_id"])
        if m is None:
            # Non-submitter — leave metric keys absent so renderers
            # draw blank cells (not zeros).
            entry.update({c: None for c in metric_cols})
        else:
            entry.update(m)
        out.append(entry)
    return out


async def compute_daily_work_daily(
    db: AsyncSession, *, target_date: date,
) -> list[dict]:
    """One row per active PS. Numeric fields SUMMED across every
    daily_work_entry that PS filed for target_date; final_report
    split into A/B/C counts (rendered as 'A:n, B:m, C:k')."""
    numeric_cols = [
        "notices_35_41a_count",
        "notices_91_92_94_banks",
        "notices_91_92_94_intermediary",
        "notices_91_92_94_account_holder",
        "notices_91_92_94_cdr_ipdr",
        "lien_requests_count",
        "freeze_requests_count",
        "total_lien_amount",
        "unlien_requests_count",
        "defreeze_requests_count",
        "total_unlien_amount",
        "arrests_count",
        "statements_count",
    ]

    sum_cols = [
        sql_func.coalesce(sql_func.sum(getattr(DailyWorkEntry, c)), 0).label(c)
        for c in numeric_cols
    ]

    q = (
        select(
            DailyWorkEntry.ps_id,
            sql_func.count(DailyWorkEntry.id).label("fir_count"),
            *sum_cols,
            sql_func.sum(cast(DailyWorkEntry.final_report == "A", Integer)).label("final_a"),
            sql_func.sum(cast(DailyWorkEntry.final_report == "B", Integer)).label("final_b"),
            sql_func.sum(cast(DailyWorkEntry.final_report == "C", Integer)).label("final_c"),
        )
        .where(DailyWorkEntry.report_date == target_date)
        .group_by(DailyWorkEntry.ps_id)
    )
    result = await db.execute(q)
    by_ps: dict[int, dict] = {}
    for row in result.all():
        rd = row._mapping
        ps_id = int(rd["ps_id"])
        agg = {c: (float(rd[c]) if "amount" in c else int(rd[c] or 0)) for c in numeric_cols}
        agg["fir_count"] = int(rd["fir_count"] or 0)
        agg["final_report_a"] = int(rd["final_a"] or 0)
        agg["final_report_b"] = int(rd["final_b"] or 0)
        agg["final_report_c"] = int(rd["final_c"] or 0)
        parts = [
            f"{L}:{n}"
            for L, n in [
                ("A", agg["final_report_a"]),
                ("B", agg["final_report_b"]),
                ("C", agg["final_report_c"]),
            ]
            if n
        ]
        agg["final_report_abc"] = ", ".join(parts) if parts else None
        by_ps[ps_id] = agg

    roster = await _all_active_ps_roster(db)
    out: list[dict] = []
    for ps in roster:
        entry = {"ps_id": ps["ps_id"], "ps_name": ps["ps_name"], "district": ps["district"]}
        m = by_ps.get(ps["ps_id"])
        if m is None:
            entry.update({c: None for c in numeric_cols})
            entry["fir_count"] = 0
            entry["final_report_a"] = 0
            entry["final_report_b"] = 0
            entry["final_report_c"] = 0
            entry["final_report_abc"] = None
        else:
            entry.update(m)
        out.append(entry)
    return out


def _portals_daily_filename(ext: str, target_date: date) -> str:
    return f"Portals_DSR_{target_date.isoformat()}.{ext}"


def _daily_work_daily_filename(ext: str, target_date: date) -> str:
    return f"Daily_Work_Done_{target_date.isoformat()}.{ext}"


@router.get("/portals-dsr-daily.pdf")
async def get_portals_dsr_daily_pdf(
    target_date: date = Query(..., alias="date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """PDF export of the Portals DSR daily report, PS-wise."""
    rows = await compute_portals_dsr_daily(db, target_date=target_date)
    pdf = render_portals_dsr_daily_pdf(rows, target_date=target_date)
    return _pdf_response(pdf, _portals_daily_filename("pdf", target_date))


@router.get("/portals-dsr-daily.xlsx")
async def get_portals_dsr_daily_xlsx(
    target_date: date = Query(..., alias="date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Excel export of the Portals DSR daily report, PS-wise."""
    rows = await compute_portals_dsr_daily(db, target_date=target_date)
    xlsx = render_portals_dsr_daily_xlsx(rows, target_date=target_date)
    return _xlsx_response(xlsx, _portals_daily_filename("xlsx", target_date))


@router.get("/daily-work-daily.pdf")
async def get_daily_work_daily_pdf(
    target_date: date = Query(..., alias="date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """PDF export of the Daily Work Done report, PS-wise aggregated."""
    rows = await compute_daily_work_daily(db, target_date=target_date)
    pdf = render_daily_work_daily_pdf(rows, target_date=target_date)
    return _pdf_response(pdf, _daily_work_daily_filename("pdf", target_date))


@router.get("/daily-work-daily.xlsx")
async def get_daily_work_daily_xlsx(
    target_date: date = Query(..., alias="date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Excel export of the Daily Work Done report, PS-wise aggregated."""
    rows = await compute_daily_work_daily(db, target_date=target_date)
    xlsx = render_daily_work_daily_xlsx(rows, target_date=target_date)
    return _xlsx_response(xlsx, _daily_work_daily_filename("xlsx", target_date))
