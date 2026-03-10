import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import json
import re
import tempfile
import threading

from typing import Optional, List, Literal
from pydantic import BaseModel

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

from mysql_db import get_conn
from ollama_client import ollama_chat
from rag import index_document, ask_pdf, ask_docs_agent, clear_all_documents, get_all_doc_chunks, get_indexed_doc_list
from config import WHISPER_MODEL
from auth import router as auth_router, CurrentUser, get_current_user
from cases import router as cases_router, _get_case_for_user
from entity_graph import extract_and_store_entities, get_all_entities, get_graph_data, clear_graph_data
from activity_timeline import extract_and_store_activities, get_timeline_data, get_breadcrumb_trail, get_groups as get_timeline_groups, clear_timeline_data, get_extracted_doc_ids
from qa_testing import extract_prompts_from_file, start_test_run, get_test_status, get_test_results
from location_extractor import (
    extract_and_store_locations,
    get_all_locations,
    clear_locations_data,
    get_extracted_doc_ids_for_locations,
)
from structured_tables import (
    get_all_smac_reports,
    get_smac_report_by_doc,
    get_all_ir_reports,
    get_ir_report_full,
    execute_sql_query,
    get_table_schema_description,
    clear_all_structured_data,
)

# Lazy-loaded Whisper model (only loads when voice is first used)
_whisper_model = None


def _scoped_col(collection: str, case_id: int) -> str:
    """Return ChromaDB collection name scoped to a case: e.g. IR_c3, SMAC_c5."""
    return f"{collection}_c{case_id}"

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
app = FastAPI(title="ISD Document Intelligence V5")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth routes: /auth/register, /auth/login, /auth/me, /auth/change-password
app.include_router(auth_router)

# Case management routes: /cases  (list, create, get, update, delete)
app.include_router(cases_router)


# ------------------------------------------------------------------------------
# Models
# ------------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class DocQuestion(BaseModel):
    question: str
    history: Optional[List[ChatMessage]] = None
    doc_id: Optional[str] = None
    collection: str = "SMAC"
    case_id: int = 0


class DocAgentQuestion(BaseModel):
    question: str
    history: Optional[List[ChatMessage]] = None
    doc_ids: List[str]
    collection: str = "SMAC"
    case_id: int = 0


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def build_context_from_history(history: Optional[List[ChatMessage]], keep_last: int = 8) -> str:
    if not history:
        return ""
    last = history[-keep_last:]
    lines = []
    for m in last:
        lines.append(f"{m.role.upper()}: {m.content}")
    return "\n".join(lines)


# ------------------------------------------------------------------------------
# Spell Checker (browser-independent, offline)
# ------------------------------------------------------------------------------
from spellchecker import SpellChecker

_spell = SpellChecker()
_spell.word_frequency.load_words([
    "associates", "hideouts", "accused", "complainant", "fir", "chargesheet",
    "smac", "ncrp", "cybercrime", "aadhaar", "pancard", "aadhar",
    "accomplice", "accomplices", "hideout", "absconding", "absconder",
])

# ------------------------------------------------------------------------------
# Health
# ------------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True, "service": "ISD Document Intelligence"}


# Pending entity extraction jobs (deferred until all indexing is done)
_pending_entity_jobs: list = []

# Extraction progress tracking (for frontend polling)
_extraction_status = {
    "running": False, "completed": 0, "total": 0, "done": False, "error": "",
    "batch_current": 0, "batch_total": 0, "doc_name": "",
}

# Timeline extraction progress tracking
_timeline_extraction_status = {"running": False, "completed": 0, "total": 0, "done": False, "error": ""}

# Location extraction progress tracking
_location_extraction_status = {"running": False, "completed": 0, "total": 0, "done": False, "error": ""}


