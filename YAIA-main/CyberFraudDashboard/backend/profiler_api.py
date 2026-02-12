"""
Account Profiler — Mule account detection + AI-powered deep profiling.

Phase 1: Auto-detect accounts appearing in multiple Acknowledgement Numbers.
Phase 2: Deep profile any account with Ollama-powered AI analysis.
"""

import os
import json
from decimal import Decimal

import pyodbc
import httpx
from neo4j import GraphDatabase
from dotenv import load_dotenv
from fastapi import APIRouter
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

router = APIRouter(prefix="/profiler", tags=["Profiler"])

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


# ─── Phase 1: Mule Account Detection ────────────────────────────────────────

@router.get("/mule-accounts")
def get_mule_accounts():
    """Detect accounts appearing in 2+ Acknowledgement Numbers across all tables."""
    conn = pyodbc.connect(CONN_STR)
    try:
        cur = conn.cursor()

        # Union all account appearances across all tables
        cur.execute("""
            WITH AllAccounts AS (
                SELECT AccountNo AS account_no, BankFIs AS bank,
                       AcknowledgementNo AS ack_no, TransactionAmount AS amount,
                       Layer AS layer, 'MoneyTransfer' AS source_table
                FROM dbo.MoneyTransferTo
                WHERE AccountNo IS NOT NULL

                UNION ALL

                SELECT AccountOrWalletId AS account_no, NULL AS bank,
                       AcknowledgementNo AS ack_no, PutOnHoldAmount AS amount,
                       Layer AS layer, 'PutOnHold' AS source_table
                FROM dbo.PutOnHold
                WHERE AccountOrWalletId IS NOT NULL

                UNION ALL

                SELECT AccountOrWalletId AS account_no, NULL AS bank,
                       AcknowledgementNo AS ack_no, WithdrawalAmount AS amount,
                       NULL AS layer, 'ATMWithdrawal' AS source_table
                FROM dbo.ATMWithdrawal
                WHERE AccountOrWalletId IS NOT NULL

                UNION ALL

                SELECT AccountOrWalletId AS account_no, NULL AS bank,
                       AcknowledgementNo AS ack_no, WithdrawalAmount AS amount,
                       ParentLayer AS layer, 'AEPS' AS source_table
                FROM dbo.AEPS
                WHERE AccountOrWalletId IS NOT NULL
            ),
            AccountSummary AS (
                SELECT
                    account_no,
                    COUNT(DISTINCT ack_no) AS case_count,
                    COUNT(*) AS total_appearances,
                    ISNULL(SUM(amount), 0) AS total_amount,
                    MIN(ISNULL(bank, 'N/A')) AS bank,
                    MIN(ISNULL(layer, 0)) AS min_layer,
                    MAX(ISNULL(layer, 0)) AS max_layer
                FROM AllAccounts
                GROUP BY account_no
                HAVING COUNT(DISTINCT ack_no) >= 2
            )
            SELECT
                account_no,
                case_count,
                total_appearances,
                total_amount,
                bank,
                min_layer,
                max_layer
            FROM AccountSummary
            ORDER BY case_count DESC, total_amount DESC
        """)

        cols = [c[0] for c in cur.description]
        rows = cur.fetchall()

        accounts = []
        for r in rows:
            row_dict = {cols[i]: r[i] for i in range(len(cols))}
            case_count = int(row_dict["case_count"])
            total_amount = round(_to_float(row_dict["total_amount"]), 2)

            # Risk classification
            if case_count >= 5:
                risk = "CRITICAL"
            elif case_count >= 3:
                risk = "HIGH"
            else:
                risk = "MEDIUM"

            accounts.append({
                "account_no": _to_str(row_dict["account_no"]),
                "case_count": case_count,
                "total_appearances": int(row_dict["total_appearances"]),
                "total_amount": total_amount,
                "bank": _to_str(row_dict["bank"]),
                "min_layer": int(row_dict["min_layer"]) if row_dict["min_layer"] else 0,
                "max_layer": int(row_dict["max_layer"]) if row_dict["max_layer"] else 0,
                "risk": risk,
            })

        # Summary stats
        total_mules = len(accounts)
        critical_count = sum(1 for a in accounts if a["risk"] == "CRITICAL")
        high_count = sum(1 for a in accounts if a["risk"] == "HIGH")
        medium_count = sum(1 for a in accounts if a["risk"] == "MEDIUM")
        total_amount_all = sum(a["total_amount"] for a in accounts)

        return {
            "summary": {
                "total_mule_accounts": total_mules,
                "critical": critical_count,
                "high": high_count,
                "medium": medium_count,
                "total_amount_involved": round(total_amount_all, 2),
            },
            "accounts": accounts,
        }

    finally:
        conn.close()


