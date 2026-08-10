#!/usr/bin/env python3
"""Replay every statement's balance chain over the STORED rows and report
which individual rows the arithmetic rejects.

WHY THIS EXISTS
---------------
`upload_ledger.status = 'ok'` is a FILE-level verdict: the chain held on
at least 98% of steps. That tolerance is deliberate — statements
interrupt their own chain at page breaks and carried-forward bands — but
it was then used to vouch for every row inside the file, which is a
different and much stronger claim.

Measured consequence on one real account: 29 rows out of 3,700 (0.78%,
comfortably inside the tolerance) carried Rs 205,642,955,681 of a
Rs 205,648,905,136 reported total. Excluding them, the same account
reads Rs 5,949,455 out and Rs 5,960,228 in — a ratio of 1.00, which is
what a mule account should look like.

The chain does not merely detect those rows, it says what the right
answer was. A row recording a Rs 44,476,848,191 debit whose balance
moved 25,000.10 -> 24,500.10 had a true debit of Rs 500.

OUT / IN AS A SMELL TEST
------------------------
Money in should roughly equal money out for a pass-through account. A
ratio in the thousands is not a finding about the account, it is a
finding about the parse. Reported here alongside the corrected figures
so a bad file announces itself without needing a hand-picked threshold
like "no transaction above X crore", which would eventually be wrong.

    python -m analysis.verify_chain              # top 25 by reported debit
    python -m analysis.verify_chain --top 100
    python -m analysis.verify_chain --all        # every account (slow)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from sqlalchemy import text                            # noqa: E402

#: Same tolerance verify.py uses for a single chain step.
TOL = 0.05


def _rupees(v: float) -> str:
    neg, s = v < 0, f"{abs(v):.0f}"
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if neg else "") + s


class Tally:
    """Three buckets, because a row can be in three states and only one
    of them may be summed as fact.

      PASSED     the chain tested this row and it balanced
      REJECTED   the chain tested it and it did not
      UNTESTED   there was nothing to test it against — the statement
                 carries no running balance, or the row sits at a chain
                 restart (file boundary, or after a gap)

    Collapsing UNTESTED into PASSED is exactly the mistake this module
    was written to expose. An RBL export with no balance column had its
    account number read as the debit on all 16,493 rows; no chain step
    could contradict it, so a two-bucket replay reported the resulting
    Rs 6.68 QUADRILLION as fully corrected and clean.

    Untested is not innocent. It is unknown, and unknown money does not
    belong in a total an officer reads.
    """

    def __init__(self):
        self.passed_d = self.passed_c = 0.0
        self.rejected_d = self.untested_d = 0.0
        self.passed = self.rejected = self.untested = 0

    @property
    def testable(self) -> int:
        return self.passed + self.rejected


def replay(rows) -> Tally:
    """rows: (source_file, row_no, debit, credit, balance), in order.

    The chain restarts at every file boundary and wherever a balance is
    missing — a gap is not evidence of an error, but it is also not
    evidence of correctness.
    """
    t = Tally()
    prev = None
    cur_file = None
    for src, _rn, d, cr, bal in rows:
        if src != cur_file:
            cur_file, prev = src, None
        d = float(d or 0)
        cr = float(cr or 0)
        if bal is None:
            prev = None
            t.untested += 1
            t.untested_d += d
            continue
        bal = float(bal)
        if prev is None:
            # First row of a chain: nothing precedes it, so it cannot be
            # tested even though it has a balance.
            t.untested += 1
            t.untested_d += d
        elif abs((prev - d + cr) - bal) <= TOL:
            t.passed += 1
            t.passed_d += d
            t.passed_c += cr
        else:
            t.rejected += 1
            t.rejected_d += d
        prev = bal
    return t


async def run(top: int, do_all: bool) -> int:
    from database import engine

    async with engine.begin() as conn:
        q = """
            SELECT s.account_id, a.account_holder_name, a.account_no,
                   SUM(s.debit) d, SUM(s.credit) c, SUM(s.txns) n
            FROM account_statement_summary s
            JOIN all_accounts a ON a.id = s.account_id
            GROUP BY s.account_id, a.account_holder_name, a.account_no
            ORDER BY SUM(s.debit) DESC
        """
        if not do_all:
            q += f" LIMIT {int(top)}"
        accounts = (await conn.execute(text(q))).all()

        print(f"{'#':>3} {'account holder':<23} {'txns':>6} "
              f"{'reported out':>24} {'PASSED out':>14} {'PASSED in':>13} "
              f"{'rej':>4} {'untested':>9} {'ratio':>7}")
        print("-" * 112)
        tot_rep = tot_pass = tot_rej = tot_unt = 0.0
        n_rej = n_unt = 0
        for i, (aid, nm, no, rep_d, rep_c, n) in enumerate(accounts, 1):
            rows = (await conn.execute(text("""
                SELECT source_file, row_no, debit, credit, balance
                FROM statement_transactions
                WHERE account_id = :a ORDER BY source_file, row_no"""),
                {"a": aid})).all()
            t = replay(rows)
            tot_rep += float(rep_d or 0)
            tot_pass += t.passed_d
            tot_rej += t.rejected_d
            tot_unt += t.untested_d
            n_rej += t.rejected
            n_unt += t.untested
            ratio = t.passed_d / t.passed_c if t.passed_c > 0.01 else None
            rs = f"{ratio:.2f}" if ratio is not None else "n/a"
            flag = ""
            if t.testable == 0:
                flag = "  <-- UNTESTABLE, no balance column"
            elif ratio is not None and not (0.2 <= ratio <= 5):
                flag = "  <-- still odd"
            print(f"{i:>3} {(nm or '-').strip()[:22]:<23} {int(n):>6,} "
                  f"{_rupees(float(rep_d or 0)):>24} {_rupees(t.passed_d):>14} "
                  f"{_rupees(t.passed_c):>13} {t.rejected:>4} "
                  f"{t.untested:>9,} {rs:>7}{flag}")
        print("-" * 112)
        print(f"  reported out        Rs {_rupees(tot_rep):>26}")
        print(f"  of which PASSED     Rs {_rupees(tot_pass):>26}  "
              f"<- the only figure fit to publish")
        print(f"           REJECTED   Rs {_rupees(tot_rej):>26}  ({n_rej:,} rows)")
        print(f"           UNTESTED   Rs {_rupees(tot_unt):>26}  ({n_unt:,} rows)")
        if tot_pass > 0:
            print(f"  reported / passed   {tot_rep/tot_pass:>26,.0f}x")
    await engine.dispose()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    return asyncio.run(run(a.top, a.all))


if __name__ == "__main__":
    sys.exit(main())
