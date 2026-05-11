#!/usr/bin/env bash
# CyberFraud — full deploy: refresh source, build frontend, sync to runtime,
# (one-shot) drop+reseed DB, restart backend, reload nginx, run 6 verifies,
# and copy the fresh seed_credentials_*.csv into the invoking user's home.
#
# Cumulative coverage (Innspark Audit Reports v1.0.1 — Preliminary +
# Full-Scope dated 2026-05-05):
#   7.5      Improper input validation (cases + mule schemas)
#   7.6      Web server version disclosure (nginx server_tokens off)
#   7.7      Within-PS BOLA (per-record + role-aware authz)
#   7.8      Cross-PS BOLA (admins are PS-scoped, no cross-PS access)
#   7.10     XLSX cell payload sanitization at parse time
#   8 rec#2  UUID PKs on cases/mule_reports + 13 child tables
#   10 rec#2 XLSX per-cell allow-list (length caps, control chars, IFSC fmt)
#
# Stage 3 (drop+reseed) is destructive but marker-gated: it fires once, on
# the first deploy after the UUID + super_admin enum migrations, then
# auto-skips on every subsequent run via /opt/cyberfraud_v2/.db_migration_done.
# To force a re-reset: sudo rm /opt/cyberfraud_v2/.db_migration_done
#
# Idempotent end-to-end. Aborts on first failure (set -euo pipefail).
#
# Usage on the server:
#   cd /opt/scrb && git pull && bash CyberFraudDataEntry_V2/deploy/redeploy-vapt-fixes.sh
#
# V2 lives parallel to V1 — different runtime path, different systemd
# service, different DB, different nginx port (8443 vs 443). V1 is
# untouched.
#
# (the leading `git pull` is in the one-liner so this script picks up its
#  own latest version; the script also pulls again internally to be safe.)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$(cd "$SCRIPT_DIR/.." && pwd)"          # /opt/scrb/CyberFraudDataEntry
REPO_ROOT="$(cd "$SOURCE/.." && pwd)"           # /opt/scrb
RUNTIME=/opt/cyberfraud_v2
SVC=cyberfraud-v2-backend
NGINX_SITE=/etc/nginx/sites-available/cyberfraud_v2

# Resolve the user who invoked the script (sudo or direct) so the
# credentials CSV lands in their home, not root's.
INVOKING_USER="${SUDO_USER:-$USER}"
INVOKING_HOME="$(getent passwd "$INVOKING_USER" | cut -d: -f6)"

echo "================================================================"
echo "  CyberFraud V2 full deploy"
echo "  SOURCE: $SOURCE"
echo "  REPO  : $REPO_ROOT"
echo "  USER  : $INVOKING_USER  (home=$INVOKING_HOME)"
echo "================================================================"

echo
echo "=== 1. git pull on $REPO_ROOT ==="
cd "$REPO_ROOT"
git pull
echo "    HEAD: $(git log -1 --oneline)"

echo
echo "=== 2. Build frontend (npm install + npm run build) ==="
cd "$SOURCE/frontend"
npm install
npm run build
echo "    dist/ rebuilt:"
ls -la "$SOURCE/frontend/dist/" | head -10

echo
echo "=== 3. Sync code from source to runtime ($RUNTIME) ==="
sudo cp -r "$SOURCE"/backend "$RUNTIME/"
sudo cp -r "$SOURCE"/frontend "$RUNTIME/"
sudo cp -r "$SOURCE"/deploy "$RUNTIME/"
sudo chown -R cyberfraud_v2:cyberfraud_v2 "$RUNTIME/backend" "$RUNTIME/frontend" "$RUNTIME/deploy"

echo
echo "=== 4. Reset DB (drop all tables) + re-seed (Item 8 rec #2) ==="

# This stage is destructive — it drops EVERY application table and lets
# seed.py rebuild from `All District CEN_PS.xlsx`. It must run exactly
# once (the first deploy after the UUID + super_admin migrations) and
# never again, because real production data starts accumulating after.
# The marker file below records that the migration has been applied.
# To force a re-run (e.g. seed gone wrong), remove the marker:
#     sudo rm /opt/cyberfraud_v2/.db_migration_done
MARKER="$RUNTIME/.db_migration_done"

