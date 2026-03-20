#!/bin/bash
# ============================================================================
# ISD Document Intelligence V5 — Production Server Setup Script
# Target: Ubuntu 24.04 + NVIDIA H100 GPU + MySQL 8.x
# ============================================================================
# Usage:
#   1. Copy this file to the server:  scp setup_production.sh user@SERVER_IP:~/
#   2. SSH into server:               ssh user@SERVER_IP
#   3. Make executable:               chmod +x setup_production.sh
#   4. Run a phase:                   ./setup_production.sh phase1
#
# Phases:
#   phase1  — Fix NVIDIA drivers, hold versions, reboot
#   phase2  — Install MySQL, Ollama, Miniconda, Node.js, nginx
#   phase3  — Clone repo, configure backend, build frontend
#   phase4  — Configure nginx, SSL, systemd service
#   phase5  — Create admin user, firewall rules, verify
# ============================================================================

set -e  # Exit on error

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[ISD]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; }

# ============================================================================
# PHASE 1: Fix NVIDIA & System Updates
# ============================================================================
phase1() {
    log "=== PHASE 1: System Updates & NVIDIA Fix ==="

    # Fix any broken packages
    log "Fixing broken packages..."
    sudo dpkg --configure -a || true
    sudo apt --fix-broken install -y || true

    # Remove conflicting NVIDIA packages if stuck
    for pkg in libnvidia-gl-580 libnvidia-gl-575; do
        if dpkg -l | grep -q "$pkg"; then
            log "Removing conflicting package: $pkg"
            sudo dpkg --remove --force-remove-reinstreq "$pkg" || true
        fi
    done

    sudo apt --fix-broken install -y || true

    # Hold NVIDIA driver versions to prevent future conflicts
    log "Holding NVIDIA driver versions..."
    sudo apt-mark hold nvidia-driver-575 nvidia-driver-580 \
        libnvidia-gl-580 libnvidia-gl-575 2>/dev/null || true

    # System updates (skipping held NVIDIA packages)
    log "Running system updates..."
    sudo apt update
    sudo apt upgrade -y

    # Install basic tools
    log "Installing basic tools..."
    sudo apt install -y curl wget git unzip build-essential \
        ca-certificates gnupg lsb-release software-properties-common

    log "=== PHASE 1 COMPLETE ==="
    log "Now REBOOT the server:  sudo reboot"
    log "After reboot, verify GPU:  nvidia-smi"
    log "Then run:  ./setup_production.sh phase2"
}

