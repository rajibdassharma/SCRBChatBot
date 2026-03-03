# ISD Document Intelligence V4 — Deployment Guide

**Version:** V4
**Architecture:** Multi-user, case-isolated, GPU-accelerated
**Target Deployment:** On-premise H100 GPU server

---

## 1. Server Sizing

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **GPU** | 1× NVIDIA H100 80GB | 1× NVIDIA H100 80GB SXM |
| **RAM** | 64 GB | 128 GB |
| **CPU** | 16 cores | 32 cores (AMD EPYC or Intel Xeon) |
| **OS Disk** | 100 GB SSD | 200 GB NVMe |
| **Data Disk** | 500 GB NVMe | 2 TB NVMe (for ChromaDB + uploaded docs) |
| **Network** | 1 Gbps | 10 Gbps (internal LAN) |
| **Concurrent Users** | 5–10 | 5–10 |

> **Why H100?** The large LLM models (llama3.3:70b, llama3.1:70b) require 40–80 GB VRAM. The H100 80GB SXM fits a 70B model in full precision (BF16) with room for the embedding model alongside.

---

## 2. Operating System

**Recommended: Ubuntu 22.04 LTS (Jammy Jellyfish) — Server Edition**

Ubuntu 22.04 is the standard OS for NVIDIA GPU workloads. It has the best driver support, long-term security updates (until 2027), and runs MSSQL Server natively via the Microsoft Linux repository.

```
Download: https://ubuntu.com/download/server
Variant:  Ubuntu Server 22.04.x LTS (no GUI needed)
```

> **If a Windows Server environment is mandatory:** Use Windows Server 2022 Standard. All commands in this guide have Windows equivalents, but Linux is strongly preferred for GPU stability.

---

## 3. Software Stack

```
┌─────────────────────────────────────────────────────────┐
│  Browser (Chrome / Edge)  ←  Users on the LAN           │
└─────────────────┬───────────────────────────────────────┘
                  │ HTTPS :443
┌─────────────────▼───────────────────────────────────────┐
│  nginx  (reverse proxy + static file server)            │
│    /          → serves frontend/dist/ (React SPA)       │
│    /api/      → proxies to FastAPI :8001                 │
└─────────────────┬───────────────────────────────────────┘
                  │ HTTP :8001 (localhost only)
┌─────────────────▼───────────────────────────────────────┐
│  FastAPI (uvicorn, 4 workers)                            │
│  • Auth + JWT           (auth.py)                       │
│  • Case management      (cases.py)                      │
│  • RAG pipeline         (rag.py)                        │
│  • Entity graph         (entity_graph.py)               │
│  • Activity timeline    (activity_timeline.py)          │
│  • Location extractor   (location_extractor.py)         │
│  • Structured tables    (structured_tables.py)          │
└────────┬──────────────────────────┬─────────────────────┘
         │                          │
┌────────▼────────┐      ┌─────────▼──────────────────────┐
│  Ollama :11434  │      │  Microsoft SQL Server 2022      │
│  (LLM + Embed)  │      │  Database: ISDIntelligenceV4    │
│  H100 GPU       │      │  Auth: SQL Auth (username/pwd)  │
└─────────────────┘      └────────────────────────────────┘
         │
┌────────▼────────────────────────────────────────────────┐
│  ChromaDB  (local directory: /opt/isd/chroma_db_v4)     │
│  faster-whisper  (STT, CPU or GPU)                      │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Step-by-Step Installation

### 4.1 — System Updates & Basic Tools

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl wget git unzip build-essential \
    ca-certificates gnupg lsb-release software-properties-common
```

---

### 4.2 — NVIDIA GPU Drivers + CUDA

```bash
# Add NVIDIA package repo
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update

# Install CUDA 12.x toolkit and drivers
sudo apt install -y cuda-toolkit-12-4 nvidia-driver-550

# Reboot
sudo reboot

# Verify after reboot
nvidia-smi
# Expected: shows H100 80GB, driver version, CUDA version
```

---

### 4.3 — Ollama (LLM Runtime)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Verify GPU is detected
ollama serve &
ollama run llama3.1:8b "Say hello"   # quick test with small model

# Pull production models
ollama pull llama3.3:70b             # primary LLM (requires ~80 GB VRAM)
ollama pull mxbai-embed-large        # embedding model
ollama pull gemma3:12b               # fallback / faster LLM

