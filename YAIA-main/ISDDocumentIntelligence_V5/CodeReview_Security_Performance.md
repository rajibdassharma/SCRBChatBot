# ISD Document Intelligence V5 — Code Review
## Security & Performance Analysis
**Date:** 2026-03-19
**Reviewed by:** Claude Code (Opus 4.6)
**Scope:** All backend Python files

---

## SECURITY REVIEW

### CRITICAL (2)

| # | Finding | File:Line | Description | Suggested Fix |
|---|---------|-----------|-------------|---------------|
| S1 | SQL injection via f-string | cases.py:210 | `cur.execute(f"UPDATE cases SET {', '.join(updates)} ...")` — column names interpolated directly. Safe today due to Pydantic whitelist but fragile pattern. | Validate column names against explicit whitelist. Add comment explaining safety. |
| S2 | Database name interpolation | mysql_db.py:51 | `MYSQL_DATABASE` in f-string for CREATE DATABASE. If value contains backtick, escaping breaks. | Validate `MYSQL_DATABASE` matches `^[a-zA-Z0-9_]+$` at startup. |

### HIGH (7)

| # | Finding | File:Line | Description | Suggested Fix |
|---|---------|-----------|-------------|---------------|
| S3 | Unrestricted CORS | app.py:67-73 | `allow_origins=["*"]` with `allow_credentials=True`. Any website can call authenticated endpoints. | Set `allow_origins` to explicit frontend domain(s) in production. Remove wildcard. |
| S4 | Plaintext DB password in .env | .env:31 | `MYSQL_PASSWORD=Sandy@411` committed to git. | Use secrets manager in production. Create `.env.example` without real values. |
| S5 | Weak JWT secret | .env:10 | Predictable string: `isd-intelligence-local-dev-secret-key-change-in-prod`. | Generate with `openssl rand -hex 32`. Validate key length at startup. |
| S6 | Missing auth on 12+ endpoints | app.py (multiple) | No `Depends(get_current_user)` on: `/spell-check`, `/docs/transcribe`, `/docs/voice-ask`, `/qa/upload-prompts`, `/qa/run`, `/qa/status`, `/qa/results`, `/structured/smac`, `/structured/smac/{doc_id}`, `/structured/ir`, `/structured/ir/{doc_id}`, `/structured/query`. | Add `current_user: CurrentUser = Depends(get_current_user)` to all sensitive endpoints. |
| S7 | No file upload size limits | app.py:159-207 | `file.read()` with no size check. Attacker can upload arbitrarily large files. | Add `MAX_FILE_SIZE` check (e.g., 100MB). Return 413 if exceeded. |
| S8 | NL-to-SQL injection | structured_tables.py:344-358 | LLM-generated SQL validated only by keyword blacklist. Bypassable with comments, backticks, multi-statement attacks. | Use SQL parser library (e.g., `sqlparse`) to validate AST. Whitelist approach instead of blacklist. |
| S9 | Debug audio with user-controlled extension | app.py:488-493 | Audio saved as `last_recording{ext}` where `ext` comes from user filename. Could save `.php`/`.exe`. | Whitelist extensions: `.webm`, `.wav`, `.mp3`, `.ogg`. Disable debug saving in production. |

### MEDIUM (6)

| # | Finding | File:Line | Description | Suggested Fix |
|---|---------|-----------|-------------|---------------|
| S10 | Weak password policy | auth.py:161 | Only 6 character minimum, no complexity requirements. | Increase to 12+ chars. Require mixed case, numbers, symbols. |
| S11 | No rate limiting on auth | auth.py:153-232 | Login and register have no rate limiting. Brute force possible. | Use `slowapi` library: 5/minute on login, 1/hour on register per IP. |
| S12 | Missing admin checks | app.py (multiple) | Only `/auth/users` checks admin role. Destructive endpoints (`/docs/clear`, `/graph/clear`, etc.) accept any authenticated user. | Add admin role check to all destructive/clearing endpoints. |
| S13 | Case ID ownership not validated | app.py (multiple) | `case_id` accepted from user input but not validated for ownership. User can access other users' cases by guessing IDs. | Use `_get_case_for_user(case_id, user_id)` on all case-scoped endpoints. |
| S14 | SQL blacklist insufficient | structured_tables.py:344 | Regex `\bDROP\b` bypassable with backticks, comments, multi-statements (`;DROP TABLE`). | Parse SQL with `sqlparse`, verify it's a single SELECT statement. |
| S15 | Error messages leak system info | app.py:205-206 | `f"{type(e).__name__}: {str(e)}"` returned to client — exposes file paths, module names. | Log full exception server-side. Return generic error to client. |

