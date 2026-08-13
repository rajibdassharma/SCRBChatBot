#!/usr/bin/env python3
"""Export analysis RESULTS for the production server.

    python -m analysis.export_for_prod

Writes ``proddata/analysis_YYYY-MM-DD.sql.gz`` (~6 MB) for
``deploy/import-analysis.sh`` to load on the server.

WHY PYTHON AND NOT A SHELL SCRIPT
---------------------------------
This half runs on the DEVELOPMENT LAPTOP, which is Windows; only the
import runs on Ubuntu. A .sh export would need git-bash, while every
other command in this workflow is ``python -m analysis.<something>``.

More importantly, the obvious shell form is unsafe here:

    mysqldump ... | gzip > out.sql.gz

PowerShell's ``>`` encodes as UTF-16 and truncates binary streams, so
that pipeline yields a corrupt archive outside git-bash -- and a corrupt
archive is only discovered on the server, at import time. Passing
``--result-file`` makes mysqldump write the bytes itself, with no shell
in the path at all.

WHAT MOVES, AND WHAT DOES NOT
-----------------------------
    account_statement_summary    27 MB   Money Trail
    upload_ledger                30 MB   Statement Coverage
    id_photo_hashes              18 MB   Duplicate IDs
    mule_account_link             1 MB   Mule Network
                                ------
                                 76 MB   -> ~6 MB gzipped

    statement_transactions   12,753 MB   STAYS HERE

The fact table is excluded because no API route reads it: routes_dashboard
imports StatementTransaction but never queries it, and every dashboard
reads account_statement_summary instead. Shipping it would put 12.5 GB on
a 50 GB production disk already holding 15 GB of uploads and their backup
tarball.

Interim arrangement until production storage grows. After that,
deploy/install-analysis.sh moves the whole job onto the server.
"""
from __future__ import annotations

import asyncio
import gzip
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
REPO = os.path.dirname(BACKEND)
OUT_DIR = os.path.join(REPO, "proddata")

if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from sqlalchemy import text                            # noqa: E402
from config import settings                            # noqa: E402
from database import engine                            # noqa: E402

#: Exactly the tables the dashboards read. Keep in sync with
#: deploy/import-analysis.sh and the exclusion list in backup-db.sh.
TABLES = [
    "account_statement_summary",
    "upload_ledger",
    "id_photo_hashes",
    "mule_account_link",
    "crypto_txn",
]

#: IST. The filename must agree with the backup filenames it will sit
#: beside, and those are stamped Asia/Kolkata (see backup-db.sh).
IST = timezone(timedelta(hours=5, minutes=30))


def _find_mysqldump() -> str:
    """Locate mysqldump, including the default Windows install path.

    MySQL's Windows installer does not add its bin/ to PATH, so a plain
    shutil.which() fails on exactly the machine this script targets.
    """
    found = shutil.which("mysqldump")
    if found:
        return found
    import glob
    for pat in (r"C:\Program Files\MySQL\MySQL Server *\bin\mysqldump.exe",
                r"C:\Program Files (x86)\MySQL\MySQL Server *\bin\mysqldump.exe"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]          # highest version
    raise SystemExit(
        "ERROR: mysqldump not found on PATH.\n"
        "       Install MySQL client tools, or add its bin/ to PATH."
    )


async def _preflight() -> tuple[dict[str, int], bool]:
    """Row counts, plus whether the summary is older than the parse.

    Both checks exist to stop a bad export reaching the server, where
    its symptoms would be much harder to read.
    """
    counts: dict[str, int] = {}
    async with engine.begin() as c:
        for t in TABLES:
            counts[t] = int((await c.execute(
                text(f"SELECT COUNT(*) FROM `{t}`"))).scalar() or 0)
        # file_kind='statement' is load-bearing.
        #
        # Without it this compares against the whole ledger, and step 8
        # of the pipeline writes PHOTO rows minutes after parsing ends
        # — so the guard fired on every successful run. Measured
        # 2026-08-10: statements finished 18:08:18, the summary was
        # rebuilt at 18:08:18, photos were hashed at 18:15:18, and the
        # export refused to run.
        #
        # A guard that fails on the healthy case is worse than no guard:
        # it trains you to answer "y" without reading it, and then it is
        # silent the day it matters.
        stale = bool((await c.execute(text("""
            SELECT (SELECT MAX(processed_at) FROM upload_ledger
                     WHERE file_kind = 'statement')
                 > (SELECT MAX(updated_at) FROM account_statement_summary)
        """))).scalar())
    await engine.dispose()
    return counts, stale


