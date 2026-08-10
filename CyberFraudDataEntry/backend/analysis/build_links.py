#!/usr/bin/env python3
"""Find direct mule-to-mule transfers and store them (migration 021).

    python -m analysis.build_links              # rebuild
    python -m analysis.build_links --dry-run    # report, write nothing

HOW THE MATCH IS DONE, AND WHY IT IS NOT A JOIN
-----------------------------------------------
The obvious query is a join between statement_transactions and
all_accounts on the counterparty number. Two things make that useless
here.

1. SPELLING. A narration prints the number as the bank typed it —
   0000120003057362 where all_accounts holds 120003057362. Matching raw
   strings found 0.10% of destinations. Generating the zero-padded
   spellings of each mule number and looking THOSE up found 939
   connected accounts. The difference is the whole feature.

2. INDEXES. Normalising both sides in SQL —
   TRIM(LEADING '0' FROM ...) = TRIM(LEADING '0' FROM ...) — defeats
   ix_stmt_txn_cp_account and scans 10.4M rows. The first attempt at
   that had to be killed. So the normalisation happens in Python over
   the ~14k mule numbers (small), and the resulting spellings are looked
   up through the index in chunks.

BOTH ENDS MUST BE A MULE
------------------------
The destination is constrained by construction — it came from the mule
spelling table. The SOURCE is whatever account owns the statement, and
that is frequently a Victim or a Non-Mule. Forgetting to filter it
answers "who pays mules" rather than "which mules are connected", and
inflated the first measurement by 13%.
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

from sqlalchemy import bindparam, text                  # noqa: E402

PARSER_VERSION = "links-v1"

#: Spellings looked up per query. Small enough for the optimiser to use
#: the index, large enough to amortise the round trip.
CHUNK = 400

#: Zero-padded widths an Indian account number is printed at. Cheap to
#: over-generate: a spelling nothing matches simply finds no rows.
PAD_WIDTHS = (11, 12, 13, 14, 15, 16, 17, 18)

BATCH = 500


async def build(conn, dry_run: bool = False) -> dict:
    mules = (await conn.execute(text("""
        SELECT id, account_no, fir_no
        FROM all_accounts
        WHERE account_type = 'Mule'
          AND account_no IS NOT NULL AND account_no <> ''"""))).all()
    mule_ids = {m[0] for m in mules}
    fir_of = {m[0]: m[2] for m in mules}

    spell: dict[str, str] = {}
    for aid, no, _fir in mules:
        base = (no or "").strip()
        if not base:
            continue
        core = base.lstrip("0") or base
        for v in {base, core, *(core.zfill(w) for w in PAD_WIDTHS)}:
            # setdefault, not assignment: if two mule accounts collide on
            # a spelling the first wins deterministically rather than
            # whichever happened to be read last.
            spell.setdefault(v, aid)

    keys = list(spell)
    edges: dict[tuple[str, str], list] = {}
    for i in range(0, len(keys), CHUNK):
        rows = (await conn.execute(
            text("""
                SELECT t.account_id, t.counterparty_account,
                       COUNT(*), COALESCE(SUM(t.debit), 0),
                       MIN(t.txn_date), MAX(t.txn_date)
                FROM statement_transactions t
                WHERE t.counterparty_account IN :ks
                  AND t.debit IS NOT NULL
                GROUP BY t.account_id, t.counterparty_account
            """).bindparams(bindparam("ks", expanding=True)),
            {"ks": keys[i:i + CHUNK]})).all()
        for src, cp, n, amt, d0, d1 in rows:
            dst = spell.get(cp)
            if not dst or dst == src or src not in mule_ids:
                continue
            e = edges.setdefault((src, dst), [0, 0.0, None, None])
            e[0] += int(n)
            e[1] += float(amt or 0)
            if d0 and (e[2] is None or d0 < e[2]):
                e[2] = d0
            if d1 and (e[3] is None or d1 > e[3]):
                e[3] = d1

    cross = sum(1 for (s, d) in edges
                if fir_of.get(s) and fir_of.get(d) and fir_of[s] != fir_of[d])
    stats = {
        "overflowed": 0,
        "edges": len(edges),
        "cross_fir": cross,
        "src": len({s for s, _ in edges}),
        "dst": len({d for _, d in edges}),
        "accounts": len({x for e in edges for x in e}),
        "spellings": len(keys),
        "mules": len(mules),
    }
    if dry_run:
        return stats

    await conn.execute(text("DELETE FROM mule_account_link"))
    # total_debit is DECIMAL(18,2) — 16 integer digits. A link whose sum
    # exceeds that is carrying rows the balance chain would reject (the
    # ~Rs 44 billion misparses), and MySQL's response is to TRUNCATE the
    # value with a warning nobody reads. Clamping here turns a silent
    # wrong number into an explicit ceiling, and `overflowed` reports
    # how many links are affected so the UI can withhold their weight.
    LIMIT = 10.0 ** 16 - 0.01
    stats["overflowed"] = sum(1 for v in edges.values() if v[1] > LIMIT)
    payload = [{
        "s": s, "d": d, "n": v[0], "amt": min(v[1], LIMIT),
        "x": 1 if (fir_of.get(s) and fir_of.get(d)
                   and fir_of[s] != fir_of[d]) else 0,
        "sf": fir_of.get(s), "df": fir_of.get(d),
        "t0": v[2], "t1": v[3], "pv": PARSER_VERSION,
    } for (s, d), v in edges.items()]
    for k in range(0, len(payload), BATCH):
        await conn.execute(text("""
            INSERT INTO mule_account_link
                (src_account_id, dst_account_id, txns, total_debit, cross_fir,
                 src_fir_no, dst_fir_no, first_txn, last_txn, parser_version)
            VALUES (:s, :d, :n, :amt, :x, :sf, :df, :t0, :t1, :pv)
        """), payload[k:k + BATCH])
    return stats


async def _main(dry_run: bool) -> int:
    from database import engine
    async with engine.begin() as conn:
        st = await build(conn, dry_run)
    await engine.dispose()
    print("=" * 60)
    print(f"  mule accounts with a number : {st['mules']:,}")
    print(f"  spellings searched          : {st['spellings']:,}")
    print(f"  DIRECT mule -> mule links   : {st['edges']:,}")
    print(f"    crossing two FIRs         : {st['cross_fir']:,}"
          f"   <- cases nobody has connected")
    print(f"  paying mules                : {st['src']:,}")
    print(f"  receiving mules             : {st['dst']:,}")
    print(f"  mules in the network        : {st['accounts']:,}")
    if st.get("overflowed"):
        print(f"  !! {st['overflowed']} link(s) exceed DECIMAL(18,2) and were")
        print(f"     clamped — they carry rows the balance chain rejects.")
        print(f"     Their COUNTS are sound; their rupee totals are not.")
    print("=" * 60)
    if dry_run:
        print("dry run: nothing written.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    sys.exit(asyncio.run(_main(ap.parse_args().dry_run)))
