"""
SQL safety net for chat-generated queries.

The LLM cannot be fully trusted to produce safe SQL. Even with a tight
system prompt, prompt injection in the user question or a hallucination
could produce DML, DDL, or queries that touch tables we never exposed.

This module sits between the LLM output and the database:
  1. Extracts the SQL from whatever the LLM emitted (code-fenced or bare).
  2. Parses it with sqlparse and verifies it's a single SELECT.
  3. Blocks any keyword we never want to see (INSERT/UPDATE/DELETE/DDL,
     INTO OUTFILE, LOAD_FILE, INFORMATION_SCHEMA, mysql.*, etc.).
  4. Blocks references to tables outside the allowlist.
  5. Forces a LIMIT (default 200) if the LLM didn't add one.
  6. Executes with a 5s server-side timeout.

If any check fails the route returns 422 with a friendly message — the
SQL never reaches MySQL.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import sqlparse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


# Tables the chat is allowed to read. Anything else triggers a 422.
ALLOWED_TABLES: frozenset[str] = frozenset({
    "cases", "arrests", "victims", "petitions", "lien_accounts", "refunds",
    "units", "police_stations",
})

# Hard-blocked tokens (defence in depth on top of the SELECT-only check).
# Two lists because some patterns are word-bounded (DDL/DML verbs) and
# some include non-word characters (parens, spaces) that need substring
# matching.
#
# IMPORTANT: word-boundary matching is required, not substring — a naive
# `if "create" in sql` flags `created_at`, `if "update" in sql` flags
# `updated_at`, etc. Underscores ARE word chars in regex, so `\bcreate\b`
# correctly matches `CREATE` and does NOT match `created_at`.
_BLOCKED_TOKENS_WORD: frozenset[str] = frozenset({
    # DDL / DML — already blocked by SELECT-only check; double safety net.
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "rename", "grant", "revoke", "lock", "unlock", "call", "exec", "execute",
    # File-system reach
    "load_file", "outfile", "dumpfile",
    # System-table access — the ALLOWED_TABLES filter is the primary
    # defence; these add a belt for cases where the LLM tries to reference
    # them in a subquery or function-style.
    "information_schema", "performance_schema",
    # Timing / fingerprinting probes
    "sleep", "benchmark", "current_user",
})
_BLOCKED_SUBSTRINGS: frozenset[str] = frozenset({
    "into outfile", "into dumpfile", "user(", "version(",
})

_DEFAULT_LIMIT = 200
_QUERY_TIMEOUT_S = 5


class SqlRejected(Exception):
    """Raised when generated SQL fails a safety check."""


def extract_sql(llm_response: str) -> str:
    """Pull the SQL out of an LLM response. Accepts code-fenced blocks
    (```sql ... ``` or ``` ... ```) and bare SQL."""
    s = (llm_response or "").strip()
    # Strip ```sql ... ``` or ``` ... ```
    fence_match = re.search(r"```(?:sql)?\s*(.+?)```", s, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        s = fence_match.group(1).strip()
    # Trim a trailing semicolon (we'll re-add as needed).
    return s.rstrip(";").strip()


def validate(sql: str) -> str:
    """Validate the SQL is a single read-only SELECT touching only allowed
    tables. Returns the (possibly LIMIT-augmented) SQL. Raises SqlRejected
    on any safety violation."""
    if not sql:
        raise SqlRejected("No SQL was produced.")

    # Parse — sqlparse returns a list of statements.
    parsed = sqlparse.parse(sql)
    if len(parsed) != 1:
        raise SqlRejected("Multiple statements are not allowed.")
    stmt = parsed[0]

    stmt_type = (stmt.get_type() or "").upper()
    if stmt_type != "SELECT":
        raise SqlRejected(
            f"Only SELECT queries are allowed (got: {stmt_type or 'unknown'})."
        )

    # Word-bounded blocked tokens (case-insensitive). \b is a word
    # boundary so `created_at` won't match `create`, `updated_at` won't
    # match `update`, etc.
    lower = sql.lower()
    for bad in _BLOCKED_TOKENS_WORD:
        if re.search(rf"\b{re.escape(bad)}\b", lower):
            raise SqlRejected(f"Query contains forbidden keyword: {bad!r}.")
    # Substring-matched (paren-suffixed function calls, multi-token phrases).
    for bad in _BLOCKED_SUBSTRINGS:
        if bad in lower:
            raise SqlRejected(f"Query contains forbidden pattern: {bad!r}.")

    # Table allowlist — find any identifier that's likely a table.
    # We scan for tokens after FROM / JOIN.
    used_tables = _extract_table_names(sql)
    bad_tables = used_tables - ALLOWED_TABLES
    if bad_tables:
        raise SqlRejected(
            f"Query touches tables that are not exposed to chat: "
            f"{sorted(bad_tables)}."
        )

    # Inject LIMIT if missing.
    if not re.search(r"\blimit\s+\d", lower):
        sql = sql + f" LIMIT {_DEFAULT_LIMIT}"

    return sql


def _extract_table_names(sql: str) -> set[str]:
    """Cheap and conservative extraction of table identifiers from a SQL
    string. Picks tokens that follow FROM/JOIN keywords and ignores
    aliases, subqueries, and ON clauses."""
    names: set[str] = set()
    # FROM <table> [AS alias] ...
    # JOIN <table> [AS alias] ...
    for m in re.finditer(r"\b(?:from|join)\s+([`\"]?)([a-zA-Z_][\w]*)\1", sql, re.IGNORECASE):
        names.add(m.group(2).lower())
    return names


async def execute(db: AsyncSession, sql: str, *, max_rows: int = _DEFAULT_LIMIT) -> tuple[list[dict], int]:
    """Run the validated SQL and return (rows-as-dicts, total_returned).

    Uses MySQL's MAX_EXECUTION_TIME hint so a runaway query gets killed at
    the server side after _QUERY_TIMEOUT_S seconds — defence even if the
    asyncio timeout misbehaves."""
    # Inject MySQL hint just after the SELECT keyword.
    timed = re.sub(
        r"(?i)^\s*select\s+",
        f"SELECT /*+ MAX_EXECUTION_TIME({_QUERY_TIMEOUT_S * 1000}) */ ",
        sql,
        count=1,
    )
    result = await db.execute(text(timed))
    rows = [dict(r._mapping) for r in result.fetchall()]
    # Clip defensively in case the LIMIT was somehow bypassed (e.g. UNION).
    return rows[:max_rows], len(rows)


def safe_serialise_rows(rows: list[dict]) -> list[dict]:
    """Convert non-JSON-serialisable values (Decimal, date, datetime) into
    primitives so FastAPI can render them. We do this here so the route is
    a clean pass-through."""
    from datetime import date, datetime
    from decimal import Decimal

    def _convert(v):
        if isinstance(v, Decimal):
            return float(v)
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        return v

    return [{k: _convert(v) for k, v in row.items()} for row in rows]
