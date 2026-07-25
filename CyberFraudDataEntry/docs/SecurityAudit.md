# Security Audit — Cyber Fraud Data Entry

**Audit Date:** 2026-04-02
**Audited By:** Claude Code (automated static analysis)
**Scope:** Full backend + frontend + deployment configuration

---

## Critical Severity

### 1. JWT Tokens Never Expire
- **File:** `backend/auth/security.py`, lines 21-31
- **Issue:** `create_access_token()` creates tokens without an `exp` claim. `decode_token()` uses `verify_exp=False`.
- **Impact:** Stolen tokens are valid forever. Users cannot be forcibly logged out.
- **Status:** FIXED — Added expiry using `JWT_EXPIRE_MINUTES` from config. Enabled `verify_exp=True`.

### 2. Default JWT Secret Not Validated
- **File:** `backend/config.py`, line 12
- **Issue:** Default `JWT_SECRET = "change-this-to-a-random-secret-in-production"`. If not overridden in `.env`, all instances share the same secret.
- **Impact:** Anyone can forge valid JWT tokens and impersonate any user.
- **Status:** FIXED — Added startup warning if default secret is detected.

### 3. No File Upload Validation
- **File:** `backend/main.py`, photo upload endpoint
- **Issue:** Accepts any file extension, no MIME type check, no file size limit.
- **Impact:** Attackers can upload executable files or cause DoS with large files.
- **Status:** FIXED — Added extension whitelist (.jpg, .jpeg, .png, .gif), MIME type check, and 5MB size limit.

### 4. JWT Token Stored in localStorage
- **File:** `frontend/src/lib/stores/auth-store.ts`, lines 17-18
- **Issue:** JWT token stored in `localStorage`, accessible to any XSS attack.
- **Impact:** If XSS exists anywhere in the app, attacker can steal all user sessions.
- **Status:** NOTED — Requires architecture change to httpOnly cookies. Mitigated by input sanitization.

---

## High Severity

### 5. No Rate Limiting on Login
- **File:** `backend/api/routes_auth.py`
- **Issue:** Login endpoint has no rate limiting. Brute force attacks are trivial.
- **Impact:** Attacker can try thousands of password combinations per minute.
- **Status:** FIXED — Added in-memory rate limiter (5 attempts per IP per minute).

### 6. CORS Too Permissive
- **File:** `backend/main.py`, lines 33-39
- **Issue:** `allow_methods=["*"]` and `allow_headers=["*"]` allows any HTTP method and header.
- **Impact:** Broader attack surface for CSRF and cross-origin attacks.
- **Status:** FIXED — Restricted to explicit methods (GET, POST, PUT, DELETE) and headers (Content-Type, Authorization).

### 7. No File Size Limit on Excel Uploads
- **File:** `backend/api/routes_mule_report.py`
- **Issue:** Excel upload reads entire file into memory without size check.
- **Impact:** DoS via uploading very large files.
- **Status:** FIXED — Added 10MB file size limit.

### 8. No Security Headers
- **File:** `backend/main.py`
- **Issue:** Missing X-Frame-Options, X-Content-Type-Options, Strict-Transport-Security, Content-Security-Policy.
- **Impact:** Clickjacking, MIME sniffing, and other browser-based attacks.
- **Status:** FIXED — Added security headers middleware.

### 9. Swagger/OpenAPI Exposed in Production
- **File:** `backend/main.py`
- **Issue:** API documentation visible to anyone at `/docs` and `/openapi.json`.
- **Impact:** Information disclosure — attackers can see all endpoints, parameters, and schemas.
- **Status:** FIXED — Disabled in production via `CFDSR_DISABLE_DOCS` env var.

### 10. Debug Print Statements Leak Information
- **File:** `backend/api/routes_mule_report.py`, lines 91, 105, 107, 195
- **Issue:** Print statements output acknowledgement numbers, sheet names, transaction counts.
- **Impact:** Sensitive data in server logs.
- **Status:** FIXED — Replaced with proper logging.