# ─── Phase 2: Deep Account Profile ──────────────────────────────────────────

def gather_account_data(account_no: str) -> dict:
    """Gather all data about a specific account across all NCRP tables."""
    conn = pyodbc.connect(CONN_STR)
    try:
        cur = conn.cursor()
        data = {}

        # All cases this account appears in (MoneyTransferTo)
        cur.execute(
            "SELECT AcknowledgementNo, AccountOrWalletId, Layer, BankFIs, IFSCCode, "
            "TransactionAmount, DisputedAmount, ActionTakenByBank, Remarks "
            "FROM dbo.MoneyTransferTo WHERE AccountNo = ? "
            "ORDER BY AcknowledgementNo, Layer",
            (account_no,),
        )
        cols = [c[0] for c in cur.description]
        data["money_transfers"] = [
            {cols[i]: round(_to_float(r[i]), 2) if isinstance(r[i], (Decimal, float, int))
             and cols[i] not in ("AcknowledgementNo", "Layer")
             else _to_str(r[i]) if not isinstance(r[i], (int, float)) else r[i]
             for i in range(len(cols))}
            for r in cur.fetchall()
        ]

        # Distinct cases (check both AccountNo and AccountOrWalletId across all tables)
        cur.execute("""
            SELECT DISTINCT AcknowledgementNo FROM (
                SELECT AcknowledgementNo FROM dbo.MoneyTransferTo WHERE AccountNo = ? OR AccountOrWalletId = ?
                UNION
                SELECT AcknowledgementNo FROM dbo.PutOnHold WHERE AccountOrWalletId = ?
                UNION
                SELECT AcknowledgementNo FROM dbo.ATMWithdrawal WHERE AccountOrWalletId = ?
                UNION
                SELECT AcknowledgementNo FROM dbo.AEPS WHERE AccountOrWalletId = ?
            ) AS AllCases
        """, (account_no, account_no, account_no, account_no, account_no))
        data["cases"] = [str(r[0]) for r in cur.fetchall()]

        # Case-wise amount breakdown across ALL tables
        cur.execute("""
            WITH CaseData AS (
                SELECT AcknowledgementNo AS ack_no, TransactionAmount AS amount,
                       DisputedAmount AS disputed, Layer AS layer,
                       BankFIs AS bank, ActionTakenByBank AS action,
                       'MoneyTransfer (received)' AS source
                FROM dbo.MoneyTransferTo WHERE AccountNo = ?

                UNION ALL

                SELECT AcknowledgementNo, TransactionAmount, DisputedAmount, Layer,
                       BankFIs, ActionTakenByBank,
                       'MoneyTransfer (sent)' AS source
                FROM dbo.MoneyTransferTo WHERE AccountOrWalletId = ?

                UNION ALL

                SELECT AcknowledgementNo, PutOnHoldAmount, 0, Layer,
                       NULL, ActionTakenByBank,
                       'PutOnHold' AS source
                FROM dbo.PutOnHold WHERE AccountOrWalletId = ?

                UNION ALL

                SELECT AcknowledgementNo, WithdrawalAmount, DisputedAmount, NULL,
                       NULL, ActionTakenByBank,
                       'ATMWithdrawal' AS source
                FROM dbo.ATMWithdrawal WHERE AccountOrWalletId = ?

                UNION ALL

                SELECT AcknowledgementNo, WithdrawalAmount, 0, ParentLayer,
                       NULL, ActionTakenByBank,
                       'AEPS' AS source
                FROM dbo.AEPS WHERE AccountOrWalletId = ?
            ),
            DistinctSources AS (
                SELECT DISTINCT ack_no, source FROM CaseData
            ),
            SourceAgg AS (
                SELECT ack_no, STRING_AGG(source, ', ') AS sources
                FROM DistinctSources
                GROUP BY ack_no
            )
            SELECT cd.ack_no,
                   COUNT(*) AS records,
                   ISNULL(SUM(cd.amount), 0) AS total_amount,
                   ISNULL(SUM(cd.disputed), 0) AS total_disputed,
                   MIN(ISNULL(cd.layer, 0)) AS min_layer,
                   MAX(ISNULL(cd.layer, 0)) AS max_layer,
                   MIN(cd.bank) AS bank,
                   MIN(cd.action) AS action,
                   sa.sources
            FROM CaseData cd
            LEFT JOIN SourceAgg sa ON cd.ack_no = sa.ack_no
            GROUP BY cd.ack_no, sa.sources
            ORDER BY SUM(cd.amount) DESC
        """, (account_no, account_no, account_no, account_no, account_no))
        data["case_wise_breakdown"] = [
            {
                "ack_no": str(r[0]),
                "records": r[1],
                "total_amount": round(_to_float(r[2]), 2),
                "total_disputed": round(_to_float(r[3]), 2),
                "min_layer": int(r[4]) if r[4] is not None else 0,
                "max_layer": int(r[5]) if r[5] is not None else 0,
                "bank": _to_str(r[6]),
                "action": _to_str(r[7]),
                "sources": _to_str(r[8]),
            }
            for r in cur.fetchall()
        ]

        # Summary for this account (as destination in MoneyTransferTo)
        cur.execute(
            "SELECT COUNT(*), ISNULL(SUM(TransactionAmount),0), ISNULL(SUM(DisputedAmount),0), "
            "COUNT(DISTINCT AcknowledgementNo) "
            "FROM dbo.MoneyTransferTo WHERE AccountNo = ?",
            (account_no,),
        )
        mt = cur.fetchone()
        data["summary"] = {
            "transfer_count": mt[0],
            "total_transaction_amount": round(_to_float(mt[1]), 2),
            "total_disputed_amount": round(_to_float(mt[2]), 2),
            "case_count_as_destination": mt[3],
            "case_count": len(data["cases"]),
        }

        # Check if this account also appears as a parent/source account (AccountOrWalletId)
        cur.execute(
            "SELECT COUNT(*), ISNULL(SUM(TransactionAmount),0), "
            "COUNT(DISTINCT AcknowledgementNo) "
            "FROM dbo.MoneyTransferTo WHERE AccountOrWalletId = ?",
            (account_no,),
        )
        src = cur.fetchone()
        data["as_source"] = {
            "transfer_count": src[0],
            "total_amount": round(_to_float(src[1]), 2),
            "case_count": src[2],
        }

        # PutOnHold records
        cur.execute(
            "SELECT AcknowledgementNo, PutOnHoldAmount, PutOnHoldDate, "
            "ActionTakenByBank, Layer "
            "FROM dbo.PutOnHold WHERE AccountOrWalletId = ?",
            (account_no,),
        )
        cols_ph = [c[0] for c in cur.description]
        data["put_on_hold"] = [
            {cols_ph[i]: round(_to_float(r[i]), 2) if isinstance(r[i], (Decimal, float, int))
             and cols_ph[i] not in ("AcknowledgementNo", "Layer")
             else _to_str(r[i]) for i in range(len(cols_ph))}
            for r in cur.fetchall()
        ]

        # ATM Withdrawal records
        cur.execute(
            "SELECT AcknowledgementNo, WithdrawalAmount, DisputedAmount, "
            "ATMID, ATMLocation, ActionTakenByBank, Remarks "
            "FROM dbo.ATMWithdrawal WHERE AccountOrWalletId = ?",
            (account_no,),
        )
        cols_atm = [c[0] for c in cur.description]
        data["atm_withdrawals"] = [
            {cols_atm[i]: round(_to_float(r[i]), 2) if isinstance(r[i], (Decimal, float, int))
             and cols_atm[i] != "AcknowledgementNo"
             else _to_str(r[i]) for i in range(len(cols_atm))}
            for r in cur.fetchall()
        ]

        # AEPS records
        cur.execute(
            "SELECT AcknowledgementNo, WithdrawalAmount, "
            "ParentAccountNo, ParentIFSCCode, ParentLayer, "
            "ActionTakenByBank, Remarks "
            "FROM dbo.AEPS WHERE AccountOrWalletId = ?",
            (account_no,),
        )
        cols_ae = [c[0] for c in cur.description]
        data["aeps"] = [
            {cols_ae[i]: round(_to_float(r[i]), 2) if isinstance(r[i], (Decimal, float, int))
             and cols_ae[i] != "AcknowledgementNo"
             else _to_str(r[i]) for i in range(len(cols_ae))}
            for r in cur.fetchall()
        ]

        # Bank info from MoneyTransferTo (check both AccountNo and AccountOrWalletId)
        cur.execute(
            "SELECT TOP 1 BankFIs, IFSCCode FROM dbo.MoneyTransferTo "
            "WHERE AccountNo = ? OR AccountOrWalletId = ?",
            (account_no, account_no),
        )
        bank_row = cur.fetchone()
        if bank_row:
            data["bank_info"] = {
                "bank": _to_str(bank_row[0]),
                "ifsc": _to_str(bank_row[1]),
            }
        else:
            data["bank_info"] = {"bank": "N/A", "ifsc": "N/A"}

        return data
    finally:
        conn.close()


