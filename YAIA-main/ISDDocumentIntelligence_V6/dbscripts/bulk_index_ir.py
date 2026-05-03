#!/usr/bin/env python3
"""
bulk_index_ir.py — Bulk index IR (Interrogation Report) DOCX/DOC files.

Features:
  - Resume support  : SQLite progress DB — already-indexed files are skipped
  - Duplicate check : backend rejects files already indexed (by filename)
  - Log file        : writes results to dbscripts/logfiles/bulk_index_ir.log
  - Dry run         : --dry-run to preview files without indexing

Usage:
  python bulk_index_ir.py --folder "C:/IR_Files" --username admin --password secret
  python bulk_index_ir.py --folder "C:/IR_Files" --limit 10
  python bulk_index_ir.py --folder "C:/IR_Files" --dry-run
  python bulk_index_ir.py --reset

Requirements: pip install requests
"""

import argparse
import getpass
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

DEFAULT_BACKEND = "http://localhost:8003"
PROGRESS_DB = ".ir_bulk_progress.db"
LOG_DIR = Path(__file__).parent / "logfiles"
LOG_FILE = LOG_DIR / "bulk_index_ir.log"

# Files to skip by name (case-insensitive stem)
SKIP_NAMES = {"report", "reports", "feedback", "attachment", "attachments"}


# --- Progress DB ---

