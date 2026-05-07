import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, Query, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models.unit import Unit
from api.deps import get_current_user
from api.routes_auth import router as auth_router
from api.routes_case import router as case_router
from api.routes_dashboard import router as dashboard_router
from api.routes_dsr import router as dsr_router
from api.routes_mule import router as mule_router
from api.routes_mule_report import router as mule_report_router

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads/photos")
ALLOWED_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_PHOTO_MIMETYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_PHOTO_SIZE = 5 * 1024 * 1024  # 5 MB


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

app.include_router(auth_router)
app.include_router(case_router)
app.include_router(dashboard_router)
app.include_router(dsr_router)
app.include_router(mule_router)
app.include_router(mule_report_router)


@app.get("/health")
async def health():
    return {"ok": True, "service": "CyberFraud Data Entry"}


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
    """Public endpoint for police station dropdown (no auth required)."""
    from models.police_station import PoliceStation
    q = select(PoliceStation).where(PoliceStation.is_active == True)
    if district:
        q = q.where(PoliceStation.district_name == district)
    q = q.order_by(PoliceStation.station_name)
    stations = (await db.execute(q)).scalars().all()
    return [{"id": s.id, "district_name": s.district_name, "station_name": s.station_name} for s in stations]


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("cyber_fraud:app", host="0.0.0.0", port=8000, reload=True)
