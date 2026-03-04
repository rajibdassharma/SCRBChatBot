"""
TC-H: Health & Utility Endpoints
"""
import requests


class TestHealth:

    def test_health_ok(self, base_url):
        """GET /health → 200, ok=True"""
        r = requests.get(f"{base_url}/health")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_health_service_name(self, base_url):
        """GET /health → service field present"""
        r = requests.get(f"{base_url}/health")
        assert "service" in r.json()


class TestSpellCheck:

    def test_spell_check_corrections(self, base_url):
        """POST /spell-check → finds misspelled words"""
        r = requests.post(f"{base_url}/spell-check", json={"text": "teh quiick brwon foxe"})
        assert r.status_code == 200
        data = r.json()
        assert "corrections" in data
        # At least some of the misspelled words should be detected
        assert len(data["corrections"]) > 0

    def test_spell_check_correct_text(self, base_url):
        """POST /spell-check → no corrections for correct text"""
        r = requests.post(f"{base_url}/spell-check", json={"text": "the quick brown fox"})
        assert r.status_code == 200
        data = r.json()
        assert "corrections" in data
        # "the", "quick", "brown", "fox" are all correct
        assert len(data["corrections"]) == 0

    def test_spell_check_empty_text(self, base_url):
        """POST /spell-check → empty text returns empty corrections"""
        r = requests.post(f"{base_url}/spell-check", json={"text": ""})
        assert r.status_code == 200
        assert r.json()["corrections"] == {}

    def test_spell_check_known_domain_words(self, base_url):
        """POST /spell-check → custom domain words (SMAC, NCRP) are not flagged"""
        r = requests.post(f"{base_url}/spell-check", json={"text": "smac ncrp aadhaar"})
        assert r.status_code == 200
        # Domain words should not appear in corrections
        corrections = r.json()["corrections"]
        for word in ["smac", "ncrp", "aadhaar"]:
            assert word.lower() not in {k.lower() for k in corrections}
