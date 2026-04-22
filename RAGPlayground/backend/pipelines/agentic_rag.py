"""
AgenticRAG Pipeline — AI Agent with tools for multi-step investigation Q&A.

The agent does NOT index documents — it reads from StructuredRAG's existing
MySQL tables and ChromaDB data. Select StructuredRAG to index, then switch
to AgenticRAG for intelligent multi-step Q&A.

Supports two query patterns:
  1. Individual questions — about a specific accused person
  2. Case-wide questions — about all accused in a case (uses chargesheet accused list)

Tools available to the agent:
  - list_cases: List all indexed cases
  - list_accused: Get accused names from docs in a case
  - get_accused_list: Get all accused/suspects/absconders from chargesheet
  - get_ir_fields: Get table fields for an accused's IR
  - get_statement: Get narrative/statement text for an accused
  - get_chargesheet: Get chargesheet content for a case
  - get_brief_description: Get the case brief description from chargesheet
  - search_text: Semantic search within a case or across all docs
"""

import json
import re
from typing import Dict, Any, List, Optional

from pipelines.base import BasePipeline
from shared.ollama_client import ollama_chat, ollama_embed_batch
from shared.structured_tables import (
    get_ir_fields, get_ir_statement, find_ir_docs_by_name,
    find_ir_docs_by_case, get_all_case_names, execute_sql_query,
    get_chargesheet, get_chargesheet_persons, get_chargesheet_fields,
)
from shared.mysql_db import get_conn

# Import StructuredRAG's ChromaDB for search
import chromadb
import os
from config import CHROMA_PATH


# ── Tool implementations ─────────────────────────────────────────────

def _tool_list_cases() -> str:
    cases = get_all_case_names()
    if not cases:
        return "No cases found. Index documents with StructuredRAG first."
    return f"Found {len(cases)} cases:\n" + "\n".join(f"- {c}" for c in cases)


def _tool_list_accused(case_name: str) -> str:
    docs = find_ir_docs_by_case(case_name)
    if not docs:
        # Try partial match
        all_cases = get_all_case_names()
        matches = [c for c in all_cases if case_name.lower() in c.lower()]
        if matches:
            docs = find_ir_docs_by_case(matches[0])
            case_name = matches[0]
    if not docs:
        return f"No documents found for case '{case_name}'."

    result = f"Case: {case_name}\nDocuments ({len(docs)}):\n"
    for d in docs:
        # Extract a clean name from the filename for the agent to use
        fname = d['doc_name'].split('/')[-1]  # Remove path prefix
        fname_clean = fname.rsplit('.', 1)[0]  # Remove extension
        result += f"- {fname_clean} (full: {d['doc_name']}, doc_id: {d['doc_id'][:12]}...)\n"
    result += "\nTIP: When searching for an accused, use the main name from the document name above (e.g., 'Abdul karim' from 'Abdul karim @ Chota Karim')."
    return result


def _find_docs_flexible(name: str) -> list:
    """Flexible document search — tries AND match, then individual words, then single longest word."""
    words = [w for w in name.split() if len(w) > 1]
    if not words:
        return []

    # Try 1: AND match (all words)
    docs = find_ir_docs_by_name(words)
    if docs:
        return docs

    # Try 2: Each word individually, score by matches
    conn = get_conn()
    cur = conn.cursor()
    # OR match with scoring
    or_conditions = ["doc_name LIKE %s" for _ in words]
    params = [f"%{w}%" for w in words]
    sql = (
        f"SELECT DISTINCT doc_id, doc_name, case_name, "
        f"({' + '.join(['(doc_name LIKE %s)' for _ in words])}) as score "
        f"FROM ir_reports "
        f"WHERE {' OR '.join(or_conditions)} "
        f"ORDER BY score DESC, doc_name"
    )
    all_params = params + params  # once for score, once for WHERE
    try:
        cur.execute(sql, tuple(all_params))
        docs = cur.fetchall()
    except Exception:
        docs = []
    cur.close()
    conn.close()

    if docs:
        print(f"[AgenticRAG] Flexible search for '{name}': found {len(docs)} docs (OR match)")
        return docs

    return []


