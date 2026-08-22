#!/usr/bin/env bash
# ============================================================================
# CyberFraud Data Entry — GREEN-FIELD BOOTSTRAP
#
# One execution on a bare Ubuntu box -> a running application.
#
# This is the sibling of update.sh, and the division is deliberate:
#
#   bootstrap.sh   bare machine -> running app. Installs system packages,
#                  MySQL, Node, the venv, the schema and the data. Run once
#                  per machine (but safe to re-run).
#   update.sh      running app -> newer running app. Assumes every one of
#                  the above already exists. Run on every deploy.
#
# Two jobs it has to do well:
#   1. Stand up a dev / build box (a laptop, the DGX Spark)
#   2. DISASTER RECOVERY. A dead server, a fresh VM, and one command
#      between them and being back online. That is why every step is
#      idempotent and why the script verifies its own work at the end:
#      during a real recovery nobody is in a state to spot a silent
#      half-failure.
#
# USAGE
#   # environment only -- you load the data yourself afterwards
#   sudo bash deploy/bootstrap.sh --mode prod --skip-data
#
#   sudo bash deploy/bootstrap.sh --mode dev
#   sudo bash deploy/bootstrap.sh --mode prod \
#        --restore-dump    /path/to/cyber_fraud_dsr-2026-08-22.sql.gz \
#        --restore-uploads /path/to/uploads-backups/
#
# FLAGS
#   --mode dev|prod       dev: localhost, you start the servers yourself.
#                         prod: gunicorn + nginx + systemd, brought up now.
#                         Default: dev
#   --db-password PASS    MySQL root password. Generated if omitted.
#   --restore-dump FILE   .sql or .sql.gz to load INSTEAD of seeding.
#   --restore-uploads DIR Directory holding uploads_full_<ts>.tar and any
#                         uploads_inc_<ts>.tar. The newest full is chosen,
#                         then every increment newer than it, in order.
#   --skip-apt            Don't touch apt. For re-runs and air-gapped boxes.
#   --skip-frontend       Don't build the frontend.
#   --skip-data           Build the environment and stop at the data: no
#                         seed, no restore, and no migrations against an
#                         empty schema. For when you load the dump and the
#                         uploads yourself. Re-run afterwards with
#                         --skip-apt to apply migrations and verify.
#   --yes                 No prompts. Implied when stdin is not a terminal.
#   --help
#
# WHAT IT WILL NOT DO
#   - Overwrite an existing backend/.env. Your secrets survive a re-run.
#   - Re-seed a database that already has tables, unless you pass
#     --restore-dump (an explicit instruction to replace the contents).
#   - Commit, push, or phone home.
# ============================================================================

set -uo pipefail

# ── Where things are ────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$(cd "$SCRIPT_DIR/.." && pwd)"          # .../CyberFraudDataEntry
BACKEND="$SOURCE/backend"
FRONTEND="$SOURCE/frontend"
RUNTIME=/opt/cyberfraud                          # prod mode only
NODE_MAJOR=22

MODE=dev
DB_PASSWORD=""
RESTORE_DUMP=""
RESTORE_UPLOADS=""
SKIP_APT=0
SKIP_FRONTEND=0
SKIP_DATA=0
ASSUME_YES=0
[ -t 0 ] || ASSUME_YES=1

# ── Output helpers ──────────────────────────────────────────────────────
step()  { printf "\n\033[1;36m=== %s ===\033[0m\n" "$1"; }
ok()    { printf "  \033[32mok\033[0m    %s\n" "$1"; }
warn()  { printf "  \033[33mwarn\033[0m  %s\n" "$1"; }
note()  { printf "        %s\n" "$1"; }
die()   { printf "\n  \033[31mFATAL\033[0m %s\n\n" "$1" >&2; exit 1; }

FAILED=0
pass_() { printf "  \033[32mPASS\033[0m  %s\n" "$1"; }
fail_() { printf "  \033[31mFAIL\033[0m  %s\n" "$1"; FAILED=1; }
verify() {  # verify "<label>" <command...>
    local label="$1"; shift
    if "$@" >/dev/null 2>&1; then pass_ "$label"; else fail_ "$label"; fi
}

