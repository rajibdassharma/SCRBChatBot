# Project: Cyber Fraud Data Entry

A multi-unit law enforcement data entry platform for Karnataka State Police (SCRB / CID Cyber Crime). 44 Cyber Crime Police Stations across 36 districts, ~90 operators. FastAPI + async SQLAlchemy backend, React 19 SPA frontend, MySQL 8+.

**In production.** All schema changes go via numbered migrations. Local test before every push. Deploy is a single `./update.sh` on the server.

See @docs/SRS.md for what the product does — 5 modules, 3 roles, functional requirements.
See @docs/Architecture.md for how it's built — schema, routes, deploy flow.
See @docs/Operations.md, @docs/ProductionDeployment.md, @docs/database.md for runtime + deployment.

---

## Deployment context

- **Multi-user** — ~90 operators across 44 PSes on the KSWAN internal government network
- **Server**: Ubuntu 24.04 VM at SCRB HQ, self-signed HTTPS
- **Backend**: `/opt/cyberfraud/`, systemd unit `cyberfraud-backend`, port 8000
- **Frontend**: built `dist/` served by Nginx on 443
- **DB**: MySQL 8+, `cyber_fraud_dsr` on localhost:3306
- **Deploy**: `./deploy/update.sh` on the server — git pull, pip, migrations, npm build, rsync, restart, self-verify
- **This is NOT the ISD Document Intelligence project** — that's a separate app under `YAIA-main/`

---

## The five modules

Every URL, every route, every dashboard belongs to one of these:

| Module | Sidebar entries | URL prefixes |
|---|---|---|
| **Cases & Petitions** | New Case, Update Case, New Petition, Update Petition, Reports, Cases & Petitions Dashboard | `/cases/*`, `/petitions/*`, `/dashboard`, `/reports` |
| **NCRP Data** | New Report, Update Report, Upload Bulk Data | `/mule/*` |
| **All Accounts** | New Account, Update Account, Account Details Dashboard | `/all-accounts/*`, `/accounts-dashboard` |
| **DSR** | New FIR, Investigation, Daily Work Done Report, Portals, Portals DSR Report, FIR Dashboard, Portals DSR Dashboard, Daily Work Done Dashboard | `/dsr/*`, `/daily-work/*`, `/portals-dsr/*` |
| **Admin** | User Management, Ask the Data | `/users`, `/chat` |

Module definitions live in `frontend/src/lib/utils/modules.ts` — one edit adds a sidebar entry. Adding a new **module** = one entry in `MODULES` array. Never sprinkle sidebar links across multiple files.

---

## Three user roles

Enforce at every route via `api/deps.py`:

- **`super_admin`** — SCRB HQ Senior Officer. Cross-PS read + write everywhere. Only role that can use the chat.
- **`admin`** — station-level admin. Full read + write on own `(unit_id, ps_id)`. Sees own PS's dashboards + reports. Manages users at own PS.
- **`unit_user`** — operator. Read + write only records they personally submitted, within own `(unit_id, ps_id)`. No dashboards.

Old CLAUDE / SPEC docs mention only admin + unit_user — that's out of date. Super_admin was added 2026-07-23.

---

## Repo structure

```
/backend                        # FastAPI (Python 3.10+)
  cyber_fraud.py                # App entry — CORS, router mounting, lifespan
  config.py                     # Pydantic Settings, env prefix CFDSR_
  database.py                   # Async engine + session factory
  seed.py                       # Seed units, PSes, admin user
  /api                          # 13 route modules (see Architecture.md)
    deps.py                     # get_current_user, require_admin, check_record_access
    routes_auth.py routes_users.py routes_case.py
    routes_mule_report.py routes_all_accounts.py
    routes_dsr.py routes_mule.py routes_daily_work.py
    routes_portals_dsr.py routes_nil.py routes_dashboard.py
    routes_reports.py routes_chat.py
  /auth/security.py             # JWT + bcrypt
  /models                       # 30 models in Base.metadata. NOT one per
                                # table: the 6 analysis models are not
                                # imported by models/__init__.py, and
                                # mule_account_link has no model at all
  /schemas                      # Pydantic per-domain
  /reports                      # PDF (reportlab) + Excel (openpyxl) renderers
    base.py                     # Shared chrome for PDFs
  /chat/schema_description.py   # LLM schema hint
  /utils/{validators,sanitize}.py
  gunicorn.conf.py              # Prod process config — the systemd unit
                                # will not start without it
  requirements-dev.txt          # app + analysis + test deps in one install
  /migrations/001..026_*.py     # Numbered, idempotent
  /analysis/                    # Upload analysis — BATCH ONLY.
                                # The web app never imports this.
                                # daily.py is the nightly chain.

/frontend                       # React 19 + TS strict + Vite
  /src
    App.tsx                     # React Router 7 routes
    /components/{auth,layout}   # LoginForm, ProtectedRoute, AppShell, Sidebar
    /pages/*.tsx                # 32 pages, one per route
    /lib
      /api/*.ts                 # Typed apiFetch wrappers, one per domain
      /stores/auth-store.ts     # Zustand — auth only
      /utils/*.ts               # modules, format, fir-no, indian-states,
                                # karnataka-districts, crime-types, portals-tabs
    /types/index.ts             # ALL TypeScript interfaces (single file)
  vite.config.ts                # /api → localhost:8000
  package.json

/deploy
  update.sh                     # The one-and-only prod deploy script
  backup-db.sh backup-uploads.sh

/proddata                       # Historical DB dumps
```

