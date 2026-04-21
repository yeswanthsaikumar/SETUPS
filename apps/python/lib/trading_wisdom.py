"""trading_wisdom.py — a curated, attributed, category-tagged bank of
reminders, quotes, rules and psychological anchors from the traders the
user has studied: Jesse Livermore, William O'Neil, Stan Weinstein,
Nicolas Darvas, Dan Zanger, Mark Minervini, Kristjan Kullamägi, Mark
Douglas, Van Tharp, Paul Tudor Jones, Peter Lynch, Alexander Elder,
Prateek Bhonde (Power of Stocks), and more.

Every entry is a dict with:
    text     – the quote or reminder
    author   – person or system ("system" for first-party rules)
    tags     – list of category tags (see TAGS constant below)

The module is pure-data. The web API layers contextual selection
(quote-of-the-day, page-specific nudges, regime-based prompts) on top.
"""
from __future__ import annotations

import datetime
import hashlib
import random
from typing import Iterable

# Category taxonomy — keep small and meaningful.  A quote MUST carry at
# least one tag; most carry 2–3.
TAGS = {
    "psychology",        # Douglas, discipline, ego, fear
    "risk",              # position sizing, stops, risk per trade
    "process",           # rules, checklists, written plan
    "market_regime_bull",# only-long, aggression in Stage 2 / bull cycles
    "market_regime_bear",# defence, cash is position, sit out Stage 4
    "watchlist",         # narrow focus, A+ setups, curation
    "positions",         # trade management, holding winners, cutting losers
    "rs",                # relative strength / leadership
    "adr",               # volatility / tradeable range
    "patterns",          # VCP, cup-handle, flags, EPs
    "exits",             # sell rules, trailing, climax tops
    "journal",           # review, learning loop
    "entries",           # pivot, pullback, first-red-day
    "general",           # universal truths
}


# ── The bank ───────────────────────────────────────────────────────────────
# Ordering is intentional but not special; the API rotates via date hash.

