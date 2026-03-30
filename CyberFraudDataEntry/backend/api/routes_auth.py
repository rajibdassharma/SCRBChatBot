from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from models.unit import Unit
from models.police_station import PoliceStation
from schemas.auth import LoginRequest, TokenResponse, UserResponse
from auth.security import verify_password, create_access_token
from api.deps import get_current_user, CurrentUser

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    # Look up user by username
    user = (await db.execute(
        select(User).where(User.username == body.username)
    )).scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

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
    )


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
