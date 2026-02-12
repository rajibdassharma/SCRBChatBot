# backend/graph_qa.py
import json
import re
from typing import Any, Dict, Tuple, Set

from ollama_client import ollama_chat
from config import GRAPH_MODEL
from neo4j_client import run_cypher

# -----------------------------
# Safety: allow ONLY read-only Cypher
# -----------------------------
BLOCKLIST = [
    r"\bCREATE\b", r"\bMERGE\b", r"\bDELETE\b", r"\bDETACH\b", r"\bSET\b",
    r"\bDROP\b", r"\bCALL\b", r"\bLOAD\s+CSV\b", r"\bAPOC\b",
    r"\bFOREACH\b", r"\bREMOVE\b", r"\bALTER\b"
]

def validate_readonly_cypher(cypher: str) -> Tuple[bool, str]:
    if not cypher or not cypher.strip():
        return False, "Empty Cypher"

    c = cypher.strip()

    # must start with MATCH/WITH/RETURN
    if not re.match(r"^\s*(MATCH|WITH|RETURN)\b", c, re.IGNORECASE):
        return False, "Cypher must start with MATCH/WITH/RETURN"

    for pat in BLOCKLIST:
        if re.search(pat, c, re.IGNORECASE):
            return False, f"Blocked keyword detected: {pat}"

    # enforce limit if not present (safe)
    if re.search(r"\bLIMIT\b", c, re.IGNORECASE) is None:
        c += "\nLIMIT 50"

    return True, c


# -----------------------------
# Graph intent + fallback helpers
# -----------------------------
_GRAPH_INTENT_RE = re.compile(
    r"\b(graph|visual|visualize|visualisation|visualization|network|money\s+flow|funds?\s+flow|flow\s+of\s+money|money\s+trail)\b",
    re.IGNORECASE,
)

def wants_graph(question: str) -> bool:
    return bool(question and _GRAPH_INTENT_RE.search(question))

def looks_graph_return(cypher: str) -> bool:
    if not cypher:
        return False
    if re.search(r"\bRETURN\b\s+\w+\s*,\s*\w+\s*,\s*\w+", cypher, re.IGNORECASE):
        return True
    if re.search(r"\bRETURN\b\s+\w+\s*,\s*\w+", cypher, re.IGNORECASE) and "TRANSFERRED_TO" in cypher:
        return True
    return False


# -----------------------------
# Generic param handling
# -----------------------------
_PARAM_RE = re.compile(r"(?<!\$)\$([A-Za-z_][A-Za-z0-9_]*)")

def find_cypher_params(cypher: str) -> Set[str]:
    """
    Return set of parameter names referenced in cypher ($param).
    """
    if not cypher:
        return set()
    return set(m.group(1) for m in _PARAM_RE.finditer(cypher))

def missing_params(params: Dict[str, Any], required: Set[str]) -> Set[str]:
    """
    Params are considered missing if:
    - key not present OR value is None OR empty string
    """
    missing = set()
    params = params or {}
    for k in required:
        if k not in params or params[k] is None:
            missing.add(k)
        elif isinstance(params[k], str) and not params[k].strip():
            missing.add(k)
    return missing


# -----------------------------
# Schema hints for the LLM
# -----------------------------
GRAPH_SCHEMA_HINT = """
You are generating Cypher for a Neo4j fraud investigation graph.

Node:
(:Account)
Key properties:
- account_no (string)
- name (string)
- role (victim/accused)
- account_type (victim/child)
- level (int) 0..N
- crime_no (string)
- victim_id (int)
- unit_id (int)
- bank_name (string)
- color (string like "#ffd400") optional
Other personal details may exist (address/mobile/kyc etc).

Relationship:
(:Account)-[:TRANSFERRED_TO]->(:Account)
Key relationship properties:
- amount (number)
- flow_date (datetime/string)
- crime_no (string)
- victim_id (int)
- unit_id (int)

IMPORTANT:
- Use READ ONLY Cypher only.
- Prefer parameters ($param) when user provides values.
- If user asks for a graph visualization, also provide a graph-friendly query that returns nodes and relationships.
"""

