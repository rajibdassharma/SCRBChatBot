"""
Fraud Investigation Assistant — Ollama-powered AI agent.

Gathers case data from MSSQL + Neo4j, builds a comprehensive prompt,
and streams an investigation report from a local Ollama LLM.
"""

import os
import json
from decimal import Decimal

import pyodbc
import httpx
from neo4j import GraphDatabase
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

load_dotenv()

# MSSQL config (reuse from app.py pattern)
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

router = APIRouter(prefix="/investigate", tags=["Investigation"])

neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))


def _to_float(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, Decimal):
        return float(val)
    return float(val)


def _to_str(val) -> str:
    if val is None:
        return "N/A"
    return str(val).strip() or "N/A"


# ─── Data Gathering ──────────────────────────────────────────────────────────

def gather_mssql_data(ack_no: str) -> dict:
    """Gather detailed case data from all 6 NCRP tables."""
    conn = pyodbc.connect(CONN_STR)
    try:
        cur = conn.cursor()
        data = {}

        # MoneyTransferTo — detailed rows
        cur.execute(
            "SELECT AccountOrWalletId, AccountNo, Layer, BankFIs, IFSCCode, "
            "TransactionAmount, DisputedAmount, ActionTakenByBank, Remarks "
            "FROM dbo.MoneyTransferTo WHERE AcknowledgementNo = ? "
            "ORDER BY Layer, TrailID",
            (ack_no,),
        )
        cols = [c[0] for c in cur.description]
        mt_rows = [{cols[i]: r[i] for i in range(len(cols))} for r in cur.fetchall()]
        data["money_transfers"] = [
            {k: _to_float(v) if isinstance(v, (Decimal, float, int)) and k != "Layer"
             else _to_str(v) if not isinstance(v, int) else v
             for k, v in row.items()}
            for row in mt_rows
        ]

        # Summary aggregates
        cur.execute(
            "SELECT COUNT(*), ISNULL(SUM(TransactionAmount),0), ISNULL(SUM(DisputedAmount),0) "
            "FROM dbo.MoneyTransferTo WHERE AcknowledgementNo = ?",
            (ack_no,),
        )
        mt = cur.fetchone()
        data["summary"] = {
            "money_transfer_count": mt[0],
            "total_transaction_amount": round(_to_float(mt[1]), 2),
            "total_disputed_amount": round(_to_float(mt[2]), 2),
        }

        # PutOnHold — detailed rows
        cur.execute(
            "SELECT AccountOrWalletId, PutOnHoldAmount, PutOnHoldDate, "
            "ActionTakenByBank, Layer "
            "FROM dbo.PutOnHold WHERE AcknowledgementNo = ?",
            (ack_no,),
        )
        cols_ph = [c[0] for c in cur.description]
        ph_rows = [{cols_ph[i]: r[i] for i in range(len(cols_ph))} for r in cur.fetchall()]
        data["put_on_hold_details"] = [
            {k: round(_to_float(v), 2) if isinstance(v, (Decimal, float, int)) else _to_str(v)
             for k, v in row.items()}
            for row in ph_rows
        ]

        cur.execute(
            "SELECT COUNT(*), ISNULL(SUM(PutOnHoldAmount),0) "
            "FROM dbo.PutOnHold WHERE AcknowledgementNo = ?",
            (ack_no,),
        )
        ph = cur.fetchone()
        data["summary"]["put_on_hold_count"] = ph[0]
        data["summary"]["total_put_on_hold"] = round(_to_float(ph[1]), 2)

        # OtherTransactions
        cur.execute(
            "SELECT COUNT(*), ISNULL(SUM(OtherAmount),0) "
            "FROM dbo.OtherTransactions WHERE AcknowledgementNo = ?",
            (ack_no,),
        )
        ot = cur.fetchone()
        data["summary"]["other_transactions_count"] = ot[0]
        data["summary"]["total_other_amount"] = round(_to_float(ot[1]), 2)

        # ATMWithdrawal — detailed rows
        cur.execute(
            "SELECT AccountOrWalletId, WithdrawalAmount, DisputedAmount, "
            "ATMID, ATMLocation, ActionTakenByBank, Remarks "
            "FROM dbo.ATMWithdrawal WHERE AcknowledgementNo = ?",
            (ack_no,),
        )
        cols_atm = [c[0] for c in cur.description]
        atm_rows = [{cols_atm[i]: r[i] for i in range(len(cols_atm))} for r in cur.fetchall()]
        data["atm_withdrawal_details"] = [
            {k: round(_to_float(v), 2) if isinstance(v, (Decimal, float, int)) else _to_str(v)
             for k, v in row.items()}
            for row in atm_rows
        ]

        cur.execute(
            "SELECT COUNT(*), ISNULL(SUM(WithdrawalAmount),0), ISNULL(SUM(DisputedAmount),0) "
            "FROM dbo.ATMWithdrawal WHERE AcknowledgementNo = ?",
            (ack_no,),
        )
        atm = cur.fetchone()
        data["summary"]["atm_withdrawal_count"] = atm[0]
        data["summary"]["total_atm_withdrawal"] = round(_to_float(atm[1]), 2)

        # AEPS — detailed rows
        cur.execute(
            "SELECT AccountOrWalletId, WithdrawalAmount, "
            "ParentAccountNo, ParentIFSCCode, ParentLayer, "
            "ActionTakenByBank, Remarks "
            "FROM dbo.AEPS WHERE AcknowledgementNo = ?",
            (ack_no,),
        )
        cols_ae = [c[0] for c in cur.description]
        ae_rows = [{cols_ae[i]: r[i] for i in range(len(cols_ae))} for r in cur.fetchall()]
        data["aeps_details"] = [
            {k: round(_to_float(v), 2) if isinstance(v, (Decimal, float, int)) else _to_str(v)
             for k, v in row.items()}
            for row in ae_rows
        ]

        cur.execute(
            "SELECT COUNT(*), ISNULL(SUM(WithdrawalAmount),0) "
            "FROM dbo.AEPS WHERE AcknowledgementNo = ?",
            (ack_no,),
        )
        ae = cur.fetchone()
        data["summary"]["aeps_count"] = ae[0]
        data["summary"]["total_aeps_withdrawal"] = round(_to_float(ae[1]), 2)

        # OthersLessThan500
        cur.execute(
            "SELECT COUNT(*) FROM dbo.OthersLessThan500 WHERE AcknowledgementNo = ?",
            (ack_no,),
        )
        lt = cur.fetchone()
        data["summary"]["others_lt500_count"] = lt[0]

        total_rows = (mt[0] + ot[0] + ph[0] + lt[0] + ae[0] + atm[0])
        data["summary"]["total_records"] = total_rows

        # Layer-wise aggregation
        cur.execute(
            "SELECT ISNULL(Layer, 0) AS Layer, COUNT(*) AS cnt, "
            "ISNULL(SUM(TransactionAmount), 0) AS total_amt, "
            "COUNT(DISTINCT AccountNo) AS unique_accounts, "
            "COUNT(DISTINCT BankFIs) AS unique_banks "
            "FROM dbo.MoneyTransferTo WHERE AcknowledgementNo = ? "
            "GROUP BY Layer ORDER BY Layer",
            (ack_no,),
        )
        data["layer_breakdown"] = [
            {
                "layer": int(r[0]),
                "transfer_count": r[1],
                "total_amount": round(_to_float(r[2]), 2),
                "unique_accounts": r[3],
                "unique_banks": r[4],
            }
            for r in cur.fetchall()
        ]

        # Bank-wise aggregation
        cur.execute(
            "SELECT ISNULL(BankFIs, 'Unknown') AS Bank, "
            "COUNT(*) AS cnt, "
            "ISNULL(SUM(TransactionAmount), 0) AS total_amt, "
            "COUNT(DISTINCT AccountNo) AS unique_accounts "
            "FROM dbo.MoneyTransferTo WHERE AcknowledgementNo = ? "
            "GROUP BY BankFIs ORDER BY SUM(TransactionAmount) DESC",
            (ack_no,),
        )
        data["bank_breakdown"] = [
            {
                "bank": _to_str(r[0]),
                "transfer_count": r[1],
                "total_amount": round(_to_float(r[2]), 2),
                "unique_accounts": r[3],
            }
            for r in cur.fetchall()
        ]

        # Action status breakdown
        cur.execute(
            "SELECT ISNULL(ActionTakenByBank, 'No Action') AS action, "
            "COUNT(*) AS cnt, "
            "ISNULL(SUM(TransactionAmount), 0) AS total_amt "
            "FROM dbo.MoneyTransferTo WHERE AcknowledgementNo = ? "
            "GROUP BY ActionTakenByBank ORDER BY COUNT(*) DESC",
            (ack_no,),
        )
        data["action_breakdown"] = [
            {
                "action": _to_str(r[0]),
                "count": r[1],
                "total_amount": round(_to_float(r[2]), 2),
            }
            for r in cur.fetchall()
        ]

        return data
    finally:
        conn.close()


