from __future__ import annotations

from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.case import Case
from models.arrest import Arrest
from models.lien_account import LienAccount
from models.unfreeze_detail import UnfreezeDetail
from models.refund import Refund
from models.petition import Petition
from models.dsr_entry import DsrEntry
from models.nil_declaration import NilDeclaration
from models.mule_entry import MuleEntry
from models.mule_report import MuleReport
from models.money_transfer import MoneyTransfer
from models.atm_withdrawal import AtmWithdrawal
from models.unit import Unit
from models.user import User
from models.police_station import PoliceStation
from schemas.dashboard import (
    KpiSummary, UnitComparison, PsComparison, TrendPoint, SubmissionStatus,
    QuietUnit, TimeToArrestRow, BankSlaRow,
    RecurringAccount, BankConcentration, AtmHotspot, LayerBucket,
    LienAccountAtLayer,
    AccountCaseDetail, CaseDetailFull,
    ArrestSummary, LienSummary, PetitionSummary, RefundSummary,
    DisposalSummary, TrialSummary, PendingByYearRow,
)
from api.deps import require_admin, CurrentUser

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


# Scoping rule:
#   role == 'admin'        -> stats for admin.unit_id only (per VAPT 7.8)
#   role == 'super_admin'  -> stats across ALL PSes (Senior Officer privilege).
#                             This intentionally bypasses the unit_id filter.
#                             Per-record BOLA still applies on /cases/{id} etc.

def _scope_to_unit(query, current: CurrentUser, case_alias=Case):
    if current.role == "super_admin":
        return query
    if not current.unit_id:
        raise HTTPException(status_code=403, detail="Account is not assigned to any PS.")
    return query.where(case_alias.unit_id == current.unit_id)


