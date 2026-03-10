# ISD Document Intelligence V5 — Architecture & Design Best Practices

## 1. System Overview

ISD Document Intelligence V5 is a standalone, fully offline AI-powered document analysis system built for Karnataka State Police (KSP). It allows officers to upload case documents (PDF, DOCX, DOC, XLSX, CSV), index them into a local vector database, store structured fields in MySQL, extract entity relationships and activity timelines using LLM, and query them using text or voice — all without any internet connectivity or cloud dependency.

**V5 Key Changes (from V4):**
- **Database:** Migrated from MSSQL (SQL Server) to **MySQL 8.x** for cross-platform compatibility
- **Answer Rating System:** 5-point scale (+2 to -2) for UAT feedback collection
- **Source Citations:** LLM responses cite source document names in parentheses
- **Case-Scoped Collection Fallback:** Queries automatically fall back to global collections when case-scoped collections are empty
- **ChromaDB Path:** Renamed from `chroma_db_v4` to `chroma_db_v5`

### Architecture Diagram

```
+-------------------+         +-------------------+         +------------------+
|                   |  HTTP   |                   |  HTTP   |                  |
|   React Frontend  +-------->+  FastAPI Backend   +-------->+  Ollama (Local)  |
|   (Vite + TS)     |         |  (Python)         |         |  gemma3:12b      |
|                   |         |                   |         |  mxbai-embed-lg  |
+-------------------+         +--------+----------+         +------------------+
                                       |
                    +------------------+------------------+
                    |                  |                  |
           +--------v-------+ +-------v--------+ +------v---------+
           |                | |                | |                |
           |  ChromaDB      | |  MySQL 8.x     | |  faster-whisper|
           |  (Vector Store) | |  (Structured   | |  (Local STT)   |
           |  Persistent on | |   Storage)     | |                |
           |  local disk    | |  ISDIntelligence| |                |
           +----------------+ +----------------+ +----------------+
```

### Technology Stack

| Layer           | Technology                     | Purpose                                      |
|----------------|-------------------------------|----------------------------------------------|
| Frontend       | React 19 + TypeScript + Vite 7 | Single-page UI with 3 tabs                   |
| Backend        | FastAPI (Python)               | REST API, document processing                |
| LLM            | Ollama (local) — gemma3:12b    | Text generation, entity/activity extraction  |
| Embeddings     | mxbai-embed-large (via Ollama) | Vector embeddings for RAG (1024 dimensions)  |
| Vector DB      | ChromaDB (persistent)          | Document chunk storage & retrieval           |
| Structured DB  | MySQL 8.x                      | Structured fields, entities, activities, locations, ratings |
| Auth           | JWT (PyJWT + bcrypt)           | User authentication and session management   |
| STT            | faster-whisper (local)         | Speech-to-text transcription                 |
| TTS            | Browser SpeechSynthesis API    | Text-to-speech (no server needed)            |
| Audio          | PyAV (ffmpeg bindings)         | WebM to WAV audio conversion                 |
| PDF Export     | jsPDF (client-side)            | Conversation history download                |

### Three-Tab UI

| Tab                    | Purpose                                                              |
|-----------------------|----------------------------------------------------------------------|
| Document Intelligence | Upload, index, and query documents via text/voice                    |
| Connections Map       | Entity knowledge graph visualization + location map                  |
| Activity Timeline     | Temporal activity trail with Bread Crumb cross-references            |

### Two Document Collections

| Collection | Document Type                        | Use Case                        |
|-----------|--------------------------------------|---------------------------------|
| SMAC      | Log Reports with TMS IDs             | Activity monitoring, group tracking |
| IR        | Interrogation Reports (Form-16)      | Case investigation, suspect analysis |

---

## 2. Project Structure

```
ISDDocumentIntelligence_V5/
  backend/
    app.py                # FastAPI application with 30+ endpoints
    config.py             # Environment-based configuration (Ollama, MySQL)
    rag.py                # RAG pipeline: indexing, hybrid search, NL-to-SQL
    ollama_client.py      # Ollama API client (chat + batch embedding)
    mysql_db.py           # MySQL connection factory & DB bootstrap
    auth.py               # JWT authentication (register, login, token validation)
    cases.py              # Case management (create, list, switch)
    structured_tables.py  # smac_reports + ir_reports tables (structured storage)
    entity_graph.py       # Entity & relationship extraction (knowledge graph)
    activity_timeline.py  # Activity & cross-reference extraction (timeline)
    location_extractor.py # Address extraction & offline geocoding
    llm_kv_extractor.py   # LLM-based key-value extraction (hybrid doc reading)
    requirements.txt      # Python dependencies
    .env                  # Environment variables (MySQL, Ollama, JWT)
    chroma_db_v5/         # ChromaDB persistent storage (auto-created or migrated)
    debug_audio/          # Debug audio recordings (auto-created)
  frontend/
    index.html            # HTML entry point
    package.json          # Node dependencies
    vite.config.ts        # Vite build configuration
    src/
      main.tsx            # React entry point
      App.tsx             # Main application component
      App.css             # All styles
      index.css           # Global reset styles
      assets/
        ksp_logo.png      # KSP branding logo
        banner_logo.png   # Banner image
  dbscripts/
    bulk_index_smac.py    # Bulk SMAC document indexer (multi-threaded)
    migrate_mssql_to_mysql.py  # V4 (MSSQL) → V5 (MySQL) data migration
  tests/
    conftest.py           # Pytest fixtures
    test_*.py             # Test suites
  test_data/
    generate_test_pdfs.py    # Generate test IR PDFs
    generate_group_reports.py # Generate test SMAC log report PDFs
```

