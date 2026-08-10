"""Header words -> canonical column roles.

This table is the whole reason there is no per-bank parser. Every
layout measured across 600 statements says the same seven things in
different words; map the words and one parser reads them all.

Patterns are regexes matched against a header cell that has already
been lowercased and whitespace-collapsed.

ORDER IS LOAD-BEARING. Roles are tried top to bottom and the first hit
wins, so the specific must precede the general:

  - BALANCE_DRCR before BALANCE, or "balance indicator" is read as a
    balance column and the direction flag is lost.
  - VALUE_DATE before TXN_DATE, or "value date" matches TXN_DATE's
    bare "date" and the two dates swap.
  - REF_NO before TXN_DATE, or "cheque details" ... does not collide,
    but "ref txn no" would match TXN_DATE's "txn" if TXN_DATE came
    first.

Anything unmatched is ignored rather than guessed at. Account number,
branch, SOL ID, journal number and row index are all real columns in
this corpus and none of them belong in statement_transactions.
"""
from __future__ import annotations

import re

#: (role, [patterns]) in resolution order. See ORDER IS LOAD-BEARING.
ROLES: list[tuple[str, list[str]]] = [
    # Direction flag before anything containing "balance" or "cr".
    ("drcr", [
        r"^bal(ance)?\s*ind(icator)?", r"^dr\s*/\s*cr$", r"^cr\s*/\s*dr$",
        r"^d\s*/\s*c$", r"^type\s*of\s*tran", r"^indicator$",
    ]),
    ("balance", [
        r"balance", r"^bal\b", r"^closing\s*bal", r"^running\s*bal",
    ]),
    ("value_date", [
        r"^value\s*d(ate|t)", r"^val\s*d(ate|t)", r"^effective\s*date",
    ]),
    ("ref_no", [
        r"ch(e)?q(ue)?", r"\bref\b", r"reference", r"instrument",
        r"^inst\s*no", r"^utr\b", r"^rrn\b", r"^tran\s*id",
        r"^txn\s*id", r"^journal", r"^jrnl",
    ]),
    ("txn_time", [
        r"^post\s*time", r"^txn\s*time", r"^time$", r"^tran\s*time",
    ]),
    ("txn_date", [
        r"^(tran|trans|txn|transaction|post|posting|book(ing)?)\s*d(ate|t)",
        r"^date", r"date$", r"^dt$",
    ]),
    ("description", [
        r"particular", r"description", r"narration", r"remark",
        r"^details$", r"^transaction$", r"^tran\s*desc", r"^detail",
        r"^narrative",
    ]),
    # \bdebit\b, not ^debit: real exports write "TRAN_DEBIT_AMT" and
    # "Debit Amount", and an anchored pattern misses both. The looseness
    # is only safe because _IDENTIFIER_WORDS below refuses money roles
    # for identifier columns — see the note there.
    # The trailing `s?` is not optional-by-accident: "debits" and
    # "credits" are the header words in 5.7% of this corpus, and
    # \bdebit\b rejects them because the "s" is a word character.
    ("debit", [
        r"\bdebits?\b", r"\bdr\s*amt\b", r"^dr\b", r"withdraw", r"^paid\s*out",
    ]),
    ("credit", [
        r"\bcredits?\b", r"\bcr\s*amt\b", r"^cr\b", r"deposit", r"^paid\s*in",
    ]),
    # Only reached when there is no debit/credit PAIR — a single signed
    # or flagged amount column. Last, because "debit amount" and
    # "withdrawal amt" both contain "amount" and must not land here.
    ("amount", [
        r"^amount", r"amount$", r"^amt\b", r"^tran\s*amt",
    ]),
]

_COMPILED = [(role, [re.compile(p) for p in pats]) for role, pats in ROLES]

#: Header words that prove a row is a header rather than data. Used to
#: FIND the header row, not to map it.
HEADER_HINTS = (
    "date", "narration", "particular", "description", "withdraw",
    "deposit", "debit", "credit", "balance", "chq", "cheque", "ref",
    "value", "remark", "amount", "detail",
)


