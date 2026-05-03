# Architecture — ISD Document Intelligence V6

## System Overview

```
                          ┌──────────────────┐
                          │   React 19 SPA   │
                          │   (port 5176)    │
                          └────────┬─────────┘
                                   │ HTTP (fetch)
                          ┌────────▼─────────┐
                          │  FastAPI Server   │
                          │   (port 8003)     │
                          └──┬───┬───┬───┬───┘
                             │   │   │   │
              ┌──────────────┘   │   │   └──────────────┐
              │                  │   │                   │
     ┌────────▼────────┐  ┌─────▼───▼─────┐   ┌────────▼────────┐
     │  Ollama (LLM)   │  │    MySQL 8+    │   │    ChromaDB     │
     │  gemma3:12b     │  │ ISDIntelligence│   │  (persistent)   │
     │  (port 11434)   │  │                │   │                 │
     └─────────────────┘  └────────────────┘   └─────────────────┘
```

**Data flow:**
1. User uploads document via frontend → FastAPI `/docs/upload`
2. Backend routes to IR or SMAC pipeline based on `collection` parameter
3. Document parsed → chunks embedded → stored in ChromaDB + structured fields in MySQL
4. Knowledge extraction (entities, timeline, locations) runs as background tasks via LLM
5. Q&A: user question → hybrid search (vector + BM25) → LLM generates answer from context
6. Frontend visualizes: chat Q&A, entity graph, activity timeline, location map

---

## Document Pipelines

### IR Pipeline (Interrogation Reports)

```
DOCX/DOC/PDF file
    │
    ▼
ir_parser.py (pure Python, no LLM)
    │  ├─ parse_ir_docx(): python-docx table extraction
    │  ├─ parse_ir_pdf(): pypdf + regex pattern matching
    │  └─ _convert_doc_to_docx(): Word COM automation (Windows)
    │
    ▼
List of {serial_no, field_key, field_value} + accused_name
    │
    ├──▶ MySQL ir_reports (EAV table)
    └──▶ ChromaDB IR_db collection (each field as a chunk)
```

**IR Parser details (ir_parser.py):**
- Expects 3-column table structure: `[Serial No | Field Name | Value]`
- Handles merged cells in DOCX (deduplicates adjacent identical cells)
- Cleans encoding artifacts: smart quotes, em-dashes, replacement chars
- NIL value filter: `-`, `nil`, `n/a`, `none`, `not available`, etc. → empty string
- Extracts accused name from fields containing "name" + "accused"
- Three row patterns: serial+key+value, empty-serial+key+value, header-style rows

**IR Q&A flow (rag_ir.py):**
1. LLM extracts person name from question (temp=0.0)
2. AND-match: all name words must exist in doc_name
3. If multiple matches → return list for user selection
4. LLM identifies relevant field serial numbers from question
5. Build focused prompt with only matched fields
6. LLM answers from matched fields only
7. Aggregate queries ("how many", "count", "list all") → NL-to-SQL on ir_reports table

### SMAC Pipeline (Surveillance/Investigation Documents)

```
PDF/DOCX/XLSX/CSV file
    │
    ▼
rag_smac.py → index_document()
    │  ├─ PDF: Docling (tables + text) or pypdf fallback
    │  ├─ DOCX: python-docx (paragraphs + tables)
    │  ├─ XLSX: openpyxl (header detection, row-to-KV, max 300 rows/sheet)
    │  └─ CSV: csv reader (max 500 rows)
    │
    ▼
Raw text units (paragraphs, table rows, etc.)
    │
    ▼
Chunking: 2000 chars, 120 char overlap, min 25 chars
    │
    ├──▶ ChromaDB SMAC collection (embedded chunks + metadata)
    ├──▶ BM25 in-memory index (tokenized chunks)
    └──▶ MySQL smac_reports (optional, if LLM parser enabled)
```

---

## RAG Pipeline — SMAC (Hybrid Search)

### Indexing