---

## 3. Database Schema

### 3.1 MySQL — ISDIntelligence Database

All structured data is stored in a MySQL database (`ISDIntelligence`) with 10 tables. All tables use `utf8mb4` character set for full Unicode support.

**Important:** VARCHAR columns used in UNIQUE KEY constraints are limited to **VARCHAR(255)** due to MySQL's 3072-byte key length limit with `utf8mb4` (4 bytes/char × 255 = 1020 bytes per column).

#### users (JWT Authentication)

| Column        | Type         | Purpose                          |
|--------------|-------------|----------------------------------|
| id           | INT (PK)     | Auto-increment primary key       |
| username     | VARCHAR(100) | Unique login username            |
| password_hash| VARCHAR(255) | bcrypt-hashed password           |
| full_name    | VARCHAR(200) | Display name                     |
| role         | VARCHAR(50)  | User role (admin/user)           |
| is_active    | TINYINT      | Account active flag              |
| created_at   | DATETIME     | Registration timestamp           |

#### cases (Case Isolation)

| Column      | Type         | Purpose                          |
|------------|-------------|----------------------------------|
| id         | INT (PK)     | Auto-increment primary key       |
| user_id    | INT (FK)     | Owner user ID                    |
| name       | VARCHAR(200) | Case name                        |
| description| TEXT         | Case description                 |
| collection | VARCHAR(50)  | Default collection type          |
| created_at | DATETIME     | Creation timestamp               |

#### smac_reports (Structured SMAC Data — Flat Columnar)

| Column         | Type         | Purpose                          |
|---------------|-------------|----------------------------------|
| id            | INT (PK)     | Auto-increment primary key       |
| doc_id        | VARCHAR(255) | Document identifier (UNIQUE)     |
| doc_name      | VARCHAR(500) | Original filename                |
| input_id      | VARCHAR(100) | TMS input ID                     |
| date_of_receipt| VARCHAR(100)| Date received                    |
| originator    | VARCHAR(200) | Report originator                |
| source_name   | VARCHAR(200) | Source name                      |
| grading       | VARCHAR(50)  | Report grading                   |
| theatre       | VARCHAR(200) | Activity theatre                 |
| priority      | VARCHAR(50)  | Priority level                   |
| subject       | TEXT         | Report subject                   |
| gist          | TEXT         | Report gist/summary              |
| threat_details| TEXT         | Threat details                   |
| shared_with   | TEXT         | Distribution list                |
| classification| VARCHAR(100) | Security classification          |
| raw_fields    | TEXT         | Raw extracted fields (JSON)      |
| indexed_at    | DATETIME     | Indexing timestamp               |

#### ir_reports (Structured IR Data — EAV Key-Value)

| Column      | Type         | Purpose                          |
|------------|-------------|----------------------------------|
| id         | INT (PK)     | Auto-increment primary key       |
| doc_id     | VARCHAR(255) | Document identifier              |
| doc_name   | VARCHAR(500) | Original filename                |
| collection | VARCHAR(50)  | "IR"                             |
| serial_no  | VARCHAR(50)  | Field serial number              |
| field_key  | VARCHAR(255) | Field name (e.g., "Name of Accused") |
| field_value| TEXT         | Field value                      |

UNIQUE KEY on `(doc_id, collection, field_key(255))`

#### entities (Knowledge Graph Nodes)

| Column   | Type         | Purpose                          |
|---------|-------------|----------------------------------|
| id      | INT (PK)     | Auto-increment primary key       |
| name    | VARCHAR(255) | Entity name                      |
| type    | VARCHAR(50)  | PERSON, ORGANIZATION, LOCATION, PHONE, VEHICLE, OTHER |
| doc_id  | VARCHAR(255) | Source document                  |
| doc_name| VARCHAR(500) | Source filename                  |
| context | TEXT         | Surrounding text context         |
| case_id | INT          | Case isolation ID                |

UNIQUE KEY on `(name, type, doc_id)`

#### relationships (Knowledge Graph Edges)

| Column             | Type     | Purpose                          |
|-------------------|---------|----------------------------------|
| id                | INT (PK) | Auto-increment primary key       |
| source_entity_id  | INT (FK) | References entities.id           |
| target_entity_id  | INT (FK) | References entities.id           |
| relationship_type | VARCHAR  | See relationship types below     |
| doc_id            | VARCHAR(255) | Source document              |
| context           | TEXT     | Surrounding text context         |
| case_id           | INT      | Case isolation ID                |

**Relationship types:** MEMBER_OF, WORKS_AT, SIBLING, SPOUSE, PARENT_OF, CHILD_OF, LIVES_AT, COLLEAGUE, PARTICIPATED_IN, REPORTS_TO, LOCATED_IN, RELATED_TO, CO_OCCURRENCE, HELPER_OF, ADVOCATE_OF, DOCTOR_OF, FINANCIER_OF, ASSOCIATE_OF, ACCOMPLICE_OF, HANDLER_OF, SYMPATHIZER_OF, ACCUSED_WITH, CO_ACCUSED

