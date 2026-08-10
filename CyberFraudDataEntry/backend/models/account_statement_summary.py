"""Pre-aggregated statement totals per (account, channel) — migration 020.

A cache of statement_transactions, maintained by analysis/summary.py.
Nothing writes to it directly; the parser calls refresh() for the
accounts it touched, and `python -m analysis.summary` rebuilds it.

Read this instead of statement_transactions for any rollup. The fact
table is for drill-downs — individual transactions of one account —
where the row count is small because it is already filtered.

Verified and unverified totals sit side by side because the dashboard
needs both at once: coverage counts every parsed row, while rupee
totals count only statements whose balance chain reconciled.
"""
import uuid

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, func,
)

from database import Base


class AccountStatementSummary(Base):
    __tablename__ = "account_statement_summary"

    account_id = Column(
        String(36), ForeignKey("all_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    #: '' means the narration carried no recognisable channel marker.
    #: Not NULL, because this is half the primary key.
    channel = Column(String(30), primary_key=True, default="")

    txns = Column(Integer, nullable=False, default=0)
    debit = Column(Numeric(18, 2), nullable=False, default=0)
    credit = Column(Numeric(18, 2), nullable=False, default=0)

    #: Rows whose balance chain was tested AND agreed (chain_ok = 1).
    #: These three are the only figures any dashboard is allowed to
    #: present as money.
    verified_txns = Column(Integer, nullable=False, default=0)
    verified_debit = Column(Numeric(18, 2), nullable=False, default=0)
    verified_credit = Column(Numeric(18, 2), nullable=False, default=0)

    #: Rows with nothing to test against (chain_ok = -1) -- typically a
    #: statement export carrying no running-balance column. Migration
    #: 023; mapped here so the dashboards can read the COUNT.
    #:
    #: untested_debit/credit are stored but deliberately NOT surfaced by
    #: any endpoint. "Untested" is not a weaker "verified"; it is the
    #: absence of evidence, and a rupee total built from it would look
    #: exactly like a real one. The count is what an officer can act on
    #: -- it says how much of the picture is missing without inventing
    #: a number for it.
    untested_txns = Column(Integer, nullable=False, default=0)
    untested_debit = Column(Numeric(18, 2), nullable=False, default=0)
    untested_credit = Column(Numeric(18, 2), nullable=False, default=0)

    #: 0 if ANY statement behind this account/channel failed
    #: reconciliation. Aggregates upward with MIN().
    all_verified = Column(Boolean, nullable=False, default=False)

    first_txn = Column(Date, nullable=True)
    last_txn = Column(Date, nullable=True)
    parser_version = Column(String(30), nullable=True)
    updated_at = Column(DateTime, server_default=func.now())
