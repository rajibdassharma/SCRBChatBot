"""
Structured Tables for ISD Document Intelligence.

Two tables:
  - smac_reports : dedicated columnar table for SMAC Log Report fields
  - ir_reports   : key-value store for IR Form-16 fields

SMAC reports get proper columns (input_id, originator, subject, gist, etc.)
IR documents use the flexible key-value design to handle 60+ varied fields.
"""

import json
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
    """Create smac_reports and ir_reports tables if they don't exist."""
    conn = _get_conn()

    # ── smac_reports ──────────────────────────────────────────────────────
    conn.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'smac_reports'
        )
        CREATE TABLE smac_reports (
            id               INT IDENTITY(1,1) PRIMARY KEY,
            doc_id           NVARCHAR(500)  NOT NULL UNIQUE,
            doc_name         NVARCHAR(500)  NOT NULL,
            input_id         NVARCHAR(200)  NULL,   -- TMS / Input number
            date_of_receipt  NVARCHAR(200)  NULL,   -- Date received
            originator       NVARCHAR(500)  NULL,   -- Originating unit
            source_name      NVARCHAR(500)  NULL,   -- Intelligence source
            grading          NVARCHAR(100)  NULL,   -- Source/input grading (A1, B2...)
            theatre          NVARCHAR(500)  NULL,   -- Operational area / theatre
            priority         NVARCHAR(100)  NULL,   -- Current priority level
            subject          NVARCHAR(1000) NULL,   -- Subject line
            gist             NVARCHAR(MAX)  NULL,   -- Main intelligence content
            threat_details   NVARCHAR(MAX)  NULL,   -- Specific threat details
            shared_with      NVARCHAR(MAX)  NULL,   -- Distribution / shared with list
            classification   NVARCHAR(100)  NULL,   -- SECRET / TOP SECRET etc.
            raw_fields       NVARCHAR(MAX)  NULL,   -- JSON of any unmapped fields
            indexed_at       DATETIME       NOT NULL DEFAULT GETDATE()
        )
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_smac_input_id' AND object_id = OBJECT_ID('smac_reports'))
            CREATE INDEX idx_smac_input_id ON smac_reports(input_id)
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_smac_originator' AND object_id = OBJECT_ID('smac_reports'))
            CREATE INDEX idx_smac_originator ON smac_reports(originator)
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_smac_date' AND object_id = OBJECT_ID('smac_reports'))
            CREATE INDEX idx_smac_date ON smac_reports(date_of_receipt)
    """)

    # ── ir_reports (IR only) ──────────────────────────────────────────────
    conn.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'ir_reports'
        )
        CREATE TABLE ir_reports (
            id           INT IDENTITY(1,1) PRIMARY KEY,
            doc_id       NVARCHAR(500)  NOT NULL,
            doc_name     NVARCHAR(500)  NOT NULL,
            collection   NVARCHAR(50)   NOT NULL DEFAULT 'IR',
            serial_no    NVARCHAR(20)   NULL,
            field_key    NVARCHAR(500)  NOT NULL,
            field_value  NVARCHAR(MAX)  NOT NULL
        )
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_ir_doc_id' AND object_id = OBJECT_ID('ir_reports'))
            CREATE INDEX idx_ir_doc_id ON ir_reports(doc_id)
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_ir_collection' AND object_id = OBJECT_ID('ir_reports'))
            CREATE INDEX idx_ir_collection ON ir_reports(collection)
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_ir_field_key' AND object_id = OBJECT_ID('ir_reports'))
            CREATE INDEX idx_ir_field_key ON ir_reports(field_key)
    """)

    conn.commit()
    conn.close()
    print("[StructuredTables] smac_reports and ir_reports tables ready.")


# Initialize on module load
init_db()


# ═══════════════════════════════════════════════════════════════════════════
#  SMAC FIELD MAPPER
# ═══════════════════════════════════════════════════════════════════════════

_NIL_VALUES = {"-", "–", "—", "Nil", "nil", "NIL", "N/A", "n/a", "None", "none", "-nil-", ""}