def _tool_get_ir_fields(accused_name: str) -> str:
    docs = _find_docs_flexible(accused_name)
    if not docs:
        return f"No IR document found for '{accused_name}'. Try using the exact name from the document list."

    # Use first match
    doc = docs[0]
    fields = get_ir_fields(doc["doc_id"])
    if not fields:
        return f"Document '{doc['doc_name']}' has no extracted fields."

    result = f"IR Fields for {doc['doc_name']} ({len(fields)} fields):\n\n"
    for f in fields:
        if f.get("field_value"):
            val = f["field_value"]
            if len(val) > 200:
                val = val[:200] + "..."
            result += f"[{f['serial_no']}] {f['field_key']}: {val}\n"
    return result


def _tool_get_statement(accused_name: str) -> str:
    docs = _find_docs_flexible(accused_name)
    if not docs:
        return f"No IR document found for '{accused_name}'. Try using the exact name from the document list."

    doc = docs[0]
    statement = get_ir_statement(doc["doc_id"])
    if not statement:
        return f"No statement/narrative found for '{doc['doc_name']}'."

    if len(statement) > 6000:
        return f"Statement for {doc['doc_name']} ({len(statement)} chars):\n\n{statement[:6000]}\n\n... [truncated]"
    return f"Statement for {doc['doc_name']} ({len(statement)} chars):\n\n{statement}"


def _tool_get_chargesheet(case_name: str) -> str:
    """Get chargesheet summary including header fields."""
    # Try chargesheet table first (new structured storage)
    cs = get_chargesheet(_resolve_case_name(case_name))
    if cs:
        result = f"Chargesheet: {cs['doc_name']}\nCase: {cs['case_name']}\n\n"

        # Header fields
        fields = get_chargesheet_fields(cs["case_name"])
        if fields:
            result += "Header Fields:\n"
            for f in fields:
                result += f"  {f['field_key']}: {f['field_value'][:200]}\n"

        # Accused summary
        if cs.get("accused_details"):
            text = cs["accused_details"][:4000]
            result += f"\nAccused Details ({len(cs['accused_details'])} chars):\n{text}"
            if len(cs["accused_details"]) > 4000:
                result += "\n... [truncated]"

        return result

    # Fallback: look for chargesheet in IR docs
    docs = find_ir_docs_by_case(_resolve_case_name(case_name))
    if not docs:
        return f"No documents found for case '{case_name}'."

    chargesheet_doc = None
    for d in docs:
        name_lower = d["doc_name"].lower()
        if "charge" in name_lower or "chargesheet" in name_lower:
            chargesheet_doc = d
            break

    if not chargesheet_doc:
        return f"No chargesheet found in case '{case_name}'."

    statement = get_ir_statement(chargesheet_doc["doc_id"])
    fields = get_ir_fields(chargesheet_doc["doc_id"])

    result = f"Chargesheet: {chargesheet_doc['doc_name']}\n\n"
    if fields:
        result += "Fields:\n"
        for f in fields:
            if f.get("field_value"):
                result += f"  {f['field_key']}: {f['field_value'][:200]}\n"
    if statement:
        text = statement[:6000] if len(statement) > 6000 else statement
        result += f"\nContent ({len(statement)} chars):\n{text}"
        if len(statement) > 6000:
            result += "\n... [truncated]"

    return result


