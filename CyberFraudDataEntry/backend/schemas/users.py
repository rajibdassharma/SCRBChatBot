"""Pydantic schemas for the User Management feature (PS-admin only).

Used by `api/routes_users.py`. Matches the `User` ORM model in
`models/user.py`. Email and mobile are required for newly created users
even though the DB column allows NULL (legacy seeded users have no
contact info).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ── Helpers ──────────────────────────────────────────────────────────


def _strip_or_none(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = v.strip()
    return s or None


# ── Create ───────────────────────────────────────────────────────────


class UserCreate(BaseModel):
    """Body for POST /api/v1/users — admin enters contact details only;
    username + temp password are server-generated."""

    full_name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    mobile: str = Field(..., min_length=7, max_length=20)

    @field_validator("full_name", mode="before")
    @classmethod
    def _strip_full_name(cls, v):  # noqa: D401
        return v.strip() if isinstance(v, str) else v

    @field_validator("mobile", mode="before")
    @classmethod
    def _strip_and_normalize_mobile(cls, v):
        if not isinstance(v, str):
            return v
        # Keep digits, +, and spaces only — strip everything else
        cleaned = "".join(c for c in v if c.isdigit() or c in "+ ").strip()
        return cleaned


class UserUpdate(BaseModel):
    """Body for PATCH /api/v1/users/{id} — all fields optional."""

    full_name: Optional[str] = Field(None, min_length=2, max_length=150)
    email: Optional[EmailStr] = None
    mobile: Optional[str] = Field(None, min_length=7, max_length=20)

    @field_validator("full_name", mode="before")
    @classmethod
    def _strip_full_name(cls, v):
        return _strip_or_none(v) if isinstance(v, str) else v

    @field_validator("mobile", mode="before")
    @classmethod
    def _normalize_mobile(cls, v):
        if not isinstance(v, str):
            return v
        cleaned = "".join(c for c in v if c.isdigit() or c in "+ ").strip()
        return cleaned or None


# ── Response ─────────────────────────────────────────────────────────


class UserListItem(BaseModel):
    """Row in GET /api/v1/users — never includes password material."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: Optional[str]
    email: Optional[str]
    mobile: Optional[str]
    role: str
    is_active: bool
    must_change_password: bool
    created_at: Optional[datetime]
    deactivated_at: Optional[datetime]


class UserCreateResponse(BaseModel):
    """Returned ONCE on POST /api/v1/users — contains the generated
    plaintext temp password so the admin can hand it to the new user.
    The frontend must display + copy it; the server will not return it
    again."""

    user: UserListItem
    generated_password: str


class PasswordResetResponse(BaseModel):
    """Returned ONCE on POST /api/v1/users/{id}/reset-password."""

    user_id: int
    username: str
    generated_password: str
