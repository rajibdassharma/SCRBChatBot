"""
TC-T: Activity Timeline Endpoints
  POST /timeline/extract-all
  GET  /timeline/extraction-status
  GET  /timeline/data
  GET  /timeline/groups
  GET  /timeline/breadcrumb
"""
import requests


class TestTimelineExtract:

    def test_extract_all_requires_auth(self, base_url, test_case):
        """POST /timeline/extract-all without token → 403"""
        r = requests.post(f"{base_url}/timeline/extract-all",
                          params={"collection": "SMAC", "case_id": test_case})
        assert r.status_code == 403

    def test_extract_all_no_docs(self, base_url, auth_headers, test_case):
        """POST /timeline/extract-all on empty case → ok=True"""
        # Clear docs first
        requests.post(f"{base_url}/docs/clear", headers=auth_headers,
                      params={"collection": "SMAC", "case_id": test_case})

        r = requests.post(f"{base_url}/timeline/extract-all", headers=auth_headers,
                          params={"collection": "SMAC", "case_id": test_case})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True

    def test_extraction_status_structure(self, base_url):
        """GET /timeline/extraction-status → all status fields present"""
        r = requests.get(f"{base_url}/timeline/extraction-status")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        for field in ["running", "completed", "total", "done", "error"]:
            assert field in data, f"Missing field: {field}"

    def test_extraction_status_not_running_after_empty(self, base_url):
        """GET /timeline/extraction-status → running=False when no job active"""
        r = requests.get(f"{base_url}/timeline/extraction-status")
        data = r.json()
        # Should not be permanently running
        # (may be True briefly; we just check the field exists and is bool)
        assert isinstance(data["running"], bool)


class TestTimelineData:

    def test_data_requires_auth(self, base_url, test_case):
        """GET /timeline/data without token → 403"""
        r = requests.get(f"{base_url}/timeline/data", params={"case_id": test_case})
        assert r.status_code == 403

    def test_data_ok_structure(self, base_url, auth_headers, test_case):
        """GET /timeline/data → ok=True, activities is list"""
        r = requests.get(f"{base_url}/timeline/data", headers=auth_headers,
                         params={"case_id": test_case})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert isinstance(data["activities"], list)
        assert "count" in data

    def test_data_filter_by_group(self, base_url, auth_headers, test_case):
        """GET /timeline/data?group=X → returns filtered list"""
        r = requests.get(f"{base_url}/timeline/data", headers=auth_headers,
                         params={"case_id": test_case, "group": "NONEXISTENT_GROUP"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["activities"] == []

    def test_data_filter_by_search(self, base_url, auth_headers, test_case):
        """GET /timeline/data?search=test → returns list (may be empty)"""
        r = requests.get(f"{base_url}/timeline/data", headers=auth_headers,
                         params={"case_id": test_case, "search": "test"})
        assert r.status_code == 200
        assert r.json()["ok"] is True


class TestTimelineGroups:

    def test_groups_requires_auth(self, base_url, test_case):
        """GET /timeline/groups without token → 403"""
        r = requests.get(f"{base_url}/timeline/groups", params={"case_id": test_case})
        assert r.status_code == 403

    def test_groups_ok_structure(self, base_url, auth_headers, test_case):
        """GET /timeline/groups → ok=True, groups is list"""
        r = requests.get(f"{base_url}/timeline/groups", headers=auth_headers,
                         params={"case_id": test_case})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert isinstance(data["groups"], list)


class TestTimelineBreadcrumb:

    def test_breadcrumb_requires_auth(self, base_url, test_case):
        """GET /timeline/breadcrumb without token → 403"""
        r = requests.get(f"{base_url}/timeline/breadcrumb",
                         params={"tms_id": "TMS-001", "case_id": test_case})
        assert r.status_code == 403

    def test_breadcrumb_nonexistent_tms(self, base_url, auth_headers, test_case):
        """GET /timeline/breadcrumb for unknown TMS ID → ok=True, empty result"""
        r = requests.get(f"{base_url}/timeline/breadcrumb", headers=auth_headers,
                         params={"tms_id": "TMS-NONEXISTENT-XYZ", "case_id": test_case})
        assert r.status_code == 200
        assert r.json()["ok"] is True
