# ISD Document Intelligence V5 — Deployment Guide

**Version:** V5.1
**Architecture:** Multi-user, case-isolated, GPU-accelerated
**Database:** MySQL 8.x
**Target Deployment:** On-premise H100 GPU server
**Last Updated:** March 20, 2026

---

## 1. Server Sizing

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **GPU** | 1x NVIDIA H100 80GB | 1x NVIDIA H100 80GB SXM |
| **RAM** | 64 GB | 128 GB |
| **CPU** | 16 cores | 32 cores (AMD EPYC or Intel Xeon) |
| **OS Disk** | 100 GB SSD | 200 GB NVMe |
| **Data Disk** | 500 GB NVMe | 2 TB NVMe (for ChromaDB + uploaded docs) |
| **Network** | 1 Gbps | 10 Gbps (internal LAN) |
| **Concurrent Users** | 5-10 | 5-10 |

> **Why H100?** The large LLM models (llama3.3:70b, llama3.1:70b) require 40-80 GB VRAM. The H100 80GB SXM fits a 70B model in full precision (BF16) with room for the embedding model alongside.

---

## 2. Operating System

**Recommended: Ubuntu 22.04 LTS (Jammy Jellyfish) -- Server Edition**

```
Download: https://ubuntu.com/download/server
Variant:  Ubuntu Server 22.04.x LTS (no GUI needed)
```

---

## 3. Architecture Overview

```
Browser (Chrome/Edge) -- Users on the LAN
         |  HTTPS :443
    nginx (reverse proxy + static file server)
    /          -> serves frontend/dist/ (React SPA)
    /api/      -> proxies to FastAPI :8001
         |  HTTP :8001 (localhost only)
    FastAPI (uvicorn, 4 workers)
    - Auth + JWT           (auth.py)
    - Case management      (cases.py)
    - RAG pipeline         (rag.py)
    - Entity graph         (entity_graph.py)
    - Activity timeline    (activity_timeline.py)
    - Location extractor   (location_extractor.py)
    - Structured tables    (structured_tables.py)
    - Answer ratings       (app.py)
         |                |                |
    Ollama :11434    sentence-        MySQL 8.x
    (LLM only)      transformers     DB: ISDIntelligence
    H100 GPU        (Embeddings)
                    Direct GPU
         |
    ChromaDB (local dir: /opt/isd/chroma_db_v5)
```

### Data Indexing Pipeline

```
Document Upload
    |
    +-- Digital PDFs (Docling table extraction, no LLM)
    |     |
    |     +-- Extract tables (Docling, OCR disabled)
    |     +-- Parse KV fields (pipe-split parser)
    |     +-- Chunk full text (pypdf)
    |     +-- Embed (sentence-transformers mxbai-embed-large-v1)
    |     +-- Store: ChromaDB (vectors + BM25) + MySQL (structured fields)
    |     +-- Tagged: source=digital
    |
    +-- Scanned PDFs (Docling + EasyOCR)
    |     |
    |     +-- OCR text extraction (Docling + EasyOCR)
    |     +-- Parse KV fields (pipe-split parser)
    |     +-- Chunk OCR'd text
    |     +-- Embed (sentence-transformers)
    |     +-- Store: ChromaDB + MySQL
    |     +-- Tagged: source=ocr
    |
    +-- IR Documents (Docling + LLM for complex nested tables)
          |
          +-- USE_LLM_PARSER=true for IR only
          +-- Store: ChromaDB + MySQL (ir_reports table)
```

### Q&A Pipeline

```
Question -> Smart Routing
    |
    +-- Aggregate? ("how many", "list all") -> NL-to-SQL -> MySQL
    +-- Field-specific? ("gist", "originator") -> Direct metadata lookup
    +-- General? -> Hybrid Retrieval:
          +-- Vector Search (ChromaDB)
          +-- BM25 Keyword Search (in-memory)
          +-- Reciprocal Rank Fusion (merge)
          +-- LLM Re-ranking (optional)
    |
    All results -> LLM generates answer (gemma3:12b / llama3.3:70b)
    |
    Post-processing: hallucination guard, strip non-Latin chars
```

---

## 4. Step-by-Step Installation

### 4.1 -- System Updates & Basic Tools

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl wget git unzip build-essential \
    ca-certificates gnupg lsb-release software-properties-common
