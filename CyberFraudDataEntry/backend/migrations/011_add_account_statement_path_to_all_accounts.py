"""
Migration 011 — add `account_statement_path` to `all_accounts`.

Why:
  Operators asked for an Account Statement upload (PDF or Excel) on
  the All Accounts entry form (2026-07-20). One file per account,
  stored on the server filesystem the same way ID photos are, path
  tracked in a nullable column here.

Design:
  - VARCHAR(500) nullable — same shape as `id_photo_path`. Existing
    rows retain NULL; the entry form treats it as optional.
  - Files land under uploads/statements/ (separate from uploads/photos/)
    so ops can size-cap / retention-policy them independently.
  - Placed AFTER id_photo_path so schema reads left-to-right in the
    order the entry form surfaces the two upload widgets.

Idempotent — safe to re-run.

Usage:
  python -m migrations.011_add_account_statement_path_to_all_accounts
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
    print("Running migration 011 — add all_accounts.account_statement_path")
    async with engine.begin() as conn:
        if await _column_exists(conn, "all_accounts", "account_statement_path"):
            print("  = all_accounts.account_statement_path already exists, skipping ADD COLUMN")
        else:
            print("  + ADD COLUMN all_accounts.account_statement_path VARCHAR(500) NULL")
            await conn.execute(text(
                "ALTER TABLE all_accounts "
                "ADD COLUMN account_statement_path VARCHAR(500) NULL AFTER id_photo_path"
            ))

    print("Migration 011 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
