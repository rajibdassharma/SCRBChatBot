"""Victim's additional bank accounts on a case.

The primary victim bank account still lives on the `victims` row
(bank_account_no, bank_name, bank_branch_address). This table holds
any *additional* accounts the victim used when the fraud spanned
multiple accounts of theirs. Captured on DSR -> New FIR only.

Same shape as accused_accounts minus the person's name (the victim
is already identified on the parent `victims` row).
"""
import uuid

from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, func
from sqlalchemy.orm import relationship

from database import Base


class VictimAccount(Base):
    __tablename__ = "victim_accounts"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(
        String(36),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    bank_name = Column(String(200), nullable=False)
    branch_name = Column(String(200), nullable=True)
    branch_address = Column(String(500), nullable=True)
    state = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    ifsc_code = Column(String(20), nullable=True)
    amount_transferred = Column(Numeric(18, 2), default=0)
    created_at = Column(DateTime, server_default=func.now())

    case = relationship("Case", back_populates="victim_accounts")
