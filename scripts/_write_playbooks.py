"""Write all remaining playbook markdown files in one batch."""
from pathlib import Path

DOCS = Path("/Users/yeshwantha/IdeaProjects/SETUPS/docs")

files = {}

# ─────────────────────────────────────────────────────────────────────
# 1. STOP LOSS MASTERY
# ─────────────────────────────────────────────────────────────────────
files["STOP_LOSS_MASTERY.md"] = r"""# Stop Loss Mastery — How to Lose Like a Professional

> **Stops aren't where you give up. Stops are where you admit the trade idea was wrong.** Master your stops and the rest of trading gets quiet. Read this weekly until you stop second-guessing red.

## A Story Before the Rules

A trader buys a breakout at 500. He places a stop at 485 — just below the base. Three days later the stock dips to 486. His stop holds. Two days later it dips to 484. His stop triggers. He's out at a 3% loss.

He watches the stock reverse and run to 540 the next week.

He is furious. "The stop killed the trade!"

Wrong. The stop did its job. It said: "If price goes here, the setup is no longer working." Price went there. The setup wasn't working. He survived. What he should be furious about is that he didn't have a re-entry plan.

> A stop is a contract: when this happens, I am wrong.

---

## 1. The Three Truths of Stops

1. **Every trade needs a stop before you enter.** Not after. Not "I'll see how it acts." Before you click buy.
2. **The stop level is determined by the chart, not by your wallet.** The chart picks the stop. Your sizing adapts.
3. **Stops are honored mechanically, not emotionally.** Discipline isn't optional — it's the entire game.

---

## 2. The Five Types of Stops

### Type 1: Pattern Invalidation Stop (gold standard)
Place stop just below the structural low that defines the pattern.
- Bull flag -> below flag low
- VCP -> below final contraction low
- Cup & handle -> below handle low
- Double bottom -> below second low
- Inverse H&S -> below right shoulder

### Type 2: Volatility-Adjusted (ATR) Stop
- Stop = Entry - (1.5x to 2.5x ATR-14)
- Best for high-vol growth stocks where 8-10% noise swings are normal
- Position size shrinks with wider ATR stops

### Type 3: Percentage Stop (simplest)
- Fixed: Entry - 5-8% for swing trades
- The classic O'Neil rule: never let a loss exceed 7-8%
- Use when chart structure isn't clean enough for a logical level

### Type 4: Time Stop
- If the trade hasn't moved in your favor within 5-10 bars, exit regardless of price
- A trade you have to "wait out" is rarely a trade that pays

### Type 5: Trailing Stop
- After T1 hit, trail under each new higher low
- Or trail under 10 EMA (tight), 21 EMA (medium), 50 EMA (loose)

---

## 3. Stop Placement Decision Tree

```
Clean structural pivot within 8% of entry?
  YES -> Pattern invalidation stop (Type 1)
  NO  -> Stock high-volatility (ATR > 4% of price)?
         YES -> ATR stop, 2x ATR (Type 2)
         NO  -> 7-8% percentage stop (Type 3)

After break-even hit?
  -> Trail (Type 5)

Trade going nowhere for 7+ days?
  -> Time stop (Type 4)
```

---

## 4. Hard Stop vs Mental Stop

### Hard stops (placed in broker)
Use when you can't watch the screen, the stock is illiquid, or you have a discipline problem honoring mental stops.

### Mental stops (exit manually on close)
Use when you're a full-time screen watcher and the stock has wild intraday wicks that fake out hard stops.

### Hybrid (recommended)
Hard stop placed 1.5-2x ATR below your mental stop. Mental stop closes the trade on a confirmed close. Hard stop is a disaster guard for gaps.

---

## 5. Stops You Should Never Use

- "Round number" stops (everyone clusters there; algorithms hunt them)
- "Whatever I can afford to lose" stops (gambling, not trading)
- Moving stops down/away from price after entry (never correct in a long trade)
- "I'll average down" instead of stopping out (the single most expensive mistake)
- "It'll come back" stops (override = failure)

---

## 6. What to Do When Stopped Out

### The five-step post-stop ritual
1. Close the position. No negotiation.
2. Journal the trade within 30 minutes.
3. Do not look at the stock for 2 trading days.
4. Move on to the next setup.
5. End-of-week review: was the stop the right level?

### Re-entry rules
- Only if a new setup forms (not just price recovering)
- New pivot, new stop, new trade plan
- Wait at least one full session
- Size at half of what you originally used

---

## 7. Stop Discipline During Drawdowns

- Do not widen stops during a drawdown. Tighten position size instead.
- Do not move to mental stops if you've been failing hard stops.
- Do not skip the next signal out of fear.
- Do reduce size to half. Take the next 5 trades at 50% size. Get your read back.

---

## 8. Real Examples

### Bull flag
Entry 500, flag low 488, stop 486. Risk/share 14 = 2.8%. Below the level that defines the pattern.

### VCP with tight final contraction
Entry 620, contraction low 605, stop 604. Risk/share 16 = 2.6%. Below the bowstring.

### Cup with handle
Entry 1100, handle low 1062, stop 1060. Risk/share 40 = 3.6%. Below the rest.

### ATR stop on high-vol breakout
Entry 2400, ATR(14)=70, 2x ATR=140, stop 2260. Risk/share 140 = 5.8%. Structure too far, ATR-scaled to noise.

---

## 9. The Fatal Stop Mistakes

1. Placing the stop where you "won't feel it"
2. Trailing a stop before T1 — you cap profit while still risking initial loss
3. Cancelling the stop when "the news is just temporary"
4. Replacing a hit stop with a smaller position at a worse price
5. Letting one losing trade exceed 1.5x your normal risk allowance
6. Failing to stop out because you'd "feel stupid"

---

## 10. Daily, Weekly, Monthly Habits

### Daily
- [ ] Every open position has a stop in writing
- [ ] No stop has been moved away from price today
- [ ] If a stop was hit, the trade was closed within the rules

### Weekly
- [ ] All stops reviewed: any too tight, too loose, or stale?
- [ ] All trailing stops adjusted under new higher lows
- [ ] Loss log reviewed: were all losses <= planned risk?

### Monthly
- [ ] Total stops hit / total trades = "stop frequency" — stable?
- [ ] Average loss in R: should be <= 1.0R. If higher, you're letting losses run.
- [ ] Largest single loss: was it <= 2x normal risk? Root cause if not.
- [ ] Re-read this playbook in full.

---

## 11. The One-Page Cheat Sheet

```
Before entry -> write the stop down. No exceptions.
Stop level   -> determined by chart, not by wallet.
Stop type    -> pattern > ATR > percentage > time.
Hard or mental -> hard for gaps; mental on close for screen watchers.
Stop hit     -> close, journal, walk away 2 days.
Re-entry     -> new trade, half size, only if new setup.
Drawdown     -> reduce size, don't widen stops.
Never        -> average down, move stops away, skip the stop, "wait it out."
```

---

## 12. The Final Rule

> **The stop is not your enemy. The stop is your business partner. It's the only voice that's always right when you're wrong.**

The trader who survives a decade is not the trader with the best entries. It's the trader whose biggest losses are still small.

Honor every stop. Especially when it hurts.

---

*-- End of Stop Loss Mastery --*
"""

