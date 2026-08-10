"""Migration 022 -- per-row balance-chain verdict.

THE BUG THIS FIXES
------------------
`upload_ledger.status = 'ok'` is a FILE-level verdict: the running
balance held on at least 98% of steps. That tolerance is deliberate --
statements interrupt their own chain at page breaks and
carried-forward bands -- but it was then used to vouch for every row
INSIDE the file, which is a different and much stronger claim.

Measured on this corpus, one account reported Rs 205,648,905,136 of
outflow. Its file scored 99.22% and was marked `ok`. Twenty-nine rows
out of 3,700 -- comfortably inside the 2% slack -- carried
Rs 205,642,955,681 of that. Excluding them the same account reads
Rs 5,949,455 out against Rs 5,960,228 in: a ratio of 1.00, which is
what a pass-through account should look like.

The chain does not merely detect those rows, it says what the right
answer was. A row recording a Rs 44,476,848,191 debit whose balance
moved 25,000.10 -> 24,500.10 had a true debit of Rs 500.

WHY THREE STATES AND NOT A BOOLEAN
----------------------------------
    1  PASSED    tested against the preceding balance, and it agreed
    0  REJECTED  tested, and it did not
   -1  UNTESTED  nothing to test against: the statement carries no
                 running balance, or the row sits at a chain restart
                 (file boundary, or after a gap)

Collapsing UNTESTED into PASSED is exactly the mistake this column
exists to prevent. An RBL export with no balance column had its account
number read as the debit on all 16,493 rows; no chain step could
contradict it, so a two-state check waved it through and reported
Rs 6.68 QUADRILLION as clean. Untested is not innocent -- it is
unknown, and unknown money must not enter a total an officer reads.

Across the top accounts measured before this landed:
    reported   Rs 10,37,24,29,13,70,88,562
    PASSED     Rs             3,69,38,520   <- the only publishable figure
    REJECTED   Rs  1,00,96,93,10,86,78,842
    UNTESTED   Rs  9,36,27,35,99,14,71,200

NO RE-PARSING REQUIRED
----------------------
Every input the chain needs -- row_no, debit, credit, balance -- is
already stored. analysis/stamp_chain.py replays it over the existing
rows. Nothing re-reads a PDF.

Idempotent -- safe to re-run.

Usage:
  python -m migrations.022_statement_chain_ok
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
    print("Running migration 022 -- per-row balance chain verdict")
    async with engine.begin() as conn:
        if await _column_exists(conn, "statement_transactions", "chain_ok"):
            print("  = chain_ok already exists, skipping")
        else:
            print("  + ALTER statement_transactions ADD chain_ok")
            # Defaults to -1 (UNTESTED), not 1. A row that has never
            # been through the stamping pass has not been verified by
            # anything, and defaulting to PASSED would silently admit
            # every existing row to the money totals -- the precise
            # failure this migration exists to end.
            await conn.execute(text("""
                ALTER TABLE statement_transactions
                ADD COLUMN chain_ok TINYINT NOT NULL DEFAULT -1
                    COMMENT '1=passed 0=rejected -1=untested',
                ADD KEY ix_stmt_txn_chain (chain_ok)
            """))
            print("    all existing rows default to -1 (untested) until stamped")
    print("Migration 022 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
