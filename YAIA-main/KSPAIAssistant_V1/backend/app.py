import os
import json
import tempfile

from typing import Optional, Dict, Any, List, Literal, Tuple
from pydantic import BaseModel

from fastapi import FastAPI, UploadFile, File, HTTPException
from graph_api import router as graph_router

from pydantic import BaseModel

from ollama_client import ollama_chat
from db import fetch_schema, validate_safe_select, run_sql, clean_sql

from graph_qa import graph_ask

# ✅ CHANGED: import the correct functions from rag.py
# - index_document supports PDF/DOCX/XLSX/CSV
# - ask_pdf supports doc_id=None (search across all docs) or doc_id=<id>
# - clear_all_documents safely deletes all indexed docs and embeddings
from rag import index_document, ask_pdf, clear_all_documents


# ------------------------------------------------------------------------------
# App
# ------------------------------------------------------------------------------
app = FastAPI(title="KSP AI Assistant")

app.include_router(graph_router)


# ------------------------------------------------------------------------------
# Models
# ------------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class DBQuestion(BaseModel):
    question: str
    history: Optional[List[ChatMessage]] = None


class DocQuestion(BaseModel):
    question: str
    history: Optional[List[ChatMessage]] = None
    doc_id: Optional[str] = None  # None => search across ALL indexed docs

class GraphQuestion(BaseModel):
    question: str
    history: Optional[List[ChatMessage]] = None
    param_overrides: Optional[Dict[str, Any]] = None

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def build_context_from_history(history: Optional[List[ChatMessage]], keep_last: int = 8) -> str:
    """
    Convert last N messages into a compact context block for follow-ups like:
    "top 10", "only 2024", "same query but group by district", etc.
    """
    if not history:
        return ""
    last = history[-keep_last:]
    lines = []
    for m in last:
        lines.append(f"{m.role.upper()}: {m.content}")
    return "\n".join(lines)


def llm_generate_sql(question: str, schema_text: str) -> Tuple[str, str]:
    """
    Returns (sql_clean, sql_raw).
    Prompts Ollama to return JSON only: {"sql":"SELECT ..."}
    Then extracts sql, cleans it (removes fences, prose, trailing junk, etc.)
    """
    response = ollama_chat(
        [
            {
                "role": "system",
                "content":
                    "You are a Microsoft SQL Server query generator.\n"
                    "You MUST output ONLY valid JSON. No markdown. No prose. No extra keys.\n"
                    "Return EXACTLY one JSON object with exactly one key:\n"
                    "{\"sql\":\"...\"}\n"
                    "\n"
                    "STRICT JSON RULES:\n"
                    "- Output must start with '{' and end with '}'.\n"
                    "- Do not output anything before or after the JSON.\n"
                    "- JSON must contain ONLY the key \"sql\".\n"
                    "\n"
                    "STRICT SQL RULES (value of sql):\n"
                    "- Exactly ONE statement\n"
                    "- SELECT only\n"
                    "- No semicolons\n"
                    "- No comments (-- or /* */)\n"
                    "- No USE\n"
                    "- Use only single quotes in SQL literals\n"
                    "- Do NOT use double quotes anywhere inside the SQL\n"
                    "- Use only tables/columns from the provided schema\n"
                    "- If returning rows, use TOP 50\n"
            },
            {
                "role": "user",
                "content":
                    f"SCHEMA:\n{schema_text}\n\n"
                    f"QUESTION:\n{question}\n\n"
                    "Return only the JSON object."
            },
        ],
        temperature=0.0,
    )

    # Extract sql_raw from JSON if possible
    try:
        obj = json.loads(response)
        sql_raw = obj.get("sql", "")
        if not isinstance(sql_raw, str):
            sql_raw = str(sql_raw)
    except Exception:
        sql_raw = response

    # Clean SQL (IMPORTANT)
    sql_cleaned = clean_sql(sql_raw)

    return sql_cleaned, sql_raw


# ------------------------------------------------------------------------------
# Health / Test Endpoints
# ------------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True, "service": "Local AI Assistant"}


@app.get("/db/test")
def db_test():
    """
    Simple DB connectivity check. Adjust query if needed.
    """
    try:
        data = run_sql("SELECT TOP 1 name AS DatabaseName FROM sys.databases ORDER BY name")
        return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ------------------------------------------------------------------------------
