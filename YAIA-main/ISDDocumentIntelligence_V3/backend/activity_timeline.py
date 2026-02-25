"""
Activity Timeline — MSSQL-backed activity extraction and temporal intelligence
for ISD Document Intelligence.

Extracts structured activities (TMS IDs, dates, groups, participants, cross-references)
from document chunks using the local LLM, stores them in SQL Server, and provides
timeline data + Bread Crumb trail queries for visualization.
"""

import json
from typing import List, Dict, Any, Optional, Tuple

import pyodbc

from ollama_client import ollama_chat
from config import PDF_MODEL
from entity_graph import _find_balanced_json_object
from mssql_db import get_conn, _fetchone, _fetchall

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TEMPORAL_STATUSES = {"PAST", "CURRENT", "FUTURE"}


# ---------------------------------------------------------------------------
# MSSQL Schema Setup
# ---------------------------------------------------------------------------
def _get_conn() -> pyodbc.Connection:
    return get_conn()


def init_db():
    conn = _get_conn()

    # ── activities table ─────────────────────────────────────────────────────
    conn.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'activities'
        )
        CREATE TABLE activities (
            id               INT IDENTITY(1,1) PRIMARY KEY,
            tms_id           NVARCHAR(100)  NULL,
            doc_id           NVARCHAR(500)  NOT NULL,
            doc_name         NVARCHAR(500)  NOT NULL,
            activity_date    NVARCHAR(100)  NULL,
            group_name       NVARCHAR(500)  NULL,
            subject          NVARCHAR(500)  NULL,
            description      NVARCHAR(MAX)  NULL,
            temporal_status  NVARCHAR(50)   NOT NULL DEFAULT 'CURRENT',
            priority         NVARCHAR(100)  NULL,
            theatre          NVARCHAR(200)  NULL,
            participants     NVARCHAR(MAX)  NULL
        )
    """)
    # Filtered unique index: enforce uniqueness only when tms_id is not NULL
    # (SQLite allowed multiple NULL tms_ids per doc; MSSQL needs a filtered index)
    conn.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'idx_activities_tms_doc' AND object_id = OBJECT_ID('activities')
        )
        CREATE UNIQUE INDEX idx_activities_tms_doc
            ON activities(tms_id, doc_id)
            WHERE tms_id IS NOT NULL
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_activities_tms_id' AND object_id = OBJECT_ID('activities'))
            CREATE INDEX idx_activities_tms_id ON activities(tms_id)
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_activities_group' AND object_id = OBJECT_ID('activities'))
            CREATE INDEX idx_activities_group ON activities(group_name)
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_activities_date' AND object_id = OBJECT_ID('activities'))
            CREATE INDEX idx_activities_date ON activities(activity_date)
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_activities_doc_id' AND object_id = OBJECT_ID('activities'))
            CREATE INDEX idx_activities_doc_id ON activities(doc_id)
    """)

    # ── cross_references table ───────────────────────────────────────────────
    conn.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'cross_references'
        )
        CREATE TABLE cross_references (
            id              INT IDENTITY(1,1) PRIMARY KEY,
            source_tms_id   NVARCHAR(100)  NOT NULL,
            target_tms_id   NVARCHAR(100)  NOT NULL,
            context         NVARCHAR(500)  NULL,
            doc_id          NVARCHAR(500)  NOT NULL,
            CONSTRAINT uq_xref UNIQUE (source_tms_id, target_tms_id, doc_id)
        )
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_xref_source' AND object_id = OBJECT_ID('cross_references'))
            CREATE INDEX idx_xref_source ON cross_references(source_tms_id)
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_xref_target' AND object_id = OBJECT_ID('cross_references'))
            CREATE INDEX idx_xref_target ON cross_references(target_tms_id)
    """)

    conn.commit()
    conn.close()


# Initialize on module load
init_db()


# ---------------------------------------------------------------------------
# LLM Activity Extraction
# ---------------------------------------------------------------------------
def extract_activities_from_chunks(
    chunks: List[str], batch_size: int = 3
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Extract structured activities and cross-references from text chunks using the local LLM.
    Returns (activities_list, cross_references_list).
    """
    all_activities: List[Dict[str, Any]] = []
    all_xrefs: List[Dict[str, Any]] = []

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        combined_text = "\n\n---\n\n".join(
            f"[CHUNK {start + i}]\n{chunk[:2000]}" for i, chunk in enumerate(batch)
        )

        prompt = (
            "Extract all activities and cross-references from the following intelligence report text.\n\n"
            "For each ACTIVITY found, extract:\n"
            "- tms_id: The TMS identifier (e.g., TMS-2025-0412). If none found, use empty string.\n"
            "- date: The date of the activity (e.g., 'Mar 18 2025'). Extract the most specific date mentioned.\n"
            "- group: The organization/group/club conducting the activity.\n"
            "- subject: A short title/subject of the activity.\n"
            "- description: A 2-3 sentence summary of what happened or is planned.\n"
            "- temporal_status: PAST (already completed), CURRENT (ongoing), or FUTURE (planned/upcoming).\n"
            "  Determine this from language cues: past tense = PAST, present continuous = CURRENT, "
            "future tense/planned/scheduled = FUTURE.\n"
            "- priority: The priority level if mentioned (e.g., 'Informative', 'For Action', 'Routine', 'High').\n"
            "- theatre: The intelligence source type if mentioned (e.g., 'Social Media', 'OSINT', 'HUMINT').\n"
            "- participants: Array of person names involved in the activity.\n\n"
            "For each CROSS-REFERENCE found (where one report references another TMS ID):\n"
            "- source_tms_id: The TMS ID of the current report.\n"
            "- target_tms_id: The TMS ID being referenced.\n"
            "- context: Brief description of why it is referenced.\n\n"
            "Return ONLY a JSON object:\n"
            "{\n"
            '  "activities": [{"tms_id": "...", "date": "...", "group": "...", "subject": "...", '
            '"description": "...", "temporal_status": "PAST|CURRENT|FUTURE", "priority": "...", '
            '"theatre": "...", "participants": ["name1", "name2"]}],\n'
            '  "cross_references": [{"source_tms_id": "...", "target_tms_id": "...", "context": "..."}]\n'
            "}\n\n"
            "IMPORTANT:\n"
            "- Extract ALL activities mentioned, including past activities referenced in the text.\n"
            "- For cross-references, look for patterns like 'ref: TMS-XXXX-XXXX' or other TMS ID mentions.\n"
            "- participant names should be full names as they appear in the text.\n"
            '- If no activities found, return {"activities": [], "cross_references": []}\n\n'
            f"TEXT:\n{combined_text}"
        )

        try:
            response = ollama_chat(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                model=PDF_MODEL,
            )

            parsed = _parse_timeline_response(response)
            batch_acts = len(parsed.get("activities", []))
            batch_xrefs = len(parsed.get("cross_references", []))
            print(f"[Timeline] Batch {start}: parsed {batch_acts} activities, {batch_xrefs} cross-references")

            for a in parsed.get("activities", []):
                if isinstance(a, dict) and (a.get("subject") or a.get("description")):
                    status = (a.get("temporal_status") or "CURRENT").upper().strip()
                    if status not in TEMPORAL_STATUSES:
                        status = "CURRENT"
                    participants = a.get("participants", [])
                    if isinstance(participants, list):
                        participants = ", ".join(str(p) for p in participants)
                    elif not isinstance(participants, str):
                        participants = ""
                    all_activities.append({
                        "tms_id": (a.get("tms_id") or "").strip(),
                        "date": (a.get("date") or "").strip(),
                        "group": (a.get("group") or "").strip(),
                        "subject": (a.get("subject") or "").strip()[:300],
                        "description": (a.get("description") or "").strip()[:1000],
                        "temporal_status": status,
                        "priority": (a.get("priority") or "").strip(),
                        "theatre": (a.get("theatre") or "").strip(),
                        "participants": participants[:500],
                    })

            for x in parsed.get("cross_references", []):
                if isinstance(x, dict) and x.get("source_tms_id") and x.get("target_tms_id"):
                    all_xrefs.append({
                        "source_tms_id": x["source_tms_id"].strip(),
                        "target_tms_id": x["target_tms_id"].strip(),
                        "context": (x.get("context") or "").strip()[:300],
                    })

        except Exception as ex:
            print(f"[Timeline] Extraction failed for batch starting at {start}: {ex}")

    return all_activities, all_xrefs


