#!/usr/bin/env bash
#
# Install the single nightly chain and RETIRE the two timers it replaces.
#
# Before: cyberfraud-backup.timer  at 00:00 IST -> backup-all.sh
#         cyberfraud-analysis.timer at 01:00 IST -> analysis.daily
#
# Two timers an hour apart look like ordering and are not. The backup
# fired first, so every backup carried the PREVIOUS day's analysis --
# and on a heavy upload day the analysis could still be running when
# the next one started. Nothing errored; the dates just quietly lied.
#
# After:  cyberfraud-nightly.timer at 23:00 IST -> nightly-all.sh
#           1. analysis.daily --skip-relink
#           2. backup-all.sh  (DB then uploads)
#
# Disabling the old timers is the part that matters. Leaving them
# enabled would run the backup twice and the analysis twice, and the
# stray backup would land at 00:00 between the new chain's two halves --
# capturing a database mid-analysis, which is the exact failure this
# change exists to remove.
#
# Idempotent: safe to re-run after any deploy.
set -euo pipefail

SOURCE_REPO=/opt/scrb
SOURCE_DEPLOY=$SOURCE_REPO/CyberFraudDataEntry/deploy
RUNTIME_BASE=/opt/cyberfraud
RUNTIME_DEPLOY=$RUNTIME_BASE/deploy
BACKUP_DIR=$RUNTIME_BASE/backups

NEW_SERVICE=cyberfraud-nightly.service
NEW_TIMER=cyberfraud-nightly.timer
OLD_TIMERS=(cyberfraud-backup.timer cyberfraud-analysis.timer)

echo "============================================================"
echo "  CyberFraud — install the nightly analysis + backup chain"
echo "  Order  : analysis FIRST, then backup"
echo "  Time   : 23:00 IST daily"
echo "  Retires: ${OLD_TIMERS[*]}"
echo "============================================================"

echo
echo "=== 1. git pull on $SOURCE_REPO ==="
cd "$SOURCE_REPO"
sudo git pull
echo "    HEAD: $(git log -1 --oneline)"

for f in nightly-all.sh backup-all.sh backup-db.sh backup-uploads.sh \
         "$NEW_SERVICE" "$NEW_TIMER"; do
    if [ ! -f "$SOURCE_DEPLOY/$f" ]; then
        echo "ERROR: $SOURCE_DEPLOY/$f missing after git pull" >&2
        exit 1
    fi
done

echo
echo "=== 2. Sync deploy/ -> $RUNTIME_DEPLOY ==="
sudo cp -r "$SOURCE_DEPLOY" "$RUNTIME_BASE/"
sudo chmod +x "$RUNTIME_DEPLOY"/*.sh
sudo chown -R cyberfraud:cyberfraud "$RUNTIME_DEPLOY"
sudo mkdir -p "$BACKUP_DIR"
sudo chown cyberfraud:cyberfraud "$BACKUP_DIR"

echo
echo "=== 3. Analysis dependencies ==="
# Kept OUT of requirements.txt on purpose: the web app never imports
# analysis/, and pdfplumber pulls a Pillow that reportlab -- which
# renders every operator-facing PDF -- would then be running against.
# requirements-analysis.txt pins pillow<12 to keep that from happening.
sudo -u cyberfraud "$RUNTIME_BASE/venv/bin/pip" install -q \
     -r "$SOURCE_REPO/CyberFraudDataEntry/backend/requirements-analysis.txt"
sudo -u cyberfraud "$RUNTIME_BASE/venv/bin/python" -c \
     "import pdfplumber, xlrd, PIL, reportlab; print('    ok: pdfplumber', pdfplumber.__version__, '/ Pillow', PIL.__version__, '/ reportlab', reportlab.Version)"

echo
echo "=== 4. Retire the old timers ==="
for t in "${OLD_TIMERS[@]}"; do
    if systemctl list-unit-files | grep -q "^$t"; then
        sudo systemctl disable --now "$t" 2>/dev/null || true
        echo "    disabled $t"
    else
        echo "    $t not installed — nothing to do"
    fi
done

echo
echo "=== 5. Install the new unit ==="
sudo cp "$SOURCE_DEPLOY/$NEW_SERVICE" /etc/systemd/system/
sudo cp "$SOURCE_DEPLOY/$NEW_TIMER"   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now "$NEW_TIMER"

echo
echo "=== 6. Verify ==="
systemctl list-timers --all | grep -E "cyberfraud" || true
echo
ACTIVE_OLD=0
for t in "${OLD_TIMERS[@]}"; do
    if systemctl is-enabled "$t" >/dev/null 2>&1; then
        echo "    ✗ $t is STILL enabled — it would run a backup mid-analysis"
        ACTIVE_OLD=1
    fi
done
if [ "$ACTIVE_OLD" -eq 0 ]; then
    echo "    ✓ old timers retired"
fi
if systemctl is-enabled "$NEW_TIMER" >/dev/null 2>&1; then
    echo "    ✓ $NEW_TIMER enabled"
else
    echo "    ✗ $NEW_TIMER is not enabled"
    exit 1
fi

echo
echo "============================================================"
echo "  Done. Run it once by hand before trusting the timer:"
echo "      sudo systemctl start $NEW_SERVICE"
echo "      journalctl -u $NEW_SERVICE -f"
echo "============================================================"
