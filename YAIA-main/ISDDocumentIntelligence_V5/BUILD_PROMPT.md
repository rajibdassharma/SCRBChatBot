# ISD Document Intelligence V5 — Full-Stack Build Prompt

> **Purpose:** This prompt provides a complete specification for a coding AI agent (Claude Code, Cursor, etc.) to recreate the ISD Document Intelligence V5 application from scratch.
>
> **Target:** Full-stack web application — FastAPI backend + React frontend + MySQL + ChromaDB + Ollama LLM
>
> **Phases:** 6 sequential phases, each building on the previous

---

## APPLICATION OVERVIEW

Build a fully offline, AI-powered document analysis system for law enforcement (Karnataka State Police). The system allows officers to:
1. Upload case documents (PDF, DOCX, DOC, XLSX, CSV)
2. Index them into a vector database (ChromaDB) and structured database (MySQL)
3. Query them using natural language text or voice
4. Visualize entity knowledge graphs extracted by LLM
5. View activity timelines with cross-reference "Bread Crumb" trails
6. See geocoded locations on an interactive map
7. Rate AI answers for quality feedback (UAT)

**All processing is local — no internet required after initial setup.**

### Technology Stack

| Layer | Technology | Version/Details |
|-------|-----------|-----------------|
| Backend | FastAPI (Python) | REST API, document processing |
| Frontend | React 19 + TypeScript + Vite 7 | Single-page application |
| LLM | Ollama (local) | gemma3:12b for generation |
| Embeddings | mxbai-embed-large (via Ollama) | 1024-dimension vectors |
| Vector DB | ChromaDB | Persistent on-disk storage |
| Structured DB | MySQL 8.x | utf8mb4 charset, InnoDB engine |
| Auth | JWT (PyJWT + bcrypt) | Stateless token auth |
| STT | faster-whisper (local) | Speech-to-text |
| TTS | Browser SpeechSynthesis API | No server needed |
| Audio | PyAV | WebM to WAV conversion |

### Two Document Types

| Collection | Document Type | Structure |
|-----------|--------------|-----------|
| **SMAC** | Log Reports with TMS IDs | 3-column tabular PDF (S.No \| Field Name \| Value), ~17 fields |
| **IR** | Interrogation Reports (Form-16) | 3-column DOCX table (Sl No \| Description \| Value), 62+ fields |

---

# PHASE 1: Project Setup, Configuration & Database Schema

## 1.1 Project Structure

Create the following directory structure:

```
ISDDocumentIntelligence_V5/
  backend/
    app.py                  # FastAPI main application
    config.py               # Environment-based configuration
    mysql_db.py             # MySQL connection factory & bootstrap
    auth.py                 # JWT authentication module
    cases.py                # Case management module
    rag.py                  # RAG pipeline (indexing + search + Q&A)
    ollama_client.py        # Ollama API client (chat + embeddings)
    structured_tables.py    # smac_reports + ir_reports tables
    entity_graph.py         # Entity & relationship extraction
    activity_timeline.py    # Activity & cross-reference extraction
    location_extractor.py   # Address extraction & offline geocoding
    llm_kv_extractor.py     # LLM-based key-value extraction
    requirements.txt
    .env
  frontend/
    index.html
    package.json
    vite.config.ts
    tsconfig.json
    .env
    public/
      geo/
        countries-110m.json  # TopoJSON for world map
    src/
      main.tsx
      App.tsx
      App.css
      index.css
      assets/
        ksp_logo.png
        banner_logo.png
  dbscripts/
    bulk_index_smac.py      # Multi-threaded bulk indexer
  tests/
    conftest.py
```

## 1.2 Backend Configuration — `config.py`

```python
import os
from dotenv import load_dotenv
load_dotenv()

# JWT Authentication
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production-use-a-long-random-string")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

# Ollama LLM
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
PDF_MODEL = os.getenv("PDF_MODEL", "gemma3:12b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "mxbai-embed-large")

# ChromaDB
CHROMA_PATH = os.getenv("CHROMA_PATH", "chroma_db_v5")

# Whisper STT
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")

# RAG Accuracy Features (toggleable)
ENABLE_HYBRID_SEARCH = os.getenv("ENABLE_HYBRID_SEARCH", "true").lower() == "true"
ENABLE_MULTI_QUERY = os.getenv("ENABLE_MULTI_QUERY", "true").lower() == "true"
ENABLE_RERANKING = os.getenv("ENABLE_RERANKING", "true").lower() == "true"

# LLM-powered document parser
USE_LLM_PARSER = os.getenv("USE_LLM_PARSER", "true").lower() == "true"
MAX_LLM_CALLS_PDF = int(os.getenv("MAX_LLM_CALLS_PDF", "25"))

# MySQL
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "ISDIntelligence")
```

## 1.3 Backend `.env` File

```
OLLAMA_BASE_URL=http://localhost:11434
PDF_MODEL=gemma3:12b
EMBED_MODEL=mxbai-embed-large
WHISPER_MODEL=small
CHROMA_PATH=chroma_db_v5
ENABLE_HYBRID_SEARCH=true
ENABLE_MULTI_QUERY=true
ENABLE_RERANKING=true
USE_LLM_PARSER=true
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=<your-password>
MYSQL_DATABASE=ISDIntelligence
JWT_SECRET_KEY=<random-64-char-string>
```

