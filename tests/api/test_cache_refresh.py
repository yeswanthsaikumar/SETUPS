"""FastAPI tests for cache refresh endpoints.

Confirms that the Groww-only gate is enforced end-to-end: when we ask for
refresh-status of an Indian symbol, the code path never attempts yfinance
or raw Yahoo (block_network would raise).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


class TestCacheRefresh:
    def test_refresh_status_shape(self, api_client, regression_golden):
        r = api_client.get("/api/cache/refresh-status")
        assert r.status_code == 200
        regression_golden("cache_refresh_status", r.json())

    def test_refresh_symbols_groww_only_indian(self, api_client, groww_mock):
        """.NS symbols must go through Groww mock — no real network.
        Endpoint accepts a bare JSON list.
        """
        r = api_client.post("/api/cache/refresh-symbols",
                            json=["RELIANCE.NS"])
        assert r.status_code in (200, 202)
        assert "results" in r.json()

    def test_refresh_symbols_empty_list_400(self, api_client):
        r = api_client.post("/api/cache/refresh-symbols", json=[])
        assert r.status_code == 400

    def test_refresh_symbols_too_many_400(self, api_client):
        r = api_client.post("/api/cache/refresh-symbols",
                            json=[f"SYM{i}.NS" for i in range(25)])
        assert r.status_code == 400