def _parse_timeline_response(response: str) -> Dict[str, Any]:
    """Parse LLM response to extract JSON object with activities and cross_references."""
    result = _find_balanced_json_object(response)
    if result and isinstance(result, dict) and ("activities" in result or "cross_references" in result):
        return result

    try:
        obj = json.loads(response.strip())
        if isinstance(obj, dict) and ("activities" in obj or "cross_references" in obj):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass

    print(f"[Timeline] WARNING: Could not parse LLM response ({len(response)} chars): {response[:200]}...")
    return {"activities": [], "cross_references": []}


# ---------------------------------------------------------------------------
# Store Activities and Cross-References
# ---------------------------------------------------------------------------
def store_activities(
    doc_id: str,
    doc_name: str,
    activities: List[Dict[str, Any]],
    cross_references: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Store extracted activities and cross-references in SQL Server."""
    conn = _get_conn()
    act_count = 0
    xref_count = 0

    for a in activities:
        try:
            tms_id = a.get("tms_id") or None  # store as NULL when empty

            if tms_id:
                # Unique check only applies when tms_id is not NULL
                conn.execute(
                    """
                    IF NOT EXISTS (SELECT 1 FROM activities WHERE tms_id = ? AND doc_id = ?)
                    INSERT INTO activities
                        (tms_id, doc_id, doc_name, activity_date, group_name, subject,
                         description, temporal_status, priority, theatre, participants)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tms_id, doc_id,
                        tms_id, doc_id, doc_name,
                        a.get("date", ""), a.get("group", ""),
                        a.get("subject", ""), a.get("description", ""),
                        a.get("temporal_status", "CURRENT"),
                        a.get("priority", ""), a.get("theatre", ""),
                        a.get("participants", ""),
                    ),
                )
            else:
                # No tms_id — always insert (no duplicate check needed)
                conn.execute(
                    """
                    INSERT INTO activities
                        (tms_id, doc_id, doc_name, activity_date, group_name, subject,
                         description, temporal_status, priority, theatre, participants)
                    VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc_id, doc_name,
                        a.get("date", ""), a.get("group", ""),
                        a.get("subject", ""), a.get("description", ""),
                        a.get("temporal_status", "CURRENT"),
                        a.get("priority", ""), a.get("theatre", ""),
                        a.get("participants", ""),
                    ),
                )
            act_count += 1
        except Exception as ex:
            print(f"[Timeline] Failed to store activity: {ex}")

    for x in cross_references:
        try:
            conn.execute(
                """
                IF NOT EXISTS (
                    SELECT 1 FROM cross_references
                    WHERE source_tms_id = ? AND target_tms_id = ? AND doc_id = ?
                )
                INSERT INTO cross_references (source_tms_id, target_tms_id, context, doc_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    x["source_tms_id"], x["target_tms_id"], doc_id,
                    x["source_tms_id"], x["target_tms_id"], x.get("context", ""), doc_id,
                ),
            )
            xref_count += 1
        except Exception as ex:
            print(f"[Timeline] Failed to store cross-reference: {ex}")

    conn.commit()
    conn.close()
    print(f"[Timeline] Stored {act_count} activities, {xref_count} cross-references for {doc_name}")
    return {"activities_stored": act_count, "xrefs_stored": xref_count, "doc_id": doc_id}


