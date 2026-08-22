# Startup — Cyber Fraud Data Entry

Multi-unit data entry platform for Karnataka State Police cyber fraud units.
45+ Cyber Crime Police Stations across 36 districts, ~90 users
(unit_user + admin per PS, plus super_admins at SCRB HQ).
**Active**, running in production.

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

**Step 0 — Local sanity first.** Backend AST-parse + `npm run build`
must pass. If you touched anything security-sensitive, run the
regression suite locally (see [Operations.md](./Operations.md)).

One command on the server:

```bash
cd /opt/scrb && git pull && sudo bash CyberFraudDataEntry/deploy/update.sh
```

`deploy/update.sh` handles everything — pip deps, migrations 001 →
026 (idempotent), frontend build, sync into runtime, backend restart,
nginx `/uploads/` proxy fixup, and a self-verify panel that aborts on
the first schema / route regression. See
[Operations.md § Deploying Updates](./Operations.md#deploying-updates)
for the full step-by-step breakdown.

### Post-deploy verification

The self-verify block already runs these; check the deploy output for
the ✓ marks. If a check aborts the deploy, that same command shows
exactly which one.

### Rollback

```bash
cd /opt/scrb
git log --oneline -10                    # find previous good SHA
git checkout <previous-sha>
sudo bash CyberFraudDataEntry/deploy/update.sh   # re-run — idempotent
```

Migrations don't roll back (additive-only post-VAPT); if a migration
introduced a regression, forward-fix with a new migration rather than
reverting.

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
