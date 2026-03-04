"""
Entity Graph — Neo4j-backed entity + relationship extraction and knowledge graph
for ISD Document Intelligence V5.

Extracts named entities AND typed relationships from document chunks using the local LLM,
stores them in Neo4j graph database, and provides graph data for visualization.

Relationship types include: MEMBER_OF, WORKS_AT, SIBLING, SPOUSE, PARENT_OF, CHILD_OF,
LIVES_AT, COLLEAGUE, PARTICIPATED_IN, REPORTS_TO, LOCATED_IN, RELATED_TO, CO_OCCURRENCE.
"""

import json
import re
from typing import List, Dict, Any, Optional, Tuple

from neo4j import GraphDatabase

from ollama_client import ollama_chat
from config import PDF_MODEL, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

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
# Neo4j Driver (module-level, thread-safe)
# ---------------------------------------------------------------------------
_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ---------------------------------------------------------------------------
# Neo4j Schema Setup
# ---------------------------------------------------------------------------
def init_db():
    """Create Neo4j constraints and indexes on startup."""
    with _driver.session() as session:
        # Unique constraint on (name, type, doc_id) — prevents duplicate entity nodes
        session.run("""
            CREATE CONSTRAINT entity_unique IF NOT EXISTS
            FOR (e:Entity) REQUIRE (e.name, e.type, e.doc_id) IS UNIQUE
        """)
        # Index for case-scoped queries
        session.run("""
            CREATE INDEX entity_case IF NOT EXISTS FOR (e:Entity) ON (e.case_id)
        """)
        # Index for type-filtered queries
        session.run("""
            CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)
        """)
    print("[EntityGraph] Neo4j schema initialized.")


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
# Neo4j Storage Helpers
# ---------------------------------------------------------------------------
# Entity "key" in Neo4j context: (name, type, doc_id) tuple
EntityKey = Tuple[str, str, str]


def _insert_or_get_entity(
    session,
    name: str,
    etype: str,
    doc_id: str,
    doc_name: str,
    context: str,
    case_id=None,
) -> EntityKey:
    """
    MERGE entity node by (name, type, doc_id). Returns (name, type, doc_id) key.
    ON CREATE sets doc_name, context, case_id.
    """
    session.run(
        """
        MERGE (e:Entity {name: $name, type: $type, doc_id: $doc_id})
        ON CREATE SET e.doc_name = $doc_name, e.context = $context, e.case_id = $case_id
        """,
        name=name, type=etype, doc_id=doc_id,
        doc_name=doc_name, context=context, case_id=case_id,
    )
    return (name, etype, doc_id)


def _insert_relationship_if_absent(
    session,
    src_key: EntityKey,
    tgt_key: EntityKey,
    rel_type: str,
    doc_id: str,
    context: str,
    case_id=None,
) -> None:
    """
    MERGE relationship between two entity nodes.
    rel_type is validated against RELATIONSHIP_TYPES whitelist before interpolation
    into the Cypher string (safe — no user input reaches this function directly).
    """
    if rel_type not in RELATIONSHIP_TYPES:
        rel_type = "RELATED_TO"

    src_name, src_type, src_doc_id = src_key
    tgt_name, tgt_type, tgt_doc_id = tgt_key

    # rel_type is from a closed whitelist — interpolation is safe
    cypher = f"""
        MATCH (src:Entity {{name: $src_name, type: $src_type, doc_id: $src_doc_id}})
        MATCH (tgt:Entity {{name: $tgt_name, type: $tgt_type, doc_id: $tgt_doc_id}})
        MERGE (src)-[r:{rel_type} {{doc_id: $doc_id}}]->(tgt)
        ON CREATE SET r.context = $context, r.case_id = $case_id
    """
    session.run(
        cypher,
        src_name=src_name, src_type=src_type, src_doc_id=src_doc_id,
        tgt_name=tgt_name, tgt_type=tgt_type, tgt_doc_id=tgt_doc_id,
        doc_id=doc_id, context=context, case_id=case_id,
    )


