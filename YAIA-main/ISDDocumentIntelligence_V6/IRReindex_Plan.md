# IR Bulk Re-Index Plan — May 2026 Batch (~500 files)

**Scope:** Index ~500 new IR (Interrogation Report) DOCX/DOC/PDF files into the
local V6 instance on Windows, then mirror the resulting MySQL + ChromaDB state
onto the Ubuntu production server. Server's `ranking` table is preserved.

**Strategy:** Local indexing only (script-based, with resume support).
Server gets a full overwrite of everything *except* the `ranking` table.

**Estimated wall time:** 30–90 min for indexing + ~30 min for transfer/verify.

---

# ════════════════════════════════════════════════════════════
#  PART 1 — LOCAL (Windows machine)
# ════════════════════════════════════════════════════════════

## Phase 1A — Pre-flight (local, ~10 min)

1. Backend running locally on port 8003.

2. **Recommended for speed:** in `backend/.env`, set:
   ```
   USE_OLLAMA_EMBEDDINGS=false
   ```
   This routes embedding through sentence-transformers on the GPU (batch
   256), 4–10× faster than the Ollama HTTP path. **Restart the local
   backend** after the change so it picks up the new env value.

   **Note on `USE_LLM_PARSER_IR`:** ignore this flag — the bulk IR path
   always uses `ir_parser.py` (pure Python), no LLM, regardless of
   the flag.

   Verify CUDA is wired up before starting:
   ```powershell
   python -c "import torch; print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE')"
   ```
   Must print `CUDA: True` and your RTX 4090 name.

3. Ollama is needed only if you leave `USE_OLLAMA_EMBEDDINGS=true`.
   With `false` it isn't needed for indexing (still needed later for
   Q&A on the frontend).

4. Disk space on local: room for backup folder + index growth + transfer
   folder.

5. 500 IR files staged in one folder, e.g. `C:/IR_Files_Batch2026May/`.
   **Subfolders are fine** — the script recurses (`rglob`). Files
   literally named `report` / `reports` / `feedback` / `attachment` /
   `attachments` are auto-skipped.

6. Backup + transfer folders exist:
   ```powershell
   New-Item -ItemType Directory -Force C:/Backups/V6
   New-Item -ItemType Directory -Force C:/Transfer/V6
   ```

7. Note baseline counts (write them down):
   ```sql
   -- Local MySQL
   SELECT COUNT(DISTINCT doc_id) AS ir_docs, COUNT(*) AS ir_field_rows FROM ir_reports;
   ```

---

## Phase 1B — Backup local state (~10–20 min)

Fall-back point if local indexing produces bad data.

```powershell
# 1. Local MySQL — full dump
mysqldump -u root -pSandy@411 --single-transaction --routines ISDIntelligence > C:/Backups/V6/local_pre_index_ISDIntelligence.sql

# 2. Local ChromaDB folders
Copy-Item -Recurse c:/VSCProjects/SCRBChatBot/YAIA-main/ISDDocumentIntelligence_V6/backend/chroma_db_ir_v6 C:/Backups/V6/local_pre_index_chroma_ir_v6
Copy-Item -Recurse c:/VSCProjects/SCRBChatBot/YAIA-main/ISDDocumentIntelligence_V6/backend/chroma_db_smac_v6 C:/Backups/V6/local_pre_index_chroma_smac_v6

# 3. Bulk-indexing progress DB (only if it exists from a prior run)
Copy-Item c:/VSCProjects/SCRBChatBot/YAIA-main/ISDDocumentIntelligence_V6/dbscripts/.ir_bulk_progress.db C:/Backups/V6/local_pre_index_ir_progress.db
```

---

## Phase 1C — Local indexing (~30–90 min)

Use the script — resumable, logged, dedup-aware. NOT the UI for 500 files.

```powershell
cd c:/VSCProjects/SCRBChatBot/YAIA-main/ISDDocumentIntelligence_V6/dbscripts

# 1. Dry run — confirms recursive file discovery before doing real work
python bulk_index_ir.py --folder "C:/IR_Files_Batch2026May" --dry-run
```

Check that the dry-run total matches your expected ~500. If it's much
lower, the SKIP_NAMES filter or some other issue is excluding files —
investigate before proceeding.

```powershell
# 2. Real indexing
python bulk_index_ir.py --folder "C:/IR_Files_Batch2026May" --username admin --password <PWD>
```

**During the run:** the script prints `OK`/`FAIL` per file and writes to
`logfiles/bulk_index_ir.log`. If anything fails (network blip, OOM, etc.),
just re-run the same command — it skips already-done files via the SQLite
progress DB.

