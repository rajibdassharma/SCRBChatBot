"""
Quick test: see what Docling extracts from a SMAC PDF.
Run from backend/ directory:
    python test_docling_smac.py "path/to/smac.pdf"
"""
import sys
import os
import re

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

if len(sys.argv) < 2:
    print("Usage: python test_docling_smac.py <pdf_path>")
    sys.exit(1)

pdf_path = sys.argv[1]
if not os.path.exists(pdf_path):
    print(f"File not found: {pdf_path}")
    sys.exit(1)

# Step 1: Extract tables with Docling
print(f"\n{'='*60}")
print(f"  Docling extraction: {os.path.basename(pdf_path)}")
print(f"{'='*60}\n")

from llm_kv_extractor import _extract_pdf_tables_docling

table_text, paragraph_text = _extract_pdf_tables_docling(pdf_path)

print(f"\n--- TABLE TEXT ({len(table_text)} chars) ---")
print(table_text[:3000] if table_text else "(empty)")

# Step 2: Direct pipe-split parser (no regex needed)
if table_text:
    print(f"\n{'='*60}")
    print(f"  Direct pipe-split parsing")
    print(f"{'='*60}\n")

    _NIL_VALUES = {"-", "–", "—", "nil", "-nil-", "n/a", "none",
                   "not available", "not applicable", "na", ".", "..", "---"}

    units = []
    metas = []

    for line in table_text.split("\n"):
        if not line.startswith("Row "):
            continue

        # Strip "Row N: " prefix
        content = line.split(": ", 1)[1] if ": " in line else line

        # Split on pipe
        parts = [p.strip() for p in content.split("|")]

        if len(parts) < 3:
            continue

        # Column 1: serial number (e.g. "1." or "1")
        serial = parts[0].rstrip(". ")

        # Column 2: field name
        field_name = parts[1].strip()

        # Column 3+: value (rejoin in case value contains pipes)
        value = " | ".join(parts[2:]).strip()

        # Skip if serial is not a number (it's a different table)
        if not re.match(r"^\d+$", serial):
            continue

        # Stop if serial resets (second table detected)
        if units and int(serial) <= int(metas[-1]["serial_no"]):
            break

        # Skip nil values
        if not field_name or not value:
            continue
        if value.lower().strip(".- ") in _NIL_VALUES:
            continue

        units.append(f"{field_name}: {value}")
        metas.append({"field_name": field_name, "serial_no": serial, "page": 1})

    print(f"Parsed {len(units)} fields:\n")
    for u, m in zip(units, metas):
        fn = m.get("field_name", "?")
        sno = m.get("serial_no", "")
        print(f"  {sno:>3s} | {fn:30s} | {u}")
else:
    print("\nNo table text extracted. Docling did not find tables.")