# Configure Ollama to bind only to localhost (security)
sudo systemctl edit ollama
```

Add the following override in the editor:
```ini
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
sudo systemctl enable ollama
```

---

### 4.4 — Microsoft SQL Server 2022

```bash
# Add Microsoft SQL Server repo
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg
curl https://packages.microsoft.com/config/ubuntu/22.04/mssql-server-2022.list \
    | sudo tee /etc/apt/sources.list.d/mssql-server.list

sudo apt update
sudo apt install -y mssql-server

# Run setup wizard (choose Developer/Express edition for on-premise)
sudo /opt/mssql/bin/mssql-conf setup

# Enable and start
sudo systemctl enable mssql-server
sudo systemctl start mssql-server

# Install sqlcmd tools
curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list \
    | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt update
sudo ACCEPT_EULA=Y apt install -y mssql-tools18 unixodbc-dev

echo 'export PATH="$PATH:/opt/mssql-tools18/bin"' >> ~/.bashrc
source ~/.bashrc

# Create the V4 database and a SQL auth user
sqlcmd -S localhost -U sa -P '<SA_PASSWORD>' -Q "
CREATE DATABASE ISDIntelligenceV4;
CREATE LOGIN isd_user WITH PASSWORD = '<STRONG_PASSWORD>';
USE ISDIntelligenceV4;
CREATE USER isd_user FOR LOGIN isd_user;
ALTER ROLE db_owner ADD MEMBER isd_user;
"
```

---

### 4.5 — ODBC Driver for Python (pyodbc)

```bash
# Add Microsoft ODBC repo (same key already added above)
curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list \
    | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt update
sudo ACCEPT_EULA=Y apt install -y msodbcsql17 msodbcsql18
```

Test:
```bash
python3 -c "import pyodbc; print(pyodbc.drivers())"
# Should list: ['ODBC Driver 17 for SQL Server', 'ODBC Driver 18 for SQL Server']
```

---

### 4.6 — Python Environment (Miniconda)

```bash
# Install Miniconda
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh -b -p /opt/miniconda3
echo 'export PATH="/opt/miniconda3/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Create dedicated environment
conda create -n isd python=3.11 -y
conda activate isd

# Install backend dependencies
cd /opt/isd/backend
pip install -r requirements.txt

# Install docling (LLM PDF parser)
pip install docling
```

---

### 4.7 — Node.js (for frontend build only)

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node --version   # should be 20.x
npm --version
```

---

### 4.8 — nginx

```bash
sudo apt install -y nginx
sudo systemctl enable nginx
```

---

## 5. Deploy the Application

### 5.1 — Copy Files to Server

From your development machine (Windows), transfer the project to the server. Exclude `node_modules`, `__pycache__`, `chroma_db*`, and `*.db`.

**Option A — rsync (from WSL or Linux):**
```bash
rsync -av --exclude='node_modules' --exclude='__pycache__' \
    --exclude='chroma_db*' --exclude='*.db' --exclude='dist' \
    "YAIA-main/ISDDocumentIntelligence_V4/" \
    deploy_user@<SERVER_IP>:/opt/isd/
```

**Option B — Git (recommended for repeatable deploys):**
```bash
# On server
sudo mkdir -p /opt/isd
sudo chown $USER:$USER /opt/isd
cd /opt/isd
git clone <your-repo-url> .
# or git pull for updates
```

---

### 5.2 — Configure Backend Environment

```bash
cd /opt/isd/backend
cp .env .env.bak        # keep backup of dev .env
nano .env
```

Production `.env` values:
```ini
OLLAMA_BASE_URL=http://127.0.0.1:11434
PDF_MODEL=llama3.3:70b
EMBED_MODEL=mxbai-embed-large
CHROMA_PATH=/opt/isd/chroma_db_v4

# JWT — generate a strong random key:
# python3 -c "import secrets; print(secrets.token_hex(48))"
JWT_SECRET_KEY=<64-character-random-hex-string>
JWT_EXPIRE_HOURS=12

WHISPER_MODEL=small

ENABLE_HYBRID_SEARCH=true
ENABLE_MULTI_QUERY=true
ENABLE_RERANKING=true
USE_LLM_PARSER=true
MAX_LLM_CALLS_PDF=25

# SQL Server — use SQL Auth (no Windows Auth on Linux)
MSSQL_SERVER=localhost
MSSQL_DATABASE=ISDIntelligenceV4
MSSQL_DRIVER=ODBC Driver 17 for SQL Server
MSSQL_AUTH=sql
MSSQL_USER=isd_user
MSSQL_PASSWORD=<STRONG_PASSWORD>
```