## 1.4 MySQL Connection Module — `mysql_db.py`

Create a connection factory with these functions:

- **`ensure_database_exists()`** — Connect without database, run `CREATE DATABASE IF NOT EXISTS ISDIntelligence CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci`. Call at module import time.
- **`get_conn()`** — Return `pymysql.connect(...)` with `autocommit=False`, `DictCursor`, `charset="utf8mb4"`.
- **`_fetchone(cursor)`** and **`_fetchall(cursor)`** — Thin wrappers for API compatibility.

**CRITICAL MySQL constraint:** All VARCHAR columns in UNIQUE KEY constraints must be **VARCHAR(255)** or less. MySQL utf8mb4 uses 4 bytes/char, and InnoDB has a 3072-byte key length limit. `VARCHAR(255) × 4 = 1020 bytes` per column.

## 1.5 Database Schema — 10 Tables

All tables use `INT AUTO_INCREMENT PRIMARY KEY` and are created via `init_db()` functions called at module import time. Parameter placeholders use `%s` (pymysql syntax, NOT `?`).

### Table 1: `users`
```sql
CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name     VARCHAR(200),
    role          VARCHAR(50) NOT NULL DEFAULT 'user',
    is_active     TINYINT(1) NOT NULL DEFAULT 1,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
```

### Table 2: `cases`
```sql
CREATE TABLE IF NOT EXISTS cases (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    name        VARCHAR(200) NOT NULL,
    description VARCHAR(500),
    collection  VARCHAR(50) NOT NULL DEFAULT 'IR',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_cases_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
)
```

### Table 3: `smac_reports` (Flat Columnar — one row per SMAC document)
```sql
CREATE TABLE IF NOT EXISTS smac_reports (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    doc_id           VARCHAR(255) NOT NULL UNIQUE,
    doc_name         VARCHAR(500) NOT NULL,
    input_id         VARCHAR(200) NULL,
    date_of_receipt  VARCHAR(200) NULL,
    originator       VARCHAR(500) NULL,
    source_name      VARCHAR(500) NULL,
    grading          VARCHAR(100) NULL,
    theatre          VARCHAR(200) NULL,
    priority         VARCHAR(100) NULL,
    subject          TEXT NULL,
    gist             TEXT NULL,
    threat_details   TEXT NULL,
    shared_with      TEXT NULL,
    classification   VARCHAR(100) NULL,
    raw_fields       TEXT NULL,
    indexed_at       DATETIME NULL,
    comments         TEXT NULL,
    case_id          INT NULL
)
-- Indexes: input_id, originator, date_of_receipt
```

### Table 4: `ir_reports` (EAV Key-Value — multiple rows per IR document)
```sql
CREATE TABLE IF NOT EXISTS ir_reports (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    doc_id       VARCHAR(255) NOT NULL,
    doc_name     VARCHAR(500) NOT NULL,
    collection   VARCHAR(100) NOT NULL DEFAULT 'IR',
    serial_no    VARCHAR(50) NULL,
    field_key    VARCHAR(255) NOT NULL,
    field_value  TEXT NULL,
    case_id      INT NULL,
    UNIQUE KEY uq_ir_reports (doc_id, field_key)
)
-- Indexes: doc_id, collection, field_key
```

### Table 5: `entities` (Knowledge Graph Nodes)
```sql
CREATE TABLE IF NOT EXISTS entities (
    id       INT AUTO_INCREMENT PRIMARY KEY,
    name     VARCHAR(255) NOT NULL,
    type     VARCHAR(100) NOT NULL,
    doc_id   VARCHAR(255) NOT NULL,
    doc_name VARCHAR(500) NOT NULL,
    context  TEXT NULL,
    case_id  INT NULL,
    UNIQUE KEY uq_entities (name, type, doc_id)
)
-- Indexes: name, type, doc_id
```

### Table 6: `relationships` (Knowledge Graph Edges)
```sql
CREATE TABLE IF NOT EXISTS relationships (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    source_entity_id  INT NOT NULL,
    target_entity_id  INT NOT NULL,
    relationship_type VARCHAR(100) NOT NULL,
    doc_id            VARCHAR(255) NOT NULL,
    context           TEXT NULL,
    case_id           INT NULL,
    UNIQUE KEY uq_relationships (source_entity_id, target_entity_id, relationship_type, doc_id)
)
```

**23 Relationship Types:**
```
MEMBER_OF, WORKS_AT, SIBLING, SPOUSE, PARENT_OF, CHILD_OF, LIVES_AT,
COLLEAGUE, PARTICIPATED_IN, REPORTS_TO, LOCATED_IN, RELATED_TO, CO_OCCURRENCE,
HELPER_OF, ADVOCATE_OF, DOCTOR_OF, FINANCIER_OF, ASSOCIATE_OF, ACCOMPLICE_OF,
HANDLER_OF, SYMPATHIZER_OF, ACCUSED_WITH, CO_ACCUSED
```

