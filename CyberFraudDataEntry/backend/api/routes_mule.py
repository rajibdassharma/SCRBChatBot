from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.mule_entry import MuleEntry
from models.unit import Unit
from schemas.mule import MuleCreate, MuleResponse
from api.deps import get_current_user, require_admin, CurrentUser

router = APIRouter(prefix="/api/v1/mule", tags=["mule"])

_MULE_FIELDS = [
    "accounts_most_liens", "recruiters_for_lien_accounts",
    "accounts_max_money_routed", "accounts_max_transactions",
    "recency_atm_transactions", "cash_withdrawals_mule_wise",
    "atm_geo_identification", "atm_table_by_transactions",
    "cheque_withdrawal_branches", "money_left_system_stats",
    "crypto_mule_accounts",
]


def _entry_to_response(entry: MuleEntry, unit_name: str | None = None) -> dict:
    d = {f: getattr(entry, f) for f in _MULE_FIELDS}
    d.update(
        id=entry.id,
        unit_id=entry.unit_id,
        unit_name=unit_name,
        report_date=entry.report_date,
        submitted_by=entry.submitted_by,
        created_at=str(entry.created_at) if entry.created_at else None,
        updated_at=str(entry.updated_at) if entry.updated_at else None,
    )
    return d


@router.post("/", response_model=MuleResponse)
async def upsert_mule(
    body: MuleCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    unit_id = current_user.unit_id
    if not unit_id:
        raise HTTPException(status_code=403, detail="No district assigned to this account.")

    existing = (await db.execute(
        select(MuleEntry).where(MuleEntry.unit_id == unit_id, MuleEntry.report_date == body.report_date)
    )).scalar_one_or_none()

    if existing:
        values = {f: getattr(body, f) for f in _MULE_FIELDS}
        values["submitted_by"] = current_user.user_id
        await db.execute(update(MuleEntry).where(MuleEntry.id == existing.id).values(**values))
        await db.commit()
        await db.refresh(existing)
        return _entry_to_response(existing, current_user.unit_name)
    else:
        entry = MuleEntry(unit_id=unit_id, report_date=body.report_date, submitted_by=current_user.user_id)
        for f in _MULE_FIELDS:
            setattr(entry, f, getattr(body, f))
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return _entry_to_response(entry, current_user.unit_name)


@router.get("/", response_model=Optional[MuleResponse])
async def get_own_mule(
    date: date = Query(..., alias="date"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    unit_id = current_user.unit_id
    if not unit_id:
        raise HTTPException(status_code=403, detail="Use /all endpoint for admin access")

    entry = (await db.execute(
        select(MuleEntry).where(MuleEntry.unit_id == unit_id, MuleEntry.report_date == date)
    )).scalar_one_or_none()

    if not entry:
        return None
    return _entry_to_response(entry, current_user.unit_name)


@router.get("/history", response_model=List[MuleResponse])
async def get_mule_history(
    limit: int = Query(30, ge=1, le=365),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    unit_id = current_user.unit_id
    if not unit_id:
        raise HTTPException(status_code=403, detail="Use /all endpoint for admin access")

    entries = (await db.execute(
        select(MuleEntry)
        .where(MuleEntry.unit_id == unit_id)
        .order_by(MuleEntry.report_date.desc())
        .limit(limit)
    )).scalars().all()

    return [_entry_to_response(e, current_user.unit_name) for e in entries]


@router.get("/all", response_model=List[MuleResponse])
async def get_all_mule(
    date: date = Query(..., alias="date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    entries = (await db.execute(
        select(MuleEntry).where(MuleEntry.report_date == date)
    )).scalars().all()

    units = (await db.execute(select(Unit))).scalars().all()
    unit_map = {u.id: u.name for u in units}

    return [_entry_to_response(e, unit_map.get(e.unit_id)) for e in entries]
