"""
Test Docling extraction on all PDFs in a folder.
Shows which docs are missing TMS I.D. (serial_no 1).

Run from backend/ directory:
    python test_docling_folder.py "C:/path/to/smac/folder"
"""
import sys
import os
import re
from pathlib import Path

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

if len(sys.argv) < 2:
    print("Usage: python test_docling_folder.py <folder_path>")
    sys.exit(1)

folder = Path(sys.argv[1])
if not folder.is_dir():
    print(f"Folder not found: {folder}")
    sys.exit(1)

from llm_kv_extractor import _extract_pdf_tables_docling

_NIL_VALUES = frozenset({
    "-", "–", "—", "nil", "-nil-", "n/a", "none",
    "not available", "not applicable", "na", ".", "..", "---",
})

pdfs = sorted(folder.rglob("*.pdf")) + sorted(folder.rglob("*.PDF"))
# Deduplicate
seen = set()
unique_pdfs = []
for p in pdfs:
    k = str(p).lower()
    if k not in seen:
        seen.add(k)
        unique_pdfs.append(p)

print(f"\nFound {len(unique_pdfs)} PDFs in {folder}\n")

ok_count = 0
missing_tms = []
no_table = []
errors = []

for i, pdf_path in enumerate(unique_pdfs, 1):
    fname = pdf_path.name
    print(f"[{i:>4d}/{len(unique_pdfs)}] {fname}...", end=" ")

    try:
        table_text, _ = _extract_pdf_tables_docling(str(pdf_path))
    except Exception as e:
        print(f"ERROR: {e}")
        errors.append((fname, str(e)))
        continue

    if not table_text:
        print("NO TABLES")
        no_table.append(fname)
        continue

    # Parse fields
    units = []
    metas = []
    for line in table_text.split("\n"):
        if not line.startswith("Row "):
            continue
        content = line.split(": ", 1)[1] if ": " in line else line
        parts = [p.strip() for p in content.split("|")]
        if len(parts) < 3:
            continue
        serial = parts[0].rstrip(". ")
        field_name = parts[1].strip()
        value = " | ".join(parts[2:]).strip()
        if not re.match(r"^\d+$", serial):
            continue
        if units and int(serial) <= int(metas[-1]["serial_no"]):
            break
        if not field_name or not value:
            continue
        if value.lower().strip(".- ") in _NIL_VALUES:
            continue
        units.append(f"{field_name}: {value}")
        metas.append({"field_name": field_name, "serial_no": serial})

    has_tms = any(m["serial_no"] == "1" for m in metas)

    if has_tms:
        print(f"OK ({len(units)} fields)")
        ok_count += 1
    else:
        # Check if TMS is in row 0 raw text
        row0 = ""
        for line in table_text.split("\n"):
            if line.startswith("Row 0:"):
                row0 = line
                break
        print(f"MISSING serial 1 ({len(units)} fields) | Row 0: {row0[:100]}")
        missing_tms.append((fname, row0, len(units)))

print(f"\n{'='*60}")
print(f"  SUMMARY")
print(f"{'='*60}")
print(f"  Total PDFs     : {len(unique_pdfs)}")
print(f"  OK (has TMS)   : {ok_count}")
print(f"  Missing TMS    : {len(missing_tms)}")
print(f"  No tables      : {len(no_table)}")
print(f"  Errors         : {len(errors)}")
print(f"{'='*60}")

if missing_tms:
    print(f"\nFiles missing serial_no 1 (TMS I.D.):")
    for fname, row0, fields in missing_tms:
        print(f"  {fname}")
        print(f"    Row 0: {row0[:120]}")
        print(f"    Fields captured: {fields}")

if no_table:
    print(f"\nFiles with no tables detected:")
    for fname in no_table[:20]:
        print(f"  {fname}")
    if len(no_table) > 20:
        print(f"  ... and {len(no_table) - 20} more")
