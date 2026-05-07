# The Professional Swing Trader's Risk Management Playbook

> *"The goal is not to make money. The goal is to protect the money you have and let profits run. Risk management separates professionals from gamblers."* — A veteran trader

## Why Risk Management Comes First

Most traders start by asking: *"What's my profit target?"* — the wrong question. The right question is: *"How much can I afford to lose?"* Risk management isn't defensive; it's **the foundation of all consistent profits**. A trader who risks 1% per trade but takes 60% winners will compound capital indefinitely. A trader who risks 10% per trade will be wiped out, even with 65% winners.

This playbook covers the five critical layers of professional risk management that separate swing traders from those who blow up accounts.

---

## 1. Open Risk: The Portfolio-Level Floor

**Open risk** is the sum of all active positions' **drawdown potential at today's close**. This is your portfolio's soft stop-loss.

### Why It Matters
- A single catastrophic gap down (earnings miss, geopolitical shock, fraud) can wipe out months of gains
- Open risk constrains how many concurrent positions you can hold
- It forces position sizing discipline

### How to Calculate It

For each open position:
```
Position Risk = Entry Price – Stop Loss
Position Shares = Capital Deployed
Position Risk $ = Position Risk × Position Shares

Total Open Risk % = (Sum of All Position Risk $) / Account Balance
```

**Example:**

| Position | Entry | Stop | Shares | Risk/Share | Risk $ |
|----------|-------|------|--------|-----------|---------|
| RELIANCE | ₹2500 | ₹2400 | 100 | ₹100 | ₹10,000 |
| TCS | ₹3900 | ₹3750 | 50 | ₹150 | ₹7,500 |
| INFY | ₹1800 | ₹1700 | 60 | ₹100 | ₹6,000 |
| **Total** | — | — | — | — | **₹23,500** |

**Account Balance:** ₹500,000  
**Open Risk:** ₹23,500 ÷ ₹500,000 = **4.7%**

### Professional Standards

| Account Size | Max Open Risk | Rationale |
|--------------|---------------|-----------|
| < ₹500K | 2–3% | Small accounts need tighter control; one mistake = big setback |
| ₹500K–₹2M | 3–5% | Sweet spot; allows 3–5 concurrent positions |
| ₹2M–₹10M | 4–6% | Slightly higher; liquidity & diversification benefit |
| > ₹10M | 5–8% | Institutional-grade capital; can absorb volatility |

### The Open Risk Decision Tree

```
Are you at max open risk?
├─ YES → 
│  ├─ Is the next trade a HIGH-CONVICTION breakout? → Wait
│  ├─ Is it a scalp/profit-taker? → OK to squeeze in (reduce another position)
│  └─ Is it uncertain? → DON'T TAKE IT
└─ NO → 
   ├─ Is there <3.5 hours to market close? → Reduce position size 25%
   ├─ Is earnings in 2 days? → Reduce position size 50% or exit
   └─ Proceed normally
```

---

## 2. Market-Based Risk: Regime Adjustment

**Market-based risk** acknowledges that the same position size is **not equally risky** in all market regimes. A 3% stop-loss in a bull flag works great in an uptrend but bleeds capital in a consolidation.

### The Four Market Regimes

#### 🟢 **Uptrend (Strong Market)**
- **VIX < 15, Nifty above 50-EMA, Leaders strong**
- Position size: 100% (baseline)
- Optimal stop placement: Under swing low or 50-EMA
- Examples: RELIANCE breaking above 2500, TCS above 3800

```
Risk Profile:
- Favorable: Pullbacks held, breakouts clean
- Unfavorable: Gap fills can surprise
- Action: Add to winners on pullbacks
```

#### 🟡 **Consolidation (Choppy Market)**
- **VIX 15–20, Nifty chopping 50±200 pts, Leaders tired**
- Position size: **70% of baseline** (tighter stops = more whipsaws)
- Optimal stop placement: Outside consolidation range + 0.5% buffer
- Examples: INFY range-bound ₹1750–₹1900

```
Risk Profile:
- Favorable: Lower volatility intraday
- Unfavorable: Breakouts fail 40% of time; tight stops get hit
- Action: Play pocket pivots & 3-bar bounces, not breakouts
```

#### 🟠 **Correction (Weak Market)**
- **VIX 20–30, Nifty down 3%+ from highs, Leaders rolling over**
- Position size: **50% of baseline** (volatility expanding, reversals violent)
- Optimal stop placement: Outside key support + 1% buffer
- Examples: HDFC Bank failing below 200-day EMA

