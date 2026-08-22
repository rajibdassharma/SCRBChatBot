# Database Design Conventions — CyberFraud Data Entry

Source of truth for **how to write schema-changing code** that won't break
on deploy. [Architecture.md](./Architecture.md) describes the logical
schema; this file describes the physical constraints that the LLM / a
human refactor will trip over if they ignore them.

> **TL;DR for migration authors:** new tables/columns that reference an
> existing column **must match its `CHARSET`, `COLLATE`, and exact type**.
> If you're adding an FK, copy the referenced column's full definition
> verbatim. Anything else risks MySQL error 3780.

---

## 1. Production database parameters

These are the values to match when adding new tables or columns. Verified
on `cyber_fraud_dsr` at 2026-06-20:

| Property | Value |
|---|---|
| Server | MySQL 8 (Ubuntu 24.04) |
| Database | `cyber_fraud_dsr` |
| Default charset | `utf8mb4` |
| Default collation | `utf8mb4_unicode_ci` |
| Engine | `InnoDB` |

**Verify on any environment with:**

```sql
SELECT default_character_set_name, default_collation_name
FROM information_schema.schemata
WHERE schema_name = 'cyber_fraud_dsr';

SHOW CREATE TABLE cases\G   -- the canonical reference table
```

Local dev MySQL **may differ** (MySQL 8 defaults to `utf8mb4_0900_ai_ci`
for fresh databases). Migrations must be explicit, not rely on env
defaults.

---

## 2. ID column convention — VARCHAR(36) UUIDs

Adopted in **VAPT v1.0.1 item 8 recommendation #2** (2026-05-10) for
parent records. Mixed legacy and new pattern is in play, so the rule is:

| Table category | ID type | Rationale |
|---|---|---|
| Parent records (`cases`, `arrests`, `victims`, `lien_accounts`, `petitions`, `refunds`, `unfreeze_details`, `mule_reports`, all mule-report transaction tables) | `VARCHAR(36)` UUIDv4 | VAPT — prevents enumeration / IDOR |
| Lookup tables (`units`, `police_stations`) | `INT AUTO_INCREMENT` | Stable, never enumerated by clients |
| Auth (`users`, `revoked_tokens`) | `INT AUTO_INCREMENT` | Legacy; not exposed to client |
| Reference fields to lookups (e.g. `unit_id`, `ps_id`, `submitted_by`) | `INT` | Match the lookup PK |

Source of truth for any specific table = the SQLAlchemy model in
`backend/models/*.py`.

---

## 3. The 2026-06-20 incident — FK collation mismatch

What broke migration 003 on production:

```sql
CREATE TABLE victims (
    case_id VARCHAR(36) NOT NULL,
    ...
    FOREIGN KEY (case_id) REFERENCES cases(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Failed with `MySQL 3780 "Referencing column 'case_id' and referenced
column 'id' in foreign key constraint 'fk_victims_case_id' are
incompatible"`.

**Root cause:** the table declared `CHARSET=utf8mb4` but no `COLLATE`.
MySQL then defaulted to `utf8mb4_0900_ai_ci`. Production's `cases.id` was
created with `utf8mb4_unicode_ci`. FK requires both to match exactly,
including collation.

**Fix:** explicitly declare both:

