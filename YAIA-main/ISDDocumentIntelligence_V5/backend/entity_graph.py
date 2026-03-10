"""
Entity Graph — MySQL-backed entity + relationship extraction and knowledge graph
for ISD Document Intelligence V5.

Extracts named entities AND typed relationships from document chunks using the local LLM,
stores them in MySQL database, and provides graph data for visualization.

Relationship types include: MEMBER_OF, WORKS_AT, SIBLING, SPOUSE, PARENT_OF, CHILD_OF,
LIVES_AT, COLLEAGUE, PARTICIPATED_IN, REPORTS_TO, LOCATED_IN, RELATED_TO, CO_OCCURRENCE.
"""

import json
import re
from typing import List, Dict, Any, Optional, Tuple

from mysql_db import get_conn, _fetchone, _fetchall

from ollama_client import ollama_chat
from config import PDF_MODEL

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
# MySQL Schema Setup
# ---------------------------------------------------------------------------
def _get_conn():
    return get_conn()


def init_db():
    """Create MySQL tables and indexes on startup."""
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            name       VARCHAR(255)  NOT NULL,
            type       VARCHAR(100)  NOT NULL,
            doc_id     VARCHAR(255)  NOT NULL,
            doc_name   VARCHAR(500)  NOT NULL,
            context    TEXT          NULL,
            case_id    INT           NULL,
            UNIQUE KEY uq_entities (name, type, doc_id)
        )
    """)

    try:
        cur.execute("CREATE INDEX idx_entities_name ON entities(name(255))")
    except Exception:
        pass
    try:
        cur.execute("CREATE INDEX idx_entities_type ON entities(type)")
    except Exception:
        pass
    try:
        cur.execute("CREATE INDEX idx_entities_doc_id ON entities(doc_id(255))")
    except Exception:
        pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id                 INT AUTO_INCREMENT PRIMARY KEY,
            source_entity_id   INT            NOT NULL,
            target_entity_id   INT            NOT NULL,
            relationship_type  VARCHAR(200)   NOT NULL DEFAULT 'CO_OCCURRENCE',
            doc_id             VARCHAR(255)   NOT NULL,
            context            TEXT           NULL DEFAULT NULL,
            case_id            INT            NULL,
            FOREIGN KEY (source_entity_id) REFERENCES entities(id) ON DELETE NO ACTION,
            FOREIGN KEY (target_entity_id) REFERENCES entities(id) ON DELETE NO ACTION,
            UNIQUE KEY uq_relationships (source_entity_id, target_entity_id, relationship_type, doc_id)
        )
    """)
    try:
        cur.execute("CREATE INDEX idx_rel_source ON relationships(source_entity_id)")
    except Exception:
        pass
    try:
        cur.execute("CREATE INDEX idx_rel_target ON relationships(target_entity_id)")
    except Exception:
        pass

    conn.commit()
    conn.close()
    print("[EntityGraph] MySQL schema initialized.")


# Initialize on module load
init_db()


# ---------------------------------------------------------------------------
# LLM Entity + Relationship Extraction  (unchanged from V4 — pure LLM logic)
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

    if len(cleaned) < 6:
        return [cleaned]

    parts = re.split(r"\s*(?:,|;|/| and )\s*", cleaned, flags=re.IGNORECASE)
    parts = [p.strip(" -") for p in parts if p and p.strip(" -")]

    if len(parts) <= 1:
        return [cleaned]

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
# MySQL Storage Helpers
# ---------------------------------------------------------------------------

def _insert_or_get_entity(conn, name, etype, doc_id, doc_name, context, case_id=None):
    """
    INSERT IGNORE entity row by (name, type, doc_id). Returns integer id.
    """
    cur = conn.cursor()
    cur.execute(
        "INSERT IGNORE INTO entities (name, type, doc_id, doc_name, context, case_id) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (name, etype, doc_id, doc_name, context, case_id),
    )
    if cur.rowcount > 0:
        return cur.lastrowid

    # Row already existed — fetch its id
    cur.execute(
        "SELECT id FROM entities WHERE name = %s AND type = %s AND doc_id = %s",
        (name, etype, doc_id),
    )
    row = cur.fetchone()
    return row["id"] if row else None


