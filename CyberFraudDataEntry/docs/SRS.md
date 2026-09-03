# Software Requirements Specification — Cyber Fraud Data Entry

**Client:** Karnataka State Police — SCRB / CID Cyber Crime Division
**Scale:** 44 Cyber Crime Police Stations across 36 districts
**Users:** ~90 (2–3 per station: unit_user + admin, plus a small number of super_admins at SCRB HQ)
**Deployment:** Ubuntu VM on internal government network (KSWAN); single-tenant, on-premise.

---

## 1. Overview

A centralised web application that replaces the paper-and-Excel workflow every Cyber Crime PS in Karnataka uses today for cyber-fraud casework. Operators log FIRs, arrests, petitions, mule accounts, bank transactions, and daily portal counters directly into the system. SCRB HQ gets a live, cross-state dashboard instead of collating 44 spreadsheets by email.

The app is organised around **five modules**, mirrored in the landing-page tile grid and the sidebar:

| Module | What it holds |
|---|---|
| **Cases & Petitions** | Full FIR records with arrests, petitions, lien accounts, unfreeze details, refunds, victim details |
| **NCRP Data** | Mule-account investigation reports; six categories of bank transactions per report; bulk Excel upload |
| **All Accounts** | Master register of every account (victim / mule / non-mule) the PS has touched, with mule-herder linkage |
| **DSR** | Daily reporting — the "New FIR" lightweight entry, per-FIR investigation activity log, and 8-portal daily counters |
| **Admin** | User management, natural-language "Ask the Data" chat |

A sixth surface — **Upload Analysis** — sits inside the All Accounts dashboard rather than on the tile grid. It is super_admin-only, and its figures are not typed by anyone: they are derived from the ID photos and bank statements already attached to All Accounts rows (§3.5).

Everything is scoped to `(unit_id, ps_id)` at the DB level so an operator in Bagalkot never sees Bengaluru City's data.

---

## 2. Users & Roles

Three roles. Every route enforces this at the FastAPI dependency layer, and every query filters by the caller's scope.

### unit_user
The default operator — one of 2 users per PS.
- Can create / edit / view only records they personally submitted, within their own `(unit_id, ps_id)`
- Cannot see other operators' work even at the same PS
- Cannot see dashboards, reports, or user management

### admin
Station-level admin — one per PS, sees everything the PS produces.
- Can create / edit / view all records at their `(unit_id, ps_id)`, including other operators' entries
- Can access their PS's dashboards
- Can download PDF / Excel reports scoped to their PS
- Can create + manage unit_user accounts at their PS
- Cannot see other PSes

### super_admin
Senior Officer at SCRB HQ — cross-PS oversight.
- Full read + write access across every active PS in the state
- Dashboards show all 44 PSes; reports include the full roster
- Can create + manage users at any PS
- Only role that can use the "Ask the Data" chat feature
- Only role that can see the Upload Analysis tabs (§3.5) — they aggregate across every PS, so there is no meaningful PS-scoped version of them

---

## 3. Functional Requirements by Module

### 3.1 Cases & Petitions

The heart of the app. One FIR / NCRP / Walk-In / Petition = one case row with a rich set of nested children.

**As a unit_user, I want to log a new FIR case** so my PS's activity is captured in a searchable digital record instead of a paper file.
- FIR No follows the format `NNNN/YYYY` (client + server validated via a shared regex util)
- Case types: NCRP, Walk-In, Petition. Petitions can have no FIR (petition_no carries identity instead)
- Crime type: pick from a 31-entry KSP Cyber Crime classification list; "Others" reveals a free-text field
- Sections: free-text list of BNS / BNSS / IT-Act sections (e.g. "318(4), 319, 340")
- Nature: Financial or Non-Financial. Non-Financial hides the lien/unfreeze/refund tabs and the victim banking block
- Every case is scoped to the operator's `(unit_id, ps_id)` — no cross-PS visibility
- FIR No is UNIQUE per `(unit_id, ps_id)`; server returns 409 with a clear message on collision

**As an operator, I want to save partial work as a draft** so I don't lose data when I get interrupted.
- Cases have `status = draft | submitted`
- Draft saves skip required-field enforcement so partial data is accepted
- Only `status = submitted` triggers the full validation (FIR No, registration_date, victim mandatory fields)