def _map_smac_fields(field_values: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Map LLM-extracted field-value pairs to smac_reports columns.
    Unmapped fields are collected into raw_fields (stored as JSON).
    """
    row: Dict[str, Any] = {
        "input_id": None, "date_of_receipt": None, "originator": None,
        "source_name": None, "grading": None, "theatre": None,
        "priority": None, "subject": None, "gist": None,
        "threat_details": None, "shared_with": None, "classification": None,
        "raw_fields": [],
    }

    for fv in field_values:
        raw_key = fv.get("field_name", "").strip()
        val     = fv.get("value", "").strip()
        key     = raw_key.lower()

        if not val or val in _NIL_VALUES:
            continue

        if any(k in key for k in ("input id", "input no", "tms id", "tms no", "tms i.d", "input i.d")):
            row["input_id"] = row["input_id"] or val
        elif any(k in key for k in ("date of receipt", "date rec", "receipt date", "date of input")):
            row["date_of_receipt"] = row["date_of_receipt"] or val
        elif "originator" in key:
            row["originator"] = row["originator"] or val
        elif "source" in key and "grading" not in key and "assess" not in key:
            row["source_name"] = row["source_name"] or val
        elif "grading" in key or "grade" in key:
            row["grading"] = (row["grading"] + " | " + val) if row["grading"] else val
        elif "theatre" in key:
            row["theatre"] = row["theatre"] or val
        elif "priority" in key:
            row["priority"] = row["priority"] or val
        elif "subject" in key:
            row["subject"] = row["subject"] or val
        elif any(k in key for k in ("threat detail", "threat assess", "threat")):
            row["threat_details"] = (row["threat_details"] + "\n" + val) if row["threat_details"] else val
        elif any(k in key for k in ("shared with", "shared by", "distribution", "forwarded to")):
            row["shared_with"] = row["shared_with"] or val
        elif any(k in key for k in ("classif", "security class")):
            row["classification"] = row["classification"] or val
        elif any(k in key for k in ("gist", "input", "content", "details", "information", "intelligence")):
            row["gist"] = (row["gist"] + "\n" + val) if row["gist"] else val
        else:
            row["raw_fields"].append({"field": raw_key, "value": val})

    row["raw_fields"] = json.dumps(row["raw_fields"], ensure_ascii=False) if row["raw_fields"] else None
    return row


# ═══════════════════════════════════════════════════════════════════════════
#  SMAC — DEDICATED TABLE STORE
# ═══════════════════════════════════════════════════════════════════════════

def store_smac_report(doc_id: str, doc_name: str, field_values: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Store a SMAC Log Report into the dedicated smac_reports table.
    Replaces any previous entry for the same doc_id (safe re-indexing).
    """
    conn = _get_conn()
    row = _map_smac_fields(field_values)

    conn.execute("DELETE FROM smac_reports WHERE doc_id = ?", (doc_id,))
    conn.execute(
        "INSERT INTO smac_reports "
        "(doc_id, doc_name, input_id, date_of_receipt, originator, "
        " source_name, grading, theatre, priority, subject, gist, "
        " threat_details, shared_with, classification, raw_fields) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            doc_id, doc_name,
            row["input_id"], row["date_of_receipt"], row["originator"],
            row["source_name"], row["grading"], row["theatre"], row["priority"],
            row["subject"], row["gist"], row["threat_details"],
            row["shared_with"], row["classification"], row["raw_fields"],
        ),
    )
    conn.commit()
    conn.close()

    stored = sum(1 for v in row.values() if v is not None and v not in ("[]", "null"))
    print(f"[StructuredTables] Stored SMAC report for {doc_name} ({stored} columns mapped)")
    return {"ok": True, "stored": stored, "doc_id": doc_id}


# ═══════════════════════════════════════════════════════════════════════════
#  IR — KEY-VALUE STORE
# ═══════════════════════════════════════════════════════════════════════════

def _store_ir_fields(
    doc_id: str,
    doc_name: str,
    collection: str,
    field_values: List[Dict[str, str]],
) -> Dict[str, Any]:
    """
    Store all field-value pairs from an IR document into ir_reports.

    field_values: list of dicts with keys:
      - "serial_no" (optional): Sl No from document
      - "field_name": the field key (Column 2)
      - "value": the field value (Column 3)
    """
    conn = _get_conn()

    # Delete any previous entries for this document (handles re-indexing)
    cur = conn.execute(
        "SELECT COUNT(*) FROM ir_reports WHERE doc_id = ? AND collection = ?",
        (doc_id, collection),
    )
    old_count = cur.fetchone()[0]
    if old_count > 0:
        conn.execute(
            "DELETE FROM ir_reports WHERE doc_id = ? AND collection = ?",
            (doc_id, collection),
        )
        print(f"[StructuredTables] Cleared {old_count} old rows for {doc_name} ({collection})")

    stored = 0
    for fv in field_values:
        fn  = fv.get("field_name", "").strip()
        val = fv.get("value", "").strip()
        sno = fv.get("serial_no", "").strip()

        if not fn or not val:
            continue
        if val in ("-", "–", "—", "Nil", "nil", "NIL", "N/A", "n/a", "None", "none", "-nil-"):
            continue

        conn.execute(
            "INSERT INTO ir_reports (doc_id, doc_name, collection, serial_no, field_key, field_value) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, doc_name, collection, sno or None, fn, val),
        )
        stored += 1

    conn.commit()
    conn.close()
    print(f"[StructuredTables] Stored {stored} fields for {doc_name} ({collection})")
    return {"ok": True, "stored": stored, "doc_id": doc_id}


