# Security Posture — Cyber Fraud Data Entry

Snapshot of every known security control + finding, from the first
in-house audit (2026-04-02) through the Innspark VAPT v1.0.1
closure (2026-05-10) and every post-VAPT hardening shipped since.

If you're doing an audit / handover: this is what the app looks like
today. If you're doing a historical trace: git log the file.

---

## 1. Applied controls (what's in the code right now)

### Authentication & session

- **JWT HS256** — 8-hour expiry (`CFDSR_JWT_EXPIRE_MINUTES`), `verify_exp=True` on every decode
- **JWT secret validation** — backend refuses to start if `CFDSR_JWT_SECRET` is missing, still the default placeholder, or < 32 chars (enforced in `config.py`)
- **Token revocation** — `revoked_tokens` table checked on every request; logout inserts the current jti
- **Password hashing** — bcrypt via passlib
- **First-login password change** — every user seeded / reset with `must_change_password = true`; all routes except `/auth/change-password` return 403 until cleared
- **Login rate limiting** — in-memory per-IP counter; N failed attempts locks the source for 15 min
- **No default passwords** — `seed.py` generates a random secure password per user and writes them to a one-time CSV

### Authorization (RBAC + per-record scoping)

- **Three roles** — `super_admin`, `admin`, `unit_user` enforced via `require_admin()` / `require_unit_user()` dependencies in `api/deps.py`
- **Per-record `(unit_id, ps_id)` scoping** — `check_record_access()` gates every mutation route; super_admin bypasses only on cross-PS read routes (senior officer oversight)
- **No horizontal privilege escalation** — `unit_user` sees only records they personally submitted, within their own PS
- **`docs_url=None, redoc_url=None`** — FastAPI Swagger + OpenAPI schema disabled in production

### Input validation & sanitisation

- **Free-text sanitisation** — every `str` field on every Pydantic write schema runs through `strip_html` (VAPT rec)
- **Format validators** — phone (10 digits), pincode (6 digits), bank_account_no (9–18 digits), FIR No (`NNNN/YYYY`) — shared client + server regex
- **Amount cap** — every `Numeric` amount field runs through `_validate_amount` (≥ 0, ≤ ₹100 crore)
- **Duplicate detection on writes** — arrests reject same-name / same-Aadhar within one case

### File handling

- **HMAC-signed `/uploads/*` URLs** — every file link carries a 1-hour expiry signature; leaked URLs (in exports, screenshots, chat history) die within the hour
- **MIME-type + size limits** on every upload endpoint (photos 5 MB, statements 5 MB app-side; nginx caps body at 25 MB)
- **UUIDv4 filenames** — original filenames stripped; no traversal risk
- **Uploads served through the backend** — `location /uploads/ {}` in nginx proxies to backend so the signature middleware runs before file access

### Transport & headers

- **HTTPS** via nginx TLS termination (self-signed cert on KSWAN)
- **Security headers** middleware — X-Frame-Options, X-Content-Type-Options, HSTS
- **CORS locked down** — explicit methods (GET/POST/PUT/DELETE) and headers (Content-Type, Authorization); `CFDSR_CORS_ORIGINS` restricts origins to configured URLs only

### Data integrity

- **Every operator-created row carries `submitted_by`** — audit trail on writes
- **CASCADE deletes are explicit** — no orphan protection anywhere; a delete on a parent is intentional
- **All schema changes via numbered migrations** — no more `reset_db.py`; every change is idempotent and self-verified in `deploy/update.sh`
- **Chat audit trail** — every question + generated SQL + row_count + error stored in `chat_messages` for LLM-answer traceability (super_admin only)

### Deploy & runtime

- **Non-root systemd user** — `cyberfraud` service user with `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome=true`, restricted `ReadWritePaths`
- **MySQL bound to `127.0.0.1`** — no external DB exposure
- **Backend bound to `127.0.0.1:8000`** — reached only via nginx
- **UFW default deny inbound** — SSH + 80 + 443 the only open ports
- **Self-verify block on every deploy** — `update.sh` step 8 aborts on route / schema regression before restarting
- **Nightly encrypted-at-rest backups** — systemd timer + `deploy/backup-db.sh` + `backup-uploads.sh`

---

## 2. VAPT v1.0.1 (Innspark, 2026-05-10) — CLOSED

External VAPT engagement by Innspark; all 10 findings re-validated closed on 2026-05-10. Every fix on that list is covered by the controls in section 1. Highlights:

