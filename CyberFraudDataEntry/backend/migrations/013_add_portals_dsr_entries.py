"""
Migration 013 — create `portals_dsr_entries` table.

Why:
  New "Portals DSR" feature (2026-07-21) — one row per PS submission
  of daily portal counters (NCRP, Samanvaya, Sahayog, GRM, MRM,
  Bharatpol, OCWC, NCMEC Tipline). Operators can enter multiple
  batches per day (shift-based), so this is create-new-per-submit
  (NOT upsert like dsr_entries).

Design:
  - Per-PS scoping via (unit_id, ps_id). Same VAPT 7.7/7.8 rule the
    All Accounts + Cases tables use.
  - `report_date` is the calendar day the entry belongs to (not the
    exact submission timestamp — that's `created_at`). Dashboard
    aggregates SUM per (unit_id, ps_id, report_date) so morning +
    afternoon entries roll up to a single per-PS-day figure.
  - 25 metric columns spread across 8 portals. All INT DEFAULT 0
    NOT NULL — a missing field means "we entered zero", not
    "unknown". Keeps the SUM aggregation trivial.
  - `status` ('draft' | 'submitted') — matches the case + all_accounts
    workflow so operators can save partial work.
  - No unique constraint on (unit_id, ps_id, report_date) — multiple
    entries per day are legal by design.

CHARSET / COLLATE explicit (utf8mb4 / utf8mb4_unicode_ci) so FKs to
units.id + police_stations.id + users.id line up cleanly with those
tables (same lesson as migrations 003 + 007 + 009).

Idempotent — safe to re-run.

Usage:
  python -m migrations.013_add_portals_dsr_entries
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
    print("Running migration 013 — add portals_dsr_entries")
    async with engine.begin() as conn:
        if await _table_exists(conn, "portals_dsr_entries"):
            print("  = portals_dsr_entries already exists, skipping CREATE")
        else:
            print("  + CREATE TABLE portals_dsr_entries")
            await conn.execute(text("""
                CREATE TABLE portals_dsr_entries (
                    id                                    VARCHAR(36) NOT NULL,
                    unit_id                               INT         NOT NULL,
                    ps_id                                 INT         NOT NULL,
                    report_date                           DATE        NOT NULL,
                    status                                VARCHAR(20) NOT NULL DEFAULT 'draft',

                    -- NCRP (3)
                    ncrp_received                         INT NOT NULL DEFAULT 0,
                    ncrp_disposed                         INT NOT NULL DEFAULT 0,
                    ncrp_pending                          INT NOT NULL DEFAULT 0,

                    -- Samanvaya (6) — coordination portal, both incoming + outgoing.
                    -- Incoming side has Actions + Action Pending as SEPARATE fields.
                    -- Outgoing side ends with Replies Pending (not the generic 'Pending').
                    samanvaya_request_received            INT NOT NULL DEFAULT 0,
                    samanvaya_actions                     INT NOT NULL DEFAULT 0,
                    samanvaya_action_pending              INT NOT NULL DEFAULT 0,
                    samanvaya_request_sent                INT NOT NULL DEFAULT 0,
                    samanvaya_reply_received              INT NOT NULL DEFAULT 0,
                    samanvaya_replies_pending             INT NOT NULL DEFAULT 0,

                    -- Sahayog (3) — content-removal portal
                    sahayog_unlawful_content_removal      INT NOT NULL DEFAULT 0,
                    sahayog_intermediary_requests         INT NOT NULL DEFAULT 0,
                    sahayog_crypto_requests               INT NOT NULL DEFAULT 0,

                    -- GRM (3) — Action + Pending split into two columns per operator ask
                    grm_request_received                  INT NOT NULL DEFAULT 0,
                    grm_action                            INT NOT NULL DEFAULT 0,
                    grm_pending                           INT NOT NULL DEFAULT 0,

                    -- MRM (3) — same shape as GRM
                    mrm_request_received                  INT NOT NULL DEFAULT 0,
                    mrm_action                            INT NOT NULL DEFAULT 0,
                    mrm_pending                           INT NOT NULL DEFAULT 0,

                    -- Bharatpol (1) — only Requests Received captured on the paper form
                    bharatpol_request_received            INT NOT NULL DEFAULT 0,

                    -- OCWC (3)
                    ocwc_received                         INT NOT NULL DEFAULT 0,
                    ocwc_disposed                         INT NOT NULL DEFAULT 0,
                    ocwc_pending                          INT NOT NULL DEFAULT 0,

                    -- NCMEC Tipline (3)
                    ncmec_received                        INT NOT NULL DEFAULT 0,
                    ncmec_disposed                        INT NOT NULL DEFAULT 0,
                    ncmec_pending                         INT NOT NULL DEFAULT 0,

                    submitted_by                          INT      NULL,
                    created_at                            DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at                            DATETIME DEFAULT CURRENT_TIMESTAMP
                                                          ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    CONSTRAINT fk_portals_dsr_unit_id
                        FOREIGN KEY (unit_id) REFERENCES units(id),
                    CONSTRAINT fk_portals_dsr_ps_id
                        FOREIGN KEY (ps_id) REFERENCES police_stations(id),
                    CONSTRAINT fk_portals_dsr_submitted_by
                        FOREIGN KEY (submitted_by) REFERENCES users(id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))

        # Helper indexes — dashboard filters by (unit_id, ps_id, report_date)
        # heavily; PS-scoped list orders by created_at DESC.
        if await _index_exists(conn, "portals_dsr_entries", "ix_portals_dsr_unit_ps_date"):
            print("  = ix_portals_dsr_unit_ps_date already exists, skipping")
        else:
            print("  + CREATE INDEX ix_portals_dsr_unit_ps_date")
            await conn.execute(text(
                "CREATE INDEX ix_portals_dsr_unit_ps_date "
                "ON portals_dsr_entries (unit_id, ps_id, report_date)"
            ))

        if await _index_exists(conn, "portals_dsr_entries", "ix_portals_dsr_report_date"):
            print("  = ix_portals_dsr_report_date already exists, skipping")
        else:
            print("  + CREATE INDEX ix_portals_dsr_report_date")
            await conn.execute(text(
                "CREATE INDEX ix_portals_dsr_report_date "
                "ON portals_dsr_entries (report_date)"
            ))

    print("Migration 013 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
