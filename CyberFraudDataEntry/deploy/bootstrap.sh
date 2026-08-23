#!/usr/bin/env bash
# ============================================================================
# CyberFraud Data Entry — STAND UP A NEW ENVIRONMENT
#
# Takes a bare Ubuntu machine to a running application: system packages,
# MySQL, Node, the venvs, the schema, the data, systemd and nginx.
#
# THIS IS NOT THE PRODUCTION DEPLOY SCRIPT.
#
#   deploy/update.sh      PRODUCTION. An existing, running installation ->
#                         a newer one. Battle-tested, with a per-migration
#                         self-verify. Use this for every prod deploy.
#   deploy/bootstrap.sh   A NEW ENVIRONMENT, or disaster recovery. A
#                         machine that has nothing -> a machine that runs
#                         the app. Also the right tool when an environment
#                         is in an unknown state and you want a clean base.
#
# The division is deliberate. update.sh assumes MySQL, the venv, the
# schema and the service user all exist and only moves code forward; it
# would fail on a bare machine at the first step. bootstrap.sh builds all
# of that, which necessarily makes it more invasive -- it can purge MySQL
# -- and that is not what you want pointed at production every week.
#
# The only thing that differs between environments is the MySQL password,
# which you pass in.
#
#   sudo bash deploy/bootstrap.sh --db-password 'CyberFraud@2026'
#
# FIRST RUN ON A MACHINE (or any time you want a guaranteed-clean base):
#
#   sudo bash deploy/bootstrap.sh --reset --db-password 'CyberFraud@2026'
#
# FULL DR IN ONE COMMAND:
#
#   sudo bash deploy/bootstrap.sh --reset --db-password 'CyberFraud@2026' \
#        --restore-dump    /backups/dbdump_20AUG2026.sql.gz \
#        --restore-uploads /backups/filedump_21AUG2026.tar.gz
#
# ── FLAGS ───────────────────────────────────────────────────────────────
#   --db-password PASS    REQUIRED when MySQL is new or --reset is used.
#                         Afterwards it is read from backend/.env, so
#                         routine re-runs need no arguments. Never
#                         generated, never defaulted, never in the repo.
#   --reset               Purge and reinstall MySQL from scratch: stops it,
#                         removes the packages AND /var/lib/mysql, drops
#                         every database, reinstalls. DESTRUCTIVE — it
#                         confirms first unless --yes.
#   --mode prod|dev       prod (default): gunicorn + nginx + systemd, all
#                         started. dev: no systemd, you run the servers.
#   --restore-dump FILE   .sql or .sql.gz to load. Omit to leave the
#                         database alone.
#   --restore-uploads X   A single .tar/.tar.gz, or a directory holding the
#                         server's uploads_full_/uploads_inc_ chain.
#   --restore-latest      Find the newest dump and the newest uploads
#                         archive in the backup directory and restore both.
#                         Saves naming files by hand on a recovery.
#   --backup-dir PATH     Where to look. Default /opt/cyberfraud/backups —
#                         the same path backup-db.sh writes to. If that is
#                         empty, a few obvious places are searched too.
#   --no-pull             Skip the git pull. Default is to pull first.
#   --no-nightly          Do not install the 23:00 analysis+backup timer.
#                         For any machine that is a RESTORED COPY rather
#                         than the system of record: the analysis half of
#                         that chain is destructive against a restored
#                         database.
#   --skip-apt            Don't touch apt (faster re-runs).
#   --skip-frontend       Don't rebuild the frontend.
#   --yes                 No prompts. Required for unattended runs.
#   --help
#
# ── WHAT IT GUARANTEES ──────────────────────────────────────────────────
#   * Idempotent. Running it twice does not do damage.
#   * MySQL and every backend/.env always agree on the password — it
#     reconciles them on every run rather than assuming.
#   * It verifies its own work and exits non-zero if any check fails,
#     including "can the app authenticate with the password in its .env".
#     A recovery is the worst moment to discover a silent half-failure.
# ============================================================================

set -uo pipefail

# ── Paths ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$(cd "$SCRIPT_DIR/.." && pwd)"           # .../CyberFraudDataEntry
REPO_ROOT="$(cd "$SOURCE/.." && pwd)"            # the git clone root
BACKEND="$SOURCE/backend"
FRONTEND="$SOURCE/frontend"
RUNTIME=/opt/cyberfraud
DB_NAME=cyber_fraud_dsr
# Where backups live. The same path backup-db.sh and backup-uploads.sh
# write to, so --restore-latest finds what the nightly chain produced
# without being told. Override with --backup-dir.
BACKUP_DIR=/opt/cyberfraud/backups
NODE_MAJOR=22

MODE=prod
DB_PASSWORD=""
RESTORE_DUMP=""
RESTORE_UPLOADS=""
DO_RESET=0
DO_PULL=1
RESTORE_LATEST=0
NO_NIGHTLY=0
SKIP_APT=0
SKIP_FRONTEND=0
ASSUME_YES=0
[ -t 0 ] || ASSUME_YES=1

