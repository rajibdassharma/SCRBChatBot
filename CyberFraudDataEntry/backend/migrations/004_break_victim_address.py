"""
Migration 004 — break victims.address into structured fields.

What changes
  Adds six columns to victims:
    - house_no     VARCHAR(50)   NULL
    - street_name  VARCHAR(200)  NULL
    - city         VARCHAR(100)  NULL
    - state        VARCHAR(100)  NULL
    - country      VARCHAR(100)  NULL DEFAULT 'India'
    - pincode      VARCHAR(10)   NULL

  The old `address` TEXT column is left in place. It's no longer read or
  written by the application — the API schema and ORM model dropped it.
  Leaving the column behind is safer than DROP COLUMN at this stage:
    - The migration stays purely additive (rollback = drop the new cols).
    - Any free-form address text that operators have already entered
      since migration 003 isn't lost; it can be hand-migrated into the
      new columns before a later migration drops it.

Idempotent — safe to re-run.

Usage:
  python -m migrations.004_break_victim_address
"""

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from database import engine
from config import settings


_NEW_COLUMNS: list[tuple[str, str]] = [
    ("house_no",    "VARCHAR(50)  NULL"),
    ("street_name", "VARCHAR(200) NULL"),
    ("city",        "VARCHAR(100) NULL"),
    ("state",       "VARCHAR(100) NULL"),
    ("country",     "VARCHAR(100) NULL DEFAULT 'India'"),
    ("pincode",     "VARCHAR(10)  NULL"),
]


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
    print("Running migration 004 — break victim address into structured fields")
    async with engine.begin() as conn:
        for name, ddl in _NEW_COLUMNS:
            if await _column_exists(conn, "victims", name):
                print(f"  = victims.{name} already exists, skipping")
                continue
            stmt = f"ALTER TABLE victims ADD COLUMN {name} {ddl}"
            print(f"  + {stmt}")
            await conn.execute(text(stmt))
    print("Migration 004 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