# ============================================================================
# PHASE 2: Install MySQL, Ollama, Python, Node.js, nginx
# ============================================================================
phase2() {
    log "=== PHASE 2: Install Core Software ==="

    # Verify GPU first
    if nvidia-smi > /dev/null 2>&1; then
        log "GPU detected:"
        nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
    else
        err "nvidia-smi not working! Fix GPU drivers first."
        exit 1
    fi

    # --- MySQL 8.x ---
    log "Installing MySQL 8.x..."
    sudo apt install -y mysql-server

    sudo systemctl enable mysql
    sudo systemctl start mysql

    # Create database and user
    log "Creating ISDIntelligence database..."
    read -sp "Enter MySQL root password (press Enter if none set): " MYSQL_ROOT_PASS
    echo

    if [ -z "$MYSQL_ROOT_PASS" ]; then
        sudo mysql <<EOF
CREATE DATABASE IF NOT EXISTS ISDIntelligence
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'CHANGE_ME_STRONG_PASSWORD';
FLUSH PRIVILEGES;
EOF
        warn "MySQL root password set to 'CHANGE_ME_STRONG_PASSWORD' — change it!"
    else
        mysql -u root -p"$MYSQL_ROOT_PASS" <<EOF
CREATE DATABASE IF NOT EXISTS ISDIntelligence
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
FLUSH PRIVILEGES;
EOF
    fi

    log "MySQL installed and ISDIntelligence database created."

    # Verify
    sudo systemctl status mysql --no-pager -l | head -5

    # --- Ollama ---
    log "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh

    # Configure Ollama to bind to localhost only
    sudo mkdir -p /etc/systemd/system/ollama.service.d
    cat <<EOF | sudo tee /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable ollama
    sudo systemctl restart ollama

    log "Pulling LLM models (this will take 30-60 minutes)..."
    log "Pulling mxbai-embed-large (embedding model)..."
    ollama pull mxbai-embed-large

    log "Pulling gemma3:12b (fast model for testing)..."
    ollama pull gemma3:12b

    log "Pulling llama3.3:70b (production model — ~40GB download)..."
    log "This is the largest download. Please wait..."
    ollama pull llama3.3:70b

    # Verify GPU usage
    log "Verifying GPU usage..."
    ollama run gemma3:12b "Say hello" > /dev/null 2>&1
    ollama ps

    # --- Miniconda ---
    log "Installing Miniconda..."
    if [ ! -d "/opt/miniconda3" ]; then
        wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh
        sudo bash /tmp/miniconda.sh -b -p /opt/miniconda3
        rm /tmp/miniconda.sh
    fi

    # Add to PATH for current session
    export PATH="/opt/miniconda3/bin:$PATH"

    # Add to .bashrc if not already there
    if ! grep -q "miniconda3" ~/.bashrc; then
        echo 'export PATH="/opt/miniconda3/bin:$PATH"' >> ~/.bashrc
    fi

    # Create Python environment
    log "Creating Python environment..."
    /opt/miniconda3/bin/conda create -n isd python=3.11 -y 2>/dev/null || true

    log "Python environment ready at /opt/miniconda3/envs/isd/"

    # --- Node.js ---
    log "Installing Node.js 20.x..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt install -y nodejs
    node --version
    npm --version

    # --- nginx ---
    log "Installing nginx..."
    sudo apt install -y nginx
    sudo systemctl enable nginx

    log "=== PHASE 2 COMPLETE ==="
    log "Installed: MySQL, Ollama (3 models), Miniconda, Node.js, nginx"
    log "Next run:  ./setup_production.sh phase3"
}

