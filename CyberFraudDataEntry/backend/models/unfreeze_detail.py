import uuid

from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, func
from database import Base
from sqlalchemy.orm import relationship

class UnfreezeDetail(Base):
    __tablename__ = "unfreeze_details"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    unfreeze_type = Column(String(20), nullable=False)  # letter, court_order
    crime_no = Column(String(50), nullable=True)
    bank_name = Column(String(200), nullable=True)
    account_no = Column(String(50), nullable=True)
    amount = Column(Numeric(18, 2), default=0)
    created_at = Column(DateTime, server_default=func.now())

    case = relationship("Case", back_populates="unfreeze_details")
