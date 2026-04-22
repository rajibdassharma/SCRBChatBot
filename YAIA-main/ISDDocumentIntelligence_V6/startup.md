# Startup — ISD Document Intelligence V6

Fully offline, air-gapped document intelligence platform for Internal
Security Division analysts. Two pipelines (IR Form-16 pure-Python parser;
SMAC surveillance via HybridRAG) plus entity graph, activity timeline,
and location extraction. **Deployed** single-user on a dedicated
air-gapped Ubuntu server.

**Ports** — backend `8003`, frontend `5176` (see port scheme below)

See `MyProjectDashboard/STARTUP_TEMPLATE.md` for the section structure this
file follows.

## Prerequisites

- Python 3.10+, Node.js 18+
- Ollama with `gemma3:12b` pulled
- MySQL 8+ (database `ISDIntelligence` auto-created on first boot)
- CUDA GPU strongly recommended for sentence-transformers embedding mode
- EasyOCR + Docling dependencies (installed via `requirements.txt`)

## First-time setup

```bash
cd c:/VSCProjects/SCRBChatBot/YAIA-main/ISDDocumentIntelligence_V6/backend

# Install PyTorch FIRST for GPU support (critical — do not skip this order)
pip install torch --index-url https://download.pytorch.org/whl/cu124

# Then the rest
pip install -r requirements.txt

cd ../frontend
npm install
```

Create `backend/.env` (see Environment variables below).

## Environment variables

Key settings (see `backend/config.py` for the full list):

| Variable | Purpose | Default |
|---|---|---|
| `OLLAMA_BASE_URL` | Ollama endpoint | `http://localhost:11434` |
| `PDF_MODEL` | Generation LLM | `gemma3:12b` |
| `EMBED_MODEL` | Embedding model name | `mxbai-embed-large` |
| `CHROMA_PATH_SMAC` | SMAC vector store | `chroma_db_smac_v6` |
| `CHROMA_PATH_IR` | IR vector store | `chroma_db_ir_v6` |
| `ENABLE_HYBRID_SEARCH` | BM25 + vector fusion | `true` |
| `ENABLE_MULTI_QUERY` | Synonym query expansion | `true` |
| `ENABLE_RERANKING` | LLM re-ranking | `true` |
| `USE_OLLAMA_EMBEDDINGS` | `true` = HTTP, `false` = GPU sentence-transformers | `true` |
| `USE_LLM_PARSER_IR` / `_SMAC` | LLM-based doc parsing | `true` / `false` |
| `MAX_LLM_CALLS_PDF` | Max LLM calls per PDF | `25` |
| `MYSQL_HOST` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | DB creds | localhost / root / `Sandy@411` (local) / `ISDIntelligence` |
| `JWT_SECRET_KEY` | JWT signing secret | *(change in prod)* |
| `JWT_EXPIRE_HOURS` | Token expiry | `24` |
| `WHISPER_MODEL` | Speech-to-text model | `small` |

Production server MySQL password: `isdadmin`.

## Local development

```bash
# Backend (port 8003)
cd c:/VSCProjects/SCRBChatBot/YAIA-main/ISDDocumentIntelligence_V6/backend
uvicorn app:app --host 0.0.0.0 --port 8003 --reload

# Frontend (port 5176)
cd c:/VSCProjects/SCRBChatBot/YAIA-main/ISDDocumentIntelligence_V6/frontend
npm run dev
```

Open http://localhost:5176

> **Note:** backend module is `app:app` (not following the project-named
> convention other projects use). Kept as-is because production server
> scripts reference this name — renaming requires a coordinated server
> update.

## Verification

- `curl http://localhost:8003/health` → `{"status": "ok"}`
- Browser http://localhost:5176 → login page, then four tabs after auth
  (Doc Intel, Graph, Map, Timeline)
- Register a test user via `/auth/register`, log in, create a case, upload
  a sample PDF — should extract entities/timeline in the background
- Ollama reachable: `curl http://localhost:11434/api/tags` should list
  `gemma3:12b`

## Bulk indexing

