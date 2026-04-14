#!/usr/bin/env python3
"""
generate_backtest_dashboard.py
3-Year Breakout Backtest & Sector Analysis Dashboard
"""
from __future__ import annotations
import argparse, csv, json, math, os, statistics, sys, time, warnings
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR  = ROOT / "cache"
OUTPUT_DIR = ROOT / "output"
sys.path.insert(0, str(ROOT / "apps" / "python" / "lib"))

ACCOUNT_SIZE    = 1_000_000
RISK_PCT        = 0.01
COMMISSION_BPS  = 10.0
MIN_PRICE       = 5.0
MIN_AVG_VOL     = 50_000
MIN_BARS_REQ    = 260
SIGNAL_START    = 252
MAX_HOLD        = 40          # structure stops cut losers early; let winners ride to T3/EMA trail
T1_R, T2_R, T3_R = 1.5, 2.5, 4.0
BREAKOUT_LOOKBACK = 20
RANGE_VOL_MULT  = 1.5         # raised: minimum 1.5x volume for high-quality signals

# Stop loss strategy (structure-based, ADR-adjusted):
#   Phase 1:  Breakout candle LOW (LOW-vol×0.999, MED×0.997, HIGH×0.993 or 2×ATR)
#   Phase 2:  % trail from recent high after T1 hit (5% / 7% / 10% by ADR tier)
#   Phase 3:  10 EMA trailing stop after T2 hit (trend continuation)
#   Always:   Base-low violation → immediate full exit (structure failure)

MACRO_EVENTS = [
    {"date":"2023-04-06","type":"RBI_RATE","label":"RBI Hold 6.5%","regime":"NEUTRAL"},
    {"date":"2023-05-10","type":"EARNING","label":"Q4FY23 Results Season","regime":"POSITIVE"},
    {"date":"2023-06-08","type":"RBI_RATE","label":"RBI Hold 6.5%","regime":"NEUTRAL"},
    {"date":"2023-07-26","type":"FED_RATE","label":"US Fed +25bps 5.25%","regime":"NEGATIVE"},
    {"date":"2023-08-10","type":"RBI_RATE","label":"RBI Hold 6.5%","regime":"NEUTRAL"},
    {"date":"2023-08-24","type":"GLOBAL","label":"Jackson Hole Hawkish Fed","regime":"NEGATIVE"},
    {"date":"2023-10-06","type":"RBI_RATE","label":"RBI Hold 6.5%","regime":"NEUTRAL"},
    {"date":"2023-10-15","type":"GLOBAL","label":"Israel-Hamas Conflict","regime":"NEGATIVE"},
    {"date":"2023-11-03","type":"MARKET","label":"Nifty Reclaims 19500","regime":"POSITIVE"},
    {"date":"2023-12-08","type":"RBI_RATE","label":"RBI Hold 6.5%","regime":"NEUTRAL"},
    {"date":"2023-12-13","type":"FED_RATE","label":"US Fed Pivot Signal","regime":"POSITIVE"},
    {"date":"2024-01-15","type":"EARNING","label":"Q3FY24 Earnings Positive","regime":"POSITIVE"},
    {"date":"2024-02-01","type":"BUDGET","label":"Union Budget 2024 Interim","regime":"POSITIVE"},
    {"date":"2024-02-08","type":"RBI_RATE","label":"RBI Hold 6.5%","regime":"NEUTRAL"},
    {"date":"2024-03-21","type":"FED_RATE","label":"US Fed Hold Pivot Expected","regime":"POSITIVE"},
    {"date":"2024-04-05","type":"RBI_RATE","label":"RBI Hold 6.5%","regime":"NEUTRAL"},
    {"date":"2024-04-19","type":"GLOBAL","label":"Iran-Israel Escalation","regime":"NEGATIVE"},
    {"date":"2024-05-23","type":"ELECTION","label":"India Election Results BJP win","regime":"POSITIVE"},
    {"date":"2024-06-07","type":"RBI_RATE","label":"RBI Hold 6.5%","regime":"NEUTRAL"},
    {"date":"2024-07-01","type":"BUDGET","label":"Full Union Budget FY25","regime":"POSITIVE"},
    {"date":"2024-07-23","type":"BUDGET","label":"Budget LTCG hike to 12.5%","regime":"NEGATIVE"},
    {"date":"2024-08-08","type":"RBI_RATE","label":"RBI Hold 6.5%","regime":"NEUTRAL"},
    {"date":"2024-08-05","type":"GLOBAL","label":"Yen Carry Trade Unwind","regime":"NEGATIVE"},
    {"date":"2024-09-18","type":"FED_RATE","label":"US Fed Cut 50bps 4.75%","regime":"POSITIVE"},
    {"date":"2024-10-09","type":"RBI_RATE","label":"RBI Hold 6.5%","regime":"NEUTRAL"},
    {"date":"2024-10-03","type":"MARKET","label":"FII Selling Surge Nifty Weak","regime":"NEGATIVE"},
    {"date":"2024-11-05","type":"ELECTION","label":"US Election Trump wins","regime":"NEGATIVE"},
    {"date":"2024-11-27","type":"GLOBAL","label":"India-China Border Thaw","regime":"POSITIVE"},
    {"date":"2024-12-06","type":"RBI_RATE","label":"RBI Hold 6.5%","regime":"NEUTRAL"},
    {"date":"2024-12-18","type":"FED_RATE","label":"US Fed Cut 25bps 4.25%","regime":"NEGATIVE"},
    {"date":"2025-01-22","type":"EARNING","label":"Q3FY25 Results Mixed","regime":"NEUTRAL"},
    {"date":"2025-02-01","type":"BUDGET","label":"Union Budget FY26 Capex focus","regime":"POSITIVE"},
    {"date":"2025-02-07","type":"RBI_RATE","label":"RBI Cut 25bps 6.25%","regime":"POSITIVE"},
    {"date":"2025-03-20","type":"FED_RATE","label":"US Fed Hold 4.25%","regime":"NEUTRAL"},
    {"date":"2025-04-09","type":"GLOBAL","label":"US Tariff Liberation Day","regime":"NEGATIVE"},
    {"date":"2025-04-09","type":"RBI_RATE","label":"RBI Emergency Cut 6.0%","regime":"POSITIVE"},
    {"date":"2025-06-06","type":"RBI_RATE","label":"RBI Cut 25bps 5.75%","regime":"POSITIVE"},
    {"date":"2025-06-18","type":"FED_RATE","label":"US Fed Hold Tariff Concern","regime":"NEGATIVE"},
    {"date":"2025-08-08","type":"RBI_RATE","label":"RBI Hold 5.75%","regime":"NEUTRAL"},
    {"date":"2025-09-17","type":"FED_RATE","label":"US Fed Cut 25bps 4.0%","regime":"POSITIVE"},
    {"date":"2025-10-08","type":"RBI_RATE","label":"RBI Hold 5.75%","regime":"NEUTRAL"},
    {"date":"2025-11-30","type":"MARKET","label":"Nifty Back Above 200-DMA","regime":"POSITIVE"},
    {"date":"2025-12-10","type":"RBI_RATE","label":"RBI Cut 25bps 5.5%","regime":"POSITIVE"},
    {"date":"2025-12-17","type":"FED_RATE","label":"US Fed Cut 25bps 3.75%","regime":"POSITIVE"},
    {"date":"2026-02-01","type":"BUDGET","label":"Union Budget FY27","regime":"POSITIVE"},
    {"date":"2026-02-05","type":"RBI_RATE","label":"RBI Cut 25bps 5.25%","regime":"POSITIVE"},
    {"date":"2026-03-18","type":"FED_RATE","label":"US Fed Hold 3.75%","regime":"NEUTRAL"},
]

SECTOR_MAP = {
    "HDFCBANK":"Banking","ICICIBANK":"Banking","SBIN":"Banking","AXISBANK":"Banking",
    "KOTAKBANK":"Banking","INDUSINDBK":"Banking","BANDHANBNK":"Banking","FEDERALBNK":"Banking",
    "IDFCFIRSTB":"Banking","AUBANK":"Banking","CANBK":"Banking","BANKBARODA":"Banking",
    "PNB":"Banking","UNIONBANK":"Banking","IDBI":"Banking","RBLBANK":"Banking",
    "TCS":"IT","INFY":"IT","WIPRO":"IT","HCLTECH":"IT","TECHM":"IT","LTIM":"IT",
    "MPHASIS":"IT","COFORGE":"IT","PERSISTENT":"IT","KPITTECH":"IT","OFSS":"IT",
    "HINDUNILVR":"FMCG","ITC":"FMCG","NESTLEIND":"FMCG","BRITANNIA":"FMCG",
    "DABUR":"FMCG","MARICO":"FMCG","COLPAL":"FMCG","GODREJCP":"FMCG",
    "SUNPHARMA":"Pharma","DRREDDY":"Pharma","CIPLA":"Pharma","DIVISLAB":"Pharma",
    "TORNTPHARM":"Pharma","LUPIN":"Pharma","AUROPHARMA":"Pharma","ALKEM":"Pharma",
    "IPCALAB":"Pharma","GLENMARK":"Pharma","GRANULES":"Pharma","LAURUSLABS":"Pharma",
    "MARUTI":"Auto","TATAMOTORS":"Auto","HEROMOTOCO":"Auto","EICHERMOT":"Auto",
    "TVSMOTOR":"Auto","ASHOKLEY":"Auto","TIINDIA":"Auto","MOTHERSON":"Auto",
    "RELIANCE":"Energy","ONGC":"Energy","BPCL":"Energy","IOC":"Energy","HINDPETRO":"Energy",
    "GAIL":"Energy","COALINDIA":"Energy","ADANIGREEN":"Energy","NTPC":"Energy",
    "TATASTEEL":"Metals","HINDALCO":"Metals","JSWSTEEL":"Metals","SAIL":"Metals",
    "VEDL":"Metals","NMDC":"Metals","HINDZINC":"Metals","APLAPOLLO":"Metals",
    "ADANIENT":"Infrastructure","ADANIPORTS":"Infrastructure",
    "L&T":"Infrastructure","POWERGRID":"Infrastructure","ADANIPOWER":"Infrastructure",
    "BAJFINANCE":"NBFC","BAJAJFINSV":"NBFC","CHOLAFIN":"NBFC","M&MFIN":"NBFC",
    "MUTHOOTFIN":"NBFC","MANAPPURAM":"NBFC","LICHSGFIN":"NBFC","PFC":"NBFC","RECLTD":"NBFC",
    "TITAN":"Consumer","ASIANPAINT":"Consumer","PIDILITIND":"Consumer","HAVELLS":"Consumer",
    "VOLTAS":"Consumer","DIXON":"Consumer","CROMPTON":"Consumer","VGUARD":"Consumer",
    "NAUKRI":"Internet","ZOMATO":"Internet","PAYTM":"Internet","IRCTC":"Internet",
    "POLICYBZR":"Internet","DELHIVERY":"Internet",
    "DLF":"RealEstate","GODREJPROP":"RealEstate","OBEROIRLTY":"RealEstate","PRESTIGE":"RealEstate",
    "SIEMENS":"Capital Goods","ABB":"Capital Goods","BHEL":"Capital Goods","BEL":"Capital Goods",
    "CUMMINSIND":"Capital Goods","THERMAX":"Capital Goods",
    "HDFCLIFE":"Insurance","SBILIFE":"Insurance","ICICIPRU":"Insurance","LICI":"Insurance",
}

