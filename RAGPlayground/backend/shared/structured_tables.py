"""
Structured Tables — EAV storage for SMAC, IR, and Chargesheet documents.
RAG Playground version with case_name support, ir_statements, and chargesheet tables.
"""

import re
from typing import List, Dict, Any, Optional
from shared.mysql_db import get_conn


def _get_conn():
    return get_conn()


def init_db():
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS smac_reports (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            doc_id       VARCHAR(255)  NOT NULL,
            doc_name     VARCHAR(500)  NOT NULL,
            serial_no    VARCHAR(50)   NULL,
            field_key    VARCHAR(255)  NOT NULL,
            field_value  TEXT          NULL,
            UNIQUE KEY uq_smac_reports (doc_id, field_key)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ir_reports (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            doc_id       VARCHAR(255)  NOT NULL,
            doc_name     VARCHAR(500)  NOT NULL,
            case_name    VARCHAR(500)  NULL,
            collection   VARCHAR(100)  NOT NULL DEFAULT 'IR',
            serial_no    VARCHAR(50)   NULL,
            field_key    VARCHAR(255)  NOT NULL,
            field_value  TEXT          NULL,
            UNIQUE KEY uq_ir_reports (doc_id, field_key)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ir_statements (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            doc_id       VARCHAR(255)  NOT NULL,
            doc_name     VARCHAR(500)  NOT NULL,
            case_name    VARCHAR(500)  NULL,
            statement    LONGTEXT      NULL,
            UNIQUE KEY uq_ir_statements (doc_id)
        )
    """)

    # Chargesheets — one per case, stores full text sections
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chargesheets (
            id                  INT AUTO_INCREMENT PRIMARY KEY,
            doc_id              VARCHAR(255)  NOT NULL,
            doc_name            VARCHAR(500)  NOT NULL,
            case_name           VARCHAR(500)  NOT NULL,
            accused_details     LONGTEXT      NULL,
            absconder_details   LONGTEXT      NULL,
            suspect_details     LONGTEXT      NULL,
            brief_description   LONGTEXT      NULL,
            UNIQUE KEY uq_cs_case (case_name)
        )
    """)

    # Chargesheet persons — individual person rows for structured lookups
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chargesheet_persons (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            doc_id        VARCHAR(255)  NOT NULL,
            case_name     VARCHAR(500)  NOT NULL,
            serial_no     VARCHAR(50)   NULL,
            person_name   VARCHAR(500)  NOT NULL,
            person_type   VARCHAR(50)   NOT NULL,
            details       TEXT          NULL,
            INDEX idx_csp_case (case_name),
            INDEX idx_csp_type (person_type),
            INDEX idx_csp_doc (doc_id)
        )
    """)

    # Chargesheet fields — EAV for header fields (FIR no, sections of law, etc.)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chargesheet_fields (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            doc_id        VARCHAR(255)  NOT NULL,
            case_name     VARCHAR(500)  NOT NULL,
            serial_no     VARCHAR(50)   NULL,
            field_key     VARCHAR(255)  NOT NULL,
            field_value   TEXT          NULL,
            UNIQUE KEY uq_csf (doc_id, field_key),
            INDEX idx_csf_case (case_name)
        )
    """)

    # ── Scan Test tables (decoupled from main pipeline) ──────────────

    cur.execute("""
        CREATE TABLE IF NOT EXISTS scantest_chargesheets (
            id                  INT AUTO_INCREMENT PRIMARY KEY,
            doc_id              VARCHAR(255)  NOT NULL,
            doc_name            VARCHAR(500)  NOT NULL,
            case_name           VARCHAR(500)  NULL,
            accused_details     LONGTEXT      NULL,
            absconder_details   LONGTEXT      NULL,
            suspect_details     LONGTEXT      NULL,
            brief_description   LONGTEXT      NULL,
            full_text_chars     INT            DEFAULT 0,
            UNIQUE KEY uq_st_cs (doc_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS scantest_chargesheet_persons (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            doc_id        VARCHAR(255)  NOT NULL,
            case_name     VARCHAR(500)  NULL,
            serial_no     VARCHAR(50)   NULL,
            person_name   VARCHAR(500)  NOT NULL,
            person_type   VARCHAR(50)   NOT NULL,
            details       TEXT          NULL,
            INDEX idx_st_csp_doc (doc_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS scantest_chargesheet_fields (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            doc_id        VARCHAR(255)  NOT NULL,
            case_name     VARCHAR(500)  NULL,
            serial_no     VARCHAR(50)   NULL,
            field_key     VARCHAR(255)  NOT NULL,
            field_value   TEXT          NULL,
            UNIQUE KEY uq_st_csf (doc_id, field_key),
            INDEX idx_st_csf_doc (doc_id)
        )
    """)

    # Indexes
    for idx_sql in [
        "CREATE INDEX idx_ir_case_name ON ir_reports(case_name)",
        "CREATE INDEX idx_ir_doc_id ON ir_reports(doc_id)",
        "CREATE INDEX idx_ir_field_key ON ir_reports(field_key)",
        "CREATE INDEX idx_irst_case_name ON ir_statements(case_name)",
        "CREATE INDEX idx_irst_doc_id ON ir_statements(doc_id)",
    ]:
        try:
            cur.execute(idx_sql)
        except Exception:
            pass

    conn.commit()
    cur.close()
    conn.close()
    print("[StructuredTables] All tables ready (main + scantest).")


