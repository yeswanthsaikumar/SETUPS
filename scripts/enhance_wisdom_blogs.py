#!/usr/bin/env python3
"""
Enhance every wisdom blog with:
  • A reader-friendly story opening (if missing)
  • A concrete worked example using realistic Indian stock scenarios
  • A step-by-step "How to Trade This" process checklist

Idempotent: re-running won't duplicate sections (guarded by marker tags).
"""

from __future__ import annotations
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"

STORY_MARKER  = "<!-- ENHANCED_STORY -->"
EXAMPLE_MARKER = "<!-- ENHANCED_EXAMPLE -->"

# ────────────────────────────────────────────────────────────────────────────
# Per-blog content: (filename, story_intro_or_None, worked_example, process)
# story_intro_or_None: prepended after the first H1 + intro block, ONLY if the
#   blog doesn't already have a "## A Story Before the Rules" or similar.
# worked_example + process: appended at the very end.
# ────────────────────────────────────────────────────────────────────────────

BLOGS: dict[str, dict[str, str | None]] = {
    "JESSE_LIVERMORE_WISDOM.md": {
        "story": """## 📖 A Story Before the Rules

Imagine a 14-year-old boy in 1891, standing in a Boston bucket shop, chalk in hand. He's not yet Jesse Livermore — he's just **Jesse**, an office boy who quietly notices that prices repeat patterns. He starts writing down numbers in a notebook. Within a year, he's making more money trading than his weekly salary.

By 1907, he had made $3 million shorting the panic.
By 1929, he had made $100 million shorting the crash.
By 1940, he had lost it all and died broke.

His success and his failure came from the **same set of rules** — followed in his winning years, and broken in his losing ones.

This blog is the distillation of those rules. Read it not as history, but as a mirror: every time you feel impatient, oversized, or "sure," ask yourself — *am I trading like the Jesse of 1907, or the Jesse of 1934?*
""",
        "example": """
---

## 🎯 Worked Example — Trading Like Livermore in Today's Market

**Setup:** TITAN forms a 9-week base, breaks out on 1.8× volume, Nifty in confirmed uptrend.

**The Livermore Way:**

| Step | Action | Livermore Principle |
|------|--------|---------------------|
| 1 | Wait for breakout above pivot ₹3,420 | "Never anticipate — react." |
| 2 | Buy 25% starter at ₹3,425 | "Probe first. Don't load until you're proven right." |
| 3 | Stop at ₹3,310 (-3.4%, below pivot) | "If wrong, get out fast." |
| 4 | Add 25% after first pullback that holds the 10-EMA | "Pyramid winners, never losers." |
| 5 | Trail under each higher low | "Sit tight — the big money is in the sitting." |
| 6 | Exit on first violation of 10-week MA on heavy volume | "The market tells you when the move is done." |

**Result:** Even if you only hold for half the trend, your R-multiple comes from **scaling, not predicting**. That is Livermore's edge in modern form.

---

## ✅ How to Trade This — Step-by-Step Process

1. **Build a watchlist** of leading stocks in leading sectors. Livermore traded the strongest, not the cheapest.
2. **Wait for the pivot.** No buying inside the base. Only on breakout.
3. **Start small** — 25% of intended size. Treat the first entry as a probe.
4. **Cut fast** if it fails. A 3-5% stop is the price of admission.
5. **Add only when proven right.** Each add must come on strength, not on hope.
6. **Trail, don't predict.** Use structure — higher lows, 10-week MA — to stay in.
7. **Exit on the line of least resistance reversing.** When the trend breaks, you leave.
8. **Review weekly.** Livermore re-read his rules every Sunday. So should you.
""",
    },

    "IMPULSE_CONTROL_TRADING.md": {
        "story": """## 📖 A Story Before the Rules

Rahul opens his Zerodha app at 9:18 AM. Nifty is gapping up. His WhatsApp group is full of green emojis. PERSISTENT is up 4% pre-market. He hasn't researched it. He hasn't planned it. But his thumb taps "Buy" before his brain finishes a sentence.

By 11 AM, the stock has reversed. He's down ₹14,000.

By 1 PM, he's averaged down to "make it work."
By 3 PM, he's down ₹38,000 and furious.

That night, he can't sleep. He swears he'll "be more disciplined tomorrow."

Tomorrow, the same thing happens with a different stock.

This is not a discipline problem. This is an **impulse-control problem** — and impulse is not defeated by willpower. It's defeated by **process design** that makes impulse trades physically impossible.

That is what this blog teaches.
""",
        "example": """
---

## 🎯 Worked Example — The Anti-Impulse Filter in Action

**Scenario:** You spot ZOMATO breaking out at 10:30 AM. Your hand hovers over the buy button.

**Apply the 4-question anti-impulse filter:**

| Question | If "No" → | Your Answer |
|---------|-----------|-------------|
| Is this stock on my pre-market watchlist? | Skip the trade | _____ |
| Have I defined entry, stop, and target in writing? | Skip the trade | _____ |
| Is the volume above 1.5× the 20-day average? | Skip the trade | _____ |
| Is my position size pre-calculated for 1% risk? | Skip the trade | _____ |

If any answer is "No," the trade does not happen — no matter how good it looks.

**The discipline isn't in saying no when it's hard. It's in making the rule so clear that the decision is automatic.**

---

## ✅ How to Trade This — Step-by-Step Process

1. **Pre-market planning (8:30-9:00 AM):** Build a watchlist of 3-5 names with entry zones, stops, and targets written down.
2. **No new names during market hours.** If it's not on the watchlist, it doesn't exist today.
3. **Use limit orders only.** Market orders are the language of impulse.
4. **Set a daily trade cap** — 2 entries max. Quality beats quantity.
5. **Hide your P&L.** Watch the chart, not the rupees.
6. **Phone in another room.** Your charts are on the desktop. Your phone is the gateway to FOMO.
7. **Take a 5-minute walk after each entry.** Decisions made calmly survive longer.
8. **Journal every impulse you resisted.** Build the muscle of saying no.
""",
    },

    "CHART_PATTERN_TRADE_PLANS.md": {
        "story": """## 📖 A Story Before the Rules

Two traders see the same bull flag on TATAMOTORS.

**Trader A** says: *"Looks bullish, let me buy."* He enters at the midpoint of the flag, has no stop, no target, no size plan. The flag breaks down. He holds because "it'll come back." It doesn't.

**Trader B** says: *"This is a 3-week bull flag on a strong leader. Pivot is ₹785. Stop below the flag low at ₹758. Target is the flag pole height projected up — ₹855. Risk is 3.4%. Reward is 8.9%. R:R = 2.6:1."* He waits for the breakout candle, enters on close, and lets the pattern resolve.

Same chart. Same pattern. Two completely different outcomes.

**Trader A traded a feeling. Trader B traded a plan.** That is the only difference that matters.

This blog teaches you to be Trader B for every pattern you'll ever see.
""",
        "example": """
---

## 🎯 Worked Example — Trading a Bull Flag Like a Pro

**Stock:** DIVISLAB
**Setup:** Pole = 18% rally in 8 days. Flag = 6-day consolidation, declining volume, holding 10-EMA.

**The Trade Plan (written before entry):**

| Element | Value | Why |
|---------|-------|-----|
| Pattern | Bull flag on daily | Continuation, leader, post-earnings |
| Pivot | ₹5,640 | Top of flag, breakout trigger |
| Entry | ₹5,648 | Close above pivot on >1.5× volume |
| Initial stop | ₹5,488 (-2.8%) | Below flag low |
| Target 1 | ₹5,840 (+3.4%) | First resistance, take 30% off |
| Target 2 | ₹6,100 (+8.0%) | Pole projection, take 40% off |
| Trail | Remainder under 10-EMA | Let the trend pay |
| Size | 1% account risk | Standard book risk |
| R:R | 2.9:1 on first target | Asymmetric edge |

**What kills this trade:**
- Breakout fails to hold close above pivot → exit at break-even
- Volume comes in light (< 1.5×) → reduce size or skip
- Flag pattern violates lower trendline before breakout → invalidated, watchlist only

---

## ✅ How to Trade This — Step-by-Step Process

1. **Scan for the pattern** in leading stocks (high RS rank).
2. **Validate context** — uptrending market, leading sector, prior strength.
3. **Mark the pivot, stop, and target** *before* entry on the chart.
4. **Wait for the trigger** — close above pivot on confirming volume.
5. **Enter on close or next-day open** — never chase intraday.
6. **Calculate position size** from your stop, not your desire.
7. **Scale out at targets** — don't be greedy with the first move.
8. **Trail the runner** under structure.
9. **Journal every pattern trade** with screenshot, plan, and outcome.
10. **Review monthly** — which patterns work best for *you* in *this* market.
""",
    },

    "EVENT_PIVOT_GAP_RISK.md": {
        "story": """## 📖 A Story Before the Rules

It's 3:25 PM on a Friday. INFOSYS reports earnings tonight. The stock is up 3% today on hope. Priya is sitting on a 7% gain after holding for 12 days. Her plan said "exit before earnings." But the chart looks strong. Her group says "results will beat." She holds.

Monday morning: INFOSYS opens **-9%** on a guidance cut. Her ₹50,000 gain is now a ₹40,000 loss. A 90-point swing. Her stop-loss never even got a chance — because gaps don't honor stops.

This is the brutal reality of **event risk**: a single overnight headline can erase weeks of careful trading. The market doesn't care about your stop, your average price, or your "high-conviction thesis." It only cares about the open price on Monday.

This blog teaches you how to survive — and even profit from — the events that destroy careless traders.
""",
        "example": """
---

## 🎯 Worked Example — De-Risking Before Earnings

**Position:** Long HDFCBANK, 200 shares at ₹1,620, currently at ₹1,705 (+5.2%, ₹17,000 profit).
**Event:** Q2 results in 4 sessions.

**The De-Risk Decision Tree:**

| Factor | Reading | Action |
|--------|---------|--------|
| Open profit | +5.2% (>1R) | Eligible to hold partial |
| Recent reaction history | Mixed (last 4 quarters: +2%, -4%, +6%, -3%) | Cut at least half |
| Sector momentum | Strong (Bank Nifty making highs) | Keep some skin |
| Implied volatility (options) | Elevated | Reduce more |

**Decision:** Sell 60% (120 shares) at ₹1,705. Lock ₹10,200 profit. Hold 80 shares with stop tightened to ₹1,665 (break-even on remainder).

**Outcome scenarios:**
- Gap up +5%: Make ₹10,200 (booked) + ₹6,800 (open) = ₹17,000
- Gap down -8%: Make ₹10,200 (booked) - ₹3,200 (gap loss on 80 shares) = +₹7,000 still positive
- Flat: Make ₹10,200 (booked) + ~₹0 = ₹10,200

**No scenario destroys the trade.** That is what de-risking buys you.

---

## ✅ How to Trade This — Step-by-Step Process

1. **Track every event** on your holdings — earnings, RBI, budget, FOMC, ex-date.
2. **Mark T-5 to T-1 sessions** as "de-risk zone" on each name.
3. **Default action:** trim 50-75% before binary events unless you've sized assuming gap risk.
4. **Never average down before an event.** Wait for the gap to print.
5. **Use options to define risk** when you must hold full size — protective puts cost 1-2% but cap disaster.
6. **Avoid new entries in the 3 sessions before earnings** on the stock you're trading.
7. **After a gap against you,** don't reflex-sell at open. Let the first 30 minutes print, then act on the plan.
8. **After a gap in your favor,** book at least 30-50% — windfalls fade.
""",
    },

    "TRAILING_WINNERS_ACTION_PLAN.md": {
        "story": """## 📖 A Story Before the Rules

Amit bought BAJFINANCE at ₹4,200. Sold at ₹4,520 for a 7.6% gain. Felt smart.

Six months later, BAJFINANCE was ₹7,800.

If he had held with a structure trail, he would have made **86%**, not 7.6%. The difference between a hobby trader and a professional is not finding the trade. It's **holding it through the noise that scares everyone else out**.

This blog teaches you the five-stage trailing system that lets a single winner pay for ten losers — the math that makes swing trading actually profitable.
""",
        "example": """
---

## 🎯 Worked Example — Trailing PERSISTENT for a 60% Move

**Entry:** ₹5,400 breakout from 7-week base, 200 shares.
**Initial stop:** ₹5,200 (-3.7%).
**Result over 14 weeks:**

| Stage | Price | Action | Trailing Stop | Locked Gain |
|-------|-------|--------|---------------|-------------|
| Entry | ₹5,400 | Buy 200 | ₹5,200 | -3.7% (risk) |
| +5% (week 1) | ₹5,670 | Move to BE | ₹5,400 | 0% |
| +10% (week 2) | ₹5,940 | Trail under 10-EMA | ₹5,720 | +5.9% |
| +20% (week 4) | ₹6,480 | Trail under 10-EMA | ₹6,180 | +14.4% |
| +35% (week 7) | ₹7,290 | Sell 30% at climax wick | ₹6,720 | +24.4% on remainder |
| +50% (week 10) | ₹8,100 | Trail under 20-EMA (slower) | ₹7,650 | +41.7% on remainder |
| +62% (week 13) | ₹8,748 | Climax volume + reversal day | EXIT remainder at ₹8,700 | **Average: +44%** |

**Lesson:** The biggest part of the gain came from **not selling at +20%**. The stage system gave a mechanical way to ignore the urge.

---

## ✅ How to Trade This — Step-by-Step Process

1. **Stage 1 — Survival.** First 3-5 days: don't touch the stop. Let the trade prove itself.
2. **Stage 2 — Break-even.** After +1R or first higher-low, move stop to entry. The trade can no longer hurt.
3. **Stage 3 — Structure trail.** Trail under each new higher-low or 10-EMA close. Mechanical, no opinion.
4. **Stage 4 — Climax recognition.** Watch for parabolic acceleration, exhaustion gap, reversal on huge volume → take partial profits (30-50%).
5. **Stage 5 — Slower trail on runner.** Switch to 20-EMA or 10-week MA for the final piece. Let it run until structure breaks.
6. **Never widen a stop.** Stops only move up.
7. **Don't trail on intraday wicks.** Use closing prices only.
8. **Review every trailed winner monthly.** Where did you exit early? Where did you hold too long? Adjust the rules, not the trade.
""",
    },

    "TIMEFRAME_ANALYSIS_TOP_DOWN.md": {
        "story": """## 📖 A Story Before the Rules

Two traders look at the same RELIANCE chart.

**Trader A** zooms in on the 15-minute. He sees a "bull flag." He buys. Within 2 hours, the stock has reversed because — on the daily — it was rolling over at a major resistance.

**Trader B** starts on the monthly. He sees RELIANCE in a 5-year base, finally breaking out. He drops to weekly: clean cup-and-handle. Drops to daily: tight pullback to 10-EMA. Drops to hourly: clean entry trigger. He buys the same level Trader A bought, but with **the full weight of three higher timeframes behind him**.

Six weeks later, Trader B is up 22%. Trader A is still telling himself "patterns don't work anymore."

The pattern worked. The **context** was missing.

This blog teaches you to never trade a single timeframe again.
""",
        "example": """
---

## 🎯 Worked Example — Top-Down Stack on ICICIBANK

**Monthly:** 18-month base, breaking out of all-time-high zone. Bullish bias confirmed.
**Weekly:** 8-week handle, declining volume, holding 10-week MA. Continuation setup.
**Daily:** Tight 3-day inside-day cluster at pivot ₹1,275. Pre-breakout coil.
**Hourly:** First hour of breakout day closes above pivot on 1.7× volume.

**All four timeframes agree → A++ trade.**

| Timeframe | Question | Answer |
|-----------|----------|--------|
| Monthly | What's the multi-year trend? | Up, breakout |
| Weekly | What's the swing structure? | Higher highs, handle complete |
| Daily | What's the immediate setup? | Coil at pivot |
| Hourly | Where's the trigger? | Hour-2 close >₹1,275 with volume |

**Position size:** Full risk (1%) — confluence justifies it.
**Result:** Trade runs +18% over 6 weeks with two add-ons at higher-low retests.

Now contrast: if monthly was rolling over, even a clean daily flag would only get **half-risk** or no trade at all.

---

## ✅ How to Trade This — Step-by-Step Process

1. **Always start with the monthly.** Define the multi-year trend and major levels.
2. **Drop to weekly.** Identify the active pattern and key MAs (10W, 30W).
3. **Drop to daily.** Find the pivot, the volatility contraction, the volume signature.
4. **Drop to hourly only for the trigger.** Don't trade hourly setups against daily structure.
5. **Score the confluence:**
   - 4/4 aligned → full size
   - 3/4 aligned → 75% size
   - 2/4 aligned → 50% size or skip
   - ≤1 aligned → no trade
6. **Manage on the same timeframe you entered.** Hourly entry → hourly trail. Daily entry → daily trail.
7. **Re-check higher timeframe weekly** while in the trade. If the monthly bias flips, your trade just changed character.
8. **Never let a lower timeframe override a higher one.** Hourly noise is not a thesis change.
""",
    },

    "SWING_TRADER_RISK_MANAGEMENT.md": {
        "story": """## 📖 A Story Before the Rules

Two friends start with ₹5 lakh each in January.

**Vikram** risks 5% per trade ("I want to grow fast"). He has 8 wins and 7 losses. He's down ₹62,000 by April. He doubles down. By July he's down ₹1.4 lakh.

**Aditya** risks 1% per trade. He has 7 wins and 8 losses. He's still up ₹18,000 by April. By July he's up ₹52,000. By December he's up ₹2.1 lakh.

**Same trades. Same edge. Different risk per trade. Different lives.**

This blog teaches the five-layer risk system that ensures *your* July looks like Aditya's, not Vikram's.
""",
        "example": """
---

## 🎯 Worked Example — The Five Risk Layers on a Single Trade

**Setup:** TATAPOWER breakout, ₹400 entry, stop ₹380 (-5%).
**Account:** ₹10,00,000.
**Current state:** Market in confirmed uptrend, 2 winners + 1 loss this week, pattern is B+ (decent, not perfect).

| Layer | Reading | Multiplier |
|-------|---------|-----------|
| **1. Open risk floor** | 3 positions open, 2.1% portfolio heat | OK to add (cap is 6%) |
| **2. Market regime** | Confirmed uptrend, Nifty above 50DMA | 1.0× (normal) |
| **3. Base per-trade risk** | 1% of ₹10L = ₹10,000 | — |
| **4. Situational** | 2W:1L this week, fresh and clean | 1.0× (no penalty) |
| **5. Setup quality** | B+ pattern (not A+) | 0.75× |

**Final risk:** ₹10,000 × 1.0 × 1.0 × 0.75 = **₹7,500**
**Stop distance:** ₹20
**Position size:** ₹7,500 / ₹20 = **375 shares**
**Capital deployed:** ₹400 × 375 = ₹1,50,000 (15% of account)

Now imagine after a 4-loss streak: situational multiplier drops to 0.5×, so risk = ₹3,750, size = 187 shares. **The system protects you when you're cold.**

---

## ✅ How to Trade This — Step-by-Step Process

1. **Define base risk = 1% of account.** Never higher, often lower.
2. **Check open-risk floor first** — if total open heat is already 6%, no new trade.
3. **Read the market regime** before any trade. Bear market = 0.5× or no trade.
4. **Apply situational multiplier:**
   - Streak: 3+ losses = 0.5×, 3+ wins = 1.0× (don't get cocky)
   - Time: avoid first hour, last 30 minutes
   - Calendar: pre-earnings = 0.5× or skip
5. **Score setup quality** A+/A/B/C. Multiply by 1.25/1.0/0.75/skip.
6. **Multiply all layers** → final risk in ₹.
7. **Position size from stop**, not from "feel."
8. **Re-check weekly:** are you violating any layer? Adjust before the streak punishes you.
""",
    },

    "POSITION_SIZING_PLAYBOOK.md": {
        "example": """
---

## 🎯 Worked Example — Sizing a Trade in Real Numbers

**Account:** ₹15,00,000
**Trade:** LT breakout, entry ₹3,650, stop ₹3,545 (-2.9%)
**Conditions:** Bull regime (1.0×), A-grade pattern (1.0×), 2-win streak (1.0×), heat at 2.5%/6% cap.

**Math:**

| Step | Calculation | Result |
|------|-------------|--------|
| Base risk | 1% × ₹15,00,000 | ₹15,000 |
| Regime adj | × 1.0 | ₹15,000 |
| Setup adj | × 1.0 | ₹15,000 |
| Streak adj | × 1.0 | ₹15,000 |
| Heat check | 2.5% + 1% = 3.5% (under 6% cap) | ✓ |
| Stop distance | ₹3,650 - ₹3,545 | ₹105 |
| Position size | ₹15,000 / ₹105 | **142 shares** |
| Capital deployed | 142 × ₹3,650 | ₹5,18,300 (34.5% of acct) |

**Why this works:** if stopped, lose ₹14,910 ≈ 1% of account. If hits +3R, make ₹44,730 ≈ 3%. **You can lose 10 in a row and still be fine. You only need 3-4 winners to fund a strong year.**

---

## ✅ How to Trade This — Step-by-Step Process

1. **Never decide size by capital deployed.** Always decide by risk in ₹.
2. **Risk = Base × Regime × Setup × Streak.** Compute every time.
3. **Stop distance comes from the chart, not from "what feels okay."**
4. **Shares = Risk ₹ ÷ Stop distance.** Round down, never up.
5. **Check portfolio heat before entering.** 6% open risk is the ceiling.
6. **For pyramids:** add ½ of previous tranche on each new higher-low. Never below entry.
7. **Reduce size after 3 losses** until you have 2 wins back.
8. **Re-size every Monday** based on the new account balance.
""",
    },

    "STOP_LOSS_MASTERY.md": {
        "example": """
---

## 🎯 Worked Example — Five Stops on One Trade

**Stock:** APOLLOHOSP, entry ₹6,850, position 50 shares, account ₹12L.

| Stop Type | Level | Why | When Used |
|-----------|-------|-----|-----------|
| **1. Initial (hard)** | ₹6,650 (-2.9%) | Below pivot + last swing low | Day 1-3 |
| **2. Break-even** | ₹6,852 | After +1R move (₹7,050) | Day 4-7 |
| **3. Structure** | ₹6,920 | Under first higher-low | After confirmation |
| **4. 10-EMA trail** | follows MA | Once trend is established | Week 3+ |
| **5. Time** | Exit at ₹6,850 if no progress in 10 sessions | Setups should work or die | Always running |

**Discipline:** Every stop is in the system as a GTT order. Mental stops are honored within 30 seconds of the trigger close. **No exceptions, ever.**

---

## ✅ How to Trade This — Step-by-Step Process

1. **Place the hard stop the instant the order fills.** Not "after I see how it acts."
2. **Calculate position size from the stop**, not retrofit a stop to size.
3. **Move to break-even only after proof** (+1R or first higher-low), never out of nervousness.
4. **Once trailing, never widen.** Stops are a ratchet, not a slider.
5. **Use closing prices for trail decisions** — ignore intraday wicks.
6. **Apply a time stop** — if the trade hasn't worked in 10 sessions, it probably won't.
7. **Honor every stop.** One skipped stop = the habit that destroys your career.
8. **Journal every stop hit** — was it noise, or was your entry wrong?
""",
    },

    "DRAWDOWN_MANAGEMENT.md": {
        "example": """
---

## 🎯 Worked Example — Climbing Out of a -12% Drawdown

**Account peak:** ₹20,00,000 → **Current:** ₹17,60,000 (-12%).
**Recent record:** 8 losses, 2 small wins. Confidence shaken.

**The Recovery Protocol:**

| Week | Action | Risk Per Trade | Trades Allowed |
|------|--------|---------------|---------------|
| 1 | Cut risk to 0.5%, only A+ setups | ₹8,800 | Max 1/day |
| 2 | Same, journal every trade | ₹8,800 | Max 2/day |
| 3 | If 60%+ win rate, ramp to 0.75% | ₹13,200 | Max 2/day |
| 4 | If equity curve up, return to 1% | ₹17,600 | Normal |

**Why it works:** small risk means you stop losing capital, but you keep playing. The journal forces you to identify what changed. The graduated ramp prevents the "revenge size-up" that turns -12% into -25%.

---

## ✅ How to Trade This — Step-by-Step Process

1. **Set tiered drawdown limits** — 5% (yellow), 10% (orange), 15% (red).
2. **At yellow:** review every trade of the week, no rule changes.
3. **At orange:** cut risk in half until equity recovers 50% of drawdown.
4. **At red:** stop for 3 sessions. Review without trading.
5. **Never increase size to "make it back."** Recovery comes from consistency, not aggression.
6. **Track drawdown daily** — gut feel underestimates it 2×.
7. **Separate skill vs market issue.** Bad market regime ≠ bad trader.
8. **Document every drawdown** — they're your best teachers if studied calmly.
""",
    },

    "LOSING_STREAK_SURVIVAL_GUIDE.md": {
        "example": """
---

## 🎯 Worked Example — Surviving a 6-Loss Streak

**Trader:** account ₹8L, base risk 1%.
**Streak:** 6 losses in a row over 9 sessions. Down ~6%.

**The Streak Response Protocol:**

| Loss # | Action | New Risk |
|--------|--------|----------|
| 1-2 | Normal | 1.0% (₹8,000) |
| 3 | Yellow flag — log mistakes | 0.75% (₹6,000) |
| 4 | Cut risk | 0.5% (₹4,000) |
| 5 | A+ setups only, max 1 trade/day | 0.5% |
| 6 | **Stop trading for 2 sessions.** Review charts only. | — |
| Return | Re-enter at 0.5%, must get 2 wins | 0.5% |
| After 2 wins | Step up to 0.75% | 0.75% |
| After 4 wins | Return to 1% | 1.0% |

**Result:** even a 10-loss streak only costs ~5% of account instead of 10%. **The streak doesn't kill the trader who scales down.**

---

## ✅ How to Trade This — Step-by-Step Process

1. **Count losses in real time.** Don't pretend a streak isn't happening.
2. **After 3 losses:** drop risk to 0.5%.
3. **After 5 losses:** stop for 1-2 sessions. Reset emotionally.
4. **No revenge trades. No size-up. Ever.**
5. **Take only A+ setups during recovery.** Skip everything else.
6. **Require 2 wins before stepping risk back up.**
7. **Read your journal of past streaks** — they always end, and the next 3 trades after are often great.
8. **Distinguish market issue from process issue.** Bear market streaks ≠ broken trader.
""",
    },

    "OVERNIGHT_RISK_SURVIVAL_GUIDE.md": {
        "example": """
---

## 🎯 Worked Example — Sizing With Gap Risk Built In

**Stock:** IRCTC, holding 150 shares at ₹780, current ₹820 (+5.1%).
**Calendar:** monthly traffic data release tonight.

**Gap Survival Math:**

| Scenario | Gap | Loss on 150 shares | % of account (₹10L) |
|----------|-----|--------------------|---------------------|
| Best case | +6% | Gain ₹7,380 | +0.74% |
| Base case | -3% | Lose ₹3,690 | -0.37% |
| Bad case | -7% | Lose ₹8,610 | -0.86% |
| Disaster | -12% | Lose ₹14,760 | -1.48% |

If disaster > 1% account risk → **cut size before close.**
Action: sell 50 shares at ₹820 (book ₹2,000), hold 100. Disaster case now -0.98%.

**You don't avoid every gap. You ensure no single gap can hurt more than one normal stop.**

---

## ✅ How to Trade This — Step-by-Step Process

1. **List every overnight event** for your positions every Friday.
2. **Compute worst-case gap loss** on each name (use 2× recent ATR).
3. **If worst case > 1.5% account,** trim until it fits.
4. **Never carry full size into binary events** (earnings, Fed, RBI, budget).
5. **Use protective puts** when you must hold full size.
6. **Avoid Friday-to-Monday holding** in fragile setups — too many headlines possible.
7. **After an adverse gap,** wait 15-30 min to let the first move shake out, then act on the plan.
8. **After a favorable gap,** book at least 30-50% of position.
""",
    },

    "PROFIT_TAKING_PLAYBOOK.md": {
        "example": """
---

## 🎯 Worked Example — Scaling Out of a +3R Winner

**Stock:** POLYCAB entry ₹4,800, stop ₹4,650 (R = ₹150).
**Plan:** scale at 1R, 2R, 3R.

| Move | Price | Action | Shares Left | Locked Profit |
|------|-------|--------|-------------|---------------|
| +1R | ₹4,950 | Sell 1/3, move stop to BE | 67% | +1% account |
| +2R | ₹5,100 | Sell 1/3, trail under 10-EMA | 33% | +2% account |
| +3R | ₹5,250 | Optional 1/2 of remainder | 16% | +2.5% account |
| Climax | ₹5,400 | Exit on reversal candle | 0% | +3.3% account |

**Total return:** about 3.3% on a single trade with no opinion-based decisions. The system did the work.

---

## ✅ How to Trade This — Step-by-Step Process

1. **Predefine scale-out levels** at entry — 1R, 2R, 3R minimum.
2. **Move stop to break-even at 1R.** The trade can no longer hurt.
3. **Trail under 10-EMA after 2R.** Use closes only.
4. **Take final partial on climax signs** — vertical move, exhaustion gap, huge volume reversal.
5. **Never sell everything at one level.** Always leave a runner.
6. **Don't reverse the scale plan to hold more.** Greed kills.
7. **Track your "left on table" vs "saved by exits"** in the journal.
8. **Refine ratios over 50 trades.** Some traders do 25/25/50, others 50/25/25 — find yours.
""",
    },

    "HOLD_VS_SELL_FRAMEWORK.md": {
        "example": """
---

## 🎯 Worked Example — A Real Hold-vs-Sell Decision

**Position:** BAJFINANCE long, entry ₹7,200, current ₹8,150 (+13%).
**Day's action:** Closed -2.4% on heavy volume after a 5-day vertical run.

**Run the 5/5 checklist:**

| Sell Signal | Yes/No |
|-------------|--------|
| Close below 10-EMA on volume | No |
| Climax day (vertical + huge volume) | Yes |
| Trendline broken | No |
| Distribution count (4+ days) | No |
| Stop hit | No |

| Hold Signal | Yes/No |
|-------------|--------|
| Holding 10-EMA | Yes |
| Higher highs intact | Yes |
| Leading group strength | Yes |
| RS still rising | Yes |
| Volume on up days > down days | Borderline |

**Decision:** 1 sell signal (climax), 4 hold signals. **Action: sell 30-40% to lock climax profit, hold 60-70% under structure trail.**

You did not flip a coin. You followed the framework. **That repeatability is the edge.**

---

## ✅ How to Trade This — Step-by-Step Process

1. **Build the 5-sell + 5-hold checklist** on a sticky note next to your screen.
2. **Run it every evening on every open position.**
3. **3+ sell signals → exit fully.**
4. **1-2 sell signals → trim 30-50%.**
5. **0 sell signals + multiple hold signals → do nothing.**
6. **Move stop after every higher-low** — mechanical, no opinion.
7. **Never sell on a single down day** without checking the framework.
8. **Journal every "hold vs sell" decision** with the framework score.
""",
    },

    "RISK_REWARD_EXPECTANCY.md": {
        "example": """
---

## 🎯 Worked Example — Why 1:1 Trades Destroy You

**Trader A:** 55% win rate, average win = average loss (1R).
Expectancy = 0.55(1) - 0.45(1) = **+0.10R per trade**.
On 100 trades: +10R total. Costs (slippage, brokerage) eat most of it.

**Trader B:** 45% win rate, average win = 2.5× average loss.
Expectancy = 0.45(2.5) - 0.55(1) = **+0.575R per trade**.
On 100 trades: +57.5R total. Massive edge.

**Trader A loses sleep chasing accuracy. Trader B sleeps fine letting winners run.**

This is the math behind every successful swing trader: **chase R-multiples, not win rates.**

---

## ✅ How to Trade This — Step-by-Step Process

1. **Calculate your expectancy** monthly: (Win% × Avg Win R) - (Loss% × Avg Loss R).
2. **If expectancy < 0.3R**, your edge is too small. Either improve setups or stop trading.
3. **Target minimum 2:1 R:R on every entry.** Below 2:1 → skip.
4. **Cut losers at -1R, no exceptions.** Let winners reach 2R+ before partial exits.
5. **Track R-multiples instead of ₹** in your journal. Removes account-size bias.
6. **Find your A+ patterns** — the ones with 3R+ average winners.
7. **Trade those patterns 80% of the time.** Skip B/C setups.
8. **Review every losing month** — was it variance or did expectancy actually break?
""",
    },

    "MARKET_REGIME_PLAYBOOK.md": {
        "example": """
---

## 🎯 Worked Example — Adjusting to a Regime Shift

**Scenario:** Nifty closes below 50DMA for the 3rd time, distribution count = 5.
**Previous regime:** Confirmed uptrend.
**New regime read:** Correction (orange).

**Immediate adjustments:**

| Variable | Uptrend | Correction |
|---------|---------|------------|
| Risk per trade | 1.0% | 0.5% |
| Max open positions | 6 | 3 |
| Patterns played | Breakouts + pullbacks | Pullbacks only |
| Profit-taking | Aggressive trail | Take 50% at 1R |
| New entries | 2-3/week | 1/week max |
| Cash level | 20% | 50%+ |

**Result:** even if the market drops 8% over 4 weeks, your portfolio is down 2-3% — survivable. **When the regime turns back, you're alive with capital to deploy.**

---

## ✅ How to Trade This — Step-by-Step Process

1. **Read the regime every Monday** — Nifty vs 50DMA, distribution count, breadth.
2. **Score 1-4 (Strong/Neutral/Correction/Bear)** and write it on your dashboard.
3. **Apply the position-sizing multiplier:** 1.0× / 0.75× / 0.5× / 0.25× or none.
4. **Cap positions:** 6 / 4 / 3 / 1 max.
5. **Change pattern menu:** breakouts in strong, pullbacks in neutral, bounces in correction, almost nothing in bear.
6. **Re-score mid-week** if a major level breaks.
7. **Don't fight the regime.** Even great setups underperform when context is wrong.
8. **Keep a regime journal** — note how your equity curve behaves in each.
""",
    },

    "TRADING_PSYCHOLOGY_PLAYBOOK.md": {
        "example": """
---

## 🎯 Worked Example — Catching FOMO in Real Time

**9:32 AM:** Nifty gaps up 1%. Your watchlist is all green. ZOMATO is up 4% pre-market on news. Your hand reaches for the buy button.

**Pause. Run the 4-question pre-trade ritual:**

1. **Is it on my pre-market plan?** No.
2. **Did I write the stop and target before the urge?** No.
3. **Is my pulse elevated?** Yes.
4. **Would I take this trade if it were Monday at 11 AM with no buzz?** No.

**Decision:** No trade. Put phone face-down. Walk 3 minutes.

**11 AM:** ZOMATO has reversed -2%. The trade you "had to take" would have hit your stop.

The win isn't the trade you skipped — it's the **emotional muscle you built** by skipping it.

---

## ✅ How to Trade This — Step-by-Step Process

1. **Pre-market ritual every day** — plan in writing before 9 AM.
2. **Pre-trade ritual every entry** — 4 questions above.
3. **Hide unrealized P&L** during market hours.
4. **Phone away from the desk** during trading.
5. **Daily emotion journal** — name the emotion, log the trigger, score 1-10.
6. **Weekly review** — which emotions cost money this week?
7. **One identity shift:** stop saying "I want to win," start saying "I want to follow process."
8. **Read one Mark Douglas chapter per week.** Repetition is the only path to integration.
""",
    },

    "WHEN_NOT_TO_TRADE.md": {
        "example": """
---

## 🎯 Worked Example — A Day You Should Not Have Traded

**Date:** Budget day, RBI meeting in 3 days, Nifty in choppy range for 2 weeks.
**Mood:** You slept 4 hours. Feeling restless. "I need to make today work."

**Run the no-trade checklist:**

| Condition | Reading |
|-----------|---------|
| Major event today/tomorrow? | Yes (Budget) |
| Market in clear regime? | No (choppy) |
| Personal state (sleep, mood)? | Poor |
| Setups on watchlist? | 1 borderline |
| Recent streak? | 3 losses |

**Score: 4/5 no-trade flags. Action: zero trades today. Watch only.**

**Result:** market chops 1.5% both ways during the day. Borderline setup gaps down on Budget. **You saved a 2% loss by trading nothing.** That is alpha.

---

## ✅ How to Trade This — Step-by-Step Process

1. **Build a no-trade checklist** of 8-10 conditions.
2. **Run it every morning before 9:15 AM.**
3. **2+ flags = half size or no trade.**
4. **3+ flags = no trade, watch only.**
5. **Use no-trade days to study charts, refine watchlists, journal.**
6. **Track no-trade days vs P&L** — most great accounts have many "zero" days.
7. **Never trade because you're bored, behind, or angry.**
8. **Cash is a position.** Treat it that way.
""",
    },

    "SWING_TRADING_JOURNAL_SYSTEM.md": {
        "example": """
---

## 🎯 Worked Example — A Trade Card Done Right

**Stock:** DIVISLAB
**Date:** entered Mon, exited Fri (5 sessions)

**Trade Card:**

| Field | Entry | Exit |
|-------|-------|------|
| Setup | Bull flag on weekly, daily VCP | — |
| Pattern grade | A | — |
| Pivot | ₹5,640 | — |
| Entry price | ₹5,648 | — |
| Stop | ₹5,488 | — |
| Target | ₹6,100 | — |
| R:R planned | 2.9:1 | — |
| Size | 100 shares (1% risk) | — |
| Market regime | Confirmed uptrend | — |
| Conviction | 8/10 | — |
| Exit price | — | ₹5,945 (trail hit) |
| R achieved | — | +1.86R |
| Mistakes | — | Took only 60% of normal size out of fear |
| Lesson | — | Trust the system when context is clean |

After 100 of these, **patterns emerge that no chart can show you** — like "I underperform in choppy weeks" or "my A+ setups average 2.5R."

---

## ✅ How to Trade This — Step-by-Step Process

1. **Use a trade card** for every entry — even paper trades.
2. **Fill the exit card** within 30 minutes of closing the trade.
3. **Tag mistakes** consistently (FOMO, oversize, no stop, etc.).
4. **Daily review:** 5 minutes — wins, losses, mistakes, emotions.
5. **Weekly review:** 30 minutes — equity curve, expectancy, top mistakes.
6. **Monthly review:** 60 minutes — what patterns work, which don't, what to drop.
7. **Quarterly review:** half day — rewrite playbook, retire dead rules, add new ones.
8. **Read your own journal monthly.** It is the best trading book you'll ever own.
""",
    },

    "INITIAL_POSITION_PROTECTION.md": {
        "story": """## 📖 A Story Before the Rules

Karthik enters a textbook breakout in CDSL at ₹1,420. Stop at ₹1,378. Within an hour, price wobbles down to ₹1,405. He panics, moves stop to break-even. Ten minutes later, ₹1,418 hits — break-even out. He watches in disbelief as CDSL rallies to ₹1,520 over the next two weeks.

He didn't lose money. He lost the trade. And he repeats this pattern weekly.

The problem wasn't his entry. The problem was that he **suffocated a young trade** that hadn't yet had time to breathe. Breakeven came from fear, not from confirmation.

This blog teaches the difference — so the next CDSL pays for the next 5 small losses.
""",
        "example": """
---

## 🎯 Worked Example — Protecting Without Suffocating

**Trade:** APOLLOTYRE entry ₹520, stop ₹503 (-3.3%), size 200 shares, R = ₹3,400.

**Day-by-day management:**

| Day | Action | Stop | Why |
|-----|--------|------|-----|
| 1 | Hands off | ₹503 | Trade is young; noise expected |
| 2 | Hands off | ₹503 | Holding above entry, normal pullback |
| 3 | Hands off | ₹503 | Closes near high of day |
| 4 (+1R at ₹537) | Move to BE | ₹520 | First proof |
| 5 (forms higher-low at ₹528) | Trail under structure | ₹525 | Confirmation |
| 7 (+2R, ₹554) | Take 30% off, trail rest | ₹535 | Locked partial |
| 12 (10-EMA break) | Exit remainder ₹560 | — | Trend break |

**Result:** ~+₹6,800 = +2R on the trade. Compare to the "fearful" version where you move to BE on day 1 wobble and lose the entire move.

---

## ✅ How to Trade This — Step-by-Step Process

1. **Place the hard stop immediately** at structural invalidation.
2. **Do nothing for the first 2-3 sessions** unless the stop is hit.
3. **Move to BE only after +1R or first confirmed higher-low** — not before.
4. **Trail under structure (higher-lows or 10-EMA)** once proof exists.
5. **Apply a time stop** — no progress in 7-10 sessions = trim or exit.
6. **Apply a behavior stop** — failed follow-through, distribution, leader breakdown → reduce.
7. **Never widen a stop. Only tighten as proof accumulates.**
8. **Journal every "moved to BE too early" mistake** — it's the #1 killer of young winners.
""",
    },
}


