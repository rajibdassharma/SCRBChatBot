import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, Query, UploadFile, File, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from utils.friendly_errors import to_friendly
from models.unit import Unit
from api.deps import get_current_user
from api.routes_auth import router as auth_router
from api.routes_case import router as case_router
from api.routes_dashboard import router as dashboard_router
from api.routes_dsr import router as dsr_router
from api.routes_mule import router as mule_router
from api.routes_mule_report import router as mule_report_router
from api.routes_users import router as users_router
from api.routes_reports import router as reports_router
from api.routes_chat import router as chat_router
from api.routes_nil import router as nil_router
from api.routes_all_accounts import router as all_accounts_router

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads/photos")
ALLOWED_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_PHOTO_MIMETYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_PHOTO_SIZE = 5 * 1024 * 1024  # 5 MB

STATEMENT_DIR = Path("uploads/statements")
ALLOWED_STATEMENT_EXTENSIONS = {".pdf", ".xlsx", ".xls"}
# Some browsers/OSes send application/octet-stream for xlsx — accept
# it too since the extension check above narrows the risk anyway.
ALLOWED_STATEMENT_MIMETYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # xlsx
    "application/vnd.ms-excel",                                            # xls
    "application/octet-stream",
}
MAX_STATEMENT_SIZE = 5 * 1024 * 1024  # 5 MB — enough for a few months of statements


# ── Security Headers Middleware ──────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


# ── App Setup ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("CyberFraud Data Entry backend starting...")
    yield
    logger.info("Shutting down.")


docs_url = None if settings.DISABLE_DOCS else "/docs"
openapi_url = None if settings.DISABLE_DOCS else "/openapi.json"

app = FastAPI(
    title="CyberFraud Data Entry",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=docs_url,
    openapi_url=openapi_url,
)

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ── 422 validation-error handler ────────────────────────────────────
# Serves two audiences from one place:
#   * developers — the raw Pydantic error list (PII stripped) goes to
#     the systemd journal, so `journalctl -u cyberfraud-backend | grep
#     "422"` shows exact field + rule + ctx.
#   * end users — the response `detail` is a plain-English sentence
#     built by `utils.friendly_errors.to_friendly`, so operators see
#     e.g. "Victim Phone must be at least 10 characters long." in the
#     toast instead of "victim.phone: String should have at least 10
#     characters". Multiple failures are joined with "; ".

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    raw = exc.errors()
    safe_for_log = [{k: v for k, v in err.items() if k != "input"} for err in raw]
    client_ip = request.client.host if request.client else "?"
    logger.warning(
        "422 %s %s from %s → %s",
        request.method,
        request.url.path,
        client_ip,
        safe_for_log,
    )
    friendly = to_friendly(raw)
    return JSONResponse(status_code=422, content={"detail": "; ".join(friendly)})


app.include_router(auth_router)
app.include_router(case_router)
app.include_router(dashboard_router)
app.include_router(dsr_router)
app.include_router(mule_router)
app.include_router(mule_report_router)
app.include_router(users_router)
app.include_router(reports_router)
if settings.CHAT_ENABLED:
    app.include_router(chat_router)
app.include_router(nil_router)
app.include_router(all_accounts_router)


@app.get("/health")
async def health():
    return {"ok": True, "service": "CyberFraud Data Entry"}


@app.get("/api/v1/features")
async def features():
    """Public feature flags consumed by the frontend on app load.
    Lets the sidebar hide entry points for features that aren't
    provisioned in this environment (e.g. chat without a GPU box)."""
    return {"chat_enabled": settings.CHAT_ENABLED}


