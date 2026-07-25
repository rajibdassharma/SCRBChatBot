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

All migrations are idempotent — safe to re-run. Order matters only when
later migrations depend on earlier columns / tables existing.

**Deploy:** `deploy/update.sh` runs `001 → 004, 006 → 018` in sequence
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
