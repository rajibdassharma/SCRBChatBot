"""
Migration 008 — add `ps_id` to the `dsr_entries` table and re-scope
uniqueness to `(unit_id, ps_id, report_date)`.

Why:
  DSR was a per-district filing since day one — one row per unit per
  date, enforced by UNIQUE (unit_id, report_date). Product decision
  on 2026-07-08: DSR becomes per-PS. Each PS files its own DSR;
  bigger districts like Bengaluru Urban (multiple CEN PSes) will now
  have one DSR row per PS per date.

What this migration does:
  1. Adds `ps_id INT NULL` (nullable first so the backfill can run).
  2. Backfills: `dsr_entries.ps_id = users.ps_id` of the submitter.
  3. Sanity check — aborts if any row still has NULL ps_id (would
     mean submitted_by is missing or that user has no ps_id).
  4. Flips `ps_id` to NOT NULL + adds FK to `police_stations(id)`.
  5. Drops the old `uq_dsr_unit_date` unique index.
  6. Adds the new `uq_dsr_unit_ps_date` unique index on
     `(unit_id, ps_id, report_date)`.
  7. Adds a helper index on `ps_id` alone for the dashboard's
     "was DSR filed today?" per-PS lookups.

Migration-day behaviour:
  Existing DSR rows retain their data and get attributed to whichever
  PS submitted them. Any PS in the same district that never submitted
  before will show red ✗ on the dashboard until their own admin
  files. Intentional — this is the point of the change.

Idempotent — safe to re-run.

Usage:
  python -m migrations.008_add_ps_id_to_dsr_entries
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


async def _column_is_nullable(conn: AsyncConnection, table: str, column: str) -> bool:
    row = await conn.execute(
        text(
            "SELECT IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl AND COLUMN_NAME = :col"
        ),
        {"db": settings.DB_NAME, "tbl": table, "col": column},
    )
    r = row.first()
    return bool(r and r[0] == "YES")


async def _fk_exists(conn: AsyncConnection, table: str, fk_name: str) -> bool:
    row = await conn.execute(
        text(
            "SELECT 1 FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl "
            "AND CONSTRAINT_NAME = :name AND CONSTRAINT_TYPE = 'FOREIGN KEY'"
        ),
        {"db": settings.DB_NAME, "tbl": table, "name": fk_name},
    )
    return row.first() is not None


async def _index_exists(conn: AsyncConnection, table: str, index_name: str) -> bool:
    row = await conn.execute(
        text(
            "SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl AND INDEX_NAME = :name"
        ),
        {"db": settings.DB_NAME, "tbl": table, "name": index_name},
    )
    return row.first() is not None


async def run() -> None:
    print("Running migration 008 — add ps_id to dsr_entries")
    async with engine.begin() as conn:
        # ── 1. ADD COLUMN (nullable so backfill can run) ────────────
        if await _column_exists(conn, "dsr_entries", "ps_id"):
            print("  = dsr_entries.ps_id already exists, skipping ADD COLUMN")
        else:
            print("  + ALTER TABLE dsr_entries ADD COLUMN ps_id INT NULL")
            await conn.execute(text(
                "ALTER TABLE dsr_entries ADD COLUMN ps_id INT NULL AFTER unit_id"
            ))

        # ── 2. Backfill from users.ps_id ────────────────────────────
        result = await conn.execute(text(
            "UPDATE dsr_entries d "
            "JOIN users u ON u.id = d.submitted_by "
            "SET d.ps_id = u.ps_id "
            "WHERE d.ps_id IS NULL AND u.ps_id IS NOT NULL"
        ))
        print(f"  ~ backfilled ps_id on {result.rowcount} row(s)")

        # ── 3. Sanity check — any row still NULL blocks the migration ──
        row = await conn.execute(text(
            "SELECT COUNT(*) FROM dsr_entries WHERE ps_id IS NULL"
        ))
        null_count = (row.first() or (0,))[0]
        if null_count:
            # Also dump the offenders so the operator can act.
            orphans = (await conn.execute(text(
                "SELECT d.id, d.unit_id, d.report_date, d.submitted_by "
                "FROM dsr_entries d WHERE d.ps_id IS NULL LIMIT 20"
            ))).all()
            raise RuntimeError(
                f"Migration 008 aborted: {null_count} dsr_entries row(s) still "
                f"have NULL ps_id after backfill. First 20 offenders:\n"
                + "\n".join(
                    f"  id={r[0]} unit_id={r[1]} report_date={r[2]} submitted_by={r[3]}"
                    for r in orphans
                )
                + "\nFix the underlying users (assign a ps_id) or delete these DSR "
                  "rows, then re-run the migration."
            )
        print("  = sanity check OK — every dsr_entries row has a ps_id")

        # ── 4. Flip ps_id to NOT NULL + add FK ──────────────────────
        if await _column_is_nullable(conn, "dsr_entries", "ps_id"):
            print("  + ALTER TABLE dsr_entries MODIFY ps_id INT NOT NULL")
            await conn.execute(text(
                "ALTER TABLE dsr_entries MODIFY ps_id INT NOT NULL"
            ))
        else:
            print("  = dsr_entries.ps_id is already NOT NULL")

        if await _fk_exists(conn, "dsr_entries", "fk_dsr_ps_id"):
            print("  = FK fk_dsr_ps_id already exists, skipping")
        else:
            print("  + ADD CONSTRAINT fk_dsr_ps_id FOREIGN KEY (ps_id) REFERENCES police_stations(id)")
            await conn.execute(text(
                "ALTER TABLE dsr_entries "
                "ADD CONSTRAINT fk_dsr_ps_id FOREIGN KEY (ps_id) REFERENCES police_stations(id)"
            ))

        # ── 5. Add NEW (unit_id, ps_id, report_date) unique index FIRST.
        # Must come before dropping the old one because MySQL uses the
        # old uq_dsr_unit_date as the backing index for the FK on
        # unit_id (every FK needs an index that starts with the FK
        # column). Creating the new one first — which also starts with
        # unit_id — lets MySQL swap the FK's backing index cleanly.
        if await _index_exists(conn, "dsr_entries", "uq_dsr_unit_ps_date"):
            print("  = uq_dsr_unit_ps_date already exists, skipping CREATE")
        else:
            print("  + CREATE UNIQUE INDEX uq_dsr_unit_ps_date ON dsr_entries (unit_id, ps_id, report_date)")
            await conn.execute(text(
                "CREATE UNIQUE INDEX uq_dsr_unit_ps_date "
                "ON dsr_entries (unit_id, ps_id, report_date)"
            ))

        # ── 6. Drop old unique index (now safe — new index above covers
        # the FK-backing requirement on unit_id).
        if await _index_exists(conn, "dsr_entries", "uq_dsr_unit_date"):
            print("  - DROP INDEX uq_dsr_unit_date")
            await conn.execute(text(
                "ALTER TABLE dsr_entries DROP INDEX uq_dsr_unit_date"
            ))
        else:
            print("  = uq_dsr_unit_date already absent, skipping DROP")

        # ── 7. Helper index on ps_id alone (dashboard lookups) ─────
        if await _index_exists(conn, "dsr_entries", "ix_dsr_ps_id"):
            print("  = ix_dsr_ps_id already exists, skipping")
        else:
            print("  + CREATE INDEX ix_dsr_ps_id ON dsr_entries (ps_id)")
            await conn.execute(text(
                "CREATE INDEX ix_dsr_ps_id ON dsr_entries (ps_id)"
            ))

    print("Migration 008 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