# ---------------------------------------------------------------------------
# Orchestrator (called from app.py)
# ---------------------------------------------------------------------------
def extract_and_store_activities(
    doc_id: str,
    doc_name: str,
    chunks: List[str],
) -> Dict[str, Any]:
    """Full pipeline: extract activities + cross-references from chunks, store in SQL Server."""
    print(f"[Timeline] Starting extraction for {doc_name} ({len(chunks)} chunks)")

    activities, xrefs = extract_activities_from_chunks(chunks, batch_size=3)
    print(f"[Timeline] Extracted {len(activities)} activities, {len(xrefs)} cross-references from {doc_name}")

    # Deduplicate activities by tms_id (keep first occurrence)
    seen_tms: set = set()
    unique_activities: List[Dict[str, Any]] = []
    for a in activities:
        tms = a.get("tms_id", "")
        if tms and tms in seen_tms:
            continue
        if tms:
            seen_tms.add(tms)
        unique_activities.append(a)

    # Deduplicate cross-references
    seen_xrefs: set = set()
    unique_xrefs: List[Dict[str, Any]] = []
    for x in xrefs:
        key = (x["source_tms_id"], x["target_tms_id"])
        if key not in seen_xrefs:
            seen_xrefs.add(key)
            unique_xrefs.append(x)

    return store_activities(doc_id, doc_name, unique_activities, unique_xrefs)