#### activities (Timeline Activities)

| Column          | Type     | Purpose                          |
|----------------|---------|----------------------------------|
| id             | INT (PK) | Auto-increment primary key       |
| tms_id         | VARCHAR  | TMS tracking number              |
| doc_id         | VARCHAR  | Source document                  |
| doc_name       | VARCHAR  | Source filename                  |
| activity_date  | VARCHAR  | Date of activity                 |
| group_name     | VARCHAR  | Organizational group             |
| subject        | VARCHAR  | Activity subject line            |
| description    | TEXT     | Full activity description        |
| temporal_status| VARCHAR  | PAST, CURRENT, or FUTURE         |
| priority       | VARCHAR  | Priority level                   |
| theatre        | VARCHAR  | Activity theatre/domain          |
| participants   | TEXT     | Comma-separated participant names |
| activity_type  | VARCHAR  | Activity classification          |
| case_id        | INT      | Case isolation ID                |

#### cross_references (Bread Crumb Links)

| Column         | Type     | Purpose                          |
|---------------|---------|----------------------------------|
| id            | INT (PK) | Auto-increment primary key       |
| source_tms_id | VARCHAR  | Source activity TMS ID           |
| target_tms_id | VARCHAR  | Target activity TMS ID           |
| context       | VARCHAR  | Cross-reference context          |
| doc_id        | VARCHAR(255) | Source document              |
| case_id       | INT      | Case isolation ID                |

#### doc_locations (Geocoded Addresses)

| Column       | Type     | Purpose                          |
|-------------|---------|----------------------------------|
| id          | INT (PK) | Auto-increment primary key       |
| doc_id      | VARCHAR(255) | Source document              |
| doc_name    | VARCHAR  | Source filename                  |
| person_name | VARCHAR(200) | Person associated with address |
| address_text| TEXT     | Full address text                |
| city        | VARCHAR  | City/district                    |
| locality    | VARCHAR  | Locality/area                    |
| lat         | FLOAT    | Latitude (offline geocoded)      |
| lng         | FLOAT    | Longitude (offline geocoded)     |
| address_type| VARCHAR  | Address classification           |
| case_id     | INT      | Case isolation ID                |

#### answer_ratings (UAT Feedback)

| Column      | Type         | Purpose                          |
|------------|-------------|----------------------------------|
| id         | INT (PK)     | Auto-increment primary key       |
| user_id    | INT          | Rater's user ID                  |
| username   | VARCHAR(100) | Rater's username                 |
| collection | VARCHAR(50)  | SMAC or IR                       |
| case_id    | INT          | Case context                     |
| question   | TEXT         | Asked question (stored for +1/+2)|
| answer     | TEXT         | LLM answer (stored for +1/+2)   |
| rating     | INT          | -2, -1, 0, +1, or +2            |
| created_at | DATETIME     | Rating timestamp                 |

### 3.2 ChromaDB (Vector Store)

- Persistent on-disk storage at `chroma_db_v5/`
- Separate collections for SMAC and IR documents
- Case-scoped collection names: `SMAC_c1`, `IR_c2` (case_id > 0), or `SMAC`/`IR` (global, case_id=0)
- Each chunk stored with metadata: `doc_id`, `doc_name`, `page`, `chunk_index`, `field_name` (IR)
- Embedding model: `mxbai-embed-large` (1024 dimensions)
- Used for semantic vector search in the RAG pipeline

---

## 4. Data Flow

### 4.1 Document Indexing Flow

```
User selects files/folder
        |
        v
Frontend filters to .pdf/.docx/.doc/.xlsx/.csv
        |
        v
POST /docs/upload (one file at a time, with progress bar)
  Authorization: Bearer <JWT token>
        |
        v
Backend saves to temp file, detects extension
        |
        v
rag.py: index_document() routes to index_pdf/docx/xlsx/csv
        |
        +-----> Text extraction + chunking (2000 chars, 120 overlap)
        |         - PDF: per-page chunks + table/form line extraction
        |         - DOCX: paragraph chunks + table row extraction
        |         - XLSX: row-to-key-value conversion (Header: Value)
        |         - CSV: row-to-key-value conversion
        |
        +-----> LLM key-value extraction (hybrid document reading)
        |         - DOCX: python-docx (reads XML directly)
        |         - PDF: Docling with OCR disabled, fallback to pypdf
        |         Stored in MySQL smac_reports / ir_reports tables
        |
        v
ollama_embed_batch(): embed all chunks in batches of 64
        |
        v
ChromaDB: store embeddings + metadata (case-scoped collection)
 +  BM25 Index: add tokenized documents for keyword search
        |
        v
Background: entity extraction queued (auto-starts)
        |
        v
Response: { doc_id, doc_name, chunks: N }
```

### 4.2 Question Answering Flow (Hybrid Search + NL-to-SQL)

