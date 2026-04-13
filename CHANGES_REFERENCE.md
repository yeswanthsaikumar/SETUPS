# Trade Card Changes — Quick Reference

## 1. HTML Changes (index.html)

### Change #1: Trade Plan Grid (Lines 757-769)
**BEFORE:**
```javascript
document.getElementById('arPlanGrid').innerHTML = [
  _planItem('Current Price', tp.currentPrice),
  _planItem('Pivot', tp.pivotPrice),
  _planItem('Entry', tp.entryPrice),
  _planItem('Stop Loss', tp.stopLoss),
  _planItem('Target 1', tp.target1),              // ❌ REMOVED
  _planItem('Target 2', tp.target2),              // ❌ REMOVED
  _planItem('Target 3', tp.target3),              // ❌ REMOVED
  _planItem('R:R @ T1', tp.rrT1, 'x'),           // ❌ REMOVED
  _planItem('R:R @ T2', tp.rrT2, 'x'),           // ❌ REMOVED
  _planItem('Risk/Share', tp.riskPerShare),
  _planItem('Suggested Shares', tp.suggestedShares),
  _planItem('Dist from Pivot', tp.distFromPivotPct != null ? tp.distFromPivotPct + '%' : null),
].join('');
```

**AFTER:**
```javascript
document.getElementById('arPlanGrid').innerHTML = [
  _planItem('Current Price', tp.currentPrice),     // ✅ KEPT
  _planItem('Pivot', tp.pivotPrice),               // ✅ KEPT
  _planItem('Entry', tp.entryPrice),               // ✅ KEPT
  _planItem('Stop Loss', tp.stopLoss),             // ✅ KEPT
  _planItem('Risk/Share', tp.riskPerShare),        // ✅ KEPT
  _planItem('Suggested Shares', tp.suggestedShares), // ✅ KEPT
  _planItem('Dist from Pivot', tp.distFromPivotPct != null ? tp.distFromPivotPct + '%' : null),
].join('');
```

---

### Change #2: Regime Display (Lines 779-830)
**BEFORE:**
```javascript
if (a.regimeAnalysis || a.mtfAnalysis) {
  const rBullets = [];
  if (a.regimeAnalysis) {
    rBullets.push(a.regimeAnalysis.emoji + ' ' + a.regimeAnalysis.summary);
    if (a.regimeAnalysis.supportText) rBullets.push('   ↳ ' + a.regimeAnalysis.supportText);
    rBullets.push(`📊 Regime score: ${a.regimeAnalysis.score}`);
  }
  if (a.mtfAnalysis) rBullets.push(a.mtfAnalysis.summary);
  _renderList('arRegimeBullets', rBullets);
  _setSectionDisplay('arRegimeSection', true);
} else {
  _setSectionDisplay('arRegimeSection', false);
}

if (a.rsAnalysis) {
  _renderList('arRsBullets', a.rsAnalysis.bullets);
  _setSectionDisplay('arRsSection', true);
} else {
  _setSectionDisplay('arRsSection', false);
}
```

**AFTER:**
```javascript
if (a.regimeAnalysis || a.mtfAnalysis || a.rsAnalysis || a.volumeAnalysis) {
  const rBullets = [];
  if (a.regimeAnalysis) {
    rBullets.push(a.regimeAnalysis.emoji + ' ' + a.regimeAnalysis.summary);
    if (a.regimeAnalysis.supportText) rBullets.push('   ↳ ' + a.regimeAnalysis.supportText);
    rBullets.push(`📊 Regime score: ${a.regimeAnalysis.score}`);
  }

  // ✨ NEW: Add RS metrics if available
  if (a.rsAnalysis) {
    const rs3m = _formatCompareValue(a.rsAnalysis.rs3m, '%');
    const rs6m = _formatCompareValue(a.rsAnalysis.rs6m, '%');
    rBullets.push(`📈 RS 3M: ${rs3m} | RS 6M: ${rs6m}`);
  }

  // ✨ NEW: Add volume and range expansion if available
  if (a.scanData) {
    const volPct = _formatCompareValue(a.scanData['vol%']);
    const rexp = _formatCompareValue(a.scanData['rexp']);
    if (volPct !== '—' || rexp !== '—') {
      rBullets.push(`📊 VOL%: ${volPct} | REXP: ${rexp}`);
    }
  }

  if (a.mtfAnalysis) rBullets.push(a.mtfAnalysis.summary);
  _renderList('arRegimeBullets', rBullets);
  _setSectionDisplay('arRegimeSection', true);
} else {
  _setSectionDisplay('arRegimeSection', false);
}

// ✨ NEW: Combined RS/Volume display
if (a.rsAnalysis) {
  const volBullets = [];
  if (a.rsAnalysis.bullets && a.rsAnalysis.bullets.length) {
    volBullets.push(...a.rsAnalysis.bullets);
  }
  if (a.volumeAnalysis && a.volumeAnalysis.bullets && a.volumeAnalysis.bullets.length) {
    volBullets.push(...a.volumeAnalysis.bullets);
  }
  if (volBullets.length) {
    _renderList('arRsBullets', volBullets);
    _setSectionDisplay('arRsSection', true);
  } else {
    _setSectionDisplay('arRsSection', false);
  }
} else if (a.volumeAnalysis && a.volumeAnalysis.bullets && a.volumeAnalysis.bullets.length) {
  _renderList('arRsBullets', a.volumeAnalysis.bullets);
  _setSectionDisplay('arRsSection', true);
} else {
  _setSectionDisplay('arRsSection', false);
}
```

