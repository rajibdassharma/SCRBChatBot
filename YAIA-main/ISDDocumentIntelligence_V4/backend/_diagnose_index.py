"""Diagnostic script: check what's stored for IR documents in MSSQL + ChromaDB."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from mssql_db import get_conn
from rag import _get_col

print("=" * 70)
print("1. MSSQL document_fields — IR collection")
print("=" * 70)
conn = get_conn()

# Total fields per document
cur = conn.execute(
    "SELECT doc_name, COUNT(*) as field_count "
    "FROM document_fields WHERE collection = 'IR' "
    "GROUP BY doc_name ORDER BY doc_name"
)
rows = cur.fetchall()
if not rows:
    print("  NO IR DOCUMENTS FOUND in document_fields!")
else:
    for r in rows:
        print(f"  {r[0]}: {r[1]} fields")

print()

# List all field_keys for IR
cur2 = conn.execute(
    "SELECT doc_name, serial_no, field_key, LEFT(field_value, 80) as val_preview "
    "FROM document_fields WHERE collection = 'IR' "
    "ORDER BY doc_name, id"
)
rows2 = cur2.fetchall()
print(f"  Total IR field rows: {len(rows2)}")
print()
for r in rows2:
    val = r[3] or ""
    sno = r[1] or "?"
    print(f"  [{sno:>4}] {r[2]}: {val}")

print()

# Specifically check for 'associate'
cur3 = conn.execute(
    "SELECT doc_name, field_key, field_value "
    "FROM document_fields WHERE collection = 'IR' AND field_key LIKE '%associate%'"
)
assoc_rows = cur3.fetchall()
print(f"  Fields matching 'associate': {len(assoc_rows)}")
for r in assoc_rows:
    print(f"    {r[0]} | {r[1]} = {r[2][:200]}")

conn.close()

print()
print("=" * 70)
print("2. ChromaDB — IR collection chunks")
print("=" * 70)
try:
    col = _get_col("IR")
    count = col.count()
    print(f"  Total chunks in IR collection: {count}")

    # Get all chunks and check field_name metadata
    all_data = col.get(include=["documents", "metadatas"])
    docs = all_data.get("documents") or []
    metas = all_data.get("metadatas") or []

    field_chunks = 0
    page_only_chunks = 0
    for m in metas:
        if m.get("field_name"):
            field_chunks += 1
        else:
            page_only_chunks += 1

    print(f"  Chunks with field_name metadata: {field_chunks}")
    print(f"  Chunks without field_name (page text): {page_only_chunks}")

    # List unique field_names
    field_names = set()
    for m in metas:
        fn = m.get("field_name")
        if fn:
            field_names.add(fn)
    print(f"\n  Unique field_names in ChromaDB ({len(field_names)}):")
    for fn in sorted(field_names):
        print(f"    - {fn}")

    # Check for associate
    print()
    assoc_chunks = [(d, m) for d, m in zip(docs, metas)
                    if "associate" in (m.get("field_name") or "").lower()
                    or "associate" in d.lower()[:200]]
    print(f"  Chunks matching 'associate' (in field_name or text): {len(assoc_chunks)}")
    for d, m in assoc_chunks[:5]:
        print(f"    field_name: {m.get('field_name', 'N/A')}")
        print(f"    text: {d[:200]}")
        print()

except Exception as e:
    print(f"  Error accessing ChromaDB: {e}")

print("=" * 70)
print("DONE")
