# Project: Cyber Fraud Data Entry

A multi-unit law enforcement data entry platform for tracking cyber fraud cases,
mule accounts, bank transactions, petitions, and daily status reports. FastAPI
backend, React 19 frontend, MySQL database. Role-based access for admin and
unit-level users.

See @Architecture.md for system design decisions and detailed schema reference.
See @SPEC.md for product specification and feature details.
See @PLAN.md for roadmap and implementation status.

## Deployment Context

- **Multi-user** application — 44 Cyber Command Police Stations across 36 districts
- **88 users** (2 per station: admin + unit_user), seeded via `seed.py`
- **Production server**: Ubuntu 24.04, Nginx + Gunicorn + Uvicorn on port 8000
- **Frontend**: built `dist/` served by Nginx on port 80/443 (HTTPS with self-signed cert)
- **Server paths**: code at `/opt/cyberfraud/`, systemd service `cyberfraud-backend`
- **MySQL password on server**: `CyberFraud@KSP2026`, database `cyber_fraud_dsr`
- **Network**: Internal government network (KSWAN), accessible by all 44 stations
- **Updates**: clone from SCRBChatBot monorepo, copy to `/opt/cyberfraud/`
- **This is NOT the ISD Document Intelligence project** — that is a separate single-user app for document analysis

---

## Repo structure

```
/backend                    # FastAPI server (Python, port 8000)
  main.py                   # App entry point — CORS, router mounting, lifespan
  config.py                 # Pydantic Settings (env prefix: CFDSR_)
  database.py               # SQLAlchemy async engine + session factory
  seed.py                   # Seed script for units, police stations, admin user
  .env                      # Environment variables
  requirements.txt          # Python dependencies
  /api                      # Route handlers
    deps.py                 # Auth dependencies (get_current_user, require_admin)
    routes_auth.py          # Login, /me
    routes_case.py          # Case CRUD + search
    routes_dashboard.py     # Admin KPI summary + unit comparison
    routes_dsr.py           # DSR upsert + history
    routes_mule_report.py   # Mule report CRUD + Excel upload/parse
  /auth
    security.py             # JWT creation/decode, bcrypt password hashing
  /models                   # SQLAlchemy ORM models (one file per table)
    user.py, unit.py, police_station.py, case.py, arrest.py,
    accomplice.py, accused_detail.py, petition.py, lien_account.py,
    unfreeze_detail.py, refund.py, mule_entry.py, mule_report.py,
    money_transfer.py, other_transaction.py, transaction_on_hold.py,
    other_less_than_500.py, aeps_transaction.py, atm_withdrawal.py,
    dsr_entry.py
  /schemas                  # Pydantic request/response models
    auth.py, case.py, dashboard.py, dsr.py, mule.py
/frontend                   # React 19 + TypeScript + Vite SPA (port 5173)
  /src
    App.tsx                 # React Router routes
    main.tsx                # Entry point
    index.css               # Tailwind CSS imports
    /components
      /auth                 # LoginForm.tsx, ProtectedRoute.tsx
      /dsr                  # DsrForm.tsx
      /mule                 # MuleForm.tsx
      /layout               # AppShell.tsx, Sidebar.tsx
    /pages                  # Page components (one per route)
    /lib
      /api                  # API client + typed fetch wrappers
        client.ts           # Base apiFetch with auth header injection
        auth.ts, cases.ts, dsr.ts, mule.ts, mule-reports.ts, dashboard.ts
      /stores
        auth-store.ts       # Zustand auth state (token + user)
      /utils
        format.ts           # Formatting helpers
    /types
      index.ts              # All TypeScript interfaces
  package.json
  vite.config.ts            # Proxy /api → localhost:8000
  tailwind.config.js
  tsconfig.json
```

---

## Essential commands

