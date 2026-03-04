# ISD Document Intelligence V4 — Automated Test Suite

Integration tests that run against the **live backend**. No mocking — tests the real MSSQL, ChromaDB, and API stack.

---

## Prerequisites

1. **Backend running** on port 8001:
   ```powershell
   .\start_v4_backend.ps1
   ```
2. **MSSQL** (`ISDIntelligenceV4`) accessible
3. **Anaconda Python** at `C:\Anaconda3\anaconda3\python.exe`

---

## How to Run

### All tests (recommended)
```powershell
.\run_tests_v4.ps1
```

### Specific test file
```powershell
.\run_tests_v4.ps1 -TestFile test_auth.py
.\run_tests_v4.ps1 -TestFile test_cases.py
.\run_tests_v4.ps1 -TestFile test_docs.py
```

### Specific test class or function
```powershell
.\run_tests_v4.ps1 -TestFilter "TestCaseCRUD"
.\run_tests_v4.ps1 -TestFilter "test_login_success"
```

### With print output visible
```powershell
.\run_tests_v4.ps1 -Extra "-s"
```

### Manually with pytest
```powershell
cd YAIA-main\ISDDocumentIntelligence_V4\backend
C:\Anaconda3\anaconda3\python.exe -m pytest tests/ -v
```

---

## Test Files & Coverage

| File | Code | What it tests |
|------|------|--------------|
| `test_health.py` | TC-H | `GET /health`, `POST /spell-check` |
| `test_auth.py` | TC-A | Register, Login, Me, Change Password, Admin users |
| `test_cases.py` | TC-C | Case CRUD, ownership isolation between users |
| `test_docs.py` | TC-D | Upload PDF/DOCX, List docs, Ask Q&A, Clear, Entity extraction |
| `test_graph.py` | TC-G | Entity graph: list, data, clear, extract-all, status |
| `test_timeline.py` | TC-T | Activity timeline: extract, data, groups, breadcrumb |
| `test_structured.py` | TC-S | SMAC/IR structured tables, location extraction |

**Total: ~60 test cases**

---

## Key Design Decisions

- **Integration tests** — runs against the live stack; no mocking
- **Session-scoped fixtures** — one test user + one test case per run (fast)
- **Unique usernames** — each run uses a timestamp suffix (`testuser_1234567890`) so parallel runs don't collide
- **Q&A tests check structure only** — LLM answers are non-deterministic; we verify `ok=True` and `answer` field exists, not the content
- **Auto cleanup** — the test case is deleted on teardown; test users remain (harmless in test DB)

---

## Adding New Tests

When you add a new endpoint, add a test class to the appropriate file following this pattern:

```python
class TestMyNewEndpoint:

    def test_happy_path(self, base_url, auth_headers, test_case):
        """Description of what this tests"""
        r = requests.post(f"{base_url}/my/endpoint", headers=auth_headers, json={...})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_requires_auth(self, base_url):
        """Endpoint requires authentication"""
        r = requests.post(f"{base_url}/my/endpoint", json={...})
        assert r.status_code == 403

    def test_validation_error(self, base_url, auth_headers):
        """Bad input returns 400"""
        r = requests.post(f"{base_url}/my/endpoint", headers=auth_headers, json={"bad": "data"})
        assert r.status_code == 400
```

---

## Regression Checklist (after major changes)

Run the full suite and verify:
- [ ] All TC-H tests pass (backend is healthy)
- [ ] All TC-A tests pass (JWT auth still works)
- [ ] All TC-C tests pass (case isolation not broken)
- [ ] All TC-D tests pass (document upload + Q&A pipeline intact)
- [ ] All TC-G tests pass (entity graph endpoints respond correctly)
- [ ] All TC-T tests pass (timeline endpoints respond correctly)
- [ ] All TC-S tests pass (structured data endpoints respond correctly)
