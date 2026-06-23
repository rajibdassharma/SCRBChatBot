"""
POST /api/v1/nil/declare  — operator marks today (or another date) as NIL
                            for their PS. Idempotent — re-declaring the
                            same (unit_id, ps_id, date) is a no-op, not
                            an error.

GET  /api/v1/nil/today    — was today already declared NIL by the
                            caller's PS? Used to grey out the sidebar
                            button after the user clicks it.
"""
from __future__ import annotations

from datetime import date as date_cls

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.nil_declaration import NilDeclaration
from models.user import User
from schemas.nil import NilDeclarationCreate, NilDeclarationResponse
from api.deps import get_current_user, CurrentUser

router = APIRouter(prefix="/api/v1/nil", tags=["nil"])


async def _row_to_response(db: AsyncSession, row: NilDeclaration) -> NilDeclarationResponse:
    declarer = (await db.execute(
        select(User).where(User.id == row.declared_by)
    )).scalar_one_or_none()
    return NilDeclarationResponse(
        id=str(row.id),
        unit_id=int(row.unit_id),
        ps_id=int(row.ps_id),
        declared_by=int(row.declared_by),
        declared_by_name=(declarer.full_name or declarer.username) if declarer else None,
        nil_date=row.nil_date,
        reason=row.reason,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


@router.post("/declare", response_model=NilDeclarationResponse)
async def declare_nil(
    body: NilDeclarationCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.unit_id or not current_user.ps_id:
        raise HTTPException(
            status_code=403,
            detail="Cannot declare NIL — your account isn't tied to a specific PS.",
        )

    target_date = body.nil_date or date_cls.today()

    # Idempotent: if a row already exists for this (unit, ps, date),
    # return it instead of failing on the UNIQUE index.
    existing = (await db.execute(
        select(NilDeclaration)
        .where(NilDeclaration.unit_id == current_user.unit_id)
        .where(NilDeclaration.ps_id == current_user.ps_id)
        .where(NilDeclaration.nil_date == target_date)
    )).scalar_one_or_none()
    if existing:
        return await _row_to_response(db, existing)

    row = NilDeclaration(
        unit_id=current_user.unit_id,
        ps_id=current_user.ps_id,
        declared_by=current_user.user_id,
        nil_date=target_date,
        reason=(body.reason or None),
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        # Race: another request for the same key inserted between our
        # SELECT and our INSERT. Re-read and return that row.
        await db.rollback()
        existing = (await db.execute(
            select(NilDeclaration)
            .where(NilDeclaration.unit_id == current_user.unit_id)
            .where(NilDeclaration.ps_id == current_user.ps_id)
            .where(NilDeclaration.nil_date == target_date)
        )).scalar_one()
        return await _row_to_response(db, existing)
    return await _row_to_response(db, row)


@router.get("/today", response_model=NilDeclarationResponse | None)
async def today_nil(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns the NIL declaration for today for the caller's PS, or None."""
    if not current_user.unit_id or not current_user.ps_id:
        return None
    today = date_cls.today()
    row = (await db.execute(
        select(NilDeclaration)
        .where(NilDeclaration.unit_id == current_user.unit_id)
        .where(NilDeclaration.ps_id == current_user.ps_id)
        .where(NilDeclaration.nil_date == today)
    )).scalar_one_or_none()
    if not row:
        return None
    return await _row_to_response(db, row)