---

## Essential commands

```bash
# ── Backend (dev) ──
cd backend
pip install -r requirements.txt
uvicorn cyber_fraud:app --host 0.0.0.0 --port 8000 --reload
python seed.py                                   # first-time only
python -m migrations.018_rename_cen_to_cyber_in_ps_names   # any single migration

# ── Frontend (dev) ──
cd frontend
npm install
npm run dev                                      # http://localhost:5175
npm run build                                    # tsc -b && vite build (prod)
npm run lint

# ── Deploy (server only) ──
cd /opt/scrb
sudo ./CyberFraudDataEntry/deploy/update.sh
```

Prereqs: MySQL 8+, Python 3.10+, Node 18+.

---

## Stack

**Backend** — FastAPI 0.115, SQLAlchemy 2.0 async + asyncmy, Pydantic v2, python-jose (JWT HS256), passlib+bcrypt, openpyxl, reportlab, python-multipart.

**Frontend** — React 19, TypeScript strict, Vite, Tailwind CSS (no component lib), Zustand (auth only), React Router 7, Recharts, Lucide, Sonner (toasts).

**Infra** — MySQL 8+, Nginx (TLS + reverse proxy + static), Gunicorn+Uvicorn, systemd.

---

## Code style

**Backend**
- One model file per DB table under `models/` — **36 of the 37 tables.**
  The exception is `mule_account_link`, which is read by raw `text()` in
  `routes_dashboard.py` and has no ORM model. Adding one is fine; just
  don't assume it is already there
- One Pydantic domain file per feature under `schemas/`
- One route module per feature under `api/`
- All endpoints `async def` — use `await` with `AsyncSession`
- Use `selectinload()` for parent-with-children reads (no N+1)
- All free-text write fields sanitised with `strip_html` via a Pydantic `field_validator`

**Frontend**
- Page components in `pages/` (one per route)
- API functions in `lib/api/` — typed wrappers around `apiFetch`
- All server-facing types in `src/types/index.ts` (single file)
- Zustand state stays minimal — auth only
- No new state-management libs, no new form libs — plain `useState` + arrays for nested forms

**Naming**
- Backend files: snake_case (`routes_daily_work.py`, `all_account.py`)
- Frontend pages: PascalCase (`DailyWorkReportPage.tsx`)
- URLs: kebab-case (`/api/v1/daily-work-daily.pdf`)
- DB tables: snake_case plural (`daily_work_entries`, `portals_dsr_entries`)
- Env vars: `CFDSR_` prefix + SCREAMING_SNAKE

---

## Architecture rules

**Three roles, enforced at every route.** `super_admin`, `admin`, `unit_user`. Use `require_admin()` (accepts super_admin too) or `require_unit_user()` from `api/deps.py`. Per-record access uses `check_record_access()` which bypasses super_admin.

**Data isolation by `(unit_id, ps_id)`.** Every operator-created row carries both. Every query filters by them — except super_admin routes that pass an all-PS or single-PS scope explicitly.

**Cases have deep nested children.** Arrests → (accomplices, accused_details), plus petitions, lien_accounts, unfreeze_details, refunds, victim (1:1), victim_accounts, accused_accounts. Update route deletes-and-re-inserts all children — PUT body MUST include the complete state. Two exceptions: `victim_accounts` and `accused_accounts` are `Optional[List]=None` — omit the key to leave rows untouched (passthrough for Update Case).

