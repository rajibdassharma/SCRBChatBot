#!/usr/bin/env bash
# CyberFraud — redeploy + verify VAPT findings 7.5 (input validation)
# and 7.6 (Server header disclosure) on the production server.
#
# Idempotent: safe to re-run. Aborts on first failure.
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
echo "=== 3. Restart backend so new sanitizer code is loaded ==="
sudo systemctl restart "$SVC"
sleep 2
sudo systemctl is-active "$SVC"

echo
echo "=== 4. Apply new nginx config (server_tokens off, proxy_hide_header Server) ==="
sudo cp "$RUNTIME/deploy/nginx.conf" "$NGINX_SITE"
sudo nginx -t
sudo systemctl reload nginx

echo
echo "=== 5. Verify #5 — sanitizer code is loaded in the running backend ==="
sudo -u cyberfraud bash -c "cd $RUNTIME/backend && venv/bin/python -c \"
from utils.sanitize import strip_html
out = strip_html('<script>alert(1)</script>real facts')
print('OUTPUT:', repr(out))
assert '<script' not in out.lower(), 'FAIL: <script> survived sanitization'
assert 'onerror' not in strip_html('<img src=x onerror=alert(3)>').lower(), 'FAIL: onerror survived'
assert 'javascript:' not in strip_html('javascript:alert(2)').lower(), 'FAIL: javascript: survived'
print('PASS: sanitizer strips <script>, onerror, and javascript:')
\""

echo
echo "=== 6. Verify #6 — Server header does not disclose nginx version ==="
HEADERS=$(curl -skI https://localhost/ 2>&1)
SERVER_LINE=$(echo "$HEADERS" | grep -i '^server:' | head -1 | tr -d '\r')
echo "    $SERVER_LINE"
# Audit requirement (Innspark VAPT 7.6): "Remove or minimize the Server
# response header." A bare "Server: nginx" with no version satisfies it;
# only a "/X.Y.Z" version string would still expose the finding.
if echo "$SERVER_LINE" | grep -q '/'; then
    echo "FAIL: Server header still discloses version"
    exit 1
else
    echo "PASS: Server header has no version disclosure"
fi

echo
echo "================================================="
echo "  ALL CHECKS PASSED — VAPT 7.5 and 7.6 now LIVE"
echo "================================================="
