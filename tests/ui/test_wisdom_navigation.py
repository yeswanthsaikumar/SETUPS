"""End-to-end freshness tests in a real browser.

Guards against regression of the specific bug the user reported:
'on moving between pages why they are not updating and when they get
refreshed'.  These tests simulate real navigation and reload, then
assert the contextual nudge cards actually change.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.network]


def _clear_wisdom_state(page):
    page.evaluate("""() => {
        localStorage.removeItem('setups_wisdom_collapsed');
        localStorage.removeItem('setups_market_regime');
    }""")


def _read_nudge_texts(page):
    """Return the text of every non-primary nudge card in order."""
    page.wait_for_function(
        "() => document.querySelectorAll("
        "'.setups-wisdom-panel .swp-quote:not(.swp-primary) .swp-text'"
        ").length >= 1",
        timeout=5000,
    )
    return page.eval_on_selector_all(
        ".setups-wisdom-panel .swp-quote:not(.swp-primary) .swp-text",
        "els => els.map(e => e.textContent.trim())",
    )


class TestNudgesRefreshAcrossNavigation:
    def test_navigating_between_pages_changes_nudges(
            self, live_server, page):
        """board → breadth → board: the three /board visits must not all
        yield the same nudge texts (the pool is randomized per request)."""
        page.goto(live_server + "/board")
        _clear_wisdom_state(page)
        page.reload()
        page.wait_for_selector(".swp-quote.swp-primary", timeout=5000)
        first = _read_nudge_texts(page)

        # Sibling page — different tag pool, almost certainly different text.
        page.goto(live_server + "/breadth")
        page.wait_for_selector(".swp-quote.swp-primary", timeout=5000)
        breadth = _read_nudge_texts(page)
        assert set(breadth) != set(first), \
            "breadth nudges identical to board nudges"

        # Back to /board: must NOT repeat the first visit byte-for-byte.
        variations = set()
        variations.add(tuple(first))
        for _ in range(4):
            page.goto(live_server + "/board")
            page.wait_for_selector(".swp-quote.swp-primary", timeout=5000)
            variations.add(tuple(_read_nudge_texts(page)))
        assert len(variations) >= 2, (
            f"/board nudges never changed across 5 visits — "
            f"cache or date-seed regressed. got {len(variations)} unique"
        )

    def test_reload_changes_nudges(self, live_server, page):
        page.goto(live_server + "/board")
        _clear_wisdom_state(page)
        page.reload()
        page.wait_for_selector(".swp-quote.swp-primary", timeout=5000)

        seen = set()
        for _ in range(6):
            page.reload()
            page.wait_for_selector(".swp-quote.swp-primary", timeout=5000)
            seen.add(tuple(_read_nudge_texts(page)))
        assert len(seen) >= 2, (
            "page reload kept returning the same nudges — "
            "either browser cache or server seed is locking output"
        )

    def test_qotd_stays_same_across_reload_same_day(
            self, live_server, page):
        """The intentional stable anchor: QOTD should NOT change on reload."""
        page.goto(live_server + "/board")
        _clear_wisdom_state(page)
        page.reload()
        page.wait_for_selector(".swp-quote.swp-primary .swp-text", timeout=5000)
        first = page.locator(
            ".swp-quote.swp-primary .swp-text").inner_text().strip()
        page.reload()
        page.wait_for_selector(".swp-quote.swp-primary .swp-text", timeout=5000)
        second = page.locator(
            ".swp-quote.swp-primary .swp-text").inner_text().strip()
        assert first == second, \
            "QOTD changed across reload on the same day — that breaks the " \
            "'quote of the day' contract. Use the rotate button for variety."

