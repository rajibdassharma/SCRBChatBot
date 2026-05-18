#!/usr/bin/env bash
# CyberFraud — INCREMENTAL UPDATE deploy.
#
# This script applies a feature update WITHOUT touching production data:
#   - No reset_db.py, no seed.py
#   - No regression-test re-runs
#   - No nginx config changes (use the destructive script for that)
#
# What it does (idempotent end-to-end):
#   1. git pull on /opt/scrb to fetch the latest source
#   2. Install / upgrade pip deps from backend/requirements.txt
#   3. Run additive DB migration 001 (adds user contact + audit columns
#      if not already present — uses INFORMATION_SCHEMA checks)
#   4. Build the frontend (npm install + npm run build)
#   5. Sync backend/ + frontend/dist/ from source to runtime
#   6. Restart the backend systemd service
#   7. Self-verify: service active + /health endpoint responding
#
# Usage on the server:
#   cd /opt/scrb && git pull && \
#     sudo bash CyberFraudDataEntry/deploy/update.sh
#
# (the leading `git pull` ensures this script picks up its own latest
#  version; the script also pulls again internally to be safe.)
#
# Aborts on first failure (set -euo pipefail). Safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$(cd "$SCRIPT_DIR/.." && pwd)"          # /opt/scrb/CyberFraudDataEntry
REPO_ROOT="$(cd "$SOURCE/.." && pwd)"           # /opt/scrb
RUNTIME=/opt/cyberfraud
SVC=cyberfraud-backend

echo "================================================================"
echo "  CyberFraud incremental update"
echo "  SOURCE : $SOURCE"
echo "  REPO   : $REPO_ROOT"
echo "  RUNTIME: $RUNTIME"
echo "================================================================"

# ── 1. Pull latest source ────────────────────────────────────────────
echo
echo "=== 1. git pull on $REPO_ROOT ==="
cd "$REPO_ROOT"
git pull
echo "    HEAD: $(git log -1 --oneline)"

# ── 2. Install / upgrade Python deps ─────────────────────────────────
echo
echo "=== 2. Install pip dependencies (catches new packages) ==="
sudo -u cyberfraud bash -c "
    cd $RUNTIME/backend
    venv/bin/pip install --quiet --upgrade -r $SOURCE/backend/requirements.txt
"
echo "    Done."

# ── 3. Run additive DB migrations ────────────────────────────────────
echo
echo "=== 3. Run additive DB migration 001 (idempotent) ==="
# Copy the migrations folder into runtime so the script can `import config`
# / `import database` from the runtime venv path.
sudo cp -r "$SOURCE/backend/migrations" "$RUNTIME/backend/"
sudo chown -R cyberfraud:cyberfraud "$RUNTIME/backend/migrations"
sudo -u cyberfraud bash -c "
    cd $RUNTIME/backend && venv/bin/python -m migrations.001_add_user_contact_columns
"

# ── 4. Build the frontend ────────────────────────────────────────────
echo
echo "=== 4. Build frontend (npm install + npm run build) ==="
cd "$SOURCE/frontend"
npm install --silent
npm run build
echo "    dist/ built:"
ls -la "$SOURCE/frontend/dist/" | head -10

# ── 5. Sync code from source to runtime ──────────────────────────────
echo
echo "=== 5. Sync backend + frontend dist to $RUNTIME ==="
sudo cp -r "$SOURCE/backend" "$RUNTIME/"
sudo cp -r "$SOURCE/frontend" "$RUNTIME/"
sudo chown -R cyberfraud:cyberfraud "$RUNTIME/backend" "$RUNTIME/frontend"

# ── 6. Restart backend ───────────────────────────────────────────────
echo
echo "=== 6. Restart backend service ==="
sudo systemctl restart "$SVC"
sleep 2
sudo systemctl is-active "$SVC"

# ── 7. Self-verify ───────────────────────────────────────────────────
echo
echo "=== 7. Self-verify ==="
# Health endpoint via nginx (proxied path)
if curl -sk --max-time 5 https://localhost/health | grep -q '"ok"'; then
    echo "    ✓ /health responding via nginx"
else
    echo "    ✗ /health check failed via nginx — checking backend directly..."
    curl -s --max-time 5 http://127.0.0.1:8000/health || true
    exit 1
fi

# New routes mounted?
if curl -sk --max-time 5 -o /dev/null -w "%{http_code}" https://localhost/api/v1/users | grep -qE '^(401|403)$'; then
    echo "    ✓ /api/v1/users mounted (returned auth error — expected for unauth'd request)"
else
    echo "    ✗ /api/v1/users not responding correctly"
    exit 1
fi

if curl -sk --max-time 5 -o /dev/null -w "%{http_code}" "https://localhost/api/v1/reports/dsr.pdf?from=2026-01-01&to=2026-01-01" | grep -qE '^(401|403)$'; then
    echo "    ✓ /api/v1/reports/dsr.pdf mounted"
else
    echo "    ✗ /api/v1/reports/dsr.pdf not responding correctly"
    exit 1
fi

echo
echo "================================================================"
echo "  ✓ Incremental update complete."
echo
echo "  Reminder: tell users of the renamed PS to pick"
echo "  'South East CEN PS' on the login dropdown."
echo "================================================================"
