#!/usr/bin/env bash
# Read-only pre-deploy checklist. Mutates nothing.
#
# Run this before redeploy-vapt-fixes.sh to confirm the server is in
# shape. Exits 0 on all-pass, 1 on any failure, so it can also be used
# in CI / pre-deploy gates.
#
# Usage:
#   cd /opt/scrb && bash CyberFraudDataEntry/deploy/preflight.sh

set -uo pipefail  # intentionally NO -e — every check must run

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SOURCE/.." && pwd)"
RUNTIME=/opt/cyberfraud

fail=0

ok()   { printf "  \033[32mPASS\033[0m  %-32s %s\n" "$1" "${2:-}"; }
nope() { printf "  \033[31mFAIL\033[0m  %-32s %s\n" "$1" "${2:-}"; fail=1; }

check_cmd() {
    local label="$1"; shift
    local out
    if out=$("$@" 2>/dev/null); then ok "$label" "$out"; else nope "$label" "(command failed)"; fi
}

check_path() {
    local label="$1" path="$2"
    if [ -e "$path" ]; then ok "$label" "$path"; else nope "$label" "$path missing"; fi
}

echo "=== CyberFraud pre-deploy checklist ==="
echo "  SOURCE  $SOURCE"
echo "  REPO    $REPO_ROOT"
echo "  RUNTIME $RUNTIME"
echo

# Toolchain
check_cmd  "node available"             node --version
check_cmd  "npm available"              npm --version

# Filesystem prerequisites the deploy script depends on
check_path "seed Excel"                 "$RUNTIME/All District CEN_PS.xlsx"
check_path "backend venv python"        "$RUNTIME/backend/venv/bin/python"
check_path "nginx site config"          /etc/nginx/sites-available/cyberfraud
check_path "redeploy script readable"   "$SCRIPT_DIR/redeploy-vapt-fixes.sh"

# Services
if systemctl is-active --quiet mysql; then ok   "MySQL service active"
else                                       nope "MySQL service active" "(systemctl is-active mysql)"; fi

if systemctl list-unit-files --no-pager 2>/dev/null | grep -q '^cyberfraud-backend\.service'; then
    ok   "cyberfraud-backend service unit installed"
else
    nope "cyberfraud-backend service unit installed" "(no systemd unit file)"
fi

# OS user the runtime files are chowned to
if id cyberfraud >/dev/null 2>&1; then ok   "cyberfraud OS user exists"
else                                   nope "cyberfraud OS user exists"; fi

# Source-clone state — tell operator HEAD + whether they're behind origin
if cd "$REPO_ROOT" 2>/dev/null; then
    HEAD=$(git log -1 --oneline 2>/dev/null || echo "<no git>")
    ok "git HEAD" "$HEAD"
    git fetch --quiet 2>/dev/null && true
    BEHIND=$(git rev-list --count HEAD..@{u} 2>/dev/null || echo "?")
    if [ "$BEHIND" = "0" ]; then
        ok "git up-to-date with origin" "behind=0"
    elif [ "$BEHIND" = "?" ]; then
        nope "git up-to-date with origin" "(no upstream tracking branch)"
    else
        nope "git up-to-date with origin" "behind=$BEHIND — run: cd $REPO_ROOT && git pull"
    fi
fi

# Informational — tells the operator whether stage 4 will run or skip
echo
if [ -f "$RUNTIME/.db_migration_done" ]; then
    printf "  \033[33mINFO\033[0m  DB migration marker PRESENT — stage 4 will SKIP the destructive reset.\n"
else
    printf "  \033[33mINFO\033[0m  DB migration marker ABSENT  — stage 4 will RUN the destructive reset (one-shot).\n"
fi

echo
if [ $fail -eq 0 ]; then
    echo "All pre-flight checks passed. Safe to run:"
    echo "    bash CyberFraudDataEntry/deploy/redeploy-vapt-fixes.sh"
    exit 0
else
    echo "Some pre-flight checks FAILED. Fix them before running the deploy."
    exit 1
fi
