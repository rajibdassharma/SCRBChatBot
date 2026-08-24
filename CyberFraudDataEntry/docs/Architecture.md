# Architecture — Cyber Fraud Data Entry

Technical reference for the system. See [SRS.md](./SRS.md) for what the product does; this file explains **how** it's built.

---

## 1. System Overview

```
                            ┌───────────────────────────┐
                            │   React 19 SPA (Vite)     │
                            │   TypeScript strict       │
                            │   Tailwind + Zustand      │
                            │   Recharts, Sonner        │
                            └───────────┬───────────────┘
                                        │ /api/* proxy
                            ┌───────────▼───────────────┐
                            │   Nginx (prod)            │
                            │   TLS + static dist/      │
                            │   client_max_body_size 25M│
                            └───────────┬───────────────┘
                                        │
                            ┌───────────▼───────────────┐
                            │   FastAPI (port 8000)     │
                            │   Gunicorn + Uvicorn      │
                            │   async SQLAlchemy 2.0    │
                            └──┬─────────────────┬──────┘
                               │                 │
                     ┌─────────▼─────────┐   ┌───▼──────────────┐
                     │   MySQL 8+        │   │  File storage    │
                     │   cyber_fraud_dsr │   │  backend/uploads │
                     │   utf8mb4         │   │  (photos, xlsx)  │
                     └───────────────────┘   └──────────────────┘
```

**Request flow (typical read):**
1. Operator interacts with the React SPA.
2. Frontend calls `/api/v1/*`. Vite proxies to `localhost:8000` in dev; nginx reverse-proxies in prod.
3. FastAPI dependency layer decodes JWT → `CurrentUser` → applies per-record `(unit_id, ps_id)` scoping (or bypasses for super_admin on read routes).
4. Async SQLAlchemy runs the query with `selectinload(...)` for eager children.
5. Pydantic serialises the response. Files (PDF / XLSX) stream back through `StreamingResponse`.

---

## 2. Authentication & Authorization

### JWT

- Algorithm: HS256
- Expiry: `CFDSR_JWT_EXPIRE_MINUTES` (default 480 = 8 h)
- Secret: `CFDSR_JWT_SECRET`. Backend refuses to start if missing, still-default, or < 32 chars — enforced in `config.py`
- Claims: `sub` (user_id), `role`, `unit_id`, `ps_id`, `must_change_password`
- Revocation: `revoked_tokens` table checked on every request; logout inserts the token id
- Token expiry now enforced (`verify_exp=True`) — VAPT v1.0.1 fix

### Roles

| Role | Data scope | Dashboards | User mgmt | Chat |
|---|---|---|---|---|
| `super_admin` | Every PS across the state | Yes (all PSes) | Yes (any PS) | Yes (only role that can) |
| `admin` | Own `(unit_id, ps_id)` only | Yes (own PS) | Yes (own PS) | No |
| `unit_user` | Own submissions within own `(unit_id, ps_id)` | No | No | No |

### Dependencies (`api/deps.py`)

- `get_current_user()` — parses + verifies JWT, returns `CurrentUser`
- `require_admin()` — accepts `admin` or `super_admin`
- `require_unit_user()` — restricts to `unit_user`
- `check_record_access(record, user)` — per-record scope check; bypasses for super_admin (2026-07-23)
- `require_password_changed()` — blocks all routes for users flagged `must_change_password`

Every mutation route calls these dependencies before touching the DB. VAPT 7.7 + 7.8 are enforced at this layer, not at application logic.

---

## 3. Repository Structure

