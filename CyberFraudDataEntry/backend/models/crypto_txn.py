"""Transactions whose narration names a crypto exchange or asset.

DERIVED, not entered. Rebuilt by analysis/build_crypto.py from
statement_transactions; see migration 024 for why this is its own table
rather than a column on the 19M-row fact table.

`description` is stored deliberately. The detector behind this has
already produced two rounds of plausible-looking false positives -- a
substring match reported 168 "OKX" transactions that were men called
Ashok, and a word-boundary match reported 58 "Ethereum" rows that were
all the same bank header, "JOINT HOLDERS : Cust ID : 40943276 ETH".
Keeping the narration means an officer can see the evidence for any
flagged row instead of trusting the label.
"""
from sqlalchemy import (
    Column, String, Date, Numeric, SmallInteger, DateTime, ForeignKey, func,
)

from database import Base


class CryptoTxn(Base):
    __tablename__ = "crypto_txn"

    id = Column(String(36), primary_key=True)
    account_id = Column(
        String(36), ForeignKey("all_accounts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    #: statement_transactions.id. UNIQUE, so a rebuild upserts rather
    #: than duplicating when the scan is re-run.
    txn_id = Column(String(36), nullable=False, unique=True)

    #: Canonical label from analysis/parsers/crypto.py -- an exchange
    #: ("BINANCE", "WAZIRX") or an asset ("USDT"). Never free text.
    exchange = Column(String(20), nullable=False, index=True)

    txn_date = Column(Date, nullable=True)
    debit = Column(Numeric(18, 2), nullable=True)
    credit = Column(Numeric(18, 2), nullable=True)
    description = Column(String(500), nullable=True)

    #: Copied from the source row: 1 passed / 0 rejected / -1 untested.
    #: Carried so this tab applies the SAME rule as Money Trail -- only
    #: chain-passed rows may be presented as money.
    chain_ok = Column(SmallInteger, nullable=False, default=-1)

    parser_version = Column(String(30), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
