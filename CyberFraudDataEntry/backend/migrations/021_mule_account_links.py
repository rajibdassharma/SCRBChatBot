"""Migration 021 -- direct mule-to-mule transfer links.

WHAT THIS STORES
  One row per (source mule account -> destination mule account) pair for
  which at least one parsed bank statement shows a transfer. Both ends
  are accounts already recorded in all_accounts with account_type
  'Mule'. Nothing inferred, nothing shared-destination: A's own
  statement names B's account number.

WHY A TABLE AND NOT A QUERY
  Finding these links means matching a free-text counterparty number
  against 13,970 mule account numbers, and the spelling varies -- a
  narration prints 0000120003057362 where all_accounts holds
  120003057362. Matching raw strings finds almost nothing; generating
  the zero-padded spellings finds 939 connected accounts. That means
  ~75,000 indexed lookups, which took minutes. It cannot sit behind a
  page load, so it is computed by analysis/build_links.py and stored.

WHAT MAKES A ROW INTERESTING
  `cross_fir`. Two mule accounts transferring to each other inside the
  SAME FIR is expected -- they were reported together, which is why
  both are in the file. The finding is a transfer between mules in
  DIFFERENT FIRs: two investigations that nobody has connected. On the
  first measured corpus, 667 of 1,307 links crossed FIRs.

A NOTE ON THE AMOUNTS
  total_debit is summed from statement_transactions and inherits
  whatever is wrong there. As of 2026-08-06 the per-row balance-chain
  check (chain_ok) is not yet wired in, so a link's rupee figure may
  include rows the arithmetic would reject. The LINK itself is sound --
  counterparty extraction is independent of the amount columns -- but
  the weight is not yet publishable. See migration 022.

Idempotent -- safe to re-run.

Usage:
  python -m migrations.021_mule_account_links
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


async def run() -> None:
    print("Running migration 021 -- mule account links")
    async with engine.begin() as conn:
        if await _table_exists(conn, "mule_account_link"):
            print("  = mule_account_link already exists, skipping")
        else:
            print("  + CREATE TABLE mule_account_link")
            await conn.execute(text("""
                CREATE TABLE mule_account_link (
                    src_account_id VARCHAR(36) NOT NULL,
                    dst_account_id VARCHAR(36) NOT NULL,
                    txns           INT          NOT NULL DEFAULT 0,
                    total_debit    DECIMAL(18,2) NOT NULL DEFAULT 0,
                    -- Denormalised so the ranking can filter and index
                    -- on it. Recomputed on every rebuild, so it cannot
                    -- drift from the FIRs it describes.
                    cross_fir      TINYINT(1)   NOT NULL DEFAULT 0,
                    src_fir_no     VARCHAR(20)  NULL,
                    dst_fir_no     VARCHAR(20)  NULL,
                    first_txn      DATE         NULL,
                    last_txn       DATE         NULL,
                    parser_version VARCHAR(30)  NULL,
                    updated_at     DATETIME     DEFAULT CURRENT_TIMESTAMP
                                                ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (src_account_id, dst_account_id),
                    KEY ix_mal_src (src_account_id),
                    KEY ix_mal_dst (dst_account_id),
                    KEY ix_mal_cross (cross_fir),
                    CONSTRAINT fk_mal_src FOREIGN KEY (src_account_id)
                        REFERENCES all_accounts(id) ON DELETE CASCADE,
                    CONSTRAINT fk_mal_dst FOREIGN KEY (dst_account_id)
                        REFERENCES all_accounts(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))
    print("Migration 021 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
