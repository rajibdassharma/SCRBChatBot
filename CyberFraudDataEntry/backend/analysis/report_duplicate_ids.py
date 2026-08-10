#!/usr/bin/env python3
"""F1 report -- resolve duplicate ID images into accounts, FIRs and
police stations.

Clusters on SHA-256 -- byte-identical files -- NOT the perceptual
hash. An earlier version of this report used a 64-bit dHash and its
two headline clusters (28 and 23 documents) were both false: each held
28 and 23 DISTINCT files under as many different holder names. The
dHash had matched the Aadhaar template rather than the document. Exact
file identity cannot fail that way.

Same file is still not automatically a finding: the same image on one
account twice is a data-entry artefact, and one person legitimately
holding several accounts is not fraud. What makes it a finding is the
SPREAD -- one ID file behind several DIFFERENT account holders, across
several FIRs, in several police stations.

This ranks clusters by that spread, so the top of the list is the
strongest signal rather than the largest pile of files.

Prints aggregates and cluster shapes. Names and account numbers are
NOT printed -- the account id is enough to look the case up in the
portal, and this output may end up pasted into a chat or an email.

    python analysis/report_duplicate_ids.py [--min-accounts 2] [--top 25]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from sqlalchemy import text                       # noqa: E402
from database import engine                       # noqa: E402


async def run(min_accounts: int, top: int) -> None:
    async with engine.begin() as conn:
        rows = (await conn.execute(text("""
            SELECT h.file_sha256,
                   h.account_id,
                   a.account_holder_name,
                   a.account_no,
                   a.fir_no,
                   a.account_type,
                   u.name          AS district,
                   p.station_name  AS ps_name
            FROM id_photo_hashes h
            JOIN all_accounts a ON a.id = h.account_id
            LEFT JOIN units u           ON u.id = a.unit_id
            LEFT JOIN police_stations p ON p.id = a.ps_id
        """))).all()

    by_hash = defaultdict(list)
    for r in rows:
        by_hash[r.file_sha256].append(r)

    clusters = []
    for h, members in by_hash.items():
        accounts = {m.account_id for m in members}
        if len(accounts) < min_accounts:
            continue
        holders = {(m.account_holder_name or "").strip().lower()
                   for m in members if m.account_holder_name}
        acct_nos = {(m.account_no or "").strip() for m in members if m.account_no}
        firs = {m.fir_no for m in members if m.fir_no}
        pses = {m.ps_name for m in members if m.ps_name}
        dists = {m.district for m in members if m.district}
        types = {m.account_type for m in members if m.account_type}
        # A cluster containing VICTIM accounts is far more likely a
        # placeholder image than a mule farm: a network does not recruit
        # the people it defrauds. Left un-penalised such a cluster sits
        # at the top of the screen and teaches officers the feature is
        # noise.
        has_victim = "Victim" in types
        clusters.append({
            "hash": h, "images": len(members), "accounts": len(accounts),
            "holders": len(holders), "acct_nos": len(acct_nos),
            "firs": len(firs), "pses": len(pses), "districts": len(dists),
            "types": sorted(types), "ids": sorted(accounts),
            "has_victim": has_victim,
            # Lead term is the WEAKER of {account numbers, holder names}
            # — identity reuse needs both, and each alone has an
            # innocent reading. Kept identical to the ranking in
            # routes_dashboard.get_duplicate_ids so this report and the
            # dashboard can never disagree about what is at the top.
            "score": (0 if has_victim else 1,
                      min(len(acct_nos), len(holders), 50),
                      min(len(pses), 20), min(len(dists), 20),
                      min(len(acct_nos), 50), len(firs)),
        })

    clusters.sort(key=lambda c: c["score"], reverse=True)

    total_imgs = len(rows)
    multi = [c for c in clusters if c["accounts"] >= 2]
    # Identity reuse needs BOTH different account numbers and different
    # names. Different names on one account number is an operator typing
    # the same person several ways; different account numbers under one
    # name is a person's own accounts.
    reuse = [c for c in clusters
             if c["acct_nos"] >= 2 and c["holders"] >= 2 and not c["has_victim"]]
    reuse_fir = [c for c in reuse if c["firs"] >= 2]
    reuse_ps = [c for c in reuse if c["pses"] >= 2]

    print("=" * 74)
    print(f"ID images with a stored fingerprint : {total_imgs:,}")
    print(f"clustering on                       : SHA-256 (byte-identical)")
    print(f"clusters on >= {min_accounts} accounts            : {len(multi):,}")
    print(f"  IDENTITY REUSE (2+ a/c nos AND    : {len(reuse):,}")
    print(f"                  2+ holder names)")
    print(f"    ...spanning 2+ FIRs             : {len(reuse_fir):,}"
          f"   <- not one case's shared attachment")
    print(f"    ...spanning 2+ police stations  : {len(reuse_ps):,}"
          f"   <- not one operator's habit")
    print("=" * 74)

    if not clusters:
        print("\nno clusters met the threshold.")
        await engine.dispose()
        return

    print(f"\nTOP {min(top, len(clusters))} BY IDENTITY-REUSE STRENGTH")
    print(f"{'#':>3}  {'imgs':>4} {'accts':>5} {'names':>5} {'a/cs':>4} "
          f"{'FIRs':>4} {'PS':>3} {'dist':>4}  types")
    print("-" * 74)
    for i, c in enumerate(clusters[:top], 1):
        print(f"{i:>3}  {c['images']:>4} {c['accounts']:>5} {c['holders']:>5} "
              f"{c['acct_nos']:>4} {c['firs']:>4} {c['pses']:>3} {c['districts']:>4}"
              f"  {','.join(c['types'])}")

    # Cross-FIR, not cross-PS. Cross-PS was the earlier bar and it set
    # itself too high: a recruiter operating in one station's area
    # produces a single-station cluster, and that is a narrower case,
    # not a weaker one. Cross-FIR is the bar that actually matters here
    # — it rules out the one innocent explanation that survives
    # everything else, an officer attaching the same file to every
    # account in a single case.
    strong = [c for c in reuse if c["firs"] >= 2]
    print(f"\nSTRONGEST SIGNAL — one ID file, 2+ different account numbers,")
    print(f"2+ different holder names, 2+ FIRs: {len(strong)} cluster(s)")
    for c in strong[:10]:
        print(f"   {c['holders']} names / {c['accounts']} accounts / "
              f"{c['firs']} FIRs / {c['pses']} stations / {c['districts']} districts")
        print(f"      account ids: {', '.join(c['ids'][:6])}"
              + (f" (+{len(c['ids'])-6} more)" if len(c["ids"]) > 6 else ""))
    print("\nNOTE: a shared FILE is a LEAD, not proof. It can also be one")
    print("person with several accounts, or an operator attaching the same")
    print("file twice. Verify each cluster in the portal before acting.")
    await engine.dispose()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-accounts", type=int, default=2)
    ap.add_argument("--top", type=int, default=25)
    a = ap.parse_args()
    asyncio.run(run(a.min_accounts, a.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