init_db()


_NIL_VALUES = {"-", "–", "—", "Nil", "nil", "NIL", "N/A", "n/a", "None", "none", "-nil-", ""}


# ═══════════════════════════════════════════════════════════════════════════
#  SMAC
# ═══════════════════════════════════════════════════════════════════════════

def store_smac_report(doc_id, doc_name, field_values):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM smac_reports WHERE doc_id = %s", (doc_id,))
    stored = 0
    for fv in field_values:
        fn = fv.get("field_name", "").strip()
        val = fv.get("value", "").strip()
        sno = fv.get("serial_no", "").strip()
        if not fn or not val or val in _NIL_VALUES:
            continue
        cur.execute(
            "INSERT INTO smac_reports (doc_id, doc_name, serial_no, field_key, field_value) VALUES (%s, %s, %s, %s, %s)",
            (doc_id, doc_name, sno or None, fn, val),
        )
        stored += 1
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True, "stored": stored}


# ═══════════════════════════════════════════════════════════════════════════
#  IR — Field Storage
# ═══════════════════════════════════════════════════════════════════════════

def store_ir_report(doc_id, doc_name, field_values, case_name=None):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM ir_reports WHERE doc_id = %s", (doc_id,))
    stored = 0
    seen_keys = set()
    for fv in field_values:
        fn = fv.get("field_name", "").strip()
        val = fv.get("value", "").strip()
        sno = fv.get("serial_no", "").strip()
        if not fn or not val or val in _NIL_VALUES:
            continue
        # Truncate field_key if too long
        if len(fn) > 250:
            fn = fn[:250]
        # Handle duplicate field keys — append serial_no to make unique
        dedup_key = fn
        if dedup_key in seen_keys:
            dedup_key = f"{fn} ({sno})" if sno else f"{fn} (#{stored + 1})"
        if dedup_key in seen_keys:
            dedup_key = f"{fn} (#{stored + 1})"
        seen_keys.add(dedup_key)
        try:
            cur.execute(
                "INSERT INTO ir_reports (doc_id, doc_name, case_name, collection, serial_no, field_key, field_value) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (doc_id, doc_name, case_name, "IR", sno or None, dedup_key, val),
            )
            stored += 1
        except Exception as e:
            print(f"[StructuredTables] Skip field '{fn[:50]}': {e}")
            continue
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True, "stored": stored}


# ═══════════════════════════════════════════════════════════════════════════
#  IR — Statement Storage
# ═══════════════════════════════════════════════════════════════════════════

def store_ir_statement(doc_id, doc_name, statement_text, case_name=None):
    """Store the full statement/narrative text for an IR document."""
    if not statement_text or not statement_text.strip():
        return {"ok": True, "stored": 0}

    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM ir_statements WHERE doc_id = %s", (doc_id,))
    cur.execute(
        "INSERT INTO ir_statements (doc_id, doc_name, case_name, statement) VALUES (%s, %s, %s, %s)",
        (doc_id, doc_name, case_name, statement_text.strip()),
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"[StructuredTables] Stored statement for {doc_name} ({len(statement_text)} chars)")
    return {"ok": True, "stored": 1}