### Table 7: `activities` (Timeline)
```sql
CREATE TABLE IF NOT EXISTS activities (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    tms_id          VARCHAR(100) NULL,
    doc_id          VARCHAR(500) NOT NULL,
    doc_name        VARCHAR(500) NOT NULL,
    activity_date   VARCHAR(100) NULL,
    group_name      VARCHAR(500) NULL,
    subject         VARCHAR(500) NULL,
    description     TEXT NULL,
    temporal_status VARCHAR(50) NOT NULL DEFAULT 'CURRENT',
    priority        VARCHAR(100) NULL,
    theatre         VARCHAR(200) NULL,
    participants    TEXT NULL,
    activity_type   VARCHAR(100) NULL,
    case_id         INT NULL,
    UNIQUE INDEX idx_activities_tms_doc (tms_id, doc_id)
)
```

### Table 8: `cross_references` (Bread Crumb Links)
```sql
CREATE TABLE IF NOT EXISTS cross_references (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    source_tms_id VARCHAR(100) NOT NULL,
    target_tms_id VARCHAR(100) NOT NULL,
    context       VARCHAR(500) NULL,
    doc_id        VARCHAR(255) NOT NULL,
    case_id       INT NULL,
    UNIQUE KEY uq_cross_references (source_tms_id, target_tms_id, doc_id)
)
```

### Table 9: `doc_locations` (Geocoded Addresses)
```sql
CREATE TABLE IF NOT EXISTS doc_locations (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    doc_id       VARCHAR(255) NOT NULL,
    doc_name     VARCHAR(500) NOT NULL,
    person_name  VARCHAR(200) NOT NULL DEFAULT '',
    address_text TEXT NOT NULL,
    city         VARCHAR(200) NOT NULL DEFAULT '',
    locality     VARCHAR(200) NOT NULL DEFAULT '',
    lat          DOUBLE NULL,
    lng          DOUBLE NULL,
    address_type VARCHAR(50) NOT NULL DEFAULT 'OTHER',
    case_id      INT NULL,
    UNIQUE KEY uq_doc_locations (doc_id, person_name, address_type)
)
```

### Table 10: `answer_ratings` (UAT Feedback)
```sql
CREATE TABLE IF NOT EXISTS answer_ratings (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    username   VARCHAR(100) NOT NULL,
    collection VARCHAR(50) NOT NULL DEFAULT 'SMAC',
    case_id    INT NOT NULL DEFAULT 0,
    question   TEXT,
    answer     TEXT,
    rating     INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
```

## 1.6 Requirements — `requirements.txt`

```
fastapi
uvicorn
python-dotenv
requests
pypdf
chromadb
python-multipart
python-docx
openpyxl
faster-whisper
rank-bm25
pymysql
python-jose[cryptography]
passlib[bcrypt]
gunicorn
```

---

# PHASE 2: Authentication & Case Management

## 2.1 Authentication Module — `auth.py`

### Password Hashing
- Use `passlib.context.CryptContext` with bcrypt scheme
- `_hash_password(plain)` and `_verify_password(plain, hashed)`

### JWT Token
- `_create_token(user_id, username, role)` → JWT with `sub`, `username`, `role`, `exp` (24h default)
- Algorithm: HS256, key from `JWT_SECRET_KEY`

### FastAPI Dependency: `get_current_user()`
- Extract Bearer token via `HTTPBearer`
- Decode JWT, validate, return `CurrentUser(user_id, username, role)`
- Raise HTTP 401 if invalid/expired

### API Router — prefix `/auth`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/auth/register` | POST | Register user. Validate: username ≥ 3 chars, password ≥ 6 chars. Check for duplicates. Return JWT + user. |
| `/auth/login` | POST | Login. Verify password with bcrypt. Check `is_active`. Return JWT + user. |
| `/auth/me` | GET | Return current user's profile (protected). |
| `/auth/change-password` | POST | Change password (protected). Verify current password first. |
| `/auth/users` | GET | Admin only: list all users. |

### Module-level Bootstrap
Call `init_users_table()` at import time to create the table.

## 2.2 Case Management Module — `cases.py`

A "case" is a named, isolated workspace belonging to one user. All documents, vectors, and structured data are scoped by `case_id`.

### Helper: `_get_case_for_user(case_id, user_id)`
- Fetch case row, verify ownership (HTTP 404 if not found, HTTP 403 if wrong user)

### FastAPI Dependency: `get_active_case(case_id, current_user)`
- Validates case ownership, returns case dict

### API Router — prefix `/cases`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/cases` | GET | List user's cases (newest first) |
| `/cases` | POST | Create case. Validate: name not empty, collection in `["IR", "SMAC"]` |
| `/cases/{case_id}` | GET | Get single case (ownership check) |
| `/cases/{case_id}` | PATCH | Update name/description |
| `/cases/{case_id}` | DELETE | Delete case + purge ChromaDB collections |

### Case-Scoped ChromaDB Collections
```python
def _scoped_col(collection: str, case_id: int) -> str:
    return f"{collection}_c{case_id}"   # e.g., "SMAC_c1", "IR_c3"
```

When `case_id=0`, use the unscoped name (`"SMAC"` or `"IR"`).

---

