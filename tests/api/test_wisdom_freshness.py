"""Freshness / cache-control contract tests.

Why these exist: the first rollout felt 'stuck' because
  1. reminders_for_page() defaulted to a date-seeded RNG, so every call
     returned the same trio all day long (deterministic = boring), and
  2. /api/wisdom/* responses had no cache-control headers, so Safari and
     some corporate proxies served stale quotes on every reload.

These tests lock in the fix so a future refactor can't silently restore
either behaviour.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


class TestWisdomNoCacheHeaders:
    @pytest.mark.parametrize("path", [
        "/api/wisdom/quote-of-the-day",
        "/api/wisdom/random",
        "/api/wisdom/for-page?page=board",
        "/api/wisdom/stats",
    ])
    def test_no_store_header_on_every_wisdom_endpoint(self, api_client, path):
        r = api_client.get(path)
        assert r.status_code == 200, f"{path} returned {r.status_code}"
        cc = r.headers.get("cache-control", "").lower()
        assert "no-store" in cc, \
            f"{path} should be Cache-Control: no-store, got {cc!r}"


class TestPageNudgesRotatePerCall:
    """Two consecutive calls to /for-page for the same page must NOT always
    return identical payloads.  It's acceptable to occasionally collide
    (small pool + dedup), so we sample several times and demand *some*
    variation — the hard guarantee is that the API does NOT lock onto the
    same seed all day.
    """

    def test_same_page_varies_across_calls(self, api_client):
        seen = set()
        for _ in range(8):
            r = api_client.get("/api/wisdom/for-page?page=board&count=3")
            assert r.status_code == 200
            body = r.json()
            key = tuple(q["text"] for q in body["items"])
            seen.add(key)
        assert len(seen) >= 2, (
            "for-page should rotate across calls; got identical payload "
            f"{len(seen)} times across 8 requests"
        )

    def test_different_pages_have_different_pools(self, api_client):
        """board vs. watchlist must draw from different tag pools — so at
        least one of the page-nudges should differ in any single call."""
        a = api_client.get("/api/wisdom/for-page?page=board&count=5").json()
        b = api_client.get("/api/wisdom/for-page?page=watchlist&count=5").json()
        texts_a = {q["text"] for q in a["items"]}
        texts_b = {q["text"] for q in b["items"]}
        # They should share *some* diversity — not be identical sets.
        assert texts_a != texts_b, \
            "board and watchlist returned the exact same nudges"


class TestQotdRemainsDeterministic:
    """QOTD is the one stable anchor — same date, same quote, forever."""

    def test_qotd_stable_within_same_date(self, api_client):
        a = api_client.get("/api/wisdom/quote-of-the-day").json()
        b = api_client.get("/api/wisdom/quote-of-the-day").json()
        assert a == b, (
            "QOTD must stay identical within the same day — it's literally "
            "'Quote of the Day'. Rotate is done via /api/wisdom/random."
        )

