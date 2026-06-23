"""
Migration 007 — add the `daily_nil_declarations` table.

Why:
  PSes that genuinely have no cyber-fraud activity on a given day look
  indistinguishable from PSes that just forgot to enter data — both show
  as zero on the Submission Status table. This table lets an operator
  declare "we have nothing to report today" explicitly. The dashboard
  then renders a green "NIL declared" pill instead of a red zero.

Design:
  - Keyed UNIQUE on (unit_id, ps_id, nil_date) so a PS can declare NIL
    at most once per day, and re-clicking the button is a no-op rather
    than an error.
  - declared_by FK to users(id) so we know who recorded it.
  - Optional reason text for any note ("public holiday", "system down
    in PS network", etc.).

CHARSET / COLLATE explicit (utf8mb4 / utf8mb4_unicode_ci) so the FK to
users.id matches users.id's collation exactly — same lesson as
migration 003 (see database.md §3).

Idempotent.

Usage:
  python -m migrations.007_add_daily_nil_declarations
"""

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from database import engine
from config import settings


async def _table_exists(conn: AsyncConnection, table: str) -> bool:
    row = await conn.execute(
        text(
            "SELECT 1 FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl"
        ),
        {"db": settings.DB_NAME, "tbl": table},
    )
    return row.first() is not None


async def _index_exists(conn: AsyncConnection, table: str, index: str) -> bool:
    row = await conn.execute(
        text(
            "SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl AND INDEX_NAME = :idx"
        ),
        {"db": settings.DB_NAME, "tbl": table, "idx": index},
    )
    return row.first() is not None


async def run() -> None:
    print("Running migration 007 — add daily_nil_declarations table")
    async with engine.begin() as conn:
        if await _table_exists(conn, "daily_nil_declarations"):
            print("  = daily_nil_declarations already exists, skipping CREATE")
        else:
            print("  + CREATE TABLE daily_nil_declarations")
            await conn.execute(text("""
                CREATE TABLE daily_nil_declarations (
                    id           VARCHAR(36) NOT NULL,
                    unit_id      INT NOT NULL,
                    ps_id        INT NOT NULL,
                    declared_by  INT NOT NULL,
                    nil_date     DATE NOT NULL,
                    reason       VARCHAR(255) NULL,
                    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    CONSTRAINT fk_nil_declared_by
                        FOREIGN KEY (declared_by) REFERENCES users(id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))

        if await _index_exists(conn, "daily_nil_declarations", "uq_nil_unit_ps_date"):
            print("  = uq_nil_unit_ps_date already exists, skipping")
        else:
            print("  + CREATE UNIQUE INDEX uq_nil_unit_ps_date ON daily_nil_declarations (unit_id, ps_id, nil_date)")
            await conn.execute(text(
                "CREATE UNIQUE INDEX uq_nil_unit_ps_date "
                "ON daily_nil_declarations (unit_id, ps_id, nil_date)"
            ))

        if await _index_exists(conn, "daily_nil_declarations", "ix_nil_date"):
            print("  = ix_nil_date already exists, skipping")
        else:
            print("  + CREATE INDEX ix_nil_date ON daily_nil_declarations (nil_date)")
            await conn.execute(text(
                "CREATE INDEX ix_nil_date ON daily_nil_declarations (nil_date)"
            ))

    print("Migration 007 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
