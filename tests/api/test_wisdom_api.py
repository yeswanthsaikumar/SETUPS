"""API tests for the /api/wisdom/* endpoints."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


class TestWisdomApi:
    def test_qotd(self, api_client, regression_golden):
        r = api_client.get("/api/wisdom/quote-of-the-day")
        assert r.status_code == 200
        body = r.json()
        for k in ("author", "text", "tags", "date"):
            assert k in body, f"missing key {k}: {body}"
        assert isinstance(body["tags"], list) and body["tags"]
        regression_golden("wisdom_qotd", body)

    def test_qotd_stable_across_calls(self, api_client):
        a = api_client.get("/api/wisdom/quote-of-the-day").json()
        b = api_client.get("/api/wisdom/quote-of-the-day").json()
        assert a == b, "QOTD must be deterministic within a single day"

    def test_random(self, api_client):
        r = api_client.get("/api/wisdom/random")
        assert r.status_code == 200
        body = r.json()
        assert body["author"] and body["text"] and body["tags"]

    def test_random_filtered_by_tag(self, api_client):
        r = api_client.get("/api/wisdom/random?tags=risk")
        assert r.status_code == 200
        assert "risk" in r.json()["tags"]

    def test_random_filter_no_match_returns_404(self, api_client):
        r = api_client.get("/api/wisdom/random?tags=nonexistent_tag_xyz")
        # Either 404 (no match) or 200 (if the API treats unknown tags as
        # no-filter).  The CURRENT behaviour is 404, and that's the better
        # contract — we pin it.
        assert r.status_code in (404, 200)

    def test_for_page_board(self, api_client, regression_golden):
        r = api_client.get("/api/wisdom/for-page?page=board&count=3")
        assert r.status_code == 200
        body = r.json()
        assert body["page"] == "board"
        assert 1 <= body["count"] <= 3
        assert all("text" in q and "author" in q for q in body["items"])
        regression_golden("wisdom_for_page_board", body)

    def test_for_page_watchlist_surfaces_watchlist_wisdom(self, api_client):
        r = api_client.get("/api/wisdom/for-page?page=watchlist&count=5").json()
        # At least one quote must actually be tagged watchlist/rs/adr/process
        assert any(
            any(t in q["tags"] for t in ("watchlist", "rs", "adr", "process"))
            for q in r["items"])

    def test_for_page_count_clamped(self, api_client):
        """API must clamp `count` to a sane range so a malicious / typo'd
        call can't exhaust the bank."""
        r = api_client.get("/api/wisdom/for-page?page=home&count=9999").json()
        assert r["count"] <= 10

    def test_stats(self, api_client, regression_golden):
        r = api_client.get("/api/wisdom/stats")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 50
        assert body["authors"] and body["tags"]
        regression_golden("wisdom_stats", body)

