"""Migration 025 — ifsc_branch.

The IFSC-to-branch directory: which bank, branch, district and state an
IFSC code belongs to. ~183,000 rows, loaded by analysis/load_ifsc.py
from the open Razorpay IFSC dataset.

MASTER DATA, NOT DERIVED DATA
-----------------------------
This is the one analysis-adjacent table that is NOT rebuildable from
anything on this server. statement_transactions, crypto_txn and
mule_account_link can all be regenerated from the uploaded PDFs; this
one comes from outside and production sits on KSWAN with no route to
the internet. It therefore belongs IN the nightly dump, alongside the
operational tables, and must never be added to backup-db.sh's derived
exclusion list.

WHY A TABLE RATHER THAN A FILE SHIPPED WITH THE CODE
----------------------------------------------------
A 35 MB CSV in the repo would be carried by every clone and deploy
forever, and would still need parsing on every read. As a table it is
loaded once, joined in SQL, backed up with everything else, and reaches
the dev laptop through the ordinary restore.

WHAT IT IS FOR
--------------
branch_district is entered by operators and is populated on only 4.6%
of mule accounts. Measured against the 1,033 accounts that carry both
an IFSC and an entered district, the dataset agrees 79.8% of the time,
and where it disagrees at STATE level (6.8%) the entry is the wrong one
-- 49% of entered branch districts are simply the operator's OWN police
district. This table resolves 94.8% of the accounts that have no
district at all.

The derived value is joined at READ time and reported separately from
the entered one. Nothing here overwrites operator input: an entry that
disagrees is a data-quality finding for someone to look at, not a row
to silently correct.
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
    print("Running migration 025 -- ifsc_branch")
    async with engine.begin() as conn:
        if await _table_exists(conn, "ifsc_branch"):
            print("  = ifsc_branch already exists, skipping")
        else:
            # No foreign keys: this is a lookup keyed by a code that
            # appears as free text on account rows, and plenty of those
            # codes are malformed (786 of them). An FK would reject the
            # account rather than simply failing to resolve it.
            #
            # CHARSET + COLLATE declared explicitly regardless -- see
            # docs/database.md on MySQL 3780.
            await conn.execute(text("""
                CREATE TABLE ifsc_branch (
                    ifsc        VARCHAR(11)  NOT NULL,
                    bank        VARCHAR(200) NULL,
                    branch      VARCHAR(200) NULL,
                    district    VARCHAR(100) NULL,
                    state       VARCHAR(100) NULL,
                    city        VARCHAR(100) NULL,
                    centre      VARCHAR(100) NULL,
                    address     VARCHAR(500) NULL,
                    -- Which dataset release these rows came from, so a
                    -- stale load is visible rather than guessed at.
                    source      VARCHAR(50)  NULL,
                    loaded_at   DATETIME     DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (ifsc),
                    KEY ix_ifsc_branch_district (district),
                    KEY ix_ifsc_branch_state (state)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                  COLLATE=utf8mb4_unicode_ci
            """))
            print("  + created ifsc_branch")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
