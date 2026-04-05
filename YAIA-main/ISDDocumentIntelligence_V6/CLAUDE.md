# Project: ISD Document Intelligence V6

A law enforcement document intelligence platform for extracting, analyzing, and
correlating information from investigative documents. FastAPI backend, React 19
frontend, MySQL database, ChromaDB vector store. Fully offline with local LLMs.

See @Architecture.md for system design decisions and detailed schema reference.

## Deployment Context

- **Single user** application — one analyst on a dedicated server
- **Server access** via RDP over dedicated LAN connection
- **No internet** on the server — fully air-gapped
- **Backend**: uvicorn on port 8003
- **Frontend**: `python3 -m http.server 5175` serving built `dist/` folder (no Nginx, no Vite dev server)
- **Server paths**: code at `/opt/isd/ISDDocumentIntelligence_V6/`, shared venv at `/opt/isd/venv/`
- **MySQL password on server**: `isdadmin` (local dev: `Sandy@411`)
- **Updates**: build `dist/` locally on Windows, copy via USB to server. No `npm install` on server.
- **This is NOT the CyberFraud project** — that is a separate multi-user app for 44 police stations

---

## Repo structure

```
/backend                # FastAPI server (Python, port 8003)
  app.py                # Main API — all routes, upload, Q&A, extraction
  config.py             # Loads .env settings (LLM, DB, feature flags)
  .env                  # Environment variables (secrets, model config)
  rag_smac.py           # RAG pipeline for SMAC docs (hybrid search, multi-query)
  rag_ir.py             # RAG pipeline for IR docs (structured field Q&A)
  ir_parser.py          # Pure Python IR Form-16 table parser (NO LLM)
  llm_kv_extractor.py   # LLM-based key-value extraction from PDFs/DOCX
  ollama_client.py      # Ollama LLM & embedding client (chat + embed)
  mysql_db.py           # MySQL connection manager (pymysql + DictCursor)
  structured_tables.py  # EAV tables: smac_reports & ir_reports
  entity_graph.py       # Entity & relationship extraction → MySQL
  activity_timeline.py  # Temporal event extraction → MySQL
  location_extractor.py # Location & address extraction with offline geocoding
  auth.py               # JWT auth (bcrypt, HS256, 24h tokens)
  cases.py              # Case management (multi-user isolation)
  chroma_db_smac_v6/    # ChromaDB persistent store (SMAC collection)
  chroma_db_ir_v6/      # ChromaDB persistent store (IR collection)
/frontend               # React 19 + TypeScript + Vite SPA (port 5175)
  src/App.tsx           # Main component (4 tabs: Doc Intel, Connections, Timeline, QA)
  src/App.css           # KSP-branded styling
/dbscripts              # Bulk indexing utilities with SQLite progress tracking
  bulk_index_smac.py    # Parallel SMAC PDF indexing (ThreadPoolExecutor)
  bulk_index_ir.py      # Sequential IR DOCX indexing
  ocr_index_smac.py     # OCR-based indexing for scanned PDFs
```

---

## Essential commands

```bash
# ── Backend ──────────────────────────────────────────────────
cd backend

# Install dependencies (install torch FIRST for GPU support)
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt

# Start dev server
uvicorn app:app --host 0.0.0.0 --port 8003 --reload

# ── Frontend ─────────────────────────────────────────────────
cd frontend
npm install
npm run dev          # dev server on port 5175
npm run build        # production build
npm run lint         # ESLint

# ── Bulk Indexing ────────────────────────────────────────────
cd dbscripts

# SMAC documents (parallel, 3 workers)
python bulk_index_smac.py --folder "C:/SMAC_Files" --case-id 0 --username admin --password secret --workers 3

# IR documents (sequential)
python bulk_index_ir.py --folder "C:/IR_Files" --username admin --password secret

# OCR for scanned PDFs (reads pdfs_pending_ocr.txt)
python ocr_index_smac.py --case-id 0

# Reset progress and re-index
python bulk_index_smac.py --folder "C:/SMAC_Files" --case-id 0 --reset

# Dry run (preview without uploading)
python bulk_index_ir.py --folder "C:/IR_Files" --dry-run
```

**Prerequisites:**
- Ollama running locally with `gemma3:12b` model pulled
- MySQL 8+ (database `ISDIntelligence` is auto-created on startup)
- Python 3.10+, Node.js 18+
- CUDA GPU recommended for sentence-transformers embeddings

---

## Stack