```
CyberFraudDataEntry/
├── backend/                    # FastAPI server (Python 3.10+)
│   ├── cyber_fraud.py          # App entry — CORS, router mounting, lifespan
│   ├── config.py               # Pydantic Settings, env prefix CFDSR_
│   ├── database.py             # Async engine + session factory
│   ├── seed.py                 # Seed units + PSes + admin user
│   ├── gunicorn.conf.py        # Prod process config. LOAD-BEARING: the
│   │                           # systemd unit will not start without it
│   ├── requirements.txt        # the web app
│   ├── requirements-analysis.txt   # the parser (pins pillow<12)
│   ├── requirements-dev.txt    # composes all three, for dev/build boxes
│   ├── .env                    # NEVER commit. Keys are CFDSR_-prefixed
│   ├── api/                    # Route handlers (13 files)
│   │   ├── deps.py             # Auth + scoping dependencies
│   │   ├── routes_auth.py      # Login, /me, change-password
│   │   ├── routes_users.py     # User CRUD (admin+)
│   │   ├── routes_case.py      # Case CRUD + search
│   │   ├── routes_mule_report.py  # Mule report CRUD + Excel upload/parse
│   │   ├── routes_all_accounts.py # All accounts CRUD
│   │   ├── routes_dsr.py       # DSR upsert + history
│   │   ├── routes_mule.py      # Mule intel entry upsert + history
│   │   ├── routes_daily_work.py   # Daily Work Done CRUD + dashboard
│   │   ├── routes_portals_dsr.py  # Portals DSR CRUD + dashboard
│   │   ├── routes_nil.py       # NIL declarations
│   │   ├── routes_dashboard.py # All admin dashboards + aggregators
│   │   ├── routes_reports.py   # PDF + Excel + JSON preview endpoints
│   │   └── routes_chat.py      # Ask-the-Data chat (super_admin only)
│   ├── auth/security.py        # JWT create/decode, bcrypt hashing
│   ├── models/                 # SQLAlchemy ORM. 30 tables in
│   │                           # Base.metadata; the 6 analysis models are
│   │                           # deliberately NOT imported by __init__.py,
│   │                           # and mule_account_link has no model at all
│   ├── schemas/                # Pydantic (one file per domain)
│   ├── reports/                # PDF + Excel renderers
│   │   ├── base.py             # Shared chrome (title, page header, tables)
│   │   ├── dsr_aggregator.py
│   │   ├── case_pdf.py
│   │   ├── dsr_pdf.py
│   │   ├── mule_pdf.py
│   │   ├── submission_status_pdf.py
│   │   ├── fir_ps_performance_{pdf,xlsx}.py
│   │   ├── accounts_ps_comparison_{pdf,xlsx}.py
│   │   ├── portals_dsr_daily_{pdf,xlsx}.py    # 2026-07-24
│   │   └── daily_work_daily_{pdf,xlsx}.py     # 2026-07-24
│   ├── chat/schema_description.py  # LLM schema-hint prompt
│   ├── utils/
│   │   ├── validators.py       # amount cap, FIR No format
│   │   └── sanitize.py         # strip_html for all free text
│   ├── migrations/             # 001–026, idempotent, hand-rolled
│   └── analysis/               # Upload analysis — BATCH ONLY, never
│       │                       # imported by the web app
│       ├── daily.py            # The nightly chain: migrations → parse →
│       │                       # photos → links → crypto → verify
│       ├── runtime.py          # Memory/CPU governor — workers are
│       │                       # budgeted from FREE RAM, not core count
│       ├── parse_statements.py # PDF/XLSX → statement_transactions
│       ├── hash_id_photos.py   # SHA-256 + perceptual hash, banded
│       ├── build_links.py      # mule → mule transfer graph
│       ├── build_crypto.py     # narration → crypto_txn
│       ├── summary.py          # Rebuild / verify the money cache
│       ├── relink.py           # Repair account links after a restore
│       ├── progress.py         # Read-only progress probe
│       ├── load_ifsc.py        # Load the IFSC directory
│       └── parsers/            # Per-format readers + crypto detector
├── frontend/                   # React 19 SPA (Vite + TypeScript strict)
│   ├── src/
│   │   ├── App.tsx             # React Router routes
│   │   ├── main.tsx
│   │   ├── index.css           # Tailwind + KSP palette vars
│   │   ├── assets/ksp_logo.png
│   │   ├── components/
│   │   │   ├── auth/           # LoginForm, ProtectedRoute, ChangePassword
│   │   │   └── layout/         # AppShell, Sidebar, HomeTiles
│   │   ├── pages/              # One per route (32 files)
│   │   ├── lib/
│   │   │   ├── api/            # Typed fetch wrappers (15 files)
│   │   │   ├── stores/         # Zustand — auth only
│   │   │   └── utils/          # format, modules, indian-states,
│   │   │                       # karnataka-districts, fir-no,
│   │   │                       # portals-tabs, crime-types
│   │   └── types/index.ts      # ALL TypeScript interfaces
│   ├── vite.config.ts          # /api → localhost:8000 proxy
│   └── package.json
├── deploy/                     # Deploy scripts
│   ├── update.sh               # git pull → pip → migrations → build → sync → restart → self-verify
│   ├── backup-db.sh            # nightly mysqldump, keep newest
│   └── backup-uploads.sh       # nightly tarball, keep newest
├── proddata/                   # DB backups (historical snapshots)
├── CLAUDE.md                   # Working notes for Claude (auto-loaded from root)
└── docs/                       # Everything else (human docs)
    ├── SRS.md                      # Product bible
    ├── Architecture.md             # This file
    ├── Operations.md               # Runbook
    ├── ProductionDeployment.md     # Full server bring-up guide
    ├── SecurityAudit.md            # VAPT v1.0.1 tracking
    ├── database.md                 # Migration + charset conventions
    ├── OfflineGitSetup.md          # Air-gapped git workflow
    └── startup.md                  # Dev quickstart
```