```
User types question (or speaks via microphone)
        |
        v
POST /docs/ask (with JWT auth, collection, case_id)
        |
        v
rag.py: ask_pdf() -> ask_docs()
        |
        v
COLLECTION FALLBACK:
   If case-scoped collection (e.g., SMAC_c1) is empty,
   automatically fall back to global collection ("SMAC")
        |
        v
SMART ROUTING: Is this an aggregate question?
   "Name all accused", "How many documents", "List all phone numbers"
        |
   +----+----+
   |         |
   YES       NO
   |         |
   v         v
NL-to-SQL   Hybrid RAG Search
Pipeline    (see below)
   |
   v
LLM generates SQL query against smac_reports / ir_reports
   |
   v
Execute SQL -> Format results via LLM -> Return answer
```

**Hybrid RAG Search Pipeline:**

```
Step 1: MULTI-QUERY EXPANSION (if enabled)
   LLM generates 3 alternative phrasings of the question
        |
        v
Step 2: STRUCTURED KEYWORD SEARCH
   Search ir_reports/smac_reports for matching field values
   Uses synonym expansion (e.g., "accused" -> ["name", "accused"])
        |
        v
Step 3: VECTOR SEARCH (for each query variation)
   Embed question -> ChromaDB similarity search (top_k=36)
        |
        v
Step 4: BM25 KEYWORD SEARCH (for each query variation)
   Exact keyword matching for case numbers, account numbers, names
        |
        v
Step 5: RECIPROCAL RANK FUSION (RRF)
   Merge vector + BM25 + structured results, deduplicate, score
        |
        v
Step 6: LLM RE-RANKING (if enabled)
   LLM scores top candidates by relevance, reorders to top 12
        |
        v
Build context blocks with source metadata
        |
        v
ollama_chat(): LLM generates answer with source citations
  "IMPORTANT: cite the source document name in parentheses"
        |
        v
Response: { answer, used_chunks[] }
```

### 4.3 Entity Graph Extraction Flow

```
POST /graph/extract-all (or auto after upload)
   Authorization: Bearer <JWT token>
        |
        v
Retrieve document chunks from ChromaDB (max 60 per doc)
        |
        v
For each document:
  Process chunks in batches of 5
        |
        v
  LLM extracts entities + relationships as JSON
        |
        v
  Store in MySQL: entities + relationships tables (with case_id)
        |
        v
GET /graph/data -> Returns nodes + edges for force-graph visualization
```

### 4.4 Activity Timeline Extraction Flow

```
POST /timeline/extract-all (incremental — skips already-extracted docs)
        |
        v
Retrieve all document chunks from ChromaDB
        |
        v
For each document (not yet extracted):
  Process chunks in batches of 3
        |
        v
  LLM extracts activities + cross-references as JSON
        |
        v
  Store in MySQL: activities + cross_references tables (with case_id)
        |
        v
GET /timeline/data -> Returns activities sorted by date
GET /timeline/breadcrumb?tms_id=X -> Returns Bread Crumb trail
```

### 4.5 Location Extraction Flow

```
POST /locations/extract-all (incremental — IR collection only)
        |
        v
For each IR document (not yet extracted):
  LLM extracts addresses and person-address associations
        |
        v
  Offline geocoding using India district/city dictionary
        |
        v
  Store in MySQL: doc_locations table (with case_id)
        |
        v
GET /locations/data -> Returns geocoded locations for map pins
```

### 4.6 Voice Q&A Flow

```
User clicks mic -> browser MediaRecorder captures audio
        |
        v
Audio blob (WebM/Opus) sent to POST /docs/transcribe
        |
        v
Backend: WebM -> 16kHz mono WAV conversion (PyAV)
        |
        v
faster-whisper: transcribe WAV (GPU if available)
        |
        v
Transcription returned to frontend
        |
        v
Frontend auto-submits transcription as question via /docs/ask
        |
        v
Answer displayed + spoken aloud via SpeechSynthesis API
```

### 4.7 Answer Rating Flow

```
User reads LLM answer
        |
        v
Clicks rating button: +2 (Excellent), +1 (Good), 0 (OK), -1 (Poor), -2 (Wrong)
        |
        v
POST /ratings (with user_id, collection, case_id, question, answer, rating)
        |
        v
Backend stores in MySQL answer_ratings table:
  - Ratings +1 and +2: Store question + answer (training data for future fine-tuning)
  - Ratings 0, -1, -2: Store rating only (no Q&A text)
        |
        v
GET /ratings/stats -> Aggregated rating counts for analytics
```

---

## 5. API Endpoints (30+ total)

### Authentication (3 endpoints)

| Method | Path              | Purpose                                    |
|--------|------------------|--------------------------------------------|
| POST   | `/auth/register` | Register new user                          |
| POST   | `/auth/login`    | Login and receive JWT token                |
| GET    | `/auth/me`       | Get current user info from token           |

### Case Management (3 endpoints)

| Method | Path              | Purpose                                    |
|--------|------------------|--------------------------------------------|
| POST   | `/cases/create`  | Create a new case                          |
| GET    | `/cases/list`    | List user's cases                          |
| GET    | `/cases/{id}`    | Get case details                           |

### Document Management (8 endpoints)

