# ISD Document Intelligence V3 — Architecture & Design Best Practices

## 1. System Overview

ISD Document Intelligence V3 is a standalone, fully offline AI-powered document analysis system built for Karnataka State Police (KSP). It allows officers to upload case documents (PDF, DOCX, DOC, XLSX, CSV), index them into a local vector database, store structured fields in SQL Server, extract entity relationships and activity timelines using LLM, and query them using text or voice — all without any internet connectivity or cloud dependency.

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
           |  ChromaDB      | |  SQL Server    | |  faster-whisper|
           |  (Vector Store) | |  (MSSQL)       | |  (Local STT)   |
           |  Persistent on | |  ISDIntelligence| |                |
           |  local disk    | |  Database       | |                |
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
| Structured DB  | SQL Server (MSSQL)             | Structured fields, entities, activities, locations |
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
ISDDocumentIntelligence_V3/
  backend/
    app.py                # FastAPI application with 27 endpoints
    config.py             # Environment-based configuration (Ollama, MSSQL)
    rag.py                # RAG pipeline: indexing, hybrid search, NL-to-SQL
    ollama_client.py      # Ollama API client (chat + batch embedding)
    mssql_db.py           # MSSQL connection factory & DB bootstrap
    structured_tables.py  # EAV document_fields table (structured storage)
    entity_graph.py       # Entity & relationship extraction (knowledge graph)
    activity_timeline.py  # Activity & cross-reference extraction (timeline)
    location_extractor.py # Address extraction & offline geocoding
    requirements.txt      # Python dependencies
    .env                  # Environment variables
    chroma_db/            # ChromaDB persistent storage (auto-created)
    debug_audio/          # Debug audio recordings (auto-created)
  frontend/
    index.html            # HTML entry point
    package.json          # Node dependencies
    vite.config.ts        # Vite build configuration
    tsconfig.json         # TypeScript project references
    tsconfig.app.json     # App TypeScript config
    tsconfig.node.json    # Node TypeScript config
    eslint.config.js      # ESLint configuration
    .env                  # Frontend environment (API base URL)
    public/
      vite.svg            # Favicon
      geo/
        countries-110m.json  # TopoJSON for world map
    src/
      main.tsx            # React entry point
      App.tsx             # Main application component (~2150 lines)
      App.css             # All styles (~1650 lines)
      index.css           # Global reset styles
      assets/
        ksp_logo.png      # KSP branding logo
        banner_logo.png   # Banner image
        banner_logo.jpeg  # Banner image (JPEG)
  test_data/
    generate_test_pdfs.py    # Generate 50 employee IR test PDFs
    generate_group_reports.py # Generate 25 SMAC log report PDFs
    employees/               # 50 employee IR PDFs (EMP-001 to EMP-050)
    groups/                  # 25 group log report PDFs (LOG-001 to LOG-025)