@router.get("/summary", response_model=KpiSummary)
async def get_summary(
    target_date: date = Query(..., alias="date", description="Cumulative cutoff date — include records created on or before this date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Cumulative totals as of `date` (inclusive). Records entered after
    this date are excluded — filter is `<created_at> <= date`."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    # MySQL DATE(x) <= :date  is inclusive of any time on that date
    total_cases = (await db.execute(
        _scope_to_unit(select(func.count(Case.id)), admin)
        .where(func.date(Case.created_at) <= target_date)
    )).scalar() or 0

    total_arrests = (await db.execute(
        _scope_to_unit(
            select(func.count(Arrest.id)).join(Case, Arrest.case_id == Case.id),
            admin,
        ).where(func.date(Arrest.created_at) <= target_date)
    )).scalar() or 0

    total_amount_lien_marked = float((await db.execute(
        _scope_to_unit(
            select(func.coalesce(func.sum(LienAccount.amount_lien_marked), 0))
            .join(Case, LienAccount.case_id == Case.id),
            admin,
        ).where(func.date(LienAccount.created_at) <= target_date)
    )).scalar() or 0)

    total_amount_refunded = float((await db.execute(
        _scope_to_unit(
            select(func.coalesce(func.sum(Refund.amount), 0))
            .join(Case, Refund.case_id == Case.id),
            admin,
        )
        .where(Refund.refunded == "yes")
        .where(func.date(Refund.created_at) <= target_date)
    )).scalar() or 0)

    total_accounts_lien_marked = (await db.execute(
        _scope_to_unit(
            select(func.count(LienAccount.id)).join(Case, LienAccount.case_id == Case.id),
            admin,
        ).where(func.date(LienAccount.created_at) <= target_date)
    )).scalar() or 0

    total_accounts_defreezed = (await db.execute(
        _scope_to_unit(
            select(func.count(UnfreezeDetail.id)).join(Case, UnfreezeDetail.case_id == Case.id),
            admin,
        ).where(func.date(UnfreezeDetail.created_at) <= target_date)
    )).scalar() or 0

    total_amount_defreezed = float((await db.execute(
        _scope_to_unit(
            select(func.coalesce(func.sum(UnfreezeDetail.amount), 0))
            .join(Case, UnfreezeDetail.case_id == Case.id),
            admin,
        ).where(func.date(UnfreezeDetail.created_at) <= target_date)
    )).scalar() or 0)

    # Units submitted = how many distinct PSes have at least one case as of date
    if admin.role == "super_admin":
        units_submitted = (await db.execute(
            select(func.count(func.distinct(Case.unit_id)))
            .where(func.date(Case.created_at) <= target_date)
        )).scalar() or 0
        units_total = (await db.execute(
            select(func.count(Unit.id)).where(Unit.is_active == True)  # noqa: E712
        )).scalar() or 0
    else:
        units_submitted = 1 if total_cases > 0 else 0
        units_total = 1

    return KpiSummary(
        total_cases=int(total_cases),
        total_arrests=int(total_arrests),
        total_amount_lien_marked=total_amount_lien_marked,
        total_amount_refunded=total_amount_refunded,
        total_amount_defreezed=total_amount_defreezed,
        total_accounts_lien_marked=int(total_accounts_lien_marked),
        total_accounts_defreezed=int(total_accounts_defreezed),
        units_submitted=int(units_submitted),
        units_total=int(units_total),
    )


@router.get("/unit-comparison", response_model=List[UnitComparison])
async def get_unit_comparison(
    target_date: date = Query(..., alias="date", description="Cumulative cutoff date — include records created on or before this date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """admin: single row for own PS. super_admin: row per PS that has cases.
    All counts are cumulative as of `date` (inclusive)."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    if admin.role == "super_admin":
        rows = (await db.execute(
            select(
                Unit.id,
                Unit.name,
                func.count(func.distinct(Case.id)).label("case_count"),
            )
            .join(Case, Case.unit_id == Unit.id)
            .where(func.date(Case.created_at) <= target_date)
            .group_by(Unit.id, Unit.name)
            .order_by(func.count(func.distinct(Case.id)).desc())
        )).all()
    else:
        rows = (await db.execute(
            select(
                Unit.id,
                Unit.name,
                func.count(func.distinct(Case.id)).label("case_count"),
            )
            .join(Case, Case.unit_id == Unit.id)
            .where(Unit.id == admin.unit_id)
            .where(func.date(Case.created_at) <= target_date)
            .group_by(Unit.id, Unit.name)
        )).all()

    # One round-trip to get PS count per district — used to gate the
    # drill-into-PSes affordance on the frontend.
    ps_count_map = dict((await db.execute(
        select(User.unit_id, func.count(func.distinct(User.ps_id)))
        .where(User.unit_id.is_not(None))
        .where(User.ps_id.is_not(None))
        .group_by(User.unit_id)
    )).all())

    out: List[UnitComparison] = []
    for unit_id, unit_name, case_count in rows:
        arrest_count = (await db.execute(
            select(func.count(Arrest.id))
            .join(Case, Arrest.case_id == Case.id)
            .where(Case.unit_id == unit_id)
            .where(func.date(Arrest.created_at) <= target_date)
        )).scalar() or 0
        lien_amount = float((await db.execute(
            select(func.coalesce(func.sum(LienAccount.amount_lien_marked), 0))
            .join(Case, LienAccount.case_id == Case.id)
            .where(Case.unit_id == unit_id)
            .where(func.date(LienAccount.created_at) <= target_date)
        )).scalar() or 0)
        out.append(UnitComparison(
            unit_id=int(unit_id),
            unit_name=unit_name,
            cases=int(case_count or 0),
            arrests=int(arrest_count),
            amount_lien_marked=lien_amount,
            ps_count=int(ps_count_map.get(unit_id, 0) or 0),
        ))
    return out


@router.get("/cases-by-ps", response_model=List[PsComparison])
async def get_cases_by_ps(
    target_date: date = Query(..., alias="date", description="Cumulative cutoff date"),
    unit_id: int = Query(..., description="District (unit) to drill down into"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Cases-per-PS breakdown for one district.

    Cases attribute to PSes via the submitting user's `ps_id`. Cases
    submitted by users with no PS assignment are surfaced under
    `(Unassigned)` so the totals reconcile with the district view.

    Authorisation: super_admin may drill into any district. admin
    (PS-level) may only drill into their own unit_id — any other
    unit_id returns 403."""
    if admin.role == "admin":
        if not admin.unit_id:
            raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")
        if unit_id != admin.unit_id:
            raise HTTPException(status_code=403, detail="You can only view your own district's PSes.")

    rows = (await db.execute(
        select(
            PoliceStation.station_name,
            func.count(Case.id).label("cases"),
        )
        .select_from(Case)
        .join(User, User.id == Case.submitted_by, isouter=True)
        .join(PoliceStation, PoliceStation.id == User.ps_id, isouter=True)
        .where(Case.unit_id == unit_id)
        .where(func.date(Case.created_at) <= target_date)
        .group_by(PoliceStation.station_name)
        .order_by(func.count(Case.id).desc())
    )).all()

    return [
        PsComparison(
            ps_name=name if name else "(Unassigned)",
            cases=int(c or 0),
        )
        for name, c in rows
    ]


@router.get("/trends", response_model=List[TrendPoint])
async def get_trends(
    from_: date = Query(..., alias="from"),
    to: date = Query(...),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Daily counts of cases / arrests / petitions registered between
    [from, to] inclusive. Day buckets that have no activity are
    returned with zeros so the line chart draws a continuous axis."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")
    if from_ > to:
        raise HTTPException(status_code=422, detail="`from` must be on or before `to`.")
    if (to - from_).days > 365:
        raise HTTPException(status_code=422, detail="Date range cannot exceed 365 days.")

    # Cases per day (by registration_date)
    case_q = (
        select(Case.registration_date, func.count(Case.id))
        .where(Case.registration_date.between(from_, to))
        .group_by(Case.registration_date)
    )
    case_q = _scope_to_unit(case_q, admin)
    case_rows = {d: int(c) for d, c in (await db.execute(case_q)).all() if d}

    # Arrests per day (by date_of_arrest)
    arr_q = (
        select(Arrest.date_of_arrest, func.count(Arrest.id))
        .join(Case, Arrest.case_id == Case.id)
        .where(Arrest.date_of_arrest.between(from_, to))
        .group_by(Arrest.date_of_arrest)
    )
    arr_q = _scope_to_unit(arr_q, admin)
    arr_rows = {d: int(c) for d, c in (await db.execute(arr_q)).all() if d}

    # Petitions per day (use parent case registration_date; petitions have no own date)
    pet_q = (
        select(Case.registration_date, func.count(Petition.id))
        .join(Petition, Petition.case_id == Case.id)
        .where(Case.registration_date.between(from_, to))
        .group_by(Case.registration_date)
    )
    pet_q = _scope_to_unit(pet_q, admin)
    pet_rows = {d: int(c) for d, c in (await db.execute(pet_q)).all() if d}

    out: List[TrendPoint] = []
    cur = from_
    while cur <= to:
        out.append(TrendPoint(
            report_date=cur.isoformat(),
            total_cases=case_rows.get(cur, 0),
            total_arrests=arr_rows.get(cur, 0),
            total_petitions=pet_rows.get(cur, 0),
        ))
        cur += timedelta(days=1)
    return out


async def compute_submission_status(
    db: AsyncSession,
    target_date: date,
    *,
    unit_id_filter: int | None = None,
    ps_id_filter: int | None = None,
) -> List[SubmissionStatus]:
    """Compute the per-PS submission rollup for `target_date`.

    Shared by the JSON `/submission-status` route and the PDF
    `/reports/submission-status.pdf` route so both reflect identical
    numbers. When `unit_id_filter` + `ps_id_filter` are set, narrows to
    that single (unit, PS) pair; otherwise sweeps everything.
    """
    # Enumerate the (unit, PS) pairs that actually have users assigned —
    # PSes with no users can't submit data, so showing an empty row would
    # be noise. Same source we use for `unit-comparison`'s ps_count.
    ps_q = (
        select(
            Unit.id.label("unit_id"),
            Unit.name.label("unit_name"),
            PoliceStation.id.label("ps_id"),
            PoliceStation.station_name.label("ps_name"),
        )
        .select_from(User)
        .join(Unit, Unit.id == User.unit_id)
        .join(PoliceStation, PoliceStation.id == User.ps_id)
        .where(Unit.is_active == True)  # noqa: E712
        .where(User.is_active == True)  # noqa: E712
        .where(User.unit_id.is_not(None))
        .where(User.ps_id.is_not(None))
        .distinct()
    )
    if unit_id_filter is not None and ps_id_filter is not None:
        ps_q = ps_q.where(Unit.id == unit_id_filter).where(PoliceStation.id == ps_id_filter)
    ps_rows = (await db.execute(ps_q)).all()

    # Cases per (unit_id, ps_id) — cases.ps_id is canonical post migration 002.
    case_rows = (await db.execute(
        select(Case.unit_id, Case.ps_id,
               func.count(Case.id),
               func.max(func.date(Case.created_at)))
        .where(func.date(Case.created_at) <= target_date)
        .group_by(Case.unit_id, Case.ps_id)
    )).all()

    # Mule reports — derive ps_id from submitter (mule_reports lacks the column).
    # Drops mule reports whose submitter has no ps_id (only legacy / system rows).
    mule_rows = (await db.execute(
        select(MuleReport.unit_id, User.ps_id,
               func.count(MuleReport.id),
               func.max(func.date(MuleReport.created_at)))
        .join(User, User.id == MuleReport.submitted_by, isouter=True)
        .where(func.date(MuleReport.created_at) <= target_date)
        .where(User.ps_id.is_not(None))
        .group_by(MuleReport.unit_id, User.ps_id)
    )).all()

    # Petitions — child rows of `petitions`. Attribute to a PS via the
    # parent case's (unit_id, ps_id). Same definition the DSR aggregator
    # uses so the two reports stay reconciled.
    petition_rows = (await db.execute(
        select(
            Case.unit_id,
            Case.ps_id,
            func.count(Petition.id),
            func.max(func.date(Petition.created_at)),
        )
        .select_from(Petition)
        .join(Case, Petition.case_id == Case.id)
        .where(func.date(Petition.created_at) <= target_date)
        .group_by(Case.unit_id, Case.ps_id)
    )).all()

    # DSR became per-PS in migration 008 (was per-district before then).
    # Fetch the (unit_id, ps_id) tuples that filed for target_date so
    # each PS row can render its own DSR flag independently.
    dsr_rows = (await db.execute(
        select(DsrEntry.unit_id, DsrEntry.ps_id)
        .where(DsrEntry.report_date == target_date)
    )).all()

    # Build (unit_id, ps_id) → metric maps
    case_counts: dict[tuple[int, int], int] = {
        (int(uid), int(pid)): int(n or 0) for uid, pid, n, _ in case_rows if pid is not None
    }
    case_last: dict[tuple[int, int], date | None] = {
        (int(uid), int(pid)): d for uid, pid, _, d in case_rows if pid is not None
    }
    mule_counts: dict[tuple[int, int], int] = {
        (int(uid), int(pid)): int(n or 0) for uid, pid, n, _ in mule_rows if pid is not None
    }
    mule_last: dict[tuple[int, int], date | None] = {
        (int(uid), int(pid)): d for uid, pid, _, d in mule_rows if pid is not None
    }
    petition_counts: dict[tuple[int, int], int] = {
        (int(uid), int(pid)): int(n or 0) for uid, pid, n, _ in petition_rows if pid is not None
    }
    petition_last: dict[tuple[int, int], date | None] = {
        (int(uid), int(pid)): d for uid, pid, _, d in petition_rows if pid is not None
    }
    dsr_filed: set[tuple[int, int]] = {
        (int(u), int(p)) for u, p in dsr_rows if u is not None and p is not None
    }

    # NIL declarations for target_date — one row per (unit_id, ps_id)
    # because the PS explicitly said "no activity today". We also pick up
    # the declarer's name so the table can surface it on hover.
    nil_rows = (await db.execute(
        select(NilDeclaration.unit_id, NilDeclaration.ps_id, User.full_name, User.username)
        .join(User, User.id == NilDeclaration.declared_by, isouter=True)
        .where(NilDeclaration.nil_date == target_date)
    )).all()
    nil_map: dict[tuple[int, int], str | None] = {
        (int(u), int(p)): (full or uname) for u, p, full, uname in nil_rows
    }

    # Cumulative NIL rollup up to target_date, per (unit_id, ps_id).
    # Feeds both the new "NIL" column (count) and the "Last Entry"
    # column, which treats a NIL declaration as a valid entry per the
    # 2026-07-08 product refinement.
    nil_rollup_rows = (await db.execute(
        select(
            NilDeclaration.unit_id,
            NilDeclaration.ps_id,
            func.count(NilDeclaration.id),
            func.max(NilDeclaration.nil_date),
        )
        .where(NilDeclaration.nil_date <= target_date)
        .group_by(NilDeclaration.unit_id, NilDeclaration.ps_id)
    )).all()
    nil_counts: dict[tuple[int, int], int] = {
        (int(u), int(p)): int(n or 0) for u, p, n, _ in nil_rollup_rows
    }
    nil_last: dict[tuple[int, int], date | None] = {
        (int(u), int(p)): d for u, p, _, d in nil_rollup_rows
    }

    out: List[SubmissionStatus] = []
    for uid, uname, pid, pname in ps_rows:
        key = (int(uid), int(pid))
        c = case_counts.get(key, 0)
        p = petition_counts.get(key, 0)
        m = mule_counts.get(key, 0)
        # last_entry_date is the max across cases, petitions, mule reports,
        # AND NIL declarations. A PS whose only activity is petitions (or
        # only NIL) still shows the last real date, not "Never".
        last_dates = [
            d for d in (
                case_last.get(key),
                petition_last.get(key),
                mule_last.get(key),
                nil_last.get(key),
            )
            if d is not None
        ]
        last = max(last_dates) if last_dates else None
        out.append(SubmissionStatus(
            unit_id=int(uid),
            unit_name=uname,
            ps_id=int(pid),
            ps_name=pname or "",
            entry_count=c + p + m,
            cases_count=c,
            petitions_count=p,
            mule_count=m,
            last_entry_date=last.isoformat() if last else None,
            dsr_filed=(int(uid), int(pid)) in dsr_filed,
            nil_declared=key in nil_map,
            nil_declared_by_name=nil_map.get(key),
            nil_count=nil_counts.get(key, 0),
        ))
    return out


@router.get("/submission-status", response_model=List[SubmissionStatus])
async def get_submission_status(
    target_date: date = Query(..., alias="date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Submission rollup at PS level (one row per active PS).

    Most districts have a single CEN PS, but Bangalore City has multiple
    and each needs its own row. Cases attribute via cases.ps_id directly;
    mule reports attribute via the submitter's users.ps_id (mule_reports
    has no ps_id column of its own). DSR is a district-level concept —
    every PS row in the same district shares the same dsr_filed flag.

    admin: own (unit_id, ps_id) only. super_admin: every active (unit, PS).
    """
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")
    return await compute_submission_status(
        db,
        target_date,
        unit_id_filter=admin.unit_id if admin.role != "super_admin" else None,
        ps_id_filter=admin.ps_id if admin.role != "super_admin" else None,
    )


# ── Operations tab ──────────────────────────────────────────────────────────


@router.get("/quiet-units", response_model=List[QuietUnit])
async def get_quiet_units(
    target_date: date = Query(..., alias="date"),
    threshold_days: int = Query(7, ge=1, le=365),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Units with no case OR mule-report entry in the last `threshold_days`
    leading up to `date` (inclusive). Units that have NEVER entered anything
    are surfaced with `days_silent = null` so the UI sorts them to the top."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    # In-scope units
    if admin.role == "super_admin":
        units = (await db.execute(
            select(Unit.id, Unit.name).where(Unit.is_active == True)  # noqa: E712
            .order_by(Unit.name)
        )).all()
    else:
        units = (await db.execute(
            select(Unit.id, Unit.name).where(Unit.id == admin.unit_id)
        )).all()

    # Last case / mule-report timestamp per unit (capped at target_date)
    case_last = dict((await db.execute(
        select(Case.unit_id, func.max(func.date(Case.created_at)))
        .where(func.date(Case.created_at) <= target_date)
        .group_by(Case.unit_id)
    )).all())
    mule_last = dict((await db.execute(
        select(MuleReport.unit_id, func.max(func.date(MuleReport.created_at)))
        .where(func.date(MuleReport.created_at) <= target_date)
        .group_by(MuleReport.unit_id)
    )).all())

    out: List[QuietUnit] = []
    for uid, uname in units:
        c, m = case_last.get(uid), mule_last.get(uid)
        last = max([d for d in (c, m) if d is not None], default=None)
        if last is None:
            # Never entered anything — always surfaced
            out.append(QuietUnit(unit_id=int(uid), unit_name=uname, days_silent=None, last_entry_date=None))
            continue
        delta = (target_date - last).days
        if delta >= threshold_days:
            out.append(QuietUnit(
                unit_id=int(uid), unit_name=uname,
                days_silent=int(delta), last_entry_date=last.isoformat(),
            ))

    # None first, then descending days_silent
    out.sort(key=lambda r: (0 if r.days_silent is None else 1, -(r.days_silent or 0)))
    return out


@router.get("/time-to-arrest", response_model=List[TimeToArrestRow])
async def get_time_to_arrest(
    target_date: date = Query(..., alias="date"),
    lookback_days: int = Query(90, ge=7, le=365),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Per-unit average days from `cases.registration_date` to first
    `arrests.date_of_arrest`. Sample is cases whose `registration_date`
    falls in the trailing `lookback_days` window ending at `date`."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    window_start = target_date - timedelta(days=lookback_days)

    # First arrest per case in the window
    inner = (
        select(
            Case.unit_id.label("unit_id"),
            Case.id.label("case_id"),
            Case.registration_date.label("reg_date"),
            func.min(Arrest.date_of_arrest).label("first_arrest"),
        )
        .join(Arrest, Arrest.case_id == Case.id)
        .where(Case.registration_date.between(window_start, target_date))
        .where(Arrest.date_of_arrest.is_not(None))
        .where(Case.registration_date.is_not(None))
        .group_by(Case.unit_id, Case.id, Case.registration_date)
    )
    inner = _scope_to_unit(inner, admin)
    rows = (await db.execute(inner)).all()

    # Aggregate per unit, drop negative deltas (data-entry mistakes)
    bucket: dict[int, list[int]] = {}
    for unit_id, _case_id, reg_date, first_arrest in rows:
        if reg_date is None or first_arrest is None:
            continue
        d = (first_arrest - reg_date).days
        if d < 0:
            continue
        bucket.setdefault(unit_id, []).append(d)

    if not bucket:
        return []

    # Pull unit names for the units we have data for
    unit_names = dict((await db.execute(
        select(Unit.id, Unit.name).where(Unit.id.in_(list(bucket.keys())))
    )).all())

    out = [
        TimeToArrestRow(
            unit_name=unit_names.get(uid, f"Unit {uid}"),
            avg_days=round(sum(days) / len(days), 1),
            sample_size=len(days),
        )
        for uid, days in bucket.items()
    ]
    out.sort(key=lambda r: r.avg_days)
    return out


# Multiple date formats seen in bank-supplied Excel uploads — try each in
# order. Anything that doesn't match is dropped from the SLA sample.
_BANK_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d/%b/%Y", "%Y/%m/%d")


def _parse_bank_date(s):
    from datetime import datetime
    if not s:
        return None
    s = str(s).strip()
    if not s:
        return None
    for fmt in _BANK_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


@router.get("/bank-action-sla", response_model=List[BankSlaRow])
async def get_bank_action_sla(
    target_date: date = Query(..., alias="date"),
    lookback_days: int = Query(180, ge=30, le=365),
    min_sample: int = Query(5, ge=1, le=100),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Per-bank average days from a money-transfer's `transaction_date` to
    the bank's `date_of_action`. Date columns are stored as strings (bank
    Excel feeds vary), so dates are parsed defensively in Python; rows that
    don't match a known format are dropped. Banks with fewer than
    `min_sample` parseable rows are excluded — small N is misleading."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    q = (
        select(
            MoneyTransfer.bank,
            MoneyTransfer.transaction_date,
            MoneyTransfer.date_of_action,
        )
        .join(MuleReport, MoneyTransfer.report_id == MuleReport.id)
        .where(MoneyTransfer.bank.is_not(None))
        .where(MoneyTransfer.transaction_date.is_not(None))
        .where(MoneyTransfer.date_of_action.is_not(None))
        .where(func.date(MoneyTransfer.created_at) <= target_date)
    )
    if admin.role != "super_admin":
        q = q.where(MuleReport.unit_id == admin.unit_id)
    rows = (await db.execute(q)).all()

    window_start = target_date - timedelta(days=lookback_days)
    bucket: dict[str, list[int]] = {}
    for bank, t_str, a_str in rows:
        t = _parse_bank_date(t_str)
        a = _parse_bank_date(a_str)
        if t is None or a is None:
            continue
        if not (window_start <= t <= target_date):
            continue
        d = (a - t).days
        if d < 0:
            continue
        b = (bank or "").strip()
        if not b:
            continue
        bucket.setdefault(b, []).append(d)

    out = [
        BankSlaRow(
            bank=b,
            avg_days=round(sum(days) / len(days), 1),
            count=len(days),
        )
        for b, days in bucket.items()
        if len(days) >= min_sample
    ]
    out.sort(key=lambda r: r.avg_days, reverse=True)  # slowest first — names-and-shames
    return out[:20]


# ── Investigation tab ──────────────────────────────────────────────────────


@router.get("/recurring-mule-accounts", response_model=List[RecurringAccount])
async def get_recurring_mule_accounts(
    target_date: date = Query(..., alias="date"),
    min_cases: int = Query(2, ge=2, le=50),
    limit: int = Query(50, ge=1, le=200),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Account numbers appearing across `min_cases` or more distinct cases
    in lien_accounts. The strongest signal for a recurring mule.
    Recommended index: `CREATE INDEX idx_lien_account_no ON lien_accounts(account_no)`."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    q = (
        select(
            LienAccount.account_no,
            func.count(func.distinct(LienAccount.case_id)).label("case_count"),
            func.count(func.distinct(Case.unit_id)).label("units_count"),
            func.coalesce(func.sum(LienAccount.amount_lien_marked), 0).label("total"),
            func.max(LienAccount.bank_name).label("bank"),
        )
        .join(Case, LienAccount.case_id == Case.id)
        .where(func.date(LienAccount.created_at) <= target_date)
        .where(LienAccount.account_no.is_not(None))
        # Filter out rows where someone saved an empty lien_accounts entry
        # — they show up as a blank-account_no "lead" otherwise.
        .where(func.length(func.trim(LienAccount.account_no)) > 0)
        .group_by(LienAccount.account_no)
        .having(func.count(func.distinct(LienAccount.case_id)) >= min_cases)
        .order_by(func.count(func.distinct(LienAccount.case_id)).desc(),
                  func.sum(LienAccount.amount_lien_marked).desc())
        .limit(limit)
    )
    if admin.role != "super_admin":
        q = q.where(Case.unit_id == admin.unit_id)

    rows = (await db.execute(q)).all()
    return [
        RecurringAccount(
            account_no=acc,
            bank=bank,
            case_count=int(cc),
            units_count=int(uc),
            total_amount=float(total or 0),
        )
        for acc, cc, uc, total, bank in rows
    ]


@router.get("/account-cases", response_model=List[AccountCaseDetail])
async def get_account_cases(
    account_no: str = Query(..., min_length=1),
    target_date: date = Query(..., alias="date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """All cases that have a lien_accounts row for `account_no`.

    Authorisation follows the same rule as the parent leaderboard:
    super_admin sees every case across districts; admin (PS-level)
    sees only cases in their own unit, even if the account appears
    elsewhere. Cross-district visibility for an admin would be useful
    investigatively but is intentionally gated to super_admin per the
    existing scoping pattern."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    q = (
        select(
            Case.id,
            Case.fir_no,
            Case.petition_no,
            Case.registration_date,
            Case.case_type,
            Case.crime_type,
            Case.status,
            Unit.name.label("district"),
            PoliceStation.station_name.label("ps_name"),
            LienAccount.bank_name,
            LienAccount.amount_lien_marked,
            LienAccount.layer,
            LienAccount.created_at.label("lien_created_at"),
        )
        .select_from(LienAccount)
        .join(Case, LienAccount.case_id == Case.id)
        .join(Unit, Unit.id == Case.unit_id)
        .join(User, User.id == Case.submitted_by, isouter=True)
        .join(PoliceStation, PoliceStation.id == User.ps_id, isouter=True)
        .where(LienAccount.account_no == account_no)
        .where(func.date(LienAccount.created_at) <= target_date)
        .order_by(LienAccount.created_at.desc())
    )
    if admin.role != "super_admin":
        q = q.where(Case.unit_id == admin.unit_id)

    rows = (await db.execute(q)).all()
    return [
        AccountCaseDetail(
            case_id=str(case_id),
            fir_no=fir,
            petition_no=pet,
            registration_date=reg.isoformat() if reg else None,
            case_type=ctype,
            crime_type=crime,
            status=status,
            district=district or "",
            ps_name=ps,
            bank_name=bank,
            amount=float(amt or 0),
            layer=int(layer) if layer is not None else None,
            lien_created_at=lien_at.isoformat() if lien_at else None,
        )
        for case_id, fir, pet, reg, ctype, crime, status, district, ps, bank, amt, layer, lien_at in rows
    ]


@router.get("/case-detail", response_model=CaseDetailFull)
async def get_case_detail(
    case_id: str = Query(..., min_length=1),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Key fields for one case — header + summaries of arrests, lien accounts,
    petitions and refunds. Designed for the dashboard's third drill-down
    level, not the Case edit page (which loads the full nested object)."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    # Case header — also returns district + PS via the same join chain we use
    # in /account-cases so the response shape stays consistent.
    row = (await db.execute(
        select(
            Case.id, Case.fir_no, Case.petition_no, Case.registration_date,
            Case.case_type, Case.crime_type, Case.status, Case.facts,
            Unit.name.label("district"),
            PoliceStation.station_name.label("ps_name"),
            Case.unit_id,
        )
        .select_from(Case)
        .join(Unit, Unit.id == Case.unit_id)
        .join(User, User.id == Case.submitted_by, isouter=True)
        .join(PoliceStation, PoliceStation.id == User.ps_id, isouter=True)
        .where(Case.id == case_id)
    )).one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Case not found.")

    (cid, fir, pet, reg, ctype, crime, status, facts, district, ps, unit_id) = row
    if admin.role != "super_admin" and unit_id != admin.unit_id:
        raise HTTPException(status_code=403, detail="You can only view cases in your own district.")

    arrest_rows = (await db.execute(
        select(Arrest.name, Arrest.date_of_arrest, Arrest.aadhar, Arrest.pan)
        .where(Arrest.case_id == case_id)
        .order_by(Arrest.created_at)
    )).all()
    lien_rows = (await db.execute(
        select(LienAccount.account_no, LienAccount.bank_name,
               LienAccount.amount_lien_marked, LienAccount.layer)
        .where(LienAccount.case_id == case_id)
        .order_by(LienAccount.created_at)
    )).all()
    pet_rows = (await db.execute(
        select(Petition.petition_no, Petition.nature, Petition.petition_type, Petition.amount)
        .where(Petition.case_id == case_id)
        .order_by(Petition.created_at)
    )).all()
    ref_rows = (await db.execute(
        select(Refund.victim_name, Refund.amount, Refund.refunded)
        .where(Refund.case_id == case_id)
        .order_by(Refund.created_at)
    )).all()

    return CaseDetailFull(
        case_id=str(cid),
        fir_no=fir,
        petition_no=pet,
        registration_date=reg.isoformat() if reg else None,
        case_type=ctype,
        crime_type=crime,
        status=status,
        facts=facts,
        district=district or "",
        ps_name=ps,
        arrests=[
            ArrestSummary(
                name=n or "",
                date_of_arrest=d.isoformat() if d else None,
                aadhar=ad, pan=pn,
            ) for n, d, ad, pn in arrest_rows
        ],
        lien_accounts=[
            LienSummary(
                account_no=acc or "",
                bank_name=bn,
                amount_lien_marked=float(amt or 0),
                layer=int(layer) if layer is not None else None,
            ) for acc, bn, amt, layer in lien_rows
        ],
        petitions=[
            PetitionSummary(
                petition_no=pn, nature=nat, petition_type=pt,
                amount=float(amt or 0),
            ) for pn, nat, pt, amt in pet_rows
        ],
        refunds=[
            RefundSummary(
                victim_name=vn, amount=float(amt or 0), refunded=rf,
            ) for vn, amt, rf in ref_rows
        ],
    )


# IFSC prefix → human-readable bank name. First 4 characters of an IFSC
# encode the bank; the rest is the branch. List covers the public-sector,
# major private, and select small-finance / payments banks that show up
# in cyber-fraud cases. Unknown prefixes are shown as-is so they still
# get counted — investigators can extend the list as new banks appear.
_IFSC_TO_BANK = {
    "SBIN": "State Bank of India",
    "HDFC": "HDFC Bank",
    "ICIC": "ICICI Bank",
    "AXIS": "Axis Bank",
    "KKBK": "Kotak Mahindra Bank",
    "YESB": "Yes Bank",
    "PUNB": "Punjab National Bank",
    "BARB": "Bank of Baroda",
    "CNRB": "Canara Bank",
    "UBIN": "Union Bank of India",
    "BKID": "Bank of India",
    "CBIN": "Central Bank of India",
    "IOBA": "Indian Overseas Bank",
    "IDIB": "Indian Bank",
    "MAHB": "Bank of Maharashtra",
    "PSIB": "Punjab and Sind Bank",
    "UCBA": "UCO Bank",
    "IBKL": "IDBI Bank",
    "INDB": "IndusInd Bank",
    "FDRL": "Federal Bank",
    "RATN": "RBL Bank",
    "IDFB": "IDFC First Bank",
    "BDBL": "Bandhan Bank",
    "SIBL": "South Indian Bank",
    "DCBL": "DCB Bank",
    "KARB": "Karnataka Bank",
    "KVBL": "Karur Vysya Bank",
    "TMBL": "Tamilnad Mercantile Bank",
    "CSBK": "CSB Bank",
    "ESFB": "Equitas Small Finance Bank",
    "AUBL": "AU Small Finance Bank",
    "UTKS": "Utkarsh Small Finance Bank",
    "USFB": "Ujjivan Small Finance Bank",
    "JSFB": "Jana Small Finance Bank",
    "SUYB": "Suryoday Small Finance Bank",
    "FINO": "Fino Payments Bank",
    "AIRP": "Airtel Payments Bank",
    "IPOS": "India Post Payments Bank",
    "PYTM": "Paytm Payments Bank",
}


@router.get("/bank-concentration", response_model=List[BankConcentration])
async def get_bank_concentration(
    target_date: date = Query(..., alias="date"),
    limit: int = Query(20, ge=1, le=100),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Top banks holding mule accounts — sourced from `lien_accounts.bank_name`.
    This is the table every case populates when an account is frozen, so it
    reflects real coverage. (We previously read from money_transfers.bank
    but that table is only populated when a bank Excel is uploaded, which
    is rare — the chart looked empty even when real data existed.)

    Companion to /destination-bank-concentration, which derives the
    DESTINATION bank from money_transfers.ifsc_code prefix. The two charts
    answer different questions: this one ranks freeze-coordination
    priorities; the other ranks follow-on-freeze priorities.

    The `transaction_count` response field is overloaded here to mean
    'number of frozen accounts at this bank' — schema is unchanged so the
    frontend keeps using the existing card."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    q = (
        select(
            LienAccount.bank_name,
            func.count(LienAccount.id).label("cnt"),
            func.coalesce(func.sum(LienAccount.amount_lien_marked), 0).label("total"),
        )
        .join(Case, LienAccount.case_id == Case.id)
        .where(LienAccount.bank_name.is_not(None))
        .where(func.length(func.trim(LienAccount.bank_name)) > 0)
        .where(func.date(LienAccount.created_at) <= target_date)
        .group_by(LienAccount.bank_name)
        .order_by(func.count(LienAccount.id).desc())
        .limit(limit)
    )
    if admin.role != "super_admin":
        q = q.where(Case.unit_id == admin.unit_id)
    rows = (await db.execute(q)).all()
    return [
        BankConcentration(bank=(b or "").strip() or "(unknown)",
                          transaction_count=int(c),
                          total_amount=float(t or 0))
        for b, c, t in rows
    ]


@router.get("/destination-bank-concentration", response_model=List[BankConcentration])
async def get_destination_bank_concentration(
    target_date: date = Query(..., alias="date"),
    limit: int = Query(20, ge=1, le=100),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Banks holding 'downstream' frozen accounts — `lien_accounts` rows
    with layer > 1. These are accounts the money was moved INTO after the
    initial victim transfer, so the banks hosting them are the destinations
    in the laundering chain.

    We previously derived destination from money_transfers.ifsc_code, but
    that table is only populated when a bank shares an Excel — rare in
    practice. Switching the source to lien_accounts.layer > 1 reuses the
    data investigators already capture for every case.

    The `_IFSC_TO_BANK` lookup is kept in this module for the day we
    revive IFSC-based destination derivation as a secondary signal."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    q = (
        select(
            LienAccount.bank_name,
            func.count(LienAccount.id),
            func.coalesce(func.sum(LienAccount.amount_lien_marked), 0),
        )
        .join(Case, LienAccount.case_id == Case.id)
        .where(LienAccount.bank_name.is_not(None))
        .where(func.length(func.trim(LienAccount.bank_name)) > 0)
        .where(LienAccount.layer.is_not(None))
        .where(LienAccount.layer > 1)
        .where(func.date(LienAccount.created_at) <= target_date)
        .group_by(LienAccount.bank_name)
        .order_by(func.count(LienAccount.id).desc())
        .limit(limit)
    )
    if admin.role != "super_admin":
        q = q.where(Case.unit_id == admin.unit_id)
    rows = (await db.execute(q)).all()

    return [
        BankConcentration(
            bank=(b or "").strip() or "(unknown)",
            transaction_count=int(c),
            total_amount=float(t or 0),
        )
        for b, c, t in rows
    ]


@router.get("/atm-hotspots", response_model=List[AtmHotspot])
async def get_atm_hotspots(
    target_date: date = Query(..., alias="date"),
    limit: int = Query(20, ge=1, le=100),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """ATM locations that appear most often in cash-out (atm_withdrawals).
    Each row is a candidate hotspot for ground-level surveillance."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    q = (
        select(
            AtmWithdrawal.atm_location,
            func.count(AtmWithdrawal.id).label("cnt"),
            func.coalesce(func.sum(AtmWithdrawal.withdrawal_amount), 0).label("total"),
        )
        .join(MuleReport, AtmWithdrawal.report_id == MuleReport.id)
        .where(AtmWithdrawal.atm_location.is_not(None))
        .where(func.date(AtmWithdrawal.created_at) <= target_date)
        .group_by(AtmWithdrawal.atm_location)
        .order_by(func.count(AtmWithdrawal.id).desc())
        .limit(limit)
    )
    if admin.role != "super_admin":
        q = q.where(MuleReport.unit_id == admin.unit_id)
    rows = (await db.execute(q)).all()
    return [
        AtmHotspot(location=(loc or "").strip() or "(unknown)",
                   withdrawal_count=int(c),
                   total_amount=float(t or 0))
        for loc, c, t in rows
    ]


@router.get("/layer-distribution", response_model=List[LayerBucket])
async def get_layer_distribution(
    target_date: date = Query(..., alias="date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Distribution of lien_accounts.layer — how deep the money trail goes.
    A heavy right tail = more sophisticated laundering chains."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    q = (
        select(LienAccount.layer, func.count(LienAccount.id).label("cnt"))
        .join(Case, LienAccount.case_id == Case.id)
        .where(func.date(LienAccount.created_at) <= target_date)
        .where(LienAccount.layer.is_not(None))
        .group_by(LienAccount.layer)
        .order_by(LienAccount.layer)
    )
    if admin.role != "super_admin":
        q = q.where(Case.unit_id == admin.unit_id)
    rows = (await db.execute(q)).all()
    return [LayerBucket(layer=int(layer or 0), count=int(c)) for layer, c in rows]


@router.get("/accounts-at-layer", response_model=List[LienAccountAtLayer])
async def get_accounts_at_layer(
    target_date: date = Query(..., alias="date"),
    layer: int = Query(..., ge=1, le=50),
    limit: int = Query(200, ge=1, le=500),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Lien-account rows at a specific layer — drives the layer-distribution
    drill-down. Ordered by amount_lien_marked DESC so the largest entries
    surface first. Admin scoping mirrors the rest of the dashboard."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    q = (
        select(
            LienAccount.id,
            LienAccount.account_no,
            LienAccount.bank_name,
            LienAccount.amount_lien_marked,
            LienAccount.layer,
            Case.id,
            Case.fir_no,
            Case.petition_no,
            Case.registration_date,
            Unit.name.label("district"),
            PoliceStation.station_name.label("ps_name"),
        )
        .select_from(LienAccount)
        .join(Case, LienAccount.case_id == Case.id)
        .join(Unit, Unit.id == Case.unit_id)
        .join(User, User.id == Case.submitted_by, isouter=True)
        .join(PoliceStation, PoliceStation.id == User.ps_id, isouter=True)
        .where(LienAccount.layer == layer)
        .where(func.date(LienAccount.created_at) <= target_date)
        .order_by(LienAccount.amount_lien_marked.desc())
        .limit(limit)
    )
    if admin.role != "super_admin":
        q = q.where(Case.unit_id == admin.unit_id)
    rows = (await db.execute(q)).all()
    return [
        LienAccountAtLayer(
            lien_id=str(lid),
            account_no=acc or "",
            bank_name=bank,
            amount_lien_marked=float(amt or 0),
            layer=int(lyr) if lyr is not None else 0,
            case_id=str(cid),
            fir_no=fir,
            petition_no=pet,
            registration_date=reg.isoformat() if reg else None,
            district=district or "",
            ps_name=ps,
        )
        for lid, acc, bank, amt, lyr, cid, fir, pet, reg, district, ps in rows
    ]


# ── Disposal & Trial tab ────────────────────────────────────────────────────


def _latest_dsr_subquery(target_date: date):
    """Latest DSR per (unit, ps) on or before `target_date`. Used as a
    join target so we read only the most recent snapshot per PS, not
    the whole history. Grouping is per (unit_id, ps_id) since migration
    008 — before that DSR was a per-unit filing."""
    return (
        select(
            DsrEntry.unit_id,
            DsrEntry.ps_id,
            func.max(DsrEntry.report_date).label("max_date"),
        )
        .where(DsrEntry.report_date <= target_date)
        .group_by(DsrEntry.unit_id, DsrEntry.ps_id)
        .subquery()
    )


@router.get("/disposal-summary", response_model=DisposalSummary)
async def get_disposal_summary(
    target_date: date = Query(..., alias="date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Sum of disposal columns across the latest DSR per unit (since 1 Jan 2026
    per the DSR form's semantics)."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    sub = _latest_dsr_subquery(target_date)
    q = (
        select(
            func.coalesce(func.sum(DsrEntry.disposed_detected_chargesheeted), 0),
            func.coalesce(func.sum(DsrEntry.disposed_transferred), 0),
            func.coalesce(func.sum(DsrEntry.disposed_false), 0),
            func.coalesce(func.sum(DsrEntry.disposed_undetected), 0),
        )
        .join(sub, and_(
            DsrEntry.unit_id == sub.c.unit_id,
            DsrEntry.ps_id == sub.c.ps_id,
            DsrEntry.report_date == sub.c.max_date,
        ))
    )
    if admin.role != "super_admin":
        q = q.where(DsrEntry.unit_id == admin.unit_id)
    row = (await db.execute(q)).one_or_none()
    if not row:
        return DisposalSummary()
    detected, transferred, false_cases, undetected = row
    return DisposalSummary(
        detected=int(detected or 0),
        transferred=int(transferred or 0),
        false_cases=int(false_cases or 0),
        undetected=int(undetected or 0),
    )


@router.get("/trial-summary", response_model=TrialSummary)
async def get_trial_summary(
    target_date: date = Query(..., alias="date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Sum of trial-outcome columns across the latest DSR per unit (from 1 Jan 2026)."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    sub = _latest_dsr_subquery(target_date)
    q = (
        select(
            func.coalesce(func.sum(DsrEntry.trial_convicted), 0),
            func.coalesce(func.sum(DsrEntry.trial_discharged), 0),
            func.coalesce(func.sum(DsrEntry.trial_acquitted), 0),
            func.coalesce(func.sum(DsrEntry.trial_abated), 0),
            func.coalesce(func.sum(DsrEntry.trial_compounded), 0),
            func.coalesce(func.sum(DsrEntry.trial_ut), 0),
        )
        .join(sub, and_(
            DsrEntry.unit_id == sub.c.unit_id,
            DsrEntry.ps_id == sub.c.ps_id,
            DsrEntry.report_date == sub.c.max_date,
        ))
    )
    if admin.role != "super_admin":
        q = q.where(DsrEntry.unit_id == admin.unit_id)
    row = (await db.execute(q)).one_or_none()
    if not row:
        return TrialSummary()
    conv, disc, acq, ab, comp, ut = row
    return TrialSummary(
        convicted=int(conv or 0),
        discharged=int(disc or 0),
        acquitted=int(acq or 0),
        abated=int(ab or 0),
        compounded=int(comp or 0),
        under_trial=int(ut or 0),
    )


@router.get("/pending-by-year", response_model=List[PendingByYearRow])
async def get_pending_by_year(
    target_date: date = Query(..., alias="date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Per-unit UI-cases-pending breakdown by year, from each unit's latest DSR."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    # Latest DSR is per (unit, ps) after migration 008. For the
    # district-level pending-years view we SUM across the PSes in
    # each district so operators still see one row per unit.
    sub = _latest_dsr_subquery(target_date)
    q = (
        select(
            Unit.name,
            func.coalesce(func.sum(DsrEntry.ui_cases_pending_2021), 0),
            func.coalesce(func.sum(DsrEntry.ui_cases_pending_2022), 0),
            func.coalesce(func.sum(DsrEntry.ui_cases_pending_2023), 0),
            func.coalesce(func.sum(DsrEntry.ui_cases_pending_2024), 0),
            func.coalesce(func.sum(DsrEntry.ui_cases_pending_2025), 0),
            func.coalesce(func.sum(DsrEntry.ui_cases_pending_2026), 0),
        )
        .join(sub, and_(
            DsrEntry.unit_id == sub.c.unit_id,
            DsrEntry.ps_id == sub.c.ps_id,
            DsrEntry.report_date == sub.c.max_date,
        ))
        .join(Unit, Unit.id == DsrEntry.unit_id)
        .group_by(Unit.name)
    )
    if admin.role != "super_admin":
        q = q.where(DsrEntry.unit_id == admin.unit_id)
    rows = (await db.execute(q)).all()

    out = [
        PendingByYearRow(
            unit_name=name,
            y2021=int(y21 or 0), y2022=int(y22 or 0), y2023=int(y23 or 0),
            y2024=int(y24 or 0), y2025=int(y25 or 0), y2026=int(y26 or 0),
        )
        for name, y21, y22, y23, y24, y25, y26 in rows
    ]
    # Heaviest backlog first
    out.sort(key=lambda r: -(r.y2021 + r.y2022 + r.y2023 + r.y2024 + r.y2025 + r.y2026))
    return out