| Parameter | Value |
|-----------|-------|
| Chunk size | 2000 characters |
| Overlap | 120 characters |
| Min unit length | 25 characters |
| Max chunks per doc | 800 |
| Embedding batch size | 64 (Ollama) or 256 (sentence-transformers) |

**Metadata per chunk:**
- `doc_id` — UUID
- `doc_name` — original filename
- `chunk_index` — position in document
- `source` — "digital" or "ocr"
- `page` — page number (if available)

### Search Pipeline

```
User Question
    │
    ▼
Multi-Query Expansion (if ENABLE_MULTI_QUERY=true)
    │  Deterministic synonym-based expansion (no LLM randomness)
    │  Generates up to 3 alternative queries
    │
    ├──▶ Vector Search (ChromaDB)          ├──▶ BM25 Keyword Search
    │    top-20 results per query variant  │    top-20 results
    │    cosine similarity                 │    tokenizer: lowercase + regex [a-z0-9]+
    │                                      │
    └───────────┬──────────────────────────┘
                │
                ▼
    Reciprocal Rank Fusion (RRF)
        formula: 1.0 / (k + rank + 1), k=60
        dedup by chunk signature: {doc_id}_{chunk_index}_{first_100_chars}
        top-10 merged results
                │
                ▼
    LLM Re-ranking (if ENABLE_RERANKING=true)
        LLM ranks candidates by relevance
        candidate text truncated to 500 chars
        top-10 re-ranked results
                │
                ▼
    LLM Answer Generation
        model: PDF_MODEL (gemma3:12b)
        temperature: 0.0
        max tokens: 4096
```

### Multi-Document Agent Q&A

Function: `ask_docs_agent(question, history, doc_ids, collection_name)`

1. For each selected document: extract focused context via hybrid search
2. Build reasoning chain with doc-by-doc findings
3. Synthesize final answer from all sources
4. Returns: `{answer, reasoning_chain, used_chunks}`

---

## RAG Pipeline — IR (Field-Based Q&A)

### Single Document Q&A

```
User Question
    │
    ▼
LLM: Extract person name from question
    │
    ▼
MySQL: AND-match name words against doc_name in ir_reports
    │
    ├─ 0 matches → "No matching IR found"
    ├─ 1 match  → proceed to field lookup
    └─ N matches → return list for user to select
    │
    ▼
LLM: Identify relevant field serial numbers
    │
    ▼
MySQL: Fetch matched fields from ir_reports
    │
    ▼
LLM: Answer question from matched fields only
```

### Aggregate Q&A (Cross-Document)

Detects patterns: "how many", "count", "total", "list all", "across all"

```
User Question (aggregate)
    │
    ▼
LLM: Generate MySQL query from schema + question (NL-to-SQL)
    │
    ▼
MySQL: Execute generated query on ir_reports
    │
    ▼
LLM: Format raw results into readable answer
```

---

## MySQL Schema

### users

