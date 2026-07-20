"""
Delete every test record inserted by `seed_all_accounts_test_data.py`.

Matches by `ncrp_ack_no LIKE 'TEST-%'` — the marker the seed script
stamps on every row. `ncrp_ack_no` is the only free-form column
left; `account_no` (numeric) and `fir_no` (XXXX/XXXX) both gained
format validators so seeded rows in those fields must look real.
Never touches records an operator entered — real NCRP ack numbers
don't carry the TEST- prefix.

Cascading deletes remove the linked `all_account_mule_herders` rows
automatically (ON DELETE CASCADE on the FK).

USAGE (on the server, as the cyberfraud user):

    cd /opt/cyberfraud/backend

    # Preview what would be deleted, no writes:
    venv/bin/python purge_all_accounts_test_data.py --dry-run

    # Actually delete:
    venv/bin/python purge_all_accounts_test_data.py

Idempotent — safe to run twice; a second run finds nothing to delete.
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models.all_account import AllAccount
from models.all_account_mule_herder import AllAccountMuleHerder


TAG_PREFIX = "TEST-"


async def _count_test_rows(db: AsyncSession) -> tuple[int, int]:
    """Return (test_account_count, herder_count) for reporting."""
    n_acc = (await db.execute(
        select(func.count(AllAccount.id))
        .where(AllAccount.ncrp_ack_no.like(f"{TAG_PREFIX}%"))
    )).scalar_one()
    n_herder = (await db.execute(
        select(func.count(AllAccountMuleHerder.id))
        .join(AllAccount, AllAccountMuleHerder.account_id == AllAccount.id)
        .where(AllAccount.ncrp_ack_no.like(f"{TAG_PREFIX}%"))
    )).scalar_one()
    return int(n_acc), int(n_herder)


async def purge(dry_run: bool) -> None:
    async with async_session() as db:
        n_acc, n_herder = await _count_test_rows(db)
        print(f"Test-tagged rows found:")
        print(f"    all_accounts (ncrp_ack_no LIKE '{TAG_PREFIX}%'): {n_acc}")
        print(f"    all_account_mule_herders (cascaded):             {n_herder}")

        if n_acc == 0:
            print("Nothing to delete.")
            return

        if dry_run:
            print()
            print("--dry-run given — no rows deleted. Re-run without --dry-run to purge.")
            return

        # DELETE all_accounts rows with the tag — the FK on
        # all_account_mule_herders is ON DELETE CASCADE, so the child
        # rows drop with the parent in one statement.
        result = await db.execute(
            delete(AllAccount).where(AllAccount.ncrp_ack_no.like(f"{TAG_PREFIX}%"))
        )
        await db.commit()

        after_acc, after_herder = await _count_test_rows(db)
        print()
        print(f"=== Purged {result.rowcount} test all_accounts row(s) ===")
        print(f"    Remaining tagged all_accounts:            {after_acc}")
        print(f"    Remaining tagged all_account_mule_herders: {after_herder}")
        if after_acc == 0 and after_herder == 0:
            print("    ✓ Clean.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Only report what would be deleted; make no writes.")
    args = parser.parse_args()
    asyncio.run(purge(args.dry_run))


if __name__ == "__main__":
    main()
