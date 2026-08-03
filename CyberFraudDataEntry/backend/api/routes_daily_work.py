"""Daily-Work-Done routes.

Upsert on (unit_id, ps_id, fir_no, report_date) — one row per PS,
per FIR, per calendar date. Same scope-enforcement + admin-view
shape as `routes_dsr` (migration 008 pattern).

Endpoints:
  POST   /api/v1/daily-work/                       upsert
  GET    /api/v1/daily-work/?fir_no=&date=         load one row (own PS)
  GET    /api/v1/daily-work/by-fir?fir_no=         history for one FIR
  GET    /api/v1/daily-work/history?limit=         recent rows (own PS)
  GET    /api/v1/daily-work/{entry_id}             load one row by id
  DELETE /api/v1/daily-work/{entry_id}             delete one row
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.daily_work_entry import DailyWorkEntry
from models.unit import Unit
from models.police_station import PoliceStation
from api.test_scope import (
    where_not_test, exclude_test_ps, exclude_test_unit,
    exclude_test_station_row, exclude_test_unit_row,
    station_row_filter, viewer_is_test,
)
from schemas.daily_work import DailyWorkCreate, DailyWorkResponse
from api.deps import get_current_user, require_admin, CurrentUser

router = APIRouter(prefix="/api/v1/daily-work", tags=["daily-work"])

# Fields copied between the ORM row and the response payload.
_DW_FIELDS = [
    "fir_no",
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
    "final_report",
]


def _entry_to_response(entry: DailyWorkEntry, unit_name: str | None = None) -> dict:
    d = {f: getattr(entry, f) for f in _DW_FIELDS}
    d.update(
        id=entry.id,
        unit_id=entry.unit_id,
        ps_id=entry.ps_id,
        unit_name=unit_name,
        report_date=entry.report_date,
        submitted_by=entry.submitted_by,
        created_at=str(entry.created_at) if entry.created_at else None,
        updated_at=str(entry.updated_at) if entry.updated_at else None,
    )
    return d


def _require_scope(current_user: CurrentUser) -> tuple[int, int]:
    """Return (unit_id, ps_id). Every daily-work row is (unit, ps)-scoped."""
    if not current_user.unit_id:
        raise HTTPException(status_code=403, detail="No district assigned to this account.")
    if not current_user.ps_id:
        raise HTTPException(status_code=403, detail="No police station assigned to this account.")
    return current_user.unit_id, current_user.ps_id


@router.post("/", response_model=DailyWorkResponse)
async def upsert_daily_work(
    body: DailyWorkCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    unit_id, ps_id = _require_scope(current_user)

    existing = (await db.execute(
        select(DailyWorkEntry).where(
            DailyWorkEntry.unit_id == unit_id,
            DailyWorkEntry.ps_id == ps_id,
            DailyWorkEntry.fir_no == body.fir_no,
            DailyWorkEntry.report_date == body.report_date,
        )
    )).scalar_one_or_none()

    if existing:
        values = {f: getattr(body, f) for f in _DW_FIELDS}
        values["submitted_by"] = current_user.user_id
        await db.execute(
            update(DailyWorkEntry).where(DailyWorkEntry.id == existing.id).values(**values)
        )
        await db.commit()
        await db.refresh(existing)
        return _entry_to_response(existing, current_user.unit_name)

    entry = DailyWorkEntry(
        unit_id=unit_id,
        ps_id=ps_id,
        report_date=body.report_date,
        submitted_by=current_user.user_id,
    )
    for f in _DW_FIELDS:
        setattr(entry, f, getattr(body, f))
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _entry_to_response(entry, current_user.unit_name)


@router.get("/", response_model=Optional[DailyWorkResponse])
async def get_own_daily_work(
    fir_no: str = Query(..., min_length=1, max_length=50),
    date_: date = Query(..., alias="date"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    unit_id, ps_id = _require_scope(current_user)

    entry = (await db.execute(
        select(DailyWorkEntry).where(
            DailyWorkEntry.unit_id == unit_id,
            DailyWorkEntry.ps_id == ps_id,
            DailyWorkEntry.fir_no == fir_no.strip(),
            DailyWorkEntry.report_date == date_,
        )
    )).scalar_one_or_none()

    if not entry:
        return None
    return _entry_to_response(entry, current_user.unit_name)


@router.get("/by-fir", response_model=List[DailyWorkResponse])
async def get_daily_work_by_fir(
    fir_no: str = Query(..., min_length=1, max_length=50),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """All daily-work rows for one FIR at this PS, most-recent first.
    Powers the Update / History screen once the operator types an FIR."""
    unit_id, ps_id = _require_scope(current_user)

    entries = (await db.execute(
        select(DailyWorkEntry)
        .where(
            DailyWorkEntry.unit_id == unit_id,
            DailyWorkEntry.ps_id == ps_id,
            DailyWorkEntry.fir_no == fir_no.strip(),
        )
        .order_by(DailyWorkEntry.report_date.desc())
    )).scalars().all()

    return [_entry_to_response(e, current_user.unit_name) for e in entries]


@router.get("/history", response_model=List[DailyWorkResponse])
async def get_daily_work_history(
    limit: int = Query(30, ge=1, le=365),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    unit_id, ps_id = _require_scope(current_user)

    entries = (await db.execute(
        select(DailyWorkEntry)
        .where(DailyWorkEntry.unit_id == unit_id, DailyWorkEntry.ps_id == ps_id)
        .order_by(DailyWorkEntry.report_date.desc(), DailyWorkEntry.updated_at.desc())
        .limit(limit)
    )).scalars().all()

    return [_entry_to_response(e, current_user.unit_name) for e in entries]


# ── Dashboard aggregation ────────────────────────────────────
# MUST be declared before `/{entry_id}` — FastAPI matches routes in
# declaration order and `entry_id: int` rejects "dashboard" with 422
# before falling through, so a `/dashboard` GET declared after the
# int-typed path param is unreachable.

class DailyWorkDashboardTotals(BaseModel):
    entries: int
    unique_firs: int
    notices_35_41a: int
    notices_91_92_94_total: int
    notices_91_92_94_banks: int
    notices_91_92_94_intermediary: int
    notices_91_92_94_account_holder: int
    notices_91_92_94_cdr_ipdr: int
    lien_requests_total: int
    freeze_requests_total: int
    total_lien_amount: float
    unlien_requests_total: int
    defreeze_requests_total: int
    total_unlien_amount: float
    arrests: int
    statements: int


class DailyWorkFinalReportSplit(BaseModel):
    a: int
    b: int
    c: int
    open: int


class DailyWorkDailyPoint(BaseModel):
    day: date
    notices: int
    arrests: int
    statements: int


class DailyWorkPsRow(BaseModel):
    """One police station's investigation activity in the window.

    Only populated for super_admin — a PS-level admin sees a single
    row (its own), so the comparison would be meaningless noise."""
    unit_id: int
    district: str
    ps_id: int
    ps_name: str
    entries: int = 0
    unique_firs: int = 0
    notices: int = 0
    lien_requests: int = 0
    arrests: int = 0
    statements: int = 0
    total_lien_amount: float = 0


class DailyWorkDashboardResponse(BaseModel):
    date_from: date
    date_to: date
    totals: DailyWorkDashboardTotals
    final_report_split: DailyWorkFinalReportSplit
    daily: List[DailyWorkDailyPoint]
    # Cross-PS comparison. Empty for a PS-level admin (see above);
    # populated for super_admin so HQ can see who is actually working
    # their FIRs and who is silent.
    per_ps: List[DailyWorkPsRow] = []
    # True when the response spans every PS rather than just the
    # caller's. Lets the UI label itself honestly instead of guessing
    # from the row count.
    cross_ps: bool = False


@router.get("/dashboard", response_model=DailyWorkDashboardResponse)
async def daily_work_dashboard(
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin dashboard aggregation for Daily Work Done.

    Scope: admin's own (unit_id, ps_id) — same VAPT 7.7/7.8 rule as
    every other admin dashboard on this app. Cross-PS visibility for
    super-admin is a follow-up if the user asks for it.

    Date window defaults to the trailing 30 days when `from` / `to`
    are omitted. Inclusive on both ends.
    """
    # super_admin sees every station; a PS-level admin stays pinned to
    # its own (unit, ps) per VAPT 7.7/7.8. This mirrors the bypass every
    # other admin dashboard already has — daily-work was the only module
    # with no cross-PS branch at all, which is why HQ saw zeros.
    is_super = admin.role == "super_admin"
    if is_super:
        unit_id, ps_id = admin.unit_id, admin.ps_id
    else:
        unit_id, ps_id = _require_scope(admin)

    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = date_to - timedelta(days=29)
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="`from` must be on or before `to`.")

    # Window always applies; the (unit, ps) pin only for non-super.
    scope_filter: tuple = (
        DailyWorkEntry.report_date >= date_from,
        DailyWorkEntry.report_date <= date_to,
    )
    if not is_super:
        scope_filter = (
            DailyWorkEntry.unit_id == unit_id,
            DailyWorkEntry.ps_id == ps_id,
        ) + scope_filter
    # Applies to BOTH roles. A PS admin is already pinned to its own
    # station so this is a no-op for them; for super_admin it is the
    # only thing keeping the test fixture out of the headline totals,
    # the trend and the final-report split.
    if not viewer_is_test(admin):
        _excl = exclude_test_ps(DailyWorkEntry.ps_id)
        if _excl is not None:
            scope_filter = scope_filter + (_excl,)

    # One aggregation pass for all headline numbers. func.coalesce
    # protects against empty windows (sum → NULL, we want 0).
    row = (await db.execute(
        select(
            func.count(DailyWorkEntry.id),
            func.count(func.distinct(DailyWorkEntry.fir_no)),
            func.coalesce(func.sum(DailyWorkEntry.notices_35_41a_count), 0),
            func.coalesce(func.sum(DailyWorkEntry.notices_91_92_94_banks), 0),
            func.coalesce(func.sum(DailyWorkEntry.notices_91_92_94_intermediary), 0),
            func.coalesce(func.sum(DailyWorkEntry.notices_91_92_94_account_holder), 0),
            func.coalesce(func.sum(DailyWorkEntry.notices_91_92_94_cdr_ipdr), 0),
            func.coalesce(func.sum(DailyWorkEntry.lien_requests_count), 0),
            func.coalesce(func.sum(DailyWorkEntry.freeze_requests_count), 0),
            func.coalesce(func.sum(DailyWorkEntry.total_lien_amount), 0),
            func.coalesce(func.sum(DailyWorkEntry.unlien_requests_count), 0),
            func.coalesce(func.sum(DailyWorkEntry.defreeze_requests_count), 0),
            func.coalesce(func.sum(DailyWorkEntry.total_unlien_amount), 0),
            func.coalesce(func.sum(DailyWorkEntry.arrests_count), 0),
            func.coalesce(func.sum(DailyWorkEntry.statements_count), 0),
        ).where(*scope_filter)
    )).one()

    (
        entries, unique_firs, n_35_41a,
        n_banks, n_interm, n_ach, n_cdr,
        lien_req, freeze_req, lien_amt,
        unlien_req, defreeze_req, unlien_amt,
        arrests, statements,
    ) = row

    totals = DailyWorkDashboardTotals(
        entries=int(entries or 0),
        unique_firs=int(unique_firs or 0),
        notices_35_41a=int(n_35_41a or 0),
        notices_91_92_94_banks=int(n_banks or 0),
        notices_91_92_94_intermediary=int(n_interm or 0),
        notices_91_92_94_account_holder=int(n_ach or 0),
        notices_91_92_94_cdr_ipdr=int(n_cdr or 0),
        notices_91_92_94_total=int((n_banks or 0) + (n_interm or 0) + (n_ach or 0) + (n_cdr or 0)),
        lien_requests_total=int(lien_req or 0),
        freeze_requests_total=int(freeze_req or 0),
        total_lien_amount=float(lien_amt or 0),
        unlien_requests_total=int(unlien_req or 0),
        defreeze_requests_total=int(defreeze_req or 0),
        total_unlien_amount=float(unlien_amt or 0),
        arrests=int(arrests or 0),
        statements=int(statements or 0),
    )

    # Final-report split — one small extra query since we need
    # NULL-as-"open" bucketing which SQL COUNT(field) can't express
    # in the same GROUP BY without a case-expression per bucket.
    fr_rows = (await db.execute(
        select(DailyWorkEntry.final_report, func.count(DailyWorkEntry.id))
        .where(*scope_filter)
        .group_by(DailyWorkEntry.final_report)
    )).all()
    fr_counts: dict[Any, int] = {r[0]: int(r[1]) for r in fr_rows}
    split = DailyWorkFinalReportSplit(
        a=fr_counts.get("A", 0),
        b=fr_counts.get("B", 0),
        c=fr_counts.get("C", 0),
        open=fr_counts.get(None, 0),
    )

    # Per-day series — powers the line/bar chart. Sums of the three
    # most operator-relevant counters. Days with zero entries simply
    # don't appear; the frontend can zero-fill if needed.
    daily_rows = (await db.execute(
        select(
            DailyWorkEntry.report_date,
            func.coalesce(
                func.sum(
                    DailyWorkEntry.notices_35_41a_count
                    + DailyWorkEntry.notices_91_92_94_banks
                    + DailyWorkEntry.notices_91_92_94_intermediary
                    + DailyWorkEntry.notices_91_92_94_account_holder
                    + DailyWorkEntry.notices_91_92_94_cdr_ipdr
                ), 0,
            ),
            func.coalesce(func.sum(DailyWorkEntry.arrests_count), 0),
            func.coalesce(func.sum(DailyWorkEntry.statements_count), 0),
        )
        .where(*scope_filter)
        .group_by(DailyWorkEntry.report_date)
        .order_by(DailyWorkEntry.report_date.asc())
    )).all()
    daily = [
        DailyWorkDailyPoint(
            day=r[0],
            notices=int(r[1] or 0),
            arrests=int(r[2] or 0),
            statements=int(r[3] or 0),
        )
        for r in daily_rows
    ]

    # Per-PS comparison — the point of the cross-PS view. Skipped
    # entirely for a PS-level admin, who would get exactly one row.
    #
    # Driven by a LEFT JOIN from police_stations so a station that
    # logged NOTHING still appears with zeros. That is the row HQ
    # actually needs: silence is the finding, and an INNER JOIN would
    # hide precisely the stations worth asking about.
    per_ps: List[DailyWorkPsRow] = []
    if is_super:
        from sqlalchemy import and_
        notices_expr = (
            DailyWorkEntry.notices_35_41a_count
            + DailyWorkEntry.notices_91_92_94_banks
            + DailyWorkEntry.notices_91_92_94_intermediary
            + DailyWorkEntry.notices_91_92_94_account_holder
            + DailyWorkEntry.notices_91_92_94_cdr_ipdr
        )
        ps_q = (
            select(
                Unit.id.label("unit_id"),
                Unit.name.label("district"),
                PoliceStation.id.label("ps_id"),
                PoliceStation.station_name.label("ps_name"),
                func.count(DailyWorkEntry.id).label("entries"),
                func.count(func.distinct(DailyWorkEntry.fir_no)).label("unique_firs"),
                func.coalesce(func.sum(notices_expr), 0).label("notices"),
                func.coalesce(func.sum(DailyWorkEntry.lien_requests_count), 0).label("lien_requests"),
                func.coalesce(func.sum(DailyWorkEntry.arrests_count), 0).label("arrests"),
                func.coalesce(func.sum(DailyWorkEntry.statements_count), 0).label("statements"),
                func.coalesce(func.sum(DailyWorkEntry.total_lien_amount), 0).label("lien_amount"),
            )
            .select_from(PoliceStation)
            .join(Unit, Unit.name == PoliceStation.district_name)
            .outerjoin(
                DailyWorkEntry,
                and_(
                    DailyWorkEntry.ps_id == PoliceStation.id,
                    # The date filter MUST live on the join, not in a
                    # WHERE. In a WHERE it would turn the outer join
                    # back into an inner one and drop every silent
                    # station — the exact rows this table exists for.
                    DailyWorkEntry.report_date >= date_from,
                    DailyWorkEntry.report_date <= date_to,
                ),
            )
            .where(PoliceStation.is_active == True)  # noqa: E712
        # Test fixture is a real, active station — drop it from the
        # station LIST too, or it appears as a permanent zero row.
        .where(station_row_filter(admin))
            .group_by(Unit.id, Unit.name, PoliceStation.id, PoliceStation.station_name)
        )
        per_ps = [
            DailyWorkPsRow(
                unit_id=int(r.unit_id),
                district=r.district or "",
                ps_id=int(r.ps_id),
                ps_name=r.ps_name or "",
                entries=int(r.entries or 0),
                unique_firs=int(r.unique_firs or 0),
                notices=int(r.notices or 0),
                lien_requests=int(r.lien_requests or 0),
                arrests=int(r.arrests or 0),
                statements=int(r.statements or 0),
                total_lien_amount=float(r.lien_amount or 0),
            )
            for r in (await db.execute(ps_q)).all()
        ]
        per_ps.sort(key=lambda r: (-r.entries, r.district, r.ps_name))

    return DailyWorkDashboardResponse(
        date_from=date_from,
        date_to=date_to,
        totals=totals,
        final_report_split=split,
        daily=daily,
        per_ps=per_ps,
        cross_ps=is_super,
    )


@router.get("/{entry_id}", response_model=DailyWorkResponse)
async def get_daily_work_by_id(
    entry_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    unit_id, ps_id = _require_scope(current_user)

    entry = (await db.execute(
        select(DailyWorkEntry).where(
            DailyWorkEntry.id == entry_id,
            DailyWorkEntry.unit_id == unit_id,
            DailyWorkEntry.ps_id == ps_id,
        )
    )).scalar_one_or_none()

    if not entry:
        raise HTTPException(status_code=404, detail="Daily-work entry not found.")
    return _entry_to_response(entry, current_user.unit_name)


@router.delete("/{entry_id}", status_code=204)
async def delete_daily_work(
    entry_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    unit_id, ps_id = _require_scope(current_user)

    result = await db.execute(
        delete(DailyWorkEntry).where(
            DailyWorkEntry.id == entry_id,
            DailyWorkEntry.unit_id == unit_id,
            DailyWorkEntry.ps_id == ps_id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Daily-work entry not found.")
    await db.commit()
    return None
