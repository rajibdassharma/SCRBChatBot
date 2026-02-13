"""
Multi-Source Intelligence Agent — natural language query interface.

Investigators type questions in plain English. The AI:
1. Generates SQL (MSSQL) and/or Cypher (Neo4j) queries
2. Validates and executes them safely
3. Synthesizes a streamed intelligence report
"""

import os
import re
import json
from decimal import Decimal
from datetime import datetime, date

import pyodbc
import httpx
from neo4j import GraphDatabase
from dotenv import load_dotenv
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

load_dotenv()

# MSSQL config
MSSQL_SERVER = os.getenv("MSSQL_SERVER", "localhost")
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE", "NCRP")
MSSQL_DRIVER = os.getenv("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server")
CONN_STR = (
    f"Driver={{{MSSQL_DRIVER}}};"
    f"Server={MSSQL_SERVER};"
    f"Database={MSSQL_DATABASE};"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

# Neo4j config
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "sandy411")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# Ollama config
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

router = APIRouter(prefix="/intelligence", tags=["Intelligence"])

neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _to_float(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, Decimal):
        return float(val)
    return float(val)


def _json_serial(obj):
    """JSON serializer for types not handled by default."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


# ─── Phase 1: Query Generation ────────────────────────────────────────────────

QUERY_GENERATION_SYSTEM_PROMPT = """You are a database query generation agent for the Karnataka State Police, Criminal Investigation Department (CID). You help fraud investigators query the NCRP (National Cybercrime Reporting Portal) database.

You have access to TWO databases:

## DATABASE 1: MSSQL (NCRP relational database)

### Table: dbo.MoneyTransferTo (core money trail table)
- TrailID (bigint, PK, auto-increment)
- AcknowledgementNo (bigint) — the case/complaint number
- AccountOrWalletId (varchar(100)) — the PARENT/SOURCE account that sent money
- TransactionUTR (varchar(100)) — unique transaction reference
- BankFIs (nvarchar(200)) — bank name of the child account
- Layer (int) — 0 = victim account, 1+ = mule layers
- AccountNo (varchar(50)) — the CHILD/DESTINATION account that received money
- IFSCCode (varchar(20))
- TransactionDate (datetime2)
- TransactionAmount (decimal(18,2)) — amount in Indian Rupees
- DisputedAmount (decimal(18,2)) — disputed amount in Indian Rupees
- Remarks (nvarchar(2000))
- ActionTakenByBank (nvarchar(500))
- DateOfAction (datetime2)

KEY: AccountOrWalletId is the PARENT (source), AccountNo is the CHILD (destination) at the given Layer.

### Table: dbo.PutOnHold (frozen/held funds)
- TrailID (bigint, PK)
- AcknowledgementNo (bigint)
- AccountOrWalletId (varchar(100))
- PutOnHoldDate (datetime2)
- PutOnHoldAmount (decimal(18,2))
- ActionTakenByBank (nvarchar(500))
- Layer (int)

### Table: dbo.ATMWithdrawal
- TrailID (bigint, PK)
- AcknowledgementNo (bigint)
- AccountOrWalletId (varchar(100))
- WithdrawalDateTime (datetime2)
- WithdrawalAmount (decimal(18,2))
- DisputedAmount (decimal(18,2))
- ATMID (varchar(50))
- ATMLocation (nvarchar(300))
- ActionTakenByBank (nvarchar(500))

### Table: dbo.AEPS (Aadhaar Enabled Payment System withdrawals)
- TrailID (bigint, PK)
- AcknowledgementNo (bigint)
- AccountOrWalletId (varchar(100))
- WithdrawalDate (datetime2)
- WithdrawalAmount (decimal(18,2))
- ParentAccountNo (varchar(50))
- ParentLayer (int)
- ActionTakenByBank (nvarchar(500))

### Table: dbo.OtherTransactions
- TrailID (bigint, PK)
- AcknowledgementNo (bigint)
- AccountOrWalletId (varchar(100))
- OtherDate (datetime2)
- OtherAmount (decimal(18,2))
- ActionTakenByBank (nvarchar(500))

### Table: dbo.OthersLessThan500
- TrailID (bigint, PK)
- AcknowledgementNo (bigint)
- AccountOrWalletId (varchar(100))
- ActionTakenByBank (nvarchar(500))

## DATABASE 2: Neo4j (graph database for money flow network)