**Backend (backend/)**
- FastAPI with CORS middleware
- Python 3.10+ with relative imports (no package structure)
- pymysql with DictCursor for all MySQL access — no ORM
- ChromaDB PersistentClient for vector storage
- rank-bm25 for keyword search (in-memory BM25Okapi)
- Ollama HTTP API for LLM inference (`/api/chat`, `/api/embed`)
- sentence-transformers for GPU-accelerated embeddings (mxbai-embed-large-v1)
- Docling for PDF table extraction, pypdf for raw text
- python-docx for DOCX parsing, openpyxl for XLSX
- EasyOCR for scanned document processing
- passlib + bcrypt for password hashing, PyJWT for tokens

**Frontend (frontend/)**
- React 19 with functional components and hooks (useState, useEffect, useRef)
- TypeScript in strict mode
- Vite for build tooling and dev server
- react-force-graph-2d (D3.js) for knowledge graph visualization
- react-simple-maps for geospatial visualization
- jsPDF for chat history export

**Infrastructure**
- Ollama (local LLM server) — gemma3:12b for generation, mxbai-embed-large for embeddings
- MySQL 8+ (structured data: entities, relationships, timelines, locations, reports)
- ChromaDB (vector embeddings for semantic search)
- SQLite (bulk indexing progress tracking in dbscripts/)

---

## Code style

- All backend imports are relative: `from config import ...`, `from mysql_db import get_conn`
- No package structure — all backend files are flat in `backend/`
- Use `async/await` for FastAPI endpoints, but DB calls are synchronous (pymysql)
- Use raw SQL with pymysql DictCursor — never use an ORM
- All LLM calls go through `ollama_client.py` — never call Ollama HTTP directly
- All embeddings go through `ollama_client.ollama_embed_batch()` — handles both modes

**Naming conventions**
- Backend files: snake_case (`entity_graph.py`, `rag_smac.py`)
- Frontend components: single `App.tsx` (monolithic component)
- API routes: slash-separated (`/docs/upload`, `/graph/data`, `/timeline/groups`)
- MySQL tables: snake_case (`smac_reports`, `ir_reports`, `cross_references`)
- Environment variables: SCREAMING_SNAKE_CASE (`ENABLE_HYBRID_SEARCH`)
- ChromaDB collections: `SMAC`, `IR_db`, or case-scoped `SMAC_c{case_id}`, `IR_c{case_id}`

**Extraction module pattern**
Every knowledge extraction module (entity_graph, activity_timeline, location_extractor) follows:
- `init_db()` — auto-creates MySQL tables on import
- `extract_and_store_*()` — LLM extraction + MySQL storage
- `get_*()` / `get_*_data()` — retrieval queries
- `clear_*_data()` — cleanup function
- `get_extracted_doc_ids*()` — track which docs have been processed

---

## Architecture rules

**Two document pipelines — never mix them**
- **IR (Interrogation Reports)**: Form-16 DOCX → `ir_parser.py` (pure Python) → MySQL `ir_reports` EAV table → field-based Q&A via `rag_ir.py`
- **SMAC (Surveillance/Investigation)**: PDF → Docling/pypdf → 2000-char chunks → ChromaDB vectors + BM25 → hybrid RAG Q&A via `rag_smac.py`

**Authentication & case isolation**
- All protected routes use `Depends(get_current_user)` from `auth.py`
- Every DB query and ChromaDB collection MUST be scoped to `case_id`
- Case ownership verified in `cases.py._get_case_for_user()` — raises HTTP 403

**Feature flags in config.py**
- `ENABLE_HYBRID_SEARCH` — toggle BM25 + vector fusion
- `ENABLE_MULTI_QUERY` — toggle query expansion (synonym-based, not LLM)
- `ENABLE_RERANKING` — toggle LLM re-ranking of search results
- `USE_LLM_PARSER_IR` / `USE_LLM_PARSER_SMAC` — toggle LLM-based document parsing
- `USE_OLLAMA_EMBEDDINGS` — true = Ollama HTTP, false = sentence-transformers GPU

**Error handling**
- Backend: FastAPI HTTPException with status codes (401, 403, 404, 500)
- Frontend: error state variables per feature area (authError, docLastError, caseError)
- Bulk indexing: SQLite progress DB with status (pending/done/failed) + error message

---

## Database

