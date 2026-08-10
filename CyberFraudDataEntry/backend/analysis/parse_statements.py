#!/usr/bin/env python3
"""F2 -- parse uploaded bank statements into statement_transactions.

Incremental: upload_ledger records what has been processed and at which
parser version, so a nightly run reads only what is new. Re-running is
safe and cheap; a file is re-parsed only when the parser version has
moved on.

RESOURCE BEHAVIOUR
------------------
Every unit of parallelism goes through analysis/runtime.py, which
budgets workers from FREE MEMORY rather than core count, holds a
reserve back for the OS and the shared-iGPU video pool, runs workers at
below-normal priority and recycles them periodically. That is not
tuning: an earlier version of this work ran 20 workers off core count
and bugchecked the development laptop three times in twenty minutes.
See runtime.py for the full account.

Very long statements are handled SEPARATELY, one at a time, after the
main pass. Memory here scales with page count, not file size — the
corpus tops out at 4 MB on disk but 1,787 pages — so one such document
running beside seven others is precisely the failure mode.

WHAT COUNTS AS PARSED
---------------------
Not "produced rows". A file is `ok` only when its own balance chain
reconciles; otherwise it is stored with status `unverified` and its
reconciliation rate, and is visible as such. Rows from an unverified
file are still written, because a lead an officer can eyeball beats no
lead — but nothing downstream may treat them as established.

    python analysis/parse_statements.py --dry-run          # parse, no writes
    python analysis/parse_statements.py --limit 200        # small real run
    python analysis/parse_statements.py                    # full, incremental
    python analysis/parse_statements.py --reparse          # ignore the ledger
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
STMT_DIR = os.path.join(BACKEND, "uploads", "statements")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from analysis import runtime as R                      # noqa: E402
from analysis.parsers import enrich as EN              # noqa: E402
from analysis.parsers import extract as EX             # noqa: E402
from analysis.parsers import verify as VF              # noqa: E402
from analysis import summary as SUM                    # noqa: E402

#: Bump when the parsers change in a way that alters output. The ledger
#: compares against this to decide what to re-read.
PARSER_VERSION = "stmt-v1"

#: Rows written per INSERT. 500 keeps each statement well under any
#: max_allowed_packet while still amortising round trips.
BATCH = 500

#: Flush to the database once this many parsed rows are held in the
#: PARENT. Bounded by rows and not by files on purpose: statements in
#: this corpus range from 5 rows to 11,153, so "40 files" is somewhere
#: between trivial and half a million row dicts. The parent is the one
#: process that runs for the whole job, so it is the one whose memory
#: must not drift.
FLUSH_ROWS = 20_000

#: ...or this many FILES, whichever comes first. Needed now that
#: zero-row results are queued too: a run through a stretch of scanned
#: images would otherwise accumulate thousands of ledger entries in the
#: parent without ever reaching the row threshold.
FLUSH_FILES = 400

#: Workers for the long-statement pass.
#:
#: Was 2, chosen when a worker was assumed to need 1.5 GB. Measured
#: since: a 1,128-page statement — the worst case in this corpus —
#: peaks at 0.08 GB, because extract._release() frees page caches as
#: the reader advances. Six workers is therefore ~0.5 GB against the
#: 10 GB reserve, and takes the pass from a measured 8.6 hours to
#: roughly 2.9 at 37s per file.
#:
#: Still deliberately below the main pass: these documents are 150+
#: pages each, and keeping them in their own smaller pool means a
#: pathological file cannot land beside a full complement of others.
LONG_WORKERS = 6

#: Memory budgeted per worker in the long pass. Kept beside
#: LONG_WORKERS deliberately: these two numbers only make sense
#: together, and separating them is how the 2.0 GB above went stale
#: without anyone noticing it was overriding the worker count.
PER_WORKER_LONG_GB = 0.5


def parse_one(path: str) -> dict:
    """Worker entry point. Module-level and picklable.

    Returns plain dicts, never ORM objects — the worker has no database
    connection and must not acquire one. All writes happen in the
    parent, which keeps the connection count at one regardless of how
    many workers are running.
    """
    name = os.path.basename(path)
    try:
        ex = EX.read(path)
        rec = VF.reconcile(ex.rows)
        rows = VF.apply_repair(ex.rows, rec)
        # Per-row verdicts computed HERE, at parse time, not by a later
        # pass. reconcile() has already walked this chain; row_verdicts
        # keeps the detail it discards.
        #
        # It must happen after apply_repair, so the verdicts describe
        # the rows as they will be STORED — repair may reverse the order
        # or exchange the amount columns, and a verdict computed before
        # that would be attached to the wrong row.
        #
        # Doing it at parse time is what keeps the nightly job to one
        # step. The summary is refreshed inline per flush and aggregates
        # on chain_ok, so a separate stamping pass would compute every
        # new account's totals from rows still marked untested — and
        # untested money is excluded, so every new account would read
        # zero until someone remembered to re-run it.
        verdicts = VF.row_verdicts(rows, rec)
        for t, v in zip(rows, verdicts):
            t.chain_ok = v
            EN.enrich(t)
        if ex.method == "deferred":
            status = "deferred"
        elif ex.method == "scanned":
            status = "scanned"
        elif not rows:
            status = "failed"
        elif rec.verified:
            status = "ok"
        else:
            status = "unverified"
        return {
            "file": name, "status": status, "method": ex.method,
            "pages": ex.pages, "truncated": ex.truncated,
            "reason": ex.reason,
            "rate": rec.rate, "swapped": rec.swapped,
            "reversed": rec.reversed_order,
            "rows": [_as_dict(t) for t in rows],
        }
    except Exception as exc:                            # noqa: BLE001
        return {"file": name, "status": "failed", "method": "", "pages": 0,
                "truncated": False, "reason": type(exc).__name__,
                "rate": None, "swapped": False, "reversed": False, "rows": []}


#: DECIMAL(18,2) holds 16 integer digits. values.parse_amount already
#: refuses anything larger, but this is the last point before the
#: database and the cost of being wrong here is a rolled-back batch of
#: 20,000 rows rather than one bad value — so it is checked twice.
_MAX_DECIMAL = 10.0 ** 16


def _fit(v):
    return v if v is not None and abs(v) < _MAX_DECIMAL else None


def _as_dict(t) -> dict:
    return {
        "row_no": t.row_no, "txn_date": t.txn_date, "txn_time": t.txn_time,
        "description": (t.description or "")[:500],
        "ref_no": (t.ref_no or None) and t.ref_no[:100],
        "debit": _fit(t.debit), "credit": _fit(t.credit),
        "balance": _fit(t.balance),
        "counterparty_account": t.counterparty_account,
        "counterparty_name": (t.counterparty_name or None)
                             and t.counterparty_name[:200],
        "counterparty_upi": (t.counterparty_upi or None)
                            and t.counterparty_upi[:120],
        "channel": t.channel,
        # Default UNTESTED, never PASSED: a row that somehow reached
        # here without a verdict has not been checked by anything, and
        # defaulting it to passed would admit it to the money totals.
        "chain": getattr(t, "chain_ok", VF.UNTESTED),
    }


# --------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="parse and report; write nothing")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=0,
                    help="UPPER BOUND only; the memory budget still applies")
    ap.add_argument("--reparse", action="store_true",
                    help="ignore the ledger and re-read everything")
    ap.add_argument("--retry-failed", action="store_true",
                    help="also re-attempt files that failed under this "
                         "parser version — use after fixing the ENVIRONMENT "
                         "(a missing dependency, an unreadable mount), where "
                         "the parser is unchanged but the outcome would be")
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(STMT_DIR)
                   if f.lower().endswith((".pdf", ".xls", ".xlsx")))

    done: set[str] = set()
    if not args.reparse and not args.dry_run:
        done = _already_done(retry_failed=args.retry_failed)
        if done:
            note = " (failures included for retry)" if args.retry_failed else ""
            print(f"ledger: {len(done):,} files already settled at "
                  f"{PARSER_VERSION}; skipping them{note}")
    todo = [f for f in files if f not in done]
    if args.limit:
        todo = todo[:args.limit]

    print(f"corpus {len(files):,} statements . to parse {len(todo):,}")
    print(f"memory {R.gb(R.available_bytes()):.1f} GB free of "
          f"{R.gb(R.total_bytes()):.1f} GB . reserving {R.RESERVE_GB:.0f} GB")
    if not todo:
        print("nothing to do")
        return 0

    paths = [os.path.join(STMT_DIR, f) for f in todo]
    stats: Counter = Counter()
    methods: Counter = Counter()
    reasons: Counter = Counter()
    verified = testable = total_rows = 0
    deferred: list[str] = []
    pending: list[dict] = []
    pending_rows = 0
    t0 = time.time()
    peak = 0

    def log(m):
        print(m, flush=True)

    for i, (path, res) in enumerate(
            R.governed_map(parse_one, paths,
                           requested_workers=args.workers, log=log), 1):
        if res is None:
            stats["worker-died"] += 1
            continue
        stats[res["status"]] += 1
        methods[res["method"] or "?"] += 1
        if not res["rows"] and res["status"] not in ("deferred",):
            reasons[res["reason"] or "(no reason recorded)"] += 1
        if res["status"] == "deferred":
            deferred.append(path)
        if res["rate"] is not None:
            testable += 1
            verified += 1 if res["status"] == "ok" else 0
        total_rows += len(res["rows"])
        if not args.dry_run:
            # Queued even with ZERO rows, so the ledger records that
            # this file was seen and why it yielded nothing.
            #
            # Previously only row-bearing results were queued, so
            # scanned and failed files never reached the ledger at all.
            # Two things broke quietly: they were re-parsed on every
            # run instead of being skipped, and the Statement Coverage
            # tab reported an "unreadable" count of 0 while 42 scanned
            # images sat in the corpus — the OCR queue was invisible
            # precisely because nothing recorded it.
            pending.append(res)
            pending_rows += len(res["rows"])
            if pending_rows >= FLUSH_ROWS or len(pending) >= FLUSH_FILES:
                _flush(pending)
                pending, pending_rows = [], 0
        peak = max(peak, R.rss_bytes())
        if i % 100 == 0:
            log(f"  {i:,}/{len(paths):,}  {time.time()-t0:.0f}s  "
                f"rows {total_rows:,}  free {R.gb(R.available_bytes()):.1f} GB")

    # Long statements, in a separate low-concurrency pass.
    #
    # Two workers, not one, and not the main pass's four. Measured
    # after extract._release() was added, a 1,128-page statement peaks
    # at 0.08 GB — page caches are now freed as the reader advances, so
    # page count no longer drives memory the way it did. What is left
    # is CPU: these files take ~28s each, and at one at a time they
    # were 61% of the wall clock for 4% of the files.
    #
    # Two is the compromise. It roughly halves the backfill while
    # keeping this pass's footprint (~0.2 GB) an order of magnitude
    # below the reserve, and it is still isolated from the main pass so
    # a pathological document cannot land beside three others.
    if deferred:
        # Never hardcode a worker count in a log line. This said
        # "2 workers" while the pass actually ran at 1, and reading my
        # own literal back as if it were a measurement cost two
        # restarts. governed_map prints what it really granted.
        log(f"\nlong-statement pass: {len(deferred)} file(s), "
            f"up to {LONG_WORKERS} workers")
        for path, res in R.governed_map(
                parse_one_long, deferred, requested_workers=LONG_WORKERS,
                # Same 0.5 GB budget the main pass uses, NOT a special
                # larger one. The 2.0 here was set when long files were
                # assumed to be memory-heavy; measurement says a
                # 1,128-page statement peaks at 0.08 GB because
                # extract._release() frees page caches as it reads.
                #
                # Leaving it at 2.0 silently capped this pass at two
                # workers however high LONG_WORKERS went — the budget
                # overrides the request by design, so a stale budget
                # quietly nullifies the setting above it.
                per_worker_gb=PER_WORKER_LONG_GB, chunk=8, log=log):
            if res is None:
                stats["worker-died"] += 1
                stats["deferred"] -= 1
                continue
            stats["deferred"] -= 1
            stats[res["status"]] += 1
            methods[res["method"] or "?"] += 1
            if res["rate"] is not None:
                testable += 1
                verified += 1 if res["status"] == "ok" else 0
            if not res["rows"]:
                reasons[res["reason"] or "(no reason recorded)"] += 1
            total_rows += len(res["rows"])
            if not args.dry_run:
                pending.append(res)
                pending_rows += len(res["rows"])
                if pending_rows >= FLUSH_ROWS or len(pending) >= FLUSH_FILES:
                    _flush(pending)
                    pending, pending_rows = [], 0
            log(f"    {os.path.basename(path)[:14]}... pg={res['pages']} "
                f"rows={len(res['rows']):,} status={res['status']} "
                f"free {R.gb(R.available_bytes()):.1f} GB")

    if pending and not args.dry_run:
        _flush(pending)

    el = time.time() - t0
    print("=" * 70)
    print(f"parsed {len(paths):,} files in {el:.0f}s "
          f"({el/max(1,len(paths)):.2f}s/file) . peak parent RSS "
          f"{R.gb(peak):.2f} GB")
    print(f"transactions extracted: {total_rows:,}")
    print("\nstatus:")
    for k, n in stats.most_common():
        if n:
            print(f"  {n:>6}  {k}")
    print("\nreader used:")
    for k, n in methods.most_common():
        print(f"  {n:>6}  {k}")
    if reasons:
        # Printed because a failure bucket is a work queue, not a
        # footnote. "no text layer" is the OCR phase; anything else
        # recurring is a layout the parser has not learned yet, and the
        # count says whether learning it is worth the effort.
        print("\nwhy files yielded nothing:")
        for k, n in reasons.most_common(10):
            print(f"  {n:>6}  {k}")
    if testable:
        print(f"\nRECONCILED {verified:,}/{testable:,} "
              f"({100*verified/testable:.1f}%) of files with a testable "
              f"balance chain")
        print("  files that do not reconcile are stored as 'unverified' —")
        print("  their rows are readable but must not be treated as fact.")
    if args.dry_run:
        print("\ndry run: nothing written.")
    print("=" * 70)
    return 0


def parse_one_long(path: str) -> dict:
    """A deferred long statement, parsed in-process with the cap raised.

    Runs in the parent with nothing else in flight, so the whole memory
    budget is available to this one document.
    """
    return _parse_with_defer(path, defer_pages=10 ** 9)


def _parse_with_defer(path: str, defer_pages: int) -> dict:
    old = EX.DEFER_PAGES
    try:
        EX.DEFER_PAGES = defer_pages
        return parse_one(path)
    finally:
        EX.DEFER_PAGES = old


# --------------------------------------------------------------------
# database
# --------------------------------------------------------------------

def _already_done(retry_failed: bool = False) -> set[str]:
    """Files this parser version has already reached a verdict on.

    'failed' IS a verdict, and that is the point of including it.

    It used to be excluded, so every run re-read every failure — and
    they are the most expensive files in the corpus, since a PDF is
    fully paged before it can be rejected. Measured 2026-08-10: 3,986
    permanent failures (encrypted, corrupt, or a layout with no
    readable table) re-read on every run, ~60 minutes a day producing
    a byte-for-byte identical result.

    The version filter is what makes this safe rather than merely
    fast. The claim recorded is "stmt-v1 could not read this file",
    which stays true until stmt-v1 changes — and bumping
    PARSER_VERSION re-attempts the whole corpus, which is exactly when
    a different outcome becomes possible.

    'deferred' stays absent on purpose: it means "set aside for the
    long pass", an unfinished state rather than a verdict, so an
    interrupted run must pick those up again.

    `retry_failed` forces failures back into scope for the case the
    version filter cannot see: an ENVIRONMENTAL failure. On 2026-08-07
    a missing pdfplumber failed 4,824 files under this same version,
    and without the flag recovering them would have meant faking a
    version bump.
    """
    import asyncio
    from sqlalchemy import text
    from database import engine

    states = "('ok','unverified','scanned')" if retry_failed \
        else "('ok','unverified','scanned','failed')"

    async def go() -> set[str]:
        async with engine.begin() as conn:
            rows = (await conn.execute(text(
                "SELECT file_path FROM upload_ledger "
                "WHERE file_kind = 'statement' AND parser_version = :pv "
                f"AND status IN {states}"
            ), {"pv": PARSER_VERSION})).all()
        await engine.dispose()
        return {os.path.basename(str(r[0]).replace("\\", "/")) for r in rows}

    try:
        return asyncio.run(go())
    except Exception as exc:                            # noqa: BLE001
        print(f"  (ledger unavailable: {type(exc).__name__} — parsing all)")
        return set()


#: Basename -> account_id, loaded once per process.
#:
#: Was re-read inside every flush. On a full backfill that is a
#: 14,702-row scan repeated several hundred times, for a mapping that
#: cannot change while the job runs.
_ACCOUNT_MAP: dict[str, str] | None = None


def _flush(results: list[dict]) -> None:
    """Write one batch of parsed statements: rows, then ledger.

    Resolves each file to its account via all_accounts.account_statement_path,
    keyed on basename for the same reason F1 does — the stored path is
    relative or absolute depending on when the row was written.

    Idempotent per file: rows already stored for these source files are
    deleted before the new ones go in. Without that, a re-run after a
    PARSER_VERSION bump — or any --reparse — silently DOUBLES every
    transaction, because statement_transactions has no unique key on
    (source_file, row_no) to reject the second copy. Duplicated rows
    would not look wrong; they would look like twice the money moving.
    """
    global _ACCOUNT_MAP
    import asyncio
    from sqlalchemy import bindparam, text
    from database import engine

    async def go():
        global _ACCOUNT_MAP
        async with engine.begin() as conn:
            if _ACCOUNT_MAP is None:
                acc = (await conn.execute(text(
                    "SELECT id, account_statement_path FROM all_accounts "
                    "WHERE account_statement_path IS NOT NULL "
                    "AND account_statement_path <> ''"
                ))).all()
                # Lowest id wins when several account rows reference the
                # SAME uploaded file — 31 statement files in this corpus
                # do. A plain dict comprehension is last-write-wins,
                # which disagreed with the MIN(id) rule in
                # analysis/relink.py: each run re-pointed rows the other
                # would point back, so `relink` never reached zero.
                _ACCOUNT_MAP = {}
                for a, pth in acc:
                    nm = os.path.basename(str(pth).replace("\\", "/"))
                    if nm not in _ACCOUNT_MAP or a < _ACCOUNT_MAP[nm]:
                        _ACCOUNT_MAP[nm] = a
            by_name = _ACCOUNT_MAP

            payload, ledger = [], []
            for res in results:
                aid = by_name.get(res["file"])
                fp = f"uploads/statements/{res['file']}"
                ledger.append({
                    "id": str(uuid.uuid4()), "fp": fp, "k": "statement",
                    "aid": aid, "st": res["status"],
                    "d": (res["reason"] or
                          (f"recon {res['rate']:.3f}" if res["rate"] is not None
                           else None)),
                    "n": len(res["rows"]), "pv": PARSER_VERSION,
                })
                if aid is None:
                    # No account owns this file. Rows would be
                    # unreachable and would break the FK, so only the
                    # ledger entry is kept — the orphan stays visible.
                    continue
                for r in res["rows"]:
                    payload.append({
                        "id": str(uuid.uuid4()), "aid": aid, "src": fp,
                        **r, "bt": res["method"], "pv": PARSER_VERSION,
                        # Stamped per row from this file's own
                        # reconciliation result, so the dashboard never
                        # has to re-derive it by matching paths.
                        "ver": 1 if res["status"] == "ok" else 0,
                    })

            # Clear any previous rows for these files first — see the
            # docstring on why a missing unique key makes this the only
            # thing standing between a re-run and doubled money.
            srcs = sorted({f"uploads/statements/{r['file']}" for r in results
                           if r["rows"]})
            for k in range(0, len(srcs), 200):
                chunk = srcs[k:k + 200]
                await conn.execute(
                    text("DELETE FROM statement_transactions "
                         "WHERE source_file IN :srcs").bindparams(
                             bindparam("srcs", expanding=True)),
                    {"srcs": chunk},
                )

            for k in range(0, len(payload), BATCH):
                await conn.execute(text("""
                    INSERT INTO statement_transactions
                        (id, account_id, source_file, row_no, txn_date, txn_time,
                         description, ref_no, debit, credit, balance,
                         counterparty_account, counterparty_name, counterparty_upi,
                         channel, verified, chain_ok, bank_template, parser_version)
                    VALUES
                        (:id, :aid, :src, :row_no, :txn_date, :txn_time,
                         :description, :ref_no, :debit, :credit, :balance,
                         :counterparty_account, :counterparty_name, :counterparty_upi,
                         :channel, :ver, :chain, :bt, :pv)
                """), payload[k:k + BATCH])

            # Refresh the summary for exactly the accounts just
            # written, inside the SAME transaction as the rows. If it
            # were a separate step the cache could be committed
            # describing rows that were rolled back, or lag behind them
            # after a crash — either way the dashboard would show
            # numbers no query could reproduce.
            touched = {r["aid"] for r in payload}
            if touched:
                n = await SUM.refresh(conn, touched)
                print(f"  summary refreshed: {len(touched)} accounts, {n} rows")

            for k in range(0, len(ledger), BATCH):
                await conn.execute(text("""
                    INSERT INTO upload_ledger
                        (id, file_path, file_kind, account_id, status, detail,
                         rows_extracted, parser_version, processed_at)
                    VALUES (:id, :fp, :k, :aid, :st, :d, :n, :pv, NOW()) AS new
                    ON DUPLICATE KEY UPDATE
                        account_id=new.account_id, status=new.status,
                        detail=new.detail,
                        rows_extracted=new.rows_extracted,
                        parser_version=new.parser_version,
                        processed_at=new.processed_at
                """), ledger[k:k + BATCH])
    # REQUIRED, not tidiness — and not something to "optimise away".
    #
    # _flush runs asyncio.run(), which builds and destroys an event
    # loop per call. Async pool connections are bound to the loop that
    # opened them, so a connection kept across two asyncio.run() calls
    # is attached to a loop that no longer exists. Removing this
    # dispose to save pool rebuilds produced, on the very next run:
    #     InternalError: network operation failed due to asyncmy
    #     attribute error
    # on a DELETE, several hundred files in. Rebuilding a small pool a
    # few hundred times over a multi-hour job costs nothing next to the
    # parsing itself.
    asyncio.run(go())
    asyncio.run(engine.dispose())


if __name__ == "__main__":
    sys.exit(main())
