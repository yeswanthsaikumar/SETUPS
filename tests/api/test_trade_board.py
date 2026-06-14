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


class TestTrailingStopAutomation:
    def test_partial_exit_exit_all_closes_t1_hit_position(self, api_client):
        payload = {
            "symbol": "HDFCBANK.NS",
            "name": "HDFC Bank",
            "entry": 100.0,
            "quantity": 10,
            "sl": 90.0,
            "entry_date": "2026-04-15",
            "status": "OPEN",
        }
        add = api_client.post("/api/trade-board/positions", json=payload).json()
        pid = add["position"]["id"]

        # User marks target hit first, then wants to exit all remaining shares.
        mark_t1 = api_client.put(
            f"/api/trade-board/positions/{pid}",
            json={"status": "T1_HIT"},
        )
        assert mark_t1.status_code == 200

        pe = api_client.post(
            f"/api/trade-board/positions/{pid}/partial-exit",
            json={"exit_all": True, "price": 112.0, "reason": "T2_HIT", "date": "2026-04-16"},
        )
        assert pe.status_code == 200
        body = pe.json()
        assert body["remaining"] == 0
        assert body["position"]["status"] == "CLOSED"
        assert body["position"]["remaining_quantity"] == 0
        assert body["position"]["realized_pl"] == 120.0

    def test_auto_close_on_trailing_stop_breach(self, api_client, monkeypatch):
        import main as api_main

        payload = {
            "symbol": "RELIANCE.NS",
            "name": "Reliance",
            "entry": 100.0,
            "quantity": 10,
            "sl": 90.0,
            "entry_date": "2026-04-15",
            "status": "OPEN",
        }
        add = api_client.post("/api/trade-board/positions", json=payload).json()
        pid = add["position"]["id"]

        # SL must be "armed" first (price trades above SL at least once),
        # then a strict breach triggers SL_HIT.
        monkeypatch.setattr(api_main, "_get_price_info", lambda *a, **k: (95.0, 90.0, "2026-04-20"))
        r1 = api_client.get("/api/trade-board/positions/enriched")
        assert r1.status_code == 200

        monkeypatch.setattr(api_main, "_get_price_info", lambda *a, **k: (88.0, 90.0, "2026-04-20"))

        r = api_client.get("/api/trade-board/positions/enriched")
        assert r.status_code == 200
        pos = next(p for p in r.json()["positions"] if p["id"] == pid)
        assert pos["status"] == "SL_HIT"
        assert pos["exit_price"] == 88.0
        assert pos["remaining_quantity"] == 0
        assert pos["realized_pl"] == -120.0

    def test_equity_includes_partial_and_final_close_legs(self, api_client):
        payload = {
            "symbol": "RELIANCE.NS",
            "name": "Reliance",
            "entry": 100.0,
            "quantity": 10,
            "sl": 90.0,
            "entry_date": "2026-04-15",
            "status": "OPEN",
        }
        add = api_client.post("/api/trade-board/positions", json=payload).json()
        pid = add["position"]["id"]

        pe = api_client.post(
            f"/api/trade-board/positions/{pid}/partial-exit",
            json={"quantity": 4, "price": 115.0, "reason": "T1_HIT", "date": "2026-04-16"},
        )
        assert pe.status_code == 200

        close = api_client.put(
            f"/api/trade-board/positions/{pid}",
            json={"status": "CLOSED", "exit_price": 110.0, "exit_date": "2026-04-17"},
        )
        assert close.status_code == 200

        eq = api_client.get("/api/trade-board/equity")
        assert eq.status_code == 200
        body = eq.json()
        assert body["totalPl"] == 120.0
        # 4*(115-100)=60 partial + 6*(110-100)=60 final close leg.
        assert any(pt.get("date") == "2026-04-17" and pt.get("pl") == 60.0 for pt in body["curve"])

    def test_auto_close_through_regular_positions_endpoint(self, api_client, monkeypatch):
        """Verify SL_HIT closure works through regular /positions endpoint too."""
        import main as api_main

        payload = {
            "symbol": "INFY.NS",
            "name": "Infosys",
            "entry": 200.0,
            "quantity": 5,
            "sl": 180.0,
            "entry_date": "2026-04-15",
            "status": "OPEN",
        }
        add = api_client.post("/api/trade-board/positions", json=payload).json()
        pid = add["position"]["id"]

        # Arm above SL, then breach below SL.
        monkeypatch.setattr(api_main, "_get_price_info", lambda *a, **k: (190.0, 185.0, "2026-04-20"))
        r1 = api_client.get("/api/trade-board/positions")
        assert r1.status_code == 200

        monkeypatch.setattr(api_main, "_get_price_info", lambda *a, **k: (175.0, 185.0, "2026-04-20"))

        # Call regular endpoint instead of enriched
        r = api_client.get("/api/trade-board/positions")
        assert r.status_code == 200
        pos = next(p for p in r.json()["positions"] if p["id"] == pid)
        assert pos["status"] == "SL_HIT"
        assert pos["exit_price"] == 175.0
        assert pos["realized_pl"] == -125.0  # (175-200)*5

    def test_auto_close_with_zero_stop_loss(self, api_client, monkeypatch):
        """Edge case: Position with no SL should not auto-close."""
        import main as api_main

        payload = {
            "symbol": "TCS.NS",
            "name": "TCS",
            "entry": 150.0,
            "quantity": 2,
            "sl": 0.0,  # No stop loss
            "entry_date": "2026-04-15",
            "status": "OPEN",
        }
        add = api_client.post("/api/trade-board/positions", json=payload).json()
        pid = add["position"]["id"]

        # Price drops significantly
        monkeypatch.setattr(api_main, "_get_price_info", lambda *a, **k: (50.0, 100.0, "2026-04-20"))

        r = api_client.get("/api/trade-board/positions/enriched")
        assert r.status_code == 200
        pos = next(p for p in r.json()["positions"] if p["id"] == pid)
        # Position should remain OPEN because SL is 0
        assert pos["status"] == "OPEN"

    def test_auto_close_partial_exit_then_sl_hit(self, api_client, monkeypatch):
        """Verify SL_HIT works after partial exits."""
        import main as api_main

        payload = {
            "symbol": "RELIANCE.NS",
            "name": "Reliance",
            "entry": 100.0,
            "quantity": 10,
            "sl": 90.0,
            "entry_date": "2026-04-15",
            "status": "OPEN",
        }
        add = api_client.post("/api/trade-board/positions", json=payload).json()
        pid = add["position"]["id"]

        # First partial exit
        pe = api_client.post(
            f"/api/trade-board/positions/{pid}/partial-exit",
            json={"quantity": 3, "price": 110.0, "reason": "T1_HIT", "date": "2026-04-16"},
        )
        assert pe.status_code == 200

        # Arm above SL, then drop below SL.
        monkeypatch.setattr(api_main, "_get_price_info", lambda *a, **k: (95.0, 90.0, "2026-04-20"))
        r1 = api_client.get("/api/trade-board/positions/enriched")
        assert r1.status_code == 200

        monkeypatch.setattr(api_main, "_get_price_info", lambda *a, **k: (88.0, 90.0, "2026-04-20"))

        r = api_client.get("/api/trade-board/positions/enriched")
        assert r.status_code == 200
        pos = next(p for p in r.json()["positions"] if p["id"] == pid)
        assert pos["status"] == "SL_HIT"
        assert pos["remaining_quantity"] == 0
        # realized_pl = 3*(110-100) + 7*(88-100) = 30 - 84 = -54
        assert pos["realized_pl"] == -54.0

    def test_manual_sl_update_is_not_overwritten_by_trailing(self, api_client, monkeypatch):
        """User-updated SL should persist (not be immediately re-trailed)."""
        import main as api_main

        payload = {
            "symbol": "RELIANCE.NS",
            "name": "Reliance",
            "entry": 100.0,
            "quantity": 10,
            "sl": 90.0,
            "entry_date": "2026-04-15",
            "status": "OPEN",
        }
        add = api_client.post("/api/trade-board/positions", json=payload).json()
        pid = add["position"]["id"]

        # User manually updates SL to 95.
        u = api_client.put(f"/api/trade-board/positions/{pid}", json={"sl": 95.0})
        assert u.status_code == 200

        # Make trailing candidate want to move SL (risk=10 so candidate=min(entry, cmp-10)=100),
        # but manual lock should prevent overwrite.
        monkeypatch.setattr(api_main, "_read_ohlcv", lambda *a, **k: [])
        monkeypatch.setattr(api_main, "_get_price_info", lambda *a, **k: (120.0, 110.0, "2026-04-20"))

        r = api_client.get("/api/trade-board/positions")
        assert r.status_code == 200
        pos = next(p for p in r.json()["positions"] if p["id"] == pid)
        assert pos["sl"] == 95.0

    def test_reopen_mistakenly_closed_position_restores_remaining_qty(self, api_client):
        payload = {
            "symbol": "SBIN.NS",
            "name": "SBI",
            "entry": 100.0,
            "quantity": 5,
            "sl": 90.0,
            "entry_date": "2026-04-15",
            "status": "OPEN",
        }
        add = api_client.post("/api/trade-board/positions", json=payload).json()
        pid = add["position"]["id"]

        close = api_client.put(
            f"/api/trade-board/positions/{pid}",
            json={"status": "CLOSED", "exit_price": 103.0, "exit_date": "2026-04-16"},
        )
        assert close.status_code == 200

        reopen = api_client.put(
            f"/api/trade-board/positions/{pid}",
            json={"status": "OPEN"},
        )
        assert reopen.status_code == 200
        pos = reopen.json()["position"]
        assert pos["status"] == "OPEN"
        assert pos["remaining_quantity"] == 5
        assert pos.get("exit_price") is None
        assert pos.get("exit_date") is None
        assert pos.get("realized_pl", 0) == 0

    def test_reopen_with_partial_history_normalizes_to_partial(self, api_client):
        payload = {
            "symbol": "ICICIBANK.NS",
            "name": "ICICI Bank",
            "entry": 100.0,
            "quantity": 10,
            "sl": 90.0,
            "entry_date": "2026-04-15",
            "status": "OPEN",
        }
        add = api_client.post("/api/trade-board/positions", json=payload).json()
        pid = add["position"]["id"]

        pe = api_client.post(
            f"/api/trade-board/positions/{pid}/partial-exit",
            json={"quantity": 4, "price": 110.0, "reason": "T1_HIT", "date": "2026-04-16"},
        )
        assert pe.status_code == 200

        close = api_client.put(
            f"/api/trade-board/positions/{pid}",
            json={"status": "CLOSED", "exit_price": 105.0, "exit_date": "2026-04-17"},
        )
        assert close.status_code == 200

        reopen = api_client.put(
            f"/api/trade-board/positions/{pid}",
            json={"status": "OPEN"},
        )
        assert reopen.status_code == 200
        pos = reopen.json()["position"]
        assert pos["status"] == "PARTIAL"
        assert pos["remaining_quantity"] == 6
        # Reopen keeps realized from already-booked partial exits only.
        assert pos["realized_pl"] == 40.0

    def test_reopen_fully_exit_all_restores_full_qty(self, api_client):
        """When exit_all completely consumed all shares, reopening must restore full quantity by clearing partial exits."""
        payload = {
            "symbol": "WIPRO.NS",
            "name": "Wipro",
            "entry": 100.0,
            "quantity": 8,
            "sl": 90.0,
            "entry_date": "2026-04-15",
            "status": "OPEN",
        }
        add = api_client.post("/api/trade-board/positions", json=payload).json()
        pid = add["position"]["id"]

        # exit_all — closes all 8 shares at once
        pe = api_client.post(
            f"/api/trade-board/positions/{pid}/partial-exit",
            json={"exit_all": True, "price": 110.0, "reason": "T2_HIT", "date": "2026-04-17"},
        )
        assert pe.status_code == 200
        assert pe.json()["remaining"] == 0

        # Now user realizes it was a mistake and reopens
        reopen = api_client.put(
            f"/api/trade-board/positions/{pid}",
            json={"status": "OPEN"},
        )
        assert reopen.status_code == 200
        pos = reopen.json()["position"]
        assert pos["status"] == "OPEN"
        assert pos["remaining_quantity"] == 8  # full qty restored
        assert pos.get("exit_price") is None
        assert pos.get("realized_pl", 0) == 0  # partial exits cleared


