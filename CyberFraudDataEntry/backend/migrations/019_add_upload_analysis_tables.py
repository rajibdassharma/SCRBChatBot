"""
Migration 019 -- upload analysis tables.

Why:
  ~16k bank statements and ~10k ID photos have been uploaded, growing
  by roughly 1,000-1,500 statements a day. Today nothing is derived
  from them: the DB stores a path, the file sits on disk, and the
  contents are only ever read by a human opening them one at a time.

  These three tables hold facts DERIVED from those files. The files
  themselves stay on disk exactly as they are -- nothing here stores a
  document, and `all_accounts.id_photo_path` /
  `account_statement_path` are untouched.

Tables:
  upload_ledger
      One row per file processed. Lets the nightly job ask "what is
      new?" instead of re-reading every file. Also records failures,
      so a corrupt or scanned file is a known quantity rather than a
      silent gap -- the scanned ones are the queue for a future OCR
      phase.

  id_photo_hashes
      Two fingerprints per ID photo, and no extracted identity data --
      no name, no number, no date of birth.

      file_sha256 is the PRIMARY signal: byte-identical files mean the
      same file was attached to several accounts, which is unambiguous.

      dhash is a perceptual hash for near-duplicates (re-saved or
      re-compressed copies). It is stored at 24x24 = 576 bits, NOT the
      textbook 8x8. That matters: identity documents are near-identical
      by design -- same emblem, same colour bands, same photo position
      -- so at 8x8 every Aadhaar card collapses to the same fingerprint.
      Measured on this corpus, an 8x8 hash merged 28 DIFFERENT documents
      (28 distinct SHA-256s, 28 different holder names) into one
      "cluster". At 24x24 those separate into 28, while genuinely
      identical files stay welded together at every resolution.

  statement_transactions
      One row per transaction line parsed out of a statement.

      `verified` denormalises upload_ledger.status onto every row, and
      it is a performance fix with a measured cause. The dashboard used
      to ask "is this row from a reconciled file?" as
      `source_file IN (<one long path per ok file>)`. On 190k rows that
      IN-list cost 750 ms per use and the endpoint used it three times;
      at full-corpus scale the list would hold ~14,000 paths. The
      parser already knows the answer when it writes the row, so it
      writes it. Measured
      on a 396-statement sample: mean 407 rows per statement, so the
      current corpus yields roughly 6.6M rows (~2.5 GB with indexes).
      Ordinary for InnoDB; no partitioning needed at this size.

Design notes:
  - VARCHAR(36) PKs and CASCADE deletes on all_accounts(id), matching
    every other child table in this schema. Delete an account and its
    derived rows go with it -- the same hygiene sweep_orphaned_uploads
    already applies to the files.
  - parser_version on both derived tables. When a parser is fixed, it
    is what lets you re-run only the rows the old one got wrong
    instead of reprocessing the entire corpus.
  - file_sha256 on the ledger, so a file that is re-uploaded unchanged
    is recognised, and one that changed under the same path is not
    mistaken for it.
  - Amounts as DECIMAL(18,2), matching lien_accounts / refunds.
  - utf8mb4 / utf8mb4_unicode_ci to match all_accounts.id exactly
    (see migration 003's note on MySQL error 3780).

Idempotent -- safe to re-run. Each CREATE TABLE is guarded by an
INFORMATION_SCHEMA existence check.

Usage:
  python -m migrations.019_add_upload_analysis_tables
"""

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from database import engine
from config import settings


async def _table_exists(conn: AsyncConnection, table: str) -> bool:
    row = await conn.execute(
        text(
            "SELECT 1 FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl"
        ),
        {"db": settings.DB_NAME, "tbl": table},
    )
    return row.first() is not None


async def _column_exists(conn: AsyncConnection, table: str, col: str) -> bool:
    row = await conn.execute(
        text(
            "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl AND COLUMN_NAME = :col"
        ),
        {"db": settings.DB_NAME, "tbl": table, "col": col},
    )
    return row.first() is not None