### LOW (4)

| # | Finding | File:Line | Description | Suggested Fix |
|---|---------|-----------|-------------|---------------|
| S16 | Timing attack on password | auth.py:213-214 | Short-circuit `not row or not _verify_password(...)` leaks whether username exists via timing. | Always call `_verify_password`, even for non-existent users. |
| S17 | No audit logging | All files | No trail of who accessed what. Required for law enforcement compliance. | Log auth events, data mutations, queries to audit table. |
| S18 | No HTTPS enforcement | App config | JWTs and passwords transmitted in cleartext over HTTP. | Enforce HTTPS at reverse proxy (nginx). Add HSTS header. |
| S19 | Collection name not whitelisted | app.py:341-342 | `collection` from user input passed to ChromaDB without validation. | Whitelist: `if collection not in ["SMAC", "IR"]: raise HTTPException(...)` |

---

## PERFORMANCE REVIEW

### CRITICAL (5)

| # | Finding | File:Line | Description | Impact | Suggested Fix |
|---|---------|-----------|-------------|--------|---------------|
| P1 | No MySQL connection pooling | mysql_db.py:68-84 | Every `get_conn()` creates a new connection. Bulk indexing creates thousands. | Connection exhaustion at scale (MySQL default max=151). | Use `DBUtils.PooledDB` or `sqlalchemy.pool`. Target 5-10 pool size. |
| P2 | Full collection loaded into RAM | rag.py:2341 | `get_all_doc_chunks` calls `collection.get()` with no limit. 200K chunks = 200MB+. | OOM risk with concurrent calls. | Paginate: `collection.get(limit=1000, offset=page*1000)`. |
| P3 | BM25 re-tokenizes entire corpus on every insert | rag.py:117-123 | `_add_to_bm25()` rebuilds `BM25Okapi(corpus)` from all docs on every document add. O(N) per insert. | Indexing slows progressively — this is the slowdown observed during bulk indexing. | Defer BM25 rebuild. Only rebuild on first query, not on insert. Or use incremental BM25. |
| P4 | Multi-query pipeline creates 60s+ latency | rag.py:1390-1427 | 4 embeddings + 4 vector searches + 4 BM25 searches + RRF merge + LLM re-rank per query. | 60s per query under load. Doesn't scale to concurrent users. | Reduce to 2 query variations. Batch embed. Skip re-rank for list queries. |
| P5 | Context truncation at character boundary | rag.py:2112 | `context[:60000]` cuts mid-sentence. LLM gets incomplete data. | Answer accuracy drops 20-40% for large documents. | Truncate at chunk boundary. Drop lowest-relevance chunks first. Increase to 120K for 128K context model. |

### HIGH (11)