| Method | Path                | Purpose                                    |
|--------|--------------------|--------------------------------------------|
| GET    | `/health`          | System health check                        |
| POST   | `/docs/upload`     | Upload and index a single document         |
| GET    | `/docs/list`       | List indexed documents (by collection)     |
| POST   | `/docs/ask`        | Ask a question (RAG Q&A with hybrid search)|
| POST   | `/docs/transcribe` | Transcribe audio to text (STT only)        |
| POST   | `/docs/voice-ask`  | Combined STT + RAG Q&A in one call         |
| POST   | `/docs/agent`      | Multi-document cross-comparison Q&A        |
| POST   | `/docs/clear`      | Clear all documents, vectors, and related data |

### Entity Graph (6 endpoints)

| Method | Path                       | Purpose                                    |
|--------|---------------------------|--------------------------------------------|
| POST   | `/docs/extract-entities`  | Extract entities from pending uploaded docs |
| POST   | `/graph/extract-all`      | Extract entities from ALL indexed documents|
| GET    | `/graph/extraction-status`| Poll entity extraction progress            |
| GET    | `/graph/entities`         | Get all entities (optional type filter)    |
| GET    | `/graph/data`             | Get graph nodes + edges for visualization  |
| DELETE | `/graph/clear`            | Clear all entity graph data                |

### Activity Timeline (5 endpoints)

| Method | Path                         | Purpose                                  |
|--------|-----------------------------|--------------------------------------------|
| POST   | `/timeline/extract-all`     | Extract activities (incremental)           |
| GET    | `/timeline/extraction-status`| Poll timeline extraction progress         |
| GET    | `/timeline/data`            | Get timeline activities (with filters)     |
| GET    | `/timeline/breadcrumb`      | Get Bread Crumb trail for a TMS ID        |
| GET    | `/timeline/groups`          | Get distinct group names with counts       |

### Location Map (3 endpoints)

| Method | Path                          | Purpose                                  |
|--------|------------------------------|--------------------------------------------|
| POST   | `/locations/extract-all`     | Extract locations from IR documents        |
| GET    | `/locations/extraction-status`| Poll location extraction progress         |
| GET    | `/locations/data`            | Get geocoded locations for map             |

### Structured Data & NL-to-SQL (5 endpoints)

| Method | Path                     | Purpose                                    |
|--------|-------------------------|--------------------------------------------|
| GET    | `/structured/smac`      | List all SMAC reports                      |
| GET    | `/structured/smac/{id}` | Get single SMAC report fields              |
| GET    | `/structured/ir`        | List all IR reports                        |
| GET    | `/structured/ir/{id}`   | Get single IR report with all fields       |
| POST   | `/structured/query`     | Natural Language to SQL query pipeline     |

### Answer Ratings (2 endpoints)

| Method | Path              | Purpose                                    |
|--------|------------------|--------------------------------------------|
| POST   | `/ratings`       | Submit answer rating (+2 to -2)            |
| GET    | `/ratings/stats` | Get aggregated rating statistics           |

---

## 6. Design Best Practices

### 6.1 Dual Structured Tables: Flat (SMAC) + EAV (IR)

**Problem:** SMAC and IR documents have fundamentally different structures. SMAC reports have a fixed set of ~17 fields. IR reports have 50+ variable fields that differ across versions.

**Solution:** Two separate table designs:
- **`smac_reports`** — Flat columnar table with one row per document. Fixed columns for each known field.
- **`ir_reports`** — Entity-Attribute-Value (EAV) table storing each field as a key-value pair. Handles any document structure without schema changes.

```sql
-- SMAC: Direct column access
SELECT subject, originator, priority FROM smac_reports WHERE doc_id = 'doc123'

-- IR: Key-value lookup
SELECT field_key, field_value FROM ir_reports
WHERE doc_id = 'doc123' ORDER BY serial_no
```

**Implementation:** `structured_tables.py` -> `smac_reports` + `ir_reports` tables

---

### 6.2 Case-Scoped ChromaDB Collections with Fallback

**Problem:** Documents indexed with `case_id=0` (bulk indexing) go to global collections (`"SMAC"`, `"IR"`). But the frontend sends the active case ID, creating scoped collection names like `"SMAC_c1"`. When the scoped collection is empty, queries return no results.

**Solution:** Automatic fallback logic in both `docs_list` and `docs_ask`:
1. First query the case-scoped collection (e.g., `SMAC_c1`)
2. If empty, fall back to the global collection (`SMAC`)
3. Merge document lists from both scoped and global collections

```python
_is_smac = collection_name == "SMAC" or collection_name.startswith("SMAC_c")
_is_ir = collection_name == "IR" or collection_name.startswith("IR_c")
```

**Implementation:** `app.py` -> `docs_list()`, `docs_ask()` fallback logic; `rag.py` -> `_is_smac`/`_is_ir` checks

---

### 6.3 Hybrid Search: Structured + Vector + BM25

**Problem:** Vector (semantic) search alone misses exact matches. Searching for account number "1234567890" or name "Mohammed Ali" may fail because embedding similarity cares about meaning, not exact text.

**Solution:** Run THREE search engines in parallel and merge results:
1. **Structured Keyword Search** (MySQL `ir_reports`/`smac_reports`) — exact field value matches with synonym expansion
2. **Vector Search** (ChromaDB) — semantically similar chunks
3. **BM25 Keyword Search** (rank-bm25) — exact keyword matches in full text

