#!/usr/bin/env bash
# CyberFraud — INCREMENTAL UPDATE deploy.
#
# This script applies a feature update WITHOUT touching production data:
#   - No reset_db.py, no seed.py
#   - No regression-test re-runs
#   - No nginx config changes (use the destructive script for that)
#
# What it does (idempotent end-to-end):
#   1. git pull on /opt/scrb to fetch the latest source
#   2. Install / upgrade pip deps from backend/requirements.txt
#   3. Pre-migration safety backup (skipped if no schema changes apply)
#   4. Run additive DB migrations 001 + 002 (idempotent — INFORMATION_SCHEMA
#      checks mean each migration's a no-op when already applied)
#   5. Build the frontend (npm install + npm run build)
#   6. Sync backend/ + frontend/dist/ from source to runtime
#   7. Restart the backend systemd service
#   8. Self-verify: service active, /health responding, schema sane
#
# Usage on the server:
#   cd /opt/scrb && git pull && \
#     sudo bash CyberFraudDataEntry/deploy/update.sh
#
# (the leading `git pull` ensures this script picks up its own latest
#  version; the script also pulls again internally to be safe.)
#
# Aborts on first failure (set -euo pipefail). Safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$(cd "$SCRIPT_DIR/.." && pwd)"          # /opt/scrb/CyberFraudDataEntry
REPO_ROOT="$(cd "$SOURCE/.." && pwd)"           # /opt/scrb
RUNTIME=/opt/cyberfraud
SVC=cyberfraud-backend

echo "================================================================"
echo "  CyberFraud incremental update"
echo "  SOURCE : $SOURCE"
echo "  REPO   : $REPO_ROOT"
echo "  RUNTIME: $RUNTIME"
echo "================================================================"

# ── 1. Pull latest source ────────────────────────────────────────────
echo
echo "=== 1. git pull on $REPO_ROOT ==="
cd "$REPO_ROOT"
git pull
echo "    HEAD: $(git log -1 --oneline)"

# ── 2. Install / upgrade Python deps ─────────────────────────────────
echo
echo "=== 2. Install pip dependencies (catches new packages) ==="
sudo -u cyberfraud bash -c "
    cd $RUNTIME/backend
    venv/bin/pip install --quiet --upgrade -r $SOURCE/backend/requirements.txt
"
echo "    Done."

# ── 3. Pre-migration safety backup ───────────────────────────────────
# Take an ad-hoc backup of cyber_fraud_dsr AND the uploads/ tree just
# before any schema/code changes. Re-using the same backup scripts as
# nightly means restore is a one-liner if anything regresses. Safe to
# run even when no migration changes apply — both scripts always write
# a fresh timestamped file and prune anything older than 14d.
echo
echo "=== 3. Pre-migration DB + uploads backup ==="
sudo bash "$SOURCE/deploy/backup-db.sh"
sudo bash "$SOURCE/deploy/backup-uploads.sh"

# ── 4. Run additive DB migrations ────────────────────────────────────
echo
echo "=== 4. Run additive DB migrations 001 → 004, 006 → 011 (idempotent) ==="
# Migration 005 (chat_messages) is deliberately skipped until the GPU box
# is in place for the chat feature — there's no point provisioning an
# empty audit table for an endpoint the prod app does not yet expose.
# Copy the migrations folder into runtime so the script can `import config`
# / `import database` from the runtime venv path.
sudo cp -r "$SOURCE/backend/migrations" "$RUNTIME/backend/"
sudo chown -R cyberfraud:cyberfraud "$RUNTIME/backend/migrations"
sudo -u cyberfraud bash -c "
    set -e
    cd $RUNTIME/backend
    venv/bin/python -m migrations.001_add_user_contact_columns
    venv/bin/python -m migrations.002_add_ps_id_to_cases
    venv/bin/python -m migrations.003_add_victims_table
    venv/bin/python -m migrations.004_break_victim_address
    venv/bin/python -m migrations.006_add_is_financial_to_cases
    venv/bin/python -m migrations.007_add_daily_nil_declarations
    venv/bin/python -m migrations.008_add_ps_id_to_dsr_entries
    venv/bin/python -m migrations.009_add_all_accounts_tables
    venv/bin/python -m migrations.010_add_branch_district_to_all_accounts
    venv/bin/python -m migrations.011_add_account_statement_path_to_all_accounts
"

# ── 5. Build the frontend ────────────────────────────────────────────
echo
echo "=== 5. Build frontend (npm install + npm run build) ==="
cd "$SOURCE/frontend"
npm install --silent
npm run build
echo "    dist/ built:"
ls -la "$SOURCE/frontend/dist/" | head -10

