"""
Authentication module for ISD Document Intelligence V4.

Provides:
  - init_users_table()    — creates the users table in MSSQL (called at import)
  - router                — FastAPI APIRouter with /auth/* endpoints
  - get_current_user()    — FastAPI dependency for protected routes
  - CurrentUser           — typed user object injected into protected endpoints
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from mssql_db import get_conn, _fetchone, _fetchall
from config import JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRE_HOURS


# ---------------------------------------------------------------------------
# Password hashing (bcrypt)
# ---------------------------------------------------------------------------

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def _verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=True)


def _create_token(user_id: int, username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------

def init_users_table() -> None:
    """Create the users table in MSSQL if it does not already exist."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            IF NOT EXISTS (
                SELECT 1 FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_NAME = 'users'
            )
            CREATE TABLE users (
                id            INT IDENTITY(1,1) PRIMARY KEY,
                username      NVARCHAR(100)  NOT NULL UNIQUE,
                password_hash NVARCHAR(255)  NOT NULL,
                full_name     NVARCHAR(200),
                role          NVARCHAR(50)   NOT NULL DEFAULT 'user',
                is_active     BIT            NOT NULL DEFAULT 1,
                created_at    DATETIME       NOT NULL DEFAULT GETDATE()
            )
        """)
        conn.commit()
        print("[Auth] users table ready")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# FastAPI dependency: get_current_user
# ---------------------------------------------------------------------------

class CurrentUser:
    """Lightweight object carrying authenticated user info."""

    def __init__(self, user_id: int, username: str, role: str):
        self.user_id = user_id
        self.username = username
        self.role = role

    def __repr__(self):
        return f"<CurrentUser id={self.user_id} username={self.username} role={self.role}>"


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> CurrentUser:
    """
    FastAPI dependency.  Validates the Bearer JWT and returns a CurrentUser.
    Raises HTTP 401 if the token is missing, invalid, or expired.
    """
    _401 = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token. Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            credentials.credentials, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM]
        )
        user_id = int(payload["sub"])
        username: str = payload["username"]
        role: str = payload.get("role", "user")
        if not user_id or not username:
            raise _401
    except (JWTError, ValueError, KeyError, TypeError):
        raise _401

    return CurrentUser(user_id=user_id, username=username, role=role)


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(payload: RegisterRequest):
    """Register a new user account. Returns a JWT token on success."""
    username = payload.username.strip().lower()

    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters.")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    password_hash = _hash_password(payload.password)
    conn = get_conn()
    try:
        cur = conn.cursor()

        cur.execute("SELECT id FROM users WHERE username = ?", username)
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Username already exists.")

        cur.execute(
            "INSERT INTO users (username, password_hash, full_name) VALUES (?, ?, ?)",
            username,
            password_hash,
            payload.full_name or payload.username,
        )
        conn.commit()

        cur.execute(
            "SELECT id, username, full_name, role FROM users WHERE username = ?",
            username,
        )
        row = _fetchone(cur)
        token = _create_token(row["id"], row["username"], row["role"])

        return {
            "ok": True,
            "message": "Account created successfully.",
            "token": token,
            "user": {
                "id": row["id"],
                "username": row["username"],
                "full_name": row["full_name"],
                "role": row["role"],
            },
        }
    finally:
        conn.close()


@router.post("/login")
def login(payload: LoginRequest):
    """Login with username + password. Returns a JWT token."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, password_hash, full_name, role, is_active "
            "FROM users WHERE username = ?",
            payload.username.strip().lower(),
        )
        row = _fetchone(cur)

        if not row or not _verify_password(payload.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password.")
        if not row["is_active"]:
            raise HTTPException(
                status_code=403, detail="Account is disabled. Contact administrator."
            )

        token = _create_token(row["id"], row["username"], row["role"])
        return {
            "ok": True,
            "token": token,
            "user": {
                "id": row["id"],
                "username": row["username"],
                "full_name": row["full_name"],
                "role": row["role"],
            },
        }
    finally:
        conn.close()


@router.get("/me")
def me(current_user: CurrentUser = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, full_name, role, created_at FROM users WHERE id = ?",
            current_user.user_id,
        )
        row = _fetchone(cur)
        if not row:
            raise HTTPException(status_code=404, detail="User not found.")
        row["created_at"] = str(row["created_at"])
        return {"ok": True, "user": row}
    finally:
        conn.close()


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Change the current user's password."""
    if len(payload.new_password) < 6:
        raise HTTPException(
            status_code=400, detail="New password must be at least 6 characters."
        )
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE id = ?", current_user.user_id)
        row = _fetchone(cur)
        if not row or not _verify_password(payload.current_password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Current password is incorrect.")

        cur.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            _hash_password(payload.new_password),
            current_user.user_id,
        )
        conn.commit()
        return {"ok": True, "message": "Password changed successfully."}
    finally:
        conn.close()


@router.get("/users")
def list_users(current_user: CurrentUser = Depends(get_current_user)):
    """Admin only: list all registered users."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, full_name, role, is_active, created_at "
            "FROM users ORDER BY created_at DESC"
        )
        rows = _fetchall(cur)
        for r in rows:
            r["created_at"] = str(r["created_at"])
        return {"ok": True, "users": rows, "count": len(rows)}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Module-level bootstrap
# ---------------------------------------------------------------------------
init_users_table()