# PHASE 3: RAG Pipeline — Indexing, Hybrid Search & Q&A

This is the core of the application (~2400 lines in `rag.py`). Build it in sub-phases.

## 3.1 Ollama Client — `ollama_client.py`

### `ollama_chat(messages, temperature=0.0, model=None)`
- POST to `{OLLAMA_BASE_URL}/api/chat`
- `stream: False`, return `response["message"]["content"]`
- Timeout: 600 seconds

### `ollama_embed_batch(texts, model=None, batch_size=64, max_retries=3)`
- POST to `{OLLAMA_BASE_URL}/api/embed` with `{"model": m, "input": batch}`
- Retry failed batches up to 3 times with exponential backoff (2s, 4s, 6s)
- Fallback: embed one-by-one using `/api/embeddings` endpoint
- Use zero-vector placeholder `[0.0] * 1024` for chunks that still fail
- Return `list[list[float]]`

### `ollama_embed(text, model=None)`
- Wrapper: calls `ollama_embed_batch([text])` and returns first vector

## 3.2 ChromaDB Setup (in `rag.py`)

```python
import chromadb
_client = chromadb.PersistentClient(
    path=os.path.join(os.path.dirname(os.path.abspath(__file__)), CHROMA_PATH)
)
```

- Collection name sanitization: replace invalid chars with `_` (ChromaDB naming rules)
- Collection cache: `_col_cache = {}` dict
- `_get_col(name)` — get or create collection, rebuild BM25 index on first access

## 3.3 BM25 Index (In-Memory, Per Collection)

Maintain a parallel BM25 index for each ChromaDB collection:

```python
_bm25_state = {}   # col_name -> {"docs": [...], "metas": [...], "index": BM25Okapi}
```

- **`_rebuild_bm25(col)`** — Fetch all documents from ChromaDB, tokenize, build `BM25Okapi`
- **`_add_to_bm25(col, documents, metadatas)`** — Incrementally add new docs to existing index
- **`_clear_bm25(col)`** — Reset index for collection
- **Tokenization:** lowercase, split on non-alphanumeric, keep numbers

## 3.4 Document Indexing — `index_document(file_path, filename, collection_name)`

### Text Extraction by Format

| Format | Method | Notes |
|--------|--------|-------|
| PDF | `pypdf.PdfReader` per-page | Extract text page by page. Detect table rows (pipe-separated, colon-separated, space-separated). |
| DOCX | `python-docx` paragraphs + tables | Extract paragraph text + table rows as key-value lines. |
| XLSX | `openpyxl` | Convert each row to "Header: Value" text. Max 300 rows per sheet. |
| CSV | `csv.reader` | Convert each row to "Header: Value" text. Max 500 rows. |
| DOC | Convert to DOCX first | On Windows: COM automation via `win32com.client`. On Linux: `libreoffice --convert-to docx`. |

### Chunking
- **Chunk size:** 2000 characters
- **Overlap:** 120-140 characters
- **Min unit length:** 10-25 characters (filter out tiny fragments)
- **Max chunks per document:** 500 (`MAX_UNITS`)
- **Max pages per PDF:** 120 (`MAX_PAGES`)
- **Max chars per DOCX:** 400,000 (`MAX_CHARS`)

### Embedding & Storage
1. Generate unique `doc_id` using `uuid.uuid4().hex[:12]`
2. Embed all chunks in batches of 64 via `ollama_embed_batch()`
3. Store in ChromaDB with metadata: `{"doc_id": ..., "doc_name": ..., "page": ..., "chunk_index": ...}`
4. Add to BM25 index
5. For SMAC: extract structured fields → `store_smac_report()`
6. For IR: extract structured fields → `store_ir_report()`

### LLM Key-Value Extraction (`llm_kv_extractor.py`)
When `USE_LLM_PARSER=true`:
- **DOCX:** Read with `python-docx` (XML parsing, fast), send table text to LLM for field extraction
- **PDF:** Read with Docling (OCR disabled, `PyPdfiumDocumentBackend`), fallback to pypdf. Send to LLM.
- LLM prompt: "Extract all key-value pairs from this document table..."
- Robust JSON recovery: handle truncated JSON, markdown fences, control characters
- Returns `list[{"serial_no": "1", "field_name": "Name of Accused", "value": "Mohammed Ali"}]`

### SMAC Field Mapper (`structured_tables.py`)
Map LLM-extracted fields to `smac_reports` columns using fuzzy keyword matching:
- "input id" / "tms id" → `input_id`
- "date of receipt" → `date_of_receipt`
- "originator" → `originator`
- "source" (but not "grading") → `source_name`
- "grading" / "grade" → `grading`
- "subject" → `subject`
- "gist" / "input" / "content" / "intelligence" → `gist`
- "threat" → `threat_details`
- "shared with" / "distribution" → `shared_with`
- Unmapped fields → `raw_fields` (JSON)
- Nil values ("-", "Nil", "N/A", "None") are skipped

## 3.5 Hybrid Search Pipeline — `_hybrid_retrieve(col, question, doc_ids, top_k)`

Run THREE search engines in parallel and merge:

### Step 1: Multi-Query Expansion (if `ENABLE_MULTI_QUERY`)
LLM generates 3 alternative phrasings of the question.