#: Roles that carry MONEY. A column mapped to one of these gets summed
#: on a dashboard, so a wrong mapping here is not a cosmetic error.
_MONEY_ROLES = {"debit", "credit", "amount", "balance"}

#: Words that mark a column as an IDENTIFIER rather than an amount.
#: A header containing any of these can never take a money role.
#:
#: This exists because of a real, expensive failure. An RBL export has
#: BOTH `Debit_Account` (column 11, the debit account NUMBER) and
#: `TRAN_DEBIT_AMT` (column 25, the actual figure). First-match-wins
#: took column 11, so every one of that statement's 16,493 rows recorded
#: a debit of 405495495492 — which is the account number. The dashboard
#: then reported ₹6.68 QUADRILLION against one account, about twice
#: India's GDP, and it looked like a number rather than an error.
#:
#: The exclusion is checked before role matching, so the loose \bdebit\b
#: pattern can find "TRAN_DEBIT_AMT" without also claiming
#: "Debit_Account" or "debit_account_name".
_IDENTIFIER_WORDS = (
    "account", "acct", "a/c", "ifsc", "micr", "name", "party", "branch",
    "bank", "sol", "code", "number", "no.", "utr", "rrn", "id", "index",
    "serial", "cif", "customer", "email", "mobile", "phone", "address",
)

#: ...unless the header ALSO says it is an amount. "Balance Amount",
#: "Debit Amount" and "Account Balance" are money columns whose names
#: happen to contain an identifier word.
_AMOUNT_WORDS = ("amt", "amount", "value", "sum", "total", "balance")


def _is_identifier(h: str) -> bool:
    if any(w in h for w in _AMOUNT_WORDS):
        return False
    return any(w in h for w in _IDENTIFIER_WORDS)


def role_of(header: str) -> str | None:
    h = (header or "").lower()
    # Underscores become spaces BEFORE anything else. Finalcle-style
    # exports write "Dr_Amt" and "Cr_Amt", and an underscore is a word
    # character — so "^dr\b" finds no boundary in "dr_amt" and "^dr\s*amt"
    # finds no whitespace. Both patterns missed, the debit and credit
    # columns went unmapped, and every row in those files came out with
    # no amounts at all.
    h = h.replace("_", " ")
    h = re.sub(r"\s+", " ", h).strip()
    h = h.replace(".", "").replace("(in rs)", "").replace("₹", "").strip()
    if not h:
        return None
    ident = _is_identifier(h)
    for role, pats in _COMPILED:
        if role in _MONEY_ROLES and ident:
            continue
        if any(p.search(h) for p in pats):
            return role
    return None


def resolve(headers: list[str]) -> dict[str, int]:
    """Map a header row to {role: column index}.

    First occurrence wins. A second column claiming a taken role is
    dropped rather than overwriting — statements repeat "balance" in a
    summary block, and the transaction table's is the one that came
    first.
    """
    out: dict[str, int] = {}
    for i, h in enumerate(headers):
        r = role_of(h)
        if r and r not in out:
            out[r] = i
    return out


def is_header_row(cells: list[str], min_hits: int = 3) -> bool:
    """Does this row name columns, rather than hold data?

    Requires min_hits DISTINCT header words. Two is not enough: a
    summary band like "opening balance | total debits | total credits |
    closing balance" scores two on the naive test and gets mistaken for
    the transaction header — which is exactly what happened on 3.2% of
    the corpus before this was tightened, silently yielding zero rows.
    """
    low = [re.sub(r"\s+", " ", (c or "")).strip().lower() for c in cells]
    hits = {h for c in low for h in HEADER_HINTS if h in c}
    return len(hits) >= min_hits


def usable(roles: dict[str, int]) -> bool:
    """Enough columns to build a transaction from?

    A date, something to call it, and at least one money column. Below
    that the row is not a transaction and pretending otherwise fills
    the table with nulls.
    """
    if "txn_date" not in roles:
        return False
    if not ({"debit", "credit"} & roles.keys() or "amount" in roles
            or "balance" in roles):
        return False
    return True