Results are merged using **Reciprocal Rank Fusion (RRF)**: `score = 1/(k + rank₁) + 1/(k + rank₂)`.

**Configuration:** `ENABLE_HYBRID_SEARCH=true` in `.env`

**Implementation:** `rag.py` -> `_hybrid_retrieve()`, `_bm25_search()`, `_reciprocal_rank_fusion()`, `search_fields()`

---

### 6.4 Smart Routing: NL-to-SQL for Aggregate Questions

**Problem:** Questions like "Name all accused persons" require aggregating across ALL documents. RAG retrieves only top-k chunks and may miss documents.

**Solution:** Detect aggregate questions and route them to a Natural Language-to-SQL pipeline.

```
"Name all accused" -> LLM generates SQL:
  SELECT DISTINCT doc_name, field_value
  FROM ir_reports
  WHERE field_key LIKE '%accused%'
```

**Detection keywords:** "all", "every", "list", "how many", "count", "total", "across", "each document"

**Implementation:** `rag.py` -> `_is_aggregate_question()`, `_answer_via_sql()`

---

### 6.5 Source Document Citations

**Problem:** When answers span multiple documents, users need to know which document each piece of information comes from.

**Solution:** LLM prompts instruct the model to cite source document names in parentheses, using context block headers.

```
List prompt: "For EACH entry, mention the source document name in parentheses
(from the context block headers like [doc_name | ...])."

Regular prompt: "IMPORTANT: For each piece of information, cite the source
document name in parentheses (from the context block headers like [doc_name | ...])."
```

**Implementation:** `rag.py` -> list and regular prompt templates

---

### 6.6 Answer Rating System (+2 to -2)

**Problem:** During UAT, there's no way to collect user feedback on answer quality for future model improvement.

**Solution:** 5-point rating scale with selective storage:
- **+2 (Excellent)** and **+1 (Good)**: Store question + answer + rating (training data for fine-tuning)
- **0 (OK)**, **-1 (Poor)**, **-2 (Wrong)**: Store rating only (feedback signal without storing potentially wrong Q&A)

```
POST /ratings
{
  "user_id": 1,
  "collection": "SMAC",
  "case_id": 0,
  "question": "Who is the accused?",
  "answer": "The accused is Mohammed Ali (IR_Report_001.docx)",
  "rating": 2
}
```

**Implementation:** `app.py` -> `_init_ratings_table()`, `POST /ratings`, `GET /ratings/stats`; `App.tsx` -> rating bar UI

---

### 6.7 JWT Authentication and Case Isolation

**Problem:** Multiple officers may use the system simultaneously. Documents and cases must be isolated per user.

**Solution:** JWT-based authentication with case-scoped data:
- Users register and login via `/auth/register` and `/auth/login`
- All API calls include `Authorization: Bearer <token>`
- Documents, entities, activities, and locations are scoped by `case_id`
- ChromaDB collections are case-scoped: `SMAC_c1`, `IR_c2`

**Implementation:** `auth.py` -> JWT token generation/validation; `cases.py` -> case CRUD

---

### 6.8 Batch Embedding (GPU Optimization)

**Problem:** Embedding text chunks one-by-one via HTTP to Ollama is slow.

**Solution:** Ollama's `/api/embed` endpoint accepts a list. We send up to 64 texts per request.

```python
# GOOD: 200 chunks = 4 HTTP requests (batch_size=64)
vectors = ollama_embed_batch(chunks, batch_size=64)
```

**Impact:** 10-50x faster indexing.

**Implementation:** `ollama_client.py` -> `ollama_embed_batch()`

---

### 6.9 LLM-Based Key-Value Extraction (Hybrid Document Reading)

**Problem:** Regex-based field extraction fails on complex document layouts (merged cells, nested tables).

**Solution:** Use LLM to extract structured key-value pairs, with hybrid document reading:
- **DOCX**: python-docx (reads XML directly — fast, no ML models)
- **PDF**: Docling with OCR disabled + PyPdfiumDocumentBackend. Falls back to pypdf if Docling fails.

**Toggle:** `USE_LLM_PARSER` in `config.py` (default: true)

**Implementation:** `llm_kv_extractor.py` -> `extract_fields()`, `_read_document()`

---

### 6.10 MySQL VARCHAR(255) Constraint for UNIQUE Keys

**Problem:** MySQL's InnoDB with `utf8mb4` uses 4 bytes per character. A `VARCHAR(500)` in a UNIQUE KEY requires 2000 bytes per column, and multi-column keys easily exceed the 3072-byte limit.

**Solution:** All VARCHAR columns participating in UNIQUE KEY constraints are limited to `VARCHAR(255)` (1020 bytes). Non-keyed columns can remain `VARCHAR(500)` or `TEXT`.

```sql
-- BAD: Exceeds 3072-byte key limit
UNIQUE KEY (name VARCHAR(500), type VARCHAR(100), doc_id VARCHAR(500))

-- GOOD: Within limit (255*4 + 50*4 + 255*4 = 2240 bytes)
UNIQUE KEY (name VARCHAR(255), type VARCHAR(50), doc_id VARCHAR(255))
```

