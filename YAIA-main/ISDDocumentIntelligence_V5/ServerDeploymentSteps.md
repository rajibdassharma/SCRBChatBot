# ISD Document Intelligence V5 — Server Deployment Steps

**Date:** March 20, 2026
**Server:** Ubuntu H100 GPU Server
**Purpose:** Complete production deployment with all indexing changes

---

## 1. Installations on Server

```bash
source /opt/isd/venv/bin/activate

# Install new packages
pip install docling easyocr

# Download models (requires internet — do this BEFORE going offline)
python -c "from docling.document_converter import DocumentConverter; DocumentConverter()"
python -c "import easyocr; easyocr.Reader(['en'])"
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('mixedbread-ai/mxbai-embed-large-v1')"
```

---

## 2. Files to Copy to Server

```
Backend (copy to /opt/isd/backend/):
  1. backend/app.py
  2. backend/rag.py
  3. backend/llm_kv_extractor.py
  4. backend/structured_tables.py
  5. backend/requirements.txt

Scripts (copy to /opt/isd/dbscripts/):
  6. dbscripts/bulk_index_smac.py
  7. dbscripts/ocr_index_smac.py
  8. dbscripts/migrate_chroma_to_mysql.py

Documentation (copy to /opt/isd/):
  9. DEPLOYMENT.md
```

Do NOT copy: `.env` (server has its own), `chroma_db_v5/`, any `.db` files, `test_docling_*.py`

---

## 3. Complete Deployment Steps (in sequence)

### Step 1: Stop everything

```bash
Ctrl+C in the uvicorn terminal (if running)
```

### Step 2: Backup current state

```bash
cd /opt/isd
cp backend/app.py backend/app.py.bak
cp backend/rag.py backend/rag.py.bak
cp backend/structured_tables.py backend/structured_tables.py.bak
cp backend/llm_kv_extractor.py backend/llm_kv_extractor.py.bak
mysqldump -u root -p ISDIntelligence > /opt/isd/backup_before_deploy.sql
```

### Step 3: Install new packages

```bash
source /opt/isd/venv/bin/activate
pip install docling easyocr
```

### Step 4: Download models (needs internet)

```bash
python -c "from docling.document_converter import DocumentConverter; DocumentConverter()"
python -c "import easyocr; easyocr.Reader(['en'])"
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('mixedbread-ai/mxbai-embed-large-v1')"
```

### Step 5: Copy files to server

Copy all 9 files listed in Section 2 to their respective directories on the server.

### Step 6: Update .env on server

```bash
nano /opt/isd/backend/.env
```

Ensure these settings:
```ini
USE_LLM_PARSER=false
USE_OLLAMA_EMBEDDINGS=false
HF_HUB_OFFLINE=1
```

### Step 7: Drop and recreate smac_reports table

```bash
mysql -u root -p ISDIntelligence
```

```sql
DROP TABLE IF EXISTS smac_reports;
ALTER TABLE ir_reports MODIFY field_key VARCHAR(500) NOT NULL;
```

Exit MySQL. The backend will recreate `smac_reports` with the new EAV schema on startup.

### Step 8: Delete old ChromaDB and progress files

```bash
rm -rf /opt/isd/backend/chroma_db_v5
rm -f /opt/isd/dbscripts/.smac_bulk_progress.db
rm -f /opt/isd/dbscripts/.smac_ocr_progress.db
rm -f /opt/isd/dbscripts/pdfs_pending_ocr.txt
```

### Step 9: Start Ollama

```bash
sudo systemctl restart ollama
ollama run gemma3:12b "hello"
```

### Step 10: Start backend

```bash
source /opt/isd/venv/bin/activate
cd /opt/isd/backend
uvicorn app:app --host 0.0.0.0 --port 8001
```

Watch the terminal output for:
- `[StructuredTables] smac_reports and ir_reports tables ready.`
- `[Embed] sentence-transformers loaded on cuda`

Keep this terminal open — the backend runs in the foreground.

### Step 11: Verify backend health

```bash
curl -s http://127.0.0.1:8001/health
```

Should return a JSON response with `"ok": true`.

### Step 12: Index Digital SMAC reports

```bash
source /opt/isd/venv/bin/activate
cd /opt/isd/dbscripts
python bulk_index_smac.py \
    --folder "/data/SMAC/Digital" \
    --case-id 0 \
    --username rajibds \
    --password rajibds \
    --workers 5
```

