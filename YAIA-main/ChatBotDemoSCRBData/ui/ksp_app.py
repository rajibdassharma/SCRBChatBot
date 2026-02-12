import streamlit as st
import requests
import pandas as pd
from datetime import datetime

API = "http://localhost:8000"

# ------------------------------------------------------------------------------
# Page Setup
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="KSP • AI Analytics Assistant",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------------------------
# Law Enforcement Theme (CSS)
# ------------------------------------------------------------------------------
LE_CSS = """
<style>
:root{
  --ksp-navy:#0b1f3a;
  --ksp-blue:#123a63;
  --ksp-steel:#2b4c6f;
  --ksp-gold:#c9a227;
  --ksp-gray:#e9eef5;
  --ksp-text:#0f172a;
  --ksp-muted:#6b7280;
}

/* Layout */
.block-container {
  padding-top: calc(3.5rem + env(safe-area-inset-top));
  padding-bottom: 2.2rem;
  max-width: 1250px;
}
html, body, [class*="css"]  { font-family: "Segoe UI", system-ui, -apple-system, Arial; color: var(--ksp-text); }

/* Banner */
.ksp-banner{
  background: linear-gradient(90deg, var(--ksp-navy), var(--ksp-blue));
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 16px;
  padding: 14px 16px;
  color: white;
  box-shadow: 0 8px 20px rgba(0,0,0,0.12);
  margin-bottom: 14px;
}
.ksp-title{
  font-size: 20px; font-weight: 800; letter-spacing: 0.2px; margin: 0;
}
.ksp-subtitle{
  margin-top: 3px; font-size: 12.5px; opacity: 0.9;
}
.ksp-badges{
  margin-top: 10px;
  display:flex; gap:10px; flex-wrap:wrap;
}
.ksp-pill{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255,255,255,0.10);
  border: 1px solid rgba(255,255,255,0.15);
  font-size: 12px;
}
.ksp-pill strong{ color: var(--ksp-gold); font-weight: 800; }

/* Cards */
.card{
  border-radius: 16px;
  padding: 14px 14px;
  background: white;
  border: 1px solid rgba(2,6,23,0.08);
  box-shadow: 0 1px 10px rgba(2,6,23,0.04);
}
.card h4{ margin: 0 0 10px 0; font-size: 13px; color: #111827; letter-spacing: 0.2px; }
.muted{ color: var(--ksp-muted); font-size: 12px; line-height: 1.35; }
.small{ font-size: 11.5px; color: var(--ksp-muted); }

/* Sidebar polish */
section[data-testid="stSidebar"]{
  background: linear-gradient(180deg, rgba(11,31,58,0.06), rgba(18,58,99,0.02));
}
section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3{
  color: var(--ksp-navy);
}

/* Buttons */
.stButton>button{
  border-radius: 12px;
  padding: 0.55rem 0.9rem;
  font-weight: 700;
}
.stButton>button[kind="primary"]{
  background: var(--ksp-blue);
  border: 1px solid rgba(0,0,0,0.08);
}
.stButton>button:hover{
  filter: brightness(0.98);
}

/* Chat bubbles */
[data-testid="stChatMessage"]{
  border-radius: 16px;
  border: 1px solid rgba(2,6,23,0.08);
  box-shadow: 0 1px 10px rgba(2,6,23,0.03);
}
[data-testid="stChatMessage"][aria-label="Chat message from user"]{
  background: rgba(11,31,58,0.04);
}
[data-testid="stChatMessage"][aria-label="Chat message from assistant"]{
  background: white;
}

/* Code blocks */
pre {
  border-radius: 14px !important;
  border: 1px solid rgba(2,6,23,0.08) !important;
}

/* dividers */
hr { border-color: rgba(2,6,23,0.08) !important; }
</style>
"""
st.markdown(LE_CSS, unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def safe_json_response(r: requests.Response):
    if r is None:
        st.error("No response from backend.")
        st.stop()
    if r.status_code != 200:
        st.error(f"Backend returned HTTP {r.status_code}")
        st.code(r.text or "<empty response>")
        st.stop()
    if not (r.text or "").strip():
        st.error("Backend returned an empty response.")
        st.stop()
    try:
        return r.json()
    except Exception as e:
        st.error("Backend response is not valid JSON.")
        st.write(f"JSON parse error: {e}")
        st.code(r.text)
        st.stop()

def to_history_payload(messages, keep_last=10):
    if not messages:
        return []
    trimmed = messages[-keep_last:]
    return [{"role": m["role"], "content": m["content"]} for m in trimmed]

def card(title: str, body_md: str):
    st.markdown(
        f"""
        <div class="card">
          <h4>{title}</h4>
          <div class="muted">{body_md}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

def backend_health():
    try:
        r = requests.get(f"{API}/health", timeout=10)
        return (r.status_code == 200), (r.text or "")
    except Exception as e:
        return False, str(e)

# ------------------------------------------------------------------------------
# Session State
# ------------------------------------------------------------------------------
if "mode" not in st.session_state:
    st.session_state.mode = "DB • Investigation Q&A"

if "db_messages" not in st.session_state:
    st.session_state.db_messages = []

if "doc_id" not in st.session_state:
    st.session_state.doc_id = None
if "doc_name" not in st.session_state:
    st.session_state.doc_name = None
if "doc_chunks" not in st.session_state:
    st.session_state.doc_chunks = None

if "pdf_messages" not in st.session_state:
    st.session_state.pdf_messages = {}  # doc_id -> messages list

# ------------------------------------------------------------------------------
# Top Banner (KSP style)
# ------------------------------------------------------------------------------
ok, _ = backend_health()
banner = f"""
<div class="ksp-banner">
  <div style="display:flex; justify-content:space-between; gap:14px; flex-wrap:wrap;">
    <div>
      <div class="ksp-title">Karnataka State Police • AI Analytics Assistant</div>
      <div class="ksp-subtitle">Operational Q&A for Cyber Fraud Database (MSSQL) and Document Intelligence (PDF RAG) — Local Models via Ollama</div>
      <div class="ksp-badges">
        <div class="ksp-pill">System Status: <strong>{'ONLINE' if ok else 'OFFLINE'}</strong></div>
        <div class="ksp-pill">Data: <strong>MSSQL</strong> + <strong>Chroma</strong></div>
        <div class="ksp-pill">Models: <strong>Qwen</strong> (Chat/SQL) + <strong>nomic-embed-text</strong> (Embeddings)</div>
      </div>
    </div>
    <div style="min-width:240px; text-align:right;">
      <div class="ksp-subtitle">Secure Local Deployment</div>
      <div style="font-weight:800; font-size:12px; margin-top:6px;">
        🛡️ Read-only Query Guardrails • Audit-ready Flow
      </div>
      <div class="small" style="margin-top:8px;">
        {datetime.now().strftime("%d %b %Y • %I:%M %p")}
      </div>
    </div>
  </div>
</div>
"""
st.markdown(banner, unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# Sidebar (Mission Controls)
# ------------------------------------------------------------------------------
with st.sidebar:
    st.subheader("Mission Controls")

    st.session_state.mode = st.radio(
        "Module",
        ["DB • Investigation Q&A", "PDF • Case File Q&A"],
        index=0 if st.session_state.mode.startswith("DB") else 1
    )

    st.divider()

    # Status panel
    st.caption("Operational Status")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Health Check"):
            ok, detail = backend_health()
            st.success("Backend ONLINE" if ok else "Backend OFFLINE")
            if not ok:
                st.code(detail)
    with col2:
        if st.button("DB Test"):
            try:
                r = requests.get(f"{API}/db/test", timeout=30)
                resp = safe_json_response(r)
                st.write(resp)
            except Exception as e:
                st.error(e)

    st.divider()

    # Quick actions
    st.caption("Actions")
    if st.button("Clear DB Conversation"):
        st.session_state.db_messages = []
        st.success("DB conversation cleared.")

    if st.button("Clear Current Case File Chat"):
        if st.session_state.doc_id and st.session_state.doc_id in st.session_state.pdf_messages:
            st.session_state.pdf_messages[st.session_state.doc_id] = []
            st.success("Case file chat cleared.")
        else:
            st.info("No active case file chat.")

    st.divider()

    # Active Case File
    st.caption("Active Case File")
    if st.session_state.doc_id:
        st.write(f"**{st.session_state.doc_name}**")
        st.write(f"`doc_id`: {st.session_state.doc_id}")
        st.write(f"`chunks`: {st.session_state.doc_chunks}")
    else:
        st.info("No PDF indexed.")

    st.divider()

    st.caption("Governance")
    st.markdown(
        "- Read-only SQL enforced\n"
        "- Logs recommended (Q, SQL, rows, time)\n"
        "- Use official data handling SOPs",
    )

# ------------------------------------------------------------------------------
# Main layout
# ------------------------------------------------------------------------------
main, ops = st.columns([2.2, 1.1], gap="large")

# ==============================================================================
# DB MODULE
# ==============================================================================
if st.session_state.mode.startswith("DB"):
    with ops:
        card(
            "Investigator Prompts",
            "• Which Crime Number has the highest amount?<br>"
            "• Top 10 accused accounts by total transferred amount<br>"
            "• Victim names for accused 'ROHIT KUMAR'<br>"
            "• Total amount by bank (Top 10)<br>"
            "• Crimes with highest number of unique victim accounts",
        )
        st.write("")
        card(
            "Case Notes (manual)",
            "Use this space for operational notes. (Optional: we can store notes in a file/DB later.)"
        )
        notes = st.text_area("Notes", height=140, placeholder="e.g., Check clustering on Victim_ID for CrimeNo 2024-...")

        st.write("")
        card(
            "Audit Trail (preview)",
            "We can log: Question, Generated SQL, Exec time, Row count, User/Role, Timestamp."
        )

    with main:
        st.subheader("Database • Investigation Q&A")

        # Render chat history
        for msg in st.session_state.db_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        user_text = st.chat_input("Ask the Cyber Fraud Database…")
        if user_text:
            st.session_state.db_messages.append({"role": "user", "content": user_text})
            with st.chat_message("user"):
                st.markdown(user_text)

            history_payload = to_history_payload(st.session_state.db_messages[:-1], keep_last=10)

            start = datetime.now()
            with st.spinner("Generating SQL and executing read-only query…"):
                try:
                    r = requests.post(
                        f"{API}/db/ask",
                        json={"question": user_text, "history": history_payload},
                        timeout=600
                    )
                except Exception as e:
                    with st.chat_message("assistant"):
                        st.error(f"Backend call failed: {e}")
                    st.stop()

            res = safe_json_response(r)
            elapsed = (datetime.now() - start).total_seconds()

            if res.get("ok"):
                answer = res.get("answer", "")
                sql = res.get("sql", "")
                data = res.get("data", {})

                st.session_state.db_messages.append({"role": "assistant", "content": answer})

                with st.chat_message("assistant"):
                    st.markdown(answer)

                    # Operational metrics
                    k1, k2, k3 = st.columns(3)
                    k1.metric("Response Time", f"{elapsed:.2f}s")
                    rows = data.get("rows", [])
                    k2.metric("Rows Returned", f"{len(rows)}")
                    k3.metric("SQL Guard", "ENFORCED")

                    with st.expander("Generated SQL (Read-only)", expanded=False):
                        st.code(sql, language="sql")

                    if rows:
                        try:
                            df = pd.DataFrame(rows, columns=data.get("columns") or None)
                            st.dataframe(df, use_container_width=True)
                        except Exception:
                            st.write(rows)
                    else:
                        st.info("No rows returned.")

            else:
                err = res.get("error", "Unknown error")
                with st.chat_message("assistant"):
                    st.error(err)
                    if res.get("sql_raw"):
                        with st.expander("Raw model output (debug)", expanded=False):
                            st.code(res.get("sql_raw", ""), language="text")
                    if res.get("sql_clean"):
                        with st.expander("Cleaned SQL (debug)", expanded=False):
                            st.code(res.get("sql_clean", ""), language="sql")

# ==============================================================================
# PDF MODULE
# ==============================================================================
else:
    with ops:
        card(
            "Case File Workflow",
            "1) Upload PDF case file<br>"
            "2) Index (extract → chunk → embed)<br>"
            "3) Ask questions with continuity<br><br>"
            "<b>Tip:</b> For scanned PDFs, OCR is needed."
        )
        st.write("")
        card(
            "Suggested Questions",
            "• Summarize key facts and dates<br>"
            "• What evidence is cited and where?<br>"
            "• Extract names, places and identifiers<br>"
            "• What actions were recommended?"
        )

    with main:
        st.subheader("PDF • Case File Q&A")

        pdf = st.file_uploader("Upload Case File (PDF)", type=["pdf"])

        colA, colB = st.columns([1, 1])
        with colA:
            if pdf and st.button("Index Case File", type="primary"):
                with st.spinner("Indexing case file…"):
                    try:
                        files = {"file": (pdf.name, pdf.getvalue(), "application/pdf")}
                        r = requests.post(f"{API}/docs/upload", files=files, timeout=600)
                    except requests.exceptions.ReadTimeout:
                        st.error("Indexing timed out. Reduce chunk cap or enable background indexing.")
                        st.stop()
                    except Exception as e:
                        st.error(f"Backend call failed: {e}")
                        st.stop()

                resp = safe_json_response(r)
                if resp.get("ok"):
                    st.session_state.doc_id = resp.get("doc_id")
                    st.session_state.doc_name = resp.get("doc_name")
                    st.session_state.doc_chunks = resp.get("chunks")

                    if st.session_state.doc_id not in st.session_state.pdf_messages:
                        st.session_state.pdf_messages[st.session_state.doc_id] = []

                    st.success(f"Indexed: {st.session_state.doc_name} (chunks: {st.session_state.doc_chunks})")
                else:
                    st.error(resp.get("error", "Indexing failed"))
                    if resp.get("detail"):
                        st.code(resp.get("detail"))

        with colB:
            if st.session_state.doc_id:
                st.info(f"Active Case File: **{st.session_state.doc_name}**  \nChunks: `{st.session_state.doc_chunks}`")

        st.divider()

        if not st.session_state.doc_id:
            st.info("Upload and index a case file to start Q&A.")
            st.stop()

        doc_id = st.session_state.doc_id
        if doc_id not in st.session_state.pdf_messages:
            st.session_state.pdf_messages[doc_id] = []

        # Render chat
        for msg in st.session_state.pdf_messages[doc_id]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        q = st.chat_input("Ask the case file…")
        if q:
            st.session_state.pdf_messages[doc_id].append({"role": "user", "content": q})
            with st.chat_message("user"):
                st.markdown(q)

            history_payload = to_history_payload(st.session_state.pdf_messages[doc_id][:-1], keep_last=10)

            start = datetime.now()
            with st.spinner("Retrieving context and answering…"):
                try:
                    r = requests.post(
                        f"{API}/docs/ask",
                        json={"doc_id": doc_id, "question": q, "history": history_payload},
                        timeout=600
                    )
                except Exception as e:
                    with st.chat_message("assistant"):
                        st.error(f"Backend call failed: {e}")
                    st.stop()

            resp = safe_json_response(r)
            elapsed = (datetime.now() - start).total_seconds()

            if resp.get("ok"):
                answer = resp.get("answer", "")
                used = resp.get("used_chunks", [])

                st.session_state.pdf_messages[doc_id].append({"role": "assistant", "content": answer})

                with st.chat_message("assistant"):
                    st.markdown(answer)

                    k1, k2, k3 = st.columns(3)
                    k1.metric("Response Time", f"{elapsed:.2f}s")
                    k2.metric("Chunks Used", f"{len(used)}")
                    k3.metric("Source Mode", "RAG")

                    if used:
                        with st.expander("Retrieved chunks (debug)", expanded=False):
                            st.write(used)
            else:
                with st.chat_message("assistant"):
                    st.error(resp.get("error", "Failed to answer"))
                    if resp.get("detail"):
                        st.code(resp.get("detail"))
