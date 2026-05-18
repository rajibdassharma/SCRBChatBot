"""User Management routes — per-PS admin only.

Mounted at `/api/v1/users`. Lets a per-PS admin create, edit, deactivate,
re-activate, and reset passwords for the unit_users in their own police
station. Admin can NOT manage other admins, super_admins, or users in
other PSes — every read and write is filtered by `ps_id = admin.ps_id`.

Username convention (mirrors seed.py):
  `<ps_code>_user`, `<ps_code>_user2`, `<ps_code>_user3`, ...
The next suffix is auto-assigned based on the current count.

Generated passwords use the same `generate_strong_password` helper as
seed.py so strength and character classes match.
"""
from __future__ import annotations

import re
import secrets
import string
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from models.police_station import PoliceStation
from auth.security import hash_password
from api.deps import require_ps_admin, CurrentUser
from schemas.users import (
    UserCreate,
    UserUpdate,
    UserListItem,
    UserCreateResponse,
    PasswordResetResponse,
)


router = APIRouter(prefix="/api/v1/users", tags=["users"])


# ── Helpers ──────────────────────────────────────────────────────────


_PWD_LOWER = string.ascii_lowercase
_PWD_UPPER = string.ascii_uppercase
_PWD_DIGIT = string.digits
_PWD_SYM = "!@#$%^&*-_=+"
_PWD_ALL = _PWD_LOWER + _PWD_UPPER + _PWD_DIGIT + _PWD_SYM