# ── 6. Sync code from source to runtime ──────────────────────────────
echo
echo "=== 6. Sync backend + frontend dist to $RUNTIME ==="
sudo cp -r "$SOURCE/backend" "$RUNTIME/"
sudo cp -r "$SOURCE/frontend" "$RUNTIME/"
sudo chown -R cyberfraud:cyberfraud "$RUNTIME/backend" "$RUNTIME/frontend"

# ── 7. Restart backend ───────────────────────────────────────────────
echo
echo "=== 7. Restart backend service ==="
sudo systemctl restart "$SVC"
sleep 2
sudo systemctl is-active "$SVC"

# ── 8. Self-verify ───────────────────────────────────────────────────
echo
echo "=== 8. Self-verify ==="
# Health endpoint via nginx (proxied path)
if curl -sk --max-time 5 https://localhost/health | grep -q '"ok"'; then
    echo "    ✓ /health responding via nginx"
else
    echo "    ✗ /health check failed via nginx — checking backend directly..."
    curl -s --max-time 5 http://127.0.0.1:8000/health || true
    exit 1
fi

# New routes mounted?
if curl -sk --max-time 5 -o /dev/null -w "%{http_code}" https://localhost/api/v1/users | grep -qE '^(401|403)$'; then
    echo "    ✓ /api/v1/users mounted (returned auth error — expected for unauth'd request)"
else
    echo "    ✗ /api/v1/users not responding correctly"
    exit 1
fi

if curl -sk --max-time 5 -o /dev/null -w "%{http_code}" "https://localhost/api/v1/reports/dsr.pdf?from=2026-01-01&to=2026-01-01" | grep -qE '^(401|403)$'; then
    echo "    ✓ /api/v1/reports/dsr.pdf mounted"
else
    echo "    ✗ /api/v1/reports/dsr.pdf not responding correctly"
    exit 1
fi

# Migration 002 schema sanity check — confirms ps_id column + new
# unique index landed. Reuses CFDSR_DB_* credentials from .env via
# MYSQL_PWD so we don't echo the password.
ENV_FILE=/opt/cyberfraud/backend/.env
DB_USER=$(grep -E '^CFDSR_DB_USER='     "$ENV_FILE" | tail -1 | cut -d'=' -f2-)
DB_PASS=$(grep -E '^CFDSR_DB_PASSWORD=' "$ENV_FILE" | tail -1 | cut -d'=' -f2-)
DB_NAME=$(grep -E '^CFDSR_DB_NAME='     "$ENV_FILE" | tail -1 | cut -d'=' -f2-)
: "${DB_USER:=root}"; : "${DB_NAME:=cyber_fraud_dsr}"

# Count of cases rows with NULL ps_id MUST be 0 (column is NOT NULL after
# migration 002, but check belt-and-braces in case someone re-ran with a
# partially-applied schema).
NULL_PS=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM cases WHERE ps_id IS NULL" 2>/dev/null || echo "ERROR")
if [ "$NULL_PS" = "0" ]; then
    echo "    ✓ cases.ps_id present and fully populated"
else
    echo "    ✗ cases.ps_id check failed (got: $NULL_PS) — migration 002 may have only partially applied"
    exit 1
fi

# New unique index in place?
IDX=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='cases' AND INDEX_NAME='uq_case_unit_ps_fir'" 2>/dev/null || echo "ERROR")
if [ "$IDX" != "0" ] && [ "$IDX" != "ERROR" ]; then
    echo "    ✓ uq_case_unit_ps_fir unique index in place"
else
    echo "    ✗ uq_case_unit_ps_fir unique index missing — migration 002 did not complete"
    exit 1
fi

# Migration 003 schema sanity check — victims table present + UNIQUE (case_id).
VICTIMS_TABLE=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='victims'" 2>/dev/null || echo "ERROR")
if [ "$VICTIMS_TABLE" = "1" ]; then
    echo "    ✓ victims table present"
else
    echo "    ✗ victims table missing — migration 003 did not complete"
    exit 1
fi
VICTIMS_UQ=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='victims' AND INDEX_NAME='uq_victims_case_id'" 2>/dev/null || echo "ERROR")
if [ "$VICTIMS_UQ" != "0" ] && [ "$VICTIMS_UQ" != "ERROR" ]; then
    echo "    ✓ uq_victims_case_id unique index in place"
