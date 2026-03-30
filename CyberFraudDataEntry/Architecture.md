# Architecture — Cyber Fraud Data Entry

## System Overview

```
                        ┌───────────────────────┐
                        │   React 19 SPA        │
                        │   Vite (port 5173)    │
                        │   Tailwind + Zustand  │
                        └───────────┬───────────┘
                                    │ /api/* proxy
                        ┌───────────▼───────────┐
                        │   Nginx (prod only)   │
                        │   SSL + static files  │
                        └───────────┬───────────┘
                                    │
                        ┌───────────▼───────────┐
                        │   FastAPI (port 8000) │
                        │   Gunicorn + Uvicorn  │
                        └──┬────────────────┬───┘
                           │                │
              ┌────────────▼──┐    ┌────────▼────────┐
              │   MySQL 8+    │    │  File Storage   │
              │ cyber_fraud_  │    │  (photos, Excel)│
              │     dsr       │    │                 │
              └───────────────┘    └─────────────────┘
```

**Request flow:**
1. User interacts with React SPA
2. Frontend calls `/api/v1/*` endpoints (proxied via Vite dev server or Nginx)
3. FastAPI validates JWT token, checks role/unit authorization
4. SQLAlchemy async session executes queries against MySQL
5. Response returned as JSON (Pydantic-serialized)

---

## Authentication & Authorization

### JWT Token Flow

```
Login Request                Backend                     Frontend
    │                           │                           │
    ├── POST /auth/login ──────▶│                           │
    │   {username, password}    │                           │
    │                           ├── verify bcrypt hash      │
    │                           ├── create JWT token        │
    │◀── {token, role, unit} ──┤                           │
    │                           │                           │
    │                           │     ┌─────────────────────┤
    │                           │     │ Store in localStorage│
    │                           │     │ + Zustand store      │
    │                           │     └─────────────────────┤
    │                           │                           │
    ├── GET /api/v1/cases ─────▶│                           │
    │   Authorization: Bearer   │                           │
    │                           ├── decode JWT              │
    │                           ├── check unit_id scope     │
    │◀── {cases: [...]} ───────┤                           │
```

### JWT Token Structure

```json
{
  "sub": "user_id",
  "role": "admin | unit_user",
  "unit_id": 123
}
```

- **Algorithm:** HS256
- **Expiry:** 480 minutes (8 hours), configurable
- **Password hashing:** bcrypt (passlib CryptContext)
- **Note:** `decode_token` uses `verify_exp=False` — expiry handled by frontend

### Role-Based Access Control

| Role | Data Scope | Dashboard | User Management |
|------|-----------|-----------|-----------------|
| `admin` | All units | Yes | Yes |
| `unit_user` | Own unit only | No | No |

### Authorization Dependencies (api/deps.py)

```python
get_current_user()    # Extracts user from JWT, returns CurrentUser
require_admin()       # Raises 403 if role != admin
require_unit_user()   # Raises 403 if role != unit_user
```

---

## Database Schema

### Entity Relationship Diagram

```
units ──────┬──── users
            │
            ├──── cases ──────┬──── arrests ──────┬──── accomplices
            │                 │                   └──── accused_details
            │                 ├──── petitions
            │                 ├──── lien_accounts
            │                 ├──── unfreeze_details
            │                 └──── refunds
            │
            ├──── mule_reports ───┬──── money_transfers
            │                    ├──── other_transactions
            │                    ├──── transactions_on_hold
            │                    ├──── others_less_than_500
            │                    ├──── aeps_transactions
            │                    └──── atm_withdrawals
            │
            ├──── mule_entries
            └──── dsr_entries

police_stations (standalone lookup table)
```

### Table Definitions

#### users