def _tool_get_accused_list(case_name: str) -> str:
    """Get all accused, suspects, and absconders from the chargesheet for a case."""
    resolved = _resolve_case_name(case_name)
    persons = get_chargesheet_persons(resolved)

    if not persons:
        return f"No accused list found in chargesheet for case '{case_name}'. Make sure the chargesheet has been indexed."

    accused = [p for p in persons if p["person_type"] == "accused"]
    suspects = [p for p in persons if p["person_type"] == "suspect"]
    absconders = [p for p in persons if p["person_type"] == "absconder"]

    result = f"Chargesheet persons for case '{resolved}':\n\n"

    if accused:
        result += f"ACCUSED ({len(accused)}):\n"
        for p in accused:
            sno = f"[{p['serial_no']}] " if p.get("serial_no") else ""
            details = f" — {p['details']}" if p.get("details") else ""
            result += f"  {sno}{p['person_name']}{details}\n"
        result += "\n"

    if suspects:
        result += f"SUSPECTS ({len(suspects)}):\n"
        for p in suspects:
            details = f" — {p['details']}" if p.get("details") else ""
            result += f"  {p['person_name']}{details}\n"
        result += "\n"

    if absconders:
        result += f"ABSCONDERS ({len(absconders)}):\n"
        for p in absconders:
            details = f" — {p['details']}" if p.get("details") else ""
            result += f"  {p['person_name']}{details}\n"
        result += "\n"

    result += (
        f"Total: {len(accused)} accused, {len(suspects)} suspects, {len(absconders)} absconders\n\n"
        "TIP: Use get_ir_fields(accused_name) to get detailed table fields for any accused person, "
        "or get_statement(accused_name) to get their statement."
    )
    return result


def _tool_get_brief_description(case_name: str) -> str:
    """Get the brief description of the case from the chargesheet."""
    resolved = _resolve_case_name(case_name)
    cs = get_chargesheet(resolved)

    if not cs:
        return f"No chargesheet found for case '{case_name}'."

    brief = cs.get("brief_description", "")
    if not brief:
        return f"No brief description found in chargesheet for case '{case_name}'."

    if len(brief) > 8000:
        return f"Brief Description ({len(brief)} chars):\n\n{brief[:8000]}\n\n... [truncated]"
    return f"Brief Description ({len(brief)} chars):\n\n{brief}"


def _resolve_case_name(case_name: str) -> str:
    """Resolve a case name with partial matching."""
    all_cases = get_all_case_names()
    if case_name in all_cases:
        return case_name
    matches = [c for c in all_cases if case_name.lower() in c.lower()]
    return matches[0] if matches else case_name


def _tool_search_text(query: str, case_name: str = None) -> str:
    """Semantic search in ChromaDB."""
    try:
        client = chromadb.PersistentClient(path=os.path.join(CHROMA_PATH, "structured"))
        col = client.get_or_create_collection(name="structured_rag")

        if col.count() == 0:
            return "No documents indexed."

        query_embedding = ollama_embed_batch([query])[0]
        where_filter = {"case_name": case_name} if case_name else None
        results = col.query(query_embeddings=[query_embedding], n_results=5, where=where_filter)

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        if not docs:
            return f"No results found for '{query}'."

        result = f"Search results for '{query}':\n\n"
        for i, (doc_text, meta) in enumerate(zip(docs, metas), 1):
            doc_name = meta.get("doc_name", "Unknown")
            chunk_type = meta.get("chunk_type", "chunk")
            text = doc_text[:300] if len(doc_text) > 300 else doc_text
            result += f"{i}. [{doc_name} | {chunk_type}]\n{text}\n\n"

        return result
    except Exception as e:
        return f"Search failed: {e}"


# ── Tool registry ────────────────────────────────────────────────────

TOOLS = {
    "list_cases": {
        "description": "List all indexed case names",
        "params": "none",
        "function": lambda args: _tool_list_cases(),
    },
    "list_accused": {
        "description": "List all documents/accused persons in a specific case (from IR docs)",
        "params": "case_name (string)",
        "function": lambda args: _tool_list_accused(args.get("case_name", "")),
    },
    "get_accused_list": {
        "description": "Get all accused, suspects, and absconders from the chargesheet for a case. Use this FIRST for case-wide questions.",
        "params": "case_name (string)",
        "function": lambda args: _tool_get_accused_list(args.get("case_name", "")),
    },
    "get_ir_fields": {
        "description": "Get all structured table fields from an accused person's IR document",
        "params": "accused_name (string)",
        "function": lambda args: _tool_get_ir_fields(args.get("accused_name", "")),
    },
    "get_statement": {
        "description": "Get the narrative/statement text from an accused person's IR document",
        "params": "accused_name (string)",
        "function": lambda args: _tool_get_statement(args.get("accused_name", "")),
    },
    "get_chargesheet": {
        "description": "Get the chargesheet header fields and accused details for a case",
        "params": "case_name (string)",
        "function": lambda args: _tool_get_chargesheet(args.get("case_name", "")),
    },
    "get_brief_description": {
        "description": "Get the brief description of the case from the chargesheet",
        "params": "case_name (string)",
        "function": lambda args: _tool_get_brief_description(args.get("case_name", "")),
    },
    "search_text": {
        "description": "Semantic search across all indexed documents, optionally filtered by case",
        "params": "query (string), case_name (string, optional)",
        "function": lambda args: _tool_search_text(args.get("query", ""), args.get("case_name")),
    },
}


