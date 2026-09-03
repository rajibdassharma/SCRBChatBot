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
#   3. Run additive DB migrations (idempotent — INFORMATION_SCHEMA
#      checks mean each migration's a no-op when already applied)
#   4. Build the frontend (npm install + npm run build)
#   5. Sync backend/ + frontend/dist/ from source to runtime
#   6. Restart the backend systemd service
#   7. Ensure nginx proxies /uploads/* to the backend (auto-inserts
#      the location block once if missing; idempotent afterwards)
#   8. Self-verify: service active, /health responding, schema sane
#
# NOTE: pre-migration DB + uploads backup was removed 2026-07-24.
# Nightly systemd timers (cyberfraud-backup.{service,timer}) still
# run — run backup-db.sh / backup-uploads.sh by hand before a risky
# deploy if you want the extra insurance snapshot.
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

# ── 3. Run additive DB migrations ────────────────────────────────────
echo
echo "=== 3. Run additive DB migrations 001 → 004, 006 → 027 (idempotent) ==="
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
    venv/bin/python -m migrations.012_add_layer_and_state_to_all_accounts
    venv/bin/python -m migrations.013_add_portals_dsr_entries
    venv/bin/python -m migrations.014_add_daily_work_entries
    venv/bin/python -m migrations.015_add_sections_to_cases
    venv/bin/python -m migrations.016_add_crime_type_expansion
    venv/bin/python -m migrations.017_add_victim_and_accused_accounts
    venv/bin/python -m migrations.018_rename_cen_to_cyber_in_ps_names
    venv/bin/python -m migrations.019_add_upload_analysis_tables
    venv/bin/python -m migrations.020_account_statement_summary
    venv/bin/python -m migrations.021_mule_account_links
    venv/bin/python -m migrations.022_statement_chain_ok
    venv/bin/python -m migrations.023_summary_untested_totals
    venv/bin/python -m migrations.024_crypto_transactions
    venv/bin/python -m migrations.025_ifsc_branch
    venv/bin/python -m migrations.026_widen_summary_money
    venv/bin/python -m migrations.027_unlinked_counterparty
"

# ── 4. Build the frontend ────────────────────────────────────────────
echo
echo "=== 4. Build frontend (npm install + npm run build) ==="
cd "$SOURCE/frontend"
npm install --silent
npm run build
echo "    dist/ built:"
ls -la "$SOURCE/frontend/dist/" | head -10

# ── 5. Sync code from source to runtime ──────────────────────────────
echo
echo "=== 5. Sync backend + frontend dist + deploy to $RUNTIME ==="
sudo cp -r "$SOURCE/backend" "$RUNTIME/"
sudo cp -r "$SOURCE/frontend" "$RUNTIME/"