if [ -f "$MARKER" ]; then
    echo "    SKIPPED — marker $MARKER present (DB migration already applied)."
else
    echo "    Stopping backend before dropping tables to release FK locks..."
    sudo systemctl stop "$SVC" || true

    sudo -u cyberfraud_v2 bash -c "cd $RUNTIME/backend && venv/bin/python reset_db.py"

    echo "    Re-seeding (this also recreates tables with String(36) PKs)..."
    sudo -u cyberfraud_v2 bash -c "cd $RUNTIME/backend && venv/bin/python seed.py"

    sudo touch "$MARKER"
    sudo chown cyberfraud_v2:cyberfraud_v2 "$MARKER"
    echo "    Created marker $MARKER — future runs will skip this stage."
fi

echo
echo "=== 5. Restart backend so new code is loaded ==="
sudo systemctl restart "$SVC"
sleep 2
sudo systemctl is-active "$SVC"

echo
echo "=== 6. Apply nginx config (server_tokens off, proxy_hide_header Server) ==="
sudo cp "$RUNTIME/deploy/nginx.conf" "$NGINX_SITE"
sudo nginx -t
sudo systemctl reload nginx

echo
echo "=== 7. Verify #5 — sanitizer code is loaded (cases + mule schemas) ==="
sudo -u cyberfraud_v2 bash -c "cd $RUNTIME/backend && venv/bin/python -c \"
from utils.sanitize import strip_html
assert '<script' not in (strip_html('<script>alert(1)</script>real') or '').lower()
assert 'onerror' not in (strip_html('<img src=x onerror=alert(3)>') or '').lower()
assert 'javascript:' not in (strip_html('javascript:alert(2)') or '').lower()
# 7.5 extension: mule schemas now wire the same sanitizer
from schemas.mule import MuleReportCreate, MoneyTransferCreate, AtmWithdrawalCreate
m = MoneyTransferCreate(account_no='<script>x</script>1234', remarks='javascript:y', bank='<img onerror=z>SBI')
assert '<script' not in (m.account_no or '').lower(), 'FAIL: mule MoneyTransfer.account_no not sanitized'
assert 'javascript:' not in (m.remarks or '').lower(), 'FAIL: mule MoneyTransfer.remarks not sanitized'
assert 'onerror' not in (m.bank or '').lower(), 'FAIL: mule MoneyTransfer.bank not sanitized'
a = AtmWithdrawalCreate(atm_location='<script>q</script>MG Road')
assert '<script' not in (a.atm_location or '').lower(), 'FAIL: AtmWithdrawal.atm_location not sanitized'
print('PASS: sanitizer wired in case + mule schemas')
\""