def _resolve_entity_key(
    session, name: str, doc_id: str, case_id=None
) -> Optional[EntityKey]:
    """Find entity by name (case-insensitive) and doc_id. Returns (name, type, doc_id) or None."""
    result = session.run(
        """
        MATCH (e:Entity)
        WHERE toLower(e.name) = toLower($name) AND e.doc_id = $doc_id
          AND ($case_id IS NULL OR e.case_id = $case_id)
        RETURN e.name AS name, e.type AS type, e.doc_id AS doc_id
        LIMIT 1
        """,
        name=name.strip(), doc_id=doc_id, case_id=case_id,
    )
    row = result.single()
    return (row["name"], row["type"], row["doc_id"]) if row else None


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
    Store extracted entities and typed relationships in Neo4j.
    Falls back to CO_OCCURRENCE edges for entity pairs without explicit relationships.
    """
    with _driver.session() as session:
        entity_keys: List[EntityKey] = []
        entity_name_to_key: Dict[str, EntityKey] = {}

        for e in entities:
            try:
                key = _insert_or_get_entity(
                    session,
                    e["name"], e["type"], doc_id, doc_name, e.get("context", ""),
                    case_id=case_id,
                )
                entity_keys.append(key)
                entity_name_to_key[e["name"].lower().strip()] = key
            except Exception as ex:
                print(f"[EntityGraph] Failed to store entity {e}: {ex}")

        # Store explicit typed relationships
        linked_pairs: set = set()
        rel_count = 0

        if relationships:
            for r in relationships:
                src_name = r["source"].lower().strip()
                tgt_name = r["target"].lower().strip()

                src_key = entity_name_to_key.get(src_name)
                tgt_key = entity_name_to_key.get(tgt_name)

                if not src_key:
                    src_key = _resolve_entity_key(session, r["source"], doc_id, case_id=case_id)
                if not tgt_key:
                    tgt_key = _resolve_entity_key(session, r["target"], doc_id, case_id=case_id)

                if src_key and tgt_key and src_key != tgt_key:
                    try:
                        _insert_relationship_if_absent(
                            session, src_key, tgt_key, r["type"], doc_id,
                            r.get("context", ""), case_id=case_id,
                        )
                        linked_pairs.add((src_key, tgt_key))
                        rel_count += 1
                    except Exception:
                        pass

        # CO_OCCURRENCE edges for pairs without explicit relationships (cap at 30)
        capped_keys = entity_keys[:30]
        for i in range(len(capped_keys)):
            for j in range(i + 1, len(capped_keys)):
                pair = (capped_keys[i], capped_keys[j])
                if pair not in linked_pairs:
                    try:
                        _insert_relationship_if_absent(
                            session, capped_keys[i], capped_keys[j],
                            "CO_OCCURRENCE", doc_id, "", case_id=case_id,
                        )
                    except Exception:
                        pass

    print(f"[EntityGraph] Stored {len(entity_keys)} entities, {rel_count} typed relationships for {doc_name}")
    return {"entities_stored": len(entity_keys), "relationships_stored": rel_count, "doc_id": doc_id}


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
    Full pipeline: extract entities + relationships from chunks, store in Neo4j.

    - Caps to MAX_ENTITY_CHUNKS (60) evenly-sampled chunks.
    - Writes to Neo4j after EVERY batch so the graph starts populating immediately.
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

    with _driver.session() as session:
        for batch_idx, start in enumerate(range(0, len(chunks), batch_size)):
            batch = chunks[start : start + batch_size]
            combined_text = "\n\n---\n\n".join(
                f"[CHUNK {start + i}]\n{chunk[:2200]}" for i, chunk in enumerate(batch)
            )

            # ── LLM call ─────────────────────────────────────────────────────
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

            # ── Deduplicate entities (cross-batch) ───────────────────────────
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

            # ── Store batch entities → Neo4j ──────────────────────────────────
            entity_name_to_key: Dict[str, EntityKey] = {}
            batch_entity_keys:  List[EntityKey]       = []
            for e in batch_entities:
                try:
                    ekey = _insert_or_get_entity(
                        session, e["name"], e["type"], doc_id, doc_name,
                        e.get("context", ""), case_id=case_id,
                    )
                    batch_entity_keys.append(ekey)
                    entity_name_to_key[e["name"].lower().strip()] = ekey
                    total_entities_stored += 1
                except Exception as ex:
                    print(f"[EntityGraph] Entity insert failed ({e['name']}): {ex}")

            # ── Store batch relationships ─────────────────────────────────────
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

                src_key = entity_name_to_key.get(source.lower())
                tgt_key = entity_name_to_key.get(target.lower())
                if not src_key:
                    src_key = _resolve_entity_key(session, source, doc_id, case_id=case_id)
                if not tgt_key:
                    tgt_key = _resolve_entity_key(session, target, doc_id, case_id=case_id)
                if src_key and tgt_key and src_key != tgt_key:
                    try:
                        _insert_relationship_if_absent(
                            session, src_key, tgt_key, rtype, doc_id,
                            (r.get("context") or "")[:300], case_id=case_id,
                        )
                        linked_pairs.add((src_key, tgt_key))
                        total_rels_stored += 1
                    except Exception:
                        pass

            # CO_OCCURRENCE edges for batch entity pairs not already linked
            capped_keys = batch_entity_keys[:30]
            for i in range(len(capped_keys)):
                for j in range(i + 1, len(capped_keys)):
                    pair = (capped_keys[i], capped_keys[j])
                    if pair not in linked_pairs:
                        try:
                            _insert_relationship_if_absent(
                                session, capped_keys[i], capped_keys[j],
                                "CO_OCCURRENCE", doc_id, "", case_id=case_id,
                            )
                        except Exception:
                            pass

            # Neo4j auto-commits each session.run() — data immediately visible
            print(f"[EntityGraph] Batch {batch_idx+1}/{total_batches}: "
                  f"+{len(batch_entities)} entities | {total_entities_stored} total for {doc_name}")

            if progress_callback:
                progress_callback(batch_idx + 1, total_batches)

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
    with _driver.session() as session:
        result = session.run(
            """
            MATCH (e:Entity)
            WHERE ($case_id IS NULL OR e.case_id = $case_id)
              AND ($type_filter IS NULL OR e.type = $type_filter)
            WITH e.name AS name, e.type AS type,
                 collect(DISTINCT e.doc_name) AS doc_names,
                 count(DISTINCT e.doc_id) AS mention_count
            ORDER BY mention_count DESC, name ASC
            RETURN name, type, doc_names, mention_count
            """,
            case_id=case_id,
            type_filter=type_filter.upper() if type_filter else None,
        )
        rows = []
        for r in result:
            rows.append({
                "name": r["name"],
                "type": r["type"],
                "doc_names": ",".join(r["doc_names"]),
                "mention_count": r["mention_count"],
            })
    return rows


def get_graph_data(
    search: Optional[str] = None, limit: int = 200, case_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Return nodes + edges for force-graph visualization.
    Nodes deduplicated by (name, type) across documents.
    """
    limit = max(100, min(limit, 2000))

    with _driver.session() as session:

        if search:
            # Step 1: collect anchor names matching search + their 1-hop neighbors
            nb_result = session.run(
                """
                MATCH (anchor:Entity)
                WHERE ($case_id IS NULL OR anchor.case_id = $case_id)
                  AND toLower(anchor.name) CONTAINS toLower($search)
                WITH collect(DISTINCT anchor.name) AS anchor_names
                MATCH (anchor:Entity)
                WHERE anchor.name IN anchor_names
                  AND ($case_id IS NULL OR anchor.case_id = $case_id)
                OPTIONAL MATCH (anchor)-[]-(nbr:Entity)
                WHERE ($case_id IS NULL OR nbr.case_id = $case_id)
                WITH anchor_names + collect(DISTINCT nbr.name) AS all_names
                UNWIND all_names AS nm
                RETURN DISTINCT nm
                """,
                case_id=case_id, search=search,
            )
            visible_names = [r["nm"] for r in nb_result if r["nm"]]

            if not visible_names:
                return {"nodes": [], "edges": []}

            agg_result = session.run(
                """
                MATCH (e:Entity)
                WHERE e.name IN $names
                  AND ($case_id IS NULL OR e.case_id = $case_id)
                WITH e.name AS name, e.type AS type,
                     collect(DISTINCT e.doc_name) AS doc_names,
                     count(DISTINCT e.doc_id) AS weight,
                     collect(DISTINCT e.context)[0..5] AS contexts
                ORDER BY weight DESC, name ASC
                LIMIT $limit
                RETURN name, type, doc_names, weight, contexts
                """,
                names=visible_names, case_id=case_id, limit=limit,
            )
        else:
            agg_result = session.run(
                """
                MATCH (e:Entity)
                WHERE ($case_id IS NULL OR e.case_id = $case_id)
                WITH e.name AS name, e.type AS type,
                     collect(DISTINCT e.doc_name) AS doc_names,
                     count(DISTINCT e.doc_id) AS weight,
                     collect(DISTINCT e.context)[0..5] AS contexts
                ORDER BY weight DESC, name ASC
                LIMIT $limit
                RETURN name, type, doc_names, weight, contexts
                """,
                case_id=case_id, limit=limit,
            )

        node_rows = [dict(r) for r in agg_result]

        if not node_rows:
            return {"nodes": [], "edges": []}

        # Filter ORGANIZATION nodes that have no PERSON relationships
        org_names = [r["name"] for r in node_rows if r["type"] == "ORGANIZATION"]
        orgs_with_person_rels: set = set()
        if org_names:
            org_result = session.run(
                """
                MATCH (org:Entity)-[r]-(person:Entity)
                WHERE org.name IN $org_names
                  AND org.type = 'ORGANIZATION'
                  AND person.type = 'PERSON'
                  AND ($case_id IS NULL OR org.case_id = $case_id)
                  AND type(r) <> 'CO_OCCURRENCE'
                RETURN DISTINCT org.name AS org_name
                """,
                org_names=org_names, case_id=case_id,
            )
            orgs_with_person_rels = {r["org_name"] for r in org_result}

        node_rows = [
            r for r in node_rows
            if r["type"] != "ORGANIZATION" or r["name"] in orgs_with_person_rels
        ]

        if not node_rows:
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
                "doc_names": ",".join(row["doc_names"]),
                "contexts": " | ".join((row.get("contexts") or [])[:3])[:500],
            })

        visible_names_list = list({n["name"] for n in nodes})

        # Fetch all relationships between visible nodes
        rel_result = session.run(
            """
            MATCH (src:Entity)-[r]->(tgt:Entity)
            WHERE src.name IN $names AND tgt.name IN $names
              AND ($case_id IS NULL OR src.case_id = $case_id)
            RETURN src.name AS src_name, src.type AS src_type,
                   tgt.name AS tgt_name, tgt.type AS tgt_type,
                   type(r) AS rel_type,
                   r.context AS context
            """,
            names=visible_names_list, case_id=case_id,
        )

        # Merge edges by (src_node_idx, tgt_node_idx)
        edge_map: Dict[tuple, Dict[str, Any]] = {}
        for r in rel_result:
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
    """Delete entity nodes (and all their relationships). Scoped to case_id if given."""
    with _driver.session() as session:
        if case_id is not None:
            session.run(
                "MATCH (e:Entity {case_id: $case_id}) DETACH DELETE e",
                case_id=case_id,
            )
        else:
            session.run("MATCH (e:Entity) DETACH DELETE e")
    return {"ok": True, "message": "Graph data cleared."}
