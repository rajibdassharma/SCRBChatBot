"""One transaction line parsed out of an uploaded bank statement
(migration 019, written by analysis/parse_statements.py).

Derived data. The statement file on disk stays the record of truth;
these rows exist so the portal can ask questions across statements that
no one can answer by opening PDFs one at a time — where did the money
go, and did it go to the same place from several different accounts.

TRUST THE `ok` ROWS, NOT ALL ROWS
---------------------------------
upload_ledger.status records whether the source statement's own running
balance reconciled. Rows from a file marked `unverified` are stored and
readable, but their debit/credit columns may be transposed or their
amounts misread. Anything that presents these numbers as fact must join
through the ledger and say which it is showing.

counterparty_name is the weakest column here and must never be used as
a join key. Banks truncate it ("M.M.TRADIN"), operators mistype it, and
F1 already demonstrated the cost of treating a name as an identity.
Match on counterparty_account or counterparty_upi; show the name.
"""
import uuid

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String,
    Time, func,
)

from database import Base


class StatementTransaction(Base):
    __tablename__ = "statement_transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(
        String(36), ForeignKey("all_accounts.id", ondelete="CASCADE"), nullable=False
    )
    source_file = Column(String(500), nullable=False)
    row_no = Column(Integer, nullable=False, default=0)

    txn_date = Column(Date, nullable=True)
    #: Present on ~60% of statements only — F5 must degrade to day
    #: granularity rather than assume this is populated.
    txn_time = Column(Time, nullable=True)
    description = Column(String(500), nullable=True)
    ref_no = Column(String(100), nullable=True)

    debit = Column(Numeric(18, 2), nullable=True)
    credit = Column(Numeric(18, 2), nullable=True)
    balance = Column(Numeric(18, 2), nullable=True)

    counterparty_account = Column(String(50), nullable=True)
    counterparty_name = Column(String(200), nullable=True)
    counterparty_upi = Column(String(120), nullable=True)
    channel = Column(String(30), nullable=True)

    #: True when the SOURCE STATEMENT's balance chain reconciled.
    #: Denormalised from upload_ledger so the dashboard can filter on an
    #: indexed boolean instead of matching source_file against a list of
    #: every reconciled path — see migration 019 for the measurement.
    verified = Column(Boolean, nullable=False, default=False)
    #: PER-ROW balance-chain verdict (migration 022).
    #:  1 passed   previous - debit + credit = balance held
    #:  0 rejected the arithmetic did not hold
    #: -1 untested not enough context to check
    #:
    #: The column has existed in the database since migration 022 and was
    #: missing from this model, so ORM code could not filter on it and
    #: had to reach for the file-level `verified` flag instead -- which
    #: cannot tell a bad row from a bad file, and is the distinction 022
    #: was added to make. ONLY chain_ok = 1 may be summed.
    chain_ok = Column(Integer, nullable=False, default=-1, server_default="-1")

    #: Which reader produced the row (table-pdf / text-pdf / excel).
    #: Kept because a systematic error usually belongs to one reader.
    bank_template = Column(String(50), nullable=True)
    parser_version = Column(String(30), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
