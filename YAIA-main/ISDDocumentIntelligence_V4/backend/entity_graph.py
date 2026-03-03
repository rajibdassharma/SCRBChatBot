"""
Entity Graph — MSSQL-backed entity + relationship extraction and knowledge graph
for ISD Document Intelligence.

Extracts named entities AND typed relationships from document chunks using the local LLM,
stores them in SQL Server, and provides graph data for visualization.

Relationship types include: MEMBER_OF, WORKS_AT, SIBLING, SPOUSE, PARENT_OF, CHILD_OF,
LIVES_AT, COLLEAGUE, PARTICIPATED_IN, REPORTS_TO, LOCATED_IN, RELATED_TO, CO_OCCURRENCE.
"""

import json
import re
from typing import List, Dict, Any, Optional, Tuple

import pyodbc

from ollama_client import ollama_chat
from config import PDF_MODEL
from mssql_db import get_conn, _fetchone, _fetchall

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ENTITY_TYPES = {"PERSON", "ORGANIZATION", "LOCATION", "PHONE", "VEHICLE", "OTHER"}

_NOISE_NAMES: set = {
    "myself", "i", "he", "she", "they", "we", "you", "him", "her", "them",
    "the accused", "the suspect", "the subject", "the person", "the individual",
    "the informant", "the complainant", "the victim", "the witness",
    "unknown", "n/a", "nil", "none", "not known", "not applicable",
}

RELATIONSHIP_TYPES = {
    "MEMBER_OF", "WORKS_AT", "SIBLING", "SPOUSE", "PARENT_OF", "CHILD_OF",
    "LIVES_AT", "COLLEAGUE", "PARTICIPATED_IN", "REPORTS_TO",
    "LOCATED_IN", "RELATED_TO", "CO_OCCURRENCE",
    # Helper/associate relationships for IR documents
    "HELPER_OF", "ADVOCATE_OF", "DOCTOR_OF", "FINANCIER_OF",
    "ASSOCIATE_OF", "ACCOMPLICE_OF", "HANDLER_OF", "SYMPATHIZER_OF",
    "ACCUSED_WITH", "CO_ACCUSED",
}


# ---------------------------------------------------------------------------
# MSSQL Schema Setup
# ---------------------------------------------------------------------------
def _get_conn() -> pyodbc.Connection:
    return get_conn()


