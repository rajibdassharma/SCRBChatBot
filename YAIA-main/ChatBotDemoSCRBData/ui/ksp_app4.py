import os
import base64
import requests
import streamlit as st

# ------------------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------------------
API = "http://localhost:8000"

st.set_page_config(
    page_title="Karnataka State Police • AI Assistant",
    layout="wide",
)

# ------------------------------------------------------------------------------
# CSS (Header + Sidebar Controls + Scoped Button Colors)
# ------------------------------------------------------------------------------
st.markdown(
    """
<style>
:root{
  --ksp-yellow:#ffd400;
  --ksp-yellow-soft:#fff3b0;
  --ksp-yellow-border:#e6c200;
  --ksp-red:#b10000;
  --ksp-navy:#0b2c4a;
  --ksp-bg:#f6f8fb;
  --ksp-black:#000000;
  --ksp-navy-deep:#061f33;
}

/* App background */
html, body, [class*="css"] {
  background-color: var(--ksp-bg);
  color: var(--ksp-black);
}

/* Bring everything down so header isn't cut */
.block-container{
  padding-top: 3.4rem;
  padding-bottom: 2.2rem;
  max-width: 1300px;
}

/* --- TOP HEADER (Yellow) --- */
.ksp-banner{
  background: var(--ksp-yellow);
  border-radius: 14px;
  padding: 12px 14px;
  color: var(--ksp-black);
  box-shadow: 0 6px 16px rgba(0,0,0,0.12);
  margin-bottom: 14px;
  min-height: 132px;
  display:flex;
  align-items:center;
}

.ksp-title{
  font-size: 28px;
  font-weight: 900;
  color: var(--ksp-red);
  margin: 0;
  line-height: 1.05;
}

.ksp-subtitle{
  font-size: 13px;
  color: var(--ksp-black);
  margin-top: 4px;
  font-weight: 600;
}

.ksp-pill{
  display:inline-block;
  background: rgba(0,0,0,0.10);
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 14px;
  margin-right: 6px;
  color: var(--ksp-black);
  font-weight: 700;
}

/* Logo */
.ksp-logo{
  width: 250px;
  height: 200px;
  border-radius: 12px;
  background: rgba(255,255,255,0.45);
  padding: 8px;
  object-fit: contain;
  box-shadow: inset 0 0 0 1px rgba(0,0,0,0.18);
}

/* Section cards */
.section-card{
  background: white;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 4px 10px rgba(0,0,0,0.08);
  margin-bottom: 16px;
}

/* Chat bubbles */
.chat-user{
  background:#e8f0fe;
  padding:10px;
  border-radius:10px;
  margin-bottom:6px;
  color: var(--ksp-black);
}

.chat-ai{
  background:#f4f6f9;
  padding:10px;
  border-radius:10px;
  margin-bottom:10px;
  border-left:4px solid var(--ksp-navy);
  color: var(--ksp-black);
}

/* ---------------------------------------------
   SIDEBAR (LEFT CONTROL PANEL) LOOK & FEEL
---------------------------------------------- */
section[data-testid="stSidebar"]{
  background: var(--ksp-yellow-soft) !important;
  border-right: 2px solid var(--ksp-yellow-border) !important;
}

section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span{
  color: var(--ksp-black) !important;
}

/* Sidebar buttons (LEFT) - Yellow */
section[data-testid="stSidebar"] div.stButton > button{
  width: 75%;
  border-radius: 12px;
  padding: 0.55rem 0.9rem;
  font-weight: 800;
  background: var(--ksp-yellow) !important;
  color: #000 !important;
  border: 2px solid rgba(0,0,0,0.25) !important;
}

section[data-testid="stSidebar"] div.stButton > button:hover{
  background: #ffea70 !important;
}

/* Center-align buttons inside sidebar */
section[data-testid="stSidebar"] div.stButton {
  display: flex;
  justify-content: center;
}

/* Control button width */
section[data-testid="stSidebar"] div.stButton > button {
  width: 85%;
  text-align: center;
}

/* Prominent divider for destructive actions */
.ksp-danger-divider{
  margin: 18px 0 12px 0;
  height: 2px;
  background: linear-gradient(
    to right,
    rgba(0,0,0,0),
    #b10000,
    rgba(0,0,0,0)
  );
}

/* ---------------------------------------------
   MAIN AREA BUTTONS - Navy
---------------------------------------------- */
div[data-testid="stAppViewContainer"] div.stButton > button{
  border-radius: 12px;
  padding: 0.55rem 0.9rem;
  font-weight: 800;
}

/* Main panel buttons: navy */
.main-panel div.stButton > button{
  background: var(--ksp-navy) !important;
  color: #ffffff !important;
  border: 1px solid var(--ksp-navy-deep) !important;
}

.main-panel div.stButton > button:hover{
  background: var(--ksp-navy-deep) !important;
}

/* Normal-size buttons (not full width) for Query/Ask/Index */
.normal-btn div.stButton > button{
  background: var(--ksp-navy) !important;
  color: #ffffff !important;
  border: 1px solid var(--ksp-navy-deep) !important;
  width: auto !important;
  min-width: 150px;
}

/* MAIN: tighten tabs spacing */
div[data-testid="stTabs"] {
  margin-top: 8px;
}

/* MAIN: big title row */
.main-title{
  font-size: 24px;
  font-weight: 900;
  color: var(--ksp-navy);
  margin: 0 0 6px 0;
}

/* MAIN: helper text */
.main-help{
  font-size: 13px;
  color: rgba(0,0,0,0.75);
  margin-bottom: 12px;
}

/* MAIN: input card */
.ksp-card{
  background: #ffffff;
  border-radius: 14px;
  padding: 16px;
  box-shadow: 0 6px 16px rgba(0,0,0,0.08);
  border: 1px solid rgba(0,0,0,0.06);
  margin-bottom: 16px;
}

/* MAIN: result panel */
.ksp-result{
  background: #f7f9fc;
  border-radius: 14px;
  padding: 16px;
  border: 1px solid rgba(0,0,0,0.08);
}

/* MAIN: section label chip */
.ksp-chip{
  display:inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 800;
  background: rgba(11,44,74,0.10);
  color: var(--ksp-black);
  margin-bottom: 10px;
}

</style>
""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------------------
# UTILITIES
# ------------------------------------------------------------------------------
def backend_health() -> bool:
    try:
        return requests.get(f"{API}/health", timeout=5).status_code == 200
    except Exception:
        return False


def render_logo_html() -> str:
    logo_path = os.path.join(os.path.dirname(__file__), "assets", "ksp_logo.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f'<img src="data:image/png;base64,{b64}" class="ksp-logo" />'
    return (
        '<div class="ksp-logo" style="display:flex;align-items:center;justify-content:center;'
        'font-weight:900;color:#000;">KSP</div>'
    )


# ------------------------------------------------------------------------------
# SESSION STATE
# ------------------------------------------------------------------------------
for k in ["db_chat", "doc_chat", "docs"]:
    if k not in st.session_state:
        st.session_state[k] = []

# NEW: status + last answer/error so right panel updates instantly (no refresh)
if "doc_status" not in st.session_state:
    st.session_state.doc_status = ""
if "doc_last_answer" not in st.session_state:
    st.session_state.doc_last_answer = ""
if "doc_last_error" not in st.session_state:
    st.session_state.doc_last_error = ""


# ------------------------------------------------------------------------------
# SIDEBAR CONTROLS (LEFT PANEL)
# ------------------------------------------------------------------------------
with st.sidebar:
    # --- KSP LOGO IN SIDEBAR ---
    st.markdown(
        f"""
        <div style="display:flex; justify-content:center; margin-bottom:16px;">
            {render_logo_html()}
        </div>
        """,
        unsafe_allow_html=True
    )

    if st.button("Clear Database Chat"):
        st.session_state.db_chat.clear()
        st.success("Database chat cleared")

    if st.button("Clear Document Chat"):
        st.session_state.doc_chat.clear()
        st.session_state.doc_last_answer = ""
        st.session_state.doc_last_error = ""
        st.session_state.doc_status = "✅ Document chat cleared."
        st.rerun()

    st.markdown('<div class="ksp-danger-divider"></div>', unsafe_allow_html=True)

    confirm = st.checkbox("Confirm: clear uploaded docs")
    if st.button("Clear Uploaded Docs"):
        if not confirm:
            st.warning("Please confirm before clearing.")
        else:
            try:
                r = requests.post(f"{API}/docs/clear", timeout=120)
                if r.ok:
                    st.session_state.docs.clear()
                    st.session_state.doc_chat.clear()
                    st.session_state.doc_last_answer = ""
                    st.session_state.doc_last_error = ""
                    st.session_state.doc_status = "✅ Documents and vector DB cleared."
                    st.success("Documents and vector DB cleared")
                    st.rerun()
                else:
                    st.error(r.text)
            except Exception as e:
                st.error(f"Failed: {e}")

# ------------------------------------------------------------------------------
# HEADER
# ------------------------------------------------------------------------------
ok = backend_health()

st.markdown(
    f"""
<div class="ksp-banner" style="justify-content:flex-start;">
  <div style="display:flex; flex-direction:column; align-items:flex-start;">
    <div class="ksp-title">Karnataka State Police • AI Assistant</div>
    <div class="ksp-subtitle">
      Cyber Fraud Database (MSSQL) + Case Documents (PDF/DOCX) • Local AI (Ollama)
    </div>
    <div style="margin-top:6px;">
      <span class="ksp-pill">System: <b>{'ONLINE' if ok else 'OFFLINE'}</b></span>
      <span class="ksp-pill">DB: MSSQL</span>
      <span class="ksp-pill">Docs: Vector DB</span>
    </div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------------------
# MAIN CONTENT
# ------------------------------------------------------------------------------
st.markdown('<div class="main-panel">', unsafe_allow_html=True)

tab1, tab2 = st.tabs(["🗄️ Database Intelligence", "📄 Document Intelligence"])

# ---------------- DB TAB ----------------
with tab1:
    st.markdown('<div class="ksp-card">', unsafe_allow_html=True)

    st.markdown('<div class="main-title">Database Intelligence</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-help">Ask questions in natural language. The system generates safe SQL and returns answers.</div>', unsafe_allow_html=True)

    left_q, right_ans = st.columns([1.1, 1.0], gap="large")

    with left_q:
        st.markdown('<span class="ksp-chip">Ask</span>', unsafe_allow_html=True)
        q = st.text_area("Ask in natural language", height=140, label_visibility="visible")

        st.markdown('<div class="normal-btn">', unsafe_allow_html=True)
        db_btn = st.button("Query Database")
        st.markdown('</div>', unsafe_allow_html=True)

    with right_ans:
        st.markdown('<span class="ksp-chip">Results</span>', unsafe_allow_html=True)
        st.markdown('<div class="ksp-result">', unsafe_allow_html=True)

        if len(st.session_state.db_chat) >= 2:
            last_answer = st.session_state.db_chat[-1]["content"]
            st.markdown(f"**Answer:**  \n{last_answer}")
        else:
            st.info("Results will appear here after you query the database.")

        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # Backend call AFTER UI to keep layout stable
    if db_btn and q.strip():
        with st.spinner("Analyzing database..."):
            r = requests.post(
                f"{API}/db/ask",
                json={"question": q, "history": st.session_state.db_chat},
                timeout=600,
            )

        if r.ok:
            data = r.json()
            st.session_state.db_chat += [
                {"role": "user", "content": q},
                {"role": "assistant", "content": data.get("answer", "")},
            ]
            if data.get("sql"):
                with st.expander("Generated SQL", expanded=False):
                    st.code(data["sql"], language="sql")

            # Force immediate UI refresh so "Results" panel updates without manual refresh
            st.rerun()
        else:
            st.error(r.text)

    with st.expander("Conversation History", expanded=False):
        for msg in st.session_state.db_chat:
            if msg["role"] == "user":
                st.markdown(f'<div class="chat-user">{msg["content"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="chat-ai">{msg["content"]}</div>', unsafe_allow_html=True)


# ---------------- DOC TAB ----------------
with tab2:
    st.markdown('<div class="ksp-card">', unsafe_allow_html=True)

    st.markdown('<div class="main-title">Document Intelligence</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="main-help">'
        'Upload PDF / Word / Excel / CSV files, index them into the vector database, '
        'then ask questions across all uploaded documents.'
        '</div>',
        unsafe_allow_html=True
    )

    left_doc, right_doc = st.columns([1.1, 1.0], gap="large")

    # ---------------- LEFT: Upload + Index + Ask ----------------
    with left_doc:
        st.markdown('<span class="ksp-chip">Upload & Index</span>', unsafe_allow_html=True)

        files = st.file_uploader(
            "Upload PDF / DOCX / Excel / CSV files",
            type=["pdf", "docx", "xlsx", "csv"],
            accept_multiple_files=True,
        )

        st.markdown('<div class="normal-btn">', unsafe_allow_html=True)
        idx_btn = st.button("Index Documents")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown(
            '<span class="ksp-chip" style="margin-top:12px; display:inline-block;">Ask</span>',
            unsafe_allow_html=True
        )
        dq = st.text_area("Ask question on uploaded documents", height=140)

        st.markdown('<div class="normal-btn">', unsafe_allow_html=True)
        ask_btn = st.button("Ask Documents")
        st.markdown('</div>', unsafe_allow_html=True)

    # ---------------- RIGHT: Status + Results ----------------
    with right_doc:
        st.markdown('<span class="ksp-chip">Results</span>', unsafe_allow_html=True)
        st.markdown('<div class="ksp-result">', unsafe_allow_html=True)

        if st.session_state.doc_status:
            st.success(st.session_state.doc_status)

        if st.session_state.doc_last_error:
            st.warning(st.session_state.doc_last_error)

        if st.session_state.docs:
            st.markdown("**Indexed Documents:**")
            for d in st.session_state.docs[-10:]:
                st.write(f"• {d.get('doc_name', 'Unknown')}")
            if len(st.session_state.docs) > 10:
                st.caption(f"+ {len(st.session_state.docs) - 10} more")
        else:
            st.info("No documents indexed yet.")

        st.markdown("---")

        if st.session_state.doc_last_answer:
            st.markdown(f"**Answer:**  \n{st.session_state.doc_last_answer}")
        else:
            st.info("Answers will appear here after you ask a question.")

        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # ---------------- ACTIONS ----------------

    # -------- INDEX DOCUMENTS --------
    if idx_btn:
        st.session_state.doc_status = ""
        st.session_state.doc_last_error = ""
        st.session_state.doc_last_answer = ""

        if not files:
            st.session_state.doc_last_error = "Please choose one or more files to index."
            st.rerun()

        indexed_count = 0

        for f in files:
            with st.spinner(f"Indexing {f.name}..."):
                try:
                    r = requests.post(
                        f"{API}/docs/upload",
                        files={"file": (f.name, f.getvalue(), f.type)},
                        timeout=900,
                    )

                    if not r.ok:
                        st.session_state.doc_last_error = f"{f.name}: {r.text}"
                        continue

                    try:
                        resp = r.json()
                    except Exception as e:
                        st.session_state.doc_last_error = f"{f.name}: Invalid JSON ({e})"
                        continue

                    st.session_state.docs.append(resp)
                    indexed_count += 1

                except Exception as e:
                    st.session_state.doc_last_error = f"{f.name}: {e}"

        if indexed_count > 0:
            st.session_state.doc_status = f"✅ Indexed {indexed_count} document(s). Ready for Q&A."
        else:
            if not st.session_state.doc_last_error:
                st.session_state.doc_last_error = "Indexing failed."

        st.rerun()

    # -------- ASK DOCUMENTS --------
    if ask_btn:
        st.session_state.doc_status = ""
        st.session_state.doc_last_error = ""
        st.session_state.doc_last_answer = ""

        if not st.session_state.docs:
            st.session_state.doc_last_error = "Please index at least one document first."
            st.rerun()

        if not dq.strip():
            st.session_state.doc_last_error = "Please type a question."
            st.rerun()

        with st.spinner("Searching documents..."):
            try:
                active_doc_id = st.session_state.docs[-1].get("doc_id") if st.session_state.docs else None

                r = requests.post(
                f"{API}/docs/ask",
                json={"doc_id": active_doc_id, "question": dq, "history": st.session_state.doc_chat},
                timeout=600,
            )

            except Exception as e:
                st.session_state.doc_last_error = f"Backend call failed: {e}"
                st.rerun()

        if not r.ok:
            st.session_state.doc_last_error = r.text
            st.rerun()

        data = r.json()
        answer = (data.get("answer") or "").strip()

        st.session_state.doc_chat.extend([
            {"role": "user", "content": dq},
            {"role": "assistant", "content": answer},
        ])

        if answer.lower().startswith("not found"):
            st.session_state.doc_last_error = answer
        else:
            st.session_state.doc_last_answer = answer
            st.session_state.doc_status = "✅ Answer generated."

        st.rerun()

    # -------- CHAT HISTORY --------
    with st.expander("Conversation History", expanded=False):
        for msg in st.session_state.doc_chat:
            if msg["role"] == "user":
                st.markdown(f'<div class="chat-user">{msg["content"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="chat-ai">{msg["content"]}</div>', unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)