def _insert_relationship_if_absent(conn, src_id, tgt_id, rel_type, doc_id, context, case_id=None):
    """
    INSERT IGNORE relationship between two entity ids.
    """
    cur = conn.cursor()
    cur.execute(
        "INSERT IGNORE INTO relationships "
        "(source_entity_id, target_entity_id, relationship_type, doc_id, context, case_id) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (src_id, tgt_id, rel_type, doc_id, context, case_id),
    )


def _resolve_entity_id(conn, name, doc_id, case_id=None):
    """Find entity id by name (case-insensitive) and doc_id. Returns int id or None."""
    cur = conn.cursor()
    if case_id is not None:
        cur.execute(
            "SELECT id FROM entities WHERE LOWER(name) = LOWER(%s) AND doc_id = %s AND case_id = %s",
            (name.strip(), doc_id, case_id),
        )
    else:
        cur.execute(
            "SELECT id FROM entities WHERE LOWER(name) = LOWER(%s) AND doc_id = %s",
            (name.strip(), doc_id),
        )
    row = cur.fetchone()
    return row["id"] if row else None


# ---------------------------------------------------------------------------
# Store Entities and Relationships
# ---------------------------------------------------------------------------
def store_entities_and_relationships(
    doc_id: str,
    doc_name: str,
    entities: List[Dict[str, Any]],
    relationships: Optional[List[Dict[str, Any]]] = None,
    case_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Store extracted entities and typed relationships in MySQL.
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
            if eid is not None:
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
                        conn, src_id, tgt_id, r["type"], doc_id,
                        r.get("context", ""), case_id=case_id,
                    )
                    linked_pairs.add((src_id, tgt_id))
                    rel_count += 1
                except Exception:
                    pass

    # CO_OCCURRENCE edges for pairs without explicit relationships (cap at 30)
    capped_ids = entity_ids[:30]
    for i in range(len(capped_ids)):
        for j in range(i + 1, len(capped_ids)):
            pair = (capped_ids[i], capped_ids[j])
            if pair not in linked_pairs:
                try:
                    _insert_relationship_if_absent(
                        conn, capped_ids[i], capped_ids[j],
                        "CO_OCCURRENCE", doc_id, "", case_id=case_id,
                    )
                except Exception:
                    pass

    conn.commit()
    conn.close()
    print(f"[EntityGraph] Stored {len(entity_ids)} entities, {rel_count} typed relationships for {doc_name}")
    return {"entities_stored": len(entity_ids), "relationships_stored": rel_count, "doc_id": doc_id}


# ---------------------------------------------------------------------------
# Orchestrator  (incremental — writes after every batch)
# ---------------------------------------------------------------------------

# Maximum chunks to process per document. For very large docs (200+ chunks),
# we evenly sample to keep extraction time manageable on CPU hardware.
MAX_ENTITY_CHUNKS = 60