```sql
CREATE TABLE users (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    username        VARCHAR(50) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name       VARCHAR(150),
    role            ENUM('admin', 'unit_user') NOT NULL,
    unit_id         INT REFERENCES units(id),
    ps_id           INT REFERENCES police_stations(id),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### units

```sql
CREATE TABLE units (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(100) UNIQUE NOT NULL,
    code       VARCHAR(50) UNIQUE NOT NULL,
    is_active  BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### police_stations

```sql
CREATE TABLE police_stations (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    district_name VARCHAR(100) NOT NULL,
    station_name  VARCHAR(200) NOT NULL,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### cases

```sql
CREATE TABLE cases (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    unit_id           INT NOT NULL REFERENCES units(id),
    fir_no            VARCHAR(50),
    petition_no       VARCHAR(50),
    registration_date DATE,
    case_type         VARCHAR(20),        -- NCRP, Walk-In, Petition
    crime_type        VARCHAR(30),        -- Internet, Digital, Crypto
    facts             TEXT,
    status            VARCHAR(20) DEFAULT 'draft',  -- draft, submitted
    submitted_by      INT REFERENCES users(id),
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY (unit_id, fir_no)
);
```

#### arrests

```sql
CREATE TABLE arrests (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    case_id         INT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    name            VARCHAR(200) NOT NULL,
    address         TEXT,
    email           VARCHAR(200),
    aadhar          VARCHAR(12),
    pan             VARCHAR(10),
    date_of_arrest  DATE,
    statement       TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### accomplices

```sql
CREATE TABLE accomplices (
    id                     INT AUTO_INCREMENT PRIMARY KEY,
    arrest_id              INT NOT NULL REFERENCES arrests(id) ON DELETE CASCADE,
    where_met              VARCHAR(500),
    where_stayed           VARCHAR(500),
    interrogation_details  TEXT,
    created_at             DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### accused_details

```sql
CREATE TABLE accused_details (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    arrest_id   INT NOT NULL REFERENCES arrests(id) ON DELETE CASCADE,
    photo_path  VARCHAR(500),
    email       VARCHAR(200),
    mobile      VARCHAR(20),
    occupation  VARCHAR(100),
    remarks     TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### petitions

```sql
CREATE TABLE petitions (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    case_id         INT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    petition_no     VARCHAR(50),
    fir_registered  VARCHAR(20),          -- yes, no, transferred
    why_not         TEXT,
    nature          VARCHAR(100),
    petition_type   VARCHAR(30),          -- amount_lost, fraud_case
    amount          NUMERIC(18,2) DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### lien_accounts

```sql
CREATE TABLE lien_accounts (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    case_id                 INT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    case_type               VARCHAR(20),   -- FIR, NCRP, Petition
    account_no              VARCHAR(50) NOT NULL,
    amount_lien_marked      NUMERIC(18,2) DEFAULT 0,
    layer                   INT DEFAULT 1,
    total_amount_in_account NUMERIC(18,2) DEFAULT 0,
    bank_name               VARCHAR(200),
    created_at              DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### unfreeze_details

```sql
CREATE TABLE unfreeze_details (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    case_id        INT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    unfreeze_type  VARCHAR(20),           -- letter, court_order
    crime_no       VARCHAR(50),
    bank_name      VARCHAR(200),
    account_no     VARCHAR(50),
    amount         NUMERIC(18,2) DEFAULT 0,
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### refunds

```sql
CREATE TABLE refunds (
    id                       INT AUTO_INCREMENT PRIMARY KEY,
    case_id                  INT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    refunded                 VARCHAR(20),  -- yes, no
    victim_name              VARCHAR(200),
    amount                   NUMERIC(18,2) DEFAULT 0,
    crime_no_or_petition_no  VARCHAR(50),
    created_at               DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### mule_reports

```sql
CREATE TABLE mule_reports (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    unit_id            INT NOT NULL REFERENCES units(id),
    acknowledgement_no VARCHAR(50) UNIQUE,
    fir_no             VARCHAR(50) UNIQUE,
    status             VARCHAR(20) DEFAULT 'draft',
    submitted_by       INT REFERENCES users(id),
    created_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME ON UPDATE CURRENT_TIMESTAMP
);
```

#### money_transfers

```sql
CREATE TABLE money_transfers (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    report_id             INT NOT NULL REFERENCES mule_reports(id) ON DELETE CASCADE,
    account_no            VARCHAR(50),
    transaction_id        VARCHAR(100),
    bank                  VARCHAR(200),
    layer                 INT,
    dest_account_no       VARCHAR(50),
    ifsc_code             VARCHAR(20),
    transaction_date      DATE,
    dest_transaction_id   VARCHAR(100),
    transaction_amount    NUMERIC(18,2),
    disputed_amount       NUMERIC(18,2),
    reference_no          VARCHAR(100),
    remarks               TEXT,
    action_taken_by_bank  VARCHAR(500),
    date_of_action        DATE,
    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### other_transactions

```sql
CREATE TABLE other_transactions (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    report_id             INT NOT NULL REFERENCES mule_reports(id) ON DELETE CASCADE,
    account_no            VARCHAR(50),
    transaction_id        VARCHAR(100),
    transaction_date      DATE,
    transaction_amount    NUMERIC(18,2),
    reference_no          VARCHAR(100),
    remarks               TEXT,
    action_taken_by_bank  VARCHAR(500),
    date_of_action        DATE,
    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### transactions_on_hold

```sql
CREATE TABLE transactions_on_hold (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    report_id             INT NOT NULL REFERENCES mule_reports(id) ON DELETE CASCADE,
    account_no            VARCHAR(50),
    transaction_id        VARCHAR(100),
    hold_date             DATE,
    hold_amount           NUMERIC(18,2),
    action_taken_by_bank  VARCHAR(500),
    date_of_action        DATE,
    layer                 INT,
    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### others_less_than_500

```sql
CREATE TABLE others_less_than_500 (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    report_id             INT NOT NULL REFERENCES mule_reports(id) ON DELETE CASCADE,
    account_no            VARCHAR(50),
    transaction_id        VARCHAR(100),
    reference_no          VARCHAR(100),
    remarks               TEXT,
    action_taken_by_bank  VARCHAR(500),
    date_of_action        DATE,
    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### aeps_transactions

```sql
CREATE TABLE aeps_transactions (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    report_id             INT NOT NULL REFERENCES mule_reports(id) ON DELETE CASCADE,
    account_no            VARCHAR(50),
    transaction_id        VARCHAR(100),
    withdrawal_date       DATE,
    withdrawal_amount     NUMERIC(18,2),
    reference_no          VARCHAR(100),
    remarks               TEXT,
    action_taken_by_bank  VARCHAR(500),
    date_of_action        DATE,
    layer                 INT,
    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### atm_withdrawals

```sql
CREATE TABLE atm_withdrawals (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    report_id             INT NOT NULL REFERENCES mule_reports(id) ON DELETE CASCADE,
    account_no            VARCHAR(50),
    transaction_id        VARCHAR(100),
    withdrawal_datetime   DATETIME,
    withdrawal_amount     NUMERIC(18,2),
    disputed_amount       NUMERIC(18,2),
    atm_id                VARCHAR(100),
    atm_location          VARCHAR(500),
    reference_no          VARCHAR(100),
    remarks               TEXT,
    action_taken_by_bank  VARCHAR(500),
    date_of_action        DATE,
    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### mule_entries

```sql
CREATE TABLE mule_entries (
    id                              INT AUTO_INCREMENT PRIMARY KEY,
    unit_id                         INT NOT NULL REFERENCES units(id),
    report_date                     DATE NOT NULL,
    accounts_most_liens             TEXT,
    recruiters_for_lien_accounts    TEXT,
    accounts_max_money_routed       TEXT,
    accounts_max_transactions       TEXT,
    recency_atm_transactions        TEXT,
    cash_withdrawals_mule_wise      TEXT,
    atm_geo_identification          TEXT,
    atm_table_by_transactions       TEXT,
    cheque_withdrawal_branches      TEXT,
    money_left_system_stats         TEXT,
    crypto_mule_accounts            TEXT,
    submitted_by                    INT REFERENCES users(id),
    created_at                      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at                      DATETIME ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY (unit_id, report_date)
);
```

#### dsr_entries

```sql
CREATE TABLE dsr_entries (
    id                                  INT AUTO_INCREMENT PRIMARY KEY,
    unit_id                             INT NOT NULL REFERENCES units(id),
    report_date                         DATE NOT NULL,
    cases                               INT DEFAULT 0,
    petitions                           INT DEFAULT 0,
    details_of_arrest                   INT DEFAULT 0,
    case_type                           VARCHAR(20),
    cumulative_amount_lien_marked       NUMERIC(18,2) DEFAULT 0,
    cumulative_accounts_lien_marked     INT DEFAULT 0,
    cumulative_accounts_defreezed       INT DEFAULT 0,
    amount_refunded_to_victim           NUMERIC(18,2) DEFAULT 0,
    ui_cases_pending_2021               INT DEFAULT 0,
    ui_cases_pending_2022               INT DEFAULT 0,
    ui_cases_pending_2023               INT DEFAULT 0,
    ui_cases_pending_2024               INT DEFAULT 0,
    ui_cases_pending_2025               INT DEFAULT 0,
    ui_cases_pending_2026               INT DEFAULT 0,
    disposed_detected_chargesheeted     INT DEFAULT 0,
    disposed_transferred                INT DEFAULT 0,
    disposed_false                      INT DEFAULT 0,
    disposed_undetected                 INT DEFAULT 0,
    trial_convicted                     INT DEFAULT 0,
    trial_discharged                    INT DEFAULT 0,
    trial_acquitted                     INT DEFAULT 0,
    trial_abated                        INT DEFAULT 0,
    trial_compounded                    INT DEFAULT 0,
    trial_ut                            INT DEFAULT 0,
    submitted_by                        INT REFERENCES users(id),
    created_at                          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at                          DATETIME ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY (unit_id, report_date)
);
```

---

## API Reference

### Authentication (`/api/v1/auth`)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/login` | None | Login, returns JWT + user info |
| GET | `/me` | Bearer | Get current user |

### Public Data (no auth)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/units` | List active units |
| GET | `/api/v1/units/public` | Units for login form |
| GET | `/api/v1/districts/public` | List all districts |
| GET | `/api/v1/police-stations/public?district={name}` | Police stations by district |

### Cases (`/api/v1/cases`)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/` | Bearer | Create case with nested children |
| GET | `/` | Bearer | List own unit cases (limit/offset) |
| GET | `/all` | Admin | List all cases |
| GET | `/{case_id}` | Bearer | Get case with all children |
| GET | `/search?fir_no={fir}` | Bearer | Search by FIR number |
| GET | `/search-petition?petition_no={no}` | Bearer | Search by petition number |
| PUT | `/{case_id}` | Bearer | Update case |
| DELETE | `/{case_id}` | Bearer | Delete case (CASCADE) |

### Mule Reports (`/api/v1/mule-reports`)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/` | Bearer | Create mule report with transactions |
| GET | `/` | Bearer | List own unit reports (limit/offset) |
| GET | `/{report_id}` | Bearer | Get report with all transactions |
| GET | `/search?ack_no={no}` | Bearer | Search by acknowledgement number |
| PUT | `/{report_id}` | Bearer | Update mule report |
| DELETE | `/{report_id}` | Bearer | Delete report (CASCADE) |
| POST | `/upload-excel` | Bearer | Upload bank Excel files (batch) |
| POST | `/parse-excel` | Bearer | Preview parsed Excel (no save) |

### Mule Entries (`/api/v1/mule`)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/` | Bearer | Upsert mule entry (unit_id + date) |
| GET | `/?date={YYYY-MM-DD}` | Bearer | Get own unit entry for date |
| GET | `/history?limit=30` | Bearer | Get own unit history |
| GET | `/all?date={YYYY-MM-DD}` | Admin | Get all units for date |

### DSR (`/api/v1/dsr`)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/` | Bearer | Upsert DSR entry (unit_id + date) |
| GET | `/?date={YYYY-MM-DD}` | Bearer | Get own unit entry for date |
| GET | `/history?limit=30` | Bearer | Get own unit history |
| GET | `/all?date={YYYY-MM-DD}` | Admin | Get all units for date |

### Dashboard (`/api/v1/dashboard`) — Admin only

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/summary` | KPI totals (cases, arrests, lien amount, refunds) |
| GET | `/unit-comparison` | Per-unit comparison stats |

### Uploads (`/api/v1/uploads`)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/photo` | Bearer | Upload accused photo |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Service health check |

---

## Frontend Architecture

### Routing

```
/login                    → LoginPage (public)
/                         → Redirect to /cases/new
/cases/new                → CaseEntryPage
/cases/:id                → CaseEntryPage (edit mode)
/cases/update             → CaseUpdatePage (search + edit)
/cases                    → CaseListPage
/petitions/new            → PetitionEntryPage
/petitions/:id            → PetitionUpdatePage
/petitions/update         → PetitionUpdatePage (search)
/mule/new                 → MuleReportEntryPage
/mule/:id                 → MuleReportEntryPage (edit)
/mule/update              → MuleUpdatePage (search)
/mule/upload              → MuleUploadPage (Excel)
/mule/reports             → MuleReportListPage
/mule/entry               → MuleEntryPage
/dsr                      → DsrEntryPage
/history                  → HistoryPage (DSR + Mule)
/dashboard                → DashboardPage (admin only)
```

### State Management

**Zustand auth store** — minimal global state:
```typescript
interface AuthState {
  token: string | null
  user: User | null
  setAuth(token: string, user: User): void
  logout(): void
  loadFromStorage(): void
}
```

- Token + user persisted in `localStorage`
- All other state is local to page components (useState)

### API Client Pattern

```typescript
// lib/api/client.ts
async function apiFetch<T>(path: string, options?: RequestInit): Promise<T>
```

- Auto-injects `Authorization: Bearer {token}` header
- On 401: clears localStorage, redirects to `/login`
- All domain-specific API files use this base function

### Component Hierarchy

```
App.tsx (Router)
  └─ ProtectedRoute (auth guard)
       └─ AppShell (layout)
            ├─ Sidebar (navigation)
            └─ Page Component
                 ├─ Form sections (inline)
                 ├─ DsrForm (reusable)
                 └─ MuleForm (reusable)
```

### Nested Form Pattern (Cases)

Cases use deeply nested forms with dynamic add/remove:
```
CaseEntryPage
  ├─ Case fields (fir_no, case_type, crime_type, facts)
  ├─ Arrests[] (dynamic array)
  │    ├─ Arrest fields (name, address, aadhar, pan)
  │    ├─ Accomplices[] (nested dynamic array)
  │    └─ AccusedDetails[] (nested dynamic array)
  ├─ Petitions[] (dynamic array)
  ├─ LienAccounts[] (dynamic array)
  ├─ UnfreezeDetails[] (dynamic array)
  └─ Refunds[] (dynamic array)
```

All managed via React `useState` with array manipulation helpers.

---

## Production Deployment

### Server Architecture

```
Internet → Nginx (443/SSL) → Gunicorn (8000) → FastAPI
                           → Static files (frontend/dist)
```

### Stack
- **OS:** Ubuntu 22.04 VM (4 vCPU, 8 GB RAM, 50 GB SSD)
- **Reverse proxy:** Nginx with SSL termination
- **ASGI server:** Gunicorn with Uvicorn workers
- **Process manager:** systemd
- **Database:** MySQL 8.0

### Nginx Configuration

- Serves `frontend/dist/` as static files at `/`
- Proxies `/api/*` and `/health` to Gunicorn on port 8000
- SSL with Let's Encrypt certificates
- Gzip compression enabled

### systemd Service

- Service name: `cyberfraud-api`
- Working directory: `/opt/cyberfraud/backend`
- Command: `gunicorn main:app -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8000`
- Auto-restart on failure

---

## Excel Upload Pipeline

### Supported Sheet Types

| Sheet Name | Maps To | Key Fields |
|------------|---------|------------|
| Money Transfers | `money_transfers` | account_no, transaction_id, bank, layer, dest_account_no, amounts |
| Other Transactions | `other_transactions` | account_no, transaction_id, amounts |
| Transactions on Hold | `transactions_on_hold` | account_no, hold_date, hold_amount |
| Others < 500 | `others_less_than_500` | account_no, transaction_id, reference_no |
| AEPS | `aeps_transactions` | account_no, withdrawal_date, withdrawal_amount |
| ATM Withdrawals | `atm_withdrawals` | account_no, withdrawal_datetime, atm_id, atm_location |

### Flow

1. User uploads Excel file(s) via `/mule/upload` page
2. Frontend sends to `POST /api/v1/mule-reports/parse-excel` for preview
3. User reviews parsed data
4. Frontend sends to `POST /api/v1/mule-reports/upload-excel` to save
5. Backend creates `MuleReport` + child transaction records
6. `acknowledgement_no` extracted from first data row of Excel

### Processing (openpyxl)

- Reads each sheet by name
- First non-empty row = headers
- Subsequent rows mapped to typed transaction objects
- Skips empty rows and sheets with no data
