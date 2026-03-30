from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.case import Case
from models.arrest import Arrest
from models.lien_account import LienAccount
from models.refund import Refund
from models.unit import Unit
from schemas.dashboard import KpiSummary, UnitComparison
from api.deps import require_admin, CurrentUser

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=KpiSummary)
async def get_summary(
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total_cases = (await db.execute(select(func.count(Case.id)))).scalar() or 0
    total_arrests = (await db.execute(
        select(func.count(Arrest.id)).join(Case, Arrest.case_id == Case.id)
    )).scalar() or 0
    total_amount_lien_marked = float((await db.execute(
        select(func.coalesce(func.sum(LienAccount.amount_lien_marked), 0))
        .join(Case, LienAccount.case_id == Case.id)
    )).scalar() or 0)
    total_amount_refunded = float((await db.execute(
        select(func.coalesce(func.sum(Refund.amount), 0))
        .join(Case, Refund.case_id == Case.id)
        .where(Refund.refunded == "yes")
    )).scalar() or 0)
    units_submitted = (await db.execute(
        select(func.count(func.distinct(Case.unit_id)))
    )).scalar() or 0
    units_total = (await db.execute(
        select(func.count(Unit.id)).where(Unit.is_active == True)
    )).scalar() or 0

    return KpiSummary(
        total_cases=int(total_cases),
        total_arrests=int(total_arrests),
        total_amount_lien_marked=total_amount_lien_marked,
        total_amount_refunded=total_amount_refunded,
        units_submitted=int(units_submitted),
        units_total=int(units_total),
    )


@router.get("/unit-comparison", response_model=List[UnitComparison])
async def get_unit_comparison(
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(
            Unit.name.label("unit_name"),
            func.coalesce(func.count(Case.id), 0).label("cases"),
        )
        .outerjoin(Case, Case.unit_id == Unit.id)
        .where(Unit.is_active == True)
        .group_by(Unit.id, Unit.name)
        .order_by(func.count(Case.id).desc())
    )).all()

    results = []
    for r in rows:
        arrest_count = (await db.execute(
            select(func.count(Arrest.id))
            .join(Case, Arrest.case_id == Case.id)
            .join(Unit, Case.unit_id == Unit.id)
            .where(Unit.name == r.unit_name)
        )).scalar() or 0

        lien_amount = float((await db.execute(
            select(func.coalesce(func.sum(LienAccount.amount_lien_marked), 0))
            .join(Case, LienAccount.case_id == Case.id)
            .join(Unit, Case.unit_id == Unit.id)
            .where(Unit.name == r.unit_name)
        )).scalar() or 0)

        results.append(UnitComparison(
            unit_name=r.unit_name,
            cases=int(r.cases),
            arrests=int(arrest_count),
            amount_lien_marked=lien_amount,
        ))

    return results
