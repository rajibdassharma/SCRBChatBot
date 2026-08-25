#!/usr/bin/env bash
#
# Archive backend/uploads — WEEKLY FULL + NIGHTLY INCREMENTAL.
#
# WHY THIS CHANGED
# It used to write a complete `tar -czf` of the whole tree every night:
# 19.5 GB and ~24 minutes, to capture the ~500 MB of files actually
# uploaded that day. Uploads are append-only, so all but a fraction of
# that work re-archived bytes that had not moved since the last run.
#
# The compression was not earning its place either. Measured 2026-08-21
# on this corpus: gzip saves 11% on the statement PDFs and 5% on the ID
# photos -- both are already-compressed formats. Roughly 9% of disk for
# 24 minutes of single-threaded CPU, every night, on a 2-vCPU box that
# needs those cycles for the analysis. The archives are now plain tar.
#
# HOW THE CHAIN WORKS
# GNU tar's --listed-incremental keeps a snapshot file recording what
# was archived. A full run starts a new snapshot; each nightly run adds
# only what changed since. Restore is the full, then every increment
# after it IN ORDER.
#
#   tar -xf uploads_full_<ts>.tar   -C /opt/cyberfraud/backend
#   tar -xf uploads_inc_<ts>.tar    -C /opt/cyberfraud/backend   # each, in order
#
# WHAT A BROKEN CHAIN COSTS
# Losing an increment loses the files first seen in it, not the whole
# archive -- because uploads are append-only, each increment is
# essentially "the new files". That is why a weekly full is enough: the
# chain never grows longer than seven links.
#
#   --full   force a full now (also run automatically on FULL_DOW,
#            and whenever the snapshot is missing)
set -euo pipefail

UPLOAD_DIR=/opt/cyberfraud/backend/uploads
BACKUP_DIR=/opt/cyberfraud/backups
SNAPSHOT="$BACKUP_DIR/uploads.snar"
#: Day of week for the automatic full. 7 = Sunday (date +%u).
FULL_DOW=${CFDSR_UPLOADS_FULL_DOW:-7}

FORCE_FULL=0
[ "${1:-}" = "--full" ] && FORCE_FULL=1

if [ ! -d "$UPLOAD_DIR" ]; then
    echo "[backup-uploads] $UPLOAD_DIR does not exist yet — skipping (no files uploaded)."
    exit 0
fi
if [ -z "$(find "$UPLOAD_DIR" -type f -print -quit 2>/dev/null)" ]; then
    echo "[backup-uploads] $UPLOAD_DIR is empty — skipping."
    exit 0
fi

mkdir -p "$BACKUP_DIR"
chmod 750 "$BACKUP_DIR"
chown -R cyberfraud:cyberfraud "$BACKUP_DIR" 2>/dev/null || true

# SECONDS matter here, unlike in the old script. Names were minute
# resolution, which was harmless when every archive was self-contained:
# a second run in the same minute overwrote the first and lost nothing.
# In a CHAIN it is destructive -- overwriting an increment permanently
# loses the files that appeared only in it, and the snapshot still says
# they were archived, so no later run picks them up. Caught by restoring
# a test chain rather than by reading the code.
TIMESTAMP=$(TZ=Asia/Kolkata date +'%Y-%m-%d_%H%M%S')
DOW=$(TZ=Asia/Kolkata date +'%u')

# TWO ways the chain can be broken, and both must force a full.
#
# 1. A MISSING SNAPSHOT means there is nothing to extend, so an
#    "incremental" would archive everything while being named as though
#    it were small.
#
# 2. A MISSING FULL ARCHIVE means the increments have nothing to be
#    restored on top of. This is the dangerous one and it was not
#    checked until 2026-08-25. The full is ~20 GB and the increments are
#    a few hundred MB, so the full is exactly the file someone deletes
#    to reclaim disk. Do that and the snapshot survives, every
#    subsequent run is an incremental, every run reports success, the
#    logs look normal -- and the chain is unrestorable. You find out at
#    restore time, which is the worst possible moment.
#
#    Checked by looking for the file rather than by trusting the
#    snapshot, because the snapshot describes what tar archived, not
#    what still exists on disk.
HAVE_FULL=$(find "$BACKUP_DIR" -maxdepth 1 -name 'uploads_full_*.tar' -print -quit 2>/dev/null)