async def run() -> None:
    print("Running migration 019 -- upload analysis tables")
    async with engine.begin() as conn:

        if await _table_exists(conn, "upload_ledger"):
            print("  = upload_ledger already exists, skipping CREATE")
        else:
            print("  + CREATE TABLE upload_ledger")
            await conn.execute(text("""
                CREATE TABLE upload_ledger (
                    id              VARCHAR(36)  NOT NULL,
                    file_path       VARCHAR(500) NOT NULL,
                    file_kind       VARCHAR(20)  NOT NULL,
                    file_sha256     CHAR(64)     NULL,
                    file_bytes      BIGINT       NULL,
                    account_id      VARCHAR(36)  NULL,
                    status          VARCHAR(20)  NOT NULL DEFAULT 'pending',
                    detail          VARCHAR(500) NULL,
                    rows_extracted  INT          NOT NULL DEFAULT 0,
                    parser_version  VARCHAR(30)  NULL,
                    processed_at    DATETIME     NULL,
                    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    UNIQUE KEY uq_upload_ledger_path (file_path),
                    KEY ix_upload_ledger_status (status),
                    KEY ix_upload_ledger_kind (file_kind),
                    KEY ix_upload_ledger_account (account_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))

        if await _table_exists(conn, "id_photo_hashes"):
            print("  = id_photo_hashes already exists, skipping CREATE")
        else:
            print("  + CREATE TABLE id_photo_hashes")
            await conn.execute(text("""
                CREATE TABLE id_photo_hashes (
                    id             VARCHAR(36) NOT NULL,
                    account_id     VARCHAR(36) NOT NULL,
                    file_path      VARCHAR(500) NOT NULL,
                    file_sha256    CHAR(64)     NOT NULL,
                    dhash          VARCHAR(160) NOT NULL,
                    width          INT         NULL,
                    height         INT         NULL,
                    parser_version VARCHAR(30) NULL,
                    created_at     DATETIME    DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    UNIQUE KEY uq_id_photo_hashes_path (file_path),
                    KEY ix_id_photo_hashes_account (account_id),
                    KEY ix_id_photo_hashes_sha (file_sha256),
                    KEY ix_id_photo_hashes_dhash (dhash(32)),
                    CONSTRAINT fk_id_photo_hashes_account
                        FOREIGN KEY (account_id) REFERENCES all_accounts(id)
                        ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))

        if await _table_exists(conn, "statement_transactions"):
            print("  = statement_transactions already exists, skipping CREATE")
            # The table predates the `verified` column, so add it in
            # place rather than making anyone drop 190k parsed rows.
            if not await _column_exists(conn, "statement_transactions", "verified"):
                print("  + ALTER statement_transactions ADD verified")
                await conn.execute(text(
                    "ALTER TABLE statement_transactions "
                    "ADD COLUMN verified TINYINT(1) NOT NULL DEFAULT 0, "
                    "ADD KEY ix_stmt_txn_verified (verified)"))
                # Backfill from the ledger, which already records the
                # reconciliation outcome per file.
                r = await conn.execute(text(
                    "UPDATE statement_transactions t "
                    "JOIN upload_ledger l ON l.file_path = t.source_file "
                    "SET t.verified = (l.status = 'ok')"))
                print(f"    backfilled {r.rowcount:,} rows from upload_ledger")
        else:
            print("  + CREATE TABLE statement_transactions")
            await conn.execute(text("""
                CREATE TABLE statement_transactions (
                    id               VARCHAR(36)  NOT NULL,
                    account_id       VARCHAR(36)  NOT NULL,
                    source_file      VARCHAR(500) NOT NULL,
                    row_no           INT          NOT NULL DEFAULT 0,
                    txn_date         DATE         NULL,
                    txn_time         TIME         NULL,
                    description      VARCHAR(500) NULL,
                    ref_no           VARCHAR(100) NULL,
                    debit            DECIMAL(18,2) NULL,
                    credit           DECIMAL(18,2) NULL,
                    balance          DECIMAL(18,2) NULL,
                    counterparty_account VARCHAR(50)  NULL,
                    counterparty_name    VARCHAR(200) NULL,
                    counterparty_upi     VARCHAR(120) NULL,
                    channel          VARCHAR(30)  NULL,
                    verified         TINYINT(1)   NOT NULL DEFAULT 0,
                    bank_template    VARCHAR(50)  NULL,
                    parser_version   VARCHAR(30)  NULL,
                    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    KEY ix_stmt_txn_account (account_id),
                    KEY ix_stmt_txn_date (txn_date),
                    KEY ix_stmt_txn_cp_account (counterparty_account),
                    KEY ix_stmt_txn_cp_upi (counterparty_upi),
                    KEY ix_stmt_txn_channel (channel),
                    KEY ix_stmt_txn_source (source_file),
                    KEY ix_stmt_txn_verified (verified),
                    CONSTRAINT fk_stmt_txn_account
                        FOREIGN KEY (account_id) REFERENCES all_accounts(id)
                        ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))

    print("Migration 019 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
