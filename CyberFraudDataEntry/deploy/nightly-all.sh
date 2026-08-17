#!/usr/bin/env bash
#
# Nightly chain: ANALYSIS first, then backup.
#
# WHY ONE SCRIPT AND NOT TWO TIMERS
# The backup has to capture the analysis results, so the two are
# ordered, not merely scheduled. Two timers an hour apart looks like
# ordering and is not: an incremental analysis run varies from about
# five minutes to over an hour depending on how many statements were
# uploaded that day, and the night it overruns is the night the backup
# silently captures yesterday's figures under today's date. Nothing
# would error and nobody would notice until a restore.
#
# Sequential in one unit means the backup cannot start until the
# analysis has finished, however long that takes.
#
# WHY THE BACKUP RUNS EVEN WHEN THE ANALYSIS FAILS
# A backup of slightly stale derived data is worth far more than no
# backup at all, and the operational tables -- every case, account and
# DSR entry an operator touched today -- have nothing to do with the
# analysis and must be captured regardless. The failure is recorded and
# this script still exits non-zero so systemd marks the run failed;
# what it does not do is skip the backup as a punishment.
#
# ORDER OF THE TWO BACKUP STEPS is left to backup-all.sh.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME="${CFDSR_RUNTIME:-/opt/cyberfraud}"
START=$(date -Iseconds)

echo "================================================================"
echo "  CyberFraud nightly — started $START"
echo "================================================================"

# ── 1. Analysis ─────────────────────────────────────────────────────
echo
echo "=== 1/2  Upload analysis ==="
ANALYSIS_RC=0
(
  cd "$RUNTIME/backend" || exit 1
  # --skip-relink: relink repairs account links broken by restoring a
  # dump onto a different database. Production IS the source, so there
  # is nothing to repair and the pass would be pure cost.
  "$RUNTIME/venv/bin/python" -m analysis.daily --skip-relink
) || ANALYSIS_RC=$?

if [ "$ANALYSIS_RC" -ne 0 ]; then
    echo
    echo "  !! analysis exited $ANALYSIS_RC — continuing to the backup anyway."
    echo "     Today's operational data is unaffected by this and must"
    echo "     still be captured. Investigate with:"
    echo "       journalctl -u cyberfraud-nightly.service -n 200"
fi

# ── 2. Backup ───────────────────────────────────────────────────────
echo
echo "=== 2/2  Backup (DB + uploads) ==="
BACKUP_RC=0
bash "$SCRIPT_DIR/backup-all.sh" || BACKUP_RC=$?

echo
echo "================================================================"
echo "  nightly finished $(date -Iseconds)  (started $START)"
echo "     analysis exit $ANALYSIS_RC / backup exit $BACKUP_RC"
echo "================================================================"

# A failed backup is the more serious of the two, so it wins the exit
# code when both fail.
if [ "$BACKUP_RC" -ne 0 ]; then exit "$BACKUP_RC"; fi
exit "$ANALYSIS_RC"