# ── Arguments ───────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        --mode)             MODE="${2:-}"; shift 2 ;;
        --db-password)      DB_PASSWORD="${2:-}"; shift 2 ;;
        --restore-dump)     RESTORE_DUMP="${2:-}"; shift 2 ;;
        --restore-uploads)  RESTORE_UPLOADS="${2:-}"; shift 2 ;;
        --skip-apt)         SKIP_APT=1; shift ;;
        --skip-frontend)    SKIP_FRONTEND=1; shift ;;
        --skip-data)        SKIP_DATA=1; shift ;;
        --yes|-y)           ASSUME_YES=1; shift ;;
        --help|-h)          sed -n '2,53p' "$0"; exit 0 ;;
        *)                  die "unknown argument: $1  (try --help)" ;;
    esac
done
[ "$MODE" = dev ] || [ "$MODE" = prod ] || die "--mode must be dev or prod"

# ============================================================================
step "0. Preflight"
# ============================================================================
[ "$(id -u)" -eq 0 ] || die "run with sudo: sudo bash deploy/bootstrap.sh ..."

# The user who invoked sudo owns the dev-mode files. Root owning a dev
# checkout makes every later git pull and npm install need sudo too.
REAL_USER="${SUDO_USER:-root}"
REAL_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"
[ -n "$REAL_HOME" ] || REAL_HOME=/root

# shellcheck disable=SC1091
. /etc/os-release 2>/dev/null || die "cannot read /etc/os-release — is this Ubuntu?"
case "${ID:-}" in
    ubuntu) ok "Ubuntu ${VERSION_ID:-?} ($(uname -m))" ;;
    debian) warn "Debian, not Ubuntu — package names match, proceeding" ;;
    *)      die "unsupported OS: ${ID:-unknown}. This script targets Ubuntu." ;;
esac

if [ "$(uname -m)" = aarch64 ]; then
    note "aarch64 — every dependency has arm64 wheels, but asyncmy may"
    note "compile from source. That is what build-essential is here for."
fi

RAM_GB=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo) / 1024 / 1024 ))
DISK_GB=$(df -BG --output=avail "$SOURCE" | tail -1 | tr -dc '0-9')
ok "RAM ${RAM_GB} GB, free disk ${DISK_GB} GB"
[ "$RAM_GB" -lt 4 ] && warn "under 4 GB RAM — MySQL and the parser will contend"
[ "$DISK_GB" -lt 40 ] && warn "under 40 GB free — the uploads tree alone is ~20 GB"

[ -f "$BACKEND/requirements.txt" ] || die "not a CyberFraudDataEntry checkout: $SOURCE"
ok "source tree $SOURCE"

# Buffer pool: a quarter of RAM, floor 1G, ceiling 16G. MySQL has to leave
# room for gunicorn and, on an analysis box, the parser workers.
POOL_GB=$(( RAM_GB / 4 ))
[ "$POOL_GB" -lt 1 ]  && POOL_GB=1
[ "$POOL_GB" -gt 16 ] && POOL_GB=16

if [ "$ASSUME_YES" -eq 0 ]; then
    echo
    echo "  mode          $MODE"
    echo "  source        $SOURCE"
    echo "  buffer pool   ${POOL_GB}G"
    if [ "$SKIP_DATA" -eq 1 ]; then
        echo "  data          --skip-data: none loaded, you restore it yourself"
    else
        echo "  restore dump  ${RESTORE_DUMP:-<none — will seed a fresh roster>}"
    fi
    echo
    read -r -p "  Proceed? [y/N] " reply
    case "$reply" in y|Y) ;; *) die "aborted" ;; esac
fi

# ============================================================================
step "1. System packages"
# ============================================================================
if [ "$SKIP_APT" -eq 1 ]; then
    warn "skipped (--skip-apt)"
else
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq || die "apt-get update failed"
    apt-get install -y -qq \
        build-essential python3-dev python3-venv python3-pip pkg-config \
        mysql-server libmysqlclient-dev \
        git curl ca-certificates openssl rsync tar gzip \
        || die "apt-get install failed"
    ok "build tools, python3, mysql-server"

    if [ "$MODE" = prod ]; then
        apt-get install -y -qq nginx || die "nginx install failed"
        ok "nginx"
    fi

    if [ "$SKIP_FRONTEND" -eq 0 ]; then
        NEED_NODE=1
        if command -v node >/dev/null 2>&1; then
            CUR=$(node -v | tr -dc '0-9.' | cut -d. -f1)
            [ -n "$CUR" ] && [ "$CUR" -ge "$NODE_MAJOR" ] && NEED_NODE=0
        fi
        if [ "$NEED_NODE" -eq 1 ]; then
            curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - >/dev/null 2>&1 \
                || die "NodeSource setup failed"
            apt-get install -y -qq nodejs || die "nodejs install failed"
        fi
        ok "node $(node -v), npm $(npm -v)"
    fi