**Implementation:** All table definitions in `entity_graph.py`, `activity_timeline.py`, `location_extractor.py`, `structured_tables.py`

---

### 6.11 GPU Auto-Detection for Whisper STT

**Solution:** Auto-detect CUDA at runtime and select the best device.

```python
import torch
if torch.cuda.is_available():
    model = WhisperModel(name, device="cuda", compute_type="float16")
else:
    model = WhisperModel(name, device="cpu", compute_type="int8")
```

**Implementation:** `app.py` -> `get_whisper_model()`

---

### 6.12 Lazy Model Loading

**Solution:** Singleton pattern that loads models on first use. Fast server startup (< 2 seconds).

**Implementation:** `app.py` -> `get_whisper_model()`

---

### 6.13 Audio Pipeline: WebM to WAV Conversion

**Solution:** Convert audio server-side using PyAV (Python ffmpeg bindings). No system ffmpeg install needed.

**Implementation:** `app.py` -> `_convert_to_wav16k()`

---

### 6.14 Whisper Hallucination Filtering

**Solution:** Blocklist of known hallucination phrases ("thank you", "subscribe", etc.).

**Implementation:** `app.py` -> `docs_transcribe()`

---

### 6.15 Authorized System Prompts for Sensitive Data

**Solution:** System prompt explicitly authorizes the model as an internal KSP tool.

**Implementation:** `rag.py` -> system prompts in `ask_docs()` and `ask_docs_agent()`

---

### 6.16 Zero-Temperature LLM for Factual Accuracy

**Solution:** Use `temperature=0.0` for ALL LLM calls.

**Implementation:** All `ollama_chat()` calls across `rag.py`, `entity_graph.py`, `activity_timeline.py`

---

### 6.17 Entity Graph with Law Enforcement Relationship Types

**Solution:** 23 relationship types including law-enforcement-specific: HELPER_OF, ADVOCATE_OF, DOCTOR_OF, FINANCIER_OF, ASSOCIATE_OF, ACCOMPLICE_OF, HANDLER_OF, SYMPATHIZER_OF, ACCUSED_WITH, CO_ACCUSED.

**Implementation:** `entity_graph.py` -> `extract_entities_and_relationships_from_chunks()`

---

### 6.18 Offline Geocoding for Location Map

**Solution:** Bundled India geocoding dictionary (Karnataka districts, Bangalore localities, major Indian cities).

**Implementation:** `location_extractor.py` -> `geocode()`

---

### 6.19 Incremental Extraction (Skip Already-Processed Documents)

**Solution:** Track which documents have been processed. On extract-all, skip already-done documents.

**Implementation:** `activity_timeline.py`, `location_extractor.py` -> `get_extracted_doc_ids()`

---

### 6.20 Stateless Q&A (No Conversation History)

**Problem:** Prepending conversation history caused keyword extraction noise, zero-vector embeddings, and garbage retrieval.

**Solution:** Each Q&A call is stateless — `payload.question` goes directly to `ask_pdf()`.

**Implementation:** `app.py` -> `/docs/ask` endpoint

---

### 6.21 LLM Accuracy Optimizations (Q&A Pipeline)

A comprehensive set of fixes for the RAG Q&A pipeline:

#### A. Retrieval Accuracy
- **Clean question for keywords** (`raw_question` parameter) — prevents noise from history
- **Expanded stop-word filtering** — ~30 noise words blocked
- **Keyword synonym expansion** — "lawyer" → ["advocate", "lawyer", "legal", "counsel"]
- **IR fuzzy retrieval** — searches both `field_name` metadata AND document text
- **Direct text search** (`_ir_text_search`) — scoring-based search with majority-match
- **Always merge field/text + hybrid retrieval for IR**
- **Clean question for embedding** — prevents zero-vector embeddings

#### B. LLM Answer Generation
- **Focused context window** — 5 chunks when text search finds strong matches (vs 15 fallback)
- **Context size cap** — 30K chars hard limit (60K for list queries)
- **Anti-hallucination prompt** — "ONLY use information from CONTEXT", "Do NOT make up information"
- **Exhaustive listing instruction** — "list ALL names, items found in CONTEXT"
- **Answer truncation at 8K chars** — prevents cutting off long lists

#### Key Insight: Less Context = Better Answers
With gemma3:12b, 5 focused chunks dramatically outperform 15 loosely-related chunks. Smaller LLMs need aggressive retrieval filtering.

**Implementation:** `rag.py` — various functions documented in code comments

---

## 7. Configuration

### Backend (.env)

```
OLLAMA_BASE_URL=http://localhost:11434
PDF_MODEL=gemma3:12b
EMBED_MODEL=mxbai-embed-large
WHISPER_MODEL=small

# RAG Accuracy Features
ENABLE_HYBRID_SEARCH=true
ENABLE_MULTI_QUERY=true
ENABLE_RERANKING=true

# MySQL
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=<your-password>
MYSQL_DATABASE=ISDIntelligence

# JWT
JWT_SECRET=<your-secret-key>

# LLM Parser
USE_LLM_PARSER=true
```

### Frontend (.env)

```
VITE_API_BASE=http://localhost:8001
```

---

## 8. Document Processing Limits