---

## Medium Severity

### 11. No Audit Trail
- **Files:** All route handlers
- **Issue:** No logging of who created/modified/deleted records.
- **Impact:** Cannot investigate security incidents or unauthorized modifications.
- **Status:** NOTED — Recommend adding audit_log table in future iteration.

### 12. No CSRF Protection
- **File:** Frontend + Backend
- **Issue:** No CSRF tokens on state-changing operations.
- **Impact:** Cross-site request forgery possible if user visits malicious site while logged in.
- **Status:** NOTED — Mitigated by Bearer token auth (not cookie-based).

### 13. Error Messages Leak Stack Traces
- **File:** `backend/api/routes_mule_report.py`
- **Issue:** Exception details sent to client in error responses.
- **Impact:** Information disclosure about server internals.
- **Status:** FIXED — Generic error messages to client, full details logged server-side.

### 14. No Input Validation on FIR/Petition Numbers
- **Files:** `backend/schemas/case.py`
- **Issue:** No format validation on government reference numbers.
- **Impact:** Garbage data, potential injection if used in external systems.
- **Status:** NOTED — Recommend adding regex validation.

### 15. No Concurrent Edit Protection
- **File:** `backend/api/routes_case.py`
- **Issue:** Two users can update the same record simultaneously. Last write wins.
- **Impact:** Data loss from concurrent edits.
- **Status:** NOTED — Recommend optimistic locking in future iteration.

---

## Low Severity

### 16. Upload Directory Publicly Accessible
- **File:** `backend/main.py`
- **Issue:** `/uploads` endpoint serves all files without authentication.
- **Impact:** Anyone can access uploaded photos if they know the filename (UUID-based, so low risk).
- **Status:** NOTED — Recommend adding auth check for upload access.

---

## Deployment Issues

### 17. MySQL Using root/root
- **Issue:** Application connects as MySQL root with weak password.
- **Impact:** Full database access if credentials are compromised.
- **Recommendation:** Create dedicated `cfdsr_app` user with limited permissions.

### 18. Self-Signed SSL Certificate
- **Issue:** Browsers show security warnings.
- **Impact:** Users may ignore security warnings, training them to accept invalid certs.
- **Recommendation:** Obtain proper certificate from NIC or use internal CA.

### 19. JWT Secret Not Set in Server .env
- **Issue:** Server may be using default JWT secret.
- **Impact:** Token forgery possible.
- **Recommendation:** Add `CFDSR_JWT_SECRET=<random-64-char>` to server `.env`.

---

## Fixes Applied in This Audit

| # | Severity | Fix | File |
|---|----------|-----|------|
| 1 | Critical | JWT token expiry enforced | `auth/security.py` |
| 2 | Critical | JWT secret default warning | `config.py` |
| 3 | Critical | Photo upload validation | `main.py` |
| 5 | High | Login rate limiting | `api/routes_auth.py` |
| 6 | High | CORS restricted | `main.py` |
| 7 | High | Excel upload size limit | `api/routes_mule_report.py` |
| 8 | High | Security headers | `main.py` |
| 9 | High | Swagger disabled in prod | `main.py` |
| 10 | High | Debug prints removed | `api/routes_mule_report.py` |
| 13 | Medium | Generic error messages | `api/routes_mule_report.py` |

## Remaining Items (Future Work)

| # | Severity | Item |
|---|----------|------|
| 4 | Critical | Migrate token storage to httpOnly cookies |
| 11 | Medium | Add audit_log table |
| 12 | Medium | Add CSRF protection |
| 14 | Medium | Input validation on FIR/petition numbers |
| 15 | Medium | Optimistic locking for concurrent edits |
| 16 | Low | Auth-protected upload access |
| 17 | Deploy | Create dedicated MySQL user |
| 18 | Deploy | Proper SSL certificate |
| 19 | Deploy | Set JWT secret on server |
