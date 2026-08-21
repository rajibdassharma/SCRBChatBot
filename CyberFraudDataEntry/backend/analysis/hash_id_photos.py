#!/usr/bin/env python3
"""F1 -- find the same ID image backing accounts that claim to be
different people.

WHAT THIS DETECTS
-----------------
A mule farm reuses documents. If one Aadhaar image is attached to six
accounts across four police stations, those are not six people. Nothing
in the portal can see that today, because each upload is only ever
looked at on its own account page.

WHAT IT DOES NOT DO
-------------------
It reads no text. No name, no Aadhaar number, no date of birth, nothing
from the face. It reduces each image to fingerprints and compares those.

That matters for two reasons: the finding needs no OCR and therefore no
legal sign-off on identity extraction, and the stored artefact is a
hash, not a person's identity document.

TWO SIGNALS, DELIBERATELY UNEQUAL
---------------------------------
1. SHA-256 of the file bytes -- EXACT. Two accounts with the same
   SHA-256 have the same file attached. Unambiguous.

2. dHash at 24x24 (576 bits) -- SIMILAR. Greyscale, resize to 25x24,
   compare each pixel with its right-hand neighbour: brighter = 1.
   Survives re-compression and resizing, so it catches a document
   re-photographed or re-saved rather than re-uploaded.

WHY 24x24 AND NOT THE TEXTBOOK 8x8
----------------------------------
Because 8x8 does not work on identity documents, and it fails in a way
that looks like a result.

ID cards are near-identical by design: same emblem in the same corner,
same colour bands, same photo box, same field positions. An 8x8 hash
encodes little more than that layout. Measured on this corpus, 8x8
produced a 28-file "cluster" that on inspection held 28 DISTINCT
SHA-256s and 28 different holder names -- it had matched the Aadhaar
template, not the document. A second 23-file cluster failed the same
way.

At 24x24 those two clusters separate into 28 and 23 singletons, while
the clusters that were genuinely one file re-attached stay welded
together at every resolution tested (8x8 through 24x24). So 24x24 does
not merely reduce false positives; it distinguishes the two cases.

HOW TO READ THE OUTPUT
----------------------
  SAME FILE       Same SHA-256. A finding.
  NEAR-DUPLICATE  Different SHA-256, close dHash. A lead -- must be
                  eyeballed before it means anything.

USAGE
    python analysis/hash_id_photos.py --dry-run     # no DB, report only
    python analysis/hash_id_photos.py               # write to DB, incremental
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
PHOTO_DIR = os.path.join(BACKEND, "uploads", "photos")

# Running this as `python analysis/hash_id_photos.py` puts analysis/ on
# sys.path, not backend/ — so `import database` fails. Add the backend
# root explicitly so the script works from any working directory.
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from analysis import runtime as RT                      # noqa: E402

#: Bump when the fingerprint changes, so stored rows can be re-derived
#: selectively instead of wiping the table. v1 was a 64-bit dHash and
#: its clusters were not trustworthy; see the module docstring.
PARSER_VERSION = "idhash-v2"

#: Side of the dHash grid. 24 -> 24*24 = 576 bits, 144 hex chars.
HASH_SIZE = 24

#: Bits of the 576 that may differ and still count as the same document.
#: 20 bits is ~3.5%. Chosen conservatively: the job of this threshold is
#: no longer to find duplicates (SHA-256 does that exactly) but to
#: surface re-saved copies, so a miss is cheap and a false hit is not.
NEAR_THRESHOLD = 20


def fingerprint(path: str, size: int = HASH_SIZE):
    """(sha256, dhash_hex, width, height) — or None if unreadable."""
    from PIL import Image
    try:
        with open(path, "rb") as fh:
            sha = hashlib.sha256()
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                sha.update(chunk)
        with Image.open(path) as im:
            w, h = im.size
            g = im.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
            px = list(g.getdata())
            bits = 0
            for row in range(size):
                base = row * (size + 1)
                for col in range(size):
                    bits <<= 1
                    if px[base + col] > px[base + col + 1]:
                        bits |= 1
            return sha.hexdigest(), f"{bits:0{size * size // 4}x}", w, h
    except Exception:                              # noqa: BLE001
        return None


def _hash_one(path: str):
    return (os.path.basename(path), fingerprint(path))


def hamming(a: str, b: str) -> int:
    """Bit distance between two hex fingerprints.

    Kept for callers and tests that hold hex. The clustering path below
    does NOT use it: it parses every fingerprint to an int once and
    compares ints, because this function re-parses a 144-character hex
    string twice on every call and the seed loop calls it hundreds of
    millions of times.
    """
    return (int(a, 16) ^ int(b, 16)).bit_count()


#: Bands for candidate generation. See _band_keys.
#:
#: PIGEONHOLE, not a heuristic. Split 576 bits into 24 bands of 24. Two
#: fingerprints within NEAR_THRESHOLD (20) bits can differ in at most 20
#: bands, so at least 4 bands are IDENTICAL. Bucketing by band therefore
#: finds every genuine pair -- there are no false negatives to trade
#: away, which is why this is safe on evidence.
#:
#: Requires BANDS > threshold. Asserted in cluster().
BANDS = 24
BAND_BITS = (HASH_SIZE * HASH_SIZE) // BANDS
_BAND_MASK = (1 << BAND_BITS) - 1


def _band_keys(v: int) -> tuple:
    return tuple((v >> (i * BAND_BITS)) & _BAND_MASK for i in range(BANDS))


def cluster(hashes: dict[str, str], threshold: int) -> list[list[str]]:
    """Group files whose fingerprints are within `threshold` bits.

    NOT transitive closure. An earlier version used union-find, which
    chains A~B, B~C, C~D into one cluster even when A and D are nothing
    like each other — on this corpus that merged unrelated images into
    a bogus cluster of 363. Seed-based instead: the first unassigned
    fingerprint becomes a seed, and only fingerprints within
    `threshold` OF THAT SEED join it. Every member is therefore
    genuinely close to a single reference image.

    Exact matches (threshold 0) are bucketed first, which is O(n).
    """
    by_hash: dict[str, list[str]] = defaultdict(list)
    for f, h in hashes.items():
        by_hash[h].append(f)
    if threshold <= 0:
        return [sorted(v) for v in by_hash.values() if len(v) > 1]

    distinct = sorted(by_hash, key=lambda h: -len(by_hash[h]))

    # Parse each fingerprint ONCE. The previous version called
    # hamming(), which re-parsed both 144-character hex strings on every
    # comparison -- with ~20,000 distinct fingerprints that is ~400
    # million hex parses, and it is where the four hours went.
    ints = {h: int(h, 16) for h in distinct}

    # Candidate generation by band. Without it this loop is O(d^2):
    # 21,272 photos today, and the corpus is growing ~20,000 a month, so
    # the all-pairs version stops fitting in a night within about two
    # months.
    assert BANDS > threshold, (
        f"BANDS ({BANDS}) must exceed threshold ({threshold}) or the "
        f"pigeonhole argument fails and pairs would be missed")
    rank = {h: i for i, h in enumerate(distinct)}
    buckets: dict[tuple, list[str]] = defaultdict(list)
    for h in distinct:
        for i, b in enumerate(_band_keys(ints[h])):
            buckets[(i, b)].append(h)

    used: set[str] = set()
    out: list[list[str]] = []
    for seed in distinct:
        if seed in used:
            continue
        members = [seed]
        used.add(seed)
        seed_int = ints[seed]
        cand: set = set()
        for i, b in enumerate(_band_keys(seed_int)):
            cand.update(buckets[(i, b)])
        # Same visiting order as the old all-pairs loop, so the output
        # is byte-identical rather than merely equivalent.
        for other in sorted(cand, key=rank.__getitem__):
            if other in used:
                continue
            if (seed_int ^ ints[other]).bit_count() <= threshold:
                members.append(other)
                used.add(other)
        files: list[str] = []
        for h in members:
            files.extend(by_hash[h])
        if len(files) > 1:
            out.append(sorted(files))
    return out


def _self_test(trials: int = 300) -> int:
    """Banding must find every pair brute force finds.

    A banding mistake -- too few bands, a wrong shift, a threshold
    raised past BANDS -- does not raise. It silently stops comparing
    some pairs, and the visible result is FEWER duplicate-ID clusters,
    which looks like good news. This checks the pigeonhole property
    holds against brute force on data built to stress it.

    Run: python -m analysis.hash_id_photos --self-test
    """
    import random
    bits = HASH_SIZE * HASH_SIZE
    rnd = random.Random(7)
    bad = 0

    for t in range(trials):
        base = rnd.getrandbits(bits)
        hexes = {}
        # A base, plus neighbours at known distances either side of the
        # threshold, plus unrelated noise.
        for i, flips in enumerate((0, 1, NEAR_THRESHOLD - 1, NEAR_THRESHOLD,
                                   NEAR_THRESHOLD + 1, bits // 3)):
            v = base
            for b in rnd.sample(range(bits), flips):
                v ^= (1 << b)
            hexes[f"f{t}_{i}.jpg"] = f"{v:0{bits // 4}x}"
        for j in range(4):
            hexes[f"n{t}_{j}.jpg"] = f"{rnd.getrandbits(bits):0{bits // 4}x}"

        banded = cluster(hexes, NEAR_THRESHOLD)

        # Brute force, same seed order, no banding.
        by_hash = {}
        for f, h in hexes.items():
            by_hash.setdefault(h, []).append(f)
        distinct = sorted(by_hash, key=lambda h: -len(by_hash[h]))
        used, brute = set(), []
        for seed in distinct:
            if seed in used:
                continue
            members = [seed]
            used.add(seed)
            for other in distinct:
                if other in used:
                    continue
                if hamming(seed, other) <= NEAR_THRESHOLD:
                    members.append(other)
                    used.add(other)
            files = []
            for h in members:
                files.extend(by_hash[h])
            if len(files) > 1:
                brute.append(sorted(files))

        if banded != brute:
            bad += 1
            if bad <= 3:
                sb = {tuple(c) for c in brute}
                sn = {tuple(c) for c in banded}
                print(f"  FAIL trial {t}: missed {len(sb - sn)} cluster(s), "
                      f"extra {len(sn - sb)}")

    assert BANDS > NEAR_THRESHOLD, (
        f"BANDS ({BANDS}) must exceed NEAR_THRESHOLD ({NEAR_THRESHOLD})")
    print(f"  {trials - bad}/{trials} trials match brute force "
          f"(BANDS={BANDS}, {BAND_BITS} bits each, threshold={NEAR_THRESHOLD})")
    return bad


def is_degenerate(h: str) -> bool:
    """A blank or near-uniform image has almost no gradient, so its
    dHash collapses to nearly all 0s or all 1s. Those match each other
    for reasons that have nothing to do with being the same document.

    Cut at 6.25% of the bits from either end, the same proportion the
    64-bit version used."""
    nbits = len(h) * 4
    edge = nbits // 16
    ones = bin(int(h, 16)).count("1")
    return ones <= edge or ones >= nbits - edge


def _stored_hashes() -> dict[str, tuple[str, str, int, int, str]]:
    """Fingerprints already computed at this version, by file name.

    Value is (sha256, dhash, width, height, account_id). The account
    is carried so the writer can tell an unchanged row from one whose
    owner moved, and skip the former.

    Returns {} on any failure — a first run has no table yet, and a
    read problem here should cost time (a full re-hash) rather than
    correctness.
    """
    import asyncio
    from sqlalchemy import text
    from database import engine

    async def go() -> dict[str, tuple[str, str, int, int, str]]:
        async with engine.begin() as conn:
            rows = (await conn.execute(text(
                "SELECT file_path, file_sha256, dhash, width, height, "
                "       account_id "
                "FROM id_photo_hashes WHERE parser_version = :pv "
                "AND file_sha256 IS NOT NULL AND dhash IS NOT NULL"
            ), {"pv": PARSER_VERSION})).all()
        await engine.dispose()
        return {
            os.path.basename(str(r[0]).replace("\\", "/")):
                (str(r[1]), str(r[2]), int(r[3] or 0), int(r[4] or 0),
                 str(r[5]) if r[5] is not None else "")
            for r in rows
        }

    try:
        return asyncio.run(go())
    except Exception as exc:                            # noqa: BLE001
        print(f"  (could not read stored hashes: {exc}; hashing all)")
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="hash and report only; touch no database")
    ap.add_argument("--threshold", type=int, default=NEAR_THRESHOLD)
    ap.add_argument("--self-test", action="store_true",
                    help="check banded clustering against brute force")
    # 0 = let the memory budget decide. An explicit value is an UPPER
    # BOUND the governor may lower, never a floor it must honour -- the
    # old default of 12 read like a promise the cap of 8 could not keep.
    ap.add_argument("--workers", type=int, default=0,
                    help="upper bound on workers; 0 lets free memory decide")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--rehash", action="store_true",
                    help="re-hash every photo, ignoring stored fingerprints")
    args = ap.parse_args()

    if args.self_test:
        return 1 if _self_test() else 0

    files = sorted(f for f in os.listdir(PHOTO_DIR)
                   if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")))
    if args.limit:
        files = files[:args.limit]

    shas: dict[str, str] = {}
    hashes: dict[str, str] = {}
    dims: dict[str, tuple[int, int]] = {}
    failed: list[str] = []

    # RE-USE HASHES ALREADY STORED AT THIS VERSION.
    #
    # This module used to re-hash the whole photo directory on every
    # run — 13,992 images, ~8 minutes, for a fingerprint that is a pure
    # function of bytes that had not changed. On a job meant to run
    # daily that was most of its cost.
    #
    # The stored rows are loaded rather than merely skipped, because
    # the clustering below compares every photo against every other
    # one. Skipping without loading would silently shrink the
    # comparison set and quietly lose duplicate pairs — a WRONG answer,
    # where re-hashing was only a slow one.
    #
    # Keyed on parser_version, so bumping it re-hashes everything.
    known: dict[str, tuple[str, str, int, int, str]] = {}
    if not args.dry_run and not args.rehash:
        known = _stored_hashes()
        if known:
            print(f"ledger: {len(known):,} photo(s) already hashed at "
                  f"{PARSER_VERSION}; re-using them", flush=True)
            for name, (sha, dh, w, h, _acct) in known.items():
                shas[name], hashes[name] = sha, dh
                dims[name] = (w, h)

    todo = [f for f in files if f not in known]
    paths = [os.path.join(PHOTO_DIR, f) for f in todo]
    print(f"hashing {len(paths):,} of {len(files):,} ID photos "
          f"(sha256 + {HASH_SIZE}x{HASH_SIZE} dhash)", flush=True)
    t0 = time.time()

    # Through the governor, exactly like parse_statements.
    #
    # This ran on a bare ProcessPoolExecutor until 2026-08-07, picking
    # its own concurrency from --workers capped by core count. On that
    # date it took 12 workers, ran 2,000 images, and died with
    # BrokenProcessPool when the OS killed one of them.
    #
    # Choosing workers from CORES is the precise mistake runtime.py was
    # written to end: it is how twenty of them ended up on this laptop
    # and bugchecked it three times. That this module was never
    # converted was an oversight, not a judgement that image hashing is
    # different -- Pillow decodes a whole bitmap per file, so a worker
    # here holds as much memory as one parsing a PDF.
    #
    # governed_map also brings the two properties the raw pool lacked:
    # workers recycle every TASKS_PER_CHILD files, bounding any leak in
    # Pillow's decoders, and they run at below-normal priority so an
    # operator's request always wins.
    for i, (path, res) in enumerate(
            RT.governed_map(_hash_one, paths,
                            requested_workers=args.workers,
                            log=lambda m: print(m, flush=True)), 1):
        if res is None:
            failed.append(os.path.basename(path))
        else:
            name, payload = res
            if payload is None:
                failed.append(name)
            else:
                shas[name], hashes[name] = payload[0], payload[1]
                dims[name] = (payload[2], payload[3])
        if i % 2000 == 0:
            print(f"  {i:,}/{len(paths):,} ({time.time()-t0:.0f}s)",
                  file=sys.stderr, flush=True)
    elapsed = time.time() - t0

    print(f"\nhashed {len(hashes):,} in {elapsed:.0f}s "
          f"({elapsed/max(1,len(paths))*1000:.1f} ms/image); {len(failed)} unreadable")

    # ---- signal 1: byte-identical files -------------------------------
    same_file = cluster(shas, 0)
    same_file_n = sum(len(g) for g in same_file)

    # ---- signal 2: visually close but NOT the same file ----------------
    # Anything already caught by SHA-256 is removed first, so this
    # number answers "what does the perceptual hash add?" rather than
    # double-counting the exact matches.
    clean = {f: h for f, h in hashes.items() if not is_degenerate(h)}
    degen = len(hashes) - len(clean)
    near_all = cluster(clean, args.threshold)
    near = []
    for g in near_all:
        if len({shas[f] for f in g}) > 1:          # more than one file involved
            near.append(g)
    near_n = sum(len(g) for g in near)

    print("=" * 66)
    print(f"SAME FILE (sha256)     {len(same_file):>5} clusters, {same_file_n:>6,} files"
          f"   <- finding")
    print(f"NEAR-DUP (<= {args.threshold} bits)   {len(near):>5} clusters, {near_n:>6,} files"
          f"   <- lead, verify by eye")
    print(f"distinct files         {len(set(shas.values())):>5,} of {len(shas):,} images")
    print(f"distinct fingerprints  {len(set(clean.values())):>5,} of {len(clean):,} images")
    print(f"degenerate (blank/uniform) excluded from near-dup: {degen:,}")
    if same_file:
        sizes = sorted((len(g) for g in same_file), reverse=True)
        print(f"largest same-file      {sizes[:12]}")
        print(f"same-file 3+           {len([g for g in same_file if len(g) >= 3]):>5}"
              f"  <- strongest mule-farm signal")
    if near:
        print(f"largest near-dup       {sorted((len(g) for g in near), reverse=True)[:12]}")
    print("=" * 66)

    if args.dry_run:
        print("\ndry run: nothing written. Re-run without --dry-run to store")
        print("hashes and resolve each image to its account, FIR and PS.")
        return 0

    return _persist(shas, hashes, dims, failed, known)


def _persist(shas, hashes, dims, failed, known=None) -> int:
    """Write fingerprints and ledger rows.

    `known` is what was re-used from the database this run, keyed by
    file name with the stored account at index 4. Rows in it whose
    owner is unchanged are skipped — see the loop below.
    """
    known = known or {}
    """Write hashes and the ledger, resolving each file to its account.

    One SELECT for the whole path->account map, then batched inserts.
    A per-image lookup would be ~11k round trips for no benefit.
    """
    import asyncio
    import uuid
    from sqlalchemy import text
    from database import engine

    async def go():
        async with engine.begin() as conn:
            rows = (await conn.execute(text(
                "SELECT id, id_photo_path FROM all_accounts "
                "WHERE id_photo_path IS NOT NULL AND id_photo_path <> ''"
            ))).all()
            # Key on basename: the stored path may be relative or
            # absolute depending on when the row was written.
            by_name = {}
            # Deterministic when several account rows reference the
            # SAME uploaded file: keep the LOWEST id, matching the rule
            # analysis/relink.py uses. Plain last-write-wins here made
            # the two disagree, so every daily run re-pointed a handful
            # of rows and the next relink pointed them back — a
            # flip-flop that showed up as permanent "rows to re-point".
            for acct_id, path in rows:
                name = os.path.basename(str(path).replace("\\", "/"))
                prev = by_name.get(name)
                if prev is None or acct_id < prev:
                    by_name[name] = acct_id
            print(f"account photo paths in DB: {len(by_name):,}")

            payload, orphan, unchanged = [], 0, 0
            for name, h in hashes.items():
                acct = by_name.get(name)
                if acct is None:
                    orphan += 1
                    continue
                # Skip rows re-used from the database whose owner has
                # not moved. Their fingerprint came FROM this table, so
                # re-writing it is 13,000 upserts that change nothing —
                # pure time, and 13,000 deprecation warnings drowning
                # the log. A row whose account HAS moved still gets
                # written, so ownership stays correct.
                prev = known.get(name)
                if prev is not None and prev[4] == str(acct):
                    unchanged += 1
                    continue
                w, hh = dims.get(name, (None, None))
                payload.append({"id": str(uuid.uuid4()), "aid": acct,
                                "fp": f"uploads/photos/{name}",
                                "sha": shas[name], "dh": h,
                                "w": w, "h": hh, "pv": PARSER_VERSION})

            BATCH = 500
            for k in range(0, len(payload), BATCH):
                await conn.execute(text("""
                    INSERT INTO id_photo_hashes
                        (id, account_id, file_path, file_sha256, dhash,
                         width, height, parser_version)
                    VALUES (:id, :aid, :fp, :sha, :dh, :w, :h, :pv) AS new
                    ON DUPLICATE KEY UPDATE
                        -- account_id must be re-asserted, not just set
                        -- on first insert. file_path is UNIQUE, so a
                        -- re-run becomes an UPDATE; leaving account_id
                        -- out of this list froze every row on whichever
                        -- owner it happened to get first, and no amount
                        -- of re-hashing could correct it.
                        account_id=new.account_id,
                        file_sha256=new.file_sha256, dhash=new.dhash,
                        width=new.width, height=new.height,
                        parser_version=new.parser_version
                """), payload[k:k + BATCH])

            ledger = [{"id": str(uuid.uuid4()),
                       "fp": f"uploads/photos/{n}", "k": "photo",
                       "sha": shas.get(n),
                       "st": "ok" if n in hashes else "failed",
                       "d": None if n in hashes else "unreadable image",
                       "pv": PARSER_VERSION}
                      for n in list(hashes) + failed]
            for k in range(0, len(ledger), BATCH):
                await conn.execute(text("""
                    INSERT INTO upload_ledger
                        (id, file_path, file_kind, file_sha256, status, detail,
                         parser_version, processed_at)
                    VALUES (:id, :fp, :k, :sha, :st, :d, :pv, NOW()) AS new
                    ON DUPLICATE KEY UPDATE
                        file_sha256=new.file_sha256,
                        status=new.status, detail=new.detail,
                        parser_version=new.parser_version,
                        processed_at=new.processed_at
                """), ledger[k:k + BATCH])

            print(f"stored {len(payload):,} hashes; "
                  f"{orphan:,} images have no matching account row")
        await engine.dispose()

    asyncio.run(go())
    return 0


if __name__ == "__main__":
    sys.exit(main())
