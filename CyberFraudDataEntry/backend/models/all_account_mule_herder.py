"""AllAccountMuleHerder — one row per mule herder attached to a
Mule-typed AllAccount. Repeating child (one account can have many).

Only populated for accounts where `account_type = 'Mule'`. Cascaded
delete via the parent's `cascade='all, delete-orphan'`.
"""
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import relationship

from database import Base


class AllAccountMuleHerder(Base):
    __tablename__ = "all_account_mule_herders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(
        String(36),
        ForeignKey("all_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(200), nullable=False)
    address = Column(Text, nullable=True)
    mobile_no = Column(String(20), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    account = relationship("AllAccount", back_populates="mule_herders")
