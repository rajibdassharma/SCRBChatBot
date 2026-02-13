"""
Complaint Triage Agent — classifies complaints, extracts entities,
cross-references NCRP DB + Neo4j, assigns priority, streams triage report.
"""

import os
import re
import json
from decimal import Decimal

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

router = APIRouter(prefix="/triage", tags=["Triage"])

neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))


def _to_float(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, Decimal):
        return float(val)
    return float(val)


def _to_str(val) -> str:
    if val is None:
        return ""
    return str(val).strip()


# ─── Entity Extraction ────────────────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """You are an entity extraction agent for the Karnataka State Police Cyber Crime Division. You analyze raw complaint text from Indian cybercrime victims.

Your ONLY task is to extract structured entities from the complaint text. Return a SINGLE JSON object inside a ```json code fence.

CRITICAL RULES:
1. Extract ONLY what is explicitly stated in the complaint. NEVER invent data.
2. Account numbers may be 10-18 digits, sometimes with spaces or dashes. Clean them to digits only.
3. UPI IDs follow the pattern: username@bankhandle (e.g. name@ybl, name@paytm, name@oksbi)
4. IFSC codes are 11 characters: 4 letters + 0 + 6 alphanumeric (e.g. SBIN0001234)
5. Amounts should be raw numbers. Convert "1.5 lakh" to 150000, "2 crore" to 20000000, "50K" to 50000.
6. Indian phone numbers are 10 digits, sometimes prefixed with +91 or 0.
7. If something is not mentioned, use an empty array [] or null. NEVER guess.

FRAUD TYPE must be one of:
- online_purchase_scam
- investment_scam
- crypto_scam
- stock_trading_scam
- job_scam
- loan_fraud
- phishing
- vishing
- smishing
- sim_swap
- account_takeover
- matrimonial_fraud
- sextortion
- impersonation
- lottery_scam
- tech_support_scam
- other

Return ONLY this JSON structure inside a ```json code fence:
```json
{
  "fraud_type": "<type from list above>",
  "fraud_subtype": "<more specific description if possible, else null>",
  "confidence": <0.0 to 1.0>,
  "accounts": ["<account numbers found, digits only>"],
  "bank_names": ["<bank names mentioned>"],
  "upi_ids": ["<UPI IDs found>"],
  "ifsc_codes": ["<IFSC codes found>"],
  "amounts": [<numeric amounts in rupees>],
  "total_loss_estimate": <total amount lost as number, or null>,
  "payment_methods": ["UPI", "NEFT", "IMPS", "RTGS", "card", "cash", etc.],
  "phone_numbers": ["<phone numbers of suspects, 10 digits>"],
  "urls_apps": ["<URLs or app names mentioned>"],
  "timeline_summary": "<1-2 sentence summary of when events occurred>"
}
```"""


def parse_extraction_json(llm_response: str) -> dict:
    """Extract JSON block from LLM response with fallbacks."""
    # Try code-fenced JSON
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', llm_response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try raw JSON with fraud_type key
    match = re.search(r'\{[^{}]*"fraud_type"[^}]*\}', llm_response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Try to find any JSON object
    match = re.search(r'\{[\s\S]*\}', llm_response)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return {}


# ─── Cross-Reference MSSQL ────────────────────────────────────────────────────

def cross_reference_accounts(identifiers: list[str]) -> dict:
    """Check extracted accounts/UPI IDs against all NCRP tables."""
    if not identifiers:
        return {"matches": [], "total_matched_accounts": 0, "total_cases": 0}

    conn = pyodbc.connect(CONN_STR)
    try:
        cur = conn.cursor()
        matches = []

        for ident in identifiers:
            ident = ident.strip()
            if not ident:
                continue

            # MoneyTransferTo — both AccountNo and AccountOrWalletId
            cur.execute("""
                SELECT AcknowledgementNo,
                       ISNULL(SUM(TransactionAmount), 0) AS total_amount,
                       COUNT(*) AS appearances,
                       MIN(BankFIs) AS bank,
                       MIN(ISNULL(Layer, 0)) AS min_layer,
                       MAX(ISNULL(Layer, 0)) AS max_layer
                FROM dbo.MoneyTransferTo
                WHERE AccountNo = ? OR AccountOrWalletId = ?
                GROUP BY AcknowledgementNo
            """, (ident, ident))

            cases = []
            for r in cur.fetchall():
                cases.append({
                    "ack_no": _to_str(r[0]),
                    "total_amount": round(_to_float(r[1]), 2),
                    "appearances": r[2],
                    "bank": _to_str(r[3]),
                    "layers": f"L{r[4]}-L{r[5]}" if r[4] != r[5] else f"L{r[4]}",
                })

            # Other tables — count distinct cases
            cur.execute("""
                SELECT COUNT(DISTINCT AcknowledgementNo) FROM (
                    SELECT AcknowledgementNo FROM dbo.PutOnHold WHERE AccountOrWalletId = ?
                    UNION
                    SELECT AcknowledgementNo FROM dbo.ATMWithdrawal WHERE AccountOrWalletId = ?
                    UNION
                    SELECT AcknowledgementNo FROM dbo.AEPS WHERE AccountOrWalletId = ?
                ) AS x
            """, (ident, ident, ident))
            other_count = cur.fetchone()[0]

            if cases or other_count > 0:
                matches.append({
                    "identifier": ident,
                    "money_transfer_cases": cases,
                    "other_table_cases": other_count,
                    "total_case_count": len(cases) + other_count,
                })

        return {
            "matches": matches,
            "total_matched_accounts": len(matches),
            "total_cases": sum(m["total_case_count"] for m in matches),
        }
    finally:
        conn.close()


# ─── Cross-Reference Neo4j ────────────────────────────────────────────────────

def cross_reference_graph(identifiers: list[str]) -> dict:
    """Check extracted accounts in Neo4j for mule indicators."""
    graph_hits = []
    try:
        with neo4j_driver.session(database=NEO4J_DATABASE) as session:
            for ident in identifiers:
                ident = ident.strip()
                if not ident:
                    continue
                result = session.run(
                    "MATCH (a:Account {account_no: $acct}) "
                    "OPTIONAL MATCH (a)-[r:TRANSFERRED_TO]-() "
                    "RETURN a.case_count AS case_count, "
                    "       a.bank_name AS bank, "
                    "       a.level AS layer, "
                    "       count(r) AS connections",
                    acct=ident,
                )
                rec = result.single()
                if rec and rec["case_count"] is not None:
                    cc = rec["case_count"]
                    if hasattr(cc, "__int__"):
                        cc = int(cc)
                    graph_hits.append({
                        "account_no": ident,
                        "case_count": int(cc),
                        "bank": rec["bank"] or "N/A",
                        "layer": int(rec["layer"]) if rec["layer"] is not None else None,
                        "connections": int(rec["connections"]),
                        "is_mule": int(cc) >= 2,
                    })
    except Exception as e:
        return {"hits": graph_hits, "mule_count": 0, "error": str(e)}

    return {
        "hits": graph_hits,
        "mule_count": sum(1 for h in graph_hits if h["is_mule"]),
    }


# ─── Priority Scoring ─────────────────────────────────────────────────────────

HIGH_SEVERITY_TYPES = {
    "investment_scam", "crypto_scam", "stock_trading_scam",
    "loan_fraud", "sim_swap", "account_takeover", "sextortion",
}
MEDIUM_SEVERITY_TYPES = {
    "online_purchase_scam", "job_scam", "matrimonial_fraud",
    "phishing", "vishing", "smishing", "impersonation",
}


def compute_priority(extracted: dict, mssql_xref: dict, graph_xref: dict) -> dict:
    """Compute triage priority score (0-100)."""
    score = 0
    reasons = []

    # Factor 1: Amount (max 30 pts)
    amounts = extracted.get("amounts") or []
    total_loss = extracted.get("total_loss_estimate")
    if total_loss and isinstance(total_loss, (int, float)):
        total_amount = total_loss
    else:
        total_amount = sum(a for a in amounts if isinstance(a, (int, float)))

    if total_amount >= 10_00_000:
        score += 30
        reasons.append(f"High loss amount: ₹{total_amount:,.0f}")
    elif total_amount >= 1_00_000:
        score += 20
        reasons.append(f"Significant loss: ₹{total_amount:,.0f}")
    elif total_amount >= 10_000:
        score += 10
        reasons.append(f"Moderate loss: ₹{total_amount:,.0f}")
    elif total_amount > 0:
        score += 3
        reasons.append(f"Small loss: ₹{total_amount:,.0f}")

    # Factor 2: Fraud type severity (max 25 pts)
    fraud_type = (extracted.get("fraud_type") or "").lower()
    if fraud_type in HIGH_SEVERITY_TYPES:
        score += 25
        reasons.append(f"High-severity fraud: {fraud_type.replace('_', ' ')}")
    elif fraud_type in MEDIUM_SEVERITY_TYPES:
        score += 15
        reasons.append(f"Medium-severity fraud: {fraud_type.replace('_', ' ')}")
    else:
        score += 5
        reasons.append(f"Fraud type: {fraud_type.replace('_', ' ') or 'unclassified'}")

    # Factor 3: Accounts in existing cases (max 25 pts)
    matched = mssql_xref.get("total_matched_accounts", 0)
    linked_cases = mssql_xref.get("total_cases", 0)
    if matched > 0:
        pts = min(25, matched * 8 + linked_cases * 2)
        score += pts
        reasons.append(f"{matched} account(s) in {linked_cases} existing case(s)")

    # Factor 4: Mule indicators from Neo4j (max 20 pts)
    mule_count = graph_xref.get("mule_count", 0)
    if mule_count > 0:
        pts = min(20, mule_count * 10)
        score += pts
        reasons.append(f"{mule_count} mule account(s) detected (multi-case)")

    score = min(score, 100)

    if score >= 75:
        priority = "CRITICAL"
    elif score >= 50:
        priority = "HIGH"
    elif score >= 25:
        priority = "MEDIUM"
    else:
        priority = "LOW"

    return {
        "score": score,
        "priority": priority,
        "reasons": reasons,
        "amount_mentioned": total_amount,
        "accounts_in_db": matched,
        "mule_indicators": mule_count,
    }


# ─── Triage Report LLM Prompt ─────────────────────────────────────────────────

TRIAGE_SYSTEM_PROMPT = """You are a senior complaint triage officer for the Karnataka State Police, Criminal Investigation Department (CID), Cyber Crime Division.

