# Operations Guide — Cyber Fraud Data Entry

## Service Overview

| Service | Port | Managed By | Auto-Start |
|---------|------|-----------|------------|
| MySQL | 3306 (localhost) | systemd | Yes |
| Gunicorn (Backend) | 8000 (localhost) | systemd | Yes |
| Nginx (Reverse Proxy) | 80/443 | systemd | Yes |

---

## After a Reboot

Everything should auto-start. Verify all services are running:

```bash
sudo systemctl status mysql
sudo systemctl status cyberfraud-backend
sudo systemctl status nginx
curl http://localhost/health
```

If any service is not running, start it:

```bash
sudo systemctl start mysql
sudo systemctl start cyberfraud-backend
sudo systemctl start nginx
```

---

## Common Issues & Fixes

### App hangs or stops responding

```bash
sudo systemctl restart cyberfraud-backend
```

### Nginx 502 Bad Gateway

Backend is down. Restart it:

```bash
sudo systemctl restart cyberfraud-backend
```

If still failing, check if the backend is listening:

```bash
sudo ss -tlnp | grep 8000
```

### MySQL connection refused

```bash
sudo systemctl restart mysql
sudo systemctl restart cyberfraud-backend
```

### Login fails / Authentication errors

Verify users exist:

```bash
mysql -u root -pCyberFraud@KSP2026 -e "SELECT username, role FROM users LIMIT 10;" cyber_fraud_dsr
```

### SSL certificate expired

Regenerate (valid for 10 years):

```bash
sudo openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout /etc/ssl/private/cyberfraud.key \
    -out /etc/ssl/certs/cyberfraud.crt \
    -subj "/C=IN/ST=Karnataka/L=Bangalore/O=KSP/CN=$(hostname -I | awk '{print $1}')"
sudo systemctl reload nginx
```

---

## Restart Everything (Nuclear Option)

```bash
sudo systemctl restart mysql
sudo systemctl restart cyberfraud-backend
sudo systemctl restart nginx
curl http://localhost/health
```

---

## Check Logs

### Backend errors
```bash
sudo journalctl -u cyberfraud-backend -n 50
```

### Gunicorn access/error logs
```bash
tail -50 /var/log/cyberfraud/error.log
tail -50 /var/log/cyberfraud/access.log
```

### Nginx logs
```bash
tail -50 /var/log/nginx/cyberfraud_error.log
tail -50 /var/log/nginx/cyberfraud_access.log
```

### MySQL slow queries
```bash
tail -50 /var/log/mysql/slow.log
```

---

## Deploying Updates

**One command. Do not run the individual steps by hand.**

```bash
cd /opt/scrb && git pull && sudo bash CyberFraudDataEntry/deploy/update.sh
```

The leading `git pull` picks up the latest `update.sh` itself; the
script then re-pulls internally to be safe. Idempotent end-to-end
(safe to re-run). Aborts on the first failure — `set -euo pipefail`.

### What update.sh does