def init_db():
    conn = _get_conn()

    # ── entities table ───────────────────────────────────────────────────────
    conn.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'entities'
        )
        CREATE TABLE entities (
            id         INT IDENTITY(1,1) PRIMARY KEY,
            name       NVARCHAR(500)  NOT NULL,
            type       NVARCHAR(100)  NOT NULL,
            doc_id     NVARCHAR(500)  NOT NULL,
            doc_name   NVARCHAR(500)  NOT NULL,
            context    NVARCHAR(MAX)  NULL,
            case_id    INT            NULL,
            CONSTRAINT uq_entities UNIQUE (name, type, doc_id)
        )
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_entities_name' AND object_id = OBJECT_ID('entities'))
            CREATE INDEX idx_entities_name   ON entities(name)
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_entities_type' AND object_id = OBJECT_ID('entities'))
            CREATE INDEX idx_entities_type   ON entities(type)
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_entities_doc_id' AND object_id = OBJECT_ID('entities'))
            CREATE INDEX idx_entities_doc_id ON entities(doc_id)
    """)

    # ── relationships table ──────────────────────────────────────────────────
    conn.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'relationships'
        )
        CREATE TABLE relationships (
            id                 INT IDENTITY(1,1) PRIMARY KEY,
            source_entity_id   INT            NOT NULL,
            target_entity_id   INT            NOT NULL,
            relationship_type  NVARCHAR(200)  NOT NULL DEFAULT 'CO_OCCURRENCE',
            doc_id             NVARCHAR(500)  NOT NULL,
            context            NVARCHAR(MAX)  NULL DEFAULT '',
            case_id            INT            NULL,
            FOREIGN KEY (source_entity_id) REFERENCES entities(id) ON DELETE NO ACTION,
            FOREIGN KEY (target_entity_id) REFERENCES entities(id) ON DELETE NO ACTION,
            CONSTRAINT uq_relationships UNIQUE (source_entity_id, target_entity_id, relationship_type, doc_id)
        )
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_rel_source' AND object_id = OBJECT_ID('relationships'))
            CREATE INDEX idx_rel_source ON relationships(source_entity_id)
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_rel_target' AND object_id = OBJECT_ID('relationships'))
            CREATE INDEX idx_rel_target ON relationships(target_entity_id)
    """)

    # Schema migration: add context column to relationships if absent (for older DBs)
    conn.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'relationships' AND COLUMN_NAME = 'context'
        )
        ALTER TABLE relationships ADD context NVARCHAR(MAX) NULL DEFAULT ''
    """)

    # Schema migration: add case_id column to entities if absent
    conn.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'entities' AND COLUMN_NAME = 'case_id'
        )
        ALTER TABLE entities ADD case_id INT NULL
    """)

    # Schema migration: add case_id column to relationships if absent
    conn.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'relationships' AND COLUMN_NAME = 'case_id'
        )
        ALTER TABLE relationships ADD case_id INT NULL
    """)

    conn.commit()
    conn.close()


# Initialize on module load
init_db()


# ---------------------------------------------------------------------------
# LLM Entity + Relationship Extraction
# ---------------------------------------------------------------------------
def extract_entities_and_relationships_from_chunks(
    chunks: List[str], batch_size: int = 5
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Extract named entities AND typed relationships from text chunks using the local LLM.
    Returns (entities_list, relationships_list).
    """
    all_entities: List[Dict[str, Any]] = []
    all_relationships: List[Dict[str, Any]] = []

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        combined_text = "\n\n---\n\n".join(
            # Keep most of each chunk for better recall in long IR reports.
            f"[CHUNK {start + i}]\n{chunk[:2200]}" for i, chunk in enumerate(batch)
        )

        prompt = (
            "Extract all named entities AND their relationships from the following text.\n\n"
            "ENTITY TYPES: PERSON, ORGANIZATION, LOCATION, PHONE, VEHICLE, OTHER\n"
            "- PERSON: full names of individuals\n"
            "- ORGANIZATION: companies, clubs, groups, government bodies, departments\n"
            "- LOCATION: cities, states, addresses, places\n"
            "- PHONE: phone numbers, mobile numbers\n"
            "- VEHICLE: vehicle registration numbers\n"
            "- OTHER: case numbers, account numbers, important IDs\n\n"
            "RELATIONSHIP TYPES:\n"
            "- MEMBER_OF: person belongs to a group/club/organization\n"
            "- WORKS_AT: person is employed at organization\n"
            "- SIBLING: brother or sister\n"
            "- SPOUSE: husband or wife\n"
            "- PARENT_OF / CHILD_OF: parent-child relationship\n"
            "- LIVES_AT: person resides at a location/address\n"
            "- COLLEAGUE: two people work together\n"
            "- PARTICIPATED_IN: person/group participated in an activity or event\n"
            "- REPORTS_TO: person reports to another person\n"
            "- LOCATED_IN: organization/entity is located at a place\n"
            "- HELPER_OF: person is a helper of the accused (advocate, doctor, financier, barber, mechanic, etc.)\n"
            "- ADVOCATE_OF: advocate/lawyer appearing for the accused\n"
            "- DOCTOR_OF: doctor of the accused\n"
            "- FINANCIER_OF: person who finances the accused\n"
            "- ASSOCIATE_OF: person is an associate or operative of the accused\n"
            "- ACCOMPLICE_OF: accomplice in criminal activity\n"
            "- HANDLER_OF: handler or motivator of the accused\n"
            "- SYMPATHIZER_OF: sympathizer of the accused or organization\n"
            "- ACCUSED_WITH / CO_ACCUSED: co-accused in the same case\n"
            "- RELATED_TO: any other meaningful relationship\n\n"
            "IMPORTANT FOR INTERROGATION REPORTS:\n"
            "- Extract ALL helpers mentioned (advocate, doctor, barber, financier, mechanic, receivers, etc.)\n"
            "- Extract ALL associates, accomplices, co-accused, and operatives\n"
            "- Extract ALL hideouts/safe houses/shelters/places of stay as LOCATION entities\n"
            "- Extract handler/motivator relationships (who motivated the accused)\n"
            "- Link each helper/associate to the main accused with the appropriate relationship type\n\n"
            "Return ONLY a JSON object with two arrays:\n"
            "{\n"
            '  "entities": [{"name": "...", "type": "...", "context": "brief description"}],\n'
            '  "relationships": [{"source": "entity name", "target": "entity name", '
            '"type": "RELATIONSHIP_TYPE", "context": "what connects them, activities, details"}]\n'
            "}\n\n"
            "IMPORTANT:\n"
            "- Extract ALL relationships you can find: family ties, group memberships, employment, "
            "shared activities, shared addresses, etc.\n"
            "- If a sentence contains multiple names in a list, output EACH name as a separate PERSON entity.\n"
            "- Do NOT collapse multiple associates into a single combined entity string.\n"
            "- For each relationship, the context should describe WHAT connects them.\n"
            "- source and target must match entity names exactly.\n"
            '- If no entities found, return {"entities": [], "relationships": []}\n\n'
            f"TEXT:\n{combined_text}"
        )

        try:
            response = ollama_chat(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                model=PDF_MODEL,
            )

            parsed = _parse_extraction_response(response)
            batch_entities = len(parsed.get("entities", []))
            batch_rels = len(parsed.get("relationships", []))
            print(f"[EntityGraph] Batch {start}: parsed {batch_entities} entities, {batch_rels} relationships")

            for e in parsed.get("entities", []):
                if isinstance(e, dict) and "name" in e and "type" in e:
                    etype = e["type"].upper().strip()
                    if etype not in ENTITY_TYPES:
                        etype = "OTHER"
                    name = e["name"].strip()
                    names = _split_compound_person_name(name, etype)
                    for nm in names:
                        if len(nm) >= 2 and nm.lower() not in _NOISE_NAMES:
                            all_entities.append({
                                "name": nm,
                                "type": etype,
                                "context": (e.get("context") or "")[:300],
                            })

            for r in parsed.get("relationships", []):
                if isinstance(r, dict) and "source" in r and "target" in r:
                    rtype = (r.get("type") or "RELATED_TO").upper().strip()
                    if rtype not in RELATIONSHIP_TYPES:
                        rtype = "RELATED_TO"
                    source = r["source"].strip()
                    target = r["target"].strip()
                    if (len(source) >= 2 and len(target) >= 2
                            and source.lower() not in _NOISE_NAMES
                            and target.lower() not in _NOISE_NAMES):
                        all_relationships.append({
                            "source": source,
                            "target": target,
                            "type": rtype,
                            "context": (r.get("context") or "")[:300],
                        })

        except Exception as ex:
            print(f"[EntityGraph] Extraction failed for batch starting at {start}: {ex}")

    return all_entities, all_relationships