### Step 2: Structured Keyword Search
Search `ir_reports` / `smac_reports` tables for matching field values using `search_fields(keyword)`.

**Keyword Synonym Expansion (`_KEYWORD_SYNONYMS`):**
```python
"accused" → ["name", "accused"]
"phone" → ["mobile", "landline", "phone"]
"associate" → ["associate", "accomplice", "helper", "co-accused", "companion", "contact"]
"lawyer" → ["advocate", "lawyer", "legal", "counsel"]
"hideout" → ["hideout", "hide out", "safe house", "shelter", "place of hideout"]
"family" → ["father", "mother", "brother", "sister", "spouse", "family"]
"address" → ["address", "permanent address", "present address"]
"weapon" → ["weapon", "arms"]
"organization" → ["organi", "affiliation"]
```

### Step 3: Vector Search
Embed question → ChromaDB similarity search (top_k × 3 candidates).

### Step 4: BM25 Keyword Search
Exact keyword matching for case numbers, account numbers, names (top_k × 3 candidates).

### Step 5: Reciprocal Rank Fusion (RRF)
Merge vector + BM25 results: `score = Σ 1.0 / (k + rank + 1)` where `k=60`.
Documents found by multiple methods get boosted.

### Step 6: LLM Re-Ranking (if `ENABLE_RERANKING`)
Send top candidates to LLM to re-score by relevance. Reorder to top 12.

## 3.6 Question Answering — `ask_docs(question, doc_ids, top_k, collection_name, raw_question)`

### Smart Routing: Aggregate Detection
Detect aggregate questions and route to NL-to-SQL pipeline:

**Trigger patterns:**
```
list all|name all|show all|find all|give all|get all|display all|
all the|all accused|all subjects|all persons|all documents|all reports|
every|each document|each person|each accused|
how many|count|total number|
compare|comparison|across all|summary of all|
tabulate|table of
```

**NL-to-SQL Pipeline:**
1. Send question + table schema description to LLM
2. LLM generates SQL query
3. Execute SQL (SELECT only — validate no DROP/DELETE/INSERT/UPDATE)
4. Format results via LLM
5. Return answer

