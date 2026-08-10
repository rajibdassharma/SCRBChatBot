#!/usr/bin/env python3
"""Repair the link between derived analysis rows and their accounts.

WHY THIS IS NEEDED
------------------
The development laptop restores a production database dump every
morning. `mysqldump` writes FOREIGN_KEY_CHECKS=0 at the top of every
dump, and the restore DROPS and recreates `all_accounts` rather than
deleting from it. So the ON DELETE CASCADE that normally keeps derived
rows honest never fires, and MySQL never re-validates the constraint
against the new data.

Two things follow, and only the second one actually hurts:

  DEAD ROWS     An account removed upstream leaves transactions, hashes
                and summary rows pointing at a UUID that no longer
                exists. Harmless to the dashboards — every query
                inner-joins to all_accounts, so orphans are already
                invisible — but they accumulate.

  BROKEN LINKS  An account DELETED AND RE-ENTERED gets a new UUID while
                pointing at the same uploaded file. The ledger still
                lists that file as parsed, so parse_statements skips it;
                the transactions still carry the old account id, so the
                new account has none. Statement Coverage then shows it
                as "Not yet parsed" permanently.

The fix for the second case is NOT to re-parse. The rows are fine, only
the pointer is wrong, so it costs one UPDATE instead of re-reading a
PDF.

WHY THIS NO LONGER SCANS statement_transactions
-----------------------------------------------
The first version asked "which transaction rows point at the wrong
account?" directly:

    SELECT COUNT(*) FROM statement_transactions t
    JOIN upload_ledger l ON l.file_path = t.source_file
    WHERE t.account_id <> l.account_id

That joins 10.9M rows to the ledger on a VARCHAR(500) path. It took 27
minutes at 8.2M rows and 25+ at 10.9M, and it ran on every single
invocation — including the ones with nothing to repair. It became the
slowest part of the daily job by an order of magnitude, and it would
have been the slowest part of the nightly production job too.

It was also the wrong question. `statement_transactions.account_id` is
never independent: it is always whatever `upload_ledger.account_id` said
for that file when the rows were written. So the ledger alone knows
which files moved — and the ledger is 17k rows, not 10.9M.

The rewrite therefore works outward from the small tables:

    1. find ledger rows whose file now belongs to a different account
       (17k rows, no fact table involved)
    2. update those ledger rows
    3. update statement_transactions ONLY for the affected file paths,
       through ix_stmt_txn_source

When nothing moved — the overwhelmingly common case — step 3 does not
run at all and the fact table is never opened.

Orphan detection works the same way: `account_statement_summary` has one
row per (account, channel), so an orphaned account shows up there in
53k rows rather than 10.9M, and the fact table is only touched for the
specific account ids found.

ORDER MATTERS
-------------
Re-link first, sweep second. Sweeping first would delete rows that
re-linking was about to rescue.

PURGING IS OPT-IN
-----------------
By default this reports orphans and leaves them. Deleting is the one
irreversible thing here, and a row that looks orphaned today is
recoverable tomorrow if the account is restored upstream.

    python -m analysis.relink              # re-link, report orphans
    python -m analysis.relink --purge      # ...and delete them
    python -m analysis.relink --dry-run    # report only, change nothing
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from sqlalchemy import bindparam, text                  # noqa: E402

from analysis import summary as SUM                     # noqa: E402

#: Paths per UPDATE when the fact table does have to be touched. Small
#: enough that each statement stays index-driven.
CHUNK = 200

#: Normalise a stored path down to its filename. Both columns hold
#: either a relative or an absolute path depending on when the row was
#: written, and older rows use Windows separators.
_BASENAME = "SUBSTRING_INDEX(REPLACE({col}, '\\\\', '/'), '/', -1)"


def _owner_map(path_col: str) -> str:
    """One current owner per uploaded filename.

    MIN(id) rather than an unconstrained join: if two account rows
    reference the same file, an UPDATE ... JOIN would pick one
    arbitrarily and differ between runs. The same rule is used by
    parse_statements and hash_id_photos, so the three cannot disagree
    and undo each other.
    """
    b = _BASENAME.format(col=f"a.{path_col}")
    return f"""
        SELECT {b} AS fname, MIN(a.id) AS account_id, COUNT(*) AS claimants
        FROM all_accounts a
        WHERE a.{path_col} IS NOT NULL AND a.{path_col} <> ''
        GROUP BY {b}
    """


async def _scalar(conn, sql, params=None) -> int:
    return (await conn.execute(text(sql), params or {})).scalar() or 0


async def run(purge: bool, dry_run: bool) -> int:
    from database import engine

    changed_accounts: set[str] = set()
    t0 = time.time()
    async with engine.begin() as conn:
        print("=" * 66)
        print("RE-LINK — point derived rows at the account that owns the file")
        print("=" * 66)

        for label, col in (("statement", "account_statement_path"),
                           ("ID photo", "id_photo_path")):
            shared = await _scalar(conn, f"""
                SELECT COUNT(*) FROM ({_owner_map(col)}) m WHERE m.claimants > 1""")
            if shared:
                print(f"  ! {shared:,} {label} file(s) claimed by more than one "
                      f"account — using the lowest account id for each")

        lb = _BASENAME.format(col="l.file_path")

        # --- 1. which LEDGER rows moved? (17k rows, no fact table) ----
        moved = (await conn.execute(text(f"""
            SELECT l.file_path, l.account_id, m.account_id
            FROM upload_ledger l
            JOIN ({_owner_map('account_statement_path')}) m ON m.fname = {lb}
            WHERE l.file_kind = 'statement'
              AND (l.account_id IS NULL OR l.account_id <> m.account_id)
        """))).all()
        print(f"  ledger rows pointing at the wrong account : {len(moved):,}")

        # --- 2. files whose owner is gone entirely --------------------
        unclaimed = (await conn.execute(text(f"""
            SELECT l.file_path FROM upload_ledger l
            LEFT JOIN ({_owner_map('account_statement_path')}) m ON m.fname = {lb}
            WHERE l.file_kind = 'statement'
              AND m.account_id IS NULL AND l.account_id IS NOT NULL
        """))).all()
        print(f"  ledger rows whose file has no owner       : {len(unclaimed):,}")

        if not dry_run and moved:
            await conn.execute(text(f"""
                UPDATE upload_ledger l
                JOIN ({_owner_map('account_statement_path')}) m ON m.fname = {lb}
                SET l.account_id = m.account_id
                WHERE l.file_kind = 'statement'
                  AND (l.account_id IS NULL OR l.account_id <> m.account_id)
            """))
            # --- 3. ONLY now touch the fact table, and only for the
            # paths that actually moved. ix_stmt_txn_source makes each
            # chunk a lookup rather than a scan. With `moved` empty this
            # block never runs, which is the normal case.
            paths = [r[0] for r in moved]
            for r in moved:
                changed_accounts.update(x for x in (r[1], r[2]) if x)
            for i in range(0, len(paths), CHUNK):
                await conn.execute(
                    text("""
                        UPDATE statement_transactions t
                        JOIN upload_ledger l ON l.file_path = t.source_file
                        SET t.account_id = l.account_id
                        WHERE t.source_file IN :ps
                          AND l.account_id IS NOT NULL
                          AND t.account_id <> l.account_id
                    """).bindparams(bindparam("ps", expanding=True)),
                    {"ps": paths[i:i + CHUNK]})
            print(f"  -> re-pointed transactions for {len(paths):,} file(s)")

        if not dry_run and unclaimed:
            # NULLed, not deleted. The file WAS processed; only its owner
            # is gone. Deleting the row would make the parser read that
            # file again every morning, forever, for nothing.
            await conn.execute(text(f"""
                UPDATE upload_ledger l
                LEFT JOIN ({_owner_map('account_statement_path')}) m ON m.fname = {lb}
                SET l.account_id = NULL
                WHERE l.file_kind = 'statement'
                  AND m.account_id IS NULL AND l.account_id IS NOT NULL
            """))

        # --- 4. ID photo hashes (12k rows — already small) ------------
        hb = _BASENAME.format(col="h.file_path")
        ph = await _scalar(conn, f"""
            SELECT COUNT(*) FROM id_photo_hashes h
            JOIN ({_owner_map('id_photo_path')}) m ON m.fname = {hb}
            WHERE h.account_id <> m.account_id""")
        print(f"  ID photo hashes to re-point               : {ph:,}")
        if ph and not dry_run:
            await conn.execute(text(f"""
                UPDATE id_photo_hashes h
                JOIN ({_owner_map('id_photo_path')}) m ON m.fname = {hb}
                SET h.account_id = m.account_id
                WHERE h.account_id <> m.account_id
            """))

        # --- 5. orphans, detected on the SMALL tables -----------------
        print()
        print("=" * 66)
        print("ORPHANS — rows pointing at an account that is gone")
        print("=" * 66)
        orphan_accounts = [r[0] for r in (await conn.execute(text("""
            SELECT DISTINCT s.account_id FROM account_statement_summary s
            LEFT JOIN all_accounts a ON a.id = s.account_id
            WHERE a.id IS NULL"""))).all()]
        orphan_hashes = await _scalar(conn, """
            SELECT COUNT(*) FROM id_photo_hashes h
            LEFT JOIN all_accounts a ON a.id = h.account_id
            WHERE a.id IS NULL""")
        print(f"  accounts with summary rows but no account : "
              f"{len(orphan_accounts):,}")
        print(f"  orphaned ID photo hashes                  : {orphan_hashes:,}")

        if not orphan_accounts and not orphan_hashes:
            print("  nothing orphaned")
        elif purge and not dry_run:
            for i in range(0, len(orphan_accounts), CHUNK):
                batch = orphan_accounts[i:i + CHUNK]
                for tbl in ("statement_transactions", "account_statement_summary"):
                    await conn.execute(
                        text(f"DELETE FROM {tbl} WHERE account_id IN :ids")
                        .bindparams(bindparam("ids", expanding=True)),
                        {"ids": batch})
            await conn.execute(text("""
                DELETE h FROM id_photo_hashes h
                LEFT JOIN all_accounts a ON a.id = h.account_id
                WHERE a.id IS NULL"""))
            print(f"  purged {len(orphan_accounts):,} account(s) "
                  f"and {orphan_hashes:,} hash(es)")
        else:
            print("  left in place — they are invisible to the dashboards")
            print("  (every query inner-joins all_accounts). Re-run with --purge.")

        # --- 6. the summary must follow the rows ----------------------
        if changed_accounts and not dry_run:
            n = await SUM.refresh(conn, changed_accounts)
            print(f"\n  summary rebuilt for {len(changed_accounts)} affected "
                  f"account(s): {n} rows")

        if dry_run:
            print("\ndry run: nothing was changed.")
        print(f"\n  completed in {time.time() - t0:.1f}s")

    await engine.dispose()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--purge", action="store_true",
                    help="delete rows that are still orphaned after re-linking")
    ap.add_argument("--dry-run", action="store_true",
                    help="report only; change nothing")
    a = ap.parse_args()
    return asyncio.run(run(a.purge, a.dry_run))


if __name__ == "__main__":
    sys.exit(main())
