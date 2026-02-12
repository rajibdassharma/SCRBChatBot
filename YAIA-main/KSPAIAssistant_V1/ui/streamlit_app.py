import streamlit as st
import requests
import pandas as pd

API = "http://localhost:8000"

st.set_page_config(page_title="KSP AI Assistant", layout="wide")
st.title("KSP AI Assistant")

# -----------------------------
# Helpers
# -----------------------------
def safe_json_response(r: requests.Response):
    """
    Safely parse backend response as JSON. If not JSON, show diagnostics.
    """
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
    """
    Convert Streamlit chat messages to backend-friendly history payload.
    Only send last N messages for speed/stability.
    """
    if not messages:
        return []
    trimmed = messages[-keep_last:]
    return [{"role": m["role"], "content": m["content"]} for m in trimmed]


# -----------------------------
# Session State Initialization
# -----------------------------
if "mode" not in st.session_state:
    st.session_state.mode = "MSSQL Chat"

if "db_messages" not in st.session_state:
    st.session_state.db_messages = []  # list of {"role": "user"/"assistant", "content": "..."}

if "doc_id" not in st.session_state:
    st.session_state.doc_id = None

if "doc_name" not in st.session_state:
    st.session_state.doc_name = None

if "doc_chunks" not in st.session_state:
    st.session_state.doc_chunks = None

if "pdf_messages" not in st.session_state:
    # dict: doc_id -> list[{"role":..., "content":...}]
    st.session_state.pdf_messages = {}

# -----------------------------
# Sidebar Controls
# -----------------------------
with st.sidebar:
    st.header("Controls")

    mode = st.radio(
        "Mode",
        ["MSSQL Chat", "PDF Chat"],
        index=0 if st.session_state.mode == "MSSQL Chat" else 1
    )
    st.session_state.mode = mode

    st.divider()

    if st.button("Clear DB Chat"):
        st.session_state.db_messages = []
        st.success("DB chat cleared.")

    if st.button("Clear PDF Chat (Current Doc)"):
        if st.session_state.doc_id and st.session_state.doc_id in st.session_state.pdf_messages:
            st.session_state.pdf_messages[st.session_state.doc_id] = []
            st.success("PDF chat cleared for current document.")
        else:
            st.info("No active PDF chat to clear.")

    st.divider()

    if st.session_state.doc_id:
        st.caption("Active PDF")
        st.write(f"**{st.session_state.doc_name}**")
        st.write(f"doc_id: `{st.session_state.doc_id}`")
        st.write(f"chunks: `{st.session_state.doc_chunks}`")
    else:
        st.caption("No PDF indexed yet.")


# =============================================================================
# MODE 1: MSSQL CHAT (with continuity)
# =============================================================================
if st.session_state.mode == "MSSQL Chat":
    st.subheader("MSSQL Chat (Chat Continuity Enabled)")

    # Render past messages
    for msg in st.session_state.db_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_text = st.chat_input("Ask your database in natural language...")
    if user_text:
        # Show user msg immediately
        st.session_state.db_messages.append({"role": "user", "content": user_text})
        with st.chat_message("user"):
            st.markdown(user_text)

        history_payload = to_history_payload(st.session_state.db_messages[:-1], keep_last=10)

        with st.spinner("Generating SQL and querying MSSQL..."):
            try:
                r = requests.post(
                    f"{API}/db/ask",
                    json={"question": user_text, "history": history_payload},
                    timeout=600
                )
            except Exception as e:
                with st.chat_message("assistant"):
                    st.error(f"Failed to call backend: {e}")
                st.stop()

        res = safe_json_response(r)

        if res.get("ok"):
            answer = res.get("answer", "")
            sql = res.get("sql", "")
            data = res.get("data", {})

            # Store assistant message text (answer)
            st.session_state.db_messages.append({"role": "assistant", "content": answer})

            with st.chat_message("assistant"):
                st.markdown(answer)

                if sql:
                    with st.expander("Generated SQL", expanded=False):
                        st.code(sql, language="sql")

                rows = data.get("rows", [])
                cols = data.get("columns", [])
                if rows:
                    try:
                        df = pd.DataFrame(rows, columns=cols if cols else None)
                        st.dataframe(df, use_container_width=True)
                    except Exception:
                        st.write(rows)
                else:
                    st.info("No rows returned.")
        else:
            err = res.get("error", "Unknown error")
            st.session_state.db_messages.append({"role": "assistant", "content": f"Error: {err}"})
            with st.chat_message("assistant"):
                st.error(err)
                if res.get("sql_raw"):
                    with st.expander("Raw model output / SQL", expanded=False):
                        st.code(res.get("sql_raw", ""), language="text")
                if res.get("sql_clean"):
                    with st.expander("Cleaned SQL", expanded=False):
                        st.code(res.get("sql_clean", ""), language="sql")


