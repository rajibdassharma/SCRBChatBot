"""
Sweep uploads/ for files that no DB row references.

Why:
  The upload endpoints (POST /api/v1/uploads/photo, /statement) save
  a file BEFORE the parent row is persisted — the client gets a path
  back, fills the rest of the form, then POSTs the row. If the user
  never saves, the file lingers as an orphan. Same story if a
  browser crashes mid-form. Cascade delete on DELETE /all-accounts
  covers the happy path; this script mops up the rest.

What counts as an orphan:
  - File under uploads/photos/ or uploads/statements/
  - Not referenced by ANY of:
      all_accounts.id_photo_path
      all_accounts.account_statement_path
      accused_details.photo_path
  - Older than --min-age-hours (default 24) to avoid deleting a file
    the user is still filling in the form for.

USAGE (on the server, as the cyberfraud user):

    cd /opt/cyberfraud/backend

    # Preview only, no deletion:
    venv/bin/python sweep_orphaned_uploads.py --dry-run

    # Actually delete:
    venv/bin/python sweep_orphaned_uploads.py

    # Custom retention window:
    venv/bin/python sweep_orphaned_uploads.py --min-age-hours 6

Later this can be wired into cron (nightly). Idempotent + safe to
re-run any time.
"""
from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models.accused_detail import AccusedDetail
from models.all_account import AllAccount


UPLOAD_ROOT = Path("uploads")
SUBDIRS = ("photos", "statements")


async def _referenced_paths(db: AsyncSession) -> set[str]:
    """Return the set of every non-null upload path any row references."""
    refs: set[str] = set()

    for col in (AllAccount.id_photo_path, AllAccount.account_statement_path,
                AccusedDetail.photo_path):
        rows = (await db.execute(select(col).where(col.is_not(None)))).scalars().all()
        for p in rows:
            if p:
                refs.add(p.strip())
    return refs


async def sweep(dry_run: bool, min_age_hours: int) -> None:
    if not UPLOAD_ROOT.exists():
        print(f"[sweep] {UPLOAD_ROOT}/ does not exist — nothing to do.")
        return

    now = time.time()
    age_cutoff = now - (min_age_hours * 3600)

    async with async_session() as db:
        referenced = await _referenced_paths(db)

    print(f"[sweep] DB references {len(referenced)} upload path(s).")

    total_scanned = 0
    orphans: list[Path] = []
    too_young: int = 0

    for sub in SUBDIRS:
        d = UPLOAD_ROOT / sub
        if not d.exists():
            continue
        for f in d.iterdir():
            if not f.is_file():
                continue
            total_scanned += 1
            rel = f"uploads/{sub}/{f.name}"
            if rel in referenced:
                continue
            # Not referenced — but is it old enough to be safely called an orphan?
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            if mtime > age_cutoff:
                too_young += 1
                continue
            orphans.append(f)

    print(f"[sweep] scanned {total_scanned} file(s) under {UPLOAD_ROOT}/")
    print(f"[sweep] {len(orphans)} orphan(s) older than {min_age_hours}h")
    print(f"[sweep] {too_young} unreferenced file(s) younger than cutoff — left alone")

    if not orphans:
        return

    if dry_run:
        print()
        print("--dry-run given. Files that WOULD be deleted:")
        for f in orphans[:50]:
            print(f"    {f}")
        if len(orphans) > 50:
            print(f"    ... and {len(orphans) - 50} more")
        return

    deleted, failed = 0, 0
    for f in orphans:
        try:
            f.unlink()
            deleted += 1
        except OSError as e:
            print(f"[sweep] FAILED to delete {f}: {e}")
            failed += 1
    print(f"[sweep] deleted {deleted}, failed {failed}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Only report what would be deleted; make no writes.")
    parser.add_argument("--min-age-hours", type=int, default=24,
                        help="Don't touch files newer than this (default 24).")
    args = parser.parse_args()
    if args.min_age_hours < 1:
        raise SystemExit("--min-age-hours must be at least 1")
    asyncio.run(sweep(args.dry_run, args.min_age_hours))


if __name__ == "__main__":
    main()