def extract_and_store_entities(
    doc_id: str,
    doc_name: str,
    chunks: List[str],
    case_id: Optional[int] = None,
    progress_callback=None,
) -> Dict[str, Any]:
    """
    Full pipeline: extract entities + relationships from chunks, store in MySQL.

    - Caps to MAX_ENTITY_CHUNKS (60) evenly-sampled chunks.
    - Writes to MySQL after EVERY batch so the graph starts populating immediately.
    - Accepts an optional progress_callback(batch_done, batch_total).
    """
    original_count = len(chunks)
    if original_count > MAX_ENTITY_CHUNKS:
        step = original_count / MAX_ENTITY_CHUNKS
        chunks = [chunks[int(i * step)] for i in range(MAX_ENTITY_CHUNKS)]
        print(f"[EntityGraph] {doc_name}: sampled {MAX_ENTITY_CHUNKS}/{original_count} chunks")

    batch_size = 3 if len(chunks) >= 30 else 5
    total_batches = (len(chunks) + batch_size - 1) // batch_size
    print(f"[EntityGraph] Starting extraction for {doc_name} "
          f"({len(chunks)} chunks, {total_batches} batches)")

    # Cross-batch dedup sets
    seen_entity_keys: set = set()
    seen_rel_keys:    set = set()
    total_entities_stored = 0
    total_rels_stored     = 0

    # NOTE: do NOT use str.format() on this — document text may contain { } chars.
    prompt_prefix = (
        "Extract all named entities AND their relationships from the following text.\n\n"
        "ENTITY TYPES: PERSON, ORGANIZATION, LOCATION, PHONE, VEHICLE, OTHER\n"
        "- PERSON: full names of individuals\n"
        "- ORGANIZATION: companies, clubs, groups, government bodies, departments\n"
        "- LOCATION: cities, states, addresses, places\n"
        "- PHONE: phone numbers, mobile numbers\n"
        "- VEHICLE: vehicle registration numbers\n"
        "- OTHER: case numbers, account numbers, important IDs\n\n"
        "RELATIONSHIP TYPES:\n"
        "- MEMBER_OF, WORKS_AT, SIBLING, SPOUSE, PARENT_OF, CHILD_OF, LIVES_AT\n"
        "- COLLEAGUE, PARTICIPATED_IN, REPORTS_TO, LOCATED_IN\n"
        "- HELPER_OF, ADVOCATE_OF, DOCTOR_OF, FINANCIER_OF\n"
        "- ASSOCIATE_OF, ACCOMPLICE_OF, HANDLER_OF, SYMPATHIZER_OF\n"
        "- ACCUSED_WITH, CO_ACCUSED, RELATED_TO\n\n"
        "IMPORTANT FOR INTERROGATION REPORTS:\n"
        "- Extract ALL helpers (advocate, doctor, barber, financier, mechanic, etc.)\n"
        "- Extract ALL associates, accomplices, co-accused, operatives\n"
        "- Extract ALL hideouts/safe houses/shelters as LOCATION entities\n"
        "- Link each helper/associate to the accused with the correct relationship type\n\n"
        'Return ONLY valid JSON:\n'
        '{"entities": [{"name": "...", "type": "...", "context": "..."}], '
        '"relationships": [{"source": "...", "target": "...", "type": "...", "context": "..."}]}\n\n'
        "RULES:\n"
        "- List each name as a SEPARATE entity — do NOT collapse multiple names into one.\n"
        "- source and target must match entity names exactly.\n"
        '- If nothing found return {"entities": [], "relationships": []}\n\n'
        "TEXT:\n"
    )

    conn = _get_conn()
    try:
        for batch_idx, start in enumerate(range(0, len(chunks), batch_size)):
            batch = chunks[start : start + batch_size]
            combined_text = "\n\n---\n\n".join(
                f"[CHUNK {start + i}]\n{chunk[:2200]}" for i, chunk in enumerate(batch)
            )

            # -- LLM call ---------------------------------------------------------
            try:
                response = ollama_chat(
                    [{"role": "user", "content": prompt_prefix + combined_text}],
                    temperature=0.0,
                    model=PDF_MODEL,
                )
                parsed = _parse_extraction_response(response)
            except Exception as ex:
                print(f"[EntityGraph] Batch {batch_idx+1}/{total_batches} LLM failed: {ex}")
                if progress_callback:
                    progress_callback(batch_idx + 1, total_batches)
                continue

            # -- Deduplicate entities (cross-batch) --------------------------------
            batch_entities: List[Dict[str, Any]] = []
            for e in parsed.get("entities", []):
                if not (isinstance(e, dict) and "name" in e and "type" in e):
                    continue
                etype = e["type"].upper().strip()
                if etype not in ENTITY_TYPES:
                    etype = "OTHER"
                for nm in _split_compound_person_name(e["name"].strip(), etype):
                    if len(nm) >= 2 and nm.lower() not in _NOISE_NAMES:
                        key = (nm.lower().strip(), etype)
                        if key not in seen_entity_keys:
                            seen_entity_keys.add(key)
                            batch_entities.append({
                                "name": nm,
                                "type": etype,
                                "context": (e.get("context") or "")[:300],
                            })

            # -- Store batch entities -> MySQL ------------------------------------
            entity_name_to_id: Dict[str, int] = {}
            batch_entity_ids:  List[int]       = []
            for e in batch_entities:
                try:
                    eid = _insert_or_get_entity(
                        conn, e["name"], e["type"], doc_id, doc_name,
                        e.get("context", ""), case_id=case_id,
                    )
                    if eid is not None:
                        batch_entity_ids.append(eid)
                        entity_name_to_id[e["name"].lower().strip()] = eid
                        total_entities_stored += 1
                except Exception as ex:
                    print(f"[EntityGraph] Entity insert failed ({e['name']}): {ex}")

            # -- Store batch relationships -----------------------------------------
            linked_pairs: set = set()
            for r in parsed.get("relationships", []):
                if not (isinstance(r, dict) and "source" in r and "target" in r):
                    continue
                rtype = (r.get("type") or "RELATED_TO").upper().strip()
                if rtype not in RELATIONSHIP_TYPES:
                    rtype = "RELATED_TO"
                source = r["source"].strip()
                target = r["target"].strip()
                if (len(source) < 2 or len(target) < 2
                        or source.lower() in _NOISE_NAMES
                        or target.lower() in _NOISE_NAMES):
                    continue
                rel_key = (source.lower(), target.lower(), rtype)
                if rel_key in seen_rel_keys:
                    continue
                seen_rel_keys.add(rel_key)

                src_id = entity_name_to_id.get(source.lower())
                tgt_id = entity_name_to_id.get(target.lower())
                if not src_id:
                    src_id = _resolve_entity_id(conn, source, doc_id, case_id=case_id)
                if not tgt_id:
                    tgt_id = _resolve_entity_id(conn, target, doc_id, case_id=case_id)
                if src_id and tgt_id and src_id != tgt_id:
                    try:
                        _insert_relationship_if_absent(
                            conn, src_id, tgt_id, rtype, doc_id,
                            (r.get("context") or "")[:300], case_id=case_id,
                        )
                        linked_pairs.add((src_id, tgt_id))
                        total_rels_stored += 1
                    except Exception:
                        pass

            # CO_OCCURRENCE edges for batch entity pairs not already linked
            capped_ids = batch_entity_ids[:30]
            for i in range(len(capped_ids)):
                for j in range(i + 1, len(capped_ids)):
                    pair = (capped_ids[i], capped_ids[j])
                    if pair not in linked_pairs:
                        try:
                            _insert_relationship_if_absent(
                                conn, capped_ids[i], capped_ids[j],
                                "CO_OCCURRENCE", doc_id, "", case_id=case_id,
                            )
                        except Exception:
                            pass

            conn.commit()
            print(f"[EntityGraph] Batch {batch_idx+1}/{total_batches}: "
                  f"+{len(batch_entities)} entities | {total_entities_stored} total for {doc_name}")

            if progress_callback:
                progress_callback(batch_idx + 1, total_batches)
    finally:
        conn.close()

    print(f"[EntityGraph] Done: {total_entities_stored} entities, "
          f"{total_rels_stored} relationships stored for {doc_name}")
    return {
        "entities_stored": total_entities_stored,
        "relationships_stored": total_rels_stored,
        "doc_id": doc_id,
    }