# ------------------------------------------------------------------------------
# Docs Upload (Index) — PDF/DOCX/XLSX/CSV
# ------------------------------------------------------------------------------
@app.post("/docs/upload")
async def docs_upload(
    file: UploadFile = File(...),
    collection: str = Form("SMAC"),
    case_id: int = Form(0),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in [".pdf", ".docx", ".doc", ".xlsx", ".csv"]:
            return {"ok": False, "error": "Supported: PDF, DOCX, DOC, XLSX, CSV"}

        case = _get_case_for_user(case_id, current_user.user_id) if case_id else None
        col = _scoped_col(collection, case_id) if case_id else collection

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        indexed = index_document(tmp_path, file.filename, collection_name=col)

        try:
            os.remove(tmp_path)
        except Exception:
            pass

        if indexed.get("ok") is False:
            return indexed

        # Store chunks for deferred entity extraction
        doc_id = indexed.get("doc_id")
        doc_name = indexed.get("doc_name", file.filename)
        chunks = indexed.get("_chunks", [])
        if doc_id and chunks:
            _pending_entity_jobs.append({
                "doc_id": doc_id,
                "doc_name": doc_name,
                "chunks": chunks,
                "case_id": case_id,
            })

        # Strip internal _chunks before sending to client
        indexed.pop("_chunks", None)

        return {"ok": True, **indexed}

    except Exception as e:
        print(f"[Upload Error] {file.filename}: {type(e).__name__}: {e}")
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)}"}


# ------------------------------------------------------------------------------
# Docs Extract Entities (deferred — called after all indexing is done)
# ------------------------------------------------------------------------------
@app.post("/docs/extract-entities")
def docs_extract_entities():
    global _pending_entity_jobs, _extraction_status
    jobs = list(_pending_entity_jobs)
    _pending_entity_jobs.clear()

    if not jobs:
        return {"ok": True, "message": "No pending entity extraction jobs.", "extracted": 0}

    _extraction_status.update({
        "running": True, "completed": 0, "total": len(jobs), "done": False, "error": "",
        "batch_current": 0, "batch_total": 0, "doc_name": "",
    })

    # Run all entity extraction in a single background thread (sequential, no model swapping)
    def _run_all():
        global _extraction_status
        for i, job in enumerate(jobs):
            _extraction_status["doc_name"] = job["doc_name"]
            _extraction_status["batch_current"] = 0
            _extraction_status["batch_total"] = 0

            def _batch_cb(batch_done, batch_total):
                _extraction_status["batch_current"] = batch_done
                _extraction_status["batch_total"] = batch_total

            try:
                extract_and_store_entities(
                    job["doc_id"], job["doc_name"], job["chunks"],
                    case_id=job.get("case_id"),
                    progress_callback=_batch_cb,
                )
            except Exception as ex:
                print(f"[EntityGraph] Failed for {job['doc_name']}: {ex}")
            _extraction_status["completed"] = i + 1
        _extraction_status["running"] = False
        _extraction_status["done"] = True
        print(f"[EntityGraph] Completed entity extraction for {len(jobs)} document(s)")

    thread = threading.Thread(target=_run_all, daemon=True)
    thread.start()

    return {"ok": True, "message": f"Entity extraction started for {len(jobs)} document(s).", "extracted": len(jobs)}


