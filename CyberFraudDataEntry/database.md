# Database Design Conventions — CyberFraud Data Entry

Source of truth for **how to write schema-changing code** that won't break
on deploy. Architecture.md describes the logical schema; this file
describes the physical constraints that the LLM / a human refactor will
trip over if they ignore them.

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

**Architecture.md still shows the old `INT AUTO_INCREMENT` for parent
records — it's stale on this point.** Source of truth = the SQLAlchemy
models in `backend/models/*.py`.

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
indexes / constraints before creating them. Pattern in
`migrations/001_*.py` through `migrations/004_*.py` — re-use the helper
functions (`_table_exists`, `_column_exists`, `_index_exists`,
`_fk_exists`).

### 4.5 Migrations must be reversible in principle

For now we don't ship explicit `down()` functions, but each forward
operation should be cleanly reversible (no destructive `DROP TABLE` on
existing data without explicit operator action, etc.). The pre-migration
backup taken by `deploy/update.sh` is the rollback path.

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
| 007 | `007_add_daily_nil_declarations.py` | Creates `daily_nil_declarations` table — lets a PS explicitly mark a date as "no activity"; UNIQUE `(unit_id, ps_id, nil_date)` |
| 008 | `008_add_ps_id_to_dsr_entries.py` | Adds `ps_id` to `dsr_entries`; re-scopes uniqueness from `(unit_id, report_date)` to `(unit_id, ps_id, report_date)`. DSR becomes per-PS. Backfills from `users.ps_id` via `submitted_by`. |

All migrations are idempotent — safe to re-run. Order matters only when
later migrations depend on earlier columns/tables existing.

**Deploy:** `deploy/update.sh` runs 001 → 004, 006, 007, 008 in sequence
(005 is skipped on prod until the chat GPU box is in place). The script
includes a pre-migration backup and post-migration sanity checks. NEVER
run migrations by hand on prod unless `update.sh` itself is broken.

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

1. **Read the actual prod schema, not Architecture.md** — `SHOW CREATE TABLE x\G`.
2. **Match the referenced column's full definition** when writing FKs.
3. **Test the migration on a copy of prod data** before pushing — `deploy/backup-db.sh` produces a gzipped dump that can be restored to a scratch DB.
4. **Run migrations through `deploy/update.sh`**, never by hand on prod — the script has the right ordering, backup, and verification baked in.
