"""Narration -> crypto exchange / asset, or None.

WHY THIS IS A SEPARATE MODULE
-----------------------------
Because the naive version is worse than nothing, and it is worth
keeping the evidence next to the code.

A first pass matched `LIKE '%btc%'` and `LIKE '%okx%'` over the
narration and reported 168 "OKX" and 36 "BTC" transactions. Inspecting
them:

    IMPSP2A518188984499ASHOKX009328BANK OFBARODA
                          ^^^^^ ASHOK, then a reference character
    IMPSP2A516013019837ZOaazcokX010373NSDLPAYMENTSBANKLTD
    DEP TFR UPI/CR/123948671226/Ratan Mu/AIRP/ratanbtc19/UYD7
                                              ^^^^^^^ part of a UPI handle
    IMPSP2A532256220664ZDMKBTC180216X104583UCOBANK
    MMT/IMPS/330715481059/3BTcu38gOnCxg7d/ROSHANMEEN/I

Three-letter tickers land inside IMPS reference codes and inside names.
Four fifths of those "findings" were men called Ashok. Shipping that as
a Crypto Trail screen would have an officer chasing reference strings.

So tickers are matched on WORD BOUNDARIES and exchange names as
substrings — an exchange name is distinctive enough to survive being
jammed against other text ("BIT/BINANCE.COM", "binancecom"), a
three-letter ticker is not.

WHAT COUNTS AS EVIDENCE
-----------------------
Strongest first:

  1. A named exchange in the narration. "wazirx", "binance.com" —
     unambiguous, and the label records WHICH exchange.
  2. A stablecoin or asset named with word boundaries. "USDT
     CONVERSION" in an IMPS narration is a statement of intent.
  3. Generic wording -- "crypto", "bitcoin". Weaker, but a human wrote
     it deliberately.

Anything else is left None. A NULL costs an officer nothing; a wrong
crypto flag costs them a line of inquiry.
"""
from __future__ import annotations

import re

#: Named exchanges. Substring matching is SAFE here because these
#: strings do not occur inside Indian names or IMPS reference codes,
#: and the corpus shows them jammed against other text -- "binancecom",
#: "BIT/BINANCE.COM", "ICIC0000104/wazirx" -- which a word-boundary
#: pattern would miss.
#:
#: Value is the canonical label stored on the row.
_EXCHANGES: list[tuple[str, re.Pattern]] = [
    ("BINANCE",    re.compile(r"binance", re.I)),
    ("WAZIRX",     re.compile(r"wazirx", re.I)),
    ("COINDCX",    re.compile(r"coindcx", re.I)),
    ("COINSWITCH", re.compile(r"coinswitch", re.I)),
    ("ZEBPAY",     re.compile(r"zebpay", re.I)),
    ("BITBNS",     re.compile(r"bitbns", re.I)),
    ("GIOTTUS",    re.compile(r"giottus", re.I)),
    ("UNOCOIN",    re.compile(r"unocoin", re.I)),
    ("BUYUCOIN",   re.compile(r"buyucoin", re.I)),
    ("SUNCRYPTO",  re.compile(r"suncrypto", re.I)),
    ("MUDREX",     re.compile(r"mudrex", re.I)),
    ("COINBASE",   re.compile(r"coinbase", re.I)),
    ("KRAKEN",     re.compile(r"kraken", re.I)),
    ("BITFINEX",   re.compile(r"bitfinex", re.I)),
    ("KUCOIN",     re.compile(r"kucoin", re.I)),
    ("BYBIT",      re.compile(r"bybit", re.I)),
    ("FLITPAY",    re.compile(r"flitpay", re.I)),
    ("COINSBIT",   re.compile(r"coinsbit", re.I)),
    ("PI42",       re.compile(r"\bpi42\b", re.I)),
    ("VAULD",      re.compile(r"\bvauld\b", re.I)),
    # OKX and Huobi are real exchanges with short, collision-prone
    # names, so they get boundaries where the others do not. "okx" alone
    # matched 168 rows, essentially all of them ASHOK + a reference
    # character.
    ("OKX",        re.compile(r"\bokx\b", re.I)),
    ("HUOBI",      re.compile(r"\bhuobi\b", re.I)),
]

