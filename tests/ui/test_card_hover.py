"""UI tests for the position-card hover & click behaviour.

Verifies:
  • `.pos-card` has `overflow: visible` so hover effects are never clipped
    (regression for the "not showing complete cards on hovering" bug).
  • `.card-reveal` panel is collapsed by default, expands on :hover.
  • Clicking the card opens the full-page detail overlay (openDetail).
  • Clicking the inline "Edit" button does NOT open the detail (event
    propagation is stopped) — this invariant is easy to break.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.network]


def _open_position(symbol: str = "TESTCARD",
                   entry: float = 100.0, sl: float = 95.0,
                   t1: float = 110.0, t2: float = 120.0, t3: float = 135.0) -> dict:
    return {
        "id": "card-" + symbol.lower(),
        "symbol": symbol + ".NS", "name": symbol, "entry": entry,
        "quantity": 100, "remaining_quantity": 100,
        "sl": sl, "t1": t1, "t2": t2, "t3": t3,
        "setup": "BULL_FLAG", "rating": "A+",
        "notes": "Seeded position for hover-reveal ui test " * 3,
        "entry_date": "2026-04-10", "status": "OPEN",
        "tags": [], "partial_exits": [],
    }


class TestCardHover:
    def test_card_overflow_is_not_hidden(self, live_server, seed_positions, page):
        """Guards against a CSS refactor re-introducing overflow:hidden on
        .pos-card, which is what clipped the hover shadow + reveal panel."""
        seed_positions([_open_position()])
        page.goto(live_server + "/board")
        page.wait_for_selector(".pos-card", timeout=8000)
        overflow = page.evaluate(
            "() => getComputedStyle(document.querySelector('.pos-card')).overflow"
        )
        assert overflow == "visible", \
            f".pos-card must keep overflow:visible so hover lift isn't clipped, got {overflow!r}"

    def test_reveal_panel_collapsed_then_expanded_on_hover(
            self, live_server, seed_positions, page):
        seed_positions([_open_position()])
        page.goto(live_server + "/board")
        # Wait for the card to be visible first — reveal panel itself is
        # hidden by design (max-height:0), so we can't wait on its visibility.
        page.wait_for_selector(".pos-card", timeout=8000)
        page.wait_for_selector(".pos-card .card-reveal", state="attached", timeout=5000)

        def reveal_height_px() -> int:
            return page.evaluate(
                "() => Math.round(document.querySelector('.pos-card .card-reveal').getBoundingClientRect().height)"
            )

        collapsed = reveal_height_px()
        assert collapsed <= 2, f"reveal must be collapsed by default, got {collapsed}px"

        page.hover(".pos-card")
        # allow CSS transition to complete
        page.wait_for_function(
            "() => document.querySelector('.pos-card .card-reveal').getBoundingClientRect().height > 20",
            timeout=2000,
        )
        expanded = reveal_height_px()
        assert expanded > 20, f"reveal must expand on hover, got {expanded}px"

    def test_hover_lift_transform_and_zindex(
            self, live_server, seed_positions, page):
        seed_positions([_open_position()])
        page.goto(live_server + "/board")
        page.wait_for_selector(".pos-card", timeout=8000)
        page.hover(".pos-card")
        transform = page.evaluate(
            "() => getComputedStyle(document.querySelector('.pos-card')).transform"
        )
        z_index = page.evaluate(
            "() => getComputedStyle(document.querySelector('.pos-card')).zIndex"
        )
        # transform is 'matrix(...)' when a translate/scale is applied, not 'none'.
        assert transform and transform != "none", \
            f"hover should apply a transform (lift+scale), got {transform!r}"
        assert int(z_index) >= 10, \
            f"hovered card must be elevated above siblings, z-index={z_index}"


class TestCardClick:
    def test_click_opens_detail_overlay(
            self, live_server, seed_positions, page):
        seed_positions([_open_position()])
        page.goto(live_server + "/board")
        page.wait_for_selector(".pos-card", timeout=8000)
        # Sanity: detail overlay exists in DOM but is initially hidden.
        assert page.locator("#detOverlay").count() == 1
        page.click(".pos-card", position={"x": 30, "y": 30})
        # Detail overlay should now be visible (openDetail sets display:flex).
        page.wait_for_function(
            "() => { const el = document.getElementById('detOverlay'); "
            "return el && getComputedStyle(el).display !== 'none'; }",
            timeout=3000,
        )

    def test_edit_button_does_not_bubble_to_detail(
            self, live_server, seed_positions, page):
        """The inline 'Edit' uses event.stopPropagation so the underlying
        card onclick does NOT fire. If a future refactor drops that guard,
        clicking Edit would double-open detail + update modal."""
        seed_positions([_open_position()])
        page.goto(live_server + "/board")
        page.wait_for_selector(".pos-card .card-acts .btn", timeout=8000)
        page.click(".pos-card .card-acts .btn:has-text('Edit')")
        # Update modal should open, detail overlay stays hidden.
        det_display = page.evaluate(
            "() => getComputedStyle(document.getElementById('detOverlay')).display"
        )
        assert det_display == "none", \
            f"detail overlay must not open on Edit click, display={det_display!r}"