def main() -> int:
    print("=" * 62)
    print("  Export analysis results for production")
    print(f"  Source : {settings.DB_NAME} @ {settings.DB_HOST}:{settings.DB_PORT}")
    print("=" * 62)

    try:
        counts, stale = asyncio.run(_preflight())
    except Exception as exc:                            # noqa: BLE001
        print(f"\nERROR: cannot read the analysis tables -- {exc}")
        print("       Run `python -m analysis.daily` first.")
        return 1

    print("\n=== Row counts ===")
    for t, n in counts.items():
        print(f"  {t:<30}{n:>12,}")

    # An export of zero rows would BLANK the production dashboards on
    # import. Refuse rather than ship it.
    empty = [t for t, n in counts.items() if n == 0]
    if empty:
        print(f"\nERROR: empty table(s): {', '.join(empty)}")
        print("       Exporting would blank the production dashboards.")
        return 2

    # The summary is a cache. If parsing ran but the summary was not
    # rebuilt, this export ships yesterday's totals under today's name --
    # the one failure mode that looks entirely normal on arrival.
    if stale:
        print("\n  WARNING: files were parsed AFTER the summary was rebuilt.")
        print("  The export would carry stale totals. Run this first:")
        print("      python -m analysis.daily --skip-parse --skip-relink")
        # try/except rather than isatty(): under git-bash on Windows
        # isatty() reports True even with stdin redirected, so the
        # isatty check alone raised EOFError instead of declining.
        # Either way an unanswered prompt must mean NO -- the default
        # for a guard has to be the safe side.
        try:
            answer = input("\n  Continue anyway? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer not in ("y", "yes"):
            print("  aborted -- rebuild the summary, then re-run.")
            return 3

    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now(IST).strftime("%Y-%m-%d")
    outfile = os.path.join(OUT_DIR, f"analysis_{stamp}.sql.gz")

    # --no-create-info      production's schema is authoritative; it comes
    #                       from migrations 019-023, not from this laptop
    # --skip-add-drop-table the import does its own atomic swap
    # --complete-insert     named columns, so a column added on one side
    #                       cannot silently shift values on the other
    # --skip-add-locks      LOCK TABLES names the real table while the
    #                       import redirects inserts to staging -> MySQL
    #                       error 1100. Found by rehearsing the import.
    argv = [
        _find_mysqldump(),
        f"--host={settings.DB_HOST}", f"--port={settings.DB_PORT}",
        f"--user={settings.DB_USER}",
        "--single-transaction", "--quick", "--no-create-info",
        "--skip-add-drop-table", "--complete-insert", "--skip-add-locks",
        "--hex-blob",
    ]

    print(f"\n=== Dumping {len(TABLES)} tables ===")
    tmp = tempfile.NamedTemporaryFile(suffix=".sql", delete=False)
    tmp.close()
    try:
        # --result-file, not a shell redirect: mysqldump writes the bytes
        # itself. See the module docstring.
        env = dict(os.environ, MYSQL_PWD=settings.DB_PASSWORD)
        r = subprocess.run(
            argv + [f"--result-file={tmp.name}", settings.DB_NAME] + TABLES,
            env=env, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"ERROR: mysqldump exited {r.returncode}")
            print((r.stderr or "").strip()[:800])
            return 4

        raw = os.path.getsize(tmp.name)
        if raw < 10240:
            print(f"ERROR: dump is only {raw} bytes -- it did not work")
            return 4

        with open(tmp.name, "rb") as src, gzip.open(outfile, "wb", 9) as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    size = os.path.getsize(outfile)

    # Retain only the newest, matching backup-db.sh / backup-uploads.sh.
    pruned = 0
    for f in os.listdir(OUT_DIR):
        if (f.startswith("analysis_") and f.endswith(".sql.gz")
                and f != os.path.basename(outfile)):
            os.unlink(os.path.join(OUT_DIR, f))
            pruned += 1

    name = os.path.basename(outfile)
    print("\n" + "=" * 62)
    print(f"  Wrote  {outfile}")
    print(f"  Size   {size/1024/1024:.1f} MB  (from {raw/1024/1024:.1f} MB raw)")
    print(f"  Pruned {pruned} older export(s)")
    print("\n  Ship it:")
    print(f"    scp proddata/{name} cyberfraud@PROD:/opt/cyberfraud/backups/")
    print(f"    ssh PROD \"sudo /opt/cyberfraud/deploy/import-analysis.sh \\")
    print(f"              /opt/cyberfraud/backups/{name}\"")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