---

## 2. Python Changes (stock_analyzer.py)

### Change #1: RS Analysis (Lines 413-445)

**BEFORE:**
```python
def _build_rs_analysis(row: dict) -> dict:
    rs3m  = _to_float(row.get("rs3m"))
    rs6m  = _to_float(row.get("rs6m"))
    rs12m = _to_float(row.get("rs12m"))
    rs_score = _to_float(row.get("rsScore"))
    rs_rank  = _to_float(row.get("rsRankScore"))

    bullets: list[str] = []
    if rs_score >= 80:  # ⚠️ Can fail if rs_score is NaN
        bullets.append(f"🚀 RS Score {rs_score:.1f} — top-tier relative strength vs. universe.")
    # ... rest of logic

    return {
        "rs3m":    round(rs3m, 2),        # ⚠️ Returns 0 for missing data
        "rs6m":    round(rs6m, 2),        # ⚠️ Returns 0 for missing data
        "rs12m":   round(rs12m, 2),
        "rsScore": round(rs_score, 2),
        "rsRank":  round(rs_rank, 2),
        "bullets": bullets,
    }
```

**AFTER:**
```python
def _build_rs_analysis(row: dict) -> dict:
    # ✅ NEW: Safe defaults prevent NaN
    rs3m  = _to_float(row.get("rs3m"), default=0.0)
    rs6m  = _to_float(row.get("rs6m"), default=0.0)
    rs12m = _to_float(row.get("rs12m"), default=0.0)
    rs_score = _to_float(row.get("rsScore"), default=0.0)
    rs_rank  = _to_float(row.get("rsRankScore"), default=0.0)

    bullets: list[str] = []
    if rs_score > 0:  # ✅ Safe check for valid data
        if rs_score >= 80:
            bullets.append(f"🚀 RS Score {rs_score:.1f} — top-tier relative strength vs. universe.")
        # ... rest of logic

    if rs3m > 0:
        bullets.append(f"📅 RS 3-month: {rs3m:.1f}th percentile")
    if rs6m > 0:
        bullets.append(f"📅 RS 6-month: {rs6m:.1f}th percentile")
    if rs12m > 0:
        bullets.append(f"📅 RS 12-month: {rs12m:.1f}th percentile")

    return {
        # ✅ NEW: Returns None for zero (not 0)
        "rs3m":    round(rs3m, 2) if rs3m > 0 else None,
        "rs6m":    round(rs6m, 2) if rs6m > 0 else None,
        "rs12m":   round(rs12m, 2) if rs12m > 0 else None,
        "rsScore": round(rs_score, 2) if rs_score > 0 else None,
        "rsRank":  round(rs_rank, 2) if rs_rank > 0 else None,
        "bullets": bullets,
    }
```

---

### Change #2: Volume Analysis (Lines 446-493)

**BEFORE:**
```python
def _build_volume_analysis(row: dict) -> dict:
    avg_vol  = _to_float(row.get("avgVol20"))
    avg_dv   = _to_float(row.get("avgDollarVol20"))
    vol_dry  = _to_float(row.get("volumeDryUpRatio"))
    vol_score = _to_float(row.get("volumeDryUpScore"))
    vol_pct  = _to_float(row.get("vol%"))
    # ⚠️ MISSING: rexp field

    bullets: list[str] = []
    # ... existing logic ...

    if vol_pct != 0:
        if vol_pct > 0:
            bullets.append(f"📈 Breakout bar volume: {vol_pct:.1f}% above average — strong institutional participation.")
        else:
            bullets.append(f"📉 Breakout bar volume: {abs(vol_pct):.1f}% below average — weak volume on breakout.")
    # ⚠️ MISSING: rexp logic

    return {
        "avgVol20":       int(avg_vol) if avg_vol else None,
        "avgDollarVol20": round(avg_dv, 0) if avg_dv else None,
        "dryUpRatio":     round(vol_dry, 3) if vol_dry else None,
        "dryUpScore":     round(vol_score, 2) if vol_score else None,
        "bullets":        bullets,
    }
```