**As a unit_user, I want to capture full victim details** including primary bank account plus any *additional* accounts the money moved from.
- Primary bank account fields on the Victim row (bank_account_no, bank_name, bank_branch_address)
- "Additional Victim Accounts" section on DSR → New FIR captures extra accounts the victim used (bank, branch, IFSC, state, district, amount transferred). Karnataka district field enabled only when state=Karnataka
- Address is structured (house_no, street_name, city, state, country, pincode) not free-text
- Phone (10 digits), pincode (6 digits), bank account (9–18 digits) validated by shared regex

**As a unit_user, I want to record every arrest** with the accused's contact + accomplice info.
- Arrests: name, address, email, Aadhar, PAN, date of arrest, statement (up to 5000 chars)
- Nested Accomplices per arrest: where met / where stayed / interrogation details
- Nested Accused Details per arrest: photo upload, email, mobile, occupation, remarks
- Duplicate detection: same name (case-insensitive, whitespace-collapsed) or same Aadhar within one case is rejected with a 422 pointing at the offending row

**As a unit_user, I want to log petitions** filed at the PS separately from FIRs.
- Petition fields: petition_no, fir_registered (yes / no / transferred), why_not, nature, petition_type (amount_lost / fraud_case), amount
- Petition-type cases can save with petition_no only (no FIR)

**As a unit_user, I want to record accounts we've frozen / lien-marked** and the accused accounts money was transferred to.
- Lien Accounts (per case): account_no, amount_lien_marked, layer, total_amount_in_account, bank_name — tracks the freeze lifecycle
- Accused Accounts (per case, DSR → New FIR only): account_holder_name, bank, branch, branch_address, state, district (KA-only dropdown), IFSC, amount_transferred — tracks where the money went. Independent of Lien Accounts

**As a unit_user, I want to record account defreezes / unlien** actions and victim refunds.
- Unfreeze Details: type (letter / court_order), crime_no (mirrors FIR No), bank, account, amount
- Refunds: refunded (yes / no), victim_name, amount, crime_no_or_petition_no

**As an admin or super_admin, I want to declare NIL activity** for my PS on days with no cases so my station doesn't look silent by mistake.
- Mark NIL Today button in the sidebar of the Cases module
- One NIL per (PS, date); triggers a green "NIL declared" pill on the dashboard

**As any operator, I want to search a case by FIR or petition number** so I can find and update it.
- Search by FIR No or Petition No, scoped to the caller's role
- Super_admin search returns cross-PS matches with district + PS metadata for disambiguation

**As any operator, I want to update an existing case** — the FIR No is immutable after create.
- All child collections (arrests, petitions, liens, etc.) support add / remove / edit on update
- FIR No cannot be changed after create (silently ignored if sent)
- On update, unlisted-in-payload child arrays (victim_accounts, accused_accounts) are preserved unchanged so the shallower Update Case page doesn't wipe rows added on DSR → New FIR

**As an operator, I want to download the full case file as a PDF** for legal / offline reference.
- Report includes header + arrests (with accomplices / accused details) + petitions + lien accounts + unfreezes + refunds + victim block
- Access: super_admin any case; admin / unit_user only cases from their own PS

**As an admin, I want a Cases & Petitions Dashboard** showing my PS's totals + trends.
- KPIs: Total Cases, Total Arrests, Amount Lien Marked, Accounts Lien Marked, Accounts De-Freezed
- Tabs: Overview, Investigation, Disposal & Trial (using DSR entries)
- All amounts render inside cards without overflowing (tabular-nums, breaking allowed)

### 3.2 NCRP Data (Mule Reports)

Bank-provided data about the mule accounts fraudsters used to route stolen money.

**As a unit_user, I want to log a mule investigation report** with all six categories of bank transactions.
- Report has acknowledgement_no (from the bank, UNIQUE across the system) and fir_no (UNIQUE)
- Six transaction tables per report:
  - Money Transfers: bank-to-bank transfers with layer, IFSC, dest account, dispute amount, bank action
  - Other Transactions: non-transfer txns with amount + bank action
  - Transactions on Hold: held/blocked amounts with hold date + layer
  - Others < 500: small transactions with reference + bank action
  - AEPS Transactions: Aadhar-enabled withdrawals with withdrawal date + amount + layer
  - ATM Withdrawals: ATM cash pulls with datetime, ATM ID, location, disputed amount

**As a unit_user, I want to upload the bank's Excel file directly** instead of typing every row.
- Upload multiple files at once via /mule/upload
- Preview parsed data before saving (parse-only endpoint)
- Auto-map sheet names to transaction tables; skip empty rows
- Extract acknowledgement_no from the first data row

