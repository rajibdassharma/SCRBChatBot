from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from models.unit import Unit
from auth.security import decode_token

bearer_scheme = HTTPBearer()


class CurrentUser:
    def __init__(self, user_id: int, username: str, role: str, unit_id: int | None, unit_name: str | None):
        self.user_id = user_id
        self.username = username
        self.role = role
        self.unit_id = unit_id
        self.unit_name = unit_name


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    payload = decode_token(creds.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

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
    )


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def require_unit_user(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role != "unit_user" or not current_user.unit_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unit user access required")
    return current_user
