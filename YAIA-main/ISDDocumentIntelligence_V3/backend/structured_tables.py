"""
Structured Tables — Simple Key-Value storage for ISD Document Intelligence.

One table: document_fields
  - Each row = one field from a document (Serial No, Key, Value)
  - Works for both SMAC Log Reports and IR Form-16 documents
  - No complex mapping needed — stores exactly what's in the document

Query approach:
  - Search by field_key (LIKE '%keyword%') to find values
  - Filter by collection (SMAC/IR) and/or doc_id
  - NL→SQL uses this simple schema for 100% accurate lookups
"""

import re
from typing import List, Dict, Any, Optional

import pyodbc

from mssql_db import get_conn, _fetchone, _fetchall


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------
def _get_conn() -> pyodbc.Connection:
    return get_conn()


# ═══════════════════════════════════════════════════════════════════════════
#  SCHEMA CREATION
# ═══════════════════════════════════════════════════════════════════════════

def init_db():
    """Create the document_fields table if it doesn't already exist."""
    conn = _get_conn()

    conn.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'document_fields'
        )
        CREATE TABLE document_fields (
            id           INT IDENTITY(1,1) PRIMARY KEY,
            doc_id       NVARCHAR(500)  NOT NULL,
            doc_name     NVARCHAR(500)  NOT NULL,
            collection   NVARCHAR(50)   NOT NULL,   -- 'SMAC' or 'IR'
            serial_no    NVARCHAR(20)   NULL,        -- Sl No from document
            field_key    NVARCHAR(500)  NOT NULL,    -- Field name (Column 2)
            field_value  NVARCHAR(MAX)  NOT NULL     -- Value (Column 3)
        )
    """)

    # Indexes for fast lookups
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_df_doc_id' AND object_id = OBJECT_ID('document_fields'))
            CREATE INDEX idx_df_doc_id ON document_fields(doc_id)
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_df_collection' AND object_id = OBJECT_ID('document_fields'))
            CREATE INDEX idx_df_collection ON document_fields(collection)
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_df_field_key' AND object_id = OBJECT_ID('document_fields'))
            CREATE INDEX idx_df_field_key ON document_fields(field_key)
    """)

    conn.commit()
    conn.close()
    print("[StructuredTables] document_fields table is ready.")


# Initialize on module load
init_db()


# ═══════════════════════════════════════════════════════════════════════════
#  STORE DOCUMENT FIELDS
# ═══════════════════════════════════════════════════════════════════════════

def store_document_fields(
    doc_id: str,
    doc_name: str,
    collection: str,
    field_values: List[Dict[str, str]],
) -> Dict[str, Any]:
    """
    Store all field-value pairs from a document into document_fields.

    field_values: list of dicts with keys:
      - "serial_no" (optional): Sl No from document
      - "field_name": the field key (Column 2)
      - "value": the field value (Column 3)
    """
    conn = _get_conn()

    # Check if already stored
    cur = conn.execute(
        "SELECT COUNT(*) FROM document_fields WHERE doc_id = ?", (doc_id,)
    )
    if cur.fetchone()[0] > 0:
        conn.close()
        return {"ok": True, "message": "Document fields already stored", "doc_id": doc_id}

    stored = 0
    for fv in field_values:
        fn = fv.get("field_name", "").strip()
        val = fv.get("value", "").strip()
        sno = fv.get("serial_no", "").strip()

        if not fn or not val:
            continue
        # Skip nil/dash-only values
        if val in ("-", "–", "—", "Nil", "nil", "NIL", "N/A", "n/a", "None", "none", "-nil-"):
            continue

        conn.execute(
            "INSERT INTO document_fields (doc_id, doc_name, collection, serial_no, field_key, field_value) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, doc_name, collection, sno or None, fn, val),
        )
        stored += 1

    conn.commit()
    conn.close()
    print(f"[StructuredTables] Stored {stored} fields for {doc_name} ({collection})")
    return {"ok": True, "stored": stored, "doc_id": doc_id}


# Backward-compatible aliases (called from rag.py)
def store_smac_report(doc_id: str, doc_name: str, field_values: List[Dict[str, str]]) -> Dict[str, Any]:
    return store_document_fields(doc_id, doc_name, "SMAC", field_values)

