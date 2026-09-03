"""Migration 027 — create account_unlinked_counterparty.

WHAT IT HOLDS
-------------
Per (account, named counterparty, channel): money that LEFT the account
to somebody the bank named but gave no account number for.

WHY IT HAS TO BE A SUMMARY TABLE
--------------------------------
The Graphical Analysis screen needs this to explain why an account with
a parsed statement and hundreds of rows shows no arrows: the recipient
was named, not numbered, so no link could be built.

The obvious implementation reads statement_transactions per FIR at
request time. It was tried on 2026-09-03 and reverted the same day.
FIR 0001/2026 at Bagalkot has 29 accounts and 66,055 statement rows and
took 15.6 SECONDS on a 32 GB laptop; the 2-vCPU server returned a
gateway timeout. The aggregation was not the cost -- the same filter
with no GROUP BY took the same 15.6 s. An index on account_id yields
row pointers, and each fetch is a random read into a 27.6 GB table.
There is no query shape that reads the fact table from a request and is
fast.

So it is precomputed here, like every other figure the dashboards read.
Sized from a 500-account sample: ~58 rows per account with statements,
25,588 such accounts, so roughly 1.5 M rows. Large next to the other
summaries, trivial next to the 26.5 M-row fact table, and indexed by
account it is a handful of rows per lookup.

WHY THE ROWS ARE WHAT THEY ARE
------------------------------
Included only when the row is a DEBIT on a transfer channel with a
counterparty NAME and neither a counterparty account number nor a UPI
id -- the two things that could have made it a link instead. Cash
withdrawals and charges are excluded: the narration code for a
withdrawal ("CWDR") is picked up as a name and was, on the first FIR
tested, the largest single "recipient" at Rs 1.17 lakh across 165 rows.
An ATM is not a person.

verified_debit sums chain_ok = 1 ONLY. unverified_txns counts the rest
without adding their money to anything. Collapsing the two is what put
a quadrillion-rupee figure on a dashboard once already.

DERIVED AND REBUILDABLE from backend/uploads via analysis.daily, like
every other table in this subsystem. Losing it costs a rebuild, not
evidence.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text                                # noqa: E402
from database import engine                                # noqa: E402

TABLE = "account_unlinked_counterparty"

DDL = f"""
CREATE TABLE {TABLE} (
    id              BIGINT NOT NULL AUTO_INCREMENT,
    account_id      VARCHAR(36) NOT NULL,
    counterparty_name VARCHAR(200) NOT NULL,
    channel         VARCHAR(30) NULL,
    txns            INT NOT NULL DEFAULT 0,
    -- chain_ok = 1 rows only. The name says verified so nobody sums the
    -- wrong column by accident, the way `debit` was summed before
    -- migration 023 split it out.
    verified_debit  DECIMAL(24,2) NOT NULL DEFAULT 0,
    unverified_txns INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY ix_unlinked_account (account_id),
    -- One row per (account, name, channel). Lets the builder REPLACE
    -- rather than delete-then-insert, so a failed rebuild cannot leave
    -- the table empty.
    UNIQUE KEY uq_unlinked_acct_name_chan (account_id, counterparty_name, channel),
    CONSTRAINT fk_unlinked_account
        FOREIGN KEY (account_id) REFERENCES all_accounts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


async def _table_exists(conn, name: str) -> bool:
    return bool((await conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = :t"
    ), {"t": name})).scalar())


async def run() -> None:
    print("Running migration 027 -- account_unlinked_counterparty")
    async with engine.begin() as conn:
        if await _table_exists(conn, TABLE):
            print(f"  = {TABLE} already exists, skipping")
        else:
            # utf8mb4_unicode_ci declared explicitly: all_accounts.id is
            # utf8mb4_unicode_ci and MySQL 3780 fires on any FK whose
            # referencing column disagrees. See docs/database.md §3.
            await conn.execute(text(DDL))
            print(f"  + {TABLE} created")

    await engine.dispose()
    print("Migration 027 complete.")


if __name__ == "__main__":
    asyncio.run(run())
