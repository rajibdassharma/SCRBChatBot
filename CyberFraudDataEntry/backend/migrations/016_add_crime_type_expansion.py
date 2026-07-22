"""
Migration 016 — widen `cases.crime_type` and add `cases.crime_type_other`.

Why:
  Crime Type dropdown changes from 3 hardcoded values (Internet /
  Digital / Crypto — all fitting in VARCHAR(30)) to the 31-entry
  KSP Classification list (2026-07-22). Longest entry ("Ransomware
  Attacks, Installing Spyware & Trojan, Using Other malware &
  Viruses to infect digital server") is ~105 chars, so the column
  must widen. VARCHAR(200) gives headroom for future additions to
  the classification list without another schema migration.

  `crime_type_other` captures the operator's free-text when they
  pick "Others" from the dropdown — separate column so aggregation
  can still bucket everyone under "Others" while the specific
  free-text stays queryable.

Design:
  - `crime_type` widened in place. MySQL supports online VARCHAR
    widening on utf8mb4 as long as the new length stays within the
    same character-length class (0-255 bytes stay short); we're
    going 30 → 200, both short. Fast, non-blocking.
  - `crime_type_other` NULLABLE. NULL means "not Others" or "Others
    but operator left the free-text blank" — either way, no
    classification info to expose.
  - Legacy 645 rows keep their {Internet, Digital, Crypto} values.
    The frontend renders those under a Legacy option-group so old
    cases stay editable without silently losing their category.

Idempotent — safe to re-run. The COLUMN_TYPE check on `crime_type`
skips the widen if it's already >= VARCHAR(200).

Usage:
  python -m migrations.016_add_crime_type_expansion
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


async def _column_char_max_length(conn: AsyncConnection, table: str, column: str) -> int | None:
    row = await conn.execute(
        text(
            "SELECT CHARACTER_MAXIMUM_LENGTH "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl AND COLUMN_NAME = :col"
        ),
        {"db": settings.DB_NAME, "tbl": table, "col": column},
    )
    r = row.first()
    return None if r is None else int(r[0]) if r[0] is not None else None


async def run() -> None:
    print("Running migration 016 — widen cases.crime_type + add cases.crime_type_other")
    async with engine.begin() as conn:
        # Widen crime_type
        current_len = await _column_char_max_length(conn, "cases", "crime_type")
        if current_len is not None and current_len >= 200:
            print(f"  = cases.crime_type already VARCHAR({current_len}), skipping widen")
        else:
            print(f"  + ALTER TABLE cases MODIFY COLUMN crime_type VARCHAR(200) NOT NULL "
                  f"(was VARCHAR({current_len}))")
            await conn.execute(text(
                "ALTER TABLE cases MODIFY COLUMN crime_type VARCHAR(200) NOT NULL"
            ))

        # Add crime_type_other
        if await _column_exists(conn, "cases", "crime_type_other"):
            print("  = cases.crime_type_other already exists, skipping")
        else:
            print("  + ALTER TABLE cases ADD COLUMN crime_type_other")
            await conn.execute(text(
                "ALTER TABLE cases ADD COLUMN crime_type_other VARCHAR(500) NULL"
            ))
    print("Migration 016 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