| # | Step | Notes |
|---|---|---|
| 1 | `git pull` on `/opt/scrb` | Fetches the latest source. Prints the new HEAD. |
| 2 | `pip install -r requirements.txt` | Upgrades Python deps under `cyberfraud` user's venv. Catches new packages added since last deploy. |
| 3 | Run additive DB migrations 001 → 004, 006 → 018 | Copies `migrations/` into runtime, runs each in order under the app's venv. Every migration is idempotent (INFORMATION_SCHEMA guards); no-op if already applied. **005 is deliberately skipped** (chat feature not enabled in prod). |
| 4 | `npm install && npm run build` (frontend) | Runs `tsc -b && vite build` — TS strict must pass or the deploy aborts here. |
| 5 | Sync backend + `frontend/dist/` into runtime | `sudo cp -r … /opt/cyberfraud/`, then chown to `cyberfraud:cyberfraud`. |
| 6 | Restart `cyberfraud-backend.service` | `systemctl restart` + 2 s sleep + `is-active` check. |
| 7 | Ensure nginx proxies `/uploads/*` to the backend | Auto-inserts the `location /uploads/` block into `/etc/nginx/sites-enabled/*cyberfraud*` if missing. Backs up the site config first; runs `nginx -t` before reloading; rolls back on failure. Idempotent — a re-run notices the block is already there and does nothing. |
| 8 | Self-verify | Runs a large panel of checks: `/health` responds, every new API route returns 401/403 (proof it's mounted), every migration's target schema landed (INFORMATION_SCHEMA queries). Any single failed check aborts the deploy. |

**No pre-migration backup step** — removed 2026-07-24 after too much
friction on routine deploys. The nightly systemd timer covers it (see
"Database Backup" below); run `backup-db.sh` / `backup-uploads.sh` by
hand before a risky deploy if you want the extra insurance snapshot.

### After a deploy

- Refresh the browser (Ctrl+F5) once, so stale JS from the previous
  build isn't cached.
- If the deploy shows all ✓ marks and "Incremental update complete,"
  everything's in. If it aborts mid-way, the last successful step is
  the state you're in — re-run after fixing the issue.

---

## Database Backup

Nightly automated backups via **systemd timer** — no cron. Two
scripts run under the `cyberfraud` user:

- **`deploy/backup-db.sh`** — `mysqldump --single-transaction` of
  `cyber_fraud_dsr`, gzipped, timestamped, into a backup dir.
  **Retention: keeps only the newest snapshot** (name-exclusion prune,
  deterministic — no `-mtime` guesswork).
- **`deploy/backup-uploads.sh`** — tarball of `backend/uploads/`,
  same retention.

Both are invoked together by `cyberfraud-backup.service`, triggered
nightly by `cyberfraud-backup.timer`. Installed once via
`deploy/install-backup.sh`.

### Check the timer is running

```bash
sudo systemctl status cyberfraud-backup.timer
sudo systemctl list-timers cyberfraud-backup.timer
```

### Run a backup by hand (before a risky deploy)

```bash
sudo -u cyberfraud /opt/cyberfraud/deploy/backup-db.sh
sudo -u cyberfraud /opt/cyberfraud/deploy/backup-uploads.sh
# or both at once:
sudo -u cyberfraud /opt/cyberfraud/deploy/backup-all.sh
```

### Restore from a backup

```bash
# Newest DB snapshot (whatever the retention left)
LATEST=$(ls -1t /opt/cyberfraud/backups/*.sql.gz | head -1)
gunzip -c "$LATEST" | mysql -u root -p"$CFDSR_DB_PASSWORD" cyber_fraud_dsr

# Newest uploads snapshot
LATEST_UPLOADS=$(ls -1t /opt/cyberfraud/backups/uploads-*.tar.gz | head -1)
sudo tar -xzf "$LATEST_UPLOADS" -C /opt/cyberfraud/backend/
sudo chown -R cyberfraud:cyberfraud /opt/cyberfraud/backend/uploads
```

Adjust paths if your install put the backup dir somewhere else — check
`backup-db.sh` for the exact `BACKUP_DIR` it uses.

---

## Schema Snapshot (Structure Only, No Rows)

Sometimes you need the current DDL for an auditor / new dev / offline
reader who can't SSH into the DB. Use `deploy/dump-schema.sh` — it
runs `mysqldump --no-data` and drops a timestamped `.sql` file into
`proddata/`.

```bash
cd /opt/cyberfraud
./deploy/dump-schema.sh
# ⇒ proddata/schema-snapshot-YYYYMMDD.sql
```

Reads DB creds from `backend/.env`. NOT wired into `update.sh` (no
need to snapshot on every deploy). Regenerate on demand:

- Before / after a migration you want to compare
- For a VAPT / audit handoff
- For a new-dev handover pack

Commit the resulting file if you want to preserve it as a dated
artefact — otherwise it's a working file you can discard.

The canonical, always-current source of truth for the schema is the
SQLAlchemy models under `backend/models/*.py`, plus the tables
embedded in [database.md](./database.md#10-current-schema-reference).
The snapshot is for people / tools that can't read Python.

---

## Useful Commands

| Task | Command |
|------|---------|
| Check all service status | `systemctl status mysql cyberfraud-backend nginx` |
| Health check | `curl http://localhost/health` |
| View active connections | `sudo ss -tlnp` |
| Check disk usage | `df -h` |
| Check memory usage | `free -h` |
| Check running processes | `htop` |
| Count database records | `mysql -u root -pCyberFraud@KSP2026 -e "SELECT COUNT(*) FROM cases;" cyber_fraud_dsr` |

---

## Key File Locations

| File | Path |
|------|------|
| Backend code | `/opt/cyberfraud/backend/` |
| Frontend build | `/opt/cyberfraud/frontend/dist/` |
| Backend .env | `/opt/cyberfraud/backend/.env` |
| Gunicorn config | `/opt/cyberfraud/backend/gunicorn.conf.py` |
| Nginx config | `/etc/nginx/sites-available/cyberfraud` |
| systemd service | `/etc/systemd/system/cyberfraud-backend.service` |
| SSL certificate | `/etc/ssl/certs/cyberfraud.crt` |
| SSL key | `/etc/ssl/private/cyberfraud.key` |
| Backend logs | `/var/log/cyberfraud/` |
| Nginx logs | `/var/log/nginx/` |
| Database backups | `/opt/cyberfraud/backups/` |
