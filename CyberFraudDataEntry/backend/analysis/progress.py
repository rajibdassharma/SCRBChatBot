#!/usr/bin/env python3
"""How far the statement backfill has got. Read-only, safe to run at
any time — including while parse_statements.py is running.

    python -m analysis.progress

Reads the ledger rather than the job's console output. That is
deliberate: the parser's stdout goes through a pipe when it runs in the
background, and a pipe buffers, so the log file can sit empty for
minutes while real work is happening. The ledger is committed per
flush, so it is always current and never lies about what is done.
"""
from __future__ import annotations

import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
STMT_DIR = os.path.join(BACKEND, "uploads", "statements")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from sqlalchemy import text                            # noqa: E402


def _bar(frac: float, width: int = 40) -> str:
    n = max(0, min(width, int(round(frac * width))))
    return "[" + "#" * n + "-" * (width - n) + "]"


async def go() -> None:
    from database import engine
    from analysis import runtime as R

    on_disk = len([f for f in os.listdir(STMT_DIR)
                   if f.lower().endswith((".pdf", ".xls", ".xlsx"))])
    async with engine.begin() as c:
        rows = (await c.execute(text(
            "SELECT status, COUNT(*) FROM upload_ledger "
            "WHERE file_kind='statement' GROUP BY status"))).all()
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
    await engine.dispose()

    done = sum(n for _, n in rows)
    frac = done / max(1, on_disk)
    print(f"{_bar(frac)} {100*frac:5.1f}%")
    print(f"  parsed        {done:>8,} of {on_disk:,} files")
    print(f"  remaining     {on_disk - done:>8,}")
    for st, n in sorted(rows, key=lambda kv: -kv[1]):
        print(f"      {st:<12}{n:>8,}")
    print(f"  transactions  {txns:>8,}")
    print(f"  accounts      {accts:>8,} with a statement summary")
    print(f"  table size    {float(size):>8.2f} GB")
    print(f"  memory        {R.gb(R.available_bytes()):>8.1f} GB free")


if __name__ == "__main__":
    asyncio.run(go())