# ---------------------------------------------------------------------------
# Query Functions (for API endpoints)
# ---------------------------------------------------------------------------
def get_timeline_data(
    group_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get activities sorted by date, with optional filters."""
    conn = _get_conn()

    conditions: List[str] = []
    params: List[Any] = []

    if group_filter:
        conditions.append("group_name = ?")
        params.append(group_filter)

    if status_filter and status_filter.upper() in TEMPORAL_STATUSES:
        conditions.append("temporal_status = ?")
        params.append(status_filter.upper())

    if search:
        conditions.append(
            "(subject LIKE ? OR description LIKE ? OR participants LIKE ? OR tms_id LIKE ?)"
        )
        params.extend([f"%{search}%"] * 4)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cur = conn.execute(
        f"SELECT a.*, "
        f"(SELECT COUNT(*) FROM cross_references WHERE source_tms_id = a.tms_id OR target_tms_id = a.tms_id) AS xref_count "
        f"FROM activities a {where} "
        f"ORDER BY a.activity_date DESC, a.id DESC",
        params,
    )
    rows = _fetchall(cur)
    conn.close()
    return rows


def get_breadcrumb_trail(tms_id: str) -> Dict[str, Any]:
    """
    Get the Bread Crumb trail for a given TMS ID.
    Returns the activity plus all linked activities (forward and backward references).
    """
    conn = _get_conn()

    cur_main = conn.execute(
        "SELECT * FROM activities WHERE tms_id = ?",
        (tms_id,),
    )
    main_row = _fetchone(cur_main)

    if not main_row:
        conn.close()
        return {"main": None, "trail": [], "references": []}

    cur_xref = conn.execute(
        "SELECT * FROM cross_references WHERE source_tms_id = ? OR target_tms_id = ?",
        (tms_id, tms_id),
    )
    xrefs = _fetchall(cur_xref)

    linked_tms_ids: set = set()
    for x in xrefs:
        linked_tms_ids.add(x["source_tms_id"])
        linked_tms_ids.add(x["target_tms_id"])
    linked_tms_ids.discard(tms_id)

    trail_activities: List[Dict[str, Any]] = []
    if linked_tms_ids:
        placeholders = ",".join(["?" for _ in linked_tms_ids])
        cur_trail = conn.execute(
            f"SELECT * FROM activities WHERE tms_id IN ({placeholders}) "
            f"ORDER BY activity_date ASC",
            list(linked_tms_ids),
        )
        trail_activities = _fetchall(cur_trail)

    conn.close()
    return {
        "main": main_row,
        "trail": trail_activities,
        "references": xrefs,
    }


def get_groups() -> List[Dict[str, Any]]:
    """Get distinct group names with activity counts."""
    conn = _get_conn()
    cur = conn.execute(
        "SELECT group_name, COUNT(*) AS count "
        "FROM activities "
        "WHERE group_name IS NOT NULL AND group_name != '' "
        "  AND LOWER(group_name) NOT IN ('unknown', 'n/a', 'none') "
        "GROUP BY group_name "
        "ORDER BY count DESC"
    )
    rows = _fetchall(cur)
    conn.close()
    return rows


def get_extracted_doc_ids() -> set:
    """Return set of doc_ids that already have activities extracted."""
    conn = _get_conn()
    cur = conn.execute("SELECT DISTINCT doc_id FROM activities")
    ids = {r[0] for r in cur.fetchall()}
    conn.close()
    return ids


def clear_timeline_data() -> Dict[str, Any]:
    """Delete all activities and cross-references."""
    conn = _get_conn()
    conn.execute("DELETE FROM cross_references")
    conn.execute("DELETE FROM activities")
    conn.commit()
    conn.close()
    return {"ok": True, "message": "Timeline data cleared."}