| Parameter                  | Default | Location                           |
|---------------------------|---------|-------------------------------------|
| Max chunks per document   | 500     | `rag.py` -> `MAX_UNITS`            |
| Max pages per PDF         | 120     | `rag.py` -> `MAX_PAGES`            |
| Max chars per DOCX        | 400,000 | `rag.py` -> `MAX_CHARS`            |
| Max rows per Excel sheet  | 300     | `rag.py` -> `max_rows_per_sheet`   |
| Max rows per CSV          | 500     | `rag.py` -> `max_rows`             |
| Chunk size (chars)        | 2000    | `rag.py` -> `chunk_text()`         |
| Chunk overlap (chars)     | 120-140 | `rag.py` -> `chunk_text()`         |
| Embedding batch size      | 64      | `ollama_client.py` -> `batch_size` |
| Entity extraction batch   | 5 chunks| `entity_graph.py` -> `batch_size`  |
| Max entity chunks per doc | 60      | `entity_graph.py` -> `MAX_ENTITY_CHUNKS` |
| Activity extraction batch | 3 chunks| `activity_timeline.py` -> `batch_size` |
| RAG top_k results         | 5 (focused) / 15 (fallback) | `rag.py` -> `max_results` |
| Context size cap          | 30K chars (60K for lists) | `rag.py` -> `MAX_CONTEXT_CHARS` |
| Ollama timeout            | 90s     | `ollama_client.py` -> `timeout`    |

---

## 9. Running the Application

### Prerequisites

- Python 3.10+ (Anaconda recommended on Windows)
- Node.js 18+ with npm
- Ollama installed and running (`ollama serve`)
- MySQL 8.x running
- NVIDIA GPU with CUDA drivers (recommended)

### Pull Required Ollama Models

```bash
ollama pull gemma3:12b
ollama pull mxbai-embed-large
```

### Backend

```bash
cd ISDDocumentIntelligence_V5/backend
pip install -r requirements.txt
uvicorn app:app --reload --port 8001
```

### Frontend

```bash
cd ISDDocumentIntelligence_V5/frontend
npm install
npm run dev
```

### Verify GPU Usage

```bash
ollama ps
# Should show "100% GPU"

nvidia-smi
# Should show ~10GB VRAM used when models are loaded
```

### GPU Recovery After Reboot

Ollama may fall back to CPU after reboot. Fix:
```bash
set OLLAMA_GPU_LAYERS=999
ollama serve
```

Warm up models:
```bash
ollama run gemma3:12b "hello"
ollama run mxbai-embed-large "hello"
```

---

## 10. Migration from V4 (MSSQL) to V5 (MySQL)

A migration script is provided at `dbscripts/migrate_mssql_to_mysql.py`.

### What It Does
1. **Copies ChromaDB** from V4 `chroma_db_v4` → V5 `chroma_db_v5` (skips if exists)
2. **Creates all MySQL tables** by importing V5 backend module init functions
3. **Migrates 10 tables**: users, cases, smac_reports, ir_reports, entities, relationships, activities, cross_references, doc_locations, answer_ratings
4. **Uses INSERT IGNORE** to skip duplicate rows
5. **Resets AUTO_INCREMENT** counters after migration

### Prerequisites
```bash
pip install pyodbc pymysql python-dotenv
```

### Usage
```bash
cd ISDDocumentIntelligence_V5/dbscripts
python migrate_mssql_to_mysql.py
```

### Notes
- MSSQL must be running with the V4 `ISDIntelligence` database
- MySQL password must be set in `backend/.env`
- Migration is idempotent — safe to re-run

---

## 11. Bulk Indexing (SMAC)

### Script
`dbscripts/bulk_index_smac.py` — Multi-threaded bulk document indexer with auto-resume.

### Usage
```bash
cd ISDDocumentIntelligence_V5/dbscripts
python bulk_index_smac.py --folder "PATH_TO_PDFS" --case-id 0 --username USER --password PASS --workers 5
```

### Features
- **Auto-resume**: Progress stored in SQLite DB (`.smac_bulk_progress.db`). Re-run to continue.
- **JWT auth**: Uses registered credentials
- **Configurable workers**: Default 3, recommended 5
- **Case ID 0**: Indexes to global collection (accessible from all cases via fallback)

---

## 12. Security Considerations

- **Fully offline** — no internet connectivity required after initial setup
- **JWT authentication** — all API calls require valid tokens (except health check)
- **bcrypt password hashing** — passwords never stored in plaintext
- **CORS configured** — `allow_origins=["*"]` for localhost/internal deployment
- **Temp files cleaned up** — all uploaded files deleted after processing
- **No data leaves the machine** — all inference, embedding, and storage is local
- **MySQL password auth** — credentials in `.env` (not committed to git)
- **English-only responses** — prevents unintended language leakage
- **Case isolation** — users only see their own cases and documents

---

## 13. Target Deployment

| Environment | Hardware                    | LLM Model                          | Database |
|------------|-----------------------------|------------------------------------|----------|
| Development| Laptop + RTX 4090 (16GB)    | gemma3:12b                         | MySQL 8.x|
| Production | Server + NVIDIA H100 (80GB) | llama3.1:70b or qwen2.5:72b       | MySQL 8.x|
