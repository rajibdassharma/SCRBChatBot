#!/usr/bin/env python3
"""Populate crypto_txn from parsed bank statements.

    python -m analysis.build_crypto            # full rebuild
    python -m analysis.build_crypto --dry-run  # report, write nothing
    python -m analysis.build_crypto --recent 48

Finds transactions whose narration names a crypto exchange or asset and
records them as their own rows, so the Crypto Analysis tab does not have
to scan 21 million transactions on every page load.

WHY THIS IS A BATCH JOB AND NOT A QUERY
statement_transactions is ~21M rows and ~25 GB against a 128 MB InnoDB
buffer pool, so any narration scan is disk-bound and takes minutes. Run
once here, the answer is a few thousand rows the dashboard reads
instantly. The same reasoning as mule_account_link -- see migration 021.

TWO STAGES, AND THE SPLIT MATTERS
MySQL applies a loose REGEXP built from analysis.parsers.crypto's
literal tokens; Python then applies the authoritative detect() to what
comes back. The SQL stage is a SUPERSET and is allowed to be sloppy. It
must never be the thing that decides -- that would put the false-positive
rules in two places, and this detector has already produced two rounds of
convincing false positives ("ASHOKX" read as OKX, a bank's joint-holder
field read as ETH).

FULL REBUILD BY DEFAULT
The detector's patterns change as false positives are found. An
incremental run would leave rows matched by a rule that has since been
withdrawn, and nothing on screen would distinguish them from current
ones. --recent exists for the daily cycle, where the patterns have not
moved and only new statements need scanning; it ADDS rows and never
removes, so it is not a substitute for a rebuild after a pattern change.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from sqlalchemy import bindparam, text                         # noqa: E402

from analysis.parsers.crypto import SQL_TOKENS, detect         # noqa: E402

PARSER_VERSION = "crypto-v1"

#: Rows per INSERT. Same size the statement parser flushes at, for the
#: same reason: big enough that round trips stop mattering, small enough
#: that one bad row does not roll back a long transaction.
BATCH = 500

#: Rows per SELECT page. The candidate set is small, but a statement
#: bank with a chatty narration format could still return a lot at once.
PAGE = 5000

#: Accounts per query in --recent mode. Matches summary.py's CHUNK for
#: the same reason: a literal id list of this size lets MySQL use
#: ix_stmt_txn_account, where an IN-subquery falls back to a full scan.
ACCOUNT_CHUNK = 200


def _regexp() -> str:
    """Loose alternation for the SQL stage. Literals only — the tokens
    carry no regex metacharacters, which is checked below rather than
    assumed, because a stray '.' would silently widen the scan."""
    for t in SQL_TOKENS:
        assert t.isalnum(), f"token {t!r} is not plain alphanumeric"
    return "|".join(SQL_TOKENS)


def _account_batches(ids: list[str]):
    for i in range(0, len(ids), ACCOUNT_CHUNK):
        yield ids[i:i + ACCOUNT_CHUNK]


async def build(conn, dry_run: bool = False, recent_hours: int = 0) -> dict:
    stats = {"scanned": 0, "matched": 0, "written": 0, "by_label": {},
             "rejected": 0, "reject_sample": []}

    where = ["t.description IS NOT NULL", "t.description REGEXP :rx"]
    params: dict = {"rx": _regexp()}
    # --recent scopes by ACCOUNT, not by source_file.
    #
    # source_file was the obvious choice and is unusable: that column
    # carries no index, so MySQL scanned all 21M rows anyway and the
    # incremental mode cost exactly what a full rebuild cost. account_id
    # has ix_stmt_txn_account, and the ids must be handed over as a
    # literal list per chunk -- an IN-subquery does not push into the
    # index. Same measurement as summary.py's _check().
    recent_ids: list[str] = []
    if recent_hours:
        recent_ids = [str(r[0]) for r in (await conn.execute(text(
            "SELECT DISTINCT account_id FROM upload_ledger "
            "WHERE file_kind = 'statement' AND account_id IS NOT NULL "
            "AND processed_at >= NOW() - INTERVAL :h HOUR"
        ), {"h": recent_hours})).all()]
        print(f"  {len(recent_ids):,} account(s) touched in {recent_hours}h")
        if not recent_ids:
            return stats

    if not dry_run and not recent_hours:
        # Full rebuild replaces the table's contents. Not TRUNCATE: this
        # runs inside the caller's transaction, and TRUNCATE would commit
        # it implicitly, so a failure halfway would leave the table empty
        # with no way back.
        await conn.execute(text("DELETE FROM crypto_txn"))

    # KEYSET paging, not OFFSET. With OFFSET, MySQL re-applies the
    # REGEXP from the first row on every page, so the run costs
    # pages x 21M rows -- fine while everything fits in one page, and
    # quadratic the moment it does not. Resuming from the last id seen
    # costs one forward scan however many rows match.
    sql = text(f"""
        SELECT t.id, t.account_id, t.txn_date, t.debit, t.credit,
               t.description, t.chain_ok
        FROM statement_transactions t
        WHERE {' AND '.join(where)} AND t.id > :after
        ORDER BY t.id
        LIMIT :lim
    """)

    chunked = text(f"""
        SELECT t.id, t.account_id, t.txn_date, t.debit, t.credit,
               t.description, t.chain_ok
        FROM statement_transactions t
        WHERE {' AND '.join(where)} AND t.account_id IN :ids
    """).bindparams(bindparam("ids", expanding=True))

    pending: list[dict] = []
    after = ""
    batches = _account_batches(recent_ids) if recent_hours else None
    while True:
        if batches is not None:
            part = next(batches, None)
            if part is None:
                break
            rows = (await conn.execute(chunked, {**params, "ids": part})).all()
        else:
            rows = (await conn.execute(
                sql, {**params, "lim": PAGE, "after": after})).all()
            if not rows:
                break
            after = str(rows[-1][0])
        stats["scanned"] += len(rows)

        for tid, aid, tdate, deb, cred, desc, chain in rows:
            label = detect(desc)
            if not label:
                # Reached the SQL filter, failed the real one. Counted
                # rather than dropped silently: a large number here means
                # the loose stage is doing too much work, and a zero
                # would mean the two stages have drifted into agreement,
                # which would make the Python stage decorative.
                stats["rejected"] += 1
                if len(stats["reject_sample"]) < 12:
                    stats["reject_sample"].append((desc or "")[:70])
                continue
            stats["matched"] += 1
            stats["by_label"][label] = stats["by_label"].get(label, 0) + 1
            pending.append({
                "id": str(uuid.uuid4()), "aid": str(aid), "tid": str(tid),
                "ex": label, "d": tdate, "deb": deb, "cr": cred,
                # The narration is stored so an officer can see WHY a row
                # was flagged without going back to the fact table. Given
                # this detector's history, "show me the evidence" is the
                # feature, not a nicety.
                "desc": (desc or "")[:500],
                "chain": int(chain) if chain is not None else -1,
                "pv": PARSER_VERSION,
            })

        if not dry_run and len(pending) >= BATCH:
            stats["written"] += await _flush(conn, pending)
            pending = []

    if pending and not dry_run:
        stats["written"] += await _flush(conn, pending)
    return stats


async def _flush(conn, rows: list[dict]) -> int:
    # INSERT IGNORE on the unique txn_id. --recent re-scans files whose
    # rows may already be recorded, and a duplicate there is expected
    # rather than exceptional.
    for i in range(0, len(rows), BATCH):
        await conn.execute(text("""
            INSERT IGNORE INTO crypto_txn
                (id, account_id, txn_id, exchange, txn_date, debit, credit,
                 description, chain_ok, parser_version)
            VALUES (:id, :aid, :tid, :ex, :d, :deb, :cr, :desc, :chain, :pv)
        """), rows[i:i + BATCH])
    return len(rows)


async def _main(dry_run: bool, recent: int) -> int:
    from database import engine

    t0 = time.time()
    mode = f"incremental ({recent}h)" if recent else "full rebuild"
    print(f"scanning statement narrations for crypto — {mode}")
    async with engine.begin() as conn:
        st = await build(conn, dry_run, recent)
    await engine.dispose()

    el = time.time() - t0
    print("=" * 60)
    print(f"  candidates from SQL      : {st['scanned']:,}")
    print(f"  confirmed by detect()    : {st['matched']:,}")
    print(f"  rejected as false match  : {st['rejected']:,}"
          f"   <- the loose stage doing its job")
    if st.get("reject_sample"):
        # Printed so the count above can be checked rather than trusted.
        print("\n  a sample of what was rejected — read these:")
        for d in st["reject_sample"]:
            print(f"      {d}")
    print(f"  rows written             : {st['written']:,}")
    if st["by_label"]:
        print("\n  by exchange / asset:")
        for k, n in sorted(st["by_label"].items(), key=lambda kv: -kv[1]):
            print(f"      {k:<12}{n:>8,}")
    print(f"\n  elapsed {el:.0f}s")
    print("=" * 60)
    if dry_run:
        print("dry run: nothing written.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be written, change nothing")
    ap.add_argument("--recent", type=int, default=0, metavar="HOURS",
                    help="only scan files processed in the last N hours; "
                         "ADDS rows, never removes — after a pattern "
                         "change do a full rebuild instead")
    a = ap.parse_args()
    sys.exit(asyncio.run(_main(a.dry_run, a.recent)))
