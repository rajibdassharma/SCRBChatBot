#!/usr/bin/env bash
# Regenerate a self-signed cert + key for the CyberFraud nginx config.
# Safe to re-run — overwrites whatever's at the two paths.
#
# Usage:
#   sudo bash deploy/generate-cert.sh
#
# After this, apply the nginx config:
#   sudo cp deploy/nginx.conf /etc/nginx/sites-available/cyberfraud
#   sudo nginx -t && sudo systemctl reload nginx

set -euo pipefail

CERT_PATH="/etc/ssl/certs/cyberfraud.crt"
KEY_PATH="/etc/ssl/private/cyberfraud.key"
COMMON_NAME="${CYBERFRAUD_CERT_CN:-117.200.49.38}"

echo "Generating self-signed cert for CN=${COMMON_NAME}"
echo "  cert -> ${CERT_PATH}"
echo "  key  -> ${KEY_PATH}"

openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout "${KEY_PATH}" \
    -out "${CERT_PATH}" \
    -subj "/C=IN/ST=Karnataka/L=Bangalore/O=KSP/CN=${COMMON_NAME}"

chmod 600 "${KEY_PATH}"
chmod 644 "${CERT_PATH}"

echo ""
echo "Done. Files:"
ls -la "${CERT_PATH}" "${KEY_PATH}"