def _parse_extraction_response(response: str) -> Dict[str, Any]:
    """Parse LLM response to extract JSON with entities and relationships."""
    result = _find_balanced_json_object(response)
    if result and isinstance(result, dict) and ("entities" in result or "relationships" in result):
        return result

    try:
        obj = json.loads(response.strip())
        if isinstance(obj, dict) and ("entities" in obj or "relationships" in obj):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass

    match = re.search(r"\[.*\]", response, re.DOTALL)
    if match:
        try:
            arr = json.loads(match.group())
            if isinstance(arr, list):
                return {"entities": arr, "relationships": []}
        except json.JSONDecodeError:
            pass

    print(f"[EntityGraph] WARNING: Could not parse LLM response ({len(response)} chars): {response[:200]}...")
    return {"entities": [], "relationships": []}


def _split_compound_person_name(name: str, etype: str) -> List[str]:
    """
    Expand compact PERSON lists into individual names.
    Example: "Amit, Rohit and Sunil" -> ["Amit", "Rohit", "Sunil"].
    """
    cleaned = (name or "").strip()
    if etype != "PERSON" or not cleaned:
        return [cleaned] if cleaned else []

    # Avoid splitting obvious single names/titles.
    if len(cleaned) < 6:
        return [cleaned]

    # Split only on common list delimiters; keep words inside a name intact.
    parts = re.split(r"\s*(?:,|;|/| and )\s*", cleaned, flags=re.IGNORECASE)
    parts = [p.strip(" -") for p in parts if p and p.strip(" -")]

    # If split produced one usable token, keep original.
    if len(parts) <= 1:
        return [cleaned]

    # Filter out noisy list artifacts.
    final_parts = []
    for p in parts:
        if len(p) < 2:
            continue
        if p.lower() in _NOISE_NAMES:
            continue
        final_parts.append(p)

    return final_parts or [cleaned]