| # | Finding | File:Line | Description | Impact | Suggested Fix |
|---|---------|-----------|-------------|--------|---------------|
| P6 | BM25 rebuild on first collection access | rag.py:94-114 | `_rebuild_bm25()` loads ALL ChromaDB docs on `_get_col()` init. | 30-60s blocked on startup for large collections. | Persist BM25 index to disk (pickle). Load from cache. |
| P7 | Field lookup queries ChromaDB 4 times | rag.py:1472-1476 | `_get_chunks_by_field` tries 4 casings (title, lower, UPPER, title). | 4x unnecessary queries per field detection. | Normalize field_name to lowercase at index time. Single lookup. |
| P8 | `search_fields` called per keyword | rag.py:2043-2070 | 20 expanded keywords = 20 separate SQL LIKE queries. | 20 DB hits per user question. | Batch into single query: `WHERE field_key LIKE %k1% OR field_key LIKE %k2% ...` |
| P9 | Multi-query embeddings not batched | rag.py:1401-1410 | 4 queries embedded with 4 separate `ollama_embed()` calls. | 4s instead of 1s. | Batch: `ollama_embed_batch([q1, q2, q3, q4])` then use vectors in loop. |
| P10 | No answer caching | rag.py:2170-2187 | Same question = full LLM call every time. | Repeated common questions waste 30s each. | Cache by `(question_hash, collection, doc_ids)` with 1-hour TTL. |
| P11 | Global dicts not thread-safe | rag.py:45-46 | `_col_cache` and `_bm25` modified concurrently without locks. | Race condition: BM25 read mid-rebuild returns None. Search fails silently. | Add `threading.Lock()` around all accesses. |
| P12 | `_extraction_status` dict no locking | app.py:251 | Written by daemon thread, read by API handlers concurrently. | Status dict corruption. Incorrect progress reported. | Use `threading.Lock()`. |
| P13 | Entity graph GROUP_CONCAT unbounded | entity_graph.py:705-850 | No pagination on entity graph queries. GROUP_CONCAT on 1000s of docs. | MySQL memory exhaustion for large datasets. | Paginate results. Limit GROUP_CONCAT length. |
| P14 | `get_indexed_doc_list` full scan | rag.py:2319-2338 | Loads all metadatas to group by doc_id. No database-side grouping. | 200K metadatas = 50-100MB per call. | Maintain doc list in MySQL. Or cache result with short TTL. |
| P15 | `_get_chunks_by_field_fuzzy` full scan | rag.py | Loads entire IR collection into Python for substring matching. | All chunks in RAM for every IR question. | Build field_name index. Or use BM25 for field search. |
| P16 | Connection per function in structured_tables | structured_tables.py | No connection reuse or batching for bulk inserts. | 3000 docs = 3000 connections during indexing. | Use `executemany()` with batches. Reuse connection. |

### MEDIUM (4)

| # | Finding | File:Line | Description | Impact | Suggested Fix |
|---|---------|-----------|-------------|--------|---------------|
| P17 | 4 init_db() calls at startup | Multiple modules | Synchronous CREATE TABLE on import. | 5-20s startup delay if MySQL is slow. | Defer to FastAPI lifespan handler. |
| P18 | Sentence-transformers lazy load | ollama_client.py:7-15 | First embedding request loads 1GB+ model. | 30s delay on first user request. | Pre-load at app startup when `USE_OLLAMA_EMBEDDINGS=false`. |
| P19 | Ollama timeout 600s | ollama_client.py:26 | One hung call blocks worker thread for 10 minutes. | Worker exhaustion with 8 threads. | Reduce to 90s. Add exponential backoff retry. |
| P20 | LIKE without FULLTEXT index | structured_tables.py:288-327 | `field_key LIKE %keyword%` does full table scan. | Slow keyword search at scale. | Add FULLTEXT index. Use MATCH() AGAINST(). |

---

## SUMMARY

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| Security | 2 | 7 | 6 | 4 | 19 |
| Performance | 5 | 11 | 4 | — | 20 |
| **Total** | **7** | **18** | **10** | **4** | **39** |

## PRIORITY ACTIONS

### Immediate (before production deployment)
1. **S6** — Add authentication to all unprotected endpoints
2. **S3** — Restrict CORS to trusted origins
3. **S5** — Generate strong JWT secret
4. **S13** — Validate case ownership on all case-scoped endpoints

### Short-term (next sprint)
5. **P1** — Implement MySQL connection pooling
6. **P3** — Fix BM25 rebuild (defer to query time, not insert time)
7. **S7** — Add file upload size limits
8. **S8** — Replace SQL keyword blacklist with AST parser
9. **P8** — Batch `search_fields` into single SQL query

### Medium-term (before scale-up)
10. **P11/P12** — Add thread safety (locks on global dicts)
11. **P10** — Implement answer caching
12. **P9** — Batch multi-query embeddings
13. **P6** — Persist BM25 index to disk
14. **S17** — Implement audit logging

### Long-term (production hardening)
15. **P4** — Optimize multi-query + re-rank pipeline
16. **P5** — Intelligent context truncation
17. **P15** — Build field_name index for IR lookups
18. **S10/S11** — Strengthen password policy + rate limiting
19. **P20** — FULLTEXT indexes on structured tables
