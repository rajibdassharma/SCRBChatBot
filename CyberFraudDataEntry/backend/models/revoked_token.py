from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, func

from database import Base


class RevokedToken(Base):
    """Denylist of JWT IDs (jti) that have been explicitly invalidated
    (on logout or admin action). Checked by the auth dependency on every
    protected request."""
    __tablename__ = "revoked_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    jti = Column(String(64), nullable=False, unique=True, index=True)
    revoked_at = Column(DateTime, nullable=False, server_default=func.now())
    user_id = Column(Integer, nullable=True, index=True)
