"""
TC-S: Structured Data Endpoints
  GET  /structured/smac
  GET  /structured/smac/{doc_id}
  GET  /structured/ir
  GET  /structured/ir/{doc_id}
  POST /locations/extract-all
  GET  /locations/extraction-status
  GET  /locations/data
"""
import requests


class TestStructuredSMAC:

    def test_smac_list_ok(self, base_url):
        """GET /structured/smac → ok=True, reports is list"""
        r = requests.get(f"{base_url}/structured/smac")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert isinstance(data["reports"], list)
        assert "count" in data

    def test_smac_detail_not_found(self, base_url):
        """GET /structured/smac/nonexistent_doc → ok=False"""
        r = requests.get(f"{base_url}/structured/smac/NONEXISTENT_DOC_ID_XYZ")
        assert r.status_code == 200
        assert r.json()["ok"] is False


class TestStructuredIR:

    def test_ir_list_ok(self, base_url):
        """GET /structured/ir → ok=True, reports is list"""
        r = requests.get(f"{base_url}/structured/ir")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert isinstance(data["reports"], list)
        assert "count" in data

    def test_ir_detail_not_found(self, base_url):
        """GET /structured/ir/nonexistent_doc → ok=False"""
        r = requests.get(f"{base_url}/structured/ir/NONEXISTENT_DOC_ID_XYZ")
        assert r.status_code == 200
        assert r.json()["ok"] is False


class TestLocations:

    def test_extract_locations_requires_auth(self, base_url, test_case):
        """POST /locations/extract-all without token → 403"""
        r = requests.post(f"{base_url}/locations/extract-all",
                          params={"collection": "IR", "case_id": test_case})
        assert r.status_code == 403

    def test_extract_locations_no_docs(self, base_url, auth_headers, test_case):
        """POST /locations/extract-all on empty case → ok=True"""
        requests.post(f"{base_url}/docs/clear", headers=auth_headers,
                      params={"collection": "IR", "case_id": test_case})

        r = requests.post(f"{base_url}/locations/extract-all", headers=auth_headers,
                          params={"collection": "IR", "case_id": test_case})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_location_extraction_status_structure(self, base_url):
        """GET /locations/extraction-status → all status fields present"""
        r = requests.get(f"{base_url}/locations/extraction-status")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        for field in ["running", "completed", "total", "done", "error"]:
            assert field in data, f"Missing field: {field}"

    def test_locations_data_requires_auth(self, base_url, test_case):
        """GET /locations/data without token → 403"""
        r = requests.get(f"{base_url}/locations/data", params={"case_id": test_case})
        assert r.status_code == 403

    def test_locations_data_ok_structure(self, base_url, auth_headers, test_case):
        """GET /locations/data → ok=True, locations is list"""
        r = requests.get(f"{base_url}/locations/data", headers=auth_headers,
                         params={"case_id": test_case})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert isinstance(data["locations"], list)
        assert "count" in data