# ---------------------------------------------------------------------------
# Query Functions
# ---------------------------------------------------------------------------

def get_all_entities(type_filter: Optional[str] = None, case_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """List all entities grouped by (name, type), optionally filtered by type and case."""
    conn = _get_conn()
    cur = conn.cursor()

    sql = """
        SELECT e.name, e.type,
               GROUP_CONCAT(DISTINCT e.doc_name SEPARATOR ',') AS doc_names,
               COUNT(DISTINCT e.doc_id) AS mention_count
        FROM entities e
        WHERE 1=1
    """
    params = []

    if case_id is not None:
        sql += " AND e.case_id = %s"
        params.append(case_id)
    if type_filter:
        sql += " AND e.type = %s"
        params.append(type_filter.upper())

    sql += " GROUP BY e.name, e.type ORDER BY mention_count DESC, e.name ASC"

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "name": r["name"],
            "type": r["type"],
            "doc_names": r["doc_names"] or "",
            "mention_count": r["mention_count"],
        }
        for r in rows
    ]


def get_graph_data(
    search: Optional[str] = None, limit: int = 200, case_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Return nodes + edges for force-graph visualization.
    Nodes deduplicated by (name, type) across documents.
    """
    limit = max(100, min(limit, 2000))

    conn = _get_conn()
    cur = conn.cursor()

    if search:
        # Step 1: collect entity names matching search
        match_sql = """
            SELECT DISTINCT e.name
            FROM entities e
            WHERE LOWER(e.name) LIKE %s
        """
        match_params = [f"%{search.lower()}%"]
        if case_id is not None:
            match_sql += " AND e.case_id = %s"
            match_params.append(case_id)

        cur.execute(match_sql, tuple(match_params))
        anchor_names = [r["name"] for r in cur.fetchall()]

        if not anchor_names:
            conn.close()
            return {"nodes": [], "edges": []}

        # Step 2: get 1-hop neighbors
        placeholders = ",".join(["%s"] * len(anchor_names))
        nbr_sql = f"""
            SELECT DISTINCT e2.name
            FROM relationships r
            JOIN entities e1 ON e1.id = r.source_entity_id
            JOIN entities e2 ON e2.id = r.target_entity_id
            WHERE e1.name IN ({placeholders})
        """
        nbr_params = list(anchor_names)
        if case_id is not None:
            nbr_sql += " AND e1.case_id = %s"
            nbr_params.append(case_id)

        cur.execute(nbr_sql, tuple(nbr_params))
        nbr_names = [r["name"] for r in cur.fetchall()]

        # Also get reverse direction neighbors
        nbr_sql2 = f"""
            SELECT DISTINCT e1.name
            FROM relationships r
            JOIN entities e1 ON e1.id = r.source_entity_id
            JOIN entities e2 ON e2.id = r.target_entity_id
            WHERE e2.name IN ({placeholders})
        """
        nbr_params2 = list(anchor_names)
        if case_id is not None:
            nbr_sql2 += " AND e2.case_id = %s"
            nbr_params2.append(case_id)

        cur.execute(nbr_sql2, tuple(nbr_params2))
        nbr_names2 = [r["name"] for r in cur.fetchall()]

        visible_names = list(set(anchor_names + nbr_names + nbr_names2))

        if not visible_names:
            conn.close()
            return {"nodes": [], "edges": []}

        # Step 3: aggregate entity data for visible names
        vn_placeholders = ",".join(["%s"] * len(visible_names))
        agg_sql = f"""
            SELECT e.name, e.type,
                   GROUP_CONCAT(DISTINCT e.doc_name SEPARATOR ',') AS doc_names,
                   COUNT(DISTINCT e.doc_id) AS weight,
                   IFNULL(e.context, '') AS context
            FROM entities e
            WHERE e.name IN ({vn_placeholders})
        """
        agg_params = list(visible_names)
        if case_id is not None:
            agg_sql += " AND e.case_id = %s"
            agg_params.append(case_id)
        agg_sql += " GROUP BY e.name, e.type ORDER BY weight DESC, e.name ASC LIMIT %s"
        agg_params.append(limit)

        cur.execute(agg_sql, tuple(agg_params))
    else:
        agg_sql = """
            SELECT e.name, e.type,
                   GROUP_CONCAT(DISTINCT e.doc_name SEPARATOR ',') AS doc_names,
                   COUNT(DISTINCT e.doc_id) AS weight,
                   IFNULL(e.context, '') AS context
            FROM entities e
            WHERE 1=1
        """
        agg_params = []
        if case_id is not None:
            agg_sql += " AND e.case_id = %s"
            agg_params.append(case_id)
        agg_sql += " GROUP BY e.name, e.type ORDER BY weight DESC, e.name ASC LIMIT %s"
        agg_params.append(limit)

        cur.execute(agg_sql, tuple(agg_params))

    node_rows = cur.fetchall()

    if not node_rows:
        conn.close()
        return {"nodes": [], "edges": []}

    # Filter ORGANIZATION nodes that have no PERSON relationships
    org_names = [r["name"] for r in node_rows if r["type"] == "ORGANIZATION"]
    orgs_with_person_rels: set = set()
    if org_names:
        org_placeholders = ",".join(["%s"] * len(org_names))
        org_sql = f"""
            SELECT DISTINCT e_org.name AS org_name
            FROM entities e_org
            JOIN relationships r ON (e_org.id = r.source_entity_id OR e_org.id = r.target_entity_id)
            JOIN entities e_person ON (
                (e_person.id = r.target_entity_id AND e_org.id = r.source_entity_id)
                OR (e_person.id = r.source_entity_id AND e_org.id = r.target_entity_id)
            )
            WHERE e_org.name IN ({org_placeholders})
              AND e_org.type = 'ORGANIZATION'
              AND e_person.type = 'PERSON'
              AND r.relationship_type <> 'CO_OCCURRENCE'
        """
        org_params = list(org_names)
        if case_id is not None:
            org_sql += " AND e_org.case_id = %s"
            org_params.append(case_id)

        cur.execute(org_sql, tuple(org_params))
        orgs_with_person_rels = {r["org_name"] for r in cur.fetchall()}

    node_rows = [
        r for r in node_rows
        if r["type"] != "ORGANIZATION" or r["name"] in orgs_with_person_rels
    ]

    if not node_rows:
        conn.close()
        return {"nodes": [], "edges": []}

    # Build node list
    nodes: List[Dict[str, Any]] = []
    name_type_to_idx: Dict[tuple, int] = {}
    for i, row in enumerate(node_rows):
        key = (row["name"], row["type"])
        name_type_to_idx[key] = i
        nodes.append({
            "id": i,
            "name": row["name"],
            "type": row["type"],
            "weight": row["weight"],
            "doc_names": row["doc_names"] or "",
            "contexts": (row.get("context") or "")[:500],
        })

    visible_names_list = list({n["name"] for n in nodes})

    # Fetch all relationships between visible nodes
    vn_placeholders = ",".join(["%s"] * len(visible_names_list))
    rel_sql = f"""
        SELECT e_src.name AS src_name, e_src.type AS src_type,
               e_tgt.name AS tgt_name, e_tgt.type AS tgt_type,
               r.relationship_type AS rel_type,
               r.context AS context
        FROM relationships r
        JOIN entities e_src ON e_src.id = r.source_entity_id
        JOIN entities e_tgt ON e_tgt.id = r.target_entity_id
        WHERE e_src.name IN ({vn_placeholders})
          AND e_tgt.name IN ({vn_placeholders})
    """
    rel_params = list(visible_names_list) + list(visible_names_list)
    if case_id is not None:
        rel_sql += " AND e_src.case_id = %s"
        rel_params.append(case_id)

    cur.execute(rel_sql, tuple(rel_params))
    rel_rows = cur.fetchall()

    conn.close()

    # Merge edges by (src_node_idx, tgt_node_idx)
    edge_map: Dict[tuple, Dict[str, Any]] = {}
    for r in rel_rows:
        src_key = (r["src_name"], r["src_type"])
        tgt_key = (r["tgt_name"], r["tgt_type"])
        src_idx = name_type_to_idx.get(src_key)
        tgt_idx = name_type_to_idx.get(tgt_key)
        if src_idx is None or tgt_idx is None or src_idx == tgt_idx:
            continue
        edge_key = (min(src_idx, tgt_idx), max(src_idx, tgt_idx))
        rtype = r["rel_type"]
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
    for edata in edge_map.values():
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

    return {"nodes": nodes, "edges": edges}


def clear_graph_data(case_id: Optional[int] = None) -> Dict[str, Any]:
    """Delete entity and relationship rows. Scoped to case_id if given."""
    conn = _get_conn()
    cur = conn.cursor()

    if case_id is not None:
        # Delete relationships first (FK constraint)
        cur.execute(
            "DELETE r FROM relationships r "
            "JOIN entities e ON (e.id = r.source_entity_id OR e.id = r.target_entity_id) "
            "WHERE e.case_id = %s",
            (case_id,),
        )
        cur.execute("DELETE FROM entities WHERE case_id = %s", (case_id,))
    else:
        cur.execute("DELETE FROM relationships")
        cur.execute("DELETE FROM entities")

    conn.commit()
    conn.close()
    return {"ok": True, "message": "Graph data cleared."}