```

### 4.2 -- NVIDIA GPU Drivers + CUDA

```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update
sudo apt install -y cuda-toolkit-12-4 nvidia-driver-550
sudo reboot

# Verify after reboot
nvidia-smi
```

### 4.3 -- Ollama (LLM Runtime)

Ollama is used **only for LLM inference** (Q&A, entity extraction). Embeddings are handled by sentence-transformers.

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull gemma3:12b
ollama pull llama3.3:70b    # production LLM

# Configure to bind localhost only
sudo systemctl edit ollama
```

Add override:
```ini
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_NUM_PARALLEL=2"
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
sudo systemctl enable ollama
```

### 4.4 -- MySQL 8.x

```bash
sudo apt install -y mysql-server
sudo mysql_secure_installation
sudo systemctl enable mysql
sudo systemctl start mysql

sudo mysql -u root -p <<EOF
CREATE DATABASE IF NOT EXISTS ISDIntelligence
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'isd_user'@'localhost' IDENTIFIED BY '<STRONG_PASSWORD>';
GRANT ALL PRIVILEGES ON ISDIntelligence.* TO 'isd_user'@'localhost';
FLUSH PRIVILEGES;
EOF
```

### 4.5 -- Python Environment & Dependencies

**Important:** Python 3.12 is required. Python 3.13 is NOT supported (PyTorch CUDA).

```bash
sudo apt install -y python3.12 python3.12-venv
python3.12 -m venv /opt/isd/venv
source /opt/isd/venv/bin/activate

# Install PyTorch with CUDA support FIRST (before other packages)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# Verify GPU
python -c "import torch; print(torch.cuda.is_available())"
# Must print: True

# Install all backend dependencies
cd /opt/isd/backend
pip install -r requirements.txt
```

#### Complete Package List (requirements.txt)

```
fastapi                    - Web framework
uvicorn                    - ASGI server
python-dotenv              - .env file loading
requests                   - HTTP client (Ollama API)
pypdf                      - PDF text extraction
chromadb                   - Vector database
python-multipart           - File upload handling
python-docx                - DOCX parsing
openpyxl                   - Excel parsing
faster-whisper             - Speech-to-text (voice input)
rank-bm25                  - BM25 keyword search
pymysql                    - MySQL connector
python-jose[cryptography]  - JWT authentication
passlib[bcrypt]            - Password hashing
neo4j>=5.0                 - Neo4j driver (entity graph)
gunicorn                   - Production WSGI server
sentence-transformers      - Embedding model (mxbai-embed-large-v1)
pyspellchecker             - Spell checking
docling                    - PDF table structure extraction
easyocr                    - OCR for scanned documents
```

#### One-Time Model Downloads (requires internet)

These models are downloaded once and cached locally. After download, the server runs fully offline.

```bash
# 1. Sentence-transformers embedding model (~670 MB)
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('mixedbread-ai/mxbai-embed-large-v1')"

# 2. Docling ML models (~2 GB) -- needed for PDF table extraction
python -c "from docling.document_converter import DocumentConverter; DocumentConverter()"

# 3. EasyOCR models (~100 MB) -- needed for scanned PDF processing
python -c "import easyocr; easyocr.Reader(['en'])"

# 4. Spellchecker dictionary (bundled with package)
python -c "from spellchecker import SpellChecker; SpellChecker()"
```

> **Offline Operation:** After all models are downloaded, set `HF_HUB_OFFLINE=1` in `.env`. The server can then be fully disconnected from the internet.

### 4.6 -- Node.js (for frontend build only)

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### 4.7 -- nginx

```bash
sudo apt install -y nginx
sudo systemctl enable nginx
```

---

## 5. Deploy the Application

### 5.1 -- Copy Files to Server

```bash
rsync -av --exclude='node_modules' --exclude='__pycache__' \
    --exclude='chroma_db*' --exclude='*.db' --exclude='dist' \
    "YAIA-main/ISDDocumentIntelligence_V5/" \
    deploy_user@<SERVER_IP>:/opt/isd/
```

### 5.2 -- Configure Backend Environment

```bash
cd /opt/isd/backend
nano .env
```

