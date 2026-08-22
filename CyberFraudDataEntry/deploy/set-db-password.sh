#!/usr/bin/env bash
# ============================================================================
# CyberFraud Data Entry — CHANGE THE MySQL ROOT PASSWORD
#
# Changes it in MySQL and in every backend/.env on the machine, so the two
# never drift apart. .env stays the single source of truth: the app, the
# nightly chain, bootstrap.sh and update.sh all read the password from
# there, and nothing else stores a copy.
#
# USAGE
#   sudo bash deploy/set-db-password.sh 'NewPassword'   # from the CLI
#   sudo bash deploy/set-db-password.sh                 # prompt, hidden
#
# FLAGS
#   --yes    don't ask for confirmation
#   --help
#
# WHY IT ROLLS BACK
# There are two places the password lives, and a half-finished change
# leaves the app unable to reach its own database. If anything after the
# MySQL change fails, this puts the old password back in both places
# before exiting, so a failed run leaves you exactly where you started.
#
# NOTE ON PASSING IT ON THE COMMAND LINE
# An argument is visible in `ps` while this runs and lands in your shell
# history. On a single-user box that is usually fine. Run with no argument
# to be prompted instead — the input is hidden and never reaches history.
# ============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME=/opt/cyberfraud

ASSUME_YES=0
NEWPASS=""

ok()   { printf "  \033[32mok\033[0m    %s\n" "$1"; }
warn() { printf "  \033[33mwarn\033[0m  %s\n" "$1"; }
note() { printf "        %s\n" "$1"; }
die()  { printf "\n  \033[31mFATAL\033[0m %s\n\n" "$1" >&2; exit 1; }
step() { printf "\n\033[1;36m=== %s ===\033[0m\n" "$1"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --yes|-y)  ASSUME_YES=1; shift ;;
        --help|-h) sed -n '2,30p' "$0"; exit 0 ;;
        -*)        die "unknown option: $1  (try --help)" ;;
        *)         NEWPASS="$1"; shift ;;
    esac
done

[ "$(id -u)" -eq 0 ] || die "run with sudo: sudo bash deploy/set-db-password.sh ..."

# ── Which .env files exist on this machine ──────────────────────────────
# Both matter. bootstrap.sh and update.sh copy source -> runtime, so
# changing only the runtime copy reverts on the next deploy, silently and
# hours later.
ENV_FILES=()
for F in "$SOURCE/backend/.env" "$RUNTIME/backend/.env"; do
    [ -f "$F" ] && ENV_FILES+=("$F")
done
[ "${#ENV_FILES[@]}" -gt 0 ] || die "no backend/.env found in $SOURCE/backend or $RUNTIME/backend.
       Nothing to update — has bootstrap.sh run yet?"

step "1. Current state"
for F in "${ENV_FILES[@]}"; do ok "found $F"; done

# The current password comes from .env, so you never have to remember it.
OLDPASS=$(grep -h '^DB_PASSWORD=' "${ENV_FILES[0]}" | head -1 | cut -d= -f2-)
[ -n "$OLDPASS" ] || die "${ENV_FILES[0]} has no DB_PASSWORD line"

# If the .env copies already disagree, fix that first: this script would
# otherwise "succeed" while leaving one of them pointing at a dead password.
for F in "${ENV_FILES[@]}"; do
    THIS=$(grep -h '^DB_PASSWORD=' "$F" | head -1 | cut -d= -f2-)
    [ "$THIS" = "$OLDPASS" ] || die "the .env files disagree about DB_PASSWORD.
       ${ENV_FILES[0]} and $F hold different values. Decide which is correct,
       make them match, then run this again."
done
ok ".env copies agree"

MYSQL_PWD="$OLDPASS" mysql -uroot -e "SELECT 1" >/dev/null 2>&1 \
    || die "the DB_PASSWORD in .env does not actually work against MySQL.
       Fix that first — this script needs it to authenticate the change."
ok "current password authenticates"

# ── The new one ─────────────────────────────────────────────────────────
if [ -z "$NEWPASS" ]; then
    printf "  New MySQL root password: "; read -rs NEWPASS; printf "\n"
    printf "  Again to confirm:        "; read -rs CONFIRM; printf "\n"
    [ "$NEWPASS" = "$CONFIRM" ] || die "the two entries did not match"
fi

[ -n "$NEWPASS" ] || die "empty password"
[ "$NEWPASS" = "$OLDPASS" ] && die "that is already the current password"
[ "${#NEWPASS}" -ge 8 ] || die "too short — use at least 8 characters.
       This gates local access to real case data."

# Single quotes and backslashes would need escaping in the SQL literal and
# are not worth the risk here; everything else is accepted, because the
# .env rewrite below is character-safe (no sed).
case "$NEWPASS" in
    *\'*|*\\*) die "avoid single quotes and backslashes in the password" ;;
esac
ok "new password accepted (${#NEWPASS} characters)"

