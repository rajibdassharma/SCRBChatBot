# Feature Roadmap — ISD Document Intelligence V6

## Planned Features

### Cross-Collection Search
| Feature | Effort | Files | Description |
|---------|--------|-------|-------------|
| Cross-collection aggregate search | Small (1-2 hours) | `rag_smac.py` | Search across both SMAC and IR for aggregate queries (e.g., "how many documents mention Iran across all collections") |
| Cross-collection Q&A | Medium (4-6 hours) | `rag_smac.py`, `rag_ir.py`, `app.py`, `App.tsx` | Ask questions that search both SMAC and IR, merge results, and present combined answer |
| Cross-collection entity graph | None (already works) | — | Entities from both SMAC and IR are stored in the same MySQL tables, so the graph already spans both |

### IR Document Enhancements
| Feature | Effort | Files | Description |
|---------|--------|-------|-------------|
| Chargesheet document support | Medium-Large | `app.py`, new parser, `rag_smac.py` or new module | Support uploading and indexing Chargesheet documents (separate document type, not part of IR). Parse, chunk, and make searchable via Q&A |
| IR Summary/Narrative extraction | Medium | `ir_parser.py`, `rag_ir.py` | Extract the free-form text (Summary/Narrative) that appears after the table sections in IR DOCX files. Currently ignored by the parser. Index into ChromaDB for Q&A |

### Investigation Agent
| Feature | Effort | Files | Description |
|---------|--------|-------|-------------|
| Investigation Agent — deep cross-document research | Large (2-3 days) | New `investigation_agent.py`, `app.py`, `App.tsx` | An autonomous agent that takes an investigation starting point (person, organization, training camp, financier) and automatically: (1) Finds all information about the subject in the primary document (IR or SMAC), (2) Searches across ALL documents (both SMAC and IR) for mentions of the same subject, (3) Follows connections — associates, accomplices, organizations, locations found in step 1 and searches for those too, (4) Presents a structured investigation report: subject profile, appearances across cases, linked persons, timeline of activities, locations |
| Drill-down navigation | Medium | `App.tsx` | From the investigation report, user can click on a case reference (e.g., "John Doe also appears in Case X") to drill down into that case's documents and see the specific mentions in context |
| Investigation graph view | Medium | `App.tsx`, `entity_graph.py` | Visual graph centered on the investigation subject — showing all connected entities, cases, and relationships discovered by the agent. Reuses existing force-graph component filtered to the subject |

**Investigation Agent Flow:**
```
User asks: "Who is John Doe?"
    │
    ▼
Step 1: Find primary document (IR with John Doe as accused)
    → Extract all fields: name, aliases, address, organization, associates, helpers
    │
    ▼
Step 2: Search ALL documents for "John Doe" (ChromaDB full-text across SMAC + IR)
    → Found in: Case A (IR), Case B (SMAC), Case C (SMAC)
    │
    ▼
Step 3: For each connected entity (associates, organization, financier):
    → Search for those names across all documents too
    → Build connection map
    │
    ▼
Step 4: Present structured report:
    ┌─────────────────────────────────────┐
    │ SUBJECT: John Doe                   │
    │ Aliases: JD, Johnny                 │
    │ Organization: XYZ Group             │
    │ Address: Bangalore                  │
    ├─────────────────────────────────────┤
    │ APPEARANCES (3 cases):              │
    │  • Case A (IR) — accused            │
    │  • Case B (SMAC) — mentioned in Gist│
    │  • Case C (SMAC) — associate of X   │
    ├─────────────────────────────────────┤
    │ CONNECTIONS:                         │
    │  • Associate: Ram Singh (Case A, B)  │
    │  • Financier: ABC Corp (Case C)      │
    │  • Hideout: Mysore (Case A)          │
    └─────────────────────────────────────┘
    User can click any case to drill down
```

### SMAC Document Enhancements
| Feature | Effort | Files | Description |
|---------|--------|-------|-------------|
| SMAC additional table extraction and display | Medium | `rag_smac.py`, `llm_kv_extractor.py`, `structured_tables.py`, `App.tsx` | SMAC documents may contain additional tables (e.g., "Followup Details", "Action Taken"). When user asks "What are the Followup Details?", detect the table name, retrieve the table data, and display it in tabular format in the UI — not as free text |

### Case-Based Document Organization
| Feature | Effort | Files | Description |
|---------|--------|-------|-------------|
| Case name extraction from folder path | Medium | `app.py`, `rag_ir.py`, `rag_smac.py`, `structured_tables.py`, bulk indexing scripts | Store the parent folder name as the case name when indexing IR documents. The last folder in the path is the case name (e.g., `/Cases/Murder_Case_2025/IR_JohnDoe.docx` → case = "Murder_Case_2025") |
| Case-scoped Q&A | Medium | `rag_ir.py`, `rag_smac.py`, `App.tsx` | Allow user to select a case name, then Q&A searches only documents belonging to that case. All IRs, Chargesheets, and SMAC docs in the same case folder are grouped together |
| Case listing and browsing | Small | `app.py`, `App.tsx` | UI to list all indexed cases, show document count per case, and browse documents within a case |

### Translation
| Feature | Effort | Files | Description |
|---------|--------|-------|-------------|
| Kannada → English text translation | Done | `ir_translator.py`, `app.py`, `App.tsx` | Paste Kannada text, get English translation via TranslateGemma |
| IR document translation | In progress | `ir_translator.py`, `app.py`, `App.tsx` | Upload IR DOCX, preserve tables, translate Kannada narrative to English, review and download |

---

*Last updated: 2026-04-06*