def generate_strong_password(length: int = 16) -> str:
    """Cryptographically random password with at least one of each
    required character class. Mirrors seed.py exactly."""
    if length < 8:
        raise ValueError("length must be >= 8")
    chars = [
        secrets.choice(_PWD_LOWER),
        secrets.choice(_PWD_UPPER),
        secrets.choice(_PWD_DIGIT),
        secrets.choice(_PWD_SYM),
    ]
    chars += [secrets.choice(_PWD_ALL) for _ in range(length - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _to_code(name: str) -> str:
    """Mirrors seed.py — converts a station name to its username prefix."""
    code = name.lower().strip()
    code = re.sub(r"[^a-z0-9]+", "_", code)
    return code.strip("_")


async def _next_username(db: AsyncSession, ps_code: str) -> str:
    """Determine the next `<ps_code>_user{N}` suffix by scanning existing
    usernames. Skips `<ps_code>_admin`. The first user is `<ps_code>_user`
    (no suffix), then `_user2`, `_user3`, …"""
    pattern = f"{ps_code}_user%"
    rows = (await db.execute(
        select(User.username).where(User.username.like(pattern))
    )).scalars().all()

    suffixes_used: set[int] = set()
    base = f"{ps_code}_user"
    for u in rows:
        if u == base:
            suffixes_used.add(1)
        elif u.startswith(base):
            tail = u[len(base):]
            if tail.isdigit():
                suffixes_used.add(int(tail))

    n = 1
    while n in suffixes_used:
        n += 1
    return base if n == 1 else f"{base}{n}"


async def _load_target_user(db: AsyncSession, user_id: int, admin: CurrentUser) -> User:
    """Load `user_id` and confirm it belongs to the same PS as the admin
    and is a unit_user. Raises 404 / 403 as appropriate."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.ps_id != admin.ps_id:
        raise HTTPException(status_code=403, detail="User belongs to a different police station")
    if user.role != "unit_user":
        raise HTTPException(status_code=403, detail="Only unit_user accounts can be managed here")
    return user


# ── Routes ───────────────────────────────────────────────────────────


@router.get("", response_model=list[UserListItem])
async def list_users(
    admin: CurrentUser = Depends(require_ps_admin),
    db: AsyncSession = Depends(get_db),
):
    """List ALL users in this admin's PS — admin + unit_users alike — so
    the admin can see the full roster. Sorted by created_at."""
    rows = (await db.execute(
        select(User).where(User.ps_id == admin.ps_id).order_by(User.created_at.asc())
    )).scalars().all()
    return [UserListItem.model_validate(u) for u in rows]


@router.post("", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    admin: CurrentUser = Depends(require_ps_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new unit_user in this admin's PS.

    Server-generated:
      - username (next `<ps_code>_user{N}` suffix)
      - 16-char strong random password (returned ONCE in plaintext)
    Required from admin: full_name, email, mobile.
    """
    # Resolve PS code
    ps = (await db.execute(
        select(PoliceStation).where(PoliceStation.id == admin.ps_id)
    )).scalar_one_or_none()
    if not ps:
        raise HTTPException(status_code=500, detail="Admin's police station not found")
    ps_code = _to_code(ps.station_name)

    # Email uniqueness pre-check (DB enforces too, but we want a clean 409)
    existing = (await db.execute(
        select(User.id).where(User.email == body.email)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    # Determine next username + temp password
    username = await _next_username(db, ps_code)
    temp_pwd = generate_strong_password()

    new_user = User(
        username=username,
        hashed_password=hash_password(temp_pwd),
        full_name=body.full_name,
        email=body.email,
        mobile=body.mobile,
        role="unit_user",
        unit_id=admin.unit_id,
        ps_id=admin.ps_id,
        is_active=True,
        must_change_password=True,
        created_by=admin.user_id,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return UserCreateResponse(
        user=UserListItem.model_validate(new_user),
        generated_password=temp_pwd,
    )


@router.patch("/{user_id}", response_model=UserListItem)
async def update_user(
    user_id: int,
    body: UserUpdate,
    admin: CurrentUser = Depends(require_ps_admin),
    db: AsyncSession = Depends(get_db),
):
    """Edit full_name, email, or mobile for a unit_user in this PS."""
    user = await _load_target_user(db, user_id, admin)

    updates = body.model_dump(exclude_unset=True, exclude_none=True)

    # Email uniqueness check if changing
    new_email = updates.get("email")
    if new_email and new_email != user.email:
        clash = (await db.execute(
            select(User.id).where(User.email == new_email, User.id != user_id)
        )).scalar_one_or_none()
        if clash:
            raise HTTPException(status_code=409, detail="A user with this email already exists")

    for k, v in updates.items():
        setattr(user, k, v)

    await db.commit()
    await db.refresh(user)
    return UserListItem.model_validate(user)


@router.post("/{user_id}/deactivate", response_model=UserListItem)
async def deactivate_user(
    user_id: int,
    admin: CurrentUser = Depends(require_ps_admin),
    db: AsyncSession = Depends(get_db),
):
    """Soft-disable a unit_user. Sets is_active=0 + audit columns. The
    user can no longer log in (login route checks is_active)."""
    user = await _load_target_user(db, user_id, admin)
    if user.id == admin.user_id:
        raise HTTPException(status_code=400, detail="You cannot deactivate yourself")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="User is already deactivated")

    user.is_active = False
    user.deactivated_at = datetime.utcnow()
    user.deactivated_by = admin.user_id
    await db.commit()
    await db.refresh(user)
    return UserListItem.model_validate(user)


@router.post("/{user_id}/activate", response_model=UserListItem)
async def activate_user(
    user_id: int,
    admin: CurrentUser = Depends(require_ps_admin),
    db: AsyncSession = Depends(get_db),
):
    """Re-enable a previously deactivated unit_user."""
    user = await _load_target_user(db, user_id, admin)
    if user.is_active:
        raise HTTPException(status_code=400, detail="User is already active")

    user.is_active = True
    user.deactivated_at = None
    user.deactivated_by = None
    await db.commit()
    await db.refresh(user)
    return UserListItem.model_validate(user)


@router.post("/{user_id}/reset-password", response_model=PasswordResetResponse)
async def reset_password(
    user_id: int,
    admin: CurrentUser = Depends(require_ps_admin),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new temp password for the user and force them to change
    it on their next login. Returns the plaintext ONCE."""
    user = await _load_target_user(db, user_id, admin)

    new_pwd = generate_strong_password()
    user.hashed_password = hash_password(new_pwd)
    user.must_change_password = True
    await db.commit()

    return PasswordResetResponse(
        user_id=user.id,
        username=user.username,
        generated_password=new_pwd,
    )


@router.get("/_count", response_model=dict)
async def get_user_count(
    admin: CurrentUser = Depends(require_ps_admin),
    db: AsyncSession = Depends(get_db),
):
    """Quick stat for the admin's PS — total + active unit_user count.
    Used by the User Management page header."""
    total = (await db.execute(
        select(func.count(User.id)).where(User.ps_id == admin.ps_id, User.role == "unit_user")
    )).scalar() or 0
    active = (await db.execute(
        select(func.count(User.id)).where(
            User.ps_id == admin.ps_id, User.role == "unit_user", User.is_active == True  # noqa: E712
        )
    )).scalar() or 0
    return {"total": total, "active": active}
