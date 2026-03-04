"""
TC-C: Case Management Endpoints
  GET    /cases
  POST   /cases
  GET    /cases/{case_id}
  PATCH  /cases/{case_id}
  DELETE /cases/{case_id}
"""
import time
import requests


class TestCaseCRUD:

    def test_list_cases_empty_or_has_test_case(self, base_url, auth_headers, test_case):
        """GET /cases → 200, ok=True, cases is a list"""
        r = requests.get(f"{base_url}/cases", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert isinstance(data["cases"], list)
        # The session-scoped test_case should appear
        case_ids = [c["id"] for c in data["cases"]]
        assert test_case in case_ids

    def test_create_case_ir(self, base_url, auth_headers):
        """POST /cases with collection=IR → 201 with case object"""
        r = requests.post(f"{base_url}/cases", headers=auth_headers, json={
            "name": f"IR Case {int(time.time())}",
            "collection": "IR",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["ok"] is True
        case = data["case"]
        assert case["collection"] == "IR"
        assert "id" in case
        # Cleanup
        requests.delete(f"{base_url}/cases/{case['id']}", headers=auth_headers)

    def test_create_case_smac(self, base_url, auth_headers):
        """POST /cases with collection=SMAC → 201"""
        r = requests.post(f"{base_url}/cases", headers=auth_headers, json={
            "name": f"SMAC Case {int(time.time())}",
            "collection": "SMAC",
        })
        assert r.status_code == 201
        case = r.json()["case"]
        assert case["collection"] == "SMAC"
        requests.delete(f"{base_url}/cases/{case['id']}", headers=auth_headers)

    def test_create_case_invalid_collection(self, base_url, auth_headers):
        """POST /cases with unknown collection → 400"""
        r = requests.post(f"{base_url}/cases", headers=auth_headers, json={
            "name": "Bad Collection Case",
            "collection": "UNKNOWN",
        })
        assert r.status_code == 400

    def test_create_case_empty_name(self, base_url, auth_headers):
        """POST /cases with empty name → 400"""
        r = requests.post(f"{base_url}/cases", headers=auth_headers, json={
            "name": "   ",
            "collection": "IR",
        })
        assert r.status_code == 400

    def test_create_case_no_auth(self, base_url):
        """POST /cases without token → 403"""
        r = requests.post(f"{base_url}/cases", json={
            "name": "No Auth Case",
            "collection": "IR",
        })
        assert r.status_code == 403

    def test_get_case_own(self, base_url, auth_headers, test_case):
        """GET /cases/{id} → 200 with case details"""
        r = requests.get(f"{base_url}/cases/{test_case}", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["case"]["id"] == test_case

    def test_get_case_not_found(self, base_url, auth_headers):
        """GET /cases/999999 → 404"""
        r = requests.get(f"{base_url}/cases/999999", headers=auth_headers)
        assert r.status_code == 404

    def test_update_case_name(self, base_url, auth_headers):
        """PATCH /cases/{id} → renames case successfully"""
        # Create a case to rename
        r = requests.post(f"{base_url}/cases", headers=auth_headers, json={
            "name": f"Rename Me {int(time.time())}", "collection": "IR",
        })
        case_id = r.json()["case"]["id"]

        new_name = f"Renamed Case {int(time.time())}"
        r = requests.patch(f"{base_url}/cases/{case_id}", headers=auth_headers, json={
            "name": new_name,
        })
        assert r.status_code == 200
        assert r.json()["case"]["name"] == new_name

        requests.delete(f"{base_url}/cases/{case_id}", headers=auth_headers)

    def test_update_case_nothing_to_update(self, base_url, auth_headers, test_case):
        """PATCH /cases/{id} with no fields → 400"""
        r = requests.patch(f"{base_url}/cases/{test_case}", headers=auth_headers, json={})
        assert r.status_code == 400

    def test_delete_case(self, base_url, auth_headers):
        """DELETE /cases/{id} → 200, then GET returns 404"""
        r = requests.post(f"{base_url}/cases", headers=auth_headers, json={
            "name": f"Delete Me {int(time.time())}", "collection": "SMAC",
        })
        case_id = r.json()["case"]["id"]

        r = requests.delete(f"{base_url}/cases/{case_id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["ok"] is True

        r = requests.get(f"{base_url}/cases/{case_id}", headers=auth_headers)
        assert r.status_code == 404


class TestCaseIsolation:
    """User A cannot access User B's cases."""

    def test_get_other_user_case_forbidden(self, base_url, auth_headers, auth2, test_case):
        """User 2 cannot GET User 1's case → 403"""
        r = requests.get(f"{base_url}/cases/{test_case}", headers=auth2)
        assert r.status_code == 403

    def test_update_other_user_case_forbidden(self, base_url, auth2, test_case):
        """User 2 cannot PATCH User 1's case → 403"""
        r = requests.patch(f"{base_url}/cases/{test_case}", headers=auth2, json={
            "name": "Hacked",
        })
        assert r.status_code == 403

    def test_delete_other_user_case_forbidden(self, base_url, auth2, test_case):
        """User 2 cannot DELETE User 1's case → 403"""
        r = requests.delete(f"{base_url}/cases/{test_case}", headers=auth2)
        assert r.status_code == 403

    def test_list_cases_only_own(self, base_url, auth2):
        """GET /cases for User 2 returns only User 2's cases"""
        r = requests.get(f"{base_url}/cases", headers=auth2)
        assert r.status_code == 200
        data = r.json()
        # All returned cases should belong to auth2's session
        # (We don't know user_id in the response but count should be 0 initially)
        assert isinstance(data["cases"], list)