```
Risk Profile:
- Favorable: V-shaped reversals reward aggressive entries
- Unfavorable: Quick fills, gaps, emotional exits
- Action: Only take setups with 1:3+ risk-reward; consider cash sitting
```

#### 🔴 **Panic (Market Breaking)**
- **VIX > 30, Nifty -5%+ intraday, Circuit breakers hit**
- Position size: **25% of baseline** (only core holds; no new entries)
- Optimal action: Close 50% of holdings, raise cash, wait for stabilization
- Examples: Rate hike shock, geo-political event

```
Risk Profile:
- Favorable: Capitulation reversals (but rare)
- Unfavorable: "Catching falling knife" kills accounts
- Action: Sit. Wait. Only enter on +3% reversal confirmation
```

### Market Risk Multiplier Table

| Regime | VIX | Position Size | Stop Buffer | Max Losers Until Exit |
|--------|-----|---------------|-------------|----------------------|
| Uptrend | <15 | 100% | -1.0% | 5–6 trades |
| Consolidation | 15–20 | 70% | -1.5% | 3–4 trades |
| Correction | 20–30 | 50% | -2.0% | 2 trades |
| Panic | >30 | 25% | -3.0% | 1 trade (exit) |

---

## 3. Per-Trade Risk: The 1% Rule & Variations

**Per-trade risk** is the amount of capital you're willing to lose on **one single trade**, expressed as a percentage of your account.

### The Baseline: 1% Risk Rule

```
Position Size (shares) = (Account × 0.01) / (Entry – Stop Loss)
```

**Example:**
- Account: ₹500,000
- Entry: ₹2500
- Stop: ₹2400
- Risk per trade: ₹5,000 (1% of account)

```
Shares = ₹5,000 / (₹2500 – ₹2400)
       = ₹5,000 / ₹100
       = 50 shares
```

At close: 50 shares × ₹2500 = ₹125,000 deployed.

### When to Break the 1% Rule

#### ✅ **Increase to 1.5–2% Risk**
- **High-conviction setups:** Cup-with-handle, stage-2 breakouts, sector RSI extremes
- **Tight stops:** <0.8% from entry (less capital at risk)
- **Favorable regime:** Strong uptrend, sector leading
- **Track record:** This exact setup netted +2R, +1.8R, +1.5R last 3 times
- **Example:** INFY in strong bull flag with tight stop — 2% risk acceptable

#### ⚠️ **Drop to 0.5% Risk**
- **Loosely defined setups:** "It looks like it might go up" (vague!)
- **Wide stops:** >2% from entry (too much at risk per share)
- **Unfavorable regime:** Consolidation or early correction
- **New setup type:** You've never traded this pattern before
- **Example:** Untested earnings-reaction play, drop to 0.5%

#### 🚫 **Never Exceed 2% Per Trade**
- Even for "sure thing" setups, 2% is the hard ceiling
- This ensures 50 straight losses don't blow the account (50 × 2% = 100%)
- Professionals won't risk more than 2% because:
  - Losing streaks happen (even to 60%+ win-rate traders)
  - Emotional trades creep up to 3–5% after losses (revenge trading)
  - One bad week at 3% = account recovery takes 6 months

### The Compound Effect: Why 1% Wins

| Scenario | Per-Trade Risk | Win Rate | Avg Winner | Avg Loser | Annual Return |
|----------|----------------|----------|-----------|-----------|----------------|
| Aggressive | 5% | 55% | +2R | -5% | **-12%** (blown up) |
| Reckless | 3% | 60% | +1.5R | -3% | +18% (volatile) |
| **Professional** | **1%** | **55%** | **+1.5R** | **-1%** | **+27% (smooth)** |
| Cautious | 0.5% | 50% | +1.2R | -0.5% | +8% (slow) |

**The takeaway:** 1% per trade + realistic expectations (55% win, 1.5R avg) = sustainable +25%+ annual compounding.

---

## 4. Situation-Based Risk: Context Adjustments

**Situation-based risk** says: *"The same position size is not equally risky across different scenarios."* A trade 30 minutes before market close is different from one at 10:30 AM.

### Critical Situations & Adjustments

#### 📍 **Time of Day**

