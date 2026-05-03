#!/usr/bin/env python3
"""
test_ir_parse.py - Parse-only diagnostic tool.

Runs ir_parser.parse_ir_document() on a single file or a whole folder
WITHOUT touching MySQL, ChromaDB, or the backend at all. Pure parser test.

Use this to quickly figure out why bulk_index_ir.py is failing on certain
files - the parser is the first thing the upload pipeline does, and if
it returns 0 fields the file gets rejected with "No fields extracted".

Usage:
  python test_ir_parse.py <file.docx>                   # one file, verbose
  python test_ir_parse.py <folder>                      # folder, summary
  python test_ir_parse.py <folder> --verbose            # folder, per-file detail
  python test_ir_parse.py <folder> --limit 10           # only first 10
  python test_ir_parse.py <folder> --show-empty 5       # list first 5 empty results

Output buckets:
  OK     - parser extracted >0 fields (good)
  EMPTY  - parser ran but found 0 fields (table structure mismatch?)
  ERROR  - parser threw an exception (file format issue?)
"""

import argparse
import os
import sys
from pathlib import Path

# Add backend/ to sys.path so we can import the parser directly
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "backend"))
sys.path.insert(0, BACKEND_DIR)

from ir_parser import parse_ir_document  # noqa: E402


SKIP_NAMES = {"report", "reports", "feedback", "attachment", "attachments"}


def parse_one(fpath: Path, verbose: bool = False) -> dict:
    fname = fpath.name
    try:
        fields, accused_name = parse_ir_document(str(fpath), fname)
    except Exception as e:
        return {
            "filename": fname,
            "fields": 0,
            "accused": "",
            "status": "ERROR",
            "error": f"{type(e).__name__}: {e}",
        }

    status = "OK" if fields else "EMPTY"

    if verbose:
        print(f"\n=== {fname} ===")
        print(f"  Status:  {status}")
        print(f"  Fields:  {len(fields)}")
        print(f"  Accused: {accused_name or '(none)'}")
        if fields:
            print(f"  Sample fields (first 8):")
            for f in fields[:8]:
                key = (f.get("field_key") or "")[:45]
                val = (f.get("field_value") or "")[:50]
                if not val:
                    val = "(empty)"
                print(f"    [{f.get('serial_no', ''):>4}] {key:45s} | {val}")
            if len(fields) > 8:
                print(f"    ... and {len(fields) - 8} more")

    return {
        "filename": fname,
        "fields": len(fields),
        "accused": accused_name,
        "status": status,
    }


def collect_files(target: Path) -> list:
    extensions = ["*.docx", "*.DOCX", "*.doc", "*.DOC", "*.pdf", "*.PDF"]
    raw = []
    for ext in extensions:
        raw.extend(target.rglob(ext))

    seen = set()
    files = []
    for p in sorted(raw):
        k = str(p).lower()
        if k in seen:
            continue
        seen.add(k)
        if p.stem.lower() in SKIP_NAMES:
            continue
        files.append(p)
    return files


def main():
    parser = argparse.ArgumentParser(
        description="Test IR parser on a file or folder without touching MySQL/ChromaDB/backend.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage:")[1] if "Usage:" in __doc__ else "",
    )
    parser.add_argument("path", type=str, help="Single file or folder to parse")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show detailed per-file output (sample fields)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max files to parse (0 = all)")
    parser.add_argument("--show-empty", type=int, default=10,
                        help="How many EMPTY filenames to list at end (default 10)")
    parser.add_argument("--show-error", type=int, default=10,
                        help="How many ERROR filenames+messages to list at end (default 10)")
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"ERROR: path not found: {target}")
        sys.exit(1)

    # Single-file mode
    if target.is_file():
        result = parse_one(target, verbose=True)
        print()
        print("=" * 62)
        print(f"  RESULT: {result['status']} - {result['fields']} fields"
              f", accused='{result['accused']}'")
        print("=" * 62)
        sys.exit(0 if result["status"] == "OK" else 1)

    # Folder mode
    files = collect_files(target)
    if args.limit > 0:
        files = files[:args.limit]

    if not files:
        print(f"No matching files in {target}")
        sys.exit(0)

    print(f"Parsing {len(files)} files from {target}")
    print(f"(MySQL/ChromaDB/backend NOT touched - parser-only test)")
    print()

    results = []
    for i, fp in enumerate(files, 1):
        result = parse_one(fp, verbose=args.verbose)
        if not args.verbose:
            print(f"  [{i:>4}/{len(files)}] {result['status']:>5} {result['filename']}: {result['fields']} fields")
        results.append(result)

    # Summary
    ok    = [r for r in results if r["status"] == "OK"]
    empty = [r for r in results if r["status"] == "EMPTY"]
    err   = [r for r in results if r["status"] == "ERROR"]

    print()
    print("=" * 62)
    print("  SUMMARY")
    print("=" * 62)
    print(f"  Total:  {len(results)}")
    if ok:
        field_counts = sorted([r["fields"] for r in ok])
        median = field_counts[len(field_counts) // 2]
        avg = sum(field_counts) / len(field_counts)
        print(f"  OK:     {len(ok)}  (avg {avg:.0f} fields/doc, median {median})")
    else:
        print(f"  OK:     0")
    print(f"  Empty:  {len(empty)}  (parser ran but extracted 0 fields)")
    print(f"  Error:  {len(err)}  (parser threw an exception)")

    if empty and args.show_empty > 0 and not args.verbose:
        print()
        print(f"  Empty files (first {min(args.show_empty, len(empty))}):")
        for r in empty[:args.show_empty]:
            print(f"    {r['filename']}")

    if err and args.show_error > 0:
        print()
        print(f"  Errors (first {min(args.show_error, len(err))}):")
        for r in err[:args.show_error]:
            print(f"    {r['filename']}: {r.get('error', '')[:100]}")

    sys.exit(0 if not err and ok else 1)


if __name__ == "__main__":
    main()