### IR-Specific Retrieval
For IR questions:
1. **Fuzzy field retrieval** (`_get_chunks_by_field_fuzzy`) — Search `field_name` metadata AND document text
2. **Direct text search** (`_ir_text_search`) — Score-based, majority-match (min 2 or (len+1)//2 words)
3. Always merge field/text + hybrid retrieval results
4. Text-matched chunks placed first (higher relevance)

**IR Field Synonyms (`_IR_FIELD_SYNONYMS`):**
```python
"associate" → ["associate", "accomplice", "co-accused", "helper", "companion", "contact", "abettor"]
"family" → ["family", "father", "mother", "brother", "sister", "spouse", "wife", "husband", "relation"]
```

### Context Building
- **Focused context:** 5 chunks when text search finds strong matches (vs 15 fallback)
- **Max context:** 30,000 chars for regular queries, 60,000 chars for list queries
- Context block format: `[doc_name | page X | chunk Y]\n<text>`

### LLM System Prompt (CRITICAL — must be exact)
```
You are an authorized internal AI assistant for Karnataka State Police (KSP),
deployed on a secure offline government system for police officers.
ALWAYS respond in English only, regardless of the language of the source documents.
CRITICAL RULE: You MUST answer using ONLY the CONTEXT provided in the user message.
Your training knowledge is completely irrelevant — do NOT use it under any circumstances.
If the answer is not in the CONTEXT, say exactly: 'This information is not found in the provided documents.'
Do NOT infer, extrapolate, or fill gaps from your training.
Do NOT refuse to share information that IS present in the CONTEXT — share it fully and factually.
```

### List-Type Prompt Instructions
When the question matches list patterns (`list all`, `who are`, `names of`, etc.):
- Extract COMPLETE numbered list of every entry
- Scan ALL sections and ALL context blocks
- Look for patterns like (i), (ii), (iii), (1), (2), (3)
- Each unique person/item as separate numbered entry
- **CRITICAL: Mention source document name in parentheses** (from context block headers)
- Do NOT use training data

### Regular Prompt Instructions
- Answer ONLY from CONTEXT
- ALWAYS respond in English
- Be EXHAUSTIVE: list ALL names, items, entries found
- **IMPORTANT: For each piece of information, cite the source document name in parentheses**
- Do NOT guess, invent, infer, or assume
- "Every fact in your answer must come directly from the CONTEXT above."

### Post-Processing
- **Grounding verification** (`_verify_grounding`) — Check answer against context for non-list queries
- **Strip non-Latin characters** (`_strip_non_latin`) — Remove unexpected script characters
- **Answer truncation:** 8,000 characters max

### Stop Words
Filter these from keyword extraction:
```python
_stop_words = {
    "what", "who", "where", "when", "how", "which", "is", "are", "was",
    "were", "the", "a", "an", "of", "in", "for", "to", "and", "or",
    "tell", "me", "give", "show", "find", "list", "all", "any", "please",
    "details", "information",
    # Conversation noise
    "context", "conversation", "continuing", "ongoing", "resolve",
    "references", "previous", "answer", "question", "section",
    "assistant", "user", "current", "provided", "document", "documents",
}
```

### Temperature
ALL LLM calls use `temperature=0.0` for deterministic, factual responses.

## 3.7 Collection Fallback Logic (in `app.py`)

When `case_id > 0`:

**For `/docs/list`:**
1. Fetch docs from scoped collection (e.g., `SMAC_c1`)
2. Also fetch from global collection (`SMAC`)
3. Merge, deduplicate by `doc_name`

**For `/docs/ask`:**
1. Check if scoped collection has documents
2. If empty: fall back to global unscoped collection
3. Call `ask_pdf()` with determined collection name

This ensures documents indexed with `case_id=0` (bulk indexing) are queryable from any case.

---

# PHASE 4: Entity Graph, Activity Timeline & Location Extraction

## 4.1 Entity Graph — `entity_graph.py`

### Entity Types
`PERSON`, `ORGANIZATION`, `LOCATION`, `PHONE`, `VEHICLE`, `OTHER`

### Noise Name Filter
Skip generic references: "myself", "the accused", "the suspect", "unknown", "n/a", "nil", etc.

### Entity Extraction — `extract_and_store_entities(doc_chunks, doc_id, doc_name, case_id, progress_callback)`

1. Cap chunks at 60 per document (`MAX_ENTITY_CHUNKS`), evenly sampled if more
2. Process in batches of 5 chunks
3. LLM prompt: Extract entities AND relationships as JSON:
```json
{
  "entities": [{"name": "Amit Sharma", "type": "PERSON", "context": "..."}],
  "relationships": [{"source": "Amit Sharma", "target": "Tech Lab", "type": "MEMBER_OF", "context": "..."}]
}
```
4. The prompt explicitly lists all 23 relationship types so LLM assigns the most specific one
5. Robust JSON parsing: handle truncated JSON, find balanced `{...}` objects
6. MERGE entities (upsert): `INSERT ... ON DUPLICATE KEY UPDATE` on `(name, type, doc_id)`
7. MERGE relationships: check for existing before insert
8. Cross-batch deduplication via `seen_entity_keys` set
9. Call `progress_callback(batch_done, batch_total)` after each batch

### Graph Data API — `get_graph_data(case_id, type_filter, search, limit)`
1. Fetch entities with optional type/search filter
2. Fetch all relationships between those entities
3. Return `{"nodes": [...], "edges": [...]}` with array-index IDs (0, 1, 2...)
4. Nodes include: `name`, `type`, `doc_names` (list), `mention_count`
5. Edges include: `source` (index), `target` (index), `type`, `context`

### Clear — `clear_graph_data(case_id)`
Delete entities and relationships for a specific case or all.

## 4.2 Activity Timeline — `activity_timeline.py`

### Activity Extraction — `extract_and_store_activities(doc_chunks, ...)`

1. Process chunks in batches of 3
2. LLM prompt: Extract activities and cross-references as JSON:
```json
{
  "activities": [
    {"tms_id": "TMS-2025-0412", "date": "Mar 18 2025", "group_name": "...",
     "subject": "...", "description": "...", "temporal_status": "PAST",
     "priority": "HIGH", "theatre": "...", "participants": "name1, name2",
     "activity_type": "SURVEILLANCE"}
  ],
  "cross_references": [
    {"source_tms_id": "TMS-2025-0687", "target_tms_id": "TMS-2025-0412", "context": "..."}
  ]
}
```
3. Temporal statuses: `PAST`, `CURRENT`, `FUTURE`
4. Incremental: skip documents that already have extracted activities (`get_extracted_doc_ids()`)

### Bread Crumb Trail — `get_breadcrumb_trail(tms_id, case_id)`
Follow cross-references recursively from a TMS ID. Return chain of linked activities.

### Timeline Data — `get_timeline_data(case_id, group_filter, date_from, date_to)`
Return activities sorted by date with optional filters.

### Groups — `get_groups(case_id)`
Return distinct group names with activity counts.

## 4.3 Location Extractor — `location_extractor.py`

### Location Extraction — `extract_and_store_locations(doc_chunks, ...)`

1. IR documents only
2. LLM prompt: Extract addresses and person-address associations
3. Returns: `[{"person_name": "...", "address_text": "...", "address_type": "PERMANENT|PRESENT|OTHER"}]`

### Offline Geocoding — `geocode(address_text)`

Bundled India geocoding dictionary with coordinates for:
- All 30 Karnataka districts (with alternate spellings: Bangalore/Bengaluru, Mysore/Mysuru, etc.)
- ~30 Bangalore localities (Koramangala, Jayanagar, Whitefield, etc.)
- ~30 major Indian cities (Delhi, Mumbai, Chennai, Hyderabad, Kolkata, etc.)

Match: tokenize address, check each word against dictionary, return lat/lng.

### Location Data — `get_all_locations(case_id)`
Return all geocoded locations for map rendering.

---

# PHASE 5: Frontend — React UI with 3 Tabs

## 5.1 Project Setup

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install axios react-force-graph-2d topojson-client jspdf
```

Frontend `.env`:
```
VITE_API_BASE=http://localhost:8001
```

## 5.2 Three-Tab Layout

Single-page app (`App.tsx`, ~2000+ lines) with:

### Tab 1: Document Intelligence
- **Login/Register** forms (username + password)
- **Case selector** dropdown (create/switch cases)
- **Collection toggle** (SMAC / IR)
- **File upload** area (drag & drop or file picker, accepts .pdf/.docx/.doc/.xlsx/.csv)
- **Upload progress** bar (per-file)
- **Indexed documents** list (with delete)
- **Question input** with send button
- **Voice input** (mic button → MediaRecorder → POST /docs/transcribe → auto-submit)
- **Answer display** area with markdown rendering
- **Answer rating bar**: 5 buttons (+2, +1, 0, -1, -2) shown after each answer
- **Conversation history** display (question + answer pairs)
- **PDF export** button (download conversation as PDF via jsPDF)
- **Microphone device selector** dropdown (when multiple audio inputs)
- **Audio level meter** (real-time via Web Audio API AnalyserNode)

### Tab 2: Connections Map
- **Entity graph** visualization (react-force-graph-2d)
  - Nodes colored by type (PERSON=blue, ORGANIZATION=green, LOCATION=red, etc.)
  - Edges labeled with relationship type
  - Click node to see details (name, type, document sources)
  - Search/filter controls
- **Extract entities** button (POST /graph/extract-all with progress polling)
- **Location map** (world map using TopoJSON + SVG)
  - Map pins at geocoded coordinates
  - Hover/click for address details

### Tab 3: Activity Timeline
- **Timeline visualization** (vertical timeline)
  - Activities sorted by date
  - Color-coded by temporal status (PAST=gray, CURRENT=blue, FUTURE=green)
  - Group filter dropdown
  - Date range filter
- **Extract timeline** button (POST /timeline/extract-all with progress polling)
- **Bread Crumb trail** (click TMS ID → shows linked activity chain)

## 5.3 API Integration

All API calls include JWT Bearer token:
```typescript
const apiFetch = async (path: string, options: RequestInit = {}) => {
  const token = localStorage.getItem("token");
  const headers = {
    ...options.headers,
    "Authorization": `Bearer ${token}`,
    "Content-Type": "application/json",
  };
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  return res.json();
};
```

## 5.4 Voice Q&A Flow
1. User clicks mic → `navigator.mediaDevices.getUserMedia({ audio: { deviceId: selectedDevice } })`
2. `MediaRecorder` records audio as WebM/Opus
3. On stop: send blob to `POST /docs/transcribe`
4. Display transcription in question input
5. Auto-submit as question to `POST /docs/ask`
6. Display answer + speak aloud via `window.speechSynthesis`

## 5.5 Answer Rating UI
After each answer, show a rating bar:
```
Rate: [+2] [+1] [0] [-1] [-2]
```
- Buttons styled: +2/+1 = green shades, 0 = gray, -1/-2 = red shades
- On click: `POST /ratings` with question, answer, rating, collection, case_id
- Show "Thanks!" confirmation after submission
- Reset rating on new answer

## 5.6 Styles — `App.css`

Key CSS classes:
- `.rating-bar` — flex container, centered, gap 8px, margin-top 10px
- `.rating-btn` — 36px × 36px buttons, rounded, border, cursor pointer
- `.rating-positive` — green shades (#4CAF50, #8BC34A)
- `.rating-neutral` — gray (#9E9E9E)
- `.rating-negative` — red shades (#FF9800, #F44336)
- `.rating-active` — highlighted with box-shadow
- `.rating-thanks` — green text, fade-in

---

# PHASE 6: Bulk Indexing, Testing & Deployment

## 6.1 Bulk SMAC Indexer — `dbscripts/bulk_index_smac.py`

Multi-threaded script to index many SMAC PDFs at once.

### Features
- **Auto-resume:** Progress tracked in SQLite DB (`.smac_bulk_progress.db`). Each file's status: `pending`, `processing`, `done`, `error`.
- **JWT auth:** Logs in via `/auth/login` to get token
- **Multi-threaded:** Configurable worker count (default 3, recommended 5)
- **Per-file indexing:** Calls `POST /docs/upload` for each PDF

### Command
```bash
cd ISDDocumentIntelligence_V5/dbscripts
python bulk_index_smac.py --folder "C:\path\to\pdfs" --case-id 0 --username user --password pass --workers 5
```

### Auto-Resume
- On startup: scan folder for all `.pdf` files
- Check SQLite: skip files already marked `done`
- On success: mark `done` in SQLite
- On error: mark `error` with error message
- Re-running same command resumes from where it left off

## 6.2 FastAPI Application — `app.py`

### App Setup
```python
app = FastAPI(title="ISD Document Intelligence V5")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_router)
app.include_router(cases_router)
```

### All Endpoints (30+)

**Health:** `GET /health`

**Documents:**
- `POST /docs/upload` — Upload and index document (file + collection + case_id)
- `GET /docs/list` — List indexed docs (with collection fallback)
- `POST /docs/ask` — RAG Q&A (with collection fallback)
- `POST /docs/clear` — Clear all docs in collection
- `POST /docs/extract-entities` — Extract entities from recent uploads
- `POST /docs/agent` — Multi-document cross-comparison Q&A
- `POST /docs/transcribe` — Transcribe audio (WebM → WAV → Whisper)
- `POST /docs/voice-ask` — Combined STT + Q&A

**Entity Graph:**
- `POST /graph/extract-all` — Extract all entities (background thread with progress)
- `GET /graph/extraction-status` — Poll progress
- `GET /graph/entities` — Get entities (with type filter)
- `GET /graph/data` — Get nodes + edges for visualization
- `DELETE /graph/clear` — Clear graph data

**Timeline:**
- `POST /timeline/extract-all` — Extract activities (background, incremental)
- `GET /timeline/extraction-status` — Poll progress
- `GET /timeline/data` — Get activities (with group/date filters)
- `GET /timeline/breadcrumb` — Get Bread Crumb trail for TMS ID
- `GET /timeline/groups` — Get group names with counts

**Locations:**
- `POST /locations/extract-all` — Extract locations (background, incremental)
- `GET /locations/extraction-status` — Poll progress
- `GET /locations/data` — Get geocoded locations

**Structured Data:**
- `GET /structured/smac` — List SMAC reports
- `GET /structured/smac/{doc_id}` — Get SMAC report details
- `GET /structured/ir` — List IR reports
- `GET /structured/ir/{doc_id}` — Get IR report fields
- `POST /structured/query` — NL-to-SQL query

**Ratings:**
- `POST /ratings` — Submit answer rating (+2 to -2). Store Q&A only for ratings ≥ 1.
- `GET /ratings/stats` — Aggregated rating counts

### Background Extraction Pattern
Entity, timeline, and location extractions run in background threads:
```python
_extraction_status = {"running": False, "done": 0, "total": 0, "error": None}