```

---

## 3. Database Schema

### 3.1 SQL Server (MSSQL) — ISDIntelligence Database

All structured data is stored in a shared MSSQL database (`ISDIntelligence`) with 6 tables:

#### document_fields (EAV — Entity-Attribute-Value)

Flat key-value storage for document fields. Simple schema enables NL-to-SQL queries.

| Column      | Type         | Purpose                          |
|------------|-------------|----------------------------------|
| id         | INT (PK)     | Auto-increment primary key       |
| doc_id     | VARCHAR      | Document identifier              |
| doc_name   | VARCHAR      | Original filename                |
| collection | VARCHAR      | "SMAC" or "IR"                   |
| serial_no  | VARCHAR      | Field serial number              |
| field_key  | VARCHAR      | Field name (e.g., "Name of Accused") |
| field_value| VARCHAR      | Field value (e.g., "Mohammed Ali")   |

#### entities

Named entities extracted from documents by LLM.

| Column   | Type         | Purpose                          |
|---------|-------------|----------------------------------|
| id      | INT (PK)     | Auto-increment primary key       |
| name    | VARCHAR      | Entity name                      |
| type    | VARCHAR      | PERSON, ORGANIZATION, LOCATION, PHONE, VEHICLE, OTHER |
| doc_id  | VARCHAR      | Source document                  |
| doc_name| VARCHAR      | Source filename                  |
| context | VARCHAR      | Surrounding text context         |

#### relationships

Typed relationships between entities.

| Column             | Type     | Purpose                          |
|-------------------|---------|----------------------------------|
| id                | INT (PK) | Auto-increment primary key       |
| source_entity_id  | INT (FK) | References entities.id           |
| target_entity_id  | INT (FK) | References entities.id           |
| relationship_type | VARCHAR  | See relationship types below     |
| doc_id            | VARCHAR  | Source document                  |
| context           | VARCHAR  | Surrounding text context         |

**Relationship types:** MEMBER_OF, WORKS_AT, SIBLING, SPOUSE, PARENT_OF, CHILD_OF, LIVES_AT, COLLEAGUE, PARTICIPATED_IN, REPORTS_TO, LOCATED_IN, RELATED_TO, CO_OCCURRENCE, HELPER_OF, ADVOCATE_OF, DOCTOR_OF, FINANCIER_OF, ASSOCIATE_OF, ACCOMPLICE_OF, HANDLER_OF, SYMPATHIZER_OF, ACCUSED_WITH, CO_ACCUSED

#### activities

Temporal activities extracted from SMAC log reports.

| Column          | Type     | Purpose                          |
|----------------|---------|----------------------------------|
| id             | INT (PK) | Auto-increment primary key       |
| tms_id         | VARCHAR  | TMS tracking number (e.g., TMS-2025-0412) |
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

#### cross_references

Bread Crumb links between activities via TMS IDs.

| Column         | Type     | Purpose                          |
|---------------|---------|----------------------------------|
| id            | INT (PK) | Auto-increment primary key       |
| source_tms_id | VARCHAR  | Source activity TMS ID           |
| target_tms_id | VARCHAR  | Target activity TMS ID           |
| context       | VARCHAR  | Cross-reference context          |
| doc_id        | VARCHAR  | Source document                  |

#### doc_locations

Geocoded addresses extracted from IR documents.

| Column       | Type     | Purpose                          |
|-------------|---------|----------------------------------|
| id          | INT (PK) | Auto-increment primary key       |
| doc_id      | VARCHAR  | Source document                  |
| doc_name    | VARCHAR  | Source filename                  |
| person_name | VARCHAR  | Person associated with address   |
| address_text| TEXT     | Full address text                |
| city        | VARCHAR  | City/district                    |
| locality    | VARCHAR  | Locality/area                    |
| lat         | FLOAT    | Latitude (offline geocoded)      |
| lng         | FLOAT    | Longitude (offline geocoded)     |
| address_type| VARCHAR  | Address classification           |

### 3.2 ChromaDB (Vector Store)

- Persistent on-disk storage at `chroma_db/`
- Separate collections for SMAC and IR documents
- Each chunk stored with metadata: `doc_id`, `doc_name`, `page`, `chunk_index`
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
        +-----> Structured field extraction (regex-based)
        |         - Pipe-separated: "1 | Name | Mohammed Ali"
        |         - Colon-separated: "1. Name: Mohammed Ali"
        |         - Space-separated: "1  Name        Mohammed Ali"
        |         Stored in MSSQL document_fields table
        |
        v
ollama_embed_batch(): embed all chunks in batches of 64
        |
        v
ChromaDB: store embeddings + metadata
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
POST /docs/ask (with conversation history for context)
        |
        v
rag.py: ask_pdf() -> ask_docs()
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
LLM generates SQL query against document_fields table
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
   Search document_fields table for matching field values
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
ollama_chat(): LLM generates answer from context only (temperature=0)
        |
        v
Response: { answer, used_chunks[] }
```

### 4.3 Entity Graph Extraction Flow

```
POST /graph/extract-all (or auto after upload)
        |
        v
Retrieve all document chunks from ChromaDB
        |
        v
For each document:
  Process chunks in batches of 5
        |
        v
  LLM extracts entities + relationships as JSON:
    {
      "entities": [{"name": "Amit Sharma", "type": "PERSON", "context": "..."}],
      "relationships": [{"source": "Amit Sharma", "target": "Tech Lab", "type": "MEMBER_OF"}]
    }
        |
        v
  Store in MSSQL: entities + relationships tables
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
  LLM extracts activities + cross-references as JSON:
    {
      "activities": [{"tms_id": "TMS-2025-0412", "date": "Mar 18 2025", ...}],
      "cross_references": [{"source_tms_id": "TMS-2025-0687", "target_tms_id": "TMS-2025-0412"}]
    }
        |
        v
  Store in MSSQL: activities + cross_references tables
        |
        v
GET /timeline/data -> Returns activities sorted by date
GET /timeline/breadcrumb?tms_id=X -> Returns Bread Crumb trail of linked activities
```

