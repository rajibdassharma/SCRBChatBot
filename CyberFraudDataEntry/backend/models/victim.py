import uuid

from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from database import Base


class Victim(Base):
    """Victim details captured at FIR time. 1:1 with Case via the
    UNIQUE (case_id) constraint added in migration 003. To support
    multiple victims later, drop the unique constraint — the model and
    schema flips trivially.
    """
    __tablename__ = "victims"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, unique=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    age = Column(Integer, nullable=True)
    gender = Column(String(30), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(200), nullable=True)
    address = Column(Text, nullable=True)
    amount_lost = Column(Numeric(18, 2), default=0, nullable=False)
    bank_account_no = Column(String(50), nullable=False)
    bank_name = Column(String(200), nullable=False)
    bank_branch_address = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    case = relationship("Case", back_populates="victim")