def _find_balanced_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Find the first balanced JSON object in text using brace counting."""
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    obj = json.loads(candidate)
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    next_start = text.find("{", i + 1)
                    if next_start == -1:
                        return None
                    return _find_balanced_json_object(text[next_start:])

    return None


# ---------------------------------------------------------------------------
# Store Entities and Relationships
# ---------------------------------------------------------------------------
def _resolve_entity_id(conn: pyodbc.Connection, name: str, doc_id: str, case_id=None) -> Optional[int]:
    """Find entity ID by name (case-insensitive) and doc_id."""
    if case_id is not None:
        cur = conn.execute(
            "SELECT id FROM entities WHERE LOWER(name) = LOWER(?) AND doc_id = ? AND (case_id = ? OR case_id IS NULL)",
            (name.strip(), doc_id, case_id),
        )
    else:
        cur = conn.execute(
            "SELECT id FROM entities WHERE LOWER(name) = LOWER(?) AND doc_id = ?",
            (name.strip(), doc_id),
        )
    row = cur.fetchone()
    return row[0] if row else None


def _insert_or_get_entity(
    conn: pyodbc.Connection,
    name: str,
    etype: str,
    doc_id: str,
    doc_name: str,
    context: str,
    case_id=None,
) -> Optional[int]:
    """
    Insert entity if it doesn't exist (by name + type + doc_id).
    Returns the entity id whether inserted or already present.
    Uses OUTPUT INSERTED.id to atomically get the new row's id.
    """
    # Try to insert; OUTPUT INSERTED.id returns the id only if INSERT actually happened
    cur = conn.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM entities WHERE name = ? AND type = ? AND doc_id = ?
        )
        INSERT INTO entities (name, type, doc_id, doc_name, context, case_id)
        OUTPUT INSERTED.id
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name, etype, doc_id, name, etype, doc_id, doc_name, context, case_id),
    )
    row = cur.fetchone()
    if row:
        return row[0]  # newly inserted id

    # Row already existed — fetch its id
    cur2 = conn.execute(
        "SELECT id FROM entities WHERE name = ? AND type = ? AND doc_id = ?",
        (name, etype, doc_id),
    )
    row2 = cur2.fetchone()
    return row2[0] if row2 else None


def _insert_relationship_if_absent(
    conn: pyodbc.Connection,
    src_id: int,
    tgt_id: int,
    rel_type: str,
    doc_id: str,
    context: str,
    case_id=None,
) -> None:
    """Insert a relationship only if the (src, tgt, type, doc_id) combination doesn't exist."""
    conn.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM relationships
            WHERE source_entity_id = ? AND target_entity_id = ?
              AND relationship_type = ? AND doc_id = ?
        )
        INSERT INTO relationships (source_entity_id, target_entity_id, relationship_type, doc_id, context, case_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (src_id, tgt_id, rel_type, doc_id, src_id, tgt_id, rel_type, doc_id, context, case_id),
    )