#: Assets and generic wording. Word-boundaried, and NO THREE-LETTER
#: TICKERS -- not even bounded ones.
#:
#: \beth\b and \bbtc\b were tried and both failed on real data:
#:
#:   \beth\b  58 hits, every one the SAME statement header --
#:            "JOINT HOLDERS : Cust ID : 40943276 ETH". ETH is a bank
#:            code in the joint-holding metadata. Nothing to do with
#:            Ethereum, and it would have been the LARGEST category on
#:            the screen.
#:   \bbtc\b  4 hits, all ambiguous: "Ch h btc g h" (garbled name),
#:            "btc.starwin@okaxis" (a UPI handle), "MMT/IMPS/.../BTC/
#:            TEJAS VIDY" (an unexplained field).
#:
#: Word boundaries fixed the ASHOKX class of error and did nothing for
#: this one, because these tokens are genuinely standalone words that
#: happen not to mean the asset. Three letters is simply not enough
#: signal in bank narration. USDT survives at four characters, and
#: "USDT CONVERSION" is a statement of intent rather than a code.
_ASSETS: list[tuple[str, re.Pattern]] = [
    ("USDT",     re.compile(r"\busdt\b|\btether\b", re.I)),
    ("BITCOIN",  re.compile(r"\bbitcoin\b", re.I)),
    ("ETHEREUM", re.compile(r"\bethereum\b", re.I)),
    ("CRYPTO",   re.compile(r"\bcrypto\b|\bblockchain\b|\bvirtual\s+digital\s+asset\b", re.I)),
]


def detect(text: str | None) -> str | None:
    """Canonical crypto label for a narration, or None.

    Exchanges win over assets: "USDT purchase via WazirX" is more
    useful recorded as WAZIRX, because an exchange is somewhere an
    investigator can send a request and an asset name is not.
    """
    if not text:
        return None
    for label, pat in _EXCHANGES:
        if pat.search(text):
            return label
    for label, pat in _ASSETS:
        if pat.search(text):
            return label
    return None


#: Every one of these came out of the corpus. The FALSE cases are the
#: reason this module exists -- keep them.
_CASES: list[tuple[str, str | None]] = [
    # --- real, from the corpus ---
    ("VISA FOREX Dr 17/04/2023 binancecom", "BINANCE"),
    ("09-OCT-2024 PCA:0454105556:000000010001534: 428304573810 BIT/BINANCE.COM V", "BINANCE"),
    ("TO ECM/311114229525/binance.com \\binance", "BINANCE"),
    ("MB IMPS/IFO/105622482383/ICIC0000104/wazirx", "WAZIRX"),
    ("MMT/IMPS/524021217913/USDT CONVERSION/SHALU ISHA/K", "USDT"),
    ("UPI/501696093191/DR/rahu/BKID/77712-3@okicici/usdt", "USDT"),
    # --- false positives the naive version reported ---
    ("IMPSP2A518188984499ASHOKX009328BANK OFBARODA", None),
    ("IMPSP2A516013019837ZOaazcokX010373NSD LPAYMENTSBANKLTD", None),
    ("DEP TFR UPI/CR/123948671226/Ratan Mu/AIRP/ratanbtc19/UYD7 0097732162091", None),
    ("IMPSP2A602722763832AK8QKBTCX013497B ANKOFINDIA", None),
    ("IMPSP2A532256220664ZDMKBTC180216X104 583UCOBANK", None),
    ("MMT/IMPS/330715481059/3BTcu38gOnCxg7d/ROSHANMEEN/I", None),
    # --- three-letter tickers: standalone words that are NOT the asset ---
    ("JOINT HOLDERS : Cust ID : 40943276 ETH", None),
    ("IMPS/P2A/529447156448/Ch h btc g h/X875730/IDFCBank", None),
    ("UPI:470200231557:btc.starwin@okaxis(Mr MD AKRAM)", None),
    ("MMT/IMPS/316009779278/BTC/TEJAS VIDY/Kotak Mahindr", None),
    # --- ordinary narrations must stay clean ---
    ("UPI/CR/188120926061/PENDRA A/CNRB/**7383", None),
    ("ATW-514834XXXXXX8321-S1ANLD02-LUDHIANA", None),
    ("CLG/RSM TRADING/752049/IND/05.02.2020", None),
    (None, None),
    ("", None),
]


def _self_test() -> int:
    bad = 0
    for text, want in _CASES:
        got = detect(text)
        if got != want:
            bad += 1
            print(f"  FAIL want={want!r} got={got!r}  {(text or '')[:62]}")
    print(f"  {len(_CASES) - bad}/{len(_CASES)} cases pass")
    return bad


if __name__ == "__main__":
    import sys
    sys.exit(1 if _self_test() else 0)
