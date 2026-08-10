"""Cell -> typed value. Dates, amounts, and the small horrors of real
bank statements.

Everything here returns None rather than raising. A single unparseable
cell must not take down a 3,000-row statement, and a row that loses its
amount is caught downstream by reconciliation anyway.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time as dtime

#: Indian statements are day-first, universally. The ambiguity only
#: bites on days 1-12, where 03/04/25 could be 3 April or 4 March.
#: infer_dayfirst() below resolves it per FILE rather than per cell:
#: one unambiguous date (day > 12) settles every other date in the same
#: statement, and mixing conventions inside one file does not happen.
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_D_ALPHA = re.compile(
    r"\b(\d{1,2})[-/\s]([A-Za-z]{3,4})[-/\s](\d{2,4})\b")          # 01-Jan-2026
_D_NUM = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b")   # 01/02/2026
_D_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")                 # 2026-01-31
_TIME = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?\b")

#: 1,352.20 . 1,01,352.20 (lakh grouping) . 4437.50 . 100000
#: "1 352,20" is European, not Indian, and is deliberately unsupported.
#:
#: The grouped alternative REQUIRES a comma (`+`, not `*`), and that is
#: not cosmetic. Written with `*` the first branch matches the leading
#: three digits of an ungrouped number and, regex alternation being
#: ordered, the second branch never runs — "4437.50" parsed as 443.00
#: and "1215.00" as 121.00. PDFs hid it because they print grouped;
#: Excel stores raw numbers, so EVERY Excel amount over ₹999 was
#: silently truncated to its first three digits. Reconciliation caught
#: it at a 5% pass rate; nothing else would have.
_AMOUNT = re.compile(r"[-+(]?\s*(?:rs\.?|inr|₹)?\s*"
                     r"(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
                     r"\s*\)?", re.I)
#: Trailing Dr/Cr on a balance. HDFC writes "99,999.99Cr"; some Finacle
#: exports put the indicator in its own column instead (see columns.py).
_DRCR = re.compile(r"\b(dr|cr)\b\.?\s*$", re.I)

_BLANK = {"", "-", "--", "n/a", "na", "nil", "null", "none", "."}


def clean(cell) -> str:
    """Collapse the whitespace PDF extraction sprays through cells.

    pdfplumber returns wrapped cells with real newlines inside them —
    a date arrives as "01-Jan-\n2026" and a narration as three lines.
    Every consumer here wants one line.
    """
    if cell is None:
        return ""
    return re.sub(r"\s+", " ", str(cell)).strip()


def is_blank(cell) -> bool:
    return clean(cell).lower() in _BLANK


#: Longest digit run still credible as a rupee amount when the number
#: carries NO decimal point and NO thousands separator.
#:
#: Bank narrations are full of long bare integers that are not money —
#: NEFT/UTR references, account numbers, transaction ids. When a column
#: mapping is even slightly off, one of those lands in the balance cell
#: and gets read as an amount. That is not hypothetical: the first real
#: write of this parser died on
#:     DataError 1264: Out of range value for column 'balance'
#: after reading the 17-digit NEFT reference 52026022340809515 as a
#: balance. 12 digits is ₹9,999 crore, comfortably above any account in
#: this corpus and comfortably below a reference number.
MAX_BARE_DIGITS = 12

#: statement_transactions stores DECIMAL(18,2) — 16 integer digits. A
#: value past that cannot be written at all, so returning it would
#: guarantee the failure above rather than merely risk it.
MAX_AMOUNT = 10.0 ** 16


def parse_amount(cell) -> float | None:
    """Amount as a float, or None. Sign is NOT interpreted here.

    Statements express direction three different ways — separate debit
    and credit columns, one amount column plus a Dr/Cr flag, or a
    negative number — and which one applies is a property of the
    LAYOUT, not the cell. columns.py decides; this just reads a number.

    Parentheses and a leading minus are stripped rather than negated,
    for the same reason.

    Returns None for anything that is numerically impossible as money
    (see MAX_BARE_DIGITS). None is the right answer rather than a
    best guess: a missing amount breaks the balance chain, so
    reconciliation flags the file as unverified and a human looks at
    it — which is exactly what should happen when the parser cannot
    tell a reference number from a rupee value.
    """
    s = clean(cell)
    if not s or s.lower() in _BLANK:
        return None
    s = _DRCR.sub("", s).strip()
    m = _AMOUNT.search(s)
    if not m:
        return None
    tok = m.group(1)
    if "," not in tok and "." not in tok and len(tok) > MAX_BARE_DIGITS:
        return None
    try:
        v = float(tok.replace(",", ""))
    except ValueError:
        return None
    return None if abs(v) >= MAX_AMOUNT else v


def drcr_flag(cell) -> str | None:
    """'D' or 'C' from a Dr/Cr suffix or a balance-indicator cell."""
    s = clean(cell).lower().rstrip(".")
    if not s:
        return None
    if s in ("d", "dr", "debit"):
        return "D"
    if s in ("c", "cr", "credit"):
        return "C"
    m = _DRCR.search(s)
    if m:
        return "D" if m.group(1).lower() == "dr" else "C"
    return None


def _year(y: int) -> int:
    """Two-digit years. Statements are recent, so 24 -> 2024 and a
    value above the current century's tail would be last century."""
    if y >= 100:
        return y
    return 2000 + y if y <= 79 else 1900 + y