def store_ir_report(doc_id: str, doc_name: str, field_values: List[Dict[str, str]]) -> Dict[str, Any]:
    return _store_ir_fields(doc_id, doc_name, "IR", field_values)


# ═══════════════════════════════════════════════════════════════════════════
#  IR — QUERY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def _get_ir_documents(collection: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return a summary of all stored IR documents (doc_id, doc_name, collection, field_count)."""
    conn = _get_conn()
    if collection:
        cur = conn.execute(
            "SELECT doc_id, doc_name, collection, COUNT(*) as field_count "
            "FROM ir_reports WHERE collection = ? "
            "GROUP BY doc_id, doc_name, collection ORDER BY doc_name",
            (collection,),
        )
    else:
        cur = conn.execute(
            "SELECT doc_id, doc_name, collection, COUNT(*) as field_count "
            "FROM ir_reports "
            "GROUP BY doc_id, doc_name, collection ORDER BY doc_name"
        )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    conn.close()
    return rows


def _get_ir_fields(doc_id: str) -> List[Dict[str, Any]]:
    """Return all fields for a specific IR document, ordered by id."""
    conn = _get_conn()
    cur = conn.execute(
        "SELECT serial_no, field_key, field_value "
        "FROM ir_reports WHERE doc_id = ? "
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
            "FROM ir_reports "
            "WHERE field_key LIKE ? AND collection = ? "
            "ORDER BY doc_name, id",
            (f"%{keyword}%", collection),
        )
    else:
        cur = conn.execute(
            "SELECT doc_id, doc_name, collection, serial_no, field_key, field_value "
            "FROM ir_reports "
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
    Return a human-readable description of both structured tables.
    This is provided to the LLM as context for NL→SQL generation.
    """
    return """
DATABASE SCHEMA — ISDIntelligence (SQL Server / T-SQL syntax)

═══════════════════════════════════════════════════════
TABLE: smac_reports   (one row per SMAC Log Report PDF)
═══════════════════════════════════════════════════════
  - id (INT, PK, auto-increment)
  - doc_id (NVARCHAR, UNIQUE) — unique document hash
  - doc_name (NVARCHAR) — filename of the PDF
  - input_id (NVARCHAR, nullable) — TMS / Input number (e.g. 'TMS-2023-0042')
  - date_of_receipt (NVARCHAR, nullable) — date the input was received
  - originator (NVARCHAR, nullable) — originating unit / organisation
  - source_name (NVARCHAR, nullable) — intelligence source name
  - grading (NVARCHAR, nullable) — source and input grading (e.g. 'A1', 'B2')
  - theatre (NVARCHAR, nullable) — operational area / theatre of operations
  - priority (NVARCHAR, nullable) — current priority level (e.g. 'HIGH', 'MEDIUM')
  - subject (NVARCHAR, nullable) — subject line / headline of the report
  - gist (NVARCHAR MAX, nullable) — main intelligence content / gist of the report
  - threat_details (NVARCHAR MAX, nullable) — specific threat assessment details
  - shared_with (NVARCHAR MAX, nullable) — distribution list / shared with units
  - classification (NVARCHAR, nullable) — classification level (SECRET, TOP SECRET, etc.)
  - raw_fields (NVARCHAR MAX, nullable) — JSON array of any unmapped fields
  - indexed_at (DATETIME) — when the document was indexed

SMAC QUERY EXAMPLES:

-- Count all SMAC reports:
SELECT COUNT(*) AS total_smac FROM smac_reports

-- Find reports by originator:
SELECT input_id, date_of_receipt, subject, theatre FROM smac_reports
WHERE originator LIKE '%Battalion%' ORDER BY date_of_receipt DESC

-- Find high-priority reports about a specific topic:
SELECT input_id, originator, subject, gist FROM smac_reports
WHERE priority LIKE '%HIGH%' AND subject LIKE '%IED%'

-- Find all reports for a specific theatre:
SELECT input_id, date_of_receipt, originator, subject FROM smac_reports
WHERE theatre LIKE '%Valley%' ORDER BY date_of_receipt DESC

-- Reports with SECRET classification:
SELECT input_id, originator, subject, classification FROM smac_reports
WHERE classification LIKE '%SECRET%'

-- Count reports by originator:
SELECT originator, COUNT(*) AS report_count FROM smac_reports
GROUP BY originator ORDER BY report_count DESC

-- Find reports shared with a specific unit:
SELECT input_id, originator, subject FROM smac_reports
WHERE shared_with LIKE '%Corps%'


═══════════════════════════════════════════════════════
TABLE: ir_reports   (key-value rows for IR Form-16 documents)
═══════════════════════════════════════════════════════
  - id (INT, PK, auto-increment)
  - doc_id (NVARCHAR) — unique document identifier
  - doc_name (NVARCHAR) — filename of the document
  - collection (NVARCHAR) — always 'IR'
  - serial_no (NVARCHAR, nullable) — serial number from the document (e.g., '1', '27a')
  - field_key (NVARCHAR) — the field name from column 2 of the Form-16 table
  - field_value (NVARCHAR MAX) — the actual value from column 3

COMMON IR FIELD NAMES (field_key values):
  - Name of accused: field_key LIKE '%Name%' AND LEN(field_key) < 50
  - Aliases / Nicknames: field_key LIKE '%Alias%'
  - Organization: field_key LIKE '%Organi%'
  - Helpers: field_key LIKE '%helper%'
  - Associates: field_key LIKE '%associate%' OR LIKE '%accomplice%'
  - Family members: field_key LIKE '%family%' OR LIKE '%father%' OR LIKE '%mother%'
  - Address: field_key LIKE '%address%'
  - Criminal cases: field_key LIKE '%criminal case%'
  - Weapons: field_key LIKE '%weapon%'
  - Modus operandi / Motive: field_key LIKE '%modus%' OR LIKE '%motive%'
  - Physical description: field_key LIKE '%height%' OR '%weight%' OR '%complexion%'
  - Mobile / Phone: field_key LIKE '%mobile%' OR LIKE '%phone%'

IR QUERY EXAMPLES:

-- Find the accused's name from an IR document:
SELECT field_value FROM ir_reports
WHERE collection = 'IR' AND field_key LIKE '%Name%'
  AND field_key NOT LIKE '%address%' AND field_key NOT LIKE '%organization%'
  AND LEN(field_key) < 50

-- All fields for a specific document:
SELECT serial_no, field_key, field_value FROM ir_reports
WHERE doc_name LIKE '%Abdul%' ORDER BY id

-- List accused names with their helpers:
SELECT d1.doc_name, d1.field_value AS accused_name, d2.field_value AS helpers
FROM ir_reports d1
LEFT JOIN ir_reports d2 ON d1.doc_id = d2.doc_id AND d2.field_key LIKE '%helper%'
WHERE d1.collection = 'IR' AND d1.field_key LIKE '%Name%'
  AND d1.field_key NOT LIKE '%address%' AND LEN(d1.field_key) < 50

-- Count IR documents:
SELECT COUNT(DISTINCT doc_id) AS ir_doc_count FROM ir_reports WHERE collection = 'IR'
"""


# ═══════════════════════════════════════════════════════════════════════════
#  CLEAR DATA
# ═══════════════════════════════════════════════════════════════════════════

def clear_all_structured_data():
    """Delete all rows from both smac_reports and ir_reports."""
    conn = _get_conn()
    conn.execute("DELETE FROM smac_reports")
    conn.execute("DELETE FROM ir_reports")
    conn.commit()
    conn.close()
    print("[StructuredTables] Cleared all smac_reports and ir_reports data.")


# ═══════════════════════════════════════════════════════════════════════════
#  SMAC — QUERY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_all_smac_reports() -> List[Dict[str, Any]]:
    """Return summary of all SMAC reports from smac_reports table."""
    conn = _get_conn()
    cur = conn.execute(
        "SELECT doc_id, doc_name, input_id, date_of_receipt, originator, "
        "       theatre, priority, subject, grading, classification, indexed_at "
        "FROM smac_reports ORDER BY indexed_at DESC"
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    conn.close()
    for r in rows:
        if r.get("indexed_at") is not None:
            r["indexed_at"] = str(r["indexed_at"])
    return rows


def get_smac_report_by_doc(doc_id: str) -> Dict[str, Any]:
    """Return all columns for a specific SMAC report."""
    conn = _get_conn()
    cur = conn.execute(
        "SELECT doc_id, doc_name, input_id, date_of_receipt, originator, "
        "       source_name, grading, theatre, priority, subject, gist, "
        "       threat_details, shared_with, classification, raw_fields, indexed_at "
        "FROM smac_reports WHERE doc_id = ?",
        (doc_id,),
    )
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    conn.close()
    if not row:
        return {}
    d = dict(zip(cols, row))
    if d.get("indexed_at") is not None:
        d["indexed_at"] = str(d["indexed_at"])
    if d.get("raw_fields"):
        try:
            d["raw_fields"] = json.loads(d["raw_fields"])
        except Exception:
            pass
    return d


# ═══════════════════════════════════════════════════════════════════════════
#  IR — PUBLIC ALIASES (called from app.py and rag.py)
# ═══════════════════════════════════════════════════════════════════════════

def get_all_ir_reports() -> List[Dict[str, Any]]:
    return _get_ir_documents("IR")

def get_ir_report_full(doc_id: str) -> List[Dict[str, Any]]:
    return _get_ir_fields(doc_id)