# ------------------------------------------------------------------------------
# Extract entities from ALL already-indexed documents in ChromaDB
# (useful when docs were indexed before entity graph existed, or server restarted)
# ------------------------------------------------------------------------------
@app.post("/graph/extract-all")
def graph_extract_all(
    collection: str = "SMAC",
    case_id: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Pull all doc chunks from ChromaDB and run entity extraction on them."""
    global _extraction_status
    try:
        if _extraction_status["running"]:
            return {"ok": False, "error": "Extraction is already running."}

        # For SMAC: only extract entities from Gist/Input content
        col = _scoped_col(collection, case_id) if case_id else collection
        field_filter = ["Gist", "Input"] if collection == "SMAC" else None
        doc_groups = get_all_doc_chunks(collection_name=col, field_filter=field_filter)
        if not doc_groups:
            return {"ok": True, "message": "No documents in ChromaDB to extract from.", "total": 0}

        # Clear existing graph data first to avoid duplicates
        clear_graph_data()

        _extraction_status.update({
            "running": True, "completed": 0, "total": len(doc_groups), "done": False, "error": "",
            "batch_current": 0, "batch_total": 0, "doc_name": "",
        })

        def _run_all():
            global _extraction_status
            for i, dg in enumerate(doc_groups):
                _extraction_status["doc_name"] = dg["doc_name"]
                _extraction_status["batch_current"] = 0
                _extraction_status["batch_total"] = 0

                def _batch_cb(batch_done, batch_total):
                    _extraction_status["batch_current"] = batch_done
                    _extraction_status["batch_total"] = batch_total

                try:
                    extract_and_store_entities(
                        dg["doc_id"], dg["doc_name"], dg["chunks"],
                        case_id=case_id or None,
                        progress_callback=_batch_cb,
                    )
                except Exception as ex:
                    print(f"[EntityGraph] Failed for {dg['doc_name']}: {ex}")
                _extraction_status["completed"] = i + 1
            _extraction_status["running"] = False
            _extraction_status["done"] = True
            print(f"[EntityGraph] Completed entity extraction for {len(doc_groups)} document(s) from ChromaDB")

        thread = threading.Thread(target=_run_all, daemon=True)
        thread.start()

        return {
            "ok": True,
            "message": f"Entity extraction started for {len(doc_groups)} document(s) from ChromaDB.",
            "total": len(doc_groups),
        }
    except Exception as e:
        _extraction_status.update({"running": False, "completed": 0, "total": 0, "done": False, "error": str(e), "batch_current": 0, "batch_total": 0, "doc_name": ""})
        return {"ok": False, "error": str(e)}


@app.get("/graph/extraction-status")
def graph_extraction_status():
    """Polling endpoint for frontend to check extraction progress."""
    return {"ok": True, **_extraction_status}


# ------------------------------------------------------------------------------
# Docs List (restore document list after page refresh)
# ------------------------------------------------------------------------------
@app.get("/docs/list")
def docs_list(
    collection: str = "SMAC",
    case_id: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        col = _scoped_col(collection, case_id) if case_id else collection
        docs = get_indexed_doc_list(collection_name=col)
        # Fallback: also include docs from the global (unscoped) collection
        if case_id:
            try:
                global_docs = get_indexed_doc_list(collection_name=collection)
                if global_docs:
                    existing_names = {d.get("doc_name") or d.get("name") for d in docs}
                    for gd in global_docs:
                        name = gd.get("doc_name") or gd.get("name")
                        if name not in existing_names:
                            docs.append(gd)
            except Exception:
                pass
        return {"ok": True, "docs": docs}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ------------------------------------------------------------------------------
# Docs Clear
# ------------------------------------------------------------------------------
@app.post("/docs/clear")
def clear_docs(
    collection: str = "SMAC",
    case_id: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    col = _scoped_col(collection, case_id) if case_id else collection
    cid = case_id or None
    out = clear_all_documents(collection_name=col)
    if out.get("ok"):
        try:
            clear_graph_data(case_id=cid)
        except Exception as e:
            print(f"[Graph Clear] Warning: {e}")
        try:
            clear_timeline_data(case_id=cid)
        except Exception as e:
            print(f"[Timeline Clear] Warning: {e}")
        try:
            clear_locations_data(case_id=cid)
        except Exception as e:
            print(f"[Locations Clear] Warning: {e}")
        try:
            clear_all_structured_data()
        except Exception as e:
            print(f"[Structured Clear] Warning: {e}")
        return out
    raise HTTPException(status_code=500, detail=out.get("error", "Failed to clear docs"))


# ------------------------------------------------------------------------------
# Docs Ask (RAG Q&A)
# ------------------------------------------------------------------------------
@app.post("/docs/ask")
def docs_ask(
    payload: DocQuestion,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        # Try scoped collection first; fall back to global if scoped is empty
        col = _scoped_col(payload.collection, payload.case_id) if payload.case_id else payload.collection
        # Check if scoped collection has any documents; if not, use global
        if payload.case_id:
            try:
                from rag import get_indexed_doc_list as _check_docs
                if not _check_docs(collection_name=col):
                    col = payload.collection  # Use global unscoped collection
            except Exception:
                pass
        result = ask_pdf(doc_id=payload.doc_id, question=payload.question, top_k=15, collection_name=col)

        return {"ok": True, **result}

    except Exception as e:
        return {"ok": False, "error": "Failed to answer from documents", "detail": str(e)}


# ------------------------------------------------------------------------------
# Spell Check
# ------------------------------------------------------------------------------
@app.post("/spell-check")
def spell_check(payload: dict):
    text = payload.get("text", "")
    words = re.findall(r"[a-zA-Z]+", text)
    corrections = {}
    for word in words:
        if len(word) < 3:
            continue
        if _spell.unknown([word.lower()]):
            suggestion = _spell.correction(word.lower())
            if suggestion and suggestion != word.lower():
                corrections[word] = suggestion
    return {"corrections": corrections}


# ------------------------------------------------------------------------------
# Docs Transcribe (STT only)
# ------------------------------------------------------------------------------
def _convert_to_wav16k(input_path: str, output_path: str):
    """Convert any audio file to 16kHz mono WAV using PyAV (ffmpeg)."""
    import av
    import wave

    container = av.open(input_path)
    audio_stream = next(s for s in container.streams if s.type == "audio")

    resampler = av.AudioResampler(
        format="s16",
        layout="mono",
        rate=16000,
    )

    pcm_data = bytearray()
    for frame in container.decode(audio_stream):
        for resampled in resampler.resample(frame):
            pcm_data.extend(bytes(resampled.planes[0]))

    container.close()

    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(bytes(pcm_data))

    duration = len(pcm_data) / (2 * 16000)
    print(f"[Audio Convert] {input_path} -> {output_path}, PCM bytes={len(pcm_data)}, duration={duration:.1f}s")
    return duration


@app.post("/docs/transcribe")
async def docs_transcribe(audio: UploadFile = File(...)):
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

        # Save debug copy
        debug_dir = os.path.join(os.path.dirname(__file__), "debug_audio")
        os.makedirs(debug_dir, exist_ok=True)
        import shutil
        debug_original = os.path.join(debug_dir, f"last_recording{ext}")
        shutil.copy2(tmp_path, debug_original)
        print(f"[Transcribe] Saved debug audio: {debug_original} ({file_size} bytes)")

        # Convert to 16kHz mono WAV
        wav_path = tmp_path + ".wav"
        try:
            _convert_to_wav16k(tmp_path, wav_path)
        except Exception as conv_err:
            print(f"[Transcribe] WAV conversion failed: {conv_err}, falling back to raw file")
            wav_path = None

        transcribe_path = wav_path if wav_path and os.path.exists(wav_path) else tmp_path

        if wav_path and os.path.exists(wav_path):
            debug_wav = os.path.join(debug_dir, "last_recording.wav")
            shutil.copy2(wav_path, debug_wav)

        segments, _info = get_whisper_model().transcribe(
            transcribe_path,
            beam_size=5,
            language="en",
        )
        transcription = " ".join(seg.text.strip() for seg in segments).strip()

        print(f"[Transcribe] file={file_size} bytes, lang={_info.language}, "
              f"duration={_info.duration:.1f}s, text='{transcription}'")

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
    tmp_path = None
    try:
        ext = os.path.splitext(audio.filename or "audio.webm")[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(await audio.read())
            tmp_path = tmp.name

        segments, _info = get_whisper_model().transcribe(tmp_path, language="en")
        transcription = " ".join(seg.text.strip() for seg in segments).strip()

        if not transcription:
            return {"ok": False, "error": "Could not transcribe audio. Please speak clearly and try again."}

        parsed_history: List[ChatMessage] = []
        if history:
            try:
                raw = json.loads(history)
                parsed_history = [ChatMessage(**m) for m in raw]
            except Exception:
                pass

        history_context = build_context_from_history(parsed_history, keep_last=8)
        question = transcription
        if history_context:
            question = (
                "You are continuing an ongoing conversation about the same document(s).\n"
                "Use the context to resolve references like 'it', 'that section', 'previous answer'.\n\n"
                f"CONVERSATION CONTEXT:\n{history_context}\n\n"
                f"CURRENT USER QUESTION:\n{transcription}"
            )

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
# Docs Agent (Multi-doc Q&A)
# ------------------------------------------------------------------------------
@app.post("/docs/agent")
def docs_agent(
    payload: DocAgentQuestion,
    current_user: CurrentUser = Depends(get_current_user),
):
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

        col = _scoped_col(payload.collection, payload.case_id) if payload.case_id else payload.collection
        result = ask_docs_agent(question=question, doc_ids=payload.doc_ids, top_k=6, collection_name=col)
        return {"ok": True, **result}

    except Exception as e:
        return {"ok": False, "error": "Failed to answer across documents", "detail": str(e)}


# ------------------------------------------------------------------------------
# Entity Graph Endpoints
# ------------------------------------------------------------------------------
@app.get("/graph/entities")
def graph_entities(
    type: Optional[str] = None,
    case_id: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        entities = get_all_entities(type_filter=type, case_id=case_id or None)
        return {"ok": True, "entities": entities, "count": len(entities)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/graph/data")
def graph_data(
    search: Optional[str] = None,
    limit: int = 1000,
    case_id: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        data = get_graph_data(search=search, limit=limit, case_id=case_id or None)
        return {"ok": True, **data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.delete("/graph/clear")
def graph_clear(
    case_id: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        result = clear_graph_data(case_id=case_id or None)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ------------------------------------------------------------------------------
# Activity Timeline Endpoints
# ------------------------------------------------------------------------------
@app.post("/timeline/extract-all")
def timeline_extract_all(
    collection: str = "SMAC",
    case_id: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Pull all doc chunks from ChromaDB and run activity extraction on them."""
    global _timeline_extraction_status
    try:
        if _timeline_extraction_status["running"]:
            return {"ok": False, "error": "Timeline extraction is already running."}

        # For SMAC: only extract activities from Gist/Input content
        col = _scoped_col(collection, case_id) if case_id else collection
        field_filter = ["Gist", "Input"] if collection == "SMAC" else None
        doc_groups = get_all_doc_chunks(collection_name=col, field_filter=field_filter)
        if not doc_groups:
            return {"ok": True, "message": "No documents in ChromaDB to extract from.", "total": 0}

        # Incremental: skip documents already extracted
        already_extracted = get_extracted_doc_ids(case_id=case_id or None)
        new_docs = [dg for dg in doc_groups if dg["doc_id"] not in already_extracted]

        if not new_docs:
            _timeline_extraction_status = {"running": False, "completed": 0, "total": 0, "done": True, "error": ""}
            return {"ok": True, "message": f"All {len(doc_groups)} documents already extracted. No new documents to process.", "total": 0}

        skipped = len(doc_groups) - len(new_docs)
        print(f"[Timeline] Incremental: {len(new_docs)} new, {skipped} already extracted")

        _timeline_extraction_status = {"running": True, "completed": 0, "total": len(new_docs), "done": False, "error": ""}

        def _run_all():
            global _timeline_extraction_status
            for i, dg in enumerate(new_docs):
                try:
                    extract_and_store_activities(dg["doc_id"], dg["doc_name"], dg["chunks"], case_id=case_id or None)
                except Exception as ex:
                    print(f"[Timeline] Failed for {dg['doc_name']}: {ex}")
                _timeline_extraction_status["completed"] = i + 1
            _timeline_extraction_status["running"] = False
            _timeline_extraction_status["done"] = True
            print(f"[Timeline] Completed activity extraction for {len(new_docs)} new document(s) ({skipped} skipped)")

        thread = threading.Thread(target=_run_all, daemon=True)
        thread.start()

        return {
            "ok": True,
            "message": f"Activity extraction started for {len(new_docs)} new document(s)." + (f" ({skipped} already extracted, skipped.)" if skipped else ""),
            "total": len(new_docs),
        }
    except Exception as e:
        _timeline_extraction_status = {"running": False, "completed": 0, "total": 0, "done": False, "error": str(e)}
        return {"ok": False, "error": str(e)}


@app.get("/timeline/extraction-status")
def timeline_extraction_status():
    """Polling endpoint for frontend to check timeline extraction progress."""
    return {"ok": True, **_timeline_extraction_status}


@app.get("/timeline/data")
def timeline_data(
    group: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    case_id: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        activities = get_timeline_data(group_filter=group, status_filter=status, search=search, case_id=case_id or None)
        return {"ok": True, "activities": activities, "count": len(activities)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/timeline/breadcrumb")
def timeline_breadcrumb(
    tms_id: str,
    case_id: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        trail = get_breadcrumb_trail(tms_id, case_id=case_id or None)
        return {"ok": True, **trail}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/timeline/groups")
def timeline_groups(
    case_id: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        groups = get_timeline_groups(case_id=case_id or None)
        return {"ok": True, "groups": groups}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ------------------------------------------------------------------------------
# Location Map Endpoints (IR collection — extract addresses, geocode, display on map)
# ------------------------------------------------------------------------------
@app.post("/locations/extract-all")
def locations_extract_all(
    collection: str = "IR",
    case_id: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Extract locations from all indexed IR documents (incremental)."""
    global _location_extraction_status
    try:
        if _location_extraction_status["running"]:
            return {"ok": False, "error": "Location extraction is already running."}

        col = _scoped_col(collection, case_id) if case_id else collection
        doc_groups = get_all_doc_chunks(collection_name=col)
        if not doc_groups:
            return {"ok": True, "message": "No documents in ChromaDB to extract from.", "total": 0}

        # Incremental: skip docs already extracted
        already_extracted = get_extracted_doc_ids_for_locations(case_id=case_id or None)
        new_docs = [dg for dg in doc_groups if dg["doc_id"] not in already_extracted]

        if not new_docs:
            _location_extraction_status = {"running": False, "completed": 0, "total": 0, "done": True, "error": ""}
            return {
                "ok": True,
                "message": f"All {len(doc_groups)} documents already extracted. No new documents to process.",
                "total": 0,
            }

        skipped = len(doc_groups) - len(new_docs)
        print(f"[Locations] Incremental: {len(new_docs)} new, {skipped} already extracted")

        _location_extraction_status = {
            "running": True, "completed": 0, "total": len(new_docs), "done": False, "error": ""
        }

        def _run_all():
            global _location_extraction_status
            for i, dg in enumerate(new_docs):
                try:
                    extract_and_store_locations(dg["doc_id"], dg["doc_name"], dg["chunks"], case_id=case_id or None)
                except Exception as ex:
                    print(f"[Locations] Failed for {dg['doc_name']}: {ex}")
                _location_extraction_status["completed"] = i + 1
            _location_extraction_status["running"] = False
            _location_extraction_status["done"] = True
            print(f"[Locations] Completed for {len(new_docs)} doc(s) ({skipped} skipped)")

        thread = threading.Thread(target=_run_all, daemon=True)
        thread.start()

        return {
            "ok": True,
            "message": (
                f"Location extraction started for {len(new_docs)} document(s)."
                + (f" ({skipped} already extracted, skipped.)" if skipped else "")
            ),
            "total": len(new_docs),
        }
    except Exception as e:
        _location_extraction_status = {
            "running": False, "completed": 0, "total": 0, "done": False, "error": str(e)
        }
        return {"ok": False, "error": str(e)}


@app.get("/locations/extraction-status")
def locations_extraction_status():
    """Polling endpoint for frontend to check location extraction progress."""
    return {"ok": True, **_location_extraction_status}


@app.get("/locations/data")
def locations_data(
    case_id: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return all geocoded location records for map display."""
    try:
        locations = get_all_locations(case_id=case_id or None)
        return {"ok": True, "locations": locations, "count": len(locations)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ------------------------------------------------------------------------------
# Structured Data Endpoints (SMAC and IR tables)
# ------------------------------------------------------------------------------
@app.get("/structured/smac")
def structured_smac_list():
    """Return all SMAC reports from the structured table."""
    try:
        reports = get_all_smac_reports()
        return {"ok": True, "reports": reports, "count": len(reports)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/structured/smac/{doc_id}")
def structured_smac_detail(doc_id: str):
    """Return a single SMAC report by doc_id."""
    try:
        report = get_smac_report_by_doc(doc_id)
        if report:
            return {"ok": True, "report": report}
        return {"ok": False, "error": "SMAC report not found"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/structured/ir")
def structured_ir_list():
    """Return all IR reports (main table) from the structured table."""
    try:
        reports = get_all_ir_reports()
        return {"ok": True, "reports": reports, "count": len(reports)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/structured/ir/{doc_id}")
def structured_ir_detail(doc_id: str):
    """Return a complete IR report with all child table data."""
    try:
        report = get_ir_report_full(doc_id)
        if report:
            return {"ok": True, "report": report}
        return {"ok": False, "error": "IR report not found"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ------------------------------------------------------------------------------
# NL→SQL Query Endpoint
# Natural Language question → LLM generates SQL → executes → returns results
# ------------------------------------------------------------------------------
class NLSQLQuestion(BaseModel):
    question: str
    collection: str = "SMAC"


@app.post("/structured/query")
def structured_nl_query(payload: NLSQLQuestion):
    """
    Natural Language → SQL query pipeline.
    1. User asks a question in natural language
    2. LLM receives the table schema + question, generates a SQL SELECT query
    3. SQL is executed against MSSQL
    4. LLM formats the raw results into a natural language answer
    """
    try:
        schema = get_table_schema_description()

        # Step 1: Generate SQL from natural language
        sql_prompt = (
            "You are a SQL expert for T-SQL (Microsoft SQL Server).\n"
            "Given the database schema below and the user's question, generate a SQL SELECT query.\n\n"
            f"DATABASE SCHEMA:\n{schema}\n\n"
            f"USER QUESTION: {payload.question}\n\n"
            "RULES:\n"
            "- Return ONLY the SQL query, no explanation.\n"
            "- Use T-SQL syntax (TOP instead of LIMIT, NVARCHAR, etc.).\n"
            "- The table is a key-value store: each row has field_key (field name) and field_value (value).\n"
            "- To find a value, search field_key with LIKE '%keyword%' and return field_value.\n"
            "- Use LIKE with '%keyword%' for text matching (case-insensitive).\n"
            "- Filter by collection = 'SMAC' for SMAC reports, 'IR' for IR reports.\n"
            "- Filter by doc_name LIKE '%name%' to find specific documents.\n"
            "- To compare fields across documents, self-join document_fields on doc_id.\n"
            "- Always use SELECT, never INSERT/UPDATE/DELETE.\n"
            "- Return all relevant columns that answer the question.\n"
        )

        sql_response = ollama_chat(
            [{"role": "user", "content": sql_prompt}],
            temperature=0.0,
            model=PDF_MODEL,
        )

        # Extract SQL from the response (strip markdown code fences if present)
        sql_query = sql_response.strip()
        if sql_query.startswith("```"):
            lines = sql_query.split("\n")
            sql_lines = [ln for ln in lines if not ln.strip().startswith("```")]
            sql_query = "\n".join(sql_lines).strip()

        # Remove any leading "sql" keyword from code fence
        if sql_query.lower().startswith("sql"):
            sql_query = sql_query[3:].strip()

        print(f"[NL→SQL] Generated query: {sql_query}")

        # Step 2: Execute the SQL query
        rows = execute_sql_query(sql_query)

        # Check for errors
        if rows and len(rows) == 1 and "error" in rows[0]:
            return {
                "ok": False,
                "error": f"SQL execution error: {rows[0]['error']}",
                "sql": sql_query,
            }

        # Step 3: Format results into natural language answer
        if not rows:
            answer = "No results found for your query."
        else:
            # Prepare result summary for LLM
            result_text = json.dumps(rows[:50], indent=2, default=str)  # Cap at 50 rows

            answer_prompt = (
                "You are a helpful assistant for Karnataka State Police (KSP).\n"
                "Given the user's question and the SQL query results, provide a clear, "
                "factual answer based ONLY on the data returned.\n\n"
                f"USER QUESTION: {payload.question}\n\n"
                f"SQL RESULTS ({len(rows)} rows):\n{result_text}\n\n"
                "RULES:\n"
                "- Answer in clear, readable format.\n"
                "- If results are tabular, present them as a formatted list or table.\n"
                "- Include all relevant data from the results.\n"
                "- Do NOT add information not present in the results.\n"
                "- If results are empty, say 'No matching records found'.\n"
            )

            answer = ollama_chat(
                [{"role": "user", "content": answer_prompt}],
                temperature=0.0,
                model=PDF_MODEL,
            )

        return {
            "ok": True,
            "answer": answer,
            "sql": sql_query,
            "row_count": len(rows),
            "raw_results": rows[:20],  # Include first 20 raw rows for transparency
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}


# ------------------------------------------------------------------------------
# QA Testing Endpoints
# ------------------------------------------------------------------------------
class QARunRequest(BaseModel):
    prompts: List[str]
    doc_ids: Optional[List[str]] = None
    collection: str = "SMAC"


@app.post("/qa/upload-prompts")
async def qa_upload_prompts(file: UploadFile = File(...)):
    """Upload a PDF or DOCX file containing test prompts and extract them."""
    try:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in [".pdf", ".docx", ".doc"]:
            return {"ok": False, "error": "Supported: PDF, DOCX. Please upload a file with test prompts."}

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        prompts = extract_prompts_from_file(tmp_path, file.filename)

        try:
            os.remove(tmp_path)
        except Exception:
            pass

        return {"ok": True, "prompts": prompts, "count": len(prompts)}

    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/qa/run")
def qa_run(payload: QARunRequest):
    """Start a batch QA test run in a background thread."""
    if not payload.prompts:
        return {"ok": False, "error": "No prompts provided."}

    result = start_test_run(
        prompts=payload.prompts,
        doc_ids=payload.doc_ids,
        collection=payload.collection,
    )
    return result


@app.get("/qa/status")
def qa_status(run_id: str):
    """Poll progress and partial results for a QA test run."""
    result = get_test_status(run_id)
    if result is None:
        return {"ok": False, "error": f"Test run '{run_id}' not found."}
    return result


@app.get("/qa/results")
def qa_results(run_id: str):
    """Get full results for a completed QA test run."""
    result = get_test_results(run_id)
    if result is None:
        return {"ok": False, "error": f"Test run '{run_id}' not found."}
    return result


# ------------------------------------------------------------------------------
# Answer Ratings
# ------------------------------------------------------------------------------
def _init_ratings_table():
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS answer_ratings (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                user_id     INT           NOT NULL,
                username    VARCHAR(100)  NOT NULL,
                collection  VARCHAR(50)   NOT NULL DEFAULT 'SMAC',
                case_id     INT           NOT NULL DEFAULT 0,
                question    TEXT,
                answer      TEXT,
                rating      INT           NOT NULL,
                created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        print("[Ratings] answer_ratings table ready")
    except Exception as e:
        print(f"[Ratings] Warning: {e}")
    finally:
        conn.close()

_init_ratings_table()


class RatingRequest(BaseModel):
    question: str
    answer: str
    rating: int
    collection: str = "SMAC"
    case_id: int = 0


@app.post("/ratings")
def submit_rating(
    payload: RatingRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Submit a rating for an answer. Ratings: 2,1,0,-1,-2. Q&A stored only for 1 and 2."""
    if payload.rating not in (2, 1, 0, -1, -2):
        return {"ok": False, "error": "Rating must be one of: 2, 1, 0, -1, -2"}

    conn = get_conn()
    try:
        cur = conn.cursor()
        if payload.rating >= 1:
            cur.execute(
                "INSERT INTO answer_ratings (user_id, username, collection, case_id, question, answer, rating) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (current_user.user_id, current_user.username,
                 payload.collection, payload.case_id,
                 payload.question, payload.answer, payload.rating),
            )
        else:
            cur.execute(
                "INSERT INTO answer_ratings (user_id, username, collection, case_id, rating) "
                "VALUES (%s, %s, %s, %s, %s)",
                (current_user.user_id, current_user.username,
                 payload.collection, payload.case_id,
                 payload.rating),
            )
        conn.commit()
        return {"ok": True, "message": "Rating saved."}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


@app.get("/ratings/stats")
def rating_stats(current_user: CurrentUser = Depends(get_current_user)):
    """Get rating statistics (admin view)."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT rating, COUNT(*) as cnt FROM answer_ratings GROUP BY rating ORDER BY rating DESC"
        )
        rows = [{"rating": r[0], "count": r[1]} for r in cur.fetchall()]
        total = sum(r["count"] for r in rows)
        return {"ok": True, "stats": rows, "total": total}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()
