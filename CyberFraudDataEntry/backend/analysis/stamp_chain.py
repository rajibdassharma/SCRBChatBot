#!/usr/bin/env python3
"""Stamp each stored transaction with its balance-chain verdict.

    python -m analysis.stamp_chain             # stamp everything
    python -m analysis.stamp_chain --dry-run   # report, write nothing
    python -m analysis.stamp_chain --since-version stmt-v1

NO RE-PARSING
-------------
Every input the chain needs is already in the table: row_no, debit,
credit, balance. This replays the arithmetic over stored rows. Nothing
opens a PDF.

THREE VERDICTS
--------------
    1  PASSED    tested against the preceding balance, and it agreed
    0  REJECTED  tested, and it did not
   -1  UNTESTED  nothing to test against -- no running balance in the
                 statement, or the row sits at a chain restart

Only PASSED may be summed as money. REJECTED rows are the ones carrying
a Rs 44 billion debit against a Rs 500 balance movement. UNTESTED rows
are not innocent: an RBL export with no balance column had its account
number read as the debit on all 16,493 rows, and nothing could
contradict it.

ORIENTATION IS RE-DERIVED PER FILE
----------------------------------
verify.reconcile() already knows how to find whether a statement runs
newest-first, or has its debit and credit columns transposed. That is
re-run here rather than assumed, because rows from a file that FAILED
reconciliation at parse time were stored exactly as parsed --
apply_repair only rewrites files that passed. Replaying those forward
without checking would reject every row in a merely-reversed statement,
which is a different error from the one being hunted.

WRITE STRATEGY
--------------
Per file: one bulk UPDATE sets the common verdict, then the exceptions
are corrected by id. In a healthy statement the exceptions are a
handful of rows out of thousands, so this is two or three statements
per file rather than one per row.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from sqlalchemy import bindparam, text                  # noqa: E402

from analysis.parsers.verify import TOL, reconcile      # noqa: E402

PASSED, REJECTED, UNTESTED = 1, 0, -1

#: Ids per UPDATE when correcting exceptions.
CHUNK = 800

#: Files handled between commits. Keeps the transaction short enough
#: that a stop costs little, without paying commit overhead per file.
FILES_PER_COMMIT = 200


class _Row:
    """Minimal stand-in so verify.reconcile() can be reused unchanged."""
    __slots__ = ("debit", "credit", "balance", "row_no")

    def __init__(self, debit, credit, balance, row_no):
        self.debit = float(debit) if debit is not None else None
        self.credit = float(credit) if credit is not None else None
        self.balance = float(balance) if balance is not None else None
        self.row_no = row_no


def verdicts(rows) -> dict:
    """(id -> verdict) for one file's rows, in stored order."""
    objs = [_Row(d, c, b, n) for _id, n, d, c, b in rows]
    rec = reconcile(objs)

    seq = list(range(len(rows)))
    if rec.reversed_order:
        seq.reverse()

    out = {}
    prev = None
    for i in seq:
        _id, _n, d, c, b = rows[i]
        d = float(d) if d is not None else 0.0
        c = float(c) if c is not None else 0.0
        if rec.swapped:
            d, c = c, d
        if b is None:
            prev = None
            out[_id] = UNTESTED
            continue
        b = float(b)
        if prev is None:
            # Has a balance, but nothing before it to test against.
            out[_id] = UNTESTED
        elif abs((prev - d + c) - b) <= TOL:
            out[_id] = PASSED
        else:
            out[_id] = REJECTED
        prev = b
    return out