### Node: :Account
- account_no (String, UNIQUE) — the account number
- level (Int) — layer in money trail (0=victim, 1+=mule)
- crime_no (String) — AcknowledgementNo
- account_type (String) — "victim" or "child"
- bank_name (String)
- bank_ifsc (String)
- amount (Float) — transaction amount in ₹
- case_count (Int) — number of distinct cases this account appears in
- source (String) — "NCRP_MoneyTransferTo"

### Relationship: [:TRANSFERRED_TO]
- transfer_id (Int) — TrailID
- crime_no (String) — AcknowledgementNo
- amount (Float) — ₹ transferred
- child_level (Int) — layer of destination account
- transaction_date (String)

Pattern: (parent:Account)-[:TRANSFERRED_TO]->(child:Account)

## YOUR TASK

Given a natural language question, generate the appropriate database queries.

RULES:
1. Decide data source: "sql", "cypher", or "both"
2. Use SQL for: statistics, aggregations, bank analysis, amount calculations, hold/recovery analysis
3. Use Cypher for: network/graph questions (connections, paths, clusters), multi-case detection
4. Use BOTH for: questions requiring relational aggregates AND network analysis
5. SQL must use MSSQL T-SQL syntax. Prefix tables with dbo.
6. NEVER generate INSERT, UPDATE, DELETE, DROP, ALTER, EXEC, TRUNCATE, CREATE, or MERGE
7. SQL must be SELECT only. Cypher must use MATCH/RETURN/WITH/OPTIONAL MATCH only.
8. Use ISNULL() for nullable amounts in SQL
9. Use TOP (N) with parentheses in SQL if query could return many rows, e.g. SELECT TOP (500)
10. When searching by account, check BOTH AccountOrWalletId AND AccountNo in MoneyTransferTo
11. CRITICAL: ALWAYS use short table aliases in ALL queries with JOINs or subqueries. Qualify EVERY column with its alias. Examples:
    - FROM dbo.MoneyTransferTo mt JOIN dbo.PutOnHold ph ON mt.AcknowledgementNo = ph.AcknowledgementNo
    - SELECT mt.AcknowledgementNo, mt.BankFIs, ph.PutOnHoldAmount
    - NEVER write bare column names like "AcknowledgementNo" in multi-table queries — ALWAYS use "mt.AcknowledgementNo"
    Alias conventions: mt=MoneyTransferTo, ph=PutOnHold, atm=ATMWithdrawal, ae=AEPS, ot=OtherTransactions, ol=OthersLessThan500

