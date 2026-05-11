from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, func

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=True)
    # super_admin: cross-PS dashboard visibility (Senior Officer role).
    # Per-record BOLA check still applies - super_admin can NOT view
    # individual /cases/{id} or /mule-reports/{id} outside their PS.
    role = Column(
        Enum("admin", "unit_user", "super_admin", name="user_role"),
        nullable=False,
        default="unit_user",
    )
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=True)
    ps_id = Column(Integer, ForeignKey("police_stations.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    must_change_password = Column(Boolean, default=True, nullable=False, server_default="1")
    created_at = Column(DateTime, server_default=func.now())
