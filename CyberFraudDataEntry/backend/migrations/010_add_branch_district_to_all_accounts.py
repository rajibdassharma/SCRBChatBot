"""
Migration 010 — add `branch_district` to `all_accounts`.

Why:
  Operators asked for a Karnataka District dropdown on the All Accounts
  entry form (2026-07-20). Attached to the Bank Branch section — the
  district the flagged bank branch is in — so district-scoped follow-up
  with the bank becomes filterable.

Design:
  - VARCHAR(100) nullable. Existing rows retain NULL; the entry form
    surfaces the field as optional so nothing else has to backfill.
  - No FK to police_stations.district_name — that lookup is a distinct
    projection, not an entity table. Values are validated to the app-
    layer dropdown source (/api/v1/districts/public) at the UI, and
    stored as free-text for schema simplicity.
  - Column position after `branch_name` so schema reads naturally.

Idempotent — safe to re-run.

Usage:
  python -m migrations.010_add_branch_district_to_all_accounts
"""

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from database import engine
from config import settings


async def _column_exists(conn: AsyncConnection, table: str, column: str) -> bool:
    row = await conn.execute(
        text(
            "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl AND COLUMN_NAME = :col"
        ),
        {"db": settings.DB_NAME, "tbl": table, "col": column},
    )
    return row.first() is not None


async def run() -> None:
    print("Running migration 010 — add all_accounts.branch_district")
    async with engine.begin() as conn:
        if await _column_exists(conn, "all_accounts", "branch_district"):
            print("  = all_accounts.branch_district already exists, skipping ADD COLUMN")
        else:
            print("  + ADD COLUMN all_accounts.branch_district VARCHAR(100) NULL")
            await conn.execute(text(
                "ALTER TABLE all_accounts "
                "ADD COLUMN branch_district VARCHAR(100) NULL AFTER branch_name"
            ))

    print("Migration 010 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
