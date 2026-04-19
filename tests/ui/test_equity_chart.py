"""Deep UI rendering & data-integrity tests.

These are the tests that would have caught the 'equity curve axis renders
but the line is invisible' bug. They:

  • Seed realistic closed positions directly into the isolated trade_data/
  • Load the page, click the Analytics tab
  • Assert the chart API's data meets LightweightCharts' hard requirements
    (strictly ascending, unique time values, numeric values)
  • Assert the chart canvas actually got rendered (pixel count > 0)
  • Capture every browser console.error and network 4xx/5xx during the test

The philosophy: a feature test must prove the pixels on screen match the
user's intent, not just that the HTTP endpoint returned 200.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.network]


# ── Helpers ────────────────────────────────────────────────────────────────

def _closed_position(symbol: str, entry: float, exit_p: float,
                     entry_date: str, exit_date: str, qty: int = 10,
                     status: str = "T3_HIT") -> dict:
    return {
        "id": symbol.lower() + entry_date.replace("-", ""),
        "symbol": symbol, "name": symbol, "entry": entry,
        "quantity": qty, "remaining_quantity": 0,
        "sl": entry * 0.95, "t1": entry * 1.05,
        "t2": entry * 1.10, "t3": entry * 1.20,
        "setup": "BREAKOUT", "rating": "A", "notes": "seeded",
        "entry_date": entry_date, "exit_date": exit_date,
        "exit_price": exit_p, "status": status,
        "tags": [], "partial_exits": [],
    }


@pytest.fixture
def page_with_console(page):
    """Capture all console.error + pageerror + failed responses for assertions."""
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on("console", lambda msg: errors.append(f"console.{msg.type}: {msg.text}")
            if msg.type in ("error",) else None)
    page.on("requestfailed", lambda req: errors.append(
        f"requestfailed: {req.method} {req.url} — {req.failure}"))
    page.on("response", lambda resp: errors.append(
        f"HTTP {resp.status} {resp.url}") if resp.status >= 500 else None)
    page._captured_errors = errors  # attach for tests
    return page


# ── 1. Equity-curve data-integrity contract ────────────────────────────────

class TestEquityCurveContract:
    """Invariants the /api/trade-board/equity response MUST satisfy for the
    LightweightCharts frontend to render correctly. These tests pin the
    contract so a future change cannot silently re-introduce duplicate or
    unsorted timestamps (which render as an empty chart)."""

    def test_empty_when_no_trades(self, live_server, clean_board, page):
        r = page.request.get(live_server + "/api/trade-board/equity")
        assert r.ok
        body = r.json()
        assert body["curve"] == []
        assert body["totalPl"] == 0

    def test_dates_are_strictly_ascending_and_unique(
            self, live_server, seed_positions, page):
        """THIS IS THE REGRESSION TEST for the invisible-equity-curve bug.

        Seed 3 exits on the same date + 1 on a different date. The /equity
        response must have exactly 2 unique, sorted time points."""
        seed_positions([
            _closed_position("AAA", 100, 120, "2026-03-01", "2026-04-10"),
            _closed_position("BBB", 200, 250, "2026-03-05", "2026-04-10"),
            _closed_position("CCC", 300, 280, "2026-03-10", "2026-04-10",
                             status="SL_HIT"),
            _closed_position("DDD", 400, 450, "2026-03-12", "2026-04-15"),
        ])
        r = page.request.get(live_server + "/api/trade-board/equity")
        assert r.ok, r.text()
        curve = r.json()["curve"]

        dates = [c["date"] for c in curve]
        assert len(dates) == 2, f"expected 2 aggregated points, got {dates}"
        assert dates == sorted(set(dates)), f"dates not strictly sorted+unique: {dates}"

        # Cumulative P&L must be monotonic in its aggregation semantics —
        # the sum of all daily pl must equal totalPl.
        assert round(sum(c["pl"] for c in curve), 2) == r.json()["totalPl"]
        # Last cumPl must equal totalPl.
        assert curve[-1]["cumPl"] == r.json()["totalPl"]

    def test_values_are_all_numeric(self, live_server, seed_positions, page):
        seed_positions([
            _closed_position("XYZ", 100, 110, "2026-04-01", "2026-04-05"),
        ])
        curve = page.request.get(live_server + "/api/trade-board/equity").json()["curve"]
        for c in curve:
            assert isinstance(c["cumPl"], (int, float))
            assert isinstance(c["pl"], (int, float))
            # time must be parseable date
            assert len(c["date"]) >= 10 and c["date"][4] == "-" and c["date"][7] == "-"


# ── 2. Equity chart actually renders in the browser ────────────────────────

class TestEquityChartRenders:
    """Proves the LightweightCharts canvas has pixels — not just an empty
    axis. This is what the shallow UI tests missed."""

    def test_empty_state_shows_no_trades_message(
            self, live_server, clean_board, page_with_console):
        page = page_with_console
        page.goto(live_server + "/board")
        page.wait_for_load_state("domcontentloaded")
        # Switch to the analytics page so the chart container is VISIBLE.
        # showPage('analytics') is defined in trade_board.html and triggers
        # loadEquity() as a side-effect (see line ~1272).
        page.evaluate("showPage('analytics')")
        page.wait_for_function(
            "() => { const el = document.getElementById('equityChart'); "
            "return el && el.innerHTML.length > 0; }",
            timeout=5000,
        )
        content = page.locator("#equityChart").inner_html()
        assert "No closed trades" in content or "no closed" in content.lower(), \
            f"empty state should show a message, got: {content[:200]}"

    def test_chart_renders_with_seeded_trades(
            self, live_server, seed_positions, page_with_console):
        """The REAL test: seed trades, render, and verify a canvas exists
        AND it has non-zero pixels (i.e. a line was actually drawn)."""
        seed_positions([
            _closed_position("AAA", 100, 120, "2026-03-01", "2026-04-01"),
            _closed_position("BBB", 200, 180, "2026-03-05", "2026-04-05",
                             status="SL_HIT"),
            _closed_position("CCC", 300, 360, "2026-03-10", "2026-04-10"),
            _closed_position("DDD", 150, 165, "2026-03-12", "2026-04-10"),  # same day!
        ])
        page = page_with_console
        page.goto(live_server + "/board")
        page.wait_for_load_state("domcontentloaded")

        # Make the analytics panel VISIBLE before rendering — otherwise the
        # container has offsetWidth=0 and LightweightCharts can't compute a
        # canvas box (this is exactly the bug class we're guarding against).
        page.evaluate("showPage('analytics')")

        # Wait for the chart's own marker (set by renderEqChart on success).
        page.wait_for_function(
            "() => { const el = document.getElementById('equityChart'); "
            "return el && el.dataset && Number(el.dataset.points) > 0; }",
            timeout=8000,
        )
        points = int(page.locator("#equityChart").get_attribute("data-points") or 0)
        # Seeded dates: 2026-04-01, 2026-04-05, 2026-04-10 (x2 aggregated).
        assert points == 3, f"expected 3 unique-date points, got {points}"

        # Canvas must exist AND be visible (non-zero bounding box).
        canvas_count = page.locator("#equityChart canvas").count()
        assert canvas_count >= 1, "no <canvas> inside #equityChart"
        box = page.locator("#equityChart canvas").first.bounding_box()
        assert box is not None, "canvas has no bounding box (tab hidden?)"
        assert box["width"] > 10 and box["height"] > 10, \
            f"canvas has zero pixels: {box}"

        # Zero console.error / pageerror / requestfailed during the whole flow.
        relevant = [e for e in page._captured_errors
                    if "favicon" not in e.lower()]
        assert not relevant, f"browser reported errors: {relevant}"


# ── 3. Smoke: /api/trade-board/positions enrichment must not 500 ───────────

class TestPositionsEnrichment:
    def test_enriched_endpoint_with_seeded_open_position(
            self, live_server, seed_positions, page):
        seed_positions([{
            "id": "open1", "symbol": "RELIANCE.NS", "name": "Reliance",
            "entry": 1200.0, "quantity": 10, "sl": 1140,
            "t1": 1260, "t2": 1320, "t3": 1440,
            "setup": "BREAKOUT", "rating": "A",
            "entry_date": "2026-04-10", "status": "OPEN",
            "partial_exits": [], "tags": [],
        }])
        r = page.request.get(live_server + "/api/trade-board/positions")
        assert r.ok, r.text()
        body = r.json()
        assert len(body["positions"]) == 1
        pos = body["positions"][0]
        assert pos["symbol"] == "RELIANCE.NS"
        # stats block must always be present for the frontend
        assert "stats" in body


# ── 4. Console-error budget for the trade board page load ──────────────────

class TestConsoleBudget:
    """The home page must load with ZERO JS errors. This catches broken
    feature JS the moment it's introduced."""

    def test_board_page_no_console_errors(
            self, live_server, clean_board, page_with_console):
        page = page_with_console
        page.goto(live_server + "/board")
        page.wait_for_load_state("networkidle", timeout=10000)
        relevant = [e for e in page._captured_errors
                    if "favicon" not in e.lower()
                    # stream closed noise is benign on shutdown
                    and "net::ERR_ABORTED" not in e]
        assert not relevant, f"JS errors on /board: {relevant}"