def init_progress_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            file_path TEXT PRIMARY KEY,
            status TEXT DEFAULT 'pending',
            doc_id TEXT,
            error TEXT,
            updated TEXT
        )
    """)
    conn.commit()
    return conn


def add_pending(conn, file_path):
    conn.execute(
        "INSERT OR IGNORE INTO progress (file_path, status, updated) VALUES (?, 'pending', ?)",
        (file_path, datetime.now().isoformat()),
    )


def get_pending(conn):
    return [r[0] for r in conn.execute(
        "SELECT file_path FROM progress WHERE status IN ('pending', 'failed') ORDER BY file_path"
    ).fetchall()]


def mark_done(conn, file_path, doc_id):
    conn.execute(
        "UPDATE progress SET status='done', doc_id=?, updated=? WHERE file_path=?",
        (doc_id, datetime.now().isoformat(), file_path),
    )
    conn.commit()


def mark_failed(conn, file_path, error):
    conn.execute(
        "UPDATE progress SET status='failed', error=?, updated=? WHERE file_path=?",
        (error[:500], datetime.now().isoformat(), file_path),
    )
    conn.commit()


# --- Logging ---

def log(msg: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} | {msg}\n")


# --- Authentication ---

def login(backend_url: str, username: str, password: str) -> str:
    resp = requests.post(
        f"{backend_url}/auth/login",
        json={"username": username, "password": password},
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json().get("token")
    if not token:
        raise RuntimeError("Login failed — no token returned")
    return token


# --- Upload ---

def upload_file(backend_url: str, token: str, file_path: str, filename: str) -> dict:
    with open(file_path, "rb") as fh:
        resp = requests.post(
            f"{backend_url}/docs/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (filename, fh, "application/octet-stream")},
            data={"collection": "IR", "source": "digital"},
            timeout=600,  # 10 min — large/complex IRs can exceed 120s, especially first calls when sentence-transformers model is loading into VRAM
        )
    resp.raise_for_status()
    return resp.json()


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Bulk index IR documents")
    parser.add_argument("--folder", type=str, help="Folder containing IR DOCX/DOC/PDF files")
    parser.add_argument("--backend-url", type=str, default=DEFAULT_BACKEND, help=f"Backend URL (default: {DEFAULT_BACKEND})")
    parser.add_argument("--username", type=str, default="rajibds")
    parser.add_argument("--password", type=str, default=None)
    parser.add_argument("--limit", type=int, default=0, help="Max files to process (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Preview files without indexing")
    parser.add_argument("--reset", action="store_true", help="Delete progress DB and start fresh")
    parser.add_argument("--filter", type=str, default=None,
                        help="Only include files whose name contains ANY of these keywords (comma-separated)")
    parser.add_argument("--progress-db", type=str, default=PROGRESS_DB, help="Progress DB path")
    args = parser.parse_args()

    # --- Reset ---
    if args.reset:
        if os.path.exists(args.progress_db):
            os.remove(args.progress_db)
            print(f"[Reset] Deleted {args.progress_db}")
        else:
            print(f"[Reset] No progress DB found")
        if not args.folder:
            return

    if not args.folder:
        print("ERROR: --folder is required (or --reset to clear progress)")
        sys.exit(1)

    folder = Path(args.folder)
    if not folder.exists():
        print(f"ERROR: Folder not found: {folder}")
        sys.exit(1)

    # --- Collect files ---
    extensions = ["*.docx", "*.DOCX", "*.doc", "*.DOC", "*.pdf", "*.PDF"]
    raw = []
    for ext in extensions:
        raw.extend(folder.rglob(ext))

    # Deduplicate and filter
    filter_keywords = [kw.strip().lower() for kw in args.filter.split(",")] if args.filter else None
    seen = set()
    all_files = []
    skipped = 0

    for p in sorted(raw):
        k = str(p).lower()
        if k in seen:
            continue
        seen.add(k)

        stem = p.stem.lower()
        if any(skip in stem for skip in SKIP_NAMES):
            skipped += 1
            continue

        if filter_keywords:
            if not any(kw in stem for kw in filter_keywords):
                skipped += 1
                continue

        all_files.append(p)

    print(f"Found {len(all_files)} IR files in {folder}")
    if skipped:
        print(f"Skipped {skipped} files (filtered/excluded)")

    if not all_files:
        print("No files to process.")
        return

    # --- Dry run ---
    if args.dry_run:
        for i, f in enumerate(all_files[:50], 1):
            print(f"  {i:4d}. {f.name}")
        if len(all_files) > 50:
            print(f"  ... and {len(all_files) - 50} more")
        print(f"\nTotal: {len(all_files)} files (dry run — no indexing)")
        return

    # --- Password ---
    password = args.password
    if not password:
        password = getpass.getpass("Password: ")

    # --- Login ---
    print(f"Logging in to {args.backend_url}...")
    try:
        token = login(args.backend_url, args.username, password)
        print("Login OK")
    except Exception as e:
        print(f"Login failed: {e}")
        sys.exit(1)

    # --- Init progress DB ---
    conn = init_progress_db(args.progress_db)
    for f in all_files:
        add_pending(conn, str(f))
    conn.commit()

    pending = get_pending(conn)
    if args.limit > 0:
        pending = pending[:args.limit]

    total = len(pending)
    print(f"Processing {total} files...")
    print(f"Log: {LOG_FILE}")
    print()

    ok_count = 0
    fail_count = 0
    start_time = time.time()

    for i, file_path in enumerate(pending, 1):
        fname = Path(file_path).name
        t0 = time.time()

        try:
            result = upload_file(args.backend_url, token, file_path, fname)
            elapsed = time.time() - t0

            if result.get("ok"):
                doc_id = result.get("doc_id", "")
                chunks = result.get("chunks", 0)
                fields = result.get("fields", 0)
                mark_done(conn, file_path, doc_id)
                ok_count += 1
                msg = f"{i}/{total} OK {fname} — {fields} fields, {chunks} chunks, {elapsed:.1f}s"
                print(f"  {msg}")
                log(msg)
            else:
                error = result.get("error", "Unknown error")
                mark_failed(conn, file_path, error)
                fail_count += 1
                msg = f"{i}/{total} FAIL {fname} — {error}"
                print(f"  {msg}")
                log(msg)

        except Exception as e:
            elapsed = time.time() - t0
            error = f"{type(e).__name__}: {e}"
            mark_failed(conn, file_path, error)
            fail_count += 1
            msg = f"{i}/{total} FAIL {fname} — {error} ({elapsed:.1f}s)"
            print(f"  {msg}")
            log(msg)

    conn.close()
    total_time = time.time() - start_time

    print(f"\n{'='*60}")
    print(f"  INDEXING COMPLETE")
    print(f"{'='*60}")
    print(f"  Total      : {total}")
    print(f"  OK         : {ok_count}")
    print(f"  Failed     : {fail_count}")
    print(f"  Elapsed    : {total_time:.1f}s")
    if ok_count > 0:
        print(f"  Avg/file   : {total_time / ok_count:.1f}s")
    print(f"{'='*60}")

    # Write failures
    if fail_count > 0:
        fail_log = Path(__file__).parent / ".ir_bulk_progress_failures.txt"
        with open(fail_log, "w", encoding="utf-8") as f:
            rows = sqlite3.connect(args.progress_db).execute(
                "SELECT file_path, error FROM progress WHERE status='failed'"
            ).fetchall()
            for fp, err in rows:
                f.write(f"{fp} | {err}\n")
        print(f"Failures: {fail_log}")


if __name__ == "__main__":
    main()
