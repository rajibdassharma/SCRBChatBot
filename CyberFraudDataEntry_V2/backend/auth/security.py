from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from passlib.context import CryptContext

from config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    """Issue a session-unique JWT with iat + jti claims so tokens differ every login."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    to_encode["iat"] = int(now.timestamp())
    to_encode["jti"] = str(uuid.uuid4())
    to_encode["exp"] = now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    """Verifies signature AND expiry. Returns None on any failure."""
    try:
        return jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": True},
        )
    except JWTError:
        return None


# ── Password strength (CWE-521) ─────────────────────────────────────────
_PASSWORD_MIN_LENGTH = 12


class PasswordTooWeak(ValueError):
    pass


def validate_password_strength(password: str) -> None:
    """Raises PasswordTooWeak with a clear reason if password is too weak.
    Called by the change-password route."""
    if len(password) < _PASSWORD_MIN_LENGTH:
        raise PasswordTooWeak(
            f"Password must be at least {_PASSWORD_MIN_LENGTH} characters long."
        )
    if not re.search(r"[A-Z]", password):
        raise PasswordTooWeak("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise PasswordTooWeak("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        raise PasswordTooWeak("Password must contain at least one digit.")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise PasswordTooWeak(
            "Password must contain at least one special character (e.g. !@#$%)."
        )
    weak = {"admin123", "police123", "password", "password123", "qwerty", "letmein"}
    if password.lower() in weak:
        raise PasswordTooWeak("Password is too common. Choose a more unique password.")