**MySQL tables** (auto-created by each module's `init_db()`):
- `users` — authentication (id, username, password_hash, full_name, role, is_active)
- `cases` — case isolation (id, user_id, name, description, collection)
- `smac_reports` — EAV for SMAC fields (doc_id, doc_name, serial_no, field_key, field_value, case_id)
- `ir_reports` — EAV for IR fields (same schema as smac_reports)
- `entities` — knowledge graph nodes (name, type, doc_id, doc_name, context, case_id)
- `relationships` — knowledge graph edges (source_entity_id, target_entity_id, relationship_type, context)
- `activities` — timeline events (tms_id, activity_date, group_name, subject, description, temporal_status, priority, theatre, participants)
- `cross_references` — timeline links (source_tms_id, target_tms_id, context)
- `doc_locations` — geocoded addresses (person_name, address_text, city, locality, lat, lng, address_type)

**ChromaDB collections:**
- `SMAC` or `SMAC_c{case_id}` — SMAC document chunks with embeddings
- `IR_db` or `IR_c{case_id}` — IR document fields with embeddings

**SQLite databases** (dbscripts/ — progress tracking):
- `.smac_bulk_progress.db` — SMAC indexing progress
- `.ir_bulk_progress.db` — IR indexing progress
- `.smac_ocr_progress.db` — OCR indexing progress

---

## Environment variables

- Env file location: `backend/.env`
- Loaded by `config.py` via python-dotenv
- NEVER commit `.env` files to git
- When adding a new variable, ALWAYS add it to `config.py` with a sensible default

| Variable | Purpose | Default |
|----------|---------|---------|
| `OLLAMA_BASE_URL` | Ollama endpoint | `http://localhost:11434` |
| `PDF_MODEL` | LLM model for generation | `llama3.1:8b` |
| `EMBED_MODEL` | Embedding model name | `nomic-embed-text` |
| `CHROMA_PATH_SMAC` | ChromaDB path for SMAC | `chroma_db_smac_v6` |
| `CHROMA_PATH_IR` | ChromaDB path for IR | `chroma_db_ir_v6` |
| `ENABLE_HYBRID_SEARCH` | BM25 + vector fusion | `true` |
| `ENABLE_MULTI_QUERY` | Query expansion | `true` |
| `ENABLE_RERANKING` | LLM re-ranking | `true` |
| `USE_LLM_PARSER_IR` | LLM extraction for IR | `true` |
| `USE_LLM_PARSER_SMAC` | LLM extraction for SMAC | `false` |
| `USE_OLLAMA_EMBEDDINGS` | true=Ollama HTTP, false=GPU | `true` |
| `MAX_LLM_CALLS_PDF` | Max LLM calls per PDF | `25` |
| `JWT_SECRET_KEY` | JWT signing secret | (change in prod) |
| `JWT_EXPIRE_HOURS` | Token expiry | `24` |
| `WHISPER_MODEL` | Speech-to-text model | `small` |
| `MYSQL_HOST` | MySQL host | `localhost` |
| `MYSQL_PORT` | MySQL port | `3306` |
| `MYSQL_USER` | MySQL user | `root` |
| `MYSQL_PASSWORD` | MySQL password | (empty) |
| `MYSQL_DATABASE` | MySQL database name | `ISDIntelligence` |

---

## Git workflow

- Commit messages: descriptive prefix (`V6: feature description`)
- Never commit `.env`, `chroma_db_*/`, `.smac_bulk_progress.db`, or other local data
- Never commit `node_modules/`, `__pycache__/`, or `frontend/dist/`

---

## Things Claude often gets wrong on this project

- Do NOT read or write any file outside the `ISDDocumentIntelligence_V6/` project folder
- Do NOT import from other project folders (V3, V4, V5, CyberFraud, etc.)
- Do NOT use an ORM — this project uses raw pymysql with DictCursor exclusively
- Do NOT call Ollama HTTP endpoints directly — always use `ollama_client.py` functions
- Do NOT hard-code model names or paths — always use constants from `config.py`
- Do NOT forget `case_id` scoping on MySQL queries and ChromaDB collection names
- Do NOT modify `ir_parser.py` to use LLM — it is intentionally pure Python with no LLM dependency
- Do NOT create new MySQL tables without following the `init_db()` auto-creation pattern
- Do NOT add new environment variables without adding them to `config.py` with defaults
- Do NOT use class components in the frontend — React 19 functional components with hooks only
- Do NOT create separate component files — the frontend is a single `App.tsx` monolith
- When adding a new API route in `app.py`, ALWAYS add the corresponding Pydantic model
- When adding extraction features, ALWAYS follow the `extract_and_store_*` / `get_*` / `clear_*` pattern
- When working with ChromaDB, ALWAYS use `chromadb.PersistentClient` — never ephemeral
