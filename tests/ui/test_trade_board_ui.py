"""Playwright smoke tests for the trade-board UI.

Run with:
    pip install -r requirements-dev.txt
    playwright install chromium
    pytest -m ui
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.network]
# NOTE: @network is set because the in-process uvicorn still uses 127.0.0.1
# which is allowed by block_network — but Playwright's browser talks to
# localhost via real sockets, so we opt-in here.

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402


class TestTradeBoardPage:
    def test_home_loads(self, live_server, page):
        resp = page.goto(live_server + "/")
        assert resp is not None
        assert resp.status < 500, f"home page 5xx: {resp.status}"
        title = (page.title() or "").lower()
        # Accept common title substrings from any of the bundled pages.
        assert any(kw in title for kw in ("setup", "trade", "board", "dashboard")), \
            f"unexpected home title: {page.title()!r}"

    def test_health_endpoint_from_browser(self, live_server, page):
        resp = page.request.get(live_server + "/api/health")
        assert resp.ok
        body = resp.json()
        assert "ok" in body or "status" in body


class TestNavigation:
    @pytest.mark.parametrize("path", ["/board", "/breadth", "/sector", "/trades"])
    def test_route_returns_html(self, live_server, page, path):
        resp = page.goto(live_server + path)
        # Accept 200 (page rendered) or 404 with the "run scan first" banner.
        assert resp is not None
        assert resp.status in (200, 404)


class TestVpnModal:
    def test_vpn_status_api_from_browser(self, live_server, page):
        resp = page.request.get(live_server + "/api/vpn/status")
        assert resp.ok
        body = resp.json()
        assert body.get("enabled") is False

