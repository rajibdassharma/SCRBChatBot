"""
TC-G: Entity Graph Endpoints
  GET    /graph/entities
  GET    /graph/data
  DELETE /graph/clear
  POST   /graph/extract-all
  GET    /graph/extraction-status
"""
import requests


class TestGraphEntities:

    def test_entities_requires_auth(self, base_url, test_case):
        """GET /graph/entities without token → 403"""
        r = requests.get(f"{base_url}/graph/entities", params={"case_id": test_case})
        assert r.status_code == 403

    def test_entities_ok_structure(self, base_url, auth_headers, test_case):
        """GET /graph/entities → ok=True, entities is list"""
        r = requests.get(f"{base_url}/graph/entities", headers=auth_headers,
                         params={"case_id": test_case})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert isinstance(data["entities"], list)
        assert "count" in data

    def test_entities_filter_by_type(self, base_url, auth_headers, test_case):
        """GET /graph/entities?type=PERSON → returns list (may be empty)"""
        r = requests.get(f"{base_url}/graph/entities", headers=auth_headers,
                         params={"case_id": test_case, "type": "PERSON"})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert isinstance(data["entities"], list)


class TestGraphData:

    def test_graph_data_requires_auth(self, base_url, test_case):
        """GET /graph/data without token → 403"""
        r = requests.get(f"{base_url}/graph/data", params={"case_id": test_case})
        assert r.status_code == 403

    def test_graph_data_ok_structure(self, base_url, auth_headers, test_case):
        """GET /graph/data → ok=True, nodes and edges present"""
        r = requests.get(f"{base_url}/graph/data", headers=auth_headers,
                         params={"case_id": test_case, "limit": 100})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    def test_graph_data_with_search(self, base_url, auth_headers, test_case):
        """GET /graph/data?search=test → returns filtered results"""
        r = requests.get(f"{base_url}/graph/data", headers=auth_headers,
                         params={"case_id": test_case, "search": "test"})
        assert r.status_code == 200
        assert r.json()["ok"] is True


class TestGraphClear:

    def test_graph_clear_requires_auth(self, base_url, test_case):
        """DELETE /graph/clear without token → 403"""
        r = requests.delete(f"{base_url}/graph/clear", params={"case_id": test_case})
        assert r.status_code == 403

    def test_graph_clear_ok(self, base_url, auth_headers, test_case):
        """DELETE /graph/clear → ok=True"""
        r = requests.delete(f"{base_url}/graph/clear", headers=auth_headers,
                            params={"case_id": test_case})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_graph_clear_then_empty(self, base_url, auth_headers, test_case):
        """After clear, entities list is empty"""
        requests.delete(f"{base_url}/graph/clear", headers=auth_headers,
                        params={"case_id": test_case})
        r = requests.get(f"{base_url}/graph/entities", headers=auth_headers,
                         params={"case_id": test_case})
        assert r.json()["entities"] == []


class TestGraphExtractAll:

    def test_extract_all_requires_auth(self, base_url, test_case):
        """POST /graph/extract-all without token → 403"""
        r = requests.post(f"{base_url}/graph/extract-all",
                          params={"collection": "SMAC", "case_id": test_case})
        assert r.status_code == 403

    def test_extract_all_no_docs(self, base_url, auth_headers, test_case):
        """POST /graph/extract-all on empty case → ok=True, message about no docs"""
        # Ensure empty (clear first)
        requests.post(f"{base_url}/docs/clear", headers=auth_headers,
                      params={"collection": "SMAC", "case_id": test_case})

        r = requests.post(f"{base_url}/graph/extract-all", headers=auth_headers,
                          params={"collection": "SMAC", "case_id": test_case})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "message" in data

    def test_extraction_status_structure(self, base_url):
        """GET /graph/extraction-status → all status fields present"""
        r = requests.get(f"{base_url}/graph/extraction-status")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        for field in ["running", "completed", "total", "done", "error"]:
            assert field in data, f"Missing field: {field}"