# ── Output ──────────────────────────────────────────────────────────────
step()  { printf "\n\033[1;36m=== %s ===\033[0m\n" "$1"; }
ok()    { printf "  \033[32mok\033[0m    %s\n" "$1"; }
warn()  { printf "  \033[33mwarn\033[0m  %s\n" "$1"; }
note()  { printf "        %s\n" "$1"; }
die()   { printf "\n  \033[31mFATAL\033[0m %s\n\n" "$1" >&2; exit 1; }

FAILED=0
pass_() { printf "  \033[32mPASS\033[0m  %s\n" "$1"; }
fail_() { printf "  \033[31mFAIL\033[0m  %s\n" "$1"; FAILED=1; }
verify() { local l="$1"; shift; if "$@" >/dev/null 2>&1; then pass_ "$l"; else fail_ "$l"; fi; }

# ── Arguments ───────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        --db-password)     DB_PASSWORD="${2:-}"; shift 2 ;;
        --reset)           DO_RESET=1; shift ;;
        --mode)            MODE="${2:-}"; shift 2 ;;
        --restore-dump)    RESTORE_DUMP="${2:-}"; shift 2 ;;
        --restore-uploads) RESTORE_UPLOADS="${2:-}"; shift 2 ;;
        --backup-dir)      BACKUP_DIR="${2:-}"; shift 2 ;;
        --restore-latest)  RESTORE_LATEST=1; shift ;;
        --no-pull)         DO_PULL=0; shift ;;
        --no-nightly)      NO_NIGHTLY=1; shift ;;
        --skip-apt)        SKIP_APT=1; shift ;;
        --skip-frontend)   SKIP_FRONTEND=1; shift ;;
        --yes|-y)          ASSUME_YES=1; shift ;;
        --help|-h)         sed -n '2,78p' "$0"; exit 0 ;;
        *)                 die "unknown argument: $1  (try --help)" ;;
    esac
done
[ "$MODE" = dev ] || [ "$MODE" = prod ] || die "--mode must be prod or dev"

# ── .env writer ─────────────────────────────────────────────────────────
# Sets one KEY=VALUE, creating the file if needed, preserving every other
# line and the file's owner and mode.
#
# No sed: a value containing & | / or # breaks a sed replacement, and those
# are ordinary password characters. No sourcing either — `set -a; . .env`
# runs the file through the shell, which truncates a value at a # and
# forks on an &. The app never sources it: pydantic-settings and systemd's
# EnvironmentFile both parse it literally, and so does this.
set_env_var() {
    local file="$1" key="$2" val="$3" tmp owner mode
    [ -f "$file" ] || { install -m 600 /dev/null "$file"; }
    owner=$(stat -c '%U:%G' "$file"); mode=$(stat -c '%a' "$file")
    tmp="$file.tmp$$"; : > "$tmp"
    local found=0
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            "$key"=*) printf '%s\n' "$key=$val" >> "$tmp"; found=1 ;;
            *)        printf '%s\n' "$line"     >> "$tmp" ;;
        esac
    done < "$file"
    [ "$found" -eq 1 ] || printf '%s\n' "$key=$val" >> "$tmp"
    chown "$owner" "$tmp" 2>/dev/null; chmod "$mode" "$tmp"
    mv -f "$tmp" "$file"
}
get_env_var() {  # get_env_var FILE KEY
    [ -f "$1" ] || return 1
    grep -m1 "^$2=" "$1" | cut -d= -f2-
}

# ============================================================================
step "0. Preflight"
# ============================================================================
[ "$(id -u)" -eq 0 ] || die "run with sudo:  sudo bash deploy/bootstrap.sh --db-password '...'"

REAL_USER="${SUDO_USER:-root}"

# shellcheck disable=SC1091
. /etc/os-release 2>/dev/null || die "cannot read /etc/os-release — is this Ubuntu?"
case "${ID:-}" in
    ubuntu) ok "Ubuntu ${VERSION_ID:-?} ($(uname -m))" ;;
    debian) warn "Debian, not Ubuntu — package names match, proceeding" ;;
    *)      die "unsupported OS: ${ID:-unknown}. This script targets Ubuntu." ;;
esac

[ -f "$BACKEND/requirements.txt" ] || die "not a CyberFraudDataEntry checkout: $SOURCE"

RAM_GB=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo) / 1024 / 1024 ))
DISK_GB=$(df -BG --output=avail "$SOURCE" | tail -1 | tr -dc '0-9')
ok "RAM ${RAM_GB} GB, free disk ${DISK_GB} GB"
ok "source $SOURCE"
[ "$DISK_GB" -lt 40 ] && warn "under 40 GB free — the uploads tree alone is ~22 GB"

