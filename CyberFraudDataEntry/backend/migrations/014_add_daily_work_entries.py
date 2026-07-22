"""
Migration 014 — create `daily_work_entries` table.

Why:
  New "Investigation Log" feature (2026-07-22) — call-centre PSes
  log per-FIR-per-day investigation activity (notices, lien/unlien
  requests, arrests, statements, final report). Follows the same
  per-PS scoping the DSR + all-accounts + portals-dsr tables use
  (VAPT 7.7 / 7.8 rule since migration 008).

Design:
  - Uniqueness key (unit_id, ps_id, fir_no, report_date) — one row
    per PS's work on one FIR on one day. Upsert on POST — a re-
    submit for the same key updates in place.
  - All counter columns INT NOT NULL DEFAULT 0. Empty means "we
    entered zero", not "unknown" — keeps SUM aggregation trivial.
  - `total_lien_amount` / `total_unlien_amount` NUMERIC(18,2)
    matching the DSR + cases money columns.
  - `final_report` VARCHAR(1) NULLABLE — A / B / C — most days
    the case is still open so this stays NULL.

CHARSET / COLLATE explicit (utf8mb4 / utf8mb4_unicode_ci) — same
lesson as migrations 003 + 007 + 009 + 013 so FKs to units /
police_stations / users line up cleanly.

Idempotent — safe to re-run.

Usage:
  python -m migrations.014_add_daily_work_entries
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
    print("Running migration 014 — add daily_work_entries")
    async with engine.begin() as conn:
        if await _table_exists(conn, "daily_work_entries"):
            print("  = daily_work_entries already exists, skipping CREATE")
        else:
            print("  + CREATE TABLE daily_work_entries")
            await conn.execute(text("""
                CREATE TABLE daily_work_entries (
                    id                              INT AUTO_INCREMENT PRIMARY KEY,
                    unit_id                         INT         NOT NULL,
                    ps_id                           INT         NOT NULL,
                    report_date                     DATE        NOT NULL,
                    fir_no                          VARCHAR(50) NOT NULL,

                    -- Red section: Notices
                    notices_35_41a_count            INT NOT NULL DEFAULT 0,
                    notices_91_92_94_banks          INT NOT NULL DEFAULT 0,
                    notices_91_92_94_intermediary   INT NOT NULL DEFAULT 0,
                    notices_91_92_94_account_holder INT NOT NULL DEFAULT 0,
                    notices_91_92_94_cdr_ipdr       INT NOT NULL DEFAULT 0,

                    -- Yellow section: Lien / Unlien
                    lien_requests_count             INT           NOT NULL DEFAULT 0,
                    freeze_requests_count           INT           NOT NULL DEFAULT 0,
                    total_lien_amount               NUMERIC(18,2) NOT NULL DEFAULT 0,
                    unlien_requests_count           INT           NOT NULL DEFAULT 0,
                    defreeze_requests_count         INT           NOT NULL DEFAULT 0,
                    total_unlien_amount             NUMERIC(18,2) NOT NULL DEFAULT 0,

                    -- Green section: Investigation Outcomes
                    arrests_count                   INT NOT NULL DEFAULT 0,
                    statements_count                INT NOT NULL DEFAULT 0,
                    final_report                    VARCHAR(1)   NULL,

                    submitted_by                    INT      NULL,
                    created_at                      DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at                      DATETIME DEFAULT CURRENT_TIMESTAMP
                                                       ON UPDATE CURRENT_TIMESTAMP,
                    CONSTRAINT uq_daily_work_unit_ps_fir_date
                        UNIQUE (unit_id, ps_id, fir_no, report_date),
                    CONSTRAINT fk_daily_work_unit_id
                        FOREIGN KEY (unit_id) REFERENCES units(id),
                    CONSTRAINT fk_daily_work_ps_id
                        FOREIGN KEY (ps_id) REFERENCES police_stations(id),
                    CONSTRAINT fk_daily_work_submitted_by
                        FOREIGN KEY (submitted_by) REFERENCES users(id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))

        # Helper index for the by-fir history lookup (Update page).
        if await _index_exists(conn, "daily_work_entries", "ix_daily_work_unit_ps_fir"):
            print("  = ix_daily_work_unit_ps_fir already exists, skipping")
        else:
            print("  + CREATE INDEX ix_daily_work_unit_ps_fir")
            await conn.execute(text(
                "CREATE INDEX ix_daily_work_unit_ps_fir "
                "ON daily_work_entries (unit_id, ps_id, fir_no)"
            ))

        # Helper index for cross-FIR history (main entry page loads
        # recent rows for this PS on mount).
        if await _index_exists(conn, "daily_work_entries", "ix_daily_work_report_date"):
            print("  = ix_daily_work_report_date already exists, skipping")
        else:
            print("  + CREATE INDEX ix_daily_work_report_date")
            await conn.execute(text(
                "CREATE INDEX ix_daily_work_report_date "
                "ON daily_work_entries (report_date)"
            ))

    print("Migration 014 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
