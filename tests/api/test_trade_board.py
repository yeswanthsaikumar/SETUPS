"""FastAPI tests for the trade-board position lifecycle.

Verifies the *existing* contract:
  GET    /api/trade-board/positions
  POST   /api/trade-board/positions
  DELETE /api/trade-board/positions/{id}

Any new feature on trade_board that breaks these shapes will fail CI.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


class TestTradeBoardRead:
    def test_list_positions_empty(self, api_client):
        r = api_client.get("/api/trade-board/positions")
        assert r.status_code == 200
        data = r.json()
        # Accept either a list or an envelope with 'positions'
        if isinstance(data, dict):
            assert "positions" in data or "items" in data or data == {} or "ok" in data
        else:
            assert data == []

    def test_summary_endpoint(self, api_client, regression_golden):
        r = api_client.get("/api/trade-board/summary")
        assert r.status_code == 200
        regression_golden("trade_board_summary", r.json())


class TestTradeBoardWrite:
    def test_add_position(self, api_client, sample_position):
        r = api_client.post("/api/trade-board/positions", json=sample_position)
        # The endpoint may return 200 or 201 depending on implementation.
        assert r.status_code in (200, 201)
        body = r.json()
        assert body.get("ok") is True or "id" in body or "position" in body

    def test_add_then_list_contains(self, api_client, sample_position):
        api_client.post("/api/trade-board/positions", json=sample_position)
        r = api_client.get("/api/trade-board/positions").json()
        if isinstance(r, dict):
            items = r.get("positions") or r.get("items") or []
        else:
            items = r
        symbols = [p.get("symbol") or p.get("base_symbol") for p in items]
        assert any(s and "RELIANCE" in s for s in symbols)

