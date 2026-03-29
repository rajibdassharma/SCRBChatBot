"""
RAG pipeline for IR (Interrogation Report) documents.

Indexing: parse DOCX tables → store fields in MySQL (ir_reports) + ChromaDB (chroma_db_ir_v6)
Q&A:     find document by name (MySQL) → get all fields → build focused prompt → LLM answer
"""

import os
import re
import uuid
from typing import Dict, List, Any, Optional

import chromadb

from config import (
    CHROMA_PATH_IR, EMBED_MODEL, PDF_MODEL,
)
from ollama_client import ollama_embed, ollama_embed_batch, ollama_chat
from structured_tables import store_ir_report, find_ir_docs_by_name, find_ir_docs_by_name_or, execute_sql_query, get_table_schema_description
from ir_parser import parse_ir_document


# -------------------------------------------------------------------
# ChromaDB client — IR only
# -------------------------------------------------------------------
_client = chromadb.PersistentClient(path=CHROMA_PATH_IR)
_collection_name = "IR_db"
_collection = None


def _get_collection() -> chromadb.Collection:
    global _collection
    if _collection is None:
        _collection = _client.get_or_create_collection(name=_collection_name)
    return _collection


# -------------------------------------------------------------------
# Duplicate check
# -------------------------------------------------------------------
def _doc_exists(filename: str) -> Optional[str]:
    """Check if a document with this filename is already indexed. Returns doc_id or None."""
    col = _get_collection()
    # Check ChromaDB metadata for existing doc_name
    try:
        results = col.get(
            where={"doc_name": filename},
            include=["metadatas"],
            limit=1,
        )
        if results and results.get("metadatas") and len(results["metadatas"]) > 0:
            return results["metadatas"][0].get("doc_id")
    except Exception:
        pass
    return None


# -------------------------------------------------------------------
# Index IR document
# -------------------------------------------------------------------
def index_ir(file_path: str, filename: str, source: str = "digital") -> Dict[str, Any]:
    """
    Index an IR document (DOCX/DOC).

    1. Check for duplicates by filename
    2. Parse tables → field list
    3. Store in MySQL (ir_reports)
    4. Embed and store in ChromaDB
    """
    # Step 1: Duplicate check
    existing_id = _doc_exists(filename)
    if existing_id:
        print(f"[RAG-IR] Duplicate: '{filename}' already indexed (doc_id={existing_id[:12]}...)")
        return {"ok": False, "error": f"Document '{filename}' is already indexed", "doc_id": existing_id}

    # Step 2: Parse
    fields, accused_name = parse_ir_document(file_path, filename)
    if not fields:
        return {"ok": False, "error": f"No fields extracted from '{filename}'"}

    doc_id = str(uuid.uuid4())
    print(f"[RAG-IR] Indexing '{filename}': {len(fields)} fields, accused='{accused_name}', doc_id={doc_id[:12]}...")

    # Step 3: Store in MySQL
    try:
        field_values = []
        for f in fields:
            field_values.append({
                "field_name": f["field_key"],
                "value": f["field_value"],
                "serial_no": f["serial_no"],
            })
        store_ir_report(doc_id, filename, field_values)
        print(f"[RAG-IR] MySQL: stored {len(field_values)} fields")
    except Exception as e:
        print(f"[RAG-IR] MySQL store failed: {e}")
        return {"ok": False, "error": f"MySQL storage failed: {e}"}

    # Step 4: Embed and store in ChromaDB
    try:
        # Build text units for embedding: "field_key: field_value"
        units = []
        metas = []
        for f in fields:
            text = f"{f['field_key']}: {f['field_value']}" if f["field_value"] else f["field_key"]
            units.append(text)
            metas.append({
                "doc_id": doc_id,
                "doc_name": filename,
                "doc_type": os.path.splitext(filename)[1].lower().lstrip("."),
                "field_name": f["field_key"],
                "serial_no": f["serial_no"],
                "source": source,
            })

        # Filter out very short units
        filtered_units = []
        filtered_metas = []
        for u, m in zip(units, metas):
            if len(u.strip()) >= 5:
                filtered_units.append(u)
                filtered_metas.append(m)

        if not filtered_units:
            return {"ok": True, "doc_id": doc_id, "doc_name": filename, "chunks": 0,
                    "warning": "All fields were empty"}

        # Batch embed
        print(f"[RAG-IR] Embedding {len(filtered_units)} units...")
        embeddings = ollama_embed_batch(filtered_units, model=EMBED_MODEL)

        # Store in ChromaDB
        ids = [f"{doc_id}_{i}" for i in range(len(filtered_units))]
        _get_collection().add(
            ids=ids,
            embeddings=embeddings,
            documents=filtered_units,
            metadatas=filtered_metas,
        )
        print(f"[RAG-IR] ChromaDB: stored {len(filtered_units)} chunks")

    except Exception as e:
        print(f"[RAG-IR] ChromaDB store failed: {e}")
        # MySQL already has the data — ChromaDB failed
        # Return partial success so the doc can be queried via MySQL
        return {"ok": True, "doc_id": doc_id, "doc_name": filename, "chunks": 0,
                "warning": f"ChromaDB failed: {e}, MySQL data stored"}

    return {
        "ok": True,
        "doc_id": doc_id,
        "doc_name": filename,
        "chunks": len(filtered_units),
        "fields": len(fields),
        "accused_name": accused_name,
    }


