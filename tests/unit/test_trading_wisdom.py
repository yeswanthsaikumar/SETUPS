"""Unit tests for the wisdom bank — guarantees a minimum quality bar so
regressions (e.g. accidentally removing quotes, shipping empty author
attribution) can't sneak in.
"""
from __future__ import annotations

import datetime

import pytest

pytestmark = pytest.mark.unit

import trading_wisdom as tw


class TestBankIntegrity:
    def test_minimum_quote_count(self):
        assert len(tw.QUOTES) >= 50, \
            "wisdom bank must carry at least 50 quotes to feel fresh daily"

    def test_every_quote_has_text_author_tags(self):
        for q in tw.QUOTES:
            assert q["text"].strip(), f"empty text: {q}"
            assert q["author"].strip(), f"empty author: {q}"
            assert q["tags"], f"no tags: {q}"

    def test_all_tags_are_in_taxonomy(self):
        for q in tw.QUOTES:
            for t in q["tags"]:
                assert t in tw.TAGS, f"{q['author']} uses unknown tag {t!r}"

    def test_required_authors_present(self):
        """The user listed specific mentors; at least one quote from each
        must ship so the lived experience covers their full lineage."""
        required = {
            "Jesse Livermore", "William O'Neil", "Stan Weinstein",
            "Nicolas Darvas", "Dan Zanger", "Mark Minervini",
            "Kristjan Kullamägi", "Mark Douglas", "Van Tharp",
            "Prateek Bhonde",
        }
        have = set(tw.authors())
        missing = required - have
        assert not missing, f"missing required authors: {missing}"

    def test_first_party_system_rules_exist(self):
        system_qs = [q for q in tw.QUOTES if q["author"] == "system"]
        assert len(system_qs) >= 5, \
            "need ≥5 'system' reminders for process/risk/watchlist/positions"

    def test_category_balance(self):
        """No single tag should starve — the UI picks by category and empty
        categories break contextual nudges silently."""
        for required_tag in ("risk", "psychology", "watchlist",
                             "positions", "process"):
            assert len(tw.by_tag(required_tag)) >= 5, \
                f"tag {required_tag!r} under-represented"


class TestQuoteOfTheDay:
    def test_deterministic_for_same_date(self):
        d = datetime.date(2026, 4, 19)
        a = tw.quote_of_the_day(d)
        b = tw.quote_of_the_day(d)
        assert a == b

    def test_varies_across_dates(self):
        """Over 30 consecutive dates we should see at least 10 distinct
        quotes — otherwise the rotation is too sticky and users stop reading."""
        base = datetime.date(2026, 4, 1)
        picked = {tw.quote_of_the_day(base + datetime.timedelta(days=i))["text"]
                  for i in range(30)}
        assert len(picked) >= 10, f"too little variety: {len(picked)} unique"


class TestSelection:
    def test_by_tag_returns_only_matching(self):
        got = tw.by_tag("risk")
        assert got, "risk tag should have matches"
        for q in got:
            assert "risk" in q["tags"]

    def test_by_tags_match_all(self):
        got = tw.by_tags(["psychology", "risk"], match="all")
        for q in got:
            assert "psychology" in q["tags"] and "risk" in q["tags"]

    def test_random_quote_respects_exclude(self):
        q = tw.random_quote(exclude_authors=["Mark Douglas"], seed=42)
        assert q and q["author"] != "Mark Douglas"

    def test_random_quote_honors_tags(self):
        q = tw.random_quote(tags=["watchlist"], seed=7)
        assert q and "watchlist" in q["tags"]

    def test_reminders_for_page_context_watchlist(self):
        items = tw.reminders_for_page("watchlist", count=3)
        assert 1 <= len(items) <= 3
        # At least one item must come from a watchlist/rs/adr/process tag.
        assert any(
            any(t in q["tags"] for t in ("watchlist", "rs", "adr", "process"))
            for q in items)

    def test_reminders_for_page_unique_authors(self):
        """Contextual nudges must not repeat the same author on one page —
        feels lazy to the user."""
        items = tw.reminders_for_page("board", count=3, seed=1)
        authors = [q["author"] for q in items]
        assert len(authors) == len(set(authors)), f"duplicate authors: {authors}"

    def test_reminders_respect_market_regime(self):
        bull = tw.reminders_for_page("breadth", market_regime="bull", count=5)
        # In a bull regime we expect at least one market_regime_bull-tagged quote.
        assert any("market_regime_bull" in q["tags"] for q in bull), \
            "bull regime context should surface bull-tagged wisdom"


class TestStats:
    def test_stats_shape(self):
        s = tw.stats()
        assert s["total"] == len(tw.QUOTES)
        assert sum(s["authors"].values()) == s["total"]
        # Every tag in the taxonomy appears in stats with count >= 0
        for t in tw.TAGS:
            assert t in s["tags"]

