"""
StructuredRAG Pipeline — Table Parsing → MySQL EAV → Field-Based Q&A

For IR:
  - Pure Python table parser OR LLM parser → MySQL ir_reports (with case_name)
  - Statement/narrative → MySQL ir_statements + ChromaDB chunks
  - Q&A searches both table fields AND statement

For SMAC:
  - Text extraction → MySQL smac_reports + ChromaDB → hybrid search + LLM answer

Document type (IR/SMAC) selected by user.
Case name extracted from immediate parent folder.
"""

import os
import re
import uuid
from typing import Dict, Any, List

import chromadb
from rank_bm25 import BM25Okapi

from pipelines.base import BasePipeline
from shared.document_loader import extract_text, extract_case_name
from shared.chunking import chunk_text
from shared.ollama_client import ollama_chat, ollama_embed_batch
from shared.ir_parser import parse_ir_document
from shared.structured_tables import (
    store_ir_report, store_smac_report, store_ir_statement,
    get_ir_fields, get_ir_statement, find_ir_docs_by_name,
    find_ir_docs_by_case, get_all_case_names,
    store_chargesheet, store_chargesheet_persons, store_chargesheet_fields,
    clear_all,
)
from shared.chargesheet_parser import parse_chargesheet
from config import CHROMA_PATH


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _filter_valid_embeddings(units, unit_metas, embeddings, doc_id):
    """Filter out units where embedding failed (dimension mismatch)."""
    if not embeddings:
        return [], [], [], []

    # Find the expected dimension from the first good embedding
    expected_dim = None
    for emb in embeddings:
        if len(emb) > 1:
            expected_dim = len(emb)
            break

    if not expected_dim:
        print(f"[StructuredRAG] WARNING: All embeddings failed for {doc_id}")
        return [], [], [], []

    valid_units = []
    valid_metas = []
    valid_embeddings = []
    valid_ids = []
    skipped = 0

    for i, (u, m, emb) in enumerate(zip(units, unit_metas, embeddings)):
        if len(emb) == expected_dim:
            valid_units.append(u)
            valid_metas.append(m)
            valid_embeddings.append(emb)
            valid_ids.append(f"{doc_id}_{i}")
        else:
            skipped += 1

    if skipped > 0:
        print(f"[StructuredRAG] Filtered out {skipped} failed embeddings (kept {len(valid_units)})")

    return valid_ids, valid_units, valid_metas, valid_embeddings


