from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from models.unit import Unit
from models.revoked_token import RevokedToken
from auth.security import decode_token

bearer_scheme = HTTPBearer()


class CurrentUser:
    def __init__(self, user_id: int, username: str, role: str, unit_id: int | None, unit_name: str | None, jti: str | None = None):
        self.user_id = user_id
        self.username = username
        self.role = role
        self.unit_id = unit_id
        self.unit_name = unit_name
        self.jti = jti


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    payload = decode_token(creds.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = payload.get("sub")
    jti = payload.get("jti")
    if not user_id or not jti:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    # Reject tokens that were revoked (logout / admin revocation)
    revoked = (await db.execute(
        select(RevokedToken).where(RevokedToken.jti == jti)
    )).scalar_one_or_none()
    if revoked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")

    user = (await db.execute(select(User).where(User.id == int(user_id)))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    unit_name = None
    if user.unit_id:
        unit = (await db.execute(select(Unit).where(Unit.id == user.unit_id))).scalar_one_or_none()
        unit_name = unit.name if unit else None

    return CurrentUser(
        user_id=user.id,
        username=user.username,
        role=user.role,
        unit_id=user.unit_id,
        unit_name=unit_name,
        jti=jti,
    )


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    # super_admin (Senior Officer) is also allowed through admin gates.
    if current_user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def require_unit_user(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role != "unit_user" or not current_user.unit_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unit user access required")
    return current_user


def check_record_access(record, current_user: CurrentUser) -> None:
    """Enforce per-record authorization (VAPT 7.7 + 7.8).

    Model:
      - admin (PS admin): sees all records in their own unit_id; NEVER cross-PS
      - unit_user        : sees only records they submitted, in their own unit_id

    There is no global admin role - every account is scoped to a single PS.
    Use on every detail/edit endpoint that takes a record id from the URL.
    Caller is responsible for handling 404 (record not found) before calling.
    """
    # Cross-PS access is denied for everyone, including admins.
    if current_user.unit_id is None or getattr(record, "unit_id", None) != current_user.unit_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    # Within the PS, unit_users can only touch records they personally
    # submitted. admin and super_admin see all records in their PS.
    if (
        current_user.role not in ("admin", "super_admin")
        and getattr(record, "submitted_by", None) != current_user.user_id
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
