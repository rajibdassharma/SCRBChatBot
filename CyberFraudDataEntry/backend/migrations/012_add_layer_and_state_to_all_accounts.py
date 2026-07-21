"""
Migration 012 — add `layer` and `branch_state` to `all_accounts`.

Why:
  Operators asked for two additional fields in the Account Details
  section (2026-07-21):
    - `layer` INT (1..15) — the money-trail layer this account sits
      at, same concept as lien_accounts.layer + money_transfers.layer.
    - `branch_state` VARCHAR(100) — the Indian state the bank branch
      is in. Nullable. Entry form disables the KA-districts dropdown
      when a state other than Karnataka is chosen.

Design:
  - Both columns are nullable so existing rows keep NULL and no
    backfill is required.
  - `layer` is a plain INT (no CHECK constraint) so we can widen the
    range later without a schema change; Pydantic validator enforces
    1..15 at the API layer.
  - `branch_state` is free-text VARCHAR — same pattern as
    branch_district. Frontend enforces the picklist.
  - Positioned right after `branch_district` so the schema reads
    naturally: branch_name -> district -> state.

Idempotent — safe to re-run.

Usage:
  python -m migrations.012_add_layer_and_state_to_all_accounts
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
    print("Running migration 012 — add all_accounts.layer + all_accounts.branch_state")
    async with engine.begin() as conn:
        if await _column_exists(conn, "all_accounts", "branch_state"):
            print("  = all_accounts.branch_state already exists, skipping ADD COLUMN")
        else:
            print("  + ADD COLUMN all_accounts.branch_state VARCHAR(100) NULL")
            await conn.execute(text(
                "ALTER TABLE all_accounts "
                "ADD COLUMN branch_state VARCHAR(100) NULL AFTER branch_district"
            ))

        if await _column_exists(conn, "all_accounts", "layer"):
            print("  = all_accounts.layer already exists, skipping ADD COLUMN")
        else:
            print("  + ADD COLUMN all_accounts.layer INT NULL")
            await conn.execute(text(
                "ALTER TABLE all_accounts "
                "ADD COLUMN layer INT NULL AFTER branch_state"
            ))

    print("Migration 012 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