def enhance(filename: str, payload: dict) -> str:
    path = DOCS / filename
    if not path.exists():
        return f"SKIP (missing): {filename}"

    text = path.read_text(encoding="utf-8")
    changed = False

    # 1) Inject story intro after first H1 + blockquote if needed
    story = payload.get("story")
    if story and STORY_MARKER not in text:
        # Only insert if blog doesn't already have its own story heading
        if not any(h in text for h in [
            "## A Story Before",
            "## Story Before",
            "## 📖 A Story",
            "## The Trader's Journey",
        ]):
            lines = text.splitlines(keepends=True)
            # find first blank line after the title block
            insert_at = 0
            seen_h1 = False
            for i, line in enumerate(lines):
                if line.startswith("# "):
                    seen_h1 = True
                if seen_h1 and i > 0 and line.strip() == "" and i + 1 < len(lines):
                    nxt = lines[i + 1].lstrip()
                    if nxt.startswith("## ") or nxt.startswith("# "):
                        insert_at = i + 1
                        break
            if insert_at == 0:
                insert_at = min(3, len(lines))
            block = f"\n{STORY_MARKER}\n{story}\n"
            lines.insert(insert_at, block)
            text = "".join(lines)
            changed = True

    # 2) Append worked example + process
    example = payload.get("example")
    if example and EXAMPLE_MARKER not in text:
        if not text.endswith("\n"):
            text += "\n"
        text += f"\n{EXAMPLE_MARKER}\n{example}\n"
        changed = True

    if changed:
        path.write_text(text, encoding="utf-8")
        return f"OK : {filename}"
    return f"-- : {filename} (already enhanced)"


def main() -> None:
    for fname, payload in BLOGS.items():
        print(enhance(fname, payload))


if __name__ == "__main__":
    main()