def gather_graph_data(ack_no: str) -> dict:
    """Gather graph intelligence from Neo4j."""
    graph_data = {
        "total_accounts": 0,
        "max_layer": 0,
        "multi_case_accounts": [],
        "top_accounts_by_amount": [],
    }

    try:
        with neo4j_driver.session(database=NEO4J_DATABASE) as session:
            # Basic stats
            result = session.run(
                "MATCH (p:Account)-[r:TRANSFERRED_TO]->(c:Account) "
                "WHERE r.crime_no = $ack_no "
                "RETURN count(DISTINCT p) + count(DISTINCT c) AS total_accounts, "
                "max(toInteger(c.level)) AS max_layer",
                ack_no=ack_no,
            )
            rec = result.single()
            if rec:
                graph_data["total_accounts"] = rec["total_accounts"] or 0
                graph_data["max_layer"] = rec["max_layer"] or 0

            # Multi-case accounts (involved in more than one AcknowledgementNo)
            result = session.run(
                "MATCH (a:Account)-[r:TRANSFERRED_TO]-() "
                "WHERE r.crime_no = $ack_no AND a.case_count > 1 "
                "RETURN DISTINCT a.account_no AS account_no, "
                "a.bank_name AS bank, a.case_count AS case_count, "
                "a.level AS layer "
                "ORDER BY a.case_count DESC LIMIT 20",
                ack_no=ack_no,
            )
            for rec in result:
                cc = rec["case_count"]
                if hasattr(cc, "to_int"):
                    cc = cc.to_int() if callable(getattr(cc, "to_int", None)) else int(cc)
                graph_data["multi_case_accounts"].append({
                    "account_no": rec["account_no"],
                    "bank": rec["bank"] or "N/A",
                    "case_count": int(cc) if cc else 1,
                    "layer": int(rec["layer"]) if rec["layer"] is not None else 0,
                })

            # Top accounts by transaction amount
            result = session.run(
                "MATCH (p:Account)-[r:TRANSFERRED_TO]->(c:Account) "
                "WHERE r.crime_no = $ack_no "
                "RETURN c.account_no AS account_no, c.bank_name AS bank, "
                "c.level AS layer, sum(r.amount) AS total_received "
                "ORDER BY total_received DESC LIMIT 10",
                ack_no=ack_no,
            )
            for rec in result:
                graph_data["top_accounts_by_amount"].append({
                    "account_no": rec["account_no"],
                    "bank": rec["bank"] or "N/A",
                    "layer": int(rec["layer"]) if rec["layer"] is not None else 0,
                    "total_received": round(float(rec["total_received"] or 0), 2),
                })

    except Exception as e:
        graph_data["error"] = str(e)

    return graph_data


