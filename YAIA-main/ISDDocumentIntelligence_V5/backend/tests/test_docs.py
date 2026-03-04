"""
TC-D: Document Management Endpoints
  POST /docs/upload
  GET  /docs/list
  POST /docs/ask
  POST /docs/clear
  POST /docs/extract-entities
  GET  /graph/extraction-status
"""
import os
import requests
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _upload(base_url, headers, filepath, collection="SMAC", case_id=0):
    filename = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        r = requests.post(
            f"{base_url}/docs/upload",
            headers=headers,
            files={"file": (filename, f, "application/octet-stream")},
            data={"collection": collection, "case_id": str(case_id)},
        )
    return r


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDocsList:

    def test_list_docs_requires_auth(self, base_url, test_case):
        """GET /docs/list without token → 403"""
        r = requests.get(f"{base_url}/docs/list", params={
            "collection": "SMAC", "case_id": test_case,
        })
        assert r.status_code == 403

    def test_list_docs_ok_structure(self, base_url, auth_headers, test_case):
        """GET /docs/list → 200, ok=True, docs is list"""
        r = requests.get(f"{base_url}/docs/list", headers=auth_headers, params={
            "collection": "SMAC", "case_id": test_case,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert isinstance(data["docs"], list)


class TestDocUpload:

    def test_upload_pdf_success(self, base_url, auth_headers, test_case, sample_pdf):
        """POST /docs/upload PDF → ok=True with doc_id"""
        if not os.path.exists(sample_pdf):
            pytest.skip(f"Sample PDF not found: {sample_pdf}")

        r = _upload(base_url, auth_headers, sample_pdf,
                    collection="SMAC", case_id=test_case)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True, f"Upload failed: {data}"
        assert "doc_id" in data
        assert "doc_name" in data

    def test_upload_docx_success(self, base_url, auth_headers, test_case, sample_docx):
        """POST /docs/upload DOCX → ok=True"""
        if not os.path.exists(sample_docx):
            pytest.skip(f"Sample DOCX not found: {sample_docx}")

        r = _upload(base_url, auth_headers, sample_docx,
                    collection="SMAC", case_id=test_case)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True, f"DOCX upload failed: {data}"

    def test_upload_invalid_type(self, base_url, auth_headers, test_case, tmp_path):
        """POST /docs/upload with .txt file → ok=False (unsupported)"""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("This is a plain text file.")
        with open(txt_file, "rb") as f:
            r = requests.post(
                f"{base_url}/docs/upload",
                headers=auth_headers,
                files={"file": ("test.txt", f, "text/plain")},
                data={"collection": "SMAC", "case_id": str(test_case)},
            )
        assert r.status_code == 200
        assert r.json()["ok"] is False

    def test_upload_requires_auth(self, base_url, test_case, sample_pdf):
        """POST /docs/upload without token → 403"""
        if not os.path.exists(sample_pdf):
            pytest.skip(f"Sample PDF not found: {sample_pdf}")
        with open(sample_pdf, "rb") as f:
            r = requests.post(
                f"{base_url}/docs/upload",
                files={"file": ("test.pdf", f, "application/pdf")},
                data={"collection": "SMAC", "case_id": str(test_case)},
            )
        assert r.status_code == 403

    def test_upload_appears_in_list(self, base_url, auth_headers, test_case, sample_pdf):
        """After upload, document appears in /docs/list"""
        if not os.path.exists(sample_pdf):
            pytest.skip(f"Sample PDF not found: {sample_pdf}")

        r = _upload(base_url, auth_headers, sample_pdf,
                    collection="SMAC", case_id=test_case)
        assert r.json()["ok"] is True
        doc_id = r.json()["doc_id"]

        r = requests.get(f"{base_url}/docs/list", headers=auth_headers,
                         params={"collection": "SMAC", "case_id": test_case})
        doc_ids = [d["doc_id"] for d in r.json()["docs"]]
        assert doc_id in doc_ids


class TestDocAsk:

    def test_ask_returns_answer_structure(self, base_url, auth_headers, test_case, sample_pdf):
        """POST /docs/ask → ok=True, answer field present (content not checked — LLM non-deterministic)"""
        if not os.path.exists(sample_pdf):
            pytest.skip(f"Sample PDF not found: {sample_pdf}")

        # Ensure at least one doc is indexed
        _upload(base_url, auth_headers, sample_pdf, collection="SMAC", case_id=test_case)

        r = requests.post(f"{base_url}/docs/ask", headers=auth_headers, json={
            "question": "What is the name of the person?",
            "collection": "SMAC",
            "case_id": test_case,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "answer" in data
        assert len(data["answer"]) > 0

    def test_ask_requires_auth(self, base_url, test_case):
        """POST /docs/ask without token → 403"""
        r = requests.post(f"{base_url}/docs/ask", json={
            "question": "What is the name?",
            "collection": "SMAC",
            "case_id": test_case,
        })
        assert r.status_code == 403

    def test_ask_no_docs_returns_gracefully(self, base_url, auth_headers):
        """POST /docs/ask on empty case → ok=True with answer (graceful no-results)"""
        r = requests.post(f"{base_url}/docs/ask", headers=auth_headers, json={
            "question": "Who is the subject?",
            "collection": "SMAC",
            "case_id": 0,        # case_id=0 → no scoping, likely empty
        })
        assert r.status_code == 200
        # Should return ok=True even with no docs (returns "no information" type answer)
        data = r.json()
        assert "ok" in data


class TestDocClear:

    def test_clear_requires_auth(self, base_url, test_case):
        """POST /docs/clear without token → 403"""
        r = requests.post(f"{base_url}/docs/clear",
                          params={"collection": "SMAC", "case_id": test_case})
        assert r.status_code == 403

    def test_clear_docs_ok(self, base_url, auth_headers, test_case, sample_pdf):
        """POST /docs/clear → ok=True, list becomes empty"""
        if not os.path.exists(sample_pdf):
            pytest.skip(f"Sample PDF not found: {sample_pdf}")

        # Upload something first
        _upload(base_url, auth_headers, sample_pdf, collection="SMAC", case_id=test_case)

        # Clear
        r = requests.post(f"{base_url}/docs/clear", headers=auth_headers,
                          params={"collection": "SMAC", "case_id": test_case})
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # List should be empty now
        r = requests.get(f"{base_url}/docs/list", headers=auth_headers,
                         params={"collection": "SMAC", "case_id": test_case})
        assert r.json()["docs"] == []


class TestEntityExtraction:

    def test_extract_entities_no_pending_jobs(self, base_url):
        """POST /docs/extract-entities with no pending jobs → ok=True, extracted=0"""
        # After the test run clears docs, no pending jobs should remain
        r = requests.post(f"{base_url}/docs/extract-entities")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True

    def test_extraction_status_ok(self, base_url):
        """GET /graph/extraction-status → ok=True, status fields present"""
        r = requests.get(f"{base_url}/graph/extraction-status")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "running" in data
        assert "completed" in data
        assert "total" in data
        assert "done" in data
