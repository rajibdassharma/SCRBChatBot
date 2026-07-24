"""Accused bank accounts on a case.

One row per accused account that received a transfer from the victim
during the fraud. Cybercrime typically fans out across many mule /
accused accounts; this table captures the "where the money went"
side of the transfer. Independent of `lien_accounts` (which tracks
the freeze/lien lifecycle after the fact).

Captured on DSR -> New FIR only.
"""
import uuid

from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, func
from sqlalchemy.orm import relationship

from database import Base


class AccusedAccount(Base):
    __tablename__ = "accused_accounts"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(
        String(36),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_holder_name = Column(String(200), nullable=False)
    bank_name = Column(String(200), nullable=False)
    branch_name = Column(String(200), nullable=True)
    branch_address = Column(String(500), nullable=True)
    state = Column(String(100), nullable=True)
    # District dropdown is populated with the 36 Karnataka districts on
    # the client only when state == "Karnataka" -- for any other state
    # the field is disabled and left blank. Column stays nullable so
    # legacy / non-KA rows work.
    district = Column(String(100), nullable=True)
    ifsc_code = Column(String(20), nullable=True)
    amount_transferred = Column(Numeric(18, 2), default=0)
    created_at = Column(DateTime, server_default=func.now())

    case = relationship("Case", back_populates="accused_accounts")