class StructuredRAGPipeline(BasePipeline):
    name = "StructuredRAG"
    description = "Table Parsing → MySQL EAV → Field-Based Q&A (IR + SMAC) — with case support"

    def __init__(self):
        self._client = chromadb.PersistentClient(path=os.path.join(CHROMA_PATH, "structured"))
        self._col = self._client.get_or_create_collection(name="structured_rag")
        self._bm25_docs: List[str] = []
        self._bm25_metas: List[Dict] = []
        self._bm25_index = None
        self._rebuild_bm25()
        self._doc_types: Dict[str, str] = {}

    def _rebuild_bm25(self):
        count = self._col.count()
        if count == 0:
            self._bm25_docs, self._bm25_metas, self._bm25_index = [], [], None
            return
        all_docs, all_metas = [], []
        offset = 0
        while True:
            batch = self._col.get(include=["documents", "metadatas"], limit=500, offset=offset)
            docs = batch.get("documents", [])
            metas = batch.get("metadatas", [])
            if not docs:
                break
            all_docs.extend(docs)
            all_metas.extend(metas)
            if len(docs) < 500:
                break
            offset += 500
        self._bm25_docs = all_docs
        self._bm25_metas = all_metas
        corpus = [_tokenize(d) for d in all_docs]
        self._bm25_index = BM25Okapi(corpus) if corpus else None
        print(f"[StructuredRAG] BM25 index: {len(all_docs)} chunks")

    # ── Indexing ─────────────────────────────────────────────────────

    def index(self, file_path: str, filename: str, model: str,
              doc_type: str = "SMAC", use_llm_parser: bool = False,
              case_name_override: str = None) -> Dict[str, Any]:
        doc_id = str(uuid.uuid4())
        case_name = case_name_override or extract_case_name(file_path)
        self._doc_types[doc_id] = doc_type

        if doc_type == "IR":
            return self._index_ir(file_path, filename, doc_id, model, use_llm_parser, case_name)
        else:
            return self._index_smac(file_path, filename, doc_id, model, case_name)

    @staticmethod
    def _is_chargesheet(filename: str) -> bool:
        """Detect if a file is a chargesheet by its filename."""
        name = filename.lower()
        return "chargesheet" in name or "charge_sheet" in name or "charge sheet" in name

    def _index_ir(self, file_path: str, filename: str, doc_id: str,
                  model: str, use_llm_parser: bool, case_name: str = None) -> Dict[str, Any]:
        # Route chargesheets to dedicated parser
        if self._is_chargesheet(filename):
            return self._index_chargesheet(file_path, filename, doc_id, model, case_name)

        if use_llm_parser:
            return self._index_ir_llm(file_path, filename, doc_id, model, case_name)
        else:
            return self._index_ir_python(file_path, filename, doc_id, case_name)

    def _index_ir_python(self, file_path: str, filename: str, doc_id: str,
                         case_name: str = None) -> Dict[str, Any]:
        """IR indexing with pure Python parser + statement extraction."""
        fields, accused_name, statement_text = parse_ir_document(file_path, filename)

        if not fields and not statement_text:
            return {"ok": False, "error": f"No fields or text extracted from '{filename}'"}

        # Store table fields in MySQL
        if fields:
            field_values = [{"field_name": f["field_key"], "value": f["field_value"], "serial_no": f["serial_no"]} for f in fields]
            store_ir_report(doc_id, filename, field_values, case_name=case_name)

        # Store statement in MySQL
        if statement_text:
            store_ir_statement(doc_id, filename, statement_text, case_name=case_name)

        # Build ChromaDB units: table fields + statement chunks
        units = []
        unit_metas = []

        # Table fields as chunks
        for f in fields:
            text = f"{f['field_key']}: {f['field_value']}" if f["field_value"] else f["field_key"]
            if len(text.strip()) >= 10:
                units.append(text)
                unit_metas.append({
                    "doc_id": doc_id, "doc_name": filename, "doc_type": "IR",
                    "case_name": case_name or "", "chunk_type": "field",
                    "field_name": f["field_key"], "serial_no": f["serial_no"],
                })

        # Statement chunks
        if statement_text:
            stmt_chunks = chunk_text(statement_text, chunk_size=2000, overlap=120)
            for i, chunk in enumerate(stmt_chunks):
                if len(chunk.strip()) >= 20:
                    units.append(chunk)
                    unit_metas.append({
                        "doc_id": doc_id, "doc_name": filename, "doc_type": "IR",
                        "case_name": case_name or "", "chunk_type": "statement",
                        "chunk_index": i,
                    })

        if units:
            print(f"[StructuredRAG:IR] Embedding {len(units)} units ({len(fields)} fields + {len(units) - len(fields)} statement chunks)...")
            embeddings = ollama_embed_batch(units)
            ids, valid_units, valid_metas, valid_embeddings = _filter_valid_embeddings(units, unit_metas, embeddings, doc_id)
            if valid_units:
                try:
                    self._col.add(ids=ids, embeddings=valid_embeddings, documents=valid_units, metadatas=valid_metas)
                except Exception as e:
                    print(f"[StructuredRAG:IR] ChromaDB add failed: {e}")
            self._rebuild_bm25()

        stmt_chars = len(statement_text) if statement_text else 0
        print(f"[StructuredRAG:IR:Python] Indexed '{filename}': {len(fields)} fields, "
              f"{stmt_chars} chars statement, case='{case_name}', accused='{accused_name}'")
        return {
            "ok": True, "doc_id": doc_id, "doc_name": filename,
            "chunks": len(units), "fields": len(fields),
            "details": {
                "type": "IR", "parser": "python", "accused_name": accused_name,
                "fields": len(fields), "statement_chars": stmt_chars,
                "case_name": case_name or "(none)",
            },
        }

    def _index_ir_llm(self, file_path: str, filename: str, doc_id: str,
                      model: str, case_name: str = None) -> Dict[str, Any]:
        """IR indexing with LLM parser."""
        try:
            from shared.llm_kv_extractor import extract_kv_from_docx
        except ImportError as e:
            return {"ok": False, "error": f"LLM parser not available: {e}"}

        ext = os.path.splitext(filename)[1].lower()
        if ext not in (".docx", ".doc"):
            return {"ok": False, "error": f"LLM parser only supports DOCX files, got '{ext}'"}

        units, metas, paragraph_text = extract_kv_from_docx(file_path)
        if not units and not paragraph_text:
            return {"ok": False, "error": f"No fields extracted from '{filename}' (LLM parser)"}

        # Store fields in MySQL
        field_values = []
        for u, m in zip(units, metas):
            fn = m.get("field_name", "")
            val = u.split(": ", 1)[1] if ": " in u else u
            sno = m.get("serial_no", "")
            field_values.append({"field_name": fn, "value": val, "serial_no": sno})
        if field_values:
            store_ir_report(doc_id, filename, field_values, case_name=case_name)

        # Store statement
        if paragraph_text:
            store_ir_statement(doc_id, filename, paragraph_text, case_name=case_name)

        # ChromaDB: fields + statement chunks
        all_units = []
        all_metas_chroma = []

        for u in units:
            if len(u.strip()) >= 10:
                all_units.append(u)
                all_metas_chroma.append({
                    "doc_id": doc_id, "doc_name": filename, "doc_type": "IR",
                    "case_name": case_name or "", "chunk_type": "field",
                })

        if paragraph_text:
            stmt_chunks = chunk_text(paragraph_text, chunk_size=2000, overlap=120)
            for i, chunk in enumerate(stmt_chunks):
                if len(chunk.strip()) >= 20:
                    all_units.append(chunk)
                    all_metas_chroma.append({
                        "doc_id": doc_id, "doc_name": filename, "doc_type": "IR",
                        "case_name": case_name or "", "chunk_type": "statement",
                        "chunk_index": i,
                    })

        if all_units:
            embeddings = ollama_embed_batch(all_units)
            ids, valid_units, valid_metas, valid_embeddings = _filter_valid_embeddings(all_units, all_metas_chroma, embeddings, doc_id)
            if valid_units:
                try:
                    self._col.add(ids=ids, embeddings=valid_embeddings, documents=valid_units, metadatas=valid_metas)
                except Exception as e:
                    print(f"[StructuredRAG:IR:LLM] ChromaDB add failed: {e}")
            self._rebuild_bm25()

        accused_name = ""
        for fv in field_values:
            fn = fv.get("field_name", "").lower()
            if "name" in fn and ("accused" in fn or fn == "name") and fv.get("value"):
                accused_name = fv["value"]
                break

        print(f"[StructuredRAG:IR:LLM] Indexed '{filename}': {len(field_values)} fields, case='{case_name}'")
        return {
            "ok": True, "doc_id": doc_id, "doc_name": filename,
            "chunks": len(all_units), "fields": len(field_values),
            "details": {"type": "IR", "parser": "llm", "accused_name": accused_name,
                        "case_name": case_name or "(none)"},
        }

    def _index_chargesheet(self, file_path: str, filename: str, doc_id: str,
                           model: str, case_name: str = None) -> Dict[str, Any]:
        """Index a chargesheet document (scanned PDF or DOCX)."""
        parsed = parse_chargesheet(file_path, filename)

        if parsed.get("error"):
            return {"ok": False, "error": parsed["error"]}

        # 1. Store chargesheet summary in MySQL
        store_chargesheet(
            doc_id=doc_id, doc_name=filename, case_name=case_name or "",
            accused_details=parsed.get("accused_details_text"),
            absconder_details=parsed.get("absconder_details_text"),
            suspect_details=parsed.get("suspect_details_text"),
            brief_description=parsed.get("brief_description"),
        )

        # 2. Store individual persons
        all_persons = parsed.get("accused_persons", []) + parsed.get("pending_persons", [])
        if all_persons:
            store_chargesheet_persons(doc_id, case_name or "", all_persons)

        # 3. Store header fields
        header_fields = parsed.get("header_fields", [])
        if header_fields:
            store_chargesheet_fields(doc_id, case_name or "", header_fields)

        # 4. Also store in ir_reports so existing IR queries can find the chargesheet
        #    (header fields as EAV rows with collection='CHARGESHEET')
        if header_fields:
            field_values = [{"field_name": f["field_name"], "value": f["value"],
                             "serial_no": f["serial_no"]} for f in header_fields]
            store_ir_report(doc_id, filename, field_values, case_name=case_name)

        # 5. Store brief description as statement for text search
        brief = parsed.get("brief_description", "")
        if brief:
            store_ir_statement(doc_id, filename, brief, case_name=case_name)

        # 6. Build ChromaDB chunks for vector + BM25 search
        units = []
        unit_metas = []

        # Accused details as chunks
        accused_text = parsed.get("accused_details_text", "")
        if accused_text:
            accused_chunks = chunk_text(accused_text, chunk_size=2000, overlap=120)
            for i, ch in enumerate(accused_chunks):
                if len(ch.strip()) >= 20:
                    units.append(ch)
                    unit_metas.append({
                        "doc_id": doc_id, "doc_name": filename, "doc_type": "IR",
                        "case_name": case_name or "", "chunk_type": "chargesheet_accused",
                        "chunk_index": i,
                    })

        # Brief description as chunks
        if brief:
            brief_chunks = chunk_text(brief, chunk_size=2000, overlap=120)
            for i, ch in enumerate(brief_chunks):
                if len(ch.strip()) >= 20:
                    units.append(ch)
                    unit_metas.append({
                        "doc_id": doc_id, "doc_name": filename, "doc_type": "IR",
                        "case_name": case_name or "", "chunk_type": "chargesheet_brief",
                        "chunk_index": i,
                    })

        # Header fields as individual chunks
        for f in header_fields:
            text = f"{f['field_name']}: {f['value']}"
            if len(text.strip()) >= 10:
                units.append(text)
                unit_metas.append({
                    "doc_id": doc_id, "doc_name": filename, "doc_type": "IR",
                    "case_name": case_name or "", "chunk_type": "chargesheet_field",
                    "field_name": f["field_name"],
                })

        # Full text chunks (OCR output) for general search
        full_text = parsed.get("full_text", "")
        if full_text and len(full_text) > len(accused_text) + len(brief):
            # Only add chunks that aren't already covered by accused/brief
            remaining = full_text
            remaining_chunks = chunk_text(remaining, chunk_size=2000, overlap=120)
            for i, ch in enumerate(remaining_chunks):
                if len(ch.strip()) >= 20:
                    units.append(ch)
                    unit_metas.append({
                        "doc_id": doc_id, "doc_name": filename, "doc_type": "IR",
                        "case_name": case_name or "", "chunk_type": "chargesheet_content",
                        "chunk_index": i,
                    })

        # Embed and store in ChromaDB
        if units:
            print(f"[StructuredRAG:Chargesheet] Embedding {len(units)} chunks...")
            embeddings = ollama_embed_batch(units)
            ids, valid_units, valid_metas, valid_embeddings = _filter_valid_embeddings(
                units, unit_metas, embeddings, doc_id)
            if valid_units:
                try:
                    self._col.add(ids=ids, embeddings=valid_embeddings,
                                  documents=valid_units, metadatas=valid_metas)
                except Exception as e:
                    print(f"[StructuredRAG:Chargesheet] ChromaDB add failed: {e}")
            self._rebuild_bm25()

        print(f"[StructuredRAG:Chargesheet] Indexed '{filename}': "
              f"{len(header_fields)} header fields, {len(all_persons)} persons, "
              f"{len(brief)} chars brief desc, {len(units)} chunks, case='{case_name}'")

        return {
            "ok": True, "doc_id": doc_id, "doc_name": filename,
            "chunks": len(units), "fields": len(header_fields),
            "details": {
                "type": "IR", "subtype": "chargesheet",
                "header_fields": len(header_fields),
                "accused_count": len(parsed.get("accused_persons", [])),
                "pending_count": len(parsed.get("pending_persons", [])),
                "brief_desc_chars": len(brief),
                "case_name": case_name or "(none)",
            },
        }

    def _index_smac(self, file_path: str, filename: str, doc_id: str,
                    model: str, case_name: str = None) -> Dict[str, Any]:
        full_text, table_rows = extract_text(file_path, filename)
        if not full_text.strip():
            return {"ok": False, "error": "No text extracted"}

        chunks = chunk_text(full_text, chunk_size=2000, overlap=120)
        chunks = [c for c in chunks if len(c) >= 20]

        if chunks:
            embeddings = ollama_embed_batch(chunks)
            metadatas = [{"doc_id": doc_id, "doc_name": filename, "doc_type": "SMAC",
                          "case_name": case_name or "", "chunk_index": i} for i in range(len(chunks))]
            ids, valid_chunks, valid_metas, valid_embeddings = _filter_valid_embeddings(chunks, metadatas, embeddings, doc_id)
            if valid_chunks:
                try:
                    self._col.add(ids=ids, embeddings=valid_embeddings, documents=valid_chunks, metadatas=valid_metas)
                except Exception as e:
                    print(f"[StructuredRAG:SMAC] ChromaDB add failed: {e}")
            self._rebuild_bm25()

        field_values = []
        for row in table_rows:
            cells = row.get("cells", [])
            if len(cells) >= 3:
                sno = cells[0].strip()
                fn = cells[1].strip()
                val = cells[2].strip()
                if sno and fn and val and re.match(r"^\d+$", sno):
                    field_values.append({"serial_no": sno, "field_name": fn, "value": val})

        if field_values:
            store_smac_report(doc_id, filename, field_values)

        print(f"[StructuredRAG:SMAC] Indexed '{filename}': {len(chunks)} chunks, {len(field_values)} fields")
        return {
            "ok": True, "doc_id": doc_id, "doc_name": filename,
            "chunks": len(chunks), "fields": len(field_values),
            "details": {"type": "SMAC", "chunks": len(chunks), "fields": len(field_values)},
        }

    # ── Query ────────────────────────────────────────────────────────

    def query(self, question: str, model: str, doc_id: str = None,
              case_name: str = None) -> Dict[str, Any]:
        # If case_name specified, scope to that case
        if case_name:
            return self._query_case(question, model, case_name)

        if doc_id and self._doc_types.get(doc_id) == "IR":
            return self._query_ir(question, model, doc_id)

        ir_docs = self._try_find_ir_doc(question, model)
        if ir_docs:
            return self._query_ir_by_docs(question, model, ir_docs)

        return self._query_hybrid(question, model, doc_id)

    def _query_case(self, question: str, model: str, case_name: str) -> Dict[str, Any]:
        """Answer a question scoped to a specific case — searches all docs in that case."""
        case_docs = find_ir_docs_by_case(case_name)
        if not case_docs:
            return {"answer": f"No documents found for case '{case_name}'.", "used_chunks": [], "search_method": "case_scope"}

        # Search ChromaDB with case_name filter
        query_embedding = ollama_embed_batch([question])[0]
        results = self._col.query(
            query_embeddings=[query_embedding],
            n_results=10,
            where={"case_name": case_name},
        )
        v_docs = results.get("documents", [[]])[0]
        v_metas = results.get("metadatas", [[]])[0]

        if not v_docs:
            return {"answer": f"No relevant content found in case '{case_name}'.", "used_chunks": [], "search_method": "case_scope"}

        # Build context from both field and statement chunks
        context_parts = []
        used_chunks = []
        for doc_text, meta in zip(v_docs, v_metas):
            chunk_type = meta.get("chunk_type", "unknown")
            label = f"[{meta.get('doc_name', '?')} | {chunk_type}]"
            context_parts.append(f"{label}\n{doc_text}")
            used_chunks.append({"doc_name": meta.get("doc_name"), "chunk_type": chunk_type, "text": doc_text[:200]})

        context = "\n\n---\n\n".join(context_parts)

        prompt = (
            f"You are answering questions about case: '{case_name}'.\n"
            "Answer ONLY from the CONTEXT below. Do NOT use your training knowledge.\n"
            "The context includes both structured table fields and narrative statement text.\n"
            "If the answer is not in the CONTEXT, say 'Not found in the case documents.'\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"QUESTION: {question}\n\nAnswer:"
        )

        answer = ollama_chat([{"role": "user", "content": prompt}], temperature=0.0, model=model)
        return {
            "answer": answer, "used_chunks": used_chunks,
            "search_method": f"case_scope ({case_name}, {len(case_docs)} docs)",
            "details": {"case_name": case_name, "docs_in_case": len(case_docs), "chunks_found": len(v_docs)},
        }

    def _try_find_ir_doc(self, question: str, model: str) -> List[Dict]:
        try:
            name_prompt = (
                "Extract the person's name from this question. Return ONLY the name, nothing else.\n"
                "If no person name is mentioned, return 'NONE'.\n\n"
                f"Question: {question}\n\nName:"
            )
            name = ollama_chat([{"role": "user", "content": name_prompt}], temperature=0.0, model=model).strip()
            if name.upper() == "NONE" or len(name) < 2:
                return []
            words = [w for w in name.split() if len(w) > 1]
            if not words:
                return []
            return find_ir_docs_by_name(words)
        except Exception:
            return []

    def _query_ir(self, question: str, model: str, doc_id: str) -> Dict[str, Any]:
        """Answer from a specific IR document — searches both fields AND statement."""
        fields = get_ir_fields(doc_id)
        statement = get_ir_statement(doc_id)

        if not fields and not statement:
            return {"answer": "No data found for this document.", "used_chunks": [], "search_method": "ir_combined"}

        # Build combined context
        context_parts = []

        if fields:
            field_text = "\n".join([f"[{f['serial_no']}] {f['field_key']}: {f['field_value']}" for f in fields if f.get('field_value')])
            context_parts.append(f"=== TABLE FIELDS ===\n{field_text}")

        if statement:
            # Truncate statement if very long — use first 8000 chars for context
            stmt_preview = statement[:8000]
            if len(statement) > 8000:
                stmt_preview += "\n... [statement truncated]"
            context_parts.append(f"=== STATEMENT / NARRATIVE ===\n{stmt_preview}")

        context = "\n\n".join(context_parts)

        prompt = (
            "Answer the question from the TABLE FIELDS and STATEMENT below.\n"
            "Return the COMPLETE value exactly as stored. Do NOT summarize or truncate.\n"
            "Search both the table fields AND the narrative statement for the answer.\n"
            "If the information is not found, say 'This information is not available.'\n\n"
            f"{context}\n\n"
            f"QUESTION: {question}\n\nAnswer:"
        )

        answer = ollama_chat([{"role": "user", "content": prompt}], temperature=0.0, model=model)
        return {
            "answer": answer,
            "used_chunks": [{"doc_name": "IR fields + statement", "text": f"{len(fields)} fields, {len(statement or '')} chars statement"}],
            "search_method": "ir_combined (fields + statement)",
            "details": {"fields_count": len(fields), "statement_chars": len(statement or "")},
        }

    def _query_ir_by_docs(self, question: str, model: str, ir_docs: List[Dict]) -> Dict[str, Any]:
        if len(ir_docs) == 1:
            return self._query_ir(question, model, ir_docs[0]["doc_id"])
        doc_list = "\n".join([f"- {d['doc_name']}" + (f" (Case: {d.get('case_name', '')})" if d.get('case_name') else "") for d in ir_docs])
        return {
            "answer": f"Found {len(ir_docs)} matching IR documents:\n\n{doc_list}\n\nPlease specify which document you're asking about.",
            "used_chunks": [], "search_method": "ir_name_search",
        }

    def _query_hybrid(self, question: str, model: str, doc_id: str = None) -> Dict[str, Any]:
        if self._col.count() == 0:
            return {"answer": "No documents indexed.", "used_chunks": [], "search_method": "none"}

        query_embedding = ollama_embed_batch([question])[0]
        where_filter = {"doc_id": doc_id} if doc_id else None
        v_results = self._col.query(query_embeddings=[query_embedding], n_results=20, where=where_filter)
        v_docs = v_results.get("documents", [[]])[0]
        v_metas = v_results.get("metadatas", [[]])[0]
        vector_results = list(zip(v_docs, v_metas))

        bm25_results = []
        if self._bm25_index:
            tokens = _tokenize(question)
            if tokens:
                scores = self._bm25_index.get_scores(tokens)
                ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
                for idx in ranked[:20]:
                    if scores[idx] <= 0:
                        break
                    meta = self._bm25_metas[idx]
                    if doc_id and meta.get("doc_id") != doc_id:
                        continue
                    bm25_results.append((self._bm25_docs[idx], meta))

        scores_map = {}
        items = {}
        k = 60
        for rank, (text, meta) in enumerate(vector_results):
            key = f"{meta.get('doc_id', '')}_{meta.get('chunk_index', meta.get('serial_no', ''))}_{text[:80]}"
            scores_map[key] = scores_map.get(key, 0) + 1.0 / (k + rank + 1)
            items[key] = (text, meta)
        for rank, (text, meta) in enumerate(bm25_results):
            key = f"{meta.get('doc_id', '')}_{meta.get('chunk_index', meta.get('serial_no', ''))}_{text[:80]}"
            scores_map[key] = scores_map.get(key, 0) + 1.0 / (k + rank + 1)
            items[key] = (text, meta)

        ranked_keys = sorted(scores_map.keys(), key=lambda x: scores_map[x], reverse=True)
        merged = [items[x] for x in ranked_keys[:5]]

        if not merged:
            return {"answer": "No relevant chunks found.", "used_chunks": [], "search_method": "hybrid"}

        context_parts = []
        used_chunks = []
        for doc_text, meta in merged:
            chunk_type = meta.get("chunk_type", "chunk")
            context_parts.append(f"[{meta.get('doc_name', '?')} | {chunk_type}]\n{doc_text}")
            used_chunks.append({"doc_name": meta.get("doc_name"), "chunk_type": chunk_type, "text": doc_text[:200]})

        context = "\n\n---\n\n".join(context_parts)

        prompt = (
            "Answer the question ONLY from the CONTEXT below.\n"
            "If the answer is not in the CONTEXT, say 'Not found in the documents.'\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"QUESTION: {question}\n\nAnswer:"
        )

        answer = ollama_chat([{"role": "user", "content": prompt}], temperature=0.0, model=model)
        return {
            "answer": answer, "used_chunks": used_chunks,
            "search_method": "hybrid (vector + BM25 + RRF)",
            "details": {"vector": len(vector_results), "bm25": len(bm25_results), "merged": len(merged)},
        }

    # ── List, Cases, Clear ───────────────────────────────────────────

    def list_docs(self) -> List[Dict[str, Any]]:
        if self._col.count() == 0:
            return []
        all_metas = []
        offset = 0
        while True:
            batch = self._col.get(include=["metadatas"], limit=500, offset=offset)
            metas = batch.get("metadatas", [])
            if not metas:
                break
            all_metas.extend(metas)
            if len(metas) < 500:
                break
            offset += 500
        doc_map = {}
        for m in all_metas:
            did = m.get("doc_id", "")
            if did not in doc_map:
                doc_map[did] = {
                    "doc_id": did, "doc_name": m.get("doc_name", ""),
                    "chunks": 0, "type": m.get("doc_type", ""),
                    "case_name": m.get("case_name", ""),
                }
            doc_map[did]["chunks"] += 1
        return list(doc_map.values())

    def list_cases(self) -> List[str]:
        return get_all_case_names()

    def clear(self) -> Dict[str, Any]:
        count = self._col.count()
        self._client.delete_collection("structured_rag")
        self._col = self._client.get_or_create_collection(name="structured_rag")
        self._bm25_docs, self._bm25_metas, self._bm25_index = [], [], None
        self._doc_types.clear()
        clear_all()
        return {"ok": True, "cleared": count}