Production `.env`:
```ini
OLLAMA_BASE_URL=http://127.0.0.1:11434
PDF_MODEL=gemma3:12b
EMBED_MODEL=mxbai-embed-large
CHROMA_PATH=/opt/isd/chroma_db_v5

# JWT -- generate: python3 -c "import secrets; print(secrets.token_hex(48))"
JWT_SECRET_KEY=<64-character-random-hex-string>
JWT_EXPIRE_HOURS=12

WHISPER_MODEL=small

ENABLE_HYBRID_SEARCH=true
ENABLE_MULTI_QUERY=true
ENABLE_RERANKING=true

# LLM parser: false for SMAC (Docling handles it), true for IR
USE_LLM_PARSER=false
MAX_LLM_CALLS_PDF=25

# Embeddings: sentence-transformers direct GPU (recommended)
USE_OLLAMA_EMBEDDINGS=false

# Offline mode
HF_HUB_OFFLINE=1

# MySQL
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=isd_user
MYSQL_PASSWORD=<STRONG_PASSWORD>
MYSQL_DATABASE=ISDIntelligence
```

```bash
chmod 600 /opt/isd/backend/.env
```

### 5.3 -- Build the Frontend

```bash
cd /opt/isd/frontend
echo "VITE_API_BASE=https://<SERVER_DOMAIN_OR_IP>" > .env
npm install --legacy-peer-deps
npm run build
```

### 5.4 -- Configure nginx

```bash
sudo nano /etc/nginx/sites-available/isd-v5
```

```nginx
server {
    listen 80;
    server_name <SERVER_DOMAIN_OR_IP>;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name <SERVER_DOMAIN_OR_IP>;

    ssl_certificate     /etc/ssl/isd/server.crt;
    ssl_certificate_key /etc/ssl/isd/server.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    client_max_body_size 200M;

    root /opt/isd/frontend/dist;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        rewrite ^/api/(.*) /$1 break;
        proxy_pass         http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/isd-v5 /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 5.5 -- SSL Certificate (Self-signed for internal LAN)

```bash
sudo mkdir -p /etc/ssl/isd
sudo openssl req -x509 -nodes -days 3650 -newkey rsa:4096 \
    -keyout /etc/ssl/isd/server.key \
    -out /etc/ssl/isd/server.crt \
    -subj "/C=IN/ST=Karnataka/O=KSP/CN=<SERVER_IP>"
```

### 5.6 -- systemd Service for Backend

```bash
sudo nano /etc/systemd/system/isd-backend.service
```

```ini
[Unit]
Description=ISD Document Intelligence V5 Backend
After=network.target mysql.service ollama.service

[Service]
Type=exec
User=isd
Group=isd
WorkingDirectory=/opt/isd/backend
Environment="PATH=/opt/isd/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
EnvironmentFile=/opt/isd/backend/.env
ExecStart=/opt/isd/venv/bin/uvicorn app:app \
    --host 127.0.0.1 \
    --port 8001 \
    --workers 4 \
    --timeout-keep-alive 600
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo useradd -r -s /bin/false -d /opt/isd isd
sudo chown -R isd:isd /opt/isd
sudo systemctl daemon-reload
sudo systemctl enable isd-backend
sudo systemctl start isd-backend
```

### 5.7 -- Create the First Admin User

```bash
curl -k -X POST https://<SERVER_IP>/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<STRONG_ADMIN_PASSWORD>","full_name":"Administrator"}'

mysql -u isd_user -p ISDIntelligence -e \
  "UPDATE users SET role='admin' WHERE username='admin';"
```

---

## 6. Data Indexing

### 6.1 -- Start Services

```bash
sudo systemctl start ollama
ollama run gemma3:12b "hello"

source /opt/isd/venv/bin/activate
cd /opt/isd/backend
uvicorn app:app --host 0.0.0.0 --port 8001
```

### 6.2 -- Digital SMAC Reports (Docling, no OCR)

For PDF files with selectable text (typically 2025-2026 documents):

```bash
source /opt/isd/venv/bin/activate
cd /opt/isd/dbscripts
python bulk_index_smac_ir.py \
    --folder "/data/SMAC/Digital" \
    --case-id 0 \
    --username rajibds \
    --password rajibds \
    --workers 5