MODE=incremental
if [ "$FORCE_FULL" -eq 1 ] || [ ! -f "$SNAPSHOT" ] || [ -z "$HAVE_FULL" ]    || [ "$DOW" = "$FULL_DOW" ]; then
    MODE=full
fi

# Say WHY, so a full appearing on a Tuesday is explicable from the log
# rather than alarming.
if [ "$MODE" = "full" ]; then
    if   [ "$FORCE_FULL" -eq 1 ];   then WHY="--full requested"
    elif [ ! -f "$SNAPSHOT" ];      then WHY="no snapshot: $SNAPSHOT is missing"
    elif [ -z "$HAVE_FULL" ];       then WHY="no full archive left in $BACKUP_DIR"
    else                                 WHY="scheduled (day $FULL_DOW)"
    fi
    echo "[backup-uploads] taking a FULL archive -- $WHY"
fi

if [ "$MODE" = "full" ]; then
    OUTFILE="$BACKUP_DIR/uploads_full_${TIMESTAMP}.tar"
    # Start a fresh chain. The old snapshot must go BEFORE tar runs, or
    # tar extends the previous chain and the "full" is not one.
    rm -f "$SNAPSHOT"
else
    OUTFILE="$BACKUP_DIR/uploads_inc_${TIMESTAMP}.tar"
fi

# Belt and braces on top of the second-resolution name: never write
# over an existing archive, whatever the clock says.
if [ -e "$OUTFILE" ]; then
    echo "[backup-uploads] ERROR: $OUTFILE already exists — refusing to" >&2
    echo "                 overwrite an archive that may be part of the chain." >&2
    exit 1
fi

echo "[backup-uploads] $(date -Iseconds) — $MODE archive of $UPLOAD_DIR → $OUTFILE"

# --listed-incremental writes the snapshot as it goes. Writing to a
# temporary and moving it into place on success means a tar that dies
# halfway cannot leave a snapshot claiming files it never archived --
# which would make the NEXT increment skip them silently.
TMP_SNAP="$SNAPSHOT.tmp"
[ -f "$SNAPSHOT" ] && cp -p "$SNAPSHOT" "$TMP_SNAP" || : > "$TMP_SNAP"

tar --listed-incremental="$TMP_SNAP" \
    -C "$(dirname "$UPLOAD_DIR")" \
    -cf "$OUTFILE" "$(basename "$UPLOAD_DIR")"

mv -f "$TMP_SNAP" "$SNAPSHOT"
chmod 640 "$OUTFILE" "$SNAPSHOT"
chown cyberfraud:cyberfraud "$OUTFILE" "$SNAPSHOT" 2>/dev/null || true

SIZE=$(stat -c '%s' "$OUTFILE")
FILE_COUNT=$(find "$UPLOAD_DIR" -type f | wc -l)
echo "[backup-uploads] OK — wrote $OUTFILE ($SIZE bytes)"
# Counting members costs a full read of the archive, so it is done only
# for increments -- a few hundred MB, and the count is the interesting
# number there. On a 19.5 GB full it would mean reading the whole thing
# back just to print a figure the source-tree count already implies.
if [ "$MODE" = "incremental" ]; then
    ARCHIVED=$(tar -tf "$OUTFILE" | grep -vc '/$' || true)
    echo "[backup-uploads] $ARCHIVED new/changed file(s); $FILE_COUNT in the source tree"
else
    echo "[backup-uploads] $FILE_COUNT file(s) in the source tree"
fi

# Retention: a full invalidates every archive before it, so prune then
# and only then. Increments are kept -- they ARE the chain.
if [ "$MODE" = "full" ]; then
    CURRENT_NAME=$(basename "$OUTFILE")
    PRUNED=$(find "$BACKUP_DIR" -maxdepth 1 -type f \
        \( -name 'uploads_full_*.tar' -o -name 'uploads_inc_*.tar' \
           -o -name 'uploads_*.tar.gz' \) \
        ! -name "$CURRENT_NAME" -print -delete | wc -l)
    echo "[backup-uploads] full archive — pruned $PRUNED superseded archive(s)"
else
    echo "[backup-uploads] incremental — chain retained; next full on day $FULL_DOW"
fi

echo "[backup-uploads] current archives:"
ls -lh "$BACKUP_DIR" | grep -E 'uploads_' || true
