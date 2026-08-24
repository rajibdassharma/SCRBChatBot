# CyberFraud Data Entry — Production Deployment Guide

**Application**: CyberFraud DSR & Mule Account Data Entry System
**Client**: Karnataka State Police (SCRB / CID Cyber Crime)
**Scale**: 44 Cyber Command Police Stations (CCPS) across 36 districts
**Network**: Internal government network (KSWAN / NIC)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [VM Requirements](#2-vm-requirements)
3. [Network Setup](#3-network-setup)
4. [OS Preparation](#4-os-preparation)
5. [MySQL Production Setup](#5-mysql-production-setup)
6. [Python Backend Setup](#6-python-backend-setup)
7. [Frontend Build](#7-frontend-build)
8. [Nginx Reverse Proxy](#8-nginx-reverse-proxy)
9. [Gunicorn + Uvicorn Workers](#9-gunicorn--uvicorn-workers)
10. [Systemd Service Files](#10-systemd-service-files)
11. [Environment Variables](#11-environment-variables)
12. [Seed Data](#12-seed-data)
13. [SSL/TLS Configuration](#13-ssltls-configuration)
14. [Security Hardening](#14-security-hardening)
15. [Monitoring and Logging](#15-monitoring-and-logging)
16. [Backup Strategy](#16-backup-strategy)
17. [Update / Deployment Procedure](#17-update--deployment-procedure)
18. [Troubleshooting](#18-troubleshooting)

---

## 1. Architecture Overview

```
                       KSWAN / NIC Internal Network
                                 |
                          ┌──────┴──────┐
                          │   Nginx     │  :80 / :443
                          │  (reverse   │
                          │   proxy)    │
                          └──┬──────┬───┘
                  static /   │      │  /api/*, /health
                  files      │      │
            ┌────────────┐   │   ┌──┴────────────┐
            │  React SPA │   │   │  Gunicorn      │
            │  dist/     │   │   │  + Uvicorn     │  :8000 (localhost only)
            │  (built)   │   │   │  workers       │
            └────────────┘   │   └──────┬─────────┘
                             │          │
                             │   ┌──────┴──────┐
                             │   │   MySQL 8    │  :3306 (localhost only)
                             │   │  cyber_fraud │
                             │   │    _dsr      │
                             │   └─────────────┘
```

**Stack**:
- **Backend**: Python 3.12+ (Ubuntu 24.04 default), FastAPI (async), SQLAlchemy 2.0 + asyncmy, JWT auth, bcrypt
- **Frontend**: React 19, Vite, TypeScript, Tailwind CSS, Zustand, Recharts
- **Database**: MySQL 8.0
- **Proxy**: Nginx
- **Process manager**: systemd + Gunicorn with Uvicorn workers

---

## 2. VM Requirements

| Resource | Minimum | Recommended | Notes |
|----------|---------|-------------|-------|
| CPU | 4 vCPU | 8 vCPU | Handles 44 CCPS stations concurrently. **The live server has 2** — fine for the web app, but the nightly analysis had to be told so explicitly (`CFDSR_ANALYSIS_RESERVE_CORES=0`), or its governor reserves 2 cores for the OS and plans a single worker |
| RAM | 8 GB | 16 GB | MySQL buffer pool + Python workers. **Live: 16 GB**, `innodb_buffer_pool_size=4G` |
| Storage | 50 GB SSD | 100 GB SSD | Database growth, logs, backups |
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS | Or RHEL 8/9 per NIC policy |
| Network | 1 Gbps | 1 Gbps | Internal KSWAN connectivity |

---

## 3. Network Setup

### Ports

| Port | Service | Bind Address | Exposed |
|------|---------|-------------|---------|
| 80 | Nginx (HTTP) | 0.0.0.0 | Yes — KSWAN internal |
| 443 | Nginx (HTTPS) | 0.0.0.0 | Yes — if SSL enabled |
| 8000 | Gunicorn/Uvicorn | 127.0.0.1 | No — localhost only |
| 3306 | MySQL | 127.0.0.1 | No — localhost only |
| 22 | SSH | 0.0.0.0 | Yes — admin access only |

### Firewall (UFW)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment 'SSH'
sudo ufw allow 80/tcp comment 'HTTP'
sudo ufw allow 443/tcp comment 'HTTPS'
sudo ufw enable
```

### DNS / IP

- Request a **static internal IP** from NIC/KSWAN team
- Optionally request internal DNS (e.g., `cyberfraud.ksp.karnataka.gov.in`)
- If no DNS, users access via `http://<static-ip>/`

---

## 4. OS Preparation

```bash
sudo apt update && sudo apt upgrade -y

sudo apt install -y \
    python3 python3-venv python3-dev \
    mysql-server \
    nginx \
    curl git ufw htop unzip

# Node.js 20 LTS (for building frontend)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

---

## 5. MySQL Production Setup

### Install and Secure

```bash
sudo systemctl enable mysql
sudo systemctl start mysql
sudo mysql_secure_installation
```

### Create Dedicated Database User

```sql
sudo mysql -u root -p

CREATE DATABASE IF NOT EXISTS cyber_fraud_dsr
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER 'cfdsr_app'@'localhost'
  IDENTIFIED BY '<STRONG_RANDOM_PASSWORD>';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP
  ON cyber_fraud_dsr.* TO 'cfdsr_app'@'localhost';

FLUSH PRIVILEGES;
```

Generate a strong password: `openssl rand -base64 32`

### MySQL Tuning (`/etc/mysql/mysql.conf.d/mysqld.cnf`)

```ini
[mysqld]
bind-address = 127.0.0.1
innodb_buffer_pool_size = 4G
max_connections = 200
slow_query_log = 1
slow_query_log_file = /var/log/mysql/slow.log
long_query_time = 2
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
log_bin = /var/log/mysql/mysql-bin
expire_logs_days = 14
```

---

## 6. Clone from GitHub & Python Backend Setup

```bash
cd /opt
sudo git clone https://github.com/rajibdassharma/SCRBChatBot.git
sudo cp -r SCRBChatBot/CyberFraudDataEntry cyberfraud
sudo chown -R $USER:$USER /opt/cyberfraud

# Create venv
cd /opt/cyberfraud/backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt gunicorn openpyxl
# On a dev or build box, install everything instead:
#   pip install -r requirements-dev.txt
```

### Production .env

```bash
cat > /opt/cyberfraud/backend/.env << 'EOF'
CFDSR_DB_HOST=localhost
CFDSR_DB_PORT=3306
CFDSR_DB_USER=cfdsr_app
CFDSR_DB_PASSWORD=<YOUR_STRONG_PASSWORD>
CFDSR_DB_NAME=cyber_fraud_dsr
CFDSR_JWT_SECRET=<RANDOM_64_CHAR_SECRET>
CFDSR_JWT_ALGORITHM=HS256
CFDSR_JWT_EXPIRE_MINUTES=480
CFDSR_CORS_ORIGINS=http://<SERVER_IP>
EOF

chmod 600 /opt/cyberfraud/backend/.env
```

Generate JWT secret: `openssl rand -hex 32`

### Seed Data

```bash
cd /opt/cyberfraud/backend
source venv/bin/activate
python seed.py
```

Creates: 36 districts, 44 CCPS stations, 88 users (2 per CCPS: admin + user).

### Post-Seed Schema Patches

Run these after `seed.py` (seed creates tables but doesn't alter existing ones):

```sql
ALTER TABLE arrests ADD COLUMN statement TEXT NULL AFTER date_of_arrest;
```

---

## 7. Frontend Build

```bash
cd /opt/cyberfraud/frontend
echo 'VITE_API_BASE=' > .env.production
npm ci
npm run build
```

Nginx will serve from `/opt/cyberfraud/frontend/dist/`.

---

## 8. Nginx Reverse Proxy

The canonical config lives at `deploy/nginx.conf` in the repo — copy
that into place rather than hand-editing. Key blocks (paraphrased
from the current file):

```nginx
# /etc/nginx/sites-available/cyberfraud

upstream backend {
    server 127.0.0.1:8000;
}

server {
    listen 443 ssl;
    server_name <SERVER_IP_OR_DOMAIN>;
    ssl_certificate     /etc/ssl/certs/cyberfraud.crt;
    ssl_certificate_key /etc/ssl/private/cyberfraud.key;

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Strict-Transport-Security "max-age=31536000" always;

    # 25M covers phone-camera JPGs + bank-statement PDFs.
    # Photo upload endpoint fails with "Failed to fetch" if this is < ~5M.
    client_max_body_size 25M;

    root /opt/cyberfraud/frontend/dist;
    index index.html;

    # Proxy /uploads/* to the backend so the HMAC-signed URL middleware
    # gates every file download. Without this, nginx would fall through
    # to try_files → SPA fallback → login redirect.
    # deploy/update.sh auto-inserts this block on first run if missing.
    location /uploads/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location /health {
        proxy_pass http://backend;
        proxy_set_header Host $host;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location ~ /\. { deny all; }

    access_log /var/log/nginx/cyberfraud_access.log;
    error_log /var/log/nginx/cyberfraud_error.log;
}
```

```bash
sudo ln -s /etc/nginx/sites-available/cyberfraud /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

---

## 9. Gunicorn + Uvicorn Workers

**The config lives in the repo: [`backend/gunicorn.conf.py`](../backend/gunicorn.conf.py).**
Read it there rather than from a copy here — a snippet in a document is a
second source of truth that drifts, and this one nearly caused real harm.

Until 2026-08-23 the file existed ONLY on the production server,
hand-written once and never committed. The values were written down here
and nowhere else. That meant:

- a new machine could not start the service at all —
  `gunicorn: Error: 'gunicorn.conf.py' doesn't exist`
- a genuine recovery OF PRODUCTION would have hit the same wall, at the
  moment the server and the file were both gone

When it was finally reconstructed, the first attempt sized `workers` from
`os.cpu_count()`. Production has 2 vCPUs and runs **4** workers, so that
would have halved a box serving 90 users, and `update.sh` copies
`backend/` over the runtime — it would have shipped silently. The
committed file now matches the live one field for field.

The settings that are decisions rather than defaults:

| setting | value | why |
|---|---|---|
| `workers` | 4 | Async workers, I/O-bound app. Deliberate over-provision against 2 vCPUs — empirical, not derived |
| `timeout` | 120 | PDF/Excel reports render inside the request; a 45-station landscape sheet exceeds the default 30 s |
| `max_requests` / `_jitter` | 1000 / 50 | Recycles workers to bound any slow leak, staggered so they do not all retire at once |
| `preload_app` | False | `database.py` builds the async engine at import; preloading forks a shared pool and a dead event loop into every worker |

```bash
sudo mkdir -p /var/log/cyberfraud
sudo chown cyberfraud:cyberfraud /var/log/cyberfraud
```

The unit's `ReadWritePaths=/var/log/cyberfraud` makes this the only
directory the service may write to, so moving the logs means editing the
unit as well.

---

## 10. Systemd Service Files

Three service units live in the repo under `deploy/`:

| File | Purpose |
|---|---|
| `deploy/cyberfraud-backend.service` | Gunicorn+Uvicorn worker for the backend |
| `deploy/bootstrap.sh` | **Green-field only.** Bare machine -> running app. Can purge MySQL; never use it for a routine deploy |
| `deploy/update.sh` | **Every deploy, every environment.** Running installation -> newer one |
| `deploy/set-db-password.sh` | Changes the MySQL password in MySQL and in every `.env` together, with rollback if either half fails |
| `deploy/cyberfraud-nightly.service` | One-shot nightly chain (runs `nightly-all.sh`: analysis, then `backup-all.sh`) |
| `deploy/cyberfraud-nightly.timer` | Fires the nightly chain at 23:00 IST |
| `deploy/cyberfraud-backup.{service,timer}` | **Retired 2026-08-17.** Backup-only, 00:00 IST. Superseded by the chain above; `install-nightly.sh` disables it |
| `deploy/cyberfraud-analysis.{service,timer}` | **Retired 2026-08-17.** Analysis-only, 01:00 IST. Same |

Install once:

```bash
# Create the runtime user
sudo useradd --system --no-create-home --shell /usr/sbin/nologin cyberfraud
sudo chown -R cyberfraud:cyberfraud /opt/cyberfraud /var/log/cyberfraud

# Backend service
sudo cp /opt/scrb/CyberFraudDataEntry/deploy/cyberfraud-backend.service \
    /etc/systemd/system/cyberfraud-backend.service
sudo systemctl daemon-reload
sudo systemctl enable --now cyberfraud-backend

# Nightly analysis + backup chain -- installs the units, syncs the scripts
# into the runtime, and DISABLES the two timers it replaces.
sudo bash /opt/scrb/CyberFraudDataEntry/deploy/install-nightly.sh
```

`update.sh` does NOT re-copy these files on every deploy. If you
change the service file itself, re-run the `cp + daemon-reload` for
that unit by hand.

---

## 11. Environment Variables

| Variable | Description | Production Value |
|----------|-------------|-----------------|
| `CFDSR_DB_HOST` | MySQL host | `localhost` |
| `CFDSR_DB_PORT` | MySQL port | `3306` |
| `CFDSR_DB_USER` | MySQL user | `cfdsr_app` (NOT root) |
| `CFDSR_DB_PASSWORD` | MySQL password | Strong random |
| `CFDSR_DB_NAME` | Database name | `cyber_fraud_dsr` |
| `CFDSR_JWT_SECRET` | JWT signing key — server refuses to start if missing / default / < 32 chars | 64-char random hex (`openssl rand -hex 32`) |
| `CFDSR_JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `CFDSR_JWT_EXPIRE_MINUTES` | Token expiry | `480` (8 hours) |
| `CFDSR_CORS_ORIGINS` | Allowed origins | `https://<SERVER_IP>` |
| `CFDSR_UPLOAD_SIGNING_KEY` | HMAC key for signed `/uploads/*` URLs | 64-char random hex |
| `CFDSR_CHAT_ENABLED` | Feature flag for the Ask-the-Data chat | `false` in prod (until GPU box arrives) |
| `CFDSR_LLM_API_KEY` | Required only when chat is enabled | (empty when disabled) |

---

## 12. Seed Data

| Data | Source | Count |
|------|--------|-------|
| Districts (units) | seed CSV under `backend/data/` | 36 |
| Cyber Crime PSes | seed CSV | 45+ |
| Users | Auto-generated per PS | ~90 (unit_user + admin per PS) |
| super_admins | Manually seeded via `backend/add_test_users.py` or a bespoke script for SCRB HQ officers | small handful |

### Credential policy (post-VAPT — v1.0.1 closed 2026-05-10)

- **No default passwords.** `seed.py` generates a random secure
  password per user and writes them to `seed_credentials_<timestamp>.csv`.
  Distribute that CSV to operators via out-of-band channel and then
  delete it.
- **Every seeded user has `must_change_password = true`.** All routes
  except `/auth/change-password` return 403 until the operator sets a
  new password on first login.
- **Password reset** goes through `/api/v1/users/{id}/reset-password`
  (admin+ only) — the API generates a new random password and returns
  it once. The reset user is flagged `must_change_password = true`
  again.

### Roles (3, not 2)

| Role | Scope | Set at seed time? |
|---|---|---|
| `unit_user` | own submissions within own `(unit_id, ps_id)` | yes (one per PS) |
| `admin` | full read + write on own `(unit_id, ps_id)` | yes (one per PS) |
| `super_admin` | cross-PS oversight; only role that can use chat | manually — SCRB HQ officers only |

---

## 13. SSL/TLS Configuration

### Option A: No SSL (internal KSWAN only)
HTTP on port 80 may be acceptable. Confirm with NIC security.

### Option B: Self-Signed Certificate
```bash
sudo openssl req -x509 -nodes -days 3650 \
    -newkey rsa:2048 \
    -keyout /etc/ssl/private/cyberfraud.key \
    -out /etc/ssl/certs/cyberfraud.crt \
    -subj "/C=IN/ST=Karnataka/L=Bangalore/O=KSP/CN=<SERVER_IP>"
```

### Option C: NIC-Issued Certificate (preferred for `.gov.in` domain)

---

## 14. Security Hardening

Almost all of the below is already applied in the shipping code — see
[SecurityAudit.md](./SecurityAudit.md) for the current posture and
VAPT v1.0.1 closure status. This section is a bring-up checklist for
the OS / MySQL / SSH layer that lives outside the app.

Already applied by the app (nothing to do):

- JWT token expiry (`verify_exp=True`, 480-min lifetime)
- JWT secret validation (server refuses to start on missing / default / < 32 chars)
- Per-record `(unit_id, ps_id)` scoping — every mutation route enforces it
- Free-text HTML/script sanitisation on every write (`strip_html`)
- File upload MIME-type + size limits (25 MB nginx cap, per-endpoint app-side check)
- HMAC-signed `/uploads/*` URLs — leaked links die within 1 hour
- Login rate limiting (in-memory, per-IP)
- Security headers (X-Frame-Options, X-Content-Type-Options, HSTS)
- FastAPI `/docs` + `/openapi.json` disabled in production
- Token revocation on logout (`revoked_tokens` table)

Bring-up checklist for the OS + MySQL + SSH layer:

- [ ] Generate a strong `CFDSR_JWT_SECRET`: `openssl rand -hex 32`
- [ ] Generate a strong `CFDSR_UPLOAD_SIGNING_KEY`: same
- [ ] Restrict `CFDSR_CORS_ORIGINS` to your actual server URL — no wildcards
- [ ] MySQL: create dedicated `cfdsr_app` user (see §5); revoke DROP/CREATE after seed
- [ ] SSH: disable root login (`PermitRootLogin no`), use key-based auth only
- [ ] Install `fail2ban` for SSH brute-force protection
- [ ] UFW rules from §3 applied and `ufw enable` run
- [ ] SSL certificate installed (§13) — even self-signed is better than plain HTTP

---

## 15. Monitoring and Logging

| Log | Location |
|-----|----------|
| Gunicorn access | `/var/log/cyberfraud/access.log` |
| Gunicorn error | `/var/log/cyberfraud/error.log` |
| Nginx access | `/var/log/nginx/cyberfraud_access.log` |
| Nginx error | `/var/log/nginx/cyberfraud_error.log` |
| MySQL slow queries | `/var/log/mysql/slow.log` |
| systemd journal | `journalctl -u cyberfraud-backend` |

Health check cron:
```bash
*/5 * * * * root curl -sf http://localhost/health > /dev/null || systemctl restart cyberfraud-backend
```

---

## 16. Backup Strategy

Nightly automated via **systemd timer** — no cron.

- `cyberfraud-nightly.timer` (23:00 IST) → `cyberfraud-nightly.service`
  → `nightly-all.sh`, which runs the upload analysis and THEN
  `backup-all.sh` (`backup-db.sh` + `backup-uploads.sh`), as root
- The order is the whole point: the backup captures the analysis of the
  SAME night. The two independent timers this replaced ordered by clock
  instead of by dependency, so every backup carried yesterday's analysis
- `backup-db.sh`: gzipped mysqldump, timestamped, **excluding only
  `statement_transactions`** (27.6 GB, rebuildable from the PDFs).
  Retention keeps the newest snapshot
- `backup-uploads.sh`: **weekly full + nightly incremental** via
  `tar --listed-incremental`, uncompressed. A restore needs the full
  plus every increment after it, applied in order. Nightly fulls
  re-archived 19.5 GB to capture ~500 MB of new files; gzip returned 9%
  on already-compressed PDFs for 24 minutes of CPU
- Install once via `deploy/install-nightly.sh` (which retires
  `install-backup.sh`'s timer)

See [Operations.md § Database Backup](./Operations.md#database-backup)
for the check / restore commands. A schema-only snapshot for audit /
handover use goes through `deploy/dump-schema.sh` (see the same doc).

---

## 17. Update / Deployment Procedure

**One command.** Do not run individual steps by hand.

```bash
cd /opt/scrb && git pull && sudo bash CyberFraudDataEntry/deploy/update.sh
```

`update.sh` does:

1. `git pull` (again, in case the script itself changed)
2. Upgrade pip deps under the `cyberfraud` venv
3. Run additive DB migrations 001 → 004, 006 → 026 (idempotent; 005 skipped until chat lands)
4. Frontend `npm install && npm run build` — TS strict must pass
5. rsync backend + `frontend/dist/` into `/opt/cyberfraud/`
6. `systemctl restart cyberfraud-backend`
7. Auto-insert nginx `/uploads/` proxy block if missing + `nginx -t` + reload
8. Self-verify: `/health`, every new route responds 401, every migration's schema landed

Any single failure aborts the deploy. Idempotent — safe to re-run.

See [Operations.md § Deploying Updates](./Operations.md#deploying-updates)
for the full step-by-step breakdown, or read
`deploy/update.sh` directly.

---

## 18. Troubleshooting

| Problem | Solution |
|---------|----------|
| Backend won't start | `sudo journalctl -u cyberfraud-backend -n 50` |
| MySQL connection refused | `sudo systemctl status mysql` |
| Nginx 502 | Check backend: `sudo ss -tlnp \| grep 8000` |
| Login fails | Verify user exists: `SELECT username FROM users WHERE username='...'` |
| High memory | Reduce Gunicorn workers in `gunicorn.conf.py` |

---

## Quick Start Checklist

- [ ] VM provisioned with Ubuntu 22.04/24.04 LTS
- [ ] Firewall configured (ports 22, 80, 443)
- [ ] MySQL 8 installed, secured, dedicated user created
- [ ] Python venv + dependencies installed
- [ ] Production `.env` with strong passwords
- [ ] `seed.py` run successfully
- [ ] Frontend built and deployed to `/opt/cyberfraud/frontend/`
- [ ] Nginx configured and tested
- [ ] systemd service enabled
- [ ] `curl http://localhost/health` returns OK
- [ ] Default passwords changed
- [ ] Backup cron configured
- [ ] Log rotation configured

---

*Prepared for CyberFraud Data Entry — Karnataka State Police*
