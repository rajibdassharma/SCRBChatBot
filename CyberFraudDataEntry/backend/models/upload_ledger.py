"""One row per uploaded file that the analysis pipeline has processed
(migration 019).

Answers "what is new?" so a nightly run reads only what it has not seen,
and records failures so a corrupt or scanned file is a known quantity
rather than a silent gap. The scanned ones are the queue for a future
OCR phase.

`status` values written by analysis/parse_statements.py:

    ok          rows extracted AND the statement's balance chain
                reconciled — the only status whose money may be summed
    unverified  rows extracted, arithmetic did not agree
    scanned     image-only PDF, no text layer; needs OCR
    failed      text present but no transaction rows found
    deferred    very long statement, queued for the serial pass

The status is also denormalised onto every transaction row as
statement_transactions.verified — see migration 019 for why matching on
file paths at query time was too slow to keep.
"""
import uuid

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, func

from database import Base


class UploadLedger(Base):
    __tablename__ = "upload_ledger"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    file_path = Column(String(500), nullable=False, unique=True)
    #: 'statement' | 'photo'
    file_kind = Column(String(20), nullable=False)
    file_sha256 = Column(String(64), nullable=True)
    file_bytes = Column(BigInteger, nullable=True)
    #: NULL when no account references the file — an orphan upload. The
    #: row is still kept, so the orphan stays visible.
    account_id = Column(String(36), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    detail = Column(String(500), nullable=True)
    rows_extracted = Column(Integer, nullable=False, default=0)
    parser_version = Column(String(30), nullable=True)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