# ─── LLM Prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior cyber fraud investigation analyst working for the Karnataka State Police, Criminal Investigation Department (CID). You analyze financial crime cases from the National Cybercrime Reporting Portal (NCRP).

Your task is to analyze the provided case data and generate a comprehensive investigation report. Be specific, cite actual account numbers, amounts, and banks from the data.

CRITICAL: ALL monetary amounts MUST be in Indian Rupees using the ₹ symbol (e.g. ₹1,50,000.00). NEVER use $, USD, or any other currency. Use Indian number formatting with commas (lakhs/crores system).

ABSOLUTE RULE — NEVER HALLUCINATE OR INVENT DATA:
- The NCRP database contains ONLY financial data: account numbers, bank names, IFSC codes, transaction amounts, layer numbers, and acknowledgement numbers.
- There are NO personal names, phone numbers, email addresses, or physical addresses in this data. Do NOT invent any.
- NEVER write placeholder text like "[Insert X]", and NEVER invent fake names like "John Doe" or "Rajesh Kumar".
- ONLY include data that is explicitly provided in the context below. If a field is not in the data, do NOT mention it at all.
- If an entire section has no data, write "No data available from NCRP records." and move on.

IMPORTANT FORMATTING RULES — you MUST follow these:
- Use markdown headers: # for main title, ## for sections, ### for subsections
- Use **bold** for important values, account numbers, and amounts
- Use markdown tables (| Header | Header |) when presenting structured data
- Use bullet points (- ) for lists
- Use > blockquotes for key findings or warnings
- Use --- horizontal rules between major sections
- Keep paragraphs concise — short and impactful