@app.get("/api/v1/units")
async def list_units(
    _: None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    units = (await db.execute(
        select(Unit).where(Unit.is_active == True).order_by(Unit.name)
    )).scalars().all()
    return [{"id": u.id, "name": u.name, "code": u.code} for u in units]


@app.get("/api/v1/units/public")
async def list_units_public(db: AsyncSession = Depends(get_db)):
    """Public endpoint for login page unit dropdown (no auth required)."""
    units = (await db.execute(
        select(Unit).where(Unit.is_active == True).order_by(Unit.name)
    )).scalars().all()
    return [{"id": u.id, "name": u.name} for u in units]


@app.get("/api/v1/police-stations/public")
async def list_police_stations_public(
    district: str = Query(None, max_length=100),
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint for police station dropdown (no auth required).

    Each row includes `has_super_admin` so the login form knows whether
    to expose the Super toggle for that PS — only the one PS where the
    Senior Officer is anchored will return True.
    """
    from models.police_station import PoliceStation
    from models.user import User
    q = select(PoliceStation).where(PoliceStation.is_active == True)
    if district:
        q = q.where(PoliceStation.district_name == district)
    q = q.order_by(PoliceStation.station_name)
    stations = (await db.execute(q)).scalars().all()

    # One small query lookup-set: PS ids that have at least one super_admin.
    super_ps_ids = set((await db.execute(
        select(User.ps_id).where(User.role == "super_admin", User.is_active == True)
    )).scalars().all())

    return [
        {
            "id": s.id,
            "district_name": s.district_name,
            "station_name": s.station_name,
            "has_super_admin": s.id in super_ps_ids,
        }
        for s in stations
    ]


@app.get("/api/v1/users/public")
async def list_users_for_ps_public(
    ps_id: int = Query(..., ge=1),
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint for login page user dropdown (no auth required).

    Returns the active usernames at the given PS so the login form can
    show a dropdown instead of asking the operator to remember their
    username. Exposing usernames publicly is acceptable for this
    deployment — KSWAN is an internal network and password remains
    the authentication factor.

    Ordering: super_admin → admin → unit_user, then username, so the
    most-likely-to-log-in accounts surface first.
    """
    from models.user import User
    _role_order = "(CASE role WHEN 'super_admin' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END)"
    users = (await db.execute(
        select(User.username, User.role)
        .where(User.ps_id == ps_id, User.is_active == True)
        .order_by(text(_role_order), User.username)
    )).all()
    return [{"username": u, "role": r} for u, r in users]


@app.get("/api/v1/districts/public")
async def list_districts_public(db: AsyncSession = Depends(get_db)):
    """Public endpoint for distinct district names (no auth required)."""
    from models.police_station import PoliceStation
    q = select(PoliceStation.district_name).distinct().order_by(PoliceStation.district_name)
    districts = (await db.execute(q)).scalars().all()
    return [{"name": d} for d in districts]


# -- Static file serving for uploads ------------------------------------
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# -- Photo upload endpoint -----------------------------------------------

@app.post("/api/v1/uploads/photo")
async def upload_photo(
    file: UploadFile = File(...),
    _: None = Depends(get_current_user),
):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Validate file extension
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in ALLOWED_PHOTO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_PHOTO_EXTENSIONS)}")

    # Validate MIME type
    if file.content_type and file.content_type not in ALLOWED_PHOTO_MIMETYPES:
        raise HTTPException(status_code=400, detail="Invalid file type")

    # Read and validate size
    content = await file.read()
    if len(content) > MAX_PHOTO_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size: {MAX_PHOTO_SIZE // (1024*1024)}MB")

    filename = f"{uuid.uuid4()}{ext}"
    filepath = UPLOAD_DIR / filename
    filepath.write_bytes(content)
    return {"ok": True, "photo_path": f"uploads/photos/{filename}"}


# -- Account statement upload endpoint (PDF + Excel) ---------------------

@app.post("/api/v1/uploads/statement")
async def upload_statement(
    file: UploadFile = File(...),
    _: None = Depends(get_current_user),
):
    """Upload a bank account statement (PDF or Excel) attached to an
    All Accounts row. Files stored under uploads/statements/ and served
    via the existing /uploads static mount. Called from the entry form's
    Account Details section."""
    STATEMENT_DIR.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in ALLOWED_STATEMENT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(sorted(ALLOWED_STATEMENT_EXTENSIONS))}",
        )

    if file.content_type and file.content_type not in ALLOWED_STATEMENT_MIMETYPES:
        raise HTTPException(status_code=400, detail="Invalid file type")

    content = await file.read()
    if len(content) > MAX_STATEMENT_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {MAX_STATEMENT_SIZE // (1024 * 1024)}MB",
        )

    filename = f"{uuid.uuid4()}{ext}"
    filepath = STATEMENT_DIR / filename
    filepath.write_bytes(content)
    # Keep the original filename so the UI can show it back to the user
    # (server-authoritative path is what actually gets stored on the row).
    return {
        "ok": True,
        "statement_path": f"uploads/statements/{filename}",
        "original_filename": file.filename,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("cyber_fraud:app", host="0.0.0.0", port=8000, reload=True)