def _build_tools_description() -> str:
    lines = []
    for name, tool in TOOLS.items():
        lines.append(f"- {name}({tool['params']}): {tool['description']}")
    return "\n".join(lines)


# ── Agent logic ──────────────────────────────────────────────────────

AGENT_SYSTEM_PROMPT = f"""You are an AI investigation agent for Karnataka State Police. You help officers find information about accused persons, cases, and connections.

You have access to these tools:
{_build_tools_description()}

To use a tool, respond with this format:
{{"tool": "tool_name", "args": {{"param": "value"}}}}

Examples:
{{"tool": "list_cases", "args": {{}}}}
{{"tool": "get_accused_list", "args": {{"case_name": "Bengaluru Blast Case"}}}}
{{"tool": "get_ir_fields", "args": {{"accused_name": "Abdul Karim"}}}}
{{"tool": "get_statement", "args": {{"accused_name": "Abdul Karim"}}}}
{{"tool": "get_chargesheet", "args": {{"case_name": "Bengaluru Blast Case"}}}}
{{"tool": "get_brief_description", "args": {{"case_name": "Bengaluru Blast Case"}}}}
{{"tool": "search_text", "args": {{"query": "explosives", "case_name": "Bengaluru Blast Case"}}}}

TWO QUERY PATTERNS:

1. INDIVIDUAL QUESTION (about a specific person):
   - Example: "What crime numbers has John Doe been charged with?"
   - Strategy: get_ir_fields(accused_name) → answer from their data

2. CASE-WIDE QUESTION (about all accused or the whole case):
   - Example: "List all training camps mentioned in the case" or "What are the crime numbers for all accused?"
   - Strategy:
     Step 1: get_accused_list(case_name) → get ALL accused names from chargesheet
     Step 2: For EACH accused, call get_ir_fields(name) to get their details
     Step 3: Also call get_brief_description(case_name) if the question is about case narrative
     Step 4: Combine all findings into a comprehensive FINAL ANSWER

   For case-wide questions, you MUST iterate through the accused list. Do NOT stop after one person.

CRITICAL RULES:
1. Think step by step. Use tools to gather information.
2. You can use multiple tools in sequence — I will show you the result after each tool call.
3. When you have gathered enough information to answer the question, you MUST provide your final answer prefixed with "FINAL ANSWER:"
4. For INDIVIDUAL questions: focus only on the person asked about.
5. For CASE-WIDE questions: use get_accused_list first, then iterate through each relevant accused.
6. If a tool returns no data for a person, skip them and move on. Do NOT retry the same person.
7. Always cite which document the information came from.
8. If information is not found, say so clearly but still give a FINAL ANSWER: with what you DID find.
9. Answer in English only.
10. Do NOT make up information. Only use data returned by tools.

IMPORTANT: You MUST always end with "FINAL ANSWER:" followed by your complete response. Never leave without a final answer."""


MAX_AGENT_STEPS = 25  # Increased: case-wide questions need accused_list + one call per accused


