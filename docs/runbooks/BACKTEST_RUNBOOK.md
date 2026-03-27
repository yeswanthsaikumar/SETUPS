# Backtest Runbook — SETUPS Scanner

The SETUPS backtest engine replays three years of historical breakout detection
across all cached NSE India stocks and produces an interactive HTML dashboard
covering performance analysis, sector returns, and macro event impact.

---

## How the Backtest Works

### Data Source

- **Files:** `cache/*.NS_900.csv` — one file per NSE stock
- **Coverage:** ~1,935 India NSE stocks
- **Date range:** April 2023 – March 2026 (~729 daily bars per stock)
- **Fields:** `date, open, high, low, close, volume`

Cache files are populated by the daily scan and persist across runs.
No internet access is required for the backtest itself.

---

### Entry Strategy — Quality Gates

Every signal must pass **all** gates before a trade is simulated:

| Gate | Requirement | Rationale |
|------|-------------|-----------|
| Trend | Close > SMA200 × 0.97 **and** Close > SMA50 × 0.98 | Only trade with the trend |
| 10 EMA slope | 10 EMA rising over last 3 bars (≥ −0.1% tolerance) | Active upward momentum |
| Candle quality | Close in **top 45%** of bar's high–low range | Buyers in control at close |
| Not extended | Close < pivot × 1.05 (within 5% of pivot) | Tight entry = better R:R |
| Volume (Range Exp) | ≥ 1.5× 20-day average | Institutional participation |
| Volume (VCP) | ≥ 1.2× 20-day average | Confirmation of interest |
| Bullish candle | Close > Open | No reversal candle entries |
| Stop feasibility | Stop distance ≤ 7% from entry | Reject unchaseable stops |

**Range Expansion** — a wide-range breakout candle that closes above the 20-bar
pivot high on heavy volume, in the top 45% of its own range.

**VCP (Volatility Contraction Pattern)** — 8-bar price range has contracted to
≤ 78% of the prior 4-bar range (clear tightening), OR an NR7 bar
(narrowest range of last 7 bars), then a breakout close above the 20-bar pivot.

One signal per stock per **calendar month** to avoid re-detecting the same move.

---

### Stop Loss Strategy — Structure-Based, 4 Phases

Stop loss is **never a fixed percentage**. It is placed at the structural
invalidation level and managed dynamically through the trade's lifecycle.

#### Phase 1 — Breakout Candle Low (from entry until T1 is hit)

The stop is the **low of the breakout candle itself**. A close below that level
means the breakout has structurally failed and the trade is exited immediately.

Stop price is adjusted for the stock's volatility tier (Average Daily Range %):

| Tier | ADR% | Stop formula | Typical % from entry |
|------|------|-------------|----------------------|
| LOW vol | < 1.8% | Candle low × 0.999 | ~0.8 – 1.5% |
| MED vol | 1.8 – 3.5% | Candle low × 0.997 | ~1.5 – 3.0% |
| HIGH vol | > 3.5% | max(candle low × 0.993, entry − 2×ATR) | ~3.0 – 6.0% |

Safety rails: stop never tighter than 1.5×ATR, never wider than 6%.

**Base-low violation** (any phase): if the stock closes below the lowest low of
its 15-bar contraction base, the entire pattern has failed → immediate full exit.

#### Phase 2 — Percentage Trail from Swing High (after T1 hit, 35% exited)

Stop trails below the rolling high-water mark at a tier-adjusted percentage:

| Tier | Trail % | Typical stock profile |
|------|---------|----------------------|
| LOW vol | 5% below recent high | Large-cap, steady movers (HDFC, TCS) |
| MED vol | 7% below recent high | Mid-cap breakouts (standard) |
| HIGH vol | 10% below recent high | Small-cap, high-beta stocks |

Stop is **locked at minimum breakeven** — you cannot lose once T1 is hit.

#### Phase 3 — 10 EMA Trailing Stop (after T2 hit, 75% exited)

Once T2 (+2.5R) is hit, the remaining 25% of the position is managed with the
**10 EMA as the dynamic trailing stop**:

- Exit on **close below 10 EMA** — the uptrend structure has broken
- In a strong bull trend with macro support, price respects the 10 EMA as support
- Minimum floor: stop never pulled below entry + 1.0R
- This allows big winners to ride full multi-week trends to T3 and beyond

#### Phase 4 — T3 or Max-Hold (40 bars)

- **T3 hit (+4.0R)** → exit remaining 25% at full target
- **40-bar time limit** → exit at close (safety net for stalled trades)

---

### Partial-Exit Simulation Model

| Event | Portion exited | At price | Trailing stop action |
|-------|---------------|----------|---------------------|
| T1 hit (+1.5R) | 35% | T1 level | Trail to swing_high × (1 − tier%) |
| T2 hit (+2.5R) | 40% | T2 level | Switch to 10 EMA trailing stop |
| T3 hit (+4.0R) | 25% | T3 level | Full close |
| Candle low break (Phase 1) | 100% remaining | Closing price | Structure failed |
| Trail stop hit (intraday) | 100% remaining | Trail level | Stop order fills |
| 10 EMA break (Phase 3 close) | 100% remaining | Closing price | Uptrend ended |
| Base-low break (any phase) | 100% remaining | Closing price | Pattern invalidated |
| Max hold (40 bars) | 100% remaining | Closing price | Time exit |

**R-multiple** = weighted-average exit price vs entry, normalised by initial risk (R = entry − stop).

**Costs:** 10 bps round-trip commission. No slippage model beyond that.

---

## Running the Backtest