**As a unit_user, I want to search by acknowledgement number** to find a report to update.

**As any operator with mule access, I want to download a mule report as a landscape PDF** covering all six transaction tables.

### 3.3 All Accounts

Master register of every bank account the PS has ever recorded, tagged as Victim / Mule / Non-Mule.

**As a unit_user, I want to log any account we've encountered** with full KYC + bank routing info.
- Fields: serial_no (auto per PS), account_no, bank_name, branch_name, branch_district, branch_state, layer, IFSC, account_holder_name, KYC address, KYC mobile
- Optional file uploads: id_photo_path, account_statement_path
- Account type: Victim / Mule / Non-Mule
- Mule accounts can have multiple mule-herder rows attached (name, address, mobile)
- Optional linkage: fir_no OR ncrp_ack_no

**As a unit_user, I want to search by serial no / account no / holder name** to update a record.

**As an admin, I want an Account Details Dashboard** to see the account-portfolio shape of my PS.
- KPIs: Total Accounts, Victim / Mule / Non-Mule split, Unique Banks, Unique Mule Herders, Accounts with photo
- Per-PS comparison table with Yesterday column (new accounts on today−1)
- Top 10 banks by account count (stacked bars by account type)
- Top 10 PSes by account count
- Account Type Distribution donut (Victim red / Mule dark-red / Non-Mule blue)
- Daily-growth line chart from 20 July 2026 to yesterday
- Downloadable per-PS comparison as PDF or Excel

### 3.4 DSR (Daily Status Report)

Daily reporting module — three separate entry surfaces (New FIR, Investigation, Portals) plus three dashboards and two daily reports.

**As a unit_user, I want a lightweight "New FIR" entry point** to log an FIR the moment it's registered, without filling every child field.
- Same shape as Cases → New Case but only Case Details + Victim Details + Facts + the two multi-account sections
- Arrests, petitions, lien accounts etc. are added later via Cases → Update Case
- Additional Victim Accounts + Accused Accounts sections are only editable on this page (pass-through on Update Case)

**As a unit_user, I want to log per-FIR investigation activity daily** — notices sent, lien / unlien requests, amounts, arrests, statements, final report.
- Daily Work Done entry: one row per (PS, FIR, date), upsert
- Three-band form matching the paper sheet: Red (notices), Yellow (lien / unlien), Green (outcomes)
- Notices 91/92/94 broken out by recipient (Banks / Intermediary / Account Holder / CDR-IPDR)
- Final Report is A (chargesheeted) / B (false) / C (undetected), nullable until close

**As a unit_user, I want to enter daily counters for each of 8 external portals** the PS interacts with.
- Portals: NCRP, Samanvaya, Sahayog, GRM, MRM, Bharatpol, OCWC, NCMEC Tipline
- 25 metric fields grouped by portal (matches the paper form)
- Multiple entries per (PS, date) legal — shift-based batches; dashboards SUM across all rows
- Draft / submitted status; dashboards exclude drafts

**As an admin, I want an FIR Dashboard** showing FIRs registered per PS over a date window.
- Table: District, Police Station, Yesterday (today−1 count), Total FIRs in window
- Sortable columns; scoped to admin's PS
- Downloadable PDF / Excel

**As an admin, I want a Portals DSR Dashboard** showing per-PS portal counter aggregations.
- KPIs: Submitted Entries, PSes Reporting, Total Counters Logged
- Per-PS comparison table with Yesterday column (today−1 submissions)
- Top 10 PSes chart

**As an admin, I want a Daily Work Done Dashboard** showing per-PS activity across the date range.
- KPIs across notices, lien, arrests, statements
- Final Report split by A/B/C
- Daily-activity line chart

**As an admin, I want a Portals DSR Report for a single date** in the exact paper-form layout, downloadable as PDF or Excel with an on-screen preview first.
- 45 PS rows × 25 metric columns grouped under the 8 portal headers
- All 45 PSes always shown (blank cells for non-submitters — silence stays visible)
- Landscape A4 PDF (fits without overflow); Excel with frozen header + first two columns
- Grand-total row at the bottom
- Defaults to yesterday's date; date is selectable
- Preview table auto-loads on date change