**AFTER:**
```python
def _build_volume_analysis(row: dict) -> dict:
    avg_vol  = _to_float(row.get("avgVol20"))
    avg_dv   = _to_float(row.get("avgDollarVol20"))
    vol_dry  = _to_float(row.get("volumeDryUpRatio"))
    vol_score = _to_float(row.get("volumeDryUpScore"))
    vol_pct  = _to_float(row.get("vol%"), default=0.0)  # ✅ Safe default
    rexp     = _to_float(row.get("rexp"), default=0.0)   # ✅ NEW: Range expansion

    bullets: list[str] = []
    # ... existing logic ...

    if vol_pct and vol_pct != 0:  # ✅ Better check
        if vol_pct > 0:
            bullets.append(f"📈 Breakout bar volume: {vol_pct:.1f}% above average — strong institutional participation.")
        else:
            bullets.append(f"📉 Breakout bar volume: {abs(vol_pct):.1f}% below average — weak volume on breakout.")
    
    # ✅ NEW: REXP quality tiers
    if rexp and rexp > 0:
        if rexp >= 4.0:
            bullets.append(f"🎯 Range expansion: {rexp:.2f}x — very strong breakout candle.")
        elif rexp >= 2.5:
            bullets.append(f"✅ Range expansion: {rexp:.2f}x — strong breakout candle.")
        elif rexp >= 1.5:
            bullets.append(f"🟡 Range expansion: {rexp:.2f}x — moderate breakout signal.")
        else:
            bullets.append(f"📊 Range expansion: {rexp:.2f}x — wide candle present.")

    return {
        "avgVol20":       int(avg_vol) if avg_vol else None,
        "avgDollarVol20": round(avg_dv, 0) if avg_dv else None,
        "dryUpRatio":     round(vol_dry, 3) if vol_dry else None,
        "dryUpScore":     round(vol_score, 2) if vol_score else None,
        "volPct":         round(vol_pct, 2) if vol_pct else None,     # ✅ NEW
        "rexp":           round(rexp, 2) if rexp else None,           # ✅ NEW
        "bullets":        bullets,
    }
```

---

## Summary of Changes

| Item | Before | After | Impact |
|------|--------|-------|--------|
| **Trade Plan Items** | 12 | 7 | -5 items (T1, T2, T3, R:R) |
| **VOL% Field** | Not displayed | Displayed | Shows volume surge % |
| **REXP Field** | Missing | Added | Shows breakout strength |
| **RS 3M/6M** | Separate section | Integrated | In regime display |
| **Zero Handling** | Returns 0 | Returns None | Clearer intent |
| **Default Values** | None | `default=0.0` | Prevents NaN errors |

---

## Testing the Changes

### Before Fix
```
Trade Plan:
- Target 1: 0.00  ❌ Wrong (calculated incorrectly)
- Target 2: 0.00  ❌ Wrong
- Target 3: 0.00  ❌ Wrong

Regime:
- Score: 0.00
(RS metrics in separate section)
```

### After Fix
```
Trade Plan:  ✅ Clean, focused
- Current Price: 755.20
- Entry: 755.20
- Stop Loss: 659.35
- Risk/Share: 95.85
- Shares: 104
- Dist from Pivot: 0.00%

Regime: ✅ Complete metrics
- Unfavorable | Score: 50.2
- RS 3M: 75.5% | RS 6M: 42.1%
- VOL%: 69.0% | REXP: 4.26x
```

---

## 3. Trade Board Changes — April 14, 2026

### Backend (`apps/web/api/main.py`)

#### Change #1: Day P&L helper — `_get_price_info()`
**BEFORE:**
```python
def _get_current_price(symbol: str) -> Optional[float]:
    rows = _read_ohlcv(symbol, days=5)
    return rows[-1]["close"] if rows else None
```

**AFTER:**
```python
def _get_current_price(symbol: str) -> Optional[float]:
    rows = _read_ohlcv(symbol, days=5)
    return rows[-1]["close"] if rows else None

def _get_price_info(symbol: str) -> tuple[Optional[float], Optional[float]]:
    """Returns (cmp, prev_close) from cached OHLCV data."""
    rows = _read_ohlcv(symbol, days=5)
    if not rows:
        return None, None
    return rows[-1]["close"], rows[-2]["close"] if len(rows) >= 2 else None
```

---

#### Change #2: `_compute_board_stats()` — live day_pl
**BEFORE:** `day_pl = 0.0` (never computed)