### Full run — all 1,935 stocks (~40 sec)

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/generate_backtest_dashboard.py
```

Output: `output/backtest_3yr_dashboard.html`

### With custom account size

```bash
python3 apps/python/cli/generate_backtest_dashboard.py --account-size 2000000
```

### Quick subset run (testing, ~4 sec)

```bash
python3 apps/python/cli/generate_backtest_dashboard.py --max-stocks 200
```

### Custom output path

```bash
python3 apps/python/cli/generate_backtest_dashboard.py \
  --output output/backtest_custom.html
```

### All CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--max-stocks N` | all (~1,935) | Limit to first N stocks (alphabetical) |
| `--account-size N` | 1,000,000 | Account size in ₹ for position sizing |
| `--output PATH` | `output/backtest_3yr_dashboard.html` | HTML output path |

---

## Interpreting the Results

### Performance Tab — Key Metrics

| Metric | Actual (Apr 2023–Mar 2026) | Healthy range |
|--------|---------------------------|---------------|
| Trades | 5,243 | — |
| Win Rate | 38% | 38–55% depending on regime |
| VCP Avg R | **+0.35R** (positive) | > 0.0R |
| Range Exp Avg R | −0.15R (bear drag) | > 0.0R in bull |
| T3 Hit Rate | 4.9% | 4–8% |
| EMA10 Exit | 2.4% | big winners riding trend |
| Max Hold | 1.0% | low — structure stops cut losers early |

### Exit Reason Breakdown (actual results)

| Exit Reason | Count | % | Interpretation |
|-------------|-------|---|----------------|
| CANDLE_LOW_BREAK | 1,744 | 33% | Breakout failed on structure — **correct early exit** |
| TRAIL_STOP | 1,572 | 30% | Winners trailed after T1, stop eventually hit |
| STOP | 1,464 | 28% | Initial stop hit before T1 |
| T3 | 255 | 5% | Full runners at +4R |
| EMA10_BREAK | 126 | 2% | Trend ended, 10 EMA trail triggered |
| MAX_HOLD | 55 | 1% | Time exit on stalled trades |
| BASE_BREAK | 27 | 1% | Complete base structure failure |

**CANDLE_LOW_BREAK is the most important exit** — it replaces the old fixed-% stop
and cuts losses early when the breakout structure fails, often saving 0.3–0.5R vs
holding to the full stop level.

### Why VCP outperforms Range Expansion

VCP (+0.35R avg) wins because:
- Tighter contraction base = lower candle low = tighter initial stop
- Narrower range = when the breakout holds, momentum is stronger
- NR7 breakouts tend to have clear directional follow-through

Range Expansion shows negative avg R in the test period due to the 2024–2026
bear market — many wide-range breakouts reversed quickly during FII selling waves.

### Market Regime Context

The 3-year window (Apr 2023 – Mar 2026) spans two very different phases:

| Phase | Period | Nifty | Breakout environment |
|-------|--------|-------|----------------------|
| Bull market | Apr 2023 – Sep 2024 | 17,500 → 26,000 | High success; many T2/T3 hits |
| Correction | Oct 2024 – Mar 2026 | 26,000 → 22,000 | Low success; CANDLE_LOW exits dominate |

Cross-reference the **Monthly Net R** chart on the Performance tab against the
**Macro Impact** tab to see exactly which events caused the drawdown periods.

### Equity Curve Analysis

- Rising curve = system working
- Drawdown periods align with: LTCG hike (Jul 2024), Yen carry unwind (Aug 2024),
  Trump election (Nov 2024), US tariff shock (Apr 2025)
- Recovery periods align with: RBI rate cuts, Budget rallies, US Fed cuts

### Using the Trade Plans Tab

The **Trade Plans** tab shows today's **live signals** from the latest scan —
not historical backtest signals. Use it for today's actionable trades.

Stop loss shown is calculated using the **same structure-based method** as the backtest:
breakout candle low, adjusted for ADR tier. This means the stop and R:R figures
in the Trade Plans tab are directly comparable to the backtest's historical results.

---

## Stop Loss Quick Reference Card

```
Entry day:   SL = breakout candle low  (LOW: ×0.999  MED: ×0.997  HIGH: ×0.993)
             Never tighter than 1.5×ATR, never wider than 6%

After T1:    Raise SL to breakeven (min)
             Then trail: LOW vol = 5%, MED = 7%, HIGH = 10% below swing high

After T2:    Switch to 10 EMA as trailing stop
             Exit on close < 10 EMA
             Floor: never below entry + 1.0R

Always:      If close < base low → immediate full exit (base break)
             If close < breakout candle low → exit (Phase 1 only)
```

---

## Updating Backtest for New Data

As time passes and fresh 900-bar cache files accumulate:

```bash
# Step 1: refresh cache (from daily scan)
./run_master.sh

# Step 2: re-run backtest (automatically uses all .NS_900.csv files on disk)
python3 apps/python/cli/generate_backtest_dashboard.py
```

No configuration changes needed — the engine auto-discovers all cache files.

---

## Performance Benchmarks by Volatility Tier

| ADR Tier | Trail % | Expected WR (Bull) | Expected WR (Bear) | Avg Stop Distance |
|----------|---------|--------------------|--------------------|-------------------|
| LOW (<1.8%) | 5% | 48–55% | 38–44% | 0.8–1.5% |
| MED (1.8–3.5%) | 7% | 44–52% | 35–42% | 1.5–3.0% |
| HIGH (>3.5%) | 10% | 40–48% | 30–38% | 3.0–6.0% |

---

## Files Created / Modified

```
output/
  backtest_3yr_dashboard.html   ← main output (~2.5 MB)
  trade_plans_live.html         ← trade plans page (~936 KB)
  sector_macro_analysis.html    ← sector page (~82 KB)
  index.html                    ← hub page (static)
```

No cache files are modified. No scan outputs are overwritten.