echo
echo "=== 8. Verify #6 — Server header does not disclose nginx version ==="
HEADERS=$(curl -skI https://localhost:8443/ 2>&1)
SERVER_LINE=$(echo "$HEADERS" | grep -i '^server:' | head -1 | tr -d '\r')
echo "    $SERVER_LINE"
if echo "$SERVER_LINE" | grep -q '/'; then
    echo "FAIL: Server header still discloses version"
    exit 1
else
    echo "PASS: Server header has no version disclosure"
fi

echo
echo "=== 9. Verify #7 + #8 — per-record authz helper is wired into routes ==="
# These checks confirm the deployed code references the new helper.
# Full behavioral validation requires the pytest suite (run locally
# with seed users; see tests/README.md).
sudo -u cyberfraud_v2 bash -c "cd $RUNTIME/backend && venv/bin/python -c \"
from api import deps
assert hasattr(deps, 'check_record_access'), 'FAIL: check_record_access helper missing from api/deps.py'
import inspect
case_src = inspect.getsource(__import__('api.routes_case', fromlist=['*']))
mule_src = inspect.getsource(__import__('api.routes_mule_report', fromlist=['*']))
assert 'check_record_access' in case_src, 'FAIL: routes_case.py does not call check_record_access'
assert 'check_record_access' in mule_src, 'FAIL: routes_mule_report.py does not call check_record_access'
print('PASS: per-record authorization helper wired in case + mule-report routes')
\""

echo
echo "=== 10. Verify #10 — XLSX _safe_str sanitises cell content ==="
sudo -u cyberfraud_v2 bash -c "cd $RUNTIME/backend && venv/bin/python -c \"
from api.routes_mule_report import _safe_str
out = _safe_str('<script>alert(1)</script>1234')
assert '<script' not in out.lower(), 'FAIL: _safe_str leaks <script>'
assert 'onerror' not in _safe_str('<img src=x onerror=z>SBI').lower(), 'FAIL: _safe_str leaks onerror'
assert 'javascript:' not in _safe_str('javascript:alert(1)').lower(), 'FAIL: _safe_str leaks javascript:'
print('PASS: XLSX cell parser strips HTML/script/handlers at parse time')
\""

echo
echo "=== 11. Verify Item 8 rec #2 — UUID PKs on cases + mule_reports ==="
sudo -u cyberfraud_v2 bash -c "cd $RUNTIME/backend && venv/bin/python -c \"
from sqlalchemy import inspect as sa_inspect
from models.case import Case
from models.mule_report import MuleReport
from models.arrest import Arrest
from models.money_transfer import MoneyTransfer

for model, label in [(Case, 'cases'), (MuleReport, 'mule_reports'),
                     (Arrest, 'arrests'), (MoneyTransfer, 'money_transfers')]:
    pk = sa_inspect(model).primary_key[0]
    assert pk.type.python_type is str, f'FAIL: {label}.id is not String, got {pk.type}'
    assert pk.type.length == 36, f'FAIL: {label}.id length is {pk.type.length}, expected 36'
    print(f'  PASS: {label}.id is String(36)')
print('PASS: UUID PKs on UUID-affected tables')
\""

echo
echo "=== 12. Verify Item 10 rec #2 — XLSX per-cell allow-list active ==="
sudo -u cyberfraud_v2 bash -c "cd $RUNTIME/backend && venv/bin/python -c \"
from api.routes_mule_report import _safe_str, _safe_ifsc, _FIELD_CAPS
# Length cap
out = _safe_str('A' * 200, field='account_no')
assert len(out) <= 30, f'FAIL: account_no cap not enforced, got len={len(out)}'
# Control-char strip
out = _safe_str('ACCT\x00\x01\x021234', field='account_no')
assert '\x00' not in out and '\x01' not in out, f'FAIL: control chars survived: {out!r}'
# IFSC valid
assert _safe_ifsc('SBIN0001234') == 'SBIN0001234', 'FAIL: valid IFSC blanked'
# IFSC invalid
assert _safe_ifsc('not-a-real-ifsc') == '', 'FAIL: invalid IFSC kept'
print('PASS: XLSX per-cell allow-list (length cap + ctrl-char + IFSC) active')
\""

echo
echo "=== 13. Hand off fresh seed_credentials_*.csv (if any) ==="
shopt -s nullglob
CRED_FILES=("$RUNTIME"/backend/seed_credentials_*.csv)
shopt -u nullglob
if [ ${#CRED_FILES[@]} -gt 0 ]; then
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
    echo "    No seed_credentials_*.csv in $RUNTIME/backend/."
    echo "    (Expected when stage 4 was skipped — no DB reset on re-runs.)"
fi

cat <<EOF

================================================================
  ALL CHECKS PASSED — proceed to browser smoke test
================================================================

VAPT 7.5-7.10 + Item 8/10 + super_admin role + dashboard fixes LIVE.

Smoke-test https://117.200.49.38:8443 :

  1. Log in as a PS admin from the new CSV (use any production PS).
  2. Visit /dashboard — KPI tiles render, no blank screen.
  3. /cases/new -> save a draft -> URL becomes /cases/<long-uuid>.
     Confirm a green "Draft saved" toast appears top-right.
  4. Open the case's Unfreeze + Refunds tabs — the "FIR No" field
     is locked and shows the case's FIR.
  5. Edit it -> submit -> green toast "Case submitted".
  6. Try /cases/1 directly in the address bar — must 404.
  7. /mule/new -> create one manually, confirm UUID URL.
  8. /mule/upload -> upload a bank XLSX, confirm rows appear in the
     created mule report.
  9. Sign out as admin, sign in as the matching unit_user.
     /dashboard should be hidden from the sidebar.

Server logs if needed:
    sudo journalctl -u cyberfraud-v2-backend -n 100 --no-pager

Full behavioral test suite (run from a workstation):
    cd backend && pytest tests/ -v
EOF
