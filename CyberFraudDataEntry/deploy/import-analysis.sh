#!/usr/bin/env bash
# ============================================================================
# CyberFraud Data Entry — import analysis results onto PRODUCTION.
#
#   sudo /opt/cyberfraud/deploy/import-analysis.sh <analysis_YYYY-MM-DD.sql.gz>
#
# Loads the four dashboard tables produced by deploy/export-analysis.sh
# on the parsing machine. Takes a few seconds. Runs against a live
# server serving ~90 operators.
#
# HOW IT AVOIDS IMPACTING THE RUNNING APPLICATION
# -----------------------------------------------
# The naive import — TRUNCATE then INSERT — leaves the dashboards
# reading an empty or half-filled table for the duration. Any officer
# who loads Money Trail in that window sees zero transactions and no
# error, which is worse than a failure because it looks like an answer.
#
# So the load happens in three stages:
#
#   1. Rows go into STAGING tables (`_stg` suffix). Nothing the
#      application reads is touched. This is the slow part.
#   2. One TRANSACTION per table does DELETE + INSERT...SELECT from
#      staging. InnoDB's MVCC means concurrent readers continue to see
#      the OLD rows until COMMIT — there is no instant at which a
#      dashboard can observe a partial table.
#   3. Staging tables are dropped.
#
# The INSERT...SELECT inner-joins all_accounts, which silently drops
# rows referencing accounts deleted on production since the parsing
# machine took its copy. Those rows are invisible to the dashboards
# anyway (every dashboard query inner-joins all_accounts), and letting
# them through would fail the foreign key and abort the whole import.
#
# NOT touched: statement_transactions. It is not shipped and not needed
# — no API route reads it.
#
# Safe to re-run. Safe to interrupt: an abort before COMMIT leaves the
# live tables exactly as they were.
# ============================================================================

set -euo pipefail
set -o pipefail

DUMP="${1:-}"
# Overridable so the whole import can be rehearsed against a scratch
# database before it is ever pointed at production. On the server the
# default is correct and nothing needs to be set.
ENV_FILE="${CFDSR_ENV_FILE:-/opt/cyberfraud/backend/.env}"

if [ -z "$DUMP" ]; then
    echo "Usage: $0 <analysis_YYYY-MM-DD.sql.gz>" >&2
    exit 1
fi
if [ ! -r "$DUMP" ]; then
    echo "ERROR: cannot read $DUMP" >&2
    exit 1
fi
if [ ! -r "$ENV_FILE" ]; then
    echo "ERROR: cannot read $ENV_FILE" >&2
    exit 1
fi

val() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d'=' -f2- || true; }
DB_HOST=$(val CFDSR_DB_HOST); DB_PORT=$(val CFDSR_DB_PORT)
DB_USER=$(val CFDSR_DB_USER); DB_PASS=$(val CFDSR_DB_PASSWORD)
DB_NAME=$(val CFDSR_DB_NAME)
: "${DB_HOST:=localhost}"; : "${DB_PORT:=3306}"
: "${DB_USER:=root}";      : "${DB_NAME:=cyber_fraud_dsr}"

my() { MYSQL_PWD="$DB_PASS" mysql --host="$DB_HOST" --port="$DB_PORT" \
       --user="$DB_USER" "$@"; }
q()  { my --skip-column-names --batch "$DB_NAME" -e "$1"; }

#: Tables, and the column each uses to reach all_accounts. Kept
#: explicit rather than derived so a schema change forces a human to
#: reconsider the join instead of the script guessing.
TABLES="account_statement_summary:account_id
upload_ledger:account_id
id_photo_hashes:account_id
mule_account_link:src_account_id"

echo "============================================================"
echo "  Import analysis results  ->  $DB_NAME"
echo "  Dump: $DUMP"
echo "  $(TZ=Asia/Kolkata date -Iseconds)"
echo "============================================================"

# ── 1. Record what is live now, so the swap can be reported ──────────
echo
echo "=== 1. Current row counts ==="
declare -A BEFORE
for entry in $TABLES; do
    t="${entry%%:*}"
    n=$(q "SELECT COUNT(*) FROM \`$t\`" 2>/dev/null || echo 0)
    BEFORE[$t]=$n
    printf '  %-30s %12s\n' "$t" "$n"
done