Structure your report with these sections:

## 1. EXECUTIVE SUMMARY
Brief overview with a table showing: total amount, disputed amount, accounts involved, layers depth, hold amount, recovery rate percentage.

## 2. LAYER-WISE MONEY FLOW ANALYSIS
For each layer, describe how money moved. Use a table with columns: Layer, Accounts, Banks, Amount, % of Total.

## 3. BANK-WISE ANALYSIS
Table showing which banks are most involved: Bank Name, No. of Accounts, Total Amount, Action Taken.

## 4. SUSPICIOUS ACCOUNTS & MULE IDENTIFICATION
List accounts appearing in multiple cases (mule accounts). Show: Account No, Bank, Cases Count, Layer, Amount. Flag high-risk ones with ⚠️.

## 5. HELD & RECOVERED FUNDS
Detail of put-on-hold amounts, ATM/AEPS withdrawals. Recovery analysis.

## 6. RED FLAGS & PATTERNS
Bullet-pointed list of suspicious patterns found. Be specific with evidence.

## 7. RECOMMENDATIONS
Numbered action items for investigators. Be specific — which accounts to freeze, which banks to contact, what follow-up actions.

Be thorough but focused on actionable intelligence."""


def build_prompt(ack_no: str, mssql_data: dict, graph_data: dict) -> str:
    """Build the analysis prompt with all gathered data."""
    summary = mssql_data.get("summary", {})
    transfers = mssql_data.get("money_transfers", [])
    put_on_hold = mssql_data.get("put_on_hold_details", [])
    atm_details = mssql_data.get("atm_withdrawal_details", [])
    aeps_details = mssql_data.get("aeps_details", [])
    layer_breakdown = mssql_data.get("layer_breakdown", [])
    bank_breakdown = mssql_data.get("bank_breakdown", [])
    action_breakdown = mssql_data.get("action_breakdown", [])

    # Truncate transfer details if too many (keep first 100)
    transfer_text = json.dumps(transfers[:100], indent=2, default=str)
    if len(transfers) > 100:
        transfer_text += f"\n... and {len(transfers) - 100} more transfers"

    prompt = f"""Analyze the following cyber fraud case and generate a detailed investigation report using proper markdown formatting with tables, headers, bold text, and bullet points.

**Acknowledgement Number:** {ack_no}

