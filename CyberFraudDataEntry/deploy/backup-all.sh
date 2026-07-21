#!/usr/bin/env bash
# ============================================================================
# CyberFraud Data Entry — combined DB + uploads backup
#
# Fires backup-db.sh and backup-uploads.sh in sequence. Fails loudly
# if either step fails (so cron / a systemd timer can alert on it).
# Safe to run any time — both underlying scripts timestamp their
# output files and prune anything older than 7 days.
#
# Manual usage on the server:
#     sudo bash /opt/scrb/CyberFraudDataEntry/deploy/backup-all.sh
#
# Cron nightly at 02:00 IST (as root, so both scripts can read .env
# and write under /opt/cyberfraud/backups/):
#     0 2 * * * root /opt/scrb/CyberFraudDataEntry/deploy/backup-all.sh \
#         >> /var/log/cyberfraud-backup.log 2>&1
#
# Or as a systemd timer — say the word and I'll write the unit files.
#
# Outputs land in /opt/cyberfraud/backups/ :
#   - cyber_fraud_dsr_YYYY-MM-DD_HHMM.sql.gz   (from backup-db.sh)
#   - uploads_YYYY-MM-DD_HHMM.tar.gz           (from backup-uploads.sh)
# Both keep 7 days of history and auto-prune older files.
#
# Restore reminders:
#   DB      : zcat /opt/cyberfraud/backups/cyber_fraud_dsr_<ts>.sql.gz \
#             | mysql -u root -p cyber_fraud_dsr
#   Uploads : cd /opt/cyberfraud/backend && \
#             tar xzf /opt/cyberfraud/backups/uploads_<ts>.tar.gz
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START=$(date -Iseconds)

echo "================================================================"
echo "  CyberFraud backup — started $START"
echo "================================================================"

# ── 1/2 Database ────────────────────────────────────────────────────
echo
echo "=== 1/2  Database ==="
bash "$SCRIPT_DIR/backup-db.sh"

# ── 2/2 Uploads (photos + statements) ───────────────────────────────
echo
echo "=== 2/2  Uploads (photos + statements) ==="
bash "$SCRIPT_DIR/backup-uploads.sh"

# ── Summary ────────────────────────────────────────────────────────
echo
echo "================================================================"
echo "  ✓ Backup complete — started $START, finished $(date -Iseconds)"
echo
echo "  Files retained in /opt/cyberfraud/backups/ (7-day rolling):"
ls -lh /opt/cyberfraud/backups/ 2>/dev/null | tail -n +2 | sort -k9 || true
echo "================================================================"