# ─────────────────────────────────────────────────────────────────────
# 2. PROFIT TAKING PLAYBOOK
# ─────────────────────────────────────────────────────────────────────
files["PROFIT_TAKING_PLAYBOOK.md"] = r"""# Profit Taking Playbook — How to Sell Without Regret

> **Entries get the glory. Exits get the money.** This guide teaches you when to take profits, how much to sell, and how to hold winners without giving everything back.

## A Story Before the Rules

A trader catches a 35% winner. He sells nothing. Two weeks later, the stock pulls back 15%. He still sells nothing — "it'll come back." It pulls back another 10%. Now his 35% gain is a 10% gain. He finally sells, feeling like he lost money even though he technically profited.

Another trader catches the same 35% move. At +20%, she sells one-third. At +30%, she trails the stop under the 21 EMA. When the pullback comes, her trailing stop takes her out at +28% on the remaining two-thirds. She books a clean +24% weighted gain.

> The first trader made more per share on paper. The second trader made more money in her account.

---

## 1. The Core Profit-Taking Models

### Model A: Fixed R-Multiple Exits
- Sell 1/3 at +2R
- Sell 1/3 at +3R
- Trail the final 1/3 under 21 EMA or each higher low

Best for: swing traders who want predictable, repeatable results.

### Model B: Percentage Targets
- Sell 1/3 at +10-15%
- Sell 1/3 at +20-25%
- Trail the rest

Best for: position traders in trending markets.

### Model C: Structure-Based Exits
- Sell at the next resistance zone / measured-move target
- Trail under each higher low
- Exit on a close below a key moving average

Best for: experienced traders who can read chart structure in real time.

### Model D: Time-Based Exits
- If the stock hasn't moved meaningfully in 7-10 trading days, exit at whatever the current price is
- Capital sitting still is capital not compounding

---

## 2. The Scaling System

The professional approach is to scale out of winners:

```
At entry:     100% position
At +1R:       raise stop to break-even
At +2R:       sell 33%, lock profit
At +3R:       sell 33%, trail stop tight
Remaining:    trail under 10/21 EMA until stopped out
```

This achieves three things:
1. You always lock some profit from winners
2. You always have exposure to big moves
3. You never give back 100% of a gain

---

## 3. When to Sell Into Strength (Climax Signals)

Sell aggressively when you see any of these:
- Largest-range candle in the entire move (climax bar)
- Gap up on huge volume after a long run (exhaustion gap)
- 3+ consecutive wide-range up days (parabolic thrust)
- Stock 30%+ above its 50 EMA
- Volume is 3-5x average but price can't hold gains (churning)
- RSI > 80 on daily after extended trend

These are distribution signals. Institutions are selling to retail. You should be joining institutions, not retail.

---

## 4. When to Hold (Not Every Pullback Is a Sell)

Hold through normal pullbacks when:
- Pullback is on lower volume (healthy)
- Price holds above key moving average (10/21 EMA)
- No distribution days (heavy volume closes in lower half)
- Market index is still constructive
- Stock's relative strength is still positive
- The pullback depth is normal for the prior move (3-5% after a 15-20% run)

> A normal pullback is not a sell signal. It's a test of your conviction — and your trailing stop is the judge, not your emotions.

---

## 5. The Sell Decision Matrix

```
Take profits now if:
  - Climax signals present (Section 3) -> YES -> sell 50-100%
  - Target hit (2R/3R or measured move) -> YES -> sell 33% + trail
  - Time stop: 7-10 days, no progress  -> YES -> exit position

Hold and trail if:
  - Normal pullback on low volume      -> HOLD -> trail under 21 EMA
  - Price above trailing stop           -> HOLD -> do nothing
  - RS still positive, market ok        -> HOLD -> let it work

Exit fully if:
  - Close below trailing stop           -> EXIT -> journal, move on
  - Distribution day inside the move    -> EXIT -> sell remaining
  - Market regime shifts to weak/bear   -> EXIT -> protect capital
```

---

## 6. The Common Profit-Taking Mistakes

1. **Selling 100% at the first target** — you cap upside on every trade. Winners pay for losers; let them.
2. **Holding 100% until the stop** — you give back all gains on every reversal.
3. **Moving the take-profit further away** because "it's working" — you're now gambling, not following a plan.
4. **Selling because you're "scared of losing gains"** — that's emotion, not signal. Use trailing stops, not anxiety.
5. **Not having a profit target at all** — "I'll know when to sell" is the most expensive sentence in trading.

---

## 7. Daily, Weekly, Monthly Habits

### Daily
- [ ] Are any open positions at +2R or beyond? Act on the scaling plan.
- [ ] Are any positions showing climax signals? Protect gains.
- [ ] Are trailing stops updated under new higher lows?

### Weekly
- [ ] Review closed winners: was profit taken at the planned levels?
- [ ] Any trades where you gave back > 50% of open gains? Root cause.
- [ ] Is the average profit per winner >= 2R? If not, you're cutting too early.

### Monthly
- [ ] Profit factor (gross wins / gross losses): should be > 1.5
- [ ] Average winner vs average loser: target 2:1 or better
- [ ] Percentage of trades where you held to max target: should increase over time
- [ ] Re-read this playbook.

---

## 8. The One-Page Cheat Sheet

```
At +1R  -> raise stop to break-even
At +2R  -> sell 1/3, lock profit
At +3R  -> sell 1/3 more, trail tight
Rest    -> trail under 10/21 EMA until stopped

Climax signals    -> sell aggressively
Normal pullback   -> hold, trail
No progress 7-10d -> exit (time stop)
Never            -> sell from fear alone, hold from hope alone
```

---

## 9. The Final Rule

> **The goal is not to sell at the exact top. The goal is to sell with a plan, at a level that makes mathematical sense, and without regret.**

You will never catch the top. You will occasionally sell too early. You will occasionally sell too late. But if you follow a scaling system, your average exit will always be good enough to compound wealth.

---

*-- End of Profit Taking Playbook --*
"""