Speed: ~5-6 seconds per document.
Logs: `dbscripts/logfiles/bulk_index_smac.log`

### Step 13: Index Scanned SMAC reports

```bash
cd /opt/isd/backend
python ../dbscripts/ocr_index_smac.py --folder "/data/SMAC/Scanned"
```

Speed: ~10-11 seconds per document.
Logs: `dbscripts/logfiles/ocr_index_smac.log`

### Step 14: Index IR documents

```bash
# Change .env for IR
nano /opt/isd/backend/.env
# Set: USE_LLM_PARSER=true

# Restart backend to pick up the change
Ctrl+C in the uvicorn terminal, then restart:
source /opt/isd/venv/bin/activate && cd /opt/isd/backend && uvicorn app:app --host 0.0.0.0 --port 8001

# Run IR indexing
cd /opt/isd/dbscripts
python bulk_index_smac.py \
    --folder "/data/IR" \
    --collection IR \
    --filter "ir,interrogation report" \
    --workers 1 \
    --username rajibds \
    --password rajibds
```

Speed: ~30-60 seconds per document.
Logs: `dbscripts/logfiles/bulk_index_ir.log`

### Step 15: Verify data

```bash
mysql -u root -p ISDIntelligence
```

```sql
-- SMAC structured data
SELECT COUNT(DISTINCT doc_id) as smac_docs FROM smac_reports;
SELECT field_key, COUNT(*) as cnt FROM smac_reports GROUP BY field_key ORDER BY cnt DESC LIMIT 15;

-- IR structured data
SELECT COUNT(DISTINCT doc_id) as ir_docs FROM ir_reports;
SELECT field_key, COUNT(*) as cnt FROM ir_reports GROUP BY field_key ORDER BY cnt DESC LIMIT 15;
```

Exit MySQL.

### Step 16: Set back to production mode

```bash
nano /opt/isd/backend/.env
# Set: USE_LLM_PARSER=false
# (keep false — IR is already indexed, SMAC doesn't need it)

Ctrl+C in the uvicorn terminal, then restart:
source /opt/isd/venv/bin/activate && cd /opt/isd/backend && uvicorn app:app --host 0.0.0.0 --port 8001
```

### Step 17: Test Q&A

Open browser, login, upload a test document, ask a question. Verify answers.

---

## 4. Reset Commands (if needed)

### Reset Digital SMAC only

```bash
cd /opt/isd/dbscripts
python bulk_index_smac.py --reset --username rajibds --password rajibds
```

### Reset OCR SMAC only

```bash
cd /opt/isd/backend
python ../dbscripts/ocr_index_smac.py --reset
```

### Reset everything (nuclear option)

```bash
Ctrl+C in the uvicorn terminal (if running)
rm -rf /opt/isd/backend/chroma_db_v5
rm -f /opt/isd/dbscripts/.smac_bulk_progress.db
rm -f /opt/isd/dbscripts/.smac_ocr_progress.db
mysql -u root -p ISDIntelligence -e "DELETE FROM smac_reports; DELETE FROM ir_reports;"
sudo systemctl start isd-backend
```

Then re-run Steps 12-16.

---

## 5. Troubleshooting

| Problem | Solution |
|---------|----------|
| ReadTimeout during indexing | Restart Ollama: `sudo systemctl restart ollama && ollama run gemma3:12b "hello"` |
| Indexing slows down | Restart backend: Ctrl+C in uvicorn terminal, then re-run uvicorn (BM25 memory buildup) |
| "Data too long for field_key" | `mysql -u root -p ISDIntelligence -e "ALTER TABLE ir_reports MODIFY field_key VARCHAR(500) NOT NULL;"` |
| sentence-transformers not on GPU | Check uvicorn terminal for `[Embed] sentence-transformers loaded on cuda`. If missing, verify `torch.cuda.is_available()` |
| Docling model not found | Re-run: `python -c "from docling.document_converter import DocumentConverter; DocumentConverter()"` |
| EasyOCR model not found | Re-run: `python -c "import easyocr; easyocr.Reader(['en'])"` |
| Backend won't start | Check uvicorn terminal output for error messages |
| smac_reports table error | `mysql -e "DROP TABLE smac_reports;"` then restart uvicorn |

---

*Prepared for ISD Document Intelligence V5 server deployment — March 20, 2026*
