#!/usr/bin/env python3
"""One command to run after restoring the nightly backup.

    python -m analysis.daily

Does, in this order and stopping at the first failure:

    1. migrations 019-023      idempotent; only act if a restore
                               removed the analysis tables
    2. relink                  re-point derived rows at the account
                               that currently owns each file
    3. parse_statements        incremental — only files the ledger has
                               not already seen
    4. hash_id_photos          full re-hash (~2 min; not worth making
                               incremental at 1 ms/image)
    5. build_links             rebuild the mule -> mule network (~30s)
    6. summary --check         verify the dashboard cache still matches
                               the rows underneath it

WHY THE ORDER IS FIXED
----------------------
Migrations before everything, because the rest assumes the tables
exist. Relink before parsing, because parsing writes summary rows and
there is no sense computing them from links that are about to move.
The check last, because it is the only step that can tell you the
previous four left the data consistent.

WHY RELINK IS NOT OPTIONAL HERE
-------------------------------
The restore DROPS and recreates all_accounts with FOREIGN_KEY_CHECKS=0,
so ON DELETE CASCADE never fires. An account deleted and re-entered
upstream keeps its uploaded file but gets a new id, and without a
relink its statement stays attached to the id that no longer exists —
the parser skips the file as already done, and the account shows as
"Not yet parsed" on Statement Coverage forever.

EXIT CODE
---------
Non-zero if any step fails, so this is safe to put behind a scheduler
later. The check failing is a real failure: it means the dashboard is
reporting numbers no query can reproduce.

    --skip-parse    everything except the statement parse (quick sanity
                    pass when no new files have landed)
    --skip-relink   skip the relink step. Correct on PRODUCTION, which
                    never restores and therefore has no broken links to
                    repair.
    --purge         let relink delete rows that are still orphaned
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)

#: (label, argv-after-python). Kept as data so the sequence is
#: readable at a glance and so --skip-parse is a filter, not a branch.
STEPS = [
    ("migration 019 — analysis tables",
     ["-m", "migrations.019_add_upload_analysis_tables"]),
    ("migration 020 — statement summary",
     ["-m", "migrations.020_account_statement_summary"]),
    ("migration 021 — mule account links",
     ["-m", "migrations.021_mule_account_links"]),
    ("migration 022 — per-row chain verdict",
     ["-m", "migrations.022_statement_chain_ok"]),
    ("migration 023 — untested totals on the summary",
     ["-m", "migrations.023_summary_untested_totals"]),
    ("migration 024 — crypto transactions",
     ["-m", "migrations.024_crypto_transactions"]),
    # 025 creates the IFSC directory table but never fills it --
    # load_ifsc.py does that, by hand, from a CSV carried to the box.
    # The migration is here so a fresh server has somewhere to put it.
    ("migration 025 — IFSC branch directory",
     ["-m", "migrations.025_ifsc_branch"]),
    ("migration 026 — widen summary money columns",
     ["-m", "migrations.026_widen_summary_money"]),
    ("relink — repair account links after the restore",
     ["-m", "analysis.relink"]),
    ("parse statements — incremental",
     [os.path.join("analysis", "parse_statements.py")]),
    ("hash ID photos",
     [os.path.join("analysis", "hash_id_photos.py")]),
    # After parsing, not before: links are found by matching
    # counterparty numbers in freshly parsed rows against known mule
    # accounts, so running this first would miss everything new.
    ("rebuild mule network links",
     ["-m", "analysis.build_links"]),
    # After parsing, for the same reason as the links rebuild: it reads
    # freshly parsed narrations. --recent rather than a full rebuild,
    # which rescans 21M rows and takes ~7 minutes on its own.
    #
    # NOTE: --recent only ADDS rows. After changing a pattern in
    # analysis/parsers/crypto.py, run a full `python -m
    # analysis.build_crypto` by hand — otherwise rows matched by the
    # withdrawn rule stay on screen, indistinguishable from current ones.
    ("find crypto transactions — incremental",
     ["-m", "analysis.build_crypto", "--recent", "48"]),
    ("verify summary cache",
     ["-m", "analysis.summary", "--check"]),
]


def _ledger_and_facts_agree() -> bool:
    """Refuse to run when the ledger claims work the fact table cannot show.

    A machine restored from a dump gets `upload_ledger` — every file
    marked parsed — but NOT `statement_transactions`, which backup-db.sh
    excludes as rebuildable. That combination is never valid and it fails
    DESTRUCTIVELY rather than loudly:

      * parse_statements skips every file, because the ledger says done
      * build_links then does DELETE FROM mule_account_link and rebuilds
        from an empty fact table, wiping the links that came in the dump
      * summary --check compares the restored summaries against nothing

    Cost the 2026-08-18 re-seed. Cheap to detect, so detect it.
    """
    try:
        import sqlalchemy as sa
        sys.path.insert(0, BACKEND)
        from config import settings
        from urllib.parse import quote_plus
        url = (f"mysql+pymysql://{settings.DB_USER}:{quote_plus(settings.DB_PASSWORD)}"
               f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
        try:
            eng = sa.create_engine(url)
        except Exception:
            url = url.replace("pymysql", "mysqldb")
            eng = sa.create_engine(url)
        with eng.connect() as c:
            ledger = c.execute(sa.text("SELECT COUNT(*) FROM upload_ledger")).scalar() or 0
            facts = c.execute(sa.text("SELECT COUNT(*) FROM statement_transactions")).scalar() or 0
        eng.dispose()
    except Exception as exc:                       # table missing on a first run
        print(f"[daily] ledger/fact consistency check skipped ({exc.__class__.__name__})")
        return True

    if ledger > 0 and facts == 0:
        print("=" * 70)
        print("REFUSING TO RUN — the ledger and the fact table disagree")
        print("=" * 70)
        print(f"  upload_ledger          {ledger:,} rows")
        print(f"  statement_transactions {facts:,} rows")
        print()
        print("  The ledger says every file has been parsed; the fact table")
        print("  says nothing has. That is what a restore looks like, because")
        print("  backup-db.sh excludes statement_transactions as rebuildable.")
        print()
        print("  Running anyway would SKIP every file (the ledger says done),")
        print("  then DELETE FROM mule_account_link and rebuild it from an")
        print("  empty table — destroying the links that came in the dump.")
        print()
        print("  If you want the fact table on this machine, reparse from")
        print("  scratch — hours, and it needs the uploaded files present:")
        print("      mysql ... -e 'TRUNCATE upload_ledger;'")
        print("      python -m analysis.daily")
        print()
        print("  If you only want the app to work, you need neither: no API")
        print("  route reads statement_transactions. Do nothing.")
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-parse", action="store_true",
                    help="skip the statement parse (the slow step)")
    ap.add_argument("--purge", action="store_true",
                    help="let relink delete rows that remain orphaned")
    ap.add_argument("--skip-relink", action="store_true",
                    help="skip the relink step (production: nothing restores "
                         "there, so there are no broken links to repair)")
    args = ap.parse_args()

    steps = list(STEPS)
    if args.purge:
        steps = [(l, a + ["--purge"] if "analysis.relink" in a else a)
                 for l, a in steps]
    if args.skip_parse:
        steps = [(l, a) for l, a in steps if "parse_statements" not in str(a)]
    if args.skip_relink:
        # relink repairs foreign keys broken by a RESTORE. Production
        # never restores, so running it there is pure cost — and it is
        # the one step whose cost grows with the fact table.
        steps = [(l, a) for l, a in steps if "analysis.relink" not in str(a)]

    if not _ledger_and_facts_agree():
        return 2

    print("=" * 70)
    print("DAILY POST-RESTORE RUN")
    print("=" * 70)
    t_all = time.time()
    for i, (label, argv) in enumerate(steps, 1):
        print(f"\n[{i}/{len(steps)}] {label}")
        print("-" * 70, flush=True)
        t0 = time.time()
        # cwd=BACKEND so `-m migrations...` and the relative script
        # paths resolve the same way they do when run by hand.
        r = subprocess.run([sys.executable] + argv, cwd=BACKEND)
        el = time.time() - t0
        if r.returncode != 0:
            print(f"\nFAILED at step {i} ({label}) after {el:.0f}s "
                  f"— exit {r.returncode}")
            print("Nothing after this step has run. Fix the cause and "
                  "re-run; every step is safe to repeat.")
            return r.returncode
        print(f"-- ok ({el:.0f}s)")

    print("\n" + "=" * 70)
    print(f"ALL STEPS OK in {time.time() - t_all:.0f}s")
    print("Dashboards are current: Money Trail, Statement Coverage, "
          "Duplicate IDs.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