# deploy/ was NOT synced until 2026-08-12, and the omission was silent
# and expensive.
#
# The systemd timers execute /opt/cyberfraud/deploy/backup-all.sh, which
# is this copy — not the one in the git clone. So every fix to a backup
# script sat in /opt/scrb doing nothing, and the only thing that ever
# refreshed them was install-backup.sh, run by hand months apart.
#
# What it cost: backup-db.sh gained --ignore-table for the five derived
# analysis tables, the server never received it, and once
# import-analysis.sh started populating those tables on production the
# nightly dump silently grew from 18 MB to 46 MB. Nothing failed; the
# backups were simply carrying ~76 MB of data that is rebuildable by
# design. Left alone it would keep growing with the corpus.
#
# Syncing here means a deploy-script fix reaches the server the same way
# a backend fix does: git pull, update.sh, done.
sudo cp -r "$SOURCE/deploy" "$RUNTIME/"
# Executable bits: git stores most of these 100644, and the timers call
# them via `bash <script>` so it does not matter there — but a human
# running ./backup-db.sh should not get "permission denied".
sudo chmod +x "$RUNTIME"/deploy/*.sh
sudo chown -R cyberfraud:cyberfraud "$RUNTIME/backend" "$RUNTIME/frontend" "$RUNTIME/deploy"

# ── 6. Restart backend ───────────────────────────────────────────────
echo
echo "=== 6. Restart backend service ==="
sudo systemctl restart "$SVC"
sleep 2
sudo systemctl is-active "$SVC"

# ── 7. Nginx: ensure /uploads/ is proxied to backend (idempotent) ────
# The backend serves file downloads at /uploads/photos/* and
# /uploads/statements/* — but nginx by default only forwards /api/*.
# Without this, browser requests to /uploads/xxx hit the SPA fallback
# and get caught by ProtectedRoute → redirected to /login. We insert
# the location block once, right before the existing /api/ block, so
# it lands in the same server context (HTTPS listener). Idempotent:
# a re-run notices the block is already there and does nothing.
echo
echo "=== 7. Nginx /uploads/ proxy ==="
SITE_LINK=$(ls /etc/nginx/sites-enabled/*cyberfraud* 2>/dev/null | head -1 || true)
if [ -z "$SITE_LINK" ]; then
    echo "    ⚠  no cyberfraud site under /etc/nginx/sites-enabled/ — skipping."
    echo "       Add the location /uploads/ block manually if drill-down file links redirect to login."
else
    # Follow the symlink so we edit the real file in sites-available/.
    SITE_CONF=$(readlink -f "$SITE_LINK" 2>/dev/null || echo "$SITE_LINK")

    if grep -q "location /uploads/" "$SITE_CONF"; then
        echo "    ✓ /uploads/ location already present in $SITE_CONF"
    elif ! grep -q "location /api/" "$SITE_CONF"; then
        echo "    ⚠  no 'location /api/' anchor in $SITE_CONF — refusing to guess where to insert."
        echo "       Add the /uploads/ block manually and re-run."
    else
        BACKUP="$SITE_CONF.bak.$(date +%s)"
        NEW_CONF=$(mktemp)
        echo "    + inserting /uploads/ location before /api/ in $SITE_CONF"

        # Insert before the first `location /api/` line, matching that
        # line's leading whitespace so the block stays properly indented.
        awk '
            /location \/api\// && !inserted {
                match($0, /^[[:space:]]*/); pad = substr($0, RSTART, RLENGTH)
                print pad "# cyberfraud: added by deploy/update.sh -- proxy /uploads/* to backend"
                print pad "location /uploads/ {"
                print pad "    proxy_pass http://127.0.0.1:8000;"
                print pad "    proxy_set_header Host $host;"
                print pad "    proxy_set_header X-Real-IP $remote_addr;"
                print pad "    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;"
                print pad "    proxy_set_header X-Forwarded-Proto $scheme;"
                print pad "}"
                print ""
                inserted = 1
            }
            { print }
        ' "$SITE_CONF" > "$NEW_CONF"

        cp "$SITE_CONF" "$BACKUP"
        cat "$NEW_CONF" > "$SITE_CONF"
        rm -f "$NEW_CONF"

        if sudo nginx -t; then
            sudo systemctl reload nginx
            echo "    ✓ nginx reloaded (pre-edit backup: $BACKUP)"
        else
            echo "    ✗ nginx -t FAILED — restoring $BACKUP"
            cp "$BACKUP" "$SITE_CONF"
            sudo nginx -t
            exit 1
        fi
    fi
fi

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
#
# The `|| true` on each grep is CRITICAL: under `set -euo pipefail`,
# a `grep` that finds no match returns 1 and kills the whole script
# with no error message. If .env is missing a variable (or the file
# itself is absent), we just fall back to the defaults below.
ENV_FILE=/opt/cyberfraud/backend/.env
DB_USER=$( (grep -E '^CFDSR_DB_USER='     "$ENV_FILE" 2>/dev/null || true) | tail -1 | cut -d'=' -f2- )
DB_PASS=$( (grep -E '^CFDSR_DB_PASSWORD=' "$ENV_FILE" 2>/dev/null || true) | tail -1 | cut -d'=' -f2- )
DB_NAME=$( (grep -E '^CFDSR_DB_NAME='     "$ENV_FILE" 2>/dev/null || true) | tail -1 | cut -d'=' -f2- )
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

# Portals DSR endpoints must be mounted (401/403 fine — no session).
if curl -sk --max-time 5 -o /dev/null -w "%{http_code}" "https://localhost/api/v1/portals-dsr" | grep -qE '^(401|403)$'; then
    echo "    ✓ /api/v1/portals-dsr mounted"
else
    echo "    ✗ /api/v1/portals-dsr not responding correctly"
    exit 1
fi
if curl -sk --max-time 5 -o /dev/null -w "%{http_code}" "https://localhost/api/v1/dashboard/portals-summary?from=2026-01-01&to=2026-01-31" | grep -qE '^(401|403)$'; then
    echo "    ✓ /api/v1/dashboard/portals-summary mounted"