fi

# ============================================================================
step "2. MySQL"
# ============================================================================
systemctl enable --now mysql >/dev/null 2>&1 || die "mysql failed to start"

# Ubuntu's fresh root uses auth_socket, so `mysql` as root works with no
# password until we set one. Detect which state we are in rather than
# assuming — this script has to be re-runnable.
if mysql --protocol=socket -uroot -e "SELECT 1" >/dev/null 2>&1; then
    ok "root reachable over the unix socket (fresh install)"
    if [ -z "$DB_PASSWORD" ]; then
        DB_PASSWORD="$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 24)"
        note "generated a MySQL root password; it goes into backend/.env"
    fi
    # mysql_native_password first: widest compatibility for asyncmy over
    # TCP. Ubuntu 24.04 ships MySQL 8.0 where it still exists; if a newer
    # server has dropped the plugin, fall back to the default.
    mysql --protocol=socket -uroot -e \
        "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '${DB_PASSWORD}';" 2>/dev/null \
    || mysql --protocol=socket -uroot -e \
        "ALTER USER 'root'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';" \
    || die "could not set the MySQL root password"
    mysql --protocol=socket -uroot -e "FLUSH PRIVILEGES;" >/dev/null 2>&1
    ok "root password set"
elif [ -n "$DB_PASSWORD" ] && mysql -uroot -p"$DB_PASSWORD" -e "SELECT 1" >/dev/null 2>&1; then
    ok "root password already set and matches --db-password"
elif [ -f "$BACKEND/.env" ] && grep -q '^DB_PASSWORD=' "$BACKEND/.env"; then
    DB_PASSWORD="$(grep '^DB_PASSWORD=' "$BACKEND/.env" | head -1 | cut -d= -f2-)"
    mysql -uroot -p"$DB_PASSWORD" -e "SELECT 1" >/dev/null 2>&1 \
        || die "the DB_PASSWORD in backend/.env does not work. Pass --db-password."
    ok "reusing the password already in backend/.env"
else
    die "MySQL root needs a password and none worked. Pass --db-password."
fi
MYSQL_ARGS=(-uroot -p"$DB_PASSWORD")

# utf8mb4_unicode_ci is NOT optional. Ubuntu's MySQL 8 defaults new
# databases to utf8mb4_0900_ai_ci, and every FK in the schema then fails
# against a table created the other way with error 3780. This one line is
# the 2026-06-20 production incident, prevented.
mysql "${MYSQL_ARGS[@]}" -e \
    "CREATE DATABASE IF NOT EXISTS cyber_fraud_dsr CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" \
    || die "could not create the database"
COLL=$(mysql "${MYSQL_ARGS[@]}" -N -B -e \
    "SELECT default_collation_name FROM information_schema.schemata WHERE schema_name='cyber_fraud_dsr';")
[ "$COLL" = utf8mb4_unicode_ci ] \
    || die "cyber_fraud_dsr exists with collation '$COLL', not utf8mb4_unicode_ci.
       Every foreign key will fail with error 3780. Drop the database and re-run."
ok "database cyber_fraud_dsr ($COLL)"

cat > /etc/mysql/mysql.conf.d/z-cyberfraud.cnf <<MYCNF
# Written by deploy/bootstrap.sh — sized from this machine's RAM.
[mysqld]
innodb_buffer_pool_size = ${POOL_GB}G
max_allowed_packet      = 1G
MYCNF
systemctl restart mysql || die "mysql failed to restart with the new config"
ok "buffer pool ${POOL_GB}G, max_allowed_packet 1G"

# ============================================================================
step "3. Python environment"
# ============================================================================
cd "$BACKEND" || die "no backend dir"
[ -d venv ] || python3 -m venv venv || die "venv creation failed"
./venv/bin/pip install -q -U pip wheel || die "pip self-upgrade failed"

