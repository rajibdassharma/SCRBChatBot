"""
Delete every row in mule_reports + its six transaction child tables.

Called for the 2026-07-30 decision that PSes should NOT have been
using the NCRP Data entry option at all -- the surviving rows are
non-authoritative and must be removed. Post-purge the module gate
(`visibleForPsNames: ['CID', 'Test PS']` in modules.ts) prevents
re-entry from non-CID PSes.

Tables cleared (children first so we get row counts per table, even
though InnoDB CASCADE would do the same in one DELETE FROM
mule_reports):
    money_transfers
    other_transactions
    transactions_on_hold
    others_less_than_500
    aeps_transactions
    atm_withdrawals
    mule_reports

USAGE (local dev + on the server, as the cyberfraud user):

    cd /opt/cyberfraud/backend      # or your local backend/ dir

    # Preview counts, no writes:
    venv/bin/python purge_ncrp_data.py --dry-run

    # Actually delete (asks for confirmation unless --yes given):
    venv/bin/python purge_ncrp_data.py
    venv/bin/python purge_ncrp_data.py --yes    # skip prompt

Idempotent -- a second run finds zero rows and reports "already clean".
No pre-purge backup is taken; the nightly mysqldump is the rollback
path (per user's 2026-07-30 decision).
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session


# Ordered children -> parent so we can log a row count per table
# even though ON DELETE CASCADE would do the same in one shot.
TABLES_IN_ORDER = [
    "money_transfers",
    "other_transactions",
    "transactions_on_hold",
    "others_less_than_500",
    "aeps_transactions",
    "atm_withdrawals",
    "mule_reports",
]


async def _counts(db: AsyncSession) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in TABLES_IN_ORDER:
        r = await db.execute(text(f"SELECT COUNT(*) FROM {t}"))
        out[t] = int(r.scalar() or 0)
    return out


def _print_counts(label: str, counts: dict[str, int]) -> None:
    print(f"\n=== {label} ===")
    for t, n in counts.items():
        print(f"    {t:<26} {n:>10} rows")
    print(f"    {'TOTAL':<26} {sum(counts.values()):>10} rows")


async def purge(dry_run: bool, skip_prompt: bool) -> None:
    async with async_session() as db:
        before = await _counts(db)
        _print_counts("BEFORE", before)

        total = sum(before.values())
        if total == 0:
            print("\nAlready clean -- nothing to delete.")
            return

        if dry_run:
            print("\n--dry-run given, no writes performed.")
            return

        if not skip_prompt:
            print(
                f"\nAbout to DELETE {total} rows across {len(TABLES_IN_ORDER)} tables. "
                "This is IRREVERSIBLE (no pre-purge dump)."
            )
            resp = input("Type 'DELETE' to proceed: ").strip()
            if resp != "DELETE":
                print("Aborted -- no rows changed.")
                return

        print("\n=== DELETING ===")
        for t in TABLES_IN_ORDER:
            r = await db.execute(text(f"DELETE FROM {t}"))
            print(f"    {t:<26} deleted {r.rowcount:>10} row(s)")
        await db.commit()

        after = await _counts(db)
        _print_counts("AFTER", after)

        remaining = sum(after.values())
        if remaining == 0:
            print("\n[OK] All seven tables are empty.")
        else:
            print(f"\n[WARN] {remaining} row(s) remain -- investigate.")
            sys.exit(1)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Purge every row from mule_reports + its 6 child transaction tables.",
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Only print row counts; make no writes.")
    p.add_argument("--yes", action="store_true",
                   help="Skip the interactive 'type DELETE to confirm' prompt.")
    args = p.parse_args()
    asyncio.run(purge(dry_run=args.dry_run, skip_prompt=args.yes))


if __name__ == "__main__":
    main()
