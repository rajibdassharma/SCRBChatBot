# Startup — Cyber Fraud Data Entry

Multi-unit data entry platform for Karnataka State Police cyber fraud units.
44 stations, 88 users. **Active**, running in production.

**Ports** — backend `8000`, frontend `5175` (see port scheme below)

See `MyProjectDashboard/STARTUP_TEMPLATE.md` for the section structure this
file follows.

## Prerequisites

- Python 3.10+, Node.js 18+
- MySQL 8+ running locally (database `cyber_fraud_dsr` auto-created on first
  boot)
- On production: Ubuntu 24.04, Nginx, systemd

## First-time setup

```bash
# Backend
cd c:/VSCProjects/SCRBChatBot/CyberFraudDataEntry/backend
pip install -r requirements.txt
python seed.py              # one-time: units, police stations, admin user

# Frontend
cd ../frontend
npm install
```

Create `backend/.env`:

```
CFDSR_DB_HOST=localhost
CFDSR_DB_PORT=3306
CFDSR_DB_USER=root
CFDSR_DB_PASSWORD=<set-this>
CFDSR_DB_NAME=cyber_fraud_dsr
CFDSR_JWT_SECRET=<random-32-chars-in-prod>
CFDSR_JWT_EXPIRE_MINUTES=480
CFDSR_CORS_ORIGINS=http://localhost:5175
```

## Environment variables

All prefixed `CFDSR_` (Pydantic Settings). Frontend uses `VITE_API_BASE`
(only needed if not using Vite proxy — default setup proxies `/api` to
`localhost:8000` automatically).

| Variable | Purpose | Default |
|---|---|---|
| `CFDSR_DB_HOST` | MySQL host | `localhost` |
| `CFDSR_DB_PORT` | MySQL port | `3306` |
| `CFDSR_DB_USER` | MySQL user | `root` |
| `CFDSR_DB_PASSWORD` | MySQL password | *(required)* |
| `CFDSR_DB_NAME` | Database name | `cyber_fraud_dsr` |
| `CFDSR_JWT_SECRET` | JWT signing secret | *(change in prod)* |
| `CFDSR_JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `CFDSR_JWT_EXPIRE_MINUTES` | Token expiry | `480` (8h) |
| `CFDSR_CORS_ORIGINS` | Allowed origins | `http://localhost:5175` |
| `VITE_API_BASE` (frontend) | API base URL | `http://localhost:8000` |

Production server values: MySQL password `CyberFraud@KSP2026`, stored in
`/opt/cyberfraud/backend/.env`.

## Local development

```bash
# Backend (port 8000)
cd c:/VSCProjects/SCRBChatBot/CyberFraudDataEntry/backend
uvicorn cyber_fraud:app --host 0.0.0.0 --port 8000 --reload

# Frontend (port 5175)
cd c:/VSCProjects/SCRBChatBot/CyberFraudDataEntry/frontend
npm run dev
```

Open http://localhost:5175 (Vite proxies `/api/*` and `/health` to 8000)

## Verification

- `curl http://localhost:8000/health` → `{"status": "ok"}`
- Browser http://localhost:5175 → login page loads
- Log in with credentials from `seed_credentials_<timestamp>.csv` (produced by `python seed.py`)
- First login forces password change — confirm the change-password page loads
- Admin dashboard should show unit count + KPI totals after second login

## Security regression tests

Pytest suite at `backend/tests/test_security.py` — 14 tests mapped 1:1
to the Innspark VAPT findings. **Run before every production deploy.**

### Pre-flight

Backend must be running on `:8000` AND a fresh seed must exist:
```bash
cd backend
pip install -r tests/requirements-test.txt
python seed.py                                  # if not already seeded
```

### Run the suite

```bash
cd backend
pytest tests/ -v
```

Expected: **14 passed**. See [tests/README.md](backend/tests/README.md)
for per-test descriptions and known side-effects (e.g. test_7_4 locks
one user for 15 minutes).

### Via Claude (subagent)

Project ships with `CyberFraudDataEntry/.claude/agents/security-tester.md`
— a scoped subagent that runs the pytest suite and reports pass/fail per
VAPT finding. Trigger it by asking Claude:

> *"Run the security-tester agent"*

Claude will verify pre-flight (backend up, seed file present), run
pytest, and produce a compact VAPT-mapped summary. Fastest way to
sanity-check before deploy.

## Production deployment (Ubuntu VM)

**Target:** `/opt/cyberfraud/`, systemd service `cyberfraud-backend`,
Nginx reverse proxy on 443 with Let's Encrypt SSL, internal KSWAN network.

### Update procedure

**Step 0 — Run the security regression suite locally first** (see the
"Security regression tests" section above). Only proceed if 14/14 pass.
Deploy is blocked on any regression in a VAPT finding.

```bash
# On server
cd /opt/cyberfraud
git pull

# Sync systemd service + nginx configs whenever deploy/ files change
sudo cp deploy/cyberfraud-backend.service /etc/systemd/system/cyberfraud-backend.service
sudo cp deploy/nginx.conf /etc/nginx/sites-available/cyberfraud
sudo systemctl daemon-reload

# Rebuild frontend
cd frontend && npm run build
cd ..

# Restart backend + reload nginx
sudo systemctl restart cyberfraud-backend
sudo nginx -t && sudo systemctl reload nginx
```

The systemd service file lives in `deploy/cyberfraud-backend.service` in
the repo, so `git pull` brings down both code and service config together.
The `cp` + `daemon-reload` step is only required when the service file
itself changes.

### Post-deploy verification

```bash
sudo systemctl status cyberfraud-backend       # should be active (running)
curl -k https://<server-domain>/health          # through nginx
sudo journalctl -u cyberfraud-backend -n 50     # last 50 log lines
```

### Rollback

```bash
cd /opt/cyberfraud
git log --oneline -10                    # find previous good SHA
git checkout <previous-sha>
sudo cp deploy/cyberfraud-backend.service /etc/systemd/system/cyberfraud-backend.service
sudo systemctl daemon-reload
sudo systemctl restart cyberfraud-backend
```

## Common troubleshooting

| Problem | Fix |
|---|---|
| 401 Invalid credentials on valid password | Rate limiter triggered after N failed attempts — restart backend to clear the in-memory counter |
| `bcrypt` / `passlib` errors on Python 3.14 | `pip install bcrypt==4.0.1` (bcrypt 5.x breaks passlib) |
| CORS error in browser console | Add origin to `CFDSR_CORS_ORIGINS` |
| Excel upload parses nothing | Confirm sheet names match the six expected types (Money Transfers, AEPS, ATM, etc.) |

## Cross-project port scheme

| Project | Backend | Frontend |
|---|---|---|
| ChargePoint V1 | 8007 | 5173 |
| ChargePoint V2 | 8008 | 5174 |
| **CyberFraudDataEntry** | **8000** | **5175** |
| ISD Document Intelligence V6 | 8003 | 5176 |
| RAG Playground | 8006 | 5177 |