```sql
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

## 4. Rules for writing schema migrations

### 4.1 New tables — always declare both charset and collation

```sql
CREATE TABLE foo (
    id VARCHAR(36) NOT NULL,
    ...
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 4.2 New columns on existing tables — let the table default win

`ALTER TABLE ... ADD COLUMN` inherits the table's CHARSET/COLLATE; do
NOT specify them explicitly on the column. The column will automatically
match its siblings (and any FK source).

### 4.3 New foreign keys — sanity check before writing the SQL

Before you write `FOREIGN KEY (x) REFERENCES y(z)`, run:

```sql
SELECT column_name, column_type, character_set_name, collation_name
FROM information_schema.columns
WHERE table_schema = 'cyber_fraud_dsr'
  AND table_name = '<target_table>'
  AND column_name = '<target_column>';
```

…and copy `column_type` + the character set + the collation onto the
referencing column. The combination must match.

### 4.4 Migrations must be idempotent

Every migration must check `INFORMATION_SCHEMA` for tables / columns /
indexes / constraints before creating them. Re-use the helper functions
established in `migrations/001_*.py` through `migrations/004_*.py`
(`_table_exists`, `_column_exists`, `_index_exists`, `_fk_exists`). Data
migrations (018) use `WHERE ... REGEXP '\\bCEN\\b'` guards so re-runs
touch 0 rows.

### 4.5 Migrations must be additive and reversible in principle

Post-VAPT the app is production — **additive changes only**. No `DROP
TABLE`, no `DROP COLUMN`, no destructive `UPDATE` without a WHERE guard
that can be re-run safely. The nightly `deploy/backup-db.sh` mysqldump
is the rollback path (kept as the newest snapshot on the server);
`update.sh` itself no longer takes a pre-migration backup (the nightly
timer covers it, and the pre-migration step was removed after adding
too much friction to routine deploys).

### 4.6 Every schema change must be self-verified in update.sh

For each new migration, add TWO lines to `deploy/update.sh`:
1. The migration invocation in step 3 (in numeric order)
2. A self-verify block in step 8 that asserts the change actually
   landed — an `INFORMATION_SCHEMA` query that returns 1 for a new
   column / table / index, or a data query that returns 0 rows for a
   rewrite migration (e.g. "no standalone 'CEN' left" for 018)

Skipping the self-verify block means a partial migration failure ships
silently. See existing checks in `update.sh` step 8 for the pattern.

---

## 5. Cross-environment schema verification

When you suspect a local-vs-prod schema drift (the 2026-06-20 incident
was caused by this):

```bash
# Diff the cases table between two environments
sudo MYSQL_PWD='...' mysql -uroot cyber_fraud_dsr -e "SHOW CREATE TABLE cases\G" > /tmp/cases_prod.txt
# vs. local:
mysql -uroot -pSandy@411 cyber_fraud_dsr -e "SHOW CREATE TABLE cases\G" > /tmp/cases_local.txt
diff /tmp/cases_prod.txt /tmp/cases_local.txt
```

Likely sources of drift:
1. MySQL version differences (8.0.x defaults to different collations)
2. Tables created via `metadata.create_all` on first start vs. via migrations
3. Production tables that pre-date later schema decisions (Architecture.md inertia)

---

## 6. Migration registry

| # | Filename | Purpose |
|---|---|---|
| 001 | `001_add_user_contact_columns.py` | Adds email / mobile / audit columns to `users` |
| 002 | `002_add_ps_id_to_cases.py` | Adds `ps_id` to `cases`; re-scopes uniqueness to `(unit_id, ps_id, fir_no)` |
| 003 | `003_add_victims_table.py` | Creates `victims` table (1:1 with `cases` via UNIQUE `case_id`) |
| 004 | `004_break_victim_address.py` | Adds structured address columns to `victims`; deprecates the original `address` TEXT column |
| 005 | `005_add_chat_messages.py` | Adds `chat_messages` audit table (only deploy if chat feature is enabled) |
| 006 | `006_add_is_financial_to_cases.py` | Adds `is_financial TINYINT(1) NOT NULL DEFAULT 1` to `cases`; backfills all existing rows as Financial |
| 007 | `007_add_daily_nil_declarations.py` | Creates `daily_nil_declarations` table; UNIQUE `(unit_id, ps_id, nil_date)` |
| 008 | `008_add_ps_id_to_dsr_entries.py` | Adds `ps_id` to `dsr_entries`; re-scopes uniqueness to `(unit_id, ps_id, report_date)`. Backfills from `users.ps_id` via `submitted_by` |
| 009 | `009_add_all_accounts_tables.py` | Creates `all_accounts` + `all_account_mule_herders` tables for the All Accounts module. UNIQUE `(unit_id, ps_id, serial_no)` |
| 010 | `010_add_branch_district_to_all_accounts.py` | Adds `branch_district` to `all_accounts` |
| 011 | `011_add_account_statement_path_to_all_accounts.py` | Adds `account_statement_path` (file path for bank-statement uploads) |
| 012 | `012_add_layer_and_state_to_all_accounts.py` | Adds `layer INT` + `branch_state VARCHAR(100)` to `all_accounts` |
| 013 | `013_add_portals_dsr_entries.py` | Creates `portals_dsr_entries` (25-metric-column table across 8 external portals). NO UNIQUE — multiple shift-batches per `(unit_id, ps_id, report_date)` are legal, dashboards SUM |
| 014 | `014_add_daily_work_entries.py` | Creates `daily_work_entries` (per-FIR daily activity: notices, lien/unlien, arrests, statements, final_report). UNIQUE `(unit_id, ps_id, fir_no, report_date)` |
| 015 | `015_add_sections_to_cases.py` | Adds `sections VARCHAR(500) NULL` to `cases` (free-text BNS / BNSS / IT-Act sections) |
| 016 | `016_add_crime_type_expansion.py` | Widens `cases.crime_type` from `VARCHAR(30)` to `VARCHAR(200)` for the 31-entry KSP Cyber Crime classification; adds `crime_type_other VARCHAR(500) NULL` for the "Others → free text" case |
| 017 | `017_add_victim_and_accused_accounts.py` | Creates `victim_accounts` + `accused_accounts` tables (multi-account rows on DSR → New FIR). Both CASCADE from `cases.id` |
| 018 | `018_rename_cen_to_cyber_in_ps_names.py` | Data migration: `UPDATE police_stations SET station_name = REGEXP_REPLACE(station_name, '\bCEN\b', 'Cyber')`. Word-boundary regex protects "BANGALORE CENTRAL JAIL" etc. Requires MySQL 8+ (`REGEXP_REPLACE`) |
| 019 | `019_add_upload_analysis_tables.py` | Creates `upload_ledger`, `statement_transactions`, `id_photo_hashes` — the upload-analysis subsystem. `statement_transactions` is the fact table and the only large object in the schema |
| 020 | `020_account_statement_summary.py` | Creates `account_statement_summary` at (account, channel) grain — the cache every money screen reads. Aggregating the fact table per request took ~6.8 s on 190k rows and the table is now 26M |
| 021 | `021_mule_account_links.py` | Creates `mule_account_link` — direct mule → mule transfers, built by matching counterparty numbers in parsed narrations. Not a SQL join: the normalisation cannot be expressed as one |
| 022 | `022_statement_chain_ok.py` | Adds `statement_transactions.chain_ok TINYINT` — the PER-ROW balance-chain verdict. 1 passed / 0 rejected / −1 untested. The file-level verdict it replaced could not distinguish a bad row from a bad file |
| 023 | `023_summary_untested_totals.py` | Adds `untested_txns` / `untested_debit` / `untested_credit` to the summary. Untested money was previously indistinguishable from verified money |
| 024 | `024_crypto_transactions.py` | Creates `crypto_txn` — statement rows whose narration names a crypto exchange or asset. FK to `all_accounts` with CASCADE |
| 025 | `025_ifsc_branch.py` | Creates `ifsc_branch` — the IFSC → bank/branch/district/state directory. MASTER DATA from outside; the server has no route to the internet to re-fetch it, so it must stay in the backup |
| 026 | `026_widen_summary_money.py` | Widens the summary's six money columns `DECIMAL(18,2)` → `DECIMAL(24,2)`. The raw totals include chain-REJECTED rows, and 439 of those carry misparsed amounts up to ₹1,000 trillion — enough of them in one account overflowed the column and killed the nightly run |

All migrations are idempotent — safe to re-run. Order matters only when
later migrations depend on earlier columns / tables existing.

**Deploy:** `deploy/update.sh` runs `001 → 004, 006 → 026` in sequence
(005 is deliberately skipped on prod until the chat GPU box is in place
— no point provisioning an audit table for a feature the app doesn't
expose). Every migration has a self-verify block in step 8 that aborts
the deploy if the schema change didn't land. NEVER run migrations by
hand on prod unless `update.sh` itself is broken.

---

## 7. Tables NOT to add foreign keys to

Some tables are intentionally referenced by ID without FK constraints
because:

| Table | Why no FK |
|---|---|
| `cases.submitted_by → users.id` | Originally FK'd; kept INT for compatibility but the FK is fragile when users get hard-deleted. Treat as soft reference. |
| `chat_messages.user_id → users.id` | Has FK but rows are retained for audit even after the user is deactivated. Don't add CASCADE. |

If you're adding a new FK and the parent is `users`, talk to whoever
owns auth first.

---

## 8. Common operations cheat-sheet

### Add a new child table referencing `cases`

```sql
CREATE TABLE my_new_child (
    id            VARCHAR(36) NOT NULL,
    case_id       VARCHAR(36) NOT NULL,
    -- ... columns ...
    PRIMARY KEY (id),
    CONSTRAINT fk_my_new_child_case_id
        FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### Add a column to `victims`

```sql
ALTER TABLE victims ADD COLUMN my_new_col VARCHAR(100) NULL;
-- No CHARSET/COLLATE — inherits from the table.
```

### Check FK compatibility before writing one

```sql
SELECT
    cs.character_set_name AS charset,
    cl.collation_name     AS collation
FROM information_schema.columns c
JOIN information_schema.character_sets cs USING (character_set_name)
JOIN information_schema.collations cl USING (collation_name)
WHERE c.table_schema = 'cyber_fraud_dsr'
  AND c.table_name = 'cases'
  AND c.column_name = 'id';
```

### List all FKs into a table (sanity check on cascade behaviour)

```sql
SELECT constraint_name, table_name, column_name, referenced_table_name, referenced_column_name
FROM information_schema.key_column_usage
WHERE referenced_table_schema = 'cyber_fraud_dsr'
  AND referenced_table_name = 'cases';
```

---

## 9. When in doubt

1. **Read the actual prod schema, not any doc** — `SHOW CREATE TABLE x\G`.
2. **Match the referenced column's full definition** when writing FKs.
3. **Test the migration on a copy of prod data** before pushing — the nightly `deploy/backup-db.sh` mysqldump can be restored to a scratch DB.
4. **Run migrations through `deploy/update.sh`**, never by hand on prod — the script has the right ordering + a self-verify block per migration.
5. **Additive changes only** — post-VAPT no `DROP TABLE`, no `DROP COLUMN`, no unconditional data rewrites.

---

## 10. Current Schema Reference

Column-level snapshot of every table, generated from the SQLAlchemy
models under `backend/models/*.py`. Update whenever a model changes.
For the deployed DDL — including indexes, engine settings, and any
prod-only drift — run `deploy/dump-schema.sh` to produce a fresh
timestamped `.sql` under `proddata/` (see [Operations.md](./Operations.md#schema-snapshot-structure-only-no-rows)).

### 10.1 Identity & Reference Tables

#### `units` — 44 KA districts

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INT | NO | PK autoincrement |
| `name` | VARCHAR(100) | NO | UNIQUE |
| `code` | VARCHAR(50) | NO | UNIQUE |
| `is_active` | BOOLEAN | YES | default true |
| `created_at` | DATETIME | YES | server default now() |

#### `police_stations` — 45+ Cyber Crime PSes

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INT | NO | PK autoincrement |
| `district_name` | VARCHAR(100) | NO | |
| `station_name` | VARCHAR(200) | NO | migration 018 renamed `CEN` → `Cyber` (word-boundary regex) |
| `is_active` | BOOLEAN | YES | default true |
| `created_at` | DATETIME | YES | server default now() |

#### `users` — login accounts

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INT | NO | PK autoincrement |
| `username` | VARCHAR(50) | NO | UNIQUE |
| `hashed_password` | VARCHAR(255) | NO | bcrypt |
| `full_name` | VARCHAR(150) | YES | |
| `email` | VARCHAR(200) | YES | UNIQUE, added migration 001 |
| `mobile` | VARCHAR(20) | YES | added migration 001 |
| `role` | ENUM | NO | `admin` / `unit_user` / `super_admin` (default `unit_user`) |
| `unit_id` | INT | YES | FK `units.id` |
| `ps_id` | INT | YES | FK `police_stations.id` |
| `is_active` | BOOLEAN | YES | default true |
| `must_change_password` | BOOLEAN | NO | default true (server_default '1') |
| `created_at` | DATETIME | YES | |
| `created_by` | INT | YES | FK `users.id` (self-ref), audit column, added migration 001 |
| `deactivated_at` | DATETIME | YES | audit |
| `deactivated_by` | INT | YES | FK `users.id` (self-ref), audit |

#### `revoked_tokens` — JWT denylist

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INT | NO | PK autoincrement |
| `jti` | VARCHAR(64) | NO | UNIQUE, indexed. JWT ID claim |
| `revoked_at` | DATETIME | NO | server default now() |
| `user_id` | INT | YES | indexed (no FK — audit rows kept even if user removed) |

---

### 10.2 Cases module (11 tables)

#### `cases` — FIR / NCRP / Walk-In / Petition parent

UNIQUE `(unit_id, ps_id, fir_no)` — `uq_case_unit_ps_fir` (migration 002).

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK (VAPT v1.0.1 rec #2) |
| `unit_id` | INT | NO | FK `units.id` |
| `ps_id` | INT | NO | FK `police_stations.id` (migration 002) |
| `fir_no` | VARCHAR(50) | YES | `NNNN/YYYY` format enforced by shared validator |
| `petition_no` | VARCHAR(50) | YES | for Petition-type cases without an FIR |
| `registration_date` | DATE | YES | |
| `case_type` | VARCHAR(20) | NO | NCRP / Walk-In / Petition |
| `crime_type` | VARCHAR(200) | NO | 31-entry KSP classification since migration 016 (widened from VARCHAR(30)) |
| `crime_type_other` | VARCHAR(500) | YES | free text when `crime_type = 'Others'` (migration 016) |
| `sections` | VARCHAR(500) | YES | free-text BNS / BNSS / IT-Act sections (migration 015) |
| `is_financial` | INT | NO | 1 / 0 (migration 006, backfilled 1 for legacy rows) |
| `facts` | TEXT | YES | |
| `status` | VARCHAR(20) | NO | `draft` / `submitted` (default `draft`) |
| `submitted_by` | INT | YES | FK `users.id` |
| `created_at` | DATETIME | YES | |
| `updated_at` | DATETIME | YES | onupdate now() |

#### `arrests` — persons arrested per case

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `case_id` | VARCHAR(36) | NO | FK `cases.id` CASCADE |
| `name` | VARCHAR(200) | NO | |
| `address` | TEXT | YES | |
| `email` | VARCHAR(200) | YES | |
| `aadhar` | VARCHAR(12) | YES | |
| `pan` | VARCHAR(10) | YES | |
| `date_of_arrest` | DATE | YES | |
| `statement` | TEXT | YES | up to 5000 chars enforced client-side |
| `created_at` | DATETIME | YES | |

#### `accomplices` — per-arrest accomplice info

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `arrest_id` | VARCHAR(36) | NO | FK `arrests.id` CASCADE |
| `where_met` | VARCHAR(500) | YES | |
| `where_stayed` | VARCHAR(500) | YES | |
| `interrogation_details` | TEXT | YES | |
| `created_at` | DATETIME | YES | |

#### `accused_details` — per-arrest contact + photo

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `arrest_id` | VARCHAR(36) | NO | FK `arrests.id` CASCADE |
| `photo_path` | VARCHAR(500) | YES | filesystem path under `backend/uploads/` |
| `email` | VARCHAR(200) | YES | |
| `mobile` | VARCHAR(20) | YES | |
| `occupation` | VARCHAR(200) | YES | |
| `remarks` | TEXT | YES | |
| `created_at` | DATETIME | YES | |

#### `petitions` — legal petitions per case

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `case_id` | VARCHAR(36) | YES | FK `cases.id` CASCADE |
| `petition_no` | VARCHAR(50) | YES | |
| `fir_registered` | VARCHAR(20) | NO | yes / no / transferred |
| `why_not` | TEXT | YES | |
| `nature` | VARCHAR(100) | YES | |
| `petition_type` | VARCHAR(30) | NO | amount_lost / fraud_case |
| `amount` | NUMERIC(18,2) | YES | default 0, ≤ ₹100 crore enforced by validator |
| `created_at` | DATETIME | YES | |

#### `lien_accounts` — frozen accounts per case

Tracks the freeze / lien lifecycle. Distinct from `accused_accounts`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `case_id` | VARCHAR(36) | NO | FK `cases.id` CASCADE |
| `case_type` | VARCHAR(20) | NO | FIR / NCRP / Petition |
| `account_no` | VARCHAR(50) | NO | |
| `amount_lien_marked` | NUMERIC(18,2) | YES | default 0 |
| `layer` | INT | YES | default 1, money-trail depth |
| `total_amount_in_account` | NUMERIC(18,2) | YES | default 0 |
| `bank_name` | VARCHAR(200) | YES | |
| `created_at` | DATETIME | YES | |

#### `unfreeze_details` — defreeze / unlien records per case

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `case_id` | VARCHAR(36) | NO | FK `cases.id` CASCADE |
| `unfreeze_type` | VARCHAR(20) | NO | letter / court_order |
| `crime_no` | VARCHAR(50) | YES | mirrors case FIR No at write time |
| `bank_name` | VARCHAR(200) | YES | |
| `account_no` | VARCHAR(50) | YES | |
| `amount` | NUMERIC(18,2) | YES | default 0 |
| `created_at` | DATETIME | YES | |

#### `refunds` — victim refunds per case

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `case_id` | VARCHAR(36) | NO | FK `cases.id` CASCADE |
| `refunded` | VARCHAR(5) | NO | yes / no |
| `victim_name` | VARCHAR(200) | YES | |
| `amount` | NUMERIC(18,2) | YES | default 0 |
| `crime_no_or_petition_no` | VARCHAR(100) | YES | |
| `created_at` | DATETIME | YES | |

#### `victims` — 1:1 with case (migration 003)

UNIQUE `(case_id)` — enforces 1:1 at DB level.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `case_id` | VARCHAR(36) | NO | FK `cases.id` CASCADE, UNIQUE |
| `first_name` | VARCHAR(100) | NO | |
| `last_name` | VARCHAR(100) | NO | |
| `age` | INT | YES | |
| `gender` | VARCHAR(30) | YES | |
| `phone` | VARCHAR(20) | YES | 10 digits enforced by validator |
| `email` | VARCHAR(200) | YES | |
| `house_no` | VARCHAR(50) | YES | added migration 004 |
| `street_name` | VARCHAR(200) | YES | migration 004 |
| `city` | VARCHAR(100) | YES | migration 004 |
| `state` | VARCHAR(100) | YES | migration 004 |
| `country` | VARCHAR(100) | YES | migration 004, default 'India' |
| `pincode` | VARCHAR(10) | YES | 6 digits enforced by validator |
| `amount_lost` | NUMERIC(18,2) | NO | default 0 |
| `bank_account_no` | VARCHAR(50) | NO | 9–18 digits enforced by validator (primary account) |
| `bank_name` | VARCHAR(200) | NO | primary account |
| `bank_branch_address` | TEXT | YES | primary account |
| `created_at` | DATETIME | YES | |

*Legacy `address` TEXT column persists in the DB pre-migration-004 but is not mapped in the model.*

#### `victim_accounts` — additional victim accounts (migration 017)

Captured on DSR → New FIR only. `Optional[List]=None` on update = passthrough (see routes_case.py).

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `case_id` | VARCHAR(36) | NO | FK `cases.id` CASCADE |
| `bank_name` | VARCHAR(200) | NO | |
| `branch_name` | VARCHAR(200) | YES | |
| `branch_address` | VARCHAR(500) | YES | |
| `state` | VARCHAR(100) | YES | |
| `district` | VARCHAR(100) | YES | KA-only dropdown on client |
| `ifsc_code` | VARCHAR(20) | YES | |
| `amount_transferred` | NUMERIC(18,2) | YES | default 0 |
| `created_at` | DATETIME | YES | |

#### `accused_accounts` — bank accounts money went TO (migration 017)

Independent of `lien_accounts`. Captured on DSR → New FIR only.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `case_id` | VARCHAR(36) | NO | FK `cases.id` CASCADE |
| `account_holder_name` | VARCHAR(200) | NO | |
| `bank_name` | VARCHAR(200) | NO | |
| `branch_name` | VARCHAR(200) | YES | |
| `branch_address` | VARCHAR(500) | YES | |
| `state` | VARCHAR(100) | YES | |
| `district` | VARCHAR(100) | YES | KA-only dropdown on client |
| `ifsc_code` | VARCHAR(20) | YES | |
| `amount_transferred` | NUMERIC(18,2) | YES | default 0 |
| `created_at` | DATETIME | YES | |

---

### 10.3 NCRP Data module (7 tables)

#### `mule_reports` — bank-provided investigation report parent

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `unit_id` | INT | NO | FK `units.id` |
| `acknowledgement_no` | VARCHAR(50) | YES | UNIQUE across the whole DB |
| `fir_no` | VARCHAR(50) | YES | UNIQUE across the whole DB |
| `status` | VARCHAR(20) | NO | draft / submitted (default draft) |
| `submitted_by` | INT | YES | FK `users.id` |
| `created_at` | DATETIME | YES | |
| `updated_at` | DATETIME | YES | onupdate now() |

*Note: does not carry `ps_id` — pre-dates migration 008's per-PS scoping. Ownership resolves via `submitted_by`.*

#### `money_transfers` — bank-to-bank transfers per report

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `report_id` | VARCHAR(36) | NO | FK `mule_reports.id` CASCADE |
| `account_no` | VARCHAR(100) | YES | |
| `transaction_id` | VARCHAR(100) | YES | |
| `bank` | VARCHAR(200) | YES | |
| `layer` | INT | YES | money-trail depth |
| `dest_account_no` | VARCHAR(100) | YES | |
| `ifsc_code` | VARCHAR(20) | YES | |
| `transaction_date` | VARCHAR(50) | YES | free-text (bank format varies) |
| `dest_transaction_id` | VARCHAR(100) | YES | |
| `transaction_amount` | NUMERIC(18,2) | YES | default 0 |
| `disputed_amount` | NUMERIC(18,2) | YES | default 0 |
| `reference_no` | VARCHAR(100) | YES | |
| `remarks` | TEXT | YES | |
| `action_taken_by_bank` | VARCHAR(200) | YES | |
| `date_of_action` | VARCHAR(50) | YES | free-text |
| `created_at` | DATETIME | YES | |

#### `other_transactions` — non-transfer txns per report

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `report_id` | VARCHAR(36) | NO | FK `mule_reports.id` CASCADE |
| `account_no` | VARCHAR(100) | YES | |
| `transaction_id` | VARCHAR(100) | YES | |
| `transaction_date` | VARCHAR(50) | YES | |
| `transaction_amount` | NUMERIC(18,2) | YES | default 0 |
| `reference_no` | VARCHAR(100) | YES | |
| `remarks` | TEXT | YES | |
| `action_taken_by_bank` | VARCHAR(200) | YES | |
| `date_of_action` | VARCHAR(50) | YES | |
| `created_at` | DATETIME | YES | |

#### `transactions_on_hold` — held / blocked per report

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `report_id` | VARCHAR(36) | NO | FK `mule_reports.id` CASCADE |
| `account_no` | VARCHAR(100) | YES | |
| `transaction_id` | VARCHAR(100) | YES | |
| `hold_date` | VARCHAR(50) | YES | |
| `hold_amount` | NUMERIC(18,2) | YES | default 0 |
| `action_taken_by_bank` | VARCHAR(200) | YES | |
| `date_of_action` | VARCHAR(50) | YES | |
| `layer` | INT | YES | |
| `created_at` | DATETIME | YES | |

#### `others_less_than_500` — < ₹500 txns per report

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `report_id` | VARCHAR(36) | NO | FK `mule_reports.id` CASCADE |
| `account_no` | VARCHAR(100) | YES | |
| `transaction_id` | VARCHAR(100) | YES | |
| `reference_no` | VARCHAR(100) | YES | |
| `remarks` | TEXT | YES | |
| `action_taken_by_bank` | VARCHAR(200) | YES | |
| `date_of_action` | VARCHAR(50) | YES | |
| `created_at` | DATETIME | YES | |

#### `aeps_transactions` — Aadhaar-enabled withdrawals per report

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `report_id` | VARCHAR(36) | NO | FK `mule_reports.id` CASCADE |
| `account_no` | VARCHAR(100) | YES | |
| `transaction_id` | VARCHAR(100) | YES | |
| `withdrawal_date` | VARCHAR(50) | YES | |
| `withdrawal_amount` | NUMERIC(18,2) | YES | default 0 |
| `reference_no` | VARCHAR(100) | YES | |
| `remarks` | TEXT | YES | |
| `action_taken_by_bank` | VARCHAR(200) | YES | |
| `date_of_action` | VARCHAR(50) | YES | |
| `layer` | INT | YES | |
| `created_at` | DATETIME | YES | |

#### `atm_withdrawals` — ATM cash withdrawals per report

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `report_id` | VARCHAR(36) | NO | FK `mule_reports.id` CASCADE |
| `account_no` | VARCHAR(100) | YES | |
| `transaction_id` | VARCHAR(100) | YES | |
| `withdrawal_datetime` | VARCHAR(50) | YES | |
| `withdrawal_amount` | NUMERIC(18,2) | YES | default 0 |
| `disputed_amount` | NUMERIC(18,2) | YES | default 0 |
| `atm_id` | VARCHAR(100) | YES | |
| `atm_location` | VARCHAR(500) | YES | |
| `reference_no` | VARCHAR(100) | YES | |
| `remarks` | TEXT | YES | |
| `action_taken_by_bank` | VARCHAR(200) | YES | |
| `date_of_action` | VARCHAR(50) | YES | |
| `created_at` | DATETIME | YES | |

---

### 10.4 All Accounts module (2 tables)

#### `all_accounts` — master register per PS

UNIQUE `(unit_id, ps_id, serial_no)` — `uq_all_account_ps_serial`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `unit_id` | INT | NO | FK `units.id` |
| `ps_id` | INT | NO | FK `police_stations.id` |
| `serial_no` | INT | NO | auto-generated per (unit_id, ps_id) at create time |
| `fir_no` | VARCHAR(50) | YES | optional linkage |
| `ncrp_ack_no` | VARCHAR(60) | YES | optional linkage |
| `account_no` | VARCHAR(50) | NO | |
| `bank_name` | VARCHAR(200) | NO | |
| `branch_name` | VARCHAR(200) | YES | |
| `branch_district` | VARCHAR(100) | YES | added migration 010 |
| `branch_state` | VARCHAR(100) | YES | added migration 012 |
| `layer` | INT | YES | added migration 012, money-trail depth |
| `ifsc_code` | VARCHAR(20) | YES | |
| `account_holder_name` | VARCHAR(200) | NO | |
| `kyc_address` | TEXT | YES | |
| `kyc_mobile` | VARCHAR(20) | YES | |
| `id_photo_path` | VARCHAR(500) | YES | filesystem path |
| `account_statement_path` | VARCHAR(500) | YES | added migration 011 |
| `account_type` | VARCHAR(20) | NO | Victim / Mule / Non-Mule |
| `submitted_by` | INT | YES | FK `users.id` |
| `created_at` | DATETIME | NO | |
| `updated_at` | DATETIME | YES | onupdate now() |

#### `all_account_mule_herders` — per-Mule-account herder rows

Only populated when `account_type = 'Mule'`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `account_id` | VARCHAR(36) | NO | FK `all_accounts.id` CASCADE |
| `name` | VARCHAR(200) | NO | |
| `address` | TEXT | YES | |
| `mobile_no` | VARCHAR(20) | YES | |
| `created_at` | DATETIME | NO | |

---

### 10.5 DSR module (5 tables)

#### `dsr_entries` — daily district-level report

UNIQUE `(unit_id, ps_id, report_date)` — `uq_dsr_unit_ps_date` (migration 008 rescoped from `(unit_id, report_date)`).

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INT | NO | PK autoincrement |
| `unit_id` | INT | NO | FK `units.id` |
| `ps_id` | INT | NO | FK `police_stations.id` (migration 008) |
| `report_date` | DATE | NO | |
| `cases` | INT | YES | default 0 |
| `petitions` | INT | YES | default 0 |
| `details_of_arrest` | INT | YES | default 0 |
| `case_type` | VARCHAR(20) | YES | FIR / NCRP |
| `cumulative_amount_lien_marked` | NUMERIC(18,2) | YES | default 0 |
| `cumulative_accounts_lien_marked` | INT | YES | default 0 |
| `cumulative_accounts_defreezed` | INT | YES | default 0 |
| `amount_refunded_to_victim` | NUMERIC(18,2) | YES | default 0 |
| `ui_cases_pending_2021` … `_2026` | INT | YES | six columns, default 0 |
| `disposed_detected_chargesheeted` | INT | YES | default 0 |
| `disposed_transferred` | INT | YES | default 0 |
| `disposed_false` | INT | YES | default 0 |
| `disposed_undetected` | INT | YES | default 0 |
| `trial_convicted` / `_discharged` / `_acquitted` / `_abated` / `_compounded` / `_ut` | INT | YES | default 0 each |
| `submitted_by` | INT | YES | FK `users.id` |
| `created_at` / `updated_at` | DATETIME | YES | |

#### `mule_entries` — daily mule intel free-text summaries

UNIQUE `(unit_id, report_date)` — `uq_mule_unit_date`.

*Note: still district-level (no `ps_id`) — pre-dates the per-PS convention.*

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INT | NO | PK autoincrement |
| `unit_id` | INT | NO | FK `units.id` |
| `report_date` | DATE | NO | |
| `accounts_most_liens` | TEXT | YES | |
| `recruiters_for_lien_accounts` | TEXT | YES | |
| `accounts_max_money_routed` | TEXT | YES | |
| `accounts_max_transactions` | TEXT | YES | |
| `recency_atm_transactions` | TEXT | YES | |
| `cash_withdrawals_mule_wise` | TEXT | YES | |
| `atm_geo_identification` | TEXT | YES | |
| `atm_table_by_transactions` | TEXT | YES | |
| `cheque_withdrawal_branches` | TEXT | YES | |
| `money_left_system_stats` | TEXT | YES | |
| `crypto_mule_accounts` | TEXT | YES | |
| `submitted_by` | INT | YES | FK `users.id` |
| `created_at` / `updated_at` | DATETIME | YES | |

#### `daily_work_entries` — per-FIR per-day investigation log (migration 014)

UNIQUE `(unit_id, ps_id, fir_no, report_date)` — `uq_daily_work_unit_ps_fir_date`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INT | NO | PK autoincrement |
| `unit_id` | INT | NO | FK `units.id` |
| `ps_id` | INT | NO | FK `police_stations.id` |
| `report_date` | DATE | NO | |
| `fir_no` | VARCHAR(50) | NO | |
| `notices_35_41a_count` | INT | NO | default 0 (red) |
| `notices_91_92_94_banks` | INT | NO | default 0 (red) |
| `notices_91_92_94_intermediary` | INT | NO | default 0 (red) |
| `notices_91_92_94_account_holder` | INT | NO | default 0 (red) |
| `notices_91_92_94_cdr_ipdr` | INT | NO | default 0 (red) |
| `lien_requests_count` | INT | NO | default 0 (yellow) |
| `freeze_requests_count` | INT | NO | default 0 (yellow) |
| `total_lien_amount` | NUMERIC(18,2) | NO | default 0 (yellow) |
| `unlien_requests_count` | INT | NO | default 0 (yellow) |
| `defreeze_requests_count` | INT | NO | default 0 (yellow) |
| `total_unlien_amount` | NUMERIC(18,2) | NO | default 0 (yellow) |
| `arrests_count` | INT | NO | default 0 (green) |
| `statements_count` | INT | NO | default 0 (green) |
| `final_report` | VARCHAR(1) | YES | A (chargesheeted) / B (false) / C (undetected) |
| `submitted_by` | INT | YES | FK `users.id` |
| `created_at` / `updated_at` | DATETIME | YES | |

#### `portals_dsr_entries` — 8-portal daily counters (migration 013)

**No UNIQUE constraint** — multiple shift-batches per `(unit_id, ps_id, report_date)` are legal; dashboards SUM.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `unit_id` | INT | NO | FK `units.id` |
| `ps_id` | INT | NO | FK `police_stations.id` |
| `report_date` | DATE | NO | |
| `status` | VARCHAR(20) | NO | draft / submitted (default draft) |
| `ncrp_received` / `_disposed` / `_pending` | INT | NO | default 0 |
| `samanvaya_request_received` / `_actions` / `_action_pending` / `_request_sent` / `_reply_received` / `_replies_pending` | INT | NO | default 0 each |
| `sahayog_unlawful_content_removal` / `_intermediary_requests` / `_crypto_requests` | INT | NO | default 0 |
| `grm_request_received` / `_action` / `_pending` | INT | NO | default 0 |
| `mrm_request_received` / `_action` / `_pending` | INT | NO | default 0 |
| `bharatpol_request_received` | INT | NO | default 0 |
| `ocwc_received` / `_disposed` / `_pending` | INT | NO | default 0 |
| `ncmec_received` / `_disposed` / `_pending` | INT | NO | default 0 |
| `submitted_by` | INT | YES | FK `users.id` |
| `created_at` | DATETIME | NO | |
| `updated_at` | DATETIME | YES | onupdate now() |

*Total metric columns: 25 (3 + 6 + 3 + 3 + 3 + 1 + 3 + 3).*

#### `daily_nil_declarations` — PS "no activity" flag (migration 007)

UNIQUE `(unit_id, ps_id, nil_date)` — `uq_nil_unit_ps_date`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `unit_id` | INT | NO | (no FK — captured for scoping) |
| `ps_id` | INT | NO | |
| `declared_by` | INT | NO | FK `users.id` |
| `nil_date` | DATE | NO | |
| `reason` | VARCHAR(255) | YES | |
| `created_at` | DATETIME | YES | |

---

### 10.6 Admin module (1 table)

#### `chat_messages` — LLM chat audit trail (migration 005)

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(36) | NO | UUIDv4 PK |
| `user_id` | INT | NO | FK `users.id` (no CASCADE — audit rows kept even if user removed) |
| `unit_id` | INT | YES | captured for analytics; not FK-enforced |
| `ps_id` | INT | YES | same |
| `question` | TEXT | NO | operator's natural-language question |
| `generated_sql` | TEXT | YES | LLM-generated SQL |
| `row_count` | INT | YES | rows returned by the SQL |
| `error` | VARCHAR(500) | YES | if generation / execution failed |
| `latency_ms` | INT | YES | end-to-end |
| `created_at` | DATETIME | YES | |

*Only super_admin can create rows here. Migration 005 is deliberately skipped on prod until the chat feature ships.*

---

### 10.7 Upload analysis subsystem (7 tables)

Added by migrations 019–026. **These are DERIVED**, not operator-entered:
every row is a pure function of the files under `backend/uploads/` and
can be rebuilt by re-running `analysis.daily`. That property is what
lets `backup-db.sh` exclude the largest of them.

| Table | Rows (2026-08-22) | Purpose |
|---|---|---|
| `statement_transactions` | 26.5 M / 27.6 GB | Parsed bank-statement rows. `chain_ok` carries the per-row balance verdict. **The only table excluded from the nightly dump** — it is rebuildable from the PDFs, and including it would make the dump ~600× larger |
| `upload_ledger` | 33 k | Which uploaded file has been processed, at which `parser_version`, and why it yielded nothing. Drives the incremental parse: a file listed here as settled is skipped |
| `account_statement_summary` | 108 k | (account, channel) rollup. Every money figure on every dashboard reads this, never the fact table |
| `id_photo_hashes` | 21 k | SHA-256 + 24×24 perceptual hash per ID photo. Powers Duplicate IDs |
| `mule_account_link` | 2.4 k | Direct mule → mule transfers, with a `cross_fir` flag. **The one table with no ORM model** — `routes_dashboard.py` reads it through raw `text()` |
| `crypto_txn` | 984 | Statement rows naming a crypto exchange or asset |
| `ifsc_branch` | 183 k | IFSC → bank / branch / district / state. Master data from outside |

**The ledger and the fact table must live on the same machine.** Shipping
`upload_ledger` without `statement_transactions` gives a server that
CLAIMS work it never did — the parser skips every file the ledger calls
settled, and the summaries then describe rows that are not there. This
happened on 2026-08-18 and cost a 25 GB re-seed; see Operations.md.

---

**Total: 37 tables.** Ownership chain summary:

- `cases` → 10 direct children (arrests → 2 grandchildren; petitions, lien_accounts, unfreeze_details, refunds, victims (1:1), victim_accounts, accused_accounts)
- `mule_reports` → 6 direct children (all txn tables)
- `all_accounts` → 1 direct child (all_account_mule_herders)
- Every operator-created row carries `submitted_by`
- Every CASCADE deletion is intentional; no orphan protection anywhere
- The 7 analysis tables hang off `all_accounts` (or off nothing) and are
  rebuildable; the other 30 are operator-entered and are not
