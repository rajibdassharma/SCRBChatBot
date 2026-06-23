import uuid

from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, func
from database import Base


class NilDeclaration(Base):
    """A PS's explicit "no activity today" declaration. UNIQUE (unit_id,
    ps_id, nil_date) — at most one per PS per day. Re-declaring is a
    no-op rather than an error (handled at the route layer)."""
    __tablename__ = "daily_nil_declarations"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    unit_id = Column(Integer, nullable=False)
    ps_id = Column(Integer, nullable=False)
    declared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    nil_date = Column(Date, nullable=False)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
