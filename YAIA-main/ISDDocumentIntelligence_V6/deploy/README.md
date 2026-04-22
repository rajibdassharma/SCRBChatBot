# Production deployment — systemd service files

This folder contains the canonical copies of the systemd unit files used on
the air-gapped ISD production server. Changes to these files must be
reflected on the server via `git pull` + `cp`, not edited directly in
`/etc/systemd/system/`.

## Files

| File | Purpose | Listens on |
|---|---|---|
| `isd-backend.service` | FastAPI backend (uvicorn) | `:8003` |
| `isd-frontend.service` | Static file server for the built frontend dist/ | `:5176` |

## One-time server install (run these once per server)

```bash
# 1. Create the service account + log directory
sudo useradd --system --no-create-home --shell /usr/sbin/nologin isd
sudo chown -R isd:isd /opt/isd /var/log/isd
sudo mkdir -p /var/log/isd
sudo chown isd:isd /var/log/isd

# 2. Copy the service files into place
cd /opt/isd/ISDDocumentIntelligence_V6
sudo cp deploy/isd-backend.service /etc/systemd/system/isd-backend.service
sudo cp deploy/isd-frontend.service /etc/systemd/system/isd-frontend.service

# 3. Reload systemd and enable services for BOOT (this is the key step)
sudo systemctl daemon-reload
sudo systemctl enable --now isd-backend
sudo systemctl enable --now isd-frontend

# 4. Also ensure MySQL + Ollama auto-start on boot
sudo systemctl enable mysql      # if not already enabled
sudo systemctl enable ollama     # if ollama is registered as a service
```

After this, the apps will:
- Start automatically when the server boots
- Restart automatically if they crash (`Restart=on-failure`)
- Write logs to `/var/log/isd/backend.log` and `/var/log/isd/frontend.log`

## Verify reboot-survival

```bash
systemctl is-enabled isd-backend isd-frontend mysql
# All three should print: enabled
```

If any print `disabled`, run `sudo systemctl enable <name>` for that one.

## Updating after a code change

```bash
cd /opt/isd/ISDDocumentIntelligence_V6
git pull    # (or manual USB drop in the air-gapped case)

# Sync service files (only needed when deploy/*.service changes)
sudo cp deploy/isd-backend.service /etc/systemd/system/isd-backend.service
sudo cp deploy/isd-frontend.service /etc/systemd/system/isd-frontend.service
sudo systemctl daemon-reload

# Restart services
sudo systemctl restart isd-backend isd-frontend
```

## Checking status / logs

```bash
sudo systemctl status isd-backend
sudo systemctl status isd-frontend
sudo journalctl -u isd-backend -n 100 --no-pager
tail -f /var/log/isd/backend.log
```

## Rollback

```bash
cd /opt/isd/ISDDocumentIntelligence_V6
git log --oneline -10
git checkout <previous-sha>
sudo cp deploy/isd-backend.service /etc/systemd/system/isd-backend.service
sudo systemctl daemon-reload
sudo systemctl restart isd-backend isd-frontend
```