def llm_to_cypher(question: str) -> Tuple[str, Dict[str, Any]]:
    """
    LLM must output strict JSON:
    {
      "cypher": "...",
      "params": {...},
      "intent": "...",
      "graph_cypher": "..."   // optional
    }
    """
    prompt = (
        "You are a Cypher generator for an investigation graph.\n"
        "Return ONLY valid JSON. No markdown. No prose.\n\n"
        "Output format EXACTLY one JSON object with these keys:\n"
        "{\"cypher\":\"...\",\"params\":{...},\"intent\":\"...\",\"graph_cypher\":\"...\"}\n\n"
        "RULES:\n"
        "- READ ONLY queries. Use MATCH/WHERE/RETURN.\n"
        "- Do NOT use CREATE/MERGE/DELETE/SET/CALL/APOC.\n"
        "- Use parameters whenever possible (e.g., $account_no, $crime_no).\n"
        "- If question asks for a TABLE/summary, cypher can return columns.\n"
        "- If question asks for a GRAPH/visualization, set graph_cypher to a query returning nodes + relationships.\n"
        "- Treat requests mentioning 'money flow', 'funds flow', or 'money trail' as GRAPH/visualization requests.\n"
        "- graph_cypher should usually RETURN p,r,c (or RETURN a,r,b) so Neovis can draw.\n"
        "- Always add LIMIT 50 (or LIMIT 500 for big graph).\n\n"
        f"{GRAPH_SCHEMA_HINT}\n\n"
        f"QUESTION:\n{question}\n"
    )

    raw = ollama_chat(
        [
            {"role": "system", "content": "You output STRICT JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        model=GRAPH_MODEL
    )

    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise ValueError("JSON is not an object")
        return raw, obj
    except Exception:
        # fallback: treat raw as cypher (no params)
        return raw, {"cypher": raw, "params": {}, "intent": "unknown", "graph_cypher": ""}


def graph_ask(question: str, param_overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Generic Graph Q&A:
    - LLM generates cypher + params (+ optional graph_cypher)
    - We validate read-only
    - We validate parameters *generically* (no crime_no logic)
    - If missing params -> return missing list (UI can ask user)
    - If ok -> run cypher and summarize
    """
    cypher_raw, obj = llm_to_cypher(question)

    cypher = (obj.get("cypher") or "").strip()
    params = obj.get("params") or {}
    intent = (obj.get("intent") or "").strip()
    graph_cypher_raw = (obj.get("graph_cypher") or "").strip()

    # allow UI to supply/override params (generic)
    if param_overrides:
        try:
            params.update(param_overrides)
        except Exception:
            pass
    # validate cypher
    ok, cypher_clean_or_reason = validate_readonly_cypher(cypher)
    if not ok:
        return {
            "ok": False,
            "error": f"Unsafe/invalid cypher: {cypher_clean_or_reason}",
            "cypher_raw": cypher_raw,
        }
    cypher_clean = cypher_clean_or_reason

    # validate graph_cypher if present
    graph_cypher = ""
    if graph_cypher_raw:
        okg, graph_clean_or_reason = validate_readonly_cypher(graph_cypher_raw)
        if okg:
            graph_cypher = graph_clean_or_reason
        else:
            # don't fail the whole request; just ignore bad visualization query
            graph_cypher = ""
    # Fallback: if question implies graph but graph_cypher is missing, reuse main cypher if graph-shaped
    if not graph_cypher and wants_graph(question):
        if looks_graph_return(cypher_clean):
            graph_cypher = cypher_clean

    # ---- Generic required param detection ----
    required_main = find_cypher_params(cypher_clean)
    required_graph = find_cypher_params(graph_cypher) if graph_cypher else set()
    required_all = required_main.union(required_graph)

    miss = missing_params(params, required_all)
    if miss:
        # Don’t even hit Neo4j; tell UI what’s needed
        return {
            "ok": False,
            "error": "Missing required parameters for query.",
            "missing_params": sorted(list(miss)),
            "cypher": cypher_clean,
            "graph_cypher": graph_cypher,
            "params": params,
            "intent": intent
        }

    # ---- Run main query ----
    try:
        data = run_cypher(cypher_clean, params=params)
    except Exception as e:
        # if Neo4j still complains, bubble up
        return {
            "ok": False,
            "error": "Neo4j query failed",
            "detail": str(e),
            "cypher": cypher_clean,
            "graph_cypher": graph_cypher,
            "params": params,
            "intent": intent
        }

    # ---- Summarize for investigators ----
    answer = ollama_chat(
        [
            {"role": "system", "content": "You are an investigation analyst. Summarize results clearly and briefly. Use Indian Rupees (INR, ₹) for all currency amounts."},
            {"role": "user", "content": f"QUESTION: {question}\nCYPHER: {cypher_clean}\nPARAMS: {params}\nRESULT: {data}"},
        ],
        temperature=0.0,
        model=GRAPH_MODEL
    )

    return {
        "ok": True,
        "answer": answer,
        "cypher": cypher_clean,
        "params": params,
        "intent": intent,
        "data": data,
        "graph_cypher": graph_cypher
    }