Return ONLY a JSON object inside a ```json code fence:
```json
{
  "data_source": "sql",
  "sql_query": "SELECT ...",
  "cypher_query": null,
  "explanation": "Brief explanation"
}
```"""


def parse_query_json(llm_response: str) -> dict:
    """Extract JSON block from LLM response."""
    # Try code-fenced JSON
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', llm_response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try raw JSON with data_source key
    match = re.search(r'\{[^{}]*"data_source"[^}]*\}', llm_response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Try any JSON object
    match = re.search(r'\{[\s\S]*\}', llm_response)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return {}


# ─── Phase 2: Query Validation ────────────────────────────────────────────────

SQL_FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "EXEC", "EXECUTE",
    "TRUNCATE", "CREATE", "MERGE", "GRANT", "REVOKE", "DENY",
    "OPENROWSET", "OPENDATASOURCE", "BULK", "SHUTDOWN", "BACKUP", "RESTORE",
]


def validate_sql(query: str) -> tuple[bool, str]:
    """Validate SQL is safe (SELECT only). Returns (is_valid, error_or_query)."""
    if not query or not query.strip():
        return False, "Empty SQL query"

    normalized = query.strip().upper()

    # Must start with SELECT or WITH (for CTEs)
    if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
        return False, "SQL must start with SELECT or WITH"

    # Check for forbidden keywords
    for kw in SQL_FORBIDDEN_KEYWORDS:
        pattern = r'\b' + kw + r'\b'
        if re.search(pattern, normalized):
            return False, f"Forbidden keyword: {kw}"

    # No semicolons (prevent query stacking)
    query = query.strip().rstrip(';').strip()
    if ';' in query:
        return False, "Multiple statements not allowed"

    return True, query


CYPHER_ALLOWED_STARTS = ["MATCH", "OPTIONAL", "WITH", "UNWIND", "CALL"]
CYPHER_FORBIDDEN_KEYWORDS = [
    "CREATE", "DELETE", "DETACH", "MERGE", "SET ", "REMOVE",
    "DROP", "LOAD CSV", "FOREACH",
]


def validate_cypher(query: str) -> tuple[bool, str]:
    """Validate Cypher is read-only. Returns (is_valid, error_or_query)."""
    if not query or not query.strip():
        return False, "Empty Cypher query"

    normalized = query.strip().upper()

    first_word = normalized.split()[0] if normalized.split() else ""
    if first_word not in CYPHER_ALLOWED_STARTS:
        return False, f"Cypher must start with MATCH/OPTIONAL/WITH, got: {first_word}"

    if "RETURN" not in normalized:
        return False, "Cypher must contain RETURN"

    for kw in CYPHER_FORBIDDEN_KEYWORDS:
        pattern = r'\b' + kw.strip() + r'\b'
        if re.search(pattern, normalized):
            return False, f"Forbidden keyword: {kw.strip()}"

    if "LIMIT" not in normalized:
        query = query.rstrip().rstrip(';') + " LIMIT 500"

    return True, query


# ─── Phase 2: Query Execution ─────────────────────────────────────────────────

def _run_sql(query: str, max_rows: int = 500) -> dict:
    """Execute a single SQL query and return results dict."""
    conn = pyodbc.connect(CONN_STR, timeout=30)
    try:
        conn.timeout = 30
        cur = conn.cursor()
        cur.execute(query)
        columns = [c[0] for c in cur.description] if cur.description else []
        rows = []
        for row in cur.fetchmany(max_rows):
            row_dict = {}
            for i, col in enumerate(columns):
                val = row[i]
                if isinstance(val, Decimal):
                    val = float(val)
                elif isinstance(val, (datetime, date)):
                    val = val.isoformat()
                elif val is not None and not isinstance(val, (int, float)):
                    val = str(val)
                row_dict[col] = val
            rows.append(row_dict)
        return {"columns": columns, "rows": rows, "row_count": len(rows)}
    finally:
        conn.close()


def _fix_ambiguous_columns(query: str, error_msg: str) -> str | None:
    """Try to fix 'Ambiguous column name' by qualifying bare columns with first table alias."""
    match = re.search(r"Ambiguous column name '(\w+)'", error_msg)
    if not match:
        return None
    col_name = match.group(1)

    # Find first table + alias in FROM clause:  FROM dbo.Table alias  /  FROM dbo.Table AS alias
    table_match = re.search(
        r'\bFROM\s+(?:dbo\.)?(\w+)(?:\s+(?:AS\s+)?(\w+))?',
        query, re.IGNORECASE
    )
    if not table_match:
        return None

    table_name = table_match.group(1)
    alias = table_match.group(2) or table_name

    # Don't pick up SQL keywords as aliases
    reserved = {'INNER', 'LEFT', 'RIGHT', 'OUTER', 'CROSS', 'JOIN', 'ON',
                'WHERE', 'GROUP', 'ORDER', 'HAVING', 'WITH', 'SET', 'AS'}
    if alias.upper() in reserved:
        alias = table_name

    # Qualify every bare reference: col_name that is NOT preceded by a dot/word char
    fixed = re.sub(
        r'(?<![.\w])(' + re.escape(col_name) + r')(?!\w)',
        f'{alias}.\\1',
        query
    )
    return fixed if fixed != query else None


def execute_sql(query: str, max_rows: int = 500) -> dict:
    """Execute SQL with automatic retry on common syntax errors."""
    try:
        return _run_sql(query, max_rows)
    except Exception as first_err:
        error_str = str(first_err)

        # Fix: Ambiguous column name → qualify with first table alias
        if "Ambiguous column name" in error_str:
            fixed = _fix_ambiguous_columns(query, error_str)
            if fixed:
                try:
                    return _run_sql(fixed, max_rows)
                except Exception as second_err:
                    # If still ambiguous (different column), try fixing again
                    if "Ambiguous column name" in str(second_err):
                        fixed2 = _fix_ambiguous_columns(fixed, str(second_err))
                        if fixed2:
                            try:
                                return _run_sql(fixed2, max_rows)
                            except Exception:
                                pass

        # Fix: TOP N without parentheses → TOP (N)
        fixed = re.sub(r'\bTOP\s+(\d+)\b', r'TOP (\1)', query, flags=re.IGNORECASE)
        if fixed != query:
            try:
                return _run_sql(fixed, max_rows)
            except Exception:
                pass

        # Fix: Remove TOP entirely (fetchmany already caps rows)
        stripped = re.sub(r'\bTOP\s*\(?\s*\d+\s*\)?\s*', '', query, flags=re.IGNORECASE)
        if stripped != query:
            try:
                return _run_sql(stripped, max_rows)
            except Exception:
                pass

        # All retries failed — raise the original error
        raise first_err


def execute_cypher(query: str) -> dict:
    """Execute validated Cypher against Neo4j."""
    records = []
    keys = []
    try:
        with neo4j_driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(query)
            keys = list(result.keys())
            for record in result:
                rec_dict = {}
                for key in keys:
                    val = record[key]
                    if hasattr(val, '__int__') and not isinstance(val, (int, float, str, bool)):
                        val = int(val)
                    elif isinstance(val, float):
                        val = round(val, 2)
                    rec_dict[key] = val
                records.append(rec_dict)
    except Exception as e:
        return {"columns": keys, "records": [], "record_count": 0, "error": str(e)}

    return {"columns": keys, "records": records, "record_count": len(records)}


# ─── Phase 3: Answer Synthesis ─────────────────────────────────────────────────

SYNTHESIS_SYSTEM_PROMPT = """You are a senior intelligence analyst for the Karnataka State Police CID.

YOUR ONLY JOB: Read the QUERY RESULTS DATA below and present it as a clear, formatted intelligence report that answers the investigator's question.

ABSOLUTE RULES — VIOLATION MEANS FAILURE:
1. ONLY use data from the QUERY RESULTS sections below. Every number, name, and fact you write MUST come from the provided data.
2. NEVER invent, fabricate, or hallucinate any data, numbers, bank names, account numbers, or statistics.
3. NEVER change or rephrase the investigator's question. Answer EXACTLY what was asked.
4. If the query returned an error, report the error and suggest the investigator rephrase the question.
5. If the query returned 0 rows, say "No data found" — do NOT make up alternative answers.
6. ALL monetary amounts: use ₹ with Indian number formatting (e.g. ₹12,50,000).

FORMAT:
- Start with ## followed by a title that matches the question
- Use markdown tables (| Col | Col |) to present the data rows
- Use **bold** for important values
- End with ## Key Insights — 2-3 bullet points summarizing the findings
- Use > blockquotes for critical alerts

If accounts appear in multiple cases, flag them as potential mule accounts."""


def build_synthesis_prompt(
    question: str,
    queries: dict,
    sql_results: dict | None,
    cypher_results: dict | None,
) -> str:
    """Build synthesis prompt with question + queries + results."""
    parts = [f"## INVESTIGATOR'S QUESTION\n{question}\n"]

    if queries.get("sql_query"):
        parts.append(f"## SQL QUERY\n```sql\n{queries['sql_query']}\n```\n")
    if queries.get("cypher_query"):
        parts.append(f"## CYPHER QUERY\n```cypher\n{queries['cypher_query']}\n```\n")
    if queries.get("explanation"):
        parts.append(f"## QUERY EXPLANATION\n{queries['explanation']}\n")

    if sql_results:
        if sql_results.get("error"):
            parts.append(f"## SQL RESULTS\nError: {sql_results['error']}\n")
        elif sql_results.get("row_count", 0) == 0:
            parts.append("## SQL RESULTS\nNo rows returned.\n")
        else:
            rows_to_show = sql_results["rows"][:200]
            parts.append(
                f"## SQL RESULTS ({sql_results['row_count']} rows)\n"
                f"Columns: {', '.join(sql_results.get('columns', []))}\n"
                f"```json\n{json.dumps(rows_to_show, indent=2, default=_json_serial)}\n```\n"
            )
            if sql_results["row_count"] > 200:
                parts.append(f"... and {sql_results['row_count'] - 200} more rows\n")

    if cypher_results:
        if cypher_results.get("error"):
            parts.append(f"## CYPHER RESULTS\nError: {cypher_results['error']}\n")
        elif cypher_results.get("record_count", 0) == 0:
            parts.append("## CYPHER RESULTS\nNo records returned.\n")
        else:
            recs_to_show = cypher_results["records"][:200]
            parts.append(
                f"## CYPHER RESULTS ({cypher_results['record_count']} records)\n"
                f"```json\n{json.dumps(recs_to_show, indent=2, default=_json_serial)}\n```\n"
            )

    parts.append(
        "---\n"
        f"REMINDER: The investigator asked: \"{question}\"\n"
        "Answer THIS EXACT question using ONLY the data shown above. "
        "Present the data in a markdown table. Use ₹ for amounts. "
        "Do NOT invent any data. Do NOT answer a different question. "
        "If no data was returned, say 'No data found for this query.'"
    )
    return "\n".join(parts)


# ─── SSE Streaming Pipeline ───────────────────────────────────────────────────

async def _stream_intelligence(question: str):
    """Generator that yields SSE events for the intelligence query pipeline."""

    # Phase 1: Query Generation
    yield f"data: {json.dumps({'type': 'status', 'message': 'Understanding your question...'})}\n\n"

    queries = {}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            yield f"data: {json.dumps({'type': 'status', 'message': 'Generating database queries...'})}\n\n"
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": f"Generate database queries for this question:\n\n{question}",
                    "system": QUERY_GENERATION_SYSTEM_PROMPT,
                    "stream": False,
                    "options": {"temperature": 0, "top_p": 0.9},
                },
            )
            if resp.status_code == 200:
                llm_text = resp.json().get("response", "")
                queries = parse_query_json(llm_text)
    except httpx.ConnectError:
        yield f"data: {json.dumps({'type': 'error', 'message': 'Cannot connect to Ollama. Make sure Ollama is running (ollama serve).'})}\n\n"
        return
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Query generation failed: {e}'})}\n\n"
        return

    if not queries or "data_source" not in queries:
        yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to generate valid queries. Please rephrase your question.'})}\n\n"
        return

    data_source = queries.get("data_source", "sql")
    sql_query = queries.get("sql_query")
    cypher_query = queries.get("cypher_query")

    # Phase 2: Validate and Execute
    sql_results = None
    cypher_results = None

    if sql_query and data_source in ("sql", "both"):
        is_valid, result = validate_sql(sql_query)
        if not is_valid:
            yield f"data: {json.dumps({'type': 'status', 'message': f'SQL validation issue: {result}. Skipping SQL.'})}\n\n"
            sql_query = None
        else:
            sql_query = result
            yield f"data: {json.dumps({'type': 'status', 'message': 'Executing SQL query...'})}\n\n"
            try:
                sql_results = execute_sql(sql_query)
            except Exception as e:
                error_msg = str(e)
                # Strip all [Driver][Server] bracket prefixes from pyodbc errors
                cleaned = re.sub(r'\[.*?\]', '', error_msg).strip()
                if cleaned:
                    error_msg = cleaned
                sql_results = {"columns": [], "rows": [], "row_count": 0, "error": error_msg}

    if cypher_query and data_source in ("cypher", "both"):
        is_valid, result = validate_cypher(cypher_query)
        if not is_valid:
            yield f"data: {json.dumps({'type': 'status', 'message': f'Cypher validation issue: {result}. Skipping graph query.'})}\n\n"
            cypher_query = None
        else:
            cypher_query = result
            yield f"data: {json.dumps({'type': 'status', 'message': 'Executing graph query...'})}\n\n"
            try:
                cypher_results = execute_cypher(cypher_query)
            except Exception as e:
                cypher_results = {"columns": [], "records": [], "record_count": 0, "error": str(e)}

    # Emit queries event AFTER validation (shows actual executed queries)
    queries_payload = {}
    if sql_query:
        queries_payload["sql"] = sql_query
    if cypher_query:
        queries_payload["cypher"] = cypher_query
    if queries.get("explanation"):
        queries_payload["explanation"] = queries["explanation"]
    yield f"data: {json.dumps({'type': 'queries', 'data': queries_payload})}\n\n"

    # Phase 3: Synthesis
    yield f"data: {json.dumps({'type': 'status', 'message': f'Synthesizing intelligence report ({OLLAMA_MODEL})...'})}\n\n"
    prompt = build_synthesis_prompt(question, queries, sql_results, cypher_results)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "system": SYNTHESIS_SYSTEM_PROMPT,
                    "stream": True,
                    "options": {"temperature": 0, "top_p": 0.9},
                },
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    yield f"data: {json.dumps({'type': 'error', 'message': f'Ollama error ({response.status_code}): {body.decode()}'})}\n\n"
                    return

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("response", "")
                        if token:
                            token = token.replace("$", "₹")
                            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue

    except httpx.ConnectError:
        yield f"data: {json.dumps({'type': 'error', 'message': 'Cannot connect to Ollama.'})}\n\n"
        return
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Report generation failed: {e}'})}\n\n"
        return

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@router.post("/query")
async def intelligence_query(request: Request):
    """Stream an AI-generated intelligence report for a natural language question."""
    body = await request.json()
    question = body.get("question", "").strip()
    if not question:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': 'No question provided.'})}\n\n"]),
            media_type="text/event-stream",
        )
    return StreamingResponse(
        _stream_intelligence(question),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