**Watch the backend stdout for the embedding mode confirmation** on the first
indexed file:
```
[Embed] sentence-transformers loaded on cuda      ← good (GPU mode)
[Embed] sentence-transformers loaded on cpu       ← falling back to CPU, slow
```
If `cpu`, stop and re-check Phase 1A step 2.

---

## Phase 1D — Local verification (~5 min)

```sql
-- New counts should be roughly old + 500 docs (less any filtered)
SELECT COUNT(DISTINCT doc_id) AS ir_docs, COUNT(*) AS ir_field_rows FROM ir_reports;
```

Spot-check 1–2 new files via the frontend Q&A — confirm answers come back.

If indexing went wrong: **restore local from Phase 1B and STOP** (do not
proceed to server). See Rollback section.

**Note:** the bulk script does not pass `case_id`, so all 500 new IR docs
go to the global `IR_db` ChromaDB collection and `ir_reports.case_id`
will be NULL. This matches the existing data layout — no behavioral change.

---

## Phase 1E — Prepare transfer artifacts (~5 min)

Local Windows → USB.

```powershell
# 1. Dump local MySQL EXCLUDING the ranking table (server's ranking stays as-is)
mysqldump -u root -pSandy@411 --single-transaction --routines --ignore-table=ISDIntelligence.ranking ISDIntelligence > C:/Transfer/V6/post_index_ISDIntelligence_no_ranking.sql

# 2. Copy the IR ChromaDB folder to transfer area
Copy-Item -Recurse c:/VSCProjects/SCRBChatBot/YAIA-main/ISDDocumentIntelligence_V6/backend/chroma_db_ir_v6 C:/Transfer/V6/chroma_db_ir_v6
```

(Skip SMAC ChromaDB unless you also indexed SMAC files in this batch.)

Then copy `C:/Transfer/V6/` to USB stick. ✅ All Windows work done.

---

# ════════════════════════════════════════════════════════════
#  PART 2 — SERVER (Ubuntu, via RDP/SSH)
# ════════════════════════════════════════════════════════════

## Phase 2A — Plug in USB and pre-flight (~5 min)

1. Mount USB and copy artifacts to `/opt/transfer/v6/`.
2. Confirm artifacts arrived:
   ```bash
   ls -lh /opt/transfer/v6/
   # Expect: post_index_ISDIntelligence_no_ranking.sql + chroma_db_ir_v6/
   ```
3. Backup folder exists:
   ```bash
   sudo mkdir -p /opt/backups/v6
   ```
4. Note baseline server counts (compare to Phase 2D later):
   ```bash
   mysql -u root -pisdadmin ISDIntelligence -e "SELECT COUNT(*) FROM ir_reports; SELECT COUNT(*) FROM ranking;"
   ```

---

## Phase 2B — Backup server state (~10–20 min)

Fall-back point if the apply step goes wrong. **Two backups** for defense
in depth.

```bash
# 1. Server MySQL — full dump (includes ranking)
sudo mysqldump -u root -pisdadmin --single-transaction --routines ISDIntelligence > /opt/backups/v6/server_pre_deploy_ISDIntelligence.sql

# 2. Server MySQL — ranking table only (safety net)
sudo mysqldump -u root -pisdadmin ISDIntelligence ranking > /opt/backups/v6/server_pre_deploy_ranking_table_only.sql

# 3. Server ChromaDB folders
sudo cp -r /opt/isd/ISDDocumentIntelligence_V6/backend/chroma_db_ir_v6 /opt/backups/v6/server_pre_deploy_chroma_ir_v6
sudo cp -r /opt/isd/ISDDocumentIntelligence_V6/backend/chroma_db_smac_v6 /opt/backups/v6/server_pre_deploy_chroma_smac_v6
```

Verify backups exist with non-zero size:
```bash
ls -lh /opt/backups/v6/
```

---

## Phase 2C — Apply on server (~10–20 min)

The server runs `isd-backend` as a systemd service under user `isd`, NOT
root. So we use `systemctl` to stop/start, and `chown` after every copy
so the `isd` user can read/write the new ChromaDB files.

```bash
# 1. Stop the backend service (frontend service can stay up)
sudo systemctl stop isd-backend

# 2. Restore MySQL — drops & recreates all tables in the dump (ranking
#    is excluded, stays intact)
sudo mysql -u root -pisdadmin ISDIntelligence < /opt/transfer/v6/post_index_ISDIntelligence_no_ranking.sql

# 3. Replace ChromaDB IR folder
sudo rm -rf /opt/isd/ISDDocumentIntelligence_V6/backend/chroma_db_ir_v6
sudo cp -r /opt/transfer/v6/chroma_db_ir_v6 /opt/isd/ISDDocumentIntelligence_V6/backend/

# 4. CRITICAL — chown so the isd-backend service user can access the files
sudo chown -R isd:isd /opt/isd/ISDDocumentIntelligence_V6/backend/chroma_db_ir_v6

# 5. Verify ranking table is intact (count must match Phase 2A baseline)
mysql -u root -pisdadmin ISDIntelligence -e "SELECT COUNT(*) FROM ranking;"

# 6. Start the backend service
sudo systemctl start isd-backend
sudo systemctl status isd-backend --no-pager | head -10
```

