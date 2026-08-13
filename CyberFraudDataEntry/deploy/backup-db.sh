#!/usr/bin/env bash
# ============================================================================
# CyberFraud Data Entry — MySQL backup script
#
# Fires every night at 02:00 IST via systemd timer `cyberfraud-backup.timer`.
# Writes a gzipped mysqldump of `cyber_fraud_dsr` into /opt/cyberfraud/backups/
# and RETAINS ONLY THE NEWEST BACKUP — every prior file matching the same
# pattern is deleted after the current write succeeds (2026-07-24). Restore
# window is therefore always exactly one night. Output goes to journal:
#     sudo journalctl -u cyberfraud-backup.service -n 50 --no-pager
#
# Runs as the `cyberfraud` user (matches the backend service), so DB
# credentials come from the same /opt/cyberfraud/backend/.env file the
# backend already reads.
# ============================================================================

set -euo pipefail

# Fail the whole pipeline if mysqldump fails before gzip sees its stdin
set -o pipefail

ENV_FILE=/opt/cyberfraud/backend/.env
BACKUP_DIR=/opt/cyberfraud/backups

# ── Read DB credentials from .env ────────────────────────────────────
if [ ! -r "$ENV_FILE" ]; then
    echo "ERROR: cannot read $ENV_FILE" >&2
    exit 1
fi

# Strip comments/blank lines and pull each CFDSR_DB_* value. Use cut -d= -f2-
# to preserve any '=' inside the value (e.g. in a password).
DB_HOST=$(grep -E '^CFDSR_DB_HOST='     "$ENV_FILE" | tail -1 | cut -d'=' -f2- || true)
DB_PORT=$(grep -E '^CFDSR_DB_PORT='     "$ENV_FILE" | tail -1 | cut -d'=' -f2- || true)
DB_USER=$(grep -E '^CFDSR_DB_USER='     "$ENV_FILE" | tail -1 | cut -d'=' -f2- || true)
DB_PASS=$(grep -E '^CFDSR_DB_PASSWORD=' "$ENV_FILE" | tail -1 | cut -d'=' -f2- || true)
DB_NAME=$(grep -E '^CFDSR_DB_NAME='     "$ENV_FILE" | tail -1 | cut -d'=' -f2- || true)

: "${DB_HOST:=localhost}"
: "${DB_PORT:=3306}"
: "${DB_USER:=root}"
: "${DB_NAME:=cyber_fraud_dsr}"

if [ -z "$DB_PASS" ]; then
    echo "ERROR: CFDSR_DB_PASSWORD not found in $ENV_FILE" >&2
    exit 1
fi

# ── Prepare output path ──────────────────────────────────────────────
mkdir -p "$BACKUP_DIR"
chmod 750 "$BACKUP_DIR"
# The backup dir + everything in it should be owned by the backend
# user, not root — otherwise `sudo bash` invocations leave root-owned
# artefacts that the cyberfraud user (nightly timers, scp readbacks)
# can't touch. Chown is a no-op if we're already the target user.
chown -R cyberfraud:cyberfraud "$BACKUP_DIR" 2>/dev/null || true

# TZ=Asia/Kolkata because the SCHEDULE is IST (cyberfraud-backup.timer
# fires at 00:00 Asia/Kolkata) while the server's clock is UTC. Without
# it, the midnight-IST run stamps the file 18:33 the PREVIOUS DAY — so
# the dump labelled the 9th actually holds data as of midnight opening
# the 10th, and whoever restores it copies the wrong file.
TIMESTAMP=$(TZ=Asia/Kolkata date +'%Y-%m-%d_%H%M')
OUTFILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql.gz"

echo "[backup-db] $(date -Iseconds) — dumping $DB_NAME → $OUTFILE"

# ── Derived analysis tables: EXCLUDED from the dump ──────────────────
# These five hold nothing an operator typed. Every row is computed from
# the files under backend/uploads/ by `python -m analysis.daily`, and
# any of them can be rebuilt from scratch at any time.
#
# Measured 2026-08-07 on the dev copy: the source tables total ~30 MB,
# these five total ~11.4 GB. Including them would make this nightly
# dump 374x larger — and 374x slower to write, transfer, and restore —
# to carry data that is a pure function of files we already back up
# separately in backup-uploads.sh.
#
# --ignore-table drops STRUCTURE as well as rows. That is correct and
# deliberate: migrations 019-023 create these tables, and both
# update.sh and analysis.daily run those migrations, so a restore onto
# a clean server still ends up with the right schema.
#
# The payoff on the DEV laptop is the part that matters day to day: a
# dump that never mentions these tables cannot DROP them, so restoring
# yesterday's production data leaves ~14 million parsed transactions —
# the better part of a day's compute — untouched. Adding a table here
# without that property would silently destroy it on every restore.
DERIVED_TABLES=(
    upload_ledger              # which files have been processed
    statement_transactions     # parsed rows — the 11 GB
    account_statement_summary  # per (account, channel) rollup
    id_photo_hashes            # SHA-256 + perceptual hash per photo
    mule_account_link          # direct mule -> mule transfers
    crypto_txn                 # statement rows naming a crypto exchange
)
IGNORE_ARGS=()
for t in "${DERIVED_TABLES[@]}"; do
    IGNORE_ARGS+=( "--ignore-table=${DB_NAME}.${t}" )
done
echo "[backup-db] excluding ${#DERIVED_TABLES[@]} derived table(s): ${DERIVED_TABLES[*]}"

# ── Dump + compress in one streaming pipeline ────────────────────────
# --single-transaction : consistent snapshot without table locks
# --routines / --triggers : carry over stored procedures + triggers (cheap)
# --quick : row-by-row streaming (memory-safe for large tables)
# --hex-blob : safe encoding for any binary columns
MYSQL_PWD="$DB_PASS" mysqldump \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --user="$DB_USER" \
    --single-transaction \
    --routines \
    --triggers \
    --quick \
    --hex-blob \
    "${IGNORE_ARGS[@]}" \
    "$DB_NAME" \
  | gzip --best > "$OUTFILE"

# Restrict access — dumps contain bcrypt hashes and operational data.
# Chown to the backend user so cyberfraud (not root) owns the file —
# consistent with the rest of /opt/cyberfraud/.
chmod 640 "$OUTFILE"
chown cyberfraud:cyberfraud "$OUTFILE" 2>/dev/null || true

# ── Sanity check: a dump of any real DB is well over 1 KB ────────────
SIZE=$(stat -c '%s' "$OUTFILE")
if [ "$SIZE" -lt 1024 ]; then
    echo "ERROR: backup file $OUTFILE is suspiciously small ($SIZE bytes)" >&2
    exit 2
fi
echo "[backup-db] OK — wrote $OUTFILE ($SIZE bytes)"

# ── Retain only the file we just wrote ──────────────────────────────
# Explicit name-exclusion (not mtime-based) so the boundary is
# deterministic: at the end of this script exactly one backup file
# exists on disk regardless of when previous runs happened. Safe —
# we only reach this line if the size check above passed, so OUTFILE
# is real and populated.
CURRENT_NAME=$(basename "$OUTFILE")
PRUNED=$(find "$BACKUP_DIR" -maxdepth 1 -type f -name "${DB_NAME}_*.sql.gz" ! -name "$CURRENT_NAME" -print -delete | wc -l)
echo "[backup-db] pruned $PRUNED prior backup(s); retaining only $CURRENT_NAME"

# ── Show what's currently retained ───────────────────────────────────
echo "[backup-db] current backups:"
ls -lh "$BACKUP_DIR" | tail -n +2 | sort -k9