def gather_account_graph_data(account_no: str) -> dict:
    """Gather graph intelligence about a specific account from Neo4j."""
    graph_data = {
        "connected_accounts": [],
        "connected_cases": [],
        "total_connections": 0,
    }

    try:
        with neo4j_driver.session(database=NEO4J_DATABASE) as session:
            # All connections (incoming + outgoing)
            result = session.run(
                "MATCH (a:Account {account_no: $acct})-[r:TRANSFERRED_TO]-(b:Account) "
                "RETURN b.account_no AS connected_account, b.bank_name AS bank, "
                "b.level AS layer, r.amount AS amount, r.crime_no AS case_no, "
                "CASE WHEN startNode(r) = a THEN 'OUTGOING' ELSE 'INCOMING' END AS direction "
                "ORDER BY r.amount DESC",
                acct=account_no,
            )
            for rec in result:
                graph_data["connected_accounts"].append({
                    "account_no": rec["connected_account"],
                    "bank": rec["bank"] or "N/A",
                    "layer": int(rec["layer"]) if rec["layer"] is not None else 0,
                    "amount": round(float(rec["amount"] or 0), 2),
                    "case_no": str(rec["case_no"]),
                    "direction": rec["direction"],
                })

            graph_data["total_connections"] = len(graph_data["connected_accounts"])

            # Distinct cases from graph
            result = session.run(
                "MATCH (a:Account {account_no: $acct})-[r:TRANSFERRED_TO]-() "
                "RETURN DISTINCT r.crime_no AS case_no",
                acct=account_no,
            )
            graph_data["connected_cases"] = [str(rec["case_no"]) for rec in result]

    except Exception as e:
        graph_data["error"] = str(e)

    return graph_data


