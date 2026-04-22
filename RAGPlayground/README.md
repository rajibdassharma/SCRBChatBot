# RAG Playground

A testing ground for experimenting with different RAG (Retrieval-Augmented Generation) pipeline approaches. Test document parsing, indexing, and retrieval strategies here before integrating into production projects.

---

## Project Structure

```
RAGPlayground/
├── BasicRAG/           # Baseline: chunk → embed → vector search → LLM answer
├── HybridRAG/          # Vector + BM25 keyword search + RRF fusion + reranking
├── StructuredRAG/      # Table parsing → MySQL/SQL → field-based lookup
├── AgenticRAG/         # Multi-step agent with tool use and reasoning
├── GraphRAG/           # Entity extraction → knowledge graph → graph-based retrieval
├── MultimodalRAG/      # Vision model for scanned docs, images, complex layouts
└── shared/             # Common utilities shared across all pipelines
```

---

## Pipeline Descriptions

### BasicRAG
- **Best for:** Simple text documents, reports, articles
- **How it works:** Document → text extraction → fixed-size chunking → embed with sentence-transformers → store in ChromaDB → vector similarity search → LLM generates answer from top chunks
- **Strengths:** Simple, fast, works for most text
- **Weaknesses:** Misses keyword-specific matches, struggles with tables

### HybridRAG
- **Best for:** Mixed content — text with specific IDs, numbers, terminology
- **How it works:** Same as BasicRAG but adds BM25 keyword search alongside vector search. Results merged using Reciprocal Rank Fusion (RRF). Optional LLM reranking of merged results.
- **Strengths:** Catches both semantic meaning AND exact keyword matches
- **Weaknesses:** More complex, BM25 index needs rebuilding on document changes

### StructuredRAG
- **Best for:** Tables, forms, structured documents (IR Form-16, SMAC reports)
- **How it works:** Parse tables into field_key/field_value pairs → store in MySQL (EAV schema) → keyword/field-name matching → direct value retrieval or NL-to-SQL for aggregates
- **Strengths:** Precise field-level retrieval, supports SQL queries across documents
- **Weaknesses:** Depends on parser quality, complex table structures may be missed

### AgenticRAG
- **Best for:** Complex multi-step questions requiring reasoning
- **How it works:** Agent receives question → decides which tool to use (vector search, SQL query, cross-document search, follow-up) → executes steps → synthesizes final answer
- **Strengths:** Handles "find person X, then find all their associates across all cases"
- **Weaknesses:** Slower (multiple LLM calls), harder to debug

### GraphRAG
- **Best for:** Entity relationships, connection mapping, investigation
- **How it works:** Extract entities (persons, organizations, locations) and relationships from documents → build knowledge graph in MySQL → graph traversal for connected entities → LLM summarizes findings
- **Strengths:** Discovers hidden connections across documents
- **Weaknesses:** Entity extraction quality depends on LLM, can produce noise

### MultimodalRAG
- **Best for:** Scanned documents, images embedded in PDFs, complex table layouts
- **How it works:** OCR or vision model extracts text/descriptions from images and scanned pages → text indexed like BasicRAG → alternatively, treat entire pages as images and use vision LLM to answer directly
- **Strengths:** Handles documents that text extraction fails on
- **Weaknesses:** Slower (OCR/vision processing), lower accuracy than text-based parsing

---

## Shared Utilities (`shared/`)

Common code used across all pipelines:

| Module | Purpose |
|--------|---------|
| `ollama_client.py` | LLM chat and embedding via Ollama HTTP API |
| `chunking.py` | Text chunking with configurable size and overlap |
| `embeddings.py` | Embedding via Ollama or sentence-transformers |
| `chromadb_utils.py` | ChromaDB collection management |
| `mysql_utils.py` | MySQL connection and query helpers |
| `document_loader.py` | PDF/DOCX/XLSX text and table extraction |
| `evaluation.py` | Compare pipeline results (precision, recall, answer quality) |

---

## How to Use

1. Pick a pipeline folder (e.g., `HybridRAG/`)
2. Place test documents in the folder
3. Run the pipeline script to index and query
4. Compare results across pipelines
5. Once satisfied, port the approach to the production project (ISD Document Intelligence V6)

---

## Test Scenarios

| Scenario | Pipeline to Test | Document Type |
|----------|-----------------|---------------|
| Simple Q&A on text reports | BasicRAG | SMAC PDFs |
| Search for specific TMS IDs or names | HybridRAG | SMAC PDFs |
| Extract fields from IR Form-16 tables | StructuredRAG | IR DOCX |
| Complex tables with merged cells, sub-items | StructuredRAG + MultimodalRAG | IR DOCX |
| "Who is John Doe" across all documents | AgenticRAG | IR + SMAC |
| Find all associates of a person | GraphRAG | IR DOCX |
| Scanned/image-based PDFs | MultimodalRAG | Scanned SMAC PDFs |
| Count occurrences across all documents | HybridRAG (ChromaDB full-text) | SMAC PDFs |

---

## Tech Stack

- **LLM:** Ollama (local, offline) — gemma3:12b or any installed model
- **Embeddings:** mxbai-embed-large via Ollama or sentence-transformers
- **Vector DB:** ChromaDB (persistent)
- **SQL DB:** MySQL (for structured and graph pipelines)
- **Document Parsing:** python-docx, pypdf, Docling, openpyxl
- **OCR:** RapidOCR (via Docling) or EasyOCR
- **Python 3.10+**

---

## ISD Document Intelligence V6 — RAG Approaches in Production

V6 uses a combination of 5 RAG approaches working together:

| Feature | Pipeline Used | How It Works |
|---------|--------------|--------------|
| SMAC Q&A (regular questions) | **HybridRAG** | Vector + BM25 + RRF fusion + LLM reranking |
| SMAC aggregate ("how many mention Iran") | **HybridRAG** | ChromaDB full-text keyword search across all chunks |
| SMAC field-specific ("what is the input for TMS X") | **StructuredRAG** | Direct field lookup from MySQL/ChromaDB metadata, no LLM |
| SMAC NL-to-SQL ("list all originators") | **StructuredRAG** | LLM generates SQL against `smac_reports` table |
| IR Q&A (single document) | **StructuredRAG** | MySQL field lookup, LLM selects relevant fields from 200+ fields |
| IR aggregate ("list all accused") | **StructuredRAG** | NL-to-SQL against `ir_reports` table |
| Entity graph (connections map) | **GraphRAG** | LLM extracts entities/relationships → MySQL graph → force-graph viz |
| Activity timeline | **GraphRAG** variant | LLM extracts temporal events → MySQL → chronological display |
| Location map | **GraphRAG** variant | LLM extracts addresses → offline geocoding → map visualization |
| Multi-document agent Q&A | **AgenticRAG** | Sequential reasoning across selected documents |
| OCR indexing (scanned PDFs) | **MultimodalRAG** | Docling OCR + TableFormer for scanned document processing |

**Not used:** BasicRAG (pure vector search) — skipped in favor of HybridRAG which is strictly better.

---

## DO NOT DO

- **DO NOT** read any file outside the project folder without user consent.

---

*Last updated: 2026-04-11*
