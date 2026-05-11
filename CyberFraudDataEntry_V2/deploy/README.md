# Production deployment configs

Canonical copies of all the server-side config files used in production.
`git pull` + `cp` is the ONLY deployment sync step — never edit files in
`/etc/` directly without mirroring the change back here.

## Files

| File | Purpose | Server path |
|---|---|---|
| `cyberfraud-backend.service` | systemd unit for the FastAPI backend | `/etc/systemd/system/cyberfraud-backend.service` |
| `nginx.conf` | nginx site config: TLS, security headers, API proxy | `/etc/nginx/sites-available/cyberfraud` |

## One-time server install

```bash
# Systemd service
sudo cp deploy/cyberfraud-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cyberfraud-backend

# Nginx site
sudo cp deploy/nginx.conf /etc/nginx/sites-available/cyberfraud
sudo ln -sf /etc/nginx/sites-available/cyberfraud /etc/nginx/sites-enabled/cyberfraud
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# Also ensure server_tokens is off globally (CWE-200)
# Add to /etc/nginx/nginx.conf inside the http {} block if missing:
#   server_tokens off;
sudo grep -q "server_tokens off" /etc/nginx/nginx.conf || \
  sudo sed -i '/http {/a \\tserver_tokens off;' /etc/nginx/nginx.conf
sudo nginx -t && sudo systemctl reload nginx

# Ensure services survive reboots
sudo systemctl enable mysql nginx cyberfraud-backend
systemctl is-enabled mysql nginx cyberfraud-backend    # all should print: enabled
```

## Update procedure

```bash
cd /opt/cyberfraud
git pull

# Sync service + nginx files if deploy/ changed
sudo cp deploy/cyberfraud-backend.service /etc/systemd/system/
sudo cp deploy/nginx.conf /etc/nginx/sites-available/cyberfraud
sudo systemctl daemon-reload

# Rebuild frontend + restart backend + reload nginx
cd frontend && npm run build
cd ..
sudo systemctl restart cyberfraud-backend
sudo nginx -t && sudo systemctl reload nginx
```

## Verify

```bash
systemctl status cyberfraud-backend
curl -I https://<domain>/                              # should NOT show Server: nginx/x.y.z
curl -I https://<domain>/ | grep -i content-security   # should show CSP header
```