async def run(dry_run: bool, version: str | None, resume: bool) -> int:
    from database import engine

    t0 = time.time()
    tally: Counter = Counter()
    async with engine.connect() as conn:
        where = "WHERE parser_version = :pv" if version else ""
        params = {"pv": version} if version else {}
        files = [r[0] for r in (await conn.execute(text(
            f"SELECT DISTINCT source_file FROM statement_transactions {where}"
        ), params)).all()]
        total_files = len(files)

        if resume:
            # A file counts as already stamped if ANY of its rows holds
            # a definite verdict. The column defaults to -1, which also
            # means UNTESTED, so an all-untested file is indistinguishable
            # from an unstamped one and gets redone — that is a small,
            # harmless cost (same input, same verdict) and much safer
            # than inventing a fourth sentinel or paying another
            # ten-minute ALTER on a 15 GB table to add a marker column.
            stamped = {r[0] for r in (await conn.execute(text(
                "SELECT DISTINCT source_file FROM statement_transactions "
                "WHERE chain_ok <> -1"))).all()}
            files = [f for f in files if f not in stamped]
            print(f"resume: {len(stamped):,} file(s) already stamped, "
                  f"{len(files):,} of {total_files:,} remain")
        else:
            print(f"files to stamp: {len(files):,}")
        # That SELECT autobegan a transaction. Close it before the
        # batch loop, which manages its own — SQLAlchemy refuses an
        # explicit begin() while an implicit one is open.
        await conn.commit()

        done = 0
        for start in range(0, len(files), FILES_PER_COMMIT):
            batch = files[start:start + FILES_PER_COMMIT]
            for src in batch:
                rows = (await conn.execute(text("""
                    SELECT id, row_no, debit, credit, balance
                    FROM statement_transactions
                    WHERE source_file = :s ORDER BY row_no, id"""),
                    {"s": src})).all()
                if not rows:
                    continue
                v = verdicts(rows)
                tally.update(v.values())
                if dry_run:
                    continue

                # Bulk-set the majority verdict, then fix the rest by id.
                majority = Counter(v.values()).most_common(1)[0][0]
                await conn.execute(text(
                    "UPDATE statement_transactions SET chain_ok = :c "
                    "WHERE source_file = :s"), {"c": majority, "s": src})
                for verdict in (PASSED, REJECTED, UNTESTED):
                    if verdict == majority:
                        continue
                    ids = [k for k, val in v.items() if val == verdict]
                    for i in range(0, len(ids), CHUNK):
                        await conn.execute(
                            text("UPDATE statement_transactions "
                                 "SET chain_ok = :c WHERE id IN :ids")
                            .bindparams(bindparam("ids", expanding=True)),
                            {"c": verdict, "ids": ids[i:i + CHUNK]})
            # One commit per batch of files: short enough that a stop
            # costs little, long enough not to pay commit overhead per
            # file. Dry runs roll back instead, so the same code path
            # is exercised either way.
            if dry_run:
                await conn.rollback()
            else:
                await conn.commit()
            done += len(batch)
            if start % (FILES_PER_COMMIT * 5) == 0 or done == len(files):
                el = time.time() - t0
                print(f"  {done:,}/{len(files):,} files  {el:.0f}s  "
                      f"passed {tally[PASSED]:,} rejected {tally[REJECTED]:,} "
                      f"untested {tally[UNTESTED]:,}", flush=True)

    await engine.dispose()

    total = sum(tally.values())
    print("=" * 62)
    for label, k in (("PASSED   (publishable)", PASSED),
                     ("REJECTED (arithmetic disagrees)", REJECTED),
                     ("UNTESTED (nothing to test against)", UNTESTED)):
        n = tally[k]
        print(f"  {label:<36}{n:>12,}  {100*n/max(1,total):>5.1f}%")
    print(f"  {'TOTAL':<36}{total:>12,}")
    print("=" * 62)
    if dry_run:
        print("dry run: nothing written.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-resume", action="store_true",
                    help="re-stamp every file, not just unstamped ones")
    ap.add_argument("--since-version", default=None,
                    help="only stamp rows written by this parser version")
    a = ap.parse_args()
    return asyncio.run(run(a.dry_run, a.since_version, not a.no_resume))


if __name__ == "__main__":
    sys.exit(main())
