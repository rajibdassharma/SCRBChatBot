from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, func

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=True)
    role = Column(Enum("admin", "unit_user", name="user_role"), nullable=False, default="unit_user")
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=True)
    ps_id = Column(Integer, ForeignKey("police_stations.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
