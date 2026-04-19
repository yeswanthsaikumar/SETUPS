"""FastAPI tests for watchlist + scan endpoints.

Freezes the JSON shape of:
  GET  /api/watchlist/default-list
  GET  /api/watchlist/market-phases
  GET  /api/outputs/scan/latest
  GET  /api/assistant/scan-brief
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


class TestWatchlistReadOnly:
    def test_default_list(self, api_client, regression_golden):
        r = api_client.get("/api/watchlist/default-list")
        assert r.status_code == 200
        regression_golden("watchlist_default_list", r.json())

    def test_market_phases(self, api_client, groww_mock, regression_golden):
        r = api_client.get("/api/watchlist/market-phases")
        assert r.status_code == 200
        regression_golden("watchlist_market_phases", r.json())


class TestScanOutputs:
    def test_scan_latest_no_crash(self, api_client):
        r = api_client.get("/api/outputs/scan/latest")
        # Accept 200 with empty/"no scan yet" payload or 404.
        assert r.status_code in (200, 404)

    def test_scan_brief_no_crash(self, api_client):
        r = api_client.get("/api/assistant/scan-brief")
        assert r.status_code in (200, 404)

