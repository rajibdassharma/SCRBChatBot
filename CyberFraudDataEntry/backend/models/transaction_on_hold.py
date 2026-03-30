from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, func
from sqlalchemy.orm import relationship
from database import Base

class TransactionOnHold(Base):
    __tablename__ = "transactions_on_hold"
    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("mule_reports.id", ondelete="CASCADE"), nullable=False)
    account_no = Column(String(100), nullable=True)
    transaction_id = Column(String(100), nullable=True)
    hold_date = Column(String(50), nullable=True)
    hold_amount = Column(Numeric(18, 2), default=0)
    action_taken_by_bank = Column(String(200), nullable=True)
    date_of_action = Column(String(50), nullable=True)
    layer = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    report = relationship("MuleReport", back_populates="transactions_on_hold")