# ─────────────────────────────────────────────────────────────────────
# 3. RISK REWARD EXPECTANCY
# ─────────────────────────────────────────────────────────────────────
files["RISK_REWARD_EXPECTANCY.md"] = r"""# Risk-Reward & Expectancy — The Math That Makes Traders Rich

> **You don't need to be right most of the time. You need to make more when you're right than you lose when you're wrong.** This is the math. Internalize it and you will never chase a 1:1 trade again.

## A Story Before the Rules

Trader A wins 70% of his trades. Average winner: +1R. Average loser: -1R.
Expectancy = (0.70 x 1) - (0.30 x 1) = +0.40R per trade. Decent.

Trader B wins only 40% of his trades. Average winner: +3R. Average loser: -1R.
Expectancy = (0.40 x 3) - (0.60 x 1) = +0.60R per trade. Better.

Trader B wins less often but makes 50% more money per trade. Why? Because his winners are 3x his losers. That asymmetry is how professional trading works.

> Win rate is vanity. Expectancy is profit.

---

## 1. The Expectancy Formula

```
Expectancy = (Win% x Avg Win in R) - (Loss% x Avg Loss in R)
```

Positive expectancy = you make money over time.
Negative expectancy = you lose money no matter how often you trade.

### The minimum viable system

| Win Rate | Avg Winner Needed | Expectancy |
|---|---|---|
| 30% | 3.0R | +0.20R |
| 40% | 2.5R | +0.40R |
| 50% | 2.0R | +0.50R |
| 60% | 1.5R | +0.50R |
| 70% | 1.0R | +0.40R |

**Notice:** High win rates don't need large winners. Low win rates demand them. Pick your style and commit.

---

## 2. What R Means

R = the amount you risk on a trade (Entry - Stop x Shares).

- If you risk 7,500 and make 15,000, that's a +2R win.
- If you risk 7,500 and lose 7,500, that's a -1R loss.
- If you risk 7,500 and lose 12,000, that's a -1.6R loss — and a discipline failure.

### The critical rule
Every loss should be as close to -1R as possible. Losses larger than -1.5R destroy expectancy faster than winners build it.

---

## 3. Why 1:1 Trades Kill You

At 1:1 risk-reward, you need > 55% win rate just to break even after commissions and slippage. Most traders achieve 45-55% win rates. That means at 1:1, most traders slowly bleed.

At 2:1, you only need 35% win rate to break even.
At 3:1, you only need 26% win rate.

> **The higher your reward-to-risk, the less accurate you need to be.** This is why professionals obsess over setup quality (which delivers high R:R trades) rather than prediction accuracy.

---

## 4. How to Calculate R:R Before Every Trade

Before entering, answer:
1. Where is entry? (E)
2. Where is stop? (S)
3. Where is target? (T)

```
Risk per share = E - S
Reward per share = T - E
R:R = Reward / Risk
```

### Decision rules
- R:R >= 3:1 -> excellent, full size
- R:R 2:1-3:1 -> good, standard size
- R:R 1.5:1-2:1 -> acceptable only with very high win-rate pattern
- R:R < 1.5:1 -> skip. Math doesn't support it.

---

## 5. The Expectancy Journal

Every month, calculate your actual expectancy:

```
Total R-profit from winners / Number of winners = Avg Win (R)
Total R-loss from losers / Number of losers = Avg Loss (R)
Winners / Total trades = Win Rate

Expectancy = (Win% x Avg Win) - (Loss% x Avg Loss)
```

Track this monthly. A declining expectancy means your setup selection or trade management is degrading — and you need to fix it before it kills the account.

---

## 6. Pattern-Specific R:R Expectations

| Pattern | Typical R:R | Notes |
|---|---|---|
| Bull Flag | 2:1 - 4:1 | Tight stop, good runner |
| VCP | 3:1 - 5:1 | Very tight final contraction = tiny risk |
| Cup with Handle | 2:1 - 4:1 | Measured move from cup depth |
| Flat Base | 2:1 - 3:1 | Continuation bias improves R:R |
| Double Bottom | 2:1 - 3:1 | Midpoint projection |
| Inverse H&S | 2:1 - 3:1 | Head-to-neckline projection |
| High Tight Flag | 3:1 - 10:1 | Explosive if regime supports |

---

## 7. Daily, Weekly, Monthly Habits

### Daily
- [ ] Before any entry: calculate R:R. Skip if < 2:1.
- [ ] After any exit: log the trade in R-multiples.

### Weekly
- [ ] Running expectancy this week (quick tally)
- [ ] Any trades entered below 2:1 R:R? Why?

### Monthly
- [ ] Full expectancy calculation
- [ ] Average winner R vs average loser R
- [ ] Win rate
- [ ] Is expectancy trending up, flat, or down?
- [ ] Re-read this playbook.

---

## 8. The One-Page Cheat Sheet

```
Expectancy = (Win% x Avg Win R) - (Loss% x Avg Loss R)
Minimum R:R for entry: 2:1
Keep every loss at -1R or less
Win rate doesn't matter if R:R is strong
Track expectancy monthly — it's your real edge
```

---

## 9. The Final Rule

> **You don't need to predict the market. You need to structure trades where being right pays more than being wrong costs.** That's expectancy. That's the game.

---

*-- End of Risk-Reward & Expectancy --*
"""