# -------------------------------------------------------------------
# Q&A: Single document
# -------------------------------------------------------------------
def _extract_person_name(question: str) -> List[str]:
    """Use LLM to extract the person's name from the question."""
    try:
        response = ollama_chat(
            [{"role": "user", "content": (
                "Extract ONLY the person's name from this question. "
                "Return ONLY the name (first name and last name), nothing else. "
                "If there is no person's name, return NONE.\n\n"
                f"Question: {question}\n\n"
                "Name:"
            )}],
            temperature=0.0,
            model=PDF_MODEL,
        )
        name = response.strip().strip('"').strip("'")
        print(f"[RAG-IR] LLM extracted name: '{name}'")

        if not name or name.upper() == "NONE":
            return []

        return [w for w in name.split() if len(w) >= 2]
    except Exception as e:
        print(f"[RAG-IR] Name extraction failed: {e}")
        return []


def _find_document(question: str) -> Optional[Dict[str, str]]:
    """
    Find the IR document matching the person name in the question.

    1. LLM extracts the person's name from the question
    2. MySQL AND search on doc_name
    3. Fallback: OR search if AND returns nothing

    Returns {doc_id, doc_name} or None.
    """
    name_words = _extract_person_name(question)
    if not name_words:
        print(f"[RAG-IR] No person name found in question")
        return None

    print(f"[RAG-IR] Searching for: {name_words}")

    # AND match — all name words must be in filename
    matched = find_ir_docs_by_name(name_words)
    if matched:
        if len(matched) == 1:
            print(f"[RAG-IR] Found: {matched[0]['doc_name']}")
            return matched[0]
        best = max(matched, key=lambda d: sum(1 for w in name_words if w.lower() in d["doc_name"].lower()))
        print(f"[RAG-IR] Best of {len(matched)}: {best['doc_name']}")
        return best

    # OR fallback — at least one name word matches
    matched = find_ir_docs_by_name_or(name_words, min_score=1)
    if matched:
        print(f"[RAG-IR] Found (OR): {matched[0]['doc_name']}")
        return matched[0]

    print(f"[RAG-IR] No document found for name: {name_words}")
    return None


def _get_all_fields(doc_id: str) -> List[Dict[str, str]]:
    """Get all fields for a document from MySQL."""
    from structured_tables import _get_conn
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT serial_no, field_key, field_value FROM ir_reports "
        "WHERE doc_id = %s ORDER BY id",
        (doc_id,),
    )
    rows = cur.fetchall()  # DictCursor returns list of dicts directly
    print(f"[RAG-IR] _get_all_fields(doc_id={doc_id}) → {len(rows)} rows")
    cur.close()
    conn.close()
    return rows


def _find_matching_fields(question: str, all_fields: List[Dict[str, str]], doc_name: str = "") -> List[Dict[str, str]]:
    """
    Use LLM to identify which field(s) match the question.

    Call 1 (field selection): Send field_keys list + question → LLM returns matching serial numbers.
    Then return only those fields for the answer prompt.
    """
    # Build field list for LLM (keys only, no values — small prompt)
    field_list = []
    for f in all_fields:
        sno = f.get("serial_no", "")
        key = f.get("field_key", "")
        field_list.append(f"[{sno}] {key}")

    fields_text = "\n".join(field_list)

    selection_prompt = (
        f"You are matching a user's question to fields from an Interrogation Report.\n\n"
        f"AVAILABLE FIELDS:\n{fields_text}\n\n"
        f"QUESTION: {question}\n\n"
        f"Which field(s) best answer this question? Return ONLY the serial numbers as a comma-separated list.\n"
        f"If the question is about a group (e.g., 'family'), include ALL related fields.\n"
        f"If no field matches, return 'NONE'.\n"
        f"Examples:\n"
        f"  Question: 'father name' → Answer: 25\n"
        f"  Question: 'family details' → Answer: 84,85,86,87,88,89,90,91,92,93,94,95,96\n"
        f"  Question: 'associates' → Answer: 107\n"
        f"  Question: 'date of birth' → Answer: 30\n"
        f"Return ONLY numbers separated by commas. No explanation.\n"
    )

    try:
        response = ollama_chat(
            [{"role": "user", "content": selection_prompt}],
            temperature=0.0,
            model=PDF_MODEL,
        )
        response = response.strip()
        print(f"[RAG-IR] LLM field selection: '{response}'")

        if response.upper() == "NONE":
            print(f"[RAG-IR] LLM found no matching fields")
            return all_fields

        # Parse serial numbers from response
        selected_snos = set()
        for part in re.findall(r"\d+", response):
            selected_snos.add(part)

        if not selected_snos:
            print(f"[RAG-IR] Could not parse field numbers from LLM response")
            return all_fields

        # Filter fields by selected serial numbers
        matched = [f for f in all_fields if f.get("serial_no", "") in selected_snos]
        print(f"[RAG-IR] Selected {len(matched)} field(s): serial_nos={selected_snos}")

        if matched:
            return matched

    except Exception as e:
        print(f"[RAG-IR] LLM field selection failed: {e}")

    # Fallback — return all fields
    print(f"[RAG-IR] Fallback: using all {len(all_fields)} fields")
    return all_fields


