import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import json
import tempfile

from typing import Optional, Dict, Any, List, Literal, Tuple
from pydantic import BaseModel

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from graph_api import router as graph_router

from pydantic import BaseModel

from ollama_client import ollama_chat
from db import fetch_schema, validate_safe_select, run_sql, clean_sql

from graph_qa import graph_ask

# ✅ CHANGED: import the correct functions from rag.py
# - index_document supports PDF/DOCX/XLSX/CSV
# - ask_pdf supports doc_id=None (search across all docs) or doc_id=<id>
# - clear_all_documents safely deletes all indexed docs and embeddings
from rag import index_document, ask_pdf, ask_docs_agent, clear_all_documents

from config import WHISPER_MODEL

# Lazy-loaded Whisper model (only loads when voice is first used)
_whisper_model = None

def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        import torch
        from faster_whisper import WhisperModel
        if torch.cuda.is_available():
            print(f"[Whisper] Using GPU: {torch.cuda.get_device_name(0)}")
            _whisper_model = WhisperModel(WHISPER_MODEL, device="cuda", compute_type="float16")
        else:
            print("[Whisper] No GPU detected, using CPU")
            _whisper_model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return _whisper_model


# ------------------------------------------------------------------------------
# App
# ------------------------------------------------------------------------------
app = FastAPI(title="KSP AI Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class DBReportQuestion(BaseModel):
    crime_no: str


class DocQuestion(BaseModel):
    question: str
    history: Optional[List[ChatMessage]] = None
    doc_id: Optional[str] = None  # None => search across ALL indexed docs

class DocAgentQuestion(BaseModel):
    question: str
    history: Optional[List[ChatMessage]] = None
    doc_ids: List[str]

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


def _escape_sql_literal(value: str) -> str:
    return (value or "").replace("'", "''")


def _rows_to_dicts(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Convert {"columns": [...], "rows": [[...]]} -> list of dicts.
    """
    if not isinstance(data, dict):
        return []
    cols = data.get("columns") or []
    rows = data.get("rows") or []
    out = []
    for r in rows:
        if isinstance(r, (list, tuple)):
            out.append({cols[i]: r[i] if i < len(r) else None for i in range(len(cols))})
    return out


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
# DB Report (Crime No dossier)
# ------------------------------------------------------------------------------
@app.post("/db/report")
def db_report(payload: DBReportQuestion):
    try:
        crime_no = (payload.crime_no or "").strip()
        if not crime_no:
            return {"ok": False, "error": "Crime No is required."}

        c = _escape_sql_literal(crime_no)

        victims_sql = (
            "SELECT Victim_ID, Victim_Name, VictimAccountNo, VictimBankDetail, "
            "VictimBankBranch, amountSent "
            "FROM Tbl_Fraud_VictimAccount "
            f"WHERE Crime_No = '{c}'"
        )
        accused_sql = (
            "SELECT AccusedAccountLevel, AccusedName, AccusedAccountNo, AccusedBankName, "
            "AccusedBankBranch, AccusedMobileNo, AccusedAddress, amountReceived, "
            "ParentAccountNo, ParentAccountType, FlowDate, FlowType "
            "FROM Tbl_Fraud_AccusedAccount "
            f"WHERE Crime_No = '{c}' AND ParentAccountType = 'c'"
        )
        accused_by_level_sql = (
            "SELECT AccusedAccountLevel, COUNT(*) AS accused_count, "
            "SUM(amountReceived) AS total_received "
            "FROM Tbl_Fraud_AccusedAccount "
            f"WHERE Crime_No = '{c}' AND ParentAccountType = 'c' "
            "GROUP BY AccusedAccountLevel "
            "ORDER BY AccusedAccountLevel"
        )
        totals_sql = (
            "SELECT "
            "(SELECT COUNT(*) FROM Tbl_Fraud_VictimAccount WHERE Crime_No = '{c}') AS victim_count, "
            "(SELECT SUM(amountSent) FROM Tbl_Fraud_VictimAccount WHERE Crime_No = '{c}') AS total_amount_sent, "
            "(SELECT COUNT(*) FROM Tbl_Fraud_AccusedAccount WHERE Crime_No = '{c}') AS accused_count, "
            "(SELECT SUM(amountReceived) FROM Tbl_Fraud_AccusedAccount WHERE Crime_No = '{c}') AS total_amount_received"
        ).format(c=c)
        cross_crime_sql = (
            "SELECT AccusedAccountNo, AccusedName, Crime_No "
            "FROM Tbl_Fraud_AccusedAccount "
            "WHERE AccusedAccountNo IN ("
            f"SELECT DISTINCT AccusedAccountNo FROM Tbl_Fraud_AccusedAccount WHERE Crime_No = '{c}' AND ParentAccountType = 'c'"
            ") AND Crime_No <> '{c}' AND ParentAccountType = 'c' "
            "ORDER BY AccusedAccountNo, Crime_No"
        )

        victims = _rows_to_dicts(run_sql(victims_sql))
        accused = _rows_to_dicts(run_sql(accused_sql))
        accused_by_level = _rows_to_dicts(run_sql(accused_by_level_sql))
        totals = _rows_to_dicts(run_sql(totals_sql))
        cross_crime = _rows_to_dicts(run_sql(cross_crime_sql))

        answer = ollama_chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a crime analyst. Summarize the dossier clearly and briefly. "
                        "Use INR for all currency amounts."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"CRIME_NO: {crime_no}\n"
                        f"TOTALS: {totals}\n"
                        f"ACCUSED_BY_LEVEL: {accused_by_level}\n"
                        f"CROSS_CRIME: {cross_crime}\n"
                    ),
                },
            ],
            temperature=0.0,
        )

        return {
            "ok": True,
            "crime_no": crime_no,
            "summary": answer,
            "totals": totals,
            "victims": victims,
            "accused": accused,
            "accused_by_level": accused_by_level,
            "cross_crime": cross_crime,
        }

    except Exception as e:
        return {"ok": False, "error": "Failed to build report", "detail": str(e)}


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
# Docs Transcribe (STT only — no RAG)
# ------------------------------------------------------------------------------
def _convert_to_wav16k(input_path: str, output_path: str):
    """Convert any audio file to 16kHz mono WAV using PyAV (ffmpeg)."""
    import av
    import numpy as np
    import wave
    import struct

    container = av.open(input_path)
    audio_stream = next(s for s in container.streams if s.type == "audio")

    resampler = av.AudioResampler(
        format="s16",       # 16-bit signed PCM
        layout="mono",      # mono
        rate=16000,          # 16kHz — what Whisper expects
    )

    pcm_data = bytearray()
    for frame in container.decode(audio_stream):
        for resampled in resampler.resample(frame):
            pcm_data.extend(bytes(resampled.planes[0]))

    container.close()

    # Write as WAV
    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit = 2 bytes
        wf.setframerate(16000)
        wf.writeframes(bytes(pcm_data))

    duration = len(pcm_data) / (2 * 16000)  # bytes / (bytes_per_sample * sample_rate)
    print(f"[Audio Convert] {input_path} -> {output_path}, PCM bytes={len(pcm_data)}, duration={duration:.1f}s")
    return duration


@app.post("/docs/transcribe")
async def docs_transcribe(audio: UploadFile = File(...)):
    """
    Transcribe audio to text using local Whisper. Returns { ok, transcription }.
    """
    tmp_path = None
    wav_path = None
    try:
        ext = os.path.splitext(audio.filename or "audio.webm")[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(await audio.read())
            tmp_path = tmp.name

        file_size = os.path.getsize(tmp_path)
        if file_size < 1000:
            return {"ok": False, "error": f"Audio too short ({file_size} bytes). Please speak longer and try again."}

        # Save debug copy so user can verify audio quality
        debug_dir = os.path.join(os.path.dirname(__file__), "debug_audio")
        os.makedirs(debug_dir, exist_ok=True)
        import shutil
        debug_original = os.path.join(debug_dir, f"last_recording{ext}")
        shutil.copy2(tmp_path, debug_original)
        print(f"[Transcribe] Saved debug audio: {debug_original} ({file_size} bytes)")

        # Convert webm/opus -> 16kHz mono WAV for reliable Whisper decoding
        wav_path = tmp_path + ".wav"
        try:
            audio_duration = _convert_to_wav16k(tmp_path, wav_path)
        except Exception as conv_err:
            print(f"[Transcribe] WAV conversion failed: {conv_err}, falling back to raw file")
            wav_path = None
            audio_duration = 0

        transcribe_path = wav_path if wav_path and os.path.exists(wav_path) else tmp_path

        # Also save the converted WAV for debugging
        if wav_path and os.path.exists(wav_path):
            debug_wav = os.path.join(debug_dir, "last_recording.wav")
            shutil.copy2(wav_path, debug_wav)

        segments, _info = get_whisper_model().transcribe(
            transcribe_path,
            beam_size=5,
            language="en",
        )
        transcription = " ".join(seg.text.strip() for seg in segments).strip()

        # Log for debugging
        print(f"[Transcribe] file={file_size} bytes, lang={_info.language}, "
              f"duration={_info.duration:.1f}s, text='{transcription}'")

        # Filter out empty or common Whisper hallucinations on silence/noise
        cleaned = transcription.strip().strip(".").strip()
        HALLUCINATIONS = {
            "", "thank you", "thanks for watching", "subscribe",
            "you", "bye", ".", "...", "thank you for watching",
            "please subscribe", "like and subscribe",
        }
        if not cleaned or cleaned.lower() in HALLUCINATIONS or len(cleaned) < 3:
            return {
                "ok": False,
                "error": (
                    f"Could not transcribe audio ({file_size} bytes, "
                    f"lang={_info.language}, {_info.duration:.1f}s). "
                    f"Whisper heard: '{transcription}'. "
                    f"Please speak clearly and try again."
                ),
            }

        return {"ok": True, "transcription": transcription}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": "Transcription failed", "detail": str(e)}
    finally:
        for p in [tmp_path, wav_path]:
            if p:
                try:
                    os.remove(p)
                except Exception:
                    pass


# ------------------------------------------------------------------------------
# Docs Voice Ask (STT + RAG Q&A)
# ------------------------------------------------------------------------------
@app.post("/docs/voice-ask")
async def docs_voice_ask(
    audio: UploadFile = File(...),
    doc_id: Optional[str] = Form(None),
    history: Optional[str] = Form(None),
):
    """
    Voice Q&A: receive audio → transcribe with local Whisper → answer via RAG.
    Returns { ok, transcription, answer, used_chunks }.
    """
    tmp_path = None
    try:
        # Save uploaded audio to temp file
        ext = os.path.splitext(audio.filename or "audio.webm")[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(await audio.read())
            tmp_path = tmp.name

        # Transcribe with faster-whisper (local, offline)
        segments, _info = get_whisper_model().transcribe(tmp_path, language="en")
        transcription = " ".join(seg.text.strip() for seg in segments).strip()

        if not transcription:
            return {"ok": False, "error": "Could not transcribe audio. Please speak clearly and try again."}

        # Parse history if provided
        parsed_history: List[ChatMessage] = []
        if history:
            try:
                raw = json.loads(history)
                parsed_history = [ChatMessage(**m) for m in raw]
            except Exception:
                pass

        # Build context from history (reuse existing helper)
        history_context = build_context_from_history(parsed_history, keep_last=8)
        question = transcription
        if history_context:
            question = (
                "You are continuing an ongoing conversation about the same document(s).\n"
                "Use the context to resolve references like 'it', 'that section', 'previous answer'.\n\n"
                f"CONVERSATION CONTEXT:\n{history_context}\n\n"
                f"CURRENT USER QUESTION:\n{transcription}"
            )

        # Answer via existing RAG pipeline
        result = ask_pdf(doc_id=doc_id, question=question, top_k=15)

        return {"ok": True, "transcription": transcription, **result}

    except Exception as e:
        return {"ok": False, "error": "Voice Q&A failed", "detail": str(e)}
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except Exception:
                pass


# ------------------------------------------------------------------------------
# Docs Ask (Agentic Multi-doc Q&A)
# ------------------------------------------------------------------------------
@app.post("/docs/agent")
def docs_agent(payload: DocAgentQuestion):
    """
    Agentic multi-doc Q&A across selected documents.
    """
    try:
        history_context = build_context_from_history(payload.history, keep_last=8)

        question = payload.question
        if history_context:
            question = (
                "You are continuing an ongoing conversation about the same set of documents.\n"
                "Use the context to resolve references like 'it', 'that section', 'previous answer'.\n\n"
                f"CONVERSATION CONTEXT:\n{history_context}\n\n"
                f"CURRENT USER QUESTION:\n{payload.question}"
            )

        result = ask_docs_agent(question=question, doc_ids=payload.doc_ids, top_k=6)
        return {"ok": True, **result}

    except Exception as e:
        return {"ok": False, "error": "Failed to answer across documents", "detail": str(e)}


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