- **7.1** JWT expiry + revocation → closed (see Authentication controls)
- **7.2** JWT secret validation → closed
- **7.3** Password policy (rate limit + must-change-password) → closed
- **7.4** File upload validation → closed
- **7.5** Security headers → closed
- **7.6** CORS restriction → closed
- **7.7 + 7.8** BOLA / per-record scoping → closed (`check_record_access` on every route)
- **7.9** Free-text XSS via strip_html → closed
- **7.10** UUIDv4 primary keys on user-facing tables → closed (VAPT rec #2)

After 2026-05-10, no `reset_db.py`, no bulk drops. Every future schema change is a numbered additive migration.

---

## 3. Pre-VAPT audit (in-house, 2026-04-02) — closed via VAPT

The 19-item internal audit that pre-dated Innspark's engagement. Kept
here as a historical trace; all items either fixed pre-VAPT or rolled
into the VAPT closure above.

| # | Item | Where it lives now |
|---|---|---|
| 1 | JWT tokens never expire | §1 Authentication — expiry enforced |
| 2 | Default JWT secret | §1 Authentication — startup check |
| 3 | No file upload validation | §1 File handling — MIME + size + UUID names |
| 4 | JWT in localStorage (XSS-exposed) | §1 Transport — mitigated by strip_html + CSP + HMAC uploads; migration to httpOnly cookies deferred (architecture change) |
| 5 | No rate limiting on login | §1 Authentication — 5/min per-IP |
| 6 | CORS too permissive | §1 Transport — explicit methods + headers |
| 7 | No file size limit on Excel uploads | §1 File handling — 25 MB nginx cap + per-endpoint check |
| 8 | Missing security headers | §1 Transport — X-Frame-Options, HSTS, etc. |
| 9 | Swagger exposed in prod | §1 Authorization — `docs_url=None` |
| 10 | Debug print statements | Fixed — replaced with logging |
| 11 | No audit trail | §1 Data integrity — every row has `submitted_by`; chat has `chat_messages` |
| 12 | No CSRF protection | Mitigated — Bearer token auth (not cookie-based) makes CSRF non-applicable |
| 13 | Stack traces in errors | Fixed — generic client errors, full details in server logs |
| 14 | No FIR / petition-no validation | §1 Input validation — shared `NNNN/YYYY` regex |
| 15 | No concurrent-edit protection | **OPEN** — see §4 |
| 16 | Upload dir publicly accessible | §1 File handling — HMAC signature middleware |
| 17 | MySQL using root/root | Deploy checklist — dedicated `cfdsr_app` user (see ProductionDeployment §5) |
| 18 | Self-signed SSL | Accepted — internal KSWAN network; NIC has not issued a cert |
| 19 | JWT secret not set on server | §1 Authentication — server refuses to start without it |

---

## 4. Known-open items (deliberate deferrals)

None are blockers, but they're on the radar.

- **Optimistic locking on concurrent edits.** Two users editing the same case race — last write wins. Real-world impact is low (per-PS scoping means only 2–3 people per station can touch the same row) but a future migration could add a `version` column + If-Match precondition.
- **JWT storage in `localStorage`.** Standard SPA pattern, still vulnerable in principle to XSS. Mitigated by `strip_html` on every write + no CSP-bypassing scripts anywhere in the frontend. Migration to httpOnly cookies would require a session-cookie architecture change; not planned.
- **Chat feature disabled in prod.** `CFDSR_CHAT_ENABLED=false`; the audit table exists (migration 005 SKIPPED) and the routes are wired, but the external LLM call is gated by a super_admin-only role AND the flag. Enable only when the GPU box + on-premise LLM lands so no data leaves KSWAN.
- **`cases.submitted_by` FK is fragile.** Kept as an INT reference; hard-deleting a user leaves orphan `submitted_by` values pointing at nothing. Treated as a soft reference — no CASCADE, no NULLIFY. Users get deactivated (`is_active=false`), not deleted, so this is theoretical.

---

## 5. Ongoing hygiene

- Run `deploy/update.sh` for every deploy — its self-verify step catches route / schema regressions before restart.
- Before pushing anything security-sensitive, add a check to `update.sh` step 8 that would have caught it.
- Re-audit annually or after any major feature (chat, mobile app, third-party integration).
- Nightly backup timer covers the DB + uploads; test-restore once a quarter into a scratch DB.
- Rotate `CFDSR_JWT_SECRET` via `deploy/rotate-jwt-secret.sh` if compromise is suspected — every session becomes invalid at once.

---

_Living document. See git log for change history. Next scheduled review: on the next major feature or 2027-04 whichever comes first._
