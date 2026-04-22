# Startup — Cyber Fraud Data Entry

**Ports** — backend `8000`, frontend `5175` (see port scheme below)

Production multi-unit app for Karnataka State Police cyber fraud units —
44 stations, 88 users. Deployed on Ubuntu VM with Nginx + Gunicorn.

## Local Development

### Prerequisites

- MySQL 8+ running locally
- Database `cyber_fraud_dsr` is auto-created on startup

### Backend (FastAPI on :8000)

```bash
cd c:/VSCProjects/SCRBChatBot/CyberFraudDataEntry/backend
uvicorn cyber_fraud:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend (Vite on :5175)

```bash
cd c:/VSCProjects/SCRBChatBot/CyberFraudDataEntry/frontend
npm run dev
```

Open http://localhost:5175 (proxies `/api/*` and `/health` to port 8000)

## First-time setup

```bash
# Python deps
cd c:/VSCProjects/SCRBChatBot/CyberFraudDataEntry/backend
pip install -r requirements.txt

# Seed database (units, police stations, admin user) — run once
python seed.py

# Frontend deps
cd ../frontend
npm install
```

`backend/.env` must include:
```
CFDSR_DB_HOST=localhost
CFDSR_DB_PORT=3306
CFDSR_DB_USER=root
CFDSR_DB_PASSWORD=<your-password>
CFDSR_DB_NAME=cyber_fraud_dsr
CFDSR_JWT_SECRET=<change-in-prod>
CFDSR_CORS_ORIGINS=http://localhost:5175
```

## Production deployment (Ubuntu VM)

- Code at `/opt/cyberfraud/`
- MySQL database: `cyber_fraud_dsr` (password: `CyberFraud@KSP2026`)
- systemd service: `cyberfraud-backend`
- Nginx reverse proxy + Let's Encrypt SSL
- Gunicorn + Uvicorn workers on port 8000

```bash
# Deploy updates (on server)
cd /opt/cyberfraud
git pull

# Sync systemd service file from repo (do this whenever deploy/cyberfraud-backend.service changes)
sudo cp deploy/cyberfraud-backend.service /etc/systemd/system/cyberfraud-backend.service
sudo systemctl daemon-reload

# Rebuild frontend
cd frontend && npm run build

# Restart backend + reload nginx
sudo systemctl restart cyberfraud-backend
sudo systemctl reload nginx
```

The systemd service file now lives in `deploy/cyberfraud-backend.service` in the repo, so `git pull` brings down both code and service-config changes together.

## Port scheme across all local projects

| Project | Backend | Frontend |
|---|---|---|
| ChargePoint V1 | 8007 | 5173 |
| ChargePoint V2 | 8008 | 5174 |
| **CyberFraudDataEntry** | **8000** | **5175** |
| ISD Document Intelligence V6 | 8003 | 5176 |
| RAG Playground | 8006 | 5177 |