@app.post("/graph/extract-all")
def extract_all(collection, case_id, current_user):
    if _extraction_status["running"]:
        raise HTTPException(409, "Extraction already running")
    _extraction_status.update(running=True, done=0, total=0, error=None)
    thread = threading.Thread(target=_run_extraction, args=(...))
    thread.start()
    return {"ok": True, "message": "Started"}
```

### Whisper STT — Lazy Loading + GPU Auto-Detection
```python
_whisper_model = None
def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        import torch
        if torch.cuda.is_available():
            _whisper_model = WhisperModel(WHISPER_MODEL, device="cuda", compute_type="float16")
        else:
            _whisper_model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return _whisper_model
```

### Audio Conversion (WebM → WAV)
Use PyAV (Python ffmpeg bindings) to convert browser WebM/Opus to 16kHz mono WAV:
```python
def _convert_to_wav16k(input_bytes: bytes) -> str:
    # Save to temp file, open with av, resample to 16kHz mono, save as WAV
```

### Whisper Hallucination Filter
```python
HALLUCINATIONS = {"", "thank you", "thanks for watching", "subscribe", "you", "bye"}
```

## 6.3 Deployment

### Development
```bash
# Terminal 1: Ollama
set OLLAMA_GPU_LAYERS=999
ollama serve

