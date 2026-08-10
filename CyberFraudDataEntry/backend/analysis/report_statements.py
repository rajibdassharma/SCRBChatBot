#!/usr/bin/env python3
"""F2 report -- what came out of the parsed bank statements.

parse_statements.py fills statement_transactions. This is how you look
at it without a UI and without writing SQL.

Prints aggregates and per-account summaries. Account holder names and
account numbers ARE shown here, unlike the F1 report: this output is
for the officer working the case, on a machine inside the network, and
a money trail without the account it belongs to is not usable. Do not
paste it into a chat.

    python analysis/report_statements.py                 # overview
    python analysis/report_statements.py --account <id>  # one account
    python analysis/report_statements.py --top 20        # biggest movers
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

from sqlalchemy import text                       # noqa: E402
from database import engine                       # noqa: E402


def rupees(v) -> str:
    """Indian grouping, because every reader of this is Indian and
    12,34,567 parses at a glance where 1234567 does not."""
    if v is None:
        return "-"
    n = float(v)
    neg = n < 0
    s = f"{abs(n):.2f}"
    whole, frac = s.split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return ("-" if neg else "") + whole + "." + frac


async def overview(top: int) -> None:
    async with engine.begin() as c:
        row = (await c.execute(text("""
            SELECT COUNT(*) rows_, COUNT(DISTINCT account_id) accts,
                   COUNT(DISTINCT source_file) files,
                   MIN(txn_date) d0, MAX(txn_date) d1,
                   SUM(debit) dr, SUM(credit) cr
            FROM statement_transactions
        """))).first()
        if not row or not row.rows_:
            print("statement_transactions is empty — run "
                  "analysis/parse_statements.py first.")
            return

        led = {r[0]: r[1] for r in (await c.execute(text(
            "SELECT status, COUNT(*) FROM upload_ledger "
            "WHERE file_kind='statement' GROUP BY status"))).all()}
        total_files = sum(led.values()) or 1

        print("=" * 74)
        print("F2 -- PARSED BANK STATEMENTS")
        print("=" * 74)
        print(f"  transactions      {row.rows_:>14,}")
        print(f"  accounts covered  {row.accts:>14,}")
        print(f"  statements parsed {row.files:>14,}")
        print(f"  date range        {row.d0} to {row.d1}")
        print(f"  total debits      {rupees(row.dr):>14}")
        print(f"  total credits     {rupees(row.cr):>14}")
        print()
        print("  file outcomes:")
        for k in ("ok", "unverified", "scanned", "failed", "deferred"):
            if led.get(k):
                note = {
                    "ok": "balance chain reconciles",
                    "unverified": "rows stored, arithmetic does NOT agree",
                    "scanned": "image only — needs OCR",
                    "failed": "no transaction rows found",
                    "deferred": "not yet processed",
                }[k]
                print(f"    {led[k]:>6} ({100*led[k]/total_files:>4.1f}%)  "
                      f"{k:<11} {note}")

        print("\n" + "-" * 74)
        print("CHANNEL MIX")
        print("-" * 74)
        for r in (await c.execute(text("""
            SELECT COALESCE(channel,'(not identified)') k, COUNT(*) n,
                   SUM(debit) dr, SUM(credit) cr
            FROM statement_transactions GROUP BY k ORDER BY n DESC LIMIT 10
        """))).all():
            print(f"  {r.k:<18} {r.n:>9,}   out {rupees(r.dr):>18}   "
                  f"in {rupees(r.cr):>18}")

        print("\n" + "-" * 74)
        print(f"TOP {top} ACCOUNTS BY MONEY OUT")
        print("-" * 74)
        print(f"  {'holder':<26} {'PS':<20} {'txns':>6} "
              f"{'out':>16} {'in':>16}")
        for r in (await c.execute(text("""
            SELECT a.account_holder_name nm, p.station_name ps,
                   COUNT(*) n, SUM(t.debit) dr, SUM(t.credit) cr
            FROM statement_transactions t
            JOIN all_accounts a ON a.id = t.account_id
            LEFT JOIN police_stations p ON p.id = a.ps_id
            GROUP BY t.account_id, a.account_holder_name, p.station_name
            ORDER BY SUM(t.debit) DESC LIMIT :n
        """), {"n": top})).all():
            print(f"  {(r.nm or '-')[:25]:<26} {(r.ps or '-')[:19]:<20} "
                  f"{r.n:>6,} {rupees(r.dr):>16} {rupees(r.cr):>16}")

        print("\n" + "-" * 74)
        print(f"TOP {top} COUNTERPARTIES  (where the money went)")
        print("-" * 74)
        print("  Matched on account number and UPI handle, never on name —")
        print("  names are truncated and misspelt by the banks themselves.")
        print()
        print(f"  {'counterparty':<34} {'seen':>6} {'accounts':>9} {'total':>18}")
        for r in (await c.execute(text("""
            SELECT COALESCE(counterparty_upi, counterparty_account) k,
                   MAX(counterparty_name) nm,
                   COUNT(*) n, COUNT(DISTINCT account_id) a, SUM(debit) dr
            FROM statement_transactions
            WHERE debit IS NOT NULL
              AND (counterparty_upi IS NOT NULL OR counterparty_account IS NOT NULL)
            GROUP BY k HAVING COUNT(DISTINCT account_id) > 1
            ORDER BY a DESC, dr DESC LIMIT :n
        """), {"n": top})).all():
            label = f"{r.k[:24]} {(r.nm or '')[:9]}"
            print(f"  {label:<34} {r.n:>6,} {r.a:>9,} {rupees(r.dr):>18}")
        print()
        print("  'accounts' > 1 means the SAME counterparty received money")
        print("  from several different mule accounts — the F4 signal.")
        print("=" * 74)


async def one_account(account_id: str) -> None:
    async with engine.begin() as c:
        a = (await c.execute(text("""
            SELECT a.account_holder_name nm, a.account_no, a.bank_name,
                   a.fir_no, a.account_type, p.station_name ps
            FROM all_accounts a
            LEFT JOIN police_stations p ON p.id = a.ps_id
            WHERE a.id = :id"""), {"id": account_id})).first()
        if not a:
            print("no such account")
            return
        print("=" * 74)
        print(f"  {a.nm}   a/c {a.account_no}   {a.bank_name}")
        print(f"  {a.account_type} . FIR {a.fir_no} . {a.ps}")
        print("=" * 74)
        rows = (await c.execute(text("""
            SELECT txn_date, txn_time, debit, credit, balance, channel,
                   counterparty_name, counterparty_upi, counterparty_account,
                   description
            FROM statement_transactions WHERE account_id = :id
            ORDER BY txn_date, row_no LIMIT 200"""), {"id": account_id})).all()
        print(f"  {'date':<11} {'ch':<8} {'out':>14} {'in':>14} "
              f"{'balance':>14}  counterparty")
        for r in rows:
            cp = r.counterparty_upi or r.counterparty_account or \
                 r.counterparty_name or (r.description or "")[:28]
            print(f"  {str(r.txn_date):<11} {(r.channel or '-'):<8} "
                  f"{rupees(r.debit):>14} {rupees(r.credit):>14} "
                  f"{rupees(r.balance):>14}  {cp[:30]}")
        print(f"\n  showing {len(rows)} rows")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default="")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    async def go():
        if args.account:
            await one_account(args.account)
        else:
            await overview(args.top)
        await engine.dispose()

    asyncio.run(go())
    return 0


if __name__ == "__main__":
    sys.exit(main())
