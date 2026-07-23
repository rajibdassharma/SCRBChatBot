#!/usr/bin/env bash
# ============================================================================
# CyberFraud Data Entry — uploads/ backup script
#
# Mirrors backup-db.sh, but for the user-uploaded files under
# /opt/cyberfraud/backend/uploads/ (ID photos + bank statements).
# The DB dump alone is not enough — it only knows the paths, not the
# bytes. Losing this directory means every attached document is gone
# even though the DB rows still point at them.
#
# Fires from step 3 of deploy/update.sh (pre-migration), and can also
# be pointed at from a nightly systemd timer alongside the DB backup.
#
# Writes a gzipped tar into /opt/cyberfraud/backups/uploads_<ts>.tar.gz
# and RETAINS ONLY THE NEWEST BACKUP — every prior uploads_*.tar.gz is
# deleted after the current write succeeds (2026-07-24).
# ============================================================================

set -euo pipefail

UPLOAD_DIR=/opt/cyberfraud/backend/uploads
BACKUP_DIR=/opt/cyberfraud/backups

# ── No uploads directory yet? Nothing to back up — that's fine. ─────
if [ ! -d "$UPLOAD_DIR" ]; then
    echo "[backup-uploads] $UPLOAD_DIR does not exist yet — skipping (no files uploaded)."
    exit 0
fi

# ── Uploads directory exists but is empty? Skip the tar too. ────────
if [ -z "$(find "$UPLOAD_DIR" -type f -print -quit 2>/dev/null)" ]; then
    echo "[backup-uploads] $UPLOAD_DIR is empty — skipping."
    exit 0
fi

mkdir -p "$BACKUP_DIR"
chmod 750 "$BACKUP_DIR"
# Owned by the backend user (not root) so future non-sudo readers /
# nightly timers can access it. Chown is a no-op if we're already
# the target user.
chown -R cyberfraud:cyberfraud "$BACKUP_DIR" 2>/dev/null || true

TIMESTAMP=$(date +'%Y-%m-%d_%H%M')
OUTFILE="$BACKUP_DIR/uploads_${TIMESTAMP}.tar.gz"

echo "[backup-uploads] $(date -Iseconds) — archiving $UPLOAD_DIR → $OUTFILE"

# Tar from the parent so the archive extracts to `uploads/` (matching
# the runtime layout — restore is: cd /opt/cyberfraud/backend && tar xzf ...).
tar -C "$(dirname "$UPLOAD_DIR")" -czf "$OUTFILE" "$(basename "$UPLOAD_DIR")"

# Restrict access — attached files may contain PII (IDs, KYC docs).
# Chown to the backend user so cyberfraud (not root) owns the file.
chmod 640 "$OUTFILE"
chown cyberfraud:cyberfraud "$OUTFILE" 2>/dev/null || true

SIZE=$(stat -c '%s' "$OUTFILE")
FILE_COUNT=$(find "$UPLOAD_DIR" -type f | wc -l)
echo "[backup-uploads] OK — wrote $OUTFILE ($SIZE bytes, $FILE_COUNT source file(s))"

# ── Retain only the file we just wrote ──────────────────────────────
# Explicit name-exclusion (not mtime-based) so the boundary is
# deterministic: at the end of this script exactly one archive
# exists on disk. Safe — we only reach this line after the tar +
# stat + chown succeeded, so OUTFILE is real and populated.
CURRENT_NAME=$(basename "$OUTFILE")
PRUNED=$(find "$BACKUP_DIR" -maxdepth 1 -type f -name "uploads_*.tar.gz" ! -name "$CURRENT_NAME" -print -delete | wc -l)
echo "[backup-uploads] pruned $PRUNED prior archive(s); retaining only $CURRENT_NAME"

# ── Show what's currently retained ───────────────────────────────────
echo "[backup-uploads] current backups:"
ls -lh "$BACKUP_DIR" | grep 'uploads_' | sort -k9 || true
