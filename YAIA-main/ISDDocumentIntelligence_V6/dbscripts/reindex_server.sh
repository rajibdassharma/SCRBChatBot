#!/usr/bin/env bash
# reindex_server.sh — V6 IR Reindex PART 2: all server Ubuntu phases.
#
# Runs Phases 2A through 2D end-to-end on the production server:
#   2A — pre-flight (verify USB artifacts, baseline counts)
#   2B — server backup (full MySQL + ranking-only + ChromaDB folders, timestamped)
#   2C — apply (stop service, restore MySQL, replace chroma, chown, restart)
#   2D — validate (counts, ranking preserved, health check)
#
# MySQL credentials come from backend/.env. The script auto-resolves its
# own location so it works whether the project lives at /opt/isd/... or
# anywhere else.
#
# Usage (after USB drop to /opt/transfer/v6/):
#   sudo bash /opt/isd/ISDDocumentIntelligence_V6/dbscripts/reindex_server.sh
#
# Override defaults via env vars:
#   sudo TRANSFER_DIR=/mnt/usb/V6 bash reindex_server.sh
#   sudo BACKUP_DIR=/data/backups bash reindex_server.sh
#   sudo SERVICE=isd-backend-v7 bash reindex_server.sh

set -euo pipefail

# ── Configuration (override via env) ─────────────────────────────────
TRANSFER_DIR="${TRANSFER_DIR:-/opt/transfer/v6}"
BACKUP_DIR_BASE="${BACKUP_DIR:-/opt/backups/v6}"
SERVICE="${SERVICE:-isd-backend}"
SERVICE_USER="${SERVICE_USER:-isd}"

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
    # Returns numeric count from a SELECT COUNT(*) query
    mysql -u "$MYSQL_USER" "-p$MYSQL_PASSWORD" "$MYSQL_DB" -N -e "$1"
}

phase() {
    echo ""
    echo "============================================================"
    echo "  $1"
    echo "============================================================"
}

# ── Phase 2A — Pre-flight ────────────────────────────────────────────
phase "Phase 2A — Pre-flight"
echo "  Transfer dir : $TRANSFER_DIR"
echo "  Backup dir   : $BACKUP_DIR"
echo "  App dir      : $APP_DIR"
echo "  Service      : $SERVICE (running as $SERVICE_USER)"
echo "  MySQL DB     : $MYSQL_DB (user: $MYSQL_USER)"

if [ ! -f "$TRANSFER_DIR/post_index_ISDIntelligence_no_ranking.sql" ]; then
    echo "ERROR: missing artifact: $TRANSFER_DIR/post_index_ISDIntelligence_no_ranking.sql"
    echo "       Did you copy from USB to $TRANSFER_DIR ?"
    exit 1
fi
if [ ! -d "$TRANSFER_DIR/chroma_db_ir_v6" ]; then
    echo "ERROR: missing artifact: $TRANSFER_DIR/chroma_db_ir_v6/"
    exit 1
fi
echo ""
echo "Transfer artifacts:"
ls -lh "$TRANSFER_DIR/"

mkdir -p "$BACKUP_DIR"

echo ""
echo "Baseline server counts (before deploy):"
mysql_run "SELECT 'ir_docs' AS metric, COUNT(DISTINCT doc_id) AS count FROM ir_reports
           UNION ALL SELECT 'ir_field_rows', COUNT(*) FROM ir_reports
           UNION ALL SELECT 'ranking_rows', COUNT(*) FROM ranking;"

RANKING_BASELINE="$(mysql_count 'SELECT COUNT(*) FROM ranking;')"
echo "  Saved ranking baseline: $RANKING_BASELINE"

# ── Phase 2B — Server backup ─────────────────────────────────────────
phase "Phase 2B — Server backup → $BACKUP_DIR"

echo "Full MySQL dump (includes ranking)..."
mysqldump -u "$MYSQL_USER" "-p$MYSQL_PASSWORD" --single-transaction --routines "$MYSQL_DB" \
    > "$BACKUP_DIR/server_pre_deploy_ISDIntelligence.sql"

echo "Ranking table only (safety net)..."
mysqldump -u "$MYSQL_USER" "-p$MYSQL_PASSWORD" "$MYSQL_DB" ranking \
    > "$BACKUP_DIR/server_pre_deploy_ranking_table_only.sql"

echo "ChromaDB folders..."
cp -r "$APP_DIR/backend/chroma_db_ir_v6"   "$BACKUP_DIR/server_pre_deploy_chroma_ir_v6"
cp -r "$APP_DIR/backend/chroma_db_smac_v6" "$BACKUP_DIR/server_pre_deploy_chroma_smac_v6"

echo ""
echo "Backups:"
ls -lh "$BACKUP_DIR/"

# ── Phase 2C — Apply ─────────────────────────────────────────────────
phase "Phase 2C — Apply on server"

echo "Stopping $SERVICE..."
systemctl stop "$SERVICE"

echo "Restoring MySQL from local dump (excludes ranking)..."
mysql -u "$MYSQL_USER" "-p$MYSQL_PASSWORD" "$MYSQL_DB" \
    < "$TRANSFER_DIR/post_index_ISDIntelligence_no_ranking.sql"

echo "Replacing ChromaDB IR folder..."
rm -rf "$APP_DIR/backend/chroma_db_ir_v6"
cp -r "$TRANSFER_DIR/chroma_db_ir_v6" "$APP_DIR/backend/"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/backend/chroma_db_ir_v6"

echo "Verifying ranking table is intact..."
RANKING_AFTER="$(mysql_count 'SELECT COUNT(*) FROM ranking;')"
if [ "$RANKING_AFTER" != "$RANKING_BASELINE" ]; then
    echo "WARNING: ranking count changed (baseline=$RANKING_BASELINE, after=$RANKING_AFTER)"
    echo "Restoring ranking from backup..."
    mysql -u "$MYSQL_USER" "-p$MYSQL_PASSWORD" "$MYSQL_DB" \
        < "$BACKUP_DIR/server_pre_deploy_ranking_table_only.sql"
    RANKING_AFTER="$(mysql_count 'SELECT COUNT(*) FROM ranking;')"
    if [ "$RANKING_AFTER" != "$RANKING_BASELINE" ]; then
        echo "ERROR: ranking restore did not match. Aborting before service start."
        exit 1
    fi
    echo "Ranking restored ($RANKING_AFTER rows)."
else
    echo "  Ranking intact: $RANKING_AFTER rows"
fi

echo "Starting $SERVICE..."
systemctl start "$SERVICE"
sleep 3
systemctl status "$SERVICE" --no-pager | head -10

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
           UNION ALL SELECT 'ir_field_rows', COUNT(*) FROM ir_reports
           UNION ALL SELECT 'ranking_rows', COUNT(*) FROM ranking;"

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
echo ""
echo "Rollback (if validation fails):"
echo "  sudo systemctl stop $SERVICE"
echo "  sudo mysql -u $MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DB < $BACKUP_DIR/server_pre_deploy_ISDIntelligence.sql"
echo "  sudo rm -rf $APP_DIR/backend/chroma_db_ir_v6"
echo "  sudo cp -r $BACKUP_DIR/server_pre_deploy_chroma_ir_v6 $APP_DIR/backend/chroma_db_ir_v6"
echo "  sudo chown -R $SERVICE_USER:$SERVICE_USER $APP_DIR/backend/chroma_db_ir_v6"
echo "  sudo systemctl start $SERVICE"
