"""
Security regression tests — one test per finding in the Innspark VAPT
Preliminary Audit Report v1.0.1 (2026-04-22).

Every finding that had a code-level fix is covered here. If any test
fails in future work, that finding has regressed and must be fixed
BEFORE merging.

Coverage map:
  7.1 Weak admin credentials         -> test_7_1_*
  7.2 Improper session termination   -> test_7_2_*
  7.3 Identical tokens each login    -> test_7_3_*
  7.4 No rate limiting on auth       -> test_7_4_*
  7.5 Improper input validation      -> test_7_5_*
  7.6 Nginx version disclosure       -> deferred to production nginx

Run:  cd backend && pytest tests/ -v
Pre-req:  backend running on localhost:8000, fresh `python seed.py` run
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import pytest
import requests


# ─────────────────────────────────────────────────────────────────────
# 7.1  Weak administrative credential controls
# ─────────────────────────────────────────────────────────────────────

def test_7_1_seed_passwords_are_unique(seed_users):
    all_pw = [u["password"] for role in seed_users.values() for u in role]
    assert len(all_pw) == len(set(all_pw)), "seed passwords are not all unique"


def test_7_1_seed_passwords_meet_strength(seed_users):
    import re
    all_pw = [u["password"] for role in seed_users.values() for u in role]
    weak_common = {"admin123", "police123", "password", "password123"}
    for pw in all_pw:
        assert len(pw) >= 12, f"password too short: {pw!r}"
        assert re.search(r"[A-Z]", pw), f"missing uppercase in {pw!r}"
        assert re.search(r"[a-z]", pw), f"missing lowercase in {pw!r}"
        assert re.search(r"\d", pw), f"missing digit in {pw!r}"
        assert re.search(r"[^A-Za-z0-9]", pw), f"missing special char in {pw!r}"
        assert pw.lower() not in weak_common, f"weak common password: {pw!r}"


@pytest.mark.parametrize("bad_password,expected_phrase", [
    ("admin123",          "12 characters"),
    ("short1!",           "12 characters"),
    ("alllowercase2026!", "uppercase"),
    ("NOLOWER2026!",      "lowercase"),
    ("NoDigits!abc",      "digit"),
    ("NoSpecialChars123", "special character"),
])
def test_7_1_change_password_rejects_weak(base_url, admin_token, admin_creds,
                                           bad_password, expected_phrase):
    r = requests.post(
        f"{base_url}/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"current_password": admin_creds["password"], "new_password": bad_password},
        timeout=10,
    )
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
    assert expected_phrase.lower() in r.json()["detail"].lower(), (
        f"expected '{expected_phrase}' in error detail, got: {r.text}"
    )


# ─────────────────────────────────────────────────────────────────────
# 7.2  Improper session termination (logout does not revoke)
# ─────────────────────────────────────────────────────────────────────

def test_7_2_token_works_before_logout(base_url, admin_token):
    r = requests.get(
        f"{base_url}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    assert r.status_code == 200


def test_7_2_token_rejected_after_logout(base_url, fresh_admin_login):
    # Get a dedicated token just for this test — logging it out would
    # otherwise poison the session-scoped admin_token used by other tests
    captured = fresh_admin_login()
    logout_resp = requests.post(
        f"{base_url}/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {captured}"},
        timeout=10,
    )
    assert logout_resp.status_code == 200

    reuse = requests.get(
        f"{base_url}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {captured}"},
        timeout=10,
    )
    assert reuse.status_code == 401
    assert "revoked" in reuse.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────
# 7.3  Identical bearer token issued on every login
# ─────────────────────────────────────────────────────────────────────

def _decode_jwt_claims(token: str) -> dict:
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64))


def test_7_3_tokens_differ_across_logins(base_url, admin_creds):
    def login():
        r = requests.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": admin_creds["username"], "password": admin_creds["password"]},
            timeout=10,
        )
        assert r.status_code == 200
        return r.json()["token"]

    t1 = login()
    time.sleep(1.1)  # ensure iat advances by at least 1 second
    t2 = login()
    assert t1 != t2, "two consecutive logins produced the same token"


def test_7_3_token_has_iat_jti_exp(admin_token):
    claims = _decode_jwt_claims(admin_token)
    assert "iat" in claims, "token missing iat claim"
    assert "jti" in claims, "token missing jti claim (makes tokens session-unique)"
    assert "exp" in claims, "token missing exp claim"
    # jti should be a UUID-shaped string
    assert len(claims["jti"]) >= 32


# ─────────────────────────────────────────────────────────────────────
# 7.4  Lack of rate limiting / account lockout
# ─────────────────────────────────────────────────────────────────────

def test_7_4_account_locks_after_five_failures(base_url, lockout_user):
    username = lockout_user["username"]
    real_pw = lockout_user["password"]
    # 5 wrong attempts — all should return 401
    for i in range(5):
        r = requests.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": username, "password": f"wrong_password_{i}"},
            timeout=10,
        )
        assert r.status_code == 401, (
            f"attempt {i+1}: expected 401 (invalid creds), got {r.status_code}"
        )

    # 6th wrong attempt — account now locked (429)
    r = requests.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": username, "password": "wrong_password_6"},
        timeout=10,
    )
    assert r.status_code == 429

    # Even CORRECT password is rejected while locked
    r = requests.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": username, "password": real_pw},
        timeout=10,
    )
    assert r.status_code == 429, (
        "account was not locked against the correct password — lockout broken"
    )
    assert "locked" in r.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────
# 7.5  Improper input validation (stored XSS)
# ─────────────────────────────────────────────────────────────────────

def test_7_5_case_payload_sanitized(base_url, admin_token):
    payload = {
        "fir_no": f"XSS-AUTOTEST-{int(time.time())}",
        "registration_date": "2026-04-22",
        "case_type": "NCRP",
        "crime_type": "Internet",
        "facts": "<script>alert(1)</script>Real facts go here",
        "status": "draft",
        "unfreeze_details": [
            {"unfreeze_type": "letter", "crime_no": "javascript:alert(2)", "amount": 0}
        ],
        "refunds": [
            {"refunded": "yes",
             "victim_name": "<img src=x onerror=alert(3)>John Doe",
             "amount": 100}
        ],
    }
    r = requests.post(
        f"{base_url}/api/v1/cases/",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=payload,
        timeout=10,
    )
    assert r.status_code == 200, f"case create failed: {r.status_code} {r.text}"
    case = r.json()

    facts = case.get("facts") or ""
    crime_no = (case.get("unfreeze_details") or [{}])[0].get("crime_no") or ""
    victim = (case.get("refunds") or [{}])[0].get("victim_name") or ""

    for field_name, value in [("facts", facts), ("crime_no", crime_no), ("victim_name", victim)]:
        assert "<script" not in value.lower(), f"<script survived in {field_name}: {value!r}"
        assert "onerror" not in value.lower(), f"onerror survived in {field_name}: {value!r}"
        assert "javascript:" not in value.lower(), f"javascript: survived in {field_name}: {value!r}"

    # Clean up the test case
    case_id = case.get("id")
    if case_id:
        requests.delete(
            f"{base_url}/api/v1/cases/{case_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10,
        )