Set restrictive permissions on the .env file:
```bash
chmod 600 /opt/isd/backend/.env
```

---

### 5.3 — Build the Frontend

```bash
cd /opt/isd/frontend

# Point API base to the server (nginx will proxy /api → :8001)
# Edit .env to use relative path or server IP:
echo "VITE_API_BASE=https://<SERVER_DOMAIN_OR_IP>" > .env

npm install --legacy-peer-deps
npm run build
# Output: frontend/dist/
```

---

### 5.4 — Configure nginx

```bash
sudo nano /etc/nginx/sites-available/isd-v4
```

Paste the following (replace `<SERVER_DOMAIN_OR_IP>` with your actual domain or IP):

```nginx
server {
    listen 80;
    server_name <SERVER_DOMAIN_OR_IP>;

    # Redirect HTTP → HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name <SERVER_DOMAIN_OR_IP>;

    # SSL certificates (see Section 5.5)
    ssl_certificate     /etc/ssl/isd/server.crt;
    ssl_certificate_key /etc/ssl/isd/server.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Increase upload limit for large PDFs / DOCX files
    client_max_body_size 200M;

    # Serve React SPA
    root /opt/isd/frontend/dist;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy API calls to FastAPI backend
    location /api/ {
        rewrite ^/api/(.*) /$1 break;
        proxy_pass         http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 600s;    # long timeout for LLM inference
        proxy_send_timeout 600s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/isd-v4 /etc/nginx/sites-enabled/
sudo nginx -t           # test config
sudo systemctl reload nginx
```

> **Note on VITE_API_BASE:** If nginx proxies `/api/` to the backend, set `VITE_API_BASE=/api` in the frontend `.env` before building. If frontend and backend share the same domain via nginx, you can use an empty base or `/api`.

---

### 5.5 — SSL Certificate

**Option A — Self-signed (internal LAN, no public domain):**
```bash
sudo mkdir -p /etc/ssl/isd
sudo openssl req -x509 -nodes -days 3650 -newkey rsa:4096 \
    -keyout /etc/ssl/isd/server.key \
    -out /etc/ssl/isd/server.crt \
    -subj "/C=IN/ST=Karnataka/O=KSP/CN=<SERVER_IP>"
```
Users will see a browser warning for self-signed certs — click "Advanced → Proceed".

**Option B — Let's Encrypt (if server has a public domain):**
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d <your.domain.com>
```

---

### 5.6 — systemd Service for FastAPI Backend

```bash
sudo nano /etc/systemd/system/isd-backend.service
```

```ini
[Unit]
Description=ISD Document Intelligence V4 Backend
After=network.target mssql-server.service ollama.service

[Service]
Type=exec
User=isd
Group=isd
WorkingDirectory=/opt/isd/backend
Environment="PATH=/opt/miniconda3/envs/isd/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
EnvironmentFile=/opt/isd/backend/.env
ExecStart=/opt/miniconda3/envs/isd/bin/uvicorn app:app \
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
# Create a dedicated system user for the service
sudo useradd -r -s /bin/false -d /opt/isd isd
sudo chown -R isd:isd /opt/isd

sudo systemctl daemon-reload
sudo systemctl enable isd-backend
sudo systemctl start isd-backend
sudo systemctl status isd-backend
```

---

### 5.7 — Create the First Admin User

Once the backend is running, register the first user via the API and promote them to admin:

```bash
# Register admin user
curl -k -X POST https://<SERVER_IP>/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<STRONG_ADMIN_PASSWORD>","full_name":"Administrator"}'

# Promote to admin in MSSQL
sqlcmd -S localhost -U isd_user -P '<PASSWORD>' -d ISDIntelligenceV4 -Q \
  "UPDATE users SET role='admin' WHERE username='admin';"