# ─────────────────────────────────────────────────────────────────────
# 4. TRADING PSYCHOLOGY PLAYBOOK
# ─────────────────────────────────────────────────────────────────────
files["TRADING_PSYCHOLOGY_PLAYBOOK.md"] = r"""# Trading Psychology Playbook — Master Your Mind, Master Your P&L

> **Your biggest enemy is not the market. It's the voice in your head that says "just this once."** This playbook is your defense against every emotional impulse that destroys trading accounts.

## A Story Before the Rules

Two traders have the same system, the same setups, the same sizing rules.

Trader A follows the system 95% of the time. The other 5%, he "goes with his gut." Those gut trades cost him his entire edge — in fact, they give him a negative year.

Trader B follows the system 100% of the time. She has a +32% year. Not because her system was better. Because she didn't fight it.

> **Psychology doesn't add to your edge. Psychology protects the edge you already have.**

---

## 1. The Seven Emotions That Kill Trades

### 1. Fear of Missing Out (FOMO)
You see a stock running 8% and chase it without a setup. You buy extended. You hold because you "can't miss this." You get trapped.
**Fix:** If you missed the entry, you missed the trade. There will be another one tomorrow.

### 2. Fear of Giving Back Profits
You have a 15% winner. You sell everything because "I don't want to give this back." But the stock runs 50% more.
**Fix:** Use trailing stops. Let the system decide when to sell, not your anxiety.

### 3. Revenge Trading
You just got stopped out. You're angry. You immediately enter another trade to "make it back." It's a worse setup. You lose again.
**Fix:** After any stop, wait at least one full session before the next trade. Journal the loss first.

### 4. Overtrading
You trade 15 times this week because "opportunities are everywhere." Most of them are B and C setups. Your commissions pile up. Your focus dilutes.
**Fix:** Maximum 3-5 new entries per week. If you can't pick the best 3, you shouldn't be trading.

### 5. Hesitation After Losses
You see the perfect setup but can't click buy because the last two trades lost. You watch it run 20% without you.
**Fix:** Reduced size. Take the trade at 50% size. Get back in the game without the full risk.

### 6. Boredom Trading
Nothing is setting up. You take a mediocre trade "just to do something." You lose.
**Fix:** No trade is always a valid position. Cash is a position. Boredom is not an entry signal.

### 7. Overconfidence After Wins
You've won 5 in a row. You double your size. You skip the checklist. You get lazy. The market humbles you.
**Fix:** Keep sizing mechanical. Winning streaks don't change the formula.

---

## 2. The Pre-Trade Mental Checklist

Before every trade, answer honestly:

- [ ] Am I following my trade plan, or acting on impulse?
- [ ] Is this trade driven by FOMO, revenge, or boredom?
- [ ] Did I calculate R:R and position size?
- [ ] Can I describe the exact invalidation level?
- [ ] If this trade loses, will I be okay?
- [ ] Am I in the right emotional state to make this decision?

If any answer is "no" or uncertain: **don't take the trade.** Come back in 30 minutes.

---

## 3. The Mark Douglas Framework

From "Trading in the Zone" — the four trading truths:

1. **Anything can happen.** No trade is guaranteed.
2. **You don't need to know what happens next to make money.** Expectancy works over many trades.
3. **There is a random distribution between wins and losses for any given set of variables.** You'll have losing streaks. They're normal.
4. **Every edge is nothing more than a higher probability.** Not a certainty. Never a certainty.

Read these four truths every morning before market open. They eliminate 80% of emotional interference.

---

## 4. The Identity Shift

Stop saying:
- "I need to be right" -> Say: "I need to follow the system"
- "This trade will make me money" -> Say: "This trade has positive expectancy"
- "I lost money today" -> Say: "I paid the cost of doing business"
- "The market screwed me" -> Say: "My read was wrong and I honored the stop"

You are not your last trade. You are your process across 200 trades.

---

## 5. The Emotional Journal

After every trading day, write three things:

1. **The strongest emotion I felt today** (fear, greed, anger, boredom, overconfidence)
2. **Did that emotion affect any decision?** (Yes/No + what happened)
3. **What's my emotional readiness for tomorrow?** (1-5 scale)

If you score below 3 on readiness: trade at 50% size or not at all.

---

## 6. Daily, Weekly, Monthly Habits

### Daily (2 minutes — before open)
- Read the four Mark Douglas truths
- Do the pre-trade mental checklist
- Rate your emotional state (1-5)

### Weekly (10 minutes — Sunday)
- Review emotional journal entries
- Identify the dominant emotion of the week
- Did you break any rules? What triggered it?
- Recommit to one specific discipline for next week

### Monthly (20 minutes)
- Count rule breaks. Is the number declining month-over-month?
- Identify your "worst emotional trade" of the month
- Identify your "best disciplined trade" of the month
- Re-read this playbook in full

---

## 7. The One-Page Cheat Sheet

```
Before trading  -> Read the 4 truths. Rate your state 1-5.
Before any trade -> Pre-trade mental checklist. All yeses = go.
After a loss    -> Journal. Wait one session. Reduce size.
After a win     -> Don't change anything. Keep sizing the same.
FOMO            -> "There will be another trade tomorrow."
Revenge         -> "I already paid the cost. Don't pay twice."
Boredom         -> "Cash is a position. Patience is a skill."
Overconfidence  -> "The formula doesn't change when I'm hot."
```

---

## 8. The Final Rule

> **Trade your plan, not your feelings. If you can do that 95% of the time, you will make money. The other 5% is what separates good traders from great ones.**

---

*-- End of Trading Psychology Playbook --*
"""

# ─────────────────────────────────────────────────────────────────────
# 5. LOSING STREAK SURVIVAL GUIDE
# ─────────────────────────────────────────────────────────────────────
files["LOSING_STREAK_SURVIVAL_GUIDE.md"] = r"""# Losing Streak Survival Guide — How to Trade Through the Worst of It

> **Every trader who has ever made money has had losing streaks. The ones who survived them are the ones who didn't panic, didn't revenge trade, and didn't quit.** This is your protocol.

## A Story Before the Rules

You've lost 5 trades in a row. Your account is down 5%. You question everything — your system, your ability, your decision to trade at all. You feel like every trade you take will lose. You feel physically sick looking at your positions.

This is normal. This happens to every trader. The difference between the ones who survive and the ones who blow up is what they do in the next 48 hours.

---

## 1. The Losing Streak Reality Check

At a 50% win rate (which is above average for many swing systems), the probability of hitting streaks:

| Streak Length | Probability over 100 trades |
|---|---|
| 3 losses in a row | ~97% (virtually certain) |
| 5 losses in a row | ~81% (will happen) |
| 7 losses in a row | ~55% (more likely than not) |
| 10 losses in a row | ~18% (not rare) |

**You are not broken. You are experiencing statistics.**

---

## 2. The Streak Response Protocol

### After 3 consecutive losses
- Reduce position size to 50%
- Review the last 3 trades: were setups A-grade? Were stops right?
- Continue trading at reduced size

### After 5 consecutive losses
- Reduce position size to 25%
- Mandatory journal review of all 5 trades
- Take 1 day off from trading (no screens, no charts)
- Return with 25% size for the next 3 trades

### After 7 consecutive losses
- Stop trading completely for 3-5 trading days
- Full system review: is the market regime wrong for your setups?
- Paper trade for 5 trades before returning with real money
- Return at 25% size, rebuild to 50%, then 100% over 2 weeks

### After 10 consecutive losses
- Stop trading for 2 full weeks
- Consult your system rules: is something fundamentally broken?
- If system is intact, this is a regime mismatch — wait for better conditions
- Resume with 10% of normal size and rebuild slowly

---

## 3. What NOT to Do During a Losing Streak

1. **Don't increase size to "make it back faster"** — this is how small drawdowns become big ones
2. **Don't switch systems** — every system has losing streaks; switching during one just restarts the count
3. **Don't revenge trade** — the next trade is not related to the last one
4. **Don't skip good setups out of fear** — reduced size, not zero trades
5. **Don't seek advice from everyone** — confusion makes streaks worse
6. **Don't blame the market** — the market doesn't know you exist

---

## 4. The Recovery Roadmap

```
Phase 1 (First 2 winners after streak):
  - 25-50% size
  - Only A+ setups
  - Journal every trade in detail

Phase 2 (Next 3-5 trades):
  - 50-75% size
  - A or A+ setups only
  - Weekly review

Phase 3 (Normal operations):
  - Full size (100%)
  - Standard setup criteria
  - Regular routines

Never skip phases. Never rush back to full size.
```

---

## 5. The Emotional First Aid Kit

During a losing streak, do these specific things:

1. **Exercise before market open** — reduce cortisol, improve decision-making
2. **Re-read your best trade journal entries** — remind yourself you can do this
3. **Calculate your all-time expectancy** — a 5-trade streak doesn't erase 200 trades of positive expectancy
4. **Talk to one person** (not about what to trade, but about how you feel)
5. **Set a maximum daily screen time** — overmonitoring during streaks makes everything worse

---

## 6. The Weekly Streak Dashboard

Track this every week:

| Metric | This Week | Last Week | Trend |
|---|---|---|---|
| Win/Loss streak (current) | | | |
| Position size level (25/50/75/100%) | | | |
| Number of A+ setups taken | | | |
| Number of rule breaks | | | |
| Emotional state (1-5) | | | |

---

## 7. Daily, Weekly, Monthly Habits

### Daily (during a streak)
- [ ] Confirm: am I at the correct reduced size?
- [ ] Am I only taking A+ setups?
- [ ] Have I journaled today's trades?
- [ ] Physical exercise done?

### Weekly
- [ ] Update the streak dashboard
- [ ] Review: are the losses setup-quality problems or market-regime problems?
- [ ] Plan next week's maximum number of trades (lower than normal)

### Monthly
- [ ] Full expectancy recalculation
- [ ] Streak frequency: how many 3+ streaks this month?
- [ ] Recovery speed: how quickly did you return to normal size?

---

## 8. The Final Rule

> **Losing streaks are not a sign that you're a bad trader. They're a sign that you're a trader. How you respond to them determines whether you become a successful one.**

Reduce size. Stay in the game. Trust the system. Rebuild slowly. This is the only path.

---

*-- End of Losing Streak Survival Guide --*
"""

