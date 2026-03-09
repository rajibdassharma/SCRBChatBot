#!/usr/bin/env python3
"""
bulk_index_smac.py — Bulk index SMAC PDF files into ISD Document Intelligence V4.

Features:
  - Resume support  : SQLite progress DB — already-indexed files are skipped automatically
  - Parallel workers: configurable thread pool (default 3)
  - JWT auto-refresh: re-authenticates 1 h before the 24 h token expires
  - Final report    : prints summary + writes a failures log for easy retry

Usage (run from the dbscripts folder):
  python bulk_index_smac.py --folder "C:/SMAC_Files" --case-id 0 --username admin --password secret
  python bulk_index_smac.py --folder "C:/SMAC_Files" --case-id 0 --workers 5
  python bulk_index_smac.py --folder "C:/SMAC_Files" --case-id 0 --reset   # clear progress, start fresh

Requirements: pip install requests   (stdlib only otherwise)
"""

import argparse
import getpass
import os
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import requests

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_BACKEND    = "http://localhost:8001"
DEFAULT_WORKERS    = 3
DEFAULT_COLLECTION = "SMAC"
# Progress DB stored in the same folder as this script
PROGRESS_DB_NAME   = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".smac_bulk_progress.db")
# Refresh token 1 hour before the 24-hour window closes
TOKEN_REFRESH_SECS = 3_600


# ==============================================================================
# Progress Database
# ==============================================================================

