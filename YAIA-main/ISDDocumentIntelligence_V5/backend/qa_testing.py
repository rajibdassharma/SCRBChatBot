"""
QA Testing — Batch prompt execution and accuracy validation
for ISD Document Intelligence V3.

Extracts test prompts from uploaded PDF/DOCX files, runs them
against the RAG pipeline, and collects results for review.
"""

import re
import time
import uuid
import threading
from typing import List, Dict, Any, Optional

from pypdf import PdfReader
from docx import Document as DocxDocument

from rag import ask_pdf


# ---------------------------------------------------------------------------
# Module-level state for test runs
# ---------------------------------------------------------------------------
_test_runs: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Prompt Extraction from PDF / DOCX
# ---------------------------------------------------------------------------
def extract_prompts_from_file(file_path: str, filename: str) -> List[str]:
    """
    Extract test prompts from a PDF or DOCX file.
    Splits text into individual prompts by:
      1. Numbered lines (e.g., "1.", "2)", "Q1:", etc.)
      2. Falling back to one prompt per non-empty line
    """
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if ext == "pdf":
        raw_text = _extract_text_from_pdf(file_path)
    elif ext in ("docx", "doc"):
        raw_text = _extract_text_from_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: .{ext}. Please upload a PDF or DOCX file.")

    return _split_into_prompts(raw_text)


def _extract_text_from_pdf(path: str) -> str:
    """Extract all text from a PDF using pypdf."""
    reader = PdfReader(path)
    pages: List[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text.strip())
    return "\n".join(pages)


def _extract_text_from_docx(path: str) -> str:
    """Extract all paragraph text from a DOCX file."""
    doc = DocxDocument(path)
    paragraphs: List[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


# Regex for numbered lines: "1.", "1)", "1:", "Q1.", "Q1)", "#1", etc.
_NUMBERED_LINE_RE = re.compile(
    r"^\s*(?:Q|q|#)?\s*(\d{1,3})\s*[.):\-]\s+(.+)", re.MULTILINE
)


def _split_into_prompts(text: str) -> List[str]:
    """
    Split extracted text into individual prompts.
    First tries numbered-line splitting; falls back to line-by-line.
    """
    # Try numbered extraction
    matches = _NUMBERED_LINE_RE.findall(text)
    if len(matches) >= 2:
        prompts = [m[1].strip() for m in matches if m[1].strip()]
        if prompts:
            return prompts

    # Fallback: one prompt per non-empty line (skip very short lines)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    # Filter out lines that look like headers/titles (too short to be a question)
    prompts = [line for line in lines if len(line) > 10]
    return prompts


# ---------------------------------------------------------------------------
# Batch Test Runner
# ---------------------------------------------------------------------------
def start_test_run(
    prompts: List[str],
    doc_ids: Optional[List[str]] = None,
    collection: str = "SMAC",
) -> Dict[str, Any]:
    """
    Start a batch test run in a background thread.
    Returns the run_id immediately; frontend polls for progress.
    """
    run_id = f"qa-{uuid.uuid4().hex[:12]}"

    run_state = {
        "id": run_id,
        "prompts": prompts,
        "doc_ids": doc_ids,
        "collection": collection,
        "results": [],
        "status": "running",
        "current": 0,
        "total": len(prompts),
    }
    _test_runs[run_id] = run_state

    thread = threading.Thread(
        target=_execute_test_run,
        args=(run_id,),
        daemon=True,
    )
    thread.start()

    return {"ok": True, "run_id": run_id, "total": len(prompts)}


def _execute_test_run(run_id: str):
    """Background thread: run each prompt through the RAG pipeline."""
    run = _test_runs.get(run_id)
    if not run:
        return

    prompts = run["prompts"]
    doc_ids = run["doc_ids"]
    collection = run["collection"]

    for i, prompt in enumerate(prompts):
        run["current"] = i
        t0 = time.time()

        try:
            if doc_ids and len(doc_ids) == 1:
                result = ask_pdf(doc_id=doc_ids[0], question=prompt, top_k=15, collection_name=collection)
            else:
                result = ask_pdf(doc_id=None, question=prompt, top_k=15, collection_name=collection)

            elapsed_ms = int((time.time() - t0) * 1000)

            run["results"].append({
                "index": i,
                "prompt": prompt,
                "answer": result.get("answer", ""),
                "used_chunks": [
                    {"doc_name": c.get("doc_name", ""), "page": c.get("page")}
                    for c in result.get("used_chunks", [])
                ],
                "elapsed_ms": elapsed_ms,
                "error": None,
            })
        except Exception as ex:
            elapsed_ms = int((time.time() - t0) * 1000)
            run["results"].append({
                "index": i,
                "prompt": prompt,
                "answer": "",
                "used_chunks": [],
                "elapsed_ms": elapsed_ms,
                "error": str(ex),
            })

        run["current"] = i + 1

    run["status"] = "done"
    print(f"[QA] Test run {run_id} completed: {len(prompts)} prompts")


def get_test_status(run_id: str) -> Optional[Dict[str, Any]]:
    """Get current status and partial results for a test run."""
    run = _test_runs.get(run_id)
    if not run:
        return None
    return {
        "ok": True,
        "run_id": run["id"],
        "status": run["status"],
        "current": run["current"],
        "total": run["total"],
        "results": run["results"],
    }


def get_test_results(run_id: str) -> Optional[Dict[str, Any]]:
    """Get full results for a completed test run."""
    run = _test_runs.get(run_id)
    if not run:
        return None
    return {
        "ok": True,
        "run_id": run["id"],
        "status": run["status"],
        "total": run["total"],
        "results": run["results"],
        "doc_ids": run["doc_ids"],
        "collection": run["collection"],
    }
