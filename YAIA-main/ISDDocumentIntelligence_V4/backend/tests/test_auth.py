"""
TC-A: Authentication Endpoints
  POST /auth/register
  POST /auth/login
  GET  /auth/me
  POST /auth/change-password
  GET  /auth/users  (admin only)
"""
import time
import requests


class TestRegister:

    def test_register_success(self, base_url):
        """POST /auth/register → 201 with token and user object"""
        username = f"reg_test_{int(time.time())}"
        r = requests.post(f"{base_url}/auth/register", json={
            "username": username,
            "password": "SecurePass1!",
            "full_name": "Registration Test",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["ok"] is True
        assert "token" in data
        assert data["user"]["username"] == username

    def test_register_duplicate_username(self, base_url, auth):
        """POST /auth/register with existing username → 409"""
        username = auth["_username"]
        r = requests.post(f"{base_url}/auth/register", json={
            "username": username,
            "password": "AnotherPass1!",
        })
        assert r.status_code == 409

    def test_register_short_username(self, base_url):
        """POST /auth/register with 2-char username → 400"""
        r = requests.post(f"{base_url}/auth/register", json={
            "username": "ab",
            "password": "ValidPass1!",
        })
        assert r.status_code == 400

    def test_register_short_password(self, base_url):
        """POST /auth/register with 5-char password → 400"""
        r = requests.post(f"{base_url}/auth/register", json={
            "username": f"shortpw_{int(time.time())}",
            "password": "abc",
        })
        assert r.status_code == 400

    def test_register_no_full_name(self, base_url):
        """POST /auth/register without full_name → 201 (optional field)"""
        username = f"nofull_{int(time.time())}"
        r = requests.post(f"{base_url}/auth/register", json={
            "username": username,
            "password": "ValidPass1!",
        })
        assert r.status_code == 201
        assert r.json()["ok"] is True


class TestLogin:

    def test_login_success(self, base_url, auth):
        """POST /auth/login with correct credentials → 200 with token"""
        r = requests.post(f"{base_url}/auth/login", json={
            "username": auth["_username"],
            "password": auth["_password"],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "token" in data
        assert "user" in data

    def test_login_wrong_password(self, base_url, auth):
        """POST /auth/login with wrong password → 401"""
        r = requests.post(f"{base_url}/auth/login", json={
            "username": auth["_username"],
            "password": "WrongPassword999",
        })
        assert r.status_code == 401

    def test_login_unknown_user(self, base_url):
        """POST /auth/login with non-existent user → 401"""
        r = requests.post(f"{base_url}/auth/login", json={
            "username": "nobody_xyz_12345",
            "password": "SomePassword1!",
        })
        assert r.status_code == 401

    def test_login_case_insensitive_username(self, base_url, auth):
        """POST /auth/login username is case-insensitive"""
        r = requests.post(f"{base_url}/auth/login", json={
            "username": auth["_username"].upper(),
            "password": auth["_password"],
        })
        assert r.status_code == 200


class TestMe:

    def test_me_authenticated(self, base_url, auth_headers):
        """GET /auth/me with valid token → 200 with user profile"""
        r = requests.get(f"{base_url}/auth/me", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "user" in data
        user = data["user"]
        assert "id" in user
        assert "username" in user
        assert "role" in user

    def test_me_no_token(self, base_url):
        """GET /auth/me without token → 403"""
        r = requests.get(f"{base_url}/auth/me")
        assert r.status_code == 403

    def test_me_bad_token(self, base_url):
        """GET /auth/me with invalid token → 403"""
        r = requests.get(f"{base_url}/auth/me",
                         headers={"Authorization": "Bearer this.is.not.valid"})
        assert r.status_code == 403

    def test_me_expired_token(self, base_url):
        """GET /auth/me with a clearly malformed JWT → 403"""
        r = requests.get(f"{base_url}/auth/me",
                         headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.e30.INVALID"})
        assert r.status_code == 403


class TestChangePassword:

    def test_change_password_success(self, base_url):
        """POST /auth/change-password → can login with new password"""
        # Register a dedicated user for this test
        username = f"chgpw_{int(time.time())}"
        old_pw = "OldPass1!"
        new_pw = "NewPass2!"

        r = requests.post(f"{base_url}/auth/register", json={
            "username": username, "password": old_pw,
        })
        assert r.status_code == 201
        token = r.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Change password
        r = requests.post(f"{base_url}/auth/change-password", headers=headers, json={
            "current_password": old_pw,
            "new_password": new_pw,
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # Login with new password
        r = requests.post(f"{base_url}/auth/login", json={
            "username": username, "password": new_pw,
        })
        assert r.status_code == 200

        # Login with old password should fail
        r = requests.post(f"{base_url}/auth/login", json={
            "username": username, "password": old_pw,
        })
        assert r.status_code == 401

    def test_change_password_wrong_current(self, base_url, auth_headers):
        """POST /auth/change-password with wrong current password → 401"""
        r = requests.post(f"{base_url}/auth/change-password", headers=auth_headers, json={
            "current_password": "WrongOldPassword!",
            "new_password": "NewValidPass1!",
        })
        assert r.status_code == 401

    def test_change_password_too_short(self, base_url, auth_headers):
        """POST /auth/change-password with new password < 6 chars → 400"""
        r = requests.post(f"{base_url}/auth/change-password", headers=auth_headers, json={
            "current_password": "anything",
            "new_password": "abc",
        })
        assert r.status_code == 400


class TestAdminUsers:

    def test_list_users_non_admin_forbidden(self, base_url, auth_headers):
        """GET /auth/users as non-admin → 403"""
        r = requests.get(f"{base_url}/auth/users", headers=auth_headers)
        assert r.status_code == 403

    def test_list_users_no_token(self, base_url):
        """GET /auth/users without token → 403"""
        r = requests.get(f"{base_url}/auth/users")
        assert r.status_code == 403
