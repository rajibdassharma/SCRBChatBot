# Security regression tests

One pytest per finding in the Innspark VAPT Preliminary Audit Report
v1.0.1 (2026-04-22). Run before every production deploy to confirm no
finding has regressed.

## Coverage

| Test | VAPT finding | What it proves |
|---|---|---|
| `test_7_1_seed_passwords_are_unique` | 7.1 | seed_credentials CSV contains no duplicate passwords |
| `test_7_1_seed_passwords_meet_strength` | 7.1 | every seeded password passes the strength rules |
| `test_7_1_change_password_rejects_weak[...]` | 7.1 | 6 weak-pattern rejection messages on `/change-password` |
| `test_7_2_token_works_before_logout` | 7.2 | baseline — valid token accepted |
| `test_7_2_token_rejected_after_logout` | 7.2 | token returns 401 "revoked" after `/logout` |
| `test_7_3_tokens_differ_across_logins` | 7.3 | two logins → two different tokens |
| `test_7_3_token_has_iat_jti_exp` | 7.3 | tokens carry `iat`, `jti`, `exp` claims |
| `test_7_4_account_locks_after_five_failures` | 7.4 | 6th wrong attempt returns 429; correct password rejected while locked |
| `test_7_5_case_payload_sanitized` | 7.5 | `<script>`, `javascript:`, `onerror=` stripped from `facts` / `crime_no` / `victim_name` |

**Not covered**: 7.6 (nginx version disclosure) — that's a production-Nginx
config concern, verified via `curl -I` against the deployed site.

## Prerequisites

1. **Backend running** on `http://localhost:8000` (override with
   `CFDSR_TEST_BASE` env var if elsewhere)
2. **Fresh seed** — the tests read credentials from the most recent
   `backend/seed_credentials_*.csv`. Re-seed before running:
   ```bash
   # In MySQL, purge users first:
   #   DELETE FROM users; DROP TABLE IF EXISTS revoked_tokens;
   cd backend && python seed.py
   ```
3. **Test deps**:
   ```bash
   pip install -r tests/requirements-test.txt
   ```

## Run

```bash
cd backend
pytest tests/ -v
```

Verbose output shows each test pass/fail. Expected: 14 passed.

## Notes on state side-effects

- **test_7_2_token_rejected_after_logout** revokes the token used by
  `admin_token` fixture — since the fixture is function-scoped, the next
  test gets a fresh login, no pollution.
- **test_7_4_account_locks_after_five_failures** locks out one specific
  `unit_user` (the last one in the CSV) for 15 minutes. Subsequent runs
  within that window will already be in lockout state — the test still
  passes because it asserts the lockout behavior, not the unlocked state.
  If you need to re-run cleanly within 15 min, restart the backend (the
  lockout counter is in-memory).
- **test_7_5_case_payload_sanitized** creates a test case with a unique
  FIR number (timestamp-based) and deletes it on pass. If the test fails
  mid-way, you may have a leftover `XSS-AUTOTEST-*` case to clean up.

## Extending

When adding a new security fix:
1. Add a `test_<finding_id>_<short_name>` function here
2. Update the coverage table above
3. Mention the VAPT finding ID in the docstring
4. Run the full suite and commit only on all green