# requirements-dev.txt composes app + analysis + test deps. Production gets
# requirements.txt alone: it never runs pytest, and requirements-analysis's
# pillow pin only matters where pdfplumber is installed.
REQ=requirements-dev.txt
[ "$MODE" = prod ] && REQ=requirements.txt
[ -f "$REQ" ] || REQ=requirements.txt
./venv/bin/pip install -q -r "$REQ" || die "pip install -r $REQ failed"
ok "venv ready from $REQ"

if [ "$MODE" = dev ] && [ "$REAL_USER" != root ]; then
    chown -R "$REAL_USER":"$REAL_USER" venv
    ok "venv handed to $REAL_USER"
fi

# ============================================================================
step "4. backend/.env"
# ============================================================================
if [ -f .env ]; then
    ok ".env already exists — left untouched"
    grep -q '^JWT_SECRET=' .env || die ".env has no JWT_SECRET; the app refuses to start without one"
else
    JWT_SECRET="$(openssl rand -hex 32)"
    if [ "$MODE" = prod ]; then DOCS=true; else DOCS=false; fi
    # vite.config.ts pins the dev server to 5175, and proxies /api to :8000.
    cat > .env <<ENVEOF
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=${DB_PASSWORD}
DB_NAME=cyber_fraud_dsr
JWT_SECRET=${JWT_SECRET}
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60
CORS_ORIGINS=http://localhost:5175
DISABLE_DOCS=${DOCS}
CHAT_ENABLED=false
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:32b
ENVEOF
    chmod 600 .env
    [ "$REAL_USER" != root ] && chown "$REAL_USER":"$REAL_USER" .env
    ok ".env written (chmod 600), JWT_SECRET is 64 hex chars"
fi

