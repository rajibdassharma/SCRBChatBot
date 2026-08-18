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

# Budget for the ANALYSIS alone, comfortably inside the unit's
# TimeoutStartSec.
#
# The unit timeout kills this whole script, backup included. On the
# first night it did exactly that: the analysis was still hashing
# photos at the 8h mark, systemd terminated the unit, and no backup was
# taken -- defeating the "the backup always runs" guarantee below, which
# only ever handled the analysis FAILING, not the analysis being killed
# together with the script.
#
# Its own budget means an overrun ends the analysis and leaves this
# script alive with time on the clock to still take a backup.
ANALYSIS_TIMEOUT="${CFDSR_ANALYSIS_TIMEOUT:-6h}"

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
  # $RUNTIME/backend/venv, not $RUNTIME/venv. update.sh reaches the
  # venv only after a `cd $RUNTIME/backend`, so the relative path
  # there hides where it actually is.
  # --kill-after: SIGTERM first so Python can close its worker pool,
  # SIGKILL two minutes later if it will not go. The parse is resumable
  # from the ledger either way, so a kill costs a retry, never work.
  timeout --signal=TERM --kill-after=120 "$ANALYSIS_TIMEOUT" "$RUNTIME/backend/venv/bin/python" -m analysis.daily --skip-relink
) || ANALYSIS_RC=$?

if [ "$ANALYSIS_RC" -eq 124 ]; then
    echo
    echo "  !! analysis hit its $ANALYSIS_TIMEOUT budget and was stopped."
    echo "     Unfinished files are never marked settled, so the next run"
    echo "     picks them up. Taking the backup now."
elif [ "$ANALYSIS_RC" -ne 0 ]; then
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
