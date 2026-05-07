#!/usr/bin/env bash
# CyberFraud — redeploy + verify ALL VAPT findings that have a code-level fix.
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
# UUID migration is destructive — the 15 affected tables are dropped and
# re-seeded. SAFE only because the application has not been used in
# production yet (seed data only). Do NOT re-run after real data exists.
#
# Idempotent for everything except the drop step. Aborts on first failure.
#
# Usage on the server (works regardless of where the source clone lives):
#   cd /opt/scrb && git pull && bash CyberFraudDataEntry/deploy/redeploy-vapt-fixes.sh

set -euo pipefail

# Resolve SOURCE relative to this script — works whether the clone is at
# /opt/scrb, /opt/SCRBChatBot, or anywhere else.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME=/opt/cyberfraud
SVC=cyberfraud-backend
NGINX_SITE=/etc/nginx/sites-available/cyberfraud

echo "=== 1. Source commit currently on disk ==="
echo "    SOURCE=$SOURCE"
cd "$SOURCE/.." && git log -1 --oneline

echo
echo "=== 2. Sync code from source to runtime ($RUNTIME) ==="
sudo cp -r "$SOURCE"/backend "$RUNTIME/"
sudo cp -r "$SOURCE"/frontend "$RUNTIME/"
sudo cp -r "$SOURCE"/deploy "$RUNTIME/"
sudo chown -R cyberfraud:cyberfraud "$RUNTIME/backend" "$RUNTIME/frontend" "$RUNTIME/deploy"

echo
echo "=== 3. Reset DB (drop all tables) + re-seed (Item 8 rec #2) ==="
echo "    Stopping backend before dropping tables to release FK locks..."
sudo systemctl stop "$SVC" || true

# Pre-production phase: drop EVERY application table (cases, mule reports
# and children, users, revoked_tokens, mule/dsr entries, police_stations,
# units) and let seed.py rebuild from `All District CEN_PS.xlsx`. Yields a
# fresh seed_credentials_*.csv. Once real data exists, switch to per-table
# migrations and remove this stage.
sudo -u cyberfraud bash -c "cd $RUNTIME/backend && venv/bin/python reset_db.py"

echo "    Re-seeding (this also recreates tables with String(36) PKs)..."
sudo -u cyberfraud bash -c "cd $RUNTIME/backend && venv/bin/python seed.py"

echo
echo "=== 4. Restart backend so new code is loaded ==="
sudo systemctl restart "$SVC"
sleep 2
sudo systemctl is-active "$SVC"

echo
echo "=== 5. Apply nginx config (server_tokens off, proxy_hide_header Server) ==="
sudo cp "$RUNTIME/deploy/nginx.conf" "$NGINX_SITE"
sudo nginx -t
sudo systemctl reload nginx

echo
echo "=== 6. Verify #5 — sanitizer code is loaded (cases + mule schemas) ==="
sudo -u cyberfraud bash -c "cd $RUNTIME/backend && venv/bin/python -c \"
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
echo "=== 7. Verify #6 — Server header does not disclose nginx version ==="
HEADERS=$(curl -skI https://localhost/ 2>&1)
SERVER_LINE=$(echo "$HEADERS" | grep -i '^server:' | head -1 | tr -d '\r')
echo "    $SERVER_LINE"
if echo "$SERVER_LINE" | grep -q '/'; then
    echo "FAIL: Server header still discloses version"
    exit 1
else
    echo "PASS: Server header has no version disclosure"
fi

echo
echo "=== 8. Verify #7 + #8 — per-record authz helper is wired into routes ==="
# These checks confirm the deployed code references the new helper.
# Full behavioral validation requires the pytest suite (run locally
# with seed users; see tests/README.md).
sudo -u cyberfraud bash -c "cd $RUNTIME/backend && venv/bin/python -c \"
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
echo "=== 9. Verify #10 — XLSX _safe_str sanitises cell content ==="
sudo -u cyberfraud bash -c "cd $RUNTIME/backend && venv/bin/python -c \"
from api.routes_mule_report import _safe_str
out = _safe_str('<script>alert(1)</script>1234')
assert '<script' not in out.lower(), 'FAIL: _safe_str leaks <script>'
assert 'onerror' not in _safe_str('<img src=x onerror=z>SBI').lower(), 'FAIL: _safe_str leaks onerror'
assert 'javascript:' not in _safe_str('javascript:alert(1)').lower(), 'FAIL: _safe_str leaks javascript:'
print('PASS: XLSX cell parser strips HTML/script/handlers at parse time')
\""

echo
echo "=== 10. Verify Item 8 rec #2 — UUID PKs on cases + mule_reports ==="
sudo -u cyberfraud bash -c "cd $RUNTIME/backend && venv/bin/python -c \"
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
echo "=== 11. Verify Item 10 rec #2 — XLSX per-cell allow-list active ==="
sudo -u cyberfraud bash -c "cd $RUNTIME/backend && venv/bin/python -c \"
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
echo "================================================="
echo "  ALL CHECKS PASSED — VAPT 7.5-7.10 + Item 8/10 LIVE"
echo "================================================="
echo
echo "For full behavioral verification (multi-user BOLA tests and XLSX upload"
echo "round-trip), run the pytest suite from a workstation against the server:"
echo "    cd backend && pytest tests/ -v"