def get_ir_statement(doc_id):
    """Get the full statement text for an IR document."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT statement FROM ir_statements WHERE doc_id = %s", (doc_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row["statement"] if row else None


# ═══════════════════════════════════════════════════════════════════════════
#  IR — Query Functions
# ═══════════════════════════════════════════════════════════════════════════

def get_ir_fields(doc_id):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT serial_no, field_key, field_value FROM ir_reports WHERE doc_id = %s ORDER BY id", (doc_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def find_ir_docs_by_name(name_words):
    conn = _get_conn()
    cur = conn.cursor()
    conditions = ["doc_name LIKE %s" for _ in name_words]
    params = [f"%{w}%" for w in name_words]
    if not conditions:
        cur.close()
        conn.close()
        return []
    sql = f"SELECT DISTINCT doc_id, doc_name, case_name FROM ir_reports WHERE {' AND '.join(conditions)}"
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def find_ir_docs_by_case(case_name):
    """Find all IR documents belonging to a case."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT doc_id, doc_name FROM ir_reports WHERE case_name = %s ORDER BY doc_name",
        (case_name,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def get_all_case_names():
    """Return all distinct case names from IR reports and chargesheets."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT case_name FROM ("
        "  SELECT case_name FROM ir_reports WHERE case_name IS NOT NULL "
        "  UNION "
        "  SELECT case_name FROM chargesheets WHERE case_name IS NOT NULL"
        ") AS all_cases ORDER BY case_name"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [r["case_name"] for r in rows]


def execute_sql_query(sql):
    sql_stripped = sql.strip().upper()
    if not sql_stripped.startswith("SELECT"):
        return [{"error": "Only SELECT queries are allowed"}]
    dangerous = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "TRUNCATE"]
    for kw in dangerous:
        if re.search(rf'\b{kw}\b', sql_stripped):
            return [{"error": f"Forbidden keyword: {kw}"}]
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


# ═══════════════════════════════════════════════════════════════════════════
#  Chargesheet — Storage
# ═══════════════════════════════════════════════════════════════════════════

def store_chargesheet(doc_id, doc_name, case_name, accused_details=None,
                      absconder_details=None, suspect_details=None,
                      brief_description=None):
    """Store or replace chargesheet summary for a case."""
    conn = _get_conn()
    cur = conn.cursor()
    # Replace if exists (one chargesheet per case)
    cur.execute("DELETE FROM chargesheets WHERE case_name = %s", (case_name,))
    cur.execute(
        "INSERT INTO chargesheets (doc_id, doc_name, case_name, accused_details, "
        "absconder_details, suspect_details, brief_description) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (doc_id, doc_name, case_name, accused_details, absconder_details,
         suspect_details, brief_description),
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"[StructuredTables] Stored chargesheet for case '{case_name}'")
    return {"ok": True}


def store_chargesheet_persons(doc_id, case_name, persons):
    """Store individual person entries from chargesheet.

    persons: list of {"serial_no": str, "person_name": str,
                      "person_type": str, "details": str}
    person_type should be one of: 'accused', 'suspect', 'absconder'
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM chargesheet_persons WHERE doc_id = %s", (doc_id,))
    stored = 0
    for p in persons:
        name = p.get("person_name", "").strip()
        ptype = p.get("person_type", "accused").strip().lower()
        if not name or len(name) < 2:
            continue
        cur.execute(
            "INSERT INTO chargesheet_persons (doc_id, case_name, serial_no, "
            "person_name, person_type, details) VALUES (%s, %s, %s, %s, %s, %s)",
            (doc_id, case_name, p.get("serial_no"), name, ptype,
             p.get("details")),
        )
        stored += 1
    conn.commit()
    cur.close()
    conn.close()
    print(f"[StructuredTables] Stored {stored} chargesheet persons for case '{case_name}'")
    return {"ok": True, "stored": stored}


def store_chargesheet_fields(doc_id, case_name, field_values):
    """Store header-level EAV fields from chargesheet (FIR no, sections of law, etc.)."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM chargesheet_fields WHERE doc_id = %s", (doc_id,))
    stored = 0
    seen_keys = set()
    for fv in field_values:
        fn = fv.get("field_name", "").strip()
        val = fv.get("value", "").strip()
        sno = fv.get("serial_no", "").strip()
        if not fn or not val or val in _NIL_VALUES:
            continue
        if len(fn) > 250:
            fn = fn[:250]
        dedup_key = fn
        if dedup_key in seen_keys:
            dedup_key = f"{fn} ({sno})" if sno else f"{fn} (#{stored + 1})"
        seen_keys.add(dedup_key)
        try:
            cur.execute(
                "INSERT INTO chargesheet_fields (doc_id, case_name, serial_no, "
                "field_key, field_value) VALUES (%s, %s, %s, %s, %s)",
                (doc_id, case_name, sno or None, dedup_key, val),
            )
            stored += 1
        except Exception as e:
            print(f"[StructuredTables] Skip chargesheet field '{fn[:50]}': {e}")
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True, "stored": stored}


# ═══════════════════════════════════════════════════════════════════════════
#  Chargesheet — Query Functions
# ═══════════════════════════════════════════════════════════════════════════

def get_chargesheet(case_name):
    """Get the chargesheet summary for a case."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM chargesheets WHERE case_name = %s", (case_name,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def get_chargesheet_persons(case_name, person_type=None):
    """Get persons from chargesheet. Optionally filter by type (accused/suspect/absconder)."""
    conn = _get_conn()
    cur = conn.cursor()
    if person_type:
        cur.execute(
            "SELECT serial_no, person_name, person_type, details "
            "FROM chargesheet_persons WHERE case_name = %s AND person_type = %s "
            "ORDER BY id", (case_name, person_type),
        )
    else:
        cur.execute(
            "SELECT serial_no, person_name, person_type, details "
            "FROM chargesheet_persons WHERE case_name = %s ORDER BY person_type, id",
            (case_name,),
        )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def get_chargesheet_fields(case_name):
    """Get header fields from chargesheet (FIR no, sections of law, etc.)."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT serial_no, field_key, field_value FROM chargesheet_fields "
        "WHERE case_name = %s ORDER BY id", (case_name,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def clear_all():
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM smac_reports")
    cur.execute("DELETE FROM ir_reports")
    cur.execute("DELETE FROM ir_statements")
    cur.execute("DELETE FROM chargesheets")
    cur.execute("DELETE FROM chargesheet_persons")
    cur.execute("DELETE FROM chargesheet_fields")
    conn.commit()
    cur.close()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
#  Scan Test — Storage (decoupled from main pipeline)
# ═══════════════════════════════════════════════════════════════════════════

def scantest_store_chargesheet(doc_id, doc_name, case_name=None,
                                accused_details=None, absconder_details=None,
                                suspect_details=None, brief_description=None,
                                full_text_chars=0):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM scantest_chargesheets WHERE doc_id = %s", (doc_id,))
    cur.execute(
        "INSERT INTO scantest_chargesheets (doc_id, doc_name, case_name, accused_details, "
        "absconder_details, suspect_details, brief_description, full_text_chars) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (doc_id, doc_name, case_name, accused_details, absconder_details,
         suspect_details, brief_description, full_text_chars),
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}


def scantest_store_persons(doc_id, case_name, persons):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM scantest_chargesheet_persons WHERE doc_id = %s", (doc_id,))
    stored = 0
    for p in persons:
        name = p.get("person_name", "").strip()
        ptype = p.get("person_type", "accused").strip().lower()
        if not name or len(name) < 2:
            continue
        cur.execute(
            "INSERT INTO scantest_chargesheet_persons (doc_id, case_name, serial_no, "
            "person_name, person_type, details) VALUES (%s, %s, %s, %s, %s, %s)",
            (doc_id, case_name, p.get("serial_no"), name, ptype, p.get("details")),
        )
        stored += 1
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True, "stored": stored}


def scantest_store_fields(doc_id, case_name, field_values):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM scantest_chargesheet_fields WHERE doc_id = %s", (doc_id,))
    stored = 0
    seen_keys = set()
    for fv in field_values:
        fn = fv.get("field_name", "").strip()
        val = fv.get("value", "").strip()
        sno = fv.get("serial_no", "").strip()
        if not fn or not val or val in _NIL_VALUES:
            continue
        if len(fn) > 250:
            fn = fn[:250]
        dedup_key = fn
        if dedup_key in seen_keys:
            dedup_key = f"{fn} ({sno})" if sno else f"{fn} (#{stored + 1})"
        seen_keys.add(dedup_key)
        try:
            cur.execute(
                "INSERT INTO scantest_chargesheet_fields (doc_id, case_name, serial_no, "
                "field_key, field_value) VALUES (%s, %s, %s, %s, %s)",
                (doc_id, case_name, sno or None, dedup_key, val),
            )
            stored += 1
        except Exception:
            pass
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True, "stored": stored}


# ═══════════════════════════════════════════════════════════════════════════
#  Scan Test — Query Functions
# ═══════════════════════════════════════════════════════════════════════════

def scantest_get_chargesheet(doc_id):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM scantest_chargesheets WHERE doc_id = %s", (doc_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def scantest_get_persons(doc_id):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT serial_no, person_name, person_type, details "
        "FROM scantest_chargesheet_persons WHERE doc_id = %s ORDER BY person_type, id",
        (doc_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def scantest_get_fields(doc_id):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT serial_no, field_key, field_value FROM scantest_chargesheet_fields "
        "WHERE doc_id = %s ORDER BY id", (doc_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def scantest_list_docs():
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT doc_id, doc_name, case_name, full_text_chars FROM scantest_chargesheets ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def scantest_clear():
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM scantest_chargesheets")
    cur.execute("DELETE FROM scantest_chargesheet_persons")
    cur.execute("DELETE FROM scantest_chargesheet_fields")
    conn.commit()
    cur.close()
    conn.close()
