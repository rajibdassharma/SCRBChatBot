#!/usr/bin/env bash
# ============================================================================
# CyberFraud Data Entry — one-time install of the nightly MySQL backup.
#
# Wraps every step that used to be in the deploy/README.md "One-time backup
# install" section. Idempotent — safe to re-run if a step failed or you
# tweaked the unit files.
#
# Usage on the server:
#   sudo bash /opt/scrb/CyberFraudDataEntry/deploy/install-backup.sh
#
# What it does:
#   1. git pull on /opt/scrb to grab the latest backup files.
#   2. Sync deploy/ from /opt/scrb/CyberFraudDataEntry/ → /opt/cyberfraud/.
#   3. Create /opt/cyberfraud/backups/ owned by the `cyberfraud` user.
#   4. Make backup-db.sh executable.
#   5. Install the systemd .service + .timer unit files.
#   6. Reload systemd, enable + start the .timer.
#   7. Verify the timer is scheduled.
#   8. Trigger one manual backup run as a smoke test.
#   9. Show the journal output + list backup files.
# ============================================================================

set -euo pipefail

SOURCE_REPO=/opt/scrb
SOURCE_DEPLOY=$SOURCE_REPO/CyberFraudDataEntry/deploy
RUNTIME_BASE=/opt/cyberfraud
RUNTIME_DEPLOY=$RUNTIME_BASE/deploy
BACKUP_DIR=$RUNTIME_BASE/backups
SERVICE=cyberfraud-backup.service
TIMER=cyberfraud-backup.timer

echo "============================================================"
echo "  CyberFraud — install nightly MySQL backup automation"
echo "  Source : $SOURCE_DEPLOY"
echo "  Runtime: $RUNTIME_DEPLOY"
echo "  Backups: $BACKUP_DIR"
echo "============================================================"

# ── 1. Pull latest source ────────────────────────────────────────────
echo
echo "=== 1. git pull on $SOURCE_REPO ==="
cd "$SOURCE_REPO"
sudo git pull
echo "    HEAD: $(git log -1 --oneline)"

# Fail early if the new files aren't actually present after the pull
for f in backup-db.sh cyberfraud-backup.service cyberfraud-backup.timer; do
    if [ ! -f "$SOURCE_DEPLOY/$f" ]; then
        echo "ERROR: $SOURCE_DEPLOY/$f missing after git pull" >&2
        exit 1
    fi
done

# ── 2. Sync deploy/ to runtime ───────────────────────────────────────
echo
echo "=== 2. Sync deploy/ → $RUNTIME_DEPLOY ==="
sudo cp -r "$SOURCE_DEPLOY" "$RUNTIME_BASE/"
sudo chown -R cyberfraud:cyberfraud "$RUNTIME_DEPLOY"
echo "    Done."

# ── 3. Backup directory ──────────────────────────────────────────────
echo
echo "=== 3. Ensure backup directory exists ==="
sudo mkdir -p "$BACKUP_DIR"
sudo chown cyberfraud:cyberfraud "$BACKUP_DIR"
sudo chmod 750 "$BACKUP_DIR"
echo "    $BACKUP_DIR  $(stat -c '%U:%G  %a' "$BACKUP_DIR")"

# ── 4. Make backup script executable ─────────────────────────────────
echo
echo "=== 4. Make backup-db.sh executable ==="
sudo chmod +x "$RUNTIME_DEPLOY/backup-db.sh"
ls -l "$RUNTIME_DEPLOY/backup-db.sh"

# ── 5. Install systemd unit files ────────────────────────────────────
echo
echo "=== 5. Install systemd unit files ==="
sudo cp "$RUNTIME_DEPLOY/cyberfraud-backup.service" /etc/systemd/system/
sudo cp "$RUNTIME_DEPLOY/cyberfraud-backup.timer"   /etc/systemd/system/
echo "    Installed /etc/systemd/system/$SERVICE"
echo "    Installed /etc/systemd/system/$TIMER"

# ── 6. Reload + enable + start timer ─────────────────────────────────
echo
echo "=== 6. systemctl daemon-reload + enable --now $TIMER ==="
sudo systemctl daemon-reload
sudo systemctl enable --now "$TIMER"

# ── 7. Verify schedule ───────────────────────────────────────────────
echo
echo "=== 7. Verify timer is scheduled ==="
systemctl list-timers "$TIMER" --no-pager
echo "    Status: $(systemctl is-active $TIMER)  /  enabled: $(systemctl is-enabled $TIMER)"

# ── 8. Manual smoke-test run ─────────────────────────────────────────
echo
echo "=== 8. Trigger one manual backup as a smoke test ==="
sudo systemctl start "$SERVICE"
# Give the oneshot a few seconds to finish before we read the journal
sleep 3

# Wait up to 60s for the service to settle into a terminal state
for i in {1..30}; do
    STATE=$(systemctl show -p ActiveState --value "$SERVICE")
    SUBSTATE=$(systemctl show -p SubState --value "$SERVICE")
    case "$SUBSTATE" in
        dead|exited|failed) break ;;
    esac
    sleep 2
done

echo "    ActiveState=$STATE  SubState=$SUBSTATE"
echo "    --- journal output ---"
sudo journalctl -u "$SERVICE" -n 30 --no-pager

# ── 9. List backup files + final summary ─────────────────────────────
echo
echo "=== 9. Backup files on disk ==="
sudo -u cyberfraud ls -lh "$BACKUP_DIR" || true

echo
echo "============================================================"
if [ "$SUBSTATE" = "failed" ]; then
    echo "  ✗ Manual backup FAILED — see journal output above."
    echo "  The timer is still installed, but fix the failure"
    echo "  before relying on the nightly run."
    echo "============================================================"
    exit 2
fi
echo "  ✓ Nightly backup installed."
echo "  Next scheduled fire: see 'systemctl list-timers $TIMER'"
echo "  Backups will land in: $BACKUP_DIR"
echo "  Logs: sudo journalctl -u $SERVICE --since '1 hour ago'"
echo "============================================================"