else
    echo "    ✗ /api/v1/dashboard/portals-summary not responding correctly"
    exit 1
fi

# Top-banks dashboard endpoint must be mounted (401/403 fine — no session).
if curl -sk --max-time 5 -o /dev/null -w "%{http_code}" "https://localhost/api/v1/dashboard/accounts-top-banks?date=2026-01-01&limit=10" | grep -qE '^(401|403)$'; then
    echo "    ✓ /api/v1/dashboard/accounts-top-banks mounted"
else
    echo "    ✗ /api/v1/dashboard/accounts-top-banks not responding correctly"
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

# Migration 013 schema sanity check — portals_dsr_entries table
# with 25 metric columns and its (unit_id, ps_id, report_date) index.
PORTALS_TABLE=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='portals_dsr_entries'" 2>/dev/null || echo "ERROR")
if [ "$PORTALS_TABLE" = "1" ]; then
    echo "    ✓ portals_dsr_entries table present"
else
    echo "    ✗ portals_dsr_entries table missing — migration 013 did not complete"
    exit 1
fi
PORTALS_COLS=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS \
        WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='portals_dsr_entries' \
          AND COLUMN_NAME REGEXP '^(ncrp|samanvaya|sahayog|grm|mrm|bharatpol|ocwc|ncmec)_'" 2>/dev/null || echo "ERROR")
if [ "$PORTALS_COLS" = "25" ]; then
    echo "    ✓ portals_dsr_entries has all 25 metric columns"
else
    echo "    ✗ portals_dsr_entries metric column count = $PORTALS_COLS (expected 25)"
    exit 1
fi

# Migration 012 schema sanity check — layer + branch_state columns
# on all_accounts. Both nullable, so presence is enough.
LAYER_COL=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='all_accounts' AND COLUMN_NAME='layer'" 2>/dev/null || echo "ERROR")
STATE_COL=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='all_accounts' AND COLUMN_NAME='branch_state'" 2>/dev/null || echo "ERROR")
if [ "$LAYER_COL" = "1" ] && [ "$STATE_COL" = "1" ]; then
    echo "    ✓ all_accounts.layer + branch_state columns present"
else
    echo "    ✗ layer=$LAYER_COL branch_state=$STATE_COL — migration 012 did not complete"
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

# Migration 014 schema sanity check — daily_work_entries table
# with its (unit_id, ps_id, fir_no, report_date) uniqueness in place.
DW_TABLE=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='daily_work_entries'" 2>/dev/null || echo "ERROR")
if [ "$DW_TABLE" = "1" ]; then
    echo "    ✓ daily_work_entries table present"
else
    echo "    ✗ daily_work_entries table missing — migration 014 did not complete"
    exit 1
fi
DW_UQ=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='daily_work_entries' AND INDEX_NAME='uq_daily_work_unit_ps_fir_date'" 2>/dev/null || echo "ERROR")
if [ "$DW_UQ" != "0" ] && [ "$DW_UQ" != "ERROR" ]; then
    echo "    ✓ uq_daily_work_unit_ps_fir_date unique index in place"
else
    echo "    ✗ uq_daily_work_unit_ps_fir_date unique index missing — migration 014 incomplete"
    exit 1
fi

# Migration 015 schema sanity check — cases.sections column landed.
# Nullable free-text (VARCHAR(500)); presence is enough.
SECTIONS_COL=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='cases' AND COLUMN_NAME='sections'" 2>/dev/null || echo "ERROR")
if [ "$SECTIONS_COL" = "1" ]; then
    echo "    ✓ cases.sections column present"
else
    echo "    ✗ cases.sections column missing — migration 015 did not complete"
    exit 1
fi

# Migration 016 schema sanity check — cases.crime_type widened
# (VARCHAR(30) → 200) AND cases.crime_type_other column added.
# The widen matters: without it the 31-entry classification list's
# longer values fail to insert with a data-truncated error.
CRIME_TYPE_LEN=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='cases' AND COLUMN_NAME='crime_type'" 2>/dev/null || echo "ERROR")
if [ "$CRIME_TYPE_LEN" -ge 200 ] 2>/dev/null; then
    echo "    ✓ cases.crime_type widened to VARCHAR($CRIME_TYPE_LEN)"
