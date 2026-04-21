"""
Integration tests for the multi-level groups + industry-groups + sector-rotation
endpoints after the enriched-taxonomy wiring.
"""
from __future__ import annotations

import pytest


class TestIndustryGroupsEndpoint:
    def test_basic_shape(self, api_client):
        r = api_client.get("/api/industry-groups")
        assert r.status_code == 200
        body = r.json()
        for k in ("groups", "total", "timestamp", "bgRefreshing",
                  "ohlcvRefreshing"):
            assert k in body

    def test_min_stocks_filter(self, api_client):
        r1 = api_client.get("/api/industry-groups?min_stocks=2").json()
        r10 = api_client.get("/api/industry-groups?min_stocks=10").json()
        assert r10["total"] <= r1["total"]

    def test_detail_handles_unknown_group(self, api_client):
        r = api_client.get("/api/industry-groups/__does_not_exist__")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            assert r.json().get("stockCount", 0) == 0


class TestGroupsLevelsEndpoint:
    def test_levels_listed(self, api_client):
        r = api_client.get("/api/groups/levels")
        assert r.status_code == 200
        body = r.json()
        keys = {lv["key"] for lv in body["levels"]}
        assert keys == {"macro", "sector", "industry",
                        "basic_industry", "theme"}
        assert isinstance(body["themes"], list)


class TestGroupsEndpoint:
    @pytest.mark.parametrize("level",
                             ["macro", "sector", "industry",
                              "basic_industry", "theme"])
    def test_each_level_returns_200(self, api_client, level):
        r = api_client.get(f"/api/groups?level={level}&min_stocks=2")
        assert r.status_code == 200
        body = r.json()
        assert body["level"] == level
        assert isinstance(body["groups"], list)

    def test_bad_level_rejected(self, api_client):
        r = api_client.get("/api/groups?level=bogus")
        assert r.status_code == 400

    def test_sort_by_rotation_accepted(self, api_client):
        r = api_client.get("/api/groups?level=industry&sort_by=rotationScore")
        assert r.status_code == 200
        assert r.json()["sortBy"] == "rotationScore"


class TestSectorRotationEndpoint:
    def test_shape(self, api_client):
        r = api_client.get("/api/sector-rotation?level=sector&top_n=5")
        assert r.status_code == 200
        body = r.json()
        assert "emerging" in body and "cooling" in body
        assert body["level"] == "sector"

    def test_top_n_upper_bounded(self, api_client):
        r = api_client.get(
            "/api/sector-rotation?level=industry&top_n=100").json()
        assert len(r["emerging"]) <= 100

    def test_invalid_level_400(self, api_client):
        r = api_client.get("/api/sector-rotation?level=foo")
        assert r.status_code == 400


class TestTaxonomyReload:
    def test_reload_ok(self, api_client):
        r = api_client.post("/api/taxonomy/reload")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["taxonomyEntries"] > 0

    def test_reload_then_groups_still_works(self, api_client):
        api_client.post("/api/taxonomy/reload")
        r = api_client.get("/api/groups?level=industry").json()
        assert isinstance(r["groups"], list)


class TestGroupsRefresh:
    def test_refresh_all(self, api_client):
        r = api_client.post("/api/groups/refresh")
        assert r.status_code == 200
        assert r.json().get("cleared") == "all"

    def test_refresh_single_level(self, api_client):
        r = api_client.post("/api/groups/refresh?level=macro")
        assert r.status_code == 200
        assert r.json().get("cleared") == "macro"

    def test_refresh_bad_level(self, api_client):
        r = api_client.post("/api/groups/refresh?level=bogus")
        assert r.status_code == 400