QUOTES: list[dict] = [
    # ── Jesse Livermore ────────────────────────────────────────────────────
    {"author": "Jesse Livermore",
     "text": "It never was my thinking that made the big money for me. It was my sitting.",
     "tags": ["psychology", "positions"]},
    {"author": "Jesse Livermore",
     "text": "The market is never wrong; opinions often are.",
     "tags": ["psychology", "general"]},
    {"author": "Jesse Livermore",
     "text": "There is nothing new in Wall Street. What has happened in the past will happen again, because human nature does not change.",
     "tags": ["psychology", "general"]},
    {"author": "Jesse Livermore",
     "text": "Buy on the line of least resistance — upward. Sell on the line of least resistance — downward.",
     "tags": ["entries", "general"]},
    {"author": "Jesse Livermore",
     "text": "The big money is not in the buying and selling, but in the waiting.",
     "tags": ["psychology", "process"]},
    {"author": "Jesse Livermore",
     "text": "A man must believe in himself and his judgment if he expects to make a living at this game.",
     "tags": ["psychology", "process"]},

    # ── William J. O'Neil ──────────────────────────────────────────────────
    {"author": "William O'Neil",
     "text": "Cut every loss at 7–8% below your buy point. No exceptions. No hope.",
     "tags": ["risk", "exits"]},
    {"author": "William O'Neil",
     "text": "75% of stocks follow the market. Don't fight the tape.",
     "tags": ["market_regime_bull", "market_regime_bear"]},
    {"author": "William O'Neil",
     "text": "Buy the leaders — the best 1–2 names in the best 1–2 industries. Laggards pay in pain, not profit.",
     "tags": ["rs", "watchlist"]},
    {"author": "William O'Neil",
     "text": "A confirmed Follow-Through Day is the green light. Before that, you are guessing.",
     "tags": ["market_regime_bull", "process"]},
    {"author": "William O'Neil",
     "text": "If the market is not in a confirmed uptrend, don't buy. Cash is a position.",
     "tags": ["market_regime_bear", "risk"]},

    # ── Stan Weinstein ─────────────────────────────────────────────────────
    {"author": "Stan Weinstein",
     "text": "Only buy in Stage 2. Never short in Stage 2. Only short in Stage 4. Never buy in Stage 4.",
     "tags": ["market_regime_bull", "market_regime_bear", "process"]},
    {"author": "Stan Weinstein",
     "text": "Volume is the fingerprint of smart money. A breakout without volume is a trap.",
     "tags": ["patterns", "entries"]},
    {"author": "Stan Weinstein",
     "text": "Relative Strength line at new highs before price is your single best tell of leadership.",
     "tags": ["rs", "watchlist"]},

    # ── Nicolas Darvas ─────────────────────────────────────────────────────
    {"author": "Nicolas Darvas",
     "text": "I only buy stocks at new 52-week highs. Everything else is drifting or dying.",
     "tags": ["rs", "entries", "watchlist"]},
    {"author": "Nicolas Darvas",
     "text": "Simplicity beats noise. Boxes, breakouts, stops — that is the whole game.",
     "tags": ["process", "general"]},
    {"author": "Nicolas Darvas",
     "text": "There are no good or bad stocks. Only rising stocks.",
     "tags": ["rs", "general"]},

    # ── Dan Zanger ─────────────────────────────────────────────────────────
    {"author": "Dan Zanger",
     "text": "Trade only the strongest 1% of stocks. Everything else is a distraction.",
     "tags": ["rs", "watchlist"]},
    {"author": "Dan Zanger",
     "text": "Volume must be at least 2× the 30-day average on a breakout. Otherwise it is not a breakout.",
     "tags": ["patterns", "entries"]},
    {"author": "Dan Zanger",
     "text": "Sell into strength. Parabolic moves end with the last euphoric buyer — don't be her.",
     "tags": ["exits", "psychology"]},
    {"author": "Dan Zanger",
     "text": "Multiple timeframes: weekly for trend, daily for entry, intraday for precision.",
     "tags": ["process", "entries"]},

    # ── Mark Minervini ─────────────────────────────────────────────────────
    {"author": "Mark Minervini",
     "text": "Risk is the only thing you can truly control. Focus on risk, and profits take care of themselves.",
     "tags": ["risk", "psychology"]},
    {"author": "Mark Minervini",
     "text": "The Trend Template is non-negotiable. If a stock fails even one criterion, skip it.",
     "tags": ["process", "rs", "watchlist"]},
    {"author": "Mark Minervini",
     "text": "Volatility contraction is the footprint of institutional accumulation. Tight is right.",
     "tags": ["patterns", "entries"]},
    {"author": "Mark Minervini",
     "text": "A concentrated portfolio of best-in-class names beats a diversified portfolio of mediocrity.",
     "tags": ["positions", "risk"]},
    {"author": "Mark Minervini",
     "text": "Amateur traders ask 'will I be right?'. Professionals ask 'what is my risk?'.",
     "tags": ["psychology", "risk"]},

    # ── Kristjan Kullamägi ─────────────────────────────────────────────────
    {"author": "Kristjan Kullamägi",
     "text": "I'd rather do nothing than force a B setup. A+ only.",
     "tags": ["psychology", "watchlist", "process"]},
    {"author": "Kristjan Kullamägi",
     "text": "ADR under 5% is not tradeable. The stock cannot pay you enough R to justify the risk.",
     "tags": ["adr", "watchlist"]},
    {"author": "Kristjan Kullamägi",
     "text": "Episodic pivots are the highest-R trades in the market. Gap, volume, catalyst, first red day — buy the break.",
     "tags": ["patterns", "entries"]},
    {"author": "Kristjan Kullamägi",
     "text": "Trail winners with the 10-EMA for fast movers, 20-EMA for normal swings. Don't over-manage.",
     "tags": ["exits", "positions"]},
    {"author": "Kristjan Kullamägi",
     "text": "Most of your yearly return will come from 3–5 trades. Protect them. Kill everything else fast.",
     "tags": ["positions", "exits"]},

    # ── Mark Douglas ───────────────────────────────────────────────────────
    {"author": "Mark Douglas",
     "text": "Anything can happen. You don't need to know what will happen next to make money.",
     "tags": ["psychology", "general"]},
    {"author": "Mark Douglas",
     "text": "An edge is merely a higher probability of one outcome over another — not a certainty.",
     "tags": ["psychology", "risk"]},
    {"author": "Mark Douglas",
     "text": "Think in probabilities over a series of trades, not the outcome of any single one.",
     "tags": ["psychology", "process"]},
    {"author": "Mark Douglas",
     "text": "Every moment in the market is unique. Past patterns are guides, not guarantees.",
     "tags": ["psychology", "patterns"]},
    {"author": "Mark Douglas",
     "text": "The market owes you nothing. Your expectations are the source of your pain.",
     "tags": ["psychology", "general"]},

    # ── Van Tharp ──────────────────────────────────────────────────────────
    {"author": "Van Tharp",
     "text": "Position sizing is 90% of the variance in performance between traders with the same edge.",
     "tags": ["risk", "process"]},
    {"author": "Van Tharp",
     "text": "Think in R-multiples, not dollars. Dollars are emotional. R is objective.",
     "tags": ["risk", "psychology"]},
    {"author": "Van Tharp",
     "text": "Expectancy = (Win% × AvgWin) − (Loss% × AvgLoss). If it isn't positive, you don't have a system.",
     "tags": ["process", "journal"]},
    {"author": "Van Tharp",
     "text": "The first job is to protect capital. The second job is to make it grow. Confuse the order at your peril.",
     "tags": ["risk", "psychology"]},

    # ── Paul Tudor Jones ──────────────────────────────────────────────────
    {"author": "Paul Tudor Jones",
     "text": "Losers average losers. Winners add to winners.",
     "tags": ["positions", "risk"]},
    {"author": "Paul Tudor Jones",
     "text": "I'm looking for 5:1 risk-reward. That way I can be wrong four out of five times and still break even.",
     "tags": ["risk", "process"]},
    {"author": "Paul Tudor Jones",
     "text": "The secret to being successful is defense, defense, defense.",
     "tags": ["risk", "psychology"]},
    {"author": "Paul Tudor Jones",
     "text": "Don't focus on making money; focus on protecting what you have.",
     "tags": ["risk", "psychology"]},

    # ── Peter Lynch ────────────────────────────────────────────────────────
    {"author": "Peter Lynch",
     "text": "Know what you own, and know why you own it.",
     "tags": ["process", "positions"]},
    {"author": "Peter Lynch",
     "text": "The person that turns over the most rocks wins the game.",
     "tags": ["watchlist", "process"]},
    {"author": "Peter Lynch",
     "text": "In the long run, it's not just how much money you make, but how much you keep.",
     "tags": ["risk", "general"]},

    # ── Alexander Elder ────────────────────────────────────────────────────
    {"author": "Alexander Elder",
     "text": "The goal of a successful trader is to make the best trades. Money is secondary.",
     "tags": ["psychology", "process"]},
    {"author": "Alexander Elder",
     "text": "2% per trade, 6% total open risk. That is the line between trading and gambling.",
     "tags": ["risk"]},
    {"author": "Alexander Elder",
     "text": "Triple Screen: weekly trend, daily oscillator, intraday trigger. Never skip the weekly.",
     "tags": ["process", "entries"]},

    # ── Prateek Bhonde (Power of Stocks) ──────────────────────────────────
    {"author": "Prateek Bhonde",
     "text": "Trade only in the direction of the first 15-minute candle. After 09:45, the day's bias is set.",
     "tags": ["entries", "process"]},
    {"author": "Prateek Bhonde",
     "text": "1% risk per trade. No revenge trades. If two losses in a row, walk away.",
     "tags": ["risk", "psychology"]},
    {"author": "Prateek Bhonde",
     "text": "Inside bars + trendline break is the highest-probability swing entry for Indian markets.",
     "tags": ["patterns", "entries"]},
    {"author": "Prateek Bhonde",
     "text": "A focused watchlist of 20 stocks beats a messy list of 200. Quality, not quantity.",
     "tags": ["watchlist", "process"]},

    # ── Warren Buffett (selective) ─────────────────────────────────────────
    {"author": "Warren Buffett",
     "text": "Rule No. 1: Never lose money. Rule No. 2: Never forget rule No. 1.",
     "tags": ["risk", "general"]},
    {"author": "Warren Buffett",
     "text": "Be fearful when others are greedy, and greedy when others are fearful.",
     "tags": ["psychology", "market_regime_bull", "market_regime_bear"]},

    # ── Ed Seykota ─────────────────────────────────────────────────────────
    {"author": "Ed Seykota",
     "text": "The elements of good trading are: cutting losses, cutting losses, and cutting losses.",
     "tags": ["risk", "exits"]},
    {"author": "Ed Seykota",
     "text": "Everybody gets what they want from the market. If you keep losing, look inward.",
     "tags": ["psychology", "journal"]},

    # ── Richard Dennis / Turtle Traders ────────────────────────────────────
    {"author": "Richard Dennis",
     "text": "Trading decisions should be based on rules, not feelings. If you can't backtest it, don't trade it.",
     "tags": ["process", "psychology"]},

    # ── Jack Schwager (Market Wizards) ────────────────────────────────────
    {"author": "Jack Schwager",
     "text": "Amateurs focus on rewards. Professionals focus on risk.",
     "tags": ["risk", "psychology"]},

    # ── First-party system rules (always labelled 'system') ───────────────
    {"author": "system",
     "text": "Before every trade, answer: Market OK? Stock OK? Setup OK? Risk OK? If any 'no', stand down.",
     "tags": ["process", "risk"]},
    {"author": "system",
     "text": "Risk per trade ≤ 1% of capital. Total open risk ≤ 6%. No exceptions — not even for 'sure things'.",
     "tags": ["risk", "positions"]},
    {"author": "system",
     "text": "A watchlist of 200 is a to-do list of guilt. Curate to 20 A+ names. Review weekly.",
     "tags": ["watchlist", "process"]},
    {"author": "system",
     "text": "If the index is below its 50-day MA, halve your size. Below the 200-day, go to cash.",
     "tags": ["market_regime_bear", "risk"]},
    {"author": "system",
     "text": "In Stage 2 bull markets: press winners, scale up, stay full. This is the short window that pays for the year.",
     "tags": ["market_regime_bull", "positions"]},
    {"author": "system",
     "text": "After a 10%+ drawdown, cut size 50% until the account recovers 5%. Mechanical. No ego.",
     "tags": ["risk", "psychology"]},
    {"author": "system",
     "text": "Journal every trade the same day: setup, entry, stop, exit, R, emotion, lesson. No journal, no improvement.",
     "tags": ["journal", "process"]},
    {"author": "system",
     "text": "Relative Strength ≥ 85 and ADR ≥ 3% are minimums. Anything weaker cannot pay swing R:R.",
     "tags": ["rs", "adr", "watchlist"]},
    {"author": "system",
     "text": "An open position is a promise to follow your exit rules — not a hope to be right.",
     "tags": ["positions", "exits", "psychology"]},
    {"author": "system",
     "text": "Three consecutive red days on big volume = distribution. Trim, don't rationalise.",
     "tags": ["exits", "positions"]},
    {"author": "system",
     "text": "Every Sunday: score the watchlist, tag stage changes, archive stale names. Consistency compounds.",
     "tags": ["watchlist", "journal", "process"]},

    # ── Richard Weissman ──────────────────────────────────────────────────
    {"author": "Richard Weissman",
     "text": "The hard work in trading comes in the preparation. The actual trading should be effortless.",
     "tags": ["process", "psychology"]},

    # ── Michael Marcus ────────────────────────────────────────────────────
    {"author": "Michael Marcus",
     "text": "Every trader has strengths and weaknesses. The winners maximize strengths, minimize weaknesses.",
     "tags": ["journal", "psychology"]},

    # ── Linda Raschke ─────────────────────────────────────────────────────
    {"author": "Linda Raschke",
     "text": "The best trades work almost right away. If a trade is struggling early, trust the tape — exit.",
     "tags": ["exits", "positions"]},

    # ── Bruce Kovner ──────────────────────────────────────────────────────
    {"author": "Bruce Kovner",
     "text": "Novice traders trade 5 to 10 times too big. Reduce size. Survive. Then grow.",
     "tags": ["risk", "positions"]},

    # ── Sam Zell ──────────────────────────────────────────────────────────
    {"author": "Sam Zell",
     "text": "Listen to everyone. Take advice from no one. The decision — and the loss — is always yours.",
     "tags": ["psychology", "general"]},
]


