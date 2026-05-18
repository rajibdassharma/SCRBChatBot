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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from api.deps import get_current_user, CurrentUser
from reports.dsr_aggregator import aggregate_dsr
from reports.dsr_pdf import render_dsr_pdf
from reports.mule_pdf import render_mule_pdf
from reports.case_pdf import render_case_pdf
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