---

## 4. Database Schema

MySQL 8+ / InnoDB / `utf8mb4` / `utf8mb4_unicode_ci`. `cases.id` is `VARCHAR(36)` (UUIDv4, VAPT v1.0.1 rec #2). Everything else that references `cases.id` MUST match its full column type or MySQL 3780 fires (see [database.md](./database.md)).

### Core identity

| Table | Purpose |
|---|---|
| `units` | 44 districts (name, code, active) |
| `police_stations` | 45+ Cyber Crime PSes (district, station name, active). Migration 018 renamed `CEN` → `Cyber` in station_name |
| `users` | Login accounts (username, hashed_password, role, unit_id, ps_id, is_active, must_change_password) |
| `revoked_tokens` | JWT logout / rotation list |

### Cases module

| Table | UNIQUE | Notes |
|---|---|---|
| `cases` | `(unit_id, ps_id, fir_no)` | 31-entry crime_type since migration 016; `sections` free-text; `is_financial` bool |
| `arrests` | CASCADE from cases | Per-case arrests |
| `accomplices` | CASCADE from arrests | Per-arrest accomplices |
| `accused_details` | CASCADE from arrests | Photos, contact, occupation |
| `petitions` | CASCADE from cases | Includes petition_type + amount |
| `lien_accounts` | CASCADE from cases | Frozen accounts with layer tracking |
| `unfreeze_details` | CASCADE from cases | Court order / letter defreezes |
| `refunds` | CASCADE from cases | Per-case victim refunds |
| `victims` | UNIQUE (case_id), CASCADE | 1:1 with cases; primary bank account fields |
| `victim_accounts` | CASCADE from cases | Additional victim accounts (migration 017) |
| `accused_accounts` | CASCADE from cases | Bank accounts money went to (migration 017) |

### NCRP Data module

| Table | UNIQUE | Notes |
|---|---|---|
| `mule_reports` | `acknowledgement_no`, `fir_no` | Parent for six txn tables |
| `money_transfers` | CASCADE from mule_reports | Bank-to-bank transfers |
| `other_transactions` | CASCADE from mule_reports | |
| `transactions_on_hold` | CASCADE from mule_reports | |
| `others_less_than_500` | CASCADE from mule_reports | |
| `aeps_transactions` | CASCADE from mule_reports | Aadhar-enabled withdrawals |
| `atm_withdrawals` | CASCADE from mule_reports | |

### All Accounts module

| Table | UNIQUE | Notes |
|---|---|---|
| `all_accounts` | `(unit_id, ps_id, serial_no)` | account_type Victim/Mule/Non-Mule; branch_state + layer since migration 012 |
| `all_account_mule_herders` | CASCADE from all_accounts | Multiple mule-herders per account |

### DSR module

| Table | UNIQUE | Notes |
|---|---|---|
| `dsr_entries` | `(unit_id, ps_id, report_date)` | Legacy district-level DSR — ps_id added migration 008 |
| `mule_entries` | `(unit_id, report_date)` | Mule intel free-text summaries |
| `daily_work_entries` | `(unit_id, ps_id, fir_no, report_date)` | Per-FIR daily activity (migration 014) |
| `portals_dsr_entries` | none | Multiple shift-batches per (unit, ps, date) legal (migration 013) |
| `daily_nil_declarations` | `(unit_id, ps_id, nil_date)` | NIL activity flag (migration 007) |

### Admin module

| Table | Notes |
|---|---|
| `chat_messages` | Every question + answer + SQL for audit (migration 005) |

### Upload analysis (7 tables, migrations 019–026)

`statement_transactions` (26.5 M rows / 27.6 GB), `upload_ledger`,
`account_statement_summary`, `id_photo_hashes`, `mule_account_link`,
`crypto_txn`, `ifsc_branch`.

**All DERIVED.** Every row is a function of the files under
`backend/uploads/` and is rebuildable by re-running `analysis.daily`.
**No web endpoint reads `statement_transactions`** — dashboards read the
~150 MB of summary tables instead, which is what keeps page loads
independent of a fact table heading for 200 GB. See
[database.md](./database.md#107-upload-analysis-subsystem-7-tables).

Total: 37 tables. Every child table CASCADE-deletes with its parent; every operator-created row carries `submitted_by`.

### Migration discipline

- Numbered, idempotent, hand-rolled Python scripts under `backend/migrations/`
- Each migration guards changes with INFORMATION_SCHEMA checks — safe to re-run
- Applied automatically by `deploy/update.sh` on every deploy
- No `reset_db.py` anymore — post-VAPT the app is production and dropping tables is banned. Every schema change goes via a new migration
- 001–026 currently in the pipeline (001–004 initial + fixups; 005 chat; 006 financial; 007 NIL; 008 ps_id on DSR; 009–012 All Accounts; 013 Portals DSR; 014 Daily Work; 015 sections; 016 crime types; 017 victim + accused accounts; 018 CEN → Cyber rename; 019–023 upload analysis; 024 crypto; 025 IFSC directory; 026 widen summary money)

---

## 5. API Surface

Everything under `/api/v1/`. Each route module scopes writes to `(unit_id, ps_id)` and enforces the role dependency.

### Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/login` | none | Login → JWT |
| POST | `/auth/logout` | Bearer | Revoke current token |
| GET | `/auth/me` | Bearer | Return current user |
| POST | `/auth/change-password` | Bearer | Change password, clear must_change_password flag |

### Public lookups (no auth)

| Method | Path |
|---|---|
| GET | `/units/public` |
| GET | `/districts/public` |
| GET | `/police-stations/public?district=` |

### Users

| Method | Path | Auth |
|---|---|---|
| GET | `/users` | admin+ |
| POST | `/users` | admin+ |
| PATCH | `/users/{id}` | admin+ |
| POST | `/users/{id}/reset-password` | admin+ |

### Cases

| Method | Path | Auth |
|---|---|---|
| POST | `/cases/` | Bearer |
| GET | `/cases/` | Bearer |
| GET | `/cases/all` | admin+ |
| GET | `/cases/{id}` | Bearer (per-record) |
| GET | `/cases/search?fir_no=` | Bearer |
| GET | `/cases/search-petition?petition_no=` | Bearer |
| PUT | `/cases/{id}` | Bearer (per-record) |
| DELETE | `/cases/{id}` | Bearer (per-record) |

### Mule reports

| Method | Path | Auth |
|---|---|---|
| POST | `/mule-reports/` | Bearer |
| GET | `/mule-reports/` | Bearer |
| GET | `/mule-reports/{id}` | Bearer (per-record) |
| GET | `/mule-reports/search?ack_no=` | Bearer |
| PUT | `/mule-reports/{id}` | Bearer (per-record) |
| DELETE | `/mule-reports/{id}` | Bearer (per-record) |
| POST | `/mule-reports/upload-excel` | Bearer |
| POST | `/mule-reports/parse-excel` | Bearer |

### All Accounts

| Method | Path | Auth |
|---|---|---|
| POST | `/all-accounts/` | Bearer |
| GET | `/all-accounts/` | Bearer |
| GET | `/all-accounts/{id}` | Bearer (per-record) |
| PUT | `/all-accounts/{id}` | Bearer (per-record) |
| DELETE | `/all-accounts/{id}` | Bearer (per-record) |

### DSR / Daily Work / Portals DSR / NIL

| Method | Path | Auth |
|---|---|---|
| POST/GET | `/dsr/` | Bearer |
| POST/GET | `/mule/` | Bearer (mule intel entry, distinct from mule-reports) |
| GET/POST/PUT/DELETE | `/daily-work/` | Bearer |
| GET | `/daily-work/dashboard` | admin+ |
| GET/POST/PUT/DELETE | `/portals-dsr/` | Bearer |
| POST | `/nil/` | admin+ (NIL declaration) |

### Dashboards (admin+ only)

| Method | Path | Notes |
|---|---|---|
| GET | `/dashboard/summary` | Cases module KPIs |
| GET | `/dashboard/unit-comparison` | |
| GET | `/dashboard/submission-status?date=` | Cross-PS submitted / NIL flags |
| GET | `/dashboard/fir-ps-performance?from=&to=` | FIR Dashboard |
| GET | `/dashboard/portals-summary?from=&to=` | Portals DSR KPIs |
| GET | `/dashboard/portals-comparison?from=&to=` | Per-PS Portals DSR |
| GET | `/dashboard/accounts-summary?date=` | Accounts KPIs |
| GET | `/dashboard/accounts-comparison?date=` | Per-PS accounts (with yesterday col) |
| GET | `/dashboard/accounts-daily-growth` | Line chart data |
| GET | `/dashboard/accounts-geo?scope=` | Map view — state / district / reporting |
| GET | `/dashboard/accounts-fir-trace?fir_no=&ps_id=` | Graphical Analysis — one FIR across 5 source tables, plus statement-derived flows and crypto |
| GET | `/dashboard/repeat-accounts` | Accounts appearing in 2+ FIRs |
| GET | `/dashboard/duplicate-ids` | F1 — accounts sharing a byte-identical ID photo |
| GET | `/dashboard/money-trail` | F2 — parsed-statement money movement |
| GET | `/dashboard/statement-coverage` | F2 — which accounts still have no usable statement |
| GET | `/dashboard/mule-network` | F4 — direct mule → mule transfers |
| GET | `/dashboard/mule-accounts` | The full mule roll, connected or not |
| GET | `/dashboard/crypto-trail` | Crypto Analysis — venues, accounts, evidence |

**All super_admin only.** Each crosses police-station boundaries, so a
station-scoped view would be meaningless and would breach the VAPT
7.7/7.8 scoping rule. They read the derived analysis tables, never
`statement_transactions`.

### Reports (admin+)

| Method | Path | Format |
|---|---|---|
| GET | `/reports/case.pdf?fir_no=` | Case file PDF |
| GET | `/reports/mule.pdf?ack_no=` | Mule report PDF |
| GET | `/reports/dsr.pdf?from=&to=&ps_id=` | DSR aggregated PDF |
| GET | `/reports/submission-status.pdf?date=` | |
| GET | `/reports/fir-ps-performance.{pdf,xlsx}?from=&to=` | |
| GET | `/reports/accounts-ps-comparison.{pdf,xlsx}?date=` | |
| GET | `/reports/portals-dsr-daily.{pdf,xlsx,json}?date=` | Daily PS-wise (2026-07-24) |
| GET | `/reports/daily-work-daily.{pdf,xlsx,json}?date=` | Daily PS-wise (2026-07-24) |

`.json` variants return the same aggregated data the PDF/XLSX use, letting the frontend render an on-screen preview before download.

### Chat (super_admin only)

| Method | Path |
|---|---|
| POST | `/chat/ask` |
| GET | `/chat/history` |

### Uploads

| Method | Path | Auth |
|---|---|---|
| POST | `/uploads/photo` | Bearer |
| POST | `/uploads/statement` | Bearer |

### Health

| Method | Path |
|---|---|
| GET | `/health` |

---

## 6. Frontend Architecture

### Modules

Frontend is organised around five modules defined once in `src/lib/utils/modules.ts`. The landing page renders a tile grid; the sidebar shows only the current module's links.

```
cases      → /cases/*, /petitions/*, /dashboard, /reports
ncrp       → /mule/*
accounts   → /all-accounts/*, /accounts-dashboard
dsr        → /dsr/*, /daily-work/*, /portals-dsr/*
admin      → /users, /chat
```

`getCurrentModule(pathname)` matches URL prefixes to the module def. Adding a new sidebar entry = one edit to `modules.ts`.

### Routing

React Router 7 flat routes in `App.tsx`. Every authenticated route is wrapped in `<ProtectedRoute>`; admin-only ones add `requireAdmin`. URLs stay stable even when the module reorganises (e.g. DSR module owns `/portals-dsr/*` even though those URLs predate the DSR module).

### State

Zustand for auth only (`token`, `user`). Everything else is local component state — no global stores. `localStorage` persists the token so refreshes work.

### API client

`lib/api/client.ts` exports `apiFetch<T>(path, opts)` which:
- Auto-injects `Authorization: Bearer {token}`
- Extracts human-readable error from Pydantic 422 responses (was `[object Object]` before the fix)
- Redirects to `/login` on 401

Every domain has its own typed wrapper (`lib/api/cases.ts`, `lib/api/reports.ts`, etc.) that re-uses `apiFetch`. Downloads use a separate `downloadPdf` helper in `reports.ts` that fetches a blob + triggers a save dialog.

### Types

Every server-facing interface lives in `src/types/index.ts`. Consolidated (not split by domain) so it's one grep to find any shape.

### Nested forms

Cases are the deepest — 6 nested collections + a 1:1 victim. State managed via plain `useState` + array-manipulation helpers. Never introduce `react-hook-form` or similar without discussion.

### Styling

Tailwind CSS with a KSP palette on CSS custom properties (`--ksp-navy`, `--ksp-yellow`, `--ksp-red`). No component library — utilities + a few reusable primitives (`AppShell`, `Sidebar`, `KpiCard`, `ChartCard`).

### Charts

Recharts. Common patterns: Bar / Line / Pie with a KSP-tuned palette. Every metric that spans multiple charts (Victim / Mule / Non-Mule) uses shared constants at the top of each dashboard page.

---

## 7. Report Generation

### Shared chrome (`reports/base.py`)

- `KSP_NAVY`, `KSP_YELLOW`, `KSP_RED` colors
- `_draw_page_chrome()` — yellow header band, KSP logo, page footer
- `build_pdf()` — wraps SimpleDocTemplate with A4 portrait / landscape defaults + 15mm margins
- `data_table()`, `report_title()`, `section_heading()`, `spacer()`, `kv_table()`

Most reports use `build_pdf()`. Wide reports (Portals DSR daily, Daily Work daily) drive `SimpleDocTemplate` directly to tighten margins to 8mm so 25+ columns fit on A4 landscape.

### XLSX renderers

openpyxl. Convention: title row + subtitle row + blank + header row + data rows + grand total row. Header uses navy fill + white bold; data rows alternate white / soft-grey; grand total row uses KSP yellow fill.

### Streaming responses

`_pdf_response(bytes, filename)` and `_xlsx_response(bytes, filename)` wrap raw bytes in `StreamingResponse` with the right MIME + `Content-Disposition: attachment` header. Frontend `downloadPdf()` prefers server-provided filename, falls back to a client-provided default.

### Preview endpoints

Every daily report has a `.json` sibling that returns the same aggregated rows the PDF / XLSX renderers consume. Frontend renders an on-screen table before the operator downloads — preview and file are always the same shape.

---

## 8. Deployment

### Production stack

- Ubuntu 24.04 VM (**2 vCPU / 16 GB / 300 GB**)
  - Corrected 2026-08-19. The earlier "4 vCPU / 8 GB / 50 GB" was wrong
    in every field, and the CPU figure mattered: the analysis governor
    holds back two cores for the OS, so on a 2-vCPU box it planned
    exactly ONE worker and the nightly parse ran serially at 12.5 s/file
    against 1.15 s/file on a laptop. `CFDSR_ANALYSIS_RESERVE_CORES=0` in
    the unit file is the fix, not a bigger number elsewhere
  - `innodb_buffer_pool_size` raised 128 MB → 4 GB (2026-08-19)
- MySQL 8.0 on localhost
- Backend: Gunicorn (4 workers) + Uvicorn, systemd unit `cyberfraud-backend`
- Nginx TLS termination (self-signed), reverse proxy `/api/*` and `/health`, static `dist/`
- `cyberfraud-nightly.timer` at 23:00 IST runs the analysis-then-backup
  chain (see Backups below). It REPLACED `cyberfraud-backup.timer` and
  `cyberfraud-analysis.timer`; leaving either enabled would fire a
  backup between the chain's two halves

### update.sh flow

1. `git pull` on `/opt/scrb`
2. pip install
3. Run migrations 001 → 004, 006 → 026 (idempotent — each is a no-op when already applied; 005 is skipped on prod)
4. `npm install && npm run build` (frontend)
5. rsync backend + frontend/dist into runtime
6. Restart `cyberfraud-backend.service`
7. Reload nginx
8. Self-verify — hits `/health`, checks every migration's target schema landed, checks admin routes respond 401 (not 500 / 404)

Self-verify aborts the deploy if any check fails, so you don't ship a half-migrated schema. See `deploy/update.sh` for the current check list.

### Backups

**One nightly chain, not two timers.** `cyberfraud-nightly.timer` fires
at 23:00 IST and runs `nightly-all.sh`:

1. `analysis.daily --skip-relink` — the full analysis pass
2. `backup-all.sh` — `backup-db.sh` then `backup-uploads.sh`

The ORDER is the point. It was previously two timers an hour apart —
backup at 00:00, analysis at 01:00 — which orders by clock rather than
by dependency, so every backup carried the PREVIOUS day's analysis.
Sequential in one unit is what makes "the backup contains today's
analysis" true rather than usually true.

The analysis gets its own 6 h budget inside a 10 h unit timeout, so an
overrun ends the analysis and still leaves time to back up. The backup
runs even when the analysis fails; the unit still exits non-zero.

- `backup-db.sh` → nightly mysqldump. Excludes **only**
  `statement_transactions` (27.6 GB, rebuildable from the PDFs). The
  summaries ARE included — production generates them now, so they are
  the only copy that exists
- `backup-uploads.sh` → **weekly full + nightly incremental** via
  `tar --listed-incremental`, uncompressed. A nightly full re-archived
  19.5 GB to capture ~500 MB of new files, and gzip saves 9% on
  already-compressed PDFs and JPEGs for 24 minutes of CPU
- Both are safe to run mid-day (the mysqldump uses `--single-transaction`)

---

## 9. Feature Flags

- `CFDSR_CHAT_ENABLED` — gates the Ask-the-Data chat page + API. Default false in prod; requires the LLM API key to be set for it to work at all. Even when on, only super_admins can use it.

---

## 10. Known Constraints

- FastAPI async only — every route is `async def`; every DB call uses `AsyncSession`. Sync code is not allowed
- No raw SQL — SQLAlchemy ORM exclusively (a small number of `func.count` etc. in aggregators is fine, hand-written SQL is not)
- Free-text on write → `strip_html` — VAPT v1.0.1 rec, applied via Pydantic `field_validator`
- File uploads go to `backend/uploads/` — never to `frontend/public` or a CDN
- Every case update rebuilds the entire nested tree — the update route deletes all children and re-inserts, so PUT bodies MUST include the complete state (except `victim_accounts` / `accused_accounts`, which are Optional pass-through)
- Adding an env var → `CFDSR_` prefix + `config.py` registration or the setting won't be read

---

_See [SRS.md](./SRS.md) for the product view. See [database.md](./database.md) for migration + charset conventions. See [ProductionDeployment.md](./ProductionDeployment.md) for full server bring-up._
