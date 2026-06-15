"""
Migration 002 — add `ps_id` to the `cases` table and re-scope uniqueness
to `(unit_id, ps_id, fir_no)`.

Why:
  The current UNIQUE constraint is (unit_id, fir_no). In districts that
  contain multiple police stations (Bangalore City being the obvious
  example), this wrongly blocks PS-B from registering FIR 45/2026
  because PS-A already used that number against the same unit_id —
  even though FIRs are independently numbered per PS in police
  operations.

What this migration does:
  1. Adds `ps_id INT NULL` (nullable first so the backfill can run)
  2. Backfills: `cases.ps_id = users.ps_id` of the submitter
  3. Sanity check — aborts if any row still has NULL `ps_id`
  4. Flips `ps_id` to NOT NULL + adds FK to `police_stations(id)`
  5. Drops the old `uq_case_unit_fir` unique index
  6. Adds the new `uq_case_unit_ps_fir` unique index on
     `(unit_id, ps_id, fir_no)`
  7. Adds a helper index on `ps_id` alone for the new
     PS-scoped search queries

The user verified ahead of time that every existing case row has a
submitter with a valid ps_id — there are no orphan rows. The sanity
check in step 3 belts-and-braces against that assumption.

Idempotent — safe to re-run.

Usage:
  python -m migrations.002_add_ps_id_to_cases
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


async def _index_exists(conn: AsyncConnection, table: str, index: str) -> bool:
    row = await conn.execute(
        text(
            "SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl AND INDEX_NAME = :idx"
        ),
        {"db": settings.DB_NAME, "tbl": table, "idx": index},
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


async def _fk_exists(conn: AsyncConnection, table: str, constraint_name: str) -> bool:
    row = await conn.execute(
        text(
            "SELECT 1 FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl "
            "AND CONSTRAINT_NAME = :name AND CONSTRAINT_TYPE = 'FOREIGN KEY'"
        ),
        {"db": settings.DB_NAME, "tbl": table, "name": constraint_name},
    )
    return row.first() is not None


async def run() -> None:
    print("Running migration 002 — add ps_id to cases + re-scope uniqueness")
    async with engine.begin() as conn:

        # 1. Add column (nullable)
        if await _column_exists(conn, "cases", "ps_id"):
            print("  = cases.ps_id already exists, skipping ADD COLUMN")
        else:
            print("  + ALTER TABLE cases ADD COLUMN ps_id INT NULL")
            await conn.execute(text("ALTER TABLE cases ADD COLUMN ps_id INT NULL"))

        # 2. Backfill from users.ps_id of the submitter
        result = await conn.execute(text(
            "UPDATE cases c "
            "JOIN users u ON u.id = c.submitted_by "
            "SET c.ps_id = u.ps_id "
            "WHERE c.ps_id IS NULL AND u.ps_id IS NOT NULL"
        ))
        print(f"  ~ backfilled ps_id on {result.rowcount} row(s)")

        # 3. Sanity check — must be zero
        row = await conn.execute(text("SELECT COUNT(*) FROM cases WHERE ps_id IS NULL"))
        null_count = row.scalar() or 0
        if null_count > 0:
            raise RuntimeError(
                f"ABORT: {null_count} case row(s) still have NULL ps_id after backfill. "
                f"These rows either have no submitter or the submitter has no ps_id set. "
                f"Fix the data and re-run, or relax the migration to allow NULLs."
            )
        print("  = sanity check OK — every cases row has a ps_id")

        # 4. Flip NOT NULL + add FK
        if await _column_is_nullable(conn, "cases", "ps_id"):
            print("  + ALTER TABLE cases MODIFY COLUMN ps_id INT NOT NULL")
            await conn.execute(text("ALTER TABLE cases MODIFY COLUMN ps_id INT NOT NULL"))
        else:
            print("  = cases.ps_id is already NOT NULL")

        if await _fk_exists(conn, "cases", "fk_cases_ps_id"):
            print("  = FK fk_cases_ps_id already exists, skipping")
        else:
            print("  + ADD CONSTRAINT fk_cases_ps_id FOREIGN KEY (ps_id) REFERENCES police_stations(id)")
            await conn.execute(text(
                "ALTER TABLE cases ADD CONSTRAINT fk_cases_ps_id "
                "FOREIGN KEY (ps_id) REFERENCES police_stations(id)"
            ))

        # 5. Add the new unique index FIRST — its leftmost column is
        #    unit_id, so once it exists MySQL has an index that satisfies
        #    the cases.unit_id → units.id FK requirement. Dropping the
        #    old composite is then safe.
        #
        #    If we drop first, MySQL rejects it with error 1553
        #    "Cannot drop index 'uq_case_unit_fir': needed in a foreign
        #    key constraint" — because the old composite is the only
        #    index currently covering unit_id.
        if await _index_exists(conn, "cases", "uq_case_unit_ps_fir"):
            print("  = uq_case_unit_ps_fir already exists, skipping CREATE")
        else:
            print("  + CREATE UNIQUE INDEX uq_case_unit_ps_fir ON cases (unit_id, ps_id, fir_no)")
            await conn.execute(text(
                "CREATE UNIQUE INDEX uq_case_unit_ps_fir ON cases (unit_id, ps_id, fir_no)"
            ))

        # 6. Now safe to drop the old unique index.
        if await _index_exists(conn, "cases", "uq_case_unit_fir"):
            print("  - DROP INDEX uq_case_unit_fir ON cases")
            await conn.execute(text("ALTER TABLE cases DROP INDEX uq_case_unit_fir"))
        else:
            print("  = uq_case_unit_fir already absent, skipping DROP")

        # 7. Helper index on ps_id alone — speeds up PS-scoped search
        if await _index_exists(conn, "cases", "ix_cases_ps_id"):
            print("  = ix_cases_ps_id already exists, skipping")
        else:
            print("  + CREATE INDEX ix_cases_ps_id ON cases (ps_id)")
            await conn.execute(text("CREATE INDEX ix_cases_ps_id ON cases (ps_id)"))

    print("Migration 002 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
