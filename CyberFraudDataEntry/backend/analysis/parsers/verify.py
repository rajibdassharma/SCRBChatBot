"""Balance-chain reconciliation — the correctness gate for F2.

WHY THIS EXISTS
---------------
A statement parser that produces output is easy. A statement parser
that produces CORRECT output is not, and the difference is invisible
from the outside: swap the debit and credit columns and every row still
looks like a transaction. Drop every continuation line and the table
still fills up. Read 03/04 as 4 March and the dates are still dates.

Every statement carries its own check. The running balance is a
recurrence over the rows:

    balance[i] = balance[i-1] - debit[i] + credit[i]

If that holds on every row, then the debit and credit columns were
identified correctly, the amounts were parsed correctly, and no row was
skipped — because any of those errors breaks the chain immediately.

RECONCILIATION AS REPAIR, NOT JUST AS A TEST
--------------------------------------------
The chain also says WHICH mistake was made, so three of them are fixed
rather than merely reported:

  reversed order   Statements are commonly newest-first. The chain then
                   runs backwards, and testing it backwards is what
                   distinguishes "wrong order" from "wrong parse".
  swapped columns  If the chain fails forward but succeeds with debit
                   and credit exchanged, the header mapping was wrong.
  signed amounts   Some layouts put negatives in the debit column.

Only the residue — a chain that fails under every hypothesis — is a
genuine parse failure, and the driver records it as one instead of
counting the file as done.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Paise-level tolerance. Statements round to two decimals and a long
#: chain accumulates a little drift; 5 paise is far below any real
#: transaction and far above float noise.
TOL = 0.05

#: A chain shorter than this proves nothing — two rows agreeing by
#: coincidence is common, especially when one amount is zero.
MIN_CHAIN = 4


@dataclass
class Reconciliation:
    checked: int = 0          # rows where a chain step could be tested
    ok: int = 0               # steps that balanced
    reversed_order: bool = False
    swapped: bool = False
    #: None when there was nothing to check (no balance column, or too
    #: few rows). Distinct from 0.0, which means "checked and wrong".
    rate: float | None = None

    @property
    def verified(self) -> bool:
        """A file is only 'parsed' if its own arithmetic agrees.

        98% and not 100%: a statement legitimately interrupts its own
        chain at a carried-forward page break or an opening-balance
        band, and those show up as one or two bad steps in a chain of
        hundreds. Below 98% the errors are systematic.
        """
        return self.rate is not None and self.rate >= 0.98


def _run(rows, swapped: bool, reverse: bool) -> tuple[int, int]:
    seq = list(reversed(rows)) if reverse else rows
    checked = ok = 0
    prev = None
    for r in seq:
        bal = r.balance
        if bal is None:
            # A row without a balance breaks the chain rather than
            # corrupting it: resume from the next row that has one.
            prev = None
            continue
        if prev is not None:
            d = r.credit if swapped else r.debit
            c = r.debit if swapped else r.credit
            expect = prev - (d or 0.0) + (c or 0.0)
            checked += 1
            if abs(expect - bal) <= TOL:
                ok += 1
        prev = bal
    return checked, ok


def reconcile(rows) -> Reconciliation:
    """Test the balance chain under each hypothesis; keep the best.

    `rows` are objects with .debit, .credit and .balance floats-or-None,
    in the order they appeared in the document.
    """
    if len(rows) < MIN_CHAIN or all(r.balance is None for r in rows):
        return Reconciliation()

    best = None
    for reverse in (False, True):
        for swapped in (False, True):
            checked, ok = _run(rows, swapped, reverse)
            if checked == 0:
                continue
            rate = ok / checked
            cand = Reconciliation(checked=checked, ok=ok,
                                  reversed_order=reverse, swapped=swapped,
                                  rate=rate)
            # Prefer the higher rate; on a tie prefer the plainest
            # explanation — forward order, columns as mapped. Without
            # that tiebreak a chain of all-zero amounts (every
            # hypothesis scores 1.0) would report a spurious swap.
            if best is None or (rate, not reverse, not swapped) > \
                               (best.rate, not best.reversed_order, not best.swapped):
                best = cand
    return best or Reconciliation()


#: Per-row verdicts, matching statement_transactions.chain_ok.
PASSED, REJECTED, UNTESTED = 1, 0, -1


def row_verdicts(rows, rec: Reconciliation | None = None) -> list[int]:
    """One verdict per row, in the order given.

        1  PASSED    tested against the preceding balance, and it agreed
        0  REJECTED  tested, and it did not
       -1  UNTESTED  nothing to test against -- no running balance, or
                     the row sits at a chain restart

    reconcile() already walks this exact chain to produce its file-level
    rate; it simply throws away WHICH steps failed. That discarded
    detail is the whole difference between a usable number and a wrong
    one: a file scoring 99.22% had 29 rows carrying Rs 205,642,955,681
    of a Rs 205,648,905,136 total, and the file-level verdict called it
    clean.

    UNTESTED is a distinct answer from PASSED, not a lenient version of
    it. A statement with no balance column cannot contradict anything,
    so an account number read as a debit sails through -- which is
    exactly how Rs 6.68 quadrillion reached a dashboard.
    """
    if rec is None:
        rec = reconcile(rows)
    order = list(range(len(rows)))
    if rec.reversed_order:
        order.reverse()

    out = [UNTESTED] * len(rows)
    prev = None
    for i in order:
        r = rows[i]
        d = float(r.debit or 0)
        c = float(r.credit or 0)
        if rec.swapped:
            d, c = c, d
        if r.balance is None:
            prev = None
            continue
        bal = float(r.balance)
        if prev is not None:
            out[i] = PASSED if abs((prev - d + c) - bal) <= TOL else REJECTED
        prev = bal
    return out


def apply_repair(rows, rec: Reconciliation):
    """Rewrite rows according to what reconciliation discovered.

    Returns the corrected list. Only touches what the chain proved:
    a swap exchanges the two amount columns, a reversal restores
    chronological order. Untouched when nothing was proven, so an
    unverified file is stored exactly as parsed rather than silently
    "fixed" on a guess.
    """
    if not rec.verified:
        return rows
    if rec.swapped:
        for r in rows:
            r.debit, r.credit = r.credit, r.debit
    if rec.reversed_order:
        rows = list(reversed(rows))
        for i, r in enumerate(rows):
            r.row_no = i
    return rows
