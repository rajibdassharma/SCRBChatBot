"""Migration 023 -- separate UNTESTED money in the summary.

WHAT CHANGES
  account_statement_summary gains untested_txns / untested_debit /
  untested_credit, and its existing verified_* columns change meaning:

    before   verified_*  = rows from a file whose chain passed at >=98%
    after    verified_*  = rows whose OWN chain step passed

That is the whole point of migration 022. A file-level verdict was
being used to vouch for individual rows, and 29 rows inside a file
scoring 99.22% carried Rs 205,642,955,681 of a Rs 205,648,905,136
total.

WHY UNTESTED NEEDS ITS OWN COLUMNS
  Three states, and they cannot be collapsed to two:

    PASSED    the arithmetic agrees            -> publishable
    REJECTED  the arithmetic disagrees         -> exclude
    UNTESTED  there was nothing to test against -> exclude, but SAY SO

  Rejected money is wrong. Untested money is unknown, and the two
  deserve different words on screen. An account whose bank simply never
  prints a running balance is not suspicious, and reporting it as Rs 0
  would be its own lie -- so the UI shows "Rs X verified, Rs Y
  unverifiable" rather than hiding the second number or folding it into
  the first.

  Deriving untested as (total - passed - rejected) would work
  arithmetically and lose the distinction between the two exclusions,
  which is exactly the distinction that matters.

Idempotent -- safe to re-run. After applying, rebuild with:
  python -m analysis.summary

Usage:
  python -m migrations.023_summary_untested_totals
"""

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from database import engine
from config import settings


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
    print("Running migration 023 -- untested totals on the summary")
    async with engine.begin() as conn:
        if await _column_exists(conn, "account_statement_summary", "untested_txns"):
            print("  = untested_* already exist, skipping")
        else:
            print("  + ALTER account_statement_summary ADD untested_*")
            # Small table (~56k rows), so this is quick — unlike the
            # equivalent on statement_transactions, which rebuilt 15 GB.
            await conn.execute(text("""
                ALTER TABLE account_statement_summary
                ADD COLUMN untested_txns   INT           NOT NULL DEFAULT 0,
                ADD COLUMN untested_debit  DECIMAL(18,2) NOT NULL DEFAULT 0,
                ADD COLUMN untested_credit DECIMAL(18,2) NOT NULL DEFAULT 0
            """))
            print("    values stay 0 until `python -m analysis.summary` rebuilds")
    print("Migration 023 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
