"""Migration 024 — crypto_txn.

Transactions whose narration names a crypto exchange or asset, found by
scanning statement_transactions. Populated by analysis/build_crypto.py,
which is re-runnable; nothing here is entered by hand.

WHY A DERIVED TABLE RATHER THAN A COLUMN ON statement_transactions
-----------------------------------------------------------------
A `crypto VARCHAR(20)` column was the obvious design and is worse here:

  - ALTER on a 19M-row table, then either a full re-parse or an
    hour-long stamping pass to populate it for rows already stored.
  - It couples the finding to the parser, so improving the detector
    means re-reading PDFs rather than re-running a scan.
  - The result is sparse. Roughly 850 rows in 19M carry a value; a
    column spends 19M cells to store 850 facts.

A separate table costs one indexed scan (~10 min) to rebuild from
scratch, can be re-run whenever the detector improves, and is small
enough to ship to production inside the existing analysis export --
which matters, because production never runs the parser.

Same shape and lifecycle as mule_account_link (migration 021).
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text                                # noqa: E402
from database import engine                                # noqa: E402


async def _table_exists(conn, name: str) -> bool:
    return bool((await conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = :n"
    ), {"n": name})).scalar())


async def run() -> None:
    print("Running migration 024 -- crypto_txn")
    async with engine.begin() as conn:
        if await _table_exists(conn, "crypto_txn"):
            print("  = crypto_txn already exists, skipping")
        else:
            # CHARSET + COLLATE declared explicitly: account_id is an FK
            # onto all_accounts.id (VARCHAR(36) utf8mb4_unicode_ci) and
            # MySQL 3780 fires on any mismatch -- see docs/database.md
            # for the 2026-06-20 incident this rule came from.
            await conn.execute(text("""
                CREATE TABLE crypto_txn (
                    id            VARCHAR(36)  NOT NULL,
                    account_id    VARCHAR(36)  NOT NULL,
                    txn_id        VARCHAR(36)  NOT NULL,
                    exchange      VARCHAR(20)  NOT NULL,
                    txn_date      DATE         NULL,
                    debit         DECIMAL(18,2) NULL,
                    credit        DECIMAL(18,2) NULL,
                    -- The narration that triggered the match. Stored so
                    -- an officer can see WHY a row was flagged without
                    -- going back to the fact table. This detector has
                    -- already produced two rounds of convincing false
                    -- positives; "show me the evidence" is the feature.
                    description   VARCHAR(500) NULL,
                    chain_ok      TINYINT      NOT NULL DEFAULT -1,
                    parser_version VARCHAR(30) NULL,
                    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    UNIQUE KEY uq_crypto_txn (txn_id),
                    KEY ix_crypto_txn_account (account_id),
                    KEY ix_crypto_txn_exchange (exchange),
                    CONSTRAINT fk_crypto_txn_account
                        FOREIGN KEY (account_id) REFERENCES all_accounts(id)
                        ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                  COLLATE=utf8mb4_unicode_ci
            """))
            print("  + crypto_txn created")
    await engine.dispose()
    print("Migration 024 complete.")


if __name__ == "__main__":
    asyncio.run(run())