```

**Speed:** ~5-6 seconds per document.

**Reset digital data only:**
```bash
python bulk_index_smac_ir.py --reset --username rajibds --password rajibds
```

### 6.3 -- Scanned SMAC Reports (Docling + EasyOCR)

For scanned PDF files (typically 2018-2024 documents):

```bash
source /opt/isd/venv/bin/activate
cd /opt/isd/backend
python ../dbscripts/ocr_index_smac.py --folder "/data/SMAC/Scanned"
```

**Speed:** ~10-11 seconds per document.

**Resume after interruption:** Just re-run the same command. The progress DB tracks completed files.

**Reset OCR data only:**
```bash
python ../dbscripts/ocr_index_smac.py --reset
```

### 6.4 -- IR Documents

For IR Form-16 interrogation reports (DOCX and PDF):

```bash
# Set USE_LLM_PARSER=true in .env for IR documents
# Then use bulk indexer or upload through the UI

cd /opt/isd/dbscripts
python bulk_index_smac_ir.py \
    --folder "/data/IR" \
    --collection IR \
    --case-id 0 \
    --username rajibds \
    --password rajibds \
    --workers 1
```

**Speed:** ~30-60 seconds per document (LLM parsing).

### 6.5 -- Skipped Files

The bulk indexer automatically skips files named: `Report`, `Reports`, `Feedback`, `Attachment`, `Attachments`.

Scanned files (0 extractable text) are logged to `dbscripts/pdfs_pending_ocr.txt` during digital indexing.

### 6.6 -- Re-Indexing from Scratch

```bash
# Reset digital
python bulk_index_smac_ir.py --reset --username rajibds --password rajibds

# Reset OCR
cd /opt/isd/backend
python ../dbscripts/ocr_index_smac.py --reset

# Then re-run both indexing commands
```

### 6.7 -- Monitoring Progress

```bash
# MySQL records
mysql -u isd_user -p ISDIntelligence -e "SELECT COUNT(DISTINCT doc_id) FROM smac_reports;"
mysql -u isd_user -p ISDIntelligence -e "SELECT field_key, COUNT(*) as cnt FROM smac_reports GROUP BY field_key ORDER BY cnt DESC LIMIT 15;"

# GPU usage
nvidia-smi

# Backend logs
sudo journalctl -u isd-backend -f
```

---

## 7. Database Schema

### smac_reports (EAV -- Entity-Attribute-Value)

```sql
CREATE TABLE smac_reports (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    doc_id       VARCHAR(255)  NOT NULL,
    doc_name     VARCHAR(500)  NOT NULL,
    serial_no    VARCHAR(50)   NULL,
    field_key    VARCHAR(255)  NOT NULL,
    field_value  TEXT          NULL,
    case_id      INT           NULL,
    UNIQUE KEY uq_smac_reports (doc_id, field_key)
);
```

Common SMAC field_key values: `TMS I.D.`, `Originator`, `Date`, `Theatre`, `Current Priority`, `Subject`, `Input`, `Grading`, `Has Attachment`, `Input Closed?`

### ir_reports (EAV)

```sql
CREATE TABLE ir_reports (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    doc_id       VARCHAR(255)  NOT NULL,
    doc_name     VARCHAR(500)  NOT NULL,
    collection   VARCHAR(100)  NOT NULL DEFAULT 'IR',
    serial_no    VARCHAR(50)   NULL,
    field_key    VARCHAR(255)  NOT NULL,
    field_value  TEXT          NULL,
    case_id      INT           NULL,
    UNIQUE KEY uq_ir_reports (doc_id, field_key)
);
```

### Other Tables

`users`, `cases`, `entities`, `relationships`, `activities`, `cross_references`, `doc_locations`, `answer_ratings` -- auto-created by `init_db()` on backend startup.

---

## 8. Firewall Rules

```bash
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 8001/tcp
sudo ufw deny 11434/tcp
sudo ufw deny 3306/tcp
```

---

## 9. Directory Structure

```
/opt/isd/
|-- venv/                    <- Python 3.12 virtual environment
|-- backend/
|   |-- app.py
|   |-- auth.py
|   |-- cases.py
|   |-- rag.py               <- RAG pipeline + Docling SMAC parser
|   |-- entity_graph.py
|   |-- activity_timeline.py
|   |-- location_extractor.py
|   |-- structured_tables.py  <- EAV tables for SMAC + IR
|   |-- llm_kv_extractor.py   <- Docling + LLM extraction
|   |-- mysql_db.py
|   |-- config.py
|   |-- ollama_client.py      <- embedding toggle logic
|   |-- requirements.txt
|   `-- .env                  <- production secrets (chmod 600)
|-- frontend/
|   |-- src/
|   |-- dist/                 <- built static files served by nginx
|   `-- .env                  <- VITE_API_BASE for build
|-- dbscripts/
|   |-- bulk_index_smac_ir.py    <- digital SMAC indexer (source=digital)
|   |-- ocr_index_smac.py     <- scanned SMAC indexer (source=ocr)
|   |-- migrate_chroma_to_mysql.py  <- ChromaDB -> MySQL migration
|   |-- .smac_bulk_progress.db      <- digital indexing progress (auto-created)
|   `-- .smac_ocr_progress.db       <- OCR indexing progress (auto-created)
|-- chroma_db_v5/             <- ChromaDB vector store (auto-created)
`-- restart_ollama.sh         <- Ollama auto-restart script
```

---

## 10. LLM & Embedding Configuration

### LLM Models (via Ollama)

| Environment | PDF_MODEL | Notes |
|---|---|---|
| Development (laptop) | `gemma3:12b` | Fast, fits in 12 GB VRAM |
| Production (H100) | `llama3.3:70b` | Best accuracy |

### Embedding Model (sentence-transformers)

| Setting | Method |
|---|---|
| `USE_OLLAMA_EMBEDDINGS=false` | sentence-transformers direct GPU (**recommended**) |
| `USE_OLLAMA_EMBEDDINGS=true` | Ollama HTTP API (legacy fallback) |

### Indexing Configuration

| Setting | Digital SMAC | Scanned SMAC | IR |
|---|---|---|---|
| `USE_LLM_PARSER` | false (Docling only) | false (Docling+OCR) | true (Docling+LLM) |
| Parser | Docling table + pipe-split | Docling+EasyOCR + pipe-split | Docling+LLM KV extraction |
| Speed | ~5s/doc | ~11s/doc | ~30-60s/doc |
| Script | bulk_index_smac_ir.py | ocr_index_smac.py | bulk_index_smac_ir.py --collection IR |

---

## 11. Health Checks

```bash
curl -s http://127.0.0.1:8001/health | python3 -m json.tool
nvidia-smi
sudo journalctl -u isd-backend -f
sudo tail -f /var/log/nginx/access.log
```

---

## 12. Backup Strategy

```bash
# MySQL
mysqldump -u isd_user -p ISDIntelligence > /opt/backups/isd_$(date +%Y%m%d).sql