| Time Window | Trade Count | Position Size | Stop Distance | Why |
|-------------|-------------|---------------|----------------|-----|
| 9:15–9:45 AM | 1–2 MAX | 80% | Tight (-0.8%) | Gap fills, opening noise |
| 9:45–2:30 PM | Unlimited | 100% | Normal (-1.0%) | Clean trends, best liquidity |
| 2:30–3:15 PM | 1–2 MAX | 70% | Looser (-1.5%) | Profit-taking, closing rallies |
| 3:15–3:29 PM | 0 | 0% | N/A | Close = dumpster fire; avoid |

**Real scenario:**
- 9:30 AM: Enter RELIANCE breakout above ₹2500 (80% size)
- 9:55 AM: It drops to ₹2480 (near stop); **don't panic, close = profit**
- 2:35 PM: Enter TCS breakout (70% size, looser stop) — lower conviction time

#### 📊 **Earnings Dates**

| Window | Position Size | Action |
|--------|---------------|--------|
| >5 days pre-earnings | 100% | Normal trading |
| 5 days before | 80% | Start trimming |
| 3 days before | 50% | Cut to core; no new entries |
| 2 days before | 25% | Exit profit-takers; hold only core |
| 1 day before | 0% | **Flat. 100% cash.** |
| Earnings day | 0% | **Watching, not trading** |
| +1 day after | 50% | Cautious re-entry; verify trend |
| >3 days after | 100% | Normal operations resume |

**Why?** Earnings move 4–8% overnight; a 1% stop-loss is useless. Gap through your stop = margin call.

#### 📉 **Losing Streak (3+ losses in a row)**

| Streak Length | Position Size | Action |
|---------------|---------------|--------|
| 0–2 losses | 100% | Normal |
| **3 losses** | **50%** | Cut size, review setups |
| **4 losses** | **25%** | Sit for 2 days, analyze |
| **5+ losses** | **0%** | **STOP TRADING.** Weekend deep-dive |

After 5 losses, your judgment is compromised. Take Saturday off, review setups, come back Monday fresh.

#### 🎯 **Confluence of Bad Signals**

If 2+ of these apply, **cut position size to 30%:**
- Market choppy (VIX 18–25) + Setup early-stage (not yet confirmed)
- Stock weak vs. sector (RS <50) + Market in early correction
- Earnings within 4 days + Position sizing feels uncomfortable
- You're already holding 4 positions + This setup is "just OK"

#### ✅ **Confluence of Good Signals**

If 3+ of these apply, **you can go to 1.5× normal size** (but never exceed 2% per trade):
- Market strong uptrend (VIX <12, Nifty fresh highs) + Stock RS >85 leading
- Setup textbook-perfect (clear cup-handle, volume, breakout confirmed)
- 10+ period streak of wins (your edge is hot); low risk of over-leverage
- Open risk still <3%
- >3 hours left in trading day

---

## 5. Setup-Based Risk: Pattern-Dependent Position Sizing

**Setup-based risk** recognizes that some chart patterns have **inherently better risk-reward** than others. A tight cup-with-handle risks 0.5%; a broken reversal risks 2%.

### High-Confidence Setups → Can Go 1.5× Normal Size

#### 🏆 **Cup-with-Handle (Tight)**
- Stop <1% below handle low
- Entry: Close above handle resistance
- Target: Cup height above breakout
- **Risk-Reward: Typically 1:4 or better**
- **Position Size Adjustment: +25% (1.25× normal)**
- **Example:** INFY forms 8-week cup, handle 3%, tight stop below handle

#### 🏆 **Stage-2 Breakout (Established Uptrend)**
- Stop: Under 50-EMA or prior swing low (tight, <1%)
- Entry: Close above former resistance
- Target: Next resistance or 4–8% range
- **Risk-Reward: Typically 1:2 to 1:3**
- **Position Size Adjustment: +15% (1.15× normal)**
- **Example:** TCS consolidating, finally breaks above ₹4000 on volume

#### 🏆 **Pocket Pivot (intraday, fast)**
- Stop: Intraday low + 0.3%, very tight
- Entry: Close above prior close, on volume
- Target: Previous high
- **Risk-Reward: Often 1:1.5 to 1:2 intraday**
- **Position Size Adjustment: +10% (1.1× normal, usually small-cap)**
- **Example:** SBIN 3-day consolidation, breaks on high volume 11:15 AM

### Medium-Confidence Setups → Use Normal (1×) Size

#### 🟡 **Shallow Flag Pullback**
- Stop: Under flag low, <1.5%
- Entry: Break above flag, on volume
- Target: Approximate flag height above breakout
- **Risk-Reward: Typically 1:1.5 to 1:2.5**
- **Position Size Adjustment: Normal (1.0× baseline)**
- **Example:** HDFC Bank pulls back 3%, consolidates, resumes up

