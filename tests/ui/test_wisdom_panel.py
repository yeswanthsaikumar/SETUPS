"""UI tests for the always-on wisdom panel.

Design invariants being protected:
  - wisdom.js is loaded on every route (board, breadth, sector, trades, home)
  - A persistent lightbulb toggle button always exists (never vanishes)
  - The panel opens by default on first visit (fresh localStorage)
  - Panel shows a primary Quote-of-the-Day + contextual nudges
  - x collapses the panel but LEAVES the toggle button in place
  - Collapsed preference persists across reloads
  - W keyboard shortcut toggles the panel
  - Rotating the quote changes the text
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.network]


def _clear_wisdom_state(page):
    page.evaluate("""() => {
        localStorage.removeItem('setups_wisdom_collapsed');
        localStorage.removeItem('setups_market_regime');
    }""")


class TestScriptPresence:
    @pytest.mark.parametrize("path", [
        "/", "/board", "/breadth", "/sector", "/trades",
    ])
    def test_wisdom_js_loaded_on_every_page(self, live_server, page, path):
        page.goto(live_server + path)
        page.wait_for_load_state("domcontentloaded")
        assert "/ui/wisdom.js" in page.content(), \
            f"wisdom.js tag missing from {path}"

    def test_wisdom_js_served_with_expected_classes(self, live_server, page):
        r = page.request.get(live_server + "/ui/wisdom.js")
        assert r.ok, f"wisdom.js not served: {r.status}"
        body = r.text()
        assert "setups-wisdom-root" in body
        assert "SETUPS_WISDOM" in body


class TestPanelLifecycle:
    def test_toggle_button_always_present(self, live_server, page):
        page.goto(live_server + "/board")
        page.wait_for_selector(".setups-wisdom-toggle", timeout=5000)
        assert page.locator(".setups-wisdom-toggle").is_visible()

    def test_panel_open_by_default_on_first_visit(self, live_server, page):
        page.goto(live_server + "/board")
        _clear_wisdom_state(page)
        page.reload()
        page.wait_for_selector(".setups-wisdom-root.open", timeout=5000)
        page.wait_for_selector(".setups-wisdom-panel .swp-quote", timeout=5000)
        assert page.locator(".setups-wisdom-panel .swp-quote").count() >= 1

    def test_primary_quote_has_author_text_and_tags(self, live_server, page):
        page.goto(live_server + "/board")
        _clear_wisdom_state(page)
        page.reload()
        page.wait_for_selector(".swp-quote.swp-primary", timeout=5000)
        primary = page.locator(".swp-quote.swp-primary").first
        author = primary.locator(".swp-auth").inner_text().strip()
        text = primary.locator(".swp-text").inner_text()
        assert author, "author missing"
        assert len(text) > 10, f"text too short: {text!r}"
        assert primary.locator(".swp-tag").count() >= 1

    def test_contextual_nudges_render_for_board(self, live_server, page):
        page.goto(live_server + "/board")
        _clear_wisdom_state(page)
        page.reload()
        page.wait_for_selector(".swp-quote.swp-primary", timeout=5000)
        page.wait_for_function(
            "() => document.querySelectorAll("
            "'.setups-wisdom-panel .swp-quote').length >= 2",
            timeout=5000,
        )
        total = page.locator(".setups-wisdom-panel .swp-quote").count()
        assert 2 <= total <= 4, f"unexpected card count {total}"


class TestCollapseAndPersist:
    def test_x_collapses_but_keeps_toggle(self, live_server, page):
        page.goto(live_server + "/board")
        _clear_wisdom_state(page)
        page.reload()
        page.wait_for_selector(".setups-wisdom-root.open", timeout=5000)
        page.click(".setups-wisdom-panel .swp-x")
        page.wait_for_function(
            "() => !document.querySelector("
            "'.setups-wisdom-root').classList.contains('open')",
            timeout=2000,
        )
        assert page.locator(".setups-wisdom-toggle").is_visible(), \
            "toggle must never vanish"

    def test_collapsed_preference_persists_across_reload(
            self, live_server, page):
        page.goto(live_server + "/board")
        _clear_wisdom_state(page)
        page.reload()
        page.wait_for_selector(".setups-wisdom-root.open", timeout=5000)
        page.click(".setups-wisdom-panel .swp-x")
        page.wait_for_function(
            "() => !document.querySelector("
            "'.setups-wisdom-root').classList.contains('open')",
            timeout=2000,
        )
        page.reload()
        page.wait_for_selector(".setups-wisdom-toggle", timeout=5000)
        page.wait_for_timeout(200)
        assert not page.locator(".setups-wisdom-root.open").count(), \
            "collapse state did not persist across reload"
        assert page.locator(".setups-wisdom-toggle").is_visible()

    def test_toggle_reopens_panel(self, live_server, page):
        page.goto(live_server + "/board")
        _clear_wisdom_state(page)
        page.evaluate(
            "() => localStorage.setItem('setups_wisdom_collapsed', 'yes')")
        page.reload()
        page.wait_for_selector(".setups-wisdom-toggle", timeout=5000)
        assert not page.locator(".setups-wisdom-root.open").count()
        page.click(".setups-wisdom-toggle")
        page.wait_for_selector(".setups-wisdom-root.open", timeout=2000)


class TestRotateAndShortcuts:
    def test_rotate_button_changes_primary_quote(self, live_server, page):
        page.goto(live_server + "/board")
        _clear_wisdom_state(page)
        page.reload()
        page.wait_for_selector(
            ".swp-quote.swp-primary .swp-text", timeout=5000)
        before = page.locator(
            ".swp-quote.swp-primary .swp-text").inner_text()
        changed = False
        for _ in range(10):
            page.click(
                ".setups-wisdom-panel .swp-head button:first-of-type")
            page.wait_for_timeout(250)
            after = page.locator(
                ".swp-quote.swp-primary .swp-text").inner_text()
            if after != before:
                changed = True
                break
        assert changed, "rotate never produced a different quote in 10 tries"

    def test_w_keyboard_toggles(self, live_server, page):
        page.goto(live_server + "/board")
        _clear_wisdom_state(page)
        page.reload()
        page.wait_for_selector(".setups-wisdom-root.open", timeout=5000)
        # Move focus away from any input.
        page.locator("body").click(position={"x": 5, "y": 5})
        page.keyboard.press("w")
        page.wait_for_function(
            "() => !document.querySelector("
            "'.setups-wisdom-root').classList.contains('open')",
            timeout=2000,
        )
        page.keyboard.press("W")
        page.wait_for_selector(".setups-wisdom-root.open", timeout=2000)

