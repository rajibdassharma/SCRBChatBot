"""
Bulk Indexer for RAG Playground — Index all documents in a case folder.

Scans a folder structure:
    CaseFolder/
    ├── CaseName1/
    │   ├── Chargesheet_CaseName1.pdf   ← detected as chargesheet
    │   ├── IR_AccusedName1.docx        ← detected as IR
    │   ├── IR_AccusedName2.docx
    │   └── ...
    └── CaseName2/
        └── ...

Usage:
    python bulk_index.py --folder "C:/Cases" --pipeline StructuredRAG
    python bulk_index.py --folder "C:/Cases/MyCase" --pipeline StructuredRAG --single-case
    python bulk_index.py --folder "C:/Cases" --dry-run

Options:
    --folder       Root folder containing case subfolders (or a single case folder with --single-case)
    --pipeline     Pipeline to use (default: StructuredRAG)
    --model        LLM model name (default: server default)
    --server       Backend URL (default: http://localhost:8006)
    --single-case  Treat --folder as a single case folder, not a parent of cases
    --dry-run      Preview what would be indexed without actually indexing
    --llm-parser   Use LLM parser for IR documents
"""

import argparse
import os
import sys
import time
import requests


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".csv"}


def is_chargesheet(filename: str) -> bool:
    """Detect if a file is a chargesheet by its filename."""
    name_lower = filename.lower()
    return "chargesheet" in name_lower or "charge_sheet" in name_lower or "charge sheet" in name_lower


def detect_doc_type(filename: str) -> str:
    """Detect document type from filename. Returns 'IR' or 'SMAC'."""
    # Chargesheets are indexed as IR doc_type (StructuredRAG routes them internally)
    return "IR"


def scan_case_folder(case_path: str, case_name: str) -> list:
    """Scan a single case folder and return file entries."""
    entries = []
    for item in sorted(os.listdir(case_path)):
        item_path = os.path.join(case_path, item)
        if not os.path.isfile(item_path):
            continue
        ext = os.path.splitext(item)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        is_cs = is_chargesheet(item)
        entries.append({
            "file_path": item_path,
            "filename": item,
            "case_name": case_name,
            "doc_type": detect_doc_type(item),
            "is_chargesheet": is_cs,
            # relative_path: "RootFolder/CaseName/filename" format for the API
            "relative_path": f"Cases/{case_name}/{item}",
        })

    return entries


def scan_root_folder(root_path: str) -> list:
    """Scan root folder containing case subfolders."""
    all_entries = []
    for case_dir in sorted(os.listdir(root_path)):
        case_path = os.path.join(root_path, case_dir)
        if not os.path.isdir(case_path):
            continue
        # Skip hidden/system dirs
        if case_dir.startswith(".") or case_dir.startswith("_"):
            continue

        entries = scan_case_folder(case_path, case_dir)
        all_entries.extend(entries)

    return all_entries


def index_file(entry: dict, server: str, pipeline: str, model: str,
               use_llm_parser: bool) -> dict:
    """Upload and index a single file via the API."""
    url = f"{server}/api/index"

    with open(entry["file_path"], "rb") as f:
        files = {"file": (entry["filename"], f)}
        data = {
            "pipeline": pipeline,
            "doc_type": entry["doc_type"],
            "relative_path": entry["relative_path"],
            "use_llm_parser": str(use_llm_parser).lower(),
        }
        if model:
            data["model"] = model

        try:
            resp = requests.post(url, files=files, data=data, timeout=600)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            return {"ok": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Bulk index documents for RAG Playground")
    parser.add_argument("--folder", required=True, help="Root folder with case subfolders")
    parser.add_argument("--pipeline", default="StructuredRAG", help="Pipeline name (default: StructuredRAG)")
    parser.add_argument("--model", default="", help="LLM model name")
    parser.add_argument("--server", default="http://localhost:8006", help="Backend URL")
    parser.add_argument("--single-case", action="store_true", help="Treat folder as single case")
    parser.add_argument("--dry-run", action="store_true", help="Preview without indexing")
    parser.add_argument("--llm-parser", action="store_true", help="Use LLM parser for IR docs")
    args = parser.parse_args()

    if not os.path.isdir(args.folder):
        print(f"ERROR: Folder not found: {args.folder}")
        sys.exit(1)

    # Scan files
    if args.single_case:
        case_name = os.path.basename(args.folder.rstrip("/\\"))
        entries = scan_case_folder(args.folder, case_name)
    else:
        entries = scan_root_folder(args.folder)

    if not entries:
        print("No supported files found.")
        sys.exit(0)

    # Sort: chargesheets first (they should be indexed before IRs for the accused list)
    entries.sort(key=lambda e: (e["case_name"], 0 if e["is_chargesheet"] else 1, e["filename"]))

    # Summary
    cases = set(e["case_name"] for e in entries)
    chargesheets = [e for e in entries if e["is_chargesheet"]]
    ir_docs = [e for e in entries if not e["is_chargesheet"]]

    print(f"\n{'=' * 60}")
    print(f"RAG Playground Bulk Indexer")
    print(f"{'=' * 60}")
    print(f"Folder:       {args.folder}")
    print(f"Pipeline:     {args.pipeline}")
    print(f"Cases:        {len(cases)}")
    print(f"Chargesheets: {len(chargesheets)}")
    print(f"IR Documents: {len(ir_docs)}")
    print(f"Total Files:  {len(entries)}")
    print(f"LLM Parser:   {'Yes' if args.llm_parser else 'No'}")
    print(f"{'=' * 60}\n")

    # List files
    current_case = None
    for e in entries:
        if e["case_name"] != current_case:
            current_case = e["case_name"]
            print(f"\nCase: {current_case}")
            print(f"{'-' * 40}")
        tag = "[CHARGESHEET]" if e["is_chargesheet"] else "[IR]"
        print(f"  {tag:15s} {e['filename']}")

    if args.dry_run:
        print(f"\n[DRY RUN] Would index {len(entries)} files. No changes made.")
        return

    # Check server health
    try:
        health = requests.get(f"{args.server}/health", timeout=10).json()
        if not health.get("ollama_ok"):
            print(f"\nWARNING: Ollama is not reachable. Indexing may fail.")
    except Exception as e:
        print(f"\nERROR: Cannot reach server at {args.server}: {e}")
        sys.exit(1)

    # Index files
    print(f"\nStarting indexing...\n")
    success = 0
    failed = 0
    total_time = 0

    for i, entry in enumerate(entries, 1):
        tag = "CS" if entry["is_chargesheet"] else "IR"
        print(f"[{i}/{len(entries)}] [{tag}] {entry['case_name']}/{entry['filename']}...", end=" ", flush=True)

        start = time.time()
        result = index_file(entry, args.server, args.pipeline, args.model, args.llm_parser)
        elapsed = time.time() - start
        total_time += elapsed

        if result.get("ok"):
            chunks = result.get("chunks", 0)
            fields = result.get("fields", 0)
            print(f"OK ({elapsed:.1f}s, {chunks} chunks, {fields} fields)")
            success += 1
        else:
            error = result.get("error", "Unknown error")
            print(f"FAILED ({elapsed:.1f}s) — {error}")
            failed += 1

    # Final report
    print(f"\n{'=' * 60}")
    print(f"Indexing Complete")
    print(f"{'=' * 60}")
    print(f"Success: {success}/{len(entries)}")
    print(f"Failed:  {failed}/{len(entries)}")
    print(f"Time:    {total_time:.1f}s total, {total_time/len(entries):.1f}s avg")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