### 4.5 Location Extraction Flow

```
POST /locations/extract-all (incremental — IR collection only)
        |
        v
Retrieve IR document chunks from ChromaDB
        |
        v
For each document (not yet extracted):
  LLM extracts addresses and person-address associations
        |
        v
  Offline geocoding using India district/city dictionary
  (Karnataka districts, Bangalore localities, major Indian cities)
        |
        v
  Store in MSSQL: doc_locations table
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

---

## 5. API Endpoints (27 total)

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

### Entity Graph (5 endpoints)

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

### Structured Data & NL-to-SQL (6 endpoints)

| Method | Path                     | Purpose                                    |
|--------|-------------------------|--------------------------------------------|
| GET    | `/structured/smac`      | List all SMAC reports                      |
| GET    | `/structured/smac/{id}` | Get single SMAC report fields              |
| GET    | `/structured/ir`        | List all IR reports                        |
| GET    | `/structured/ir/{id}`   | Get single IR report with all fields       |
| POST   | `/structured/query`     | Natural Language to SQL query pipeline     |

---

## 6. Design Best Practices

### 6.1 EAV Schema for Document Fields (Simple over Complex)

**Problem:** Police documents have varied structures — IR reports have 50+ fields, SMAC reports have 15+ fields, and field names differ across versions. A normalized schema with separate tables per document type becomes unmanageable.

**Solution:** Use a single Entity-Attribute-Value (EAV) table (`document_fields`) that stores each field as a key-value pair. This handles any document structure without schema changes.

```sql
-- One table handles ALL document types
SELECT field_key, field_value FROM document_fields
WHERE doc_id = 'doc123' ORDER BY serial_no
```

**Why EAV over normalized tables:**
- No schema migration when document formats change
- Simple NL-to-SQL — LLM only needs to understand one table
- Easy keyword search with `LIKE` queries
- Aggregate queries across all documents work naturally

**Implementation:** `structured_tables.py` -> `document_fields` table

---

### 6.2 Hybrid Search: Structured + Vector + BM25

**Problem:** Vector (semantic) search alone misses exact matches. Searching for account number "1234567890" or name "Mohammed Ali" may fail because embedding similarity cares about meaning, not exact text.

**Solution:** Run THREE search engines in parallel and merge results:
1. **Structured Keyword Search** (MSSQL `document_fields`) — exact field value matches with synonym expansion
2. **Vector Search** (ChromaDB) — semantically similar chunks
3. **BM25 Keyword Search** (rank-bm25) — exact keyword matches in full text

Results are merged using **Reciprocal Rank Fusion (RRF)**: `score = 1/(k + rank₁) + 1/(k + rank₂)`. Documents found by multiple methods get boosted.

**Synonym expansion** maps user terms to likely field names:
```python
"accused" -> ["name", "accused", "suspect"]
"phone"   -> ["phone", "mobile", "contact"]
"address" -> ["address", "residence", "location"]
```

**Impact:** Catches exact case numbers, phone numbers, and names that vector search misses. Critical for law enforcement accuracy.

**Configuration:** `ENABLE_HYBRID_SEARCH=true` in `.env`

**Implementation:** `rag.py` -> `_hybrid_retrieve()`, `_bm25_search()`, `_reciprocal_rank_fusion()`, `search_fields()`

---

### 6.3 Smart Routing: NL-to-SQL for Aggregate Questions

**Problem:** Questions like "Name all accused persons" or "How many documents mention Bangalore?" require aggregating across ALL documents. RAG retrieves only top-k chunks and may miss documents.

**Solution:** Detect aggregate questions and route them to a Natural Language-to-SQL pipeline instead of RAG.

```
"Name all accused" -> LLM generates SQL:
  SELECT DISTINCT doc_name, field_value
  FROM document_fields
  WHERE field_key LIKE '%accused%'