---

## Phase 2D — Server validation (~5 min)

1. Backend health (give it 5–10s after start):
   ```bash
   curl -s http://localhost:8003/health
   ```
2. New IR doc count via MySQL (most reliable):
   ```bash
   mysql -u root -pisdadmin ISDIntelligence -e "SELECT COUNT(DISTINCT doc_id) AS ir_docs, COUNT(*) AS ir_field_rows FROM ir_reports;"
   ```
   Should match Phase 1D post-index counts.
3. Watch live logs while running test queries:
   ```bash
   sudo tail -f /var/log/isd/backend.log
   ```
4. **Q&A on a new doc**: pick a name from the May 2026 batch, ask a
   question via the frontend, confirm an answer comes back.
5. **Q&A on an old doc**: pick a name from the previous batch, confirm
   it still works (ensures we didn't lose old data).
6. Ranking table count = Phase 2A baseline.

If all 6 pass: **deploy is complete**. Inform the analyst.

---

# ════════════════════════════════════════════════════════════
#  ROLLBACK PROCEDURES (use only if needed)
# ════════════════════════════════════════════════════════════

### If local indexing produced bad data (during/after Phase 1C, before USB transfer)
```powershell
mysql -u root -pSandy@411 ISDIntelligence < C:/Backups/V6/local_pre_index_ISDIntelligence.sql
Remove-Item -Recurse -Force c:/VSCProjects/SCRBChatBot/YAIA-main/ISDDocumentIntelligence_V6/backend/chroma_db_ir_v6
Copy-Item -Recurse C:/Backups/V6/local_pre_index_chroma_ir_v6 c:/VSCProjects/SCRBChatBot/YAIA-main/ISDDocumentIntelligence_V6/backend/chroma_db_ir_v6
```

### If server deploy went wrong (during/after Phase 2C)
```bash
# 1. Stop backend
sudo systemctl stop isd-backend

# 2. Restore MySQL from full server backup (includes ranking)
sudo mysql -u root -pisdadmin ISDIntelligence < /opt/backups/v6/server_pre_deploy_ISDIntelligence.sql

# 3. Restore ChromaDB IR folder
sudo rm -rf /opt/isd/ISDDocumentIntelligence_V6/backend/chroma_db_ir_v6
sudo cp -r /opt/backups/v6/server_pre_deploy_chroma_ir_v6 /opt/isd/ISDDocumentIntelligence_V6/backend/chroma_db_ir_v6
sudo chown -R isd:isd /opt/isd/ISDDocumentIntelligence_V6/backend/chroma_db_ir_v6

# 4. Restart backend
sudo systemctl start isd-backend
```

### Worst case — `ranking` table got wiped despite the `--ignore-table` exclusion
```bash
sudo mysql -u root -pisdadmin ISDIntelligence < /opt/backups/v6/server_pre_deploy_ranking_table_only.sql
```

---

## Notes / assumptions

- Local MySQL credentials: root / `Sandy@411`. Server: root / `isdadmin`.
- Server backend runs as systemd service `isd-backend` under user `isd`.
  Always use `sudo systemctl stop|start|restart isd-backend`, never
  Ctrl+C / manual kill.
- ChromaDB folder paths from `backend/.env` → `chroma_db_ir_v6` and
  `chroma_db_smac_v6` (defaults). Files in those folders MUST be owned
  by `isd:isd` so the service can read AND write them (ChromaDB needs
  write access for SQLite WAL files even on read operations).
- `users` and `cases` tables WILL be replaced by the local dump. This is
  fine per "local and server are the same" — but if you've made any
  user/case changes on the server side that aren't on local, those will
  be lost. Worth a sanity check before Phase 1E.
- BM25 indexes are intentionally not updated during bulk indexing
  (`rag_smac.py:629`). They auto-rebuild on first access after the
  backend restarts in Phase 2C — no extra step needed.
- The IR bulk script does NOT trigger entity / timeline / location
  extraction. Those are separate workflows triggered from the frontend
  ("Extract All" buttons) or via the corresponding `/extract-all`
  endpoints. Run them after Phase 2D if needed.
