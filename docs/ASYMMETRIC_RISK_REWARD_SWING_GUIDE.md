# Asymmetric Risk–Reward for the Professional Swing Trader

> **Purpose of this guide.** Swing trading edges rarely live in a single chart pattern. They live in **pairing** (1) a setup with a defined worst case, (2) a market regime that pays that setup, and (3) position sizing that keeps losers boring while winners can compound. This document is a **working framework**—checklists, regime lenses, and scenario tables—not a promise of outcomes.

> **Core principle:** Asymmetry isn't about winning more often. It's about structuring every trade so that **three small losses are erased by one moderate winner**, and the occasional life-changing winner pays for years of boring small losses. This flips traditional risk perception: you want frequent small losses if massive gains are the tail outcome.

---


## 1. Definitions (precision matters)

### Risk (R)

**R** is the dollar or percentage loss at your **planned invalidation**, not at “where I hope it stops.”  
If you resize mid-trade without rewriting R, you are trading a different position—do it consciously.

### Reward (multiple of R)

**Target R** is hypothetical until booked. What matters for process is **distribution**: typical winner size, tail winners, and average loser size **after** exits—not what the chart “could” do.

### Expectancy (per trade, simplified)

\[
E \approx P(\text{win}) \times \overline{\text{winner}} - P(\text{loss}) \times \overline{\text{loser}}
\]

(R-multiple formulation is equivalent when losers are normalized to ~1R.)

**Asymmetry** means the **right-hand tail** of outcomes (large winners, or many modest winners) dominates the **left tail** (losers capped near −1R). Professional swing trading optimizes **expectancy and survival**, not the aesthetics of a single trade's stated ratio.

#### Worked expectancy example: Symmetric vs Asymmetric

**Symmetric approach** (most retail traders):
- Win rate: 55% | Avg winner: +1.5R | Avg loser: −1R
- Expectancy = (0.55 × 1.5) − (0.45 × 1) = **+0.375R per trade**
- Feels balanced. Is mediocre. Requires constant trading just to compound slowly.

**Asymmetric approach** (professional traders):
- Win rate: 35% | Avg winner: +3.5R | Avg loser: −1R
- Expectancy = (0.35 × 3.5) − (0.65 × 1) = **+0.575R per trade**
- Lower win rate, but **+0.20R advantage per trade**. On 100 trades: +20R additional profit.

**On ₹10,00,000 account, risking 0.75% (₹7,500 per trade):**
- Symmetric: 100 trades @ +0.375R = +₹28,125 gain
- Asymmetric: 100 trades @ +0.575R = +₹43,125 gain

**Same account, same market, same risk-per-trade. Asymmetry adds ₹15,000 over 100 trades.** That's why professionals hunt it obsessively.

### Why "stated R:R" lies on the spreadsheet

- **Slippage, gaps, and widening spreads** subtract from winners and add to losers.
  - Entry slippage: −$0.05 on a 1,000-share position = −$50 off your immediate profit
  - Exit gaps at earnings: −$0.20 per share on a position that was supposed to be +$0.50 winner
  - Wide spread at 4:00 p.m.: costs 2–4 cents per share to exit cleanly
  
- **Early scratches** turn −1R plans into −0.3R noise—but destroy tail payoff if done habitually.
  - Benefit: Feel safer exiting 5% winners early
  - Cost: Miss the 5R+ winners that only happen on trades you didn't scalp
  - Trap: Exit 30 small +0.3R winners, miss two +5R winners → net -0.5R
  
- **Regime shifts** between entry and exit change the same pattern's payoff distribution.
  - You enter on a bull flag in a strong trend. Overnight gap down, regime flips to bear.
  - Same price structure, vastly different holding period and outcome odds
  
So: **model asymmetry as a process**, not as one number printed at entry. Track distribution over 30–50 trades before believing any single trade's stated ratio.


---

## 2. Two axes of analysis (always combine)