# ============================================================================
# PHASE 3: Deploy Application Code
# ============================================================================
phase3() {
    log "=== PHASE 3: Deploy Application ==="

    export PATH="/opt/miniconda3/bin:$PATH"

    # Create app directory
    sudo mkdir -p /opt/isd
    sudo chown $USER:$USER /opt/isd

    # Clone or copy the repo
    if [ -d "/opt/isd/backend" ]; then
        log "Application directory already exists. Updating..."
        cd /opt/isd
    else
        log "Enter the Git repository URL (or press Enter to skip and copy files manually):"
        read -r REPO_URL
        if [ -n "$REPO_URL" ]; then
            git clone "$REPO_URL" /tmp/isd-repo
            cp -r /tmp/isd-repo/YAIA-main/ISDDocumentIntelligence_V5/* /opt/isd/
            rm -rf /tmp/isd-repo
        else
            warn "Skipping git clone. Copy files manually to /opt/isd/"
            warn "Expected structure: /opt/isd/backend/, /opt/isd/frontend/"
            log "After copying, run this phase again."
            return
        fi
    fi

    # --- Backend Setup ---
    log "Installing backend Python dependencies..."
    /opt/miniconda3/envs/isd/bin/pip install -r /opt/isd/backend/requirements.txt
    /opt/miniconda3/envs/isd/bin/pip install docling 2>/dev/null || warn "Docling install failed (optional — PDF parsing fallback available)"

    # --- Configure Backend .env ---
    log "Configuring backend .env..."
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(48))")

    read -sp "Enter MySQL password for root user: " MYSQL_PASS
    echo

    # Ask for LLM model
    log "Select primary LLM model:"
    log "  1) llama3.3:70b  (best accuracy, recommended for H100)"
    log "  2) gemma3:12b    (faster, good for testing)"
    read -p "Choice [1]: " MODEL_CHOICE
    if [ "$MODEL_CHOICE" = "2" ]; then
        PDF_MODEL="gemma3:12b"
    else
        PDF_MODEL="llama3.3:70b"
    fi

    cat > /opt/isd/backend/.env <<EOF
OLLAMA_BASE_URL=http://127.0.0.1:11434
PDF_MODEL=${PDF_MODEL}
EMBED_MODEL=mxbai-embed-large
CHROMA_PATH=/opt/isd/chroma_db_v5
WHISPER_MODEL=small

# JWT Authentication
JWT_SECRET_KEY=${JWT_SECRET}
JWT_EXPIRE_HOURS=12

# RAG Features
ENABLE_HYBRID_SEARCH=true
ENABLE_MULTI_QUERY=true
ENABLE_RERANKING=true
USE_LLM_PARSER=true
MAX_LLM_CALLS_PDF=25

# MySQL
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=${MYSQL_PASS}
MYSQL_DATABASE=ISDIntelligence
EOF

    chmod 600 /opt/isd/backend/.env
    log "Backend .env configured (permissions: 600)"

    # --- Test backend starts ---
    log "Testing backend startup..."
    cd /opt/isd/backend
    /opt/miniconda3/envs/isd/bin/python -c "
from config import *
print(f'  PDF_MODEL:    {PDF_MODEL}')
print(f'  EMBED_MODEL:  {EMBED_MODEL}')
print(f'  MYSQL_HOST:   {MYSQL_HOST}')
print(f'  MYSQL_DB:     {MYSQL_DATABASE}')
print(f'  CHROMA_PATH:  {CHROMA_PATH}')
print('Config OK')
"

    # --- Frontend Build ---
    log "Building frontend..."
    read -p "Enter server IP or domain (e.g., 192.168.1.100): " SERVER_IP

    echo "VITE_API_BASE=https://${SERVER_IP}" > /opt/isd/frontend/.env

    cd /opt/isd/frontend
    npm install --legacy-peer-deps 2>/dev/null
    npm run build

    if [ -d "/opt/isd/frontend/dist" ]; then
        log "Frontend built successfully at /opt/isd/frontend/dist/"
    else
        err "Frontend build failed!"
        exit 1
    fi

    log "=== PHASE 3 COMPLETE ==="
    log "Backend configured, frontend built."
    log "Next run:  ./setup_production.sh phase4"
}

# ============================================================================
# PHASE 4: nginx, SSL, systemd Service
# ============================================================================
phase4() {
    log "=== PHASE 4: nginx, SSL & systemd Service ==="

    read -p "Enter server IP or domain: " SERVER_IP

    # --- Self-signed SSL Certificate ---
    log "Generating self-signed SSL certificate..."
    sudo mkdir -p /etc/ssl/isd
    sudo openssl req -x509 -nodes -days 3650 -newkey rsa:4096 \
        -keyout /etc/ssl/isd/server.key \
        -out /etc/ssl/isd/server.crt \
        -subj "/C=IN/ST=Karnataka/O=KSP/CN=${SERVER_IP}" 2>/dev/null

    log "SSL certificate generated (valid 10 years)"

    # --- nginx Configuration ---
    log "Configuring nginx..."
    cat <<EOF | sudo tee /etc/nginx/sites-available/isd-v5
server {
    listen 80;
    server_name ${SERVER_IP};
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    server_name ${SERVER_IP};

    ssl_certificate     /etc/ssl/isd/server.crt;
    ssl_certificate_key /etc/ssl/isd/server.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    client_max_body_size 200M;

    root /opt/isd/frontend/dist;
    index index.html;
    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location /api/ {
        rewrite ^/api/(.*) /\$1 break;
        proxy_pass         http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
EOF

    # Enable site
    sudo rm -f /etc/nginx/sites-enabled/default
    sudo ln -sf /etc/nginx/sites-available/isd-v5 /etc/nginx/sites-enabled/
    sudo nginx -t
    sudo systemctl reload nginx

    log "nginx configured and running"

    # --- systemd Service ---
    log "Creating systemd service..."
    cat <<EOF | sudo tee /etc/systemd/system/isd-backend.service
[Unit]
Description=ISD Document Intelligence V5 Backend
After=network.target mysql.service ollama.service

[Service]
Type=exec
User=$USER
Group=$USER
WorkingDirectory=/opt/isd/backend
Environment="PATH=/opt/miniconda3/envs/isd/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
EnvironmentFile=/opt/isd/backend/.env
ExecStart=/opt/miniconda3/envs/isd/bin/uvicorn app:app \
    --host 127.0.0.1 \
    --port 8001 \
    --workers 4 \
    --timeout-keep-alive 600
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable isd-backend
    sudo systemctl start isd-backend

    # Wait for startup
    sleep 5

    # Check status
    if sudo systemctl is-active --quiet isd-backend; then
        log "Backend service is running!"
    else
        err "Backend service failed to start. Check logs:"
        err "  sudo journalctl -u isd-backend -n 50"
    fi

    log "=== PHASE 4 COMPLETE ==="
    log "Next run:  ./setup_production.sh phase5"
}

# ============================================================================
# PHASE 5: Admin User, Firewall, Verification
# ============================================================================
phase5() {
    log "=== PHASE 5: Final Setup & Verification ==="

    read -p "Enter server IP or domain: " SERVER_IP

    # --- Firewall ---
    log "Configuring firewall..."
    sudo ufw allow ssh
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
    sudo ufw deny 8001/tcp
    sudo ufw deny 11434/tcp
    sudo ufw deny 3306/tcp
    echo "y" | sudo ufw enable
    sudo ufw status

    # --- Create Admin User ---
    log "Creating admin user..."
    read -p "Admin username: " ADMIN_USER
    read -sp "Admin password: " ADMIN_PASS
    echo

    # Register via API
    REGISTER_RESPONSE=$(curl -sk -X POST "https://${SERVER_IP}/api/auth/register" \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"${ADMIN_USER}\",\"password\":\"${ADMIN_PASS}\",\"full_name\":\"Administrator\"}" 2>/dev/null)

    echo "Register response: $REGISTER_RESPONSE"

    # Promote to admin
    read -sp "Enter MySQL password: " MYSQL_PASS
    echo
    mysql -u root -p"$MYSQL_PASS" ISDIntelligence -e \
        "UPDATE users SET role='admin' WHERE username='${ADMIN_USER}';"
    log "User '${ADMIN_USER}' promoted to admin."

    # --- Verification ---
    log "=== VERIFICATION ==="

    # 1. GPU
    log "1. GPU Status:"
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

    # 2. MySQL
    log "2. MySQL:"
    mysql -u root -p"$MYSQL_PASS" ISDIntelligence -e "SHOW TABLES;" 2>/dev/null && log "   MySQL OK" || err "   MySQL FAILED"

    # 3. Ollama
    log "3. Ollama models:"
    ollama list

    # 4. Backend
    log "4. Backend health:"
    curl -sk "https://${SERVER_IP}/api/health" 2>/dev/null | python3 -m json.tool || err "   Backend FAILED"

    # 5. nginx
    log "5. nginx:"
    sudo systemctl is-active nginx && log "   nginx OK" || err "   nginx FAILED"

    # 6. Frontend
    log "6. Frontend:"
    if [ -f "/opt/isd/frontend/dist/index.html" ]; then
        log "   Frontend dist exists — OK"
    else
        err "   Frontend dist not found!"
    fi

    log ""
    log "=== SETUP COMPLETE ==="
    log "Access the application at: https://${SERVER_IP}"
    log "Login with: ${ADMIN_USER}"
    log ""
    log "Useful commands:"
    log "  sudo journalctl -u isd-backend -f     # View backend logs"
    log "  sudo systemctl restart isd-backend     # Restart backend"
    log "  ollama ps                              # Check GPU usage"
    log "  nvidia-smi                             # GPU status"
}

# ============================================================================
# MAIN
# ============================================================================
case "${1}" in
    phase1) phase1 ;;
    phase2) phase2 ;;
    phase3) phase3 ;;
    phase4) phase4 ;;
    phase5) phase5 ;;
    *)
        echo "ISD Document Intelligence V5 — Production Setup"
        echo ""
        echo "Usage: $0 <phase>"
        echo ""
        echo "Phases (run in order):"
        echo "  phase1  — Fix NVIDIA drivers, system updates (REBOOT after)"
        echo "  phase2  — Install MySQL, Ollama, Python, Node.js, nginx"
        echo "  phase3  — Deploy app code, configure backend, build frontend"
        echo "  phase4  — Configure nginx SSL, create systemd service"
        echo "  phase5  — Create admin user, firewall, verify everything"
        echo ""
        echo "Example:"
        echo "  ./setup_production.sh phase1"
        echo "  sudo reboot"
        echo "  ./setup_production.sh phase2"
        ;;
esac
