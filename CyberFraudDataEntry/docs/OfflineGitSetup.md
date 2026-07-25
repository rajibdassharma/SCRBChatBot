# Offline Git Setup — Air-Gapped Government Network (KSWAN)

Guide for managing code deployments on a server with no internet access.

---

## Overview

Git works fully offline — all commits, branches, logs, and diffs are local operations. For the government network (KSWAN/NIC), we use either:

- **Option A:** SSH-based git remote (if laptop can reach server on KSWAN)
- **Option B:** Git bundles (for fully air-gapped transfers via USB)

---

## Initial Setup on Server

### Create a bare Git repository on the server

```bash
sudo mkdir -p /opt/git-repos
sudo git init --bare /opt/git-repos/CyberFraudDataEntry.git
sudo chown -R cyberfraud:cyberfraud /opt/git-repos
```

### Initialize the deployed app as a Git repo

```bash
cd /opt/cyberfraud
git init
git remote add local /opt/git-repos/CyberFraudDataEntry.git
git add .
git commit -m "Initial deployment"
git push local main
```

---

## Option A: SSH Push from Laptop (KSWAN Network)

Use this when your laptop is connected to the same KSWAN network as the server.

### One-time setup on your laptop

```bash
cd CyberFraudDataEntry
git remote add server ssh://cyberfraud@<SERVER_IP>/opt/git-repos/CyberFraudDataEntry.git
```

### Push updates from laptop to server

```bash
# On your laptop — push latest code
git push server main
```

### Apply updates on the server

```bash
# SSH into the server
cd /opt/cyberfraud
git pull local main

# Restart services
sudo systemctl restart cyberfraud-backend
```

### If frontend changed

```bash
cd /opt/cyberfraud/frontend
npm ci
npx vite build
sudo systemctl reload nginx
```

---

## Option B: Git Bundle (Fully Air-Gapped / USB Transfer)

Use this when your laptop cannot directly reach the server. Transfer code via USB drive.

### Step 1: Create a bundle on your laptop (with internet)

```bash
cd CyberFraudDataEntry

# Full repo bundle (first time)
git bundle create cyberfraud-full.bundle --all

# Or incremental bundle (subsequent updates — only new commits)
git bundle create cyberfraud-update.bundle origin/main..main
```

### Step 2: Copy to USB drive

Copy the `.bundle` file to a USB drive.

### Step 3: On the server — apply the bundle

```bash
# Copy from USB to server
cp /media/usb/cyberfraud-full.bundle /tmp/

# First time — clone from bundle
cd /opt
git clone /tmp/cyberfraud-full.bundle cyberfraud-from-bundle
sudo cp -r cyberfraud-from-bundle/* /opt/cyberfraud/
sudo chown -R cyberfraud:cyberfraud /opt/cyberfraud

# Subsequent updates — pull from bundle
cd /opt/cyberfraud
git pull /tmp/cyberfraud-update.bundle main
```

### Step 4: Restart services

```bash
sudo systemctl restart cyberfraud-backend

# If frontend changed
cd /opt/cyberfraud/frontend
npm ci
npx vite build
sudo systemctl reload nginx
```

---

## Option C: Simple File Copy (No Git on Server)

Simplest approach — just copy changed files. No git needed on the server.

### From laptop via SCP

```bash
# Copy specific files
scp backend/main.py cyberfraud@<SERVER_IP>:/opt/cyberfraud/backend/
scp backend/api/routes_auth.py cyberfraud@<SERVER_IP>:/opt/cyberfraud/backend/api/

# Copy entire backend
scp -r backend/ cyberfraud@<SERVER_IP>:/opt/cyberfraud/

# Restart
ssh cyberfraud@<SERVER_IP> "sudo systemctl restart cyberfraud-backend"
```

### Via USB drive

```bash
# Copy from USB to server
sudo cp -r /media/usb/CyberFraudDataEntry/* /opt/cyberfraud/
sudo chown -R cyberfraud:cyberfraud /opt/cyberfraud
sudo systemctl restart cyberfraud-backend
```

---

## Quick Reference

| Scenario | Method | Command |
|----------|--------|---------|
| Laptop on KSWAN | SSH push | `git push server main` |
| No network access | Git bundle | `git bundle create update.bundle` → USB → `git pull /tmp/update.bundle main` |
| Quick hotfix | SCP | `scp file.py user@server:/opt/cyberfraud/backend/` |
| Full redeploy | USB copy | `cp -r /media/usb/* /opt/cyberfraud/` |

### After any update on the server

```bash
# Always restart backend
sudo systemctl restart cyberfraud-backend

# Only if frontend changed
cd /opt/cyberfraud/frontend && npm ci && npx vite build
sudo systemctl reload nginx

# Verify
curl http://localhost/health
```

---

## Verifying Bundle Integrity

Before applying a bundle, verify it:

```bash
git bundle verify /tmp/cyberfraud-update.bundle
```

This checks that the bundle is valid and the required commits exist.

---

## SSH Key Setup (for Option A)

To avoid typing passwords every time:

### On your laptop

```bash
ssh-keygen -t ed25519 -C "developer@ksp"
ssh-copy-id cyberfraud@<SERVER_IP>
```

Now `git push server main` and `ssh` will work without a password prompt.
