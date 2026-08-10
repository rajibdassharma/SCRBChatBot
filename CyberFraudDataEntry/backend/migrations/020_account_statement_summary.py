"""Migration 020 -- per-account statement summary (the Money Trail cache).

Why:
  The Money Trail tab aggregated statement_transactions on every
  request. Measured on 190,435 rows that cost ~6.8s, of which ~4s was
  two GROUP BYs, and cold and warm timings were identical because the
  194 MB table does not fit the 128 MB InnoDB buffer pool.

  That is survivable at 190k rows and not at all survivable after the
  full backfill, which is ~15.5M rows -- roughly 80x the work for the
  same screen. No amount of index tuning fixes re-deriving the same
  answer from scratch on every page load.

  So the aggregate is computed once, when the parser writes the rows,
  and stored.

Grain: (account_id, channel).
  Deliberately NOT one row per account. The tab filters by state scope,
  account type and test-station exclusion, so a globally pre-aggregated
  channel breakdown could not answer "channels for Karnataka mule
  accounts". Keeping the channel in the key lets one table serve all
  three panels -- KPIs, channel mix and the account table -- because
  every one of them is a GROUP BY over the same rows, joined to
  all_accounts for the filters.

  Size: accounts x distinct channels. On the current corpus that is
  154 x ~11 = ~1.7k rows in place of 190k, and after the full backfill
  roughly 12,000 x ~11 = ~130k rows in place of 15.5M.

Verified vs unverified is carried as SEPARATE totals rather than a
flag, because the tab shows coverage over everything and money over
reconciled statements only. Storing one and deriving the other would
mean re-reading the fact table, which is the thing this table exists
to avoid.

Idempotent -- safe to re-run.

Usage:
  python -m migrations.020_account_statement_summary
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
    print("Running migration 020 -- account statement summary")
    async with engine.begin() as conn:
        if await _table_exists(conn, "account_statement_summary"):
            print("  = account_statement_summary already exists, skipping")
        else:
            print("  + CREATE TABLE account_statement_summary")
            await conn.execute(text("""
                CREATE TABLE account_statement_summary (
                    account_id       VARCHAR(36)  NOT NULL,
                    -- '' rather than NULL: this is half the primary key,
                    -- and a PK column cannot be NULL. '' means the
                    -- narration carried no recognisable channel marker.
                    channel          VARCHAR(30)  NOT NULL DEFAULT '',
                    txns             INT          NOT NULL DEFAULT 0,
                    debit            DECIMAL(18,2) NOT NULL DEFAULT 0,
                    credit           DECIMAL(18,2) NOT NULL DEFAULT 0,
                    verified_txns    INT          NOT NULL DEFAULT 0,
                    verified_debit   DECIMAL(18,2) NOT NULL DEFAULT 0,
                    verified_credit  DECIMAL(18,2) NOT NULL DEFAULT 0,
                    -- 0 if ANY statement behind this account/channel
                    -- failed reconciliation. Aggregates with MIN().
                    all_verified     TINYINT(1)   NOT NULL DEFAULT 0,
                    first_txn        DATE         NULL,
                    last_txn         DATE         NULL,
                    parser_version   VARCHAR(30)  NULL,
                    updated_at       DATETIME     DEFAULT CURRENT_TIMESTAMP
                                                  ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (account_id, channel),
                    KEY ix_ass_channel (channel),
                    KEY ix_ass_debit (debit),
                    CONSTRAINT fk_ass_account
                        FOREIGN KEY (account_id) REFERENCES all_accounts(id)
                        ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))
    print("Migration 020 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
