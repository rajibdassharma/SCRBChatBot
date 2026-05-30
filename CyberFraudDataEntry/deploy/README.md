# Production deployment configs

Canonical copies of all the server-side config files used in production.
`git pull` + `cp` is the ONLY deployment sync step — never edit files in
`/etc/` directly without mirroring the change back here.

## Files

| File | Purpose | Server path |
|---|---|---|
| `cyberfraud-backend.service` | systemd unit for the FastAPI backend | `/etc/systemd/system/cyberfraud-backend.service` |
| `cyberfraud-backup.service` | systemd unit for the nightly MySQL backup | `/etc/systemd/system/cyberfraud-backup.service` |
| `cyberfraud-backup.timer` | timer that fires the backup at 02:00 IST daily | `/etc/systemd/system/cyberfraud-backup.timer` |
| `backup-db.sh` | the backup script itself | `/opt/cyberfraud/deploy/backup-db.sh` |
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

## One-time backup install (cron-style, runs nightly at 02:00 IST)

```bash
# 1. Create the backup target directory, owned by the service user
sudo mkdir -p /opt/cyberfraud/backups
sudo chown cyberfraud:cyberfraud /opt/cyberfraud/backups
sudo chmod 750 /opt/cyberfraud/backups

# 2. Make sure the backup script is executable + owned correctly
sudo chmod +x /opt/cyberfraud/deploy/backup-db.sh
sudo chown cyberfraud:cyberfraud /opt/cyberfraud/deploy/backup-db.sh

# 3. Install the systemd unit files
sudo cp deploy/cyberfraud-backup.service /etc/systemd/system/
sudo cp deploy/cyberfraud-backup.timer   /etc/systemd/system/

# 4. Reload, enable, and start the timer (NOT the service — the timer fires it)
sudo systemctl daemon-reload
sudo systemctl enable --now cyberfraud-backup.timer

# 5. Verify the timer is scheduled
systemctl list-timers cyberfraud-backup.timer --no-pager
# Should show NEXT firing at 02:00 IST (= 20:30 UTC) the next morning.

# 6. Run it ONCE manually to confirm it works, before waiting for 02:00
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