else
    echo "    ✗ cases.crime_type is VARCHAR($CRIME_TYPE_LEN) — migration 016 widen incomplete (need ≥ 200)"
    exit 1
fi
CRIME_OTHER_COL=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='cases' AND COLUMN_NAME='crime_type_other'" 2>/dev/null || echo "ERROR")
if [ "$CRIME_OTHER_COL" = "1" ]; then
    echo "    ✓ cases.crime_type_other column present"
else
    echo "    ✗ cases.crime_type_other column missing — migration 016 did not complete"
    exit 1
fi

# Migration 017 schema sanity check — victim_accounts + accused_accounts
# tables landed (multi-account capture on DSR -> New FIR, 2026-07-24).
VA_TBL=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='victim_accounts'" 2>/dev/null || echo "ERROR")
if [ "$VA_TBL" = "1" ]; then
    echo "    ✓ victim_accounts table present"
else
    echo "    ✗ victim_accounts table missing — migration 017 did not complete"
    exit 1
fi
AA_TBL=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='$DB_NAME' AND TABLE_NAME='accused_accounts'" 2>/dev/null || echo "ERROR")
if [ "$AA_TBL" = "1" ]; then
    echo "    ✓ accused_accounts table present"
else
    echo "    ✗ accused_accounts table missing — migration 017 did not complete"
    exit 1
fi

# Migration 018 data-sanity check — no standalone 'CEN' left in PS
# names. Uses REGEXP with \bCEN\b so 'CENTRAL JAIL' etc. are correctly
# excluded (that row is a legitimate CENTRAL, not the CEN acronym).
CEN_LEFT=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM police_stations WHERE station_name REGEXP '\\\\bCEN\\\\b'" 2>/dev/null || echo "ERROR")
if [ "$CEN_LEFT" = "0" ]; then
    echo "    ✓ police_stations.station_name has no standalone 'CEN' (migration 018 applied)"
else
    echo "    ✗ $CEN_LEFT rows still contain standalone 'CEN' — migration 018 did not complete"
    exit 1
fi

# Migrations 019-023 — the upload-analysis tables.
#
# These start EMPTY on production and stay that way: parsing runs on the
# analysis machine, and results arrive via deploy/import-analysis.sh.
# So the check is for STRUCTURE, never row counts — an empty table here
# is the correct state, not a failure.
#
# Without these tables the import has nowhere to land and fails with
# "table missing"; without the columns, it fails mid-swap having
# already emptied the live table.
for T in upload_ledger statement_transactions account_statement_summary \
         id_photo_hashes mule_account_link crypto_txn; do
    HAVE=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
        -e "SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema='$DB_NAME' AND table_name='$T'" 2>/dev/null || echo "ERROR")
    if [ "$HAVE" = "1" ]; then
        echo "    ✓ $T exists (migrations 019-021)"
    else
        echo "    ✗ $T missing — migrations 019-021 did not complete"
        exit 1
    fi
done

# Migration 022 — the per-row chain verdict column.
CHAIN_OK=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema='$DB_NAME' AND table_name='statement_transactions'
          AND column_name='chain_ok'" 2>/dev/null || echo "ERROR")
if [ "$CHAIN_OK" = "1" ]; then
    echo "    ✓ statement_transactions.chain_ok present (migration 022)"
else
    echo "    ✗ statement_transactions.chain_ok missing — migration 022 did not complete"
    exit 1
fi

# Migration 023 — the untested_* totals the dashboards read. All three,
# because the endpoint selects untested_txns and the import copies every
# column: a partial migration would pass a one-column check and then
# fail the import halfway through the swap.
UNTESTED=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema='$DB_NAME' AND table_name='account_statement_summary'
          AND column_name IN ('untested_txns','untested_debit','untested_credit')" 2>/dev/null || echo "ERROR")
if [ "$UNTESTED" = "3" ]; then
    echo "    ✓ account_statement_summary.untested_* present (migration 023)"
else
    echo "    ✗ expected 3 untested_* columns, found $UNTESTED — migration 023 did not complete"
    exit 1
fi

# Migration 026: the summary's raw money columns must be wide enough to
# hold a total that includes chain-REJECTED rows. 439 such rows carry
# amounts up to Rs 1,000 trillion from a text-PDF misparse, and at
# DECIMAL(18,2) a few of them in one account overflowed the column and
# killed the nightly run at the summary step.
WIDE=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME"     -e "SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema='$DB_NAME' AND table_name='account_statement_summary'
          AND column_name IN ('debit','credit','verified_debit',
                              'verified_credit','untested_debit','untested_credit')
          AND column_type = 'decimal(24,2)'" 2>/dev/null || echo "ERROR")
