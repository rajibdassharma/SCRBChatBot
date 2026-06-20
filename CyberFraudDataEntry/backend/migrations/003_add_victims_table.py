"""
Migration 003 — add the `victims` table.

Creates a 1:1 child table for victim details captured at FIR time:
  - first_name, last_name        (required at API layer)
  - bank_account_no, bank_name   (required at API layer)
  - amount_lost                  (required, ≥ 0, ≤ ₹100 cr per validator)
  - age, gender, phone, email,
    address, bank_branch_address (all optional)

Design notes:
  - UNIQUE (case_id) enforces 1:1 at the DB level. To support multiple
    victims per case later, drop just that index — no other migration
    needed.
  - CASCADE delete on parent case removal, same pattern as arrests etc.
  - Existing 645 cases will have NO victim row; the API treats the
    victim block as Optional on CaseCreate so legacy cases can still be
    opened and edited until an operator fills in the victim details.

Idempotent — safe to re-run.

Usage:
  python -m migrations.003_add_victims_table
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
    print("Running migration 003 — add victims table")
    async with engine.begin() as conn:

        if await _table_exists(conn, "victims"):
            print("  = victims table already exists, skipping CREATE")
        else:
            print("  + CREATE TABLE victims")
            # CHARSET + COLLATE must match cases.id exactly or the FK
            # constraint fails with MySQL error 3780 "Referencing column
            # and referenced column are incompatible". Production uses
            # utf8mb4 / utf8mb4_unicode_ci (verified 2026-06-20).
            await conn.execute(text("""
                CREATE TABLE victims (
                    id                   VARCHAR(36) NOT NULL,
                    case_id              VARCHAR(36) NOT NULL,
                    first_name           VARCHAR(100) NOT NULL,
                    last_name            VARCHAR(100) NOT NULL,
                    age                  INT NULL,
                    gender               VARCHAR(30) NULL,
                    phone                VARCHAR(20) NULL,
                    email                VARCHAR(200) NULL,
                    address              TEXT NULL,
                    amount_lost          DECIMAL(18,2) NOT NULL DEFAULT 0,
                    bank_account_no      VARCHAR(50) NOT NULL,
                    bank_name            VARCHAR(200) NOT NULL,
                    bank_branch_address  TEXT NULL,
                    created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    CONSTRAINT fk_victims_case_id
                        FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))

        # 1:1 enforcement — at most one victim row per case_id.
        if await _index_exists(conn, "victims", "uq_victims_case_id"):
            print("  = uq_victims_case_id already exists, skipping")
        else:
            print("  + CREATE UNIQUE INDEX uq_victims_case_id ON victims (case_id)")
            await conn.execute(text(
                "CREATE UNIQUE INDEX uq_victims_case_id ON victims (case_id)"
            ))

    print("Migration 003 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