#### 🟡 **3-Bar Reversal**
- Stop: Prior swing low, <1.5%
- Entry: Close above prior close on high volume
- Target: Next resistance, usually 50–150 pips
- **Risk-Reward: Typically 1:1.2 to 1:2**
- **Position Size Adjustment: Normal (1.0× baseline)**
- **Example:** Intraday bounce off support; enters on bar #3 strength

#### 🟡 **Sector Strength Play (Momentum)**
- Stop: Under 20-EMA, <2%
- Entry: Sector leading, stock joining the party
- Target: Catch momentum for 2–5 days
- **Risk-Reward: Typically 1:1 to 1:2**
- **Position Size Adjustment: Normal (1.0× baseline, tight risk management)**
- **Example:** IT sector rallying, jump into WIPRO as sector plays

### Lower-Confidence Setups → Cut to 0.5–0.7× Size

#### 🔴 **Loose Reversal**
- Stop: >2% below entry (wide, risky)
- Entry: Vague technical "looks bouncy"
- Target: Maybe 1–2% (unclear)
- **Risk-Reward: Unclear, potentially 1:0.5 (bad!)**
- **Position Size Adjustment: -40% (0.6× normal; barely worth taking)**
- **Example:** Avoid these. Don't trade "feelings."**

#### 🔴 **Earnings Bounce (Post EA)**
- Stop: Below spike low, often 3%+
- Entry: Overextended bounce
- Target: Fill gap (often fails; snap back)
- **Risk-Reward: Often 1:0.8 (you lose more than you win)**
- **Position Size Adjustment: -50% (0.5× normal, or skip it)**
- **Example:** INFY post-earnings up 4%; you catch it. Stay small.**

#### 🔴 **Unconfirmed Breakout**
- Stop: Any failed attempt re-tests stop (wide, 2%+)
- Entry: Breaking resistance but low volume
- Target: Vague
- **Risk-Reward: Typically 1:1 at best (not worth it)**
- **Position Size Adjustment: -60% (0.4× normal; skip)**
- **Example:** Stock breaks ₹1000 on 25M shares (needs 50M); pass.**

### Setup Risk-Reward Matrix

| Setup Type | Stop Width | Upside/Downside | Frequency | Position Size |
|------------|------------|-----------------|-----------|---------------|
| Cup-with-handle | 0.5–0.8% | 1:4 | Weekly | **1.25–1.5×** |
| Stage-2 breakout | 0.8–1.2% | 1:2.5 | 2–3×/week | **1.1–1.2×** |
| Flag recovery | 1.2–1.5% | 1:2 | 2–3×/week | **1.0×** |
| Pocket pivot | 0.3–0.6% | 1:1.5 | Daily | **1.0×** |
| Sector momentum | 1.5–2% | 1:1.5 | 3–4×/week | **1.0–0.9×** |
| Loose reversal | 2%+ | 1:1 or worse | Avoid | **0.5×** |
| Earnings bounce | 3%+ | 1:0.8 | Avoid usually | **Skip** |

---

## The Complete Risk Framework in Action

### Real Day: Monday Morning

**Account:** ₹1M  
**Baseline 1% Risk:** ₹10,000  
**Max Open Risk:** 3.5% (₹35,000)  
**Current Status:** 2 open positions (₹15,000 risk)

#### 9:25 AM — Market opens, Nifty gaps up 0.8%, VIX 13 (uptrend regime)

**Opportunity #1:** RELIANCE cup-with-handle breakout  
- Entry: ₹2500 (closes above handle resistance)
- Stop: ₹2405 (below handle; tight!)
- Stop distance: ₹95
- **Setup quality: Cup-with-handle → 1.2× sizing**
- **Per-trade risk: 1.2% × ₹10,000 = ₹12,000**
- **Shares needed: ₹12,000 ÷ ₹95 = 126 shares**
- **New open risk: ₹15,000 + ₹12,000 = ₹27,000 (2.7% total) ✅ Under 3.5%**
- **Action: TAKE IT**

#### 11:45 AM — TCS showing loose reversal after morning bounce

