"""
Structured Tables for ISD Document Intelligence.

Two tables (both EAV — Entity-Attribute-Value):
  - smac_reports : key-value store for SMAC Log Report fields
  - ir_reports   : key-value store for IR Form-16 fields

Both tables use the same schema: (doc_id, doc_name, serial_no, field_key, field_value).
This avoids rigid column mapping and preserves all fields exactly as extracted.
"""

import json
import re
from typing import List, Dict, Any, Optional

from mysql_db import get_conn, _fetchone, _fetchall


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------
def _get_conn():
    return get_conn()


# ═══════════════════════════════════════════════════════════════════════════
#  SCHEMA CREATION
# ═══════════════════════════════════════════════════════════════════════════

def init_db():
    """Create smac_reports and ir_reports tables if they don't exist."""
    conn = _get_conn()
    cur = conn.cursor()

    # ── smac_reports (EAV — same structure as ir_reports) ─────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS smac_reports (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            doc_id       VARCHAR(255)  NOT NULL,
            doc_name     VARCHAR(500)  NOT NULL,
            serial_no    VARCHAR(50)   NULL,
            field_key    VARCHAR(255)  NOT NULL,
            field_value  TEXT          NULL,
            case_id      INT           NULL,
            UNIQUE KEY uq_smac_reports (doc_id, field_key)
        )
    """)

    try:
        cur.execute("CREATE INDEX idx_smac_doc_id ON smac_reports(doc_id)")
    except Exception:
        pass
    try:
        cur.execute("CREATE INDEX idx_smac_field_key ON smac_reports(field_key)")
    except Exception:
        pass

    # ── ir_reports (IR only) ──────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ir_reports (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            doc_id       VARCHAR(255)  NOT NULL,
            doc_name     VARCHAR(500)  NOT NULL,
            collection   VARCHAR(100)  NOT NULL DEFAULT 'IR',
            serial_no    VARCHAR(50)   NULL,
            field_key    VARCHAR(255)  NOT NULL,
            field_value  TEXT          NULL,
            case_id      INT           NULL,
            UNIQUE KEY uq_ir_reports (doc_id, field_key)
        )
    """)

    try:
        cur.execute("CREATE INDEX idx_ir_doc_id ON ir_reports(doc_id)")
    except Exception:
        pass
    try:
        cur.execute("CREATE INDEX idx_ir_collection ON ir_reports(collection)")
    except Exception:
        pass
    try:
        cur.execute("CREATE INDEX idx_ir_field_key ON ir_reports(field_key)")
    except Exception:
        pass

    conn.commit()
    cur.close()
    conn.close()
    print("[StructuredTables] smac_reports and ir_reports tables ready.")


# Initialize on module load
init_db()


# ═══════════════════════════════════════════════════════════════════════════
#  NIL VALUE FILTER
# ═══════════════════════════════════════════════════════════════════════════

_NIL_VALUES = {"-", "–", "—", "Nil", "nil", "NIL", "N/A", "n/a", "None", "none", "-nil-", ""}


# ═══════════════════════════════════════════════════════════════════════════
#  SMAC — EAV STORE
# ═══════════════════════════════════════════════════════════════════════════

