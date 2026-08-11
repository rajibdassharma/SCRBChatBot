#!/usr/bin/env bash
# ============================================================================
# CyberFraud Data Entry — install / update the nightly upload-analysis job.
#
# Derives findings from the files operators upload:
#   F1  duplicate ID photos      (SHA-256 + perceptual hash)
#   F2  parsed bank statements   (with per-row balance-chain verdicts)
#   F4  mule -> mule transfer network
#
# Runs at 01:00 IST via cyberfraud-analysis.timer → .service →
# `python -m analysis.daily --skip-relink`.
#
# Idempotent — re-run any time you change the unit files or the schedule.
#
# Usage on the server:
#   sudo bash /opt/scrb/CyberFraudDataEntry/deploy/install-analysis.sh
#
# WHY THIS DOES NOT SMOKE-TEST BY STARTING THE SERVICE
# ----------------------------------------------------
# install-backup.sh ends by running its job once and reading the journal,
# because a backup takes seconds. The first analysis run is a FULL
# BACKFILL of the entire upload corpus and takes hours — starting it here
# would hang the installer, and worse, would start hours of load at
# whatever moment someone happened to run an install.
#
# So this script prepares and verifies everything cheap, then hands the
# first run to you as an explicit decision. Every subsequent run is
# incremental and unattended.
# ============================================================================

set -euo pipefail

SOURCE_REPO=/opt/scrb
SOURCE_DEPLOY=$SOURCE_REPO/CyberFraudDataEntry/deploy
RUNTIME_BASE=/opt/cyberfraud
RUNTIME_DEPLOY=$RUNTIME_BASE/deploy
BACKEND=$RUNTIME_BASE/backend
VENV_PY=$RUNTIME_BASE/venv/bin/python
SERVICE=cyberfraud-analysis.service
TIMER=cyberfraud-analysis.timer

echo "============================================================"
echo "  CyberFraud — install/refresh nightly upload analysis"
echo "  Scope  : F1 duplicate IDs, F2 statements, F4 mule network"
echo "  Time   : 01:00 IST daily (one hour after the backup)"
echo "  Source : $SOURCE_DEPLOY"
echo "  Runtime: $RUNTIME_DEPLOY"
echo "============================================================"

# ── 1. Pull latest source ────────────────────────────────────────────
echo
echo "=== 1. git pull on $SOURCE_REPO ==="
cd "$SOURCE_REPO"
sudo git pull
echo "    HEAD: $(git log -1 --oneline)"

for f in cyberfraud-analysis.service cyberfraud-analysis.timer; do
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

# ── 3. Verify the interpreter and the analysis package ───────────────
# Checked before installing units, so a missing venv fails here with a
# clear message rather than at 01:00 in the journal.
echo
echo "=== 3. Verify interpreter + analysis package ==="
if [ ! -x "$VENV_PY" ]; then
    echo "ERROR: $VENV_PY not found or not executable." >&2
    echo "       The backend venv must exist before installing this job." >&2
    exit 1
fi
echo "    python : $($VENV_PY --version)"
if [ ! -d "$BACKEND/analysis" ]; then
    echo "ERROR: $BACKEND/analysis missing — run deploy/update.sh first." >&2
    exit 1
fi
# Import the driver without running it. Catches a missing dependency
# (pdfplumber, openpyxl, Pillow) now instead of tonight.
sudo -u cyberfraud env -C "$BACKEND" "$VENV_PY" -c \
    'import analysis.daily, analysis.runtime, analysis.parse_statements; print("    imports OK")'

# ── 4. Report the resource plan this box will actually use ───────────
# The defaults in runtime.py describe a 32 GB laptop with hybrid
# graphics. The .service overrides the reserve for this VM. Printing the
# resolved numbers here means the plan is visible at install time rather
# than inferred from throughput later.
echo
echo "=== 4. Resource plan on this machine ==="
sudo -u cyberfraud env -C "$BACKEND" CFDSR_ANALYSIS_RESERVE_GB=2.0 "$VENV_PY" -c '
from analysis import runtime as R
print(f"    free memory  : {R.gb(R.available_bytes()):.1f} GB")
print(f"    reserve      : {R.RESERVE_GB:.1f} GB   (laptop default is 10.0)")
print(f"    low water    : {R.LOW_WATER_GB:.1f} GB")
print(f"    max workers  : {R.MAX_WORKERS}   (capped by core count)")
print(f"    planned now  : {R.plan_workers()} worker(s)")
'