```

---

## 6. Firewall Rules

```bash
sudo ufw enable
sudo ufw allow ssh          # port 22
sudo ufw allow 80/tcp       # HTTP (redirects to HTTPS)
sudo ufw allow 443/tcp      # HTTPS (nginx)
sudo ufw deny 8001/tcp      # block direct FastAPI access from outside
sudo ufw deny 11434/tcp     # block direct Ollama access from outside
sudo ufw deny 1433/tcp      # block direct MSSQL access from outside
sudo ufw status
```

---

## 7. Directory Structure on Server

```
/opt/isd/
├── backend/
│   ├── app.py
│   ├── auth.py
│   ├── cases.py
│   ├── rag.py
│   ├── entity_graph.py
│   ├── activity_timeline.py
│   ├── location_extractor.py
│   ├── structured_tables.py
│   ├── llm_kv_extractor.py
│   ├── mssql_db.py
│   ├── config.py
│   ├── requirements.txt
│   └── .env                  ← production secrets (chmod 600)
├── frontend/
│   ├── src/
│   ├── dist/                 ← built static files served by nginx
│   └── .env                  ← VITE_API_BASE for build
└── chroma_db_v4/             ← ChromaDB vector store (auto-created)
```

---

## 8. Updating the Application

```bash
# 1. Pull latest code
cd /opt/isd
git pull

# 2. Rebuild frontend if UI changed
cd /opt/isd/frontend
npm run build

# 3. Install any new Python dependencies
cd /opt/isd/backend
/opt/miniconda3/envs/isd/bin/pip install -r requirements.txt

# 4. Restart backend
sudo systemctl restart isd-backend

# nginx serves dist/ directly — no restart needed for frontend-only changes
```

---

## 9. LLM Model Selection per Environment

| Environment | PDF_MODEL | Notes |
|---|---|---|
| **Development (laptop)** | `gemma3:12b` | Fast, fits in 12 GB VRAM |
| **Production (H100 80GB)** | `llama3.3:70b` | Best accuracy, full precision |
| **Production (fallback)** | `llama3.1:8b` | If 70B is too slow for a use case |
| **Embedding** | `mxbai-embed-large` | Same across all environments |

Change the model by editing `/opt/isd/backend/.env` and restarting:
```bash
sudo systemctl restart isd-backend
```

---

## 10. Health Checks & Monitoring

```bash
# Check backend is running
curl -s http://127.0.0.1:8001/docs | head -5

# Check Ollama GPU usage
nvidia-smi

# View backend logs (live)
sudo journalctl -u isd-backend -f

# View nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# Check MSSQL
sqlcmd -S localhost -U isd_user -P '<PASSWORD>' -d ISDIntelligenceV4 \
  -Q "SELECT COUNT(*) as users FROM users; SELECT COUNT(*) as cases FROM cases;"
```

---

## 11. Backup Strategy

```bash
# 1. MSSQL backup (run as cron daily)
sqlcmd -S localhost -U sa -P '<SA_PASSWORD>' -Q \
  "BACKUP DATABASE ISDIntelligenceV4 TO DISK='/opt/backups/isd_$(date +%Y%m%d).bak'"

# 2. ChromaDB backup (stop service first to avoid corruption)
sudo systemctl stop isd-backend
tar -czf /opt/backups/chroma_$(date +%Y%m%d).tar.gz /opt/isd/chroma_db_v4/
sudo systemctl start isd-backend

# Automate with cron
crontab -e
# Add:  0 2 * * * /opt/scripts/backup_isd.sh
```

---

## 12. Quick-Start Checklist

```
[ ] Ubuntu 22.04 LTS installed, updated
[ ] NVIDIA driver 550 + CUDA 12.4 installed, nvidia-smi works
[ ] Ollama installed, llama3.3:70b and mxbai-embed-large pulled
[ ] SQL Server 2022 installed, ISDIntelligenceV4 database created
[ ] ODBC Driver 17 installed and visible to Python
[ ] Miniconda isd environment, all pip packages installed
[ ] /opt/isd/backend/.env configured with production secrets
[ ] Frontend built: npm run build (dist/ created)
[ ] nginx configured, SSL cert in place, nginx -t passes
[ ] systemd isd-backend service enabled and running
[ ] Firewall: 443 open, 8001/11434/1433 blocked externally
[ ] Admin user registered and promoted in MSSQL
[ ] Test login at https://<SERVER_IP>
[ ] Test document upload and Q&A
[ ] Backup cron job scheduled
```

---

*Document prepared for ISD Document Intelligence V4 — March 2026*
