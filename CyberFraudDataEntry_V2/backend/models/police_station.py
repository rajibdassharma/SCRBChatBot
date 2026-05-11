from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from database import Base


class PoliceStation(Base):
    __tablename__ = "police_stations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    district_name = Column(String(100), nullable=False)
    station_name = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
