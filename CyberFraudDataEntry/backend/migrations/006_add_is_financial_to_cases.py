"""
Migration 006 — add `is_financial` to `cases`.

Why:
  Operators now classify cases as Financial or Non-Financial at entry
  time. Non-Financial cases skip the Lien / Unfreeze / Refund flows and
  the victim's banking section. The dashboard analytics keep working as
  before — non-financial cases contribute zeros to amount-based KPIs.

What this migration does:
  1. Adds `is_financial TINYINT(1) NOT NULL DEFAULT 1` to `cases`.
     Default = 1 (Financial) for the existing 645+ rows, matching the
     historical assumption.

Why TINYINT(1) over a string enum:
  - The dashboard filters and aggregations are easier on a boolean.
  - Matches the existing `is_active` convention on `units` and `users`.
  - One byte vs ~15 for VARCHAR.

No CHARSET / COLLATE on the column — it's numeric, the question doesn't
arise. Per database.md §4.2, ADD COLUMN inherits the table defaults
which is the right thing here regardless.

Idempotent — safe to re-run.

Usage:
  python -m migrations.006_add_is_financial_to_cases
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
    print("Running migration 006 — add is_financial to cases")
    async with engine.begin() as conn:
        if await _column_exists(conn, "cases", "is_financial"):
            print("  = cases.is_financial already exists, skipping ADD COLUMN")
        else:
            print("  + ALTER TABLE cases ADD COLUMN is_financial TINYINT(1) NOT NULL DEFAULT 1")
            await conn.execute(text(
                "ALTER TABLE cases ADD COLUMN is_financial TINYINT(1) NOT NULL DEFAULT 1"
            ))
    print("Migration 006 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
