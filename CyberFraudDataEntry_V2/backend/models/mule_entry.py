from sqlalchemy import (
    Column, Integer, Text, Date, DateTime,
    ForeignKey, UniqueConstraint, func,
)

from database import Base


class MuleEntry(Base):
    __tablename__ = "mule_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    report_date = Column(Date, nullable=False)

    # Columns C-M from Mule Accounts sheet (all narrative text)
    accounts_most_liens = Column(Text, nullable=True)
    recruiters_for_lien_accounts = Column(Text, nullable=True)
    accounts_max_money_routed = Column(Text, nullable=True)
    accounts_max_transactions = Column(Text, nullable=True)
    recency_atm_transactions = Column(Text, nullable=True)
    cash_withdrawals_mule_wise = Column(Text, nullable=True)
    atm_geo_identification = Column(Text, nullable=True)
    atm_table_by_transactions = Column(Text, nullable=True)
    cheque_withdrawal_branches = Column(Text, nullable=True)
    money_left_system_stats = Column(Text, nullable=True)
    crypto_mule_accounts = Column(Text, nullable=True)

    # Metadata
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("unit_id", "report_date", name="uq_mule_unit_date"),
    )
