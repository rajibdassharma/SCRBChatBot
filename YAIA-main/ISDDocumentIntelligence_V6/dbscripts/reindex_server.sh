#!/usr/bin/env bash
# reindex_server.sh — V6 IR Reindex PART 2: all server Ubuntu phases.
#
# SINGLE-TABLE approach: imports a dump containing ONLY the ir_reports
# table. Every other server table (users, cases, smac_reports, entities,
# answer_ratings, etc.) is left completely untouched. The local script
# (reindex_local.ps1 Phase 1E) produces ir_reports_only.sql to match.
#
# Runs Phases 2A through 2D end-to-end on the production server:
#   2A — pre-flight (verify USB artifacts, baseline counts)
#   2B — backup ir_reports + ChromaDB IR folder (timestamped)
#   2C — apply (stop backend, restore ir_reports, replace chroma, chown, restart)
#   2D — validate (counts, health check)
#
# MySQL credentials come from backend/.env. The script auto-resolves its
# own location so it works whether the project lives at /opt/isd/... or
# anywhere else.
#
# BACKEND LIFECYCLE: by default this script tries `systemctl stop/start
# isd-backend`. If the systemd service is not installed (deploy/README.md
# install step never run), the script will detect that and switch to a
# manual mode where you must Ctrl+C the uvicorn console yourself before
# the apply phase, then restart it after.
#
# Usage (after USB drop to /opt/transfer/v6/):
#   sudo bash /opt/isd/ISDDocumentIntelligence_V6/dbscripts/reindex_server.sh
#
# Override defaults via env vars:
#   sudo TRANSFER_DIR=/mnt/usb/V6 bash reindex_server.sh
#   sudo BACKUP_DIR=/data/backups bash reindex_server.sh
#   sudo SERVICE=isd-backend-v7 bash reindex_server.sh
#   sudo MANUAL_BACKEND=1 bash reindex_server.sh   # skip systemctl entirely

set -euo pipefail

# ── Configuration (override via env) ─────────────────────────────────
TRANSFER_DIR="${TRANSFER_DIR:-/opt/transfer/v6}"
BACKUP_DIR_BASE="${BACKUP_DIR:-/opt/backups/v6}"
SERVICE="${SERVICE:-isd-backend}"
SERVICE_USER="${SERVICE_USER:-isd}"
MANUAL_BACKEND="${MANUAL_BACKEND:-0}"

# Resolve APP_DIR from this script's location (parent of dbscripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$BACKUP_DIR_BASE/$TIMESTAMP"

# ── MySQL creds — read from backend/.env ─────────────────────────────
ENV_FILE="$APP_DIR/backend/.env"
read_env() {
    local key="$1"
    if [ -f "$ENV_FILE" ]; then
        # shellcheck disable=SC2002
        cat "$ENV_FILE" | grep -E "^\s*${key}\s*=" | head -1 | \
            cut -d= -f2- | sed -e 's/^["'\'']//' -e 's/["'\'']$//' -e 's/[[:space:]]*$//'
    fi
}
MYSQL_USER="${MYSQL_USER:-$(read_env MYSQL_USER)}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-$(read_env MYSQL_PASSWORD)}"
MYSQL_DB="${MYSQL_DB:-$(read_env MYSQL_DATABASE)}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_DB="${MYSQL_DB:-ISDIntelligence}"

mysql_run() {
    mysql -u "$MYSQL_USER" "-p$MYSQL_PASSWORD" "$MYSQL_DB" -e "$1"
}
mysql_count() {
    mysql -u "$MYSQL_USER" "-p$MYSQL_PASSWORD" "$MYSQL_DB" -N -e "$1"
}

phase() {
    echo ""
    echo "============================================================"
    echo "  $1"
    echo "============================================================"
}

