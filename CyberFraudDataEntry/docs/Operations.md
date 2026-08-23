# Operations Guide — Cyber Fraud Data Entry

## Service Overview

| Service | Port | Managed By | Auto-Start |
|---------|------|-----------|------------|
| MySQL | 3306 (localhost) | systemd | Yes |
| Gunicorn (Backend) | 8000 (localhost) | systemd | Yes |
| Nginx (Reverse Proxy) | 80/443 | systemd | Yes |
| `cyberfraud-nightly` | — | systemd timer, 23:00 IST | Yes (oneshot) |

`cyberfraud-nightly` is the only scheduled job: it runs the upload
analysis and then the backup, in that order. `cyberfraud-backup.timer`
and `cyberfraud-analysis.timer` are retired — if `list-timers` shows
either of them enabled, something re-installed an old unit.

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

## Standing Up an Environment, and Keeping It Current

Two scripts, two jobs. Which one you run depends only on whether the
machine already exists.

| | script | when |
|---|---|---|
| **Green-field** | `deploy/bootstrap.sh` | **once** per machine — a bare Ubuntu box, one in an unknown state, or a disaster recovery |
| **Everything after** | `deploy/update.sh` | every deploy, on every environment, forever |

Production, the DGX Spark and the laptop are the same machine once their
green-field build is done. There is no separate "DGX procedure": past the
first run they are all maintained with `update.sh`.

### 1. Green-field build (once per machine)

```bash
sudo git clone https://github.com/rajibdassharma/SCRBChatBot.git /opt/scrb
cd /opt/scrb/CyberFraudDataEntry

# Put the dumps where the script looks:
sudo mkdir -p /opt/cyberfraud/backups
sudo cp dbdump_*.sql.gz filedump_*.tar.gz /opt/cyberfraud/backups/

sudo bash deploy/bootstrap.sh --reset --db-password '<see table below>' \
     --restore-latest --no-nightly
```

Type `RESET` when it asks. It installs apt packages, MySQL with the right
collation, Node, both venvs, the schema, the data, the frontend build, the
TLS cert, systemd and nginx — then verifies every required table **by
name** and exits non-zero if any is missing.

**The MySQL password is the only thing that differs between
environments:**

| machine | password |
|---|---|
| Laptop | `Sandy@411` |
| DGX Spark | `Sandy@411` |
| Production | `CyberFraud@KSP2026` |

Laptop and DGX share one — both are personal machines outside KSWAN.
Production keeps its own, so a compromise of a personal machine does not
carry the production credential with it.

**Flag notes, each of which cost something to learn:**

- `--reset` purges MySQL and deletes `/var/lib/mysql` — **every** database
  on the box. It belongs in the green-field command and nowhere else. The
  script refuses it without a restore flag, because `--reset` on its own
  completes "successfully" with an empty database.
- `--no-nightly` on any machine that is a RESTORED COPY rather than the
  system of record — the DGX and the laptop. The 23:00 chain runs
  `analysis.daily`, which is destructive against a restored database: the
  dump carries `upload_ledger` marked fully parsed but not
  `statement_transactions`, so `build_links` deletes `mule_account_link`
  and rebuilds it from nothing. Production IS the system of record and
  keeps its timer.
- `--db-password` is required only when MySQL is new. Afterwards it is
  read from `backend/.env`.

### 2. Every deploy after that — `update.sh`, everywhere

```bash
cd /opt/scrb && sudo git pull && sudo bash CyberFraudDataEntry/deploy/update.sh
```

The same command on production and on the DGX. `update.sh` installs pip
dependencies, runs migrations 001 → 004, 006 → 026, builds the frontend,
syncs into `/opt/cyberfraud`, restarts the backend, and self-verifies each
schema change. It never installs the nightly timer, so running it on the
DGX cannot resurrect the chain that `--no-nightly` suppressed.

**Do not use `bootstrap.sh` for routine deploys.** It can purge MySQL —
the right capability for building a machine, the wrong one for updating
it.

### Refreshing the DGX from production

Drop a newer dump in and re-run the restore path. This is the one time
`bootstrap.sh` is right on an existing machine, because it is the only
script that restores data:

```bash
sudo cp dbdump_*.sql.gz /opt/cyberfraud/backups/
sudo bash /opt/scrb/CyberFraudDataEntry/deploy/bootstrap.sh \
     --restore-latest --no-nightly
```

No `--reset`, no `--db-password`.

### After a restore you do NOT need to run the analysis

Every analysis RESULT is in the dump — `account_statement_summary`,
`mule_account_link`, `crypto_txn`, `id_photo_hashes`, `ifsc_branch`,
`upload_ledger`. Only `statement_transactions` is excluded; it is 27 GB of
raw parsed rows and **no API route reads it**. All ten analysis tabs work
off the restore.