**Upserts for daily reports.** `dsr_entries` and `mule_entries` upsert on `(unit_id, ps_id, report_date)`. `daily_work_entries` upsert on `(unit_id, ps_id, fir_no, report_date)`. `portals_dsr_entries` allows multiple rows per (unit, ps, date) — dashboards SUM.

**Excel upload (NCRP module).** openpyxl parses six sheet types into their transaction tables. Preview endpoint is parse-only; save uses the same parser.

**Every schema change is a migration.** Numbered `NNN_description.py` under `backend/migrations/`, idempotent (INFORMATION_SCHEMA guards on every operation). Add the new migration to `deploy/update.sh`'s migration list AND add a self-verify check. No `reset_db.py` — that was retired after VAPT.

---

## Database

37 tables. Full list in [Architecture.md](./Architecture.md#4-database-schema). Highlights:

- `users`, `units`, `police_stations`, `revoked_tokens` — identity
- `cases` + 10 child tables — Cases & Petitions
- `mule_reports` + 6 txn tables — NCRP Data
- `all_accounts` + `all_account_mule_herders` — All Accounts
- `dsr_entries`, `mule_entries`, `daily_work_entries`, `portals_dsr_entries`, `daily_nil_declarations` — DSR
- `chat_messages` — Admin (audit trail)
- `statement_transactions`, `upload_ledger`, `account_statement_summary`,
  `id_photo_hashes`, `mule_account_link`, `crypto_txn`, `ifsc_branch` —
  upload analysis (migrations 019–026). **All derived and rebuildable**

Key UNIQUEs: `(unit_id, ps_id, fir_no)` on cases, `acknowledgement_no`+`fir_no` on mule_reports, `(unit_id, ps_id, report_date)` on dsr, `(unit_id, ps_id, fir_no, report_date)` on daily_work, `(unit_id, ps_id, serial_no)` on all_accounts.

All child tables CASCADE with parent. All `cases.id` FKs must match `VARCHAR(36) utf8mb4_unicode_ci` exactly (MySQL 3780 lurks — see [database.md](./database.md)).

---

## Upload analysis (`backend/analysis/`)

A batch subsystem, not part of the web app. **Nothing under `api/` imports
it, and no endpoint reads `statement_transactions`** — dashboards
read the ~150 MB of derived summary tables, which is what keeps page loads
independent of a 27 GB fact table.

AN EXCEPTION WAS TRIED ON 2026-09-03 AND REVERTED THE SAME DAY. The FIR
trace read the fact table directly to list named recipients with no
account number. It was justified on one measurement -- 16 accounts,
1,530 rows, 61 ms -- and that FIR was not representative. FIR 0001/2026
at Bagalkot has 29 accounts and 66,055 rows and took 15.6 SECONDS on a
32 GB laptop; on the 2-vCPU server it was a gateway timeout.

The aggregation was not the cost. The same filter with no GROUP BY also
took 15.6 s. An index on account_id gives row pointers and each fetch is
a random read into a 27.6 GB table -- 66,000 of them. No query tuning
removes that.

So the rule holds without exception, and the lesson is about the shape
of the benchmark rather than the rule: a per-FIR lookup is not bounded
just because one FIR was small. Anything needing this data needs a
summary table filled by the nightly job.

Runs on the SERVER nightly since 2026-08-17: `cyberfraud-nightly.timer`
at 23:00 IST → `analysis.daily --skip-relink` → `backup-all.sh`. The
laptop no longer analyses anything; it restores what the server produced.

Things that have bitten, and will again:

- **Never edit `analysis/*` while a run is in flight.** Windows spawns
  re-import the module per worker; on Linux `daily.py` launches each step
  as a subprocess. Either way a mid-run edit can take the job down
- **The ledger and the fact table must stay on the same machine.**
  `upload_ledger` records what has been parsed; shipping it without
  `statement_transactions` produces a server that skips every file it
  believes is done, and summaries describing rows that are not there
- **`--recent` only ADDS rows.** After changing a detector pattern, run
  the full rebuild or withdrawn matches stay on screen
- **Tuning constants were calibrated on a 32 GB laptop.** `RESERVE_GB`,
  `RESERVE_CORES`, `IDLE_TIMEOUT_S` all have env overrides set in
  `deploy/cyberfraud-nightly.service`, and every one of them was wrong
  for the 2-vCPU server until measured there
- **Only chain-verified rows may be summed.** `chain_ok` is 1 passed /
  0 rejected / −1 untested. Collapsing untested into passed is what let
  ₹6.68 quadrillion onto a dashboard

## Environment variables

Backend env: `backend/.env`. Prefix `CFDSR_`. NEVER commit `.env`.

| Variable | Purpose | Default |
|---|---|---|
| `CFDSR_DB_HOST` | MySQL host | `localhost` |
| `CFDSR_DB_PORT` | MySQL port | `3306` |
| `CFDSR_DB_USER` | MySQL user | `root` |
| `CFDSR_DB_PASSWORD` | MySQL password | (empty) |
| `CFDSR_DB_NAME` | MySQL database | `cyber_fraud_dsr` |
| `CFDSR_JWT_SECRET` | JWT signing secret — backend refuses to start if missing / default / < 32 chars | **REQUIRED** (`openssl rand -hex 32`) |
| `CFDSR_JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `CFDSR_JWT_EXPIRE_MINUTES` | Token expiry | `480` (8h) |
| `CFDSR_CORS_ORIGINS` | Allowed CORS origins | `http://localhost:5173,http://localhost:5175` |
| `CFDSR_CHAT_ENABLED` | Feature flag for the Ask-the-Data chat | `false` |
| `CFDSR_LLM_API_KEY` | Required only when chat is enabled | (empty) |
| `VITE_API_BASE` | Frontend API base URL | (empty in prod — same origin) |

---

## Git workflow

- Commit prefix: `CyberFraud: short description`
- Never commit `.env`, `__pycache__/`, `node_modules/`, `frontend/dist/`, `backend/uploads/*`, `proddata/*.sql` (large), any Passwords*.xlsx / .csv
- Standing rule: **test locally before pushing** — this app is in production. `npm run build` is part of the deploy self-verify but a broken TS strict on push breaks the deploy for everyone

---

## Things Claude often gets wrong on this project

- **Do NOT use raw SQL** — SQLAlchemy ORM only. Small `func.count`/`func.sum` in aggregators is fine; hand-written SQL is not
- **Do NOT use synchronous DB sessions** — all DB access is `async`
- **Do NOT forget `(unit_id, ps_id)` scoping** — every query except super_admin cross-PS reads must filter by both
- **Do NOT forget CASCADE implications** — deleting a case removes arrests, accomplices, accused_details, petitions, liens, unfreezes, refunds, victim, victim_accounts, accused_accounts
- **Do NOT create new models without adding to `models/__init__.py`**
- **Do NOT create new routes without mounting in `cyber_fraud.py`**
- **Do NOT add env vars without the `CFDSR_` prefix AND registering in `config.py`**
- **Do NOT introduce new state-management libs** — Zustand handles auth; everything else is `useState`
- **Do NOT introduce new form libs** — plain `useState` + array helpers, even for the deeply-nested Case form
- **Do NOT put new pages outside `pages/`** or new components outside `components/`
- **Do NOT add API functions without corresponding types in `src/types/index.ts`**
- **Do NOT use `useEffect` for form submission** — event handlers only
- **Do NOT skip the 401 handler** — the API client auto-redirects to `/login` on 401
- **When adding a new schema change → add a numbered migration, then add it to `deploy/update.sh`** (migration list + self-verify block) OR the deploy will silently skip it
- **When adding a new table, also add the model to `models/__init__.py` `__all__`**
- **When adding a new user-facing route, also add a sidebar entry in `modules.ts`** — otherwise it's orphaned
- **When editing a case update flow, remember Optional[List]=None means passthrough** — `victim_accounts` and `accused_accounts` are only editable on DSR → New FIR; Update Case must pass them through unchanged
- **Every free-text field must be sanitised** — add it to the `_sanitize_text` field_validator on the schema
- **Every amount field must go through `_validate_amount`** — enforces ≥ 0 and ≤ ₹100 crore
- **FIR No must validate `NNNN/YYYY`** — use the shared `validate_fir_no` (client) / `_validate_fir_no` (server) helpers; don't hand-roll a regex
- **Do NOT push to GitHub without local test** — app is in production; broken push blocks every other operator's deploy

---

## Deploy checklist

Before pushing anything that changes the schema:
- [ ] New migration `NNN_<description>.py` added under `backend/migrations/`
- [ ] Migration is idempotent (INFORMATION_SCHEMA guards)
- [ ] Migration line added to `deploy/update.sh` step 3 (in order)
- [ ] Self-verify block added to `deploy/update.sh` step 8 asserting the change landed
- [ ] Local `python -m migrations.NNN_<description>` runs clean
- [ ] Backend AST parses (`python -c "import ast; ast.parse(open('backend/models/...').read())"`)
- [ ] Frontend `npm run build` passes TS strict
- [ ] Local integration test (start backend + frontend, exercise the new flow in a browser)