# ── Integrity checks (fail loud at import time if someone breaks the schema)

def _validate() -> None:
    assert len(QUOTES) >= 50, "wisdom bank shrunk below minimum of 50 entries"
    for q in QUOTES:
        assert set(q.keys()) >= {"text", "author", "tags"}, f"bad entry: {q}"
        assert q["text"].strip(), "empty text"
        assert q["author"].strip(), "empty author"
        assert q["tags"], f"{q['author']}: every quote needs at least one tag"
        for t in q["tags"]:
            assert t in TAGS, f"{q['author']}: unknown tag {t!r}"


_validate()


# ── Public selection API ──────────────────────────────────────────────────

def all_quotes() -> list[dict]:
    """Read-only snapshot of the full bank."""
    return [dict(q) for q in QUOTES]


def authors() -> list[str]:
    return sorted({q["author"] for q in QUOTES})


def by_tag(tag: str) -> list[dict]:
    return [q for q in QUOTES if tag in q["tags"]]


def by_tags(tags: Iterable[str], match: str = "any") -> list[dict]:
    """Filter by tags.

    match='any'  → quote has at least one of the tags (default)
    match='all'  → quote has every tag in the list
    """
    tagset = set(tags)
    if not tagset:
        return list(QUOTES)
    if match == "all":
        return [q for q in QUOTES if tagset.issubset(q["tags"])]
    return [q for q in QUOTES if tagset.intersection(q["tags"])]


