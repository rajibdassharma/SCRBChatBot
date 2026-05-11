# CyberFraud Data Entry — Architecture & Design Document

**Application**: CyberFraud DSR & Mule Account Data Entry System
**Client**: Karnataka State Police — SCRB / CID Cyber Crime Division
**Scale**: 44 Cyber Command Police Stations (CCPS) across 36 districts
**Network**: Internal government network (KSWAN / NIC)
**Version**: 2.0

---

## 1. System Overview

The CyberFraud Data Entry system is a web-based application for Karnataka State Police to manage:
1. **Daily Status Reports (DSR)** — FIR-based case management with arrests, petitions, lien/freeze details, and refund tracking
2. **Mule Account Data** — Bank action reports with transaction tracking across 6 categories (money transfers, holds, AEPS, ATM withdrawals, etc.)

All 44 CCPS stations across Karnataka access the system concurrently over the internal police network.

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                KSWAN / NIC Internal Network                  │
│                                                              │
│   CCPS 1     CCPS 2     CCPS 3    ...    CCPS 44           │
│   (Browser)  (Browser)  (Browser)        (Browser)          │
│                                                              │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP/HTTPS
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Ubuntu 22.04 VM                           │
│                 (4 vCPU, 8 GB RAM, 50 GB SSD)               │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                    Nginx                             │    │
│  │              (Reverse Proxy)                         │    │
│  │         :80 (HTTP) / :443 (HTTPS)                    │    │
│  │                                                      │    │
│  │   /api/* ──► Gunicorn        /* ──► Static Files     │    │
│  │   /health    (backend)              (React SPA)      │    │
│  └──────┬──────────────────────────────┬────────────────┘    │
│         │                              │                     │
│         ▼                              ▼                     │
│  ┌──────────────────┐    ┌──────────────────────────┐       │
│  │   Gunicorn        │    │    React SPA (dist/)      │       │
│  │   + Uvicorn       │    │                           │       │
│  │   Workers (4)     │    │  - LoginForm              │       │
│  │                   │    │  - CaseEntryPage           │       │
│  │   :8000           │    │  - PetitionEntryPage       │       │
│  │   (localhost only)│    │  - MuleReportEntryPage     │       │
│  └────────┬──────────┘    │  - MuleUploadPage          │       │
│           │               │  - DashboardPage           │       │
│           ▼               └──────────────────────────┘       │
│  ┌──────────────────┐                                        │
│  │    FastAPI        │                                        │
│  │    (Async)        │                                        │
│  │                   │                                        │
│  │  Auth Routes      │                                        │
│  │  Case Routes      │                                        │
│  │  Mule Routes      │                                        │
│  │  Dashboard Routes │                                        │
│  │  Excel Upload     │                                        │
│  └────────┬──────────┘                                        │
│           │                                                   │
│           ▼                                                   │
│  ┌──────────────────┐                                        │
│  │    MySQL 8.0      │                                        │
│  │    :3306           │                                        │
│  │   (localhost only) │                                        │
│  │                    │                                        │
│  │  cyber_fraud_dsr   │                                        │
│  └────────────────────┘                                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React 19 + TypeScript | Single Page Application |
| **UI Framework** | Tailwind CSS | Styling |
| **State Management** | Zustand | Client-side auth state |
| **Build Tool** | Vite | Fast dev + production builds |
| **Backend** | FastAPI (Python 3.11+) | Async REST API |
| **ORM** | SQLAlchemy 2.0 + asyncmy | Async MySQL access |
| **Authentication** | JWT (HS256) + bcrypt | Stateless auth tokens |
| **Database** | MySQL 8.0 | Relational data store |
| **Reverse Proxy** | Nginx | SSL termination, static files, load balancing |
| **Process Manager** | Gunicorn + Uvicorn workers | Multi-worker ASGI server |
| **Service Manager** | systemd | Auto-start, restart on failure |
| **Excel Parsing** | openpyxl | Bank action Excel file import |

---

## 4. Database Schema

### 4.1 Entity Relationship Overview

```
units (districts)
  │
  ├── users ──── police_stations
  │
  ├── cases (FIR-based)
  │     ├── arrests
  │     │     └── accomplices
  │     │     └── accused_details (photos)
  │     ├── petitions
  │     ├── lien_accounts
  │     ├── unfreeze_details
  │     └── refunds
  │
  └── mule_reports (Ack No based)
        ├── money_transfers
        ├── other_transactions
        ├── transactions_on_hold
        ├── others_less_than_500
        ├── aeps_transactions
        └── atm_withdrawals
```

### 4.2 Table Details

#### Authentication & Organization

| Table | Key Fields | Notes |
|-------|-----------|-------|
| `units` | id, name, code | 36 districts |
| `police_stations` | id, district_name, station_name | 44 CCPS stations |
| `users` | id, username, hashed_password, role, unit_id, ps_id | 2 per CCPS (admin + user) |

#### DSR — Case Management

| Table | Key Fields | Relationship |
|-------|-----------|-------------|
| `cases` | id, fir_no (unique), case_type, crime_type, facts, status | Parent |
| `arrests` | id, case_id, name, address, email, aadhar, pan, date_of_arrest | FK → cases |
| `accomplices` | id, arrest_id, where_met, where_stayed, interrogation_details | FK → arrests |
| `accused_details` | id, arrest_id, photo_path, email | FK → arrests |
| `petitions` | id, case_id, fir_registered, nature, petition_type, amount_lost | FK → cases (nullable) |
| `lien_accounts` | id, case_id, account_no, amount_lien, layer, total_amount, bank | FK → cases |
| `unfreeze_details` | id, case_id, unfreeze_type, crime_no, account_no, amount, bank | FK → cases |
| `refunds` | id, case_id, refunded, victim_name, amount, crime_no | FK → cases |

#### Mule Account Reports

| Table | Key Fields | Relationship |
|-------|-----------|-------------|
| `mule_reports` | id, acknowledgement_no (unique), fir_no, status | Parent |
| `money_transfers` | report_id, account_no, transaction_id, bank, layer, amount | FK → mule_reports |
| `other_transactions` | report_id, account_no, transaction_id, amount, remarks | FK → mule_reports |
| `transactions_on_hold` | report_id, account_no, hold_date, hold_amount, layer | FK → mule_reports |
| `others_less_than_500` | report_id, account_no, transaction_id, remarks | FK → mule_reports |
| `aeps_transactions` | report_id, account_no, withdrawal_amount, layer | FK → mule_reports |
| `atm_withdrawals` | report_id, account_no, atm_id, atm_location, amount | FK → mule_reports |

### 4.3 Cascade Behavior

All child tables use `ON DELETE CASCADE` — deleting a case or mule report automatically removes all associated records.

---

## 5. Application Flow

### 5.1 Authentication Flow

```
User opens browser
       │
       ▼
Login Page
  ├── Select District (dropdown, 36 options)
  ├── Select CCPS (dropdown, filtered by district)
  ├── Enter User ID
  └── Enter Password
       │
       ▼
POST /api/v1/auth/login
  ├── Validate credentials (bcrypt hash compare)
  ├── Generate JWT token (no expiry)
  └── Return token + user info (unit_id, ps_name, role)
       │
       ▼
Frontend stores token in localStorage
  └── All subsequent API calls include Authorization: Bearer <token>
```

### 5.2 DSR — Case Entry Flow

```
New Case
  │
  ▼
Tab 1: Case Details
  ├── FIR No, Date, Case Type (NCRP/Walk-In)
  ├── Crime Type (Internet/Digital/Crypto)
  └── Facts (text area)
  │
  ▼  [Save Draft] → POST/PUT /api/v1/cases/ (status=draft)
  │
Tab 2: Arrest Details
  ├── Name, Address, Email, Aadhar, PAN
  ├── Date of Arrest
  └── [+] Add more arrested persons
  │
  ▼  [Save Draft]
  │
Tab 3: IR Details
  ├── List of arrested persons (from Tab 2)
  └── Photo upload per arrested person
  │
  ▼  [Save Draft]
  │
Tab 4: Petitions
  ├── FIR Registered? (Yes/No/Transferred)
  ├── Nature of Petition, Type, Amount Lost
  └── If "No" → Text box "Why not?"
  │
  ▼  [Save Draft]
  │
Tab 5: Lien Marked Details
  ├── Case Type (FIR/NCRP/Petition)
  ├── Account No, Amount Lien, Layer, Bank
  └── [+] Add more accounts
  │
  ▼  [Save Draft]
  │
Tab 6: Unfreeze Details
  ├── Type (Letter/Court Order)
  ├── Crime No, Account No, Amount, Bank
  └── [+] Add more entries
  │
  ▼  [Save Draft]
  │
Tab 7: Refunds
  ├── Refunded / Not Refunded
  ├── Victim Name, Amount, Crime No
  └── [+] Add more entries
  │
  ▼  [Submit] → PUT /api/v1/cases/{id} (status=submitted)
```

### 5.3 Petition Entry Flow (Standalone)

Same as Case Entry but only shows Tabs 4-7 (Petitions, Lien, Unfreeze, Refunds). No Case Details, Arrests, or IR tabs.

### 5.4 Mule Account Data Flow

```
                    New Mule Report
                         │
            ┌────────────┴────────────┐
            │                         │
     Upload Excel               Manual Entry
     (one or more files)        (6 tabs)
            │                         │
            ▼                         ▼
     Parse Excel               Tab-by-tab entry:
     (openpyxl)                1. Money Transfer To
       │                       2. Other
       ├── Extract ack_no      3. Transaction On Hold
       ├── Map 6 sheets        4. Others < 500
       │   to 6 tables         5. AEPS
       └── Insert all          6. ATM Withdrawal
            │                         │
            ▼                         ▼
     POST /upload-excel        POST/PUT /api/v1/mule-reports/
            │                         │
            └────────┬────────────────┘
                     │
                     ▼
              MySQL mule_reports
              + 6 child tables
```

### 5.5 Update Flow

```
Update Case / Petition / Mule Report
       │
       ▼
Enter FIR No / Petition No / Ack No
       │
       ▼
GET /search?fir_no=... or ?ack_no=...
       │
       ├── Found → Load data into form (editable, except FIR/Ack No)
       │
       └── Not Found → Show error message
```

---

## 6. API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|---------|-------------|
| POST | `/api/v1/auth/login` | Login with username + password |
| GET | `/api/v1/districts/public` | List districts (no auth) |
| GET | `/api/v1/police-stations/public` | List PS by district (no auth) |

### Cases (DSR)
| Method | Endpoint | Description |
|--------|---------|-------------|
| POST | `/api/v1/cases/` | Create case (draft/submitted) |
| GET | `/api/v1/cases/` | List cases for user's unit |
| GET | `/api/v1/cases/{id}` | Get case with all children |
| PUT | `/api/v1/cases/{id}` | Update case |
| DELETE | `/api/v1/cases/{id}` | Delete case + all children |
| GET | `/api/v1/cases/search?fir_no=...` | Search by FIR number |

### Mule Reports
| Method | Endpoint | Description |
|--------|---------|-------------|
| POST | `/api/v1/mule-reports/` | Create report |
| GET | `/api/v1/mule-reports/` | List reports for user's unit |
| GET | `/api/v1/mule-reports/{id}` | Get report with all transactions |
| PUT | `/api/v1/mule-reports/{id}` | Update report |
| DELETE | `/api/v1/mule-reports/{id}` | Delete report + all transactions |
| GET | `/api/v1/mule-reports/search?ack_no=...` | Search by acknowledgement no |
| POST | `/api/v1/mule-reports/upload-excel` | Upload Excel files (multi-file) |

### Dashboard
| Method | Endpoint | Description |
|--------|---------|-------------|
| GET | `/api/v1/dashboard/stats` | Aggregate stats (admin only) |

---

## 7. Security Architecture

### 7.1 Authentication & Authorization

```
┌───────────────┐     JWT Token      ┌──────────────┐
│   Browser     │ ──────────────────► │  FastAPI      │
│               │  Authorization:     │  Middleware   │
│  localStorage │  Bearer <token>     │              │
│  stores token │                     │  Validates:  │
└───────────────┘                     │  - Signature │
                                      │  - Claims    │
                                      │  - Role      │
                                      └──────────────┘
```

- **JWT tokens** — stateless, signed with HS256, no expiry (internal network)
- **bcrypt password hashing** — 12 rounds, salted
- **Role-based access** — `admin` sees all unit data + dashboard; `unit_user` sees own unit only
- **Data isolation** — all queries filter by `unit_id` for non-admin users

### 7.2 Network Security

- Backend and MySQL bind to `127.0.0.1` only — not accessible from network
- Only Nginx (:80/:443) exposed to KSWAN
- UFW firewall blocks all non-whitelisted ports
- SSH key-based auth, root login disabled

### 7.3 Data Security

- Passwords never stored in plaintext (bcrypt)
- JWT secret stored in `.env` file (chmod 600)
- MySQL dedicated user with minimal privileges
- CORS restricted to server IP only
- SQL injection prevented by SQLAlchemy parameterized queries
- XSS prevented by React's default escaping

---

## 8. Concurrency & Performance

### 8.1 Capacity Planning

| Metric | Value |
|--------|-------|
| Total CCPS stations | 44 |
| Users per station | 2 (admin + user) |
| Total users | 88 |
| Max concurrent users | ~30-50 (estimated peak) |
| Requests per user | ~5-10/min during active data entry |
| Peak requests/sec | ~8-10 |

### 8.2 Why Single VM Works

- **Async FastAPI** — non-blocking I/O handles concurrent requests efficiently
- **4 Gunicorn workers** — 4 parallel Python processes, each handles multiple async requests
- **MySQL connection pool** — SQLAlchemy manages connections, prevents exhaustion
- **Static file serving** — Nginx serves React SPA directly, no backend load
- **Low compute** — CRUD operations only, no AI/ML, no file processing on server

### 8.3 Performance Bottlenecks & Mitigations

| Bottleneck | Mitigation |
|-----------|-----------|
| Concurrent logins at shift change | bcrypt is CPU-heavy; 4 workers handle 4 parallel logins |
| Large Excel upload | Async processing, openpyxl is fast (~1s per file) |
| MySQL slow queries | Indexes on fir_no, acknowledgement_no, unit_id |
| Memory pressure | max_requests=1000 recycles workers to prevent leaks |

---

## 9. Data Flow — Excel Upload

```
User selects 1-65 Excel files
         │
         ▼
POST /api/v1/mule-reports/upload-excel
  (multipart/form-data, files[])
         │
         ▼
For each file:
  ├── Read bytes into memory
  ├── openpyxl.load_workbook(BytesIO)
  ├── Extract acknowledgement_no from Row 2, Col B
  ├── Check duplicate (SELECT by ack_no)
  │     ├── Exists → skip, return error
  │     └── New → continue
  ├── Create MuleReport (status=submitted)
  ├── Parse 6 sheets:
  │     ├── "Money Transfer to" → money_transfers table
  │     ├── "Other" → other_transactions table
  │     ├── "Transaction put on hold" → transactions_on_hold table
  │     ├── "Others Less Then 500" → others_less_than_500 table
  │     ├── "AEPS" → aeps_transactions table
  │     └── "Withdrawal through ATM" → atm_withdrawals table
  └── Commit transaction
         │
         ▼
Return per-file results:
  { filename, ok, report_id, acknowledgement_no, total_transactions }
```

---

## 10. Frontend Architecture

### 10.1 Component Hierarchy

```
App
├── LoginPage
│     └── LoginForm (district → CCPS → user/pass)
│
├── AppShell (authenticated wrapper)
│     ├── Sidebar (navigation)
│     └── <Outlet> (page content)
│           ├── CaseEntryPage (7 tabs)
│           ├── CaseUpdatePage (search → edit)
│           ├── PetitionEntryPage (4 tabs)
│           ├── PetitionUpdatePage (search → edit)
│           ├── MuleReportEntryPage (upload + 6 tabs)
│           ├── MuleUpdatePage (search → edit)
│           └── DashboardPage (admin stats)
│
└── ProtectedRoute (auth guard + role check)
```

### 10.2 State Management

- **Auth state** — Zustand store in `localStorage` (token, user info)
- **Form state** — React `useState` per page (no global state for forms)
- **Draft persistence** — saved to backend via API (status=draft), not localStorage

### 10.3 Navigation Structure

```
Sidebar:
  DAILY STATUS REPORT (bold header)
    ├── New Case
    ├── Update Case
    ├── New Petition
    └── Update Petition

  MULE ACCOUNTS DATA (bold header)
    ├── New Report (includes Upload option)
    └── Update Report

  DASHBOARD (admin only)

  [Sign Out]
```

---

## 11. Deployment Architecture

### 11.1 Single VM Layout

```
/opt/cyberfraud/
├── backend/
│     ├── .env (chmod 600)
│     ├── main.py
│     ├── api/
│     ├── models/
│     ├── schemas/
│     ├── auth/
│     ├── venv/
│     ├── gunicorn.conf.py
│     └── uploads/photos/
├── frontend/  (built dist/)
│     ├── index.html
│     ├── assets/
│     └── ...
├── backups/
│     └── db/
└── All District CEN_PS.xlsx
```

### 11.2 Service Dependencies

```
systemd boot
  │
  ├── mysql.service (starts first)
  │
  ├── cyberfraud-backend.service (after mysql)
  │     └── Gunicorn → Uvicorn workers → FastAPI
  │
  └── nginx.service (after network)
        └── Reverse proxy → backend + static files
```

### 11.3 Backup & Recovery

| What | How | Frequency | Retention |
|------|-----|-----------|-----------|
| MySQL database | mysqldump + gzip | Daily at 2 AM | 30 days |
| Uploaded photos | rsync to backup dir | Daily at 3 AM | 90 days |
| Application code | Git repo | On deployment | Version controlled |
| .env secrets | Encrypted backup | Weekly | Secure storage |

---

## 12. Future Enhancements

| Enhancement | Priority | Effort |
|------------|----------|--------|
| Password reset by admin | High | Small |
| Audit log (who changed what) | High | Medium |
| Rate limiting on login | High | Small |
| Role-based field visibility | Medium | Medium |
| Report generation (PDF export) | Medium | Medium |
| Bulk password change tool | Medium | Small |
| Dashboard charts (crime trends) | Low | Medium |
| Mobile-responsive UI | Low | Medium |
| Multi-language support (Kannada) | Low | Large |

---

*Architecture Document — CyberFraud Data Entry System v2.0*
*Karnataka State Police — SCRB / CID Cyber Crime Division*
