"""
Migration 015 — add `sections` column to `cases`.

Why:
  Case entry form gets a new top-level `Sections` textbox next to
  FIR No. / Crime Type (2026-07-22). Free-text so operators can
  enter comma-separated BNS / BNSS / IT Act section numbers like
  "318(4), 319, 340" without a rigid lookup — same shape zeroFIR
  uses on its Acts sub-form.

Design:
  - VARCHAR(500) NULLABLE. 500 chars comfortably covers 20+ sections
    with delimiters + human notes; NULL preserves parity with the 645
    pre-existing cases that never had the field.
  - Column inherits table CHARSET/COLLATE (utf8mb4 / utf8mb4_unicode_ci)
    so multilingual notes work uniformly — same rule as migration 003
    (see database.md convention).
  - No index. Sections are captured for the FIR record and shown on
    the case detail page; we don't query on them.

Idempotent — safe to re-run.

Usage:
  python -m migrations.015_add_sections_to_cases
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
    print("Running migration 015 — add cases.sections")
    async with engine.begin() as conn:
        if await _column_exists(conn, "cases", "sections"):
            print("  = cases.sections already exists, skipping")
        else:
            print("  + ALTER TABLE cases ADD COLUMN sections")
            await conn.execute(text(
                "ALTER TABLE cases ADD COLUMN sections VARCHAR(500) NULL"
            ))
    print("Migration 015 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
