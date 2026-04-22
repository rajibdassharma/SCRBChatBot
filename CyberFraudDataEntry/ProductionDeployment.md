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
| CPU | 4 vCPU | 8 vCPU | Handles 44 CCPS stations concurrently |
| RAM | 8 GB | 16 GB | MySQL buffer pool + Python workers |
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

```nginx
# /etc/nginx/sites-available/cyberfraud

upstream backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name <SERVER_IP_OR_DOMAIN>;

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    client_max_body_size 10M;
    root /opt/cyberfraud/frontend/dist;
    index index.html;

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

```python
# /opt/cyberfraud/backend/gunicorn.conf.py

bind = "127.0.0.1:8000"
workers = 4                          # (2 * CPU_cores) + 1
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
accesslog = "/var/log/cyberfraud/access.log"
errorlog = "/var/log/cyberfraud/error.log"
loglevel = "info"
```

```bash
sudo mkdir -p /var/log/cyberfraud
sudo chown $USER:$USER /var/log/cyberfraud
```

---

## 10. Systemd Service File

The canonical copy of this file lives at `deploy/cyberfraud-backend.service`
in the repo. On every deploy, copy it into place so systemd picks up any
changes:

```bash
sudo cp deploy/cyberfraud-backend.service /etc/systemd/system/cyberfraud-backend.service
sudo systemctl daemon-reload
sudo systemctl restart cyberfraud-backend
```

```ini
# /etc/systemd/system/cyberfraud-backend.service

[Unit]
Description=CyberFraud Data Entry Backend
After=network.target mysql.service
Requires=mysql.service

[Service]
Type=notify
User=cyberfraud
Group=cyberfraud
WorkingDirectory=/opt/cyberfraud/backend
Environment="PATH=/opt/cyberfraud/backend/venv/bin:/usr/bin"
EnvironmentFile=/opt/cyberfraud/backend/.env
ExecStart=/opt/cyberfraud/backend/venv/bin/gunicorn cyber_fraud:app -c gunicorn.conf.py
ExecReload=/bin/kill -s HUP $MAINPID
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/log/cyberfraud /opt/cyberfraud/backend
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin cyberfraud
sudo chown -R cyberfraud:cyberfraud /opt/cyberfraud /var/log/cyberfraud
sudo systemctl daemon-reload
sudo systemctl enable cyberfraud-backend
sudo systemctl start cyberfraud-backend
```

---

## 11. Environment Variables

| Variable | Description | Production Value |
|----------|-------------|-----------------|
| `CFDSR_DB_HOST` | MySQL host | `localhost` |
| `CFDSR_DB_PORT` | MySQL port | `3306` |
| `CFDSR_DB_USER` | MySQL user | `cfdsr_app` (NOT root) |
| `CFDSR_DB_PASSWORD` | MySQL password | Strong random |
| `CFDSR_DB_NAME` | Database name | `cyber_fraud_dsr` |
| `CFDSR_JWT_SECRET` | JWT signing key | 64-char random hex |
| `CFDSR_JWT_EXPIRE_MINUTES` | Token expiry | `480` (8 hours) |
| `CFDSR_CORS_ORIGINS` | Allowed origins | `http://<SERVER_IP>` |

---

## 12. Seed Data

| Data | Source | Count |
|------|--------|-------|
| Districts (units) | All District CEN_PS.xlsx Column A | 36 |
| CCPS Stations | All District CEN_PS.xlsx Columns A+B | 44 |
| Users | Auto-generated per CCPS | 88 |

### Default Credentials

| Pattern | Password | Role |
|---------|----------|------|
| `<ccps_code>_admin` | `admin123` | admin |
| `<ccps_code>_user` | `police123` | unit_user |

Example: `belagavi_city_cen_crime_ps_user` / `police123`

**CRITICAL**: Change default passwords before production use.

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

- Generate strong JWT secret: `openssl rand -hex 32`
- Restrict CORS to server IP only
- Disable FastAPI `/docs` in production (`docs_url=None, redoc_url=None`)
- Add rate limiting on login endpoint (`slowapi`)
- MySQL: revoke DROP/CREATE after initial setup
- SSH: disable root login, use key-based auth
- Install `fail2ban`
- Change default passwords

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

### Daily DB Backup (cron at 2 AM)
```bash
mysqldump -u cfdsr_app -p'<PASSWORD>' --single-transaction \
    --databases cyber_fraud_dsr | gzip > /opt/cyberfraud/backups/db/$(date +%Y%m%d).sql.gz
```

Retain 30 days. Test restores periodically.

---

## 17. Update / Deployment Procedure

### Pull latest from GitHub
```bash
cd /opt/SCRBChatBot
git pull
sudo cp -r CyberFraudDataEntry/* /opt/cyberfraud/
```

### Backend
```bash
cd /opt/cyberfraud/backend
source venv/bin/activate
pip install -r requirements.txt
python seed.py  # idempotent — creates new tables, doesn't alter existing
# Run any schema patches (e.g., ALTER TABLE) if listed in release notes
sudo systemctl restart cyberfraud-backend
curl http://localhost/health
```

### Frontend
```bash
cd /opt/cyberfraud/frontend
npm ci
npm run build
sudo systemctl reload nginx
```

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