# ChromaDB (stop service first)
sudo systemctl stop isd-backend
tar -czf /opt/backups/chroma_$(date +%Y%m%d).tar.gz /opt/isd/chroma_db_v5/
sudo systemctl start isd-backend

# Automate: crontab -e -> 0 2 * * * /opt/scripts/backup_isd.sh
```

---

## 13. Quick-Start Checklist

```
[ ] Ubuntu 22.04 LTS installed, updated
[ ] NVIDIA driver 550 + CUDA 12.4 installed, nvidia-smi works
[ ] Ollama installed, gemma3:12b pulled, OLLAMA_NUM_PARALLEL=2 set
[ ] MySQL 8.x installed, ISDIntelligence database created
[ ] Python 3.12 venv created at /opt/isd/venv
[ ] PyTorch installed with CUDA: torch.cuda.is_available() returns True
[ ] pip install -r requirements.txt (includes sentence-transformers, docling, easyocr)
[ ] Model downloads completed:
    [ ] sentence-transformers mxbai-embed-large-v1 (~670 MB)
    [ ] Docling ML models (~2 GB)
    [ ] EasyOCR English model (~100 MB)
[ ] /opt/isd/backend/.env configured
[ ] USE_OLLAMA_EMBEDDINGS=false, USE_LLM_PARSER=false, HF_HUB_OFFLINE=1
[ ] Frontend built: npm run build
[ ] nginx configured with SSL, nginx -t passes
[ ] systemd isd-backend service enabled and running
[ ] Firewall: 443 open, 8001/11434/3306 blocked
[ ] Admin user registered and promoted
[ ] Digital SMAC indexing: bulk_index_smac_ir.py --folder ...
[ ] Scanned SMAC indexing: ocr_index_smac.py --folder ...
[ ] Verify MySQL: SELECT field_key, COUNT(*) FROM smac_reports GROUP BY field_key
[ ] Test Q&A in browser
[ ] Backup cron scheduled
```

---

*Document prepared for ISD Document Intelligence V5 -- March 2026*
