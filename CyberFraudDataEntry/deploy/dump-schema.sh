#!/usr/bin/env bash
# Dump the LIVE MySQL schema (structure only, no rows) as a timestamped
# .sql snapshot under proddata/. Use when someone -- auditor, new dev,
# offline reader -- needs the current DDL without SSH access to the DB.
#
# NOT wired into update.sh (no need to snapshot on every deploy).
# Regenerate on demand -- typically:
#   * before / after a migration you want to compare
#   * for a VAPT / audit handoff
#   * for a new dev / handover doc pack
#
# Reads DB creds from backend/.env (same source as the app + backups).

set -euo pipefail

SCRIPT_DIR="$( cd "$(dirname "${BASH_SOURCE[0]}")" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
ENV_FILE="$REPO_ROOT/backend/.env"
OUT_DIR="$REPO_ROOT/proddata"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found. This script expects backend/.env with CFDSR_DB_* values."
    exit 1
fi

# Defensive greps -- if a var isn't there, keep the empty default and let
# mysqldump error out with a clear message rather than crashing the script.
DB_USER=$( (grep -E '^CFDSR_DB_USER='     "$ENV_FILE" 2>/dev/null || true) | tail -1 | cut -d'=' -f2- )
DB_PASS=$( (grep -E '^CFDSR_DB_PASSWORD=' "$ENV_FILE" 2>/dev/null || true) | tail -1 | cut -d'=' -f2- )
DB_NAME=$( (grep -E '^CFDSR_DB_NAME='     "$ENV_FILE" 2>/dev/null || true) | tail -1 | cut -d'=' -f2- )
DB_NAME=${DB_NAME:-cyber_fraud_dsr}

mkdir -p "$OUT_DIR"
STAMP=$(date +%Y%m%d)
OUT_FILE="$OUT_DIR/schema-snapshot-${STAMP}.sql"

echo "→ Dumping $DB_NAME schema (no data) to $OUT_FILE"
MYSQL_PWD="$DB_PASS" mysqldump \
    --user="$DB_USER" \
    --no-data \
    --routines \
    --triggers \
    --skip-comments \
    --result-file="$OUT_FILE" \
    "$DB_NAME"

echo "✓ Snapshot written: $(wc -l < "$OUT_FILE") lines, $(du -h "$OUT_FILE" | cut -f1)"
echo
echo "Commit if you want to preserve this as a dated artefact:"
echo "  git add proddata/schema-snapshot-${STAMP}.sql"
echo "  git commit -m \"CyberFraud: schema snapshot ${STAMP}\""
