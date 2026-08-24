# Production deployment configs

Canonical copies of all the server-side config files used in production.
`git pull` + `cp` is the ONLY deployment sync step — never edit files in
`/etc/` directly without mirroring the change back here.

## Files

| File | Purpose | Server path |
|---|---|---|
| `cyberfraud-backend.service` | systemd unit for the FastAPI backend | `/etc/systemd/system/cyberfraud-backend.service` |
| `bootstrap.sh` | **bare Ubuntu box -> running app.** Green-field install and DR | run from the checkout |
| `update.sh` | running app -> newer running app. Every deploy | run from the checkout |
| `set-db-password.sh` | change the MySQL password in MySQL AND every `.env` in one step, rolling back if either half fails | run from the checkout |
| `generate-cert.sh` | self-signed TLS cert for nginx. `bootstrap.sh` calls it when the cert is missing | run from the checkout |
| `cyberfraud-nightly.service` | **CURRENT.** One-shot unit: analysis, then backup | `/etc/systemd/system/cyberfraud-nightly.service` |
| `cyberfraud-nightly.timer` | fires the chain at 23:00 IST daily | `/etc/systemd/system/cyberfraud-nightly.timer` |
| `nightly-all.sh` | the chain: `analysis.daily` then `backup-all.sh` | `/opt/cyberfraud/deploy/nightly-all.sh` |
| `backup-db.sh` | mysqldump, excluding the rebuildable fact table | `/opt/cyberfraud/deploy/backup-db.sh` |
| `backup-uploads.sh` | weekly full + nightly incremental tar | `/opt/cyberfraud/deploy/backup-uploads.sh` |
| `cyberfraud-backup.{service,timer}` | **RETIRED 2026-08-17** — backup without the analysis in front of it | disabled by `install-nightly.sh` |
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

## One-time install of the nightly chain (runs at 23:00 IST)

> **Use `install-nightly.sh`.** The `install-backup.sh` walkthrough
> below is kept for reference to the pieces it installs, but the timer
> it enables is retired — running it re-enables a backup that fires
> without the analysis in front of it.

```bash
sudo bash /opt/cyberfraud/deploy/install-nightly.sh
```

### Superseded: backup-only install

One command — wraps git pull, deploy sync, dir setup, systemd install,
enable timer, and a manual smoke test:

```bash
sudo bash /opt/scrb/CyberFraudDataEntry/deploy/install-backup.sh
```

The script is idempotent — safe to re-run if a step fails or you tweak
any of the unit files. It exits non-zero if the manual smoke test
fails so you'll know not to rely on the nightly run yet.

Manual steps it does (in case you ever need to do them by hand):

```bash
# 1. Pull source + sync deploy/
cd /opt/scrb && sudo git pull
sudo cp -r /opt/scrb/CyberFraudDataEntry/deploy /opt/cyberfraud/
sudo chown -R cyberfraud:cyberfraud /opt/cyberfraud/deploy

# 2. Backup directory
sudo mkdir -p /opt/cyberfraud/backups
sudo chown cyberfraud:cyberfraud /opt/cyberfraud/backups
sudo chmod 750 /opt/cyberfraud/backups

# 3. Make the backup script executable
sudo chmod +x /opt/cyberfraud/deploy/backup-db.sh

# 4. Install the systemd unit files
sudo cp /opt/cyberfraud/deploy/cyberfraud-backup.service /etc/systemd/system/
sudo cp /opt/cyberfraud/deploy/cyberfraud-backup.timer   /etc/systemd/system/

# 5. Reload, enable, and start the timer (NOT the service — the timer fires it)
sudo systemctl daemon-reload
sudo systemctl enable --now cyberfraud-backup.timer

# 6. Verify the timer is scheduled
systemctl list-timers cyberfraud-backup.timer --no-pager

# 7. Run it ONCE manually to confirm it works, before waiting for 02:00
sudo systemctl start cyberfraud-backup.service
sudo journalctl -u cyberfraud-backup.service -n 30 --no-pager
ls -lh /opt/cyberfraud/backups/
```

Daily output goes to journal:
```bash
sudo journalctl -u cyberfraud-backup.service --since "1 hour ago"
```

Backups land at `/opt/cyberfraud/backups/cyber_fraud_dsr_YYYY-MM-DD_HHMM.sql.gz`,
14-day retention auto-pruned by the script.

To restore a specific dump:
```bash
gunzip -c /opt/cyberfraud/backups/cyber_fraud_dsr_2026-05-30_0200.sql.gz \
  | sudo mysql -u root -p cyber_fraud_dsr
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
