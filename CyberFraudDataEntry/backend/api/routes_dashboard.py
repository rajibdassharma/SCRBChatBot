from __future__ import annotations

from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import bindparam, case, select, func, and_, text, true as sa_true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models.case import Case
from models.arrest import Arrest
from models.lien_account import LienAccount
from models.unfreeze_detail import UnfreezeDetail
from models.refund import Refund
from models.petition import Petition
from models.dsr_entry import DsrEntry
from models.nil_declaration import NilDeclaration
from models.statement_transaction import StatementTransaction
from models.account_statement_summary import AccountStatementSummary
from models.upload_ledger import UploadLedger
from models.mule_entry import MuleEntry
from models.mule_report import MuleReport
from models.money_transfer import MoneyTransfer
from models.atm_withdrawal import AtmWithdrawal
from models.aeps_transaction import AepsTransaction
from models.all_account import AllAccount, ACCOUNT_TYPES
from models.crypto_txn import CryptoTxn
from models.id_photo_hash import IdPhotoHash
from models.all_account_mule_herder import AllAccountMuleHerder
from models.victim import Victim
from models.victim_account import VictimAccount
from models.accused_account import AccusedAccount
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
    AccountsKpiSummary, AccountsPsComparison, AccountsBankConcentration,
    AccountsGeoRegion,
    AccountsDailyPoint, AccountsLayerDistribution,
    AccountsFirTrace, FirTraceCase, FirTraceAccount, FirTraceFlow,
    FirPsPerformanceRow, FirDailyPoint,
    FirCrimeTypeReport, FirCrimeTypeRow, FirCrimeOther, FirCrimeDistrictCell,
    FirPsCrimeCount,
    DuplicateIdSummary, DuplicateIdCluster, DuplicateIdMember,
    MuleNetworkSummary, MuleNetworkRow, MuleLinkPeer,
    StatementCoverageSummary, StatementCoverageRow,
    MoneyTrailSummary, StatementQualityRow, StatementChannelRow,
    MuleAccountList, MuleAccountRow,
    StatementAccountRow, SharedCounterparty,
    NcrpKpiSummary, NcrpPsReportCount, NcrpBankConcentration, NcrpAtmLocation,
    RepeatAccount, AccountFirOccurrence,
    CryptoTrailSummary, CryptoExchangeRow, CryptoAccountRow, CryptoEvidenceRow,
)
from schemas.all_account import AllAccountResponse, MuleHerderOut
from schemas.portals_dsr import PortalsDsrKpiSummary, PortalsDsrPsComparison
from auth.upload_signing import sign_path
from api.deps import require_admin, CurrentUser
from api.test_scope import (
    where_not_test, exclude_test_ps, exclude_test_unit,
    exclude_test_station_row, exclude_test_unit_row,
    station_row_filter, viewer_is_test,
)
from models.portals_dsr_entry import PortalsDsrEntry

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
    # Test fixture never appears in a dashboard figure.
    q = where_not_test(q, admin, exclude_test_unit(MuleReport.unit_id))
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
    limit: int = Query(2000, ge=1, le=5000),
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
    # Test fixture never appears in a dashboard figure.
    q = where_not_test(q, admin, exclude_test_unit(Case.unit_id))

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
    # Test fixture never appears in a dashboard figure.
    q = where_not_test(q, admin, exclude_test_unit(Case.unit_id))

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
    # Test fixture never appears in a dashboard figure.
    q = where_not_test(q, admin, exclude_test_unit(Case.unit_id))
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
    # Test fixture never appears in a dashboard figure.
    q = where_not_test(q, admin, exclude_test_unit(Case.unit_id))
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
    # Test fixture never appears in a dashboard figure.
    q = where_not_test(q, admin, exclude_test_unit(MuleReport.unit_id))
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
    # Test fixture never appears in a dashboard figure.
    q = where_not_test(q, admin, exclude_test_unit(Case.unit_id))
    rows = (await db.execute(q)).all()
    return [LayerBucket(layer=int(layer or 0), count=int(c)) for layer, c in rows]