Running `analysis.daily` on a restored machine is actively harmful, which
is why it refuses to start when the ledger is populated and the fact table
is empty. You would want the fact table only if THIS machine were going to
parse new uploads — and that means truncating `upload_ledger` and
reparsing ~30k files from scratch.

### The password rule

**One password per machine, reconciled on every run.** It lives in
`backend/.env` under the key **`CFDSR_DB_PASSWORD`** — `config.py` sets
`env_prefix = "CFDSR_"`, so an unprefixed `DB_PASSWORD=` is ignored
entirely and pydantic then refuses to construct `Settings` at all.

Every auth check is made **over TCP** (`--protocol=TCP -h 127.0.0.1`),
because that is how the application connects. `mysql -uroot` over the unix
socket as OS root succeeds with *any* password when root is on the
`auth_socket` plugin — so a socket-based check reports success while the
app cannot connect at all. A check that does not use the same path as the
thing it checks is not a check.

Never read `.env` with `set -a; . .env`: sourcing runs it through the
shell, so a value containing `#` is truncated and one containing `&`
forks. Use `grep -m1 '^KEY=' file | cut -d= -f2-`. Never rewrite it with
`sed -i` either — that reassigns the file's owner to whoever ran it, and a
root-owned `600 .env` stops the service with a config error that looks
nothing like a permissions problem.

### Restoring a dump by hand

```bash
gunzip -c /opt/cyberfraud/backups/dbdump_<date>.sql.gz \
  | MYSQL_PWD='<password>' mysql --protocol=TCP -h 127.0.0.1 -uroot cyber_fraud_dsr
```

`sudo` on `gunzip` if it is needed to read the file, **never on `mysql`** —
`sudo` resets the environment, `MYSQL_PWD` never arrives, and the result
is `Access denied for user root@localhost`. Equally, `sudo mysql` with no
password works only while root is still on `auth_socket`; once a password
is set it stops working, which is why the same command can succeed one
hour and fail the next.

### Things bootstrap.sh deliberately refuses to do

- **Regenerate `JWT_SECRET`.** Written once. Regenerating it logs out
  every user.
- **Invent a password.** `--db-password` is required when MySQL is new. An
  earlier version generated a random one — the right default for an
  unattended server, the wrong one for a recovery, where it hands you a
  secret you then have to go and find.
- **`--reset` with nothing to restore.** That completes successfully with
  an empty database, because an empty database is a valid outcome of a
  reset. Pass `--empty-ok` if it is genuinely what you want.
- **Restore uploads from an increment alone.** It requires a
  `uploads_full_<ts>.tar` and applies only increments newer than it, **by
  timestamp** — `full` sorts before `inc`, so filename order would treat
  every increment as newer than every full, including ones from a previous
  chain.

### The check that matters most

`seed.py` builds `units` and `police_stations` from
`All District CEN_PS.xlsx` — 44 stations across 36 districts — and falls
back to `AllDistrictPS.xlsx` if it is missing. The fallback is **1,085
stations across 40 districts**: every police station in Karnataka, not the
Cyber Crime ones, seeded with two users each. The failure looks like a
successful run that produced 2,170 accounts.

That roster was gitignored until 2026-08-22, meaning a recovery from a
fresh clone would have hit the fallback silently. It travels with the code
now — 44 rows of district and station name, all public, reference data
rather than case data. The two backup dumps stay out of git permanently;
that is what `dbdump*` / `filedump*` in `.gitignore` is for.

`bootstrap.sh` asserts `police_stations` lands between 40 and 60, and
separately checks **every required table by name** rather than counting
them. A count was the original check and it was worthless: `>= 36` passes
for 36 wrong tables, and 35 is in fact the correct number for a restored
copy, since `statement_transactions` and `chat_messages` are legitimately
absent. The expected set is derived from `Base.metadata` so it cannot
drift as models are added.

A recovery is the worst possible moment to be reading row counts by eye.

---

## Deploying Updates

**One command. Do not run the individual steps by hand.**

```bash
cd /opt/scrb && git pull && sudo bash CyberFraudDataEntry/deploy/update.sh
```

The leading `git pull` picks up the latest `update.sh` itself; the
script then re-pulls internally to be safe. Idempotent end-to-end
(safe to re-run). Aborts on the first failure — `set -euo pipefail`.

### What update.sh does