def parse_date(cell, dayfirst: bool = True) -> date | None:
    s = clean(cell)
    if not s:
        return None
    m = _D_ALPHA.search(s)
    if m:
        mon = _MONTHS.get(m.group(2)[:3].lower())
        if mon:
            try:
                return date(_year(int(m.group(3))), mon, int(m.group(1)))
            except ValueError:
                return None
    m = _D_ISO.search(s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = _D_NUM.search(s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), _year(int(m.group(3)))
        d, mo = (a, b) if dayfirst else (b, a)
        try:
            return date(y, mo, d)
        except ValueError:
            # Convention was wrong for this cell — try the other way
            # before giving up. Happens when a file's dates are mostly
            # unambiguous and one is not.
            try:
                return date(y, d, mo)
            except ValueError:
                return None
    return None


def parse_time(cell) -> dtime | None:
    """Time of day, where the statement carries one.

    Only 60% of statements do (measured), which is why F5 velocity has
    to work at day granularity and treat this as a bonus.
    """
    s = clean(cell)
    if not s:
        return None
    m = _TIME.search(s)
    if not m:
        return None
    try:
        return dtime(int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
    except ValueError:
        return None


def infer_dayfirst(cells) -> bool:
    """Decide day-first vs month-first ONCE, for a whole file.

    Reads only numeric dates and looks for a component above 12, which
    can only be a day. Returns True (day-first) when the evidence says
    so or when there is no evidence, because Indian statements are
    day-first by default and guessing the other way on an ambiguous
    file would silently shift dates by months.
    """
    first_gt12 = second_gt12 = 0
    for c in cells:
        m = _D_NUM.search(clean(c))
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a > 12:
            first_gt12 += 1
        if b > 12:
            second_gt12 += 1
    if second_gt12 > first_gt12:
        return False
    return True


def looks_like_date(cell) -> bool:
    s = clean(cell)
    return bool(_D_ALPHA.search(s) or _D_ISO.search(s) or _D_NUM.search(s))


def looks_like_amount(cell) -> bool:
    s = clean(cell)
    if not s or s.lower() in _BLANK:
        return False
    # Require a decimal part or a thousands separator. A bare integer
    # is far more often a cheque number, a reference or a row index
    # than an amount, and admitting those wrecks the column inference.
    return bool(re.search(r"\d[\d,]*\.\d{1,2}\b|\b\d{1,3}(,\d{2,3})+\b", s))
