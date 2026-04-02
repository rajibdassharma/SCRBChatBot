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

### Pull latest code
```bash
cd /opt/SCRBChatBot
git pull
sudo cp -r CyberFraudDataEntry/* /opt/cyberfraud/
sudo chown -R cyberfraud:cyberfraud /opt/cyberfraud
```

### Update backend
```bash
cd /opt/cyberfraud/backend
source venv/bin/activate
pip install -r requirements.txt
python seed.py
sudo systemctl restart cyberfraud-backend
curl http://localhost/health
```

### Update frontend
```bash
cd /opt/cyberfraud/frontend
npm ci
npx vite build
sudo systemctl reload nginx
```

---

## Database Backup

### Manual backup
```bash
mysqldump -u root -pCyberFraud@KSP2026 --single-transaction cyber_fraud_dsr > /opt/cyberfraud/backups/$(date +%Y%m%d_%H%M%S).sql
```

### Restore from backup
```bash
mysql -u root -pCyberFraud@KSP2026 cyber_fraud_dsr < /opt/cyberfraud/backups/FILENAME.sql
```

### Setup daily backup cron (2 AM)
```bash
sudo mkdir -p /opt/cyberfraud/backups
sudo chown cyberfraud:cyberfraud /opt/cyberfraud/backups

sudo crontab -e
# Add this line:
0 2 * * * mysqldump -u root -pCyberFraud@KSP2026 --single-transaction cyber_fraud_dsr | gzip > /opt/cyberfraud/backups/$(date +\%Y\%m\%d).sql.gz
```

### Cleanup old backups (keep 30 days)
```bash
find /opt/cyberfraud/backups -name "*.sql.gz" -mtime +30 -delete
```

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
