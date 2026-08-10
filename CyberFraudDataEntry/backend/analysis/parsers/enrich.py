"""Narration -> counterparty, channel, reference.

The narration is the only place a statement names the other side of a
transaction, and it is not a field — it is a slash-delimited string
whose shape depends on the channel and the core banking system. Real
examples from this corpus, lightly redacted:

    UPI/CR/188120926061/PENDRA A/CNRB/**7383
    UPI/DR/053246015722/REDDI ARU/UBIN/**kum
    UPI-SIMRANKAUR-9855478425@ybl-YESB0001-512595
    IMPS/P2A/610410506684/XXXXXXXXXX4015/hii
    MOB-IMPS-CR/PALLAVI RA/Karnataka/094725
    MMT/IMPS/006021613239/M.M.TRADIN/AXIS BANK
    ATW-514834XXXXXX8321-S1ANLD02-LUDHIANA
    CLG/RSM TRADING/752049/IND/05.02.2020
    BIL/PAVC/001928948828/Visa/card payment

WHAT IS AND IS NOT EXTRACTED
----------------------------
Channel, reference number, counterparty UPI handle and counterparty
account number are taken where they are unambiguous. Counterparty NAME
is taken too, but treated as the weakest field throughout: banks
truncate it ("REDDI ARU", "M.M.TRADIN"), operators mistype it, and the
F1 work already showed what happens when a name is trusted as an
identity — three spellings of one account holder read as three people.

So F4 will match on account number and UPI handle, with name as a
display label only. That decision lives here as a comment because this
is where the temptation to use the name arises.

Nothing here guesses. A field that cannot be read confidently is left
None, and a NULL is much cheaper than a wrong counterparty edge in a
network graph an officer is about to act on.
"""
from __future__ import annotations

import re

#: Channel markers, most specific first. ATM before CASH because an ATM
#: withdrawal narration usually contains both.
_CHANNELS: list[tuple[str, re.Pattern]] = [
    ("UPI", re.compile(r"\bUPI\b|@[a-z]{2,}\b", re.I)),
    ("IMPS", re.compile(r"\bIMPS\b|\bP2A\b|\bMMT\b", re.I)),
    ("NEFT", re.compile(r"\bNEFT\b", re.I)),
    ("RTGS", re.compile(r"\bRTGS\b", re.I)),
    ("ATM", re.compile(r"\bATM\b|\bATW\b|\bNWD\b|CASH\s*WDL|CASH\s*WITHDRAWAL", re.I)),
    ("POS", re.compile(r"\bPOS\b|\bECOM\b|\bVISA\b|\bRUPAY\b|\bMASTERCARD\b", re.I)),
    ("CHEQUE", re.compile(r"\bCLG\b|\bCHQ\b|\bCHEQUE\b|\bINWARD\b|\bOUTWARD\b", re.I)),
    ("CASH", re.compile(r"\bCASH\b|\bCDM\b|\bBY CASH\b", re.I)),
    ("CHARGES", re.compile(r"\bCHG(S)?\b|\bCHARGE|\bGST\b|\bSMS\b|\bAMB\b|\bINT\.?PD\b", re.I)),
    ("TRANSFER", re.compile(r"\bTRF\b|\bTRANSFER\b|\bFT\b", re.I)),
]

#: name@bank — the UPI VPA. Excludes e-mail by requiring no dot in the
#: handle part, which is how VPAs differ from addresses in practice.
_UPI = re.compile(r"\b([A-Za-z0-9][\w.\-]{1,48})@([a-z]{2,15})\b(?!\.)")

#: 9-18 consecutive digits: an Indian account number. Masked forms
#: (XXXXXXXXXX4015, **7383, 514834XXXXXX8321) are deliberately NOT
#: matched — a partial number is not an identifier, and treating one as
#: if it were would merge unrelated accounts in F4's graph.
_ACCT = re.compile(r"(?<!\d)(\d{9,18})(?!\d)")

#: 12-digit UPI/IMPS reference, or an explicitly labelled one.
_REF = re.compile(r"\b(?:UTR|RRN|REF|TXN)[\s:/#-]*([A-Z0-9]{6,22})\b", re.I)
_BARE_REF = re.compile(r"(?<!\d)(\d{12})(?!\d)")

#: A name-ish run: letters, spaces, dots. Two chars minimum, and must
#: contain a letter — "**7383" and "05.02.2020" must not qualify.
_NAME = re.compile(r"^[A-Za-z][A-Za-z.\s&']{1,48}$")

#: Tokens that look like names but are not counterparties.
_NOT_NAMES = {
    "cr", "dr", "upi", "imps", "neft", "rtgs", "atm", "atw", "pos", "clg",
    "chq", "cash", "trf", "mmt", "bil", "mob", "p2a", "p2p", "ind", "inb",
    "visa", "rupay", "payment", "card", "bank", "india", "ltd", "limited",
    "collect", "pay", "self", "transfer", "charges", "gst", "sms", "nil",
    "oksbi", "ybl", "paytm", "okaxis", "okhdfcbank", "okicici", "apl",
}


def _channel(text: str) -> str | None:
    for name, pat in _CHANNELS:
        if pat.search(text):
            return name
    return None


def _split(text: str) -> list[str]:
    """Narrations delimit with / or -, and mix the two freely."""
    return [p.strip() for p in re.split(r"[/\-|]+", text) if p.strip()]


def _counterparty_name(parts: list[str]) -> str | None:
    """Longest name-shaped part that is not a channel keyword.

    Longest rather than first: the leading parts are almost always
    channel and reference tokens, and the human name tends to be the
    most substantial alphabetic run in the string.
    """
    best = None
    for p in parts:
        s = p.strip()
        if len(s) < 3 or not _NAME.match(s):
            continue
        if s.lower().strip(". ") in _NOT_NAMES:
            continue
        # A part that is entirely channel keywords is not a name.
        words = [w for w in re.split(r"\s+", s.lower()) if w]
        if words and all(w.strip(".") in _NOT_NAMES for w in words):
            continue
        if best is None or len(s) > len(best):
            best = s
    return best.strip(" .") if best else None


def enrich(txn) -> None:
    """Fill the counterparty fields on a Txn, in place.

    Sets .channel, .counterparty_upi, .counterparty_account,
    .counterparty_name and .ref_no (only when the row does not already
    carry a reference from its own column, which is more reliable).
    """
    text = (txn.description or "").strip()
    if not text:
        return

    txn.channel = _channel(text)

    m = _UPI.search(text)
    if m:
        txn.counterparty_upi = f"{m.group(1)}@{m.group(2)}".lower()

    # The reference is usually a 12-digit run, and account numbers are
    # 9-18 digits — so a bare 12-digit number is ambiguous. Resolve by
    # claiming the reference FIRST and excluding it from the account
    # search, rather than letting the same digits become both.
    ref = None
    m = _REF.search(text)
    if m:
        ref = m.group(1)
    else:
        m = _BARE_REF.search(text)
        if m:
            ref = m.group(1)
    if ref and not txn.ref_no:
        txn.ref_no = ref

    for m in _ACCT.finditer(text):
        num = m.group(1)
        if num == ref:
            continue
        txn.counterparty_account = num
        break

    txn.counterparty_name = _counterparty_name(_split(text))
