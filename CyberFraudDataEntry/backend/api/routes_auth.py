from __future__ import annotations

import time
import logging
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from models.unit import Unit
from models.police_station import PoliceStation
from models.revoked_token import RevokedToken
from schemas.auth import LoginRequest, TokenResponse, UserResponse, ChangePasswordRequest
from auth.security import (
    verify_password,
    hash_password,
    create_access_token,
    validate_password_strength,
    PasswordTooWeak,
)
from api.deps import get_current_user, CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ── Rate limiting + per-username lockout (CWE-307) ────────────────────────
# Per-IP throttle: caps bursts from a single host
_ip_attempts: dict[str, list[float]] = defaultdict(list)
_IP_MAX_ATTEMPTS = 20        # allow multiple users from same NAT IP / CI pipelines
_IP_WINDOW_SECONDS = 60

# Per-username lockout: blocks the actual attack vector
_user_failures: dict[str, list[float]] = defaultdict(list)
_USER_MAX_FAILURES = 5        # 5 failed attempts
_USER_LOCKOUT_SECONDS = 900   # triggers 15 min lockout
_USER_WINDOW_SECONDS = 900    # failures counted in last 15 min


def _client_ip(request: Request) -> str:
    """Return the real client IP, honoring X-Forwarded-For (Nginx).
    Takes the first (leftmost) IP since XFF can be a comma-separated chain."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_ip_rate_limit(ip: str):
    now = time.time()
    _ip_attempts[ip] = [t for t in _ip_attempts[ip] if now - t < _IP_WINDOW_SECONDS]
    if len(_ip_attempts[ip]) >= _IP_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail=f"Too many login attempts from this IP. Try again in {_IP_WINDOW_SECONDS} seconds.",
        )
    _ip_attempts[ip].append(now)


def _check_user_lockout(username: str):
    now = time.time()
    _user_failures[username] = [t for t in _user_failures[username] if now - t < _USER_WINDOW_SECONDS]
    if len(_user_failures[username]) >= _USER_MAX_FAILURES:
        raise HTTPException(
            status_code=429,
            detail=f"Account locked due to too many failed login attempts. Try again in {_USER_LOCKOUT_SECONDS // 60} minutes.",
        )


def _record_user_failure(username: str):
    _user_failures[username].append(time.time())


def _clear_user_failures(username: str):
    _user_failures.pop(username, None)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip = _client_ip(request)
    _check_ip_rate_limit(ip)
    _check_user_lockout(body.username)

    # Look up user by username
    user = (await db.execute(
        select(User).where(User.username == body.username)
    )).scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        _record_user_failure(body.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    _clear_user_failures(body.username)

    # Get unit (district) name
    unit_name = None
    if user.unit_id:
        unit = (await db.execute(select(Unit).where(Unit.id == user.unit_id))).scalar_one_or_none()
        unit_name = unit.name if unit else None

    # Get police station name
    ps_name = None
    if user.ps_id:
        ps = (await db.execute(select(PoliceStation).where(PoliceStation.id == user.ps_id))).scalar_one_or_none()
        ps_name = ps.station_name if ps else None

    token = create_access_token({"sub": str(user.id), "role": user.role, "unit_id": user.unit_id})

    return TokenResponse(
        token=token,
        role=user.role,
        unit_id=user.unit_id,
        unit_name=unit_name,
        ps_id=user.ps_id,
        ps_name=ps_name,
        must_change_password=bool(user.must_change_password),
    )


@router.post("/logout")
async def logout(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Invalidate the current bearer token by adding its jti to the revocation list.
    Subsequent requests with the same token will be rejected by the auth dependency.

    Idempotent: the previous SELECT-then-INSERT pattern had a TOCTOU race
    when the same JWT logged out twice in parallel (double-clicked button,
    React strict-mode double-fire in dev, etc.). Both branches saw "not
    revoked yet" and both queued an INSERT; the second one crashed on the
    UNIQUE jti index. Now we just attempt the INSERT; if the UNIQUE
    constraint fires, the token is already revoked, which is the desired
    state — no-op the error and return success."""
    if current_user.jti:
        try:
            db.add(RevokedToken(jti=current_user.jti, user_id=current_user.user_id))
            await db.commit()
        except IntegrityError:
            await db.rollback()
    return {"ok": True, "message": "Logged out successfully"}


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(
        select(User).where(User.id == current_user.user_id)
    )).scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if body.new_password == body.current_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")

    try:
        validate_password_strength(body.new_password)
    except PasswordTooWeak as e:
        raise HTTPException(status_code=400, detail=str(e))

    user.hashed_password = hash_password(body.new_password)
    user.must_change_password = False
    await db.commit()

    # Force re-login: revoke the current token so the user must use the new password
    if current_user.jti:
        db.add(RevokedToken(jti=current_user.jti, user_id=current_user.user_id))
        await db.commit()

    return {"ok": True, "message": "Password changed successfully. Please log in again with the new password."}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser = Depends(get_current_user)):
    return UserResponse(
        id=current_user.user_id,
        username=current_user.username,
        full_name=None,
        role=current_user.role,
        unit_id=current_user.unit_id,
        unit_name=current_user.unit_name,
    )