**Opportunity #2:** TCS "bounce off 20-EMA"  
- Entry: ₹3900
- Stop: ₹3800 (wide!)
- Stop distance: ₹100
- **Setup quality: Loose reversal → 0.5× sizing**
- **Per-trade risk: 0.5% × ₹10,000 = ₹5,000**
- **Shares needed: ₹5,000 ÷ ₹100 = 50 shares**
- **New open risk: ₹27,000 + ₹5,000 = ₹32,000 (3.2% total) ✅ Under 3.5%**
- **Action: TAKE IT (small size)**

#### 2:35 PM — HDFC Bank potential flag breakout, but 50 min to close

**Opportunity #3:** HDFC flag breakout  
- Entry: ₹2000
- Stop: ₹1950
- Stop distance: ₹50
- **Setup quality: Flag recovery → 1.0× normal**
- **BUT time adjustment: -30% for late afternoon**
- **Final: 0.7× sizing**
- **Per-trade risk: 0.7% × ₹10,000 = ₹7,000**
- **Shares needed: ₹7,000 ÷ ₹50 = 140 shares**
- **New open risk: ₹32,000 + ₹7,000 = ₹39,000 (3.9% total) ❌ Over 3.5%**
- **Action: PASS** (or trim a small position first)

#### 3:15 PM — Market enters closing chaos

- **All remaining open positions:** Reduce size by 25% (it's last 15 min)
- **New trade entries:** STOP (no new entries in chaos window)

---

## The Risk Management Checklist Before Every Trade

Use this checklist **before you hit buy:**

```
□ What's my stop loss? (Must be <2% below entry)
□ How much can I lose if stopped? (In rupees)
□ Is this 1% or less of my account? (Rule of thumb)
□ What's my open risk now vs. max? (<3.5% target)
□ What market regime are we in? (Adjusting size accordingly)
□ Are we near market close? (<1.5 hours = reduce 30%)
□ Earnings within 3 days? (Reduce 50% or skip)
□ Am I in a losing streak? (3+ = reduce size)
□ Setup quality: High/Medium/Low confidence? (Scale 1.2× / 1.0× / 0.5×)
□ Does this fit my daily plan, or am I revenge trading?
□ Could I sleep tonight holding this position?
```

If you can't answer confidently, **don't take the trade.**

---

## The Psychology of Risk Management

**The Hard Truth:**
- Risk management isn't exciting. Position sizing isn't romantic. It doesn't feel like "winning."
- But traders who master risk management are the only ones who survive 10+ years in the market.
- Gamblers and revenge traders are gone in 2–3 years.

### Common Risk Mistakes (And How to Avoid Them)

### ❌ Mistake #1: Increasing Size After Wins ("Hot Hand")
After 4 profitable trades, traders feel invincible and jump to 2–3% per trade.  
**Then:** One gap down (even 1:2 on that trade) wipes out 3 weeks of gains.

**Fix:** Stick to fixed position sizing. Increase size only after 4–6 weeks of consistent +15% returns, and increase by 10% max (1% → 1.1%, etc.).

### ❌ Mistake #2: Holding Through "Just One More Day" to Hit Target
Entry ₹100, target ₹120 (20% upside), stop ₹95. Stock hits ₹118, then pulls back to ₹103.  
"It'll hit ₹120 tomorrow!"  
Next day: Gap down to ₹98. Stop triggered, -2.5% loss.

**Fix:** Add a "time stop": If target isn't hit in X days (2–3 days for swing), close at profit. Don't let winners become losses.

### ❌ Mistake #3: Revenge Trading After a Loss
Take a stop-loss on INFY, immediately enter WIPRO without a plan.  
"I'll make back the loss today!"

**Fix:** After any stop-loss, take a 30-minute walk. Review the setup. Don't revenge trade. The next trade is independent.

### ❌ Mistake #4: Ignoring Open Risk ("But They're All Good Setups!")
5 positions, ₹20K risk each = ₹100K (10% of ₹1M account), then Nifty gaps down 2%.  
All 5 stop simultaneously. Account down -10% in one day.

**Fix:** Check open risk before EACH trade. If you're at max, close something first.

---

## Summary: The Risk Management Formula

```
✓ Open Risk (portfolio level):    Max 3–5% of account
✓ Market Regime (context):         Adjust 50–150% of normal size
✓ Per-Trade Risk (isolated):       Max 1–2% of account per trade
✓ Situation Context (time, EA):    Reduce 25–50% in risky windows
✓ Setup Quality (pattern):         Scale 0.5–1.5× based on confidence

Final Position Size = (Account × Risk %) ÷ (Entry – Stop)
```

**Follow this, and you'll never blow up an account.**

Ignore this, and you'll blow up multiple accounts. I guarantee it.

