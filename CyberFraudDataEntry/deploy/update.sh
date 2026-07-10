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
# Take an ad-hoc backup of cyber_fraud_dsr just before any schema
# changes. Re-using deploy/backup-db.sh keeps the format identical to
# nightly backups so restore is a one-liner if anything regresses.
# Safe to run even when no migration changes apply — backup-db.sh
# always writes a fresh timestamped file and prunes older than 14d.
echo
echo "=== 3. Pre-migration DB backup ==="
sudo bash "$SOURCE/deploy/backup-db.sh"

# ── 4. Run additive DB migrations ────────────────────────────────────
echo
echo "=== 4. Run additive DB migrations 001 → 004, 006, 007, 008 (idempotent) ==="
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

echo
echo "================================================================"
echo "  ✓ Incremental update complete."
echo
echo "  Reminder: tell users of the renamed PS to pick"
echo "  'South East CEN PS' on the login dropdown."
echo "================================================================"