if [ "$ASSUME_YES" -eq 0 ]; then
    echo
    echo "  This changes the MySQL root password and rewrites"
    for F in "${ENV_FILES[@]}"; do echo "      $F"; done
    echo
    read -r -p "  Proceed? [y/N] " reply
    case "$reply" in y|Y) ;; *) die "aborted — nothing changed" ;; esac
fi

# ── Rollback plumbing ───────────────────────────────────────────────────
MYSQL_CHANGED=0
rollback() {
    printf "\n  \033[33mrolling back\033[0m\n"
    if [ "$MYSQL_CHANGED" -eq 1 ]; then
        MYSQL_PWD="$NEWPASS" mysql -uroot -e \
            "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '$OLDPASS'; FLUSH PRIVILEGES;" \
            2>/dev/null \
        || MYSQL_PWD="$NEWPASS" mysql -uroot -e \
            "ALTER USER 'root'@'localhost' IDENTIFIED BY '$OLDPASS'; FLUSH PRIVILEGES;" 2>/dev/null \
        && note "MySQL password restored"
    fi
    for F in "${ENV_FILES[@]}"; do
        [ -f "$F.pwbak" ] && mv -f "$F.pwbak" "$F" && note "restored $F"
    done
}

step "2. MySQL"
# mysql_native_password first for widest client compatibility; fall back to
# the server default if a newer MySQL has dropped the plugin.
MYSQL_PWD="$OLDPASS" mysql -uroot -e \
    "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '$NEWPASS'; FLUSH PRIVILEGES;" 2>/dev/null \
|| MYSQL_PWD="$OLDPASS" mysql -uroot -e \
    "ALTER USER 'root'@'localhost' IDENTIFIED BY '$NEWPASS'; FLUSH PRIVILEGES;" \
|| die "could not change the MySQL password — nothing else was touched"
MYSQL_CHANGED=1
ok "MySQL root password changed"

MYSQL_PWD="$NEWPASS" mysql -uroot -e "SELECT 1" >/dev/null 2>&1 \
    || { rollback; die "the new password does not authenticate — rolled back"; }
ok "new password authenticates"

step "3. .env files"
for F in "${ENV_FILES[@]}"; do
    cp -p "$F" "$F.pwbak" || { rollback; die "could not back up $F"; }
    # Rewritten line by line rather than with sed: this is safe for every
    # character a password might contain, including & | / and #.
    TMP="$F.pwtmp"
    : > "$TMP"
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            DB_PASSWORD=*) printf '%s\n' "DB_PASSWORD=$NEWPASS" >> "$TMP" ;;
            *)             printf '%s\n' "$line"                >> "$TMP" ;;
        esac
    done < "$F"

    # Compared as strings, not with grep: a password containing . * [ or ?
    # would be a regex there, and could report a match the file does not
    # actually contain.
    WROTE=$(grep -m1 '^DB_PASSWORD=' "$TMP" | cut -d= -f2-)
    [ "$WROTE" = "$NEWPASS" ] \
        || { rm -f "$TMP"; rollback; die "rewrite of $F did not take"; }

    # Keep the original owner and 600 permissions.
    chown --reference="$F" "$TMP" 2>/dev/null
    chmod 600 "$TMP"
    mv -f "$TMP" "$F" || { rollback; die "could not replace $F"; }
    ok "updated $F"
done

step "4. Service"
if systemctl list-unit-files cyberfraud-backend.service >/dev/null 2>&1 \
   && systemctl is-enabled --quiet cyberfraud-backend 2>/dev/null; then
    systemctl restart cyberfraud-backend || { rollback; die "backend failed to restart — rolled back"; }
    sleep 3
    if systemctl is-active --quiet cyberfraud-backend; then
        ok "cyberfraud-backend restarted"
    else
        rollback
        die "cyberfraud-backend is not active after the change — rolled back.
       Check: journalctl -u cyberfraud-backend -n 40"
    fi
    if curl -fsS --max-time 5 http://localhost:8000/health >/dev/null 2>&1; then
        ok "health endpoint responding"
    else
        warn "health endpoint did not answer — the password change stands,"
        warn "but check: journalctl -u cyberfraud-backend -n 40"
    fi
else
    ok "no systemd service on this machine (dev mode) — restart your own"
    note "backend so it picks up the new .env"
fi

# Success: the backups are no longer a rollback path, only stale copies of
# the OLD password sitting at mode 600. Remove them.
for F in "${ENV_FILES[@]}"; do rm -f "$F.pwbak"; done

step "5. Done"
printf "\n\033[1;32m  PASSWORD CHANGED\033[0m\n\n"
cat <<DONEEOF
  MySQL and every .env on this machine now agree.

  Use it for a restore like this — the password comes from .env, so there
  is nothing to type or remember:

    sudo bash -c 'set -a; . $RUNTIME/backend/.env; set +a;
      gunzip -c /path/to/dbdump.sql.gz |
      MYSQL_PWD="\$DB_PASSWORD" mysql -uroot cyber_fraud_dsr'

DONEEOF