PROFILE_SYSTEM_PROMPT = """You are a senior cyber fraud investigation analyst working for the Karnataka State Police, Criminal Investigation Department (CID). You specialize in profiling suspect mule accounts used in online financial fraud.

Your task is to analyze the provided account data and generate a comprehensive account profile report. Be specific — cite actual account numbers, amounts, case numbers, and banks from the data.

CRITICAL: ALL monetary amounts MUST be in Indian Rupees using the ₹ symbol (e.g. ₹1,50,000.00). NEVER use $, USD, or any other currency. Use Indian number formatting with commas (lakhs/crores system).

IMPORTANT FORMATTING RULES — you MUST follow these:
- Use markdown headers: # for main title, ## for sections, ### for subsections
- Use **bold** for important values, account numbers, and amounts
- Use markdown tables (| Header | Header |) when presenting structured data
- Use bullet points (- ) for lists
- Use > blockquotes for key findings or warnings
- Use --- horizontal rules between major sections

Structure your report with these sections:

## 1. ACCOUNT IDENTITY
Account number, bank, IFSC, layers involved. Quick summary.

## 2. CASE INVOLVEMENT ANALYSIS
How many cases this account appears in. Present a TABLE listing EVERY Acknowledgement Number with columns: Acknowledgement No, Amount (₹), Disputed (₹), Records, Layer(s), Source Tables, Bank Action. The "Source Tables" column shows which NCRP tables this account appears in for that case (e.g. MoneyTransfer, PutOnHold, ATMWithdrawal, AEPS). This table is CRITICAL — the investigator needs to see exactly how much money flowed through this account from each case. You MUST include ALL Acknowledgement Numbers from the CASE-WISE AMOUNT BREAKDOWN data. Flag if this account appears across many cases — strong indicator of a mule.

## 3. TRANSACTION SUMMARY
Total amounts sent/received across all cases. Highlight the top cases by amount.

## 4. MONEY FLOW NETWORK
Who sent money to this account and where did money go from this account. Show connected accounts in a table with: Account, Bank, Direction, Amount, Case.

## 5. RISK ASSESSMENT
Evaluate the overall risk level (CRITICAL/HIGH/MEDIUM) with evidence. Calculate a risk score and justify it based on: number of cases, total amount, layer position, connections.

## 6. BANK ACTION STATUS
What actions have banks taken on this account? Put on hold amounts, freezes, etc.

## 7. INVESTIGATIVE RECOMMENDATIONS
Specific numbered action items: freeze requests, bank communications, accounts to investigate next, evidence to preserve.

Be thorough but focused on actionable intelligence."""


