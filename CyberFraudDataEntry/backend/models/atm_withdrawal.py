from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from database import Base

class AtmWithdrawal(Base):
    __tablename__ = "atm_withdrawals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("mule_reports.id", ondelete="CASCADE"), nullable=False)
    account_no = Column(String(100), nullable=True)
    transaction_id = Column(String(100), nullable=True)
    withdrawal_datetime = Column(String(50), nullable=True)
    withdrawal_amount = Column(Numeric(18, 2), default=0)
    disputed_amount = Column(Numeric(18, 2), default=0)
    atm_id = Column(String(100), nullable=True)
    atm_location = Column(String(500), nullable=True)
    reference_no = Column(String(100), nullable=True)
    remarks = Column(Text, nullable=True)
    action_taken_by_bank = Column(String(200), nullable=True)
    date_of_action = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    report = relationship("MuleReport", back_populates="atm_withdrawals")