Your task is to generate a structured triage report for an incoming cybercrime complaint. You have been provided with:
1. The original complaint text
2. Entities extracted from the complaint
3. Cross-reference results from the NCRP financial database
4. Graph database intelligence (mule account indicators)
5. A computed priority score

CRITICAL RULES:
- ALL monetary amounts in Indian Rupees: ₹ symbol with Indian number formatting (lakhs/crores)
- NEVER hallucinate or invent data not provided in the context
- If the complaint mentions names/phones, you may reference them. If not in the data, do NOT invent them.
- Focus on ACTIONABLE intelligence for the investigating officer

IMPORTANT FORMATTING RULES:
- Use markdown headers: ## for sections
- Use **bold** for important values, account numbers, and amounts
- Use markdown tables for structured data
- Use bullet points for lists
- Use > blockquotes for key findings or alerts

Structure your report with these sections:

## 1. COMPLAINT CLASSIFICATION
Fraud type, confidence level, brief modus operandi description.

## 2. EXTRACTED ENTITIES
Table: Entity Type | Value | Notes

## 3. DATABASE CROSS-REFERENCE
For each account found in NCRP: Account No, Cases, Amount, Layers, Bank.
If NO matches: state clearly these accounts are new to the system.

## 4. MULE ACCOUNT ALERTS
Flag any accounts appearing in multiple cases. Highlight the risk.

