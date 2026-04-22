"""
RAG Playground — Test different RAG pipeline approaches.
FastAPI backend with pluggable pipeline architecture.
"""

import os
import tempfile
import time

from typing import Optional
from pydantic import BaseModel

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import OLLAMA_BASE_URL, DEFAULT_MODEL
from shared.ollama_client import list_models
from pipelines.basic_rag import BasicRAGPipeline
from pipelines.hybrid_rag import HybridRAGPipeline
from pipelines.structured_rag import StructuredRAGPipeline
from pipelines.agentic_rag import AgenticRAGPipeline

app = FastAPI(title="RAG Playground", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pipeline Registry ────────────────────────────────────────────────────

PIPELINES = {
    "BasicRAG": BasicRAGPipeline(),
    "HybridRAG": HybridRAGPipeline(),
    "StructuredRAG": StructuredRAGPipeline(),
    "AgenticRAG": AgenticRAGPipeline(),
}


def _get_pipeline(name: str):
    if name not in PIPELINES:
        raise HTTPException(400, f"Unknown pipeline: {name}. Available: {list(PIPELINES.keys())}")
    return PIPELINES[name]


# ── Health & Models ──────────────────────────────────────────────────────

@app.get("/health")
def health():
    ollama_ok = False
    try:
        import requests
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        ollama_ok = r.status_code == 200
    except Exception:
        pass
    return {
        "ok": True,
        "service": "RAG Playground",
        "ollama_connected": ollama_ok,
        "pipelines": list(PIPELINES.keys()),
    }


@app.get("/api/models")
def get_models():
    return {"ok": True, "models": list_models(), "default": DEFAULT_MODEL}


@app.get("/api/pipelines")
def get_pipelines():
    return {
        "ok": True,
        "pipelines": [
            {"name": p.name, "description": p.description}
            for p in PIPELINES.values()
        ],
    }


# ── Upload & Index ───────────────────────────────────────────────────────

@app.post("/api/index")
async def index_document(
    file: UploadFile = File(...),
    pipeline: str = Form("BasicRAG"),
    model: str = Form(""),
    doc_type: str = Form("SMAC"),
    use_llm_parser: bool = Form(False),
    relative_path: str = Form(""),
):
    """Upload and index a document using the selected pipeline."""
    p = _get_pipeline(pipeline)
    model = model or DEFAULT_MODEL

    if not file.filename:
        raise HTTPException(400, "No file provided")

    supported = (".pdf", ".docx", ".doc", ".xlsx", ".csv")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in supported:
        raise HTTPException(400, f"Unsupported format: {ext}. Supported: {supported}")

    # Extract case name from relative path
    # Structure: "RootFolder/CaseName/file.docx" or "RootFolder/CaseName/SubFolder/file.docx"
    # parts[0] = root folder (selected folder), parts[1] = case name
    case_name_override = None
    if relative_path:
        parts = relative_path.replace("\\", "/").split("/")
        if len(parts) >= 3:
            # Has root + case + file (or deeper) — case is parts[1]
            case_name_override = parts[1]
        elif len(parts) == 2:
            # File directly in selected folder — use folder name as case
            case_name_override = parts[0]
    print(f"[Index] File: {file.filename}, relative_path: {relative_path}, case_name: {case_name_override}")

    # Save to temp file
    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        start = time.time()
        if pipeline == "StructuredRAG":
            result = p.index(tmp_path, file.filename, model, doc_type=doc_type,
                             use_llm_parser=use_llm_parser, case_name_override=case_name_override)
        else:
            result = p.index(tmp_path, file.filename, model)
        result["elapsed_seconds"] = round(time.time() - start, 2)
        result["pipeline"] = pipeline
        return result
    finally:
        os.unlink(tmp_path)


# ── Query ────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    pipeline: str = "BasicRAG"
    model: str = ""
    doc_id: Optional[str] = None
    case_name: Optional[str] = None


@app.post("/api/query")
def query_documents(body: QueryRequest):
    """Ask a question using the selected pipeline."""
    p = _get_pipeline(body.pipeline)
    model = body.model or DEFAULT_MODEL

    start = time.time()
    if body.case_name and body.pipeline in ("StructuredRAG", "AgenticRAG"):
        result = p.query(body.question, model, body.doc_id, case_name=body.case_name)
    else:
        result = p.query(body.question, model, body.doc_id)
    result["elapsed_seconds"] = round(time.time() - start, 2)
    result["pipeline"] = body.pipeline
    result["model"] = model
    return result


# ── Document List ────────────────────────────────────────────────────────

@app.get("/api/docs")
def list_documents(pipeline: str = "BasicRAG"):
    p = _get_pipeline(pipeline)
    return {"ok": True, "docs": p.list_docs(), "pipeline": pipeline}


# ── Cases ────────────────────────────────────────────────────────────────

@app.get("/api/cases")
def list_cases():
    """List all indexed case names (StructuredRAG only)."""
    p = PIPELINES.get("StructuredRAG")
    if p and hasattr(p, 'list_cases'):
        return {"ok": True, "cases": p.list_cases()}
    return {"ok": True, "cases": []}


# ── Clear ────────────────────────────────────────────────────────────────

@app.post("/api/clear")
def clear_documents(pipeline: str = "BasicRAG"):
    p = _get_pipeline(pipeline)
    return p.clear()


# ═══════════════════════════════════════════════════════════════════════════
#  Scan Test — Decoupled chargesheet parse/index/query for testing
# ═══════════════════════════════════════════════════════════════════════════

import uuid
import chromadb
from config import CHROMA_PATH
from shared.chargesheet_parser import parse_chargesheet
from shared.chunking import chunk_text
from shared.ollama_client import ollama_embed_batch, ollama_chat
from shared.structured_tables import (
    scantest_store_chargesheet, scantest_store_persons, scantest_store_fields,
    scantest_get_chargesheet, scantest_get_persons, scantest_get_fields,
    scantest_list_docs, scantest_clear,
)

# Scantest ChromaDB — separate collection
_scantest_chroma = chromadb.PersistentClient(path=os.path.join(CHROMA_PATH, "scantest"))
_scantest_col = _scantest_chroma.get_or_create_collection(name="scantest_structured_rag")


@app.post("/api/scantest/parse-preview")
async def scantest_parse_preview(file: UploadFile = File(...)):
    """Parse a chargesheet and return extracted sections — no indexing, just preview."""
    if not file.filename:
        raise HTTPException(400, "No file provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".pdf", ".docx", ".doc"):
        raise HTTPException(400, f"Unsupported format: {ext}. Use PDF or DOCX.")

    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        start = time.time()
        parsed = parse_chargesheet(tmp_path, file.filename)
        elapsed = round(time.time() - start, 2)

        if parsed.get("error"):
            return {"ok": False, "error": parsed["error"]}

        # Return parsed sections (text previews, not full content for large docs)
        full_text = parsed.get("full_text", "")
        return {
            "ok": True,
            "filename": file.filename,
            "elapsed_seconds": elapsed,
            "full_text_chars": len(full_text),
            "full_text_preview": full_text[:3000],
            "header_fields": parsed.get("header_fields", []),
            "accused_persons": parsed.get("accused_persons", []),
            "accused_details_text": (parsed.get("accused_details_text") or "")[:2000],
            "pending_persons": parsed.get("pending_persons", []),
            "absconder_details_text": (parsed.get("absconder_details_text") or "")[:1000],
            "suspect_details_text": (parsed.get("suspect_details_text") or "")[:1000],
            "brief_description_preview": (parsed.get("brief_description") or "")[:2000],
            "brief_description_chars": len(parsed.get("brief_description") or ""),
            "summary": {
                "header_fields": len(parsed.get("header_fields", [])),
                "accused_count": len(parsed.get("accused_persons", [])),
                "pending_count": len(parsed.get("pending_persons", [])),
                "brief_desc_chars": len(parsed.get("brief_description") or ""),
                "full_text_chars": len(full_text),
            },
        }
    finally:
        os.unlink(tmp_path)


@app.post("/api/scantest/index")
async def scantest_index(file: UploadFile = File(...)):
    """Index a scanned chargesheet into scantest tables + ChromaDB."""
    if not file.filename:
        raise HTTPException(400, "No file provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".pdf", ".docx", ".doc"):
        raise HTTPException(400, f"Unsupported format: {ext}. Use PDF or DOCX.")

    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        start = time.time()
        doc_id = str(uuid.uuid4())
        parsed = parse_chargesheet(tmp_path, file.filename)

        if parsed.get("error"):
            return {"ok": False, "error": parsed["error"]}

        full_text = parsed.get("full_text", "")

        # Store in scantest MySQL tables
        scantest_store_chargesheet(
            doc_id=doc_id, doc_name=file.filename,
            accused_details=parsed.get("accused_details_text"),
            absconder_details=parsed.get("absconder_details_text"),
            suspect_details=parsed.get("suspect_details_text"),
            brief_description=parsed.get("brief_description"),
            full_text_chars=len(full_text),
        )

        all_persons = parsed.get("accused_persons", []) + parsed.get("pending_persons", [])
        if all_persons:
            scantest_store_persons(doc_id, None, all_persons)

        if parsed.get("header_fields"):
            scantest_store_fields(doc_id, None, parsed["header_fields"])

        # Store chunks in scantest ChromaDB
        chunks = chunk_text(full_text, chunk_size=2000, overlap=120)
        chunks = [c for c in chunks if len(c.strip()) >= 20]
        chunk_count = 0

        if chunks:
            embeddings = ollama_embed_batch(chunks)
            # Filter valid embeddings
            expected_dim = None
            for emb in embeddings:
                if len(emb) > 1:
                    expected_dim = len(emb)
                    break
            if expected_dim:
                valid_ids, valid_chunks, valid_embeddings, valid_metas = [], [], [], []
                for i, (ch, emb) in enumerate(zip(chunks, embeddings)):
                    if len(emb) == expected_dim:
                        valid_ids.append(f"{doc_id}_{i}")
                        valid_chunks.append(ch)
                        valid_embeddings.append(emb)
                        valid_metas.append({"doc_id": doc_id, "doc_name": file.filename, "chunk_index": i})
                if valid_chunks:
                    _scantest_col.add(ids=valid_ids, embeddings=valid_embeddings,
                                      documents=valid_chunks, metadatas=valid_metas)
                    chunk_count = len(valid_chunks)

        elapsed = round(time.time() - start, 2)
        return {
            "ok": True, "doc_id": doc_id, "doc_name": file.filename,
            "chunks": chunk_count, "elapsed_seconds": elapsed,
            "summary": {
                "header_fields": len(parsed.get("header_fields", [])),
                "accused_count": len(parsed.get("accused_persons", [])),
                "pending_count": len(parsed.get("pending_persons", [])),
                "brief_desc_chars": len(parsed.get("brief_description") or ""),
                "full_text_chars": len(full_text),
            },
        }
    finally:
        os.unlink(tmp_path)


class ScanTestQuery(BaseModel):
    question: str
    doc_id: Optional[str] = None
    model: str = ""


@app.post("/api/scantest/query")
def scantest_query(body: ScanTestQuery):
    """Query scantest indexed documents."""
    model = body.model or DEFAULT_MODEL

    if _scantest_col.count() == 0:
        return {"ok": False, "error": "No scantest documents indexed."}

    start = time.time()

    # Vector search
    query_embedding = ollama_embed_batch([body.question])[0]
    where_filter = {"doc_id": body.doc_id} if body.doc_id else None
    results = _scantest_col.query(
        query_embeddings=[query_embedding], n_results=5, where=where_filter,
    )
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    if not docs:
        return {"ok": True, "answer": "No relevant content found.", "used_chunks": [],
                "elapsed_seconds": round(time.time() - start, 2)}

    context = "\n\n---\n\n".join(
        f"[{m.get('doc_name', '?')} | chunk {m.get('chunk_index', '?')}]\n{d}"
        for d, m in zip(docs, metas)
    )

    prompt = (
        "Answer the question ONLY from the CONTEXT below.\n"
        "If the answer is not in the CONTEXT, say 'Not found in the documents.'\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION: {body.question}\n\nAnswer:"
    )

    answer = ollama_chat([{"role": "user", "content": prompt}], temperature=0.0, model=model)
    elapsed = round(time.time() - start, 2)

    used_chunks = [{"doc_name": m.get("doc_name"), "chunk_index": m.get("chunk_index"),
                     "text": d[:200]} for d, m in zip(docs, metas)]

    return {"ok": True, "answer": answer, "used_chunks": used_chunks,
            "elapsed_seconds": elapsed, "search_method": "scantest_vector"}


@app.get("/api/scantest/docs")
def scantest_docs():
    """List scantest indexed documents."""
    docs = scantest_list_docs()
    chroma_count = _scantest_col.count()
    return {"ok": True, "docs": docs, "chroma_chunks": chroma_count}


@app.post("/api/scantest/clear")
def scantest_clear_all():
    """Clear all scantest data."""
    global _scantest_col
    scantest_clear()
    _scantest_chroma.delete_collection("scantest_structured_rag")
    _scantest_col = _scantest_chroma.get_or_create_collection(name="scantest_structured_rag")
    return {"ok": True, "message": "Scantest data cleared"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("rag_playground:app", host="0.0.0.0", port=8006, reload=True)
