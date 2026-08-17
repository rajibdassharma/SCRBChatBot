"""Migration 026 — widen account_statement_summary money columns.

DECIMAL(18,2) -> DECIMAL(24,2) on the six money columns.

WHAT BROKE
----------
The summary's `debit` and `credit` are RAW totals: every parsed row for
an (account, channel), including the ones the balance chain rejected.
That is deliberate -- the verified_* columns carry the trustworthy
figures and the raw ones exist so a reader can see how much was thrown
away.

But raw means raw. Measured 2026-08-17: 439 rows in the corpus carry a
chain-REJECTED debit above Rs 100 crore, the worst of them Rs 1,000
trillion, produced by a misparse that read something other than an
amount out of a text-layer PDF. A handful of those in one account sums
past DECIMAL(18,2)'s ceiling of ~1e16, MySQL raises "Out of range value
for column 'debit'", and the INSERT ... SELECT that rebuilds the summary
dies -- taking the whole flush down with it and stopping the nightly run
at step 8.

WHY WIDEN RATHER THAN CLAMP
---------------------------
Clamping the sum to the column maximum would keep the pipeline alive and
silently replace a nonsense figure with a slightly smaller nonsense
figure, indistinguishable from a real one. Widening keeps the arithmetic
faithful to what was parsed: a preposterous raw total is exactly the
right thing for a preposterously misparsed statement to produce, and
every screen already reads verified_* instead.

WHAT THIS IS NOT
----------------
This is NOT a fix for the misparse. The rows are still wrong; they are
just no longer able to stop the run. The real fix is a sanity ceiling in
the parser so an implausible amount is stored as unparseable rather than
as a number, and that needs a re-parse to clean what is already stored.
Tracked separately -- do not read this migration as closing it.

24 digits holds ~1e22. The theoretical worst case here is 439 rows of
1e15 in one group, or ~4.4e17, so this leaves four orders of magnitude
of headroom against data that is already known to be garbage.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text                                # noqa: E402
from database import engine                                # noqa: E402

COLUMNS = (
    "debit", "credit",
    "verified_debit", "verified_credit",
    "untested_debit", "untested_credit",
)


async def _current_type(conn, table: str, column: str) -> str | None:
    return (await conn.execute(text(
        "SELECT column_type FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t "
        "AND column_name = :c"
    ), {"t": table, "c": column})).scalar()


async def run() -> None:
    print("Running migration 026 -- widen summary money columns")
    async with engine.begin() as conn:
        for col in COLUMNS:
            cur = await _current_type(conn, "account_statement_summary", col)
            if cur is None:
                print(f"  ! {col} not found — skipping")
                continue
            if cur.replace(" ", "").startswith("decimal(24,2"):
                print(f"  = {col} already decimal(24,2), skipping")
                continue
            # NOT NULL DEFAULT 0 preserved from migration 020: dropping
            # either would let a NULL total look like a zero one.
            await conn.execute(text(
                f"ALTER TABLE account_statement_summary "
                f"MODIFY COLUMN {col} DECIMAL(24,2) NOT NULL DEFAULT 0"))
            print(f"  + {col}: {cur} -> decimal(24,2)")

    await engine.dispose()
    print("Migration 026 complete.")


if __name__ == "__main__":
    asyncio.run(run())