Execute SQL -> LLM formats results -> Return answer
```

**Detection keywords:** "all", "every", "list", "how many", "count", "total", "across", "each document"

**Implementation:** `rag.py` -> `_is_aggregate_question()`, `_answer_via_sql()`

---

### 6.4 Batch Embedding (GPU Optimization)

**Problem:** Embedding text chunks one-by-one via HTTP to Ollama is slow.

**Solution:** Ollama's `/api/embed` endpoint accepts a list. We send up to 64 texts per request.

```python
# BAD: 200 chunks = 200 HTTP requests
for chunk in chunks:
    vec = ollama_embed(chunk)

# GOOD: 200 chunks = 4 HTTP requests (batch_size=64)
vectors = ollama_embed_batch(chunks, batch_size=64)
```

**Impact:** 10-50x faster indexing. GPU utilization goes from ~0% to visible activity.

**Implementation:** `ollama_client.py` -> `ollama_embed_batch()`

---

### 6.5 GPU Auto-Detection for Whisper STT

**Problem:** Hardcoding `device="cpu"` wastes available GPU resources.

**Solution:** Auto-detect CUDA at runtime and select the best device.

```python
import torch
if torch.cuda.is_available():
    model = WhisperModel(name, device="cuda", compute_type="float16")
else:
    model = WhisperModel(name, device="cpu", compute_type="int8")
```

**Impact:** 3-5x faster speech transcription on NVIDIA GPUs.

**Implementation:** `app.py` -> `get_whisper_model()`

---

### 6.6 Lazy Model Loading

**Problem:** Loading large ML models (Whisper ~500MB, embedding model ~274MB) at server startup slows boot time.

**Solution:** Singleton pattern that loads models on first use.

```python
_whisper_model = None
def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = WhisperModel(...)
    return _whisper_model
```

**Impact:** Fast server startup (< 2 seconds). Memory used only when features are invoked.

**Implementation:** `app.py` -> `get_whisper_model()`

---

### 6.7 Audio Pipeline: WebM to WAV Conversion

**Problem:** Browser MediaRecorder outputs WebM/Opus format. Whisper works best with 16kHz mono WAV.

**Solution:** Convert audio server-side using PyAV (Python ffmpeg bindings).

**Why PyAV instead of subprocess ffmpeg:** PyAV is a Python library (no system ffmpeg install needed), works on Windows without PATH issues, and handles the conversion in-memory.

**Implementation:** `app.py` -> `_convert_to_wav16k()`

---

### 6.8 Microphone Device Selection & Audio Level Monitoring

**Problem:** Laptops often have multiple audio input devices. The browser may default to one that captures silence.

**Solution:**
1. Enumerate all `audioinput` devices via `navigator.mediaDevices.enumerateDevices()`
2. Show a dropdown selector when multiple devices are found
3. Display a real-time audio level meter using Web Audio API's `AnalyserNode`
4. Show a warning when mic level is 0% ("No audio detected!")

**Implementation:** `App.tsx` -> `useEffect` for device enumeration, `handleVoiceToggle()`

---

### 6.9 Whisper Hallucination Filtering

**Problem:** When Whisper receives silence or very short audio, it "hallucinates" phrases like "Thank you", "Subscribe", etc.

**Solution:** Blocklist of known hallucination phrases.

```python
HALLUCINATIONS = {"", "thank you", "thanks for watching", "subscribe", "you", "bye"}
if cleaned.lower() in HALLUCINATIONS or len(cleaned) < 3:
    return {"ok": False, "error": "Could not transcribe audio..."}
