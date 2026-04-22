# Startup — RAG Playground

Experimental RAG platform for law enforcement document analysis — structured
and agentic pipelines, chargesheet OCR extraction. **Paused**; will resume
after ChargePoint V2 stabilizes.

**Ports** — backend `8006`, frontend `5177` (see port scheme below)

See `MyProjectDashboard/STARTUP_TEMPLATE.md` for the section structure this
file follows.

## Prerequisites

- Python 3.10+, Node.js 18+
- Ollama running locally with `gemma3:12b` pulled
  ```bash
  ollama pull gemma3:12b
  ollama serve
  ```
- MySQL 8+ (only required if using the structured-tables pipeline)
- (Optional) CUDA GPU for faster OCR / embeddings

## First-time setup

```bash
cd c:/VSCProjects/SCRBChatBot/RAGPlayground/backend
pip install -r requirements.txt

cd ../frontend
npm install
```

Create `backend/.env` (only the variables you use):

```
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=gemma3:12b
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=<set-this>
MYSQL_DATABASE=rag_playground
```

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `OLLAMA_BASE_URL` | Ollama endpoint | `http://localhost:11434` |
| `OLLAMA_CHAT_MODEL` | Chat model | `gemma3:12b` |
| `OLLAMA_EMBED_MODEL` | Embedding model | `mxbai-embed-large` |
| `MYSQL_HOST` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | Structured pipeline DB | *(required for structured pipeline)* |

## Local development

```bash
# Backend (port 8006)
cd c:/VSCProjects/SCRBChatBot/RAGPlayground/backend
uvicorn rag_playground:app --host 0.0.0.0 --port 8006 --reload

# Frontend (port 5177)
cd c:/VSCProjects/SCRBChatBot/RAGPlayground/frontend
npm run dev
```

Open http://localhost:5177

## Verification

- `curl http://localhost:8006/health` → JSON with `ok: true`
- Browser http://localhost:5177 → pipeline selector UI loads
- Upload `SampleChargeSheet.docx` (in the repo root) — OCR + parse should
  populate the structured tables

## Production deployment

N/A — local experimentation only.

## Common troubleshooting

| Problem | Fix |
|---|---|
| Chargesheet extracts fewer accused than expected | OCR garbles A-number markers; tune the parser or try a clearer scan |
| `mxbai-embed-large` not found | `ollama pull mxbai-embed-large` |
| MySQL connection refused | Database not running, or credentials in `.env` don't match |

## Cross-project port scheme

| Project | Backend | Frontend |
|---|---|---|
| ChargePoint V1 | 8007 | 5173 |
| ChargePoint V2 | 8008 | 5174 |
| CyberFraudDataEntry | 8000 | 5175 |
| ISD Document Intelligence V6 | 8003 | 5176 |
| **RAG Playground** | **8006** | **5177** |
