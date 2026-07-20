"""CRUD routes for the All Accounts feature (2026-07-18).

Per-PS scoping identical to Cases (VAPT 7.7 + 7.8): every read/write
runs `check_record_access` and lists are filtered to the caller's
own (unit_id, ps_id). super_admin sees all PSes.

Serial No is auto-assigned server-side as `MAX(serial_no) + 1`
scoped to the caller's (unit_id, ps_id). A unique constraint on
`(unit_id, ps_id, serial_no)` catches the (rare) race where two
concurrent creates pick the same next number — we retry once.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.deps import CurrentUser, check_record_access, get_current_user
from auth.upload_signing import sign_path, strip_signature
from database import get_db
from models.all_account import ACCOUNT_TYPES, AllAccount
from models.all_account_mule_herder import AllAccountMuleHerder
from schemas.all_account import (
    AllAccountCreate,
    AllAccountListItem,
    AllAccountResponse,
    AllAccountUpdate,
    MuleHerderOut,
)


router = APIRouter(prefix="/api/v1/all-accounts", tags=["all-accounts"])
logger = logging.getLogger(__name__)


def _unlink_upload(rel_path: str | None) -> None:
    """Best-effort delete of a file under uploads/. Never raises — a
    missing or already-deleted file is fine; we just log and move on.
    Path is the DB value ("uploads/photos/xxx.jpg") — no leading slash."""
    if not rel_path:
        return
    # Defence against absolute paths or ../ traversal — must stay
    # within uploads/. If someone stored a hostile string in the DB
    # we don't want to unlink random filesystem paths.
    if not rel_path.startswith("uploads/") or ".." in rel_path.split("/"):
        logger.warning("refusing to unlink suspicious path: %s", rel_path)
        return
    p = Path(rel_path)
    try:
        if p.exists():
            p.unlink()
            logger.info("unlinked %s", rel_path)
    except OSError as e:
        # Disk error / permissions — log but let the DB delete proceed.
        # Orphan file will get swept by sweep_orphaned_uploads.py.
        logger.warning("failed to unlink %s: %s", rel_path, e)


# ── Helpers ──────────────────────────────────────────────────────


def _scope_to_ps(query, current: CurrentUser):
    """super_admin sees all PSes. Everyone else is pinned to their
    own (unit_id, ps_id) — the same rule Cases uses."""
    if current.role == "super_admin":
        return query
    if not current.unit_id or not current.ps_id:
        raise HTTPException(status_code=403, detail="Account is not assigned to a Police Station.")
    return query.where(
        AllAccount.unit_id == current.unit_id,
        AllAccount.ps_id == current.ps_id,
    )


def _require_ps(current: CurrentUser) -> tuple[int, int]:
    """For writes: caller MUST have both unit_id + ps_id on their JWT."""
    if not current.unit_id or not current.ps_id:
        raise HTTPException(
            status_code=403,
            detail="Cannot create records — your account is not assigned to a Police Station.",
        )
    return current.unit_id, current.ps_id


async def _next_serial_no(db: AsyncSession, unit_id: int, ps_id: int) -> int:
    """Next serial for this (unit_id, ps_id) — starts at 1."""
    current_max = (await db.execute(
        select(func.coalesce(func.max(AllAccount.serial_no), 0))
        .where(AllAccount.unit_id == unit_id, AllAccount.ps_id == ps_id)
    )).scalar_one()
    return int(current_max) + 1


def _validate_type_and_herders(body: AllAccountCreate) -> None:
    """Reject payloads that violate the type ↔ herders rule:
      - Victim / Non-Mule + herders → 422 (herders don't apply)
      - Mule + no herders → allowed (operator can save partial drafts)"""
    if body.account_type not in ACCOUNT_TYPES:
        raise HTTPException(status_code=422, detail=f"account_type must be one of {sorted(ACCOUNT_TYPES)}.")
    if body.account_type != "Mule" and body.mule_herders:
        raise HTTPException(
            status_code=422,
            detail="Mule herder rows are only allowed when account_type = 'Mule'.",
        )


def _to_response(row: AllAccount) -> AllAccountResponse:
    return AllAccountResponse(
        id=row.id,
        unit_id=row.unit_id,
        ps_id=row.ps_id,
        serial_no=row.serial_no,
        fir_no=row.fir_no,
        ncrp_ack_no=row.ncrp_ack_no,
        account_no=row.account_no,
        bank_name=row.bank_name,
        branch_name=row.branch_name,
        branch_district=row.branch_district,
        ifsc_code=row.ifsc_code,
        account_holder_name=row.account_holder_name,
        kyc_address=row.kyc_address,
        kyc_mobile=row.kyc_mobile,
        # Sign the paths on the way out so the front-end URL is
        # time-limited (1h). Middleware on /uploads/* rejects
        # anything unsigned/expired.
        id_photo_path=sign_path(row.id_photo_path),
        account_statement_path=sign_path(row.account_statement_path),
        account_type=row.account_type,
        mule_herders=[
            MuleHerderOut(id=h.id, name=h.name, address=h.address, mobile_no=h.mobile_no)
            for h in row.mule_herders
        ],
        submitted_by=row.submitted_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _load(db: AsyncSession, account_id: str) -> AllAccount:
    row = (await db.execute(
        select(AllAccount)
        .options(selectinload(AllAccount.mule_herders))
        .where(AllAccount.id == account_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    return row


# ── Create ───────────────────────────────────────────────────────


@router.post("", response_model=AllAccountResponse)
async def create_account(
    body: AllAccountCreate,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    unit_id, ps_id = _require_ps(current)
    _validate_type_and_herders(body)

    # One retry on unique-constraint race — cheap and correct.
    for attempt in (1, 2):
        serial = await _next_serial_no(db, unit_id, ps_id)
        row = AllAccount(
            unit_id=unit_id,
            ps_id=ps_id,
            serial_no=serial,
            fir_no=body.fir_no,
            ncrp_ack_no=body.ncrp_ack_no,
            account_no=body.account_no,
            bank_name=body.bank_name,
            branch_name=body.branch_name,
            branch_district=body.branch_district,
            ifsc_code=body.ifsc_code,
            account_holder_name=body.account_holder_name,
            kyc_address=body.kyc_address,
            kyc_mobile=body.kyc_mobile,
            # Client round-trips the signed value we handed it on read
            # — strip the ?exp=&sig= so the DB always holds the clean path.
            id_photo_path=strip_signature(body.id_photo_path),
            account_statement_path=strip_signature(body.account_statement_path),
            account_type=body.account_type,
            submitted_by=current.user_id,
        )
        db.add(row)
        try:
            await db.flush()
            break
        except IntegrityError:
            await db.rollback()
            if attempt == 2:
                raise HTTPException(
                    status_code=409,
                    detail="Serial number collision — please retry.",
                )
            # loop and try MAX+1 again

    for h in body.mule_herders:
        db.add(AllAccountMuleHerder(
            account_id=row.id,
            name=h.name,
            address=h.address,
            mobile_no=h.mobile_no,
        ))

    await db.commit()
    # Re-load with children so the response includes them.
    row = await _load(db, row.id)
    return _to_response(row)


# ── List / search ────────────────────────────────────────────────


@router.get("", response_model=List[AllAccountListItem])
async def list_accounts(
    q: str | None = Query(default=None, description="Search account_no / holder / FIR / ack no (partial, case-insensitive)"),
    account_type: str | None = Query(default=None, description="Filter by 'Victim' or 'Mule'"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """PS-scoped inbox. Optional free-text search across the fields
    the operator is most likely to remember (account, holder, FIR,
    NCRP ack)."""
    query = select(AllAccount).order_by(AllAccount.serial_no.desc())
    query = _scope_to_ps(query, current)
    if q:
        needle = f"%{q.strip()}%"
        query = query.where(or_(
            AllAccount.account_no.ilike(needle),
            AllAccount.account_holder_name.ilike(needle),
            AllAccount.fir_no.ilike(needle),
            AllAccount.ncrp_ack_no.ilike(needle),
        ))
    if account_type:
        if account_type not in ACCOUNT_TYPES:
            raise HTTPException(status_code=400, detail=f"account_type must be one of {sorted(ACCOUNT_TYPES)}.")
        query = query.where(AllAccount.account_type == account_type)
    query = query.limit(limit).offset(offset)

    rows = (await db.execute(query)).scalars().all()
    return [
        AllAccountListItem(
            id=r.id,
            serial_no=r.serial_no,
            account_no=r.account_no,
            bank_name=r.bank_name,
            account_holder_name=r.account_holder_name,
            account_type=r.account_type,
            fir_no=r.fir_no,
            ncrp_ack_no=r.ncrp_ack_no,
            created_at=r.created_at,
        )
        for r in rows
    ]


# ── Detail ───────────────────────────────────────────────────────


@router.get("/{account_id}", response_model=AllAccountResponse)
async def get_account(
    account_id: str,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    row = await _load(db, account_id)
    check_record_access(row, current)
    return _to_response(row)


# ── Update ───────────────────────────────────────────────────────


@router.put("/{account_id}", response_model=AllAccountResponse)
async def update_account(
    account_id: str,
    body: AllAccountUpdate,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """Full-replace edit. Scalar fields overwritten; mule_herders
    replaced wholesale (delete-all + re-insert). Serial No, unit_id,
    ps_id are immutable — a PS user cannot re-anchor an account to a
    different PS."""
    row = await _load(db, account_id)
    check_record_access(row, current)
    _validate_type_and_herders(body)

    row.fir_no = body.fir_no
    row.ncrp_ack_no = body.ncrp_ack_no
    row.account_no = body.account_no
    row.bank_name = body.bank_name
    row.branch_name = body.branch_name
    row.branch_district = body.branch_district
    row.ifsc_code = body.ifsc_code
    row.account_holder_name = body.account_holder_name
    row.kyc_address = body.kyc_address
    row.kyc_mobile = body.kyc_mobile
    # Same signature strip as on create — DB never sees ?exp=&sig=.
    row.id_photo_path = strip_signature(body.id_photo_path)
    row.account_statement_path = strip_signature(body.account_statement_path)
    row.account_type = body.account_type

    # Wholesale replace of the child collection.
    await db.execute(
        AllAccountMuleHerder.__table__.delete().where(
            AllAccountMuleHerder.account_id == row.id
        )
    )
    for h in body.mule_herders:
        db.add(AllAccountMuleHerder(
            account_id=row.id,
            name=h.name,
            address=h.address,
            mobile_no=h.mobile_no,
        ))

    await db.commit()
    row = await _load(db, row.id)
    return _to_response(row)


# ── Delete ───────────────────────────────────────────────────────


@router.delete("/{account_id}")
async def delete_account(
    account_id: str,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    row = await _load(db, account_id)
    check_record_access(row, current)
    # Snapshot the file paths BEFORE the DB delete so we can clean them
    # up after the row is gone. If the DB delete fails, we haven't
    # touched disk; if the file unlink fails, the sweep script picks it
    # up later — either way, no half-state visible to the client.
    photo = row.id_photo_path
    statement = row.account_statement_path
    await db.delete(row)
    await db.commit()
    _unlink_upload(photo)
    _unlink_upload(statement)
    return {"ok": True}
