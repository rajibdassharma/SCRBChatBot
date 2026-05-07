from __future__ import annotations

from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.case import Case
from models.arrest import Arrest
from models.lien_account import LienAccount
from models.unfreeze_detail import UnfreezeDetail
from models.refund import Refund
from models.petition import Petition
from models.dsr_entry import DsrEntry
from models.mule_entry import MuleEntry
from models.unit import Unit
from schemas.dashboard import KpiSummary, UnitComparison, TrendPoint, SubmissionStatus
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
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    total_cases = (await db.execute(
        _scope_to_unit(select(func.count(Case.id)), admin)
    )).scalar() or 0

    total_arrests = (await db.execute(
        _scope_to_unit(
            select(func.count(Arrest.id)).join(Case, Arrest.case_id == Case.id),
            admin,
        )
    )).scalar() or 0

    total_amount_lien_marked = float((await db.execute(
        _scope_to_unit(
            select(func.coalesce(func.sum(LienAccount.amount_lien_marked), 0))
            .join(Case, LienAccount.case_id == Case.id),
            admin,
        )
    )).scalar() or 0)

    total_amount_refunded = float((await db.execute(
        _scope_to_unit(
            select(func.coalesce(func.sum(Refund.amount), 0))
            .join(Case, Refund.case_id == Case.id),
            admin,
        ).where(Refund.refunded == "yes")
    )).scalar() or 0)

    total_accounts_lien_marked = (await db.execute(
        _scope_to_unit(
            select(func.count(LienAccount.id)).join(Case, LienAccount.case_id == Case.id),
            admin,
        )
    )).scalar() or 0

    total_accounts_defreezed = (await db.execute(
        _scope_to_unit(
            select(func.count(UnfreezeDetail.id)).join(Case, UnfreezeDetail.case_id == Case.id),
            admin,
        )
    )).scalar() or 0

    # Units submitted = how many distinct PSes have at least one case
    if admin.role == "super_admin":
        units_submitted = (await db.execute(
            select(func.count(func.distinct(Case.unit_id)))
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
        total_accounts_lien_marked=int(total_accounts_lien_marked),
        total_accounts_defreezed=int(total_accounts_defreezed),
        units_submitted=int(units_submitted),
        units_total=int(units_total),
    )


@router.get("/unit-comparison", response_model=List[UnitComparison])
async def get_unit_comparison(
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """admin: single row for own PS. super_admin: row per PS that has cases."""
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
            .group_by(Unit.id, Unit.name)
        )).all()

    out: List[UnitComparison] = []
    for unit_id, unit_name, case_count in rows:
        arrest_count = (await db.execute(
            select(func.count(Arrest.id))
            .join(Case, Arrest.case_id == Case.id)
            .where(Case.unit_id == unit_id)
        )).scalar() or 0
        lien_amount = float((await db.execute(
            select(func.coalesce(func.sum(LienAccount.amount_lien_marked), 0))
            .join(Case, LienAccount.case_id == Case.id)
            .where(Case.unit_id == unit_id)
        )).scalar() or 0)
        out.append(UnitComparison(
            unit_name=unit_name,
            cases=int(case_count or 0),
            arrests=int(arrest_count),
            amount_lien_marked=lien_amount,
        ))
    return out


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


@router.get("/submission-status", response_model=List[SubmissionStatus])
async def get_submission_status(
    target_date: date = Query(..., alias="date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """For a given date, list the PSes in scope with whether they
    submitted their DSR. admin: own PS only. super_admin: all active PSes."""
    if admin.role == "admin" and not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    if admin.role == "super_admin":
        units = (await db.execute(
            select(Unit.id, Unit.name).where(Unit.is_active == True)  # noqa: E712
            .order_by(Unit.name)
        )).all()
    else:
        units = (await db.execute(
            select(Unit.id, Unit.name).where(Unit.id == admin.unit_id)
        )).all()

    dsr_submitted_ids = set((await db.execute(
        select(DsrEntry.unit_id).where(DsrEntry.report_date == target_date)
    )).scalars().all())
    mule_submitted_ids = set((await db.execute(
        select(MuleEntry.unit_id).where(MuleEntry.report_date == target_date)
    )).scalars().all())

    return [
        SubmissionStatus(
            unit_id=int(uid),
            unit_name=uname,
            dsr_submitted=uid in dsr_submitted_ids,
            mule_submitted=uid in mule_submitted_ids,
        )
        for uid, uname in units
    ]
