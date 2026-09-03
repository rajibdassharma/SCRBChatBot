#!/usr/bin/env python3
"""Money that left an account to a NAMED but UNNUMBERED counterparty.

    python -m analysis.build_unlinked                # FULL rebuild (slow)
    python -m analysis.build_unlinked --recent 48    # only accounts parsed
                                                     # in the last 48 h
    python -m analysis.build_unlinked --dry-run      # report, write nothing

WHAT THIS ANSWERS
-----------------
An officer opens Graphical Analysis for an FIR, sees accounts with
parsed statements and hundreds of transactions, and sees no arrows
between them. The screen looks broken. It is not: an arrow requires the
recipient's ACCOUNT NUMBER so it can be matched against the mule
register, and whether the bank writes one down is decided entirely by
channel. Measured across the corpus:

    RTGS 99%     NEFT 83%     UPI 69%     IMPS 13%

IMPS is the whole shortfall and it is the bank's narration format, not
a parser failure. Inbound reads "FT IMPS/IFI/<ref>/<NAME>/..." -- a
person and no account. Outbound reads "MB IMPS/IFO/<ref>/<IFSC>/..." --
a BRANCH code shared by thousands of accounts. Masked forms (XX0323)
are four digits. analysis/parsers/enrich.py refuses all three on
purpose; matching any of them would fabricate links.

So the money is reported instead of drawn, and this table is what the
screen reads.

WHY IT IS PRECOMPUTED
---------------------
The endpoint originally queried statement_transactions directly. It was
reverted the same day: FIR 0001/2026 at Bagalkot has 29 accounts and
66,055 statement rows and took 15.6 SECONDS on a 32 GB laptop, and a
gateway timeout on the 2-vCPU server. The aggregation was not the cost
-- the identical filter with no GROUP BY took the same 15.6 s. An index
on account_id gives row pointers and each fetch is a random read into a
27.6 GB table.

WHAT COUNTS AS A ROW HERE
-------------------------
A DEBIT, on a transfer channel, with a counterparty NAME, and with
NEITHER a counterparty account number NOR a UPI id -- the two things
that could have made it a link instead.

Cash and charges are excluded deliberately. The narration code for a
withdrawal is "CWDR", it survives name extraction, and on the first FIR
tested it was the single largest "recipient" at Rs 1.17 lakh across 165
rows. An ATM is not a person.

ONLY chain_ok = 1 IS SUMMED. The rest are counted in unverified_txns
and their money is added to nothing. Collapsing the two is what put a
quadrillion-rupee figure on a dashboard once already.

THE NAMES ARE NOT IDENTITIES. Banks truncate them ("ROHIT KUMA",
"ROHIT KUM", "ROHIT" are probably one person), operators mistype them,
and models/statement_transaction.py says plainly that this column must
never be a join key. They are grouped for DISPLAY. Nothing downstream
may treat two equal names as the same person.
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

from sqlalchemy import bindparam, text                   # noqa: E402

#: Transfer channels only. Everything else either has no counterparty
#: (charges, cash, ATM) or is not money leaving to a person.
CHANNELS = ("UPI", "IMPS", "NEFT", "RTGS", "TRANSFER")

#: Narration fragments that survive counterparty-name extraction and are
#: not people. enrich.py has _NOT_NAMES for the same job; these get
#: through because they are two words, or mixed case, or simply were not
#: on that list.
#:
#: Filtered HERE rather than in the parser on purpose. Widening the
#: parser changes what is written into 26.5 M rows and needs a full
#: re-parse to take effect; this only decides what one summary holds and
#: can be corrected by re-running this script.
NOT_A_COUNTERPARTY = {
    "upiintent", "fund tra", "fund tran", "paid via n", "paid via m",
    "paid via s", "paid via u", "sent using", "sent from", "payment fr",
    "payment to", "upi", "imps", "neft", "rtgs", "transfer", "cwdr",
    "na", "n a", "nil", "self", "req pay", "reqpay", "trans", "transfe",
    "mob", "mb", "ft", "fn", "collect", "merc", "w2b",
}

#: Accounts per pass. The whole point of this script is that the fact
#: table is only ever read in bounded slices -- a single unpartitioned
#: GROUP BY over 26.5 M rows is the thing being avoided, not just
#: relocated off the request path.
ACCOUNT_CHUNK = 300

#: MEASURED, and the reason --recent exists.
#:
#: One chunk of 300 accounts takes 63 SECONDS on a 32 GB laptop. Across
#: the 25,588 accounts that have a statement that is ~85 chunks, about
#: 90 minutes here and several hours on the 2-vCPU server -- far too
#: much to spend every night re-deriving rows that have not changed.
#:
#: So the nightly pass looks only at accounts whose statement rows were
#: parsed recently, exactly as build_crypto does. A full rebuild stays
#: available and is needed after any change to NOT_A_COUNTERPARTY or
#: CHANNELS, because --recent only refreshes the accounts it touches:
#: rows excluded by a withdrawn rule would otherwise sit there
#: indefinitely, indistinguishable from current ones.
FULL_REBUILD_NOTE = True


async def build(engine, dry_run: bool = False, recent_hours: int = 0) -> dict:
    # ONE TRANSACTION PER CHUNK, not one for the whole run.
    #
    # The first version took a connection from engine.begin() and did
    # everything inside it. Killed after two chunks it reported 26,559
    # rows processed and had written NOTHING -- the rollback took all of
    # it. On a run that takes hours, that means any interruption at hour
    # three costs three hours, and 1.5 M rows in a single transaction
    # would bloat the undo log besides.
    #
    # Committing per chunk is also what makes the comment below true
    # rather than aspirational: a run that dies halfway leaves the table
    # PARTIAL, and re-running REPLACEs what it redoes.
    if recent_hours:
        # FROM THE LEDGER, not from the fact table.
        #
        # The first version selected on statement_transactions.created_at,
        # which has no index -- so deciding what was "incremental"
        # scanned all 26.5 M rows before any useful work began, every
        # night. build_crypto already reads upload_ledger for exactly
        # this: 33 k rows, one per processed file, and processed_at is
        # what it is for.
        async with engine.connect() as c0:
            accounts = [str(r[0]) for r in (await c0.execute(text(
                "SELECT DISTINCT account_id FROM upload_ledger "
                "WHERE file_kind = 'statement' AND account_id IS NOT NULL "
                "AND processed_at >= NOW() - INTERVAL :h HOUR"),
                {"h": recent_hours})).all()]
        print(f"  {len(accounts):,} account(s) touched in {recent_hours}h",
              flush=True)
    else:
        async with engine.connect() as c0:
            accounts = [str(r[0]) for r in (await c0.execute(text(
                "SELECT DISTINCT account_id FROM account_statement_summary"))).all()]

    stats = {"accounts": len(accounts), "rows": 0, "written": 0,
             "unverified": 0, "mode": f"recent {recent_hours}h" if recent_hours
             else "full rebuild"}
    if not accounts:
        return stats

    stop = ",".join(f"'{w}'" for w in sorted(NOT_A_COUNTERPARTY))
    chans = ",".join(f"'{c}'" for c in CHANNELS)

    # REPLACE per chunk rather than TRUNCATE up front. A run that dies
    # halfway then leaves the table stale rather than empty, and stale
    # beats absent on a screen an officer is reading.
    for i in range(0, len(accounts), ACCOUNT_CHUNK):
        chunk = accounts[i:i + ACCOUNT_CHUNK]

        # One committed transaction per chunk. Read and write together,
        # so the rows written are the rows just read.
        async with engine.begin() as conn:
            rows = (await conn.execute(text(f"""
                SELECT t.account_id, t.counterparty_name, t.channel,
                       COUNT(*) AS txns,
                       SUM(CASE WHEN t.chain_ok = 1 THEN t.debit ELSE 0 END) AS ver,
                       SUM(CASE WHEN t.chain_ok <> 1 THEN 1 ELSE 0 END) AS unver
                FROM statement_transactions t
                WHERE t.account_id IN :ids
                  AND t.debit > 0
                  AND t.channel IN ({chans})
                  AND t.counterparty_name IS NOT NULL
                  AND t.counterparty_name <> ''
                  AND LOWER(t.counterparty_name) NOT IN ({stop})
                  AND (t.counterparty_account IS NULL OR t.counterparty_account = '')
                  AND (t.counterparty_upi IS NULL OR t.counterparty_upi = '')
                GROUP BY t.account_id, t.counterparty_name, t.channel
            """).bindparams(bindparam("ids", expanding=True)),
                {"ids": chunk})).all()

            stats["rows"] += len(rows)
            stats["unverified"] += sum(int(r[5] or 0) for r in rows)

            if rows and not dry_run:
                await conn.execute(text("""
                    REPLACE INTO account_unlinked_counterparty
                        (account_id, counterparty_name, channel, txns,
                         verified_debit, unverified_txns)
                    VALUES (:a, :n, :c, :t, :v, :u)
                """), [{"a": r[0], "n": r[1], "c": r[2], "t": int(r[3] or 0),
                        "v": float(r[4] or 0), "u": int(r[5] or 0)} for r in rows])
                stats["written"] += len(rows)

        done = min(i + ACCOUNT_CHUNK, len(accounts))
        print(f"  {done:,}/{len(accounts):,} accounts · "
              f"{stats['written']:,} rows written", flush=True)

    return stats


async def _main(dry_run: bool, recent_hours: int) -> int:
    from database import engine
    # build() manages its own transactions, one per chunk, so it takes
    # the engine rather than a connection. A single transaction around a
    # multi-hour run loses everything on any interruption.
    st = await build(engine, dry_run, recent_hours)
    await engine.dispose()
    print("=" * 60)
    print(f"  mode                        : {st['mode']}")
    print(f"  accounts examined           : {st['accounts']:,}")
    print(f"  named-but-unnumbered rows   : {st['rows']:,}")
    print(f"  written                     : {st['written']:,}")
    print(f"  txns excluded from the money: {st['unverified']:,}"
          f"   <- balance chain unverified")
    print("=" * 60)
    if dry_run:
        print("dry run: nothing written.")
    if st["mode"] != "full rebuild":
        print("  --recent only REFRESHES the accounts it touched. After")
        print("  changing NOT_A_COUNTERPARTY or CHANNELS, run a full")
        print("  rebuild or withdrawn rows stay on screen.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--recent", type=int, default=0, metavar="HOURS",
                    help="only accounts with rows parsed in the last N hours")
    a = ap.parse_args()
    sys.exit(asyncio.run(_main(a.dry_run, a.recent)))