# ─────────────────────────────────────────────────────────────────────
# 6. HOLD VS SELL FRAMEWORK
# ─────────────────────────────────────────────────────────────────────
files["HOLD_VS_SELL_FRAMEWORK.md"] = r"""# Hold vs Sell Framework — The Decision That Makes or Breaks Your Year

> **Most traders know when to buy. Almost none know when to sell.** This framework turns the hardest question in trading into a decision tree you can follow mechanically.

## A Story Before the Rules

You're sitting on a 22% unrealized gain. The stock pulled back 4% today. Your mind races: "Should I sell and protect this?" "What if it keeps dropping?" "What if I sell and it doubles?"

You sell. The stock recovers the next day and runs another 30%.

Or you hold. The stock drops 15% more and your 22% gain becomes a 3% gain.

Both outcomes feel terrible. Because you had no framework — you were guessing.

---

## 1. The Hold/Sell Decision Tree

```
Is the trailing stop hit?
  YES -> SELL. No debate.
  NO  -> Continue...

Is this a climax move? (Largest bar, exhaustion gap, parabolic thrust)
  YES -> SELL 50-100%. Protect gains.
  NO  -> Continue...

Is price above the key trailing MA? (10/21 EMA for swing, 50 for position)
  YES -> HOLD. Trail the stop, do nothing else.
  NO  -> Is the close below the MA, or just intraday?
         Below on close -> SELL remaining.
         Intraday wick  -> HOLD one more day, tighten stop to today's low.

Is the pullback on heavy volume?
  YES -> Distribution risk. SELL at least half.
  NO  -> Normal healthy pullback. HOLD.

Has the stock gone sideways for 2+ weeks after a big move?
  YES -> Tighten stop to range low. Either it breaks out or you're out near highs.
  NO  -> HOLD and trail.
```

---

## 2. The Five Sell Signals (Memorize These)

1. **Trailing stop hit** — mechanical, no override
2. **Climax top signals** — widest bar, exhaustion gap, 3+ wide-range days, extreme volume with no progress
3. **Close below key MA** — 10 EMA for aggressive, 21 EMA for standard, 50 EMA for position
4. **Distribution days inside the move** — heavy volume, price closes in lower half
5. **Market regime deterioration** — if the index breaks below 50 EMA, tighten all stops

---

## 3. The Five Hold Signals (Memorize These Too)

1. **Pullback on low volume** — weak hands leaving, strong hands sitting. Healthy.
2. **Price holds above trailing MA** — trend is intact
3. **Relative strength improving** — stock outperforming index during pullback
4. **No distribution bars** — red days are narrow and low-volume
5. **Base forming at highs** — a new tight range means a new potential continuation

---

## 4. The Scaling Plan for Open Positions

After T1 is hit:
- 1/3 sold, stop raised to break-even
- Now holding 2/3 at zero risk (against original entry)

After T2 or further:
- Another 1/3 sold at measured-move target or +3R
- Final 1/3 trailed under 21 EMA or under each higher low

This means:
- You always book some profit from winners
- You always participate in extended moves
- You never give back all of a gain

---

## 5. The Emotional Sell Traps

| Emotion | What It Makes You Do | What You Should Do Instead |
|---|---|---|
| Fear | Sell everything during a normal pullback | Check trailing stop — if not hit, hold |
| Greed | Hold through climax signals | Sell at least half when distribution appears |
| Regret | Chase a sold stock at higher prices | It's gone. Next setup. |
| Hope | Hold a broken trade waiting for recovery | Honor the trailing stop |
| Impatience | Sell a base-building stock "going nowhere" | Set time stop at 2-3 weeks; let it play out |

---

## 6. Daily, Weekly, Monthly Habits

### Daily
- [ ] For every open position: check trailing stop status
- [ ] Any climax signals today? Act on them.
- [ ] Any distribution days? Tighten stops.

### Weekly
- [ ] Review all exits this week: were they planned or emotional?
- [ ] Any trades where you held too long? Root cause.
- [ ] Any trades where you sold too early? Was the trailing stop the right one?

### Monthly
- [ ] Average holding period for winners
- [ ] Average % given back from peak before exit
- [ ] How many trades were exited by trailing stop vs manual decision?
- [ ] Re-read this playbook.

---

## 7. The Final Rule

> **The exit is not a prediction. It's a response to what price does at a pre-defined level.** If you can replace "should I sell?" with "has my trailing stop been hit?" — you've solved 80% of the sell problem.

---

*-- End of Hold vs Sell Framework --*
"""