```bash
# ── Backend ──────────────────────────────────────────────────
cd backend
pip install -r requirements.txt

# Start dev server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Seed database (units, police stations, admin user)
python seed.py

# ── Frontend ─────────────────────────────────────────────────
cd frontend
npm install
npm run dev          # dev server on port 5173
npm run build        # typecheck + production build
npm run lint         # ESLint
npm run preview      # preview production build
```

**Prerequisites:**
- MySQL 8+ (database `cyber_fraud_dsr` is auto-created)
- Python 3.10+, Node.js 18+
- Run `seed.py` once to populate units, police stations, and admin user

---

## Stack

**Backend (backend/)**
- FastAPI 0.115.0 with async endpoints
- SQLAlchemy 2.0 with asyncmy async MySQL driver
- Pydantic v2 for request/response validation and settings
- JWT (HS256) via python-jose, bcrypt via passlib
- openpyxl for Excel file parsing (bank transaction uploads)
- python-multipart for file uploads

**Frontend (frontend/)**
- React 19 with functional components and hooks
- TypeScript (strict mode)
- Vite for build tooling and dev server
- Tailwind CSS for styling (no component library)
- Zustand for auth state management
- React Router 7 for routing
- Recharts for dashboard charts
- Lucide React for icons
- Sonner for toast notifications

**Infrastructure**
- MySQL 8+ (primary database)
- Nginx (reverse proxy + SSL + static files in production)
- Gunicorn + Uvicorn workers (ASGI in production)
- systemd for service management

---

## Code style

**Backend**
- SQLAlchemy ORM models — one file per table in `models/`
- Pydantic schemas — one file per domain in `schemas/`
- Route handlers — one file per domain in `api/`
- All endpoints are `async def` — use `await` with async SQLAlchemy sessions
- Use `selectinload()` for eager loading relationships — avoid N+1 queries
- All DB operations use `AsyncSession` from `database.py`

**Frontend**
- Page components in `pages/` — one per route
- Reusable components in `components/` — organized by domain
- API functions in `lib/api/` — typed wrappers around `apiFetch`
- Types in `types/index.ts` — all interfaces in one file
- Zustand store in `lib/stores/` — minimal state (auth only)

**Naming conventions**
- Backend files: snake_case (`routes_case.py`, `mule_report.py`)
- Frontend pages: PascalCase (`CaseEntryPage.tsx`, `DashboardPage.tsx`)
- Frontend components: PascalCase (`AppShell.tsx`, `ProtectedRoute.tsx`)
- API routes: kebab-case (`/api/v1/mule-reports`, `/api/v1/cases`)
- DB tables: snake_case plural (`cases`, `arrests`, `mule_reports`)
- Environment variables: CFDSR_ prefix + SCREAMING_SNAKE (`CFDSR_DB_HOST`)

---

## Architecture rules

**Two user roles — enforce at every route**
- `admin` — can see all units' data, access dashboard, manage users
- `unit_user` — can only see and edit their own unit's data
- Use `require_admin()` or `require_unit_user()` dependencies from `api/deps.py`

**Data isolation by unit**
- Every case, mule report, DSR entry, and mule entry is scoped to `unit_id`
- Unit users can only query/modify records where `unit_id` matches their own
- Admin users can query across all units

**Nested form data**
- Cases have nested children: arrests (with accomplices + accused details), petitions, lien accounts, unfreeze details, refunds
- Mule reports have nested transaction tables: money transfers, other transactions, transactions on hold, others <500, AEPS, ATM withdrawals
- All children use CASCADE delete — deleting parent removes all children

**Upsert pattern for daily reports**
- DSR entries and mule entries use upsert (INSERT or UPDATE) keyed on `(unit_id, report_date)`
- Only one entry per unit per date

**Excel upload for bank transactions**
- Uses openpyxl to parse multi-sheet Excel files
- Extracts acknowledgement_no from first data row
- Maps sheet names to transaction types
- Preview (parse-only) available before saving

---

## Database