**As an admin, I want a Daily Work Done Report for a single date** — per-PS totals across every FIR that PS worked on.
- Per-PS aggregation: FIR Count column (replaces per-FIR "FIR No"), numeric fields SUMMED, Final Report shown as "A:n, B:m, C:k"
- Three colour bands (red / yellow / green) match the paper sheet
- All 45 PSes always shown; grand-total row at the bottom
- Landscape A4 PDF fits without overflow; downloadable as Excel
- Defaults to yesterday

### 3.5 Upload Analysis (super_admin only)

Eight dashboard tabs that mine the files operators have ALREADY uploaded — ID photos and bank statements attached to All Accounts rows — for patterns no single operator can see. Nothing here is entered by hand. Every figure is derived by a nightly batch job on the server and is rebuildable from the files alone.

**As a super_admin, I want to find one person operating accounts under different names** so I can charge the herder rather than 30 individual mules.
- Duplicate IDs: SHA-256 for byte-identical photos, plus a 24×24 perceptual hash for re-scans / re-compressions / crops
- Groups are shown with every account, PS and FIR the photo appears under; cross-PS groups are what matter
- A near-duplicate is any pair within a fixed Hamming distance — deliberately not "similar-looking", which is unfalsifiable in court

**As a super_admin, I want to see how much money actually moved through the mule accounts of an FIR**, not how much was claimed.
- Money Trail: per-FIR debit / credit / balance rollups from parsed statements
- **Only balance-chain-verified rows are summed.** Every row is checked against `previous − debit + credit = balance`; a row that fails, or that arrives without enough context to check, is reported separately and never added to a headline figure
- Untested and rejected money are shown as their own columns — visible, but never mixed into the verified total

**As a super_admin, I want to know which accounts have no statement yet** so I can chase the bank instead of assuming the data is complete.
- Coverage: per-PS and per-FIR counts of accounts with / without a parsed statement, and files that parsed to zero rows with the reason

**As a super_admin, I want to see mule-to-mule transfers as a network** so layering structure is visible instead of inferred.
- Mule Network: nodes are mule accounts, edges are direct transfers found by matching counterparty numbers in statement narrations
- Layer colour code — Layer 1 red, 2 blue, 3 black, 4 yellow; a halo marks an account appearing in more than one FIR
- Hovering an edge shows the amount transferred; node size is constant under zoom
- All Mule Accounts view: every mule account in the state with an All States / Karnataka / Rest of India filter, paginated, downloadable as PDF or Excel

**As a super_admin, I want to see where stolen money left the banking system for crypto.**
- Crypto Analysis: statement rows whose narration names a crypto exchange or asset, grouped by exchange and by asset
- Off-ramp direction is classified per counterparty (money out / money in / both) — a payout is not a purchase
- Evidence view: the underlying narrations, paginated, so every aggregate can be traced to the statement line it came from

**As a super_admin, I want an account that appears in several FIRs surfaced automatically.**
- Repeat Accounts: accounts recorded by more than one PS or against more than one FIR, paginated server-side
- Deep Analysis / Graphical Analysis: per-FIR account tables and the same relationships drawn as a graph

**Non-functional expectations for this module:**
- **No dashboard query AGGREGATES over the 26 M-row fact table.** Every screen reads pre-computed summary tables (~150 MB), so page load stays flat as the statement corpus grows. The single exception is the FIR trace, which does a bounded indexed lookup on one FIR's accounts to report named recipients with no account number — 61 ms measured, and its cost does not grow with the corpus
- Analysis runs nightly on the server (23:00 IST), before the backup, so each night's backup contains that night's analysis
- Figures are as of the last nightly run, not live — the tabs are investigative, not transactional
- Derived tables are rebuildable end-to-end from `backend/uploads/`; losing them costs time, not evidence

### 3.6 Admin

**As a station admin, I want to create + manage unit_user accounts at my PS.**
- Create user: system generates a random secure password + emails/prints it once
- Can toggle is_active (soft delete)
- Reset password: generates a new random one
- Cannot see users at other PSes
- Super_admin can manage users at any PS

**As a super_admin, I want a natural-language chat interface** so I can ask questions like "how many mule accounts in Bengaluru last week?" without writing SQL.
- Gated by a server-side feature flag (chat can be disabled)
- Question is translated to SQL by an LLM using a curated schema description
- Answer includes the SQL query for transparency, up to 3 follow-up suggestions, and the returned rows
- Every question + answer stored in `chat_messages` for audit
- Restricted to super_admin only

