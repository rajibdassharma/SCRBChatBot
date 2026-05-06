"""
Shared pytest fixtures for CyberFraud security regression tests.

Tests run against a LIVE running backend (default http://localhost:8000).
They read credentials from the most recent seed_credentials_*.csv file in
the backend directory — re-run `python seed.py` before running the suite
to get a fresh set of unused users.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("CFDSR_TEST_BASE", "http://localhost:8000")
BACKEND_DIR = Path(__file__).resolve().parent.parent


def _latest_credentials_csv() -> Path:
    candidates = sorted(BACKEND_DIR.glob("seed_credentials_*.csv"))
    if not candidates:
        raise FileNotFoundError(
            f"No seed_credentials_*.csv in {BACKEND_DIR}. "
            "Run `python seed.py` first to generate test credentials."
        )
    return candidates[-1]


def _load_users() -> dict[str, list[dict]]:
    """Group seed users by role: {'admin': [...], 'unit_user': [...]}."""
    path = _latest_credentials_csv()
    by_role: dict[str, list[dict]] = {"admin": [], "unit_user": []}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["role"] in by_role:
                by_role[row["role"]].append(row)
    return by_role


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def seed_users() -> dict[str, list[dict]]:
    """All seeded users grouped by role. Tests pick distinct indices so
    they don't interfere (e.g. the lockout test locks its own user)."""
    return _load_users()


@pytest.fixture(scope="session")
def admin_creds(seed_users) -> dict:
    """First admin from the CSV — used by tests that don't mutate state."""
    if not seed_users["admin"]:
        pytest.skip("No admin user in seed_credentials CSV")
    return seed_users["admin"][0]


@pytest.fixture(scope="session")
def admin_token(admin_creds, base_url) -> str:
    """Session-scoped admin token — one login shared across all tests that
    only READ with it. Tests that need to revoke/invalidate the session
    (e.g. logout revocation) should NOT use this fixture — they should
    log in separately using `fresh_admin_login`."""
    r = requests.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": admin_creds["username"], "password": admin_creds["password"]},
        timeout=10,
    )
    assert r.status_code == 200, f"admin login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture
def fresh_admin_login(admin_creds, base_url):
    """Callable that performs a new admin login every call. Use this in
    tests that will revoke or otherwise invalidate the token they receive,
    so they don't poison the shared session-scoped `admin_token`."""
    def _login() -> str:
        r = requests.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": admin_creds["username"], "password": admin_creds["password"]},
            timeout=10,
        )
        assert r.status_code == 200, f"fresh admin login failed: {r.text}"
        return r.json()["token"]
    return _login


@pytest.fixture
def lockout_user(seed_users) -> dict:
    """A unit_user reserved specifically for the rate-limit test (it will
    get locked out and can't be used by other tests)."""
    users = seed_users["unit_user"]
    if len(users) < 2:
        pytest.skip("Need at least 2 unit_user entries in seed CSV")
    # Use the LAST user so we don't collide with other tests that might
    # borrow the first unit_user row
    return users[-1]


# ─────────────────────────────────────────────────────────────────────
# Station-pair fixtures (for VAPT 7.7 + 7.8 BOLA tests)
#
# Seed CSV columns: username, password, role, station, must_change_*
# Each station has 2 users — one admin and one unit_user. The fixtures
# below find pairs grouped by `station` so the BOLA tests can act as
# distinct accounts within / across stations.
# ─────────────────────────────────────────────────────────────────────

def _users_by_station(seed_users) -> dict[str, dict[str, dict]]:
    """Return {station_name: {role: user_row}} for stations that have both
    an admin and a unit_user."""
    grouped: dict[str, dict[str, dict]] = {}
    for role, rows in seed_users.items():
        for row in rows:
            station = row.get("station") or ""
            if not station:
                continue
            grouped.setdefault(station, {})[role] = row
    # Keep only stations that have BOTH roles
    return {st: roles for st, roles in grouped.items()
            if "admin" in roles and "unit_user" in roles}


def _login(base_url: str, creds: dict) -> str:
    r = requests.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": creds["username"], "password": creds["password"]},
        timeout=10,
    )
    assert r.status_code == 200, f"login failed for {creds['username']}: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def station_pairs(seed_users) -> list[tuple[str, dict, dict]]:
    """List of (station_name, admin_row, unit_user_row) for stations that
    have both roles seeded."""
    grouped = _users_by_station(seed_users)
    return [(st, roles["admin"], roles["unit_user"]) for st, roles in grouped.items()]


@pytest.fixture
def ps_admin_login(base_url, station_pairs):
    """Callable returning a fresh JWT for the admin of station #0 (used
    paired with `ps_user_login` for VAPT 7.7 within-PS BOLA tests)."""
    if not station_pairs:
        pytest.skip("No station has both admin + unit_user in seed CSV")
    _, admin_row, _ = station_pairs[0]
    return lambda: _login(base_url, admin_row)


@pytest.fixture
def ps_user_login(base_url, station_pairs):
    """Callable returning a fresh JWT for the unit_user of the SAME station
    as `ps_admin_login`."""
    if not station_pairs:
        pytest.skip("No station has both admin + unit_user in seed CSV")
    _, _, user_row = station_pairs[0]
    return lambda: _login(base_url, user_row)


@pytest.fixture
def other_ps_admin_login(base_url, station_pairs):
    """Callable returning a fresh JWT for an admin of a DIFFERENT station
    (used for VAPT 7.8 cross-PS BOLA tests). Skips if there's only one
    station seeded."""
    if len(station_pairs) < 2:
        pytest.skip("Need at least 2 stations with admins seeded for cross-PS test")
    _, admin_row, _ = station_pairs[1]
    return lambda: _login(base_url, admin_row)
