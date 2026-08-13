#!/usr/bin/env python3
"""How far the statement backfill has got. Read-only, safe to run at
any time — including while parse_statements.py is running.

    python -m analysis.progress            # one snapshot
    python -m analysis.progress --watch    # refresh until it stops moving

Reads the ledger rather than the job's console output. That is
deliberate: the parser's stdout goes through a pipe when it runs in the
background, and a pipe buffers, so the log file can sit empty for
minutes while real work is happening. The ledger is committed per
flush, so it is always current and never lies about what is done.

WHY --watch REPORTS A RATE INSTEAD OF A FIXED s/FILE
The corpus is not homogeneous. Ordinary statements parse in about a
second; the long ones deferred to the serial pass take ~20s each. An
ETA built from a corpus-wide average therefore under-predicts the tail
by an order of magnitude, which is exactly how estimates given during
earlier runs came out wrong. The rate below is measured from what THIS
watch session has seen settle, so it tracks whichever pass is currently
running.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
STMT_DIR = os.path.join(BACKEND, "uploads", "statements")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from sqlalchemy import text                            # noqa: E402

PARSER_VERSION = "stmt-v1"

#: Terminal states. A file in any of these will not be attempted again
#: on the next run, so it counts as settled. 'deferred' is deliberately
#: NOT here: it is the interim state of a file handed to the serial
#: pass, and a file left in it never produced a result.
SETTLED = ("ok", "unverified", "scanned", "failed")


def _bar(frac: float, width: int = 40) -> str:
    n = max(0, min(width, int(round(frac * width))))
    return "[" + "#" * n + "-" * (width - n) + "]"


def _fmt(seconds: float) -> str:
    m, s = divmod(int(max(0, seconds)), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


def _on_disk() -> int:
    try:
        return len([f for f in os.listdir(STMT_DIR)
                    if f.lower().endswith((".pdf", ".xls", ".xlsx"))])
    except OSError:
        return 0


async def _snapshot(c) -> dict:
    rows = (await c.execute(text(
        "SELECT status, COUNT(*) FROM upload_ledger "
        "WHERE file_kind='statement' GROUP BY status"))).all()
    settled = (await c.execute(text(
        "SELECT COUNT(*) FROM upload_ledger "
        "WHERE file_kind='statement' AND parser_version = :pv "
        f"AND status IN {SETTLED}"), {"pv": PARSER_VERSION})).scalar() or 0
    txns = (await c.execute(text(
        "SELECT COUNT(*) FROM statement_transactions"))).scalar() or 0
    accts = (await c.execute(text(
        "SELECT COUNT(DISTINCT account_id) FROM account_statement_summary"
    ))).scalar() or 0
    size = (await c.execute(text("""
        SELECT ROUND(SUM(data_length+index_length)/1024/1024/1024, 2)
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME IN ('statement_transactions',
                             'account_statement_summary','upload_ledger')
    """))).scalar() or 0
    return {"rows": rows, "settled": int(settled), "txns": int(txns),
            "accts": int(accts), "size": float(size or 0)}


def _report(snap: dict, on_disk: int, rate: str | None) -> None:
    from analysis import runtime as R

    settled = snap["settled"]
    frac = settled / max(1, on_disk)
    print(f"{_bar(frac)} {100 * frac:5.1f}%")
    print(f"  settled       {settled:>8,} of {on_disk:,} files")
    print(f"  remaining     {on_disk - settled:>8,}")
    for st, n in sorted(snap["rows"], key=lambda kv: -kv[1]):
        # 'deferred' left over after a run means the serial pass never
        # returned a result for that file -- a timeout or a dead worker.
        # It is not settled and the next run will retry it.
        flag = "  <- not settled, will retry" if st == "deferred" else ""
        print(f"      {st:<12}{n:>8,}{flag}")
    print(f"  transactions  {snap['txns']:>8,}")
    print(f"  accounts      {snap['accts']:>8,} with a statement summary")
    print(f"  table size    {snap['size']:>8.2f} GB")
    print(f"  memory        {R.gb(R.available_bytes()):>8.1f} GB free")
    if rate:
        print(f"  rate          {rate}")


async def go(watch: bool, every: float) -> None:
    from database import engine

    first_n = first_t = None
    try:
        while True:
            on_disk = _on_disk()
            async with engine.begin() as c:
                snap = await _snapshot(c)
            now = time.time()
            if first_n is None:
                first_n, first_t = snap["settled"], now

            rate = None
            dn, dt = snap["settled"] - first_n, now - first_t
            if dn > 0 and dt > 30:
                per = dt / dn
                left = (on_disk - snap["settled"]) * per
                rate = f"{per:.1f}s/file now . ~{_fmt(left)} left"
            elif watch:
                rate = "measuring…"

            _report(snap, on_disk, rate)
            if not watch or snap["settled"] >= on_disk:
                return
            print()
            await asyncio.sleep(every)
    finally:
        await engine.dispose()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--watch", action="store_true",
                    help="refresh until every file is settled")
    ap.add_argument("--every", type=float, default=20.0,
                    help="seconds between refreshes under --watch")
    args = ap.parse_args()
    asyncio.run(go(args.watch, args.every))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