# ── 5. Install systemd unit files ────────────────────────────────────
echo
echo "=== 5. Install systemd unit files ==="
sudo cp "$RUNTIME_DEPLOY/cyberfraud-analysis.service" /etc/systemd/system/
sudo cp "$RUNTIME_DEPLOY/cyberfraud-analysis.timer"   /etc/systemd/system/
echo "    Installed /etc/systemd/system/$SERVICE"
echo "    Installed /etc/systemd/system/$TIMER"

# systemd-analyze verify catches unit-file syntax errors now rather than
# at first fire. It warns about paths that do not exist in the sandbox
# view, so a non-zero exit is reported but not treated as fatal.
if command -v systemd-analyze >/dev/null 2>&1; then
    echo "    --- systemd-analyze verify ---"
    sudo systemd-analyze verify "/etc/systemd/system/$SERVICE" 2>&1 | sed 's/^/    /' || true
fi

# ── 6. Reload + enable + (re)start timer ─────────────────────────────
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

# ── 8. Create the derived tables (fast, and safe to repeat) ──────────
# Migrations 019-023 only. This is the part of the nightly run that
# costs nothing, and running it now means tonight's fire finds its
# schema already in place instead of creating it under time pressure.
echo
echo "=== 8. Apply analysis migrations 019-023 ==="
for m in 019_add_upload_analysis_tables \
         020_account_statement_summary \
         021_mule_account_links \
         022_statement_chain_ok \
         023_summary_untested_totals; do
    echo "    -- $m"
    sudo -u cyberfraud env -C "$BACKEND" "$VENV_PY" -m "migrations.$m" 2>&1 | sed 's/^/       /'
done

# ── 9. Verify the five derived tables exist ──────────────────────────
echo
echo "=== 9. Verify derived tables ==="
sudo -u cyberfraud env -C "$BACKEND" "$VENV_PY" -c '
import asyncio
from sqlalchemy import text
from database import engine
WANT = ["upload_ledger", "statement_transactions",
        "account_statement_summary", "id_photo_hashes",
        "mule_account_link"]
async def go():
    missing = []
    async with engine.begin() as c:
        for t in WANT:
            n = (await c.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = :t"),
                {"t": t})).scalar()
            rows = 0
            if n:
                rows = (await c.execute(text(f"SELECT COUNT(*) FROM {t}"))).scalar()
            state = "OK" if n else "MISSING"
            print(f"    {t:<28}{state:<10}{rows:>12,} rows")
            if not n:
                missing.append(t)
    await engine.dispose()
    raise SystemExit(3 if missing else 0)
asyncio.run(go())
'

# ── 10. Confirm the backup EXCLUDES these tables ─────────────────────
# The whole design depends on this: these tables are rebuildable and
# must never enter the nightly dump. If someone edits backup-db.sh and
# drops the exclusion, the dump silently grows ~374x and a dev restore
# starts destroying the parsed corpus. Cheap to assert, expensive to
# discover by accident.
echo
echo "=== 10. Confirm backup-db.sh excludes the derived tables ==="
MISS=0
for t in upload_ledger statement_transactions account_statement_summary \
         id_photo_hashes mule_account_link; do
    if grep -q "$t" "$RUNTIME_DEPLOY/backup-db.sh"; then
        echo "    $t — excluded"
    else
        echo "    $t — NOT EXCLUDED  <-- backup will carry it"
        MISS=1
    fi
done
if [ "$MISS" -ne 0 ]; then
    echo
    echo "  WARNING: backup-db.sh does not exclude every derived table."
    echo "  Fix that before the next nightly dump."
fi

# ── 11. Final summary + how to run the first backfill ────────────────
echo
echo "============================================================"
echo "  ✓ Nightly analysis installed and scheduled."
echo
echo "  The timer is live, but NO parse has run yet. The first run"
echo "  reads the entire upload corpus and takes HOURS; every run"
echo "  after it is incremental and takes 20-25 minutes."
echo
echo "  Start the first backfill when the box is quiet:"
echo "      sudo systemctl start $SERVICE"
echo
echo "  It detaches — systemd owns it, so closing your SSH session"
echo "  will not kill it. Watch it with:"
echo "      sudo journalctl -u $SERVICE -f"
echo
echo "  It is safe to interrupt (systemctl stop) and re-run: the"
echo "  ledger commits per batch, so at most the current batch is"
echo "  repeated."
echo
echo "  Next scheduled fire: see 'systemctl list-timers $TIMER'"
echo "============================================================"