# ─────────────────────────────────────────────────────────────────────
# 7. MARKET REGIME PLAYBOOK
# ─────────────────────────────────────────────────────────────────────
files["MARKET_REGIME_PLAYBOOK.md"] = r"""# Market Regime Playbook — Trade the Market You're In, Not the One You Want

> **The same setup behaves completely differently in a trending market vs a choppy one.** This playbook teaches you to identify the regime, adjust your trading, and stop fighting the environment.

## A Story Before the Rules

You've been crushing it for months. Bull flags, VCP breakouts, cup-and-handles — everything works. Then the market drops 5%. Your setups start failing. Breakouts reverse. Stops hit. You keep trading the same way, thinking "it's just a dip."

Two months later your account is down 18%. Not because your setups were wrong — because the regime changed and you didn't adapt.

---

## 1. The Four Market Regimes

### Regime 1: Strong Uptrend
- Index above rising 50 and 200 EMA
- Breadth is healthy (60%+ stocks above 50 EMA)
- New highs outnumber new lows
- **Action:** Full aggression. Full size. All patterns work. Breakouts have follow-through.

### Regime 2: Neutral / Range-Bound
- Index near flat 50 EMA, above 200 EMA
- Breadth is mixed (40-60% above 50 EMA)
- No clear direction
- **Action:** Half size. Only A+ setups. Shorter holding periods. Expect more failed breakouts.

### Regime 3: Correction / Weak
- Index below 50 EMA, may be testing 200 EMA
- Breadth deteriorating (< 40% above 50 EMA)
- New lows expanding
- **Action:** Quarter size or cash. Only reversal or mean-reversion setups. Tighten all stops. No breakouts.

### Regime 4: Bear Market
- Index below declining 200 EMA
- Breadth broken (< 25% above 50 EMA)
- New lows dominating
- **Action:** Cash. No longs. Study. Preserve capital. Wait for regime change.

---

## 2. The Regime Identification Checklist (Weekly — 5 Minutes)

- [ ] Is Nifty/S&P above or below the 50 EMA?
- [ ] Is Nifty/S&P above or below the 200 EMA?
- [ ] Is the 50 EMA rising, flat, or falling?
- [ ] What percentage of stocks are above their own 50 EMA?
- [ ] Are new highs expanding or contracting?
- [ ] Are new lows expanding or contracting?

Score:
- 5-6 bullish answers = Regime 1 (Strong)
- 3-4 = Regime 2 (Neutral)
- 1-2 = Regime 3 (Correction)
- 0 = Regime 4 (Bear)

---

## 3. How Each Pattern Performs by Regime

| Pattern | Regime 1 | Regime 2 | Regime 3 | Regime 4 |
|---|---|---|---|---|
| Bull Flag | Excellent | Fair | Poor | Don't trade |
| VCP | Excellent | Good | Poor | Don't trade |
| Cup & Handle | Good | Fair | Poor | Don't trade |
| Flat Base | Excellent | Good | Fair | Don't trade |
| Inverse H&S | Fair | Good | Excellent | Fair |
| Undercut Reclaim | Fair | Good | Good | Fair |

---

## 4. The Regime Transition Playbook

### Strong -> Neutral (first warning)
- Reduce new positions to half size
- Tighten trailing stops on existing positions
- Raise cash to 30-50%

### Neutral -> Correction (second warning)
- No new breakout trades
- Close positions without momentum
- Raise cash to 60-80%
- Only trade if you see A+ reversal setups

### Correction -> Bear (final stage)
- 100% cash (or nearly)
- Study, journal, plan
- Wait for breadth to turn before re-entering

### Bear -> Correction -> Uptrend (recovery)
- First signals: index reclaims 50 EMA, breadth improves
- Start with 25% size on the earliest leaders
- Build to 50% as follow-through confirms
- Return to full size only when index confirms above 50 AND 200 EMA

---

## 5. Daily, Weekly, Monthly Habits

### Daily
- [ ] Quick breadth check: is the regime still what I think it is?
- [ ] Am I sizing correctly for the current regime?

### Weekly
- [ ] Run the regime identification checklist
- [ ] Adjust position sizing multiplier if regime changed
- [ ] Are my setups appropriate for this regime?

### Monthly
- [ ] How many trades did I take in each regime?
- [ ] Win rate by regime: am I profitable in all regimes or only trending ones?
- [ ] Did I reduce size when the regime weakened? Be honest.
- [ ] Re-read this playbook.

---

## 6. The Final Rule

> **You cannot control the regime. You can only control whether you're trading the right way for it.** Full aggression in a bull. Patience in a range. Caution in a correction. Cash in a bear. That's the entire game.

---

*-- End of Market Regime Playbook --*
"""

# ─────────────────────────────────────────────────────────────────────
# 8. DRAWDOWN MANAGEMENT
# ─────────────────────────────────────────────────────────────────────
files["DRAWDOWN_MANAGEMENT.md"] = r"""# Drawdown Management — Protecting Your Account When Everything Goes Wrong

> **Every trader will face drawdowns. The professional's job is to make sure the drawdown doesn't end the career.** This is your account-level defense system.

## A Story Before the Rules

You started the year at 10 lakhs. By March, you're at 11.5 lakhs — up 15%. You feel invincible.

By June, a market correction and two position blow-ups later, you're at 8.8 lakhs. Down 12% from peak, down 12% from starting equity.

The math says you need +25% just to get back to your March peak. If you keep trading the same way, you'll need +50% to feel whole again. Most traders never recover from this spiral — not because the market beats them, but because they refuse to slow down.

---

## 1. The Drawdown Severity Tiers

| Drawdown from Peak | Severity | Required Action |
|---|---|---|
| -3% to -5% | Normal fluctuation | Continue at full size. Review setups. |
| -5% to -8% | Elevated | Reduce to 75% position size. Tighten stops. |
| -8% to -12% | Serious | Reduce to 50% size. Only A+ setups. Weekly review. |
| -12% to -18% | Critical | Reduce to 25% size. Take 2-3 day break. Full system audit. |
| > -18% | Emergency | Stop trading. 1-2 week break. Complete trade review. Paper trade before returning. |

---

## 2. The Daily Drawdown Rules

- Maximum daily loss: -2% of account
- If you lose -2% in a single day, stop trading for the rest of the day
- Do not try to "make it back" in the same session
- Next day: trade at 50% size

---

## 3. The Weekly Drawdown Rules

- Maximum weekly loss: -3% of account
- If you hit -3% by Wednesday, no new trades for the rest of the week
- Thursday/Friday: manage existing positions only
- Weekend: full review of every loss

---

## 4. The Monthly Drawdown Rules

- Maximum monthly loss: -6% of account
- If you hit -6% by mid-month, stop all new trades
- Manage existing positions only
- Resume at 25% size the following month

---

## 5. The Recovery Protocol

```
Phase 1 — Stabilize (first 1-2 weeks after hitting circuit breaker)
  - 25% of normal position size
  - Only A+ setups in supportive market regime
  - Maximum 2 new trades per week
  - Journal every trade in detail

Phase 2 — Rebuild (next 2-4 weeks)
  - 50% of normal position size
  - A and A+ setups
  - Maximum 3-4 new trades per week
  - Weekly expectancy check

Phase 3 — Normalize (4-8 weeks after stabilization)
  - 75-100% of normal position size
  - Standard setup criteria
  - Full trading routine
  - Monthly comparison to pre-drawdown performance
```

---

## 6. The Drawdown Journal

During a drawdown, track this daily:

| Date | Account Value | Drawdown % | Trades Taken | Size Level | Emotions (1-5) |
|---|---|---|---|---|---|

This data tells you:
- Whether you're respecting the reduction rules
- Whether you're overtrading during the drawdown
- Whether your emotional state is stable enough to trade

---

## 7. The Five Most Common Drawdown Mistakes

1. **Trading at full size during a drawdown** — the fastest way to make it worse
2. **Revenge trading to recover quickly** — the second fastest way
3. **Switching systems during a drawdown** — every system has losing periods; switching restarts the learning curve
4. **Blaming the market instead of auditing your trades** — if your stops and sizing were correct, a drawdown is acceptable
5. **Not tracking the numbers** — if you don't know your drawdown %, you can't manage it

---

## 8. Daily, Weekly, Monthly Habits

### Daily
- [ ] Mark current account value and drawdown from peak
- [ ] If daily loss > 2%, stop trading for the day
- [ ] If in elevated drawdown, confirm reduced sizing

### Weekly
- [ ] Track weekly P&L vs drawdown tier
- [ ] If weekly loss > 3%, no new trades remainder of week
- [ ] Update drawdown journal

### Monthly
- [ ] Full account review: equity curve, max drawdown, recovery rate
- [ ] Assessment: did I follow the drawdown protocol this month?
- [ ] Plan: what size should I be trading next month based on current drawdown level?
- [ ] Re-read this playbook.

---

## 9. The Final Rule

> **A drawdown is not the time to fight harder. It's the time to trade smaller, trade cleaner, and wait for the market to reward discipline.** The money will come back if the trader survives.

---

*-- End of Drawdown Management --*
"""