def open_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            file_path TEXT PRIMARY KEY,
            status    TEXT    NOT NULL DEFAULT 'pending',
            doc_id    TEXT,
            attempts  INTEGER NOT NULL DEFAULT 0,
            error     TEXT,
            updated   TEXT
        )
    """)
    conn.commit()
    return conn


def register_files(conn: sqlite3.Connection, files: list) -> None:
    """Insert new files as 'pending'; skip files already in the DB."""
    conn.executemany(
        "INSERT OR IGNORE INTO progress (file_path, status, attempts, updated) "
        "VALUES (?, 'pending', 0, ?)",
        [(f, _now()) for f in files],
    )
    conn.commit()


def get_pending(conn: sqlite3.Connection) -> list:
    """Return files that have not yet been successfully indexed."""
    rows = conn.execute(
        "SELECT file_path FROM progress "
        "WHERE status IN ('pending', 'failed') ORDER BY file_path"
    ).fetchall()
    return [r[0] for r in rows]


def mark_done(conn: sqlite3.Connection, file_path: str, doc_id: str) -> None:
    conn.execute(
        "UPDATE progress SET status='done', doc_id=?, error=NULL, updated=? "
        "WHERE file_path=?",
        (doc_id, _now(), file_path),
    )
    conn.commit()


def mark_failed(conn: sqlite3.Connection, file_path: str, error: str) -> None:
    conn.execute(
        "UPDATE progress "
        "SET status='failed', attempts=attempts+1, error=?, updated=? "
        "WHERE file_path=?",
        (error[:500], _now(), file_path),
    )
    conn.commit()


def get_stats(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM progress GROUP BY status"
    ).fetchall()
    return dict(rows)


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


# ==============================================================================
# JWT Token Manager
# ==============================================================================

class TokenManager:
    """Thread-safe JWT manager that auto-refreshes before the token expires."""

    def __init__(self, backend_url: str, username: str, password: str,
                 expire_hours: int = 24):
        self._backend_url  = backend_url.rstrip("/")
        self._username     = username
        self._password     = password
        self._expire_hours = expire_hours
        self._token        = None
        self._expires_at   = datetime.utcnow()
        self._lock         = threading.Lock()
        self._do_login()

    def _do_login(self) -> None:
        resp = requests.post(
            f"{self._backend_url}/auth/login",
            json={"username": self._username, "password": self._password},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok") or not data.get("token"):
            raise RuntimeError(f"Login failed: {data}")
        self._token      = data["token"]
        self._expires_at = datetime.utcnow() + timedelta(hours=self._expire_hours)
        expiry_str = self._expires_at.strftime("%Y-%m-%d %H:%M")
        print(f"[Auth] Logged in as '{self._username}' — token valid until {expiry_str} UTC")

    def get_token(self) -> str:
        with self._lock:
            remaining = (self._expires_at - datetime.utcnow()).total_seconds()
            if remaining < TOKEN_REFRESH_SECS:
                mins = int(remaining / 60)
                print(f"[Auth] Token expires in {mins} min — refreshing now...")
                self._do_login()
            return self._token


# ==============================================================================
# Upload Worker
# ==============================================================================

def upload_file(
    file_path: str,
    backend_url: str,
    token_mgr: TokenManager,
    case_id: int,
    collection: str,
    db_conn: sqlite3.Connection,
    db_lock: threading.Lock,
    counter: dict,
    counter_lock: threading.Lock,
    total: int,
) -> None:
    token = token_mgr.get_token()
    fname = Path(file_path).name
    try:
        with open(file_path, "rb") as fh:
            resp = requests.post(
                f"{backend_url}/docs/upload",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (fname, fh, "application/octet-stream")},
                data={"collection": collection, "case_id": str(case_id)},
                timeout=300,  # 2 minutes per file
            )
        resp.raise_for_status()
        data = resp.json()

        if data.get("ok"):
            with db_lock:
                mark_done(db_conn, file_path, data.get("doc_id", ""))
            with counter_lock:
                counter["done"] += 1
                n = counter["done"] + counter["failed"]
                print(f"  [{n:>6}/{total}] OK    {fname}")
        else:
            err = data.get("error", "unknown error")
            with db_lock:
                mark_failed(db_conn, file_path, err)
            with counter_lock:
                counter["failed"] += 1
                n = counter["done"] + counter["failed"]
                print(f"  [{n:>6}/{total}] FAIL  {fname}  ({err})")

    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        with db_lock:
            mark_failed(db_conn, file_path, err)
        with counter_lock:
            counter["failed"] += 1
            n = counter["done"] + counter["failed"]
            print(f"  [{n:>6}/{total}] ERROR {fname}  ({err})")


# ==============================================================================
# Main
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Bulk index SMAC PDF files into ISD Document Intelligence V4.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Index all PDFs in a folder
  python bulk_index_smac.py --folder "C:/ISD/SMAC Data" --case-id 0 --username admin --password secret

  # Use 5 parallel workers
  python bulk_index_smac.py --folder "C:/ISD/SMAC Data" --workers 5

  # Clear progress and start fresh (will re-index everything)
  python bulk_index_smac.py --folder "C:/ISD/SMAC Data" --reset

  # Resume after interruption (just run the same command again)
  python bulk_index_smac.py --folder "C:/ISD/SMAC Data"
        """,
    )
    parser.add_argument("--folder",
                        required=True,
                        help="Folder containing SMAC PDF files (sub-folders are scanned recursively)")
    parser.add_argument("--case-id",
                        type=int, default=0,
                        help="Case ID to associate documents with (default: 0 = no case)")
    parser.add_argument("--workers",
                        type=int, default=DEFAULT_WORKERS,
                        help=f"Number of parallel upload threads (default: {DEFAULT_WORKERS})")
    parser.add_argument("--backend-url",
                        default=DEFAULT_BACKEND,
                        help=f"Backend base URL (default: {DEFAULT_BACKEND})")
    parser.add_argument("--collection",
                        default=DEFAULT_COLLECTION,
                        help=f"Document collection name (default: {DEFAULT_COLLECTION})")
    parser.add_argument("--username",
                        default="admin",
                        help="Login username (default: admin)")
    parser.add_argument("--password",
                        default="",
                        help="Login password (prompted securely if not provided)")
    parser.add_argument("--progress-db",
                        default=PROGRESS_DB_NAME,
                        help=f"Path to SQLite progress file (default: dbscripts/.smac_bulk_progress.db)")
    parser.add_argument("--reset",
                        action="store_true",
                        help="Delete the existing progress DB and start fresh")
    parser.add_argument("--dry-run",
                        action="store_true",
                        help="List discovered files and exit without uploading anything")

    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"ERROR: Folder not found: {folder}", file=sys.stderr)
        sys.exit(1)

    # ── Collect PDF files (case-insensitive, deduplicated) ─────────────────
    raw = list(folder.rglob("*.pdf")) + list(folder.rglob("*.PDF"))
    seen_lower: set = set()
    all_files: list = []
    for p in sorted(raw):
        k = str(p).lower()
        if k not in seen_lower:
            seen_lower.add(k)
            all_files.append(str(p))

    if not all_files:
        print(f"No PDF files found in: {folder}")
        sys.exit(0)

    # ── Dry-run mode ───────────────────────────────────────────────────────
    if args.dry_run:
        print(f"Dry-run: found {len(all_files)} PDF files in {folder}")
        for f in all_files[:20]:
            print(f"  {f}")
        if len(all_files) > 20:
            print(f"  ... and {len(all_files) - 20} more")
        sys.exit(0)

    # ── Header ─────────────────────────────────────────────────────────────
    print()
    print("=" * 62)
    print("  ISD Document Intelligence — Bulk SMAC Indexer")
    print("=" * 62)
    print(f"  Folder      : {folder}")
    print(f"  Files found : {len(all_files)}")
    print(f"  Backend     : {args.backend_url}")
    print(f"  Collection  : {args.collection}")
    print(f"  Case ID     : {args.case_id}")
    print(f"  Workers     : {args.workers}")
    print(f"  Progress DB : {args.progress_db}")
    print("=" * 62)
    print()

    # ── Progress DB ────────────────────────────────────────────────────────
    if args.reset and os.path.exists(args.progress_db):
        os.remove(args.progress_db)
        print(f"[Progress] Reset: deleted {args.progress_db}")

    db_conn = open_db(args.progress_db)
    register_files(db_conn, all_files)

    pending = get_pending(db_conn)
    stats   = get_stats(db_conn)
    already = stats.get("done", 0)

    print(f"[Progress] Total: {len(all_files)}  |  Already indexed: {already}  |  To process: {len(pending)}")
    print()

    if not pending:
        print("All files already indexed.")
        print("Use --reset to clear progress and re-index everything.")
        db_conn.close()
        sys.exit(0)

    # ── Password ───────────────────────────────────────────────────────────
    password = args.password
    if not password:
        password = getpass.getpass(f"Password for '{args.username}': ")

    # ── Authenticate ───────────────────────────────────────────────────────
    try:
        token_mgr = TokenManager(
            backend_url  = args.backend_url,
            username     = args.username,
            password     = password,
        )
    except Exception as exc:
        print(f"ERROR: Authentication failed: {exc}", file=sys.stderr)
        db_conn.close()
        sys.exit(1)

    # ── Verify backend health ──────────────────────────────────────────────
    try:
        h = requests.get(f"{args.backend_url}/health", timeout=5)
        h.raise_for_status()
    except Exception as exc:
        print(f"ERROR: Backend not reachable at {args.backend_url}: {exc}", file=sys.stderr)
        db_conn.close()
        sys.exit(1)

    # ── Run uploads ────────────────────────────────────────────────────────
    db_lock      = threading.Lock()
    counter_lock = threading.Lock()
    counter      = {"done": 0, "failed": 0}
    start_time   = time.time()
    total        = len(pending)

    print(f"[Start] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} — "
          f"uploading {total} files with {args.workers} workers\n")

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                upload_file,
                fp,
                args.backend_url,
                token_mgr,
                args.case_id,
                args.collection,
                db_conn,
                db_lock,
                counter,
                counter_lock,
                total,
            ): fp
            for fp in pending
        }
        for _ in as_completed(futures):
            pass  # progress printed inside upload_file

    # ── Summary ────────────────────────────────────────────────────────────
    elapsed     = time.time() - start_time
    final_stats = get_stats(db_conn)
    n_done      = final_stats.get("done", 0)
    n_failed    = final_stats.get("failed", 0)
    avg_sec     = elapsed / total if total else 0

    print()
    print("=" * 62)
    print("  BULK INDEX COMPLETE")
    print("=" * 62)
    hrs, rem = divmod(int(elapsed), 3600)
    mns, sec = divmod(rem, 60)
    print(f"  Elapsed    : {hrs}h {mns}m {sec}s")
    print(f"  Total files: {len(all_files)}")
    print(f"  Indexed    : {n_done}")
    print(f"  Failed     : {n_failed}")
    print(f"  Avg / file : {avg_sec:.1f} s")
    print("=" * 62)

    if n_failed:
        fail_rows = db_conn.execute(
            "SELECT file_path, error FROM progress "
            "WHERE status='failed' ORDER BY file_path"
        ).fetchall()

        print(f"\nFailed files ({n_failed}):")
        for fp, err in fail_rows:
            print(f"  {Path(fp).name}  —  {err}")

        # Write failures log next to the progress DB
        fail_log = args.progress_db.replace(".db", "_failures.txt")
        with open(fail_log, "w", encoding="utf-8") as fout:
            fout.write(f"# Failed files — {datetime.now().isoformat()}\n")
            for fp, err in fail_rows:
                fout.write(f"{fp}\t{err}\n")
        print(f"\nFailures saved to: {fail_log}")
        print("Run the same command again to retry only failed files (they are retried automatically).")

    db_conn.close()
    sys.exit(0 if n_failed == 0 else 1)


if __name__ == "__main__":
    main()
