import uuid

from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, func
from database import Base
from sqlalchemy.orm import relationship

class Refund(Base):
    __tablename__ = "refunds"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    refunded = Column(String(5), nullable=False)  # yes, no
    victim_name = Column(String(200), nullable=True)
    amount = Column(Numeric(18, 2), default=0)
    crime_no_or_petition_no = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    case = relationship("Case", back_populates="refunds")