def store_smac_report(doc_id: str, doc_name: str, field_values: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Store a SMAC Log Report into smac_reports (EAV table).
    Each field becomes one row: (doc_id, doc_name, serial_no, field_key, field_value).
    Replaces any previous entries for the same doc_id (safe re-indexing).
    """
    conn = _get_conn()
    cur = conn.cursor()

    # Delete any previous entries for this document
    cur.execute("DELETE FROM smac_reports WHERE doc_id = %s", (doc_id,))

    stored = 0
    for fv in field_values:
        fn  = fv.get("field_name", "").strip()
        val = fv.get("value", "").strip()
        sno = fv.get("serial_no", "").strip()

        if not fn or not val:
            continue
        if val in _NIL_VALUES:
            continue

        cur.execute(
            "INSERT INTO smac_reports (doc_id, doc_name, serial_no, field_key, field_value) "
            "VALUES (%s, %s, %s, %s, %s)",
            (doc_id, doc_name, sno or None, fn, val),
        )
        stored += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"[StructuredTables] Stored {stored} fields for {doc_name} (SMAC)")
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
    cur = conn.cursor()

    # Delete any previous entries for this document (handles re-indexing)
    cur.execute(
        "DELETE FROM ir_reports WHERE doc_id = %s AND collection = %s",
        (doc_id, collection),
    )
    if cur.rowcount > 0:
        print(f"[StructuredTables] Cleared {cur.rowcount} old rows for {doc_name} ({collection})")

    stored = 0
    for fv in field_values:
        fn  = fv.get("field_name", "").strip()
        val = fv.get("value", "").strip()
        sno = fv.get("serial_no", "").strip()

        if not fn or not val:
            continue
        if val in ("-", "–", "—", "Nil", "nil", "NIL", "N/A", "n/a", "None", "none", "-nil-"):
            continue

        cur.execute(
            "INSERT INTO ir_reports (doc_id, doc_name, collection, serial_no, field_key, field_value) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (doc_id, doc_name, collection, sno or None, fn, val),
        )
        stored += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"[StructuredTables] Stored {stored} fields for {doc_name} ({collection})")
    return {"ok": True, "stored": stored, "doc_id": doc_id}


def store_ir_report(doc_id: str, doc_name: str, field_values: List[Dict[str, str]]) -> Dict[str, Any]:
    return _store_ir_fields(doc_id, doc_name, "IR", field_values)


# ═══════════════════════════════════════════════════════════════════════════
#  SMAC — QUERY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_all_smac_reports() -> List[Dict[str, Any]]:
    """Return summary of all SMAC reports (doc_id, doc_name, field_count)."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT doc_id, doc_name, COUNT(*) as field_count "
        "FROM smac_reports "
        "GROUP BY doc_id, doc_name ORDER BY doc_name"
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def get_smac_report_by_doc(doc_id: str) -> List[Dict[str, Any]]:
    """Return all fields for a specific SMAC report, ordered by id."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT serial_no, field_key, field_value "
        "FROM smac_reports WHERE doc_id = %s "
        "ORDER BY id",
        (doc_id,),
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


# ═══════════════════════════════════════════════════════════════════════════
#  IR — QUERY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def _get_ir_documents(collection: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return a summary of all stored IR documents (doc_id, doc_name, collection, field_count)."""
    conn = _get_conn()
    cur = conn.cursor()
    if collection:
        cur.execute(
            "SELECT doc_id, doc_name, collection, COUNT(*) as field_count "
            "FROM ir_reports WHERE collection = %s "
            "GROUP BY doc_id, doc_name, collection ORDER BY doc_name",
            (collection,),
        )
    else:
        cur.execute(
            "SELECT doc_id, doc_name, collection, COUNT(*) as field_count "
            "FROM ir_reports "
            "GROUP BY doc_id, doc_name, collection ORDER BY doc_name"
        )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def _get_ir_fields(doc_id: str) -> List[Dict[str, Any]]:
    """Return all fields for a specific IR document, ordered by id."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT serial_no, field_key, field_value "
        "FROM ir_reports WHERE doc_id = %s "
        "ORDER BY id",
        (doc_id,),
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


# ═══════════════════════════════════════════════════════════════════════════
#  SEARCH FIELDS — routes to correct table based on collection
# ═══════════════════════════════════════════════════════════════════════════

def search_fields(keyword: str, collection: Optional[str] = None) -> List[Dict[str, Any]]:
    """Search for fields by keyword in field_key. Routes SMAC → smac_reports, IR → ir_reports."""
    conn = _get_conn()
    cur = conn.cursor()

    is_smac = collection and (collection == "SMAC" or collection.startswith("SMAC_c"))

    if is_smac:
        cur.execute(
            "SELECT doc_id, doc_name, serial_no, field_key, field_value "
            "FROM smac_reports "
            "WHERE field_key LIKE %s "
            "ORDER BY doc_name, id",
            (f"%{keyword}%",),
        )
    elif collection:
        cur.execute(
            "SELECT doc_id, doc_name, collection, serial_no, field_key, field_value "
            "FROM ir_reports "
            "WHERE field_key LIKE %s AND collection = %s "
            "ORDER BY doc_name, id",
            (f"%{keyword}%", collection),
        )
    else:
        # No collection specified — search both tables
        cur.execute(
            "SELECT doc_id, doc_name, 'SMAC' as collection, serial_no, field_key, field_value "
            "FROM smac_reports WHERE field_key LIKE %s "
            "UNION ALL "
            "SELECT doc_id, doc_name, collection, serial_no, field_key, field_value "
            "FROM ir_reports WHERE field_key LIKE %s "
            "ORDER BY doc_name",
            (f"%{keyword}%", f"%{keyword}%"),
        )

    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def find_ir_docs_by_name(name_words: List[str]) -> List[Dict[str, Any]]:
    """Search IR documents by name words in doc_name. Returns list of {doc_id, doc_name}."""
    conn = _get_conn()
    cur = conn.cursor()

    conditions = []
    params = []
    for w in name_words:
        conditions.append("doc_name LIKE %s")
        params.append(f"%{w}%")

    if not conditions:
        cur.close()
        conn.close()
        return []

    where = " AND ".join(conditions)
    sql = f"SELECT DISTINCT doc_id, doc_name FROM ir_reports WHERE {where} ORDER BY doc_name"
    # Print executable SQL for debugging
    debug_sql = sql
    for p in params:
        debug_sql = debug_sql.replace("%s", f"'{p}'", 1)
    print(f"[StructuredTables] {debug_sql}")
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()  # DictCursor returns list of dicts directly
    cur.close()
    conn.close()
    print(f"[StructuredTables] find_ir_docs_by_name({name_words}) → {len(rows)} docs")
    return rows


def find_ir_docs_by_name_or(words: List[str], min_score: int = 2) -> List[Dict[str, Any]]:
    """Search IR documents using OR matching with scoring. Returns docs sorted by match count."""
    conn = _get_conn()
    cur = conn.cursor()

    if not words:
        cur.close()
        conn.close()
        return []

    # Build scoring SQL with a subquery
    score_parts = []
    score_params = []
    for w in words:
        score_parts.append("(CASE WHEN doc_name LIKE %s THEN 1 ELSE 0 END)")
        score_params.append(f"%{w}%")

    score_expr = " + ".join(score_parts)

    sql = (
        f"SELECT doc_id, doc_name, ({score_expr}) as score "
        f"FROM (SELECT DISTINCT doc_id, doc_name FROM ir_reports) AS docs "
        f"HAVING score >= %s "
        f"ORDER BY score DESC, doc_name"
    )
    all_params = score_params + [min_score]

    debug_sql = sql
    for p in all_params:
        debug_sql = debug_sql.replace("%s", f"'{p}'", 1)
    print(f"[StructuredTables] {debug_sql}")

    cur.execute(sql, tuple(all_params))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    print(f"[StructuredTables] find_ir_docs_by_name_or({words}, min={min_score}) → {len(rows)} docs")
    return rows


# ═══════════════════════════════════════════════════════════════════════════
#  SQL QUERY EXECUTION (for NL→SQL pipeline)
# ═══════════════════════════════════════════════════════════════════════════

def execute_sql_query(sql: str) -> List[Dict[str, Any]]:
    """
    Execute a read-only SQL query against MySQL and return results as list of dicts.
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
    cur = conn.cursor()
    try:
        cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows] if rows else []
    except Exception as e:
        cur.close()
        conn.close()
        return [{"error": str(e)}]


