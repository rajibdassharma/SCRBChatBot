# Product Specification — Cyber Fraud Data Entry

## Purpose

A centralized data entry and reporting platform for Karnataka State Police
cyber fraud investigation units. Replaces manual Excel-based tracking with a
structured web application that enforces data consistency, enables cross-unit
visibility for administrators, and streamlines daily reporting.

---

## Users & Roles

### Admin
- Sees data across all units
- Accesses the KPI dashboard with aggregate statistics
- Manages users and units
- Can view all cases, mule reports, DSR entries, and mule entries

### Unit User
- Belongs to a specific organizational unit (e.g., CEN Bangalore, CEN Mysore)
- Can only see and modify their own unit's data
- Enters cases, arrests, petitions, lien accounts, refunds
- Enters mule reports with bank transaction details
- Submits daily DSR and mule intelligence entries
- Optionally associated with a police station (for petition routing)

---

## Feature Areas

### 1. Case Management

**What it tracks:** Cyber fraud cases — FIR registrations, NCRP complaints, and petitions.

**Case types:** NCRP, Walk-In, Petition
**Crime types:** Internet, Digital, Crypto

**Case entry includes:**
- FIR number (unique per unit), petition number, registration date
- Case type and crime type classification
- Facts/description of the case
- Status: draft → submitted

**Nested data per case:**

| Section | Purpose | Key Fields |
|---------|---------|------------|
| **Arrests** | Persons arrested | Name, address, email, Aadhar, PAN, date of arrest, statement |
| **Accomplices** | Per arrest | Where met, where stayed, interrogation details |
| **Accused Details** | Per arrest | Photo, email, mobile, occupation, remarks |
| **Petitions** | Legal petitions | Petition number, FIR registered status, nature, type (amount_lost/fraud_case), amount |
| **Lien Accounts** | Frozen bank accounts | Account number, amount lien marked, layer, total balance, bank name |
| **Unfreeze Details** | Account unfreezes | Type (letter/court_order), crime number, bank, account, amount |
| **Refunds** | Victim refunds | Refunded (yes/no), victim name, amount, crime/petition number |

**Search:** By FIR number or petition number.

### 2. Mule Report Management

**What it tracks:** Mule account investigations — accounts used by fraudsters to route stolen money.

**Mule report entry includes:**
- Acknowledgement number (from bank, unique)
- FIR number (unique)
- Status: draft → submitted

**Six transaction tables per report:**

| Table | Purpose | Key Fields |
|-------|---------|------------|
| **Money Transfers** | Bank-to-bank transfers | Account, transaction ID, bank, layer, destination account, IFSC, amounts, bank action |
| **Other Transactions** | Non-transfer transactions | Account, transaction ID, amount, bank action |
| **Transactions on Hold** | Held/blocked transactions | Account, hold date, hold amount, layer, bank action |
| **Others < 500** | Small transactions (< Rs 500) | Account, transaction ID, reference, bank action |
| **AEPS Transactions** | Aadhaar-enabled withdrawals | Account, withdrawal date/amount, layer, bank action |
| **ATM Withdrawals** | ATM cash withdrawals | Account, datetime, amount, disputed amount, ATM ID/location, bank action |

**Excel upload:** Bank-provided Excel files can be uploaded and auto-parsed into the appropriate transaction tables. Preview before saving is supported.

**Search:** By acknowledgement number.

### 3. Daily Status Report (DSR)

**What it tracks:** Daily aggregate statistics per unit.

**One entry per unit per date** (upsert pattern).

**Fields:**

| Category | Fields |
|----------|--------|
| **Activity** | Cases count, petitions count, arrests count, case type (FIR/NCRP) |
| **Financial** | Cumulative amount lien marked, cumulative accounts lien marked, accounts defreezed, amount refunded to victim |
| **Pending Cases** | UI cases pending by year (2021-2026) |
| **Disposal** | Detected/chargesheeted, transferred, false, undetected |
| **Trial** | Convicted, discharged, acquitted, abated, compounded, under trial |

**History:** View past DSR entries for the unit (up to 365 days).

### 4. Mule Intelligence Entry

**What it tracks:** Daily mule account intelligence summaries per unit.

**One entry per unit per date** (upsert pattern).

**Fields (all free-text):**
- Accounts with most liens
- Recruiters for lien accounts
- Accounts with max money routed
- Accounts with max transactions
- Recency of ATM transactions
- Cash withdrawals (mule-wise)
- ATM geo identification
- ATM table by transactions
- Cheque withdrawal branches
- Money left system stats
- Crypto mule accounts

**History:** View past mule entries for the unit.

### 5. Admin Dashboard

**Admin-only view** with aggregate KPIs:

| KPI | Description |
|-----|-------------|
| Total Cases | Count of all cases across units |
| Total Arrests | Count of all arrests |
| Total Lien Amount | Sum of all lien account amounts |
| Total Refunded | Sum of all victim refunds |
| Units Submitted | Count of units that have submitted data |
| Units Total | Total number of active units |

**Unit comparison chart:** Bar/table showing per-unit breakdown of cases, arrests, and lien amounts.

### 6. Photo Upload

- Upload accused person photos as part of accused details
- Stored on server filesystem
- Path recorded in `accused_details.photo_path`

---

## Data Entry Workflows

### Case Entry Flow

```
1. User selects "New Case" from sidebar
2. Fills case header (FIR no, type, crime type, facts)
3. Adds arrests (click "Add Arrest" → fill name, address, Aadhar, PAN)
   3a. For each arrest, optionally add accomplices and accused details
4. Adds petitions (petition number, type, amount)
5. Adds lien accounts (account no, amount, bank, layer)
6. Adds unfreeze details (type, bank, amount)
7. Adds refunds (victim name, amount, status)
8. Saves as draft or submits
```

### Case Update Flow

```
1. User navigates to "Update Case"
2. Searches by FIR number or petition number
3. System loads existing case with all nested data
4. User modifies fields, adds/removes nested records
5. Saves changes
```

### Mule Report Flow

```
1. User selects "New Mule Report"
2. Enters acknowledgement number and FIR number
3. Adds transactions manually OR uploads Excel file
   3a. Excel upload: select file → preview parsed data → confirm save
4. Reviews all transaction tables
5. Saves as draft or submits
```

### DSR Entry Flow

```
1. User selects "DSR Entry"
2. Date defaults to today (can be changed)
3. Fills all numeric fields (cases, arrests, amounts, disposals, trial stats)
4. Submits — upserts based on (unit_id, report_date)
5. Can view history of past submissions
```

---

## Business Rules

1. **FIR uniqueness:** Each FIR number must be unique within a unit
2. **Date uniqueness:** Only one DSR entry and one mule entry per unit per date
3. **Cascade deletes:** Deleting a case removes all related arrests, petitions, lien accounts, etc.
4. **Unit isolation:** Unit users cannot see or modify other units' data
5. **Draft/submit:** Cases and mule reports support draft status before final submission
6. **Acknowledgement number:** Each mule report must have a unique bank acknowledgement number
7. **Layer tracking:** Lien accounts and some transactions track "layer" (depth in money trail)

---

## Non-Functional Requirements

- **Offline-ready:** No external API dependencies (all data in local MySQL)
- **Multi-user:** Concurrent access from multiple units
- **Responsive:** Works on desktop browsers (primary) and tablets
- **Performance:** Pagination on list views (limit/offset, default 50)
- **Security:** JWT auth, bcrypt passwords, role-based access control
- **Deployment:** Single VM with Nginx + Gunicorn + MySQL