## CASE SUMMARY
- Total Transaction Amount: ₹{summary.get('total_transaction_amount', 0):,.2f}
- Total Disputed Amount: ₹{summary.get('total_disputed_amount', 0):,.2f}
- Total Put on Hold: ₹{summary.get('total_put_on_hold', 0):,.2f}
- Total ATM Withdrawal: ₹{summary.get('total_atm_withdrawal', 0):,.2f}
- Total AEPS Withdrawal: ₹{summary.get('total_aeps_withdrawal', 0):,.2f}
- Total Other Amount: ₹{summary.get('total_other_amount', 0):,.2f}
- Total Records: {summary.get('total_records', 0)}
- Money Transfer Records: {summary.get('money_transfer_count', 0)}
- Put on Hold Records: {summary.get('put_on_hold_count', 0)}
- ATM Withdrawal Records: {summary.get('atm_withdrawal_count', 0)}
- AEPS Records: {summary.get('aeps_count', 0)}
- Other Transaction Records: {summary.get('other_transactions_count', 0)}
- Others Less Than 500 Records: {summary.get('others_lt500_count', 0)}

## LAYER-WISE BREAKDOWN
{json.dumps(layer_breakdown, indent=2, default=str)}

## BANK-WISE BREAKDOWN
{json.dumps(bank_breakdown, indent=2, default=str)}

## BANK ACTION STATUS BREAKDOWN
{json.dumps(action_breakdown, indent=2, default=str)}

## GRAPH ANALYSIS
- Total Accounts in Money Trail: {graph_data.get('total_accounts', 0)}
- Maximum Layer Depth: {graph_data.get('max_layer', 0)}

## MULTI-CASE ACCOUNTS (accounts appearing in multiple fraud cases — likely mule accounts)
{json.dumps(graph_data.get('multi_case_accounts', []), indent=2, default=str)}

## TOP ACCOUNTS BY AMOUNT RECEIVED
{json.dumps(graph_data.get('top_accounts_by_amount', []), indent=2, default=str)}

## PUT ON HOLD DETAILS
{json.dumps(put_on_hold[:50], indent=2, default=str) if put_on_hold else "No put-on-hold records found."}

## ATM WITHDRAWAL DETAILS
{json.dumps(atm_details[:50], indent=2, default=str) if atm_details else "No ATM withdrawal records found."}

## AEPS WITHDRAWAL DETAILS
{json.dumps(aeps_details[:50], indent=2, default=str) if aeps_details else "No AEPS records found."}

## DETAILED MONEY TRANSFER TRAIL
{transfer_text}

Generate the investigation report now. Remember to use proper markdown formatting with ## headers, **bold**, tables, and bullet points."""

    return prompt


# ─── Streaming Endpoint ──────────────────────────────────────────────────────

async def _stream_investigation(ack_no: str):
    """Generator that yields SSE events."""
    # Step 1: Gather MSSQL data
    yield f"data: {json.dumps({'type': 'status', 'message': 'Gathering case data from NCRP database...'})}\n\n"
    try:
        mssql_data = gather_mssql_data(ack_no)
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Failed to query MSSQL: {e}'})}\n\n"
        return

    if mssql_data["summary"]["total_records"] == 0:
        yield f"data: {json.dumps({'type': 'error', 'message': f'No records found for Acknowledgement No: {ack_no}'})}\n\n"
        return

    # Step 2: Gather graph data
    yield f"data: {json.dumps({'type': 'status', 'message': 'Analyzing money flow graph...'})}\n\n"
    graph_data = gather_graph_data(ack_no)

    # Step 3: Build prompt
    yield f"data: {json.dumps({'type': 'status', 'message': f'AI agent analyzing case ({OLLAMA_MODEL})...'})}\n\n"
    prompt = build_prompt(ack_no, mssql_data, graph_data)

    # Step 4: Stream from Ollama
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "system": SYSTEM_PROMPT,
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
        yield f"data: {json.dumps({'type': 'error', 'message': 'Cannot connect to Ollama. Make sure Ollama is running (ollama serve).'})}\n\n"
        return
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Ollama streaming error: {e}'})}\n\n"
        return

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@router.get("/{ack_no}")
async def investigate(ack_no: str):
    """Stream an AI-generated investigation report for the given case."""
    return StreamingResponse(
        _stream_investigation(ack_no),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