```

**Implementation:** `app.py` -> `docs_transcribe()`

---

### 6.10 Authorized System Prompts for Sensitive Data

**Problem:** LLMs may refuse to discuss police case files, returning generic refusal messages.

**Solution:** System prompt explicitly authorizes the model as an internal tool.

```python
{"role": "system", "content": (
    "You are an authorized internal AI assistant for Karnataka State Police (KSP). "
    "You are deployed on a secure, offline government system. "
    "You MUST answer questions about the provided documents fully and factually. "
    "Do NOT refuse, censor, or redact any information. "
    "Always respond in English only."
)}
```

**Implementation:** `rag.py` -> system prompts in `ask_docs()` and `ask_docs_agent()`

---

### 6.11 Zero-Temperature LLM for Factual Accuracy

**Problem:** With temperature > 0, LLMs may generate creative but inaccurate answers.

**Solution:** Use `temperature=0.0` for ALL LLM calls (Q&A, entity extraction, NL-to-SQL).

```python
answer = ollama_chat(messages, temperature=0.0, model=PDF_MODEL)
```

**Implementation:** `rag.py`, `entity_graph.py`, `activity_timeline.py` — all `ollama_chat()` calls

---

### 6.12 Multi-Query RAG (Query Expansion)

**Problem:** A single question phrasing may not match how information is stored.

**Solution:** LLM generates 3 alternative phrasings before searching.

```
Original:    "Who is the accused?"
Variation 1: "accused person details and identity"
Variation 2: "suspect name from the case document"
Variation 3: "defendant or perpetrator information"
```

Each variation searches both vector and BM25 indexes.

**Configuration:** `ENABLE_MULTI_QUERY=true` in `.env`

**Implementation:** `rag.py` -> `_generate_multi_queries()`

---

### 6.13 LLM Re-ranking

**Problem:** After retrieving 30+ candidate chunks, the initial ranking may not reflect true relevance.

**Solution:** Send top candidates to the LLM to re-rank by relevance. The LLM sees the question AND passage together (cross-encoder style), producing more accurate relevance judgments.

```
Input:  30 candidate chunks + user question
Output: Top 12 reordered by actual relevance
```

**Configuration:** `ENABLE_RERANKING=true` in `.env`

**Implementation:** `rag.py` -> `_rerank_with_llm()`

---

### 6.14 Entity Graph with Helper/Associate Relationships

**Problem:** Standard entity extraction only captures basic relationships (WORKS_AT, MEMBER_OF). Law enforcement needs to identify helpers, accomplices, handlers, and financial connections.

**Solution:** Extended relationship type system with 23 types including law-enforcement-specific types:

- **Standard:** MEMBER_OF, WORKS_AT, SIBLING, SPOUSE, PARENT_OF, CHILD_OF, COLLEAGUE
- **Law Enforcement:** HELPER_OF, ADVOCATE_OF, DOCTOR_OF, FINANCIER_OF, ASSOCIATE_OF, ACCOMPLICE_OF, HANDLER_OF, SYMPATHIZER_OF, ACCUSED_WITH, CO_ACCUSED

The LLM prompt explicitly lists these types so the model assigns the most specific relationship.

**Implementation:** `entity_graph.py` -> `extract_entities_and_relationships_from_chunks()`

---

### 6.15 Offline Geocoding for Location Map

**Problem:** Law enforcement systems cannot use online geocoding APIs (Google Maps, OpenStreetMap) due to offline requirement.

**Solution:** Bundled India geocoding dictionary with coordinates for:
- All Karnataka districts
- Major Bangalore localities
- Major Indian cities

Address text is matched against this dictionary to produce lat/lng coordinates.

**Implementation:** `location_extractor.py` -> `geocode()`

---

### 6.16 Incremental Extraction (Skip Already-Processed Documents)

**Problem:** Re-extracting entities/activities/locations from all documents after adding one new document wastes time.

**Solution:** Track which documents have been processed. On extract-all, skip documents that already have extracted data.

```python
already_done = get_extracted_doc_ids()
for doc in all_docs:
    if doc['doc_id'] in already_done:
        continue  # Skip
    extract_and_store(doc)
```

**Implementation:** `activity_timeline.py` -> `get_extracted_doc_ids()`, `location_extractor.py` -> `get_extracted_doc_ids_for_locations()`

---

### 6.17 Persistent State Across Page Refresh

**Problem:** Refreshing the browser page loses the indexed document list and status information.

**Solution:** On app mount (and collection switch), fetch the document list from the backend and restore the status line.

```typescript
useEffect(() => {
  apiFetch(`/docs/list?collection=${activeCollection}`)
    .then((data) => {
      if (data?.ok && data.docs) {
        setDocs(data.docs)
        if (data.docs.length > 0) {
          setDocStatus(`OK ${data.docs.length} document(s) indexed. Ready for Q&A.`)
        }
      }
    })
}, [activeCollection])
```

**Implementation:** `App.tsx` -> `useEffect` on mount with `activeCollection` dependency

---

### 6.18 Conversation Context for Follow-up Questions

**Problem:** Users ask follow-up questions like "summarize it" that reference previous answers.

**Solution:** Send the last 8 messages as conversation context with each question. The backend prepends context to resolve references.

**Implementation:** `app.py` -> `build_context_from_history()`, `App.tsx` -> `docChat` state

---

### 6.19 English-Only Responses

**Problem:** When processing documents in regional languages (Kannada, Hindi), the LLM sometimes responds in the document's language instead of English.

**Solution:** All system prompts include "Always respond in English only."

**Implementation:** `rag.py` -> all system prompt strings

---

## 7. Configuration

### Backend (.env)

```
OLLAMA_BASE_URL=http://localhost:11434
PDF_MODEL=gemma3:12b
EMBED_MODEL=mxbai-embed-large
WHISPER_MODEL=small

