#!/usr/bin/env bash
# ============================================================================
# CyberFraud — rotate the JWT signing secret (CFDSR_JWT_SECRET).
#
# What it does (idempotent, safe to re-run):
#   1. Backs up /opt/cyberfraud/backend/.env → .env.bak.<timestamp>
#   2. Generates a fresh 64-char hex secret (openssl rand -hex 32).
#   3. Replaces the existing CFDSR_JWT_SECRET= line in .env, or appends
#      it if not present. Preserves file ownership + 600 permissions.
#   4. Restarts the cyberfraud-backend systemd service.
#   5. Verifies the service is active and /health responds.
#   6. Prints the new secret ONCE so it can be captured (1Password etc.).
#
# Side effects:
#   - All existing JWTs become invalid. Anyone with the app open will
#     get 401 on their next call and be redirected to /login. This is
#     the intended security behaviour for a secret rotation.
#   - .env backup is left on disk at the path printed at the end. Delete
#     it once you're sure the rotation succeeded (it contains the OLD
#     secret).
#
# Usage on the server:
#   sudo bash /opt/scrb/CyberFraudDataEntry/deploy/rotate-jwt-secret.sh
#
# Rollback (if something goes wrong):
#   sudo cp <printed-backup-path> /opt/cyberfraud/backend/.env
#   sudo systemctl restart cyberfraud-backend
# ============================================================================

set -euo pipefail

ENV_FILE=/opt/cyberfraud/backend/.env
SVC=cyberfraud-backend
ENV_OWNER=cyberfraud
ENV_GROUP=cyberfraud

echo "================================================================"
echo "  CyberFraud — rotate JWT signing secret"
echo "  .env : $ENV_FILE"
echo "  svc  : $SVC"
echo "================================================================"

# ── Sanity checks ────────────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found" >&2
    exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
    echo "ERROR: openssl not installed" >&2
    exit 1
fi
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: must run as root (use sudo)" >&2
    exit 1
fi

# ── 1. Backup .env ───────────────────────────────────────────────────
TS=$(date +'%Y%m%d_%H%M%S')
BAK="${ENV_FILE}.bak.${TS}"
cp -p "$ENV_FILE" "$BAK"
echo "=== 1. Backed up .env → $BAK"

# ── 2. Generate new secret ───────────────────────────────────────────
# openssl rand -hex 32 → 32 bytes = 64 hex chars. Well above the
# 32-char minimum enforced by config.py.
NEW_SECRET=$(openssl rand -hex 32)
echo "=== 2. Generated 64-char hex secret"

# ── 3. Replace or append CFDSR_JWT_SECRET in .env ───────────────────
# The hex secret contains only [0-9a-f] so sed delimiter `|` is safe.
if grep -q '^CFDSR_JWT_SECRET=' "$ENV_FILE"; then
    sed -i "s|^CFDSR_JWT_SECRET=.*|CFDSR_JWT_SECRET=${NEW_SECRET}|" "$ENV_FILE"
    echo "=== 3. Replaced existing CFDSR_JWT_SECRET line"
else
    echo "CFDSR_JWT_SECRET=${NEW_SECRET}" >> "$ENV_FILE"
    echo "=== 3. Appended CFDSR_JWT_SECRET to .env"
fi

# sed -i can change ownership on some setups — re-assert it.
chown "${ENV_OWNER}:${ENV_GROUP}" "$ENV_FILE"
chmod 600 "$ENV_FILE"
echo "    .env owner = ${ENV_OWNER}:${ENV_GROUP}, mode = 600"

# ── 4. Restart backend ───────────────────────────────────────────────
echo
echo "=== 4. Restart $SVC"
systemctl restart "$SVC"
sleep 2

# ── 5. Verify service is active ──────────────────────────────────────
echo
echo "=== 5. Self-verify"
if systemctl is-active "$SVC" >/dev/null; then
    echo "    ✓ $SVC is active"
else
    echo "    ✗ $SVC failed to start. Recent journal:"
    journalctl -u "$SVC" -n 30 --no-pager
    echo
    echo "ROLLBACK:  sudo cp $BAK $ENV_FILE && sudo systemctl restart $SVC"
    exit 2
fi

# ── 6. Health check ──────────────────────────────────────────────────
if curl -sk --max-time 5 https://localhost/health | grep -q '"ok"'; then
    echo "    ✓ /health responding via nginx"
elif curl -s --max-time 5 http://127.0.0.1:8000/health | grep -q '"ok"'; then
    echo "    ✓ /health responding via direct backend (nginx may be down)"
else
    echo "    ✗ /health check failed"
    journalctl -u "$SVC" -n 30 --no-pager
    echo
    echo "ROLLBACK:  sudo cp $BAK $ENV_FILE && sudo systemctl restart $SVC"
    exit 3
fi

# Sanity: the new code refuses to start if JWT_SECRET is default or
# <32 chars. If we got here AND the new secret is 64 chars, both checks
# passed. Confirm the warning is no longer in the journal.
if journalctl -u "$SVC" --since "30 seconds ago" --no-pager | grep -q "JWT_SECRET is using the public default"; then
    echo "    ✗ JWT_SECRET still reads as the default — .env edit didn't stick"
    exit 4
fi
echo "    ✓ No JWT_SECRET default-value warning in recent journal"

# ── 7. Print the new secret ONCE ─────────────────────────────────────
echo
echo "================================================================"
echo "  ✓ JWT secret rotated."
echo
echo "  CAPTURE THIS NOW (this is the only time it's printed):"
echo
echo "    CFDSR_JWT_SECRET=${NEW_SECRET}"
echo
echo "  Store it in your password manager / sealed channel."
echo
echo "  All existing user sessions are now INVALID. Active users will"
echo "  be redirected to /login on their next API call."
echo
echo "  Old .env backed up at: $BAK"
echo "  (Contains the OLD secret — delete once you're confident the"
echo "   rotation is fully verified by real user logins.)"
echo "================================================================"