# ── 2. Build staging tables ──────────────────────────────────────────
# LIKE copies the production schema exactly, so the staging table can
# never disagree with the table it will feed.
echo
echo "=== 2. Create staging tables ==="
for entry in $TABLES; do
    t="${entry%%:*}"
    q "DROP TABLE IF EXISTS \`${t}_stg\`;"
    q "CREATE TABLE \`${t}_stg\` LIKE \`$t\`;"
    # Foreign keys on staging would reject rows this script intends to
    # filter out itself, and would fire during the slow load rather
    # than at the swap. Drop them; the real tables keep theirs.
    for fk in $(q "SELECT constraint_name FROM information_schema.table_constraints
                   WHERE table_schema='$DB_NAME' AND table_name='${t}_stg'
                     AND constraint_type='FOREIGN KEY'"); do
        q "ALTER TABLE \`${t}_stg\` DROP FOREIGN KEY \`$fk\`;" || true
    done
    echo "  ${t}_stg ready"
done

cleanup() {
    for entry in $TABLES; do
        q "DROP TABLE IF EXISTS \`${entry%%:*}_stg\`;" 2>/dev/null || true
    done
}
trap cleanup EXIT

# ── 3. Load the dump into staging ────────────────────────────────────
# The dump names the REAL tables, so rewrite the INSERT targets to the
# staging names on the way in. Anchored on "INSERT INTO `name`" so the
# substitution cannot touch data inside a row.
echo
echo "=== 3. Load dump into staging ==="
#
# LOCK TABLES is rewritten too. Current exports pass --skip-add-locks
# so they carry none, but a dump made before that flag was added would
# lock the REAL table and then fail every redirected insert with error
# 1100. Rewriting both keeps old export files loadable.
SED_ARGS=()
for entry in $TABLES; do
    t="${entry%%:*}"
    SED_ARGS+=( -e "s/^INSERT INTO \`${t}\`/INSERT INTO \`${t}_stg\`/" )
    SED_ARGS+=( -e "s/^LOCK TABLES \`${t}\` WRITE/LOCK TABLES \`${t}_stg\` WRITE/" )
done
gunzip -c "$DUMP" | sed "${SED_ARGS[@]}" | my "$DB_NAME"

echo "  loaded:"
STAGED_EMPTY=0
for entry in $TABLES; do
    t="${entry%%:*}"
    n=$(q "SELECT COUNT(*) FROM \`${t}_stg\`")
    printf '    %-28s %12s\n' "${t}_stg" "$n"
    [ "$n" -eq 0 ] && STAGED_EMPTY=1
done

if [ "$STAGED_EMPTY" -ne 0 ]; then
    echo >&2
    echo "ERROR: a staging table is empty — the dump did not contain what" >&2
    echo "       was expected. Live tables NOT touched. Aborting." >&2
    exit 2
fi

# ── 4. Atomic swap, one transaction per table ────────────────────────
# Readers see the old rows until COMMIT.
#
# The join drops rows whose account no longer exists on this server —
# they would fail the foreign key and abort the import, and every
# dashboard query inner-joins all_accounts, so they were never visible.
#
# It is a LEFT JOIN keeping NULLs, not an inner join. A NULL account_id
# means a file that could not be resolved to an account, which is a
# real and countable outcome: 15,917 of upload_ledger's 34,006 rows
# are in that state, and the Statement Coverage quality breakdown reads
# `SELECT status, COUNT(*) FROM upload_ledger GROUP BY status` with no
# join at all. An inner join here silently discarded 47% of that
# denominator and made coverage look better than it is — caught by
# rehearsing this import against a scratch database.
echo
echo "=== 4. Swap into live tables ==="
for entry in $TABLES; do
    t="${entry%%:*}"; col="${entry##*:}"
    cols=$(q "SELECT GROUP_CONCAT(CONCAT('\`',column_name,'\`') ORDER BY ordinal_position)
              FROM information_schema.columns
              WHERE table_schema='$DB_NAME' AND table_name='$t'")
    my "$DB_NAME" <<SQL
START TRANSACTION;
DELETE FROM \`$t\`;
INSERT INTO \`$t\` ($cols)
SELECT $(echo "$cols" | sed 's/`\([^`]*\)`/s.`\1`/g')
FROM \`${t}_stg\` s
LEFT JOIN all_accounts a ON a.id = s.\`$col\`
WHERE s.\`$col\` IS NULL OR a.id IS NOT NULL;
COMMIT;
SQL
    after=$(q "SELECT COUNT(*) FROM \`$t\`")
    staged=$(q "SELECT COUNT(*) FROM \`${t}_stg\`")
    dropped=$(( staged - after ))
    printf '  %-30s %8s -> %-8s' "$t" "${BEFORE[$t]}" "$after"
    if [ "$dropped" -gt 0 ]; then
        printf '  (%s row(s) skipped: account not on this server)' "$dropped"
    fi
    echo
done

# ── 5. Verify ────────────────────────────────────────────────────────
echo
echo "=== 5. Verify ==="
ORPHAN=$(q "SELECT COUNT(*) FROM account_statement_summary s
            LEFT JOIN all_accounts a ON a.id = s.account_id
            WHERE a.id IS NULL")
echo "  orphaned summary rows : $ORPHAN   (must be 0)"
if [ "$ORPHAN" -ne 0 ]; then
    echo "ERROR: orphans present after import" >&2
    exit 3
fi

TXNS=$(q "SELECT COALESCE(SUM(verified_txns),0) FROM account_statement_summary")
ACCS=$(q "SELECT COUNT(DISTINCT account_id) FROM account_statement_summary")
echo "  accounts with statements : $ACCS"
echo "  chain-verified txns      : $TXNS"

echo
echo "============================================================"
echo "  Import complete. No restart needed — the application reads"
echo "  these tables per request."
echo "  Dashboards updated: Money Trail, Statement Coverage,"
echo "  Duplicate IDs, Mule Network."
echo "============================================================"