**As a new user (first login), I must change my password** before I can use the app.
- Server sets `must_change_password = true` on password creation / reset
- All routes except `/auth/change-password` return 403 until the flag is cleared

---

## 4. Cross-Cutting Requirements

### Security
- JWT authentication (HS256, 8-hour expiry). Server refuses to start if `JWT_SECRET` is missing / default / < 32 chars
- Bcrypt password hashing
- Every route enforces per-record `(unit_id, ps_id)` scoping — cross-PS access blocked at the dependency layer
- Free-text fields sanitised for HTML/script via `strip_html` on write
- File uploads restricted to configured MIME types; stored outside the web root
- Token revocation list (logout invalidates the token server-side)
- Passed VAPT v1.0.1 (Innspark, 2026-05-10) — all 10 findings closed; all future schema changes go via numbered migrations (no more `reset_db.py`)

### Data Integrity
- Every child table CASCADE-deletes with its parent
- UNIQUE constraints where identity matters: `(unit_id, ps_id, fir_no)` on cases, `acknowledgement_no` + `fir_no` on mule_reports, `(unit_id, ps_id, report_date)` on DSR entries, `(unit_id, ps_id, fir_no, report_date)` on daily work entries
- FIR No `NNNN/YYYY` format enforced on write via shared client + server validator
- Every operator-created row carries `submitted_by` for audit
- All schema changes via numbered idempotent migrations in `backend/migrations/`

### Reporting
- Every dashboard has downloadable PDF + Excel exports
- PDF renderers use ReportLab; Excel uses openpyxl
- Reports render on A4 landscape (paper is standard printer paper — no A3 dependency)
- Per-day reports default to yesterday; date is always selectable

### Performance
- Async SQLAlchemy 2.0 + asyncmy driver; every DB session is async
- Eager loading (`selectinload`) on parent-with-children reads — no N+1
- List views paginate at 50 default, max 500
- Analysis dashboards read pre-aggregated summary tables, never the 26 M-row fact table; the batch job that fills them runs off-peak under `Nice=10` so it cannot outrank the web app for CPU

### Reliability
- Systemd manages the backend (`cyberfraud-backend.service`) and the nightly chain (`cyberfraud-nightly.timer`)
- One nightly unit at 23:00 IST runs the upload analysis and THEN the backup, so each backup contains the analysis of the same night. Ordering by dependency rather than by clock is deliberate — two independent timers made every backup carry the previous day's analysis
- Nightly `mysqldump`, excluding only the rebuildable 27 GB fact table; uploads archived as a weekly full + nightly incremental (`tar --listed-incremental`)
- Derived analysis tables are recoverable without a backup by re-running the analysis over `backend/uploads/`; operator-entered data is not, and is never excluded from the dump
- All 44 PSes concurrent-access tested during VAPT

### Compliance
- KSP internal use only; hosted on KSWAN
- No external network calls except the LLM API (chat feature) — and that requires super_admin
- Self-signed HTTPS acceptable on internal network

---

## 5. Constraints & Assumptions

- **Single-tenant, on-premise** — one Ubuntu VM at SCRB HQ (2 vCPU / 16 GB / 300 GB), no multi-tenancy. Storage is the constraint that will bind first: the uploads corpus and the derived fact table both grow with every statement received
- **MySQL 8+** — required for `REGEXP_REPLACE` (migration 018) and other SQL-8 features
- **Offline-tolerant** — the app runs entirely on KSWAN; only the optional chat feature reaches outside
- **Fixed roster** — 44 PSes, 36 districts, ~90 users. Adding a district is a manual DB update (seed table)
- **Paper compatibility** — every report format must match the paper submission form; operators do side-by-side reconciliation
- **Browser support** — modern evergreen browsers only (Chrome, Edge). No IE.

---

## 6. External Interfaces

- **REST API** at `/api/v1/*` — JSON in, JSON or file (PDF / XLSX) out. See [Architecture.md](./Architecture.md) for the route map.
- **MySQL** — every operator query and admin dashboard runs against `cyber_fraud_dsr` on localhost:3306.
- **File storage** — accused photos + account statements under `backend/uploads/`. Also the INPUT to the upload-analysis module (§3.5) and therefore the one artefact that must survive: every derived table can be rebuilt from it, and nothing can rebuild it.
- **LLM API** (optional, super_admin chat only) — external HTTP call from the backend; disabled by default via feature flag.

---

_Living document — updated as features ship. See git log for change history._