def build_profile_prompt(account_no: str, account_data: dict, graph_data: dict) -> str:
    """Build the profile analysis prompt."""
    summary = account_data.get("summary", {})
    bank_info = account_data.get("bank_info", {})
    as_source = account_data.get("as_source", {})
    transfers = account_data.get("money_transfers", [])
    case_wise = account_data.get("case_wise_breakdown", [])
    put_on_hold = account_data.get("put_on_hold", [])
    atm_data = account_data.get("atm_withdrawals", [])
    aeps_data = account_data.get("aeps", [])
    cases = account_data.get("cases", [])
    connected = graph_data.get("connected_accounts", [])
    graph_cases = graph_data.get("connected_cases", [])

    prompt = f"""Analyze the following suspect account and generate a comprehensive profile report using proper markdown formatting.

**Account Number:** {account_no}
**Bank:** {bank_info.get('bank', 'N/A')}
**IFSC Code:** {bank_info.get('ifsc', 'N/A')}

## OVERVIEW
- Total cases involved: {summary.get('case_count', 0)} case(s) — {', '.join(cases) if cases else 'None'}
- Cases from graph: {len(graph_cases)} case(s) — {', '.join(graph_cases) if graph_cases else 'None'}
- As destination (AccountNo): {summary.get('transfer_count', 0)} transfers, ₹{summary.get('total_transaction_amount', 0):,.2f} received
- As source (AccountOrWalletId): {as_source.get('transfer_count', 0)} transfers, ₹{as_source.get('total_amount', 0):,.2f} sent
- Total disputed amount: ₹{summary.get('total_disputed_amount', 0):,.2f}

## CASE-WISE AMOUNT BREAKDOWN (amount received per Acknowledgement Number)
{json.dumps(case_wise, indent=2, default=str) if case_wise else "No case-wise data."}

## MONEY TRANSFER DETAILS (as destination — AccountNo)
{json.dumps(transfers[:80], indent=2, default=str) if transfers else "No transfer records found."}

## CONNECTED ACCOUNTS (from Neo4j graph)
Total connections: {graph_data.get('total_connections', 0)}
{json.dumps(connected[:50], indent=2, default=str) if connected else "No graph connections found."}

## PUT ON HOLD RECORDS
{json.dumps(put_on_hold, indent=2, default=str) if put_on_hold else "No put-on-hold records."}

## ATM WITHDRAWAL RECORDS
{json.dumps(atm_data, indent=2, default=str) if atm_data else "No ATM withdrawal records."}

## AEPS RECORDS
{json.dumps(aeps_data, indent=2, default=str) if aeps_data else "No AEPS records."}

Generate the account profile report now. Remember to use proper markdown formatting with ## headers, **bold**, tables, and bullet points."""

    return prompt


async def _stream_profile(account_no: str):
    """Generator that yields SSE events for account profiling."""
    # Step 1: Gather account data from MSSQL
    yield f"data: {json.dumps({'type': 'status', 'message': 'Gathering account data from NCRP database...'})}\n\n"
    try:
        account_data = gather_account_data(account_no)
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Failed to query MSSQL: {e}'})}\n\n"
        return

    total = (account_data["summary"]["transfer_count"]
             + account_data["as_source"]["transfer_count"]
             + len(account_data["put_on_hold"])
             + len(account_data["atm_withdrawals"])
             + len(account_data["aeps"]))

    if total == 0:
        yield f"data: {json.dumps({'type': 'error', 'message': f'No records found for account: {account_no}'})}\n\n"
        return

    # Step 2: Gather graph data
    yield f"data: {json.dumps({'type': 'status', 'message': 'Analyzing account connections in graph...'})}\n\n"
    graph_data = gather_account_graph_data(account_no)

    # Step 3: Build prompt & stream from Ollama
    yield f"data: {json.dumps({'type': 'status', 'message': f'AI agent profiling account ({OLLAMA_MODEL})...'})}\n\n"
    prompt = build_profile_prompt(account_no, account_data, graph_data)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "system": PROFILE_SYSTEM_PROMPT,
                    "stream": True,
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


@router.get("/account/{account_no}")
async def profile_account(account_no: str):
    """Stream an AI-generated profile report for the given account."""
    return StreamingResponse(
        _stream_profile(account_no),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
