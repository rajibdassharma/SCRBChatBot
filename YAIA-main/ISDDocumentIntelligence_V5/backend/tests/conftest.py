"""
Shared pytest fixtures for ISD Document Intelligence V5 integration tests.

Prerequisites:
  - Backend must be running on localhost:8002 (start_v4_backend.ps1)
  - MSSQL and ChromaDB must be accessible

Fixtures:
  base_url    — "http://localhost:8002"
  auth        — dict: Bearer headers for a freshly registered test user
  auth2       — dict: Bearer headers for a second test user (isolation tests)
  test_case   — int: case_id of a SMAC test case owned by auth user
  sample_pdf  — Path to a small test PDF
  sample_docx — Path to a small test DOCX
"""

import time
import pytest
import requests

BASE_URL = "http://localhost:8002"

# Unique suffix per test run so parallel runs don't collide
_RUN_ID = str(int(time.time()))


# ---------------------------------------------------------------------------
# Basic connectivity check — fail fast if backend is not running
# ---------------------------------------------------------------------------
def pytest_configure(config):
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code != 200:
            raise RuntimeError(f"Backend returned {r.status_code}")
    except Exception as e:
        pytest.exit(
            f"\n\nERROR: Cannot reach backend at {BASE_URL}.\n"
            f"Please start the backend first: .\\start_v4_backend.ps1\n"
            f"Detail: {e}\n",
            returncode=1,
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def auth(base_url):
    """Register + login a test user; yield Bearer headers; delete user on teardown."""
    username = f"testuser_{_RUN_ID}"
    password = "TestPass123!"
    full_name = "Test User (automated)"

    # Register
    r = requests.post(f"{base_url}/auth/register", json={
        "username": username,
        "password": password,
        "full_name": full_name,
    })
    assert r.status_code == 201, f"Register failed: {r.text}"
    data = r.json()
    assert data["ok"] is True
    token = data["token"]

    yield {
        "Authorization": f"Bearer {token}",
        "_username": username,
        "_password": password,
        "_user_id": data["user"]["id"],
    }
    # No teardown needed — test DB is separate from production


@pytest.fixture(scope="session")
def auth2(base_url):
    """Second test user for isolation/cross-user tests."""
    username = f"testuser2_{_RUN_ID}"
    password = "TestPass456!"

    r = requests.post(f"{base_url}/auth/register", json={
        "username": username,
        "password": password,
    })
    assert r.status_code == 201, f"Register user2 failed: {r.text}"
    token = r.json()["token"]

    yield {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def test_case(base_url, auth):
    """Create a SMAC test case; yield case_id; delete on teardown."""
    headers = {k: v for k, v in auth.items() if not k.startswith("_")}
    r = requests.post(f"{base_url}/cases", headers=headers, json={
        "name": f"Automated Test Case {_RUN_ID}",
        "description": "Created by pytest — safe to delete",
        "collection": "SMAC",
    })
    assert r.status_code == 201, f"Create case failed: {r.text}"
    case = r.json()["case"]
    case_id = case["id"]

    yield case_id

    # Cleanup
    requests.delete(f"{base_url}/cases/{case_id}", headers=headers)


@pytest.fixture(scope="session")
def auth_headers(auth):
    """Return only HTTP headers (strips internal _* keys)."""
    return {k: v for k, v in auth.items() if not k.startswith("_")}


@pytest.fixture(scope="session")
def sample_pdf():
    """Path to a small test PDF."""
    import os
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(
        os.path.dirname(base),
        "test_data", "employees", "EMP-001_Rajesh_Kumar.pdf"
    )


@pytest.fixture(scope="session")
def sample_docx():
    """Path to a small test DOCX."""
    import os
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(
        os.path.dirname(base),
        "test_data", "TestDataFormat2.docx"
    )