**MySQL tables** (auto-created by SQLAlchemy `metadata.create_all`):
- `users` — authentication (username, hashed_password, role, unit_id, ps_id)
- `units` — organizational units (name, code)
- `police_stations` — district + station name
- `cases` — FIR/NCRP/Petition cases (fir_no, case_type, crime_type, facts, status)
- `arrests` — arrested persons per case (name, address, aadhar, pan)
- `accomplices` — accomplice details per arrest
- `accused_details` — accused photos, contact, occupation per arrest
- `petitions` — petition tracking per case (amount, nature, type)
- `lien_accounts` — frozen bank accounts per case (account_no, amount, layer)
- `unfreeze_details` — account unfreeze records per case
- `refunds` — victim refund records per case
- `mule_reports` — mule account investigation reports (ack_no, fir_no)
- `money_transfers` — bank transfer transactions per mule report
- `other_transactions` — other transaction types per mule report
- `transactions_on_hold` — held transactions per mule report
- `others_less_than_500` — small transactions per mule report
- `aeps_transactions` — AEPS withdrawal records per mule report
- `atm_withdrawals` — ATM withdrawal records per mule report
- `mule_entries` — daily mule intelligence summaries per unit
- `dsr_entries` — daily status reports per unit

**Key constraints:**
- `cases`: UNIQUE (unit_id, fir_no)
- `dsr_entries`: UNIQUE (unit_id, report_date)
- `mule_entries`: UNIQUE (unit_id, report_date)
- `mule_reports`: UNIQUE acknowledgement_no, UNIQUE fir_no
- All child tables: CASCADE delete on parent FK

---

## Environment variables

- Env file location: `backend/.env`
- Prefix: `CFDSR_` (Pydantic Settings)
- Frontend env: `frontend/.env` (VITE_API_BASE)
- NEVER commit `.env` files to git

| Variable | Purpose | Default |
|----------|---------|---------|
| `CFDSR_DB_HOST` | MySQL host | `localhost` |
| `CFDSR_DB_PORT` | MySQL port | `3306` |
| `CFDSR_DB_USER` | MySQL user | `root` |
| `CFDSR_DB_PASSWORD` | MySQL password | (empty) |
| `CFDSR_DB_NAME` | MySQL database | `cyber_fraud_dsr` |
| `CFDSR_JWT_SECRET` | JWT signing secret | (change in prod) |
| `CFDSR_JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `CFDSR_JWT_EXPIRE_MINUTES` | Token expiry | `480` (8 hours) |
| `CFDSR_CORS_ORIGINS` | Allowed CORS origins | `http://localhost:5173,http://localhost:5175` |
| `VITE_API_BASE` | Frontend API base URL | `http://localhost:8000` |

---

## Git workflow

- Commit messages: descriptive prefix (`CyberFraud: feature description`)
- Never commit `.env`, `__pycache__/`, `node_modules/`, `frontend/dist/`
- Never commit uploaded photos or Excel files

---

## Things Claude often gets wrong on this project

- Do NOT use raw SQL — this project uses SQLAlchemy ORM exclusively
- Do NOT use synchronous DB sessions — all database access is async (`AsyncSession`)
- Do NOT forget `unit_id` scoping — every query must filter by the user's unit (except admin)
- Do NOT forget CASCADE delete implications — deleting a case removes all arrests, petitions, lien accounts, etc.
- Do NOT create new models without adding them to `models/__init__.py`
- Do NOT create new routes without adding the router to `main.py`
- Do NOT add new env variables without using the `CFDSR_` prefix in `config.py`
- Do NOT use any state management library other than Zustand — keep state minimal
- Do NOT create component files outside the `components/` or `pages/` directory structure
- Do NOT add new API functions without corresponding TypeScript types in `types/index.ts`
- Do NOT use `useEffect` for form submission — use event handlers
- Do NOT forget to handle 401 responses — the API client auto-redirects to login
- When adding a new route, ALWAYS add the Pydantic schema in `schemas/`
- When adding a new table, ALWAYS add the SQLAlchemy model in `models/` and update `__init__.py`
- Do NOT push any code to GitHub unless it has been locally tested — this app is running in production