POOL_GB=$(( RAM_GB / 4 )); [ "$POOL_GB" -lt 1 ] && POOL_GB=1; [ "$POOL_GB" -gt 16 ] && POOL_GB=16

# A password with a single quote or backslash would have to be escaped in
# the SQL literal below. Not worth the risk; everything else is fine.
case "$DB_PASSWORD" in
    *\'*|*\\*) die "avoid single quotes and backslashes in --db-password" ;;
esac

if [ "$DO_RESET" -eq 1 ] && [ "$ASSUME_YES" -eq 0 ]; then
    echo
    warn "--reset will PURGE MySQL and DELETE /var/lib/mysql."
    warn "Every database on this machine goes, not just $DB_NAME."
    echo
    read -r -p "  Type RESET to continue: " reply
    [ "$reply" = RESET ] || die "aborted — nothing changed"
fi

# ============================================================================
step "1. Pull latest from GitHub"
# ============================================================================
# Pull first, then re-exec if this script itself changed — otherwise the
# rest of the run is the OLD script operating on NEW code.
if [ "$DO_PULL" -eq 0 ]; then
    warn "skipped (--no-pull)"
elif [ ! -d "$REPO_ROOT/.git" ]; then
    warn "$REPO_ROOT is not a git clone — nothing to pull"
elif [ -n "${CFDSR_BOOTSTRAP_REEXEC:-}" ]; then
    ok "already pulled (re-executed with the updated script)"
else
    BEFORE=$(sha256sum "$0" | cut -d' ' -f1)
    git -C "$REPO_ROOT" pull --ff-only 2>&1 | sed 's/^/        /' \
        || die "git pull failed. Resolve it in $REPO_ROOT and re-run."
    ok "pulled $(git -C "$REPO_ROOT" rev-parse --short HEAD)"
    if [ "$(sha256sum "$0" | cut -d' ' -f1)" != "$BEFORE" ]; then
        note "bootstrap.sh itself changed — restarting with the new version"
        export CFDSR_BOOTSTRAP_REEXEC=1
        exec bash "$0" "$@"
    fi
fi

# ============================================================================
step "2. Reset MySQL"
# ============================================================================
if [ "$DO_RESET" -eq 0 ]; then
    ok "skipped (no --reset)"
else
    [ -n "$DB_PASSWORD" ] || die "--reset needs --db-password: MySQL comes back
       with no credentials and one has to be set."
    export DEBIAN_FRONTEND=noninteractive
    systemctl stop mysql 2>/dev/null
    apt-get purge -y -qq 'mysql-server*' 'mysql-client*' 'mysql-common' 2>/dev/null | tail -2
    apt-get autoremove -y -qq 2>/dev/null | tail -1
    # Purging leaves the data directory behind on purpose; for a clean base
    # it has to go, or the reinstall adopts the old root account.
    rm -rf /var/lib/mysql /var/log/mysql /etc/mysql
    ok "MySQL purged, /var/lib/mysql removed"
    SKIP_APT=0   # it must be reinstalled below
fi

# ============================================================================
step "3. System packages"
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
step "4. MySQL credentials"
# ============================================================================
systemctl enable --now mysql >/dev/null 2>&1 || die "mysql failed to start"

# Establish ONE working root password, from whichever source has it, and
# make MySQL and .env agree. This is the step whose absence turned a
# one-command deploy into a debugging session: the password lived in three
# places and nothing reconciled them.
ENV_PASS=$(get_env_var "$BACKEND/.env" CFDSR_DB_PASSWORD || true)

if [ -z "$DB_PASSWORD" ]; then
    [ -n "$ENV_PASS" ] || die "no --db-password given and no DB_PASSWORD in
       $BACKEND/.env (key CFDSR_DB_PASSWORD — config.py sets
       env_prefix=CFDSR_, so an unprefixed key is ignored). On a new
       machine pass it explicitly:

           sudo bash $0 --db-password 'YourPassword'"
    DB_PASSWORD="$ENV_PASS"
    ok "using the password already in backend/.env"
fi

if MYSQL_PWD="$DB_PASSWORD" mysql -uroot -e "SELECT 1" >/dev/null 2>&1; then
    ok "root already authenticates with this password"
elif mysql --protocol=socket -uroot -e "SELECT 1" >/dev/null 2>&1; then
    # Fresh install: root is auth_socket, no password yet.
    mysql --protocol=socket -uroot -e \
        "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '$DB_PASSWORD';" 2>/dev/null \
    || mysql --protocol=socket -uroot -e \
        "ALTER USER 'root'@'localhost' IDENTIFIED BY '$DB_PASSWORD';" \
    || die "could not set the root password"
    mysql --protocol=socket -uroot -e "FLUSH PRIVILEGES;" >/dev/null 2>&1
    ok "root password set (was a fresh MySQL)"
