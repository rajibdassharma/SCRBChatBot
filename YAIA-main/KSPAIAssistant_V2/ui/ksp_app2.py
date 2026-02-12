import os
import base64
import requests
import streamlit as st

# ------------------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------------------
API = "http://localhost:8000"

st.set_page_config(
    page_title="Karnataka State Police • AI Analytics Assistant",
    layout="wide",
)

# ------------------------------------------------------------------------------
# CSS (Law Enforcement Theme)
# ------------------------------------------------------------------------------
st.markdown("""
<style>
:root{
  --ksp-navy:#0b2c4a;
  --ksp-blue:#154c79;
  --ksp-accent:#f1c40f;
  --ksp-bg:#f6f8fb;
}

html, body, [class*="css"] {
  background-color: var(--ksp-bg);
}

.block-container {
  padding-top: 3.4rem;
  padding-bottom: 2.2rem;
  max-width: 1250px;
}

.ksp-banner{
  background: linear-gradient(90deg, var(--ksp-navy), var(--ksp-blue));
  border-radius: 14px;
  padding: 10px 14px;
  color: white;
  box-shadow: 0 6px 16px rgba(0,0,0,0.12);
  margin-bottom: 14px;
}

.ksp-title{
  font-size: 22px;
  font-weight: 800;
  margin: 0;
}

.ksp-subtitle{
  font-size: 12px;
  opacity: 0.9;
  margin-top: 2px;
}

.ksp-logo{
  width: 92px;
  height: 92px;
  border-radius: 10px;
  background: rgba(255,255,255,255);
  padding: 6px;
  object-fit: contain;
}

.ksp-pill{
  display:inline-block;
  background: rgba(255,255,255,0.14);
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  margin-right: 6px;
}

.section-card{
  background: white;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 4px 10px rgba(0,0,0,0.08);
  margin-bottom: 16px;
}

.chat-user{
  background:#e8f0fe;
  padding:10px;
  border-radius:10px;
  margin-bottom:6px;
}

.chat-ai{
  background:#f4f6f9;
  padding:10px;
  border-radius:10px;
  margin-bottom:10px;
  border-left:4px solid var(--ksp-blue);
}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# UTILITIES
# ------------------------------------------------------------------------------
def backend_health():
    try:
        r = requests.get(f"{API}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False

def render_logo():
    logo_path = os.path.join(os.path.dirname(__file__), "assets", "ksp_logo.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return f'<img src="data:image/png;base64,{b64}" class="ksp-logo" />'
    return '<div class="ksp-logo" style="display:flex;align-items:center;justify-content:center;font-weight:800;">KSP</div>'

# ------------------------------------------------------------------------------
# HEADER
# ------------------------------------------------------------------------------
ok = backend_health()
logo_html = render_logo()

banner = f"""
<div class="ksp-banner">
  <div style="display:flex;align-items:center;gap:12px;">
    {logo_html}
    <div>
      <div class="ksp-title">Karnataka State Police • AI Analytics Assistant</div>
      <div class="ksp-subtitle">
        Cyber Fraud Database (MSSQL) + Case Documents (PDF/DOCX) • Local AI (Ollama)
      </div>
      <div style="margin-top:4px;">
        <span class="ksp-pill">System: <b>{'ONLINE' if ok else 'OFFLINE'}</b></span>
        <span class="ksp-pill">DB: MSSQL</span>
        <span class="ksp-pill">Docs: Chroma</span>
      </div>
    </div>
  </div>
</div>
"""
st.markdown(banner, unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# SESSION STATE
# ------------------------------------------------------------------------------
if "db_chat" not in st.session_state:
    st.session_state.db_chat = []

if "doc_chat" not in st.session_state:
    st.session_state.doc_chat = []

if "docs" not in st.session_state:
    st.session_state.docs = []

# ------------------------------------------------------------------------------
# TABS
# ------------------------------------------------------------------------------
tab1, tab2 = st.tabs(["🗄️ Database Intelligence", "📄 Document Intelligence"])

# ------------------------------------------------------------------------------
# TAB 1: DATABASE CHAT
# ------------------------------------------------------------------------------
with tab1:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("🔍 Ask Questions on Cyber Fraud Database")

    q = st.text_area("Ask in natural language", height=80)

    if st.button("Query Database"):
        if q.strip():
            with st.spinner("Analyzing database..."):
                r = requests.post(
                    f"{API}/db/ask",
                    json={
                        "question": q,
                        "history": st.session_state.db_chat
                    },
                    timeout=600
                )

            if r.ok:
                data = r.json()
                st.session_state.db_chat.append({"role": "user", "content": q})
                st.session_state.db_chat.append({"role": "assistant", "content": data["answer"]})

                st.code(data.get("sql", ""), language="sql")
            else:
                st.error(r.text)

    for msg in st.session_state.db_chat:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-user">{msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-ai">{msg["content"]}</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# TAB 2: DOCUMENT INTELLIGENCE
# ------------------------------------------------------------------------------
with tab2:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("📂 Upload & Analyze Case Documents")

    files = st.file_uploader(
        "Upload PDF or DOCX files",
        type=["pdf", "docx"],
        accept_multiple_files=True
    )

    if st.button("Index Documents"):
        if files:
            for f in files:
                with st.spinner(f"Indexing {f.name}"):
                    r = requests.post(
                        f"{API}/docs/upload",
                        files={"file": (f.name, f, f.type)},
                        timeout=900
                    )
                if r.ok:
                    st.session_state.docs.append(r.json())
                else:
                    st.error(r.text)

    if st.session_state.docs:
        st.markdown("**Indexed Documents:**")
        for d in st.session_state.docs:
            st.write(f"• {d['doc_name']} ({d['doc_id']})")

    st.divider()
    dq = st.text_area("Ask question on uploaded documents", height=80)

    if st.button("Ask Documents"):
        if dq.strip():
            with st.spinner("Searching documents..."):
                r = requests.post(
                    f"{API}/docs/ask",
                    json={
                        "question": dq,
                        "history": st.session_state.doc_chat
                    },
                    timeout=600
                )

            if r.ok:
                data = r.json()
                st.session_state.doc_chat.append({"role": "user", "content": dq})
                st.session_state.doc_chat.append({"role": "assistant", "content": data["answer"]})
            else:
                st.error(r.text)

    for msg in st.session_state.doc_chat:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-user">{msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-ai">{msg["content"]}</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)
