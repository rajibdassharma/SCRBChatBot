import uuid

from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from database import Base

class AepsTransaction(Base):
    __tablename__ = "aeps_transactions"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    report_id = Column(String(36), ForeignKey("mule_reports.id", ondelete="CASCADE"), nullable=False)
    account_no = Column(String(100), nullable=True)
    transaction_id = Column(String(100), nullable=True)
    withdrawal_date = Column(String(50), nullable=True)
    withdrawal_amount = Column(Numeric(18, 2), default=0)
    reference_no = Column(String(100), nullable=True)
    remarks = Column(Text, nullable=True)
    action_taken_by_bank = Column(String(200), nullable=True)
    date_of_action = Column(String(50), nullable=True)
    layer = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    report = relationship("MuleReport", back_populates="aeps_transactions")