## 5. PRIORITY ASSESSMENT
Show priority breakdown with factors and scores. State final priority in bold.

## 6. RECOMMENDED ACTIONS
Numbered list of specific next steps:
- Which accounts to freeze immediately
- Which banks to contact
- Whether to link to existing cases
- Evidence preservation steps
- Escalation recommendations

Be thorough but concise. Every sentence should serve the investigator."""


def build_triage_prompt(
    complaint_text: str,
    extracted: dict,
    mssql_xref: dict,
    graph_xref: dict,
    priority: dict,
) -> str:
    """Build the triage analysis prompt."""
    prompt = f"""Analyze the following cybercrime complaint and generate a triage report.

## ORIGINAL COMPLAINT TEXT
{complaint_text}

## EXTRACTED ENTITIES
{json.dumps(extracted, indent=2, default=str)}

## NCRP DATABASE CROSS-REFERENCE RESULTS
{json.dumps(mssql_xref, indent=2, default=str)}

## GRAPH DATABASE INTELLIGENCE (Mule Indicators)
{json.dumps(graph_xref, indent=2, default=str)}

## COMPUTED PRIORITY
Priority: {priority['priority']} (Score: {priority['score']}/100)
Reasons:
{chr(10).join('- ' + r for r in priority['reasons'])}