```sql
CREATE TABLE users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name     VARCHAR(200),
    role          VARCHAR(50) DEFAULT 'user',
    is_active     TINYINT(1) DEFAULT 1,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### cases

```sql
CREATE TABLE cases (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    name        VARCHAR(200) NOT NULL,
    description VARCHAR(500),
    collection  VARCHAR(50) NOT NULL DEFAULT 'IR',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

### smac_reports / ir_reports (EAV)

```sql
CREATE TABLE smac_reports (          -- ir_reports has identical schema
    id          INT AUTO_INCREMENT PRIMARY KEY,
    doc_id      VARCHAR(255) NOT NULL,
    doc_name    VARCHAR(500),
    serial_no   VARCHAR(50),
    field_key   VARCHAR(255) NOT NULL,
    field_value TEXT,
    case_id     INT,
    UNIQUE KEY (doc_id, field_key),
    INDEX (doc_id),
    INDEX (field_key)
);
```

### entities

```sql
CREATE TABLE entities (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    name      VARCHAR(255) NOT NULL,
    type      VARCHAR(100) NOT NULL,
    doc_id    VARCHAR(255) NOT NULL,
    doc_name  VARCHAR(500),
    context   TEXT,
    case_id   INT,
    UNIQUE KEY (name, type, doc_id),
    INDEX (name), INDEX (type), INDEX (doc_id)
);
```

**Entity types:** `PERSON`, `ORGANIZATION`, `LOCATION`, `PHONE`, `VEHICLE`, `OTHER`

### relationships

```sql
CREATE TABLE relationships (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    source_entity_id  INT NOT NULL,
    target_entity_id  INT NOT NULL,
    relationship_type VARCHAR(200) NOT NULL,
    doc_id            VARCHAR(255),
    context           TEXT,
    case_id           INT,
    UNIQUE KEY (source_entity_id, target_entity_id, relationship_type, doc_id),
    FOREIGN KEY (source_entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY (target_entity_id) REFERENCES entities(id) ON DELETE CASCADE
);
```

**Relationship types:**
- Family: `SIBLING`, `SPOUSE`, `PARENT_OF`, `CHILD_OF`
- Employment: `WORKS_AT`, `COLLEAGUE`, `REPORTS_TO`
- Membership: `MEMBER_OF`, `LOCATED_IN`
- Activity: `PARTICIPATED_IN`
- Residence: `LIVES_AT`
- IR-specific: `HELPER_OF`, `ADVOCATE_OF`, `DOCTOR_OF`, `FINANCIER_OF`, `ASSOCIATE_OF`, `ACCOMPLICE_OF`, `HANDLER_OF`, `SYMPATHIZER_OF`, `ACCUSED_WITH`, `CO_ACCUSED`
- Fallback: `RELATED_TO`, `CO_OCCURRENCE`

**CO_OCCURRENCE logic:** Entity pairs extracted from the same document without an explicit relationship get auto-linked as `CO_OCCURRENCE` (capped at 30 per document).

### activities

```sql
CREATE TABLE activities (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    tms_id          VARCHAR(100) NOT NULL,
    doc_id          VARCHAR(500),
    doc_name        VARCHAR(500),
    activity_date   VARCHAR(100),
    group_name      VARCHAR(500),
    subject         VARCHAR(500),
    description     TEXT,
    temporal_status VARCHAR(50),
    priority        VARCHAR(100),
    theatre         VARCHAR(200),
    participants    TEXT,
    case_id         INT,
    UNIQUE KEY (tms_id, doc_id),
    INDEX (tms_id), INDEX (group_name), INDEX (activity_date), INDEX (doc_id)
);
```

**Temporal statuses:** `PAST` (completed), `CURRENT` (ongoing), `FUTURE` (planned)

**Theatre values:** `OSINT`, `HUMINT`, `Social Media`, `Technical Surveillance`, etc.

### cross_references

```sql
CREATE TABLE cross_references (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    source_tms_id  VARCHAR(100) NOT NULL,
    target_tms_id  VARCHAR(100) NOT NULL,
    context        VARCHAR(500),
    doc_id         VARCHAR(255),
    case_id        INT,
    UNIQUE KEY (source_tms_id, target_tms_id, doc_id),
    INDEX (source_tms_id), INDEX (target_tms_id)
);
```

### doc_locations

```sql
CREATE TABLE doc_locations (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    doc_id       VARCHAR(255) NOT NULL,
    doc_name     VARCHAR(500),
    person_name  VARCHAR(200),
    address_text TEXT,
    city         VARCHAR(200),
    locality     VARCHAR(200),
    lat          DOUBLE,
    lng          DOUBLE,
    address_type VARCHAR(50),
    case_id      INT,
    UNIQUE KEY (doc_id, person_name, address_type),
    INDEX (doc_id), INDEX (city), INDEX (lat)
);
```

**Address types:** `PERMANENT`, `PRESENT`, `PREVIOUS`, `OTHER`, `HIDEOUT`, `RESIDENCE`, `OFFICE`

---

## ChromaDB Collections

| Collection | Naming | Content | Metadata |
|------------|--------|---------|----------|
| SMAC (global) | `SMAC` | Document chunks (2000-char) | doc_id, doc_name, chunk_index, source, page |
| SMAC (case-scoped) | `SMAC_c{case_id}` | Same as above | Same + case_id |
| IR (global) | `IR_db` | IR fields as "field_key: field_value" | doc_id, doc_name, serial_no, field_key |
| IR (case-scoped) | `IR_c{case_id}` | Same as above | Same + case_id |

**Client:** `chromadb.PersistentClient(path=CHROMA_PATH_*)` — always persistent, never ephemeral.

**BM25 cache:** In-memory dict `_bm25[collection_name]` with `{docs, metas, index}`. Rebuilt on document addition. Uses simple tokenizer: `lowercase + regex [a-z0-9]+`.

---

## Entity Graph Extraction

**Module:** `entity_graph.py`

**Extraction flow:**
1. Chunks batched (5 per LLM call) for manageable prompt size
2. LLM prompt instructs extraction of named entities AND typed relationships
3. Response parsed as JSON: `{entities: [...], relationships: [...]}`
4. Filtering: noise names removed ("myself", "he", "she", "unknown", "n/a")
5. Compound names split: "Amit, Rohit and Sunil" → 3 separate entities
6. Minimum name length: 2 characters
7. Stored via `INSERT IGNORE` for idempotency
8. CO_OCCURRENCE edges added for entity pairs without explicit relationships (max 30)

**Graph retrieval:** `get_graph_data(case_id, doc_id)` returns `{nodes: [...], edges: [...]}` filtered by case and/or document.

---

## Activity Timeline Extraction

**Module:** `activity_timeline.py`

**Extraction flow:**
1. Chunks batched (3 per LLM call)
2. LLM extracts activities with TMS IDs (Temporal Movement Sequence)
3. Each activity: date, group, subject, description, temporal status, priority, theatre, participants
4. Cross-references link related activities (source_tms_id → target_tms_id with context)
5. Stored with `INSERT IGNORE` for idempotency

**Breadcrumb trail:** `get_breadcrumb_trail(tms_id)` follows cross-reference chain to build a linked sequence of related activities.

---

## Location Extraction

**Module:** `location_extractor.py`

**Geocoding approach:** Fully offline using an embedded Python dictionary.

**Coverage:**
- 31 Karnataka districts (Bangalore, Mysore, Hubli, Davangere, etc.)
- 50+ Bangalore localities (Frazer Town, Hebbal, Koramangala, HSR Layout, etc.)
- 200+ major Indian cities

**Flow:**
1. LLM extracts addresses + person names from document chunks
2. Geocoder matches city/locality names against dictionary
3. Returns lat/lng coordinates for map visualization
4. No external API dependency

---

## Authentication & Case Isolation

**Module:** `auth.py`

| Setting | Value |
|---------|-------|
| Password hashing | bcrypt (via passlib CryptContext) |
| JWT algorithm | HS256 |
| Token expiry | 24 hours (configurable) |
| Token payload | `{sub: user_id, username, role, exp}` |

**Protected route pattern:**
```python
@app.get("/some-route")
async def some_route(user: CurrentUser = Depends(get_current_user)):
    ...
```

**Module:** `cases.py`

**Case isolation model:**
- Each user owns multiple cases
- Each case belongs to one collection type: "IR" or "SMAC"
- Documents are indexed within scoped collections: `SMAC_c{case_id}` or `IR_c{case_id}`
- All MySQL queries filter by `case_id`
- Authorization check: `_get_case_for_user(case_id, user_id)` → raises HTTP 403 if not owner

---

## Ollama Client

**Module:** `ollama_client.py`

### LLM Chat
- Function: `ollama_chat(messages, temperature=0.0, model=PDF_MODEL)`
- Endpoint: `{OLLAMA_BASE_URL}/api/chat`
- Options: `{temperature: 0.0, num_predict: 4096}`
- Always `stream: false`

### Embeddings — Two Modes

**Mode 1: Ollama HTTP** (`USE_OLLAMA_EMBEDDINGS=true`)
- Endpoint: `/api/embed` (batch) or `/api/embeddings` (single fallback)
- Batch size: 64 texts per request
- Retry: 3 attempts with exponential backoff (2s, 4s, 6s)
- Fallback: if batch fails, retries individual texts
- Zero-vector placeholder for failed chunks

**Mode 2: sentence-transformers GPU** (`USE_OLLAMA_EMBEDDINGS=false`)
- Model: `mixedbread-ai/mxbai-embed-large-v1`
- Device: CUDA GPU if available, else CPU
- Batch size: 256 texts
- Progress bar for batches > 100 texts
- Returns normalized embeddings
- Significantly faster than Ollama HTTP

---

## LLM Key-Value Extractor

**Module:** `llm_kv_extractor.py`

**PDF processing:**
- Primary: Docling with OCR disabled, table structure enabled (TableFormer ACCURATE mode)
- Fallback: pypdf raw text extraction
- Memory optimized: no image generation

**DOCX processing:**
- python-docx XML parsing for text + tables
- Table rows → "Header: Value | Header: Value" format

**LLM extraction:**
- Separate system prompts for IR Form-16 vs SMAC Log Reports
- Handles 2/3/4-column tables, multi-line values, continuation rows

**JSON response parsing (5 strategies):**
1. Direct JSON parse
2. Strip markdown code fences, then parse
3. Regex extract `[...]` array
4. Fix common errors (trailing commas, single quotes)
5. Recover truncated JSON (LLM ran out of tokens mid-array)

---

## Frontend Architecture

**Module:** `frontend/src/App.tsx` (single monolithic component)

### Tabs

| Tab | Features | Key API Calls |
|-----|----------|---------------|
| **Document Intelligence** | File upload, Q&A chat, voice I/O, spell-check, IR doc selection, PDF export | `/docs/upload`, `/docs/ask`, `/docs/transcribe`, `/spell-check` |
| **Connections Map (Graph)** | Force-directed graph, entity type filtering, node details, search | `/graph/data`, `/graph/extract-all`, `/graph/extraction-status` |
| **Connections Map (Map)** | Location markers on map, person-address mapping | `/locations/data`, `/locations/extract-all`, `/locations/extraction-status` |
| **Activity Timeline** | Chronological events, group filtering, breadcrumb trails, cross-refs | `/timeline/data`, `/timeline/groups`, `/timeline/extract-all`, `/timeline/breadcrumb` |
| **Translation** | Upload IR DOCX, extract Kannada narrative, translate to English via TranslateGemma, download translated DOCX | `/translate/upload`, `/translate/text`, `/translate/download` |
| **QA Testing** | Bulk-run prompts against indexed docs for quality regression | (internal QA endpoints) |

### State Management
- React `useState` hooks for all state (no external state library)
- `useRef` for polling interval handles (pollRef, timelinePollRef, locationPollRef, qaPollRef)
- JWT token persisted in `localStorage` as `isd_token`

### Async Polling
- Entity/timeline/location extraction: 3-second polling intervals
- QA testing: 2-second polling interval
- Polling starts on extraction trigger, stops on completion

### Styling
- KSP brand colors: `--ksp-yellow: #ffd400`, `--ksp-navy: #0b2c4a`, `--ksp-red: #b10000`
- Font: Inter (Google Fonts)
- Layout: flexbox sidebar (280px) + main content area
- Card pattern: white background, 14px border-radius, shadow

---

## Bulk Indexing Architecture

### SMAC — Parallel (bulk_index_smac.py)

| Setting | Value |
|---------|-------|
| Parallelism | ThreadPoolExecutor (default 3 workers) |
| Progress DB | `.smac_bulk_progress.db` (SQLite) |
| JWT refresh | Auto-refresh 1 hour before 24h expiry |
| Timeout | 600 seconds per file |
| Skip list | report, reports, feedback, attachment, attachments |

**Progress schema:**
```sql
CREATE TABLE progress (
    file_path TEXT PRIMARY KEY,
    status    TEXT DEFAULT 'pending',   -- pending | done | failed
    doc_id    TEXT,
    attempts  INTEGER DEFAULT 0,
    error     TEXT,
    updated   TEXT                      -- ISO datetime
);
```

**Flow:** Scan folder → deduplicate → filter → register pending → ThreadPoolExecutor → POST `/docs/upload` → mark done/failed → write final report + failures log

**Outputs:**
- `.smac_bulk_progress_failures.txt` — failed files list
- `logfiles/bulk_index_smac.log` — detailed log
- `pdfs_pending_ocr.txt` — scanned PDFs with 0 chunks (for OCR pipeline)

### IR — Sequential (bulk_index_ir.py)

| Setting | Value |
|---------|-------|
| Parallelism | Single-threaded |
| Progress DB | `.ir_bulk_progress.db` (SQLite) |
| Timeout | 120 seconds per file |
| Duplicate check | Backend rejects files already indexed by filename |

### OCR — Scanned PDFs (ocr_index_smac.py)

| Setting | Value |
|---------|-------|
| Input | `pdfs_pending_ocr.txt` (from bulk_index_smac.py) |
| OCR engine | Docling with OCR enabled |
| Table extraction | TableFormer ACCURATE mode |
| Progress DB | `.smac_ocr_progress.db` (SQLite) |
| Max chunks | 800 per document |
| Min chunk length | 10 characters |

**Flow:** Read pending OCR list → Docling OCR extraction → table formatting → chunking (2000 chars, 140 overlap) → embed → store in ChromaDB + MySQL

---

## API Reference

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Create user account |
| POST | `/auth/login` | Login, returns JWT token |
| GET | `/auth/me` | Get current user info |
| POST | `/auth/change-password` | Change password |

### Case Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/cases` | List user's cases |
| POST | `/cases` | Create new case |
| GET | `/cases/{case_id}` | Get single case |
| PUT | `/cases/{case_id}` | Update case |
| DELETE | `/cases/{case_id}` | Delete case |

### Document Upload & Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/docs/upload` | Upload and index document (PDF/DOCX/DOC/XLSX/CSV) |
| GET | `/docs/list` | List indexed documents (`?collection=SMAC&case_id=0`) |
| POST | `/docs/clear` | Clear all documents from collection |

### Q&A
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ask` | Ask question about a document |
| POST | `/ask-docs-agent` | Multi-document agent Q&A |

### Entity Graph
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/graph/data` | Get graph nodes + edges |
| POST | `/graph/extract-all` | Trigger entity extraction |
| GET | `/graph/extraction-status` | Poll extraction progress |

### Activity Timeline
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/timeline` | Get timeline activities |
| GET | `/timeline/breadcrumb` | Get breadcrumb trail for TMS ID |
| GET | `/timeline/groups` | Get grouped activities |
| POST | `/timeline/extract` | Trigger timeline extraction |
| GET | `/timeline/extraction-status` | Poll extraction progress |

### Locations
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/locations` | Get geocoded locations |
| POST | `/locations/extract` | Trigger location extraction |
| GET | `/locations/extraction-status` | Poll extraction progress |

### Structured Data
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/structured/smac-reports` | List all SMAC report summaries |
| GET | `/structured/smac-reports/{doc_id}` | Get fields for specific SMAC doc |
| GET | `/structured/ir-reports` | List all IR report summaries |
| GET | `/structured/ir-reports/{doc_id}` | Get fields for specific IR doc |
| GET | `/structured/schema` | Get table schema DDL (for NL-to-SQL) |

### Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Service health check |
