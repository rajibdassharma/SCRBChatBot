from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
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


# Per VAPT 7.8: there is no global admin role. Every admin is a PS admin and
# is scoped to their own unit_id. Dashboard aggregates therefore reflect a
# single PS - never cross-PS data.


@router.get("/summary", response_model=KpiSummary)
async def get_summary(
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    total_cases = (await db.execute(
        select(func.count(Case.id)).where(Case.unit_id == admin.unit_id)
    )).scalar() or 0

    total_arrests = (await db.execute(
        select(func.count(Arrest.id))
        .join(Case, Arrest.case_id == Case.id)
        .where(Case.unit_id == admin.unit_id)
    )).scalar() or 0

    total_amount_lien_marked = float((await db.execute(
        select(func.coalesce(func.sum(LienAccount.amount_lien_marked), 0))
        .join(Case, LienAccount.case_id == Case.id)
        .where(Case.unit_id == admin.unit_id)
    )).scalar() or 0)

    total_amount_refunded = float((await db.execute(
        select(func.coalesce(func.sum(Refund.amount), 0))
        .join(Case, Refund.case_id == Case.id)
        .where(Case.unit_id == admin.unit_id, Refund.refunded == "yes")
    )).scalar() or 0)

    # With per-PS scoping, "units submitted" is a 0/1 indicator for the
    # admin's own PS, and "units total" is fixed at 1. Kept in the response
    # for backward-compat with the existing frontend KPI tiles.
    units_submitted = 1 if total_cases > 0 else 0
    units_total = 1

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
    """Returns a single row for the admin's PS only (VAPT 7.8 - no cross-PS)."""
    if not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    unit = (await db.execute(
        select(Unit).where(Unit.id == admin.unit_id)
    )).scalar_one_or_none()
    if not unit:
        return []

    case_count = (await db.execute(
        select(func.count(Case.id)).where(Case.unit_id == admin.unit_id)
    )).scalar() or 0

    arrest_count = (await db.execute(
        select(func.count(Arrest.id))
        .join(Case, Arrest.case_id == Case.id)
        .where(Case.unit_id == admin.unit_id)
    )).scalar() or 0

    lien_amount = float((await db.execute(
        select(func.coalesce(func.sum(LienAccount.amount_lien_marked), 0))
        .join(Case, LienAccount.case_id == Case.id)
        .where(Case.unit_id == admin.unit_id)
    )).scalar() or 0)

    return [UnitComparison(
        unit_name=unit.name,
        cases=int(case_count),
        arrests=int(arrest_count),
        amount_lien_marked=lien_amount,
    )]