if [ "$WIDE" = "6" ]; then
    echo "    ✓ summary money columns are decimal(24,2) (migration 026)"
else
    echo "    ✗ expected 6 decimal(24,2) columns, found $WIDE — migration 026 did not complete"
    exit 1
fi

# Migration 027: the table behind the "named recipients with no account
# number" panel on Graphical Analysis. It exists so that screen never
# reads statement_transactions again -- the version that did took 15.6 s
# on one FIR and returned a gateway timeout in production.
#
# Checks the TABLE, not its contents. It is filled by the nightly
# analysis run, so on the deploy that creates it the table is correctly
# empty and the panel correctly hidden.
UNLINKED=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME"     -e "SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema='$DB_NAME'
          AND table_name='account_unlinked_counterparty'" 2>/dev/null || echo "ERROR")
if [ "$UNLINKED" = "1" ]; then
    echo "    ✓ account_unlinked_counterparty exists (migration 027)"
else
    echo "    ✗ account_unlinked_counterparty missing — migration 027 did not complete"
    exit 1
fi

CRYPTO=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema='$DB_NAME' AND table_name='crypto_txn'" 2>/dev/null || echo "ERROR")
if [ "$CRYPTO" = "1" ]; then
    echo "    ✓ crypto_txn present (migration 024)"
else
    echo "    ✗ crypto_txn missing — migration 024 did not complete"
    exit 1
fi

# ifsc_branch is MASTER data, not derived: it comes from outside and
# production has no route to the internet to re-fetch it. The check is
# for the table AND for rows -- an empty directory resolves nothing and
# would look identical to a working one on every screen.
IFSCN=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME"     -e "SELECT COUNT(*) FROM ifsc_branch" 2>/dev/null || echo "ERROR")
if [ "$IFSCN" = "ERROR" ]; then
    echo "    ✗ ifsc_branch missing — migration 025 did not complete"
    exit 1
elif [ "$IFSCN" -lt 100000 ]; then
    echo "    ! ifsc_branch has only $IFSCN rows — load it with:"
    echo "      python -m analysis.load_ifsc proddata/IFSC.csv --source <tag>"
else
    echo "    ✓ ifsc_branch loaded ($IFSCN branches)"
fi

# The RUNTIME copy of backup-db.sh must exclude the derived analysis
# tables. Checked here rather than trusted, because the failure mode is
# silent: nothing errors, the nightly dump just quietly grows.
#
# It reached 46 MB from 18 MB before anyone noticed, and only because
# the size was watched. statement_transactions is 12.5 GB on the
# analysis machine — if production ever carries it, an unfixed script
# would try to dump that too.
# The exclusion list is read from the ARRAY, not grepped out of the
# whole file. Every one of these names now appears in that script's
# comments explaining why it is or is not excluded, so a file-wide grep
# would match the explanation and report success whatever the array said.
EXCL=$(sed -n '/^DERIVED_TABLES=(/,/^)/p' "$RUNTIME/deploy/backup-db.sh" 2>/dev/null        | grep -oE '^[[:space:]]+[a-z_]+' | tr -d '[:space:]')
EXCL_FAIL=0

# Must be excluded: 24.8 GB, and a pure function of the PDFs that
# backup-uploads.sh already captures.
if ! echo "$EXCL" | grep -qx "statement_transactions"; then
    echo "    ✗ backup-db.sh does not exclude statement_transactions — the"
    echo "      nightly dump will try to carry 24.8 GB of parsed rows"
    EXCL_FAIL=1
fi

# Must NOT be excluded. Production GENERATES these now, so they are the
# only copy in existence: excluding one means a restore comes back with
# empty dashboards and hours of re-parsing to recover. ifsc_branch is
# worse still — master data from outside, and this server has no route
# to the internet to re-fetch it.
for T in account_statement_summary upload_ledger id_photo_hashes          mule_account_link crypto_txn ifsc_branch; do
    if echo "$EXCL" | grep -qx "$T"; then
        echo "    ✗ backup-db.sh EXCLUDES $T — analysis runs on this server"
        echo "      now, so that table exists nowhere else and a restore"
        echo "      would lose it"
        EXCL_FAIL=1
    fi
