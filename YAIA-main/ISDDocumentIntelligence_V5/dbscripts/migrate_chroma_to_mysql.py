"""
migrate_chroma_to_mysql.py — Populate smac_reports (EAV) from ChromaDB metadata.

Reads all SMAC chunks from ChromaDB that have field_name metadata,
extracts the field_key and field_value, and inserts into MySQL smac_reports table.

No PDFs, no Ollama, no re-indexing. Just DB-to-DB.

Usage:
    cd backend/
    python ../dbscripts/migrate_chroma_to_mysql.py

    # Dry run (show what would be inserted):
    python ../dbscripts/migrate_chroma_to_mysql.py --dry-run

    # Also migrate IR collection:
    python ../dbscripts/migrate_chroma_to_mysql.py --collection IR
"""

import os
import sys
import argparse
import time

# Add backend to path so we can import modules
BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from config import CHROMA_PATH
from mysql_db import get_conn

import chromadb


_NIL_VALUES = {"-", "–", "—", "Nil", "nil", "NIL", "N/A", "n/a", "None", "none", "-nil-", ""}


def migrate(collection_name: str, target_table: str, dry_run: bool = False, batch_size: int = 500):
    """Read ChromaDB chunks with field_name metadata and insert into MySQL."""

    print(f"\n{'=' * 62}")
    print(f"  ChromaDB → MySQL Migration")
    print(f"{'=' * 62}")
    print(f"  ChromaDB path : {CHROMA_PATH}")
    print(f"  Collection    : {collection_name}")
    print(f"  Target table  : {target_table}")
    print(f"  Dry run       : {dry_run}")
    print(f"{'=' * 62}\n")

    # Open ChromaDB
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        col = client.get_collection(name=collection_name)
    except Exception:
        # Try with _db suffix (ChromaDB naming rules)
        alt_name = collection_name + "_db" if len(collection_name) < 3 else collection_name
        try:
            col = client.get_collection(name=alt_name)
            print(f"  Using collection name: {alt_name}")
        except Exception as e:
            print(f"ERROR: Collection '{collection_name}' not found in ChromaDB: {e}")
            sys.exit(1)

    total_chunks = col.count()
    print(f"  Total chunks in collection: {total_chunks}")

    if total_chunks == 0:
        print("  No chunks found. Nothing to migrate.")
        return

    # Read chunks in batches (ChromaDB's SQLite backend fails with too many at once)
    print(f"  Reading chunks from ChromaDB in batches...")
    CHROMA_BATCH = 2000
    docs = []
    metas = []
    for offset in range(0, total_chunks, CHROMA_BATCH):
        limit = min(CHROMA_BATCH, total_chunks - offset)
        batch = col.get(include=["metadatas", "documents"], limit=limit, offset=offset)
        docs.extend(batch.get("documents") or [])
        metas.extend(batch.get("metadatas") or [])
        print(f"    Read {len(docs)}/{total_chunks} chunks...")

    # Group by doc_id — collect field_key/field_value per document
    doc_fields = {}  # doc_id -> list of (serial_no, field_key, field_value, doc_name)

    for doc_text, meta in zip(docs, metas):
        field_name = meta.get("field_name")
        if not field_name:
            continue  # Skip chunks without field_name (plain text chunks)

        doc_id = meta.get("doc_id", "")
        doc_name = meta.get("doc_name", "Unknown")
        serial_no = meta.get("serial_no", "")

        if not doc_id:
            continue

        # Extract value from chunk text: "FieldName: value"
        if ": " in doc_text:
            field_value = doc_text.split(": ", 1)[1].strip()
        else:
            field_value = doc_text.strip()

        # Skip nil values
        if not field_value or field_value in _NIL_VALUES:
            continue

        if doc_id not in doc_fields:
            doc_fields[doc_id] = {"doc_name": doc_name, "fields": []}

        doc_fields[doc_id]["fields"].append({
            "serial_no": serial_no,
            "field_key": field_name,
            "field_value": field_value,
        })

    total_docs = len(doc_fields)
    total_fields = sum(len(d["fields"]) for d in doc_fields.values())
    print(f"  Found {total_fields} fields across {total_docs} documents")

    if total_docs == 0:
        print("  No fields with field_name metadata found. Nothing to migrate.")
        return

    if dry_run:
        print(f"\n  [DRY RUN] Would insert {total_fields} rows into {target_table}")
        # Show first 5 documents as sample
        for i, (doc_id, data) in enumerate(list(doc_fields.items())[:5]):
            print(f"\n  Document: {data['doc_name']}")
            for f in data["fields"]:
                print(f"    {f['serial_no']:>3s} | {f['field_key']:30s} | {f['field_value'][:60]}")
        if total_docs > 5:
            print(f"\n  ... and {total_docs - 5} more documents")
        return

    # Insert into MySQL
    print(f"\n  Inserting into {target_table}...")
    conn = get_conn()
    cur = conn.cursor()

    # Clear existing data in target table
    cur.execute(f"DELETE FROM {target_table}")
    old_count = cur.rowcount
    conn.commit()
    if old_count > 0:
        print(f"  Cleared {old_count} existing rows from {target_table}.")

    inserted = 0
    skipped = 0
    start_time = time.time()

    if target_table == "smac_reports":
        insert_sql = (
            "INSERT INTO smac_reports (doc_id, doc_name, serial_no, field_key, field_value) "
            "VALUES (%s, %s, %s, %s, %s)"
        )
    else:
        insert_sql = (
            "INSERT INTO ir_reports (doc_id, doc_name, collection, serial_no, field_key, field_value) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        )

    for doc_id, data in doc_fields.items():
        doc_name = data["doc_name"]
        seen_keys = set()

        for f in data["fields"]:
            # Deduplicate by field_key within same doc
            if f["field_key"] in seen_keys:
                skipped += 1
                continue
            seen_keys.add(f["field_key"])

            try:
                if target_table == "smac_reports":
                    cur.execute(insert_sql, (
                        doc_id, doc_name,
                        f["serial_no"] or None,
                        f["field_key"],
                        f["field_value"],
                    ))
                else:
                    cur.execute(insert_sql, (
                        doc_id, doc_name, "IR",
                        f["serial_no"] or None,
                        f["field_key"],
                        f["field_value"],
                    ))
                inserted += 1
            except Exception as e:
                skipped += 1
                if "Duplicate" not in str(e):
                    print(f"  WARNING: {doc_name} / {f['field_key']}: {e}")

        # Commit in batches
        if inserted % batch_size == 0:
            conn.commit()

    conn.commit()
    cur.close()
    conn.close()

    elapsed = time.time() - start_time

    print(f"\n{'=' * 62}")
    print(f"  MIGRATION COMPLETE")
    print(f"{'=' * 62}")
    print(f"  Documents   : {total_docs}")
    print(f"  Inserted    : {inserted}")
    print(f"  Skipped     : {skipped}")
    print(f"  Elapsed     : {elapsed:.1f}s")
    print(f"{'=' * 62}")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate ChromaDB field metadata to MySQL structured tables.",
    )
    parser.add_argument(
        "--collection", default="SMAC",
        help="ChromaDB collection name (default: SMAC)",
    )
    parser.add_argument(
        "--table", default=None,
        help="Target MySQL table (default: smac_reports for SMAC, ir_reports for IR)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be inserted without actually inserting",
    )
    parser.add_argument(
        "--batch-size", type=int, default=500,
        help="Commit batch size (default: 500)",
    )

    args = parser.parse_args()

    # Auto-detect target table from collection
    if args.table:
        target_table = args.table
    elif args.collection == "SMAC" or args.collection.startswith("SMAC_c"):
        target_table = "smac_reports"
    else:
        target_table = "ir_reports"

    migrate(
        collection_name=args.collection,
        target_table=target_table,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
