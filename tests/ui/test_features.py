"""Comprehensive UI-tier feature verification.

Each class covers one feature area of the app. Tests use Playwright's
browser to either:
  (a) load the real HTML page and assert key DOM is present, or
  (b) hit the backing API via the browser's request context — proving the
      end-to-end HTTP stack (uvicorn + FastAPI + app code) is healthy.

Why this matters: the unit/api tiers use FastAPI's in-memory TestClient.
These tests use a real TCP socket to a real uvicorn process, catching
class loading, static-mount, and middleware bugs that TestClient misses.

Run:   pytest -m ui
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.network]  # localhost sockets


# ── 1. Static pages ────────────────────────────────────────────────────────

class TestPages:
    @pytest.mark.parametrize("path,must_contain", [
        ("/",         ["<html", "</body>"]),
        ("/board",    ["<html", "</body>"]),
        ("/breadth",  ["<html"]),
        ("/sector",   ["<html"]),
        ("/trades",   ["<html"]),
    ])
    def test_page_renders(self, live_server, page, path, must_contain):
        resp = page.goto(live_server + path)
        assert resp is not None and resp.status < 500, \
            f"{path} → {resp.status if resp else 'no-resp'}"
        html = page.content()
        for needle in must_contain:
            assert needle in html, f"{path} missing {needle!r}"


# ── 2. Health & meta ───────────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self, live_server, page):
        r = page.request.get(live_server + "/api/health")
        assert r.ok
        body = r.json()
        # At least one of these keys is always present.
        assert any(k in body for k in ("ok", "status", "version"))

    def test_backup_status(self, live_server, page):
        r = page.request.get(live_server + "/api/backup/status")
        assert r.status in (200, 404, 503)  # optional feature


# ── 3. VPN / Proxy feature ─────────────────────────────────────────────────

class TestVpnFeature:
    def test_status_disabled_on_boot(self, live_server, page):
        r = page.request.get(live_server + "/api/vpn/status")
        assert r.ok
        assert r.json().get("enabled") is False

    def test_disable_idempotent(self, live_server, page):
        r1 = page.request.post(live_server + "/api/vpn/disable")
        r2 = page.request.post(live_server + "/api/vpn/disable")
        assert r1.ok and r2.ok

    def test_set_custom_proxy(self, live_server, page):
        r = page.request.post(
            live_server + "/api/vpn/config",
            data={"provider": "custom",
                  "custom_proxy_url": "http://u:p@127.0.0.1:3128"},
        )
        assert r.ok, r.text()

    def test_invalid_provider_rejected(self, live_server, page):
        r = page.request.post(
            live_server + "/api/vpn/config",
            data={"provider": "garbage-provider"},
        )
        assert r.status in (400, 422)


# ── 4. Groww data source verification ─────────────────────────────────────

class TestGrowwVerify:
    def test_verify_endpoint(self, live_server, page):
        r = page.request.get(live_server + "/api/groww/verify?symbol=RELIANCE")
        assert r.ok
        body = r.json()
        assert "ok" in body
        # Groww-only mode should be on by default.
        assert body.get("mode_groww_only") in (True, False)  # key must exist


# ── 5. Trade board CRUD ────────────────────────────────────────────────────

class TestTradeBoard:
    def test_summary(self, live_server, page):
        r = page.request.get(live_server + "/api/trade-board/summary")
        assert r.ok
        assert "stats" in r.json()

    def test_list_positions_shape(self, live_server, page):
        r = page.request.get(live_server + "/api/trade-board/positions")
        assert r.ok
        body = r.json()
        assert "positions" in body and isinstance(body["positions"], list)

    def test_add_and_delete_position(self, live_server, page, sample_position):
        # NOTE: this hits the *real* trade_data/ directory on disk — so we
        # use an obviously-test symbol and clean up after ourselves.
        sample_position["symbol"] = "UITEST.NS"
        sample_position["notes"] = "ui-test-delete-me"

        add = page.request.post(
            live_server + "/api/trade-board/positions",
            data=sample_position,
        )
        assert add.ok, add.text()
        pos_id = add.json().get("id") or add.json().get("position", {}).get("id")
        assert pos_id, f"no id returned: {add.json()}"

        # Read-back
        got = page.request.get(live_server + "/api/trade-board/positions").json()
        symbols = [p.get("symbol") for p in got.get("positions", [])]
        assert "UITEST.NS" in symbols

        # Cleanup
        rm = page.request.delete(
            live_server + f"/api/trade-board/positions/{pos_id}")
        assert rm.ok, rm.text()

    def test_watchlist_list(self, live_server, page):
        r = page.request.get(live_server + "/api/trade-board/watchlist")
        assert r.ok


# ── 6. Watchlist / scan ────────────────────────────────────────────────────

class TestWatchlistFeature:
    def test_default_list(self, live_server, page):
        r = page.request.get(live_server + "/api/watchlist/default-list")
        assert r.ok
        body = r.json()
        # Must be a list-ish payload
        assert isinstance(body, (list, dict))

    def test_market_phases(self, live_server, page):
        r = page.request.get(live_server + "/api/watchlist/market-phases")
        # Even with empty cache the endpoint should not 5xx.
        assert r.status < 500


# ── 7. Cache management ────────────────────────────────────────────────────

class TestCacheFeature:
    def test_refresh_status(self, live_server, page):
        r = page.request.get(live_server + "/api/cache/refresh-status")
        assert r.ok

    def test_refresh_symbols_rejects_empty(self, live_server, page):
        r = page.request.post(
            live_server + "/api/cache/refresh-symbols", data=[])
        assert r.status == 400

    def test_refresh_symbols_rejects_too_many(self, live_server, page):
        r = page.request.post(
            live_server + "/api/cache/refresh-symbols",
            data=[f"S{i}.NS" for i in range(25)])
        assert r.status == 400


# ── 8. Scan output & assistant ─────────────────────────────────────────────

class TestScanOutputs:
    def test_scan_latest(self, live_server, page):
        r = page.request.get(live_server + "/api/outputs/scan/latest")
        assert r.status in (200, 404)

    def test_scan_manifests(self, live_server, page):
        r = page.request.get(live_server + "/api/outputs/scan/manifests")
        assert r.status in (200, 404)

    def test_scan_brief(self, live_server, page):
        r = page.request.get(live_server + "/api/assistant/scan-brief")
        assert r.status in (200, 404)


# ── 9. Jobs registry ───────────────────────────────────────────────────────

class TestJobs:
    def test_jobs_list(self, live_server, page):
        r = page.request.get(live_server + "/api/jobs")
        assert r.ok
        assert isinstance(r.json(), (list, dict))


# ── 10. Performance feature ────────────────────────────────────────────────

class TestPerformance:
    @pytest.mark.parametrize("endpoint", [
        "/api/performance/summary",
        "/api/performance/trades",
        "/api/performance/report",
    ])
    def test_performance_endpoints(self, live_server, page, endpoint):
        r = page.request.get(live_server + endpoint)
        # Empty state may 404; that's acceptable — it just must not 5xx.
        assert r.status < 500, f"{endpoint} → {r.status}"


# ── 11. Breakout alert engine ──────────────────────────────────────────────

class TestBreakoutAlerts:
    def test_status(self, live_server, page):
        r = page.request.get(live_server + "/api/breakout-alerts/status")
        assert r.status < 500

    def test_signals(self, live_server, page):
        r = page.request.get(live_server + "/api/breakout-alerts/signals")
        assert r.status < 500


# ── 12. Trade journal CRUD ─────────────────────────────────────────────────

class TestTradeJournal:
    def test_list(self, live_server, page):
        r = page.request.get(live_server + "/api/trade-journal")
        assert r.status < 500


# ── 13. Market overview & breadth jobs ─────────────────────────────────────

class TestMarketOverview:
    def test_market_overview(self, live_server, page):
        r = page.request.get(live_server + "/api/trade-board/market-overview")
        assert r.status < 500


# ── 14. Frontend JS smoke: page title + main element present ───────────────

class TestTradeBoardDOM:
    def test_add_modal_exists(self, live_server, page):
        """The 'Add Position' modal is core to the feature — must be in DOM."""
        page.goto(live_server + "/board")
        # Wait for HTML parse; then search for the addModal id.
        assert page.locator("#addModal").count() >= 1 or \
               "addModal" in page.content(), "addModal not found on /board"

    def test_no_js_console_errors_on_home(self, live_server, page):
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(live_server + "/")
        page.wait_for_load_state("domcontentloaded")
        # Allow warnings; fail only on thrown exceptions.
        assert not errors, f"JS errors on home: {errors}"