done

if [ "$EXCL_FAIL" -eq 0 ]; then
    echo "    ✓ backup-db.sh excludes statement_transactions only"
else
    exit 1
fi

# Daily Work Done routes (mounted before /{entry_id} so /dashboard resolves).
if curl -sk --max-time 5 -o /dev/null -w "%{http_code}" https://localhost/api/v1/daily-work/history | grep -qE '^(401|403)$'; then
    echo "    ✓ /api/v1/daily-work/history mounted"
else
    echo "    ✗ /api/v1/daily-work/history not responding correctly"
    exit 1
fi
if curl -sk --max-time 5 -o /dev/null -w "%{http_code}" https://localhost/api/v1/daily-work/dashboard | grep -qE '^(401|403)$'; then
    echo "    ✓ /api/v1/daily-work/dashboard mounted (route order correct — not shadowed by /{entry_id})"
else
    echo "    ✗ /api/v1/daily-work/dashboard not responding correctly"
    exit 1
fi

# FIR Dashboard endpoint + its PDF/Excel exports.
if curl -sk --max-time 5 -o /dev/null -w "%{http_code}" \
        "https://localhost/api/v1/dashboard/fir-ps-performance?from=2026-01-01&to=2026-01-31" \
        | grep -qE '^(401|403)$'; then
    echo "    ✓ /api/v1/dashboard/fir-ps-performance mounted"
else
    echo "    ✗ /api/v1/dashboard/fir-ps-performance not responding correctly"
    exit 1
fi
if curl -sk --max-time 5 -o /dev/null -w "%{http_code}" \
        "https://localhost/api/v1/reports/fir-ps-performance.pdf?from=2026-01-01&to=2026-01-31" \
        | grep -qE '^(401|403)$'; then
    echo "    ✓ /api/v1/reports/fir-ps-performance.pdf mounted"
else
    echo "    ✗ /api/v1/reports/fir-ps-performance.pdf not responding correctly"
    exit 1
fi
if curl -sk --max-time 5 -o /dev/null -w "%{http_code}" \
        "https://localhost/api/v1/reports/fir-ps-performance.xlsx?from=2026-01-01&to=2026-01-31" \
        | grep -qE '^(401|403)$'; then
    echo "    ✓ /api/v1/reports/fir-ps-performance.xlsx mounted"
else
    echo "    ✗ /api/v1/reports/fir-ps-performance.xlsx not responding correctly"
    exit 1
fi

# Account Details map view — region rollup endpoint (2026-07-31).
# 401/403 is the expected unauthenticated answer. The `scope` param is
# whitelisted server-side, so an unknown value must be rejected rather
# than reaching the column lookup; we can't prove the 422 without a
# session (auth runs first), so the mount check is what we assert here.
if curl -sk --max-time 5 -o /dev/null -w "%{http_code}" \
        "https://localhost/api/v1/dashboard/accounts-geo?date=2026-01-01&scope=state&account_type=All" \
        | grep -qE '^(401|403)$'; then
    echo "    ✓ /api/v1/dashboard/accounts-geo mounted"
else
    echo "    ✗ /api/v1/dashboard/accounts-geo not responding correctly"
    exit 1
fi

# ── NULL fir_no → "" serializer fix (2026-07-31) ─────────────────────
# Bug: create_case coerces a blank FIR to NULL (so multiple FIR-less
# petitions can coexist under uq_case_unit_ps_fir), but CaseResponse /
# CaseListItem declare `fir_no: str`. The NULL reached Pydantic and
# raised ResponseValidationError -> 500, AFTER db.commit(). The case
# was saved, the operator saw an error, retried, and each retry wrote
# another row (the duplicate pre-check is `if fir_no:` — skipped when
# blank). The same defect existed in the mule-report serializers.
#
# There's no unauthenticated endpoint that exercises this, so we assert
# on the deployed source instead — which doubles as proof that step 5's
# sync actually landed the new code in $RUNTIME.
echo
echo "    -- NULL fir_no serializer fix --"
# NOTE on the capture idiom: `grep -c` prints "0" AND exits 1 when there
# are no matches, so a bare `|| echo 0` would append a SECOND zero and
# yield "0\n0". Use `|| true` (grep already printed the count) and only
# default to 0 when the output is empty — i.e. the file was unreadable.
CASE_COALESCE=$(grep -c '"fir_no": c.fir_no or ""' "$RUNTIME/backend/api/routes_case.py" 2>/dev/null || true)
: "${CASE_COALESCE:=0}"
if [ "$CASE_COALESCE" = "2" ]; then
    echo "    ✓ routes_case.py: both serializers coalesce NULL fir_no"
