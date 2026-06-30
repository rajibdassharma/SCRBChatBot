"""
Two-call orchestration: question → SQL, then (sql + rows) → plain English.

Call 1 uses temperature=0 for deterministic SQL.
Call 2 uses temperature=0.3 so the summary reads a bit more naturally.
"""
from __future__ import annotations

import json
import logging

from chat.ollama_client import chat as ollama_chat
from chat.schema_description import get_schema_text

log = logging.getLogger(__name__)


_SQL_SYSTEM_PROMPT = """\
You are a precise SQL generator. Output ONLY a MySQL SELECT statement
that answers the user's question. No explanation, no markdown fences,
no comments — just the SQL.

If the question cannot be answered from the schema below, output exactly
the single token NO_SQL.

Rules:
- A single SELECT statement.
- MySQL syntax (not PostgreSQL).
- Use the joins shown in the schema notes when you need district / PS info.
- Do NOT touch any table not listed in the schema.
- Limit text fields (facts, statement) — never include them in lists of
  more than a few rows. Prefer compact identifying columns.
- For "list" questions, include the FIR no and a name/title so the user
  knows what each row is.

""" + get_schema_text()


_SUMMARY_SYSTEM_PROMPT = """\
You are summarising the result of a database query for a Karnataka State
Police cyber-fraud operator. Keep your answer to 1-3 sentences. Be
direct: state the count / amount / list. Don't restate the question.
Don't mention SQL or databases. Use Indian numeric formatting (lakh /
crore is fine if natural).

If the rows are empty, say so plainly: "No matching records found."
"""


_FOLLOWUP_SYSTEM_PROMPT = """\
You are suggesting follow-up questions for a Karnataka State Police
cyber-fraud operator who just asked a question about the case
database. Lean toward DRILL-DOWNS on what they just saw — list it
out, break by district / month, compare to a prior period, look at
the entities involved (banks, victims, arrests).

Each suggestion must:
- Be answerable from the cases / arrests / victims / petitions /
  lien_accounts / refunds tables. Do not propose questions about
  data we don't have (PDFs, audio, files, login history, etc.).
- Be under 90 characters.
- Be phrased as a question or imperative ("Show...", "List...",
  "How many...", "What's the breakdown by...").
- Be DIFFERENT from the question the user just asked.

Output exactly 3 lines, one question per line. No numbering, no
quotes, no bullet markers, no preamble, no closing remarks.
"""


async def generate_sql(question: str) -> str:
    """Ask the model for SQL. Returns the LLM's raw text — the safe
    executor handles fence stripping and validation."""
    return await ollama_chat(
        system=_SQL_SYSTEM_PROMPT,
        user=question.strip(),
        temperature=0.0,
    )


async def summarise(question: str, sql: str, rows: list[dict], row_count: int) -> str:
    """Ask the model to write a 1-3 sentence natural-language answer."""
    # Truncate rows for the prompt — first 20 is plenty for summarisation.
    sample = rows[:20]
    payload = {
        "question": question.strip(),
        "row_count": row_count,
        "rows_shown": len(sample),
        "rows": sample,
    }
    return await ollama_chat(
        system=_SUMMARY_SYSTEM_PROMPT,
        user=json.dumps(payload, default=str, ensure_ascii=False),
        temperature=0.3,
        # Summary prompt is small but model could still be cold on first
        # use; align with the SQL-gen timeout to avoid spurious failures.
        timeout_s=120.0,
    )


async def suggest_followups(question: str, answer: str, row_count: int) -> list[str]:
    """Ask the model for 2-3 short follow-up questions the operator might
    want to ask next. Returns up to 3 questions, deduped against the
    original. Returns [] on any error — follow-ups are best-effort, never
    fatal."""
    payload = json.dumps(
        {"question": question.strip(), "answer": answer.strip(), "row_count": row_count},
        ensure_ascii=False,
    )
    raw = await ollama_chat(
        system=_FOLLOWUP_SYSTEM_PROMPT,
        user=payload,
        temperature=0.3,
        timeout_s=120.0,
    )
    out: list[str] = []
    seen: set[str] = {question.strip().lower()}
    for line in raw.splitlines():
        # Strip common LLM cruft: leading bullets, numbering, quotes.
        cleaned = line.strip().lstrip("-•*").lstrip("0123456789.) ").strip().strip('"').strip("'")
        if not cleaned or len(cleaned) > 120:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        if len(out) == 3:
            break
    return out