# ─────────────────────────────────────────────────────────────────────
# 9. SWING TRADING JOURNAL SYSTEM
# ─────────────────────────────────────────────────────────────────────
files["SWING_TRADING_JOURNAL_SYSTEM.md"] = r"""# Swing Trading Journal System — The Habit That Separates Pros From Everybody Else

> **You can't improve what you don't measure.** A journal isn't paperwork — it's the feedback loop that turns a losing year into a profitable one. This guide gives you the exact system.

## A Story Before the Rules

Two traders have identical systems. Same setups, same sizing, same stops.

Trader A journals every trade — entry reason, setup grade, emotional state, outcome in R, what he'd do differently. After 6 months, he identifies a pattern: his "FOMO entries" (B-grade setups he chased) account for 80% of his losses. He stops taking them. His next 6 months are profitable.

Trader B doesn't journal. He "remembers" his trades. He makes the same FOMO mistakes for another year. He doesn't get better because he has no data.

---

## 1. What to Record for Every Trade

### The Trade Card (fill at entry)
- Date and time of entry
- Symbol and market
- Setup type (bull flag, VCP, cup & handle, etc.)
- Setup grade (A+, A, B)
- Entry price
- Stop price
- Risk per share
- Position size (shares and %)
- R:R to T1 and T2
- Why I'm taking this trade (one sentence)
- Emotional state (1-5)

### The Exit Card (fill at exit)
- Date and time of exit
- Exit price
- P&L in rupees and in R
- Holding period (days)
- Exit reason (stop hit, trailing stop, target, time stop, emotional)
- What went right
- What went wrong
- What I'd do differently
- Was this trade within system rules? (Yes/No)

---

## 2. The Daily Review (5 minutes, after market close)

- [ ] All open positions have updated stops
- [ ] Any trades entered today are logged
- [ ] Any trades exited today are logged with exit cards
- [ ] Emotional state rating for the day (1-5)
- [ ] One sentence: "Today I did well because..." or "Today I struggled because..."

---

## 3. The Weekly Review (15 minutes, Sunday)

- [ ] Total trades this week: entries + exits
- [ ] Win/loss count and win rate
- [ ] Average R on winners vs losers
- [ ] Were any trades B-grade or worse? How did they perform?
- [ ] Most common emotional trigger this week
- [ ] One mistake to eliminate next week
- [ ] One thing I did well to repeat next week

---

## 4. The Monthly Review (30 minutes, last weekend)

- [ ] Total expectancy this month
- [ ] Largest winner and largest loser (in R)
- [ ] Was the largest loser > 1.5R? Why?
- [ ] Setup type performance: which patterns made money, which didn't?
- [ ] Market regime this month and how it affected results
- [ ] Streak analysis: longest winning and losing streaks
- [ ] Emotional pattern: most common emotion across all trades
- [ ] Did I follow all sizing rules? All stop rules? All entry rules?
- [ ] Three specific improvements for next month

---

## 5. The Quarterly Review (1 hour)

- [ ] Equity curve: is it trending up, flat, or down?
- [ ] Best month and worst month: what was different?
- [ ] Which setup type is my highest-expectancy? Focus there.
- [ ] Which setup type is my lowest-expectancy? Reduce or eliminate.
- [ ] Am I trading the right amount for the current regime?
- [ ] What would my results look like if I only traded A+ setups?
- [ ] Goal for next quarter: one specific, measurable improvement

---

## 6. Mistake Tags (Use These in Your Journal)

Tag every losing trade with one of these:

- `FOMO` — entered because of fear of missing out
- `REVENGE` — entered after a loss to "make it back"
- `BOREDOM` — entered because nothing else was happening
- `OVERSIZE` — position was too large for the setup
- `BAD_STOP` — stop was in the wrong place
- `CHASED` — entered too far from the pivot
- `B_SETUP` — took a B-grade trade instead of waiting for A+
- `NO_PLAN` — entered without a complete trade plan
- `HELD_TOO_LONG` — didn't honor time stop or trailing stop
- `REGIME_MISMATCH` — traded a trending setup in a choppy market

Track the frequency of each tag monthly. Your most common tag is your most expensive habit.

---

## 7. The One-Page Cheat Sheet

```
At entry  -> Fill trade card (setup, grade, size, stop, R:R, emotion)
At exit   -> Fill exit card (P&L in R, reason, lessons)
Daily     -> 5-min review: logged? stops updated? emotional state?
Weekly    -> 15-min review: win rate, avg R, mistakes, one fix
Monthly   -> 30-min review: expectancy, patterns, improvements
Quarterly -> 1-hr review: equity curve, best/worst setups, focus areas
```

---

## 8. The Final Rule

> **The journal is not optional. It's the difference between a trader who learns and a trader who repeats.** If you can't spend 10 minutes a day writing down what you did and why, you're not serious about improvement.

---

*-- End of Swing Trading Journal System --*
"""

