#!/usr/bin/env bash
# CyberFraud — top-level deploy orchestrator.
# Idempotent: safe to re-run. Stage 3 of the inner script self-skips
# after the first successful migration via a marker file.
#
# What this does:
#   A. git pull the source repo
#   B. npm install + npm run build  (regenerate frontend/dist)
#   C. invoke redeploy-vapt-fixes.sh:
#        - sync code to /opt/cyberfraud
#        - first-run only: drop+reseed DB (User.role enum widening + UUIDs)
#        - restart backend, reload nginx, run 8 verification checks
#   D. copy any new seed_credentials_*.csv to the invoking user's home
#      so it can be scp'd off the server, then printed for distribution
#
# Aborts on the first failed step (set -euo pipefail).
#
# Usage:
#   cd /opt/scrb && git pull && bash CyberFraudDataEntry/deploy/deploy.sh
#
# (the leading `git pull` is also done inside this script — it's there
#  in the one-liner so you re-pick up changes to deploy.sh itself.)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$(cd "$SCRIPT_DIR/.." && pwd)"          # /opt/scrb/CyberFraudDataEntry
REPO_ROOT="$(cd "$SOURCE/.." && pwd)"           # /opt/scrb
RUNTIME=/opt/cyberfraud

# Resolve the user who invoked the script (sudo or direct) so we can
# drop the credentials CSV in their home, not root's.
INVOKING_USER="${SUDO_USER:-$USER}"
INVOKING_HOME="$(getent passwd "$INVOKING_USER" | cut -d: -f6)"

echo "================================================================"
echo "  CyberFraud full-stack deploy"
echo "  SOURCE: $SOURCE"
echo "  REPO  : $REPO_ROOT"
echo "  USER  : $INVOKING_USER  (home=$INVOKING_HOME)"
echo "================================================================"

# ── A. Refresh source ────────────────────────────────────────────────
echo
echo "=== A. git pull on $REPO_ROOT ==="
cd "$REPO_ROOT"
git pull
echo "    HEAD: $(git log -1 --oneline)"

# ── B. Build frontend ────────────────────────────────────────────────
echo
echo "=== B. Build frontend ($SOURCE/frontend) ==="
cd "$SOURCE/frontend"
npm install
npm run build
echo "    dist/ rebuilt:"
ls -la "$SOURCE/frontend/dist/" | head -10

# ── C. Run the existing redeploy script (DB + backend + nginx + verify)
echo
echo "=== C. Run redeploy-vapt-fixes.sh ==="
bash "$SOURCE/deploy/redeploy-vapt-fixes.sh"

# ── D. Copy fresh seed credentials out (if any) ──────────────────────
echo
echo "=== D. Copy fresh seed_credentials_*.csv to $INVOKING_HOME ==="
shopt -s nullglob
CRED_FILES=("$RUNTIME"/backend/seed_credentials_*.csv)
shopt -u nullglob
if [ ${#CRED_FILES[@]} -gt 0 ]; then
    # Pick the newest one (in case multiple exist from past runs)
    LATEST_CSV=$(ls -t "$RUNTIME"/backend/seed_credentials_*.csv | head -1)
    DEST="$INVOKING_HOME/$(basename "$LATEST_CSV")"
    sudo cp "$LATEST_CSV" "$DEST"
    sudo chown "$INVOKING_USER:$INVOKING_USER" "$DEST"
    echo "    Copied: $LATEST_CSV"
    echo "    To    : $DEST"
    echo
    echo "    >>> scp this file off the server now, distribute to PSes,"
    echo "    >>> then DELETE both copies (server + your laptop)."
else
    echo "    No seed_credentials_*.csv found in $RUNTIME/backend/."
    echo "    (Expected when stage 3 was skipped — no DB reset on re-runs.)"
fi

# ── Final summary + smoke-test prompt ────────────────────────────────
cat <<EOF

================================================================
  DEPLOY OK — proceed to browser smoke test
================================================================

Smoke-test https://117.200.49.38 :

  1. Log in as a PS admin from the new CSV (use any production PS).
  2. Visit /dashboard — KPI tiles render, no blank screen.
  3. /cases/new → save a draft → URL becomes /cases/<long-uuid>.
     Confirm a green "Draft saved" toast appears top-right.
  4. Open the case's Unfreeze + Refunds tabs — the "FIR No" field
     is locked and shows the case's FIR.
  5. Edit it → submit → green toast "Case submitted".
  6. Try /cases/1 directly in the address bar — must 404.
  7. /mule/new → create one manually, confirm UUID URL.
  8. /mule/upload → upload a bank XLSX, confirm rows appear in the
     created mule report.
  9. Sign out as admin, sign in as the matching unit_user.
     /dashboard should be hidden from the sidebar.

If anything in steps 1-9 looks wrong, capture the browser dev-tools
Network tab + the server log:
    sudo journalctl -u cyberfraud-backend -n 100 --no-pager
EOF
