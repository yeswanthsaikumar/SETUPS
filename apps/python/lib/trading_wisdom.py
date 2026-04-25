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
    "market_tops",       # topping signals, sell on news, distribution
    "fii_dii",           # Foreign/Domestic institutional flow reminders
    "ipo_setup",         # IPO-specific trading rules and setups
    "india_specific",    # NSE/BSE-specific rules, India market context
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

    # ── Sam Zell ──────────────────────────────────────────────────────────────
    {"author": "Sam Zell",
     "text": "Listen to everyone. Take advice from no one. The decision — and the loss — is always yours.",
     "tags": ["psychology", "general"]},

    # ── Mark Minervini — SEPA Rules (extended) ────────────────────────────────
    {"author": "Mark Minervini",
     "text": "SEPA Rule: The RS line hitting a new high BEFORE price is the single most powerful confirmation you can get.",
     "tags": ["rs", "entries", "patterns"]},
    {"author": "Mark Minervini",
     "text": "VCP = Volatility Contraction Pattern. Look for lower lows and lower volume on each contraction. When the pivot breaks on volume, it's time.",
     "tags": ["patterns", "entries"]},
    {"author": "Mark Minervini",
     "text": "The Trend Template: price above 150MA and 200MA, 150MA above 200MA, 200MA trending up 1+ months, 50MA above both, price 25%+ above 52W low, within 25% of 52W high, RS ≥ 70. This is non-negotiable.",
     "tags": ["process", "rs", "watchlist"]},
    {"author": "Mark Minervini",
     "text": "Superperformance stocks correct 1.5× to 2.5× the correction of the general market. If it corrects 3× or more, something is wrong with that stock.",
     "tags": ["patterns", "risk", "watchlist"]},
    {"author": "Mark Minervini",
     "text": "Buy at the specific pivot — not 2% late, not on a pullback hoping. The low-risk entry is at the precise breakout point.",
     "tags": ["entries", "process"]},
    {"author": "Mark Minervini",
     "text": "In a bull market, the best stocks often go up much further than you think. Let the market hit your trailing stop — don't sell your best stock voluntarily.",
     "tags": ["positions", "exits", "market_regime_bull"]},
    {"author": "Mark Minervini",
     "text": "When institutions accumulate, weekly volume dries up near the lows. When they distribute, volume spikes on down weeks. Read the volume.",
     "tags": ["patterns", "market_tops"]},
    {"author": "Mark Minervini",
     "text": "If your stock gaps down on earnings while held overnight, you made a process error — not a trading error. Avoid earnings risk.",
     "tags": ["risk", "process"]},

    # ── Mark Douglas (extended — process over outcome, uncertainty) ───────────
    {"author": "Mark Douglas",
     "text": "The outcome of any single trade is almost irrelevant. What matters is consistent execution over 30, 50, 100 trades.",
     "tags": ["psychology", "process", "journal"]},
    {"author": "Mark Douglas",
     "text": "You don't need to know what happens next to make money. You only need to know your edge works over many trades.",
     "tags": ["psychology", "risk"]},
    {"author": "Mark Douglas",
     "text": "Accepting uncertainty completely eliminates the need to predict the market. Prediction is the enemy of systematic trading.",
     "tags": ["psychology", "process"]},
    {"author": "Mark Douglas",
     "text": "Fear-based trading: cutting winners too early, holding losers too long. The solution is not analysis — it is a pre-defined exit rule, followed without hesitation.",
     "tags": ["psychology", "exits", "risk"]},
    {"author": "Mark Douglas",
     "text": "When you believe in your system, random losses do not destabilize you. You expect some losses — they are the cost of doing business.",
     "tags": ["psychology", "process"]},
    {"author": "Mark Douglas",
     "text": "The best traders have no emotional attachment to being right. They define risk, enter, and let the market do what it does.",
     "tags": ["psychology", "risk"]},

    # ── Pradeep Bonde / Power of Stocks (India-specific extended) ─────────────
    {"author": "Pradeep Bonde",
     "text": "Super-performers have a combination of earnings acceleration, revenue acceleration, expanding margins, and a new product or theme driving the business.",
     "tags": ["watchlist", "patterns", "india_specific"]},
    {"author": "Pradeep Bonde",
     "text": "In Indian markets, stocks that go up 100%+ in a year typically have quarterly earnings growth of 50%+ for at least 3 consecutive quarters.",
     "tags": ["watchlist", "india_specific", "process"]},
    {"author": "Pradeep Bonde",
     "text": "Momentum burst: when a stock makes a 52-week high on above-average volume after a base period, the first 5–10% are the safest — buy strength, not weakness.",
     "tags": ["entries", "patterns", "india_specific"]},
    {"author": "Pradeep Bonde",
     "text": "NSE mid-cap and small-cap leaders during a domestic bull phase outperform Nifty 5–8× because institutional participation is lower and the moves are uninterrupted.",
     "tags": ["rs", "india_specific", "market_regime_bull"]},
    {"author": "Pradeep Bonde",
     "text": "Follow-through on earnings beats in India is highest in the 2 weeks following a result. Position within the setup window — after that, the risk:reward degrades fast.",
     "tags": ["entries", "india_specific", "patterns"]},
    {"author": "Pradeep Bonde",
     "text": "IPO stocks in strong sectors that list at a premium and hold above their issue price for 60+ days are often in Stage 2 accumulation. First base breakout is the entry.",
     "tags": ["ipo_setup", "entries", "india_specific"]},

    # ── IBD Rules & Proverbs ──────────────────────────────────────────────────
    {"author": "IBD",
     "text": "Distribution Day: a significant index decline on higher volume than the prior session. 4–5 in 4 weeks = market under pressure. Raise cash.",
     "tags": ["market_tops", "market_regime_bear", "process"]},
    {"author": "IBD",
     "text": "Follow-Through Day: on Day 4 or later of a rally attempt, a major index closes up 1.25%+ on higher volume. This is the only confirmed buy signal for a new uptrend.",
     "tags": ["market_regime_bull", "process", "entries"]},
    {"author": "IBD",
     "text": "The RS line making a new high while price is still forming the right side of the base is a premium tell. These are your conviction buys.",
     "tags": ["rs", "patterns", "entries"]},
    {"author": "IBD",
     "text": "Stalling action: index rises modestly or closes in lower half of its range on surging volume. A top-1 distribution signal that most traders miss.",
     "tags": ["market_tops", "process"]},
    {"author": "IBD",
     "text": "Sell a stock when it closes more than 8% below your purchase price. This is the No. 1 rule that protects your capital.",
     "tags": ["risk", "exits", "process"]},
    {"author": "IBD",
     "text": "When a leading stock flashes 3 weeks of tight weekly closes in a row, that is the pocket pivot. Buy quietly before the breakout. Institutions are loading.",
     "tags": ["patterns", "entries"]},
    {"author": "IBD",
     "text": "The best 2-week run in a stock often comes right after it establishes a new 52-week high from a sound base. Don't wait for a 'confirmation' pullback — you will miss it.",
     "tags": ["entries", "market_regime_bull"]},

    # ── Market Tops & Bottoms on News (Fade the News) ─────────────────────────
    {"author": "system",
     "text": "Markets bottom on the WORST possible news — when everyone believes the world is ending. The reversal happens when the last seller sells. Watch for breadth thrust on capitulation days.",
     "tags": ["market_regime_bull", "market_tops", "general"]},
    {"author": "system",
     "text": "Markets top on the BEST possible news — rate cuts, strong GDP, record earnings. When the news could not be better and the market can't rally, that is distribution. Sell.",
     "tags": ["market_tops", "exits", "general"]},
    {"author": "system",
     "text": "The news FOLLOWS the market, it doesn't lead it. By the time CNBC says 'market rallies on X', smart money bought it 3 weeks ago. Trade price action, not headlines.",
     "tags": ["psychology", "market_tops", "general"]},
    {"author": "system",
     "text": "War, tariff shock, pandemic — every steep correction in history recovered. The recovery always came from relative strength stocks with strong earnings. Own those.",
     "tags": ["market_regime_bull", "general", "psychology"]},
    {"author": "Jesse Livermore",
     "text": "After a long bull market, the public is most invested, most bullish, and most exposed at exactly the wrong moment. The top is made when there are no more buyers.",
     "tags": ["market_tops", "psychology"]},
    {"author": "Warren Buffett",
     "text": "The stock market is a mechanism for transferring wealth from the impatient to the patient.",
     "tags": ["psychology", "general", "positions"]},

    # ── FII / DII Activity Reminders ─────────────────────────────────────────
    {"author": "system",
     "text": "FII BUYING: when Foreign Institutional Investors turn net buyers for 5+ consecutive sessions, a sustained rally typically follows in large-cap leaders. Shift bias bullish.",
     "tags": ["fii_dii", "market_regime_bull", "india_specific"]},
    {"author": "system",
     "text": "FII SELLING: sustained FII outflow (5+ sessions) + rupee depreciation = structural headwind. Don't fight it. Reduce size, hedge with cash.",
     "tags": ["fii_dii", "market_regime_bear", "india_specific", "risk"]},
    {"author": "system",
     "text": "DII buying is a CUSHION, not a rocket. When FIIs sell and DIIs buy, the market stabilises but doesn't sprint. Wait for FII participation before scaling up.",
     "tags": ["fii_dii", "india_specific", "process"]},
    {"author": "system",
     "text": "Options expiry week (last Thursday of month): FII index positions unwind. Mid-caps often decouple from Nifty. Focus on stocks, not index direction this week.",
     "tags": ["fii_dii", "india_specific", "entries"]},
    {"author": "system",
     "text": "Budget Day and RBI policy days are NOT trading days for swing setups. The gap risk is enormous. Be flat or small before macro announcements.",
     "tags": ["fii_dii", "risk", "india_specific"]},

    # ── IPO-Specific Rules ────────────────────────────────────────────────────
    {"author": "system",
     "text": "IPO RULE 1: Never buy on listing day. Let it trade 30–60 sessions to form a proper base. The first base breakout after IPO stabilisation has the highest R:R.",
     "tags": ["ipo_setup", "entries", "risk"]},
    {"author": "system",
     "text": "IPO RULE 2: An IPO that holds above its issue price for 60 days in a tough market is showing enormous relative strength. It is being accumulated by informed money.",
     "tags": ["ipo_setup", "rs", "watchlist"]},
    {"author": "system",
     "text": "IPO RULE 3: The 10-EMA is the trail stop for IPO stocks in Stage 1. They are volatile — give them room. A close below 10-EMA for 2 sessions = warning.",
     "tags": ["ipo_setup", "exits", "positions"]},
    {"author": "system",
     "text": "IPO RULE 4: Check the lock-in expiry date (90–180 days for anchor/QIB). Heavy selling often happens as lock-ins expire. Know the cliff before it arrives.",
     "tags": ["ipo_setup", "risk", "india_specific"]},
    {"author": "William O'Neil",
     "text": "Some of the greatest winning stocks started as IPOs. They went through a base-building phase, then broke out on volume to 1000%+ gains. Patience is required.",
     "tags": ["ipo_setup", "patterns", "market_regime_bull"]},

    # ── India-Specific Market Wisdom ─────────────────────────────────────────
    {"author": "system",
     "text": "INDIA CIRCUIT LIMITS: a lower circuit hits when sellers have no buyers. It is over. Cut next morning at open, not after. The stock will circuit again.",
     "tags": ["india_specific", "risk", "exits"]},
    {"author": "system",
     "text": "INDIA BREADTH: when advance-decline on NSE is above 1:3 for 5+ days, corrections are real. Don't buy dips blindly — the selling is broad.",
     "tags": ["india_specific", "market_regime_bear", "process"]},
    {"author": "system",
     "text": "Nifty at 200-DMA is the line in the sand for Indian bull markets. Reclaim the 200-DMA with volume and breadth → bull confirmed. Fail to reclaim → go to cash.",
     "tags": ["india_specific", "market_regime_bull", "market_regime_bear", "process"]},
    {"author": "system",
     "text": "Indian small-caps are 2–3× more volatile than Nifty. Position size accordingly — treat a ₹200 small-cap like a ₹500 large-cap for sizing purposes.",
     "tags": ["india_specific", "risk", "adr"]},

    # ── System — Enhanced Reminders ──────────────────────────────────────────
    {"author": "system",
     "text": "MARKET PHASE CHECK (do this daily): Is Nifty above 200-DMA? Are 60%+ of stocks above 50-DMA? Is advance-decline ratio > 1? If yes to all three, go offensive.",
     "tags": ["process", "market_regime_bull", "india_specific"]},
    {"author": "system",
     "text": "CUT THE SETUP RATING: market A+ → full size. Market B → half size. Market C → quarter size or cash. The setup rating is useless without the market filter.",
     "tags": ["process", "risk", "market_regime_bear"]},
    {"author": "system",
     "text": "Letting winners run is not passive — it requires ACTIVE resistance to premature selling. Every day you hold a big winner, you earn the compounding bonus of the next wave.",
     "tags": ["positions", "psychology", "exits"]},
    {"author": "system",
     "text": "The trailing stop is your income protection plan. Trail the 10-EMA for fast movers, 21-EMA for normal swings, 50-EMA for leadership names. Never manual-gut the stop.",
     "tags": ["exits", "positions", "process"]},
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
        "education": ["process", "risk", "psychology", "general"],
        "india":     ["india_specific", "fii_dii", "ipo_setup", "market_regime_bull"],
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