else
    echo "    ✗ routes_case.py has $CASE_COALESCE/2 fir_no coalesces — runtime is stale or the fix regressed"
    exit 1
fi
MULE_COALESCE=$(grep -c '"fir_no": r.fir_no or ""' "$RUNTIME/backend/api/routes_mule_report.py" 2>/dev/null || true)
: "${MULE_COALESCE:=0}"
if [ "$MULE_COALESCE" = "2" ]; then
    echo "    ✓ routes_mule_report.py: both serializers coalesce NULL fir_no"
else
    echo "    ✗ routes_mule_report.py has $MULE_COALESCE/2 fir_no coalesces — runtime is stale or the fix regressed"
    exit 1
fi

# Informational only — NEVER exits non-zero. FIR-less petitions are
# legal; we just want the operator to see how many exist and whether
# the 500-retry loop left duplicates behind.
NULL_FIR=$(MYSQL_PWD="$DB_PASS" mysql --skip-column-names --user="$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM cases WHERE fir_no IS NULL OR fir_no = ''" 2>/dev/null || echo "?")
echo "    i  cases with no FIR number: $NULL_FIR (legal for petitions)"

# Retries from the 500 submit an identical payload seconds apart, so
# (unit_id, ps_id, petition_no, registration_date, crime_type) is a
# good-enough duplicate key. Anything listed here needs a human call —
# this script does NOT delete rows.
echo "    i  checking for duplicates left by the pre-fix retry loop..."
# Capture the exit status separately: a failed query (bad password,
# missing .env) returns empty output, and treating that as "no
# duplicates" would be a false all-clear. `|| DUP_OK=0` also keeps
# set -e from aborting the deploy on a query error.
DUP_OK=1
DUP_ROWS=$(MYSQL_PWD="$DB_PASS" mysql --table --user="$DB_USER" "$DB_NAME" -e "
    SELECT unit_id, ps_id,
           IFNULL(petition_no,'(none)') AS petition_no,
           IFNULL(registration_date,'(none)') AS reg_date,
           COUNT(*) AS copies,
           MIN(created_at) AS first_seen,
           MAX(created_at) AS last_seen
      FROM cases
     WHERE (fir_no IS NULL OR fir_no = '')
     GROUP BY unit_id, ps_id, petition_no, registration_date, crime_type
    HAVING COUNT(*) > 1
     ORDER BY last_seen DESC" 2>/dev/null) || DUP_OK=0
if [ "$DUP_OK" != "1" ]; then
    echo "       ⚠  duplicate check could not run (DB credentials from"
    echo "          $ENV_FILE) — run the query by hand. NOT a deploy failure."
elif [ -n "$DUP_ROWS" ]; then
    echo "$DUP_ROWS" | sed 's/^/       /'
    echo "       ⚠  duplicate FIR-less cases above — review and delete by hand."
    echo "          List one group's rows with:"
    echo "            SELECT id, created_at, submitted_by FROM cases"
    echo "             WHERE (fir_no IS NULL OR fir_no='') AND ps_id=<ps> AND unit_id=<unit>"
    echo "             ORDER BY created_at;"
else
    echo "       ✓ no duplicate FIR-less cases found"
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
echo "  Entry form now captures 'Branch State' (dropdown of Indian"
echo "  states — if not Karnataka, the District dropdown disables),"
echo "  'Branch District' (KA-only dropdown), 'Layer' (1-15 dropdown),"
echo "  plus an 'Account Statement' upload widget (PDF / Excel, 5MB)."
echo "  All new fields surface in the drill-down grid + Excel/PDF"
echo "  export. FIR No is now format-validated (XXXX/XXXX, e.g."
echo "  0001/2026) and Account No / Mobile are numeric-only with"
echo "  length checks. Update list now shows Serial No ascending."
echo
echo "  Dashboard Overview: 7 colour-accented KPI cards, Top-10 PS"
echo "  bar chart, account-type pie, Top-10 Banks bar chart, and"
echo "  reporting-coverage banner. Drill-down + Excel/PDF export"
echo "  reachable from the same PS comparison table."
echo
echo "  NEW: Portals DSR feature (2026-07-21) — per-PS daily counters"
echo "  for 8 external portals (NCRP / Samanvaya / Sahayog / GRM / MRM"
echo "  / Bharatpol / OCWC / NCMEC Tipline). Tabbed entry form with"
echo "  save-draft per tab, submit on the last; multiple entries per"
echo "  PS per day are legal (shift-based). Admin dashboard SUM-"
echo "  aggregates across the window with per-portal tiles + Top-10 PS."
echo
echo "  /uploads/* is no longer public — every file URL now carries an"
echo "  HMAC-signed 1-hour expiry. Leaked URLs (in exports, screenshots)"
echo "  die fast. Deleting an account row now unlinks its files too."
echo "  Nightly orphan cleanup: venv/bin/python sweep_orphaned_uploads.py"
echo
echo "  The former 'Dashboard' link is now 'DSR Dashboard' and the"
echo "  'Mule Accounts Data' section header is renamed 'NCRP Data'"
echo "  (URLs / API paths unchanged)."
echo
echo "  NEW (2026-07-22 — this deploy):"
echo "  • DSR module tile — merges Portals DSR + Investigation Log +"
echo "    a new 'New FIR' entry point under one sidebar."
echo "  • FIR Dashboard (DSR) — per-PS performance table with"
echo "    sortable columns, Today/7d/30d/90d chips, Excel + PDF"
echo "    downloads served from the reports/ module."
echo "  • Daily Work Done — full CRUD + admin KPI dashboard for"
echo "    per-FIR-per-day activity (notices / lien / unlien /"
echo "    arrests / statements / final report). Migration 014."
echo "  • Cases: 'Sections' free-text field alongside FIR No + Crime"
echo "    Type (migration 015). Crime Type is now the 31-entry KSP"
echo "    Cyber Crime classification with 'Others → free text'"
echo "    (migration 016; widens crime_type to VARCHAR(200) + adds"
echo "    crime_type_other)."
echo "  • FIR No format validation — shared XXXX/YYYY validator"
echo "    wired into every FIR entry point (Cases, New FIR, Daily"
echo "    Work, All Accounts). Retroactive rows exempt."
echo
echo "  HOTFIX (2026-07-31 — this deploy):"
echo "  • POST /api/v1/cases/ no longer 500s when a petition is filed"
echo "    without an FIR number. The blank FIR is stored as NULL (so"
echo "    FIR-less petitions don't collide on uq_case_unit_ps_fir),"
echo "    but the response serializer passed that NULL into a"
echo "    non-Optional 'fir_no: str' field -> ResponseValidationError."
echo "    The failure happened AFTER commit, so the case saved while"
echo "    the operator saw an error and retried — silently creating"
echo "    duplicates. Both cases and mule-report serializers now"
echo "    coalesce NULL -> \"\". No schema or frontend change."
echo "  • Any FIR-less case already in the DB also 500'd every list"
echo "    page it appeared on; those reads work again now."
echo "  • Self-verify prints existing duplicate FIR-less cases above."
echo "    Review them by hand — this script never deletes rows."
echo
echo "  NEW: Account Details -> Map View (2026-07-31, super_admin)"
echo "  • Choropleth of account concentration with three scopes:"
echo "    Branch State (all-India), Branch District (Karnataka), and"
echo "    Reporting PS District. Shade by Mule / Victim / Non-Mule /"
echo "    All; click Karnataka on the national view to drill in."
echo "  • Rendered as a TILE GRID, not an outline of India: shipping a"
echo "    third-party boundary file would risk a non-compliant"
echo "    depiction of J&K / Ladakh / Arunachal. Tiles are schematic"
echo "    and labelled as such. To upgrade to a real outline map, add"
echo "    SVG paths to the 'd' field in geo-tile-grid.ts from a"
echo "    Survey of India / KSP GIS approved source — the renderer"
echo "    already draws path-mode shapes, no other change needed."
echo "  • The map reports its own blind spot: accounts with no"
echo "    branch_state/district, and any value outside the picklist,"
echo "    are counted in an amber 'not on the map' banner rather than"
echo "    being silently dropped. Expect this to be significant until"
echo "    branch_* backfill catches up (both columns arrived in"
echo "    migrations 010/012, after data entry had begun)."
echo "  • No migration and no new npm dependency (plain SVG)."
echo "================================================================"