else
    echo "    ✗ uq_victims_case_id unique index missing — migration 003 incomplete"
    exit 1
fi

# Migration 006 schema sanity check — cases.is_financial column present and
# defaulted to 1 (Financial) for all existing rows.
IS_FIN_COL=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='cases' AND COLUMN_NAME='is_financial'" 2>/dev/null || echo "ERROR")
if [ "$IS_FIN_COL" = "1" ]; then
    echo "    ✓ cases.is_financial column present"
else
    echo "    ✗ cases.is_financial column missing — migration 006 did not complete"
    exit 1
fi
NULL_IS_FIN=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM cases WHERE is_financial IS NULL" 2>/dev/null || echo "ERROR")
if [ "$NULL_IS_FIN" = "0" ]; then
    echo "    ✓ cases.is_financial fully populated (no NULLs)"
else
    echo "    ✗ cases.is_financial has $NULL_IS_FIN NULL rows — backfill incomplete"
    exit 1
fi

# Migration 007 schema sanity check — daily_nil_declarations table present
# with the (unit_id, ps_id, nil_date) uniqueness in place.
NIL_TABLE=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='daily_nil_declarations'" 2>/dev/null || echo "ERROR")
if [ "$NIL_TABLE" = "1" ]; then
    echo "    ✓ daily_nil_declarations table present"
else
    echo "    ✗ daily_nil_declarations table missing — migration 007 did not complete"
    exit 1
fi
NIL_UQ=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='daily_nil_declarations' AND INDEX_NAME='uq_nil_unit_ps_date'" 2>/dev/null || echo "ERROR")
if [ "$NIL_UQ" != "0" ] && [ "$NIL_UQ" != "ERROR" ]; then
    echo "    ✓ uq_nil_unit_ps_date unique index in place"
else
    echo "    ✗ uq_nil_unit_ps_date unique index missing — migration 007 incomplete"
    exit 1
fi

# /api/v1/nil/today must be mounted (we don't have a session, so 401/403 is fine)
if curl -sk --max-time 5 -o /dev/null -w "%{http_code}" https://localhost/api/v1/nil/today | grep -qE '^(401|403)$'; then
    echo "    ✓ /api/v1/nil/today mounted"
else
    echo "    ✗ /api/v1/nil/today not responding correctly"
    exit 1
fi

# Migration 009 schema sanity check — All Accounts feature tables + the
# per-PS Serial No unique index.
ALL_ACC_TABLE=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='all_accounts'" 2>/dev/null || echo "ERROR")
if [ "$ALL_ACC_TABLE" = "1" ]; then
    echo "    ✓ all_accounts table present"
else
    echo "    ✗ all_accounts table missing — migration 009 did not complete"
    exit 1
fi
HERDER_TABLE=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='all_account_mule_herders'" 2>/dev/null || echo "ERROR")
if [ "$HERDER_TABLE" = "1" ]; then
    echo "    ✓ all_account_mule_herders table present"
else
    echo "    ✗ all_account_mule_herders table missing — migration 009 did not complete"
    exit 1
fi
ALL_ACC_UQ=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='all_accounts' AND INDEX_NAME='uq_all_account_ps_serial'" 2>/dev/null || echo "ERROR")
if [ "$ALL_ACC_UQ" != "0" ] && [ "$ALL_ACC_UQ" != "ERROR" ]; then
    echo "    ✓ uq_all_account_ps_serial unique index in place"
else
    echo "    ✗ uq_all_account_ps_serial unique index missing — migration 009 incomplete"
    exit 1
fi

# /api/v1/all-accounts must be mounted (401/403 is fine — no session)
if curl -sk --max-time 5 -o /dev/null -w "%{http_code}" https://localhost/api/v1/all-accounts | grep -qE '^(401|403)$'; then
    echo "    ✓ /api/v1/all-accounts mounted"
else
    echo "    ✗ /api/v1/all-accounts not responding correctly"
    exit 1
fi

# /api/v1/dashboard/accounts-summary must be mounted too.
if curl -sk --max-time 5 -o /dev/null -w "%{http_code}" "https://localhost/api/v1/dashboard/accounts-summary?date=2026-01-01" | grep -qE '^(401|403)$'; then
    echo "    ✓ /api/v1/dashboard/accounts-summary mounted"
else
    echo "    ✗ /api/v1/dashboard/accounts-summary not responding correctly"
    exit 1
fi