elif [ -f /etc/mysql/debian.cnf ] && \
     mysql --defaults-file=/etc/mysql/debian.cnf -e "SELECT 1" >/dev/null 2>&1; then
    # Root has SOME other password. Ubuntu's maintenance account has full
    # privileges and needs no restart, so use it rather than making you
    # hunt for whatever root is currently set to.
    mysql --defaults-file=/etc/mysql/debian.cnf -e \
        "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '$DB_PASSWORD'; FLUSH PRIVILEGES;" 2>/dev/null \
    || mysql --defaults-file=/etc/mysql/debian.cnf -e \
        "ALTER USER 'root'@'localhost' IDENTIFIED BY '$DB_PASSWORD'; FLUSH PRIVILEGES;" \
    || die "could not reset the root password via debian.cnf"
    ok "root password reset to the one you passed (via debian-sys-maint)"
else
    die "cannot authenticate to MySQL as root, and /etc/mysql/debian.cnf
       does not work either. Re-run with --reset to reinstall MySQL clean."
fi

MYSQL_PWD="$DB_PASSWORD" mysql -uroot -e "SELECT 1" >/dev/null 2>&1 \
    || die "root still does not authenticate after being set — stopping here"

# utf8mb4_unicode_ci is NOT optional. Ubuntu's MySQL 8 defaults new
# databases to utf8mb4_0900_ai_ci, and every foreign key in the schema then
# fails against it with error 3780. This is the 2026-06-20 incident.
MYSQL_PWD="$DB_PASSWORD" mysql -uroot -e \
    "CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" \
    || die "could not create $DB_NAME"
COLL=$(MYSQL_PWD="$DB_PASSWORD" mysql -uroot -N -B -e \
    "SELECT default_collation_name FROM information_schema.schemata WHERE schema_name='$DB_NAME';")
[ "$COLL" = utf8mb4_unicode_ci ] \
    || die "$DB_NAME has collation '$COLL', not utf8mb4_unicode_ci.
       Every foreign key will fail with error 3780. Re-run with --reset."
ok "database $DB_NAME ($COLL)"

install -d -m 755 /etc/mysql/mysql.conf.d 2>/dev/null
cat > /etc/mysql/mysql.conf.d/z-cyberfraud.cnf <<MYCNF
# Written by deploy/bootstrap.sh — sized from this machine's RAM.
[mysqld]
innodb_buffer_pool_size = ${POOL_GB}G
max_allowed_packet      = 1G
MYCNF
systemctl restart mysql || die "mysql failed to restart with the new config"
ok "buffer pool ${POOL_GB}G, max_allowed_packet 1G"

# ============================================================================
step "5. Python environment"
# ============================================================================
cd "$BACKEND" || die "no backend dir"
[ -d venv ] || python3 -m venv venv || die "venv creation failed"
./venv/bin/pip install -q -U pip wheel || die "pip self-upgrade failed"
REQ=requirements-dev.txt
[ "$MODE" = prod ] && REQ=requirements.txt
[ -f "$REQ" ] || REQ=requirements.txt
./venv/bin/pip install -q -r "$REQ" || die "pip install -r $REQ failed"
ok "venv ready from $REQ"

# ============================================================================
step "6. backend/.env"
# ============================================================================
# JWT_SECRET is generated once and never touched again — regenerating it
# would log out every user. DB_PASSWORD is reconciled on EVERY run, which
# is what keeps MySQL and .env from drifting apart.
# A .env written before 2026-08-23 has UNPREFIXED keys (DB_HOST rather
# than CFDSR_DB_HOST). config.py sets env_prefix=CFDSR_, so pydantic
# matches none of them and refuses to construct Settings at all — the app
# will not start and every migration dies on import. Preserving such a
# file is worse than replacing it, so detect and rewrite, carrying the
# JWT secret across: regenerating that would log out every user.
if [ -f "$BACKEND/.env" ] && ! grep -q '^CFDSR_' "$BACKEND/.env" 2>/dev/null; then
    OLD_JWT=$(get_env_var "$BACKEND/.env" JWT_SECRET || true)
    mv -f "$BACKEND/.env" "$BACKEND/.env.unprefixed.bak"
    warn "backend/.env had no CFDSR_ keys — config.py could never have read it"
    note "moved aside to .env.unprefixed.bak; rebuilding with the right names"
    [ -n "$OLD_JWT" ] && note "carrying the existing JWT_SECRET across"
fi

