from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, func

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=True)
    # Contact columns — added by migration 001. NULLABLE in the DB so the
    # 88 already-seeded users (which have no contact info) keep working;
    # the POST /users API enforces required for newly created users.
    email = Column(String(200), nullable=True, unique=True)
    mobile = Column(String(20), nullable=True)
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
    # Audit trail — who created this user (admin's user_id) and, if
    # deactivated, when and by whom. Added by migration 001.
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    deactivated_at = Column(DateTime, nullable=True)
    deactivated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