def store_ir_report(doc_id: str, doc_name: str, field_values: List[Dict[str, str]]) -> Dict[str, Any]:
    return store_document_fields(doc_id, doc_name, "IR", field_values)


# ═══════════════════════════════════════════════════════════════════════════
#  QUERY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_all_documents(collection: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return a summary of all stored documents (doc_id, doc_name, collection, field_count)."""
    conn = _get_conn()
    if collection:
        cur = conn.execute(
            "SELECT doc_id, doc_name, collection, COUNT(*) as field_count "
            "FROM document_fields WHERE collection = ? "
            "GROUP BY doc_id, doc_name, collection ORDER BY doc_name",
            (collection,),
        )
    else:
        cur = conn.execute(
            "SELECT doc_id, doc_name, collection, COUNT(*) as field_count "
            "FROM document_fields "
            "GROUP BY doc_id, doc_name, collection ORDER BY doc_name"
        )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    conn.close()
    return rows


def get_document_fields(doc_id: str) -> List[Dict[str, Any]]:
    """Return all fields for a specific document, ordered by serial_no."""
    conn = _get_conn()
    cur = conn.execute(
        "SELECT serial_no, field_key, field_value "
        "FROM document_fields WHERE doc_id = ? "
        "ORDER BY id",
        (doc_id,),
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    conn.close()
    return rows


def search_fields(keyword: str, collection: Optional[str] = None) -> List[Dict[str, Any]]:
    """Search for fields by keyword in field_key. Returns matching rows with doc context."""
    conn = _get_conn()
    if collection:
        cur = conn.execute(
            "SELECT doc_id, doc_name, collection, serial_no, field_key, field_value "
            "FROM document_fields "
            "WHERE field_key LIKE ? AND collection = ? "
            "ORDER BY doc_name, id",
            (f"%{keyword}%", collection),
        )
    else:
        cur = conn.execute(
            "SELECT doc_id, doc_name, collection, serial_no, field_key, field_value "
            "FROM document_fields "
            "WHERE field_key LIKE ? "
            "ORDER BY doc_name, id",
            (f"%{keyword}%",),
        )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    conn.close()
    return rows


# ═══════════════════════════════════════════════════════════════════════════
#  SQL QUERY EXECUTION (for NL→SQL pipeline)
# ═══════════════════════════════════════════════════════════════════════════

def execute_sql_query(sql: str) -> List[Dict[str, Any]]:
    """
    Execute a read-only SQL query against MSSQL and return results as list of dicts.
    Safety: only allows SELECT statements.
    """
    sql_stripped = sql.strip().upper()

    # Safety checks
    if not sql_stripped.startswith("SELECT"):
        return [{"error": "Only SELECT queries are allowed"}]

    dangerous = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "TRUNCATE", "EXEC", "EXECUTE", "MERGE"]
    for keyword in dangerous:
        if re.search(rf'\b{keyword}\b', sql_stripped):
            return [{"error": f"Forbidden keyword: {keyword}"}]

    conn = _get_conn()
    try:
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        conn.close()
        return [{"error": str(e)}]