# ── Detect backend mode (systemd vs manual) ──────────────────────────
USE_SYSTEMD=0
if [ "$MANUAL_BACKEND" != "1" ]; then
    if systemctl list-unit-files 2>/dev/null | grep -q "^${SERVICE}\.service"; then
        USE_SYSTEMD=1
    fi
fi

stop_backend() {
    if [ "$USE_SYSTEMD" = "1" ]; then
        echo "Stopping $SERVICE via systemctl..."
        systemctl stop "$SERVICE"
    else
        echo ""
        echo "============================================================"
        echo "  MANUAL BACKEND STOP REQUIRED"
        echo "============================================================"
        echo ""
        echo "  Systemd service '$SERVICE' is not installed."
        echo "  Please switch to the console where uvicorn is running and"
        echo "  press Ctrl+C now to stop the backend."
        echo ""
        echo "  Then come back here and press Enter to continue."
        read -r
    fi
}

start_backend() {
    if [ "$USE_SYSTEMD" = "1" ]; then
        echo "Starting $SERVICE via systemctl..."
        systemctl start "$SERVICE"
        sleep 3
        systemctl status "$SERVICE" --no-pager | head -10
    else
        echo ""
        echo "============================================================"
        echo "  MANUAL BACKEND START REQUIRED"
        echo "============================================================"
        echo ""
        echo "  Switch to your uvicorn console and run:"
        echo "    cd $APP_DIR/backend"
        echo "    uvicorn app:app --host 0.0.0.0 --port 8003 --reload"
        echo ""
        echo "  Then press Enter here to run the validation phase."
        read -r
    fi
}

# ── Phase 2A — Pre-flight ────────────────────────────────────────────
phase "Phase 2A — Pre-flight"
echo "  Transfer dir : $TRANSFER_DIR"
echo "  Backup dir   : $BACKUP_DIR"
echo "  App dir      : $APP_DIR"
if [ "$USE_SYSTEMD" = "1" ]; then
    echo "  Backend mode : systemd ($SERVICE, runs as $SERVICE_USER)"
else
    echo "  Backend mode : manual uvicorn (you Ctrl+C / restart by hand)"
fi
echo "  MySQL DB     : $MYSQL_DB (user: $MYSQL_USER)"

if [ ! -f "$TRANSFER_DIR/ir_reports_only.sql" ]; then
    echo "ERROR: missing artifact: $TRANSFER_DIR/ir_reports_only.sql"
    echo "       Did you copy from USB to $TRANSFER_DIR ?"
    exit 1
fi
if [ ! -d "$TRANSFER_DIR/chroma_db_ir_v6" ]; then
    echo "ERROR: missing artifact: $TRANSFER_DIR/chroma_db_ir_v6/"
    exit 1
fi

# Sanity-check the dump file is binary-safe (not UTF-16 from a bad
# PowerShell > redirect). UTF-16 LE starts with bytes ff fe.
FIRST_BYTES="$(head -c 2 "$TRANSFER_DIR/ir_reports_only.sql" | xxd -p)"
if [ "$FIRST_BYTES" = "fffe" ] || [ "$FIRST_BYTES" = "feff" ]; then
    echo "ERROR: $TRANSFER_DIR/ir_reports_only.sql is UTF-16 (BOM detected)."
    echo "       Re-dump on Windows using:"
    echo "         mysqldump ... --result-file=C:/Transfer/V6/ir_reports_only.sql ..."
    echo "       (NOT '> file.sql' — PowerShell will mangle it again.)"
    exit 1
fi

echo ""
echo "Transfer artifacts:"
ls -lh "$TRANSFER_DIR/"

mkdir -p "$BACKUP_DIR"

echo ""
echo "Baseline server counts (before deploy):"
mysql_run "SELECT 'ir_docs' AS metric, COUNT(DISTINCT doc_id) AS count FROM ir_reports
           UNION ALL SELECT 'ir_field_rows', COUNT(*) FROM ir_reports;"

# ── Phase 2B — Server backup (single-table) ──────────────────────────
phase "Phase 2B — Server backup → $BACKUP_DIR"

