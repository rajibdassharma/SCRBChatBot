import uuid

from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, func
from database import Base
from sqlalchemy.orm import relationship

class LienAccount(Base):
    __tablename__ = "lien_accounts"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    case_type = Column(String(20), nullable=False)  # FIR, NCRP, Petition
    account_no = Column(String(50), nullable=False)
    amount_lien_marked = Column(Numeric(18, 2), default=0)
    layer = Column(Integer, default=1)
    total_amount_in_account = Column(Numeric(18, 2), default=0)
    bank_name = Column(String(200), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    case = relationship("Case", back_populates="lien_accounts")
