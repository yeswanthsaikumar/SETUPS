"""UI tests that verify the wisdom layer is actually injected into every
page and that the banner + contextual nudges render with real content
from the live API.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.network]


class TestWisdomScriptInjection:
    @pytest.mark.parametrize("path", ["/", "/board", "/breadth", "/sector", "/trades"])
    def test_wisdom_js_is_loaded_on_every_page(self, live_server, page, path):
        page.goto(live_server + path)
        page.wait_for_load_state("domcontentloaded")
        html = page.content()
        assert "/ui/wisdom.js" in html, \
            f"wisdom.js script tag missing from {path}"

    def test_wisdom_js_is_served_200(self, live_server, page):
        r = page.request.get(live_server + "/ui/wisdom.js")
        assert r.ok, f"wisdom.js not served: {r.status}"
        assert "setups-wisdom-banner" in r.text(), \
            "wisdom.js payload appears empty or cached-wrong"


class TestQotdBanner:
    def test_banner_renders_with_quote_and_author(self, live_server, page):
        page.goto(live_server + "/board")
        # Clear any dismiss flag from prior runs so we see the banner fresh.
        page.evaluate("() => localStorage.removeItem('setups_wisdom_qotd_dismissed')")
        page.reload()
        page.wait_for_selector(".setups-wisdom-banner.open", timeout=5000)
        text = page.locator(".setups-wisdom-banner .swb-txt").inner_text()
        assert len(text) > 20, f"banner text suspiciously short: {text!r}"
        # Author is bolded before '·' — just check the structure element exists.
        assert page.locator(".setups-wisdom-banner .swb-auth").count() >= 1

    def test_banner_dismiss_persists(self, live_server, page):
        page.goto(live_server + "/board")
        page.evaluate("() => localStorage.removeItem('setups_wisdom_qotd_dismissed')")
        page.reload()
        page.wait_for_selector(".setups-wisdom-banner.open", timeout=5000)
        page.click(".setups-wisdom-banner .swb-x")
        # After dismiss the flag is in localStorage; reload → no banner.
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        # Give wisdom.js time to NOT render the banner.
        page.wait_for_timeout(400)
        assert page.locator(".setups-wisdom-banner").count() == 0, \
            "dismissed banner must stay dismissed for 18h"

    def test_banner_rotate_changes_text(self, live_server, page):
        page.goto(live_server + "/board")
        page.evaluate("() => localStorage.removeItem('setups_wisdom_qotd_dismissed')")
        page.reload()
        page.wait_for_selector(".setups-wisdom-banner.open", timeout=5000)
        before = page.locator(".setups-wisdom-banner .swb-txt").inner_text()
        # Try up to 8 rotates (some may randomly return same quote).
        changed = False
        for _ in range(8):
            page.click(".setups-wisdom-banner button:has-text('Another')")
            page.wait_for_timeout(250)
            after = page.locator(".setups-wisdom-banner .swb-txt").inner_text()
            if after != before:
                changed = True
                break
        assert changed, "rotate never produced a different quote in 8 tries"


class TestContextualNudges:
    def test_nudges_dock_renders_on_wide_viewport(self, live_server, page):
        page.goto(live_server + "/board")
        # Dock is delayed ~900ms after boot to let layout settle.
        page.wait_for_selector(".setups-wisdom-dock .swn", timeout=5000)
        count = page.locator(".setups-wisdom-dock .swn").count()
        assert 1 <= count <= 3, f"expected 1–3 nudges, got {count}"

    def test_nudge_shows_author_and_text(self, live_server, page):
        page.goto(live_server + "/board")
        page.wait_for_selector(".setups-wisdom-dock .swn", timeout=5000)
        first = page.locator(".setups-wisdom-dock .swn").first
        assert first.locator(".swn-auth").inner_text().strip()
        body = first.locator(".swn-body").inner_text()
        assert body.count("“") >= 1 or len(body) > 10

    def test_nudge_dismissible(self, live_server, page):
        page.goto(live_server + "/board")
        page.wait_for_selector(".setups-wisdom-dock .swn", timeout=5000)
        initial = page.locator(".setups-wisdom-dock .swn").count()
        page.locator(".setups-wisdom-dock .swn .swn-x").first.click()
        page.wait_for_timeout(250)
        remaining = page.locator(".setups-wisdom-dock .swn").count()
        assert remaining == initial - 1, \
            f"× should remove one nudge, had {initial} → {remaining}"