echo "Backing up server's ir_reports table..."
mysqldump -u "$MYSQL_USER" "-p$MYSQL_PASSWORD" --single-transaction "$MYSQL_DB" ir_reports \
    > "$BACKUP_DIR/server_pre_deploy_ir_reports.sql"

echo "Backing up server's chroma_db_ir_v6 folder..."
cp -r "$APP_DIR/backend/chroma_db_ir_v6" "$BACKUP_DIR/server_pre_deploy_chroma_ir_v6"

echo ""
echo "Backups:"
ls -lh "$BACKUP_DIR/"

# ── Phase 2C — Apply ─────────────────────────────────────────────────
phase "Phase 2C — Apply on server"

stop_backend

echo "Restoring ir_reports from local dump (single-table, drops + recreates only this table)..."
mysql -u "$MYSQL_USER" "-p$MYSQL_PASSWORD" "$MYSQL_DB" \
    < "$TRANSFER_DIR/ir_reports_only.sql"

echo "Replacing ChromaDB IR folder..."
rm -rf "$APP_DIR/backend/chroma_db_ir_v6"
cp -r "$TRANSFER_DIR/chroma_db_ir_v6" "$APP_DIR/backend/"
if [ "$USE_SYSTEMD" = "1" ]; then
    chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/backend/chroma_db_ir_v6"
else
    # Manual backend mode: chown to whoever invoked sudo (so the user
    # who runs uvicorn can read/write it). Falls back to root if SUDO_USER
    # isn't set (running as root directly).
    OWNER="${SUDO_USER:-root}"
    chown -R "$OWNER:$OWNER" "$APP_DIR/backend/chroma_db_ir_v6"
fi

start_backend

# ── Phase 2D — Validation ────────────────────────────────────────────
phase "Phase 2D — Validation"

echo "Backend health:"
if curl -sf http://localhost:8003/health; then
    echo "  OK"
else
    echo "  WARN: health check failed (give it a few more seconds and try again manually)"
fi

echo ""
echo "Post-deploy counts:"
mysql_run "SELECT 'ir_docs' AS metric, COUNT(DISTINCT doc_id) AS count FROM ir_reports
           UNION ALL SELECT 'ir_field_rows', COUNT(*) FROM ir_reports;"

echo ""
echo "============================================================"
echo "  DEPLOY COMPLETE"
echo "============================================================"
echo ""
echo "Backup is preserved at: $BACKUP_DIR"
echo ""
echo "Manual verification (do these now via the UI):"
echo "  1. Open frontend, log in, run a Q&A on a NEW doc from this batch"
echo "  2. Run a Q&A on an OLD doc to confirm prior data still works"
echo "  3. Watch live logs: sudo tail -f /var/log/isd/backend.log"
echo "     (only present if running via systemd; if manual, watch the uvicorn console)"
echo ""
echo "Rollback (if validation fails):"
if [ "$USE_SYSTEMD" = "1" ]; then
    echo "  sudo systemctl stop $SERVICE"
else
    echo "  Ctrl+C the uvicorn console"
fi
echo "  sudo mysql -u $MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DB < $BACKUP_DIR/server_pre_deploy_ir_reports.sql"
echo "  sudo rm -rf $APP_DIR/backend/chroma_db_ir_v6"
echo "  sudo cp -r $BACKUP_DIR/server_pre_deploy_chroma_ir_v6 $APP_DIR/backend/chroma_db_ir_v6"
if [ "$USE_SYSTEMD" = "1" ]; then
    echo "  sudo chown -R $SERVICE_USER:$SERVICE_USER $APP_DIR/backend/chroma_db_ir_v6"
    echo "  sudo systemctl start $SERVICE"
else
    echo "  sudo chown -R \$USER:\$USER $APP_DIR/backend/chroma_db_ir_v6"
    echo "  Restart uvicorn in your console"
fi
