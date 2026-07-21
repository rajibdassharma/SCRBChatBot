"""CRUD routes for the Portals DSR feature (2026-07-21).

Per-PS scoping identical to All Accounts + Cases (VAPT 7.7 + 7.8):
every read/write runs `check_record_access` and lists are filtered
to the caller's own (unit_id, ps_id). super_admin sees all.

Multiple entries per (unit_id, ps_id, report_date) are permitted by
design — shift-based data entry. The dashboard SUM-aggregates rows
so morning + afternoon batches roll up to a single per-day figure.
"""
from __future__ import annotations

from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import CurrentUser, check_record_access, get_current_user
from database import get_db
from models.portals_dsr_entry import PORTAL_STATUSES, PortalsDsrEntry
from schemas.portals_dsr import (
    PortalsDsrCreate,
    PortalsDsrListItem,
    PortalsDsrResponse,
    PortalsDsrUpdate,
)


router = APIRouter(prefix="/api/v1/portals-dsr", tags=["portals-dsr"])


# ── Helpers ──────────────────────────────────────────────────────


# Names of every metric column on the model. Used to sum on the fly
# for the list-item "total" field and to copy fields from the schema
# to the ORM row without listing each name twice.
_METRIC_FIELDS: tuple[str, ...] = (
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


def _scope_to_ps(query, current: CurrentUser):
    """super_admin sees all PSes. Everyone else is pinned to their
    own (unit_id, ps_id) — same rule as All Accounts."""
    if current.role == "super_admin":
        return query
    if not current.unit_id or not current.ps_id:
        raise HTTPException(status_code=403, detail="Account is not assigned to a Police Station.")
    return query.where(
        PortalsDsrEntry.unit_id == current.unit_id,
        PortalsDsrEntry.ps_id == current.ps_id,
    )


def _require_ps(current: CurrentUser) -> tuple[int, int]:
    if not current.unit_id or not current.ps_id:
        raise HTTPException(
            status_code=403,
            detail="Cannot create records — your account is not assigned to a Police Station.",
        )
    return current.unit_id, current.ps_id


def _validate_status(status: str) -> None:
    if status not in PORTAL_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(PORTAL_STATUSES)}.")


def _to_response(row: PortalsDsrEntry) -> PortalsDsrResponse:
    payload = {
        "id": row.id,
        "unit_id": row.unit_id,
        "ps_id": row.ps_id,
        "report_date": row.report_date,
        "status": row.status,
        "submitted_by": row.submitted_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    for f in _METRIC_FIELDS:
        payload[f] = getattr(row, f)
    return PortalsDsrResponse(**payload)


async def _load(db: AsyncSession, entry_id: str) -> PortalsDsrEntry:
    row = (await db.execute(
        select(PortalsDsrEntry).where(PortalsDsrEntry.id == entry_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Portals DSR entry not found.")
    return row


# ── Create ───────────────────────────────────────────────────────


@router.post("", response_model=PortalsDsrResponse)
async def create_entry(
    body: PortalsDsrCreate,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    unit_id, ps_id = _require_ps(current)
    _validate_status(body.status)

    row = PortalsDsrEntry(
        unit_id=unit_id,
        ps_id=ps_id,
        report_date=body.report_date,
        status=body.status,
        submitted_by=current.user_id,
    )
    for f in _METRIC_FIELDS:
        setattr(row, f, getattr(body, f))
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_response(row)


# ── List / search ────────────────────────────────────────────────


@router.get("", response_model=List[PortalsDsrListItem])
async def list_entries(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    status: str | None = Query(default=None, description="Filter by 'draft' or 'submitted'"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """PS-scoped list, newest first. Optional date window + status filter."""
    query = select(PortalsDsrEntry).order_by(PortalsDsrEntry.created_at.desc())
    query = _scope_to_ps(query, current)
    if from_date:
        query = query.where(PortalsDsrEntry.report_date >= from_date)
    if to_date:
        query = query.where(PortalsDsrEntry.report_date <= to_date)
    if status:
        _validate_status(status)
        query = query.where(PortalsDsrEntry.status == status)
    query = query.limit(limit).offset(offset)

    rows = (await db.execute(query)).scalars().all()
    return [
        PortalsDsrListItem(
            id=r.id,
            report_date=r.report_date,
            status=r.status,
            total=sum(getattr(r, f) or 0 for f in _METRIC_FIELDS),
            submitted_by=r.submitted_by,
            created_at=r.created_at,
        )
        for r in rows
    ]


# ── Detail ───────────────────────────────────────────────────────


@router.get("/{entry_id}", response_model=PortalsDsrResponse)
async def get_entry(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    row = await _load(db, entry_id)
    check_record_access(row, current)
    return _to_response(row)


# ── Update ───────────────────────────────────────────────────────


@router.put("/{entry_id}", response_model=PortalsDsrResponse)
async def update_entry(
    entry_id: str,
    body: PortalsDsrUpdate,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """Full-replace edit. unit_id + ps_id are immutable — a PS user
    cannot re-anchor an entry to a different PS."""
    row = await _load(db, entry_id)
    check_record_access(row, current)
    _validate_status(body.status)

    row.report_date = body.report_date
    row.status = body.status
    for f in _METRIC_FIELDS:
        setattr(row, f, getattr(body, f))

    await db.commit()
    await db.refresh(row)
    return _to_response(row)


# ── Delete ───────────────────────────────────────────────────────


@router.delete("/{entry_id}")
async def delete_entry(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    row = await _load(db, entry_id)
    check_record_access(row, current)
    await db.delete(row)
    await db.commit()
    return {"ok": True}