```bash
cd c:/VSCProjects/SCRBChatBot/YAIA-main/ISDDocumentIntelligence_V6/dbscripts

# SMAC documents (parallel, 3 workers)
python bulk_index_smac.py --folder "C:/SMAC_Files" --case-id 0 \
  --username admin --password secret --workers 3

# IR documents (sequential)
python bulk_index_ir.py --folder "C:/IR_Files" \
  --username admin --password secret

# OCR for scanned PDFs (reads pdfs_pending_ocr.txt from SMAC bulk run)
python ocr_index_smac.py --case-id 0

# Reset progress and re-index
python bulk_index_smac.py --folder "C:/SMAC_Files" --case-id 0 --reset

# Dry run (preview without uploading)
python bulk_index_ir.py --folder "C:/IR_Files" --dry-run
```

## Production deployment (air-gapped Ubuntu server)

**Target:** `/opt/isd/ISDDocumentIntelligence_V6/` on a dedicated Ubuntu
server with RDP access over dedicated LAN. **No internet** — all updates
travel via USB.

Two systemd services keep the apps running and survive reboots:

| Service | Purpose | Port |
|---|---|---|
| `isd-backend` | FastAPI via uvicorn | 8003 |
| `isd-frontend` | python3 http.server serving `frontend/dist/` | 5176 |

Both unit files live in [`deploy/`](deploy/) in the repo — see
[deploy/README.md](deploy/README.md) for the full one-time install and
reboot-survival checklist.

### One-time install (first deploy only)

Follow `deploy/README.md`. Key step that makes the services survive
reboots:

```bash
sudo systemctl enable --now isd-backend isd-frontend
sudo systemctl enable mysql ollama
```

Verify with:
```bash
systemctl is-enabled isd-backend isd-frontend mysql
# All three should print: enabled
```

### Update procedure (subsequent deploys)

```bash
# On your laptop (with internet)
cd c:/VSCProjects/SCRBChatBot/YAIA-main/ISDDocumentIntelligence_V6/frontend
npm run build                                   # produces dist/

# Copy the repo (or just backend/ + frontend/dist/ + deploy/) to USB

# On the server (via USB drop)
cd /opt/isd/ISDDocumentIntelligence_V6
# Copy updated files from USB over the existing tree

# Refresh Python deps if requirements.txt changed
source /opt/isd/venv/bin/activate
pip install -r backend/requirements.txt

# Sync systemd unit files (only needed when deploy/*.service changes)
sudo cp deploy/isd-backend.service /etc/systemd/system/isd-backend.service
sudo cp deploy/isd-frontend.service /etc/systemd/system/isd-frontend.service
sudo systemctl daemon-reload

# Restart
sudo systemctl restart isd-backend isd-frontend
```

### Post-deploy verification

```bash
sudo systemctl status isd-backend       # must show: active (running)
sudo systemctl status isd-frontend      # must show: active (running)
curl http://localhost:8003/health       # should return {"status":"ok"}
tail -f /var/log/isd/backend.log        # live logs
```

From a client on the LAN: browse to `http://<server-ip>:5176/`.

### Rollback

```bash
cd /opt/isd/ISDDocumentIntelligence_V6
git log --oneline -10                   # find previous good SHA
git checkout <previous-sha>
sudo cp deploy/isd-backend.service /etc/systemd/system/isd-backend.service
sudo systemctl daemon-reload
sudo systemctl restart isd-backend isd-frontend
```

## Common troubleshooting

| Problem | Fix |
|---|---|
| Ollama requests time out | `ollama serve` not running on the server; start it |
| Embeddings extremely slow | Set `USE_OLLAMA_EMBEDDINGS=false` to use GPU sentence-transformers (requires CUDA) |
| IR parser returns empty | Form-16 table must be exactly 3 columns (Serial No · Field · Value); check table structure in the DOCX |
| Chargesheet/SMAC returns 0 chunks | PDF is scanned — add to `pdfs_pending_ocr.txt` and run `ocr_index_smac.py` |
| `case_id` not scoping properly | All API calls must pass `case_id`; otherwise defaults to case 0 |

## Cross-project port scheme

| Project | Backend | Frontend |
|---|---|---|
| ChargePoint V1 | 8007 | 5173 |
| ChargePoint V2 | 8008 | 5174 |
| CyberFraudDataEntry | 8000 | 5175 |
| **ISD Document Intelligence V6** | **8003** | **5176** |
| RAG Playground | 8006 | 5177 |
