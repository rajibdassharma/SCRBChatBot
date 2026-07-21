#!/usr/bin/env bash
# ============================================================================
# CyberFraud Data Entry — install / update the nightly backup automation.
#
# Nightly backup now covers BOTH the MySQL database AND the uploads/ tree
# (ID photos + bank statements). Runs at 00:00 IST via
# cyberfraud-backup.timer → cyberfraud-backup.service → backup-all.sh
# (which chains backup-db.sh + backup-uploads.sh).
#
# Idempotent — re-run any time you tweak the unit files or change the
# schedule; systemctl daemon-reload + enable --now picks up the changes.
#
# Usage on the server:
#   sudo bash /opt/scrb/CyberFraudDataEntry/deploy/install-backup.sh
#
# What it does:
#   1. git pull on /opt/scrb to grab the latest backup files.
#   2. Sync deploy/ from /opt/scrb/CyberFraudDataEntry/ → /opt/cyberfraud/.
#   3. Create /opt/cyberfraud/backups/ owned by the `cyberfraud` user.
#   4. Make backup-{all,db,uploads}.sh executable.
#   5. Install the systemd .service + .timer unit files.
#   6. Reload systemd, enable + (re)start the .timer.
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
echo "  CyberFraud — install/refresh nightly backup automation"
echo "  Scope  : DB + uploads/  (via backup-all.sh)"
echo "  Time   : 00:00 IST daily"
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
for f in backup-all.sh backup-db.sh backup-uploads.sh cyberfraud-backup.service cyberfraud-backup.timer; do
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

# ── 4. Make backup scripts executable ────────────────────────────────
echo
echo "=== 4. Make backup-{all,db,uploads}.sh executable ==="
sudo chmod +x "$RUNTIME_DEPLOY/backup-all.sh" \
              "$RUNTIME_DEPLOY/backup-db.sh" \
              "$RUNTIME_DEPLOY/backup-uploads.sh"
ls -l "$RUNTIME_DEPLOY/backup-all.sh" "$RUNTIME_DEPLOY/backup-db.sh" "$RUNTIME_DEPLOY/backup-uploads.sh"

# ── 5. Install systemd unit files ────────────────────────────────────
echo
echo "=== 5. Install systemd unit files ==="
sudo cp "$RUNTIME_DEPLOY/cyberfraud-backup.service" /etc/systemd/system/
sudo cp "$RUNTIME_DEPLOY/cyberfraud-backup.timer"   /etc/systemd/system/
echo "    Installed /etc/systemd/system/$SERVICE"
echo "    Installed /etc/systemd/system/$TIMER"

# ── 6. Reload + enable + (re)start timer ─────────────────────────────
# daemon-reload picks up unit-file changes (e.g. new OnCalendar).
# restart guarantees the timer re-reads its schedule immediately —
# needed when this is a re-install with a changed .timer/.service.
echo
echo "=== 6. systemctl daemon-reload + enable + restart $TIMER ==="
sudo systemctl daemon-reload
sudo systemctl enable "$TIMER"
sudo systemctl restart "$TIMER"

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
