from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    ok: bool = True
    token: str
    role: str
    unit_id: int | None = None
    unit_name: str | None = None
    ps_id: int | None = None
    ps_name: str | None = None
    must_change_password: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str | None
    role: str
    unit_id: int | None
    unit_name: str | None
    ps_id: int | None = None
    ps_name: str | None = None

    class Config:
        from_attributes = True
