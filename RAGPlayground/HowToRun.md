# How To Run — RAG Playground

## Prerequisites
- Python 3.10+
- Node.js 18+
- MySQL 8+ running locally
- Ollama running with at least one model (e.g., `gemma3:12b`)

## Backend

```bash
cd RAGPlayground/backend
pip install -r requirements.txt
uvicorn rag_playground:app --host 0.0.0.0 --port 8006 --reload
```

Backend runs on: `http://localhost:8006`

## Frontend

```bash
cd RAGPlayground/frontend
npm install
npm run dev
```

Frontend runs on: `http://localhost:5173`

## Quick Test

1. Open `http://localhost:5173` in your browser
2. Select a pipeline (BasicRAG, HybridRAG, or StructuredRAG)
3. Select a model from the dropdown
4. Choose Document Type (IR or SMAC)
5. Upload a file and click "Index"
6. Ask questions in the Q&A panel

## Notes

- Each pipeline has its own ChromaDB store — they don't interfere
- StructuredRAG requires MySQL (database `RAGPlayground` is auto-created)
- BasicRAG and HybridRAG use ChromaDB only — no MySQL needed
- The "Use LLM Parser" checkbox appears only for StructuredRAG + IR