if [ ! -f "$BACKEND/.env" ]; then
    install -m 600 /dev/null "$BACKEND/.env"
    set_env_var "$BACKEND/.env" CFDSR_DB_HOST localhost
    set_env_var "$BACKEND/.env" CFDSR_DB_PORT 3306
    set_env_var "$BACKEND/.env" CFDSR_DB_USER root
    set_env_var "$BACKEND/.env" CFDSR_DB_NAME "$DB_NAME"
    set_env_var "$BACKEND/.env" CFDSR_JWT_SECRET "${OLD_JWT:-$(openssl rand -hex 32)}"
    set_env_var "$BACKEND/.env" CFDSR_JWT_ALGORITHM HS256
    set_env_var "$BACKEND/.env" CFDSR_JWT_EXPIRE_MINUTES 60
    set_env_var "$BACKEND/.env" CFDSR_CORS_ORIGINS http://localhost:5175
    set_env_var "$BACKEND/.env" CFDSR_DISABLE_DOCS "$([ "$MODE" = prod ] && echo true || echo false)"
    set_env_var "$BACKEND/.env" CFDSR_CHAT_ENABLED false
    set_env_var "$BACKEND/.env" CFDSR_OLLAMA_BASE_URL http://localhost:11434
    set_env_var "$BACKEND/.env" CFDSR_OLLAMA_MODEL qwen2.5-coder:32b
    ok ".env created"
else
    ok ".env exists — only CFDSR_DB_PASSWORD is reconciled"
fi
set_env_var "$BACKEND/.env" CFDSR_DB_PASSWORD "$DB_PASSWORD"
# The runtime copy is regenerated from source by the rsync in step 11, but
# only in prod mode and only if we get that far. Clear a legacy one now so
# a failure in between cannot leave the service reading unprefixed keys.
if [ -f "$RUNTIME/backend/.env" ] && ! grep -q '^CFDSR_' "$RUNTIME/backend/.env" 2>/dev/null; then
    mv -f "$RUNTIME/backend/.env" "$RUNTIME/backend/.env.unprefixed.bak"
    warn "runtime .env also had no CFDSR_ keys — moved aside"
fi
chmod 600 "$BACKEND/.env"
[ "$MODE" = dev ] && [ "$REAL_USER" != root ] && chown "$REAL_USER":"$REAL_USER" "$BACKEND/.env"
ok "CFDSR_DB_PASSWORD in backend/.env matches MySQL"