@router.get("/accounts-at-layer", response_model=List[LienAccountAtLayer])
async def get_accounts_at_layer(
    target_date: date = Query(..., alias="date"),
    layer: int = Query(..., ge=1, le=50),
    limit: int = Query(5000, ge=1, le=20000),
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
    # Test fixture never appears in a dashboard figure.
    q = where_not_test(q, admin, exclude_test_unit(Case.unit_id))
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
    # Test fixture never appears in a dashboard figure.
    q = where_not_test(q, admin, exclude_test_unit(DsrEntry.unit_id))
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
    # Test fixture never appears in a dashboard figure.
    q = where_not_test(q, admin, exclude_test_unit(DsrEntry.unit_id))
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
    # Test fixture never appears in a dashboard figure.
    q = where_not_test(q, admin, exclude_test_unit(DsrEntry.unit_id))
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


# ════════════════════════════════════════════════════════════════
# ── Accounts dashboard (All Accounts feature, 2026-07-18) ──────
# Same scoping as DSR: admin sees own PS, super_admin sees all.
# ════════════════════════════════════════════════════════════════


def _scope_accounts(query, current: CurrentUser):
    if current.role == "super_admin":
        return query
    if not current.unit_id or not current.ps_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to a Police Station.")
    return query.where(
        AllAccount.unit_id == current.unit_id,
        AllAccount.ps_id == current.ps_id,
    )


@router.get("/accounts-summary", response_model=AccountsKpiSummary)
async def get_accounts_summary(
    target_date: date = Query(..., alias="date", description="Cumulative cutoff — include accounts created on or before this date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Cumulative account-level KPIs as of `date`. Mirrors the shape
    of /summary but populated from all_accounts + its child rows."""
    base = _scope_accounts(select(AllAccount), admin).where(
        func.date(AllAccount.created_at) <= target_date
    )

    total_accounts = (await db.execute(
        _scope_accounts(select(func.count(AllAccount.id)), admin)
        .where(func.date(AllAccount.created_at) <= target_date)
    )).scalar() or 0

    victim_accounts = (await db.execute(
        _scope_accounts(select(func.count(AllAccount.id)), admin)
        .where(func.date(AllAccount.created_at) <= target_date)
        .where(AllAccount.account_type == "Victim")
    )).scalar() or 0

    mule_accounts = (await db.execute(
        _scope_accounts(select(func.count(AllAccount.id)), admin)
        .where(func.date(AllAccount.created_at) <= target_date)
        .where(AllAccount.account_type == "Mule")
    )).scalar() or 0

    # KA-branch subset of mule_accounts. branch_state was added by
    # migration 012 -- older rows are NULL and won't be counted, which
    # matches operator intent (unknown state != confirmed KA).
    karnataka_mule_accounts = (await db.execute(
        _scope_accounts(select(func.count(AllAccount.id)), admin)
        .where(func.date(AllAccount.created_at) <= target_date)
        .where(AllAccount.account_type == "Mule")
        .where(AllAccount.branch_state == "Karnataka")
    )).scalar() or 0

    non_mule_accounts = (await db.execute(
        _scope_accounts(select(func.count(AllAccount.id)), admin)
        .where(func.date(AllAccount.created_at) <= target_date)
        .where(AllAccount.account_type == "Non-Mule")
    )).scalar() or 0

    unique_banks = (await db.execute(
        _scope_accounts(select(func.count(func.distinct(AllAccount.bank_name))), admin)
        .where(func.date(AllAccount.created_at) <= target_date)
    )).scalar() or 0

    # Distinct mule herder names (across accounts scoped to caller).
    herder_q = (
        select(func.count(func.distinct(AllAccountMuleHerder.name)))
        .join(AllAccount, AllAccountMuleHerder.account_id == AllAccount.id)
        .where(func.date(AllAccountMuleHerder.created_at) <= target_date)
    )
    if admin.role != "super_admin":
        herder_q = herder_q.where(
            AllAccount.unit_id == admin.unit_id,
            AllAccount.ps_id == admin.ps_id,
        )
    # Test fixture never appears in a dashboard figure.
    herder_q = where_not_test(herder_q, admin, exclude_test_unit(AllAccount.unit_id), exclude_test_ps(AllAccount.ps_id))
    unique_mule_herders = (await db.execute(herder_q)).scalar() or 0

    accounts_with_photo = (await db.execute(
        _scope_accounts(select(func.count(AllAccount.id)), admin)
        .where(func.date(AllAccount.created_at) <= target_date)
        .where(AllAccount.id_photo_path.is_not(None))
        .where(AllAccount.id_photo_path != "")
    )).scalar() or 0

    if admin.role == "super_admin":
        units_submitted = (await db.execute(
            select(func.count(func.distinct(AllAccount.ps_id)))
            .where(func.date(AllAccount.created_at) <= target_date)
        )).scalar() or 0
        units_total = (await db.execute(
            select(func.count(PoliceStation.id))
        )).scalar() or 0
    else:
        units_submitted = 1 if total_accounts > 0 else 0
        units_total = 1
    _ = base  # keep for reader — base isn't executed directly

    return AccountsKpiSummary(
        total_accounts=int(total_accounts),
        victim_accounts=int(victim_accounts),
        mule_accounts=int(mule_accounts),
        non_mule_accounts=int(non_mule_accounts),
        karnataka_mule_accounts=int(karnataka_mule_accounts),
        unique_banks=int(unique_banks),
        unique_mule_herders=int(unique_mule_herders),
        accounts_with_photo=int(accounts_with_photo),
        units_submitted=int(units_submitted),
        units_total=int(units_total),
    )


async def compute_accounts_comparison(
    db: AsyncSession,
    *,
    target_date: date,
    admin: CurrentUser,
) -> List[AccountsPsComparison]:
    """Per-PS rollup for the Account Details dashboard.

    Sourced from `all_accounts`, cumulative as of `target_date`
    (inclusive). Adds a `yesterday_count` per row = accounts created
    on the calendar day BEFORE `target_date`, so the on-screen table
    can show a "last 24 hours" column alongside the cumulative Total.

    Every active police station appears, even when it has zero
    accounts on the target date (2026-07-27) -- silent PSes need to
    stay visible so operators can see who hasn't reported. The join
    is driven by `police_stations` LEFT JOIN `all_accounts`, so
    zero-count rows come back with total=0 across every metric.

    Shared by the JSON /accounts-comparison route and the PDF + XLSX
    report routes so all three reflect identical numbers."""
    yesterday = target_date - timedelta(days=1)

    # LEFT JOIN driven by police_stations so every active PS surfaces.
    # The `and_` on the join predicate is critical -- moving the date
    # filter into a WHERE clause would filter OUT PSes that have zero
    # accounts on that date (turning the LEFT JOIN into an INNER).
    from sqlalchemy import and_

    q = (
        select(
            PoliceStation.id.label("ps_id"),
            PoliceStation.station_name.label("ps_name"),
            Unit.id.label("unit_id"),
            Unit.name.label("unit_name"),
            func.coalesce(func.count(AllAccount.id), 0).label("total"),
            func.coalesce(func.sum(
                case((func.date(AllAccount.created_at) == yesterday, 1), else_=0)
            ), 0).label("yesterday_count"),
            func.coalesce(func.sum(
                case((AllAccount.account_type == "Victim", 1), else_=0)
            ), 0).label("victims"),
            func.coalesce(func.sum(
                case((AllAccount.account_type == "Mule", 1), else_=0)
            ), 0).label("mules"),
            func.coalesce(func.sum(
                case((AllAccount.account_type == "Non-Mule", 1), else_=0)
            ), 0).label("non_mules"),
        )
        .join(Unit, Unit.name == PoliceStation.district_name)
        .outerjoin(
            AllAccount,
            and_(
                AllAccount.ps_id == PoliceStation.id,
                func.date(AllAccount.created_at) <= target_date,
            ),
        )
        .where(PoliceStation.is_active == True)  # noqa: E712
        # Test fixture is a real, active station — drop it from the
        # station LIST too, or it appears as a permanent zero row.
        .where(station_row_filter(admin))
        .group_by(
            PoliceStation.id, PoliceStation.station_name,
            Unit.id, Unit.name,
        )
        .order_by(func.count(AllAccount.id).desc(), PoliceStation.station_name.asc())
    )
    if admin.role != "super_admin":
        q = q.where(PoliceStation.id == admin.ps_id)

    rows = (await db.execute(q)).all()
    return [
        AccountsPsComparison(
            unit_id=r.unit_id,
            unit_name=r.unit_name,
            ps_id=r.ps_id,
            ps_name=r.ps_name,
            total=int(r.total or 0),
            yesterday_count=int(r.yesterday_count or 0),
            victims=int(r.victims or 0),
            mules=int(r.mules or 0),
            non_mules=int(r.non_mules or 0),
        )
        for r in rows
    ]


@router.get("/accounts-comparison", response_model=List[AccountsPsComparison])
async def get_accounts_comparison(
    target_date: date = Query(..., alias="date", description="Cumulative cutoff — include accounts created on or before this date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """One row per PS. admin sees just their own PS; super_admin sees
    every PS that has at least one account."""
    return await compute_accounts_comparison(db, target_date=target_date, admin=admin)


# Geographic scopes the map view can group by. Kept as an explicit
# whitelist rather than accepting a column name from the query string —
# the value picks a SQLAlchemy column below, so letting the client name
# it would be a straightforward injection of our own choosing.
_GEO_SCOPES = {"state", "district", "reporting"}


@router.get("/duplicate-ids", response_model=DuplicateIdSummary)
async def get_duplicate_ids(
    min_accounts: int = Query(2, ge=2, le=50),
    limit: int = Query(2000, ge=1, le=5000,
        description="Max clusters. 50 hid 193 of 243 real clusters; the client also warns if this is reached."),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Accounts whose uploaded ID photo is the SAME FILE (F1).

    super_admin only, and deliberately so. The entire value of this
    view is that a cluster spans police stations — a station-level
    admin seeing another district's accounts would breach the VAPT
    7.7/7.8 scoping rule that every other cross-PS surface (Repeat
    Accounts, Deep Analysis) already respects.

    The match is SHA-256 of the file bytes. Nothing is read OUT of the
    image: no name, no Aadhaar number, no date of birth. That keeps the
    finding clear of identity-extraction questions entirely.

    It clusters on SHA-256 rather than the perceptual hash, and that
    choice was forced by being wrong the first time. Clustering on a
    64-bit dHash produced two headline clusters of 28 and 23 documents;
    both were false — 28 and 23 distinct files, 28 and 23 different
    holder names. The dHash had matched the Aadhaar LAYOUT, not the
    document, because ID cards are near-identical by design. Exact file
    identity cannot fail that way: same bytes means the same upload.

    The 24x24 dHash is still stored, and does separate those cases
    correctly, but near-duplicate search is O(n^2) over ~10.7k images
    and belongs in an offline pass, not in a request. When that lands
    it arrives as match_type="similar" alongside these.

    Only rows already in id_photo_hashes are considered — populated by
    analysis/hash_id_photos.py, not computed here. This endpoint is a
    read over pre-computed fingerprints and stays fast.
    """
    if admin.role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Duplicate ID analysis is available to SCRB HQ accounts only.",
        )

    # Fetch ONLY rows that belong to a multi-account cluster. The
    # subquery keeps this proportional to the finding (~1.3k rows on
    # the current corpus) rather than to the whole table.
    q = (
        select(
            IdPhotoHash.file_sha256,
            IdPhotoHash.file_path,
            IdPhotoHash.account_id,
            AllAccount.account_holder_name,
            AllAccount.account_no,
            AllAccount.fir_no,
            AllAccount.account_type,
            AllAccount.bank_name,
            Unit.name.label("district"),
            PoliceStation.station_name.label("ps_name"),
        )
        .select_from(IdPhotoHash)
        .join(AllAccount, AllAccount.id == IdPhotoHash.account_id)
        .outerjoin(Unit, Unit.id == AllAccount.unit_id)
        .outerjoin(PoliceStation, PoliceStation.id == AllAccount.ps_id)
        .where(IdPhotoHash.file_sha256.in_(
            select(IdPhotoHash.file_sha256)
            .group_by(IdPhotoHash.file_sha256)
            .having(func.count(func.distinct(IdPhotoHash.account_id)) >= min_accounts)
        ))
    )
    q = where_not_test(q, admin,
                       exclude_test_unit(AllAccount.unit_id),
                       exclude_test_ps(AllAccount.ps_id))
    rows = (await db.execute(q)).all()

    total_hashed = (await db.execute(
        select(func.count(IdPhotoHash.id))
    )).scalar() or 0

    grouped: dict[str, list] = {}
    for r in rows:
        grouped.setdefault(r.file_sha256, []).append(r)

    clusters: List[DuplicateIdCluster] = []
    for fp, members in grouped.items():
        accounts = {m.account_id for m in members}
        if len(accounts) < min_accounts:
            continue
        holders = {(m.account_holder_name or "").strip().lower()
                   for m in members if (m.account_holder_name or "").strip()}
        types = sorted({m.account_type for m in members if m.account_type})
        clusters.append(DuplicateIdCluster(
            fingerprint=fp,
            match_type="exact",
            # Every member IS byte-for-byte the same file, so the first
            # is representative in the strictest sense. Signed with the
            # same 1-hour HMAC scheme the rest of /uploads/* uses — no
            # new access path.
            image_url=sign_path(members[0].file_path),
            images=len(members),
            accounts=len(accounts),
            distinct_holders=len(holders),
            distinct_account_nos=len({(m.account_no or "").strip()
                                      for m in members if (m.account_no or "").strip()}),
            distinct_firs=len({m.fir_no for m in members if m.fir_no}),
            distinct_ps=len({m.ps_name for m in members if m.ps_name}),
            distinct_districts=len({m.district for m in members if m.district}),
            has_victim="Victim" in types,
            account_types=types,
            members=[DuplicateIdMember(
                account_id=m.account_id,
                account_holder_name=m.account_holder_name,
                account_no=m.account_no,
                fir_no=m.fir_no,
                account_type=m.account_type,
                district=m.district,
                ps_name=m.ps_name,
                bank_name=m.bank_name,
            ) for m in members],
        ))

    # Rank by SPREAD, not size, and push victim-bearing clusters down.
    # A network does not recruit the people it defrauds, so a cluster
    # containing Victim accounts reads as a placeholder image — on the
    # current corpus the single largest cluster is exactly that, and
    # left unranked it would sit at the top of the screen and teach
    # officers the feature is noise.
    #
    # The lead term is the WEAKER of {distinct account numbers, distinct
    # holder names}, not either one alone, because identity reuse needs
    # both and each is innocuous by itself. Two real cases from this
    # corpus forced that, one for each half:
    #
    #   names alone   — one file, three FIRs, three districts, names
    #                   "M/S. GREEN AURA ENTERPRISES" / "Karan" /
    #                   "Karan s/o manoj", all on ONE account number at
    #                   one bank. One mule account complained about in
    #                   three districts, with the name typed three ways.
    #   numbers alone — one file, six accounts, six account numbers, ONE
    #                   name. A person's own six accounts.
    #
    # min() of the two ranks both of those below a cluster with four
    # names on four different account numbers, which is the real thing.
    clusters.sort(
        key=lambda c: (
            0 if c.has_victim else 1,
            min(c.distinct_account_nos, c.distinct_holders, 50),
            min(c.distinct_ps, 20),
            min(c.distinct_districts, 20),
            min(c.distinct_account_nos, 50),
            c.distinct_firs,
        ),
        reverse=True,
    )

    return DuplicateIdSummary(
        total_hashed=int(total_hashed),
        clusters=len(clusters),
        with_multiple_holders=sum(1 for c in clusters if c.distinct_holders >= 2),
        across_police_stations=sum(1 for c in clusters if c.distinct_ps >= 2),
        across_firs=sum(1 for c in clusters if c.distinct_firs >= 2),
        # "Strong" means the innocent explanations are exhausted: one
        # file, 2+ DIFFERENT account numbers, 2+ different holder names.
        # Both halves are load-bearing. Different names on ONE account
        # number is an operator typing the same person three ways;
        # different account numbers under ONE name is one person's own
        # accounts. Only both together say "this document was used to
        # open accounts for people it does not belong to".
        #
        # Note what is NOT required: cross-station spread. An earlier
        # definition demanded 2+ police stations, on the reasoning that
        # spread is hardest to explain innocently. It scored the real
        # top finding at zero — one ID file behind SEVEN accounts, seven
        # names and seven account numbers, all inside a single station.
        # A mule farm run by one recruiter sits in one station, and that
        # is not a weaker case, only a narrower one. Station spread is
        # its own KPI (across_police_stations) rather than a gate here.
        strong_signal=sum(1 for c in clusters
                          if c.distinct_account_nos >= 2
                          and c.distinct_holders >= 2
                          and not c.has_victim),
        rows=clusters[:limit],
    )


#: Handle fragments belonging to payment infrastructure rather than to
#: a person or a business. These are the rails — bill-payment
#: aggregators, card switches, wallet PSPs — so they are paid by
#: virtually every account and carry no investigative signal.
#:
#: Substring match on the UPI handle, deliberately loose: PSPs mint
#: per-merchant handles (bbpsbp@ybl, bbpsbp@ax) and matching the stem
#: catches the family. A false positive here costs one row on a
#: leaderboard; a false negative fills the top of the panel with noise.
#: Accepted values for the Money Trail state filter.
_MT_SCOPES = {"all", "karnataka", "other"}

_PAYMENT_INFRA = (
    "bbps", "billdesk", "euronet", "razorpay", "payu", "ccavenue",
    "cashfree", "billpay", "npci", "upiswitch", "atomtech", "worldline",
    "pinelabs", "phonepe", "paytm-", "gpay", "googlepay", "okpay",
)


#: Accepted values for the Statement Coverage status filter.
_COVERAGE_STATUS = {"all", "missing", "unparsed", "unreadable", "parsed"}

#: Believable window for an FIR registration date, used only for
#: ageing. `cases.registration_date` in this corpus runs from 0001-01-01
#: to 2028-07-28 — both ends are data-entry noise, and a row aged from
#: the year 1 would sit permanently at the top of a work list sorted by
#: how long the gap has been open.
_FIR_DATE_MIN = date(2015, 1, 1)


@router.get("/statement-coverage", response_model=StatementCoverageSummary)
async def get_statement_coverage(
    state_scope: str = Query("all", description="all | karnataka | other"),
    account_type: str = Query("All", description="All | Mule | Non-Mule | Victim"),
    status: str = Query("all",
        description="all | missing | unparsed | unreadable | parsed"),
    limit: int = Query(25000, ge=1, le=30000,
        description="Max rows. 5,000 hid 12,618 of 17,618 accounts."),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Which accounts still have no usable bank statement (F2 coverage).

    super_admin only, matching every other cross-PS surface.

    WHY THIS IS A SEPARATE SCREEN FROM MONEY TRAIL
    ----------------------------------------------
    Money Trail analyses statements that exist. This one is about the
    ones that do not, which is a chasing job rather than an analysis —
    the output is a list to hand a bank nodal officer, so the export is
    the deliverable and the columns are identity and age, not rupees.

    It also exists because the absence was invisible. Money Trail
    showed 4 Karnataka mule accounts and the map showed 744; nothing on
    screen explained that the difference was unparsed uploads rather
    than accounts with no money movement. A dashboard that cannot say
    what it is missing invites exactly that reading.

    FOUR STATES, NOT ONE "MISSING"
    ------------------------------
        missing     no file attached                -> chase the bank
        unparsed    attached, batch job hasn't run  -> clears itself
        unreadable  attached, yielded no rows       -> OCR or parser work
        parsed      transactions extracted

    Lumping these together would put the batch job's own backlog in
    front of an officer as though it were their problem. On the current
    corpus `unparsed` is 90% of everything, and none of it is anyone's
    work.
    """
    if admin.role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Statement coverage is available to SCRB HQ accounts only.")
    if state_scope not in _MT_SCOPES:
        raise HTTPException(status_code=422,
            detail=f"state_scope must be one of: {', '.join(sorted(_MT_SCOPES))}")
    if account_type != "All" and account_type not in ACCOUNT_TYPES:
        raise HTTPException(status_code=422,
            detail=f"account_type must be 'All' or one of: {', '.join(sorted(ACCOUNT_TYPES))}")
    if status not in _COVERAGE_STATUS:
        raise HTTPException(status_code=422,
            detail=f"status must be one of: {', '.join(sorted(_COVERAGE_STATUS))}")

    has_file = and_(AllAccount.account_statement_path.isnot(None),
                    AllAccount.account_statement_path != "")
    # Joined on account_id, which the parser sets from the same basename
    # mapping the upload used. A ledger row with a NULL account_id is an
    # orphan file belonging to no account, and correctly matches nothing
    # here.
    led_status = UploadLedger.status
    status_expr = case(
        (~has_file, "missing"),
        (led_status.is_(None), "unparsed"),
        (led_status.in_(["scanned", "failed", "deferred"]), "unreadable"),
        else_="parsed",
    )

    # One case row per FIR. A plain join fans out — `cases` holds
    # duplicate fir_no values, and joining directly turned 1,415
    # missing-statement accounts into 5,002 rows.
    fir_dates = (
        select(Case.fir_no.label("fir_no"),
               func.min(Case.registration_date).label("rd"))
        .where(Case.registration_date.isnot(None))
        .where(Case.registration_date >= _FIR_DATE_MIN)
        .group_by(Case.fir_no)
        .subquery()
    )

    def scoped(q):
        q = (q.select_from(AllAccount)
              .outerjoin(UploadLedger, UploadLedger.account_id == AllAccount.id)
              .outerjoin(PoliceStation, PoliceStation.id == AllAccount.ps_id)
              .outerjoin(Unit, Unit.id == AllAccount.unit_id))
        q = where_not_test(q, admin,
                           exclude_test_unit(AllAccount.unit_id),
                           exclude_test_ps(AllAccount.ps_id))
        if account_type != "All":
            q = q.where(AllAccount.account_type == account_type)
        st = func.lower(func.trim(func.coalesce(AllAccount.branch_state, "")))
        if state_scope == "karnataka":
            q = q.where(st == "karnataka")
        elif state_scope == "other":
            q = q.where(st != "karnataka").where(st != "")
        return q

    # Counts ignore the STATUS filter on purpose, so the KPI row stays a
    # stable denominator while the user clicks between statuses.
    counts = {k: 0 for k in ("missing", "unparsed", "unreadable", "parsed")}
    verified_parsed = 0
    for st_val, n, ok_n in (await db.execute(scoped(select(
        status_expr.label("st"),
        func.count(AllAccount.id),
        func.coalesce(func.sum(case((led_status == "ok", 1), else_=0)), 0),
    )).group_by(status_expr))).all():
        counts[str(st_val)] = int(n)
        if str(st_val) == "parsed":
            verified_parsed = int(ok_n or 0)

    unstated = 0
    if state_scope != "all":
        q_un = (select(func.count(AllAccount.id)).select_from(AllAccount)
                .outerjoin(PoliceStation, PoliceStation.id == AllAccount.ps_id)
                .where(func.trim(func.coalesce(AllAccount.branch_state, "")) == ""))
        q_un = where_not_test(q_un, admin,
                              exclude_test_unit(AllAccount.unit_id),
                              exclude_test_ps(AllAccount.ps_id))
        if account_type != "All":
            q_un = q_un.where(AllAccount.account_type == account_type)
        unstated = int((await db.execute(q_un)).scalar() or 0)

    q = scoped(select(
        AllAccount.id, AllAccount.account_holder_name, AllAccount.account_no,
        AllAccount.bank_name, AllAccount.fir_no, AllAccount.account_type,
        PoliceStation.station_name, Unit.name,
        func.trim(func.coalesce(AllAccount.branch_state, "")),
        status_expr, UploadLedger.detail, fir_dates.c.rd,
    )).outerjoin(fir_dates, fir_dates.c.fir_no == AllAccount.fir_no)
    if status != "all":
        q = q.where(status_expr == status)
    # Oldest gap first, and NULL ages last in both directions — an
    # unknown age is not a young one.
    q = q.order_by(fir_dates.c.rd.is_(None), fir_dates.c.rd.asc()).limit(limit)

    today = date.today()
    rows = [
        StatementCoverageRow(
            account_id=r[0], account_holder_name=r[1], account_no=r[2],
            bank_name=r[3], fir_no=r[4], account_type=r[5], ps_name=r[6],
            district=r[7], branch_state=r[8] or None, status=str(r[9]),
            detail=r[10], fir_date=r[11],
            days_open=(today - r[11]).days if r[11] else None,
        )
        for r in (await db.execute(q)).all()
    ]

    return StatementCoverageSummary(
        state_scope=state_scope, account_type=account_type, status=status,
        total_accounts=sum(counts.values()),
        missing=counts["missing"], unparsed=counts["unparsed"],
        unreadable=counts["unreadable"], parsed=counts["parsed"],
        parsed_verified=verified_parsed,
        accounts_without_state=unstated,
        rows=rows,
    )


@router.get("/mule-network", response_model=MuleNetworkSummary)
async def get_mule_network(
    cross_fir_only: bool = Query(True,
        description="Only accounts with at least one link to a DIFFERENT FIR"),
    state_scope: str = Query("all", description="all | karnataka | other"),
    limit: int = Query(5000, ge=1, le=20000),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Mule accounts directly connected to other mule accounts (F4).

    super_admin only. The entire value here is that links cross police
    stations and FIRs, so a station-scoped view would be meaningless
    and would breach the VAPT 7.7/7.8 rule besides.

    WHAT A LINK IS
    --------------
    A's parsed bank statement records a transfer to B's account number,
    and both A and B are already recorded in all_accounts as Mule.
    Nothing is inferred. This is deliberately NOT the shared-destination
    signal: two mules paying the same payment gateway are not connected
    in any useful sense, and treating them as connected would link every
    account to every other through BBPS and Amazon.

    Reads mule_account_link, built by analysis/build_links.py. Matching
    a free-text counterparty number against 13,970 mule numbers takes
    ~75,000 indexed lookups and half a minute — not something to do
    behind a page load. See migration 021 for why the normalisation
    cannot be expressed as a SQL join.

    ON THE AMOUNTS
    --------------
    Link COUNTS are sound: counterparty extraction is independent of the
    amount columns that the balance-chain work has yet to clean up. The
    rupee figures are better here than elsewhere by luck rather than
    design — the badly misparsed rows had no counterparty matching a
    mule, so they never became links — but they are still summed from
    unvalidated rows and should be read as indicative.
    """
    if admin.role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Mule network analysis is available to SCRB HQ accounts only.")
    if state_scope not in _MT_SCOPES:
        raise HTTPException(status_code=422,
            detail=f"state_scope must be one of: {', '.join(sorted(_MT_SCOPES))}")

    links = (await db.execute(text("""
        SELECT src_account_id, dst_account_id, txns, total_debit, cross_fir
        FROM mule_account_link"""))).all()
    if not links:
        return MuleNetworkSummary()

    ids = {r[0] for r in links} | {r[1] for r in links}
    q = (select(
            AllAccount.id, AllAccount.account_holder_name, AllAccount.account_no,
            AllAccount.bank_name, AllAccount.fir_no,
            PoliceStation.station_name, PoliceStation.id, Unit.name,
            func.trim(func.coalesce(AllAccount.branch_state, "")),
            # Money-trail depth. Layer 1 is the account the victim paid;
            # each further layer is a hop away from the crime. Carried
            # so the network diagram can colour by it -- the shape of a
            # ring is far easier to read when you can see which end is
            # near the victim and which is the cash-out.
            AllAccount.layer,
         )
         .select_from(AllAccount)
         .outerjoin(PoliceStation, PoliceStation.id == AllAccount.ps_id)
         .outerjoin(Unit, Unit.id == AllAccount.unit_id)
         .where(AllAccount.id.in_(ids)))
    q = where_not_test(q, admin,
                       exclude_test_unit(AllAccount.unit_id),
                       exclude_test_ps(AllAccount.ps_id))
    info = {r[0]: r for r in (await db.execute(q)).all()}

    def in_scope(aid: str) -> bool:
        r = info.get(aid)
        if r is None:
            return False           # filtered out by test-station scoping
        st = (r[8] or "").strip().lower()
        if state_scope == "karnataka":
            return st == "karnataka"
        if state_scope == "other":
            return st not in ("karnataka", "")
        return True

    # Accumulate both directions onto each account. A transfer is
    # recorded once, on the payer's statement; the receiver needs to see
    # it too, so each link is read from both ends.
    agg: dict = {}

    def bucket(aid):
        return agg.setdefault(aid, {"peers": {}, "txns": 0, "amt": 0.0,
                                    "out": 0, "in": 0, "cross": set()})

    for src, dst, n, amt, xf in links:
        n, amt, xf = int(n), float(amt or 0), bool(xf)
        for me, other, direction in ((src, dst, "out"), (dst, src, "in")):
            if not in_scope(me) or other not in info:
                continue
            b = bucket(me)
            b["txns"] += n
            b["amt"] += amt
            b["out" if direction == "out" else "in"] += 1
            if xf:
                b["cross"].add(other)
            o = info[other]
            b["peers"][(other, direction)] = MuleLinkPeer(
                account_id=other, account_holder_name=o[1], account_no=o[2],
                bank_name=o[3], fir_no=o[4], ps_name=o[5],
                direction=direction, cross_fir=xf, txns=n, amount=amt)

    rows: List[MuleNetworkRow] = []
    for aid, b in agg.items():
        peers = list(b["peers"].values())
        connected = len({p.account_id for p in peers})
        cross = len(b["cross"])
        if cross_fir_only and cross == 0:
            continue
        r = info[aid]
        peers.sort(key=lambda p: (-int(p.cross_fir), -p.amount))
        rows.append(MuleNetworkRow(
            account_id=aid, account_holder_name=r[1], account_no=r[2],
            bank_name=r[3], fir_no=r[4], ps_name=r[5], ps_id=r[6],
            district=r[7], branch_state=r[8] or None,
            layer=r[9],
            connected=connected, cross_fir=cross,
            out_links=b["out"], in_links=b["in"],
            txns=b["txns"], amount=b["amt"], peers=peers))

    # Cross-FIR reach first: a mule wired to six accounts inside its own
    # FIR is one case, while a mule wired to two accounts in two other
    # FIRs is three cases nobody had joined.
    rows.sort(key=lambda r: (r.cross_fir, r.connected, r.amount), reverse=True)

    with_stmts = (await db.execute(
        select(func.count(func.distinct(AccountStatementSummary.account_id)))
        .select_from(AccountStatementSummary)
        .join(AllAccount, AllAccount.id == AccountStatementSummary.account_id)
        .where(AllAccount.account_type == "Mule"))).scalar() or 0

    return MuleNetworkSummary(
        total_links=len(links),
        cross_fir_links=sum(1 for r in links if r[4]),
        accounts_in_network=len(agg),
        accounts_with_statements=int(with_stmts),
        rows=rows[:limit],
    )


@router.get("/money-trail", response_model=MoneyTrailSummary)
async def get_money_trail(
    state_scope: str = Query("all",
        description="all | karnataka | other — on all_accounts.branch_state, "
                    "i.e. where the BANK BRANCH is, not the police district"),
    account_type: str = Query("All", description="All | Mule | Non-Mule | Victim"),
    account_limit: int = Query(20000, ge=1, le=25000,
        description="Max accounts returned. The client paginates and exports "
                    "these, so it needs the whole set, not one page of it."),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """What the parsed bank statements say (F2).

    super_admin only, on the same reasoning as Duplicate IDs: this view
    crosses police station boundaries, and a station-level admin seeing
    another district's transactions would breach the VAPT 7.7/7.8
    scoping rule.

    WHY account_limit IS 20,000 AND NOT 1,000
    -----------------------------------------
    It was 1,000 when this corpus held 154 accounts, and it silently
    truncated the moment the backfill passed that. Measured: raising it
    costs the server nothing — 1,000 rows took 793 ms and 20,000 took
    825 ms, because the cost is the GROUP BY, not the rows returned. It
    costs the client ~404 bytes a row, so the full corpus is about
    5.4 MB uncompressed and under 1 MB gzipped.

    `accounts_covered` is deliberately computed WITHOUT the limit, so
    the client can always tell that it received fewer accounts than
    exist and say so. A truncated table that looks complete is worse
    than a slow one.

    READS THE SUMMARY, NOT THE TRANSACTIONS
    ---------------------------------------
    Every figure here comes from account_statement_summary, which the
    parser maintains at (account, channel) grain. The fact table is not
    touched.

    That is a measured decision. Aggregating statement_transactions per
    request cost ~6.8s on 190,435 rows, with cold and warm timings
    identical because the 194 MB table does not fit the 128 MB InnoDB
    buffer pool. After the full backfill it is ~15.5M rows — the same
    screen, roughly 80x the work. The summary is ~700 rows today and
    ~130k after the backfill, so the cost stops tracking transaction
    volume and starts tracking account count, which grows far slower.

    VERIFIED vs UNVERIFIED IS SURFACED, NOT HIDDEN
    ----------------------------------------------
    Each statement carries its own arithmetic check: a running balance
    satisfying prev - debit + credit = balance on every row. Statements
    that fail are still parsed and stored, because a lead an officer
    can eyeball beats no lead — but their debit and credit columns may
    be transposed, so presenting their totals as fact would be a lie
    told in a confident font.

    Coverage counts therefore span every parsed row, while rupee totals
    come only from reconciled statements. Before that rule was applied
    the tab reported ₹111 trillion of credits — a third of India's GDP,
    from 154 accounts — because 214 rows in one failed file had a
    currency column read as an amount. The correct figure is ₹1.10
    billion.
    """
    if admin.role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Money trail analysis is available to SCRB HQ accounts only.",
        )
    if state_scope not in _MT_SCOPES:
        raise HTTPException(
            status_code=422,
            detail=f"state_scope must be one of: {', '.join(sorted(_MT_SCOPES))}")
    if account_type != "All" and account_type not in ACCOUNT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"account_type must be 'All' or one of: {', '.join(sorted(ACCOUNT_TYPES))}")

    S = AccountStatementSummary

    def scoped(q):
        """Join the summary to its account and apply the standard filters."""
        q = (q.select_from(S)
              .join(AllAccount, AllAccount.id == S.account_id)
              .outerjoin(PoliceStation, PoliceStation.id == AllAccount.ps_id)
              .outerjoin(Unit, Unit.id == AllAccount.unit_id))
        q = where_not_test(q, admin,
                           exclude_test_unit(AllAccount.unit_id),
                           exclude_test_ps(AllAccount.ps_id))
        if account_type != "All":
            q = q.where(AllAccount.account_type == account_type)
        # branch_state is free text, so compare TRIMmed and case-folded.
        # "Karnataka " and "karnataka" are the same state; only an exact
        # match would put them on opposite sides of this filter.
        st = func.lower(func.trim(func.coalesce(AllAccount.branch_state, "")))
        if state_scope == "karnataka":
            q = q.where(st == "karnataka")
        elif state_scope == "other":
            # NOT-Karnataka AND recorded. Accounts with a blank state are
            # deliberately in NEITHER bucket: for a Karnataka police
            # force, filing an unknown branch under "Other States" would
            # assert the one fact the row is missing. They remain
            # reachable under All States, and accounts_without_state
            # reports how many there are so the difference is explained
            # rather than merely noticed.
            q = q.where(st != "karnataka").where(st != "")
        return q

    # File outcomes, straight from the ledger — one row per uploaded
    # file, so this is small however large the corpus of rows becomes.
    led = (await db.execute(text(
        "SELECT status, COUNT(*) FROM upload_ledger "
        "WHERE file_kind = 'statement' GROUP BY status"
    ))).all()
    quality = [StatementQualityRow(status=k, files=v)
               for k, v in sorted(led, key=lambda kv: -kv[1])]

    head = (await db.execute(scoped(select(
        func.coalesce(func.sum(S.txns), 0),
        func.count(func.distinct(S.account_id)),
        func.min(S.first_txn),
        func.max(S.last_txn),
        func.coalesce(func.sum(S.verified_txns), 0),
        func.coalesce(func.sum(S.verified_debit), 0),
        func.coalesce(func.sum(S.verified_credit), 0),
        # Count only. There is a summary column holding the untested
        # DEBIT too, and it is not read here or anywhere else: a sum of
        # amounts that nothing could check is not a smaller truth than
        # the verified total, it is an unbacked claim wearing the same
        # rupee sign. The count is the honest form of the same fact.
        func.coalesce(func.sum(S.untested_txns), 0),
    )))).first()
    if not head or not head[0]:
        return MoneyTrailSummary(quality=quality, state_scope=state_scope,
                                 account_type=account_type)

    total_txns = int(head[0])
    verified_rows = int(head[4] or 0)

    # Distinct statement FILES in scope. Counted on the ledger rather
    # than the summary: the summary is grouped by channel, so a file's
    # rows appear under several channels and could not be counted once.
    stmt_q = (select(func.count(func.distinct(UploadLedger.file_path)))
              .select_from(UploadLedger)
              .join(AllAccount, AllAccount.id == UploadLedger.account_id)
              .outerjoin(PoliceStation, PoliceStation.id == AllAccount.ps_id)
              .where(UploadLedger.file_kind == "statement"))
    stmt_q = where_not_test(stmt_q, admin,
                            exclude_test_unit(AllAccount.unit_id),
                            exclude_test_ps(AllAccount.ps_id))
    if account_type != "All":
        stmt_q = stmt_q.where(AllAccount.account_type == account_type)
    statements_parsed = int((await db.execute(stmt_q)).scalar() or 0)

    channels = [
        StatementChannelRow(channel=r[0] or "Not identified", txns=int(r[1]),
                            debit=float(r[2] or 0), credit=float(r[3] or 0))
        for r in (await db.execute(scoped(select(
            S.channel,
            func.coalesce(func.sum(S.txns), 0),
            func.coalesce(func.sum(S.debit), 0),
            func.coalesce(func.sum(S.credit), 0),
        )).group_by(S.channel)
          .order_by(func.sum(S.txns).desc()).limit(12))).all()
    ]

    top_accounts = [
        StatementAccountRow(
            account_id=r[0], account_holder_name=r[1], account_no=r[2],
            bank_name=r[3], fir_no=r[4], account_type=r[5], ps_name=r[6],
            district=r[7], branch_state=r[8] or None,
            txns=int(r[9]), debit=float(r[10] or 0), credit=float(r[11] or 0),
            first_txn=r[12], last_txn=r[13],
            ps_id=r[15], untested_txns=int(r[16] or 0),
            rejected_txns=max(0, int(r[9]) - int(r[17] or 0) - int(r[16] or 0)),
            # THE BADGE COMES FROM ROWS, NOT FROM THE FILE FLAG.
            #
            # It used to be MIN(all_verified) -- the file-level
            # reconciliation result. But the money beside it is summed
            # from verified_debit, which already excludes every row that
            # failed. So an account could show a figure built purely
            # from passing rows and still be stamped UNVERIFIED because
            # one file it came from scored 99.22% instead of 100%.
            #
            # Measured before this change: 19,762 groups carried the
            # badge and 11,728 of them -- 59% -- had ZERO rejected rows.
            # A warning wrong three times in five is one an officer
            # learns to scroll past, which costs more than it saves on
            # the 41% that are real.
            #
            # Untested rows deliberately do NOT trip it: "nothing could
            # check this" is already reported, precisely, by the
            # unchecked count. Reserve the badge for arithmetic that
            # actively disagreed.
            verified=(int(r[9]) - int(r[17] or 0) - int(r[16] or 0)) <= 0,
        )
        for r in (await db.execute(scoped(select(
            S.account_id,
            AllAccount.account_holder_name, AllAccount.account_no,
            AllAccount.bank_name, AllAccount.fir_no, AllAccount.account_type,
            PoliceStation.station_name, Unit.name,
            func.trim(func.coalesce(AllAccount.branch_state, "")),
            func.coalesce(func.sum(S.txns), 0),
            # verified_debit, NOT debit — the same rule the KPI cards
            # above already follow. Summing the unverified column here
            # was how one RBL statement, whose account number had been
            # read as its debit amount, reached the top of this table
            # showing ₹6.68 QUADRILLION. The KPIs were protected; the
            # rows beneath them were not, and the rows are what an
            # officer reads and exports.
            #
            # An account that cannot be verified therefore shows ₹0 with
            # an UNVERIFIED badge rather than a confident wrong number.
            # Its transaction count is still shown, so it never vanishes
            # — only its money claim is withheld.
            func.coalesce(func.sum(S.verified_debit), 0),
            func.coalesce(func.sum(S.verified_credit), 0),
            func.min(S.first_txn),
            func.max(S.last_txn),
            # all_verified is the FILE-level reconciliation flag. It is
            # still selected, but no longer decides the badge — see the
            # row-level computation below.
            func.min(S.all_verified),
            PoliceStation.id,
            # Why this row's money may read Rs 0. Without it, an account
            # whose statement had no balance column is indistinguishable
            # from one that genuinely moved nothing -- and those two
            # deserve opposite reactions from an investigator.
            func.coalesce(func.sum(S.untested_txns), 0),
            # Rows that were tested AND passed. Combined with txns and
            # untested above, this yields the rejected count -- the only
            # one of the three that means "these figures are wrong".
            func.coalesce(func.sum(S.verified_txns), 0),
        )).group_by(
            S.account_id, AllAccount.account_holder_name,
            AllAccount.account_no, AllAccount.bank_name, AllAccount.fir_no,
            AllAccount.account_type, PoliceStation.station_name, Unit.name,
            func.trim(func.coalesce(AllAccount.branch_state, "")),
            PoliceStation.id,
        ).order_by(func.sum(S.debit).desc()).limit(account_limit))).all()
    ]

    # Measured OUTSIDE the state scope on purpose, and skipped when no
    # state filter is active. Inside the scope it would always read 0 —
    # precisely when the UI needs to say "these N accounts have no state
    # and appear only under All States".
    unstated = 0
    if state_scope != "all":
        q_un = (select(func.count(func.distinct(S.account_id)))
                .select_from(S)
                .join(AllAccount, AllAccount.id == S.account_id)
                .outerjoin(PoliceStation, PoliceStation.id == AllAccount.ps_id)
                .where(func.trim(func.coalesce(AllAccount.branch_state, "")) == ""))
        q_un = where_not_test(q_un, admin,
                              exclude_test_unit(AllAccount.unit_id),
                              exclude_test_ps(AllAccount.ps_id))
        if account_type != "All":
            q_un = q_un.where(AllAccount.account_type == account_type)
        unstated = int((await db.execute(q_un)).scalar() or 0)

    return MoneyTrailSummary(
        state_scope=state_scope, account_type=account_type,
        accounts_without_state=unstated,
        transactions=total_txns, accounts_covered=int(head[1]),
        statements_parsed=statements_parsed,
        date_from=head[2], date_to=head[3],
        total_debit=float(head[5] or 0), total_credit=float(head[6] or 0),
        verified_pct=round(100.0 * verified_rows / max(1, total_txns), 1),
        untested_txns=int(head[7] or 0),
        quality=quality, channels=channels, top_accounts=top_accounts,
        shared_counterparties=[],
    )


@router.get("/accounts-geo", response_model=List[AccountsGeoRegion])
async def get_accounts_by_geography(
    target_date: date = Query(..., alias="date", description="Cumulative cutoff — include accounts created on or before this date"),
    scope: str = Query("state", description="state = branch_state (all-India) | district = branch_district (Karnataka) | reporting = district of the PS that owns the row"),
    account_type: str = Query("Mule", description="Victim | Mule | Non-Mule | All"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Region rollup powering the Account Details map view (2026-07-31).

    Cumulative as of `target_date`, matching every other accounts
    endpoint, so the map and the KPI cards can never disagree.

    Returns ONLY regions that have at least one account — the caller
    owns the canonical region list (36 states/UTs, 36 KA districts) and
    fills the zeros. That keeps the payload proportional to real data
    instead of always shipping ~36 mostly-empty rows, and it means a
    region we've never heard of still comes back rather than being
    silently dropped by a server-side whitelist.

    Rows with a NULL/blank grouping value collapse to region="" instead
    of vanishing — see AccountsGeoRegion for why that bucket matters.
    """
    if scope not in _GEO_SCOPES:
        raise HTTPException(
            status_code=422,
            detail=f"scope must be one of: {', '.join(sorted(_GEO_SCOPES))}",
        )
    if account_type != "All" and account_type not in ACCOUNT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"account_type must be 'All' or one of: {', '.join(sorted(ACCOUNT_TYPES))}",
        )

    if scope == "state":
        region_col = AllAccount.branch_state
    elif scope == "district":
        region_col = AllAccount.branch_district
    else:
        region_col = PoliceStation.district_name

    # COALESCE folds NULL into '' so NULL and '' share one bucket —
    # both mean "operator never filled this in", and splitting them
    # would put two "Not recorded" rows on the map. TRIM matters just
    # as much: branch_state is free text, and grouping without it would
    # return "Karnataka" and "Karnataka " as two separate regions that
    # then collide into duplicate keys on the client.
    region_expr = func.trim(func.coalesce(region_col, ""))

    q = (
        select(
            region_expr.label("region"),
            func.count(AllAccount.id).label("total"),
            func.coalesce(func.sum(
                case((AllAccount.account_type == "Victim", 1), else_=0)
            ), 0).label("victims"),
            func.coalesce(func.sum(
                case((AllAccount.account_type == "Mule", 1), else_=0)
            ), 0).label("mules"),
            func.coalesce(func.sum(
                case((AllAccount.account_type == "Non-Mule", 1), else_=0)
            ), 0).label("non_mules"),
        )
        # Explicit anchor. Under scope='reporting' the first selected
        # column belongs to police_stations, so the FROM list is worth
        # pinning rather than leaving to inference. (Verified: SQLAlchemy
        # 2.0 infers all_accounts correctly here even without this, from
        # the count() and the WHERE — both forms compile to identical
        # SQL. Kept because it states the intent at the point of the
        # join instead of relying on that inference holding.)
        .select_from(AllAccount)
        .where(func.date(AllAccount.created_at) <= target_date)
        .group_by(region_expr)
        .order_by(func.count(AllAccount.id).desc())
    )

    # scope='reporting' reads district_name off police_stations, so that
    # table has to be joined in. Inner join is correct: ps_id is NOT NULL
    # on all_accounts, so no row can be lost.
    if scope == "reporting":
        q = q.join(PoliceStation, PoliceStation.id == AllAccount.ps_id)

    if account_type != "All":
        q = q.where(AllAccount.account_type == account_type)

    # Same scoping rule as the rest of the dashboard: a PS-level admin
    # sees only their own station's rows, super_admin sees everything.
    if admin.role != "super_admin":
        q = q.where(AllAccount.ps_id == admin.ps_id)
    # Test fixture never appears in a dashboard figure.
    q = where_not_test(q, admin, exclude_test_ps(AllAccount.ps_id))

    rows = (await db.execute(q)).all()
    return [
        AccountsGeoRegion(
            region=(r.region or "").strip(),
            total=int(r.total or 0),
            victims=int(r.victims or 0),
            mules=int(r.mules or 0),
            non_mules=int(r.non_mules or 0),
        )
        for r in rows
    ]


# All Accounts data entry began in production on 2026-07-20. Any
# earlier date on the daily-growth chart is pre-launch noise (zeros),
# so we clamp the trailing window to start no earlier than this.
# Move to config.py if we ever need a different cutoff per environment.
_ACCOUNTS_DATA_ENTRY_START = date(2026, 7, 20)


@router.get("/accounts-daily-growth", response_model=List[AccountsDailyPoint])
async def get_accounts_daily_growth(
    target_date: date = Query(..., alias="date", description="Cutoff — last day in the returned series"),
    days: int = Query(default=30, ge=1, le=365, description="Trailing days to include (inclusive of target_date)"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Per-day count of new All-Accounts rows over the trailing
    `days`-day window ending on `target_date` inclusive.

    Missing days (no rows created) are returned with `count = 0` so
    the frontend line chart draws a continuous axis rather than
    skipping days.

    Start date is floored at 2026-07-20 (data entry launch) so the
    chart doesn't lead with a run of zeros from pre-launch dates.

    Scoping matches the rest of the dashboard — admin: own PS;
    super_admin: cross-PS."""
    # Return an empty series if the cutoff pre-dates data entry launch
    # — nothing to chart yet.
    if target_date < _ACCOUNTS_DATA_ENTRY_START:
        return []

    requested_from = target_date - timedelta(days=days - 1)
    date_from = max(requested_from, _ACCOUNTS_DATA_ENTRY_START)

    q = (
        select(
            func.date(AllAccount.created_at).label("day"),
            func.count(AllAccount.id).label("count"),
        )
        .where(func.date(AllAccount.created_at) >= date_from)
        .where(func.date(AllAccount.created_at) <= target_date)
        .group_by(func.date(AllAccount.created_at))
    )
    if admin.role != "super_admin":
        if not admin.unit_id or not admin.ps_id:
            raise HTTPException(status_code=403, detail="Admin account is not assigned to a Police Station.")
        q = q.where(AllAccount.unit_id == admin.unit_id, AllAccount.ps_id == admin.ps_id)
    # Test fixture never appears in a dashboard figure.
    q = where_not_test(q, admin, exclude_test_unit(AllAccount.unit_id), exclude_test_ps(AllAccount.ps_id))

    rows = (await db.execute(q)).all()
    # MySQL returns func.date(...) as a Python `date` when the driver
    # is asyncmy; belt+braces coerce to `date` in case of surprises.
    counts: dict[date, int] = {}
    for r in rows:
        d = r.day
        if not isinstance(d, date):
            # asyncmy sometimes returns str for DATE()
            from datetime import datetime as _dt
            d = _dt.strptime(str(d), "%Y-%m-%d").date()
        counts[d] = int(r.count or 0)

    # Zero-fill missing days so the chart line is continuous.
    out: List[AccountsDailyPoint] = []
    cur = date_from
    while cur <= target_date:
        out.append(AccountsDailyPoint(day=cur, count=counts.get(cur, 0)))
        cur = cur + timedelta(days=1)
    return out


@router.get("/accounts-layer-distribution", response_model=AccountsLayerDistribution)
async def get_accounts_layer_distribution(
    target_date: date = Query(..., alias="date", description="Cumulative cutoff — accounts created on or before this date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Layer 1..15 histogram of all_accounts, split by branch state.

    Karnataka bucket : branch_state = 'Karnataka'
    Rest bucket      : branch_state != 'Karnataka' OR IS NULL
                       (legacy pre-migration-012 rows without a
                        confirmed state count as 'not confirmed KA')

    Accounts with NULL layer are excluded from both arrays but their
    count is returned separately so the UI can surface them in a hint.

    Scoping: admin -> own PS; super_admin -> cross-PS."""

    # Helper: build a (layer -> count) dict for a given branch_state
    # predicate, then flesh it out into a full LayerBucket list.
    ka_pred = AllAccount.branch_state == "Karnataka"
    rest_pred = (AllAccount.branch_state != "Karnataka") | AllAccount.branch_state.is_(None)

    async def _histogram(where_pred, layer_is_null: bool):
        q = (
            select(AllAccount.layer, func.count(AllAccount.id))
            .where(func.date(AllAccount.created_at) <= target_date)
            .where(where_pred)
            .group_by(AllAccount.layer)
        )
        if layer_is_null:
            q = q.where(AllAccount.layer.is_(None))
        else:
            q = q.where(AllAccount.layer.is_not(None))
        if admin.role != "super_admin":
            if not admin.unit_id or not admin.ps_id:
                raise HTTPException(status_code=403, detail="Admin account is not assigned to a Police Station.")
            q = q.where(AllAccount.unit_id == admin.unit_id, AllAccount.ps_id == admin.ps_id)
        # Test fixture never appears in a dashboard figure.
        q = where_not_test(q, admin, exclude_test_unit(AllAccount.unit_id), exclude_test_ps(AllAccount.ps_id))
        return (await db.execute(q)).all()

    ka_rows = await _histogram(ka_pred, layer_is_null=False)
    rest_rows = await _histogram(rest_pred, layer_is_null=False)
    ka_null_rows = await _histogram(ka_pred, layer_is_null=True)
    rest_null_rows = await _histogram(rest_pred, layer_is_null=True)

    def _rows_to_buckets(rows) -> list[LayerBucket]:
        counts: dict[int, int] = {int(layer): int(c) for layer, c in rows}
        # Emit only the layers that appear -- frontend zero-fills the
        # 1..15 axis so the bar chart stays a fixed width.
        return [LayerBucket(layer=k, count=v) for k, v in sorted(counts.items())]

    return AccountsLayerDistribution(
        ka=_rows_to_buckets(ka_rows),
        rest=_rows_to_buckets(rest_rows),
        unknown_layer_ka=sum(int(c) for _, c in ka_null_rows),
        unknown_layer_rest=sum(int(c) for _, c in rest_null_rows),
    )


@router.get("/accounts-fir-trace", response_model=AccountsFirTrace)
async def get_accounts_fir_trace(
    fir_no: str = Query(..., min_length=1, max_length=50,
                        description="FIR No to trace across every account/transfer table"),
    ps_id: int = Query(..., ge=1,
                        description="Police station scope -- FIR Nos are only unique per PS (schema: UNIQUE(unit_id, ps_id, fir_no) on cases)"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Deep Analysis: pull every account touching this FIR from all
    five relevant tables (all_accounts, lien_accounts, victim_accounts,
    accused_accounts, money_transfers) and return them tagged with
    their source. Frontend groups by layer for the layered-accounts
    table and sums by layer for the money-flow bar chart.

    ps_id is required because FIR No like '0001/2026' can exist in
    multiple PSes (schema UNIQUE key is (unit_id, ps_id, fir_no) on
    cases). super_admin picks the PS from a dropdown; admins would
    default to their own ps_id.

    super_admin only -- this is a cross-PS investigation tool. Non-
    super_admins get 403 even if the FIR belongs to their PS
    (Overview tab covers their PS-scoped view). Enforced inline
    rather than via a shared dep because this is the only route
    with that gate right now."""
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Deep Analysis is restricted to super_admin.")

    fir = fir_no.strip()
    if not fir:
        raise HTTPException(status_code=400, detail="fir_no is required.")

    # FIR variants: legacy rows may store "1/2025" while a new operator
    # types "0001/2025" (validator was grandfathered to \d{1,4}/\d{4}).
    # Match any of: as-typed, leading zeros stripped, zero-padded to 4.
    def _fir_variants(s: str) -> list[str]:
        s = s.strip()
        if "/" not in s:
            return [s]
        num, year = s.split("/", 1)
        variants = {s}
        stripped = num.lstrip("0") or "0"
        variants.add(f"{stripped}/{year}")
        try:
            padded = f"{int(stripped):04d}/{year}"
            variants.add(padded)
        except ValueError:
            pass
        return list(variants)

    fir_candidates = _fir_variants(fir)

    # Resolve the PS so we can validate it exists + surface district/name
    # in warnings, and so we know its unit_id for the mule_report cross-check.
    ps_row = (await db.execute(
        select(PoliceStation).where(PoliceStation.id == ps_id)
    )).scalar_one_or_none()
    if ps_row is None:
        raise HTTPException(status_code=404, detail=f"Police station {ps_id} not found.")
    # Derive unit_id from the PS's district (units.name == police_stations.district_name).
    unit_row = (await db.execute(
        select(Unit).where(Unit.name == ps_row.district_name)
    )).scalar_one_or_none()
    ps_unit_id = unit_row.id if unit_row else None

    accounts: list[FirTraceAccount] = []
    warnings: list[str] = []

    # ── Case metadata (may be missing if the FIR was only entered
    #    via NCRP mule-report or an all_accounts row with no matching
    #    case). Load with victim so the header can show victim_name.
    #    Scoped to the selected ps_id -- same FIR can exist in another PS.
    case_row = (await db.execute(
        select(Case, Unit, PoliceStation)
        .join(Unit, Unit.id == Case.unit_id)
        .join(PoliceStation, PoliceStation.id == Case.ps_id)
        .where(Case.fir_no.in_(fir_candidates), Case.ps_id == ps_id)
    )).first()
    case_meta: FirTraceCase | None = None
    case_id: str | None = None
    if case_row:
        c, unit, ps = case_row
        case_id = c.id
        victim_row = (await db.execute(
            select(Victim).where(Victim.case_id == c.id)
        )).scalar_one_or_none()
        victim_name = (
            f"{victim_row.first_name} {victim_row.last_name}".strip()
            if victim_row else None
        )
        case_meta = FirTraceCase(
            case_id=c.id,
            fir_no=fir,
            unit_name=unit.name,
            ps_name=ps.station_name,
            registration_date=c.registration_date,
            case_type=c.case_type,
            crime_type=c.crime_type,
            victim_name=victim_name,
            amount_lost=float(victim_row.amount_lost or 0) if victim_row else 0.0,
        )
    else:
        # Diagnostic: does the FIR exist at some OTHER PS? If yes, hint
        # at where so the operator can re-pick the dropdown instead of
        # concluding the FIR doesn't exist at all.
        other_ps_rows = (await db.execute(
            select(PoliceStation.station_name, PoliceStation.district_name, Case.fir_no)
            .join(Case, Case.ps_id == PoliceStation.id)
            .where(Case.fir_no.in_(fir_candidates), Case.ps_id != ps_id)
            .limit(5)
        )).all()
        if other_ps_rows:
            other_hint = "; ".join(
                f"{sn} ({dn}) as '{fn}'" for sn, dn, fn in other_ps_rows
            )
            warnings.append(
                f"No case row for FIR '{fir}' at {ps_row.station_name} ({ps_row.district_name}). "
                f"Same FIR does exist at: {other_hint}."
            )
        else:
            warnings.append(
                f"No case row found for FIR '{fir}' at {ps_row.station_name} ({ps_row.district_name}). "
                f"If accounts appear below, they came from the All Accounts register. "
                f"Tried FIR variants: {', '.join(fir_candidates)}."
            )

    # ── all_accounts: direct fir_no match on the accounts register,
    #    scoped to the selected PS (unit_id, ps_id, serial_no) unique key.
    all_acc_rows = (await db.execute(
        select(AllAccount).where(AllAccount.fir_no.in_(fir_candidates), AllAccount.ps_id == ps_id)
    )).scalars().all()
    for a in all_acc_rows:
        accounts.append(FirTraceAccount(
            account_id=str(a.id),
            source="all_accounts",
            layer=a.layer,
            account_no=a.account_no,
            account_holder_name=a.account_holder_name,
            bank_name=a.bank_name,
            branch_name=a.branch_name,
            branch_state=a.branch_state,
            ifsc_code=a.ifsc_code,
            amount=0,  # all_accounts doesn't carry a per-account amount
            account_type=a.account_type,
        ))

    # ── Everything hanging off the Case (if we found one)
    if case_id:
        # lien_accounts
        lien_rows = (await db.execute(
            select(LienAccount).where(LienAccount.case_id == case_id)
        )).scalars().all()
        for la in lien_rows:
            accounts.append(FirTraceAccount(
                source="lien_accounts",
                layer=la.layer,
                account_no=la.account_no,
                bank_name=la.bank_name,
                amount=float(la.amount_lien_marked or 0),
            ))

        # victim_accounts (DSR -> New FIR additions)
        va_rows = (await db.execute(
            select(VictimAccount).where(VictimAccount.case_id == case_id)
        )).scalars().all()
        for va in va_rows:
            accounts.append(FirTraceAccount(
                source="victim_accounts",
                layer=None,  # victim_accounts has no layer column
                bank_name=va.bank_name,
                branch_name=va.branch_name,
                branch_state=va.state,
                ifsc_code=va.ifsc_code,
                amount=float(va.amount_transferred or 0),
            ))

        # accused_accounts (DSR -> New FIR additions)
        aa_rows = (await db.execute(
            select(AccusedAccount).where(AccusedAccount.case_id == case_id)
        )).scalars().all()
        for aa in aa_rows:
            accounts.append(FirTraceAccount(
                source="accused_accounts",
                layer=None,  # accused_accounts has no layer column
                account_holder_name=aa.account_holder_name,
                bank_name=aa.bank_name,
                branch_name=aa.branch_name,
                branch_state=aa.state,
                ifsc_code=aa.ifsc_code,
                amount=float(aa.amount_transferred or 0),
            ))

    # NOTE: Money transfers from NCRP mule reports intentionally omitted
    # here as of 2026-07-30. PS operators were entering NCRP Data via
    # the wrong workflow; that data has been purged (purge_ncrp_data.py)
    # and the module gate now restricts entry to CID + Test PS only.
    # The Deep Analysis trace should not surface mule-report references
    # to avoid pulling stale or non-authoritative data. Restore this
    # block if CID starts posting legitimate mule reports again.

    if not accounts:
        warnings.append("No accounts, liens, or transfers found for this FIR.")

    # ── Crypto and transfer edges for the register accounts.
    #
    # Both read tables the batch jobs maintain, so a trace costs two
    # small indexed lookups rather than touching statement_transactions.
    # Accounts from the four case-child tables carry no id and are
    # skipped: they are still drawn, just without these annotations.
    traced_ids = [a.account_id for a in accounts if a.account_id]
    flows: list[FirTraceFlow] = []
    if traced_ids:
        by_id = {a.account_id: a for a in accounts if a.account_id}

        crypto = (await db.execute(
            select(CryptoTxn.account_id, CryptoTxn.exchange,
                   func.count().label("n"),
                   func.sum(case((CryptoTxn.chain_ok == 1,
                                  func.coalesce(CryptoTxn.debit, 0)),
                                 else_=0)))
            .where(CryptoTxn.account_id.in_(traced_ids))
            .group_by(CryptoTxn.account_id, CryptoTxn.exchange))).all()
        for aid, exch, n, deb in crypto:
            acc = by_id.get(str(aid))
            if not acc:
                continue
            acc.crypto_txns += int(n or 0)
            acc.crypto_debit += float(deb or 0)
            if exch and exch not in acc.crypto_exchanges:
                acc.crypto_exchanges.append(exch)

        links = (await db.execute(text(
            "SELECT src_account_id, dst_account_id, txns, total_debit, "
            "cross_fir FROM mule_account_link "
            "WHERE src_account_id IN :ids OR dst_account_id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)),
            {"ids": traced_ids})).all()
        inside = set(traced_ids)
        for src, dst, n, amt, xf in links:
            s_id, d_id = str(src), str(dst)
            if s_id in inside and d_id in inside:
                flows.append(FirTraceFlow(
                    src_account_id=s_id, dst_account_id=d_id,
                    txns=int(n or 0), amount=float(amt or 0),
                    cross_fir=bool(xf)))
            else:
                # One end is outside this FIR. Counted on whichever end
                # IS in the trace, so the screen can say "this account
                # also pays two mules you are not looking at".
                end = by_id.get(s_id) or by_id.get(d_id)
                if end:
                    end.external_links += 1

    return AccountsFirTrace(
        flows=flows,
        fir_no=fir,
        case=case_meta,
        accounts=accounts,
        warnings=warnings,
    )


@router.get("/accounts-top-banks", response_model=List[AccountsBankConcentration])
async def get_accounts_top_banks(
    target_date: date = Query(..., alias="date", description="Cumulative cutoff — include accounts created on or before this date"),
    limit: int = Query(default=10, ge=1, le=50, description="Max rows to return"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Top N banks by account-count on the Dashboard Overview.
    Scoped like /accounts-comparison — super_admin sees all PSes,
    admin only their own."""
    q = (
        select(
            AllAccount.bank_name,
            func.count(AllAccount.id).label("total"),
            func.sum(case((AllAccount.account_type == "Victim", 1), else_=0)).label("victims"),
            func.sum(case((AllAccount.account_type == "Mule", 1), else_=0)).label("mules"),
            func.sum(case((AllAccount.account_type == "Non-Mule", 1), else_=0)).label("non_mules"),
        )
        .where(func.date(AllAccount.created_at) <= target_date)
        .group_by(AllAccount.bank_name)
        .order_by(func.count(AllAccount.id).desc())
        .limit(limit)
    )
    if admin.role != "super_admin":
        if not admin.unit_id or not admin.ps_id:
            raise HTTPException(status_code=403, detail="Admin account is not assigned to a Police Station.")
        q = q.where(AllAccount.unit_id == admin.unit_id, AllAccount.ps_id == admin.ps_id)
    # Test fixture never appears in a dashboard figure.
    q = where_not_test(q, admin, exclude_test_unit(AllAccount.unit_id), exclude_test_ps(AllAccount.ps_id))

    rows = (await db.execute(q)).all()
    return [
        AccountsBankConcentration(
            bank_name=r.bank_name,
            total=int(r.total or 0),
            victims=int(r.victims or 0),
            mules=int(r.mules or 0),
            non_mules=int(r.non_mules or 0),
        )
        for r in rows
    ]


@router.get("/accounts-details-by-ps", response_model=List[AllAccountResponse])
async def get_accounts_details_by_ps(
    unit_id: int = Query(..., description="Unit id (from the PS-comparison row on the dashboard)"),
    ps_id: int = Query(..., description="Police Station id (from the PS-comparison row on the dashboard)"),
    target_date: date = Query(..., alias="date", description="Cumulative cutoff — include accounts created on or before this date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Powers the drill-down grid on the Account Details Dashboard.
    Returns every account row (with mule herders eager-loaded) for the
    requested (unit_id, ps_id) up to `date`.

    admin is pinned to their own PS (VAPT 7.8 — cannot peek into other
    PSes via the dashboard). super_admin can drill into any PS."""
    if admin.role != "super_admin":
        if admin.unit_id != unit_id or admin.ps_id != ps_id:
            raise HTTPException(
                status_code=403,
                detail="You can only view account details for your own Police Station.",
            )

    rows = (await db.execute(
        select(AllAccount)
        .options(selectinload(AllAccount.mule_herders))
        .where(
            AllAccount.unit_id == unit_id,
            AllAccount.ps_id == ps_id,
            func.date(AllAccount.created_at) <= target_date,
        )
        .order_by(AllAccount.serial_no.asc())
    )).scalars().all()

    return [
        AllAccountResponse(
            id=r.id,
            unit_id=r.unit_id,
            ps_id=r.ps_id,
            serial_no=r.serial_no,
            fir_no=r.fir_no,
            ncrp_ack_no=r.ncrp_ack_no,
            account_no=r.account_no,
            bank_name=r.bank_name,
            branch_name=r.branch_name,
            branch_district=r.branch_district,
            branch_state=r.branch_state,
            layer=r.layer,
            ifsc_code=r.ifsc_code,
            account_holder_name=r.account_holder_name,
            kyc_address=r.kyc_address,
            kyc_mobile=r.kyc_mobile,
            # Sign the file paths so /uploads/* is gated behind a
            # short-lived HMAC — same rule as the CRUD response.
            id_photo_path=sign_path(r.id_photo_path),
            account_statement_path=sign_path(r.account_statement_path),
            account_type=r.account_type,
            mule_herders=[
                MuleHerderOut(id=h.id, name=h.name, address=h.address, mobile_no=h.mobile_no)
                for h in r.mule_herders
            ],
            submitted_by=r.submitted_by,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


# ════════════════════════════════════════════════════════════════
# ── Portals DSR dashboard (2026-07-21) ─────────────────────────
# Multiple entries per PS per day are legal (shift-based data
# entry), so SUM-aggregate every metric across the window.
# Drafts EXCLUDED so KPIs never inflate on in-progress work.
# ════════════════════════════════════════════════════════════════


# Metric columns to SUM in dashboard queries — mirrors the model +
# schema. Kept as a plain tuple so we can build a select() with
# func.sum() per column without repeating the list five times.
_PORTAL_METRICS: tuple[str, ...] = (
    "ncrp_received", "ncrp_disposed", "ncrp_pending",
    "samanvaya_request_received", "samanvaya_actions", "samanvaya_action_pending",
    "samanvaya_request_sent", "samanvaya_reply_received", "samanvaya_replies_pending",
    "sahayog_unlawful_content_removal", "sahayog_intermediary_requests",
    "sahayog_crypto_requests",
    "grm_request_received", "grm_action", "grm_pending",
    "mrm_request_received", "mrm_action", "mrm_pending",
    "bharatpol_request_received",
    "ocwc_received", "ocwc_disposed", "ocwc_pending",
    "ncmec_received", "ncmec_disposed", "ncmec_pending",
)


def _scope_portals(query, admin: CurrentUser):
    if admin.role == "super_admin":
        return query
    if not admin.unit_id or not admin.ps_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to a Police Station.")
    return query.where(
        PortalsDsrEntry.unit_id == admin.unit_id,
        PortalsDsrEntry.ps_id == admin.ps_id,
    )



# ── Portals DSR — per-day dashboard (2026-07-27) ──────────────────
# Every metric is a Daily Status Report counter. Two semantic
# classes drive how we aggregate multiple shift-batches on the SAME
# date:
#   * "*_pending" fields = current point-in-time snapshot. Take the
#     LATEST entry's value (SUM would double-count outstanding work).
#   * every other field = SUM across the day's shifts (they're
#     counts of that day's activity).
# The dashboard is date-per-day (not a range) so operators can pick
# a specific DSR to review.

_PORTAL_PENDING_METRICS = frozenset({
    "ncrp_pending",
    "samanvaya_action_pending",
    "samanvaya_replies_pending",
    "grm_pending",
    "mrm_pending",
    "ocwc_pending",
    "ncmec_pending",
})


async def _compute_portals_per_ps_on_date(
    db: AsyncSession,
    *,
    target_date: date,
    admin: CurrentUser,
) -> list[dict]:
    """Return one dict per active PS in scope, with all 25 metric
    fields aggregated according to the per-day pending/sum rules
    above. Silent PSes (no submissions on target_date) come back
    with zeros across every metric.

    Shared by `get_portals_summary` and `get_portals_comparison`.
    Both endpoints run this single call and either roll up further
    (summary) or hand back verbatim (comparison)."""

    # 1) Fixed roster: every active PS -- so silent stations appear.
    ps_q = (
        select(
            PoliceStation.id.label("ps_id"),
            PoliceStation.station_name.label("ps_name"),
            Unit.id.label("unit_id"),
            Unit.name.label("unit_name"),
        )
        .join(Unit, Unit.name == PoliceStation.district_name)
        .where(PoliceStation.is_active == True)  # noqa: E712
        # Test fixture is a real, active station — drop it from the
        # station LIST too, or it appears as a permanent zero row.
        .where(station_row_filter(admin))
        .order_by(PoliceStation.district_name, PoliceStation.station_name)
    )
    if admin.role != "super_admin":
        ps_q = ps_q.where(PoliceStation.id == admin.ps_id)
    roster = (await db.execute(ps_q)).all()

    # 2) Every submitted entry on the date, ordered by created_at ASC
    #    so the LAST row per PS is the most recent -- makes the
    #    "latest for pending" pick trivial in Python.
    entry_q = (
        select(PortalsDsrEntry)
        .where(
            PortalsDsrEntry.status == "submitted",
            PortalsDsrEntry.report_date == target_date,
        )
        .order_by(PortalsDsrEntry.ps_id, PortalsDsrEntry.created_at.asc())
    )
    if admin.role != "super_admin":
        entry_q = entry_q.where(PortalsDsrEntry.ps_id == admin.ps_id)
    # Test fixture never appears in a dashboard figure.
    entry_q = where_not_test(entry_q, admin, exclude_test_ps(PortalsDsrEntry.ps_id))
    entries = (await db.execute(entry_q)).scalars().all()

    # 3) Group entries by ps_id, apply pending=LATEST / other=SUM per
    #    metric column. Roster ensures every PS lands even with zero
    #    entries.
    by_ps: dict[int, list[PortalsDsrEntry]] = {}
    for e in entries:
        by_ps.setdefault(int(e.ps_id), []).append(e)

    out: list[dict] = []
    for r in roster:
        ps_entries = by_ps.get(int(r.ps_id), [])
        latest = ps_entries[-1] if ps_entries else None  # entries already ordered ASC

        row: dict = {
            "unit_id": int(r.unit_id),
            "unit_name": r.unit_name,
            "ps_id": int(r.ps_id),
            "ps_name": r.ps_name,
            "entries": len(ps_entries),
        }
        grand_total = 0
        for f in _PORTAL_METRICS:
            if f in _PORTAL_PENDING_METRICS:
                # Latest snapshot only. No submissions today -> 0.
                v = int(getattr(latest, f) or 0) if latest else 0
            else:
                v = sum(int(getattr(e, f) or 0) for e in ps_entries)
            row[f] = v
            grand_total += v
        row["total"] = grand_total
        out.append(row)

    # Chart-friendly ordering: highest activity first, name tiebreak.
    out.sort(key=lambda r: (-r["total"], r["ps_name"]))
    return out


@router.get("/portals-summary", response_model=PortalsDsrKpiSummary)
async def get_portals_summary(
    target_date: date = Query(..., alias="date", description="Single DSR date to summarise"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Portals DSR grand totals across the caller's scope for ONE
    date. Non-pending fields sum across the day's shift-batches;
    pending fields take the LATEST value per PS (then sum across
    PSes). Only submitted entries counted."""
    per_ps = await _compute_portals_per_ps_on_date(db, target_date=target_date, admin=admin)

    payload: dict = {"total_entries": sum(r["entries"] for r in per_ps)}
    for f in _PORTAL_METRICS:
        payload[f] = sum(int(r.get(f, 0)) for r in per_ps)

    # Coverage: how many PSes actually submitted at least one row.
    if admin.role == "super_admin":
        payload["units_submitted"] = sum(1 for r in per_ps if r["entries"] > 0)
        payload["units_total"] = len(per_ps)
    else:
        payload["units_submitted"] = 1 if payload["total_entries"] > 0 else 0
        payload["units_total"] = 1

    return PortalsDsrKpiSummary(**payload)


@router.get("/portals-comparison", response_model=List[PortalsDsrPsComparison])
async def get_portals_comparison(
    target_date: date = Query(..., alias="date", description="Single DSR date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """One row per active PS for the selected date. All 25 metric
    columns populated per the pending/sum rules. Silent PSes appear
    with zeros so the frontend can show every station."""
    per_ps = await _compute_portals_per_ps_on_date(db, target_date=target_date, admin=admin)
    return [PortalsDsrPsComparison(**r) for r in per_ps]


# ── FIR Dashboard (DSR module) — PS-performance table ──────────────────
# Per-PS FIR-count rollup for a date window. Registration date drives
# the window (not created_at) — matches operator mental model of "FIRs
# registered this week / month". Includes every active (district, PS)
# pair with at least one user assigned so under-performing PSes surface
# as zero-count rows rather than being silently omitted.
#
# Scoping (same VAPT 7.7 / 7.8 rule as every other admin dashboard):
#   - admin       → own (unit_id, ps_id) only, single row
#   - super_admin → every active PS, leaderboard shape


def _resolve_fir_perf_window(
    date_from: date | None,
    date_to: date | None,
) -> tuple[date, date]:
    """Fill in default window (trailing 30 days) and validate ordering.
    Extracted so JSON + PDF + Excel routes share the same defaults."""
    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = date_to - timedelta(days=29)
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="`from` must be on or before `to`.")
    return date_from, date_to


# Financial filter values accepted across the FIR Dashboard + its two
# report routes. Kept as a whitelist because the value picks a WHERE
# clause; `cases.is_financial` is NOT NULL DEFAULT 1, so there is no
# third "unknown" bucket to account for.
_FIR_FINANCIAL_FILTERS = {"all", "yes", "no"}


def _apply_financial_filter(q, financial: str):
    """Narrow a cases query to financial / non-financial / everything."""
    if financial == "yes":
        return q.where(Case.is_financial == 1)
    if financial == "no":
        return q.where(Case.is_financial != 1)
    return q


async def compute_fir_ps_performance(
    db: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    admin: CurrentUser,
    financial: str = "all",
    with_crime_types: bool = False,
) -> List[FirPsPerformanceRow]:
    """Per-PS FIR count in [date_from, date_to] inclusive. Ordered by
    fir_count DESC then district ASC, PS name ASC for stable tiebreaks.

    Shared by the JSON /fir-ps-performance route and the PDF + XLSX
    report routes so all three reflect identical numbers."""
    # Enumerate the (unit, PS) pairs in scope. Same pattern the DSR
    # Submission Status table uses — PSes without any active user
    # can't submit anything, so hiding them prevents noise.
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
        # This one enumerates stations via User, so it never passes the
        # is_active filter the other station lists use — it needs its
        # own exclusion or the test station keeps a ranking row.
        .where(station_row_filter(admin))
        .distinct()
    )
    if admin.role != "super_admin":
        ps_q = ps_q.where(Unit.id == admin.unit_id).where(PoliceStation.id == admin.ps_id)
    ps_rows = (await db.execute(ps_q)).all()

    # Case counts per (unit_id, ps_id) in the window. cases.ps_id is
    # canonical since migration 002, so we group by it directly.
    count_q = (
        select(Case.unit_id, Case.ps_id, func.count(Case.id))
        .where(Case.registration_date.is_not(None))
        .where(Case.registration_date >= date_from)
        .where(Case.registration_date <= date_to)
        .group_by(Case.unit_id, Case.ps_id)
    )
    if admin.role != "super_admin":
        count_q = count_q.where(Case.unit_id == admin.unit_id).where(Case.ps_id == admin.ps_id)
    # Test fixture never appears in a dashboard figure.
    count_q = where_not_test(count_q, admin, exclude_test_unit(Case.unit_id), exclude_test_ps(Case.ps_id))
    # Applied to BOTH counts below — a filtered table with an unfiltered
    # "yesterday" column would silently compare different populations.
    count_q = _apply_financial_filter(count_q, financial)
    count_rows = (await db.execute(count_q)).all()
    counts: dict[tuple[int, int], int] = {
        (int(uid), int(pid)): int(n or 0)
        for uid, pid, n in count_rows
        if pid is not None
    }

    # Second query — FIRs registered YESTERDAY (server today − 1 day),
    # independent of the window. Powers the "last 24h" column on the
    # dashboard. Same PS scoping as the main count.
    yesterday = date.today() - timedelta(days=1)
    yday_q = (
        select(Case.unit_id, Case.ps_id, func.count(Case.id))
        .where(Case.registration_date == yesterday)
        .group_by(Case.unit_id, Case.ps_id)
    )
    if admin.role != "super_admin":
        yday_q = yday_q.where(Case.unit_id == admin.unit_id).where(Case.ps_id == admin.ps_id)
    # Test fixture never appears in a dashboard figure.
    yday_q = where_not_test(yday_q, admin, exclude_test_unit(Case.unit_id), exclude_test_ps(Case.ps_id))
    yday_q = _apply_financial_filter(yday_q, financial)
    yday_rows = (await db.execute(yday_q)).all()

    # Crime-type split per PS, for the dashboard tooltip. Gated because
    # the PDF and Excel exports share this helper and render no such
    # breakdown — no reason to make them pay for a query they discard.
    ps_crime: dict[tuple[int, int], list] = {}
    if with_crime_types:
        ct = func.coalesce(func.nullif(func.trim(Case.crime_type), ""), "(unclassified)")
        ct_q = (
            select(Case.unit_id, Case.ps_id, ct.label("ct"), func.count(Case.id).label("n"))
            .where(Case.registration_date.is_not(None))
            .where(Case.registration_date >= date_from)
            .where(Case.registration_date <= date_to)
            .group_by(Case.unit_id, Case.ps_id, ct)
            .order_by(func.count(Case.id).desc())
        )
        if admin.role != "super_admin":
            ct_q = ct_q.where(Case.unit_id == admin.unit_id).where(Case.ps_id == admin.ps_id)
        # Test fixture never appears in a dashboard figure.
        ct_q = where_not_test(ct_q, admin, exclude_test_unit(Case.unit_id), exclude_test_ps(Case.ps_id))
        ct_q = _apply_financial_filter(ct_q, financial)
        for uid, pid, name, n in (await db.execute(ct_q)).all():
            if pid is None:
                continue
            ps_crime.setdefault((int(uid), int(pid)), []).append(
                FirPsCrimeCount(crime_type=str(name), count=int(n or 0))
            )
    yday_counts: dict[tuple[int, int], int] = {
        (int(uid), int(pid)): int(n or 0)
        for uid, pid, n in yday_rows
        if pid is not None
    }

    rows = [
        FirPsPerformanceRow(
            unit_id=int(uid),
            district=uname,
            ps_id=int(pid),
            ps_name=pname or "",
            fir_count=counts.get((int(uid), int(pid)), 0),
            yesterday_count=yday_counts.get((int(uid), int(pid)), 0),
            crime_types=ps_crime.get((int(uid), int(pid)), []),
        )
        for uid, uname, pid, pname in ps_rows
    ]
    rows.sort(key=lambda r: (-r.fir_count, r.district, r.ps_name))
    return rows


@router.get("/fir-ps-performance", response_model=List[FirPsPerformanceRow])
async def get_fir_ps_performance(
    date_from: date = Query(None, alias="from"),
    date_to: date = Query(None, alias="to"),
    financial: str = Query("all", description="all | yes (financial) | no (non-financial)"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """JSON route for the FIR Dashboard PS-performance table."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")
    if financial not in _FIR_FINANCIAL_FILTERS:
        raise HTTPException(
            status_code=422,
            detail=f"financial must be one of: {', '.join(sorted(_FIR_FINANCIAL_FILTERS))}",
        )
    date_from, date_to = _resolve_fir_perf_window(date_from, date_to)
    return await compute_fir_ps_performance(
        db, date_from=date_from, date_to=date_to, admin=admin, financial=financial,
        with_crime_types=True,
    )


@router.get("/fir-crime-types", response_model=FirCrimeTypeReport)
async def get_fir_crime_types(
    date_from: date = Query(None, alias="from"),
    date_to: date = Query(None, alias="to"),
    financial: str = Query("all", description="all | yes (financial) | no (non-financial)"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Everything the FIR Dashboard's Crime Type tab needs, in one call.

    Deliberately SEVEN small queries rather than one wide join. victims
    is 1:1 with cases but lien_accounts and arrests are 1:N — joining
    them together would multiply the case rows and silently inflate
    every count. Aggregating each signal separately and merging in
    Python keeps each number meaning what it says.

    Window semantics match the rest of this dashboard: registration_date
    drives it, and the same financial filter applies, so the Crime Type
    tab and the Overview tab always describe the same population.
    """
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")
    if financial not in _FIR_FINANCIAL_FILTERS:
        raise HTTPException(
            status_code=422,
            detail=f"financial must be one of: {', '.join(sorted(_FIR_FINANCIAL_FILTERS))}",
        )
    date_from, date_to = _resolve_fir_perf_window(date_from, date_to)

    # Preceding window of EQUAL length, ending the day before this one
    # starts. Equal length matters: comparing 30 days against 7 would
    # make everything look like it is collapsing.
    span_days = (date_to - date_from).days
    prev_to = date_from - timedelta(days=1)
    prev_from = prev_to - timedelta(days=span_days)

    def scoped(q):
        """Apply the window-independent filters every query here shares."""
        q = q.where(Case.registration_date.is_not(None))
        if admin.role != "super_admin":
            q = q.where(Case.unit_id == admin.unit_id).where(Case.ps_id == admin.ps_id)
        # Test fixture never appears in a dashboard figure.
        q = where_not_test(q, admin, exclude_test_unit(Case.unit_id), exclude_test_ps(Case.ps_id))
        return _apply_financial_filter(q, financial)

    def in_window(q, lo: date, hi: date):
        return q.where(Case.registration_date >= lo).where(Case.registration_date <= hi)

    ctype = func.coalesce(func.nullif(func.trim(Case.crime_type), ""), "(unclassified)")

    # 1. Case count per crime type, current window.
    counts = {
        str(r[0]): int(r[1] or 0)
        for r in (await db.execute(
            in_window(scoped(select(ctype.label("t"), func.count(Case.id))), date_from, date_to)
            .group_by(ctype)
        )).all()
    }

    # 2. Same, previous window — the comparison baseline.
    prev_counts = {
        str(r[0]): int(r[1] or 0)
        for r in (await db.execute(
            in_window(scoped(select(ctype.label("t"), func.count(Case.id))), prev_from, prev_to)
            .group_by(ctype)
        )).all()
    }

    # 3. Harm: amount lost, plus how many cases actually carry a victim
    #    row so the client can report the coverage rather than imply
    #    a low number means low harm.
    harm = {
        str(r[0]): (float(r[1] or 0), int(r[2] or 0))
        for r in (await db.execute(
            in_window(
                scoped(
                    select(
                        ctype.label("t"),
                        func.coalesce(func.sum(Victim.amount_lost), 0),
                        func.count(Victim.id),
                    ).select_from(Case).join(Victim, Victim.case_id == Case.id)
                ),
                date_from, date_to,
            ).group_by(ctype)
        )).all()
    }

    # 4. Recovery: money frozen. lien_accounts is 1:N per case, which is
    #    correct to SUM but would have inflated the case counts above.
    frozen = {
        str(r[0]): float(r[1] or 0)
        for r in (await db.execute(
            in_window(
                scoped(
                    select(ctype.label("t"), func.coalesce(func.sum(LienAccount.amount_lien_marked), 0))
                    .select_from(Case).join(LienAccount, LienAccount.case_id == Case.id)
                ),
                date_from, date_to,
            ).group_by(ctype)
        )).all()
    }

    # 5. Outcome: DISTINCT cases with at least one arrest. Without the
    #    distinct, a case with three arrests would count three times and
    #    push the arrest rate above 100%.
    arrested = {
        str(r[0]): int(r[1] or 0)
        for r in (await db.execute(
            in_window(
                scoped(
                    select(ctype.label("t"), func.count(func.distinct(Case.id)))
                    .select_from(Case).join(Arrest, Arrest.case_id == Case.id)
                ),
                date_from, date_to,
            ).group_by(ctype)
        )).all()
    }

    # 6. What operators typed when the taxonomy did not fit.
    other_txt = func.trim(Case.crime_type_other)
    others = [
        FirCrimeOther(text=str(r[0]), count=int(r[1] or 0))
        for r in (await db.execute(
            in_window(
                scoped(select(other_txt.label("t"), func.count(Case.id)))
                .where(Case.crime_type_other.is_not(None))
                .where(func.trim(Case.crime_type_other) != ""),
                date_from, date_to,
            ).group_by(other_txt).order_by(func.count(Case.id).desc()).limit(100)
        )).all()
    ]

    # 7. Crime type x district. Only non-zero cells travel.
    grid = [
        FirCrimeDistrictCell(crime_type=str(r[0]), district=str(r[1] or ""), count=int(r[2] or 0))
        for r in (await db.execute(
            in_window(
                scoped(
                    select(ctype.label("t"), Unit.name.label("d"), func.count(Case.id))
                    .select_from(Case).join(Unit, Unit.id == Case.unit_id)
                ),
                date_from, date_to,
            ).group_by(ctype, Unit.name)
        )).all()
    ]

    types = [
        FirCrimeTypeRow(
            crime_type=t,
            count=counts.get(t, 0),
            prev_count=prev_counts.get(t, 0),
            amount_lost=harm.get(t, (0.0, 0))[0],
            cases_with_victim=harm.get(t, (0.0, 0))[1],
            amount_frozen=frozen.get(t, 0.0),
            cases_with_arrest=arrested.get(t, 0),
        )
        # Union of both windows: a type that vanished this window is
        # every bit as interesting as one that appeared.
        for t in sorted(set(counts) | set(prev_counts))
    ]
    types.sort(key=lambda r: (-r.count, r.crime_type))

    return FirCrimeTypeReport(
        types=types, others=others, grid=grid,
        prev_from=prev_from, prev_to=prev_to,
    )


@router.get("/fir-daily-growth", response_model=List[FirDailyPoint])
async def get_fir_daily_growth(
    date_from: date = Query(None, alias="from"),
    date_to: date = Query(None, alias="to"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Per-day FIR count across the same window the FIR Dashboard table
    uses, for the growth line on that page.

    Filters and scoping are deliberately identical to
    compute_fir_ps_performance: registration_date (not created_at),
    NULL registration dates excluded, admin limited to its own
    (unit, PS). Summing this series therefore reproduces the table's
    grand total exactly — if the two ever disagree, one of them has a
    bug rather than a different definition."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")
    date_from, date_to = _resolve_fir_perf_window(date_from, date_to)

    # A wide-open window would zero-fill into thousands of points and
    # render as a solid smear. Cap it rather than let the browser wear
    # the cost of a request nobody can read.
    span = (date_to - date_from).days
    if span > 366:
        raise HTTPException(
            status_code=400,
            detail="Window too wide for the daily series — 366 days maximum.",
        )

    q = (
        select(
            Case.registration_date.label("day"),
            func.count(Case.id).label("count"),
            func.coalesce(func.sum(case((Case.is_financial == 1, 1), else_=0)), 0).label("fin"),
            func.coalesce(func.sum(case((Case.is_financial == 1, 0), else_=1)), 0).label("nonfin"),
        )
        .where(Case.registration_date.is_not(None))
        .where(Case.registration_date >= date_from)
        .where(Case.registration_date <= date_to)
        .group_by(Case.registration_date)
    )
    if admin.role != "super_admin":
        q = q.where(Case.unit_id == admin.unit_id).where(Case.ps_id == admin.ps_id)
    # Test fixture never appears in a dashboard figure.
    q = where_not_test(q, admin, exclude_test_unit(Case.unit_id), exclude_test_ps(Case.ps_id))

    counts: dict[date, tuple[int, int, int]] = {}
    for r in (await db.execute(q)).all():
        d = r.day
        if not isinstance(d, date):
            from datetime import datetime as _dt
            d = _dt.strptime(str(d), "%Y-%m-%d").date()
        counts[d] = (int(r.count or 0), int(r.fin or 0), int(r.nonfin or 0))

    out: List[FirDailyPoint] = []
    cur = date_from
    while cur <= date_to:
        total, fin, nonfin = counts.get(cur, (0, 0, 0))
        out.append(FirDailyPoint(day=cur, count=total, financial=fin, non_financial=nonfin))
        cur = cur + timedelta(days=1)
    return out


# ── NCRP Dashboard (2026-07-30) ─────────────────────────────────
# super_admin-only cross-PS view. mule_reports doesn't carry a
# ps_id column (pre-dates migration 008 per-PS scoping) so every
# per-PS aggregation joins through users.ps_id via submitted_by.
# KPIs are cumulative to a picked date; charts + tables use a
# from/to range on mule_reports.created_at.


def _require_super_admin(admin: CurrentUser) -> None:
    """Inline gate -- keeps the /ncrp-* routes single-role without
    introducing a shared dep just for this dashboard."""
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="NCRP Dashboard is restricted to super_admin.")


@router.get("/ncrp-summary", response_model=NcrpKpiSummary)
async def get_ncrp_summary(
    target_date: date = Query(..., alias="date",
                              description="Cumulative cutoff -- everything created on or before this date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Four KPI cards for the NCRP dashboard top row, cumulative to
    the picked date. Only submitted reports count."""
    _require_super_admin(admin)
    end = target_date + timedelta(days=1)

    total_reports = (await db.execute(
        select(func.count(MuleReport.id))
        .where(MuleReport.status == "submitted", MuleReport.created_at < end)
    )).scalar() or 0

    # Unique banks: money_transfers is the only child table with a
    # bank column, so this counts distinct banks across all submitted
    # money-transfer rows in-window.
    unique_banks = (await db.execute(
        select(func.count(func.distinct(MoneyTransfer.bank)))
        .join(MuleReport, MuleReport.id == MoneyTransfer.report_id)
        .where(MuleReport.status == "submitted", MuleReport.created_at < end,
               MoneyTransfer.bank.isnot(None), MoneyTransfer.bank != "")
    )).scalar() or 0

    total_transfer_amount = (await db.execute(
        select(func.coalesce(func.sum(MoneyTransfer.transaction_amount), 0))
        .join(MuleReport, MuleReport.id == MoneyTransfer.report_id)
        .where(MuleReport.status == "submitted", MuleReport.created_at < end)
    )).scalar() or 0

    atm_amt = (await db.execute(
        select(func.coalesce(func.sum(AtmWithdrawal.withdrawal_amount), 0))
        .join(MuleReport, MuleReport.id == AtmWithdrawal.report_id)
        .where(MuleReport.status == "submitted", MuleReport.created_at < end)
    )).scalar() or 0

    aeps_amt = (await db.execute(
        select(func.coalesce(func.sum(AepsTransaction.withdrawal_amount), 0))
        .join(MuleReport, MuleReport.id == AepsTransaction.report_id)
        .where(MuleReport.status == "submitted", MuleReport.created_at < end)
    )).scalar() or 0

    return NcrpKpiSummary(
        total_reports=int(total_reports),
        unique_banks=int(unique_banks),
        total_transfer_amount=float(total_transfer_amount),
        total_atm_aeps_amount=float(atm_amt) + float(aeps_amt),
    )


@router.get("/ncrp-ps-comparison", response_model=List[NcrpPsReportCount])
async def get_ncrp_ps_comparison(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Per-PS mule-report count within the from/to window. Every
    active PS appears zero-filled so silent stations stay visible.
    ps_id is derived from users.ps_id via mule_reports.submitted_by
    (mule_reports itself has no ps_id column)."""
    _require_super_admin(admin)
    end = date_to + timedelta(days=1)

    ps_counts = (
        select(User.ps_id.label("ps_id"), func.count(MuleReport.id).label("cnt"))
        .join(User, User.id == MuleReport.submitted_by)
        .where(MuleReport.status == "submitted",
               MuleReport.created_at >= date_from,
               MuleReport.created_at < end,
               User.ps_id.isnot(None))
        .group_by(User.ps_id)
        .subquery()
    )

    rows = (await db.execute(
        select(
            PoliceStation.id, PoliceStation.district_name, PoliceStation.station_name,
            func.coalesce(ps_counts.c.cnt, 0).label("cnt"),
        )
        .outerjoin(ps_counts, ps_counts.c.ps_id == PoliceStation.id)
        .where(PoliceStation.is_active.is_(True))
        # Test fixture is a real, active station — drop it from the
        # station LIST too, or it appears as a permanent zero row.
        .where(station_row_filter(admin))
        .order_by(PoliceStation.district_name, PoliceStation.station_name)
    )).all()

    # Resolve unit_id for each row via district_name -> units.name.
    unit_lookup = {
        u.name: u.id for u in (await db.execute(select(Unit))).scalars().all()
    }
    return [
        NcrpPsReportCount(
            unit_id=unit_lookup.get(district, 0),
            district=district,
            ps_id=ps_id,
            ps_name=station_name,
            report_count=int(cnt),
        )
        for ps_id, district, station_name, cnt in rows
    ]


@router.get("/ncrp-top-banks", response_model=List[NcrpBankConcentration])
async def get_ncrp_top_banks(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    limit: int = Query(default=10, ge=1, le=50),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Top-N banks by money-transfer count in-window. money_transfers
    is the only child table with a bank column."""
    _require_super_admin(admin)
    end = date_to + timedelta(days=1)

    rows = (await db.execute(
        select(
            MoneyTransfer.bank,
            func.count(MoneyTransfer.id).label("cnt"),
            func.coalesce(func.sum(MoneyTransfer.transaction_amount), 0).label("total"),
        )
        .join(MuleReport, MuleReport.id == MoneyTransfer.report_id)
        .where(MuleReport.status == "submitted",
               MuleReport.created_at >= date_from,
               MuleReport.created_at < end,
               MoneyTransfer.bank.isnot(None),
               MoneyTransfer.bank != "")
        .group_by(MoneyTransfer.bank)
        .order_by(func.count(MoneyTransfer.id).desc())
        .limit(limit)
    )).all()

    return [
        NcrpBankConcentration(bank=bank, transfer_count=int(cnt), total_amount=float(total))
        for bank, cnt, total in rows
    ]


@router.get("/ncrp-layer-distribution", response_model=List[LayerBucket])
async def get_ncrp_layer_distribution(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Money-transfer layer histogram in-window. Rows with NULL
    layer are excluded (they're a data-quality issue, not a real
    layer-0 concept)."""
    _require_super_admin(admin)
    end = date_to + timedelta(days=1)

    rows = (await db.execute(
        select(
            MoneyTransfer.layer,
            func.count(MoneyTransfer.id).label("cnt"),
        )
        .join(MuleReport, MuleReport.id == MoneyTransfer.report_id)
        .where(MuleReport.status == "submitted",
               MuleReport.created_at >= date_from,
               MuleReport.created_at < end,
               MoneyTransfer.layer.isnot(None))
        .group_by(MoneyTransfer.layer)
        .order_by(MoneyTransfer.layer)
    )).all()

    return [LayerBucket(layer=int(layer), count=int(cnt)) for layer, cnt in rows]


@router.get("/ncrp-top-atm-locations", response_model=List[NcrpAtmLocation])
async def get_ncrp_top_atm_locations(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    limit: int = Query(default=10, ge=1, le=50),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Top-N ATM locations ranked by total disputed cash withdrawn.
    Location is free-text -- same physical ATM may appear under
    multiple spellings; operators disambiguate by eye."""
    _require_super_admin(admin)
    end = date_to + timedelta(days=1)

    rows = (await db.execute(
        select(
            AtmWithdrawal.atm_location,
            func.count(AtmWithdrawal.id).label("cnt"),
            func.coalesce(func.sum(AtmWithdrawal.withdrawal_amount), 0).label("total"),
        )
        .join(MuleReport, MuleReport.id == AtmWithdrawal.report_id)
        .where(MuleReport.status == "submitted",
               MuleReport.created_at >= date_from,
               MuleReport.created_at < end,
               AtmWithdrawal.atm_location.isnot(None),
               AtmWithdrawal.atm_location != "")
        .group_by(AtmWithdrawal.atm_location)
        .order_by(func.coalesce(func.sum(AtmWithdrawal.withdrawal_amount), 0).desc())
        .limit(limit)
    )).all()

    return [
        NcrpAtmLocation(atm_location=loc, withdrawal_count=int(cnt), total_amount=float(total))
        for loc, cnt, total in rows
    ]


# ── Repeat Accounts (2026-07-30, super_admin only) ─────────────
# Cross-PS view of accounts appearing in multiple FIRs -- a serial-
# mule / watched-account tracker. Aggregates all_accounts by
# account_no (ignoring bank_name variations for the same number),
# counts distinct fir_no, filters by min_firs. sample_firs +
# sample_ps_labels give quick pivot lists without paging.


@router.get("/repeat-accounts", response_model=List[RepeatAccount])
async def get_repeat_accounts(
    account_type: str = Query(..., description="Account type to aggregate -- 'Mule' or 'Non-Mule'"),
    min_firs: int = Query(default=2, ge=2, le=50,
                          description="Minimum distinct FIR count to be considered repeat"),
    limit: int = Query(default=1000, ge=1, le=5000,
                       description="Max rows. 100 was the old default and it "
                                   "silently hid 599 of 711 repeat accounts at "
                                   "min_firs=2 — the client shows a warning if "
                                   "this cap is ever reached."),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Accounts of a given type registered against >= min_firs
    distinct FIRs across ALL PSes. Super_admin only -- cross-PS
    view. Grouped by account_no; other fields (bank/holder/state)
    take the min value as a stable representative."""
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Repeat Accounts is restricted to super_admin.")
    if account_type not in {"Mule", "Non-Mule"}:
        raise HTTPException(
            status_code=400,
            detail="account_type must be 'Mule' or 'Non-Mule'.",
        )

    # Aggregate by account_no. Non-null fir_no only (blank rows can't
    # anchor a repeat by definition). MySQL GROUP_CONCAT gives us the
    # sample FIR + PS lists in one round-trip; they're truncated at
    # group_concat_max_len (default 1024) which is fine for a preview.
    ps_label = func.concat(PoliceStation.district_name, "/", PoliceStation.station_name)
    rows = (await db.execute(
        select(
            AllAccount.account_no,
            func.min(AllAccount.bank_name).label("bank_name"),
            func.min(AllAccount.account_holder_name).label("account_holder_name"),
            func.min(AllAccount.branch_state).label("branch_state"),
            func.count(func.distinct(AllAccount.fir_no)).label("fir_count"),
            func.count(func.distinct(AllAccount.ps_id)).label("ps_count"),
            func.group_concat(func.distinct(AllAccount.fir_no)).label("firs_csv"),
            func.group_concat(func.distinct(ps_label)).label("ps_csv"),
        )
        .join(PoliceStation, PoliceStation.id == AllAccount.ps_id)
        .where(
            AllAccount.account_type == account_type,
            AllAccount.fir_no.isnot(None),
            AllAccount.fir_no != "",
        )
        .group_by(AllAccount.account_no)
        .having(func.count(func.distinct(AllAccount.fir_no)) >= min_firs)
        .order_by(func.count(func.distinct(AllAccount.fir_no)).desc())
        .limit(limit)
    )).all()

    def _split(csv: str | None, cap: int = 10) -> list[str]:
        if not csv:
            return []
        parts = [p.strip() for p in csv.split(",") if p.strip()]
        # Preserve order but dedup -- GROUP_CONCAT DISTINCT already
        # dedups, so this is belt-and-braces.
        seen: set[str] = set()
        out: list[str] = []
        for p in parts:
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
            if len(out) >= cap:
                break
        return out

    return [
        RepeatAccount(
            account_no=account_no,
            bank_name=bank_name,
            account_holder_name=holder,
            account_type=account_type,
            branch_state=branch_state,
            fir_count=int(fir_count),
            ps_count=int(ps_count),
            sample_firs=_split(firs_csv),
            sample_ps_labels=_split(ps_csv),
        )
        for account_no, bank_name, holder, branch_state, fir_count, ps_count, firs_csv, ps_csv in rows
    ]


@router.get("/account-fir-history", response_model=List[AccountFirOccurrence])
async def get_account_fir_history(
    account_no: str = Query(..., min_length=1, max_length=50,
                            description="Account number to look up in the All Accounts register"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Every FIR that this `account_no` is registered against, one
    row per (fir, PS) pair, with the layer it was recorded at in
    each. Drives the Repeat Accounts drill-down modal so an
    operator can see "Layer 2 in FIR X at Bagalkot, Layer 4 in FIR
    Y at Hubballi". super_admin only -- cross-PS."""
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Account history is restricted to super_admin.")
    acct = account_no.strip()
    if not acct:
        raise HTTPException(status_code=400, detail="account_no is required.")

    rows = (await db.execute(
        select(
            AllAccount.fir_no,
            PoliceStation.station_name,
            PoliceStation.district_name,
            AllAccount.layer,
            AllAccount.account_type,
            AllAccount.account_holder_name,
            AllAccount.bank_name,
            AllAccount.branch_state,
            AllAccount.created_at,
        )
        .join(PoliceStation, PoliceStation.id == AllAccount.ps_id)
        .where(
            AllAccount.account_no == acct,
            AllAccount.fir_no.isnot(None),
            AllAccount.fir_no != "",
        )
        .order_by(AllAccount.created_at.desc())
    )).all()

    return [
        AccountFirOccurrence(
            fir_no=fir_no,
            ps_name=ps_name,
            district=district,
            layer=int(layer) if layer is not None else None,
            account_type=account_type,
            account_holder_name=holder,
            bank_name=bank_name,
            branch_state=branch_state,
            created_at=created_at.isoformat() if created_at is not None else None,
        )
        for fir_no, ps_name, district, layer, account_type, holder, bank_name, branch_state, created_at in rows
    ]


@router.get("/crypto-trail", response_model=CryptoTrailSummary)
async def get_crypto_trail(
    account_type: str = Query("All", description="All | Mule | Non-Mule | Victim"),
    evidence_limit: int = Query(60, ge=0, le=500,
        description="Sample narrations returned so a finding can be eyeballed"),
    account_limit: int = Query(500, ge=1, le=5000),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Accounts whose statements name a crypto exchange or asset.

    super_admin only, like the other cross-PS analysis tabs.

    Reads crypto_txn, rebuilt by analysis/build_crypto.py. Detection is
    NOT done here: matching narration patterns across 19M rows behind a
    page load would be both slow and untestable. See migration 024.

    WHY THE EVIDENCE SAMPLE EXISTS
    ------------------------------
    Because this detector has been wrong twice, convincingly:

      LIKE '%okx%'   168 hits -- "ASHOKX009328", "ZOaazcokX010373";
                     reference codes and a common Indian name.
      \beth\b        58 hits, which would have been the LARGEST
                     category on this screen -- every one the same
                     bank header, "JOINT HOLDERS : Cust ID : ... ETH".

    Word boundaries fixed the first and did nothing for the second.
    Three-letter tickers are gone entirely as a result. What remains
    is exchange names and four-character-plus assets, but the class of
    error is not closed -- a new bank's narration format could
    reintroduce it tomorrow. So every response carries real narrations
    with the match visible, and an officer can reject the finding in
    seconds rather than opening an inquiry on it.

    MONEY FOLLOWS THE SAME RULE AS MONEY TRAIL
    ------------------------------------------
    Only chain_ok = 1 rows are summed. Untested rows are counted and
    reported apart, never added in.
    """
    if admin.role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Crypto analysis is available to SCRB HQ accounts only.")
    if account_type != "All" and account_type not in ACCOUNT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"account_type must be 'All' or one of: {', '.join(sorted(ACCOUNT_TYPES))}")

    C = CryptoTxn

    def scoped(q):
        q = (q.select_from(C)
              .join(AllAccount, AllAccount.id == C.account_id)
              .outerjoin(PoliceStation, PoliceStation.id == AllAccount.ps_id))
        q = where_not_test(q, admin,
                           exclude_test_unit(AllAccount.unit_id),
                           exclude_test_ps(AllAccount.ps_id))
        if account_type != "All":
            q = q.where(AllAccount.account_type == account_type)
        return q

    # "Never scanned" and "scanned, found nothing" are different answers.
    # An empty table with no scan behind it must not read as "no crypto
    # in this corpus" -- that is a reassuring statement about data that
    # was never looked at.
    ever = int((await db.execute(
        select(func.count()).select_from(C))).scalar() or 0)

    head = (await db.execute(scoped(select(
        func.count(),
        func.count(func.distinct(C.account_id)),
        func.count(func.distinct(C.exchange)),
        func.coalesce(func.sum(case((C.chain_ok == 1, C.debit), else_=0)), 0),
        func.coalesce(func.sum(case((C.chain_ok == 1, C.credit), else_=0)), 0),
        func.coalesce(func.sum(case((C.chain_ok == -1, 1), else_=0)), 0),
    )))).first()

    by_exchange = [
        CryptoExchangeRow(exchange=r[0], txns=int(r[1]),
                          accounts=int(r[2]), debit=float(r[3] or 0),
                          credit=float(r[4] or 0))
        for r in (await db.execute(scoped(select(
            C.exchange,
            func.count(),
            func.count(func.distinct(C.account_id)),
            func.coalesce(func.sum(case((C.chain_ok == 1, C.debit), else_=0)), 0),
            func.coalesce(func.sum(case((C.chain_ok == 1, C.credit), else_=0)), 0),
        )).group_by(C.exchange).order_by(func.count().desc()))).all()
    ]

    top_accounts = [
        CryptoAccountRow(
            account_id=r[0], account_holder_name=r[1], account_no=r[2],
            bank_name=r[3], fir_no=r[4], account_type=r[5], ps_name=r[6],
            district=r[7], ps_id=r[8],
            exchanges=sorted(set((r[9] or "").split(","))) if r[9] else [],
            txns=int(r[10]), debit=float(r[11] or 0), credit=float(r[12] or 0),
            first_txn=r[13], last_txn=r[14], untested_txns=int(r[15] or 0),
        )
        for r in (await db.execute(scoped(select(
            C.account_id,
            AllAccount.account_holder_name, AllAccount.account_no,
            AllAccount.bank_name, AllAccount.fir_no, AllAccount.account_type,
            PoliceStation.station_name, Unit.name, PoliceStation.id,
            func.group_concat(C.exchange.distinct()),
            func.count(),
            func.coalesce(func.sum(case((C.chain_ok == 1, C.debit), else_=0)), 0),
            func.coalesce(func.sum(case((C.chain_ok == 1, C.credit), else_=0)), 0),
            func.min(C.txn_date), func.max(C.txn_date),
            func.coalesce(func.sum(case((C.chain_ok == -1, 1), else_=0)), 0),
        )).group_by(
            C.account_id, AllAccount.account_holder_name, AllAccount.account_no,
            AllAccount.bank_name, AllAccount.fir_no, AllAccount.account_type,
            PoliceStation.station_name, Unit.name, PoliceStation.id,
        ).order_by(func.count().desc()).limit(account_limit))).all()
    ]

    evidence = [
        CryptoEvidenceRow(
            exchange=r[0], account_holder_name=r[1], account_no=r[2],
            fir_no=r[3], txn_date=r[4], debit=float(r[5] or 0),
            credit=float(r[6] or 0), description=r[7], chain_ok=int(r[8]),
        )
        for r in (await db.execute(scoped(select(
            C.exchange, AllAccount.account_holder_name, AllAccount.account_no,
            AllAccount.fir_no, C.txn_date, C.debit, C.credit,
            C.description, C.chain_ok,
        )).order_by(C.txn_date.desc()).limit(evidence_limit))).all()
    ] if evidence_limit else []

    return CryptoTrailSummary(
        account_type=account_type,
        scanned=ever > 0,
        total_txns=int(head[0] or 0) if head else 0,
        accounts=int(head[1] or 0) if head else 0,
        exchanges_seen=int(head[2] or 0) if head else 0,
        total_debit=float(head[3] or 0) if head else 0,
        total_credit=float(head[4] or 0) if head else 0,
        untested_txns=int(head[5] or 0) if head else 0,
        by_exchange=by_exchange,
        top_accounts=top_accounts,
        evidence=evidence,
    )


@router.get("/mule-accounts", response_model=MuleAccountList)
async def get_mule_accounts(
    state_scope: str = Query("all",
        description="all | karnataka | other — on all_accounts.branch_state, "
                    "i.e. where the BANK BRANCH is, not the police district"),
    limit: int = Query(30000, ge=1, le=40000,
        description="Max rows. The client paginates and exports these, so it "
                    "needs the whole set, not one page of it."),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Every account recorded as Mule, connected or not.

    super_admin only, on the same reasoning as the rest of this file:
    the list crosses police station boundaries, and a station-level
    admin reading another district's accounts would breach the VAPT
    7.7/7.8 scoping rule.

    WHY THIS IS NOT THE MULE NETWORK LIST
    -------------------------------------
    /mule-network answers "who is connected to whom" and can only
    contain an account that HAS a link — which requires that account's
    statement to have been parsed AND someone it paid to also be on
    file. That is a minority of mule accounts. Reading the network list
    as the roll of mule accounts therefore undercounts badly, and the
    gap is invisible unless both numbers are on screen.

    This endpoint is the roll. `links` is carried on each row so the
    two questions stay visibly distinct: a row with 0 links is not a
    cleared account, it is an account with nothing on file yet.

    ATTACHED IS NOT PARSED
    ----------------------
    `has_statement_file` means a file is attached to the record.
    `statement_parsed` means it yielded transactions. Roughly 18% of
    the corpus is image-only PDFs that satisfy the first and fail the
    second, so collapsing them into one flag would report a chasing job
    as finished.
    """
    if admin.role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Mule account listing is available to SCRB HQ accounts only.")
    if state_scope not in _MT_SCOPES:
        raise HTTPException(status_code=422,
            detail=f"state_scope must be one of: {', '.join(sorted(_MT_SCOPES))}")

    st = func.lower(func.trim(func.coalesce(AllAccount.branch_state, "")))

    def scoped(q):
        if state_scope == "karnataka":
            return q.where(st == "karnataka")
        if state_scope == "other":
            # Blank state is NOT swept in here. An unrecorded branch
            # state is not evidence of a branch outside Karnataka, and
            # counting it as one would inflate "Rest of India" with
            # data-entry gaps.
            return q.where(st != "karnataka").where(st != "")
        return q

    total = (await db.execute(
        scoped(select(func.count()).select_from(AllAccount)
               .where(AllAccount.account_type == "Mule")))).scalar() or 0

    # Counted only under "All States": under a scope filter the number
    # would either be zero or the whole set, and mean nothing either way.
    blank_state = 0
    if state_scope == "all":
        blank_state = (await db.execute(
            select(func.count()).select_from(AllAccount)
            .where(AllAccount.account_type == "Mule")
            .where(st == ""))).scalar() or 0

    q = (scoped(
            select(
                AllAccount.id, AllAccount.fir_no,
                PoliceStation.station_name, Unit.name,
                # Trimmed on the way out, not in the table. A fair
                # number of holder names carry leading tabs and spaces
                # from the source upload, which sorts them above "A"
                # and renders the column ragged. Cleaning the stored
                # value is a data-quality job with its own audit
                # trail; presenting it readably is this endpoint's.
                func.trim(AllAccount.account_holder_name),
                AllAccount.account_no,
                AllAccount.bank_name, AllAccount.branch_name,
                func.trim(func.coalesce(AllAccount.branch_state, "")),
                AllAccount.ifsc_code, AllAccount.kyc_mobile, AllAccount.layer,
                AllAccount.account_statement_path,
            )
            .select_from(AllAccount)
            .where(AllAccount.account_type == "Mule"))
         # OUTER joins on both. An account whose PS or unit row is
         # missing is still a mule account, and an inner join would
         # drop it from the roll without saying so.
         .outerjoin(PoliceStation, PoliceStation.id == AllAccount.ps_id)
         .outerjoin(Unit, Unit.id == AllAccount.unit_id)
         .order_by(func.trim(AllAccount.account_holder_name))
         .limit(limit))
    rows = (await db.execute(q)).all()
    ids = {str(r[0]) for r in rows}

    # Link counts, merged in Python rather than joined. mule_account_link
    # is ~1,700 rows and a link counts for BOTH ends, which as SQL would
    # be two correlated subqueries per account across ~14,000 accounts.
    link_n: dict[str, int] = {}
    link_x: dict[str, int] = {}
    for src, dst, xf in (await db.execute(text(
            "SELECT src_account_id, dst_account_id, cross_fir "
            "FROM mule_account_link"))).all():
        for side in (str(src), str(dst)):
            if side not in ids:
                continue
            link_n[side] = link_n.get(side, 0) + 1
            if xf:
                link_x[side] = link_x.get(side, 0) + 1

    parsed_ids = {
        str(r[0]) for r in (await db.execute(
            select(AccountStatementSummary.account_id)
            .where(AccountStatementSummary.txns > 0)
            .distinct())).all()
    } & ids

    out = [
        MuleAccountRow(
            account_id=str(r[0]), fir_no=r[1], ps_name=r[2], district=r[3],
            account_holder_name=r[4], account_no=r[5], bank_name=r[6],
            branch_name=r[7], branch_state=r[8] or None, ifsc_code=r[9],
            kyc_mobile=r[10], layer=r[11],
            links=link_n.get(str(r[0]), 0),
            cross_fir_links=link_x.get(str(r[0]), 0),
            has_statement_file=bool(r[12]),
            statement_parsed=str(r[0]) in parsed_ids,
        )
        for r in rows
    ]
    return MuleAccountList(
        state_scope=state_scope,
        total_mule_accounts=int(total),
        accounts_without_state=int(blank_state),
        in_network=sum(1 for r in out if r.links > 0),
        parsed=sum(1 for r in out if r.statement_parsed),
        rows=out,
    )
