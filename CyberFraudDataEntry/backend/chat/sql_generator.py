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