# Migration 010 schema sanity check — branch_district column landed on
# all_accounts. Nullable, so no NOT NULL check; presence is enough.
BRANCH_DISTRICT_COL=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='all_accounts' AND COLUMN_NAME='branch_district'" 2>/dev/null || echo "ERROR")
if [ "$BRANCH_DISTRICT_COL" = "1" ]; then
    echo "    ✓ all_accounts.branch_district column present"
else
    echo "    ✗ all_accounts.branch_district column missing — migration 010 did not complete"
    exit 1
fi

# Migration 011 schema sanity check — account_statement_path column
# landed on all_accounts. Nullable, so no NOT NULL check.
STATEMENT_COL=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='all_accounts' AND COLUMN_NAME='account_statement_path'" 2>/dev/null || echo "ERROR")
if [ "$STATEMENT_COL" = "1" ]; then
    echo "    ✓ all_accounts.account_statement_path column present"
else
    echo "    ✗ all_accounts.account_statement_path column missing — migration 011 did not complete"
    exit 1
fi

# Upload signature middleware must be gating /uploads/* — an unsigned
# GET to any path under the mount should now return 403 (was 200/404
# with the old public StaticFiles mount). Path doesn't need to exist —
# middleware rejects BEFORE the file lookup.
UPLOAD_UNSIGNED=$(curl -sk --max-time 5 -o /dev/null -w "%{http_code}" \
    https://localhost/uploads/photos/does-not-exist.jpg)
if [ "$UPLOAD_UNSIGNED" = "403" ]; then
    echo "    ✓ /uploads/* rejects unsigned request (403) — signature middleware active"
else
    echo "    ✗ /uploads/* returned $UPLOAD_UNSIGNED for an unsigned request — signature middleware missing/broken"
    exit 1
fi

# Statement upload endpoint must be mounted (401/403 fine — no session).
# Multipart upload endpoints reject GET; a bare curl gets 405, so we check
# for the presence of any auth/method error rather than 401 specifically.
STATEMENT_CODE=$(curl -sk --max-time 5 -o /dev/null -w "%{http_code}" \
    https://localhost/api/v1/uploads/statement)
if echo "$STATEMENT_CODE" | grep -qE '^(401|403|405|422)$'; then
    echo "    ✓ /api/v1/uploads/statement mounted (returned $STATEMENT_CODE)"
else
    echo "    ✗ /api/v1/uploads/statement not responding correctly (got $STATEMENT_CODE)"
    exit 1
fi

# Drill-down endpoint that powers the per-PS detail grid + Excel/PDF export.
# Query params must be present so the request reaches the auth dependency
# (Pydantic-validated params run before dependencies in FastAPI).
if curl -sk --max-time 5 -o /dev/null -w "%{http_code}" \
        "https://localhost/api/v1/dashboard/accounts-details-by-ps?unit_id=1&ps_id=1&date=2026-01-01" \
        | grep -qE '^(401|403)$'; then
    echo "    ✓ /api/v1/dashboard/accounts-details-by-ps mounted"
else
    echo "    ✗ /api/v1/dashboard/accounts-details-by-ps not responding correctly"
    exit 1
fi

echo
echo "================================================================"
echo "  ✓ Incremental update complete."
echo
echo "  This deploy adds the All Accounts feature — a new sidebar"
echo "  section (New Account / Update Account) + Account Details"
echo "  Dashboard, now with click-through drill-down per Police"
echo "  Station and Excel / PDF export of the detail grid. Third"
echo "  account type 'Non-Mule' now available alongside Victim + Mule."
echo "  Entry form now captures 'Branch District' (dropdown of KA"
echo "  districts) alongside Branch Name, plus an 'Account Statement'"
echo "  upload widget (PDF / Excel, 5MB cap) — both surface in the"
echo "  drill-down grid + Excel/PDF export. FIR No is now format-"
echo "  validated (XXXX/XXXX, e.g. 0001/2026) and Account No / Mobile"
echo "  are numeric-only with length checks."
echo
echo "  /uploads/* is no longer public — every file URL now carries an"
echo "  HMAC-signed 1-hour expiry. Leaked URLs (in exports, screenshots)"
echo "  die fast. Deleting an account row now unlinks its files too."
echo "  Nightly orphan cleanup: venv/bin/python sweep_orphaned_uploads.py"
echo "  Pre-deploy backup now also archives uploads/ (see backup-uploads.sh)."
echo
echo "  The former 'Dashboard' link is now 'DSR Dashboard' and the"
echo "  'Mule Accounts Data' section header is renamed 'NCRP Data'"
echo "  (URLs / API paths unchanged)."
echo "================================================================"