class TestTradeBoardChartRs:
    def test_chart_includes_rs_snapshot_for_india(self, api_client, monkeypatch):
        import main as api_main

        stock = [
            {"date": "2026-04-01", "open": 99, "high": 101, "low": 98, "close": 100, "volume": 1000},
            {"date": "2026-04-02", "open": 100, "high": 103, "low": 99, "close": 102, "volume": 1100},
            {"date": "2026-04-03", "open": 102, "high": 106, "low": 101, "close": 105, "volume": 1200},
            {"date": "2026-04-04", "open": 105, "high": 108, "low": 104, "close": 107, "volume": 1300},
        ]
        nifty = [
            {"date": "2026-04-01", "open": 200, "high": 202, "low": 199, "close": 200, "volume": 10},
            {"date": "2026-04-03", "open": 201, "high": 203, "low": 200, "close": 202, "volume": 10},
            {"date": "2026-04-04", "open": 202, "high": 205, "low": 201, "close": 204, "volume": 10},
        ]
        mid = [
            {"date": "2026-04-01", "open": 300, "high": 302, "low": 299, "close": 300, "volume": 10},
            {"date": "2026-04-02", "open": 300, "high": 303, "low": 299, "close": 301, "volume": 10},
            {"date": "2026-04-03", "open": 301, "high": 304, "low": 300, "close": 303, "volume": 10},
            {"date": "2026-04-04", "open": 303, "high": 306, "low": 302, "close": 305, "volume": 10},
        ]
        sml = [
            {"date": "2026-04-01", "open": 150, "high": 151, "low": 149, "close": 150, "volume": 10},
            {"date": "2026-04-02", "open": 150, "high": 151, "low": 149, "close": 149, "volume": 10},
            {"date": "2026-04-03", "open": 149, "high": 150, "low": 148, "close": 148, "volume": 10},
            {"date": "2026-04-04", "open": 148, "high": 149, "low": 147, "close": 147, "volume": 10},
        ]

        def fake_read(sym, days=0, market="india"):
            if sym == "ABC.NS":
                return stock
            if sym == "^NSEI":
                return nifty
            if sym == "NIFTY_MIDCAP_100.NS":
                return mid
            if sym == "^CNXSC":
                return sml
            if sym == "^NSMIDCAP":
                return mid
            return []

        monkeypatch.setattr(api_main, "_read_ohlcv", fake_read)
        monkeypatch.setattr(api_main, "_get_live_price", lambda *a, **k: None)

        r = api_client.get("/api/trade-board/chart/ABC.NS?days=120&market=india")
        assert r.status_code == 200
        body = r.json()
        assert "rsLines" in body and "rsSnapshot" in body
        assert len(body["rsLines"]["nifty50"]) == 4  # 2026-04-02 aligns using 2026-04-01 benchmark close
        snap = body["rsSnapshot"]
        assert snap.get("leader") in ("nifty50", "niftyMidcap100", "niftySmallcap100")
        assert isinstance(snap.get("benchmarks"), dict)
        assert snap["benchmarks"]["nifty50"]["points"] >= 2

    def test_rs_line_skips_stale_benchmark_gaps(self):
        import main as api_main

        stock_rows = [
            {"date": "2026-04-10", "close": 100},
            {"date": "2026-04-11", "close": 105},
        ]
        bench_rows = [
            {"date": "2026-04-01", "close": 1000},
            {"date": "2026-04-02", "close": 1005},
        ]
        rs = api_main._rs_line_vs_benchmark(stock_rows, bench_rows)
        assert rs == []


