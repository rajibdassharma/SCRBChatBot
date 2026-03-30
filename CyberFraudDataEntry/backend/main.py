from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Query, UploadFile, File
import os
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models.unit import Unit
from api.deps import get_current_user
from api.routes_auth import router as auth_router
from api.routes_case import router as case_router
from api.routes_dashboard import router as dashboard_router
from api.routes_mule_report import router as mule_report_router


UPLOAD_DIR = Path("uploads/photos")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("CyberFraud Data Entry backend starting...")
    yield
    print("Shutting down.")


app = FastAPI(title="CyberFraud Data Entry", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(case_router)
app.include_router(dashboard_router)
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
    district: str = Query(None),
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
    import uuid
    ext = Path(file.filename).suffix if file.filename else ".jpg"
    filename = f"{uuid.uuid4()}{ext}"
    filepath = UPLOAD_DIR / filename
    content = await file.read()
    filepath.write_bytes(content)
    return {"ok": True, "photo_path": f"uploads/photos/{filename}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
