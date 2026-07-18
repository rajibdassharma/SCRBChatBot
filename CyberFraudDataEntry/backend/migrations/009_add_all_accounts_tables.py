"""
Migration 009 — add the All Accounts feature tables.

Why:
  New "All Accounts" feature (2026-07-18) — one row per bank / wallet
  account a KA CEN PS is investigating (victim, mule, or non-mule
  under review). Broader than mule_reports because it captures the
  victim's own accounts too, and adds a repeating Mule Herder child
  for confirmed mule accounts.

Design:
  - `all_accounts` — main row. Per-PS scoping via `unit_id + ps_id`,
    UNIQUE `(unit_id, ps_id, serial_no)` enforces the per-PS auto-
    incremented Serial No invariant so two operators can't race for
    the same number.
  - `all_account_mule_herders` — cascade child (0..n rows per Mule
    account). ON DELETE CASCADE via the parent FK.
  - `account_type` = 'Victim' | 'Mule' | 'Non-Mule' — enforced at the
    application layer (ACCOUNT_TYPES frozenset + route validator +
    Pydantic Literal). Kept as VARCHAR(20) so adding a fourth type
    later is a one-line change with no ALTER TABLE.

CHARSET / COLLATE explicit (utf8mb4 / utf8mb4_unicode_ci) so FKs to
`units.id` + `police_stations.id` + `users.id` match their collations
exactly — same lesson as migrations 003 + 007 (see database.md §3).

Idempotent — safe to re-run.

Usage:
  python -m migrations.009_add_all_accounts_tables
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
    print("Running migration 009 — add all_accounts + all_account_mule_herders")
    async with engine.begin() as conn:
        # ── all_accounts ──────────────────────────────────────────
        if await _table_exists(conn, "all_accounts"):
            print("  = all_accounts already exists, skipping CREATE")
        else:
            print("  + CREATE TABLE all_accounts")
            await conn.execute(text("""
                CREATE TABLE all_accounts (
                    id                    VARCHAR(36)  NOT NULL,
                    unit_id               INT          NOT NULL,
                    ps_id                 INT          NOT NULL,
                    serial_no             INT          NOT NULL,
                    fir_no                VARCHAR(50)  NULL,
                    ncrp_ack_no           VARCHAR(60)  NULL,
                    account_no            VARCHAR(50)  NOT NULL,
                    bank_name             VARCHAR(200) NOT NULL,
                    branch_name           VARCHAR(200) NULL,
                    ifsc_code             VARCHAR(20)  NULL,
                    account_holder_name   VARCHAR(200) NOT NULL,
                    kyc_address           TEXT         NULL,
                    kyc_mobile            VARCHAR(20)  NULL,
                    id_photo_path         VARCHAR(500) NULL,
                    account_type          VARCHAR(20)  NOT NULL,
                    submitted_by          INT          NULL,
                    created_at            DATETIME     DEFAULT CURRENT_TIMESTAMP,
                    updated_at            DATETIME     DEFAULT CURRENT_TIMESTAMP
                                          ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    CONSTRAINT fk_all_accounts_unit_id
                        FOREIGN KEY (unit_id) REFERENCES units(id),
                    CONSTRAINT fk_all_accounts_ps_id
                        FOREIGN KEY (ps_id) REFERENCES police_stations(id),
                    CONSTRAINT fk_all_accounts_submitted_by
                        FOREIGN KEY (submitted_by) REFERENCES users(id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))

        # Per-PS Serial No uniqueness — same rule the CRUD route
        # relies on for its MAX(serial_no) + 1 assignment.
        if await _index_exists(conn, "all_accounts", "uq_all_account_ps_serial"):
            print("  = uq_all_account_ps_serial already exists, skipping")
        else:
            print("  + CREATE UNIQUE INDEX uq_all_account_ps_serial")
            await conn.execute(text(
                "CREATE UNIQUE INDEX uq_all_account_ps_serial "
                "ON all_accounts (unit_id, ps_id, serial_no)"
            ))

        # Helper indexes — the PS-scoped list query filters on
        # (unit_id, ps_id) and the dashboard groups by both.
        if await _index_exists(conn, "all_accounts", "ix_all_accounts_unit_ps"):
            print("  = ix_all_accounts_unit_ps already exists, skipping")
        else:
            print("  + CREATE INDEX ix_all_accounts_unit_ps")
            await conn.execute(text(
                "CREATE INDEX ix_all_accounts_unit_ps "
                "ON all_accounts (unit_id, ps_id)"
            ))

        if await _index_exists(conn, "all_accounts", "ix_all_accounts_account_type"):
            print("  = ix_all_accounts_account_type already exists, skipping")
        else:
            print("  + CREATE INDEX ix_all_accounts_account_type")
            await conn.execute(text(
                "CREATE INDEX ix_all_accounts_account_type "
                "ON all_accounts (account_type)"
            ))

        # ── all_account_mule_herders ─────────────────────────────
        if await _table_exists(conn, "all_account_mule_herders"):
            print("  = all_account_mule_herders already exists, skipping CREATE")
        else:
            print("  + CREATE TABLE all_account_mule_herders")
            await conn.execute(text("""
                CREATE TABLE all_account_mule_herders (
                    id          VARCHAR(36)  NOT NULL,
                    account_id  VARCHAR(36)  NOT NULL,
                    name        VARCHAR(200) NOT NULL,
                    address     TEXT         NULL,
                    mobile_no   VARCHAR(20)  NULL,
                    created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    CONSTRAINT fk_herder_account_id
                        FOREIGN KEY (account_id) REFERENCES all_accounts(id)
                        ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))

        if await _index_exists(conn, "all_account_mule_herders", "ix_herder_account_id"):
            print("  = ix_herder_account_id already exists, skipping")
        else:
            print("  + CREATE INDEX ix_herder_account_id")
            await conn.execute(text(
                "CREATE INDEX ix_herder_account_id "
                "ON all_account_mule_herders (account_id)"
            ))

    print("Migration 009 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