**AFTER:**
```python
day_pl += p.get("dayChangeAmt", 0) or 0   # summed per open position
```

---

#### Change #3: `trade_board_positions()` — closed gain + day change
**BEFORE:**
```python
for p in positions:
    if p.get("status") == "OPEN":
        cmp = _get_current_price(p.get("symbol",""))
        if cmp:
            p["gainPct"] = round((cmp - p["entry"]) / p["entry"] * 100, 2)
            p["gainAmt"] = round((cmp - p["entry"]) * p.get("quantity", 1), 2)
```

**AFTER:**
```python
for p in positions:
    entry = p.get("entry", 0) or 0
    qty   = p.get("quantity", 1) or 1
    if p.get("status") == "OPEN":
        cmp, prev_close = _get_price_info(p.get("symbol", ""))
        if cmp:
            p["gainPct"] = round((cmp - entry) / entry * 100, 2)
            p["gainAmt"] = round((cmp - entry) * qty, 2)
        if cmp and prev_close and prev_close > 0:
            p["dayChangePct"] = round((cmp - prev_close) / prev_close * 100, 2)
            p["dayChangeAmt"] = round((cmp - prev_close) * qty, 2)
    elif p.get("exit_price") and entry:          # ✅ NEW: closed position gain
        ep = float(p["exit_price"])
        p["gainPct"] = round((ep - entry) / entry * 100, 2)
        p["gainAmt"] = round((ep - entry) * qty, 2)
```

---

#### Change #4: `trade_board_scan_signals()` — fallback + score normalisation
**BEFORE:** Only tried `open_trades_*_LATEST.json`; failed silently if missing.

**AFTER:** Falls back to `vcp_hits_*_LATEST.json`; normalises `score` field to `rankingScore`.

---

### Frontend (`apps/web/ui/trade_board.html`)

#### Change #1: Day change chip on card
```javascript
// Added to card-gain div (OPEN positions only)
const dayChgHtml = (p.status === 'OPEN' && dayChg != null)
  ? `<div class="card-gain-day ${dayChg>=0?'gain-pos':'gain-neg'}">${dayChg>=0?'▲':'▼'} ${Math.abs(dayChg).toFixed(1)}% today</div>`
  : '';
```

#### Change #2: Status-aware card footer
```javascript
// BEFORE: always "Holding Xd"
// AFTER:
const footerText = p.status === 'OPEN'
  ? `⏱ Holding ${days}d`
  : `${statusIcons[p.status]} ${p.status.replace('_',' ')} · ${holdDays}d`;
```

#### Change #3: EMA badge injected post-chart
After chart data loads in `renderMiniChart()`:
```javascript
const aboveEma5  = cmpNow > last.ema5;
const aboveEma20 = last.ema20 ? cmpNow > last.ema20 : true;
let maCls   = aboveEma5 && aboveEma20 ? 'ma-safe' : aboveEma20 ? 'ma-warn' : 'ma-danger';
let maLabel = aboveEma5 && aboveEma20 ? 'Above MAs' : aboveEma5 ? 'EMA20 ⚠' : 'Below MAs ⚠';
// Badge appended to #badges-{id} div in the card
```

#### Change #4: Detail panel — Trade Plan with R:R
```javascript
const risk = sl > 0 ? entry - sl : 0;
const rrT1 = risk > 0 && p.t1 ? ((p.t1 - entry) / risk).toFixed(1) : null;
// Renders: T2 · 2.4R  |  ₹478  |  +12.3% from entry
```

#### Change #5: `prefillFromSignal()` — T1/T2/T3 mapping
```javascript
// BEFORE: only entry + sl
// AFTER:
const t1 = parseFloat(s.T1||s.t1||0) || '';   // scan JSON uses uppercase T1
const t2 = parseFloat(s.T2||s.t2||0) || '';
const t3 = parseFloat(s.T3||s.t3||0) || '';
openAddModal({ symbol, entry, sl, t1, t2, t3, setup, rating, notes });
```

#### Change #6: Closed trades performance summary
```javascript
const winRate    = trades.length ? (wins.length / trades.length * 100) : 0;
const avgWin     = wins.length ? wins.reduce((s,t)=>s+t.pl,0)/wins.length : 0;
const avgLoss    = losses.length ? losses.reduce((s,t)=>s+t.pl,0)/losses.length : 0;
const expectancy = winRate/100 * avgWin + (1-winRate/100) * avgLoss;
// Rendered as: Win Rate · Avg Win · Avg Loss · Expectancy
```

---

✅ **All Trade Board changes complete and verified (server live at http://localhost:8000/board)**
✅ **All changes complete and verified!**