def _build_ir_prompt(question: str, fields: List[Dict[str, str]], doc_name: str) -> str:
    """Build a focused prompt with only the matching fields."""
    field_lines = []
    for f in fields:
        sno = f.get("serial_no", "")
        key = f.get("field_key", "")
        val = f.get("field_value", "")
        if val:
            val_lines = val.split("\n")
            if len(val_lines) > 1:
                indented = val_lines[0] + "\n" + "\n".join(f"    {ln}" for ln in val_lines[1:])
                field_lines.append(f"[{sno}] {key}:\n    {indented}")
            else:
                field_lines.append(f"[{sno}] {key}: {val}")
        else:
            field_lines.append(f"[{sno}] {key}: (not available)")

    fields_text = "\n".join(field_lines)

    prompt = (
        f"You are answering questions about an Interrogation Report (IR) document.\n"
        f"Document: {doc_name}\n\n"
        f"MATCHING FIELDS:\n{fields_text}\n\n"
        f"QUESTION: {question}\n\n"
        f"RULES:\n"
        f"- Answer ONLY from the fields listed above.\n"
        f"- Return the COMPLETE value exactly as stored. Do NOT summarize, truncate, or omit any part.\n"
        f"- If the value contains a numbered list, return ALL items with formatting preserved.\n"
        f"- If the field exists but has no value, say 'The field exists but no value is recorded.'\n"
        f"- If no matching field exists, say 'This information is not available in the document.'\n"
        f"- Include the field name in your answer for reference.\n"
    )
    return prompt