def _date_seed(d: datetime.date | None = None) -> int:
    d = d or datetime.date.today()
    return int(hashlib.md5(d.isoformat().encode()).hexdigest()[:8], 16)


def quote_of_the_day(d: datetime.date | None = None) -> dict:
    """Deterministic — same date → same quote, every time, every device.

    Rotates through the full bank so over N days every quote is shown
    at least once (subject to hash collisions which are extremely rare
    for a 50–100 entry bank).
    """
    idx = _date_seed(d) % len(QUOTES)
    return dict(QUOTES[idx])


def random_quote(tags: Iterable[str] | None = None,
                 exclude_authors: Iterable[str] | None = None,
                 seed: int | None = None) -> dict | None:
    """Random quote, optionally filtered."""
    pool = by_tags(tags) if tags else list(QUOTES)
    if exclude_authors:
        ex = set(exclude_authors)
        pool = [q for q in pool if q["author"] not in ex]
    if not pool:
        return None
    rng = random.Random(seed)
    return dict(rng.choice(pool))


def reminders_for_page(page: str,
                       market_regime: str = "unknown",
                       count: int = 3,
                       seed: int | None = None) -> list[dict]:
    """Return contextual nudges relevant to a given page & market regime.

    page values recognised: 'board' / 'watchlist' / 'trades' / 'breadth' /
    'sector' / 'analytics' / 'journal' / 'home'.
    market_regime: 'bull' | 'bear' | 'neutral' | 'unknown'.

    Guarantee: when market_regime is 'bull' or 'bear' the first item is
    ALWAYS a regime-tagged quote (if one exists) — after random shuffle +
    author-dedup, generic 'process' quotes can otherwise crowd out the
    regime-specific ones and the user misses the signal that regime was
    considered at all.

    Seed policy: when no seed is provided, picks are truly random on every
    call — moving between pages (or refreshing the same page) surfaces a
    different mix each time, which is the whole point of the reminder
    layer.  Tests that need determinism pass an explicit `seed`.
    """
    tag_map = {
        "board":     ["positions", "risk", "exits", "psychology"],
        "watchlist": ["watchlist", "rs", "adr", "process"],
        "trades":    ["positions", "exits", "journal"],
        "breadth":   ["market_regime_bull", "market_regime_bear", "process"],
        "sector":    ["rs", "watchlist"],
        "analytics": ["journal", "process", "psychology"],
        "journal":   ["journal", "psychology", "process"],
        "home":      ["general", "psychology", "process"],
    }
    base_tags = list(tag_map.get(page, ["general", "psychology"]))
    regime_tag: str | None = None
    if market_regime == "bull":
        regime_tag = "market_regime_bull"
    elif market_regime == "bear":
        regime_tag = "market_regime_bear"

    rng = random.Random(seed)   # seed=None → truly random per call

    picked: list[dict] = []
    seen_authors: set[str] = set()

    def _add_from(pool: list[dict]) -> None:
        rng.shuffle(pool)
        for q in pool:
            if len(picked) >= count:
                return
            if q["author"] in seen_authors:
                continue
            picked.append(dict(q))
            seen_authors.add(q["author"])

    # 1) Guaranteed first: a regime-tagged quote when a regime is asked for.
    if regime_tag:
        _add_from(by_tag(regime_tag))

    # 2) Then fill from the page's base context.
    _add_from(by_tags(base_tags))

    # 3) Final safety: if still short, fall back to general.
    if len(picked) < count:
        _add_from(by_tag("general"))

    return picked[:count]


def stats() -> dict:
    by_author: dict[str, int] = {}
    by_tag_count: dict[str, int] = {}
    for q in QUOTES:
        by_author[q["author"]] = by_author.get(q["author"], 0) + 1
        for t in q["tags"]:
            by_tag_count[t] = by_tag_count.get(t, 0) + 1
    return {
        "total": len(QUOTES),
        "authors": by_author,
        "tags": by_tag_count,
    }

