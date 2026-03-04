# ISD Document Intelligence V4 — Testing & Safety Guide

---

## Table of Contents

1. [Sign Out Safety Guard](#1-sign-out-safety-guard)
2. [Automated Test Suite Overview](#2-automated-test-suite-overview)
3. [Folder Structure](#3-folder-structure)
4. [Prerequisites](#4-prerequisites)
5. [How to Run Tests](#5-how-to-run-tests)
6. [Test Files — Detailed Coverage](#6-test-files--detailed-coverage)
7. [Adding New Tests](#7-adding-new-tests)
8. [Regression Checklist](#8-regression-checklist)

---

## 1. Sign Out Safety Guard

### Problem

Previously, pressing Sign Out while a document was being indexed or entities were being extracted would:
- Immediately clear the browser session
- Leave the backend still running the job (indexing/extraction continues headlessly)
- If "Clear & Sign Out" was chosen — could cause a race condition between the clear call and the ongoing write, potentially corrupting the ChromaDB index

### Solution

The Sign Out button now detects two active states:

| State variable | When `true` |
|---|---|
| `docIndexing` | A document upload + indexing job is in progress |
| `graphExtracting` | Entity extraction is running in the background |

#### Behaviour when either state is active:

| Element | Behaviour |
|---|---|
| Sign Out button | Disabled, greyed out (opacity 60%), cursor `not-allowed` |
| Button label | Changes from `"Sign Out"` → `"Indexing..."` or `"Extracting..."` |
| Hover tooltip | `"Document indexing in progress — please wait before signing out"` |
| Dialog | Blocked from opening (`handleSignOutRequest` returns early) |
| Dialog action buttons | Disabled if dialog was already open when an operation started |
| Dialog warning banner | Yellow `⚠` warning appears inside the dialog explaining the block |

#### Code location

- [frontend/src/App.tsx](frontend/src/App.tsx) — `handleSignOutRequest`, Sign Out button, Sign Out dialog

---

## 2. Automated Test Suite Overview

The test suite is a set of **integration tests** that run against the **live backend**. They test the real stack — MSSQL, ChromaDB, FastAPI — without any mocking.

### What is tested

| Code | Module | Endpoints | Test Count |
|------|--------|-----------|-----------|
| TC-H | Health & Utilities | `GET /health`, `POST /spell-check` | 5 |
| TC-A | Authentication | `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `POST /auth/change-password`, `GET /auth/users` | 14 |
| TC-C | Case Management | `GET /cases`, `POST /cases`, `GET /cases/{id}`, `PATCH /cases/{id}`, `DELETE /cases/{id}` | 14 |
| TC-D | Documents | `POST /docs/upload`, `GET /docs/list`, `POST /docs/ask`, `POST /docs/clear`, `POST /docs/extract-entities` | 12 |
| TC-G | Entity Graph | `GET /graph/entities`, `GET /graph/data`, `DELETE /graph/clear`, `POST /graph/extract-all`, `GET /graph/extraction-status` | 11 |
| TC-T | Activity Timeline | `POST /timeline/extract-all`, `GET /timeline/extraction-status`, `GET /timeline/data`, `GET /timeline/groups`, `GET /timeline/breadcrumb` | 11 |
| TC-S | Structured Data & Locations | `GET /structured/smac`, `GET /structured/ir`, `POST /locations/extract-all`, `GET /locations/data` | 8 |
| | | **TOTAL** | **~75** |

### Design principles

- **Real stack** — No mocking. If MSSQL is down, the tests fail. That's intentional — it confirms the full system works.
- **Isolated test data** — Each run creates a unique test user (`testuser_<timestamp>`) and a test case, so parallel runs don't interfere.
- **Q&A tests check structure, not content** — LLM answers are non-deterministic. Tests verify `ok=True` and `answer` field is present, not the exact words.
- **Auto cleanup** — The test case is deleted after the session. Test users remain (harmless).
- **Fast** — All non-LLM tests run in under 30 seconds. Tests that trigger LLM (Q&A) may take 30–90 seconds depending on the model.

---

## 3. Folder Structure

```
ISDDocumentIntelligence_V4/
├── backend/
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py          ← Session fixtures: test user, test case, sample file paths
│   │   ├── test_health.py       ← TC-H: Health check, spell checker
│   │   ├── test_auth.py         ← TC-A: Registration, login, token validation, password change
│   │   ├── test_cases.py        ← TC-C: Case CRUD, cross-user isolation
│   │   ├── test_docs.py         ← TC-D: Document upload, Q&A, clear, extraction trigger
│   │   ├── test_graph.py        ← TC-G: Entity graph list, data, clear, extract-all
│   │   ├── test_timeline.py     ← TC-T: Timeline extract, data, groups, breadcrumb
│   │   ├── test_structured.py   ← TC-S: SMAC/IR structured tables, location extraction
│   │   └── README.md            ← Quick-start guide for running tests
│   ├── pytest.ini               ← pytest configuration (verbose, short traceback, no warnings)
│   └── requirements-test.txt    ← Test dependencies: pytest, requests, pytest-timeout
│
└── TESTING.md                   ← This document

(repo root)
└── run_tests_v4.ps1             ← PowerShell runner script
```

---

## 4. Prerequisites

Before running tests, ensure the following are in place:

### 1. Backend is running

```powershell
.\start_v4_backend.ps1
```

Verify it is up:
```powershell
Invoke-RestMethod http://localhost:8001/health
```
Expected: `ok=True, service="ISD Document Intelligence"`

### 2. MSSQL is accessible

The backend connects to `ISDIntelligenceV4` on `localhost\SQLEXPRESS` (Windows Auth).
Confirm SQL Server service is running in Windows Services or via:
```powershell
Get-Service -Name 'MSSQL$SQLEXPRESS'
```

### 3. Anaconda Python is installed

Tests use `C:\Anaconda3\anaconda3\python.exe`.
If your Python path is different, edit `run_tests_v4.ps1` and change the `$PYTHON` variable.

### 4. Install test dependencies (first time only)

```powershell
C:\Anaconda3\anaconda3\python.exe -m pip install -r YAIA-main\ISDDocumentIntelligence_V4\backend\requirements-test.txt
```

Dependencies installed: `pytest`, `requests`, `pytest-timeout`

---

## 5. How to Run Tests

### Run all tests

```powershell
.\run_tests_v4.ps1
```

### Run a specific test file

```powershell
.\run_tests_v4.ps1 -TestFile test_auth.py
.\run_tests_v4.ps1 -TestFile test_cases.py
.\run_tests_v4.ps1 -TestFile test_docs.py
.\run_tests_v4.ps1 -TestFile test_graph.py
.\run_tests_v4.ps1 -TestFile test_timeline.py
.\run_tests_v4.ps1 -TestFile test_structured.py
```

### Run a specific test class or function

```powershell
# All tests in a class
.\run_tests_v4.ps1 -TestFilter "TestCaseIsolation"
.\run_tests_v4.ps1 -TestFilter "TestRegister"
.\run_tests_v4.ps1 -TestFilter "TestDocUpload"

# A single test function
.\run_tests_v4.ps1 -TestFilter "test_login_success"
.\run_tests_v4.ps1 -TestFilter "test_upload_pdf_success"
```

### Run with print output visible (for debugging)

```powershell
.\run_tests_v4.ps1 -Extra "-s"
```

### Run directly with pytest (without the wrapper script)

```powershell
cd YAIA-main\ISDDocumentIntelligence_V4\backend
C:\Anaconda3\anaconda3\python.exe -m pytest tests/ -v
C:\Anaconda3\anaconda3\python.exe -m pytest tests/test_auth.py -v -s
```

---

## 6. Test Files — Detailed Coverage

### `test_health.py` — TC-H: Health & Utilities

| Test | Description |
|------|-------------|
| `test_health_ok` | `GET /health` returns 200 and `ok=True` |
| `test_health_service_name` | Response includes `service` field |
| `test_spell_check_corrections` | Misspelled words are detected |
| `test_spell_check_correct_text` | Correctly spelled text returns no corrections |
| `test_spell_check_empty_text` | Empty string returns empty corrections dict |
| `test_spell_check_known_domain_words` | SMAC, NCRP, Aadhaar are not flagged as misspelled |

---

### `test_auth.py` — TC-A: Authentication

| Test | Description |
|------|-------------|
| `test_register_success` | New user gets 201 + JWT token |
| `test_register_duplicate_username` | Duplicate username returns 409 |
| `test_register_short_username` | Username < 3 chars returns 400 |
| `test_register_short_password` | Password < 6 chars returns 400 |
| `test_register_no_full_name` | `full_name` is optional — still succeeds |
| `test_login_success` | Correct credentials return 200 + token |
| `test_login_wrong_password` | Wrong password returns 401 |
| `test_login_unknown_user` | Non-existent user returns 401 |
| `test_login_case_insensitive_username` | Login works with uppercase username |
| `test_me_authenticated` | `GET /auth/me` with valid token returns profile |
| `test_me_no_token` | No token returns 403 |
| `test_me_bad_token` | Invalid token string returns 403 |
| `test_me_expired_token` | Malformed JWT returns 403 |
| `test_change_password_success` | Password changed; new password works, old fails |
| `test_change_password_wrong_current` | Wrong current password returns 401 |
| `test_change_password_too_short` | New password < 6 chars returns 400 |
| `test_list_users_non_admin_forbidden` | Non-admin cannot access user list → 403 |
| `test_list_users_no_token` | No token on admin endpoint → 403 |

---

### `test_cases.py` — TC-C: Case Management

| Test | Description |
|------|-------------|
| `test_list_cases_empty_or_has_test_case` | `GET /cases` returns list including the test case |
| `test_create_case_ir` | Create IR case → 201 with `collection=IR` |
| `test_create_case_smac` | Create SMAC case → 201 |
| `test_create_case_invalid_collection` | Unknown collection returns 400 |
| `test_create_case_empty_name` | Blank name returns 400 |
| `test_create_case_no_auth` | No token returns 403 |
| `test_get_case_own` | `GET /cases/{id}` returns case details |
| `test_get_case_not_found` | Unknown case_id returns 404 |
| `test_update_case_name` | `PATCH /cases/{id}` renames case |
| `test_update_case_nothing_to_update` | Empty PATCH body returns 400 |
| `test_delete_case` | `DELETE /cases/{id}` removes case; subsequent GET returns 404 |
| `test_get_other_user_case_forbidden` | User B cannot GET User A's case → 403 |
| `test_update_other_user_case_forbidden` | User B cannot PATCH User A's case → 403 |
| `test_delete_other_user_case_forbidden` | User B cannot DELETE User A's case → 403 |
| `test_list_cases_only_own` | `/cases` returns only the requesting user's cases |

---

### `test_docs.py` — TC-D: Documents

| Test | Description |
|------|-------------|
| `test_list_docs_requires_auth` | `GET /docs/list` without token → 403 |
| `test_list_docs_ok_structure` | Returns `ok=True`, `docs` is a list |
| `test_upload_pdf_success` | Upload `EMP-001_Rajesh_Kumar.pdf` → `ok=True`, `doc_id` returned |
| `test_upload_docx_success` | Upload `TestDataFormat2.docx` → `ok=True` |
| `test_upload_invalid_type` | Upload `.txt` file → `ok=False` |
| `test_upload_requires_auth` | Upload without token → 403 |
| `test_upload_appears_in_list` | After upload, `doc_id` appears in `/docs/list` |
| `test_ask_returns_answer_structure` | Q&A returns `ok=True` and non-empty `answer` |
| `test_ask_requires_auth` | Q&A without token → 403 |
| `test_ask_no_docs_returns_gracefully` | Q&A on empty collection returns gracefully |
| `test_clear_requires_auth` | `/docs/clear` without token → 403 |
| `test_clear_docs_ok` | After clear, `/docs/list` returns empty list |
| `test_extract_entities_no_pending_jobs` | `/docs/extract-entities` with no jobs → `ok=True` |
| `test_extraction_status_ok` | Status endpoint returns all required fields |

---

### `test_graph.py` — TC-G: Entity Graph

| Test | Description |
|------|-------------|
| `test_entities_requires_auth` | No token → 403 |
| `test_entities_ok_structure` | Returns `ok=True`, `entities` list, `count` |
| `test_entities_filter_by_type` | `?type=PERSON` returns filtered list |
| `test_graph_data_requires_auth` | No token → 403 |
| `test_graph_data_ok_structure` | Returns `ok=True`, `nodes` and `edges` lists |
| `test_graph_data_with_search` | `?search=test` returns filtered results |
| `test_graph_clear_requires_auth` | No token → 403 |
| `test_graph_clear_ok` | Clear returns `ok=True` |
| `test_graph_clear_then_empty` | After clear, entities list is empty |
| `test_extract_all_requires_auth` | No token → 403 |
| `test_extract_all_no_docs` | Empty case → `ok=True` with informational message |
| `test_extraction_status_structure` | All 5 status fields present |

---

### `test_timeline.py` — TC-T: Activity Timeline

| Test | Description |
|------|-------------|
| `test_extract_all_requires_auth` | No token → 403 |
| `test_extract_all_no_docs` | Empty case → `ok=True` |
| `test_extraction_status_structure` | All 5 status fields present |
| `test_extraction_status_not_running_after_empty` | `running` field is a boolean |
| `test_data_requires_auth` | No token → 403 |
| `test_data_ok_structure` | Returns `ok=True`, `activities` list, `count` |
| `test_data_filter_by_group` | Unknown group returns empty activities |
| `test_data_filter_by_search` | Search filter returns list |
| `test_groups_requires_auth` | No token → 403 |
| `test_groups_ok_structure` | Returns `ok=True`, `groups` list |
| `test_breadcrumb_requires_auth` | No token → 403 |
| `test_breadcrumb_nonexistent_tms` | Unknown TMS ID returns `ok=True`, empty result |

---

### `test_structured.py` — TC-S: Structured Data & Locations

| Test | Description |
|------|-------------|
| `test_smac_list_ok` | `GET /structured/smac` returns `ok=True`, reports list |
| `test_smac_detail_not_found` | Unknown doc_id returns `ok=False` |
| `test_ir_list_ok` | `GET /structured/ir` returns `ok=True`, reports list |
| `test_ir_detail_not_found` | Unknown doc_id returns `ok=False` |
| `test_extract_locations_requires_auth` | No token → 403 |
| `test_extract_locations_no_docs` | Empty case → `ok=True` |
| `test_location_extraction_status_structure` | All 5 status fields present |
| `test_locations_data_requires_auth` | No token → 403 |
| `test_locations_data_ok_structure` | Returns `ok=True`, `locations` list, `count` |

---

## 7. Adding New Tests

When a new endpoint is added to the backend, add a test class to the relevant file following this pattern:

```python
class TestMyNewEndpoint:

    def test_happy_path(self, base_url, auth_headers, test_case):
        """One-line description of what this verifies"""
        r = requests.post(f"{base_url}/my/endpoint", headers=auth_headers, json={
            "field": "value",
            "case_id": test_case,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "expected_field" in data

    def test_requires_auth(self, base_url):
        """Endpoint is protected — no token → 403"""
        r = requests.post(f"{base_url}/my/endpoint", json={"field": "value"})
        assert r.status_code == 403

    def test_validation_error(self, base_url, auth_headers):
        """Bad input is rejected → 400 or ok=False"""
        r = requests.post(f"{base_url}/my/endpoint", headers=auth_headers, json={})
        assert r.status_code in (400, 200)
        if r.status_code == 200:
            assert r.json()["ok"] is False
```

### Three tests to always write for every new endpoint:

1. **Happy path** — valid request, correct response structure
2. **Auth guard** — no token → 403
3. **Validation** — bad input → 400 or `ok=False`

---

## 8. Regression Checklist

Run the full suite after any major change and confirm all pass:

```powershell
.\run_tests_v4.ps1
```

| Module | Tests | Pass? |
|--------|-------|-------|
| TC-H: Health | `/health` up, spell-check working | ☐ |
| TC-A: Auth | JWT register/login/me/change-password all work | ☐ |
| TC-C: Cases | CRUD works, user isolation enforced | ☐ |
| TC-D: Docs | PDF/DOCX upload succeeds, Q&A returns answer, clear works | ☐ |
| TC-G: Graph | Entity endpoints respond, clear works | ☐ |
| TC-T: Timeline | Timeline endpoints respond, filters work | ☐ |
| TC-S: Structured | SMAC/IR tables accessible, locations endpoints respond | ☐ |

Expected output on success:
```
========================= N passed in X.XXs ==========================
=== ALL TESTS PASSED ===
```