# Terminal 2: Backend
cd ISDDocumentIntelligence_V5/backend
uvicorn app:app --reload --port 8001

# Terminal 3: Frontend
cd ISDDocumentIntelligence_V5/frontend
npm run dev
```

### Production
```bash
# Backend (gunicorn)
gunicorn app:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8001

# Frontend (build + serve)
npm run build
# Serve dist/ with nginx or similar
```

### GPU Notes
- **After reboot:** Ollama may fall back to CPU. Set `OLLAMA_GPU_LAYERS=999` before `ollama serve`.
- **Warm up models:** `ollama run gemma3:12b "hello"` and `ollama run mxbai-embed-large "hello"`
- **Verify GPU:** `ollama ps` should show `100% GPU`

---

## CRITICAL DESIGN PRINCIPLES

1. **Temperature = 0 everywhere** — All LLM calls use `temperature=0.0` for factual accuracy
2. **Less context = better answers** — 5 focused chunks dramatically outperform 15 loosely-related chunks with smaller LLMs
3. **Hybrid search always** — Never rely on vector search alone. BM25 catches exact matches (phone numbers, case IDs) that semantic search misses.
4. **Fallback chains** — Scoped → global collections, batch → single embedding, Docling → pypdf
5. **Module-level bootstrap** — All `init_db()` functions run at import time so tables exist before any request
6. **Stateless Q&A** — No conversation history prepended (causes keyword noise and zero-vector embeddings)
7. **English-only responses** — All system prompts include "Always respond in English only"
8. **Anti-hallucination prompts** — "ONLY use CONTEXT", "Do NOT use training knowledge", "If not found, say so"
9. **Source citations** — Every answer must cite source document names in parentheses
10. **VARCHAR(255) for UNIQUE keys** — MySQL utf8mb4 key length constraint
11. **INSERT IGNORE / ON DUPLICATE KEY UPDATE** — Idempotent upserts for re-indexing safety
12. **Incremental extraction** — Skip already-processed documents for entity/timeline/location extraction
13. **Offline everything** — No internet calls anywhere in the pipeline