# ─────────────────────────────────────────────────────────────────────
# 10. WHEN NOT TO TRADE
# ─────────────────────────────────────────────────────────────────────
files["WHEN_NOT_TO_TRADE.md"] = r"""# When Not to Trade — The Skill Nobody Teaches

> **Knowing when NOT to trade is worth more than any setup.** This is your guide to standing aside with discipline — and keeping the capital for when it matters.

## A Story Before the Rules

You check your charts. Nothing is setting up cleanly. No tight bases, no fresh breakouts, no volume signatures you trust. But you feel like you "should be doing something."

So you take a mediocre trade — a loose flag in a choppy stock with no volume confirmation. You put on normal size. It gaps down the next day. You're stopped out.

You just paid the market a tuition fee for the lesson of impatience.

---

## 1. The Complete "No Trade" Checklist

Skip the trade when:

- [ ] Market is below the 50 EMA and breadth is deteriorating
- [ ] You can't find 3 or more names setting up at once (sign of weak rotation)
- [ ] Setup is more than 5% extended from its pivot
- [ ] Volume on the breakout day is below average
- [ ] Stop placement requires more than 7-8% risk from entry
- [ ] R:R is below 2:1 to the first target
- [ ] You're in a drawdown above -8% and using elevated risk
- [ ] You've already taken 3+ trades this week with mixed results
- [ ] You're emotionally reactive (after a big win or a big loss)
- [ ] It's a Friday afternoon (gap risk over weekend)
- [ ] Earnings are within 2 weeks for the stock
- [ ] You're taking the trade because you're bored, not because it's great
- [ ] The setup looks "okay" but not "clean" — and you can feel the difference

---

## 2. The Eight Situations Where Cash Is Better

### 1. Choppy market with no direction
The same setups that win in trending markets lose in choppy ones. If the index is range-bound, your breakouts will fail.

### 2. Post-correction, before a confirmed recovery
The first bounce after a correction often fails. Wait for the follow-through day and breadth confirmation.

### 3. Heavy event calendar (FOMC, RBI, budget, elections)
Uncertainty compresses trades and expands risk. Wait for the event, trade the reaction.

### 4. During a personal losing streak
Your read is off. Reduce or stop. Don't force it.

### 5. When all your watchlist names are extended
If everything is 10% above its pivot, there's nothing to buy. Wait for the next pullback.

### 6. Low-volume periods (holidays, year-end)
Thin markets produce false signals. Breakouts on low volume are traps.

### 7. When you're exhausted or distracted
Trading while tired, sick, or emotionally overwhelmed leads to impulsive decisions. Take the day off.

### 8. When you just don't see it
Sometimes the chart just isn't speaking to you. That's okay. Not every day requires a trade.

---

## 3. What to Do Instead of Trading

When you sit out, use the time productively:

- Journal review: re-read your last 20 trades
- Pattern study: study past winners from your catalog
- Playbook review: re-read one section of your trading library
- Watchlist building: scan for names forming bases for future setups
- Physical exercise: reduce cortisol, improve readiness for when setups do appear

---

## 4. Daily, Weekly, Monthly Habits

### Daily
- [ ] Is today a "trade day" or a "watch day"?
- [ ] If no A+ setups exist, accept cash as the right position

### Weekly
- [ ] How many days this week did I correctly choose "no trade"?
- [ ] How much capital did I protect by waiting?

### Monthly
- [ ] What percentage of my trades were "boredom trades"? (Target: 0%)
- [ ] If I eliminated all B-grade trades, what would my P&L look like?
- [ ] Re-read this playbook.

---

## 5. The Final Rule

> **Cash is a position. Patience is a skill. The trader who sits in cash during weak setups will always outperform the trader who trades for the sake of activity.**

You are not paid to trade. You are paid to wait for the right trade.

---

*-- End of When Not to Trade --*
"""

# ─────────────────────────────────────────────────────────────────────
# 11. OVERNIGHT RISK SURVIVAL GUIDE
# ─────────────────────────────────────────────────────────────────────
files["OVERNIGHT_RISK_SURVIVAL_GUIDE.md"] = r"""# Overnight Risk Survival Guide — How to Sleep With Open Positions

> **Swing traders live with overnight exposure. This guide teaches you how to manage the gap risk that can bypass normal stop-loss behavior.**

## A Story Before the Rules

You buy a breakout at 3:15 PM. Clean setup, perfect stop, good sizing. You go to bed feeling great.

At 9:15 AM the next day, the stock opens 8% lower on a surprise earnings miss. Your 3% stop is untouched — the stock gapped straight through it. You're now down 8% on the position, which is 2.6% of your account from a single overnight event.

This is the reality of swing trading: your stop can only protect you when the market is open.

---

## 1. The Seven Rules of Overnight Risk

1. **Never hold a full-size position into earnings.** Cut to 25% or exit completely.
2. **Never hold more than 5% of your account in any single position overnight** (capital deployed).
3. **Check the corporate event calendar before buying.** Earnings, analyst days, FDA decisions, policy announcements.
4. **Size for the gap, not just the stop.** If a stock can realistically gap 5%, your sizing should survive that.
5. **Use hard disaster stops** 2-3x ATR below your mental stop for overnight protection.
6. **Diversify across sectors** so no single event can hit all your positions at once.
7. **Reduce overall exposure before major macro events** (RBI rates, FOMC, budget, elections).

---

## 2. The Pre-Event De-Risk Protocol

When a known event is approaching (earnings, policy decision, etc.):

### 3-5 days before the event
- Review all positions: which ones are exposed?
- Start trimming exposed positions by selling partial
- Raise cash to 30-50% if multiple positions are exposed

### 1 day before the event
- No new entries in exposed names
- Cut all positions to 25% or less of normal size
- Hard stops placed at 2x ATR below current price

### Day of the event
- No new trades during the event
- Let the market react first
- Re-evaluate after the dust settles (usually 2-3 hours)

---

## 3. The Gap Survival Sizing Formula

```
Max overnight position = Account x Max overnight risk / Expected gap size

Example:
  Account = 10,00,000
  Max overnight risk = 1.5% = 15,000
  Expected gap = 5%
  Max position = 15,000 / 0.05 = 3,00,000 deployed (30% of account)
```

This means: if you think the stock could gap 5%, don't deploy more than 30% of your account in it.

---

## 4. The Weekend Holding Rules

Friday close is when overnight risk is longest (2+ days including weekends).

- Tighten all trailing stops on Friday before close
- If a position is marginal (near stop, low conviction), close it
- Don't enter new full-size positions on Friday afternoon
- Global events can develop over the weekend — think about your exposure

---

## 5. What to Do After a Gap Against You

### Small gap (< 3% below stop)
- Assess: is the setup still valid?
- If yes: hold, but tighten stop to new level
- If no: exit immediately at the open

### Medium gap (3-6% below stop)
- Exit at least half at the open
- Review: was this event foreseeable?
- Don't add to the position

### Large gap (> 6% below stop)
- Do not panic sell in the first 15 minutes (often the worst price)
- Assess after the first 30-60 minutes
- Exit all or most of the position during the first recovery attempt
- Journal the event: what could you have done differently?

---

## 6. Daily, Weekly, Monthly Habits

### Daily (afternoon, before close)
- [ ] Any overnight events for positions I hold?
- [ ] Are hard disaster stops in place for all positions?
- [ ] Is any single position > 5% of my account overnight?

### Weekly (Friday before close)
- [ ] Weekend exposure check: what's my total overnight risk?
- [ ] Any earnings next week for stocks I hold?
- [ ] Trim or close marginal positions

### Monthly
- [ ] How many gap events affected my positions this month?
- [ ] Was any gap loss larger than planned? Why?
- [ ] Review overnight sizing: am I consistently within limits?
- [ ] Re-read this playbook.

---

## 7. The Final Rule

> **You cannot control what happens overnight. You can only control how much of your account is exposed to it.** Size for the gap. De-risk before events. Sleep well.

---

*-- End of Overnight Risk Survival Guide --*
"""


# ═════════════════════════════════════════════════════════════════════
# Write all files
# ═════════════════════════════════════════════════════════════════════
for name, content in files.items():
    path = DOCS / name
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"  wrote {name} ({len(content.strip().splitlines())} lines)")

print(f"\nDone: {len(files)} playbook files written to {DOCS}")