# =============================================================================
# MODE 2: PDF CHAT (Index + continuity per document)
# =============================================================================
else:
    st.subheader("PDF Chat (Index PDF + Chat Continuity Enabled)")

    # Upload/index area
    colA, colB = st.columns([1, 1])

    with colA:
        pdf = st.file_uploader("Upload PDF", type=["pdf"])

        if pdf and st.button("Index PDF"):
            with st.spinner("Indexing PDF (may take a few minutes)..."):
                try:
                    files = {"file": (pdf.name, pdf.getvalue(), "application/pdf")}
                    r = requests.post(f"{API}/docs/upload", files=files, timeout=600)
                except requests.exceptions.ReadTimeout:
                    st.error(
                        "Indexing timed out from the UI side (600s). "
                        "If the PDF is large, increase chunk size/cap or implement background indexing."
                    )
                    st.stop()
                except Exception as e:
                    st.error(f"Failed to call backend: {e}")
                    st.stop()

            resp = safe_json_response(r)
            if resp.get("ok"):
                st.session_state.doc_id = resp.get("doc_id")
                st.session_state.doc_name = resp.get("doc_name")
                st.session_state.doc_chunks = resp.get("chunks")

                # Initialize chat history for this doc_id
                if st.session_state.doc_id not in st.session_state.pdf_messages:
                    st.session_state.pdf_messages[st.session_state.doc_id] = []

                st.success(
                    f"Indexed: {st.session_state.doc_name} | "
                    f"Chunks: {st.session_state.doc_chunks} | "
                    f"doc_id: {st.session_state.doc_id}"
                )
            else:
                st.error(resp.get("error", "Indexing failed"))
                if resp.get("detail"):
                    st.code(resp.get("detail"))

    with colB:
        if st.session_state.doc_id:
            st.info(
                f"Active doc: **{st.session_state.doc_name}**\n\n"
                f"- doc_id: `{st.session_state.doc_id}`\n"
                f"- chunks: `{st.session_state.doc_chunks}`"
            )
        else:
            st.warning("Upload and index a PDF to start chatting with it.")

    st.divider()

    # If no doc is indexed, stop here
    if not st.session_state.doc_id:
        st.stop()

    doc_id = st.session_state.doc_id

    # Ensure message store exists
    if doc_id not in st.session_state.pdf_messages:
        st.session_state.pdf_messages[doc_id] = []

    # Render PDF chat history for this doc_id
    for msg in st.session_state.pdf_messages[doc_id]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    pdf_user_text = st.chat_input("Ask your PDF...")
    if pdf_user_text:
        # Add user message
        st.session_state.pdf_messages[doc_id].append({"role": "user", "content": pdf_user_text})
        with st.chat_message("user"):
            st.markdown(pdf_user_text)

        history_payload = to_history_payload(st.session_state.pdf_messages[doc_id][:-1], keep_last=10)

        with st.spinner("Retrieving context and generating answer..."):
            try:
                r = requests.post(
                    f"{API}/docs/ask",
                    json={
                        "doc_id": doc_id,
                        "question": pdf_user_text,
                        "history": history_payload
                    },
                    timeout=600
                )
            except Exception as e:
                with st.chat_message("assistant"):
                    st.error(f"Failed to call backend: {e}")
                st.stop()

        resp = safe_json_response(r)

        if resp.get("ok"):
            answer = resp.get("answer", "")
            st.session_state.pdf_messages[doc_id].append({"role": "assistant", "content": answer})

            with st.chat_message("assistant"):
                st.markdown(answer)
                used = resp.get("used_chunks", [])
                if used:
                    st.caption(f"Used chunks: {used}")
        else:
            err = resp.get("error", "Failed to answer")
            st.session_state.pdf_messages[doc_id].append({"role": "assistant", "content": f"Error: {err}"})
            with st.chat_message("assistant"):
                st.error(err)
                if resp.get("detail"):
                    st.code(resp.get("detail"))