def store_entities_and_relationships(
    doc_id: str,
    doc_name: str,
    entities: List[Dict[str, Any]],
    relationships: Optional[List[Dict[str, Any]]] = None,
    case_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Store extracted entities and typed relationships in SQL Server.
    Falls back to CO_OCCURRENCE edges for entity pairs without explicit relationships.
    """
    conn = _get_conn()
    entity_ids: List[int] = []
    entity_name_to_id: Dict[str, int] = {}

    for e in entities:
        try:
            eid = _insert_or_get_entity(
                conn,
                e["name"], e["type"], doc_id, doc_name, e.get("context", ""),
                case_id=case_id,
            )
            if eid:
                entity_ids.append(eid)
                entity_name_to_id[e["name"].lower().strip()] = eid
        except Exception as ex:
            print(f"[EntityGraph] Failed to store entity {e}: {ex}")

    # Store explicit typed relationships
    linked_pairs: set = set()
    rel_count = 0

    if relationships:
        for r in relationships:
            src_name = r["source"].lower().strip()
            tgt_name = r["target"].lower().strip()

            src_id = entity_name_to_id.get(src_name)
            tgt_id = entity_name_to_id.get(tgt_name)

            if not src_id:
                src_id = _resolve_entity_id(conn, r["source"], doc_id, case_id=case_id)
            if not tgt_id:
                tgt_id = _resolve_entity_id(conn, r["target"], doc_id, case_id=case_id)

            if src_id and tgt_id and src_id != tgt_id:
                try:
                    _insert_relationship_if_absent(
                        conn, src_id, tgt_id, r["type"], doc_id, r.get("context", ""),
                        case_id=case_id,
                    )
                    linked_pairs.add((min(src_id, tgt_id), max(src_id, tgt_id)))
                    rel_count += 1
                except Exception:
                    pass

    # CO_OCCURRENCE edges for pairs without explicit relationships (cap at 30)
    capped_ids = entity_ids[:30]
    for i in range(len(capped_ids)):
        for j in range(i + 1, len(capped_ids)):
            pair = (min(capped_ids[i], capped_ids[j]), max(capped_ids[i], capped_ids[j]))
            if pair not in linked_pairs:
                try:
                    _insert_relationship_if_absent(
                        conn, capped_ids[i], capped_ids[j], "CO_OCCURRENCE", doc_id, "",
                        case_id=case_id,
                    )
                except Exception:
                    pass

    conn.commit()
    conn.close()

    print(f"[EntityGraph] Stored {len(entity_ids)} entities, {rel_count} typed relationships for {doc_name}")
    return {"entities_stored": len(entity_ids), "relationships_stored": rel_count, "doc_id": doc_id}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def extract_and_store_entities(
    doc_id: str,
    doc_name: str,
    chunks: List[str],
    case_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Full pipeline: extract entities + relationships from chunks, store in SQL Server."""
    print(f"[EntityGraph] Starting extraction for {doc_name} ({len(chunks)} chunks)")

    # Smaller batches improve recall for dense long-form IR narratives.
    dynamic_batch_size = 3 if len(chunks) >= 30 else 5
    entities, relationships = extract_entities_and_relationships_from_chunks(
        chunks, batch_size=dynamic_batch_size
    )
    print(f"[EntityGraph] Extracted {len(entities)} entities, {len(relationships)} relationships from {doc_name}")

    # Deduplicate entities by (name_lower, type) before storing
    seen: set = set()
    unique_entities: List[Dict[str, Any]] = []
    for e in entities:
        key = (e["name"].lower().strip(), e["type"])
        if key not in seen:
            seen.add(key)
            unique_entities.append(e)

    # Deduplicate relationships
    seen_rels: set = set()
    unique_rels: List[Dict[str, Any]] = []
    for r in relationships:
        key = (r["source"].lower().strip(), r["target"].lower().strip(), r["type"])
        if key not in seen_rels:
            seen_rels.add(key)
            unique_rels.append(r)

    return store_entities_and_relationships(doc_id, doc_name, unique_entities, unique_rels, case_id=case_id)


# ---------------------------------------------------------------------------
# Query Functions
# ---------------------------------------------------------------------------

def _dedup_csv(csv_str: Optional[str]) -> str:
    """Remove duplicates from a comma-separated string while preserving order."""
    if not csv_str:
        return ""
    parts = [p for p in csv_str.split(",") if p and p.strip()]
    return ",".join(dict.fromkeys(parts))


def get_all_entities(type_filter: Optional[str] = None, case_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """List all entities, optionally filtered by type."""
    conn = _get_conn()
    if type_filter:
        if case_id is not None:
            cur = conn.execute(
                "SELECT e.name, e.type, "
                "STRING_AGG(e.doc_name, ',') AS doc_names, "
                "COUNT(DISTINCT e.doc_id) AS mention_count "
                "FROM entities e "
                "WHERE e.type = ? AND e.case_id = ? "
                "GROUP BY e.name, e.type "
                "ORDER BY mention_count DESC",
                (type_filter.upper(), case_id),
            )
        else:
            cur = conn.execute(
                "SELECT e.name, e.type, "
                "STRING_AGG(e.doc_name, ',') AS doc_names, "
                "COUNT(DISTINCT e.doc_id) AS mention_count "
                "FROM entities e "
                "WHERE e.type = ? "
                "GROUP BY e.name, e.type "
                "ORDER BY mention_count DESC",
                (type_filter.upper(),),
            )
    else:
        if case_id is not None:
            cur = conn.execute(
                "SELECT e.name, e.type, "
                "STRING_AGG(e.doc_name, ',') AS doc_names, "
                "COUNT(DISTINCT e.doc_id) AS mention_count "
                "FROM entities e "
                "WHERE e.case_id = ? "
                "GROUP BY e.name, e.type "
                "ORDER BY mention_count DESC",
                (case_id,),
            )
        else:
            cur = conn.execute(
                "SELECT e.name, e.type, "
                "STRING_AGG(e.doc_name, ',') AS doc_names, "
                "COUNT(DISTINCT e.doc_id) AS mention_count "
                "FROM entities e "
                "GROUP BY e.name, e.type "
                "ORDER BY mention_count DESC"
            )
    rows = _fetchall(cur)
    conn.close()

    for row in rows:
        row["doc_names"] = _dedup_csv(row.get("doc_names"))
    return rows


def get_graph_data(
    search: Optional[str] = None, limit: int = 200, case_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Return nodes + edges for force-graph visualization.
    Nodes deduplicated by (name, type) across documents.
    """
    conn = _get_conn()
    limit = max(100, min(limit, 2000))

    # Build case_id filter fragment
    if case_id is not None:
        case_filter_sql = " AND e.case_id = ?"
    else:
        case_filter_sql = ""

    if search:
        # Matching entities
        search_params: List[Any] = [limit, f"%{search}%"]
        if case_id is not None:
            search_params.append(case_id)
        cur = conn.execute(
            "SELECT TOP(?) e.name, e.type, "
            "STRING_AGG(e.doc_name, ',') AS doc_names, "
            "COUNT(DISTINCT e.doc_id) AS weight, "
            "STRING_AGG(ISNULL(e.context, ''), ',') AS contexts "
            "FROM entities e "
            f"WHERE e.name LIKE ?{case_filter_sql} "
            "GROUP BY e.name, e.type "
            "ORDER BY weight DESC, e.name ASC",
            search_params,
        )
        node_rows = _fetchall(cur)

        # Also include entities connected to matching ones
        matching_names = [r["name"] for r in node_rows]
        if matching_names:
            ph = ",".join(["?" for _ in matching_names])
            cur2 = conn.execute(
                f"SELECT id FROM entities WHERE name IN ({ph})",
                matching_names,
            )
            matching_eids = [r[0] for r in cur2.fetchall()]

            if matching_eids:
                ph2 = ",".join(["?" for _ in matching_eids])
                cur3 = conn.execute(
                    f"SELECT DISTINCT target_entity_id AS eid FROM relationships "
                    f"WHERE source_entity_id IN ({ph2}) "
                    f"UNION "
                    f"SELECT DISTINCT source_entity_id AS eid FROM relationships "
                    f"WHERE target_entity_id IN ({ph2})",
                    matching_eids + matching_eids,
                )
                connected_eids = [r[0] for r in cur3.fetchall()]

                if connected_eids:
                    ph3 = ",".join(["?" for _ in connected_eids])
                    connected_params: List[Any] = [limit] + connected_eids
                    if case_id is not None:
                        connected_params.append(case_id)
                    cur4 = conn.execute(
                        f"SELECT TOP(?) e.name, e.type, "
                        f"STRING_AGG(e.doc_name, ',') AS doc_names, "
                        f"COUNT(DISTINCT e.doc_id) AS weight, "
                        f"STRING_AGG(ISNULL(e.context, ''), ',') AS contexts "
                        f"FROM entities e "
                        f"WHERE e.id IN ({ph3}){case_filter_sql} "
                        f"GROUP BY e.name, e.type "
                        f"ORDER BY weight DESC, e.name ASC",
                        connected_params,
                    )
                    connected_rows = _fetchall(cur4)
                    existing_keys = {(r["name"], r["type"]) for r in node_rows}
                    for cr in connected_rows:
                        if (cr["name"], cr["type"]) not in existing_keys:
                            node_rows.append(cr)
                            existing_keys.add((cr["name"], cr["type"]))
    else:
        no_search_params: List[Any] = [limit]
        if case_id is not None:
            no_search_params.append(case_id)
        cur = conn.execute(
            "SELECT TOP(?) e.name, e.type, "
            "STRING_AGG(e.doc_name, ',') AS doc_names, "
            "COUNT(DISTINCT e.doc_id) AS weight, "
            "STRING_AGG(ISNULL(e.context, ''), ',') AS contexts "
            "FROM entities e "
            + (f"WHERE e.case_id = ? " if case_id is not None else "")
            + "GROUP BY e.name, e.type "
            "ORDER BY weight DESC, e.name ASC",
            no_search_params,
        )
        node_rows = _fetchall(cur)

    # Deduplicate STRING_AGG results in Python
    for row in node_rows:
        row["doc_names"] = _dedup_csv(row.get("doc_names"))
        row["contexts"] = _dedup_csv(row.get("contexts"))

    # Filter ORGANIZATION nodes that have no explicit PERSON relationships
    if node_rows:
        org_names = [r["name"] for r in node_rows if r["type"] == "ORGANIZATION"]
        orgs_with_person_rels: set = set()
        if org_names:
            ph = ",".join(["?" for _ in org_names])
            cur_org = conn.execute(
                f"SELECT DISTINCT e_org.name "
                f"FROM entities e_org "
                f"JOIN relationships r "
                f"  ON (r.source_entity_id = e_org.id OR r.target_entity_id = e_org.id) "
                f"JOIN entities e_other "
                f"  ON e_other.id = CASE "
                f"       WHEN r.source_entity_id = e_org.id THEN r.target_entity_id "
                f"       ELSE r.source_entity_id END "
                f"WHERE e_org.name IN ({ph}) AND e_org.type = 'ORGANIZATION' "
                f"  AND e_other.type = 'PERSON' "
                f"  AND r.relationship_type != 'CO_OCCURRENCE'",
                org_names,
            )
            orgs_with_person_rels = {r[0] for r in cur_org.fetchall()}
        node_rows = [
            r for r in node_rows
            if r["type"] != "ORGANIZATION" or r["name"] in orgs_with_person_rels
        ]

    # Build node list and lookup maps
    nodes: List[Dict[str, Any]] = []
    entity_name_type_to_node_id: Dict[tuple, int] = {}

    for i, row in enumerate(node_rows):
        node_key = (row["name"], row["type"])
        entity_name_type_to_node_id[node_key] = i
        nodes.append(
            {
                "id": i,
                "name": row["name"],
                "type": row["type"],
                "weight": row["weight"],
                "doc_names": row["doc_names"],
                "contexts": (row.get("contexts") or "")[:500],
            }
        )

    if not nodes:
        conn.close()
        return {"nodes": [], "edges": []}

    # Get all entity DB ids for visible node set
    visible_names = list({n["name"] for n in nodes})
    ph = ",".join(["?" for _ in visible_names])
    cur_ent = conn.execute(
        f"SELECT id, name, type FROM entities WHERE name IN ({ph})",
        visible_names,
    )
    entity_rows = _fetchall(cur_ent)

    entity_id_to_key: Dict[int, tuple] = {}
    for er in entity_rows:
        entity_id_to_key[er["id"]] = (er["name"], er["type"])

    entity_ids = list(entity_id_to_key.keys())
    if not entity_ids:
        conn.close()
        return {"nodes": nodes, "edges": []}

    # Fetch relationships where both endpoints are visible
    ph2 = ",".join(["?" for _ in entity_ids])
    cur_rel = conn.execute(
        f"SELECT source_entity_id, target_entity_id, relationship_type, "
        f"ISNULL(context, '') AS context "
        f"FROM relationships "
        f"WHERE source_entity_id IN ({ph2}) AND target_entity_id IN ({ph2})",
        entity_ids + entity_ids,
    )
    rel_rows = _fetchall(cur_rel)

    # Merge edges by (src_node, tgt_node)
    edge_map: Dict[tuple, Dict[str, Any]] = {}
    for r in rel_rows:
        src_key = entity_id_to_key.get(r["source_entity_id"])
        tgt_key = entity_id_to_key.get(r["target_entity_id"])
        if src_key and tgt_key:
            src_node = entity_name_type_to_node_id.get(src_key)
            tgt_node = entity_name_type_to_node_id.get(tgt_key)
            if src_node is not None and tgt_node is not None and src_node != tgt_node:
                edge_key = (min(src_node, tgt_node), max(src_node, tgt_node))
                rtype = r["relationship_type"]
                rcontext = r["context"] or ""

                if edge_key not in edge_map:
                    edge_map[edge_key] = {
                        "source": edge_key[0],
                        "target": edge_key[1],
                        "types": [],
                        "contexts": [],
                    }

                if rtype not in edge_map[edge_key]["types"]:
                    edge_map[edge_key]["types"].append(rtype)
                if rcontext and rcontext not in edge_map[edge_key]["contexts"]:
                    edge_map[edge_key]["contexts"].append(rcontext)

    edges: List[Dict[str, Any]] = []
    for _key, edata in edge_map.items():
        types = edata["types"]
        non_cooccurrence = [t for t in types if t != "CO_OCCURRENCE"]
        primary_type = non_cooccurrence[0] if non_cooccurrence else "CO_OCCURRENCE"
        edges.append({
            "source": edata["source"],
            "target": edata["target"],
            "type": primary_type,
            "types": types,
            "context": " | ".join(edata["contexts"][:3]),
        })

    conn.close()
    return {"nodes": nodes, "edges": edges}


def clear_graph_data(case_id: Optional[int] = None) -> Dict[str, Any]:
    """Delete entities and relationships. If case_id is given, only delete for that case."""
    conn = _get_conn()
    if case_id is not None:
        conn.execute("DELETE FROM relationships WHERE case_id = ?", (case_id,))
        conn.execute("DELETE FROM entities WHERE case_id = ?", (case_id,))
    else:
        conn.execute("DELETE FROM relationships")
        conn.execute("DELETE FROM entities")
    conn.commit()
    conn.close()
    return {"ok": True, "message": "Graph data cleared."}