| Axis | Question | What it controls |
|------|----------|------------------|
| **Setup / structure** | Where is invalidation? What proves failure vs noise? | Stop placement, time budget, pattern-specific expectancy |
| **Market condition / regime** | Is breadth supportive? Is volatility expanding or compressing? Trend vs chop? | Trade frequency, setup selection, size multiplier, holding period |

**Rule:** Never upgrade size on setup quality alone when regime disagrees. Never dismiss setup quality because regime is strong—both matter.


---


## 3. Where asymmetric opportunities tend to cluster

These are **contexts**, not automatic trades. Each has a typical failure mode.

### 3.1 Market crash / sharp correction (long side)

**Opportunity thesis:** Forced liquidation and correlation → dislocations; survivors with strong bases can mean-revert or trend later.

**Asymmetry mechanism:** Small, staged entries with wide **logical** stops (or smaller size for same dollar risk); payoff if a durable bounce or new leader emerges.

**Failure mode:** Catching a falling knife without time stop; averaging down without new information.

**Why this matters:** In crashes, the first bounce can be 8-15% fast before rolling over again. But a true stabilization can be 30-50% over weeks. Asymmetry lives in **timing and regime confirmation**, not in the chart alone.

**Worked example:**
- Stock: XYZ, rallied from ₹100 to ₹180. Market crashes 10%.
- XYZ drops to ₹145 on day 2 of crash. Close: above 50-day MA, volume heavy.
- Plan: Entry ₹145, stop ₹130 (logical invalidation = breaks 50-day MA). Target ₹180+ if bounce confirms (that's +2.4R).
- Position size: 0.5% risk (₹5,000) ÷ ₹15 per-share risk = 333 shares
- Pre-entry checklist:
  - [ ] Is this day 1–3 of the crash? (Earlier = more likely knife-catching)
  - [ ] Is underlying sector/index stabilizing or still falling hard?
  - [ ] Time stop: "If no close above entry after 5 days, exit"
  - [ ] Second entry: Only if close above 50-day MA on volume

**Checklist (before adding swing long in crash context)**

- [ ] Index / sector trend: is this **capitulation day**, **first stabilization**, or **protracted bear**?
- [ ] Stock: relative strength vs sector/index during decline?
- [ ] Liquidity: can you exit without being the exit?
- [ ] Event risk: results, debt, dilution in window?
- [ ] Plan: max adds, max portfolio heat, **time** stop if no stabilization?
- [ ] Recovery criteria: What would prove this was NOT a knife-catch? Write it down before entry.

### 3.2 Market top / distribution (long exits & selective shorts)

**Opportunity thesis:** Trend exhaustion, breadth divergence, failed breakouts—distribution favors **tighter feedback** on wrongness if shorts are structural.

**Asymmetry mechanism (short):** Defined risk above resistance / pivot; payoff if imbalance reverses. **Gap risk against shorts** is real—in equities, asymmetry often requires **smaller size** or options-defined risk.

**Failure mode:** Shorting strength too early (squeeze); ignoring borrow/carry; underestimating gap risk.

**Why gap risk matters:** A short position into potential earnings can gap up 5–10% before market open. If you risk 1R to the upside and the gap is 2R, you've broken your own sizing rule. This is why **shorted shares typically deserve 25-50% lighter sizing than long positions** in equities.

**Worked example:**
- Stock: HYPE, rallied from ₹500 to ₹850 in 8 weeks. Last 3 closes made lower highs. Volume is declining on rallies. Earnings in 10 days.
- Setup: Short ₹835 (below the last lower high at ₹840). Stop ₹860 (just above resistance). Target: ₹750 (measured move = −2.3R).
- Sizing consideration: Earnings risk → reduce to 0.4% risk instead of 0.75%
- Position: 0.4% risk (₹4,000) ÷ ₹25 risk per share = 160 shares
- Pre-entry checklist:
  - [ ] Earnings before/during holding period? If yes, reduce size or use put spreads
  - [ ] Is there hard resistance at ₹860 or just "it feels extended"? (Price-based, not mood-based)
  - [ ] Borrow rate? Is the stock borrowed easy (easy-to-borrow list) or hard?
  - [ ] Dividend: Any upcoming that could cause covering?
  - [ ] Time frame: How many days are you willing to hold? Set it now.

**Checklist (short swing in topping context)**

- [ ] Structural pivot / lower high sequence—not only "feels extended"?
- [ ] Breadth confirming (fewer names making highs)?
- [ ] Stop **above** invalidation, not inside noise?
- [ ] **Gap risk** acceptable (results, index gaps)? If uncertain, reduce size.
- [ ] Position sized so a gap up does not breach portfolio rules?
- [ ] Borrow available and rate acceptable?
- [ ] Plan for assignment/recall if shares become hard-to-borrow mid-trade?

### 3.3 Parabolic blow-off (stop the rocket—or wait)

**Opportunity thesis:** Climax runs invite **mean reversion** or **sharp resets**; payoff can be fast; failure can be violent.

**Asymmetry mechanism:** Tight **logical** invalidation (e.g., above last impulse bar / AVWAP band—whatever your playbook uses); **small size** because variance explodes.

**Failure mode:** Fighting momentum without a time-based review; oversized short into squeezes; staying in a losing parabolic short too long hoping for reversal.

**Why size matters in parabolic trades:** Parabolic moves can extend 20-30% before rolling. If you short ₹500 with a ₹510 stop (expecting mean reversion), you're risking it going to ₹600+ before reversing. Over-sizing a parabolic mean-reversion trade is one of the fastest ways to blow up.

**Trade sizing on parabolic shorts should be 30-50% of normal R%.**

**Worked example:**
- Stock: BOOM, rallied from ₹100 to ₹480 in 12 weeks. Angle of accent is visibly steeper each week. Trading range on last impulse bar: ₹470–₹487. Gap: parabolic extension, no resistance overhead.
- Setup: Short ₹480. Stop ₹492 (above last impulse high). Target ₹420 (−2R target).
- Sizing: Parabolic context → use 0.35% risk (instead of standard 0.75%)
- Position: 0.35% risk (₹3,500) ÷ ₹12 risk per share = 291 shares
- Pre-entry checklist:
  - [ ] Is this truly parabolic (accelerating rate of change) or just a strong trend? (Very different)
  - [ ] Time stop: "If I don't see reversal signals by day 3, exit regardless"
  - [ ] Invalidation is clean: above ₹492 = trade is wrong, exit immediately
  - [ ] Expected reward if I'm right: ₹480 → ₹440 over 3–7 days? (Realistic or fantasy?)

**Checklist**

- [ ] Parabolic **identified** (rate of change, extension vs MAs, volume)?
- [ ] Entry is **trigger-based**, not narrative ("must collapse")?
- [ ] Hard time stop: "If X sessions without follow-through, exit"?
- [ ] Risk capped at **0.3-0.5% of account**, not full 0.75%?
- [ ] Invalidation is sharp and defined, not subjective?
- [ ] Plan exit on first reversal bar or wait for 1-2R of room back down?

### 3.4 Base breakout (bread-and-butter swing)

**Opportunity thesis:** Compression → expansion; invalidation below base.

**Asymmetry mechanism:** Stop below structure; reward scales if trend and breadth cooperate.

**Failure mode:** Late-stage breakout in weak regime; ignoring volume/participation; entering into overhead supply.

**Why base quality matters:** A tight VCP base with a 10% risk and potential 40% move is asymmetric. A 20-bar, loose, coiling base with overlapping candles is a trap. Same chart pattern, wildly different asymmetry due to **base structure specifics**.

**Worked example:**
- Stock: BUILDER, 50-day MA at ₹285. Stock built a base from ₹280–₹290 over 6 weeks. Base is tight (only ₹10 range), 4 touches of the lows, declining volume into the base.
- Setup: Long on breakout above ₹293 (above prior resistance). Stop ₹278 (below the base lows). Base midpoint projection: ₹310 (≈+2.3R). Could run to ₹330 if trend continues (+2.6R).
- Position: 0.75% risk (₹7,500) ÷ ₹15 risk per share = 500 shares
- Pre-entry checklist:
  - [ ] Base structure: How many weeks? How tight? Is it **compression**?
  - [ ] Volume profile: Is volume declining into base (healthy) or increasing (manipulation risk)?
  - [ ] Relative strength: Is this stock stronger than the sector/index? (NOT required, but adjusts conviction)
  - [ ] Resistance overhead: Is there supply at ₹295, ₹300 that makes ₹310 unlikely without a regime shift?
  - [ ] Regime: Is the broad market in an uptrend, chop, or decline? (Adjusts size or skip)

**Checklist**

- [ ] Base length / depth consistent with your stats?
- [ ] Pivot clear; **failed breakout rules** defined? (Does a close below base low = exit, or can it bounce internally?)
- [ ] Relative strength vs peer group?
- [ ] Regime supports trending follow-through (not always required, but adjusts **size**)?
- [ ] Entry trigger: Clean break above resistance OR wait for close above? (Breakout-on-break vs close-above can have different odds)
- [ ] Volume: Does breakout have adequate volume, or is it thin? (Thin = higher squeeze risk)


---


## 4. Setup quality × regime matrix (expectancy lens)

Use this to **adjust frequency and size**, not to pretend certainty.

| Setup family | Strong bull / risk-on | Neutral / chop | Weak / bear |
|--------------|------------------------|----------------|---------------|
| Base breakout (high-quality) | Full playbook size | Reduce size; faster partials | Fewer trades; require RS leader |
| Pullback to rising MA | Often favorable | Whipsaw risk ↑ | Only strongest groups |
| Mean reversion long after flush | Selective (needs stabilization) | Often noisy | Can work if oversold + RS |
| Short parabolic / climax | Rare long-side focus | Define squeeze risk | Align with trend down |
| Short distribution | Lower squeeze risk if breadth weak | Still respect rallies | Higher conviction possible |

**Operational rule:** When regime and setup **both** align → normal risk. When only one aligns → **reduce risk or skip**. When neither aligns → cash is a position.


---


## 5. Risk–reward vs expectancy (research framing)

### What academic and practitioner literature agrees on

- Long-run survival requires **negative skew control**: limiting tail losses at portfolio level.
- **Positive expectancy** can coexist with **low win rate** if winners are sufficiently fat-tailed *and* realized—not hypothetical.
- Transaction costs and gaps turn apparent edges negative unless samples are large enough.

### What to track (minimum professional set)

| Metric | Why |
|--------|-----|
| Average R win / loss | Reality check vs plan |
| Distribution of R outcomes | Tail winners vs clipped winners |
| Win rate by **setup tag** | Pattern viability |
| Win rate by **regime tag** | Context viability |
| Largest consecutive losers | Stress-test sizing |

### Sample-size humility

A few great trades **do not** prove an edge. Neither do a few losers disprove it. Edge claims require **enough trades stratified by setup and regime**—journals exist precisely for this.

---


## 5.5 How to Measure Asymmetry in Your Trades (Monthly Dashboard)

Asymmetry is not just a concept—it's measurable. Track these metrics monthly to quantify your actual edge.

### Core asymmetry metrics

| Metric | Formula | What it signals |
|--------|---------|-----------------|
| **Skewness** (L3 metric) | (Avg Win − Avg Loss) / Win Rate | Positive = asymmetric; > 0.50 = strong |
| **Payoff Ratio** | Avg Win (R) / Avg Loss (R) | Should be ≥ 2.0 for low win rates; ≥ 1.5 for 50%+ win |
| **Tail Ratio** | (Largest 10% of wins) / (Largest 10% of losses) | If < 1.5, your winners aren't actually fat-tailed |
| **Clipped Winners %** | (# early exits before 2R) / (# total winners) | > 50% = killing your best outcomes |
| **Win Rate by Setup** | (Wins in setup X) / (Total setup X trades) | May vary wildly; some setups suck in your hands |
| **Avg Win by Regime** | Average winner $ when market was (Bull/Chop/Bear) | Different regimes pay different setups |

### Example monthly tracking

**Month: January, 30 trades completed**

| Metric | Value | Color | Action |
|--------|-------|-------|--------|
| Win rate | 40% | ✓ Green | On target |
| Avg winner | 2.8R | ✓ Green | Strong payoff |
| Avg loser | −0.95R | ✓ Green | Tight discipline |
| Expectancy | +0.68R | ✓ Green | Excellent |
| Avg win in bull regime | 3.2R | ✓ Green | Bull setups working |
| Avg win in chop regime | 1.8R | ⚠ Yellow | Reduce size in chop |
| Clipped winners % | 35% | ✓ Green | Letting winners breathe |
| **Skew** | 0.68 | ✓ Green | Highly asymmetric |

**Interpretation:** This trader has true asymmetry. She's winning only 40% but her payoff distribution is so favorable that expectancy is +0.68R. She should increase size slightly in strong bull regimes and reduce in choppy regimes.

---


## 6. Professional pre-trade checklist (asymmetric lens)

Use this checklist **before every entry**. It should take 60–90 seconds. If you skip it, you skip discipline.

### A. Thesis (The core idea)

- [ ] **One sentence:** "If wrong, I lose ~₹_____ because ______."
  - Example: "If wrong, I lose ₹7,500 because price closes below the 50-day MA and breaks the base."
  - Not acceptable: "If wrong, because the market is against me." (Vague, emotional)
  
- [ ] Invalidation is **price-based**, not mood-based.
  - Example: "Stop at ₹278 (below base lows)" ✓
  - Not acceptable: "I'll get out if it doesn't feel right" ✗

- [ ] What timeframe are you holding? (1 day, 1 week, 3 weeks?)
  - Holding period affects position sizing and discipline

### B. Context (Market & sector regime)

- [ ] Broad market regime tagged (your taxonomy—trend, chop, correction, bear).
  - Is this a strong bull where most breakouts work? OR chop where most mean-revert?
  
- [ ] Sector / peer relative strength vs. broad market.
  - Is the sector leading or lagging? Override single-stock setup quality.
  
- [ ] Event risk in your holding window?
  - Earnings, Fed announcement → consider options or smaller size

### C. Risk budget (Position sizing confirmation)

- [ ] This trade's R is ≤ per-trade cap (typically 0.5–1.0% of account).
  - Risk per trade = (Entry − Stop) × Shares
  - If calculated R exceeds cap → reduce shares, don't reduce stop
  
- [ ] Open portfolio heat (total open risk) allows new exposure.
  - If portfolio is already 3% at-risk across 4 positions, new 0.75% trade = 3.75% total
  - Rule: Never exceed 2–3% portfolio heat simultaneously
  
- [ ] Position size adjusted for regime/setup quality.
  - Strong bull + Type-A setup = 1.0% R
  - Narrow chop + Type-B setup = 0.4% R

### D. Payoff shape (Expected distribution)

- [ ] Planned partial / trail rules **written down before entry** (even if "hold full until X").
  - Examples:
    - "Exit half at +1.5R, hold half to +3R or trail by 5%"
    - "Hold full till close above moving average, then reassess"
  - Why: Prevents ad-hoc decisions and clipped winners
  
- [ ] Reward-to-risk ratio ≥ 2:1 at entry?
  - If entry to stop is ₹15 risk, target should be ₹30+
  - Below 2:1 → skip unless win rate is 65%+
  
- [ ] Known gap/event risk in holding window. (Priced in or not?)
  - Gap risk can turn a +2R trade into -1R before market open

### E. Kill criteria (When to exit if wrong)

- [ ] **Time stop** if setup requires proof by N bars/sessions.
  - "If no close above entry after 3 days, exit" (especially in reversions)
  - Prevents "holding on hope"
  
- [ ] **Behavioral invalidation** rules (volume, structure, breadth).
  - "If volume dries up for 2 consecutive days, exit"
  - "If target sector breaks below 50-day MA, re-evaluate all long positions"

---


## 7. Post-trade review (asymmetry maintenance)

**Immediate post-trade (within 24 hours)**
- Was actual R near planned R, or did emotion resize the stop?
- Was winner clipped **by rule** or **by fear**?
- Tag: setup ID + regime ID → expectancy dashboard.

**Log 5 key metrics:**
1. Setup type (Bull flag, VCP, Base breakout, etc.)
2. Market regime at entry (Bull, Chop, Bear, Correction)
3. Actual R in rupees (profit/loss)
4. R-multiple realized (e.g., +2.3R, −0.8R)
5. Exit quality (by plan, stopped out, time-stopped, squeezed, etc.)

---


## 8. Daily, Weekly, Monthly Professional Habits

**Asymmetry maintenance is a practice, not an event.** Use these habits to stay sharp.

### Daily (60–90 seconds)

- [ ] **Pre-market:** Tag today's expected regime (bull, chop, weak, crash, distribution?)
- [ ] **After each trade:** Log entry thesis, stop logic, regime tag
- [ ] **EOD:** Review any stops hit. Did the stop work as planned?
  - If stop was too tight (noisy)? Adjust for next similar setup.
  - If stop was clearly wrong (fundamentally wrong entry)? Adjust immediately.

### Weekly (15–20 minutes)

- [ ] **Trade count:** How many trades this week? Target 2–4 for amateur, 3–6 for pro.
- [ ] **Win rate by setup:** Tally wins/losses for each setup type you traded.
  - Bull flags: 3 wins, 1 loss (75%) ✓
  - Parabolic shorts: 0 wins, 2 losses (0%) ✗ → Reduce size or skip next week
  
- [ ] **Regime payoff:** Did your setup perform better in bull vs chop?
  - If significantly worse in one regime, adjust bias and sizing
  
- [ ] **Portfolio heat check:** Was I ever above 3% heat? If yes, why and what's the fix?
- [ ] **One "asymmetry win" analysis:** Pick your best trade this week. Why was it asymmetric? Replicate it.

### Monthly (45–60 minutes)

- [ ] **Full expectancy calculation:**
  - Total wins / Total trades = Win rate
  - Sum of winner R / Count of winners = Avg winner (R)
  - Sum of loser R / Count of losers = Avg loser (R)
  - Expectancy = (Win% × Avg Win R) − (Loss% × Avg Loss R)
  - Is expectancy ≥ +0.3R? If not, something is broken.
  
- [ ] **Skew calculation:**
  - (Avg Win − Avg Loss) / Win Rate
  - > 0.50 = strong asymmetry; < 0.25 = weak asymmetry
  
- [ ] **Tail winners check:**
  - What were my 3 largest winners? Sum them.
  - What were my 3 largest losses? Sum them.
  - If tail losses > tail winners, you're fighting asymmetry (too many big blowouts).
  
- [ ] **Setup viability:**
  - Rank your setups by win rate:
    - A-tier (> 50%): Do more of these. Increase size by 20%.
    - B-tier (40–50%): Keep as bread-and-butter. Standard size.
    - C-tier (< 40%): Either improve or abandon. Consider removing from rotation.
  
- [ ] **Regime payoff:**
  - What was average winner in bull regime? In chop? In bear?
  - Adjust next month's sizing: more size in best-paying regime, less in worst.
  
- [ ] **Clipped winners check:**
  - How many winners did I exit before 2R?
  - Target: ≤ 40%. If > 60%, you're killing asymmetry by over-managing winners.
  
- [ ] **Red flag audit:**
  - Largest consecutive losses: Was it 5 losses or 8? (Implies sizing or setup issue)
  - Average loser size: Is it near −1R or creeping to −1.5R+? (Discipline slipping)
  - Thesis clarity: Am I trading price-based stops or mood-based stops?

- [ ] **One rewrite:** Pick the worst-performing setup or regime combo. Rewrite your plan for it.

### Example Monthly Habit Checklist Template

```
Month: _________

✓ EXPECTANCY
  - Win rate: ___%
  - Avg winner: ___R
  - Avg loser: ___R
  - Expectancy: +___R ✓/✗

✓ SKEW
  - Skew ratio: ___ (target > 0.50)
  
✓ TAIL WINS
  - Top 3 wins summed: ___R
  - Top 3 losses summed: ___R
  - Ratio: ___ (tail wins should 2-3x tail losses)

✓ SETUP VIABILITY
  - A-tier (best): ______ (___%)
  - B-tier (mid): ______ (___%)
  - C-tier (worst): ______ (___%)
  - Action: Increase size in A? Remove C?

✓ REGIME PAYOFF
  - Bull regime, avg win: ___R
  - Chop regime, avg win: ___R
  - Bear regime, avg win: ___R
  - Adjustment for next month: ________________

✓ DISCIPLINE CHECKS
  - Largest consecutive losses: ___
  - Average loser (should be ≈ −1R): ___R
  - Clipped winners (should be ≤ 40%): ___%
  - Biggest discipline slip: ________________
  
✓ NEXT MONTH FIX
  - One setup/regime combo to rewrite: ________________
  - New rule: ________________________________________
```

---


## 9. Quick Reference: One-Page Asymmetry Checklist

**Print this. Pin it to your screen. Use it before every trade.**

### THE SETUP
- [ ] Price-based invalidation: Where is my stop? (Not "where I hope")
- [ ] Asymmetric reward: Risk:Reward ≥ 2:1?
- [ ] Entry trigger: Clear signal or "feels like it"?

### THE CONTEXT
- [ ] Market regime tagged: Bull / Chop / Weak / Crash?
- [ ] Sector RS: Leading or lagging?
- [ ] Event risk: Earnings or gaps in my holding window?

### THE SIZE
- [ ] R ≤ my cap (0.75% or whatever)?
- [ ] Portfolio heat ≤ 3%?
- [ ] Regime adjustment: Full size or reduced?

### THE PAYOFF
- [ ] Exit plan written: "Exit half at ___R, trail the rest"?
- [ ] Acceptance rule: "No winner exits before 1.5R unless plan says so"

### THE KILL
- [ ] Time stop: "Exit if no proof by day N"
- [ ] Behavior stop: "Exit if volume dies or sector breaks"

---


### Monthly Math (5 minutes)

| Metric | Formula | Target | Your #s |
|--------|---------|--------|---------|
| Win rate | Wins / Total trades | 35–55% | ___ |
| Avg winner | Winner $ / # wins | 2–4R | ___ |
| Avg loser | Loser $ / # losses | ≈ 1R | ___ |
| Expectancy | (Win% × Avg W) − (Loss% × Avg L) | ≥ +0.3R | ___ |
| Skew | (Avg W − Avg L) / Win% | > 0.5 | ___ |

If expectancy < +0.3R: **Something is broken. Fix it before trading more.**

---


## 10. Related reading in this library

- **Risk–Reward & Expectancy** — expectancy math and journaling.
- **Market Regime Playbook** — regime definitions and transitions.
- **Swing Trader Risk Management** — portfolio floors and heat.
- **Heads I Win, Tails I Lose Very Little** — young-trade management without suffocating winners.

---


---


## 11. Closing principle

**Asymmetric swing trading is not betting big on predictions.** It is repeatedly structuring trades so that **many small, bounded losses** fund **occasional large, structured wins**, while regime and setup filters prevent death by a thousand marginal trades.

**The professional trader's mindset shift:**
- Not: "How often can I be right?"
- But: "How much do I make when right vs lose when wrong?"

- Not: "Is this trade a sure winner?"
- But: "Does this trade's payoff distribution give me +0.3R+ expectancy?"

- Not: "Can I double my account this month?"
- But: "Can I maintain and compound asymmetric payoff across 100+ trades?"

Asymmetry is your **moat**. Build it. Measure it. Stick to it.

---

*Professional swing trader guide — asymmetric risk–reward, setup & regime integration.*
