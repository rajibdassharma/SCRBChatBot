# Startup — RAG Playground

**Ports** — backend `8006`, frontend `5177` (see port scheme below)

Experimental RAG platform for law enforcement document analysis — structured
and agentic pipelines, chargesheet OCR extraction. Paused; will resume after
ChargePoint V2 stabilizes.

## Local Development

### Prerequisites

- Ollama running locally with `gemma3:12b` pulled:
  ```bash
  ollama pull gemma3:12b
  ollama serve
  ```

### Backend (FastAPI on :8006)

```bash
cd c:/VSCProjects/SCRBChatBot/RAGPlayground/backend
uvicorn rag_playground:app --host 0.0.0.0 --port 8006 --reload
```

### Frontend (Vite on :5177)

```bash
cd c:/VSCProjects/SCRBChatBot/RAGPlayground/frontend
npm run dev
```

Open http://localhost:5177

## First-time setup

```bash
cd c:/VSCProjects/SCRBChatBot/RAGPlayground/backend
pip install -r requirements.txt

cd ../frontend
npm install
```

## Port scheme across all local projects

| Project | Backend | Frontend |
|---|---|---|
| ChargePoint V1 | 8007 | 5173 |
| ChargePoint V2 | 8008 | 5174 |
| CyberFraudDataEntry | 8000 | 5175 |
| ISD Document Intelligence V6 | 8003 | 5176 |
| **RAG Playground** | **8006** | **5177** |