def get_table_schema_description() -> str:
    """
    Return a human-readable description of the document_fields table.
    This is provided to the LLM as context for NL→SQL generation.
    """
    return """
DATABASE SCHEMA — ISDIntelligence (SQL Server / T-SQL syntax)

TABLE: document_fields
  - id (INT, PK, auto-increment)
  - doc_id (NVARCHAR) — unique document identifier
  - doc_name (NVARCHAR) — filename of the document
  - collection (NVARCHAR) — 'SMAC' for SMAC Log Reports, 'IR' for IR Form-16 Interrogation Reports
  - serial_no (NVARCHAR, nullable) — serial number from the document (e.g., '1', '2', '27a')
  - field_key (NVARCHAR) — the field name / description from column 2 of the document table
  - field_value (NVARCHAR MAX) — the actual value from column 3 of the document table

COMMON FIELD NAMES (field_key values found in IR documents):
  - Name of the accused/criminal/convict/subject: field_key LIKE '%Name%' (the FIRST 'Name' field per document is the accused's name)
  - Aliases / Nicknames: field_key LIKE '%Alias%'
  - Organization: field_key LIKE '%Organi%'
  - Helpers (advocate, doctor, financier, etc.): field_key LIKE '%helper%'
  - Associates / Accomplices: field_key LIKE '%associate%' OR '%accomplice%' OR '%operative%'
  - Family: field_key LIKE '%family%' OR '%father%' OR '%mother%' OR '%brother%' OR '%sister%'
  - Address: field_key LIKE '%address%'
  - Criminal cases: field_key LIKE '%criminal case%'
  - Weapons: field_key LIKE '%weapon%'
  - Modus operandi / Motive: field_key LIKE '%modus%' OR '%motive%'
  - Physical description fields: Height, Weight, Complexion, Eyes, Hair, etc.
  - Mobile / Phone: field_key LIKE '%mobile%' OR '%phone%' OR '%landline%'

NOTES:
  - Each row represents one field-value pair from a document.
  - One document = many rows (one per field). Use doc_id to group fields of the same document.
  - SMAC documents typically have 10 fields: TMS I.D., Originator, Date, Theatre, Current Priority, Subject, Input, Grading, Has Attachment, Input Closed.
  - IR documents typically have 50-100 fields covering personal details, physical description, criminal history, organization links, helpers, etc.
  - Use field_key LIKE '%keyword%' for searching fields.
  - Filter by collection = 'SMAC' or collection = 'IR' to limit scope.
  - Filter by doc_id to query a specific document.
  - Use doc_name to identify documents by filename.
  - When a field is not present for a document, there is NO row for it (use LEFT JOIN to show NULL).

EXAMPLE QUERIES:

-- Find the name of the accused in an IR document:
SELECT field_value FROM document_fields
WHERE collection = 'IR' AND field_key LIKE '%Name%'
  AND field_key NOT LIKE '%address%' AND field_key NOT LIKE '%organization%'

-- Find all fields for a specific person's document:
SELECT serial_no, field_key, field_value FROM document_fields
WHERE doc_name LIKE '%Abdul%' ORDER BY id

-- List all accused with their helpers (show NULL if no helpers):
SELECT d1.doc_name, d1.field_value AS accused_name, d2.field_value AS helpers
FROM document_fields d1
LEFT JOIN document_fields d2 ON d1.doc_id = d2.doc_id AND d2.field_key LIKE '%helper%'
WHERE d1.collection = 'IR' AND d1.field_key LIKE '%Name%'
  AND d1.field_key NOT LIKE '%address%' AND d1.field_key NOT LIKE '%organization%'
  AND LEN(d1.field_key) < 50

-- Find all subjects with their organization:
SELECT d1.doc_name, d1.field_value AS subject_name, d2.field_value AS organization
FROM document_fields d1
JOIN document_fields d2 ON d1.doc_id = d2.doc_id
WHERE d1.field_key LIKE '%Name%' AND LEN(d1.field_key) < 50
  AND d2.field_key LIKE '%Organi%'

-- Find all documents with a specific field value:
SELECT doc_name, field_key, field_value FROM document_fields
WHERE field_value LIKE '%JMB%'

-- Get all SMAC reports with their subjects:
SELECT doc_name, field_value FROM document_fields
WHERE collection = 'SMAC' AND field_key LIKE '%Subject%'

-- Count documents by collection:
SELECT collection, COUNT(DISTINCT doc_id) AS doc_count FROM document_fields GROUP BY collection
"""


# ═══════════════════════════════════════════════════════════════════════════
#  CLEAR DATA
# ═══════════════════════════════════════════════════════════════════════════

def clear_all_structured_data():
    """Delete all rows from document_fields."""
    conn = _get_conn()
    conn.execute("DELETE FROM document_fields")
    conn.commit()
    conn.close()
    print("[StructuredTables] Cleared all document_fields data.")


# Backward-compatible aliases for app.py
def get_all_smac_reports():
    return get_all_documents("SMAC")

def get_smac_report_by_doc(doc_id: str):
    return get_document_fields(doc_id)

def get_all_ir_reports():
    return get_all_documents("IR")

def get_ir_report_full(doc_id: str):
    return get_document_fields(doc_id)