def _parse_tool_call(response: str) -> Optional[Dict]:
    """Extract tool call from agent response — handles multiple formats."""

    # Format 1: JSON {"tool": "name", "args": {...}}
    try:
        match = re.search(r'\{[^{}]*"tool"\s*:\s*"[^"]+"\s*,\s*"args"\s*:\s*\{[^}]*\}[^}]*\}', response)
        if match:
            return json.loads(match.group())
    except (json.JSONDecodeError, AttributeError):
        pass

    # Format 2: JSON line by line
    for line in response.strip().split("\n"):
        line = line.strip().strip('`')
        if line.startswith("{") and '"tool"' in line:
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass

    # Format 3: tool_name(arg) or tool_name("arg") — Python-style
    for tool_name in TOOLS:
        patterns = [
            rf'{tool_name}\(\s*["\']([^"\']+)["\']\s*\)',  # tool("arg")
            rf'{tool_name}\(\s*\{{[^}}]*["\']case_name["\']\s*:\s*["\']([^"\']+)["\'][^}}]*\}}\s*\)',  # tool({"case_name": "arg"})
            rf'{tool_name}\(\s*\{{[^}}]*["\']accused_name["\']\s*:\s*["\']([^"\']+)["\'][^}}]*\}}\s*\)',
            rf'{tool_name}\(\s*\{{[^}}]*["\']query["\']\s*:\s*["\']([^"\']+)["\'][^}}]*\}}\s*\)',
        ]
        for pattern in patterns:
            m = re.search(pattern, response)
            if m:
                arg_val = m.group(1)
                # Determine the right arg name
                if tool_name in ("list_accused", "get_chargesheet", "get_accused_list", "get_brief_description"):
                    return {"tool": tool_name, "args": {"case_name": arg_val}}
                elif tool_name in ("get_ir_fields", "get_statement"):
                    return {"tool": tool_name, "args": {"accused_name": arg_val}}
                elif tool_name == "search_text":
                    return {"tool": tool_name, "args": {"query": arg_val}}
                else:
                    return {"tool": tool_name, "args": {}}

    # Format 4: Simple mention like "I will use list_cases" or "call get_ir_fields for Abdul"
    for tool_name in TOOLS:
        if tool_name in response:
            # Try to extract the argument
            if tool_name == "list_cases":
                return {"tool": tool_name, "args": {}}
            # Look for quoted names after the tool mention
            after_tool = response[response.index(tool_name):]
            name_match = re.search(r'["\']([^"\']{2,50})["\']', after_tool)
            if name_match:
                arg_val = name_match.group(1)
                if tool_name in ("list_accused", "get_chargesheet", "get_accused_list", "get_brief_description"):
                    return {"tool": tool_name, "args": {"case_name": arg_val}}
                elif tool_name in ("get_ir_fields", "get_statement"):
                    return {"tool": tool_name, "args": {"accused_name": arg_val}}
                elif tool_name == "search_text":
                    return {"tool": tool_name, "args": {"query": arg_val}}

    return None