# ============================================================================
# --restore-latest: work out WHICH files, before touching anything.
# Named to match what the backup scripts produce, plus the hand-rolled
# dbdump_/filedump_ names. If the standard directory has nothing, a few
# obvious alternatives are tried rather than failing on an empty default.
if [ "$RESTORE_LATEST" -eq 1 ]; then
    step "6b. Locating backups"
    FOUND_DIR=""
    for D in "$BACKUP_DIR" "/backups" "$HOME/backups"              "$(getent passwd "$REAL_USER" | cut -d: -f6)/backups"; do
        [ -n "$D" ] && [ -d "$D" ] || continue
        if find "$D" -maxdepth 1 \( -name 'dbdump*.sql.gz' -o -name '*.sql.gz' \)              2>/dev/null | grep -q .; then FOUND_DIR="$D"; break; fi
    done
    [ -n "$FOUND_DIR" ] || die "--restore-latest found no *.sql.gz in any of:
           $BACKUP_DIR
           /backups
           $(getent passwd "$REAL_USER" | cut -d: -f6)/backups
       Point at the right place with --backup-dir /path/to/backups"
    ok "backups in $FOUND_DIR"

    if [ -z "$RESTORE_DUMP" ]; then
        # Newest by MTIME, not by filename. The dumps are named
        # dbdump_20AUG2026 — DDMMMYYYY, which does not sort
        # chronologically: 05SEP2026 sorts before 20AUG2026.
        RESTORE_DUMP=$(find "$FOUND_DIR" -maxdepth 1 -name '*.sql.gz' -printf '%T@ %p
'                        | sort -n | tail -1 | cut -d' ' -f2-)
        [ -n "$RESTORE_DUMP" ] && ok "dump    $(basename "$RESTORE_DUMP")"
    fi
    if [ -z "$RESTORE_UPLOADS" ]; then
        # A hand-rolled filedump_*.tar.gz, else the nightly chain's
        # directory of uploads_full_/uploads_inc_ tars.
        RESTORE_UPLOADS=$(find "$FOUND_DIR" -maxdepth 1 \( -name 'filedump*.tar.gz' -o -name 'filedump*.tar' \) -printf '%T@ %p
'                           | sort -n | tail -1 | cut -d' ' -f2-)
        if [ -z "$RESTORE_UPLOADS" ] &&            find "$FOUND_DIR" -maxdepth 1 -name 'uploads_full_*.tar' | grep -q .; then
            RESTORE_UPLOADS="$FOUND_DIR"
        fi
        [ -n "$RESTORE_UPLOADS" ] && ok "uploads $(basename "$RESTORE_UPLOADS")"
    fi
    [ -n "$RESTORE_DUMP" ] || warn "no database dump found — schema only"
    [ -n "$RESTORE_UPLOADS" ] || warn "no uploads archive found"
fi

# ============================================================================
step "7. Data"
# ============================================================================
TABLES_NOW() { MYSQL_PWD="$DB_PASSWORD" mysql -uroot -N -B -e \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB_NAME';" 2>/dev/null || echo 0; }

if [ -n "$RESTORE_DUMP" ]; then
    [ -f "$RESTORE_DUMP" ] || die "--restore-dump: no such file: $RESTORE_DUMP"
    note "restoring $(basename "$RESTORE_DUMP")"
    if [ "${RESTORE_DUMP##*.}" = gz ]; then
        gunzip -c "$RESTORE_DUMP" | MYSQL_PWD="$DB_PASSWORD" mysql -uroot "$DB_NAME" \
            || die "restore failed"
    else
        MYSQL_PWD="$DB_PASSWORD" mysql -uroot "$DB_NAME" < "$RESTORE_DUMP" || die "restore failed"
    fi
    ok "dump restored — $(TABLES_NOW) tables"
    # Say what this DOES mean, not just what is absent. The earlier
    # wording ("rebuild with analysis.daily") read as an instruction and
    # sent someone off to run a job that is unnecessary here and
    # destructive against a restored database.
    note "the dump excludes statement_transactions (27 GB of raw parsed"
    note "rows). Every ANALYSIS RESULT is present — summaries, mule links,"
    note "crypto rows, photo hashes, the IFSC directory — and no API route"
    note "reads the fact table, so every dashboard works as-is."
    note "You only need it if THIS machine will parse new uploads."
elif [ "$(TABLES_NOW)" -gt 5 ]; then
    ok "database already has $(TABLES_NOW) tables — left alone"
else
    ok "database is empty — restore a dump, or seed with backend/seed.py"
fi

# ============================================================================
step "8. Migrations"
# ============================================================================
# Gated on what is actually in the database. Migrations 001+ ALTER tables
# that a dump or seed.py creates; against an empty schema the first one
# fails, which on an unattended run reads as the whole deploy failing.
if [ "$(TABLES_NOW)" -lt 5 ]; then
    warn "database empty — migrations skipped until there is data"
else
    APPLIED=0
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        m="${f%.py}"
        case "$m" in 005_*) [ "$MODE" = prod ] && continue ;; esac
        ./venv/bin/python -m "migrations.$m" >/dev/null 2>&1 \
            || die "migration $m failed. Run it directly to see the error
       (sudo is required — .env is mode 600 and root-owned):
       cd $BACKEND && sudo venv/bin/python -m migrations.$m"
        APPLIED=$((APPLIED + 1))
    done <<< "$(find migrations -maxdepth 1 -name '[0-9][0-9][0-9]_*.py' -printf '%f\n' | sort)"
    ok "$APPLIED migrations applied (idempotent)"
fi

# ============================================================================
step "9. Uploads"
# ============================================================================
UPLOADS="$BACKEND/uploads"
[ "$MODE" = prod ] && UPLOADS="$RUNTIME/backend/uploads"
mkdir -p "$UPLOADS"

if [ -z "$RESTORE_UPLOADS" ]; then
    ok "uploads/ ready ($(find "$UPLOADS" -type f 2>/dev/null | wc -l) files, nothing to restore)"
elif [ -f "$RESTORE_UPLOADS" ]; then
    # Where it unpacks depends on how it was rolled up, and getting that
    # wrong is silent: the files land a level off, every path in the
    # database misses, and the app reports "no statement" for everything.
    FIRST=$(tar -tf "$RESTORE_UPLOADS" 2>/dev/null | head -1)
    [ -n "$FIRST" ] || die "cannot read $RESTORE_UPLOADS — truncated download?"
    case "$FIRST" in
        backend/*|./backend/*) DEST=$(dirname "$UPLOADS")/..; note "archive holds backend/ — unpacking above it" ;;
        uploads/*|./uploads/*) DEST=$(dirname "$UPLOADS");    note "archive holds uploads/ — unpacking into backend/" ;;
        *)                     DEST="$UPLOADS";               note "archive holds bare files — unpacking into uploads/" ;;
    esac
    tar -xf "$RESTORE_UPLOADS" -C "$DEST" || die "extracting $RESTORE_UPLOADS failed"
    N=$(find "$UPLOADS" -type f | wc -l)
    [ "$N" -eq 0 ] && warn "0 files under $UPLOADS — check the archive layout"
    ok "uploads restored: $N files"
else
    [ -d "$RESTORE_UPLOADS" ] || die "--restore-uploads: no such file or directory"
    stamp_of() { local b; b=$(basename "$1" .tar); b="${b#uploads_full_}"; b="${b#uploads_inc_}"; printf '%s' "$b"; }
    FULL=$(find "$RESTORE_UPLOADS" -maxdepth 1 -name 'uploads_full_*.tar' | sort | tail -1)
    [ -n "$FULL" ] || die "no uploads_full_*.tar in $RESTORE_UPLOADS — an increment
       alone is not a restore; it holds only what changed."
    FULL_TS=$(stamp_of "$FULL")
    tar -xf "$FULL" -C "$(dirname "$UPLOADS")" || die "extracting $FULL failed"
    # Ordered by TIMESTAMP, not filename: "full" sorts before "inc", so
    # comparing whole names makes every increment look newer than every
    # full, including ones from a previous chain.
    while IFS= read -r INC; do
        [ -n "$INC" ] || continue
        [ "$(stamp_of "$INC")" \< "$FULL_TS" ] && continue
        tar -xf "$INC" -C "$(dirname "$UPLOADS")" || die "extracting $INC failed"
    done < <(find "$RESTORE_UPLOADS" -maxdepth 1 -name 'uploads_inc_*.tar' | sort)
    ok "uploads restored: $(find "$UPLOADS" -type f | wc -l) files"
fi

# ============================================================================
step "10. Frontend"
# ============================================================================
if [ "$SKIP_FRONTEND" -eq 1 ]; then
    warn "skipped (--skip-frontend)"
else
    cd "$FRONTEND" || die "no frontend dir"
    if [ -f package-lock.json ]; then npm ci --silent || die "npm ci failed"
    else npm install --silent || die "npm install failed"; fi
    # `npm run build` is `tsc -b && vite build`; the dev server does not
    # typecheck, so a type error only ever surfaces here.
    npm run build >/dev/null 2>&1 \
        || die "frontend build failed. Run it directly to see the errors:
       cd $FRONTEND && npm run build"
    ok "built $(du -sh dist 2>/dev/null | cut -f1)"
fi

# ============================================================================
step "11. Services"
# ============================================================================
if [ "$MODE" = dev ]; then
    ok "dev mode — no systemd. Start the servers yourself."
else
    id -u cyberfraud >/dev/null 2>&1 \
        || useradd --system --no-create-home --shell /usr/sbin/nologin cyberfraud
    mkdir -p "$RUNTIME/backend" "$RUNTIME/frontend" "$RUNTIME/backups" /var/log/cyberfraud
    # uploads is excluded: the runtime copy is the real one and holds 22 GB.
    rsync -a --delete --exclude venv --exclude __pycache__ --exclude uploads \
        "$BACKEND/" "$RUNTIME/backend/" || die "backend sync failed"
    mkdir -p "$RUNTIME/backend/uploads"
    rsync -a --delete "$FRONTEND/dist/" "$RUNTIME/frontend/dist/" 2>/dev/null
    rsync -a "$SOURCE/deploy/" "$RUNTIME/deploy/"

    [ -d "$RUNTIME/backend/venv" ] || python3 -m venv "$RUNTIME/backend/venv"
    "$RUNTIME/backend/venv/bin/pip" install -q -U pip wheel
    "$RUNTIME/backend/venv/bin/pip" install -q -r "$RUNTIME/backend/requirements.txt" \
        || die "runtime pip install failed"

    # Ownership LAST and over everything: the service runs as cyberfraud and
    # reads .env itself, so a root-owned 600 .env stops it dead with a
    # config error that looks nothing like a permissions problem.
    chown -R cyberfraud:cyberfraud "$RUNTIME" /var/log/cyberfraud
    chmod 600 "$RUNTIME/backend/.env" 2>/dev/null
    chmod +x "$RUNTIME"/deploy/*.sh 2>/dev/null
    ok "runtime staged at $RUNTIME"

    install -m 644 "$SOURCE/deploy/cyberfraud-backend.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable cyberfraud-backend >/dev/null 2>&1
    systemctl restart cyberfraud-backend || {
        journalctl -u cyberfraud-backend -n 25 --no-pager | sed 's/^/        /'
        die "cyberfraud-backend failed to start — journal above"
    }
    ok "cyberfraud-backend started"

    if [ -f "$SOURCE/deploy/nginx.conf" ]; then
        # nginx.conf listens on 443 and port 80 only redirects to it, so
        # without a certificate `nginx -t` fails, nothing serves, and you
        # are left with an API on :8000 and no browser URL. Generate a
        # self-signed one if it is missing — CYBERFRAUD_CERT_CN sets the
        # CN, defaulting to this machine's primary address so the browser
        # warning at least names the right host.
        if [ ! -f /etc/ssl/certs/cyberfraud.crt ] || [ ! -f /etc/ssl/private/cyberfraud.key ]; then
            if [ -f "$SOURCE/deploy/generate-cert.sh" ]; then
                CYBERFRAUD_CERT_CN="${CYBERFRAUD_CERT_CN:-$(hostname -I | awk '{print $1}')}" \
                    bash "$SOURCE/deploy/generate-cert.sh" >/dev/null 2>&1 \
                    && ok "self-signed cert generated (CN=$(hostname -I | awk '{print $1}'))" \
                    || warn "generate-cert.sh failed — nginx will not start"
            else
                warn "no cert and no generate-cert.sh — nginx will not start"
            fi
        else
            ok "TLS cert already present"
        fi
        install -m 644 "$SOURCE/deploy/nginx.conf" /etc/nginx/sites-available/cyberfraud
        ln -sfn /etc/nginx/sites-available/cyberfraud /etc/nginx/sites-enabled/cyberfraud
        rm -f /etc/nginx/sites-enabled/default
        if nginx -t >/dev/null 2>&1; then systemctl reload nginx && ok "nginx serving"
        else warn "nginx config did not validate — backend still up on :8000"; fi
    fi

    if [ "$NO_NIGHTLY" -eq 1 ]; then
        # Actively disable, not merely skip installing: a machine that had
        # the timer once keeps firing it.
        systemctl disable --now cyberfraud-nightly.timer  >/dev/null 2>&1
        systemctl disable --now cyberfraud-backup.timer   >/dev/null 2>&1
        systemctl disable --now cyberfraud-analysis.timer >/dev/null 2>&1
        ok "nightly timer NOT installed (--no-nightly); any existing one disabled"
        note "backups and analysis on this machine are manual, by design"
    elif [ -f "$SOURCE/deploy/install-nightly.sh" ]; then
        bash "$SOURCE/deploy/install-nightly.sh" >/dev/null 2>&1 \
            && ok "nightly analysis + backup timer installed" \
            || warn "install-nightly.sh did not complete — run it by hand"
    fi
fi

# ============================================================================
step "12. Verify"
# ============================================================================
verify "MySQL reachable" env MYSQL_PWD="$DB_PASSWORD" mysql -uroot -e "USE $DB_NAME"

# THE check. Everything else proves this script's connection works; this
# proves the one the APP uses works, read from .env the way the app reads
# it. Its absence is why a wrong password surfaced as "Access denied"
# during a restore instead of here, as one red line, while still cheap.
for F in "$BACKEND/.env" "$RUNTIME/backend/.env"; do
    [ -f "$F" ] || continue
    P=$(get_env_var "$F" CFDSR_DB_PASSWORD)
    if MYSQL_PWD="$P" mysql -uroot -e "USE $DB_NAME" >/dev/null 2>&1; then
        pass_ "CFDSR_DB_PASSWORD in $F authenticates"
    else
        fail_ "CFDSR_DB_PASSWORD in $F does NOT authenticate"
    fi
done

T=$(TABLES_NOW)
if [ "$T" -ge 36 ]; then pass_ "$T tables present"
elif [ "$T" -eq 0 ]; then warn "database empty — restore a dump, then re-run this script"
else fail_ "only $T tables — expected 36+ or 0"; fi

if [ "$T" -ge 36 ]; then
    PS_COUNT=$(MYSQL_PWD="$DB_PASSWORD" mysql -uroot -N -B "$DB_NAME" \
        -e "SELECT COUNT(*) FROM police_stations;" 2>/dev/null || echo 0)
    if [ "$PS_COUNT" -ge 40 ] && [ "$PS_COUNT" -le 60 ]; then
        pass_ "police_stations = $PS_COUNT"
    else
        fail_ "police_stations = $PS_COUNT — expected ~44"
    fi
fi

[ "$SKIP_FRONTEND" -eq 1 ] || verify "frontend built" test -f "$FRONTEND/dist/index.html"

if [ "$MODE" = prod ]; then
    verify "cyberfraud-backend active" systemctl is-active --quiet cyberfraud-backend
    sleep 3
    verify "health endpoint responds" curl -fsS --max-time 5 http://localhost:8000/health
    # The backend being up is not the same as the app being reachable.
    # nginx serves the frontend and proxies the API; if its cert is
    # missing it silently does neither.
    if systemctl is-active --quiet nginx; then
        verify "nginx serving over https" curl -fsSk --max-time 5 https://localhost/health
    else
        fail_ "nginx is not running — the app is not reachable in a browser.
        The API is still up on :8000. Check: sudo nginx -t"
    fi
    if [ -f "$RUNTIME/backend/.env" ]; then
        verify ".env readable by the service user" \
            sudo -u cyberfraud test -r "$RUNTIME/backend/.env"
    fi
fi

echo
if [ "$FAILED" -eq 0 ]; then
    printf "\033[1;32m  DEPLOY COMPLETE\033[0m\n\n"
    if [ "$MODE" = prod ]; then
        echo "  https://$(hostname -I | awk '{print $1}')/    (self-signed cert — accept the browser warning)"
        echo "  journalctl -u cyberfraud-backend -f"
    else
        echo "  cd $BACKEND   && source venv/bin/activate && uvicorn cyber_fraud:app --reload --port 8000"
        echo "  cd $FRONTEND  && npm run dev"
    fi
    echo
    echo "  Re-run any time — no arguments needed, the password comes from .env:"
    echo "      sudo bash $0"
    echo
else
    printf "\033[1;31m  FINISHED WITH FAILURES — see the FAIL lines above\033[0m\n\n"
fi
exit "$FAILED"