Generate the triage report now. Use proper markdown formatting with ## headers, tables, **bold**, and bullet points.
CRITICAL: Use ₹ for all amounts. Do NOT invent data not present above."""
    return prompt


# ─── SSE Streaming: Paste & Triage ────────────────────────────────────────────

async def _stream_triage(complaint_text: str):
    """Generator that yields SSE events for complaint triage."""

    # Phase 1: Entity extraction via Ollama (non-streaming)
    yield f"data: {json.dumps({'type': 'status', 'message': 'Extracting entities from complaint...'})}\n\n"

    extracted = {}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": f"Extract entities from this complaint:\n\n{complaint_text}",
                    "system": EXTRACTION_SYSTEM_PROMPT,
                    "stream": False,
                    "options": {"temperature": 0, "top_p": 0.9},
                },
            )
            if resp.status_code == 200:
                llm_text = resp.json().get("response", "")
                extracted = parse_extraction_json(llm_text)
    except httpx.ConnectError:
        yield f"data: {json.dumps({'type': 'error', 'message': 'Cannot connect to Ollama. Make sure Ollama is running (ollama serve).'})}\n\n"
        return
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Entity extraction failed: {e}'})}\n\n"
        return

    if not extracted:
        yield f"data: {json.dumps({'type': 'status', 'message': 'Warning: Could not parse entities. Proceeding with raw analysis...'})}\n\n"
        extracted = {"fraud_type": "other", "accounts": [], "bank_names": [],
                     "upi_ids": [], "amounts": [], "payment_methods": []}

    # Combine accounts and UPI IDs for cross-referencing
    all_identifiers = list(set(
        [a.strip() for a in (extracted.get("accounts") or []) if a.strip()] +
        [u.strip() for u in (extracted.get("upi_ids") or []) if u.strip()]
    ))

    # Phase 2: Cross-reference MSSQL
    yield f"data: {json.dumps({'type': 'status', 'message': f'Cross-referencing {len(all_identifiers)} identifier(s) with NCRP database...'})}\n\n"
    try:
        mssql_xref = cross_reference_accounts(all_identifiers)
    except Exception as e:
        mssql_xref = {"matches": [], "total_matched_accounts": 0, "total_cases": 0, "error": str(e)}

    # Phase 3: Cross-reference Neo4j
    yield f"data: {json.dumps({'type': 'status', 'message': 'Checking graph database for mule indicators...'})}\n\n"
    graph_xref = cross_reference_graph(all_identifiers)

    # Phase 4: Compute priority
    yield f"data: {json.dumps({'type': 'status', 'message': 'Computing priority score...'})}\n\n"
    priority = compute_priority(extracted, mssql_xref, graph_xref)

    # Emit structured entities event (frontend renders this as cards)
    entities_payload = {
        "extracted": extracted,
        "mssql_xref": mssql_xref,
        "graph_xref": graph_xref,
        "priority": priority,
    }
    yield f"data: {json.dumps({'type': 'entities', 'data': entities_payload})}\n\n"

    # Phase 5: Stream triage report from Ollama
    yield f"data: {json.dumps({'type': 'status', 'message': f'AI agent generating triage report ({OLLAMA_MODEL})...'})}\n\n"
    prompt = build_triage_prompt(complaint_text, extracted, mssql_xref, graph_xref, priority)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "system": TRIAGE_SYSTEM_PROMPT,
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
        yield f"data: {json.dumps({'type': 'error', 'message': 'Cannot connect to Ollama. Make sure Ollama is running.'})}\n\n"
        return
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Triage report generation failed: {e}'})}\n\n"
        return

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@router.post("/analyze")
async def analyze_complaint(request: Request):
    """Triage a complaint: extract entities, cross-reference, score, report."""
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': 'No complaint text provided.'})}\n\n"]),
            media_type="text/event-stream",
        )
    return StreamingResponse(
        _stream_triage(text),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Batch Case Priority Dashboard ────────────────────────────────────────────

def _batch_priority_score(total_amount: float, max_layer: int,
                          mule_count: int, recovery_pct: float) -> tuple[int, str]:
    """Compute auto-priority for a case in batch mode."""
    score = 0

    # Amount factor (max 30)
    if total_amount >= 10_00_000:
        score += 30
    elif total_amount >= 1_00_000:
        score += 20
    elif total_amount >= 10_000:
        score += 10

    # Complexity / depth (max 25)
    if max_layer >= 4:
        score += 25
    elif max_layer >= 2:
        score += 15
    elif max_layer >= 1:
        score += 5

    # Mule indicators (max 25)
    if mule_count >= 3:
        score += 25
    elif mule_count >= 1:
        score += 15

    # Recovery gap (max 20) — low recovery = higher priority
    if recovery_pct < 10:
        score += 20
    elif recovery_pct < 30:
        score += 12
    elif recovery_pct < 50:
        score += 5

    score = min(score, 100)

    if score >= 75:
        priority = "CRITICAL"
    elif score >= 50:
        priority = "HIGH"
    elif score >= 25:
        priority = "MEDIUM"
    else:
        priority = "LOW"

    return score, priority


@router.get("/cases")
def list_cases():
    """Return aggregated triage metrics for all cases in the DB."""
    conn = pyodbc.connect(CONN_STR)
    try:
        cur = conn.cursor()
        cur.execute("""
            WITH CaseSummary AS (
                SELECT
                    mt.AcknowledgementNo,
                    COUNT(DISTINCT mt.AccountNo) AS unique_accounts,
                    COUNT(*) AS total_records,
                    ISNULL(SUM(mt.TransactionAmount), 0) AS total_amount,
                    ISNULL(SUM(mt.DisputedAmount), 0) AS disputed_amount,
                    MAX(ISNULL(mt.Layer, 0)) AS max_layer,
                    COUNT(DISTINCT mt.BankFIs) AS unique_banks
                FROM dbo.MoneyTransferTo mt
                GROUP BY mt.AcknowledgementNo
            ),
            HoldSummary AS (
                SELECT
                    AcknowledgementNo,
                    ISNULL(SUM(PutOnHoldAmount), 0) AS held_amount,
                    COUNT(*) AS hold_records
                FROM dbo.PutOnHold
                GROUP BY AcknowledgementNo
            ),
            ActionSummary AS (
                SELECT
                    AcknowledgementNo,
                    SUM(CASE WHEN ActionTakenByBank IS NOT NULL
                             AND ActionTakenByBank <> ''
                        THEN 1 ELSE 0 END) AS actions_taken,
                    COUNT(*) AS total_trails
                FROM dbo.MoneyTransferTo
                GROUP BY AcknowledgementNo
            )
            SELECT
                cs.AcknowledgementNo,
                cs.unique_accounts,
                cs.total_records,
                cs.total_amount,
                cs.disputed_amount,
                ISNULL(hs.held_amount, 0) AS held_amount,
                cs.max_layer,
                cs.unique_banks,
                ISNULL(hs.hold_records, 0) AS hold_records,
                ISNULL(acts.actions_taken, 0) AS actions_taken,
                ISNULL(acts.total_trails, 0) AS total_trails
            FROM CaseSummary cs
            LEFT JOIN HoldSummary hs ON cs.AcknowledgementNo = hs.AcknowledgementNo
            LEFT JOIN ActionSummary acts ON cs.AcknowledgementNo = acts.AcknowledgementNo
            ORDER BY cs.total_amount DESC
        """)

        cols = [c[0] for c in cur.description]
        rows = cur.fetchall()

        # Collect all account numbers for batch mule check
        all_ack_nos = [_to_str(r[0]) for r in rows]

        # Batch mule count from Neo4j
        mule_map: dict[str, int] = {}
        try:
            with neo4j_driver.session(database=NEO4J_DATABASE) as session:
                result = session.run(
                    "MATCH (a:Account) WHERE a.case_count > 1 "
                    "UNWIND a.crime_no AS cn "
                    "RETURN cn AS ack_no, count(DISTINCT a.account_no) AS mule_count"
                )
                for rec in result:
                    mule_map[str(rec["ack_no"])] = int(rec["mule_count"])
        except Exception:
            pass  # Graph unavailable — proceed without mule data

        cases = []
        for r in rows:
            ack_no = _to_str(r[0])
            total_amount = round(_to_float(r[3]), 2)
            disputed = round(_to_float(r[4]), 2)
            held = round(_to_float(r[5]), 2)
            max_layer = int(r[6]) if r[6] is not None else 0
            actions_taken = int(r[9]) if r[9] else 0
            total_trails = int(r[10]) if r[10] else 0

            recovery_pct = round((held / total_amount * 100), 1) if total_amount > 0 else 0
            action_pct = round((actions_taken / total_trails * 100), 1) if total_trails > 0 else 0
            mule_count = mule_map.get(ack_no, 0)

            auto_score, auto_priority = _batch_priority_score(
                total_amount, max_layer, mule_count, recovery_pct
            )

            cases.append({
                "ack_no": ack_no,
                "unique_accounts": int(r[1]),
                "total_records": int(r[2]),
                "total_amount": total_amount,
                "disputed_amount": disputed,
                "held_amount": held,
                "max_layer": max_layer,
                "unique_banks": int(r[7]),
                "hold_records": int(r[8]),
                "recovery_pct": recovery_pct,
                "action_pct": action_pct,
                "mule_account_count": mule_count,
                "auto_score": auto_score,
                "auto_priority": auto_priority,
            })

        # Sort by auto_score descending
        cases.sort(key=lambda c: c["auto_score"], reverse=True)

        return {
            "total_cases": len(cases),
            "cases": cases,
        }
    finally:
        conn.close()