def get_table_schema_description() -> str:
    """
    Return a human-readable description of both structured tables.
    This is provided to the LLM as context for NL→SQL generation.
    """
    return """
DATABASE SCHEMA — ISDIntelligence (MySQL syntax)

═══════════════════════════════════════════════════════
TABLE: smac_reports   (key-value rows for SMAC Log Report documents)
═══════════════════════════════════════════════════════
  - id (INT, PK, auto-increment)
  - doc_id (VARCHAR) — unique document identifier
  - doc_name (VARCHAR) — filename of the PDF
  - serial_no (VARCHAR, nullable) — serial number from the document (e.g., '1', '9')
  - field_key (VARCHAR) — the field name from column 2 of the SMAC table
  - field_value (TEXT, nullable) — the actual value from column 3
  - case_id (INT, nullable) — case identifier

COMMON SMAC FIELD NAMES (field_key values):
  - InputID, DateOfReceipt, Originator, RequestFrom, RequestTo
  - State, Activity, InputEntryDate, Gist, SharedWith, SharedByMAC
  - Reference, Modus, Grading, InputType, ActionTaken, Attachments

SMAC QUERY EXAMPLES:

-- Count all SMAC reports:
SELECT COUNT(DISTINCT doc_id) AS total_smac FROM smac_reports

-- Find reports by originator:
SELECT DISTINCT doc_id, doc_name FROM smac_reports
WHERE field_key = 'Originator' AND field_value LIKE '%Battalion%'

-- Find reports about a specific topic (search gist):
SELECT doc_id, doc_name, field_value AS gist FROM smac_reports
WHERE field_key = 'Gist' AND field_value LIKE '%IED%'

-- Get all fields for a specific document:
SELECT serial_no, field_key, field_value FROM smac_reports
WHERE doc_name LIKE '%SomeReport%' ORDER BY id

-- List all originators with report counts:
SELECT field_value AS originator, COUNT(DISTINCT doc_id) AS report_count
FROM smac_reports WHERE field_key = 'Originator'
GROUP BY field_value ORDER BY report_count DESC

-- Get originator and gist for each document:
SELECT d1.doc_name, d1.field_value AS originator, d2.field_value AS gist
FROM smac_reports d1
LEFT JOIN smac_reports d2 ON d1.doc_id = d2.doc_id AND d2.field_key = 'Gist'
WHERE d1.field_key = 'Originator'


═══════════════════════════════════════════════════════
TABLE: ir_reports   (key-value rows for IR Form-16 documents)
═══════════════════════════════════════════════════════
  - id (INT, PK, auto-increment)
  - doc_id (VARCHAR) — unique document identifier
  - doc_name (VARCHAR) — filename of the document
  - collection (VARCHAR) — always 'IR'
  - serial_no (VARCHAR, nullable) — serial number from the document (e.g., '1', '27a')
  - field_key (VARCHAR) — the field name from column 2 of the Form-16 table
  - field_value (TEXT, nullable) — the actual value from column 3
  - case_id (INT, nullable) — case identifier

COMMON IR FIELD NAMES (field_key values):
  - Name of accused: field_key LIKE '%Name%' AND CHAR_LENGTH(field_key) < 50
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
  AND CHAR_LENGTH(field_key) < 50

-- All fields for a specific document:
SELECT serial_no, field_key, field_value FROM ir_reports
WHERE doc_name LIKE '%Abdul%' ORDER BY id

-- List accused names with their helpers:
SELECT d1.doc_name, d1.field_value AS accused_name, d2.field_value AS helpers
FROM ir_reports d1
LEFT JOIN ir_reports d2 ON d1.doc_id = d2.doc_id AND d2.field_key LIKE '%helper%'
WHERE d1.collection = 'IR' AND d1.field_key LIKE '%Name%'
  AND d1.field_key NOT LIKE '%address%' AND CHAR_LENGTH(d1.field_key) < 50

-- Count IR documents:
SELECT COUNT(DISTINCT doc_id) AS ir_doc_count FROM ir_reports WHERE collection = 'IR'
"""


# ═══════════════════════════════════════════════════════════════════════════
#  CLEAR DATA
# ═══════════════════════════════════════════════════════════════════════════

def clear_all_structured_data():
    """Delete all rows from both smac_reports and ir_reports."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM smac_reports")
    cur.execute("DELETE FROM ir_reports")
    conn.commit()
    cur.close()
    conn.close()
    print("[StructuredTables] Cleared all smac_reports and ir_reports data.")


# ═══════════════════════════════════════════════════════════════════════════
#  IR — PUBLIC ALIASES (called from app.py and rag.py)
# ═══════════════════════════════════════════════════════════════════════════

def get_all_ir_reports() -> List[Dict[str, Any]]:
    return _get_ir_documents("IR")

def get_ir_report_full(doc_id: str) -> List[Dict[str, Any]]:
    return _get_ir_fields(doc_id)
