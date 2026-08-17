#!/usr/bin/env python3
"""Load the IFSC branch directory into ifsc_branch.

    python -m analysis.load_ifsc proddata/IFSC.csv
    python -m analysis.load_ifsc proddata/IFSC.csv --source v2.0.61

Source: the open Razorpay IFSC dataset, IFSC.csv from
https://github.com/razorpay/ifsc/releases (~183,000 branches, 35 MB).

RUN THIS BY HAND, NOT NIGHTLY
The directory changes when banks merge or open branches -- a few times
a year, not daily. Putting it in analysis.daily would download or re-read
35 MB every night to change almost nothing, and production has no route
to the internet to fetch it with anyway. The CSV is carried to the
server once by scp; after that the table is ordinary backed-up data and
reaches the dev laptop through the normal restore.

REPLACE, NOT MERGE
Each load truncates and reloads. A merge would leave rows from an
earlier release that the current one has dropped -- a closed branch
would resolve forever -- and there is no way to tell those apart from
current rows afterwards.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from sqlalchemy import text                                # noqa: E402

#: Rows per INSERT. 183k rows in batches of 2,000 is ~90 round trips.
BATCH = 2000

IFSC_RE = re.compile(r'^[A-Z]{4}0[A-Z0-9]{6}$')


def _clip(v, n):
    v = (v or '').strip()
    return v[:n] if v else None


async def load(conn, path: str, source: str | None) -> dict:
    stats = {"read": 0, "loaded": 0, "malformed": 0, "dupes": 0}
    seen: set[str] = set()
    pending: list[dict] = []

    await conn.execute(text("TRUNCATE TABLE ifsc_branch"))

    with open(path, encoding='utf-8', errors='replace', newline='') as f:
        for row in csv.DictReader(f):
            stats["read"] += 1
            code = (row.get('IFSC') or '').strip().upper()
            if not IFSC_RE.match(code):
                # Kept out rather than stored: a code that cannot appear
                # on an account row can never resolve one, and storing it
                # would inflate the row count into a false sense of
                # coverage.
                stats["malformed"] += 1
                continue
            if code in seen:
                stats["dupes"] += 1
                continue
            seen.add(code)
            pending.append({
                "ifsc": code,
                "bank": _clip(row.get('BANK'), 200),
                "branch": _clip(row.get('BRANCH'), 200),
                "district": _clip(row.get('DISTRICT'), 100),
                "state": _clip(row.get('STATE'), 100),
                "city": _clip(row.get('CITY'), 100),
                "centre": _clip(row.get('CENTRE'), 100),
                "address": _clip(row.get('ADDRESS'), 500),
                "source": _clip(source, 50),
            })
            if len(pending) >= BATCH:
                await _flush(conn, pending)
                stats["loaded"] += len(pending)
                pending = []

    if pending:
        await _flush(conn, pending)
        stats["loaded"] += len(pending)
    return stats


async def _flush(conn, rows: list[dict]) -> None:
    await conn.execute(text("""
        INSERT INTO ifsc_branch
            (ifsc, bank, branch, district, state, city, centre, address, source)
        VALUES (:ifsc, :bank, :branch, :district, :state, :city, :centre,
                :address, :source)
    """), rows)


async def _main(path: str, source: str | None) -> int:
    from database import engine

    if not os.path.exists(path):
        print(f"no such file: {path}")
        return 1

    print(f"loading {path}")
    async with engine.begin() as conn:
        st = await load(conn, path, source)
        # Coverage against the accounts that actually need resolving --
        # the only number that says whether this load was any use.
        cov = (await conn.execute(text("""
            SELECT COUNT(*) FROM all_accounts a
            JOIN ifsc_branch b ON b.ifsc = UPPER(TRIM(a.ifsc_code))
            WHERE COALESCE(TRIM(a.branch_district),'') = ''"""))).scalar()
        need = (await conn.execute(text("""
            SELECT COUNT(*) FROM all_accounts
            WHERE COALESCE(TRIM(ifsc_code),'') <> ''
              AND COALESCE(TRIM(branch_district),'') = ''"""))).scalar()
    await engine.dispose()

    print("=" * 58)
    print(f"  rows read      : {st['read']:,}")
    print(f"  loaded         : {st['loaded']:,}")
    print(f"  malformed IFSC : {st['malformed']:,}")
    print(f"  duplicate codes: {st['dupes']:,}")
    print(f"\n  accounts needing a district : {need or 0:,}")
    print(f"  now resolvable              : {cov or 0:,}"
          f"  ({100 * (cov or 0) / max(1, need or 1):.1f}%)")
    print("=" * 58)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv_path", help="path to IFSC.csv")
    ap.add_argument("--source", default=None,
                    help="dataset release tag, e.g. v2.0.61")
    a = ap.parse_args()
    sys.exit(asyncio.run(_main(a.csv_path, a.source)))
