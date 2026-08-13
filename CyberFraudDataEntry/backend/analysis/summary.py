"""Maintain account_statement_summary (migration 020).

One function, used from two places: the parser calls it for the
accounts it just wrote, and a CLI rebuilds everything after a backfill
or a parser-version change.

CORRECTNESS RULE
----------------
The summary is a cache of statement_transactions and nothing else. It
is always rebuilt by DELETE-then-INSERT for the accounts in scope,
never incremented in place. Incremental arithmetic on a cache is how
caches drift: re-parse a file, add its rows again, and every total is
silently doubled with nothing to catch it. Recomputing an account is
cheap -- it touches only that account's rows -- and it cannot drift.

    python -m analysis.summary              # rebuild every account
    python -m analysis.summary --check      # verify accounts touched in 48h
    python -m analysis.summary --check-all  # verify EVERY account (slow)
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from sqlalchemy import bindparam, text                  # noqa: E402

#: Accounts per DELETE/INSERT round trip when rebuilding a subset.
CHUNK = 200

#: The aggregate itself, in ONE place. Both the refresh and the --check
#: comparison read from this, so the cache can never be validated
#: against a different definition than the one that built it.
#: chain_ok, NOT the file-level `verified` flag.
#:
#: `verified` says the SOURCE STATEMENT reconciled at >= 98%. That was
#: being used to vouch for every row inside it, and 29 rows within one
#: file scoring 99.22% carried Rs 205,642,955,681 of a
#: Rs 205,648,905,136 total. chain_ok is that row's own verdict:
#:
#:    1  passed    the arithmetic agrees      -> summed as money
#:    0  rejected  the arithmetic disagrees   -> excluded entirely
#:   -1  untested  nothing to test against    -> excluded, counted apart
#:
#: Untested is tracked separately rather than folded into either side.
#: Rejected money is wrong; untested money is unknown, and a statement
#: whose bank never prints a running balance deserves the second word,
#: not the first.
_AGG = """
    SELECT t.account_id,
           COALESCE(t.channel, '')                             AS channel,
           COUNT(*)                                            AS txns,
           COALESCE(SUM(t.debit), 0)                           AS debit,
           COALESCE(SUM(t.credit), 0)                          AS credit,
           COALESCE(SUM(t.chain_ok = 1), 0)                    AS verified_txns,
           COALESCE(SUM(CASE WHEN t.chain_ok = 1 THEN t.debit END), 0)  AS verified_debit,
           COALESCE(SUM(CASE WHEN t.chain_ok = 1 THEN t.credit END), 0) AS verified_credit,
           MIN(t.chain_ok = 1)                                 AS all_verified,
           COALESCE(SUM(t.chain_ok = -1), 0)                   AS untested_txns,
           COALESCE(SUM(CASE WHEN t.chain_ok = -1 THEN t.debit END), 0)  AS untested_debit,
           COALESCE(SUM(CASE WHEN t.chain_ok = -1 THEN t.credit END), 0) AS untested_credit,
           MIN(t.txn_date)                                     AS first_txn,
           MAX(t.txn_date)                                     AS last_txn,
           MAX(t.parser_version)                               AS parser_version
    FROM statement_transactions t
    {where}
    GROUP BY t.account_id, COALESCE(t.channel, '')
"""


async def refresh(conn, account_ids=None) -> int:
    """Rebuild summary rows. `account_ids=None` means every account.

    Returns the number of summary rows written. Runs inside the
    caller's transaction so a partial refresh can never be committed
    beside the rows it was meant to describe.
    """
    if account_ids is not None:
        ids = sorted(set(account_ids))
        if not ids:
            return 0
        written = 0
        for i in range(0, len(ids), CHUNK):
            batch = ids[i:i + CHUNK]
            for stmt in (
                "DELETE FROM account_statement_summary WHERE account_id IN :ids",
            ):
                await conn.execute(
                    text(stmt).bindparams(bindparam("ids", expanding=True)),
                    {"ids": batch},
                )
            r = await conn.execute(
                text(_INSERT.format(
                    agg=_AGG.format(where="WHERE t.account_id IN :ids"))
                ).bindparams(bindparam("ids", expanding=True)),
                {"ids": batch},
            )
            written += r.rowcount or 0
        return written

    await conn.execute(text("DELETE FROM account_statement_summary"))
    r = await conn.execute(text(_INSERT.format(agg=_AGG.format(where=""))))
    return r.rowcount or 0


_INSERT = """
    INSERT INTO account_statement_summary
        (account_id, channel, txns, debit, credit,
         verified_txns, verified_debit, verified_credit,
         all_verified, untested_txns, untested_debit, untested_credit,
         first_txn, last_txn, parser_version)
    {agg}
