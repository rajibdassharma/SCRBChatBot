from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship
from database import Base

class MuleReport(Base):
    __tablename__ = "mule_reports"
    id = Column(Integer, primary_key=True, autoincrement=True)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    acknowledgement_no = Column(String(50), nullable=True, unique=True)
    fir_no = Column(String(50), nullable=True, unique=True)
    status = Column(String(20), nullable=False, default="draft")  # draft, submitted
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    money_transfers = relationship("MoneyTransfer", back_populates="report", cascade="all, delete-orphan")
    other_transactions = relationship("OtherTransaction", back_populates="report", cascade="all, delete-orphan")
    transactions_on_hold = relationship("TransactionOnHold", back_populates="report", cascade="all, delete-orphan")
    others_less_than_500 = relationship("OtherLessThan500", back_populates="report", cascade="all, delete-orphan")
    aeps_transactions = relationship("AepsTransaction", back_populates="report", cascade="all, delete-orphan")
    atm_withdrawals = relationship("AtmWithdrawal", back_populates="report", cascade="all, delete-orphan")
