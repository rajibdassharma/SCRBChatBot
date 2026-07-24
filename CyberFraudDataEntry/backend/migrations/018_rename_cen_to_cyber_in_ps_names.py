"""
Migration 018 -- rename "CEN" to "Cyber" in police_stations.station_name.

Why:
  KSP is dropping the "CEN" acronym (Cyber Economic & Narcotic) in favour
  of "Cyber" in the operator-facing UI (2026-07-24). All PS names are
  read from `police_stations.station_name`; there is no hardcoded "CEN"
  in the frontend. One rewrite of this column propagates everywhere
  (sidebar, dashboards, PDFs, XLSX, chat answers).

  Explicitly preserved:
    - `users.username` (login IDs stay `cen_*` per operator request)
    - `units.name`     (district names -- verified 2026-07-24, no "CEN")
    - Historical dumps in proddata/           (snapshots, don't touch)
    - Migration 001's filename + comments     (historical fact)
    - `cases.facts` free text                 (operator-authored)
    - `chat_messages` historical LLM answers  (audit trail)

Design:
  - REGEXP_REPLACE with \\bCEN\\b (word boundary) so "CEN" as a
    standalone acronym is replaced, but substrings inside other words
    are left alone. Critical: without \\b the update would mangle
    'BANGALORE CENTRAL JAIL' into 'BANGALORE CyberTRAL JAIL', and
    'Central CEN Crime PS' (a real row) would become
    'Cyberral CyberCrime PS'. With \\b:
       'Central CEN Crime PS'  -> 'Central Cyber Crime PS'   ok
       'BANGALORE CENTRAL JAIL' -> unchanged                  ok
       'South East CEN PS'      -> 'South East Cyber PS'      ok
  - MySQL 8+ ships REGEXP_REPLACE (verified against the prod deployment
    context in CLAUDE.md).
  - WHERE station_name REGEXP '\\bCEN\\b' limits the update to rows
    that actually match, so the row count is meaningful telemetry.

Idempotent -- safe to re-run. After the first pass no "CEN" as a
standalone word survives, so subsequent runs update 0 rows.

Usage:
  python -m migrations.018_rename_cen_to_cyber_in_ps_names
"""

import asyncio
from sqlalchemy import text

from database import engine


async def run() -> None:
    print("Running migration 018 -- rename 'CEN' -> 'Cyber' in police_stations.station_name")
    async with engine.begin() as conn:
        before = (await conn.execute(text(
            "SELECT COUNT(*) FROM police_stations WHERE station_name REGEXP '\\\\bCEN\\\\b'"
        ))).scalar_one()
        if before == 0:
            print("  = no station_name contains the standalone acronym 'CEN' -- nothing to do")
        else:
            print(f"  + {before} rows to rewrite")
            result = await conn.execute(text(
                "UPDATE police_stations "
                "SET station_name = REGEXP_REPLACE(station_name, '\\\\bCEN\\\\b', 'Cyber') "
                "WHERE station_name REGEXP '\\\\bCEN\\\\b'"
            ))
            print(f"  + updated {result.rowcount} rows")

        # Confirm CENTRAL-containing rows survived unchanged -- belt and
        # braces for the word-boundary regex.
        central = (await conn.execute(text(
            "SELECT COUNT(*) FROM police_stations "
            "WHERE station_name LIKE '%CENTRAL%' OR station_name LIKE '%Central%'"
        ))).scalar_one()
        print(f"  = rows still containing 'CENTRAL'/'Central' (untouched): {central}")

        # Confirm no standalone 'CEN' remains.
        after = (await conn.execute(text(
            "SELECT COUNT(*) FROM police_stations WHERE station_name REGEXP '\\\\bCEN\\\\b'"
        ))).scalar_one()
        if after != 0:
            raise RuntimeError(
                f"post-check failed: {after} rows still contain standalone 'CEN'"
            )

    print("Migration 018 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