"""


#: Accounts whose files were processed within this window are the ones
#: a just-finished run could have got wrong. Generous enough to cover a
#: long overnight run plus the gap before someone looks at it.
RECENT_HOURS = 48

async def _recent_accounts(conn, hours: int) -> list[str]:
    """Accounts whose files were processed within `hours`."""
    rows = (await conn.execute(text(
        "SELECT DISTINCT account_id FROM upload_ledger "
        "WHERE account_id IS NOT NULL "
        "AND processed_at >= NOW() - INTERVAL :h HOUR"
    ), {"h": hours})).all()
    return [str(r[0]) for r in rows]


async def _check(conn, full: bool = False, hours: int = RECENT_HOURS) -> int:
    """Compare the cache against a live aggregate. Returns mismatches.

    Worth having as a command rather than a comment: this table is the
    only thing the dashboard reads, so "is it still true?" needs an
    answer that does not involve trusting that every write path
    remembered to call refresh().

    SCOPED BY DEFAULT, because the full comparison re-aggregates every
    row in statement_transactions — 17.8M of them, ~7 minutes — and on
    a job meant to run daily that was its single largest fixed cost.
    Nothing a run just did can be wrong outside the accounts that run
    touched, so the daily check verifies those and finishes in seconds.

    `full=True` re-checks everything. That is the one that would catch
    drift introduced earlier and never noticed, so it is still worth
    running — weekly, or after any manual surgery on the tables — just
    not before breakfast every day.
    """
    live: dict = {}
    cached: dict = {}

    if full:
        # Say what is about to happen, because nothing else will.
        #
        # This branch is ONE aggregate over the whole fact table: no
        # WHERE, so no index, so a full scan plus a 21M-row GROUP BY
        # through a 128 MB buffer pool. There is no chunk boundary to
        # report from and no row counter to read -- the process simply
        # sits silent until MySQL returns, measured at ~10 minutes on
        # the 2026-08-13 corpus. Printing the shape of the wait is the
        # only progress available, and it beats leaving someone to
        # wonder whether the job has hung.
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM statement_transactions"))).scalar() or 0
        print(f"  scope: ALL accounts — one aggregate over {n:,} rows")
        print("  this runs silent for several minutes (~10 at 21M rows); "
              "it has not hung", flush=True)
        t_full = time.time()
        live = {(r[0], r[1]): (int(r[2]), float(r[3]), float(r[4]))
                for r in (await conn.execute(
                    text(_AGG.format(where="")))).all()}
        print(f"  aggregate returned in {time.time() - t_full:.0f}s",
              flush=True)
        cached = {(r[0], r[1]): (int(r[2]), float(r[3]), float(r[4]))
                  for r in (await conn.execute(text(
                      "SELECT account_id, channel, txns, debit, credit "
                      "FROM account_statement_summary"))).all()}
    else:
        ids = await _recent_accounts(conn, hours)
        print(f"  scope: {len(ids):,} account(s) touched in {hours}h")
        if not ids:
            print("  nothing touched — nothing to verify")
            return 0
        # CHUNKED EXPLICIT IDS, not an IN-subquery.
        #
        # The obvious form -- `WHERE account_id IN (SELECT ... FROM
        # upload_ledger WHERE processed_at >= ...)` -- reads better and
        # is much slower: MySQL would not push it into
        # ix_stmt_txn_account, so it re-scanned the fact table anyway.
        # Measured 2026-08-10: 1m42s to check 2% of accounts, against
        # ~7m to check all of them. Handing it a literal id list per
        # chunk lets the index do its job, the same way refresh() does.
        n_chunks = (len(ids) + CHUNK - 1) // CHUNK
        t_chunks = time.time()
        print(f"  {n_chunks} chunk(s) of {CHUNK}", flush=True)
        for k in range(0, len(ids), CHUNK):
            part = ids[k:k + CHUNK]
            q = text(_AGG.format(where="WHERE t.account_id IN :ids")).bindparams(
                bindparam("ids", expanding=True))
            for r in (await conn.execute(q, {"ids": part})).all():
                live[(r[0], r[1])] = (int(r[2]), float(r[3]), float(r[4]))
            cq = text(
                "SELECT account_id, channel, txns, debit, credit "
                "FROM account_statement_summary WHERE account_id IN :ids"
            ).bindparams(bindparam("ids", expanding=True))
            for r in (await conn.execute(cq, {"ids": part})).all():
                cached[(r[0], r[1])] = (int(r[2]), float(r[3]), float(r[4]))
            # Progress on every chunk, with an ETA from THIS run's own
            # rate. Without it the only way to judge how far along a
            # 60-minute check is, is to watch the server's process list
            # and infer the chunk position -- which cannot be done
            # accurately, because the scope count is fixed at startup
            # while the 48h window it came from keeps sliding.
            j = k // CHUNK + 1
            el = time.time() - t_chunks
            eta = (el / j) * (n_chunks - j)
            print(f"  [{j}/{n_chunks}] {el:.0f}s elapsed"
                  f" . ~{int(eta // 60)}m{int(eta % 60):02d}s left"
                  f" . {len(live):,} live groups so far", flush=True)
    bad = 0
    for k in set(live) | set(cached):
        if live.get(k) != cached.get(k):
            bad += 1
            if bad <= 5:
                print(f"  MISMATCH {k}: live={live.get(k)} cached={cached.get(k)}")
    print(f"  {len(live):,} live groups, {len(cached):,} cached, {bad} mismatched")
    return bad


async def _main() -> int:
    from database import engine
    full = "--check-all" in sys.argv
    check = full or "--check" in sys.argv
    async with engine.begin() as conn:
        if check:
            print("checking account_statement_summary against source rows")
            bad = await _check(conn, full=full)
            code = 1 if bad else 0
        else:
            n = await refresh(conn)
            print(f"rebuilt account_statement_summary: {n:,} rows")
            code = 0
    await engine.dispose()
    return code


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