def ask_ir(
    question: str,
    doc_ids: Optional[List[str]] = None,
    collection_name: str = "IR",
    raw_question: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Answer a question about IR documents.

    If doc_ids is provided, answers from those specific documents.
    Otherwise, auto-detects the person name and finds the document.
    """
    q = raw_question if raw_question else question
    print(f"[RAG-IR] Question: {q[:80]}")

    # Step 1: Find the document
    doc_name = ""
    if not doc_ids:
        doc = _find_document(q)
        if not doc:
            return {"answer": "Could not identify which document to search. Please include the person's name in your question.",
                    "used_chunks": []}
        doc_ids = [doc["doc_id"]]
        doc_name = doc["doc_name"]

    # Step 2: Get all fields from MySQL
    all_fields = []
    for did in doc_ids:
        fields = _get_all_fields(did)
        if fields:
            all_fields.extend(fields)
            if not doc_name:
                doc_name = fields[0].get("doc_name", "") if "doc_name" in fields[0] else ""

    if not all_fields:
        return {"answer": "No data found for this document in the database.",
                "used_chunks": []}

    print(f"[RAG-IR] Found {len(all_fields)} fields for '{doc_name}'")

    # Step 3: Find matching fields and build prompt
    matched_fields = _find_matching_fields(q, all_fields, doc_name)
    prompt = _build_ir_prompt(q, matched_fields, doc_name)
    print(f"[RAG-IR] Prompt: {len(prompt)} chars ({len(matched_fields)} fields)")
    print(f"[RAG-IR] === FULL PROMPT ===\n{prompt}\n[RAG-IR] === END PROMPT ===")

    # Step 4: LLM answer
    try:
        answer = ollama_chat(
            [
                {"role": "system", "content": (
                    "You are an authorized internal AI assistant for Karnataka State Police (KSP). "
                    "You answer questions about Interrogation Report documents factually and concisely. "
                    "Always respond in English."
                )},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            model=PDF_MODEL,
        )
        print(f"[RAG-IR] Answer: {len(answer)} chars")
    except Exception as e:
        print(f"[RAG-IR] LLM call failed: {e}")
        return {"answer": f"Error generating answer: {e}", "used_chunks": []}

    return {
        "answer": answer,
        "used_chunks": [{"doc_id": did, "doc_name": doc_name} for did in doc_ids],
        "doc_name": doc_name,
    }


# -------------------------------------------------------------------
# Q&A: Aggregate / cross-document
# -------------------------------------------------------------------
_AGGREGATE_PATTERNS = re.compile(
    r'\b(how many|count|total number|list all|name all|show all|find all|'
    r'across all|every|each document)\b',
    re.IGNORECASE,
)


def _is_aggregate(question: str) -> bool:
    return bool(_AGGREGATE_PATTERNS.search(question))


def ask_ir_aggregate(question: str) -> Dict[str, Any]:
    """Answer aggregate questions using NL-to-SQL against ir_reports."""
    schema = get_table_schema_description()

    sql_prompt = (
        "You are a SQL expert for MySQL.\n"
        "Given the database schema and the user's question, generate a SQL SELECT query.\n\n"
        f"DATABASE SCHEMA:\n{schema}\n\n"
        f"USER QUESTION: {question}\n\n"
        "RULES:\n"
        "- Return ONLY the SQL query, no explanation.\n"
        "- Use MySQL syntax.\n"
        "- The ir_reports table stores key-value pairs per document.\n"
        "- field_key is the field name, field_value is the value.\n"
        "- Use LIKE with '%keyword%' for text matching.\n"
        "- Always use SELECT, never INSERT/UPDATE/DELETE.\n"
        "- Return doc_name for document identification.\n"
    )

    try:
        sql_response = ollama_chat(
            [{"role": "user", "content": sql_prompt}],
            temperature=0.0,
            model=PDF_MODEL,
        )

        # Extract SQL
        sql_query = sql_response.strip()
        if sql_query.startswith("```"):
            lines = sql_query.split("\n")
            sql_query = "\n".join(ln for ln in lines if not ln.strip().startswith("```")).strip()
        if sql_query.lower().startswith("sql"):
            sql_query = sql_query[3:].strip()

        print(f"[RAG-IR] NL→SQL: {sql_query}")

        rows = execute_sql_query(sql_query)
        if not rows:
            return {"answer": "No results found.", "sql": sql_query, "used_chunks": []}
        if rows and len(rows) == 1 and "error" in rows[0]:
            return {"answer": f"SQL error: {rows[0]['error']}", "sql": sql_query, "used_chunks": []}

        # Format results
        import json
        result_text = json.dumps(rows[:50], indent=2, default=str)

        answer_prompt = (
            f"USER QUESTION: {question}\n\n"
            f"SQL RESULTS ({len(rows)} rows):\n{result_text}\n\n"
            "Provide a clear, readable answer based on the results. "
            "If results are tabular, format as a list.\n"
        )

        answer = ollama_chat(
            [{"role": "user", "content": answer_prompt}],
            temperature=0.0,
            model=PDF_MODEL,
        )

        return {"answer": answer, "sql": sql_query, "used_chunks": []}

    except Exception as e:
        print(f"[RAG-IR] Aggregate query failed: {e}")
        return {"answer": f"Error: {e}", "used_chunks": []}


# -------------------------------------------------------------------
# Main entry point — routes to single-doc or aggregate
# -------------------------------------------------------------------
def ask(
    question: str,
    doc_ids: Optional[List[str]] = None,
    collection_name: str = "IR",
    raw_question: Optional[str] = None,
) -> Dict[str, Any]:
    """Main Q&A entry point for IR documents."""
    q = raw_question if raw_question else question

    if _is_aggregate(q) and not doc_ids:
        print(f"[RAG-IR] Aggregate question detected")
        return ask_ir_aggregate(q)

    return ask_ir(question=question, doc_ids=doc_ids, collection_name=collection_name, raw_question=raw_question)


# -------------------------------------------------------------------
# Document management
# -------------------------------------------------------------------
def get_indexed_doc_list() -> List[Dict[str, Any]]:
    """List all indexed IR documents from MySQL (avoids ChromaDB SQLite limits)."""
    try:
        from structured_tables import _get_conn
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT doc_id, doc_name, COUNT(*) as chunks "
            "FROM ir_reports GROUP BY doc_id, doc_name ORDER BY doc_name"
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"[RAG-IR] get_indexed_doc_list failed: {e}")
        return []


def clear_all() -> Dict[str, Any]:
    """Clear all IR data from ChromaDB."""
    global _collection
    try:
        try:
            _client.delete_collection(name=_collection_name)
        except Exception:
            pass
        _collection = _client.get_or_create_collection(name=_collection_name)
        return {"ok": True, "message": "IR ChromaDB cleared"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