# ============================================================================
step "5. Schema and data"
# ============================================================================
TABLE_COUNT=$(mysql "${MYSQL_ARGS[@]}" -N -B -e \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='cyber_fraud_dsr';" 2>/dev/null || echo 0)

if [ "$SKIP_DATA" -eq 1 ] && [ -z "$RESTORE_DUMP" ]; then
    ok "--skip-data: database left empty for you to restore into"
    note "cyber_fraud_dsr exists with utf8mb4_unicode_ci; nothing else touched"
elif [ -n "$RESTORE_DUMP" ]; then
    [ -f "$RESTORE_DUMP" ] || die "--restore-dump: no such file: $RESTORE_DUMP"
    note "restoring $(basename "$RESTORE_DUMP") — this replaces the current contents"
    if [ "${RESTORE_DUMP##*.}" = gz ]; then
        gunzip -c "$RESTORE_DUMP" | mysql "${MYSQL_ARGS[@]}" cyber_fraud_dsr || die "restore failed"
    else
        mysql "${MYSQL_ARGS[@]}" cyber_fraud_dsr < "$RESTORE_DUMP" || die "restore failed"
    fi
    ok "dump restored"
    note "the dump excludes statement_transactions by design. Rebuild it with:"
    note "  cd $BACKEND && venv/bin/python -m analysis.daily"
elif [ "$TABLE_COUNT" -gt 5 ]; then
    ok "database already has $TABLE_COUNT tables — not re-seeding"
else
    # seed.py builds units + police_stations from the roster spreadsheet and
    # creates two users per PS with unique random passwords.
    # The roster ships with the repo, so this normally just passes. It is
    # still a hard stop rather than a prompt if it is missing, because
    # seed.py's fallback is AllDistrictPS.xlsx — 1,085 stations across 40
    # districts, two users each — which looks exactly like a successful
    # run, and --yes would wave a prompt through unattended.
    ROSTER="$SOURCE/All District CEN_PS.xlsx"
    [ -f "$ROSTER" ] || die "no database to restore and no roster to seed from.

       'All District CEN_PS.xlsx' should have come with the clone but is
       not in $SOURCE — something removed it.

       Without it seed.py silently falls back to AllDistrictPS.xlsx, which
       is every police station in Karnataka (1,085 across 40 districts)
       rather than the 44 Cyber Crime stations, and seeds two users for
       each. That failure looks like success, so this script will not do it.

       Almost always you want --restore-dump instead: units and
       police_stations come back inside the dump."
    ok "roster: All District CEN_PS.xlsx (44 stations / 36 districts)"
    ./venv/bin/python seed.py || die "seed.py failed"
    ok "seeded"
    if [ -f seed_credentials.csv ]; then
        chmod 600 seed_credentials.csv
        [ "$REAL_USER" != root ] && chown "$REAL_USER":"$REAL_USER" seed_credentials.csv
        warn "backend/seed_credentials.csv holds PLAINTEXT passwords for every"
        warn "seeded user. Distribute it, then delete it. It is gitignored."
    fi
fi

# ============================================================================
step "6. Migrations"
# ============================================================================
# Always, in order, whichever path got us here: they are idempotent, so on a
# restored dump they confirm rather than change. 005 (chat_messages) is dev
# only — production does not expose the chat endpoint.
#
# Gated on what is actually IN the database, not on which flags were passed.
# Migrations 001+ ALTER tables that a dump or seed.py creates; against a
# genuinely empty schema the first one fails, which on an unattended run
# reads as the whole bootstrap having failed.
NOW_TABLES=$(mysql "${MYSQL_ARGS[@]}" -N -B -e \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='cyber_fraud_dsr';" 2>/dev/null || echo 0)
if [ "$NOW_TABLES" -lt 5 ]; then
    MIGS=""
    warn "database is empty — skipping migrations"
    note "They alter tables that a restore or a seed creates, so there is"
    note "nothing to alter yet. Load your data, then re-run:"
    note "  sudo bash $0 --mode $MODE --skip-apt --skip-frontend"
else
    MIGS=$(find migrations -maxdepth 1 -name '[0-9][0-9][0-9]_*.py' -printf '%f\n' 2>/dev/null | sort)
    [ -n "$MIGS" ] || die "no migrations found in $BACKEND/migrations/"
fi
APPLIED=0
while IFS= read -r f; do
    [ -n "$f" ] || continue
    m="${f%.py}"
    case "$m" in
        005_*) if [ "$MODE" = prod ]; then note "skip $m (chat: dev only)"; continue; fi ;;
    esac
    ./venv/bin/python -m "migrations.$m" >/dev/null 2>&1 \
        || die "migration $m failed. Re-run it by hand to see the error:
       cd $BACKEND && venv/bin/python -m migrations.$m"
    APPLIED=$((APPLIED + 1))
done <<< "$MIGS"
[ -n "$MIGS" ] && ok "$APPLIED migrations applied (idempotent — no-ops when already present)"

# ============================================================================
step "7. Uploads"
# ============================================================================
mkdir -p "$BACKEND/uploads"
if [ "$SKIP_DATA" -eq 1 ] && [ -z "$RESTORE_UPLOADS" ]; then
    ok "--skip-data: uploads/ created and left empty for you to fill"
elif [ -n "$RESTORE_UPLOADS" ] && [ -f "$RESTORE_UPLOADS" ]; then
    # A SINGLE archive — a hand-made tarball rather than the server's
    # full+increment chain. tar -xf auto-detects gzip, so .tar and .tar.gz
    # are both fine.
    #
    # Where it extracts to depends on how it was rolled up, and getting
    # this wrong silently produces uploads/uploads/... which every path in
    # the database then misses. Peek at the first member instead of
    # guessing: an archive of "uploads/" unpacks into backend/, an archive
    # of the directory's CONTENTS unpacks into backend/uploads/.
    FIRST=$(tar -tf "$RESTORE_UPLOADS" 2>/dev/null | head -1)
    [ -n "$FIRST" ] || die "cannot read $RESTORE_UPLOADS — truncated download?
       Check it with: tar -tzf '$RESTORE_UPLOADS' | head"
    case "$FIRST" in
        backend/*|./backend/*) DEST="$SOURCE"         ; note "archive contains backend/ — unpacking into the source root" ;;
        uploads/*|./uploads/*) DEST="$BACKEND"        ; note "archive contains uploads/ — unpacking into backend/" ;;
        *)                     DEST="$BACKEND/uploads"; note "archive contains bare files — unpacking into backend/uploads/" ;;
    esac
    note "archive: $(basename "$RESTORE_UPLOADS") ($(du -h "$RESTORE_UPLOADS" | cut -f1))"
    tar -xf "$RESTORE_UPLOADS" -C "$DEST" || die "extracting $RESTORE_UPLOADS failed"

    # A misplaced extraction is silent: the files exist, but every path
    # stored in the database points somewhere else, so the app shows
    # "no statement" for everything. Check the shape before moving on.
    for BAD in "$BACKEND/uploads/uploads" "$BACKEND/uploads/backend"; do
        [ -d "$BAD" ] && warn "unexpected nesting at $BAD — the archive layout was
        not what the peek suggested. Move its contents up one level, or the
        app will find none of these files."
    done
    UP_FILES=$(find "$BACKEND/uploads" -type f | wc -l)
    [ "$UP_FILES" -eq 0 ] && warn "0 files under backend/uploads/ after extracting — check the layout"
    ok "uploads restored: $UP_FILES files"

elif [ -n "$RESTORE_UPLOADS" ]; then
    [ -d "$RESTORE_UPLOADS" ] || die "--restore-uploads: no such file or directory: $RESTORE_UPLOADS"

    # Names are uploads_full_<ts>.tar / uploads_inc_<ts>.tar, where <ts> is
    # %Y-%m-%d_%H%M%S — see deploy/backup-uploads.sh. Underscores, not
    # hyphens, and the timestamp is what orders the chain.
    stamp_of() {
        local b; b=$(basename "$1" .tar)
        b="${b#uploads_full_}"; b="${b#uploads_inc_}"
        printf '%s' "$b"
    }

    FULL=$(find "$RESTORE_UPLOADS" -maxdepth 1 -name 'uploads_full_*.tar' | sort | tail -1)
    [ -n "$FULL" ] || die "no uploads_full_*.tar in $RESTORE_UPLOADS.
       An increment on its own is not a restore — it holds only what changed
       since the last one. Find the full archive that starts the chain."
    FULL_TS=$(stamp_of "$FULL")
    note "full: $(basename "$FULL")"
    tar -xf "$FULL" -C "$BACKEND/uploads" || die "extracting the full archive failed"

    # Increments MUST be applied in creation order, and only those NEWER
    # than the full. Comparing whole filenames would not do it: "full" sorts
    # before "inc", so every increment would look newer than every full
    # including ones from a previous chain. Compare the timestamps.
    # read -r, not `for INC in $(find ...)`: a backup directory path with a
    # space in it would otherwise be word-split into pieces and every tar
    # would fail on a filename that does not exist.
    APPLIED_INC=0
    while IFS= read -r INC; do
        [ -n "$INC" ] || continue
        INC_TS=$(stamp_of "$INC")
        if [ "$INC_TS" \< "$FULL_TS" ]; then
            note "skip $(basename "$INC") — predates the full, belongs to an older chain"
            continue
        fi
        note "increment: $(basename "$INC")"
        tar -xf "$INC" -C "$BACKEND/uploads" || die "extracting $INC failed"
        APPLIED_INC=$((APPLIED_INC + 1))
    done < <(find "$RESTORE_UPLOADS" -maxdepth 1 -name 'uploads_inc_*.tar' | sort)
    ok "uploads restored: 1 full + $APPLIED_INC increment(s), $(find "$BACKEND/uploads" -type f | wc -l) files"
else
    ok "uploads/ ready (empty — nothing to restore)"
fi
if [ "$REAL_USER" != root ] && [ "$MODE" = dev ]; then
    chown -R "$REAL_USER":"$REAL_USER" "$BACKEND/uploads"
fi

# ============================================================================
step "8. Frontend"
# ============================================================================
if [ "$SKIP_FRONTEND" -eq 1 ]; then
    warn "skipped (--skip-frontend)"
else
    cd "$FRONTEND" || die "no frontend dir"
    if [ -f package-lock.json ]; then
        npm ci --silent || die "npm ci failed"
    else
        npm install --silent || die "npm install failed"
    fi
    # npm run build is "tsc -b && vite build". The vite dev server does not
    # typecheck, so a type error only ever surfaces here.
    npm run build >/dev/null 2>&1 \
        || die "frontend build failed. Run it directly to see the errors:
       cd $FRONTEND && npm run build"
    ok "built: $(du -sh dist 2>/dev/null | cut -f1) in dist/"
    [ "$REAL_USER" != root ] && chown -R "$REAL_USER":"$REAL_USER" node_modules dist 2>/dev/null
fi

# ============================================================================
step "9. Service layer"
# ============================================================================
if [ "$MODE" = dev ]; then
    ok "dev mode — no systemd, no nginx. You start the servers."
else
    id -u cyberfraud >/dev/null 2>&1 \
        || useradd --system --no-create-home --shell /usr/sbin/nologin cyberfraud
    mkdir -p "$RUNTIME/backend" "$RUNTIME/frontend" "$RUNTIME/backups" /var/log/cyberfraud
    rsync -a --delete --exclude venv --exclude __pycache__ --exclude uploads \
        "$BACKEND/" "$RUNTIME/backend/"
    mkdir -p "$RUNTIME/backend/uploads"
    [ -n "$RESTORE_UPLOADS" ] && rsync -a "$BACKEND/uploads/" "$RUNTIME/backend/uploads/"
    rsync -a --delete "$FRONTEND/dist/" "$RUNTIME/frontend/dist/"
    rsync -a "$SOURCE/deploy/" "$RUNTIME/deploy/"

    # The runtime needs its OWN venv: /opt/cyberfraud is what systemd runs,
    # and the source checkout may not even be readable by the service user.
    [ -d "$RUNTIME/backend/venv" ] || python3 -m venv "$RUNTIME/backend/venv"
    "$RUNTIME/backend/venv/bin/pip" install -q -U pip wheel
    "$RUNTIME/backend/venv/bin/pip" install -q -r "$RUNTIME/backend/requirements.txt" \
        || die "runtime pip install failed"
    chown -R cyberfraud:cyberfraud "$RUNTIME" /var/log/cyberfraud
    chmod +x "$RUNTIME"/deploy/*.sh 2>/dev/null
    chmod 600 "$RUNTIME/backend/.env" 2>/dev/null
    ok "runtime staged at $RUNTIME"

    install -m 644 "$SOURCE/deploy/cyberfraud-backend.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable --now cyberfraud-backend || die "backend service failed to start"
    ok "cyberfraud-backend running"

    if [ -f "$SOURCE/deploy/nginx.conf" ]; then
        install -m 644 "$SOURCE/deploy/nginx.conf" /etc/nginx/sites-available/cyberfraud
        ln -sfn /etc/nginx/sites-available/cyberfraud /etc/nginx/sites-enabled/cyberfraud
        rm -f /etc/nginx/sites-enabled/default
        if nginx -t >/dev/null 2>&1; then
            systemctl reload nginx && ok "nginx serving"
        else
            warn "nginx config did not validate (nginx -t). The backend is"
            warn "still up on :8000 — fix nginx separately."
        fi
    fi

    # The nightly chain: analysis then backup. Its own installer, because it
    # also retires the two timers it replaced.
    if [ -f "$SOURCE/deploy/install-nightly.sh" ]; then
        if bash "$SOURCE/deploy/install-nightly.sh" >/dev/null 2>&1; then
            ok "nightly analysis + backup timer installed"
        else
            warn "install-nightly.sh did not complete — run it by hand"
        fi
    fi
fi

# ============================================================================
step "10. Self-verify"
# ============================================================================
# During a real recovery nobody is in a state to notice a step that
# half-worked. Everything below is checked, not assumed.

verify "database reachable" mysql "${MYSQL_ARGS[@]}" -e "USE cyber_fraud_dsr"

# With --skip-data the schema checks below are meaningless: the database is
# empty ON PURPOSE. Printing eight FAILs for that trains you to ignore FAIL
# lines, which is the opposite of what a DR self-check is for.
EMPTY_BY_DESIGN=0
[ "$SKIP_DATA" -eq 1 ] && [ "${NOW_TABLES:-0}" -lt 5 ] && EMPTY_BY_DESIGN=1

TABLES=$(mysql "${MYSQL_ARGS[@]}" -N -B -e \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='cyber_fraud_dsr';")
if [ "$EMPTY_BY_DESIGN" -eq 1 ]; then
    warn "schema checks skipped — database empty by request (--skip-data)"
elif [ "$TABLES" -ge 36 ]; then
    pass_ "$TABLES tables present"
else
    fail_ "only $TABLES tables — expected 36 or more"
fi

if [ "$EMPTY_BY_DESIGN" -eq 0 ]; then
for T in units police_stations users cases all_accounts upload_ledger crypto_txn ifsc_branch; do
    verify "table $T" mysql "${MYSQL_ARGS[@]}" cyber_fraud_dsr -e "SELECT 1 FROM $T LIMIT 1"
done
fi

# The check that catches the silent wrong-roster failure.
if [ "$EMPTY_BY_DESIGN" -eq 0 ]; then
PS_COUNT=$(mysql "${MYSQL_ARGS[@]}" -N -B cyber_fraud_dsr \
    -e "SELECT COUNT(*) FROM police_stations;" 2>/dev/null || echo 0)
if [ "$PS_COUNT" -ge 40 ] && [ "$PS_COUNT" -le 60 ]; then
    pass_ "police_stations = $PS_COUNT (expected ~44)"
elif [ "$PS_COUNT" -gt 60 ]; then
    fail_ "police_stations = $PS_COUNT — seeded from the WRONG roster (AllDistrictPS.xlsx, 1,085 rows). Expected ~44."
else
    printf "  \033[33mWARN\033[0m  %s\n" "police_stations = $PS_COUNT — empty or partial"
fi

fi

if [ "$EMPTY_BY_DESIGN" -eq 0 ]; then
verify "migration 023 landed (summary untested columns)" \
    mysql "${MYSQL_ARGS[@]}" -N -B -e \
    "SELECT 1 FROM information_schema.columns
     WHERE table_schema='cyber_fraud_dsr' AND table_name='account_statement_summary'
       AND column_name='untested_debit';"
verify "migration 026 landed (summary money widened)" \
    mysql "${MYSQL_ARGS[@]}" -N -B -e \
    "SELECT 1 FROM information_schema.columns
     WHERE table_schema='cyber_fraud_dsr' AND table_name='account_statement_summary'
       AND column_name='total_debit' AND numeric_precision >= 24;"

fi

verify "backend imports" env -C "$BACKEND" "$BACKEND/venv/bin/python" -c "import cyber_fraud"
verify ".env is chmod 600" bash -c "[ \"\$(stat -c %a '$BACKEND/.env')\" = 600 ]"
[ "$SKIP_FRONTEND" -eq 1 ] || verify "frontend dist built" test -f "$FRONTEND/dist/index.html"

if [ "$MODE" = prod ]; then
    verify "cyberfraud-backend active" systemctl is-active --quiet cyberfraud-backend
    sleep 3
    verify "health endpoint responds" curl -fsS --max-time 5 http://localhost:8000/health
fi

# ============================================================================
echo
if [ "$FAILED" -eq 0 ]; then
    printf "\033[1;32m  BOOTSTRAP COMPLETE\033[0m\n\n"
else
    printf "\033[1;31m  BOOTSTRAP FINISHED WITH FAILURES — read the FAIL lines above\033[0m\n\n"
fi

if [ "$MODE" = dev ]; then
    cat <<DEVEOF
  Start the app (two terminals, as $REAL_USER — not root):

    cd $BACKEND && source venv/bin/activate
    uvicorn cyber_fraud:app --reload --port 8000

    cd $FRONTEND && npm run dev          # http://localhost:5175

  Local AI — the chat feature is already Ollama-native:

    curl -fsSL https://ollama.com/install.sh | sh
    ollama pull qwen2.5-coder:32b
    sed -i 's/^CHAT_ENABLED=false/CHAT_ENABLED=true/' $BACKEND/.env

DEVEOF
else
    IP=$(hostname -I | awk '{print $1}')
    cat <<PRODEOF
  Live on   http://${IP}/
  Logs      journalctl -u cyberfraud-backend -f
  Deploys   cd $(dirname "$SOURCE") && sudo bash CyberFraudDataEntry/deploy/update.sh

PRODEOF
fi

if [ -z "$RESTORE_DUMP" ] && [ -z "$RESTORE_UPLOADS" ]; then
    cat <<FRESHEOF
  This is an EMPTY instance. To make it a copy of production:

    sudo bash $0 --mode $MODE \\
         --restore-dump    /path/to/cyber_fraud_dsr-*.sql.gz \\
         --restore-uploads /path/to/backups/

  Then rebuild the fact table the dump deliberately omits:

    cd $BACKEND && venv/bin/python -m analysis.daily

FRESHEOF
fi

exit "$FAILED"