| # | Step | Notes |
|---|---|---|
| 1 | `git pull` on `/opt/scrb` | Fetches the latest source. Prints the new HEAD. |
| 2 | `pip install -r requirements.txt` | Upgrades Python deps under `cyberfraud` user's venv. Catches new packages added since last deploy. |
| 3 | Run additive DB migrations 001 → 004, 006 → 026 | Copies `migrations/` into runtime, runs each in order under the app's venv. Every migration is idempotent (INFORMATION_SCHEMA guards); no-op if already applied. **005 is deliberately skipped** (chat feature not enabled in prod). |
| 4 | `npm install && npm run build` (frontend) | Runs `tsc -b && vite build` — TS strict must pass or the deploy aborts here. |
| 5 | Sync backend + `frontend/dist/` into runtime | `sudo cp -r … /opt/cyberfraud/`, then chown to `cyberfraud:cyberfraud`. |
| 6 | Restart `cyberfraud-backend.service` | `systemctl restart` + 2 s sleep + `is-active` check. |
| 7 | Ensure nginx proxies `/uploads/*` to the backend | Auto-inserts the `location /uploads/` block into `/etc/nginx/sites-enabled/*cyberfraud*` if missing. Backs up the site config first; runs `nginx -t` before reloading; rolls back on failure. Idempotent — a re-run notices the block is already there and does nothing. |
| 8 | Self-verify | Runs a large panel of checks: `/health` responds, every new API route returns 401/403 (proof it's mounted), every migration's target schema landed (INFORMATION_SCHEMA queries). Any single failed check aborts the deploy. |

**No pre-migration backup step** — removed 2026-07-24 after too much
friction on routine deploys. The nightly systemd timer covers it (see
"Database Backup" below); run `backup-db.sh` / `backup-uploads.sh` by
hand before a risky deploy if you want the extra insurance snapshot.

### After a deploy

- Refresh the browser (Ctrl+F5) once, so stale JS from the previous
  build isn't cached.
- If the deploy shows all ✓ marks and "Incremental update complete,"
  everything's in. If it aborts mid-way, the last successful step is
  the state you're in — re-run after fixing the issue.

---

## Database Backup

Nightly automated backups via **systemd timer** — no cron, and since
2026-08-17 the backup is the SECOND half of one nightly chain rather
than a timer of its own (see
[Upload Analysis](#upload-analysis-f1--f2)).

- **`deploy/backup-db.sh`** — `mysqldump --single-transaction` of
  `cyber_fraud_dsr`, gzipped, timestamped, into a backup dir.
  **Retention: keeps only the newest snapshot** (name-exclusion prune,
  deterministic — no `-mtime` guesswork).

  **Excludes exactly one table: `statement_transactions`.** It is
  26.5 M rows / 27.6 GB and is a pure function of the PDFs under
  `backend/uploads/` — including it would make the dump roughly 600×
  larger for something `analysis.daily` can rebuild.

  It excluded *five* analysis tables until 2026-08-17. That was wrong
  once the analysis moved to the server: the summaries, photo hashes,
  mule links and crypto rows are now GENERATED on production, so the
  dump was the only copy that could have existed and it was skipping
  them. `ifsc_branch` is worse than derived — it is master data from
  outside, and the server has no route to the internet to re-fetch it.
  **The test for excluding a table is not "is it big" but "can this
  machine rebuild it".**

- **`deploy/backup-uploads.sh`** — `backend/uploads/`, as a **weekly
  full plus nightly incrementals** (`tar --listed-incremental`),
  uncompressed. A nightly full re-archived 19.5 GB to capture ~500 MB
  of new files; gzip returned 9% on a tree of already-compressed PDFs
  and JPEGs for 24 minutes of CPU. **A restore needs the full and every
  increment after it, applied in order** — an increment alone is not a
  backup.

Both are invoked by `backup-all.sh`, which `nightly-all.sh` runs after
the analysis. Installed once via `deploy/install-nightly.sh`, which
also disables the retired `cyberfraud-backup.timer` and
`cyberfraud-analysis.timer`.

### Check the timer is running

```bash
sudo systemctl status cyberfraud-nightly.timer
sudo systemctl list-timers cyberfraud-nightly.timer

# Last night's result -- both exit codes are printed by nightly-all.sh
sudo journalctl -u cyberfraud-nightly.service --since yesterday --no-pager | tail -30
```

### Run a backup by hand (before a risky deploy)

```bash
sudo -u cyberfraud /opt/cyberfraud/deploy/backup-db.sh
sudo -u cyberfraud /opt/cyberfraud/deploy/backup-uploads.sh
# or both at once:
sudo -u cyberfraud /opt/cyberfraud/deploy/backup-all.sh
```

### Restore from a backup

```bash
# Newest DB snapshot (whatever the retention left)
LATEST=$(ls -1t /opt/cyberfraud/backups/*.sql.gz | head -1)
gunzip -c "$LATEST" | mysql -u root -p"$CFDSR_DB_PASSWORD" cyber_fraud_dsr

# Newest uploads snapshot
LATEST_UPLOADS=$(ls -1t /opt/cyberfraud/backups/uploads-*.tar.gz | head -1)
sudo tar -xzf "$LATEST_UPLOADS" -C /opt/cyberfraud/backend/
sudo chown -R cyberfraud:cyberfraud /opt/cyberfraud/backend/uploads
```

Adjust paths if your install put the backup dir somewhere else — check
`backup-db.sh` for the exact `BACKUP_DIR` it uses.

---

## Upload Analysis (F1 / F2)

Derives findings from the files officers upload: duplicate ID photos
(F1), parsed bank statements (F2), and the mule-to-mule transfer network
(F4). Nothing here is entered by hand — it is all computed from
`backend/uploads/`.

### The rule that governs everything below

**These tables are DERIVED**: every row is a pure function of the files
under `backend/uploads/`, and `analysis.daily` can rebuild any of them
from scratch. That property is what licenses everything else in this
section — the incremental parse, the exclusion from the dump, the
willingness to drop and rebuild after a parser change.

| table | rows (2026-08-22) | what it holds |
|---|---|---|
| `upload_ledger` | 33 k | one row per processed file; drives incremental runs |
| `statement_transactions` | 26.5 M / 27.6 GB | parsed transaction lines. The fact table |
| `account_statement_summary` | 108 k | per (account, channel) rollup the dashboards read |
| `id_photo_hashes` | 21 k | SHA-256 + perceptual hash per ID photo |
| `mule_account_link` | 2.4 k | direct mule → mule transfers |
| `crypto_txn` | 984 | statement rows naming a crypto exchange or asset |
| `ifsc_branch` | 183 k | IFSC → bank / branch / district / state |

"Derived" is not the same as "disposable", and the distinction decides
what gets backed up. Only `statement_transactions` is excluded from the
dump — the rest are small, and two of them are not really rebuildable in
practice: `ifsc_branch` is master data from outside and the server has
no route to the internet to re-fetch it. See
[Database Backup](#database-backup).

### Where the analysis runs — the SERVER, since 2026-08-17

Production parses everything now. It runs nightly, unattended, in
`cyberfraud-nightly.service`. The laptop analyses nothing; it restores
what the server produced.

This reverses the original design, and the reasons it reversed are
worth keeping:

- **The storage argument expired.** The old plan assumed a 50 GB disk
  that a 12.5 GB fact table would not fit alongside a 15 GB uploads
  tree. The server has 300 GB and 16 GB of RAM
- **The hand-off was the actual cost.** Analysing on the laptop meant
  exporting, copying, and importing every night, and every step was a
  chance for the two machines to disagree about what had been processed
- **The ledger and the fact table must stay together.** Shipping
  `upload_ledger` without `statement_transactions` produces a machine
  that SKIPS every file the ledger calls settled while its summaries
  describe rows that do not exist. This happened on 2026-08-18 and cost
  a 25 GB re-seed. If you ever move the analysis again, move both or
  neither

The dependency-isolation argument still holds, and it now matters more
rather than less. `pdfplumber` 0.11.10+ requires `Pillow>=12.2`, and
Pillow is what **reportlab** renders every operator-facing PDF with.
The server installs `requirements-analysis.txt` into the SAME venv as
the web app, so the two are no longer separated by machine — they are
separated only by the pins in that file (`pdfplumber==0.11.4`,
`pillow>=10,<12`). **Do not relax those pins without rendering a case
file and a mule report and looking at the output.**
`install-nightly.sh` imports both packages after installing and prints
their versions for this reason.

`cyberfraud-analysis.{service,timer}` and `install-analysis.sh` in
`deploy/` are the superseded standalone-analysis units. Retired
2026-08-17; kept only because they document the intermediate step.

### Daily cycle — the whole procedure

**The analysis runs on the SERVER, nightly and unattended.** There is
nothing to do on a data-only day. What follows is what happens by
itself, and what you do only when you have code to ship.

#### What the server does at 23:00 IST, by itself

`cyberfraud-nightly.timer` fires `nightly-all.sh`, which runs two things
in sequence:

1. **`analysis.daily --skip-relink`** — migrations, parse new statements,
   hash new ID photos, rebuild mule links, find crypto, verify the
   summary cache.
2. **`backup-all.sh`** — `mysqldump` then the uploads tarball.

**The order is the whole point.** These used to be two timers an hour
apart — backup at 00:00, analysis at 01:00 — which orders them by clock
rather than by dependency. Every backup therefore carried the PREVIOUS
day's analysis, and on a heavy upload day the analysis could still be
running when the next backup started. Nothing errored; the dates just
quietly lied. One unit running both in sequence is what makes "the
backup contains today's analysis" true rather than usually true.

**The backup runs even if the analysis fails.** A backup of slightly
stale derived data is worth far more than no backup, and every case,
account and DSR entry an operator touched today has nothing to do with
the analysis. The failure is recorded and the unit still exits non-zero;
what it does not do is skip the backup as a punishment.

Check on it:

```bash
systemctl list-timers | grep cyberfraud
journalctl -u cyberfraud-nightly.service -n 100
journalctl -u cyberfraud-nightly.service --since "yesterday 23:00"
```

Run it early, by hand, any time:

```bash
sudo systemctl start cyberfraud-nightly.service
```

#### What YOU do

**On a data-only day: nothing.** The dashboards are current by morning.

**On a code day:**

**1. Develop** on the laptop.

**2. Push — ONCE.** One commit, one push, per deploy. A second push
means a second pull, and on this setup a pull is never just a pull: it
drags a full `update.sh`, a backend restart (~10 s of 502s for ~90
operators) and a repo visibility flip. Walk the whole change set — file
modes, files scripts reference, migrations registered in `update.sh`,
docs — before the first push.

**3. Deploy on production.**

```bash
cd /opt/scrb && sudo git pull && sudo bash CyberFraudDataEntry/deploy/update.sh
```

The repo is private and the server stores no credentials, so flip
`rajibdassharma/SCRBChatBot` to public on GitHub first and back to
private after.

**4. If the change touched `deploy/` timers or `requirements-analysis.txt`:**

```bash
sudo bash /opt/scrb/CyberFraudDataEntry/deploy/install-nightly.sh
```

Idempotent, and it re-checks that the two superseded timers are still
disabled.

#### Refreshing the dev laptop

The laptop no longer analyses anything. It restores what the server
produced, which arrives complete because the nightly dump now carries
the summaries.

```powershell
mysql -u root -p cyber_fraud_dsr < cyber_fraud_dsr_<date>.sql
```

**Uploads are a full plus a chain of increments** since 2026-08-21. A
nightly full re-archived 19.5 GB to capture ~500 MB of new files, and
gzip was saving 9% on already-compressed PDFs and JPEGs for 24 minutes
of CPU. Now: a full every Sunday, plain `tar`, increments the rest of
the week.

Restore is the full, then EVERY increment after it, in order:

```bash
cd /opt/cyberfraud/backend      # on the laptop: the backend folder
tar -xf uploads_full_<ts>.tar
for f in $(ls uploads_inc_*.tar | sort); do tar -xf "$f"; done
```

Sorting matters — the increments must be applied oldest first. Losing
one loses only the files first seen in it, because uploads are
append-only, which is why a weekly full is enough: the chain is never
longer than seven links.

Force a full at any time with `backup-uploads.sh --full`; it prunes
every archive it supersedes.

**`relink` is usually NOT needed any more.** It existed because the
laptop's `upload_ledger` referenced accounts that the restore replaced
underneath it. The ledger now travels IN the dump alongside
`all_accounts`, so the two arrive already consistent. Run
`python -m analysis.relink` only if account links look wrong.

When it is needed, expect **10+ minutes**
on the current corpus, not the ~2 s this document used to claim: it
joins the ledger to `all_accounts` on a `SUBSTRING_INDEX` of the file
path, and because that expression sits on both sides of the join no
index can serve it — 42,000 ledger rows against 24,000 accounts as a
nested loop. It is the reason `--skip-relink` is passed on the server,
where nothing has moved and the pass is pure cost.

You need the uploads on the laptop regardless of analysis: the ID-photo
and statement hyperlinks on the dashboards serve files from disk. Two
files come off the server and both are required —
`cyber_fraud_dsr_<date>.sql.gz` (~60 MB, analysis results inside) and
`uploads_<date>.tar.gz` (17 GB, the raw photos and statements).

**Do NOT run `analysis.daily` or `summary --check` on the laptop.**
`statement_transactions` is excluded from the dump, so the laptop keeps
its own copy while the summaries now come from the server's. The check
compares those two and reports mismatches that are not faults — just
two fact tables describing the same PDFs.

#### What is in the nightly dump, and what is not

Changed when the analysis moved onto the server. It used to exclude all
six derived tables because the laptop produced them and shipped them
across, so production held a re-importable copy. Production now
GENERATES them, so the summaries are the only copy that exists.

| table | in the dump? | why |
|---|---|---|
| `statement_transactions` | **no** | 24.8 GB / 21.7M rows, and a pure function of the PDFs `backup-uploads.sh` already captures |
| `account_statement_summary`, `upload_ledger`, `id_photo_hashes`, `mule_account_link`, `crypto_txn` | yes | ~100 MB together; cheap to carry, hours to rebuild, and the dashboards read nothing else |
| `ifsc_branch` | yes | master data from outside; this server has no route to the internet to re-fetch it |

`update.sh` asserts both halves of that — `statement_transactions`
excluded, everything else not — by reading the array in `backup-db.sh`
rather than grepping the file, because those names all appear in its
comments now.

#### Superseded: the laptop-analysis cycle

`export_for_prod.py` and `import-analysis.sh` are **no longer part of
the daily routine**. They are kept for one case: rebuilding production's
derived tables from the laptop after a corruption, when re-parsing on
the server would take longer than shipping a copy.

### Historical: why the import could not disturb the running app

> Retired 2026-08-17. Production computes its own analysis now, so
> nothing is imported nightly. `import-analysis.sh` remains for
> restoring an old export, and the pattern below is worth keeping —
> it is how to replace a table's contents under live readers.

`import-analysis.sh` loads into **staging** tables first, then does one
transaction per table: `DELETE` + `INSERT…SELECT`. InnoDB's MVCC means
concurrent readers keep seeing the old rows until `COMMIT`, so no
dashboard can ever observe a half-loaded table. The naive
`TRUNCATE` + `INSERT` would show every officer an empty Money Trail for
the duration — an answer, not an error, which is worse.

The `SELECT` **LEFT JOINs** `all_accounts` and keeps NULL `account_id`
rows. That detail matters: 15,917 of `upload_ledger`'s 34,006 rows have
no resolved account, and Statement Coverage counts them with no join at
all. An inner join silently discarded 47% of that denominator and made
coverage look better than it was — caught by rehearsing the import
against a scratch database before it ever touched production.

### Dev laptop — after the restore

The nightly chain finishes well after 23:00, so a restore taken the
next morning is up to a day behind production. Statement Coverage
shows that honestly as "not yet parsed".

**The laptop no longer analyses anything as a matter of routine.** The
server does the parsing and the dump carries the results, so a restore
is usually complete on arrival. Run `analysis.daily` on the laptop only
when you are testing a parser change against real files — and remember
the dump does NOT contain `statement_transactions`, so the laptop's
fact table is whatever it parsed locally.

```bash
# 1. restore the dump and extract the uploads archives.
#    Uploads are a WEEKLY FULL + nightly increments -- extract the full
#    first, then every increment after it, IN ORDER. An increment on
#    its own is not a restore.
# 2. only if you are testing a parser change:
cd CyberFraudDataEntry/backend
python -m analysis.daily
```

`analysis.daily` runs, stopping at the first failure:

1. migrations 019–026 — idempotent, no-ops once applied
2. **relink** — repairs account links the restore broke (~2 s)
3. **parse_statements** — incremental, only files not in the ledger
4. **hash_id_photos** — incremental; photos already fingerprinted at
   the current version are loaded, not re-read. Near-duplicate
   clustering is banded (LSH), not all-pairs — the exact same output as
   brute force, with a self-test that proves it on random inputs
5. **build_links** — rebuilds the mule → mule network (~35 s). After
   parsing, never before: links are found by matching counterparty
   numbers in freshly parsed rows against known mule accounts, so
   running it first would miss everything new.
6. **build_crypto --recent 48** — finds statement rows naming a crypto
   exchange or asset. After parsing, for the same reason as build_links.
   `--recent`, not a full rebuild: a rebuild rescans all 26.5 M
   narrations.

   **`--recent` only ADDS rows.** After changing a pattern in
   `analysis/parsers/crypto.py`, run a full `python -m
   analysis.build_crypto` by hand — otherwise rows matched by the
   withdrawn rule stay on screen, indistinguishable from current ones.
7. **summary --check** — verifies the dashboard cache still matches its
   source rows; **exits non-zero on any mismatch**

### Why `relink` is needed on dev and not on production

`mysqldump` writes `FOREIGN_KEY_CHECKS=0`, and a restore **drops and
recreates** `all_accounts` rather than deleting from it — so the
`ON DELETE CASCADE` that normally keeps derived rows honest never fires
and MySQL never re-validates.

The case that actually hurts: an account deleted and re-entered upstream
gets a **new UUID** while pointing at the same uploaded file. The ledger
still lists that file as parsed so the parser skips it, and the
transactions still carry the old id — leaving the new account showing
"Not yet parsed" permanently. `relink` re-points the rows; it does not
re-parse, because the rows are fine and only the pointer is wrong.

### Money figures: only chain-verified rows are summed

Every statement carries its own arithmetic check —
`previous − debit + credit = balance` on each row. `chain_ok` records
the verdict **per row**:

| value | meaning | counted as money? |
|---|---|---|
| `1` | tested, and the arithmetic agreed | **yes** |
| `0` | tested, and it did not | no |
| `-1` | nothing to test against | no, reported separately |

This is not caution for its own sake. A file-level verdict was
previously used to vouch for the rows inside it, and a statement scoring
99.22% had 29 rows carrying ₹205,642,955,681 of a ₹205,648,905,136
total. Separately, an export with **no balance column** had its account
number read as the debit on all 16,493 rows — nothing could contradict
it, and the dashboard reported ₹6.68 quadrillion.

`-1` is a distinct answer from `1`, never a lenient version of it.
Rejected money is *wrong*; untested money is *unknown*, and the UI says
"₹X verified · ₹Y unverifiable" rather than hiding the second figure or
folding it into the first.

`chain_ok` is written **at parse time**, so new data is correct on
arrival and the nightly job stays one step.

### Rebuilding after a parser change

Bump `PARSER_VERSION` in `analysis/parse_statements.py`; the ledger then
treats every file as stale and the next run re-reads the corpus.

For fixes that only affect derived values, cheaper tools exist:

```bash
python -m analysis.stamp_chain      # re-derive chain_ok from stored rows
python -m analysis.summary          # rebuild the dashboard cache
python -m analysis.build_links      # rebuild the mule network (~35 s)
python -m analysis.build_crypto     # rebuild crypto_txn (~7 min, full)
python -m analysis.progress         # read-only; safe during a run
python -m analysis.progress --watch # same, refreshing with an ETA
python -m analysis.export_for_prod  # package results for the server
```

**Crypto detection is deliberately conservative.** `parsers/crypto.py`
carries 26 regression cases, most of them FALSE positives taken from
real narrations: `ASHOKX` read as OKX, a bank's joint-holder field read
as ETH, `Bankucoin` read as KuCoin, `krakenface@axl` read as Kraken.
Three-letter tickers are excluded entirely — three letters is not enough
signal in bank narration. Widening a pattern without adding its
counter-example to `_CASES` is how all four of those shipped.

Run `python -m analysis.parsers.crypto` to execute the self-test alone.

**`failed` is not a terminal state.** Every run retries files marked
`failed`, so a parser fix needs no bookkeeping — the next run picks them
up. Only `ok`, `scanned` and `unverified` are skipped. This is why a
missing dependency looks alarming but costs nothing: on 2026-08-07 a
misconfigured interpreter left 4,824 files failing with
`ModuleNotFoundError` (every PDF and `.xls` in the corpus), and simply
installing `requirements-analysis.txt` and re-running recovered them.

Parsing needs the extra dependencies:

```bash
pip install -r requirements.txt -r requirements-analysis.txt
```

`stamp_chain` resumes by default and skips files already stamped. On a
full re-stamp pass `--no-resume` is faster — the resume lookup scans the
whole fact table and costs more than it saves unless most of the work is
already done.

### Resource behaviour

Batch jobs budget workers from **free memory**, not core count, and hold
a reserve back for the OS and the shared-iGPU pool. That is not tuning:
an early version ran 20 workers chosen off core count and bugchecked the
dev laptop three times in twenty minutes (`0x0000010E`,
`VIDEO_MEMORY_MANAGEMENT_INTERNAL`).

Consequences worth knowing:

- **Free memory sets the pace.** On the dev laptop, 14 GB free gives 8
  workers; 10 GB free gives 1, and the same job goes from ~1.5 h to
  ~6.5 h. Closing a couple of applications is the cheapest speed-up
  available.
- `--workers` is an **upper bound only** — the budget can lower it and
  never raise it.
- Every run is **resumable**. Stop it any time; the ledger commits per
  batch, so at most the current batch is lost.
- **A stalled chunk gives up rather than hanging the run.** A worker that
  dies without resolving its future used to block `as_completed`
  forever: 2026-08-10 saw 13 minutes of 0% CPU, no I/O, zero worker
  children and no progress. Each chunk now carries a deadline
  (`CHUNK_TIMEOUT_PER_FILE_S`, 60 s/file, 600 s floor); on expiry the
  outstanding files are recorded as `failed` — so the next run retries
  them — and the pool is rebuilt.

Tunable via the environment when the defaults do not fit the machine:

| variable | default | when to change it |
|---|---|---|
| `CFDSR_ANALYSIS_RESERVE_GB` | 10.0 | **Server: 4.0.** 10 GB describes a 32 GB laptop whose Intel Arc iGPU draws video memory from system RAM. |
| `CFDSR_ANALYSIS_RESERVE_CORES` | 2 | **Server: 0.** Cores held back from the pool. The default protects a laptop somebody is using; the server has 2 vCPUs and no interactive user, so `cores − 2` came out at 0, clamped to ONE worker, and the parse ran serially at 12.5 s/file. `Nice=10` + `CPUSchedulingPolicy=batch` are what keep the web app ahead in the run queue — the right mechanism on a server. |
| `CFDSR_ANALYSIS_IDLE_TIMEOUT_S` | 300 | **Server: 1800.** How long `governed_map` waits with NOTHING completing before deciding the pool is dead. 300 s was fine where no file came close to it; on the server it fired 36 times in one night and abandoned 432 of 1,152 files. |
| `CFDSR_ANALYSIS_TIMEOUT` | 6h | Budget for the analysis inside `nightly-all.sh`, well under the unit's 10 h `TimeoutStartSec`. An overrun ends the analysis and still leaves time to back up. |
| `CFDSR_ANALYSIS_LOW_WATER_GB` | 0.6 × reserve | Derived on purpose. A low-water mark above the reserve makes the job wait for memory it was never going to be given. |

**Every one of these defaults was calibrated on the 32 GB laptop and
every one of them was wrong for the server.** The pattern is worth
remembering before adding another: a constant tuned on the machine you
develop on is a guess about the machine you deploy to. The server's
values live in `deploy/cyberfraud-nightly.service`, not in code.

### The systemd timers run the RUNTIME copy of deploy/

`cyberfraud-nightly.service` executes `/opt/cyberfraud/deploy/nightly-all.sh`
— the copy under the runtime, not the one in the git clone. Until
2026-08-12 `update.sh` synced `backend/` and `frontend/` but not
`deploy/`, so every fix to a backup script sat in `/opt/scrb` doing
nothing, and only `install-backup.sh` — run by hand, months apart —
ever refreshed them.

What that cost: `backup-db.sh` gained `--ignore-table` for the five
derived analysis tables, the server never received it, and once
`import-analysis.sh` began populating those tables on production the
nightly dump grew from **18 MB to 46 MB**. Nothing failed. The backups
simply carried data that existed to be rebuilt.

Then the same list became wrong in the opposite direction. Once the
analysis moved onto the server those five tables stopped being a
duplicate of the laptop's copy and became **the only copy**, so
excluding them meant a restore would come back with empty dashboards.

`update.sh` now syncs `deploy/` too, and step 8 asserts the exclusion
list in BOTH directions: `statement_transactions` must be excluded, and
the other six must NOT be. A one-directional check would have passed
happily through the second mistake. It reads the `DERIVED_TABLES` array
specifically rather than grepping the file, because every one of those
names also appears in that script's comments explaining why it is or is
not excluded — a file-wide grep would match the explanation and report
success whatever the array said.

**When editing anything under `deploy/`, the change reaches the server
only after `update.sh` runs.** A `git pull` alone updates the clone, not
what the timers execute.

### MySQL: the buffer pool is the real bottleneck

`innodb_buffer_pool_size` defaults to **128 MB**. `statement_transactions`
is **12.7 GB**. The pool can therefore cache ~1% of the table, so nearly
every read of it goes to disk — which is why the integrity check, the
mule-link rebuild and any full aggregate feel slow regardless of what
the Python does. Query-level tuning works around this; it does not fix
it.

```sql
SET GLOBAL innodb_buffer_pool_size = 4294967296;   -- 4 GB, takes effect live
```

Measured 2026-08-10: the scoped check went 91 s → 63 s on a still-cold
pool. **This resets when MySQL restarts** — put `innodb_buffer_pool_size=4G`
in `my.ini` (Windows) or `/etc/mysql/mysql.conf.d/mysqld.cnf` (server)
to keep it.

The production VM has 16 GB, not the 8 GB this document used to claim.
4 GB of buffer pool leaves roughly 3 GB for the OS and gunicorn and the
rest for the nightly workers. Raised live on 2026-08-19 —
`innodb_buffer_pool_size` is dynamic in MySQL 8, so it takes effect with
no restart and no dropped connections.

### Editing `backend/analysis/` while a run is in flight

**Don't.** On Windows every worker is spawned fresh and re-imports the
package, so a syntax error in any module under `analysis/` kills every
new worker immediately — the parent survives, the run dies, and the
console fills with `SyntaxError` from `multiprocessing.spawn`.

Verified this the hard way on 2026-08-10. If a change is urgent, stop
the run first; it is resumable and costs at most the current batch.

---

## Schema Snapshot (Structure Only, No Rows)

Sometimes you need the current DDL for an auditor / new dev / offline
reader who can't SSH into the DB. Use `deploy/dump-schema.sh` — it
runs `mysqldump --no-data` and drops a timestamped `.sql` file into
`proddata/`.

```bash
cd /opt/cyberfraud
./deploy/dump-schema.sh
# ⇒ proddata/schema-snapshot-YYYYMMDD.sql
```

Reads DB creds from `backend/.env`. NOT wired into `update.sh` (no
need to snapshot on every deploy). Regenerate on demand:

- Before / after a migration you want to compare
- For a VAPT / audit handoff
- For a new-dev handover pack

Commit the resulting file if you want to preserve it as a dated
artefact — otherwise it's a working file you can discard.

The canonical, always-current source of truth for the schema is the
SQLAlchemy models under `backend/models/*.py`, plus the tables
embedded in [database.md](./database.md#10-current-schema-reference).
The snapshot is for people / tools that can't read Python.

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
| Nightly chain script | `/opt/cyberfraud/deploy/nightly-all.sh` |
| Nightly unit + timer | `/etc/systemd/system/cyberfraud-nightly.{service,timer}` |
| Analysis package | `/opt/cyberfraud/backend/analysis/` |
| Analysis venv (shared with the app) | `/opt/cyberfraud/backend/venv/` |
| Uploaded files (the ONLY irreplaceable artefact) | `/opt/cyberfraud/backend/uploads/` |