# DB Ask
# ------------------------------------------------------------------------------
@app.post("/db/ask")
def ask_db(payload: DBQuestion):
    try:
        schema_text = fetch_schema()

        # Include history context (optional)
        history_context = build_context_from_history(payload.history, keep_last=8)
        question = payload.question

        if history_context:
            question = (
                "You are continuing an ongoing conversation.\n"
                "Use the conversation context to resolve references like 'it', 'that', 'same', 'previous'.\n\n"
                f"CONVERSATION CONTEXT:\n{history_context}\n\n"
                f"CURRENT USER QUESTION:\n{payload.question}"
            )

        # Attempt 1
        sql_cleaned, sql_raw = llm_generate_sql(question, schema_text)
        ok, reason = validate_safe_select(sql_cleaned)

        # Retry once if unsafe/invalid
        if not ok:
            retry_question = (
                "Your previous output was invalid.\n"
                f"Validation error: {reason}\n"
                "Return ONLY JSON exactly like {\"sql\":\"SELECT ...\"}.\n"
                "No extra text. No semicolons. No comments. No USE.\n"
                "No double quotes inside SQL.\n\n"
                f"{question}"
            )
            sql_cleaned2, sql_raw2 = llm_generate_sql(retry_question, schema_text)
            ok2, reason2 = validate_safe_select(sql_cleaned2)

            if not ok2:
                return {
                    "ok": False,
                    "error": f"Unsafe SQL after retry: {reason2}",
                    "sql_raw": sql_raw,
                    "sql_clean": sql_cleaned,
                    "sql_raw_retry": sql_raw2,
                    "sql_clean_retry": sql_cleaned2,
                }

            sql_cleaned = sql_cleaned2

        # Execute SQL
        data = run_sql(sql_cleaned)

        # Summarize in natural language
        answer = ollama_chat(
            [
                {"role": "system", "content": "You are a helpful analyst. Summarize the SQL result clearly and briefly."},
                {"role": "user", "content": f"QUESTION: {payload.question}\nSQL: {sql_cleaned}\nRESULT: {data}"},
            ],
            temperature=0.0,
        )

        return {"ok": True, "sql": sql_cleaned, "data": data, "answer": answer}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------------------
# Docs Upload (Index)  ✅ UPDATED: PDF/DOCX/XLSX/CSV
# ------------------------------------------------------------------------------
@app.post("/docs/upload")
async def docs_upload(file: UploadFile = File(...)):
    """
    Upload + index a document (PDF/DOCX/XLSX/CSV).
    Always returns JSON so Streamlit never fails with JSON decode errors.
    """
    try:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in [".pdf", ".docx", ".xlsx", ".csv"]:
            return {"ok": False, "error": "Supported: PDF, DOCX, XLSX, CSV"}

        # Save temp with correct suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        # Index
        indexed = index_document(tmp_path, file.filename)

        # Cleanup temp file
        try:
            os.remove(tmp_path)
        except Exception:
            pass

        if indexed.get("ok") is False:
            return indexed

        return {"ok": True, **indexed}

    except Exception as e:
        return {"ok": False, "error": "Document indexing failed", "detail": str(e)}


# ------------------------------------------------------------------------------
# Docs Clear  ✅ UPDATED: calls clear_all_docs() (safe delete)
# ------------------------------------------------------------------------------
@app.post("/docs/clear")
def clear_docs():
    """
    Clear all indexed documents and embeddings (ChromaDB).
    """
    out = clear_all_documents()
    if out.get("ok"):
        return out
    raise HTTPException(status_code=500, detail=out.get("error", "Failed to clear docs"))


# ------------------------------------------------------------------------------
# Docs Ask (RAG Q&A)
# ------------------------------------------------------------------------------
@app.post("/docs/ask")
def docs_ask(payload: DocQuestion):
    """
    Ask questions about indexed documents.
    - If payload.doc_id is set => restrict to that doc
    - If payload.doc_id is None => search across ALL indexed docs
    """
    try:
        history_context = build_context_from_history(payload.history, keep_last=8)

        question = payload.question
        if history_context:
            question = (
                "You are continuing an ongoing conversation about the same document(s).\n"
                "Use the context to resolve references like 'it', 'that section', 'previous answer'.\n\n"
                f"CONVERSATION CONTEXT:\n{history_context}\n\n"
                f"CURRENT USER QUESTION:\n{payload.question}"
            )

        # result = ask_pdf(doc_id=payload.doc_id, question=question)
        result = ask_pdf(doc_id=payload.doc_id, question=question, top_k=15)

        return {"ok": True, **result}

    except Exception as e:
        return {"ok": False, "error": "Failed to answer from documents", "detail": str(e)}


# ------------------------------------------------------------------------------
# Graph Ask (Graph Q&A)
# ------------------------------------------------------------------------------
@app.post("/graph/ask")
def ask_graph(payload: GraphQuestion):
    try:
        history_context = build_context_from_history(payload.history, keep_last=8)
        q = payload.question

        if history_context:
            q = (
                "You are continuing an investigation conversation.\n"
                "Use context to resolve references like 'same crime', 'that account', etc.\n\n"
                f"CONVERSATION CONTEXT:\n{history_context}\n\n"
                f"CURRENT USER QUESTION:\n{payload.question}"
            )

        result = graph_ask(q, param_overrides=payload.param_overrides)
        return result

    except Exception as e:
        return {"ok": False, "error": "Graph Q&A failed", "detail": str(e)}