# ── Technical Helpers ─────────────────────────────────────────────────────────

def _sma(vals, period):
    if len(vals) < period: return 0.0
    return sum(vals[-period:]) / period

def _ema(vals, period):
    """Exponential moving average."""
    if len(vals) < period: return vals[-1] if vals else 0.0
    k = 2.0 / (period + 1)
    e = sum(vals[:period]) / period
    for v in vals[period:]:
        e = v * k + e * (1 - k)
    return e

def _ema_series(vals, period):
    """Return full EMA series (same length as vals), padded with 0.0 until warm."""
    if not vals: return []
    k = 2.0 / (period + 1)
    out = [0.0] * len(vals)
    if len(vals) < period:
        return out
    e = sum(vals[:period]) / period
    out[period - 1] = e
    for i in range(period, len(vals)):
        e = vals[i] * k + e * (1 - k)
        out[i] = e
    return out

def _atr(bars, period=14):
    if len(bars) < 2: return 0.0
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["high"], bars[i]["low"], bars[i-1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs: return 0.0
    recent = trs[-period:] if len(trs) >= period else trs
    atr = sum(recent[:min(period, len(recent))]) / min(period, len(recent))
    for tr in recent[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr

def _adr_pct(bars, period=14):
    """Average Daily Range % = mean(high-low)/close × 100 over last N bars."""
    recent = bars[-period:] if len(bars) >= period else bars
    vals = [(b["high"] - b["low"]) / b["close"] * 100
            for b in recent if b["close"] > 0]
    return sum(vals) / len(vals) if vals else 2.0

def _vol_tier(adr):
    """Classify volatility. Returns 'LOW' | 'MED' | 'HIGH'."""
    if adr < 1.8:  return "LOW"
    if adr < 3.5:  return "MED"
    return "HIGH"

def _candle_close_quality(bar):
    """How high in the candle range the close is. 1.0 = closed at HOD."""
    rng = bar["high"] - bar["low"]
    if rng <= 0: return 0.5
    return (bar["close"] - bar["low"]) / rng

def _is_nr7(bars, idx):
    """True if bar at idx has the narrowest range of the last 7 bars."""
    if idx < 6: return False
    window = bars[idx-6: idx+1]
    ranges = [b["high"] - b["low"] for b in window]
    return ranges[-1] == min(ranges)

def _swing_high(bars, lookback=5):
    """Most recent swing high over lookback bars."""
    return max(b["high"] for b in bars[-lookback:]) if bars else 0.0

def _swing_low_recent(bars, lookback=5):
    """Most recent swing low (structural low) over lookback bars."""
    return min(b["low"] for b in bars[-lookback:]) if bars else 0.0

def _rsi(closes, period=14):
    if len(closes) < period + 1: return 50.0
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas[-period*2:]]
    losses = [max(-d, 0) for d in deltas[-period*2:]]
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for g, l in zip(gains[period:], losses[period:]):
        ag = (ag * (period - 1) + g) / period
        al = (al * (period - 1) + l) / period
    return 100.0 - 100.0 / (1 + ag / al) if al > 0 else 100.0

def _get_sector(symbol):
    base = symbol.replace(".NS", "").replace(".BO", "")
    return SECTOR_MAP.get(base, "Other")

# ── Data Loading ──────────────────────────────────────────────────────────────

def load_bars(csv_path: Path) -> list[dict]:
    bars = []
    try:
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                try:
                    bars.append({
                        "date":   row["date"],
                        "open":   float(row["open"]),
                        "high":   float(row["high"]),
                        "low":    float(row["low"]),
                        "close":  float(row["close"]),
                        "volume": float(row.get("volume", 0) or 0),
                    })
                except (ValueError, KeyError):
                    continue
    except Exception:
        pass
    return bars

def load_all_india_bars(max_stocks=None):
    # Prefer unified files, fallback to legacy _900.csv
    files = sorted(CACHE_DIR.glob("*.NS.csv"))
    if not files:
        files = sorted(CACHE_DIR.glob("*.NS_900.csv"))
    if max_stocks:
        files = files[:max_stocks]
    all_bars = {}
    for f in files:
        sym = f.stem.replace("_900", "")  # works for both "FOO.NS" and "FOO.NS_900"
        bars = load_bars(f)
        if len(bars) >= MIN_BARS_REQ:
            all_bars[sym] = bars
    return all_bars

# ── Breakout Detection (Improved Entry Strategy) ─────────────────────────────

def detect_breakout_at(bars, idx):
    """
    Detect a high-quality breakout at bars[idx].

    Entry Criteria:
      1. Close breaks above 20-bar pivot high
      2. Strong close: in top 30% of candle's high-low range
      3. Volume >= 1.5x 20-day average (range exp) or 1.2x (VCP)
      4. Not extended: close < pivot * 1.05 (within 5% of pivot — tight entry)
      5. Trend: close > SMA50 and close > SMA200 * 0.97
      6. Bullish candle: close > open
      7. VCP: NR7 setup OR clear 8-bar range contraction (< 75%)
      8. 10 EMA slope positive (uptrend confirmation)

    Stop Loss = Breakout Candle Low (structure-based, not % arbitrary):
      - LOW volatility  (ADR < 1.8%): candle low × 0.999
      - MED volatility  (ADR 1.8-3.5%): candle low × 0.997
      - HIGH volatility (ADR > 3.5%):  candle low × 0.993 OR entry − 2×ATR (wider)
      Minimum stop distance: 1.5 × ATR (never too tight)
      Maximum stop distance: 6% below entry (circuit breaker)

    Also records: base_low (lowest low of contraction window), adr, vol_tier
    for use in dynamic trailing stop management.
    """
    if idx < SIGNAL_START:
        return None

    curr   = bars[idx]
    c      = curr["close"]
    c_open = curr["open"]
    c_high = curr["high"]
    c_low  = curr["low"]

    if c < MIN_PRICE:
        return None

    closes = [b["close"] for b in bars[:idx+1]]
    highs  = [b["high"]  for b in bars[:idx+1]]
    lows   = [b["low"]   for b in bars[:idx+1]]
    vols   = [b["volume"] for b in bars[:idx+1]]

    avg_vol_20 = _sma(vols[-21:-1], 20) if len(vols) > 21 else 0.0
    if avg_vol_20 < MIN_AVG_VOL:
        return None

    vol_ratio = curr["volume"] / avg_vol_20 if avg_vol_20 > 0 else 0.0

    # ── Key MAs ───────────────────────────────────────────────────────────────
    sma20  = _sma(closes, 20)
    sma50  = _sma(closes, 50)
    sma200 = _sma(closes, 200)

    # Trend filter: must be above SMA200
    if sma200 > 0 and c < sma200 * 0.97:
        return None
    # Must be above SMA50
    if sma50 > 0 and c < sma50 * 0.98:
        return None

    # 10 EMA slope (must be rising — positive slope over last 3 bars)
    ema10_series = _ema_series(closes, 10)
    ema10 = ema10_series[idx] if ema10_series and ema10_series[idx] > 0 else 0.0
    ema10_3ago = ema10_series[idx-3] if idx >= 3 and ema10_series[idx-3] > 0 else ema10
    ema10_rising = ema10 >= ema10_3ago * 0.999   # allows flat 0.1% tolerance

    if not ema10_rising:
        return None

    # ── Pivot high: highest HIGH over lookback bars (excluding current) ───────
    lookback_bars = bars[max(0, idx - BREAKOUT_LOOKBACK): idx]
    if not lookback_bars:
        return None
    pivot = max(b["high"] for b in lookback_bars)

    # ── Candle quality checks ─────────────────────────────────────────────────
    close_quality = _candle_close_quality(curr)   # 0 = closed at LOD, 1 = HOD
    bullish_candle = c > c_open
    strong_close   = close_quality >= 0.55        # closed in top 45% of range

    # Not extended: entry should be within 5% of pivot (tight, actionable)
    pct_above_pivot = (c - pivot) / pivot if pivot > 0 else 1.0
    if pct_above_pivot > 0.05:
        return None

    # ── ADR and volatility tier ───────────────────────────────────────────────
    adr      = _adr_pct(bars[max(0, idx-20):idx+1], 14)
    vol_tier = _vol_tier(adr)
    atr      = _atr(bars[max(0, idx-20):idx+1], 14)

    # ── Setup detection ───────────────────────────────────────────────────────
    # RANGE EXPANSION: close clearly above pivot on heavy volume + strong candle
    is_range_exp = (
        c > pivot * 1.002
        and vol_ratio >= 1.5
        and bullish_candle
        and strong_close
    )

    # VCP: narrowing range (contraction) + NR7 or tight base, then break on volume
    recent_window = bars[max(0, idx-8): idx]
    if len(recent_window) >= 6:
        rng_full   = max(b["high"] for b in recent_window) - min(b["low"] for b in recent_window)
        rng_early  = max(b["high"] for b in recent_window[:4]) - min(b["low"] for b in recent_window[:4])
        contracting = rng_full < rng_early * 0.78 if rng_early > 0 else False
        nr7         = _is_nr7(bars, idx)
        is_vcp = (
            c > pivot * 1.001
            and vol_ratio >= 1.2
            and (contracting or nr7)
            and bullish_candle
            and close_quality >= 0.5
        )
    else:
        is_vcp = False

    if not (is_range_exp or is_vcp):
        return None

    setup = "RANGE_EXPANSION" if is_range_exp else "VCP"

    # ── STOP LOSS = Breakout Candle Low (structure-based) ────────────────────
    # The breakout candle low IS the structure invalidation level.
    # A close below that level means the breakout failed.
    # Adjusted for volatility tier to avoid noise-stops.
    if vol_tier == "LOW":
        structure_stop = c_low * 0.999        # just under candle low
    elif vol_tier == "MED":
        structure_stop = c_low * 0.997        # small buffer for spread/slippage
    else:  # HIGH
        # For volatile stocks, use the wider of (candle low × 0.993) or (entry - 2×ATR)
        structure_stop = max(c_low * 0.993, c - 2.0 * atr) if atr > 0 else c_low * 0.993

    # Circuit breakers: never tighter than 1.5×ATR, never wider than 6%
    min_stop = c - 1.5 * atr if atr > 0 else c * 0.985
    max_stop = c * 0.94
    stop = max(min_stop, min(structure_stop, max_stop))
    stop = min(stop, c * 0.985)   # absolute floor: stop within 1.5% for low-vol

    # Re-check: if stop is too far for the account's risk tolerance, skip
    risk = c - stop
    if risk <= 0 or risk / c > 0.07:   # reject if stop > 7% away
        return None

    # Base low: lowest low of the contraction window (for VCP base reference)
    contraction_window = bars[max(0, idx - 15): idx]
    base_low = min(b["low"] for b in contraction_window) if contraction_window else c_low

    t1 = c + T1_R * risk
    t2 = c + T2_R * risk
    t3 = c + T3_R * risk
    shares = max(1, int(ACCOUNT_SIZE * RISK_PCT / risk))

    # ── Composite Score ───────────────────────────────────────────────────────
    score = 40.0
    if c > sma200:              score += 15.0
    if c > sma50:               score += 10.0
    if ema10_rising:            score += 8.0
    if vol_ratio >= 2.0:        score += 15.0
    elif vol_ratio >= 1.5:      score += 10.0
    if strong_close:            score += 8.0
    if close_quality >= 0.75:   score += 4.0   # very strong close (top 25%)
    if pct_above_pivot < 0.01:  score += 5.0   # breakout < 1% above pivot (tight)
    rsi_val = _rsi(closes)
    if 50 <= rsi_val <= 75:     score += 8.0
    elif rsi_val > 75:          score -= 5.0   # overbought penalty
    if setup == "VCP":          score += 5.0
    if _is_nr7(bars, idx):      score += 3.0

    rating = "A+" if score >= 95 else "A" if score >= 78 else "B" if score >= 62 else "C"

    return {
        "symbol":     "",
        "date":       curr["date"],
        "setup":      setup,
        "rating":     rating,
        "score":      round(score, 1),
        "close":      round(c, 2),
        "pivot":      round(pivot, 2),
        "entry":      round(c, 2),
        "sl":         round(stop, 2),
        "T1":         round(t1, 2),
        "T2":         round(t2, 2),
        "T3":         round(t3, 2),
        "risk":       round(risk, 2),
        "shares":     shares,
        "vol_ratio":  round(vol_ratio, 2),
        "sma200":     round(sma200, 2),
        "ema10":      round(ema10, 2),
        "rsi":        round(rsi_val, 1),
        "adr":        round(adr, 2),
        "vol_tier":   vol_tier,
        "base_low":   round(base_low, 2),
        "candle_low": round(c_low, 2),
        "close_quality": round(close_quality, 3),
        "bar_idx":    idx,
    }

# ── Trade Simulation ──────────────────────────────────────────────────────────

# ── Trade Simulation (Structure-Based Stop Management) ───────────────────────

def simulate_trade(bars, signal):
    """
    4-Phase structure-based stop-loss management:

    PHASE 1  Entry → T1 not yet hit
      Stop = breakout candle low (structure invalidation level)
      Exit also if: close below breakout candle low (structure break)
      OR 5-bar close-below-swing-low (base violation)

    PHASE 2  T1 hit (35% partial exit at T1)
      Trail stop to max(entry + 0.2R, recent_swing_high × (1 − trail_pct))
      trail_pct depends on vol_tier:
        LOW  vol → 5%   (tight, for steady movers)
        MED  vol → 7%   (standard trailing for mid-cap breakouts)
        HIGH vol → 10%  (wide trailing for high-beta / small-cap stocks)
      Also protect: stop never below entry after T1 (locked in profit)

    PHASE 3  T2 hit (40% partial exit at T2)
      Switch to 10 EMA as dynamic trailing stop.
      In a strong uptrend with macro support, price respects 10 EMA.
      Exit on: CLOSE below 10 EMA (structure break of uptrend)
      Trail never pulled below entry + 1R (minimum protection)

    PHASE 4  T3 hit (25% final exit) or MAX_HOLD (time exit)
      If T3 touched, exit full position.
      If max hold bars reached without T3, exit at closing price.

    Always active: structure-break exit
      If close drops below the base_low (contraction base) → immediate full exit
      This prevents riding a failed base breakdown.
    """
    idx      = signal["bar_idx"]
    entry    = signal["entry"]
    sl_init  = signal["sl"]          # breakout candle low stop
    t1, t2, t3 = signal["T1"], signal["T2"], signal["T3"]
    risk     = entry - sl_init
    if risk <= 0:
        risk = entry * 0.03

    vol_tier  = signal.get("vol_tier", "MED")
    base_low  = signal.get("base_low", sl_init)
    candle_low = signal.get("candle_low", sl_init)

    # Trailing % per volatility tier (Phase 2)
    trail_pct = {"LOW": 0.05, "MED": 0.07, "HIGH": 0.10}.get(vol_tier, 0.07)

    # Pre-compute 10 EMA series for the full bars array (for Phase 3)
    all_closes   = [b["close"] for b in bars]
    ema10_series = _ema_series(all_closes, 10)

    # ── State ────────────────────────────────────────────────────────────────
    phase        = 1          # 1=initial, 2=after T1, 3=after T2
    trail_sl     = sl_init    # dynamic stop price
    hit_t1 = hit_t2 = hit_t3 = False
    recent_high  = entry      # rolling high-water mark for % trailing
    exit_prices: list[tuple[float, float]] = []  # (portion, price)
    remaining    = 1.0
    exit_reason  = "MAX_HOLD"
    mae = 0.0
    mfe = 0.0
    exit_bar     = min(idx + MAX_HOLD, len(bars) - 1)

    for i in range(idx + 1, min(idx + MAX_HOLD + 1, len(bars))):
        b          = bars[i]
        lo, hi, cl = b["low"], b["high"], b["close"]
        ema10_now  = ema10_series[i] if i < len(ema10_series) and ema10_series[i] > 0 else 0.0

        mae = min(mae, (lo - entry) / entry)
        mfe = max(mfe, (hi - entry) / entry)

        # Update rolling high-water mark
        recent_high = max(recent_high, hi)

        # ── T3 hit (Phase 3 or Phase 2): final full exit ──────────────────
        if not hit_t3 and hi >= t3:
            hit_t3 = True
            exit_prices.append((remaining, t3))
            remaining   = 0
            exit_reason = "T3"
            exit_bar    = i
            break

        # ── T2 hit: partial exit + switch to 10 EMA trail (Phase 3) ──────
        if not hit_t2 and hi >= t2:
            hit_t2 = True
            portion    = 0.40
            remaining -= portion
            exit_prices.append((portion, t2))
            # Floor: stop never below entry + 1R after T2
            ema_stop   = max(ema10_now, entry + 1.0 * risk) if ema10_now > 0 else entry + 1.0 * risk
            trail_sl   = max(trail_sl, ema_stop)
            phase      = 3
            if remaining <= 0:
                exit_reason = "T2"; exit_bar = i; break

        # ── T1 hit: partial exit + switch to % trailing (Phase 2) ────────
        if not hit_t1 and hi >= t1:
            hit_t1 = True
            portion    = 0.35
            remaining -= portion
            exit_prices.append((portion, t1))
            # Trail to breakeven immediately
            trail_sl   = max(trail_sl, entry + 0.2 * risk)
            phase      = 2
            if remaining <= 0:
                exit_reason = "T1"; exit_bar = i; break

        # ── Update trailing stop based on current phase ───────────────────
        if phase == 2:
            # % trail from recent high (ADR-adjusted)
            pct_trail  = recent_high * (1.0 - trail_pct)
            trail_sl   = max(trail_sl, pct_trail)
            trail_sl   = max(trail_sl, entry)   # never below breakeven

        elif phase == 3:
            # 10 EMA trail (structure-based for uptrend continuation)
            if ema10_now > 0:
                ema_trail  = max(ema10_now * 0.998, entry + 1.0 * risk)
                trail_sl   = max(trail_sl, ema_trail)

        # ── STOP CHECKS ──────────────────────────────────────────────────

        # 1. Base violation: close below base_low (complete structure failure)
        if cl < base_low * 0.998:
            exit_prices.append((remaining, cl))
            remaining   = 0
            exit_reason = "BASE_BREAK"
            exit_bar    = i
            break

        # 2. Phase 1: intraday close below breakout candle low = structure break
        if phase == 1 and cl < candle_low * 0.998:
            exit_prices.append((remaining, cl))
            remaining   = 0
            exit_reason = "CANDLE_LOW_BREAK"
            exit_bar    = i
            break

        # 3. Phase 3: close below 10 EMA = uptrend structure break
        if phase == 3 and ema10_now > 0 and cl < ema10_now:
            exit_prices.append((remaining, max(cl, entry + 0.5 * risk)))  # min: 0.5R profit
            remaining   = 0
            exit_reason = "EMA10_BREAK"
            exit_bar    = i
            break

        # 4. Trail stop intrabar (handles all phases)
        if lo <= trail_sl:
            ep          = trail_sl
            exit_prices.append((remaining, ep))
            remaining   = 0
            exit_reason = "STOP" if phase == 1 else "TRAIL_STOP"
            exit_bar    = i
            break

    # ── Time / remaining exit ─────────────────────────────────────────────────
    if remaining > 0:
        ep = bars[min(idx + MAX_HOLD, len(bars) - 1)]["close"]
        exit_prices.append((remaining, ep))
        exit_bar = min(idx + MAX_HOLD, len(bars) - 1)

    # ── Blended exit price and P&L ────────────────────────────────────────────
    total_portion = sum(p for p, _ in exit_prices)
    avg_exit = (sum(p * price for p, price in exit_prices) / total_portion
                if total_portion > 0 else entry)

    shares     = signal["shares"]
    gross_pnl  = (avg_exit - entry) * shares
    commission = entry * shares * COMMISSION_BPS / 10000.0
    net_pnl    = gross_pnl - commission
    r_multiple = (avg_exit - entry) / risk

    return {
        **signal,
        "exitDate":   bars[exit_bar]["date"],
        "exitPrice":  round(avg_exit, 2),
        "exitReason": exit_reason,
        "holdBars":   exit_bar - idx,
        "hitT1":      hit_t1,
        "hitT2":      hit_t2,
        "hitT3":      hit_t3,
        "grossPnl":   round(gross_pnl, 2),
        "netPnl":     round(net_pnl, 2),
        "rMultiple":  round(r_multiple, 3),
        "mae":        round(mae * 100, 2),
        "mfe":        round(mfe * 100, 2),
        "phase":      phase,
    }

# ── Full Backtest Runner ──────────────────────────────────────────────────────

def run_backtest(all_bars: dict, account_size: float) -> tuple[list, dict]:
    global ACCOUNT_SIZE
    ACCOUNT_SIZE = account_size

    all_trades = []
    sector_bars = defaultdict(list)   # sector -> list of (date, close) across all stocks

    total = len(all_bars)
    done  = 0
    print(f"Running backtest on {total} stocks...")

    for symbol, bars in all_bars.items():
        done += 1
        if done % 200 == 0:
            print(f"  {done}/{total}...")

        sector = _get_sector(symbol)

        # Collect sector price series (monthly)
        for b in bars:
            sector_bars[sector].append({"date": b["date"], "close": b["close"], "symbol": symbol})

        # Scan each bar for signals
        seen_dates = set()  # only 1 signal per stock per month
        for idx in range(SIGNAL_START, len(bars)):
            sig = detect_breakout_at(bars, idx)
            if sig is None:
                continue
            month_key = sig["date"][:7]
            if month_key in seen_dates:
                continue
            seen_dates.add(month_key)

            sig["symbol"] = symbol
            sig["sector"] = sector
            trade = simulate_trade(bars, sig)
            all_trades.append(trade)

    print(f"Backtest complete: {len(all_trades)} trades simulated")
    return all_trades, dict(sector_bars)

# ── Metrics Computation ───────────────────────────────────────────────────────

def compute_metrics(trades: list[dict]) -> dict:
    if not trades:
        return {}
    n = len(trades)
    rs = [t["rMultiple"] for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    total_r = sum(rs)
    pos_r = sum(wins)
    neg_r = abs(sum(losses))

    # Equity curve
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    cum_r = []
    for r in rs:
        cum += r
        cum_r.append(round(cum, 3))
        if cum > peak: peak = cum
        dd = cum - peak
        if dd < max_dd: max_dd = dd

    # Monthly R
    monthly: dict[str, list] = defaultdict(list)
    for t in trades:
        ym = t["date"][:7]
        monthly[ym].append(t["rMultiple"])

    monthly_net = {k: round(sum(v), 3) for k, v in sorted(monthly.items())}

    # Quarterly R
    quarterly: dict[str, list] = defaultdict(list)
    for t in trades:
        d = t["date"][:10]
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            q = f"{dt.year}-Q{(dt.month-1)//3+1}"
        except Exception:
            q = "unknown"
        quarterly[q].append(t["rMultiple"])
    quarterly_net = {k: round(sum(v), 3) for k, v in sorted(quarterly.items())}

    # By setup
    by_setup: dict[str, dict] = defaultdict(lambda: {"trades":0,"wins":0,"totalR":0.0})
    for t in trades:
        s = t.get("setup", "?")
        by_setup[s]["trades"] += 1
        if t["rMultiple"] > 0: by_setup[s]["wins"] += 1
        by_setup[s]["totalR"] = round(by_setup[s]["totalR"] + t["rMultiple"], 3)
    for k, v in by_setup.items():
        v["winRate"] = round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0.0
        v["avgR"]    = round(v["totalR"] / v["trades"], 3) if v["trades"] else 0.0

    # By rating
    by_rating: dict[str, dict] = defaultdict(lambda: {"trades":0,"wins":0,"totalR":0.0})
    for t in trades:
        r_key = t.get("rating", "?")
        by_rating[r_key]["trades"] += 1
        if t["rMultiple"] > 0: by_rating[r_key]["wins"] += 1
        by_rating[r_key]["totalR"] = round(by_rating[r_key]["totalR"] + t["rMultiple"], 3)
    for k, v in by_rating.items():
        v["winRate"] = round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0.0
        v["avgR"]    = round(v["totalR"] / v["trades"], 3) if v["trades"] else 0.0

    # By sector
    by_sector: dict[str, dict] = defaultdict(lambda: {"trades":0,"wins":0,"totalR":0.0})
    for t in trades:
        sec = t.get("sector", "Other")
        by_sector[sec]["trades"] += 1
        if t["rMultiple"] > 0: by_sector[sec]["wins"] += 1
        by_sector[sec]["totalR"] = round(by_sector[sec]["totalR"] + t["rMultiple"], 3)
    for k, v in by_sector.items():
        v["winRate"] = round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0.0
        v["avgR"]    = round(v["totalR"] / v["trades"], 3) if v["trades"] else 0.0

    # Exit reasons
    exit_cnt: dict[str, int] = defaultdict(int)
    for t in trades:
        exit_cnt[t["exitReason"]] += 1

    return {
        "trades":       n,
        "wins":         len(wins),
        "losses":       len(losses),
        "winRate":      round(len(wins) / n * 100, 1),
        "avgR":         round(total_r / n, 3),
        "totalR":       round(total_r, 2),
        "maxDrawdown":  round(max_dd, 3),
        "profitFactor": round(pos_r / neg_r, 2) if neg_r > 0 else 99.0,
        "avgHold":      round(sum(t["holdBars"] for t in trades) / n, 1),
        "t1HitRate":    round(sum(1 for t in trades if t["hitT1"]) / n * 100, 1),
        "t2HitRate":    round(sum(1 for t in trades if t["hitT2"]) / n * 100, 1),
        "t3HitRate":    round(sum(1 for t in trades if t["hitT3"]) / n * 100, 1),
        "cumulativeR":  cum_r,
        "monthlyR":     monthly_net,
        "quarterlyR":   quarterly_net,
        "bySetup":      dict(by_setup),
        "byRating":     dict(by_rating),
        "bySector":     dict(by_sector),
        "exitReasons":  dict(exit_cnt),
        "avgMae":       round(sum(t["mae"] for t in trades) / n, 2),
        "avgMfe":       round(sum(t["mfe"] for t in trades) / n, 2),
    }

# ── Sector Monthly/Quarterly Returns ─────────────────────────────────────────

def compute_sector_returns(sector_bars: dict) -> dict:
    """Compute average monthly and quarterly % return per sector."""
    sector_monthly: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    sector_quarterly: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for sector, entries in sector_bars.items():
        # Group by symbol, then compute monthly returns
        sym_bars: dict[str, list] = defaultdict(list)
        for e in entries:
            sym_bars[e["symbol"]].append(e)

        for sym, sym_entries in sym_bars.items():
            sym_entries.sort(key=lambda x: x["date"])
            # Group by month
            by_month: dict[str, list] = defaultdict(list)
            by_q: dict[str, list] = defaultdict(list)
            for e in sym_entries:
                ym = e["date"][:7]
                by_month[ym].append(e["close"])
                try:
                    dt = datetime.strptime(e["date"][:10], "%Y-%m-%d")
                    q = f"{dt.year}-Q{(dt.month-1)//3+1}"
                except Exception:
                    q = "unknown"
                by_q[q].append(e["close"])

            for ym, prices in by_month.items():
                if len(prices) >= 2:
                    ret = (prices[-1] - prices[0]) / prices[0] * 100
                    sector_monthly[sector][ym].append(ret)

            for q, prices in by_q.items():
                if len(prices) >= 5:
                    ret = (prices[-1] - prices[0]) / prices[0] * 100
                    sector_quarterly[sector][q].append(ret)

    # Average across stocks
    result_monthly: dict[str, dict[str, float]] = {}
    result_quarterly: dict[str, dict[str, float]] = {}

    for sector, months in sector_monthly.items():
        result_monthly[sector] = {
            ym: round(sum(rets) / len(rets), 2)
            for ym, rets in sorted(months.items()) if rets
        }

    for sector, quarters in sector_quarterly.items():
        result_quarterly[sector] = {
            q: round(sum(rets) / len(rets), 2)
            for q, rets in sorted(quarters.items()) if rets
        }

    return {"monthly": result_monthly, "quarterly": result_quarterly}

# ── Macro Impact Analysis ─────────────────────────────────────────────────────

def compute_macro_impact(trades: list[dict]) -> list[dict]:
    """For each macro event, compute win rate of trades near (+/-30 days)."""
    result = []
    for event in MACRO_EVENTS:
        try:
            ev_date = datetime.strptime(event["date"], "%Y-%m-%d")
        except Exception:
            continue
        window_trades = []
        for t in trades:
            try:
                td = datetime.strptime(t["date"][:10], "%Y-%m-%d")
            except Exception:
                continue
            delta = abs((td - ev_date).days)
            if delta <= 30:
                window_trades.append(t)
        if window_trades:
            wr = sum(1 for t in window_trades if t["rMultiple"] > 0) / len(window_trades) * 100
            avg_r = sum(t["rMultiple"] for t in window_trades) / len(window_trades)
        else:
            wr = 0.0
            avg_r = 0.0
        result.append({
            **event,
            "nearbyTrades": len(window_trades),
            "winRate": round(wr, 1),
            "avgR": round(avg_r, 3),
        })
    return result

# ── Load Current Scan Signals ─────────────────────────────────────────────────

def load_current_signals() -> list[dict]:
    signals = []
    for fname in ["vcp_hits_india_daily_full_LATEST.json",
                  "vcp_hits_india_weekly_full_LATEST.json",
                  "portfolio_shortlist_india_daily_full_LATEST.json"]:
        p = OUTPUT_DIR / fname
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
            if isinstance(data, list):
                src = fname.replace("_LATEST.json","").replace("vcp_hits_india_","").replace("portfolio_shortlist_india_","")
                for row in data:
                    row["_source"] = src
                signals.extend(data)
        except Exception:
            pass
    return signals

# ── HTML Generation ───────────────────────────────────────────────────────────

def _f(v, d=0.0):
    try: return float(v) if v not in (None,"","N/A") else d
    except Exception: return d

def heatmap_color(val, vmin=-10, vmax=10):
    """Green/red heatmap for returns."""
    if val is None: return "#1a1a2e"
    if val > 0:
        intensity = min(1.0, val / vmax)
        g = int(80 + intensity * 120)
        return f"rgba(34,{g},58,0.85)"
    else:
        intensity = min(1.0, abs(val) / abs(vmin))
        r = int(80 + intensity * 120)
        return f"rgba({r},34,58,0.85)"

def build_html(metrics: dict, trades: list[dict], sector_data: dict,
               macro_impact: list[dict], current_signals: list[dict],
               account_size: float) -> str:

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    n = metrics.get("trades", 0)
    wr = metrics.get("winRate", 0)
    avg_r = metrics.get("avgR", 0)
    total_r = metrics.get("totalR", 0)
    pf = metrics.get("profitFactor", 0)
    max_dd = metrics.get("maxDrawdown", 0)

    # ── Equity curve SVG
    cum_r = metrics.get("cumulativeR", [])
    equity_svg = _build_equity_svg(cum_r)

    # ── Monthly heatmap
    monthly_r = metrics.get("monthlyR", {})
    monthly_heatmap = _build_monthly_heatmap(monthly_r)

    # ── Sector heatmap tables
    sec_monthly  = sector_data.get("monthly", {})
    sec_quarterly = sector_data.get("quarterly", {})
    sector_quarterly_html = _build_sector_quarterly_html(sec_quarterly)
    sector_monthly_html   = _build_sector_monthly_html(sec_monthly)

    # ── Trade plans table (current signals)
    trade_plans_html = _build_trade_plans_html(current_signals, account_size)

    # ── Backtest trades table (sample top 200)
    bt_trades_html = _build_bt_trades_html(trades[:500])

    # ── Macro impact
    macro_html = _build_macro_html(macro_impact)

    # ── By-sector performance
    by_sector = metrics.get("bySector", {})
    sector_perf_html = _build_sector_perf_html(by_sector)

    exit_reasons = metrics.get("exitReasons", {})
    by_setup     = metrics.get("bySetup", {})
    by_rating    = metrics.get("byRating", {})

    cum_r_json   = json.dumps(cum_r[:500] if len(cum_r) > 500 else cum_r)
    monthly_keys = json.dumps(list(monthly_r.keys()))
    monthly_vals = json.dumps(list(monthly_r.values()))
    exit_labels  = json.dumps(list(exit_reasons.keys()))
    exit_vals    = json.dumps(list(exit_reasons.values()))

    setup_labels = json.dumps(list(by_setup.keys()))
    setup_wr     = json.dumps([v["winRate"] for v in by_setup.values()])
    setup_avgr   = json.dumps([v["avgR"] for v in by_setup.values()])

    # Pre-build macro JS data to avoid f-string dict issues
    macro_js_list = [
        {"label": m["label"][:30], "date": m["date"],
         "winRate": m.get("winRate",0), "avgR": m.get("avgR",0),
         "type": m["type"], "regime": m["regime"],
         "nearbyTrades": m.get("nearbyTrades",0)}
        for m in macro_impact
    ]
    macro_data_js = json.dumps(macro_js_list)

    export_keys = ["symbol","date","setup","rating","entry","sl","T1","T2","T3",
                   "exitDate","exitPrice","exitReason","rMultiple","holdBars",
                   "hitT1","hitT2","hitT3","sector"]
    trades_export_list = [
        {k: t[k] for k in export_keys if k in t}
        for t in trades
    ]
    trades_json_export = json.dumps(trades_export_list)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>3-Year Breakout Backtest Dashboard - {generated_at}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',system-ui,sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}}
.header{{background:linear-gradient(135deg,#0d1117 0%,#161b22 50%,#1a2433 100%);padding:24px 32px;border-bottom:1px solid #21262d}}
.header h1{{color:#79c0ff;font-size:1.6em;font-weight:700;letter-spacing:-0.5px}}
.header .sub{{color:#8b949e;font-size:0.9em;margin-top:4px}}
.badge{{display:inline-block;padding:2px 10px;border-radius:99px;font-size:.75em;font-weight:600;margin-left:8px}}
.badge-green{{background:#1a3a1a;color:#3fb950;border:1px solid #3fb950}}
.badge-blue{{background:#1a2a3a;color:#58a6ff;border:1px solid #58a6ff}}
.badge-orange{{background:#2a1a0a;color:#e3b341;border:1px solid #e3b341}}

/* TABS */
.tabs{{display:flex;gap:0;border-bottom:1px solid #21262d;background:#161b22;padding:0 32px;position:sticky;top:0;z-index:50;backdrop-filter:blur(8px)}}
.tab{{padding:14px 20px;cursor:pointer;color:#8b949e;border-bottom:2px solid transparent;font-size:.9em;font-weight:500;transition:all .2s;white-space:nowrap}}
.tab:hover{{color:#c9d1d9}}
.tab.active{{color:#58a6ff;border-bottom-color:#58a6ff;background:rgba(88,166,255,.06)}}
.tab-content{{display:none;padding:28px 32px;max-width:1600px;margin:0 auto}}
.tab-content.active{{display:block}}

/* METRIC CARDS */
.metrics-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:28px}}
.metric-card{{background:linear-gradient(180deg,#161b22 0%,#0f141a 100%);border:1px solid #21262d;border-radius:12px;padding:16px;transition:transform .2s}}
.metric-card:hover{{transform:translateY(-2px);border-color:#30363d}}
.metric-label{{color:#8b949e;font-size:.78em;font-weight:600;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}}
.metric-value{{font-size:1.7em;font-weight:700;line-height:1}}
.metric-value.green{{color:#3fb950}}
.metric-value.red{{color:#f85149}}
.metric-value.blue{{color:#58a6ff}}
.metric-value.yellow{{color:#e3b341}}
.metric-sub{{color:#8b949e;font-size:.78em;margin-top:5px}}

/* CHARTS GRID */
.charts-row{{display:grid;grid-template-columns:2fr 1fr;gap:20px;margin-bottom:28px}}
.chart-box{{background:#161b22;border:1px solid #21262d;border-radius:12px;padding:18px}}
.chart-title{{color:#79c0ff;font-size:.92em;font-weight:600;margin-bottom:14px;display:flex;align-items:center;gap:8px}}
.charts-row2{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;margin-bottom:28px}}

/* HEATMAP */
.heatmap-container{{overflow-x:auto;border-radius:10px;border:1px solid #21262d}}
.heatmap-table{{border-collapse:collapse;width:100%;font-size:.78em}}
.heatmap-table th{{background:#161b22;color:#8b949e;padding:8px 12px;text-align:center;font-weight:600;border:1px solid #21262d;position:sticky;top:0}}
.heatmap-table td{{padding:8px 12px;text-align:center;border:1px solid #21262d;font-weight:600;min-width:70px}}
.heatmap-table .row-label{{text-align:left;color:#c9d1d9;font-weight:600;background:#161b22;position:sticky;left:0;z-index:2}}

/* TABLES */
.data-table-wrap{{overflow-x:auto;border:1px solid #21262d;border-radius:10px}}
.data-table{{border-collapse:collapse;width:100%;font-size:.82em}}
.data-table th{{background:#161b22;color:#8b949e;padding:10px 12px;text-align:left;font-weight:600;border-bottom:1px solid #21262d;white-space:nowrap;position:sticky;top:0;z-index:5}}
.data-table td{{padding:9px 12px;border-bottom:1px solid #161b22;white-space:nowrap}}
.data-table tr:hover td{{background:rgba(88,166,255,.04)}}
.data-table tr:last-child td{{border-bottom:none}}
.tag{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.75em;font-weight:600}}
.tag-vcp{{background:#1e1b4b;color:#a5b4fc}}
.tag-rexp{{background:#1a2a0a;color:#86efac}}
.tag-mr{{background:#1a2a3a;color:#7dd3fc}}
.tag-bp{{background:#2a1a2a;color:#d8b4fe}}
.rpl{{color:#3fb950;font-weight:700}}
.rmi{{color:#f85149;font-weight:700}}
.rat-a+{{color:#ffd700}}
.rat-a{{color:#a5b4fc}}
.rat-b{{color:#7dd3fc}}

/* SEARCH / FILTERS */
.controls{{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:20px;padding:14px;background:#161b22;border-radius:10px;border:1px solid #21262d}}
.search-box,.sel{{padding:8px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:.85em;min-width:160px}}
.btn{{padding:7px 14px;border:1px solid #30363d;border-radius:6px;background:transparent;color:#58a6ff;cursor:pointer;font-size:.84em;transition:all .2s}}
.btn:hover{{background:#1f6feb33}}
.btn.active{{background:#1f6feb;border-color:#58a6ff}}
.info-banner{{background:linear-gradient(135deg,#1a2433,#1a1a2e);border:1px solid #30363d;border-radius:10px;padding:14px 18px;margin-bottom:20px;font-size:.85em;color:#8b949e;line-height:1.6}}
.info-banner strong{{color:#79c0ff}}
.section-title{{color:#c9d1d9;font-size:1.05em;font-weight:700;margin:24px 0 14px;display:flex;align-items:center;gap:10px}}
.section-title::after{{content:"";flex:1;height:1px;background:#21262d}}
.macro-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin-bottom:24px}}
.macro-card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px;transition:all .2s}}
.macro-card:hover{{border-color:#30363d;transform:translateY(-1px)}}
.macro-card .ev-type{{font-size:.72em;font-weight:700;padding:2px 8px;border-radius:4px;display:inline-block;margin-bottom:8px}}
.ev-RBI_RATE{{background:#1a2a3a;color:#58a6ff}}
.ev-FED_RATE{{background:#2a1a3a;color:#d2a8ff}}
.ev-BUDGET{{background:#1a2a1a;color:#3fb950}}
.ev-ELECTION{{background:#2a1a1a;color:#ffa657}}
.ev-GLOBAL{{background:#2a2a1a;color:#e3b341}}
.ev-MARKET{{background:#1a2a2a;color:#79c0ff}}
.ev-EARNING{{background:#2a1a2a;color:#f0883e}}
.macro-card .ev-label{{color:#c9d1d9;font-size:.88em;font-weight:600;margin-bottom:6px}}
.macro-card .ev-date{{color:#8b949e;font-size:.76em;margin-bottom:10px}}
.macro-card .ev-stats{{display:flex;gap:16px}}
.ev-stat-val{{font-size:1.1em;font-weight:700}}
.regime-POS{{color:#3fb950}}
.regime-NEG{{color:#f85149}}
.regime-NEU{{color:#e3b341}}
.pos-size-note{{background:#1a2433;border-left:3px solid #58a6ff;padding:10px 14px;border-radius:0 6px 6px 0;font-size:.82em;color:#8b949e;margin-bottom:20px}}
</style>
</head>
<body>

<div class="header">
  <h1>&#128200; 3-Year Breakout Backtest Dashboard
    <span class="badge badge-green">India NSE</span>
    <span class="badge badge-blue">Apr 2023 - Mar 2026</span>
    <span class="badge badge-orange">&#10003; {n:,} Trades</span>
  </h1>
  <div class="sub">Generated {generated_at} &nbsp;|&nbsp; Account &#8377;{account_size/100000:.1f}L &nbsp;|&nbsp; Risk 1% per trade &nbsp;|&nbsp; Max Hold {MAX_HOLD} bars</div>
</div>

<div class="tabs">
  <div class="tab active" onclick="showTab('perf',this)">&#128201; Performance</div>
  <div class="tab" onclick="showTab('plans',this)">&#127919; Trade Plans</div>
  <div class="tab" onclick="showTab('sector',this)">&#127968; Sector Analysis</div>
  <div class="tab" onclick="showTab('macro',this)">&#127758; Macro Impact</div>
  <div class="tab" onclick="showTab('bt_trades',this)">&#128218; Trade Log</div>
</div>

<!-- TAB 1: PERFORMANCE -->
<div id="tab-perf" class="tab-content active">
  <div class="metrics-grid">
    <div class="metric-card">
      <div class="metric-label">Total Trades</div>
      <div class="metric-value blue">{n:,}</div>
      <div class="metric-sub">Backtest 2023-2026</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Win Rate</div>
      <div class="metric-value {'green' if wr >= 50 else 'red'}">{wr:.1f}%</div>
      <div class="metric-sub">{metrics.get('wins',0)} wins / {metrics.get('losses',0)} losses</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Avg R-Multiple</div>
      <div class="metric-value {'green' if avg_r > 0 else 'red'}">{avg_r:.3f}R</div>
      <div class="metric-sub">Per completed trade</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Total R</div>
      <div class="metric-value {'green' if total_r > 0 else 'red'}">{total_r:.1f}R</div>
      <div class="metric-sub">Cumulative R-multiples</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Profit Factor</div>
      <div class="metric-value {'green' if pf > 1.5 else 'yellow' if pf > 1 else 'red'}">{pf:.2f}</div>
      <div class="metric-sub">Gross Profit / Loss</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Max Drawdown</div>
      <div class="metric-value red">{max_dd:.2f}R</div>
      <div class="metric-sub">Peak-to-trough R</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">T1 Hit Rate</div>
      <div class="metric-value blue">{metrics.get('t1HitRate',0):.1f}%</div>
      <div class="metric-sub">1.5R target reached</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">T2 Hit Rate</div>
      <div class="metric-value blue">{metrics.get('t2HitRate',0):.1f}%</div>
      <div class="metric-sub">2.5R target reached</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Avg Hold</div>
      <div class="metric-value yellow">{metrics.get('avgHold',0):.1f}d</div>
      <div class="metric-sub">Trading days in trade</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Avg MAE</div>
      <div class="metric-value red">-{metrics.get('avgMae',0):.1f}%</div>
      <div class="metric-sub">Avg adverse excursion</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Avg MFE</div>
      <div class="metric-value green">+{metrics.get('avgMfe',0):.1f}%</div>
      <div class="metric-sub">Avg favorable excursion</div>
    </div>
  </div>

  <div class="charts-row">
    <div class="chart-box">
      <div class="chart-title">&#128200; Cumulative R-Multiple Equity Curve (All Trades)</div>
      <canvas id="equityChart" height="80"></canvas>
    </div>
    <div class="chart-box">
      <div class="chart-title">&#9685; Exit Type Distribution</div>
      <canvas id="exitChart" height="80"></canvas>
    </div>
  </div>

  <div class="charts-row2">
    <div class="chart-box">
      <div class="chart-title">&#128202; Monthly Net R</div>
      <canvas id="monthlyChart" height="160"></canvas>
    </div>
    <div class="chart-box">
      <div class="chart-title">&#127941; Win Rate by Setup</div>
      <canvas id="setupChart" height="160"></canvas>
    </div>
    <div class="chart-box">
      <div class="chart-title">&#127941; Avg R by Setup</div>
      <canvas id="setupRChart" height="160"></canvas>
    </div>
  </div>

  <div class="section-title">&#128202; Performance by Setup Type</div>
  <div class="data-table-wrap" style="margin-bottom:24px">
    <table class="data-table">
      <thead><tr>
        <th>Setup</th><th>Trades</th><th>Win Rate</th><th>Avg R</th><th>Total R</th>
      </tr></thead>
      <tbody>
        {''.join(f'''<tr>
          <td><span class="tag {'tag-vcp' if k=='VCP' else 'tag-rexp' if k=='RANGE_EXPANSION' else 'tag-mr'}">{k}</span></td>
          <td>{v["trades"]}</td>
          <td class="{'rpl' if v['winRate']>=50 else 'rmi'}">{v["winRate"]:.1f}%</td>
          <td class="{'rpl' if v['avgR']>0 else 'rmi'}">{v["avgR"]:.3f}R</td>
          <td class="{'rpl' if v['totalR']>0 else 'rmi'}">{v["totalR"]:.1f}R</td>
        </tr>''' for k,v in by_setup.items())}
      </tbody>
    </table>
  </div>

  <div class="section-title">&#11088; Performance by Rating</div>
  <div class="data-table-wrap" style="margin-bottom:24px">
    <table class="data-table">
      <thead><tr>
        <th>Rating</th><th>Trades</th><th>Win Rate</th><th>Avg R</th><th>Total R</th>
      </tr></thead>
      <tbody>
        {''.join(f'''<tr>
          <td class="rat-{k.lower()}">{k}</td>
          <td>{v["trades"]}</td>
          <td class="{'rpl' if v['winRate']>=50 else 'rmi'}">{v["winRate"]:.1f}%</td>
          <td class="{'rpl' if v['avgR']>0 else 'rmi'}">{v["avgR"]:.3f}R</td>
          <td class="{'rpl' if v['totalR']>0 else 'rmi'}">{v["totalR"]:.1f}R</td>
        </tr>''' for k,v in sorted(by_rating.items()))}
      </tbody>
    </table>
  </div>

  {sector_perf_html}
</div>

<!-- TAB 2: TRADE PLANS -->
<div id="tab-plans" class="tab-content">
  <div class="info-banner">
    <strong>&#127919; Current Signal Trade Plans</strong> &mdash; All active breakout & VCP signals from the latest scan.
    Entry zone, pivot, stop-loss and targets (T1/T2/T3) are computed using ATR-based risk management.
    Position size is calculated for <strong>1% risk</strong> of &#8377;{account_size/100000:.1f}L account.
  </div>
  <div class="pos-size-note">
    <strong>Position Sizing Formula:</strong>
    Shares = floor(Account &times; 1% / (Entry &minus; Stop)) &nbsp;|&nbsp;
    <strong>T1</strong> = Entry + 1.5&times;Risk &nbsp;|&nbsp;
    <strong>T2</strong> = Entry + 2.5&times;Risk &nbsp;|&nbsp;
    <strong>T3</strong> = Entry + 4.0&times;Risk &nbsp;|&nbsp;
    Stop-loss = 10-bar swing low (max 4% below entry)
  </div>
  <div class="controls">
    <input class="search-box" id="planSearch" placeholder="&#128269; Search symbol..." oninput="filterPlans()">
    <select class="sel" id="planSetup" onchange="filterPlans()">
      <option value="">All Setups</option>
      <option value="RANGE_EXPANSION">Range Expansion</option>
      <option value="VCP">VCP</option>
      <option value="MEAN_REVERSION">Mean Reversion</option>
      <option value="BREAKOUT_PULLBACK">Breakout Pullback</option>
    </select>
    <select class="sel" id="planRating" onchange="filterPlans()">
      <option value="">All Ratings</option>
      <option value="A+">A+ Only</option>
      <option value="A">A &amp; Above</option>
    </select>
    <button class="btn" onclick="exportPlansCSV()">&#8659; Export CSV</button>
  </div>
  {trade_plans_html}
</div>

<!-- TAB 3: SECTOR ANALYSIS -->
<div id="tab-sector" class="tab-content">
  <div class="info-banner">
    <strong>&#127968; Sector-wise Returns Analysis</strong> &mdash; Quarterly and monthly average returns computed
    from price data of all stocks in each sector. Green = positive, Red = negative.
    Darker = stronger magnitude.
  </div>

  <div class="section-title">&#128197; Quarterly Returns by Sector (%)</div>
  {sector_quarterly_html}

  <div class="section-title" style="margin-top:32px">&#128200; Monthly Returns by Sector (%)</div>
  {sector_monthly_html}

  <div class="section-title" style="margin-top:32px">&#127942; Sector Backtest Performance (R-Multiple)</div>
  {sector_perf_html}
</div>

<!-- TAB 4: MACRO IMPACT -->
<div id="tab-macro" class="tab-content">
  <div class="info-banner">
    <strong>&#127758; Macro Event Impact on Breakout Trades</strong> &mdash; For each macro event, we analyse
    the win rate and average R-multiple of breakout signals detected within &plusmn;30 days.
    This shows how RBI policy, Union Budget, elections and global events affect breakout performance.
  </div>
  <div class="charts-row2">
    <div class="chart-box" style="grid-column:span 2">
      <div class="chart-title">&#128202; Win Rate Near Each Macro Event (trades within 30 days)</div>
      <canvas id="macroWRChart" height="120"></canvas>
    </div>
    <div class="chart-box">
      <div class="chart-title">&#9997; Macro Type Impact Summary</div>
      <canvas id="macroTypeChart" height="120"></canvas>
    </div>
  </div>
  <div class="section-title">&#128203; All Macro Events Analysis</div>
  {macro_html}
</div>

<!-- TAB 5: TRADE LOG -->
<div id="tab-bt_trades" class="tab-content">
  <div class="info-banner">
    <strong>&#128218; Full Backtest Trade Log</strong> &mdash; Historical trades simulated over 3 years.
    Each row = one completed simulated trade with entry/exit details and R-multiple outcome.
  </div>
  <div class="controls">
    <input class="search-box" id="btSearch" placeholder="&#128269; Search symbol / sector..." oninput="filterBT()">
    <select class="sel" id="btSetup" onchange="filterBT()">
      <option value="">All Setups</option>
      <option value="RANGE_EXPANSION">Range Expansion</option>
      <option value="VCP">VCP</option>
    </select>
    <select class="sel" id="btOutcome" onchange="filterBT()">
      <option value="">All Outcomes</option>
      <option value="win">Winners (R&gt;0)</option>
      <option value="loss">Losers (R&lt;0)</option>
    </select>
    <button class="btn" onclick="exportBTCSV()">&#8659; Export CSV</button>
  </div>
  {bt_trades_html}
</div>

<script>
// ── Tab switching ────────────────────────────────────────────────────────────
function showTab(id, el) {{
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  el.classList.add('active');
  if(id==='perf' && !window._chartsBuilt) buildCharts();
  if(id==='macro' && !window._macroBuilt) buildMacroCharts();
}}

// ── Chart data ──────────────────────────────────────────────────────────────
const cumR       = {cum_r_json};
const monthlyK   = {monthly_keys};
const monthlyV   = {monthly_vals};
const exitLabels = {exit_labels};
const exitVals   = {exit_vals};
const setupLabels= {setup_labels};
const setupWR    = {setup_wr};
const setupAvgR  = {setup_avgr};

const macroData  = {macro_data_js};

window._chartsBuilt = false;
window._macroBuilt  = false;

const CHART_OPTS = {{
  responsive: true,
  plugins: {{ legend: {{ labels: {{ color:'#8b949e', font:{{size:11}} }} }} }},
  scales: {{
    x: {{ ticks:{{color:'#8b949e',font:{{size:10}}}}, grid:{{color:'#21262d'}} }},
    y: {{ ticks:{{color:'#8b949e',font:{{size:10}}}}, grid:{{color:'#21262d'}} }}
  }}
}};

function buildCharts() {{
  window._chartsBuilt = true;

  // Equity curve
  new Chart(document.getElementById('equityChart'), {{
    type:'line',
    data:{{
      labels: cumR.map((_,i)=>i+1),
      datasets:[{{
        label:'Cumulative R',
        data: cumR,
        borderColor:'#58a6ff',
        backgroundColor:'rgba(88,166,255,0.08)',
        borderWidth:1.5,
        fill:true,
        pointRadius:0,
        tension:0.1
      }}]
    }},
    options:{{...CHART_OPTS,
      plugins:{{legend:{{display:false}}}},
      scales:{{
        x:{{display:true,ticks:{{color:'#8b949e',maxTicksLimit:10}},grid:{{color:'#21262d'}}}},
        y:{{ticks:{{color:'#8b949e'}},grid:{{color:'#21262d'}}}}
      }}
    }}
  }});

  // Exit pie
  new Chart(document.getElementById('exitChart'), {{
    type:'doughnut',
    data:{{
      labels: exitLabels,
      datasets:[{{
        data: exitVals,
        backgroundColor:['#3fb950','#f85149','#e3b341','#58a6ff','#d2a8ff','#79c0ff'],
        borderColor:'#0d1117',
        borderWidth:2
      }}]
    }},
    options:{{
      responsive:true,
      plugins:{{
        legend:{{labels:{{color:'#8b949e',font:{{size:10}}}}}},
        tooltip:{{callbacks:{{label:ctx=>ctx.label+': '+ctx.parsed+' trades'}}}}
      }}
    }}
  }});

  // Monthly bar
  const mColors = monthlyV.map(v=>v>=0?'rgba(63,185,80,0.7)':'rgba(248,81,73,0.7)');
  new Chart(document.getElementById('monthlyChart'), {{
    type:'bar',
    data:{{
      labels: monthlyK.map(k=>k.slice(2)),
      datasets:[{{
        label:'Net R',
        data: monthlyV,
        backgroundColor: mColors,
        borderRadius:2
      }}]
    }},
    options:{{...CHART_OPTS,
      plugins:{{legend:{{display:false}}}},
      scales:{{
        x:{{ticks:{{color:'#8b949e',maxTicksLimit:18,font:{{size:9}}}},grid:{{color:'#21262d'}}}},
        y:{{ticks:{{color:'#8b949e'}},grid:{{color:'#21262d'}}}}
      }}
    }}
  }});

  // Setup win rate
  new Chart(document.getElementById('setupChart'), {{
    type:'bar',
    data:{{
      labels: setupLabels.map(l=>l.replace('_',' ')),
      datasets:[{{
        label:'Win Rate %',
        data: setupWR,
        backgroundColor:'rgba(88,166,255,0.6)',
        borderRadius:4
      }}]
    }},
    options:{{...CHART_OPTS,
      plugins:{{legend:{{display:false}}}},
      scales:{{
        x:{{ticks:{{color:'#8b949e',font:{{size:10}}}},grid:{{color:'#21262d'}}}},
        y:{{min:0,max:100,ticks:{{color:'#8b949e',callback:v=>v+'%'}},grid:{{color:'#21262d'}}}}
      }}
    }}
  }});

  // Setup avg R
  const rColors = setupAvgR.map(v=>v>=0?'rgba(63,185,80,0.6)':'rgba(248,81,73,0.6)');
  new Chart(document.getElementById('setupRChart'), {{
    type:'bar',
    data:{{
      labels: setupLabels.map(l=>l.replace('_',' ')),
      datasets:[{{
        label:'Avg R',
        data: setupAvgR,
        backgroundColor: rColors,
        borderRadius:4
      }}]
    }},
    options:{{...CHART_OPTS,
      plugins:{{legend:{{display:false}}}},
      scales:{{
        x:{{ticks:{{color:'#8b949e',font:{{size:10}}}},grid:{{color:'#21262d'}}}},
        y:{{ticks:{{color:'#8b949e'}},grid:{{color:'#21262d'}}}}
      }}
    }}
  }});
}}

function buildMacroCharts() {{
  window._macroBuilt = true;
  const recentMacro = macroData.filter(m=>m.nearbyTrades>0||true).slice(0,20);
  const wrColors = recentMacro.map(m=>m.regime==='POSITIVE'?'rgba(63,185,80,0.6)':m.regime==='NEGATIVE'?'rgba(248,81,73,0.6)':'rgba(227,179,65,0.6)');

  new Chart(document.getElementById('macroWRChart'), {{
    type:'bar',
    data:{{
      labels: recentMacro.map(m=>m.date.slice(2,10)+' '+m.label.slice(0,20)),
      datasets:[{{
        label:'Win Rate %',
        data: recentMacro.map(m=>m.winRate),
        backgroundColor: wrColors,
        borderRadius:3
      }}]
    }},
    options:{{...CHART_OPTS,
      plugins:{{legend:{{display:false}}}},
      scales:{{
        x:{{ticks:{{color:'#8b949e',maxRotation:45,font:{{size:9}}}},grid:{{color:'#21262d'}}}},
        y:{{min:0,max:100,ticks:{{color:'#8b949e',callback:v=>v+'%'}},grid:{{color:'#21262d'}}}}
      }}
    }}
  }});

  // Type summary
  const typeMap={{}};
  macroData.forEach(m=>{{
    if(!typeMap[m.type]) typeMap[m.type]={{wr:[],r:[]}};
    if(m.winRate>0) typeMap[m.type].wr.push(m.winRate);
    if(m.avgR!==0) typeMap[m.type].r.push(m.avgR);
  }});
  const tLabels=Object.keys(typeMap);
  const tWR=tLabels.map(k=>typeMap[k].wr.length?+(typeMap[k].wr.reduce((a,b)=>a+b,0)/typeMap[k].wr.length).toFixed(1):0);
  new Chart(document.getElementById('macroTypeChart'), {{
    type:'bar',
    data:{{
      labels:tLabels,
      datasets:[{{
        label:'Avg Win Rate %',
        data:tWR,
        backgroundColor:'rgba(88,166,255,0.6)',
        borderRadius:4
      }}]
    }},
    options:{{...CHART_OPTS,
      plugins:{{legend:{{display:false}}}},
      scales:{{
        x:{{ticks:{{color:'#8b949e',font:{{size:10}}}},grid:{{color:'#21262d'}}}},
        y:{{min:0,max:100,ticks:{{color:'#8b949e',callback:v=>v+'%'}},grid:{{color:'#21262d'}}}}
      }}
    }}
  }});
}}

// Init charts on first load
document.addEventListener('DOMContentLoaded', ()=>buildCharts());

// ── Table filters ────────────────────────────────────────────────────────────
function filterPlans() {{
  const s=document.getElementById('planSearch').value.toLowerCase();
  const setup=document.getElementById('planSetup').value;
  const rating=document.getElementById('planRating').value;
  document.querySelectorAll('#planTable tr[data-symbol]').forEach(row=>{{
    const sym=row.dataset.symbol||'';
    const st=row.dataset.setup||'';
    const rt=row.dataset.rating||'';
    let show = sym.toLowerCase().includes(s) || (row.dataset.sector||'').toLowerCase().includes(s);
    if(setup && st!==setup) show=false;
    if(rating==='A+' && rt!=='A+') show=false;
    if(rating==='A' && rt!=='A+' && rt!=='A') show=false;
    row.style.display=show?'':'none';
  }});
}}

function filterBT() {{
  const s=document.getElementById('btSearch').value.toLowerCase();
  const setup=document.getElementById('btSetup').value;
  const outcome=document.getElementById('btOutcome').value;
  document.querySelectorAll('#btTable tr[data-r]').forEach(row=>{{
    const sym=row.dataset.symbol||'';
    const st=row.dataset.setup||'';
    const r=parseFloat(row.dataset.r||0);
    let show = sym.toLowerCase().includes(s);
    if(setup && st!==setup) show=false;
    if(outcome==='win' && r<=0) show=false;
    if(outcome==='loss' && r>0) show=false;
    row.style.display=show?'':'none';
  }});
}}

const _allTradesData = {trades_json_export};

function exportPlansCSV() {{
  const rows=[['Symbol','Setup','Rating','Entry','Pivot','Stop','T1','T2','T3','Shares','Sector']];
  document.querySelectorAll('#planTable tr[data-symbol]').forEach(row=>{{
    if(row.style.display==='none') return;
    const cells=[...row.querySelectorAll('td')].map(td=>td.innerText.replace(/,/g,' '));
    rows.push(cells);
  }});
  downloadCSV(rows,'trade_plans.csv');
}}

function exportBTCSV() {{
  const header=Object.keys(_allTradesData[0]||{{}});
  const rows=[header,..._allTradesData.map(t=>header.map(k=>t[k]??''))];
  downloadCSV(rows,'backtest_trades.csv');
}}

function downloadCSV(rows,filename) {{
  const csv=rows.map(r=>r.map(v=>'"'+String(v).replace(/"/g,'""')+'"').join(',')).join('\\n');
  const a=document.createElement('a');
  a.href='data:text/csv;charset=utf-8,'+encodeURIComponent(csv);
  a.download=filename;
  a.click();
}}
</script>
</body>
</html>"""

# ── Sub-HTML builders ─────────────────────────────────────────────────────────

def _build_equity_svg(cum_r):
    return ""  # SVG replaced by Chart.js

def _build_monthly_heatmap(monthly_r):
    return ""  # replaced by chart

def _build_trade_plans_html(signals, account_size):
    if not signals:
        return "<p style='color:#8b949e;padding:20px'>No current signals found.</p>"
    rows = []
    for s in signals:
        sym    = s.get("symbol","")
        setup  = s.get("setup","")
        rating = s.get("rating","")
        entry  = _f(s.get("entry") or s.get("close"))
        pivot  = _f(s.get("pivot"))
        sl     = _f(s.get("sl"))
        t1     = _f(s.get("T1"))
        t2     = _f(s.get("T2"))
        t3     = _f(s.get("T3"))
        shares = s.get("shares","") or (int(account_size * 0.01 / max(entry - sl, 0.01)) if sl else "")
        score  = s.get("score","")
        sector = _get_sector(sym)
        regime = s.get("regimeState","")
        rs3m   = _f(s.get("rs3m"))
        window = s.get("window","")

        risk = round(entry - sl, 2) if sl else 0
        rr = round((t1 - entry) / risk, 1) if risk > 0 and t1 else 0

        setup_class = {"VCP":"tag-vcp","RANGE_EXPANSION":"tag-rexp","MEAN_REVERSION":"tag-mr",
                       "BREAKOUT_PULLBACK":"tag-bp"}.get(setup, "tag-vcp")
        rating_class = "rat-a+" if rating=="A+" else "rat-a" if rating=="A" else "rat-b"

        rows.append(f'''<tr data-symbol="{sym}" data-setup="{setup}" data-rating="{rating}" data-sector="{sector}">
          <td style="font-weight:700;color:#c9d1d9">{sym}</td>
          <td>{sector}</td>
          <td><span class="tag {setup_class}">{setup.replace("_"," ")}</span></td>
          <td class="{rating_class}">{rating}</td>
          <td style="font-weight:700;color:#79c0ff">{entry:.2f}</td>
          <td>{pivot:.2f}</td>
          <td class="rmi">{sl:.2f}</td>
          <td class="rpl">{t1:.2f}</td>
          <td class="rpl">{t2:.2f}</td>
          <td class="rpl">{t3:.2f}</td>
          <td style="color:#e3b341">{shares}</td>
          <td style="color:#8b949e">{rr:.1f}R</td>
          <td style="color:#8b949e">{risk:.2f}</td>
          <td style="color:{'#f85149' if 'UNFAV' in regime else '#3fb950' if 'FAV' in regime else '#e3b341'}">{regime}</td>
          <td style="color:{'#3fb950' if rs3m>0 else '#f85149'}">{rs3m:+.1f}%</td>
          <td style="color:#8b949e">{window}</td>
          <td style="color:#8b949e">{score}</td>
        </tr>''')

    return f'''<div class="data-table-wrap">
<table class="data-table" id="planTable">
<thead><tr>
  <th>Symbol</th><th>Sector</th><th>Setup</th><th>Rating</th>
  <th>Entry</th><th>Pivot</th><th>Stop</th>
  <th>T1 (+1.5R)</th><th>T2 (+2.5R)</th><th>T3 (+4R)</th>
  <th>Shares</th><th>R:R</th><th>Risk/Share</th>
  <th>Regime</th><th>RS 3M</th><th>Window</th><th>Score</th>
</tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</div>'''

def _build_bt_trades_html(trades):
    if not trades:
        return "<p style='color:#8b949e;padding:20px'>No backtest trades found.</p>"
    rows = []
    for t in trades:
        r = t["rMultiple"]
        r_class = "rpl" if r > 0 else "rmi"
        exit_colors = {
            "T3":"#3fb950","T2":"#7ee787","T1":"#79c0ff",
            "STOP":"#f85149","MAX_HOLD":"#e3b341",
            "TRAIL_STOP":"#58a6ff",
            "EMA10_BREAK":"#d2a8ff",      # purple — 10 EMA structural exit
            "CANDLE_LOW_BREAK":"#ffa657", # orange — breakout candle low broken
            "BASE_BREAK":"#ff7b72",       # red-orange — base structure violated
        }
        exit_col = exit_colors.get(t["exitReason"], "#8b949e")
        setup_class = {"VCP":"tag-vcp","RANGE_EXPANSION":"tag-rexp"}.get(t.get("setup",""),"tag-vcp")
        rows.append(f'''<tr data-symbol="{t['symbol']}" data-setup="{t.get('setup','')}" data-r="{r}">
          <td style="font-weight:700;color:#c9d1d9">{t['symbol']}</td>
          <td><span class="tag {setup_class}">{t.get('setup','').replace('_',' ')}</span></td>
          <td>{t.get('sector','')}</td>
          <td style="color:#8b949e">{t['date']}</td>
          <td>{t['entry']:.2f}</td>
          <td class="rmi">{t['sl']:.2f}</td>
          <td class="rpl">{t['T1']:.2f}</td>
          <td class="rpl">{t['T2']:.2f}</td>
          <td class="rpl">{t['T3']:.2f}</td>
          <td style="color:#8b949e">{t.get('exitDate','')}</td>
          <td>{t['exitPrice']:.2f}</td>
          <td style="color:{exit_col}">{t['exitReason']}</td>
          <td class="{r_class}">{r:+.3f}R</td>
          <td style="color:#8b949e">{t['holdBars']}d</td>
          <td style="color:{'#3fb950' if t['hitT1'] else '#8b949e'}">{'&#10003;' if t['hitT1'] else ''}</td>
          <td style="color:{'#3fb950' if t['hitT2'] else '#8b949e'}">{'&#10003;' if t['hitT2'] else ''}</td>
          <td style="color:{'#3fb950' if t['hitT3'] else '#8b949e'}">{'&#10003;' if t['hitT3'] else ''}</td>
          <td class="rmi">{t['mae']:.1f}%</td>
          <td class="rpl">{t['mfe']:.1f}%</td>
        </tr>''')

    return f'''<div class="data-table-wrap">
<table class="data-table" id="btTable">
<thead><tr>
  <th>Symbol</th><th>Setup</th><th>Sector</th><th>Entry Date</th>
  <th>Entry</th><th>Stop</th><th>T1</th><th>T2</th><th>T3</th>
  <th>Exit Date</th><th>Exit Price</th><th>Exit Reason</th>
  <th>R-Multiple</th><th>Hold</th><th>T1</th><th>T2</th><th>T3</th>
  <th>MAE</th><th>MFE</th>
</tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</div>'''

def _build_sector_quarterly_html(sec_quarterly: dict) -> str:
    if not sec_quarterly:
        return "<p style='color:#8b949e'>No sector data available.</p>"
    all_quarters = sorted({q for rets in sec_quarterly.values() for q in rets.keys()})
    sectors = sorted(sec_quarterly.keys())
    rows = []
    for sec in sectors:
        cells = [f'<td class="row-label">{sec}</td>']
        for q in all_quarters:
            val = sec_quarterly[sec].get(q)
            if val is None:
                cells.append('<td style="color:#444">—</td>')
            else:
                bg = heatmap_color(val, -15, 15)
                txt_color = "#f0f6fc" if abs(val) > 3 else "#c9d1d9"
                cells.append(f'<td style="background:{bg};color:{txt_color}">{val:+.1f}%</td>')
        rows.append(f'<tr>{"".join(cells)}</tr>')
    ths = '<th class="row-label">Sector</th>' + ''.join(f'<th>{q}</th>' for q in all_quarters)
    return f'''<div class="heatmap-container">
<table class="heatmap-table">
<thead><tr>{ths}</tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</div>'''

def _build_sector_monthly_html(sec_monthly: dict) -> str:
    if not sec_monthly:
        return "<p style='color:#8b949e'>No sector data available.</p>"
    all_months = sorted({m for rets in sec_monthly.values() for m in rets.keys()})
    # Show last 24 months max
    all_months = all_months[-24:]
    sectors = sorted(sec_monthly.keys())
    rows = []
    for sec in sectors:
        cells = [f'<td class="row-label">{sec}</td>']
        for m in all_months:
            val = sec_monthly[sec].get(m)
            if val is None:
                cells.append('<td style="color:#444">—</td>')
            else:
                bg = heatmap_color(val, -10, 10)
                txt_color = "#f0f6fc" if abs(val) > 2 else "#c9d1d9"
                cells.append(f'<td style="background:{bg};color:{txt_color}">{val:+.1f}%</td>')
        rows.append(f'<tr>{"".join(cells)}</tr>')
    ths = '<th class="row-label">Sector</th>' + ''.join(f'<th>{m[2:]}</th>' for m in all_months)
    return f'''<div class="heatmap-container">
<table class="heatmap-table">
<thead><tr>{ths}</tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</div>'''

def _build_sector_perf_html(by_sector: dict) -> str:
    if not by_sector:
        return ""
    rows = []
    sorted_sectors = sorted(by_sector.items(), key=lambda x: x[1]["totalR"], reverse=True)
    for sec, v in sorted_sectors:
        rows.append(f'''<tr>
          <td style="font-weight:600;color:#c9d1d9">{sec}</td>
          <td>{v["trades"]}</td>
          <td class="{'rpl' if v['winRate']>=50 else 'rmi'}">{v["winRate"]:.1f}%</td>
          <td class="{'rpl' if v['avgR']>0 else 'rmi'}">{v["avgR"]:.3f}R</td>
          <td class="{'rpl' if v['totalR']>0 else 'rmi'}">{v["totalR"]:.1f}R</td>
        </tr>''')
    return f'''<div class="data-table-wrap">
<table class="data-table">
<thead><tr>
  <th>Sector</th><th>Trades</th><th>Win Rate</th><th>Avg R</th><th>Total R</th>
</tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</div>'''

def _build_macro_html(macro_impact: list) -> str:
    if not macro_impact:
        return "<p style='color:#8b949e'>No macro data.</p>"
    cards = []
    type_colors = {
        "RBI_RATE":"ev-RBI_RATE","FED_RATE":"ev-FED_RATE","BUDGET":"ev-BUDGET",
        "ELECTION":"ev-ELECTION","GLOBAL":"ev-GLOBAL","MARKET":"ev-MARKET","EARNING":"ev-EARNING"
    }
    for m in macro_impact:
        wr = m.get("winRate", 0)
        avg_r = m.get("avgR", 0)
        nearby = m.get("nearbyTrades", 0)
        regime = m.get("regime","NEUTRAL")
        regime_cls = "regime-POS" if regime=="POSITIVE" else "regime-NEG" if regime=="NEGATIVE" else "regime-NEU"
        type_cls = type_colors.get(m.get("type",""), "ev-GLOBAL")
        cards.append(f'''<div class="macro-card">
          <div class="ev-type {type_cls}">{m.get("type","")}</div>
          <div class="ev-label">{m.get("label","")}</div>
          <div class="ev-date">&#128197; {m.get("date","")} &nbsp; <span class="{regime_cls}">&#11044; {regime}</span></div>
          <div class="ev-stats">
            <div>
              <div class="metric-label">Nearby Trades</div>
              <div class="ev-stat-val {'blue'}" style="color:#58a6ff">{nearby}</div>
            </div>
            <div>
              <div class="metric-label">Win Rate</div>
              <div class="ev-stat-val" style="color:{'#3fb950' if wr>=50 else '#f85149'}">{wr:.0f}%</div>
            </div>
            <div>
              <div class="metric-label">Avg R</div>
              <div class="ev-stat-val" style="color:{'#3fb950' if avg_r>0 else '#f85149'}">{avg_r:+.2f}R</div>
            </div>
          </div>
        </div>''')
    return f'<div class="macro-grid">{"".join(cards)}</div>'

# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="3-Year Backtest Dashboard Generator")
    p.add_argument("--max-stocks", type=int, default=None)
    p.add_argument("--account-size", type=float, default=ACCOUNT_SIZE)
    p.add_argument("--output", default=str(OUTPUT_DIR / "backtest_3yr_dashboard.html"))
    return p.parse_args()

def main():
    args = parse_args()
    t0 = time.time()

    print("=" * 60)
    print("  3-Year Breakout Backtest Dashboard Generator")
    print("=" * 60)
    print(f"Account: Rs{args.account_size:,.0f} | Risk: 1% | Max Hold: {MAX_HOLD} bars")

    # Load all bars
    print("\n[1/5] Loading cached OHLCV data...")
    all_bars = load_all_india_bars(args.max_stocks)
    print(f"      Loaded {len(all_bars)} stocks")

    # Run backtest
    print("\n[2/5] Running 3-year breakout backtest...")
    trades, sector_bars = run_backtest(all_bars, args.account_size)

    # Compute metrics
    print("\n[3/5] Computing performance metrics...")
    metrics = compute_metrics(trades)
    print(f"      Trades={metrics.get('trades',0)}, WinRate={metrics.get('winRate',0):.1f}%, TotalR={metrics.get('totalR',0):.1f}R")

    # Compute sector returns
    print("\n[4/5] Computing sector returns...")
    sector_data = compute_sector_returns(sector_bars)

    # Macro impact
    macro_impact = compute_macro_impact(trades)

    # Load current signals
    print("\n[5/5] Loading current scan signals...")
    current_signals = load_current_signals()
    print(f"      Found {len(current_signals)} current signals")

    # Generate HTML
    print("\nGenerating HTML dashboard...")
    html = build_html(metrics, trades, sector_data, macro_impact, current_signals, args.account_size)

    out_path = Path(args.output)
    out_path.write_text(html, encoding="utf-8")

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"  Dashboard generated in {elapsed:.1f}s")
    print(f"  Output: {out_path}")
    print(f"  Trades: {len(trades):,}")
    print(f"  File size: {out_path.stat().st_size / 1024:.1f} KB")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()

