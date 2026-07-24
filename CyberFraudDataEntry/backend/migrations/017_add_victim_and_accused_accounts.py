"""
Migration 017 -- add `victim_accounts` and `accused_accounts` tables.

Why:
  DSR -> New FIR (2026-07-24) gains two multi-row sections:
    - "Additional Victim Accounts": any accounts *besides* the primary
      one already on `victims` that the victim transferred FROM.
    - "Accused Accounts": one row per accused/mule account the money
      was transferred TO, with account holder name + bank routing.

  Independent of `lien_accounts` (which tracks the freeze/lien
  lifecycle after the fact). This captures the transfer itself.

Design:
  - VARCHAR(36) PK, matches every other child table on `cases`.
  - CASCADE delete on cases(id), same pattern as lien_accounts /
    petitions / refunds.
  - CHARSET/COLLATE utf8mb4 / utf8mb4_unicode_ci to match cases.id
    exactly (see migration 003's note on MySQL error 3780).
  - Amounts as DECIMAL(18,2) matching the amount cap `_validate_amount`
    already enforces (Rs 100 cr).
  - district column is nullable and free-text server-side. The frontend
    populates it from a 36-Karnataka-district dropdown only when
    state == "Karnataka"; other states leave it blank.

Idempotent -- safe to re-run. Each CREATE TABLE is guarded by an
INFORMATION_SCHEMA existence check.

Usage:
  python -m migrations.017_add_victim_and_accused_accounts
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


async def run() -> None:
    print("Running migration 017 -- add victim_accounts + accused_accounts tables")
    async with engine.begin() as conn:

        if await _table_exists(conn, "victim_accounts"):
            print("  = victim_accounts already exists, skipping CREATE")
        else:
            print("  + CREATE TABLE victim_accounts")
            await conn.execute(text("""
                CREATE TABLE victim_accounts (
                    id                 VARCHAR(36) NOT NULL,
                    case_id            VARCHAR(36) NOT NULL,
                    bank_name          VARCHAR(200) NOT NULL,
                    branch_name        VARCHAR(200) NULL,
                    branch_address     VARCHAR(500) NULL,
                    state              VARCHAR(100) NULL,
                    district           VARCHAR(100) NULL,
                    ifsc_code          VARCHAR(20)  NULL,
                    amount_transferred DECIMAL(18,2) NOT NULL DEFAULT 0,
                    created_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    KEY ix_victim_accounts_case_id (case_id),
                    CONSTRAINT fk_victim_accounts_case_id
                        FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))

        if await _table_exists(conn, "accused_accounts"):
            print("  = accused_accounts already exists, skipping CREATE")
        else:
            print("  + CREATE TABLE accused_accounts")
            await conn.execute(text("""
                CREATE TABLE accused_accounts (
                    id                    VARCHAR(36) NOT NULL,
                    case_id               VARCHAR(36) NOT NULL,
                    account_holder_name   VARCHAR(200) NOT NULL,
                    bank_name             VARCHAR(200) NOT NULL,
                    branch_name           VARCHAR(200) NULL,
                    branch_address        VARCHAR(500) NULL,
                    state                 VARCHAR(100) NULL,
                    district              VARCHAR(100) NULL,
                    ifsc_code             VARCHAR(20)  NULL,
                    amount_transferred    DECIMAL(18,2) NOT NULL DEFAULT 0,
                    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    KEY ix_accused_accounts_case_id (case_id),
                    CONSTRAINT fk_accused_accounts_case_id
                        FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))

    print("Migration 017 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
