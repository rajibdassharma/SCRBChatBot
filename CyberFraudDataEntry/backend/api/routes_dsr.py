from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.dsr_entry import DsrEntry
from models.unit import Unit
from schemas.dsr import DsrCreate, DsrResponse
from api.deps import get_current_user, require_admin, CurrentUser

router = APIRouter(prefix="/api/v1/dsr", tags=["dsr"])

# Fields to copy between schema and ORM
_DSR_FIELDS = [
    "cases", "petitions", "details_of_arrest",
    "case_type", "cumulative_amount_lien_marked", "cumulative_accounts_lien_marked",
    "cumulative_accounts_defreezed", "amount_refunded_to_victim",
    "ui_cases_pending_2021", "ui_cases_pending_2022", "ui_cases_pending_2023",
    "ui_cases_pending_2024", "ui_cases_pending_2025", "ui_cases_pending_2026",
    "disposed_detected_chargesheeted", "disposed_transferred", "disposed_false", "disposed_undetected",
    "trial_convicted", "trial_discharged", "trial_acquitted",
    "trial_abated", "trial_compounded", "trial_ut",
]


def _entry_to_response(entry: DsrEntry, unit_name: str | None = None) -> dict:
    d = {f: getattr(entry, f) for f in _DSR_FIELDS}
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
    """Return (unit_id, ps_id) for the caller. Every DSR route is
    (unit, ps)-scoped after migration 008 (2026-07-08)."""
    if not current_user.unit_id:
        raise HTTPException(status_code=403, detail="No district assigned to this account.")
    if not current_user.ps_id:
        raise HTTPException(status_code=403, detail="No police station assigned to this account.")
    return current_user.unit_id, current_user.ps_id


@router.post("/", response_model=DsrResponse)
async def upsert_dsr(
    body: DsrCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    unit_id, ps_id = _require_scope(current_user)

    existing = (await db.execute(
        select(DsrEntry).where(
            DsrEntry.unit_id == unit_id,
            DsrEntry.ps_id == ps_id,
            DsrEntry.report_date == body.report_date,
        )
    )).scalar_one_or_none()

    if existing:
        values = {f: getattr(body, f) for f in _DSR_FIELDS}
        values["submitted_by"] = current_user.user_id
        await db.execute(update(DsrEntry).where(DsrEntry.id == existing.id).values(**values))
        await db.commit()
        await db.refresh(existing)
        return _entry_to_response(existing, current_user.unit_name)
    else:
        entry = DsrEntry(
            unit_id=unit_id,
            ps_id=ps_id,
            report_date=body.report_date,
            submitted_by=current_user.user_id,
        )
        for f in _DSR_FIELDS:
            setattr(entry, f, getattr(body, f))
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return _entry_to_response(entry, current_user.unit_name)


@router.get("/", response_model=Optional[DsrResponse])
async def get_own_dsr(
    date: date = Query(..., alias="date"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    unit_id, ps_id = _require_scope(current_user)

    entry = (await db.execute(
        select(DsrEntry).where(
            DsrEntry.unit_id == unit_id,
            DsrEntry.ps_id == ps_id,
            DsrEntry.report_date == date,
        )
    )).scalar_one_or_none()

    if not entry:
        return None
    return _entry_to_response(entry, current_user.unit_name)


@router.get("/history", response_model=List[DsrResponse])
async def get_dsr_history(
    limit: int = Query(30, ge=1, le=365),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    unit_id, ps_id = _require_scope(current_user)

    entries = (await db.execute(
        select(DsrEntry)
        .where(DsrEntry.unit_id == unit_id, DsrEntry.ps_id == ps_id)
        .order_by(DsrEntry.report_date.desc())
        .limit(limit)
    )).scalars().all()

    return [_entry_to_response(e, current_user.unit_name) for e in entries]


@router.get("/all", response_model=List[DsrResponse])
async def get_all_dsr(
    date: date = Query(..., alias="date"),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin view of DSR entries on a date.

    Per VAPT 7.8 + migration 008: scoped to the admin's own PS only.
    Equivalent to GET /dsr/?date= when called by an admin — kept for
    frontend backward compatibility.
    """
    unit_id, ps_id = _require_scope(admin)

    entries = (await db.execute(
        select(DsrEntry).where(
            DsrEntry.report_date == date,
            DsrEntry.unit_id == unit_id,
            DsrEntry.ps_id == ps_id,
        )
    )).scalars().all()

    return [_entry_to_response(e, admin.unit_name) for e in entries]