def _run_agent(question: str, model: str, case_name: str = None) -> Dict[str, Any]:
    """Run the agent loop: think → tool → observe → repeat → final answer."""

    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
    ]

    # Add case context if provided
    if case_name:
        messages.append({"role": "user", "content": f"Context: We are investigating case '{case_name}'.\n\nQuestion: {question}"})
    else:
        messages.append({"role": "user", "content": question})

    reasoning_chain = []
    tools_used = []

    for step in range(MAX_AGENT_STEPS):
        print(f"[AgenticRAG] Step {step + 1}/{MAX_AGENT_STEPS}")

        response = ollama_chat(messages, temperature=0.0, model=model)
        print(f"[AgenticRAG] Agent: {response[:200]}...")

        # Check for final answer
        if "FINAL ANSWER:" in response:
            answer = response.split("FINAL ANSWER:", 1)[1].strip()
            reasoning_chain.append({"step": step + 1, "type": "answer", "content": answer[:100]})
            return {
                "answer": answer,
                "used_chunks": [{"doc_name": "Agent reasoning", "text": f"{len(tools_used)} tools used in {step + 1} steps"}],
                "search_method": f"agentic ({step + 1} steps, {len(tools_used)} tool calls)",
                "details": {
                    "steps": step + 1,
                    "tools_used": tools_used,
                    "reasoning_chain": reasoning_chain,
                },
            }

        # Try to parse tool call
        tool_call = _parse_tool_call(response)

        if tool_call:
            tool_name = tool_call.get("tool", "")
            tool_args = tool_call.get("args", {})

            if tool_name in TOOLS:
                print(f"[AgenticRAG] Calling tool: {tool_name}({tool_args})")
                tool_result = TOOLS[tool_name]["function"](tool_args)
                tools_used.append(tool_name)
                reasoning_chain.append({
                    "step": step + 1, "type": "tool_call",
                    "tool": tool_name, "args": tool_args,
                    "result_preview": tool_result[:200],
                })

                # Add to conversation
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"Tool result from {tool_name}:\n\n{tool_result}\n\nContinue your investigation. Use more tools if needed, or provide your FINAL ANSWER: if you have enough information."})
            else:
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"Unknown tool '{tool_name}'. Available tools: {', '.join(TOOLS.keys())}. Try again."})
        else:
            # No tool call and no final answer — agent might be thinking
            # Check if it looks like a direct answer without the prefix
            if step > 0 and len(response) > 100:
                reasoning_chain.append({"step": step + 1, "type": "answer", "content": response[:100]})
                return {
                    "answer": response,
                    "used_chunks": [{"doc_name": "Agent reasoning", "text": f"{len(tools_used)} tools used in {step + 1} steps"}],
                    "search_method": f"agentic ({step + 1} steps, {len(tools_used)} tool calls)",
                    "details": {"steps": step + 1, "tools_used": tools_used, "reasoning_chain": reasoning_chain},
                }

            # Nudge the agent strongly
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": "You MUST either call a tool using the JSON format, or provide your FINAL ANSWER: now. Summarize everything you have found so far. Start with 'FINAL ANSWER:' followed by your complete response."})

    # Max steps reached
    return {
        "answer": "Agent reached maximum steps without a final answer. Partial information gathered:\n\n" + "\n".join(
            f"Step {r['step']}: {r.get('tool', 'thinking')} → {r.get('result_preview', r.get('content', ''))[:100]}"
            for r in reasoning_chain
        ),
        "used_chunks": [],
        "search_method": f"agentic (max steps reached, {len(tools_used)} tool calls)",
        "details": {"steps": MAX_AGENT_STEPS, "tools_used": tools_used, "reasoning_chain": reasoning_chain},
    }


# ── Pipeline class ───────────────────────────────────────────────────

class AgenticRAGPipeline(BasePipeline):
    name = "AgenticRAG"
    description = "AI Agent with tools — multi-step investigation Q&A (uses StructuredRAG data)"

    def index(self, file_path: str, filename: str, model: str, **kwargs) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": "AgenticRAG does not index documents. Use StructuredRAG to index, then switch to AgenticRAG for Q&A.",
        }

    def query(self, question: str, model: str, doc_id: str = None, case_name: str = None) -> Dict[str, Any]:
        return _run_agent(question, model, case_name=case_name)

    def list_docs(self) -> List[Dict[str, Any]]:
        # Show StructuredRAG's docs since we read from them
        try:
            client = chromadb.PersistentClient(path=os.path.join(CHROMA_PATH, "structured"))
            col = client.get_or_create_collection(name="structured_rag")
            if col.count() == 0:
                return []
            all_metas = []
            offset = 0
            while True:
                batch = col.get(include=["metadatas"], limit=500, offset=offset)
                metas = batch.get("metadatas", [])
                if not metas:
                    break
                all_metas.extend(metas)
                if len(metas) < 500:
                    break
                offset += 500
            doc_map = {}
            for m in all_metas:
                did = m.get("doc_id", "")
                if did not in doc_map:
                    doc_map[did] = {"doc_id": did, "doc_name": m.get("doc_name", ""), "chunks": 0,
                                    "type": m.get("doc_type", ""), "case_name": m.get("case_name", "")}
                doc_map[did]["chunks"] += 1
            return list(doc_map.values())
        except Exception:
            return []

    def list_cases(self) -> List[str]:
        return get_all_case_names()

    def clear(self) -> Dict[str, Any]:
        return {"ok": False, "error": "AgenticRAG shares data with StructuredRAG. Clear from StructuredRAG pipeline."}