# RAG Accuracy Features (set to false to disable any)
ENABLE_HYBRID_SEARCH=true
ENABLE_MULTI_QUERY=true
ENABLE_RERANKING=true

# SQL Server (MSSQL)
MSSQL_SERVER=localhost
MSSQL_DATABASE=ISDIntelligence
MSSQL_DRIVER=ODBC Driver 17 for SQL Server
MSSQL_AUTH=windows
MSSQL_USER=
MSSQL_PASSWORD=
```

### Frontend (.env)

```
VITE_API_BASE=http://localhost:8000
```

All values have sensible defaults in `config.py` and can be overridden via environment variables.

---

## 8. Document Processing Limits

| Parameter                  | Default | Configurable                       |
|---------------------------|---------|-------------------------------------|
| Max chunks per document   | 500     | `rag.py` -> `MAX_UNITS`            |
| Max pages per PDF         | 120     | `rag.py` -> `MAX_PAGES`            |
| Max chars per DOCX        | 400,000 | `rag.py` -> `MAX_CHARS`            |
| Max rows per Excel sheet  | 300     | `rag.py` -> `max_rows_per_sheet`   |
| Max rows per CSV          | 500     | `rag.py` -> `max_rows`             |
| Chunk size (chars)        | 2000    | `rag.py` -> `chunk_text()`         |
| Chunk overlap (chars)     | 120-140 | `rag.py` -> `chunk_text()`         |
| Min unit length           | 10-25   | `rag.py` -> `min_unit_len`         |
| Embedding batch size      | 64      | `ollama_client.py` -> `batch_size` |
| Entity extraction batch   | 5 chunks| `entity_graph.py` -> `batch_size`  |
| Activity extraction batch | 3 chunks| `activity_timeline.py` -> `batch_size` |
| RAG top_k results         | 12-15   | `app.py` / `rag.py`               |
| Conversation history kept | 8 msgs  | `app.py` -> `keep_last`           |
| Number of documents       | No limit| Disk space only                    |

---

## 9. Running the Application

### Prerequisites

- Python 3.10+ with pip
- Node.js 18+ with npm
- Ollama installed and running (`ollama serve`)
- SQL Server (MSSQL) with ODBC Driver 17 or 18
- NVIDIA GPU with CUDA drivers (recommended, for faster processing)

### Pull Required Ollama Models

```bash
ollama pull gemma3:12b
ollama pull mxbai-embed-large
```

### Backend

```bash
cd ISDDocumentIntelligence_V3/backend
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

### Frontend

```bash
cd ISDDocumentIntelligence_V3/frontend
npm install
npm run dev
```

### Verify GPU Usage

```bash
# While a model is loaded (during a query):
curl -s http://localhost:11434/api/ps | python -c "
import sys, json
for m in json.load(sys.stdin).get('models', []):
    pct = round(m.get('size_vram',0)/m.get('size',1)*100)
    print(f\"{m['name']}: {pct}% GPU\")
"
```

---

## 10. Security Considerations

- **Fully offline** — no internet connectivity required after initial setup
- **No credentials stored** — no login system, designed for secure internal networks
- **CORS open** (`allow_origins=["*"]`) — acceptable for localhost/internal deployment only
- **Temp files cleaned up** — all uploaded files are deleted after processing
- **Debug audio** — saved to `debug_audio/` for troubleshooting; clear periodically in production
- **No data leaves the machine** — all LLM inference, embedding, and storage happens locally
- **MSSQL Windows Auth** — uses Trusted_Connection by default, no SQL passwords in config
- **English-only responses** — prevents unintended language leakage in outputs
