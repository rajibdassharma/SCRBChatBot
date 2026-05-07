import uuid

from sqlalchemy import Column, Integer, String, DateTime, Text, Numeric, ForeignKey, func
from database import Base
from sqlalchemy.orm import relationship

class Petition(Base):
    __tablename__ = "petitions"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=True)
    petition_no = Column(String(50), nullable=True)
    fir_registered = Column(String(20), nullable=False)  # yes, no, transferred
    why_not = Column(Text, nullable=True)
    nature = Column(String(100), nullable=True)
    petition_type = Column(String(30), nullable=False)  # amount_lost, fraud_case
    amount = Column(Numeric(18, 2), default=0)
    created_at = Column(DateTime, server_default=func.now())

    case = relationship("Case", back_populates="petitions")
