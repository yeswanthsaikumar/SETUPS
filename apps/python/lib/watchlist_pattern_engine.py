"""
watchlist_pattern_engine.py
───────────────────────────
Advanced Watchlist Pattern Analysis Engine

Analyzes a list of stocks for the "Relative Strength Leader" pattern:
  - Stocks that ran 30-50% while market was rising
  - Held / consolidated tightly while market fell 10-20%+
  - Broke out strongly when macro cleared

Provides full thesis per stock:
  1. RS Score vs Market   — IBD-style multi-period relative strength
  2. RS Leader Pattern    — detection of hold-while-market-falls behavior
  3. ADR %                — Average Daily Range (volatility / opportunity)
  4. Consolidation Quality— base tightness, depth, length, vol dry-up
  5. Fundamental Trends   — EPS, Revenue, Debt/Equity trends
  6. FII/DII Activity     — institutional accumulation/distribution
  7. News & Catalysts     — RSS feeds + scraping (ET, Moneycontrol, NSE)
  8. Trade Thesis         — Entry, Stop, Targets, Position Size, Risk:Reward
  9. Market Phase Map     — auto-detect Nifty50 decline/consol/recovery phases
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("WatchlistPatternEngine")
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Optional imports ──────────────────────────────────────────────────────────

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False
    logger.warning("yfinance not installed")

try:
    import pandas as pd
    import numpy as np
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    logger.warning("pandas/numpy not installed")

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import curl_cffi.requests as _cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    _cffi_requests = None

# ── Constants ─────────────────────────────────────────────────────────────────

NIFTY50_SYMBOL = "^NSEI"
NIFTY500_SYMBOL = "^CNX500"

# IBD-style RS weights (most recent period weighted more)
RS_PERIODS = [63, 126, 189, 252]  # 3m, 6m, 9m, 12m in trading days
RS_WEIGHTS = [0.40, 0.20, 0.20, 0.20]

NEWS_SOURCES = [
    # Economic Times Markets RSS
    ("ET Markets", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    # Moneycontrol NSE news
    ("Moneycontrol", "https://www.moneycontrol.com/rss/MCtopnews.xml"),
    # LiveMint Markets
    ("LiveMint", "https://www.livemint.com/rss/markets"),
    # BusinessLine Markets
    ("BusinessLine", "https://www.thehindubusinessline.com/markets/?service=rss"),
]

_CACHE_TTL_PRICE = 1800  # 30 min
_CACHE_TTL_NEWS  = 900   # 15 min
_CACHE_TTL_FUND  = 86400 # 24 hr


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_path(key: str) -> Path:
    safe = re.sub(r"[^\w.-]", "_", key)
    return CACHE_DIR / f"wpe_{safe}.json"


def _cache_load(key: str, ttl: int) -> Any | None:
    p = _cache_path(key)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text("utf-8"))
        if time.time() - data.get("_ts", 0) < ttl:
            return data.get("_payload")
    except Exception:
        pass
    return None


def _cache_save(key: str, payload: Any) -> None:
    p = _cache_path(key)
    try:
        p.write_text(json.dumps({"_ts": time.time(), "_payload": payload}), "utf-8")
    except Exception:
        pass


# ── Price data ────────────────────────────────────────────────────────────────

def _yf_symbol(symbol: str, market: str) -> str:
    """Convert symbol to yfinance format."""
    sym = symbol.strip().upper()
    if market == "india":
        if not sym.endswith(".NS") and not sym.endswith(".BO"):
            return sym + ".NS"
    return sym


def fetch_prices(symbol: str, market: str = "india", days: int = 504) -> dict | None:
    """
    Fetch OHLCV price history for a symbol.
    Uses start= date to guarantee data up to TODAY (avoids invalid period strings).
    Returns dict with keys: dates, open, high, low, close, volume (all lists).

    Honors GROWW_ONLY mode: for Indian stocks, refuses to call yfinance
    (which routes via geo-blocked Yahoo). In that case the caller should
    rely on the local cache CSV (refreshed by scripts/refresh_cache.py via
    Groww).
    """
    if not HAS_YF or not HAS_PANDAS:
        return None

    yf_sym = _yf_symbol(symbol, market)
    cache_key = f"prices_{yf_sym}_{days}"
    cached = _cache_load(cache_key, _CACHE_TTL_PRICE)
    if cached:
        # Validate cache is fresh through today. Previously this used a
        # 5-calendar-day threshold which let e.g. a Friday close satisfy a
        # Wednesday request (Fri→Wed = 5 cal days, 3 biz days). For the
        # ^NSEI benchmark that caused the RS table to show "Nifty asof
        # 2026-04-17" when today was 2026-04-21. Now we fall through if the
        # gap in *business days* is >= 1 — any missed trading day invalidates.
        cached_dates = cached.get("dates", [])
        if cached_dates:
            try:
                last_dt = datetime.strptime(cached_dates[-1], "%Y-%m-%d").date()
                today = datetime.now().date()
                gap_days = (today - last_dt).days
                if gap_days > 0:
                    biz_gap = sum(
                        1 for d in range(1, gap_days + 1)
                        if (last_dt + timedelta(days=d)).weekday() < 5
                    )
                    if biz_gap > 0:
                        # stale — fall through to re-fetch
                        pass
                    else:
                        return cached
                else:
                    return cached
            except Exception:
                # On any parse error, trust the TTL load and return cache.
                return cached

    # Groww-only gate: for Indian stocks, forbid yfinance live fetch here.
    # Price data must come from the cache CSV (populated by Groww in
    # refresh_cache.py). This prevents the app from silently hitting
    # Yahoo/yfinance which is geo-blocked or requires a broken VPN.
    try:
        from groww_client import should_use_non_groww_source
        _allow_yf = should_use_non_groww_source(yf_sym)
    except Exception:
        _allow_yf = True
    if not _allow_yf:
        logger.info(
            f"fetch_prices: skipping yfinance for {yf_sym} "
            f"(GROWW_ONLY mode on). Using cached data only."
        )
        return cached  # may be None if no cache existed yet

    try:
        # Use start= date so yfinance always returns data up to TODAY
        # "504d" is NOT a valid yfinance period — use start date instead
        extra_days = int(days * 1.5) + 30  # calendar days (includes weekends/holidays)
        start_date = (datetime.now() - timedelta(days=extra_days)).strftime("%Y-%m-%d")
        end_date   = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")  # inclusive of today

        tk = yf.Ticker(yf_sym)
        df = tk.history(start=start_date, end=end_date, auto_adjust=True, timeout=20)
        if df is None or df.empty:
            # Fallback: try "2y" period
            df = tk.history(period="2y", auto_adjust=True, timeout=20)
        if df is None or df.empty:
            return None

        df = df.dropna(subset=["Close"])
        df = df.tail(days)  # keep last N trading days

        result = {
            "symbol": symbol,
            "yf_symbol": yf_sym,
            "dates": [str(d.date()) for d in df.index],
            "open":  [round(float(v), 2) for v in df["Open"]],
            "high":  [round(float(v), 2) for v in df["High"]],
            "low":   [round(float(v), 2) for v in df["Low"]],
            "close": [round(float(v), 2) for v in df["Close"]],
            "volume":[int(v) for v in df["Volume"]],
        }
        _cache_save(cache_key, result)
        return result
    except Exception as e:
        logger.warning(f"Price fetch failed for {yf_sym}: {e}")
        return None


def fetch_market_prices(days: int = 504) -> dict | None:
    """Fetch Nifty50 price history."""
    return fetch_prices(NIFTY50_SYMBOL, market="us", days=days)


# ── ADR Calculation ───────────────────────────────────────────────────────────

def compute_adr(prices: dict, window: int = 20) -> dict:
    """
    Average Daily Range % — measures average volatility/opportunity.
    ADR = mean((High - Low) / Close) * 100 over `window` days.

    ADR > 5% = high volatility (big movers)
    ADR 2-5% = moderate (good for swings)
    ADR < 2% = low (boring / institutional)
    """
    h = prices.get("high", [])
    l = prices.get("low", [])
    c = prices.get("close", [])
    if len(c) < window:
        return {"adr_pct": None, "adr_label": "N/A", "window": window}

    ranges = [
        (h[i] - l[i]) / c[i] * 100
        for i in range(-window, 0)
        if c[i] and c[i] > 0
    ]
    adr = round(sum(ranges) / len(ranges), 2) if ranges else None

    if adr is None:
        label = "N/A"
    elif adr >= 6:
        label = "🔥 Very High"
    elif adr >= 4:
        label = "⚡ High"
    elif adr >= 2.5:
        label = "✅ Good"
    elif adr >= 1.5:
        label = "🔵 Moderate"
    else:
        label = "😴 Low"

    return {"adr_pct": adr, "adr_label": label, "window": window}


# ── Relative Strength Score ───────────────────────────────────────────────────

def compute_rs_score(
    stock_prices: dict,
    market_prices: dict,
    periods: list[int] | None = None,
    weights: list[float] | None = None,
) -> dict:
    """
    Compute IBD-style Relative Strength score (1-99) for a stock vs market.

    Method: Weighted sum of return percentile across multiple periods.
    Score > 80 = Strong leader
    Score 60-80 = Above average
    Score 40-60 = Average
    Score < 40 = Laggard
    """
    periods  = periods  or RS_PERIODS
    weights  = weights  or RS_WEIGHTS
    sc = stock_prices.get("close", [])
    mc = market_prices.get("close", [])

    if len(sc) < 20 or len(mc) < 20:
        return {"rs_score": None, "rs_label": "N/A", "period_returns": {}}

    period_results = {}
    weighted_excess = 0.0
    total_weight = 0.0

    for period, weight in zip(periods, weights):
        if len(sc) < period or len(mc) < period:
            continue
        try:
            s_ret = (sc[-1] - sc[-period]) / sc[-period] * 100
            m_ret = (mc[-1] - mc[-period]) / mc[-period] * 100
            excess = s_ret - m_ret
            period_results[f"{period}d"] = {
                "stock_ret_pct": round(s_ret, 1),
                "market_ret_pct": round(m_ret, 1),
                "excess_pct": round(excess, 1),
            }
            weighted_excess += excess * weight
            total_weight += weight
        except Exception:
            continue

    if total_weight == 0:
        return {"rs_score": None, "rs_label": "N/A", "period_returns": period_results}

    # Convert weighted excess return to 1-99 score
    # Calibrated for Indian market: typical excess range -20% to +60%
    # Score = 50 + (excess × scale), clamped to 1-99
    # Scale: 0.8 pts per 1% excess (so +25% excess = score 70, +60% excess = score 98)
    norm = weighted_excess / total_weight
    score_raw = 50 + (norm * 0.8)
    score = max(1, min(99, round(score_raw)))

    if score >= 90:
        label = "🚀 Elite Leader"
        color = "#ffd700"
    elif score >= 80:
        label = "💪 Strong RS"
        color = "#4ade80"
    elif score >= 65:
        label = "✅ Above Avg"
        color = "#86efac"
    elif score >= 50:
        label = "🔵 Average"
        color = "#7dd3fc"
    elif score >= 35:
        label = "⚠️ Below Avg"
        color = "#fbbf24"
    else:
        label = "🔴 Laggard"
        color = "#f87171"

    return {
        "rs_score": score,
        "rs_label": label,
        "rs_color": color,
        "weighted_excess_pct": round(norm, 1),
        "period_returns": period_results,
    }


# ── Market Phase Detection ────────────────────────────────────────────────────

def detect_market_phases(market_prices: dict, min_decline_pct: float = 2.5) -> list[dict]:
    """
    Detect phases in market: decline, consolidation, recovery.
    Uses a dual-pass approach:
      Pass 1: label each bar using a short rolling window (fast reaction)
      Pass 2: group consecutive labels into phases, keep all meaningful phases

    Returns list of phase dicts:
      { phase, start_date, end_date, start_idx, end_idx, change_pct, start_price, end_price }
    """
    closes = market_prices.get("close", [])
    dates  = market_prices.get("dates", [])
    if len(closes) < 20:
        return []

    n = len(closes)

    # ── Pass 1: label each bar with 5-day and 10-day momentum ────────────────
    trend_labels = ["unknown"] * n
    for i in range(n):
        if i < 5:
            continue
        chg5  = (closes[i] - closes[i - 5])  / closes[i - 5]  * 100
        chg10 = (closes[i] - closes[i - 10]) / closes[i - 10] * 100 if i >= 10 else chg5

        # Use the more extreme signal (5d is faster, 10d confirms)
        if chg5 <= -2.5 or chg10 <= -2.0:
            trend_labels[i] = "decline"
        elif chg5 >= 2.5 or chg10 >= 2.0:
            trend_labels[i] = "recovery"
        else:
            trend_labels[i] = "consolidation"

    # ── Pass 2: group consecutive same-label regions ─────────────────────────
    phases = []
    current_phase = trend_labels[0]
    phase_start   = 0

    for i in range(1, n):
        if trend_labels[i] != current_phase:
            length = i - phase_start
            if length >= 4:  # at least 4 bars to be meaningful
                chg = (closes[i-1] - closes[phase_start]) / closes[phase_start] * 100
                phases.append({
                    "phase":       current_phase,
                    "start_date":  dates[phase_start] if phase_start < len(dates) else "",
                    "end_date":    dates[i-1]         if i-1 < len(dates) else "",
                    "start_idx":   phase_start,
                    "end_idx":     i - 1,
                    "change_pct":  round(chg, 1),
                    "start_price": closes[phase_start],
                    "end_price":   closes[i-1],
                })
            current_phase = trend_labels[i]
            phase_start   = i

    # Last group
    if n - phase_start >= 4:
        chg = (closes[-1] - closes[phase_start]) / closes[phase_start] * 100
        phases.append({
            "phase":       current_phase,
            "start_date":  dates[phase_start] if phase_start < len(dates) else "",
            "end_date":    dates[-1] if dates else "",
            "start_idx":   phase_start,
            "end_idx":     n - 1,
            "change_pct":  round(chg, 1),
            "start_price": closes[phase_start],
            "end_price":   closes[-1],
        })

    # Keep all phases — do NOT filter out decline phases by size
    # (a -3% gradual decline is still a real decline)
    return [p for p in phases if p["phase"] != "unknown"]



def compute_stock_behavior_during_phases(
    stock_prices: dict,
    market_phases: list[dict],
) -> list[dict]:
    """
    For each market phase, compute how the stock behaved.
    Key metric: RS during each phase (excess return vs market).
    """
    closes = stock_prices.get("close", [])
    dates  = stock_prices.get("dates", [])
    if not closes or not dates or not market_phases:
        return []

    date_to_idx = {d: i for i, d in enumerate(dates)}
    results = []

    for phase in market_phases:
        start_date = phase["start_date"]
        end_date   = phase["end_date"]
        market_chg = phase["change_pct"]

        # Find matching indices in stock data
        si = date_to_idx.get(start_date)
        ei = date_to_idx.get(end_date)

        # Try to find nearest date if exact not found
        if si is None:
            for j, d in enumerate(dates):
                if d >= start_date:
                    si = j
                    break
        if ei is None:
            for j, d in enumerate(reversed(dates)):
                if d <= end_date:
                    ei = len(dates) - 1 - j
                    break

        if si is None or ei is None or si >= ei:
            continue
        if ei >= len(closes) or si >= len(closes):
            continue

        s_start = closes[si]
        s_end   = closes[ei]
        if s_start <= 0:
            continue

        s_chg = (s_end - s_start) / s_start * 100
        excess = s_chg - market_chg

        # Quality score for this phase
        if phase["phase"] == "decline":
            # Higher is better: stock should decline less or gain
            phase_score = min(100, max(0, 50 + excess * 2))
            quality = "HOLDING_STRONG" if excess > 5 else ("RESILIENT" if excess > 0 else ("WEAK" if excess > -5 else "VERY_WEAK"))
        elif phase["phase"] == "recovery":
            # Higher is better: stock should recover more
            phase_score = min(100, max(0, 50 + excess))
            quality = "LEADING" if excess > 10 else ("OUTPERFORMING" if excess > 0 else "LAGGING")
        else:
            # Consolidation
            phase_score = min(100, max(0, 50 + excess))
            quality = "STABLE" if abs(s_chg) < 5 else ("BUILDING" if s_chg > 0 else "CORRECTING")

        results.append({
            "phase": phase["phase"],
            "start_date": start_date,
            "end_date": end_date,
            "market_chg_pct": round(market_chg, 1),
            "stock_chg_pct": round(s_chg, 1),
            "excess_pct": round(excess, 1),
            "phase_score": round(phase_score),
            "quality": quality,
        })

    return results


# ── Consolidation Analysis ────────────────────────────────────────────────────

def analyze_consolidation(prices: dict, lookback_days: int = 60) -> dict:
    """
    Analyze the quality of a stock's recent consolidation/base.

    Metrics:
    - base_depth_pct: max drawdown from recent high in base
    - tightness: std(close) / mean(close) in base (lower = tighter = better)
    - base_length_days: number of days in base
    - vol_dry_up: recent 10-day avg vol / 30-day avg vol (< 0.7 = dry up)
    - up_down_vol_ratio: avg vol on up days vs down days (> 1.3 = bullish)
    - pivot_point: highest close in base + small buffer (potential breakout level)
    - pct_from_pivot: current price vs pivot (negative = below pivot)
    """
    h = prices.get("high", [])
    l = prices.get("low", [])
    c = prices.get("close", [])
    v = prices.get("volume", [])

    n = min(lookback_days, len(c))
    if n < 10:
        return {"error": "Not enough data"}

    base_high = prices.get("high", [])[-n:]
    base_low  = prices.get("low", [])[-n:]
    base_c    = c[-n:]
    base_v    = v[-n:] if len(v) >= n else []

    # Base depth from pivot high
    pivot_high = max(base_high) if base_high else 0
    pivot_high_c = max(base_c) if base_c else 0
    current = c[-1] if c else 0

    if pivot_high_c > 0:
        base_depth_pct = (pivot_high_c - min(base_c)) / pivot_high_c * 100
        pct_from_pivot = (current - pivot_high_c) / pivot_high_c * 100
    else:
        base_depth_pct = None
        pct_from_pivot = None

    # Tightness (coefficient of variation)
    if len(base_c) > 5:
        mean_c = sum(base_c) / len(base_c)
        std_c  = (sum((x - mean_c) ** 2 for x in base_c) / len(base_c)) ** 0.5
        tightness = (std_c / mean_c * 100) if mean_c > 0 else None
    else:
        tightness = None

    # Volume dry-up
    vol_dry_up = None
    up_down_vol_ratio = None
    if len(base_v) >= 30:
        recent_vol  = sum(base_v[-10:]) / 10
        prior_vol   = sum(base_v[-30:-10]) / 20
        vol_dry_up  = round(recent_vol / prior_vol, 2) if prior_vol > 0 else None

        # Up/down volume ratio
        up_vols, dn_vols = [], []
        for i in range(1, len(base_c)):
            if base_c[i] > base_c[i-1] and i < len(base_v):
                up_vols.append(base_v[i])
            elif base_c[i] < base_c[i-1] and i < len(base_v):
                dn_vols.append(base_v[i])
        if up_vols and dn_vols:
            up_down_vol_ratio = round((sum(up_vols)/len(up_vols)) / (sum(dn_vols)/len(dn_vols)), 2)

    # Base length
    base_length_days = n

    # Pivot point (potential breakout level)
    pivot_point = round(pivot_high * 1.02, 2)  # 2% above base high

    # Quality score
    score = 50.0
    if base_depth_pct is not None:
        if base_depth_pct < 15:   score += 15
        elif base_depth_pct < 25: score += 8
        elif base_depth_pct > 40: score -= 15

    if tightness is not None:
        if tightness < 5:    score += 15
        elif tightness < 10: score += 8
        elif tightness > 20: score -= 10

    if vol_dry_up is not None:
        if vol_dry_up < 0.6:   score += 10
        elif vol_dry_up < 0.8: score += 5
        elif vol_dry_up > 1.2: score -= 5

    if up_down_vol_ratio is not None:
        if up_down_vol_ratio > 1.5: score += 10
        elif up_down_vol_ratio > 1.2: score += 5

    score = max(0, min(100, round(score)))

    if score >= 80:   quality_label = "🏆 Excellent Base"
    elif score >= 65: quality_label = "✅ Good Base"
    elif score >= 50: quality_label = "🔵 Fair Base"
    elif score >= 35: quality_label = "⚠️ Loose Base"
    else:             quality_label = "🔴 Poor Base"

    return {
        "base_depth_pct": round(base_depth_pct, 1) if base_depth_pct is not None else None,
        "tightness_pct":  round(tightness, 1) if tightness is not None else None,
        "base_length_days": base_length_days,
        "vol_dry_up_ratio": vol_dry_up,
        "up_down_vol_ratio": up_down_vol_ratio,
        "pivot_point":       pivot_point,
        "pct_from_pivot":    round(pct_from_pivot, 1) if pct_from_pivot is not None else None,
        "consolidation_score": score,
        "quality_label":       quality_label,
    }


# ── Moving Averages & Trend ───────────────────────────────────────────────────

def compute_trend_structure(prices: dict) -> dict:
    """
    Compute trend structure:
    - Price vs MA20, MA50, MA150, MA200
    - Slope of each MA (rising/falling/flat)
    - Stage (1=basing, 2=uptrend, 3=topping, 4=downtrend)
    - 52-week high/low position
    """
    c = prices.get("close", [])
    if len(c) < 20:
        return {"error": "Not enough data"}

    def sma(n):
        if len(c) < n: return None
        return round(sum(c[-n:]) / n, 2)

    def sma_slope(n, lookback=5):
        if len(c) < n + lookback: return None
        old = sum(c[-(n+lookback):-lookback]) / n
        new = sum(c[-n:]) / n
        return round((new - old) / old * 100, 2) if old > 0 else None

    current = c[-1]
    ma20    = sma(20)
    ma50    = sma(50)
    ma150   = sma(150)
    ma200   = sma(200)

    slope20  = sma_slope(20)
    slope50  = sma_slope(50)
    slope200 = sma_slope(200)

    high_52w = max(c[-252:]) if len(c) >= 252 else max(c)
    low_52w  = min(c[-252:]) if len(c) >= 252 else min(c)
    pct_from_52w_high = round((current - high_52w) / high_52w * 100, 1)
    pct_from_52w_low  = round((current - low_52w) / low_52w * 100, 1)
    pct_from_52w_range= round((current - low_52w) / (high_52w - low_52w) * 100, 1) if high_52w != low_52w else 50.0

    # Stage detection (Weinstein Stage Analysis)
    above_200 = ma200 and current > ma200
    ma200_rising = slope200 is not None and slope200 > 0.1
    above_50  = ma50 and current > ma50
    above_20  = ma20 and current > ma20

    if above_200 and ma200_rising and above_50 and above_20:
        stage = 2
        stage_label = "Stage 2 — Uptrend ✅"
        stage_color = "#4ade80"
    elif above_200 and not ma200_rising:
        stage = 3
        stage_label = "Stage 3 — Topping ⚠️"
        stage_color = "#fbbf24"
    elif not above_200 and not ma200_rising:
        stage = 4
        stage_label = "Stage 4 — Downtrend 🔴"
        stage_color = "#f87171"
    else:
        stage = 1
        stage_label = "Stage 1 — Basing 🔵"
        stage_color = "#7dd3fc"

    return {
        "current_price": round(current, 2),
        "ma20":  ma20,
        "ma50":  ma50,
        "ma150": ma150,
        "ma200": ma200,
        "slope_ma20_pct":  slope20,
        "slope_ma50_pct":  slope50,
        "slope_ma200_pct": slope200,
        "above_ma20":  ma20 is not None and current > ma20,
        "above_ma50":  ma50 is not None and current > ma50,
        "above_ma150": ma150 is not None and current > ma150,
        "above_ma200": ma200 is not None and current > ma200,
        "high_52w": round(high_52w, 2),
        "low_52w":  round(low_52w, 2),
        "pct_from_52w_high":  pct_from_52w_high,
        "pct_from_52w_low":   pct_from_52w_low,
        "pct_from_52w_range": pct_from_52w_range,
        "stage": stage,
        "stage_label": stage_label,
        "stage_color": stage_color,
    }


# ── RS Leader Pattern Detection ───────────────────────────────────────────────

def detect_rs_leader_pattern(
    stock_prices: dict,
    market_prices: dict,
    market_phases: list[dict],
) -> dict:
    """
    Detect the 'RS Leader' pattern:
    1. Stock outperformed during prior uptrend (rose more than market)
    2. Stock held/declined less during market decline
    3. Stock consolidated tightly while market fell
    4. Stock is now positioned for breakout as market recovers

    Returns pattern score and explanation.
    """
    if not market_phases:
        return {"pattern_detected": False, "pattern_score": 0, "explanation": "No market phases detected"}

    sc = stock_prices.get("close", [])
    mc = market_prices.get("close", [])
    if len(sc) < 20 or len(mc) < 20:
        return {"pattern_detected": False, "pattern_score": 0, "explanation": "Insufficient price data"}

    phase_behavior = compute_stock_behavior_during_phases(stock_prices, market_phases)
    if not phase_behavior:
        return {"pattern_detected": False, "pattern_score": 0, "explanation": "Could not compute phase behavior"}

    decline_phases   = [p for p in phase_behavior if p["phase"] == "decline"]
    recovery_phases  = [p for p in phase_behavior if p["phase"] == "recovery"]
    consol_phases    = [p for p in phase_behavior if p["phase"] == "consolidation"]

    score = 0.0
    signals = []
    pattern_checks = {
        "held_during_declines": False,
        "led_during_recovery": False,
        "consolidated_well": False,
        "near_breakout": False,
    }

    # Check 1: Held during declines
    if decline_phases:
        avg_excess_decline = sum(p["excess_pct"] for p in decline_phases) / len(decline_phases)
        if avg_excess_decline > 8:
            score += 30
            pattern_checks["held_during_declines"] = True
            signals.append(f"💪 Held market declines: outperformed by avg +{avg_excess_decline:.1f}%")
        elif avg_excess_decline > 3:
            score += 15
            pattern_checks["held_during_declines"] = True
            signals.append(f"✅ Resilient in declines: +{avg_excess_decline:.1f}% vs market")
        elif avg_excess_decline > 0:
            score += 8
            pattern_checks["held_during_declines"] = True
            signals.append(f"🔵 Slightly resilient in declines: +{avg_excess_decline:.1f}% vs market")
        else:
            signals.append(f"⚠️ Weak during declines: {avg_excess_decline:.1f}% vs market")
    else:
        # No decline phases detected in window — high-RS stocks still deserve partial recognition
        signals.append("ℹ️ No clear market decline phase in window — using RS score as proxy")
        score += 8  # partial credit; RS bonus below will add more

    # Check 2: Led during recoveries
    if recovery_phases:
        avg_excess_recovery = sum(p["excess_pct"] for p in recovery_phases) / len(recovery_phases)
        if avg_excess_recovery > 10:
            score += 25
            pattern_checks["led_during_recovery"] = True
            signals.append(f"🚀 Led market recoveries: +{avg_excess_recovery:.1f}% excess")
        elif avg_excess_recovery > 3:
            score += 12
            pattern_checks["led_during_recovery"] = True
            signals.append(f"📈 Outperformed in recoveries: +{avg_excess_recovery:.1f}%")

    # Check 3: Quality consolidation
    consol = analyze_consolidation(stock_prices, 60)
    consol_score_raw = consol.get("consolidation_score", 50)
    if consol_score_raw >= 70:
        score += 25
        pattern_checks["consolidated_well"] = True
        signals.append(f"🏆 Excellent consolidation: {consol.get('quality_label', '')}")
    elif consol_score_raw >= 55:
        score += 12
        pattern_checks["consolidated_well"] = True
        signals.append(f"✅ Good consolidation: {consol.get('quality_label', '')}")
    else:
        signals.append(f"⚠️ Loose/poor consolidation: {consol.get('quality_label', '')}")

    # Check 4: Near breakout
    pct_from_pivot = consol.get("pct_from_pivot", None)
    if pct_from_pivot is not None:
        if -3 <= pct_from_pivot <= 5:
            score += 20
            pattern_checks["near_breakout"] = True
            signals.append(f"🎯 Near breakout pivot ({pct_from_pivot:+.1f}% from pivot)")
        elif -8 <= pct_from_pivot < -3:
            score += 10
            signals.append(f"📍 Approaching pivot ({pct_from_pivot:+.1f}% from pivot)")

    # RS score as tiebreaker
    rs = compute_rs_score(stock_prices, market_prices)
    rs_val = rs.get("rs_score", 50) or 50
    if rs_val >= 80: score = min(100, score + 10)
    elif rs_val >= 65: score = min(100, score + 5)

    score = max(0, min(100, round(score)))
    pattern_detected = score >= 50 and sum(1 for v in pattern_checks.values() if v) >= 2

    if score >= 85:
        pattern_label = "🌟 ELITE RS LEADER"
        pattern_color = "#ffd700"
    elif score >= 70:
        pattern_label = "🚀 Strong RS Leader"
        pattern_color = "#4ade80"
    elif score >= 55:
        pattern_label = "✅ RS Leader"
        pattern_color = "#86efac"
    elif score >= 40:
        pattern_label = "🔵 Potential Leader"
        pattern_color = "#7dd3fc"
    else:
        pattern_label = "⚠️ Not a Leader Pattern"
        pattern_color = "#94a3b8"

    return {
        "pattern_detected": pattern_detected,
        "pattern_score": score,
        "pattern_label": pattern_label,
        "pattern_color": pattern_color,
        "pattern_checks": pattern_checks,
        "signals": signals,
        "phase_behavior": phase_behavior,
        "consolidation": consol,
    }


# ── Trade Thesis / Plan ───────────────────────────────────────────────────────

def build_trade_thesis(
    symbol: str,
    stock_prices: dict,
    rs_data: dict,
    pattern_data: dict,
    adr_data: dict,
    trend_data: dict,
    fundamentals: dict | None = None,
    mf_data: dict | None = None,
) -> dict:
    """
    Build a complete trade thesis with entry, stop, targets, size, R:R.
    """
    c = stock_prices.get("close", [])
    h = stock_prices.get("high", [])
    v = stock_prices.get("volume", [])
    if not c:
        return {"error": "No price data"}

    current = c[-1]
    consol  = pattern_data.get("consolidation", {})
    pivot   = consol.get("pivot_point", current * 1.02)
    base_d  = consol.get("base_depth_pct", 20)
    adr_pct = adr_data.get("adr_pct", 3.0) or 3.0

    # Entry: Buy above pivot (breakout entry) or buy in base near support
    entry_breakout = round(pivot * 1.001, 2)  # just above pivot
    ma20 = trend_data.get("ma20", current * 0.95)
    entry_pullback = round((ma20 or current * 0.95) * 1.005, 2)

    # Stop: Below base low or 1.5x ATR
    base_low = min(c[-60:]) if len(c) >= 60 else min(c)
    atr = current * adr_pct / 100
    stop_base = round(base_low * 0.98, 2)
    stop_atr  = round(current - 1.5 * atr, 2)
    stop_loss = max(stop_base, stop_atr)  # tighter of the two

    # Risk per share at breakout entry
    risk_per_share = entry_breakout - stop_loss
    if risk_per_share <= 0:
        risk_per_share = current * 0.05

    # Targets: 1R, 2R, 3R (standard swing trading RR)
    t1 = round(entry_breakout + risk_per_share * 1.5, 2)
    t2 = round(entry_breakout + risk_per_share * 2.5, 2)
    t3 = round(entry_breakout + risk_per_share * 4.0, 2)

    risk_pct = round(risk_per_share / entry_breakout * 100, 1)

    # Position sizing (Kelly-fractional & percent-risk)
    max_risk_capital_pct = 1.0  # risk 1% of capital per trade
    # Shares for 1% risk on 10L capital (₹10,00,000)
    capital = 1_000_000
    shares_100k = max(1, round(capital * max_risk_capital_pct / 100 / risk_per_share))
    position_value_100k = round(shares_100k * entry_breakout)

    # Average volume context
    avg_vol_20 = sum(v[-20:]) / 20 if len(v) >= 20 else None

    # Compute recent returns to detect extended stocks
    ret_20d = (c[-1] - c[-21]) / c[-21] * 100 if len(c) >= 21 else None
    ret_60d = (c[-1] - c[-63]) / c[-63] * 100 if len(c) >= 63 else None
    ret_10d = (c[-1] - c[-11]) / c[-11] * 100 if len(c) >= 11 else None

    # Detect if stock is extended (too far from base for safe entry)
    is_extended = False
    extension_reason = ""
    if ret_20d is not None and ret_20d > 40:
        is_extended = True
        extension_reason = f"+{ret_20d:.0f}% in 20 days — wait for pullback to MA20"
    elif ret_10d is not None and ret_10d > 20:
        is_extended = True
        extension_reason = f"+{ret_10d:.0f}% in 10 days — wait for base"
    elif trend_data.get("pct_from_52w_high") is not None and trend_data.get("pct_from_52w_high", 0) > 2:
        # Already at or above 52-week high — might be extended
        pass

    # Detect if currently consolidating (20d return low but 60d return high)
    is_consolidating = False
    if ret_20d is not None and ret_60d is not None:
        if abs(ret_20d) < 8 and ret_60d > 20:
            is_consolidating = True  # resting after a big move — ideal!

    # Conviction score
    rs_score = rs_data.get("rs_score", 50) or 50
    pattern_score = pattern_data.get("pattern_score", 50)
    consol_score  = consol.get("consolidation_score", 50)
    # Bonus if currently consolidating (lower 20d return + high 60d = resting)
    consol_bonus = 8 if is_consolidating else 0
    conviction = min(100, round((rs_score * 0.30 + pattern_score * 0.40 + consol_score * 0.25) + consol_bonus))

    # Setup type
    pct_from_pivot = consol.get("pct_from_pivot", -10)
    if is_extended:
        setup_type = "EXTENDED_WAIT"
    elif pct_from_pivot is not None and -3 <= (pct_from_pivot or -99) <= 5:
        setup_type = "BREAKOUT_READY"
    elif is_consolidating or (pct_from_pivot is not None and -12 <= (pct_from_pivot or -99) < -3):
        setup_type = "BASE_BUILDING"
    else:
        setup_type = "EARLY_STAGE"

    # Action
    stage = trend_data.get("stage", 2)
    if stage == 4:
        action = "AVOID"
        action_label = "🔴 AVOID — Stage 4"
    elif is_extended:
        action = "WATCH"
        action_label = f"⏳ EXTENDED — {extension_reason}"
    elif conviction >= 72 and setup_type == "BREAKOUT_READY":
        action = "BUY_NOW"
        action_label = "🟢 BUY ON BREAKOUT"
    elif conviction >= 62 or is_consolidating:
        action = "WATCH_CLOSELY"
        action_label = "🟡 WATCH CLOSELY"
    elif conviction >= 48:
        action = "WATCH"
        action_label = "🔵 ON WATCHLIST"
    else:
        action = "AVOID"
        action_label = "🔴 AVOID"

    # Catalyst summary
    catalysts = []
    if fundamentals:
        eps_qoq = fundamentals.get("eps_qoq_pct")
        if eps_qoq and eps_qoq > 15:
            catalysts.append(f"EPS growth +{eps_qoq:.0f}% QoQ")
        rev_yoy = fundamentals.get("revenue_yoy_pct")
        if rev_yoy and rev_yoy > 20:
            catalysts.append(f"Revenue +{rev_yoy:.0f}% YoY")
        debt_trend = fundamentals.get("debt_trend")
        if debt_trend == "improving":
            catalysts.append("Debt reducing ↓")

    if mf_data:
        signal = mf_data.get("smart_money_signal", "")
        if signal == "ACCUMULATING":
            catalysts.append("🏦 Smart money accumulating")
        dii_trend = mf_data.get("dii_trend", "")
        if dii_trend == "up":
            catalysts.append("DII buying ↑")

    # Summary narrative
    rs_label = rs_data.get("rs_label", "")
    pattern_label = pattern_data.get("pattern_label", "")
    summary = (
        f"{symbol}: {pattern_label} | RS {rs_score}/99 | "
        f"Entry ~₹{entry_breakout} | Stop ₹{stop_loss} (-{risk_pct}%) | "
        f"T1 ₹{t1} | T2 ₹{t2} | T3 ₹{t3}"
    )

    return {
        "symbol": symbol,
        "current_price": round(current, 2),
        "entry_breakout": entry_breakout,
        "entry_pullback": entry_pullback,
        "stop_loss": round(stop_loss, 2),
        "risk_pct": risk_pct,
        "target1": t1,
        "target2": t2,
        "target3": t3,
        "rr_t1": round((t1 - entry_breakout) / risk_per_share, 1) if risk_per_share > 0 else None,
        "rr_t2": round((t2 - entry_breakout) / risk_per_share, 1) if risk_per_share > 0 else None,
        "rr_t3": round((t3 - entry_breakout) / risk_per_share, 1) if risk_per_share > 0 else None,
        "position_value_1pct_risk": position_value_100k,
        "shares_1pct_risk_1M_capital": shares_100k,
        "avg_volume_20d": round(avg_vol_20) if avg_vol_20 else None,
        "conviction_score": conviction,
        "setup_type": setup_type,
        "action": action,
        "action_label": action_label,
        "is_extended": is_extended,
        "is_consolidating": is_consolidating,
        "extension_reason": extension_reason,
        "ret_20d": round(ret_20d, 1) if ret_20d is not None else None,
        "ret_60d": round(ret_60d, 1) if ret_60d is not None else None,
        "catalysts": catalysts,
        "summary": summary,
    }


# ── Fundamentals ──────────────────────────────────────────────────────────────

def fetch_fundamentals(symbol: str, market: str = "india") -> dict:
    """Fetch key fundamental data via yfinance.

    Honors GROWW_ONLY mode: Indian symbols skip yfinance and return cached
    data if any, otherwise an explicit marker. Use `fundamentals_provider`
    (Groww-backed) instead for live data.
    """
    if not HAS_YF:
        return {"error": "yfinance not installed"}

    yf_sym = _yf_symbol(symbol, market)
    cache_key = f"fund_{yf_sym}"
    cached = _cache_load(cache_key, _CACHE_TTL_FUND)
    if cached:
        return cached

    try:
        from groww_client import should_use_non_groww_source
        _allow_yf = should_use_non_groww_source(yf_sym)
    except Exception:
        _allow_yf = True
    if not _allow_yf:
        return {
            "symbol": symbol, "yf_symbol": yf_sym,
            "error": "groww_only_mode",
            "_hint": "Set GROWW_ONLY=0 or use fundamentals_provider (Groww).",
        }

    result: dict = {"symbol": symbol, "yf_symbol": yf_sym}
    try:
        tk = yf.Ticker(yf_sym)
        info = tk.info or {}

        # Basic
        result["company_name"] = info.get("longName", info.get("shortName", symbol))
        result["sector"]        = info.get("sector", "")
        result["industry"]      = info.get("industry", "")
        result["market_cap"]    = info.get("marketCap")
        result["pe_ratio"]      = info.get("trailingPE") or info.get("forwardPE")
        result["pb_ratio"]      = info.get("priceToBook")
        result["roe_pct"]       = round(info.get("returnOnEquity", 0) * 100, 1) if info.get("returnOnEquity") else None
        result["roa_pct"]       = round(info.get("returnOnAssets", 0) * 100, 1) if info.get("returnOnAssets") else None
        result["debt_to_equity"]= info.get("debtToEquity")
        result["current_ratio"] = info.get("currentRatio")
        result["revenue"]       = info.get("totalRevenue")
        result["net_income"]    = info.get("netIncomeToCommon")
        result["eps_ttm"]       = info.get("trailingEps")
        result["eps_fwd"]       = info.get("forwardEps")
        result["revenue_growth"]= info.get("revenueGrowth")
        result["earnings_growth"]= info.get("earningsGrowth")
        result["free_cashflow"] = info.get("freeCashflow")
        result["dividend_yield"]= info.get("dividendYield")

        # Growth metrics
        rev_growth = info.get("revenueGrowth") or 0
        earn_growth = info.get("earningsGrowth") or 0
        result["revenue_yoy_pct"]  = round(rev_growth * 100, 1) if rev_growth else None
        result["earnings_yoy_pct"] = round(earn_growth * 100, 1) if earn_growth else None

        # Quarterly EPS trend (from earnings history)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                qe = tk.quarterly_earnings
                if qe is not None and not qe.empty:
                    qe = qe.sort_index()
                    eps_vals = qe["Earnings"].tolist()
                    if len(eps_vals) >= 2:
                        old_eps = eps_vals[-2]
                        new_eps = eps_vals[-1]
                        if old_eps and old_eps != 0 and new_eps:
                            result["eps_qoq_pct"] = round((new_eps - old_eps) / abs(old_eps) * 100, 1)
        except Exception:
            pass

        # Debt trend (simple: D/E ratio vs typical threshold)
        de = result.get("debt_to_equity")
        if de is not None:
            if de < 0.3:   result["debt_trend"] = "low_debt"
            elif de < 1.0: result["debt_trend"] = "manageable"
            elif de < 2.0: result["debt_trend"] = "moderate_debt"
            else:          result["debt_trend"] = "high_debt"

        # Earnings quality
        net = result.get("net_income") or 0
        fcf = result.get("free_cashflow") or 0
        if net > 0 and fcf > 0:
            result["earnings_quality"] = "strong"
        elif net > 0:
            result["earnings_quality"] = "moderate"
        else:
            result["earnings_quality"] = "weak"

        # Format market cap
        mc = result.get("market_cap")
        if mc:
            if market == "india":
                cr = mc / 1e7
                if cr >= 10000:    result["mcap_label"] = f"₹{cr/100:.0f}K Cr (Large)"
                elif cr >= 2500:   result["mcap_label"] = f"₹{cr:.0f} Cr (Mid)"
                else:              result["mcap_label"] = f"₹{cr:.0f} Cr (Small)"
            else:
                b = mc / 1e9
                result["mcap_label"] = f"${b:.1f}B"

        _cache_save(cache_key, result)
        return result
    except Exception as e:
        logger.warning(f"Fundamentals fetch failed for {yf_sym}: {e}")
        result["error"] = str(e)
        return result


# ── News & Catalysts ──────────────────────────────────────────────────────────

def fetch_news(symbol: str, market: str = "india", max_items: int = 8) -> list[dict]:
    """
    Fetch recent news for a symbol from multiple sources:
    1. yfinance news (fastest)
    2. Economic Times RSS
    3. Moneycontrol RSS
    4. BSE/NSE announcements (India)
    """
    cache_key = f"news_{symbol.upper()}"
    cached = _cache_load(cache_key, _CACHE_TTL_NEWS)
    if cached:
        return cached

    news_items = []
    clean_sym = symbol.upper().replace(".NS", "").replace(".BO", "")

    # 1. yfinance news
    if HAS_YF:
        try:
            yf_sym = _yf_symbol(symbol, market)
            tk = yf.Ticker(yf_sym)
            yf_news = tk.news or []
            for item in yf_news[:5]:
                if isinstance(item, dict):
                    # Handle both old and new yfinance news formats
                    content = item.get("content", {})
                    if isinstance(content, dict):
                        title = content.get("title", "")
                        link  = content.get("canonicalUrl", {}).get("url", "") if isinstance(content.get("canonicalUrl"), dict) else ""
                        pub_date = content.get("pubDate", "")
                        provider = content.get("provider", {}).get("displayName", "Yahoo Finance") if isinstance(content.get("provider"), dict) else "Yahoo Finance"
                    else:
                        title = item.get("title", "")
                        link  = item.get("link", "")
                        pub_date = datetime.fromtimestamp(item.get("providerPublishTime", 0)).strftime("%Y-%m-%d") if item.get("providerPublishTime") else ""
                        provider = item.get("publisher", "Yahoo Finance")

                    if title:
                        news_items.append({
                            "title": title,
                            "link":  link,
                            "date":  pub_date,
                            "source": provider,
                            "relevance": "high",
                        })
        except Exception as e:
            logger.debug(f"yfinance news failed for {symbol}: {e}")

    # 2. RSS feeds
    if HAS_FEEDPARSER and len(news_items) < max_items:
        for source_name, feed_url in NEWS_SOURCES:
            try:
                feed = feedparser.parse(feed_url, request_headers={"User-Agent": "Mozilla/5.0"})
                for entry in feed.entries[:20]:
                    title = entry.get("title", "")
                    if clean_sym.lower() in title.lower():
                        news_items.append({
                            "title": title,
                            "link":  entry.get("link", ""),
                            "date":  entry.get("published", "")[:10] if entry.get("published") else "",
                            "source": source_name,
                            "relevance": "high",
                        })
                        if len(news_items) >= max_items:
                            break
            except Exception:
                pass
            if len(news_items) >= max_items:
                break

    # 3. NSE announcements via scraping
    if HAS_REQUESTS and market == "india" and len(news_items) < max_items:
        try:
            url = f"https://www.nseindia.com/api/corp-announcements?index=equities&symbol={clean_sym}"
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
                "Referer": "https://www.nseindia.com",
            }
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                for item in (data or [])[:3]:
                    news_items.append({
                        "title":  item.get("subject", item.get("desc", "")),
                        "link":   "",
                        "date":   item.get("exchdisstime", "")[:10],
                        "source": "NSE Announcement",
                        "relevance": "high",
                    })
        except Exception:
            pass

    # 4. Screener.in company news (scraping)
    if HAS_REQUESTS and market == "india" and len(news_items) < max_items:
        try:
            if HAS_CURL_CFFI:
                resp = _cffi_requests.get(
                    f"https://www.screener.in/company/{clean_sym}/",
                    impersonate="chrome110", timeout=8
                )
            else:
                resp = requests.get(
                    f"https://www.screener.in/company/{clean_sym}/",
                    headers={"User-Agent": "Mozilla/5.0"}, timeout=8
                )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                news_section = soup.find("section", id="announcements") or soup.find("div", class_="announcements")
                if news_section:
                    for li in news_section.find_all("li", limit=4):
                        a = li.find("a")
                        date_el = li.find(class_="date") or li.find("span")
                        if a:
                            news_items.append({
                                "title": a.get_text(strip=True),
                                "link": "https://www.screener.in" + a.get("href", ""),
                                "date": date_el.get_text(strip=True) if date_el else "",
                                "source": "Screener.in",
                                "relevance": "medium",
                            })
        except Exception:
            pass

    # Deduplicate
    seen = set()
    unique_news = []
    for item in news_items:
        key = item.get("title", "")[:60]
        if key and key not in seen:
            seen.add(key)
            unique_news.append(item)

    result = unique_news[:max_items]
    if result:
        _cache_save(cache_key, result)
    return result


# ── Volume Analysis ───────────────────────────────────────────────────────────

def compute_volume_analysis(prices: dict) -> dict:
    """Compute volume trend, accumulation/distribution, and volume patterns."""
    v = prices.get("volume", [])
    c = prices.get("close", [])
    if not v or len(v) < 20:
        return {"error": "Not enough volume data"}

    avg_vol_20  = sum(v[-20:]) / 20
    avg_vol_50  = sum(v[-50:]) / 50 if len(v) >= 50 else avg_vol_20
    vol_ratio   = round(avg_vol_20 / avg_vol_50, 2) if avg_vol_50 > 0 else 1.0

    # Recent 5-day avg vs 20-day avg (expansion vs contraction)
    avg_vol_5 = sum(v[-5:]) / 5
    recent_vol_ratio = round(avg_vol_5 / avg_vol_20, 2) if avg_vol_20 > 0 else 1.0

    # Volume on up days vs down days (accumulation/distribution)
    up_vol, dn_vol, up_days, dn_days = 0, 0, 0, 0
    for i in range(max(-30, -len(c)+1), 0):
        if c[i] > c[i-1]:
            up_vol  += v[i]
            up_days += 1
        elif c[i] < c[i-1]:
            dn_vol  += v[i]
            dn_days += 1

    avg_up_vol = up_vol / up_days if up_days > 0 else 0
    avg_dn_vol = dn_vol / dn_days if dn_days > 0 else 0
    ud_ratio = round(avg_up_vol / avg_dn_vol, 2) if avg_dn_vol > 0 else 1.0

    if ud_ratio >= 1.5:
        vol_signal = "ACCUMULATING"
        vol_color = "#4ade80"
    elif ud_ratio >= 1.1:
        vol_signal = "SLIGHT_ACCUMULATION"
        vol_color = "#86efac"
    elif ud_ratio >= 0.9:
        vol_signal = "NEUTRAL"
        vol_color = "#7dd3fc"
    elif ud_ratio >= 0.7:
        vol_signal = "SLIGHT_DISTRIBUTION"
        vol_color = "#fbbf24"
    else:
        vol_signal = "DISTRIBUTING"
        vol_color = "#f87171"

    # Dry-up pattern (vol contraction in base)
    if recent_vol_ratio < 0.6:
        dry_up_label = "🔵 Strong Dry-up"
    elif recent_vol_ratio < 0.8:
        dry_up_label = "✅ Vol Contracting"
    elif recent_vol_ratio < 1.1:
        dry_up_label = "🟡 Normal Vol"
    else:
        dry_up_label = "⚠️ Vol Expanding"

    return {
        "avg_vol_20d":     round(avg_vol_20),
        "avg_vol_50d":     round(avg_vol_50),
        "vol_ratio_20_50": vol_ratio,
        "recent_vol_ratio_5_20": recent_vol_ratio,
        "up_down_vol_ratio": ud_ratio,
        "vol_signal":      vol_signal,
        "vol_color":       vol_color,
        "dry_up_label":    dry_up_label,
        "accumulation_days": up_days,
        "distribution_days": dn_days,
    }


# ── Return Computation ────────────────────────────────────────────────────────

def compute_returns(prices: dict) -> dict:
    """Compute returns over multiple periods."""
    c = prices.get("close", [])
    if not c:
        return {}

    def ret(n):
        if len(c) >= n:
            return round((c[-1] - c[-n]) / c[-n] * 100, 1)
        return None

    return {
        "ret_1d":   ret(2),
        "ret_5d":   ret(6),
        "ret_20d":  ret(21),
        "ret_60d":  ret(63),
        "ret_3m":   ret(63),
        "ret_6m":   ret(126),
        "ret_1y":   ret(252),
        "ret_ytd":  None,  # computed separately
        "price_now": round(c[-1], 2) if c else None,
        "price_52w_ago": round(c[-252], 2) if len(c) >= 252 else None,
    }


# ── Full Stock Analysis ───────────────────────────────────────────────────────

def analyze_single_stock(
    symbol: str,
    market: str = "india",
    market_prices: dict | None = None,
    market_phases: list[dict] | None = None,
    include_news: bool = True,
    include_fundamentals: bool = True,
    include_mf: bool = True,
) -> dict:
    """
    Run complete analysis for a single stock.
    Returns a comprehensive dict with all metrics.
    """
    result: dict = {
        "symbol": symbol,
        "market": market,
        "analyzed_at": datetime.now().isoformat(timespec="seconds"),
        "error": None,
    }

    # Fetch price data
    stock_prices = fetch_prices(symbol, market, days=504)
    if not stock_prices:
        result["error"] = "Could not fetch price data"
        return result

    # Market prices (Nifty for India)
    if market_prices is None:
        market_prices = fetch_market_prices(days=504)
    if market_prices is None:
        result["error"] = "Could not fetch market (Nifty) data"
        return result

    # Market phases
    if market_phases is None:
        market_phases = detect_market_phases(market_prices)

    # Core computations
    result["prices"]         = {"dates": stock_prices.get("dates", [])[-30:],
                                "close": stock_prices.get("close", [])[-30:],
                                "high":  stock_prices.get("high", [])[-30:],
                                "low":   stock_prices.get("low", [])[-30:],
                                "volume":stock_prices.get("volume", [])[-30:]}
    result["returns"]        = compute_returns(stock_prices)
    result["adr"]            = compute_adr(stock_prices)
    result["trend"]          = compute_trend_structure(stock_prices)
    result["rs"]             = compute_rs_score(stock_prices, market_prices)
    result["volume"]         = compute_volume_analysis(stock_prices)
    result["consolidation"]  = analyze_consolidation(stock_prices, 60)
    result["pattern"]        = detect_rs_leader_pattern(stock_prices, market_prices, market_phases)

    # Fundamentals
    if include_fundamentals:
        result["fundamentals"] = fetch_fundamentals(symbol, market)

    # MF / Institutional Holdings
    mf_data = None
    if include_mf and market == "india":
        try:
            import sys
            mf_lib = str(Path(__file__).parent)
            if mf_lib not in sys.path:
                sys.path.insert(0, mf_lib)
            from mutual_funds_provider import MutualFundsProvider, swing_context
            provider = MutualFundsProvider(cache_dir=str(CACHE_DIR), cache_ttl_hours=6)
            yf_sym = _yf_symbol(symbol, market)
            raw_mf = provider.fetch(yf_sym, market=market)
            mf_data = swing_context(raw_mf)
            result["mf_holdings"] = {
                "promoters_pct": raw_mf.get("promoters_pct"),
                "fii_pct": raw_mf.get("fii_pct"),
                "dii_pct": raw_mf.get("dii_pct"),
                "public_pct": raw_mf.get("public_pct"),
                "promoters_trend": raw_mf.get("promoters_trend"),
                "fii_trend": raw_mf.get("fii_trend"),
                "dii_trend": raw_mf.get("dii_trend"),
                "dii_accumulating": raw_mf.get("dii_accumulating"),
                "smart_money_signal": raw_mf.get("smart_money_signal"),
                "summary": raw_mf.get("summary", ""),
                "swing_signal": mf_data.get("signal", ""),
            }
        except Exception as e:
            result["mf_holdings"] = {"error": str(e)}

    # News
    if include_news:
        result["news"] = fetch_news(symbol, market)

    # Trade thesis
    result["thesis"] = build_trade_thesis(
        symbol=symbol,
        stock_prices=stock_prices,
        rs_data=result["rs"],
        pattern_data=result["pattern"],
        adr_data=result["adr"],
        trend_data=result["trend"],
        fundamentals=result.get("fundamentals"),
        mf_data=result.get("mf_holdings"),
    )

    # Summary badge
    conviction = result["thesis"].get("conviction_score", 0)
    pattern_label = result["pattern"].get("pattern_label", "")
    result["summary"] = {
        "symbol": symbol,
        "conviction": conviction,
        "action": result["thesis"].get("action", "WATCH"),
        "action_label": result["thesis"].get("action_label", ""),
        "pattern_label": pattern_label,
        "pattern_score": result["pattern"].get("pattern_score", 0),
        "rs_score": result["rs"].get("rs_score"),
        "rs_label": result["rs"].get("rs_label"),
        "adr_pct": result["adr"].get("adr_pct"),
        "stage": result["trend"].get("stage"),
        "stage_label": result["trend"].get("stage_label"),
        "current_price": result["returns"].get("price_now"),
        "ret_20d": result["returns"].get("ret_20d"),
        "ret_60d": result["returns"].get("ret_60d"),
        "setup_type": result["thesis"].get("setup_type"),
        "is_extended": result["thesis"].get("is_extended", False),
        "is_consolidating": result["thesis"].get("is_consolidating", False),
        "extension_reason": result["thesis"].get("extension_reason", ""),
        "entry": result["thesis"].get("entry_breakout"),
        "stop":  result["thesis"].get("stop_loss"),
        "t1": result["thesis"].get("target1"),
        "t2": result["thesis"].get("target2"),
        "t3": result["thesis"].get("target3"),
        "rr_t1": result["thesis"].get("rr_t1"),
        "rr_t2": result["thesis"].get("rr_t2"),
        "consol_score": result["pattern"].get("consolidation", {}).get("consolidation_score"),
        "vol_dry_up": result["pattern"].get("consolidation", {}).get("vol_dry_up_ratio"),
    }

    return result


# ── Batch Watchlist Analysis ──────────────────────────────────────────────────

def analyze_watchlist(
    symbols: list[str],
    market: str = "india",
    workers: int = 6,
    include_news: bool = True,
    include_fundamentals: bool = True,
    include_mf: bool = True,
) -> dict:
    """
    Analyze a full watchlist of stocks in parallel.
    Returns ranked results sorted by conviction score.
    """
    if not symbols:
        return {"error": "No symbols provided", "results": []}

    # Pre-fetch shared data
    market_prices = fetch_market_prices(days=504)
    if not market_prices:
        return {"error": "Could not fetch market data", "results": []}

    market_phases = detect_market_phases(market_prices)

    # Market context
    mkt_closes = market_prices.get("close", [])
    mkt_dates  = market_prices.get("dates", [])
    market_context = {
        "symbol": NIFTY50_SYMBOL,
        "current": round(mkt_closes[-1], 2) if mkt_closes else None,
        "ret_1m": round((mkt_closes[-1]-mkt_closes[-22])/mkt_closes[-22]*100, 1) if len(mkt_closes) >= 22 else None,
        "ret_3m": round((mkt_closes[-1]-mkt_closes[-63])/mkt_closes[-63]*100, 1) if len(mkt_closes) >= 63 else None,
        "ret_1y": round((mkt_closes[-1]-mkt_closes[-252])/mkt_closes[-252]*100, 1) if len(mkt_closes) >= 252 else None,
        "phases": market_phases[-5:],  # last 5 phases
        "phase_summary": _summarize_phases(market_phases),
    }

    # Parallel stock analysis
    results = []
    errors  = []

    def _analyze(sym):
        try:
            return analyze_single_stock(
                symbol=sym,
                market=market,
                market_prices=market_prices,
                market_phases=market_phases,
                include_news=include_news,
                include_fundamentals=include_fundamentals,
                include_mf=include_mf,
            )
        except Exception as e:
            return {"symbol": sym, "error": str(e)}

    max_workers = min(workers, len(symbols))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_analyze, sym): sym for sym in symbols}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                res = fut.result(timeout=60)
                if res.get("error"):
                    errors.append({"symbol": sym, "error": res["error"]})
                results.append(res)
            except Exception as e:
                errors.append({"symbol": sym, "error": str(e)})

    # Sort by conviction score
    results.sort(key=lambda r: r.get("thesis", {}).get("conviction_score", 0) or 0, reverse=True)

    # Leaderboard (top RS leaders)
    leaders = [
        r for r in results
        if r.get("pattern", {}).get("pattern_detected")
        and not r.get("error")
    ]
    leaders.sort(key=lambda r: r.get("pattern", {}).get("pattern_score", 0) or 0, reverse=True)

    return {
        "analyzed_at": datetime.now().isoformat(timespec="seconds"),
        "market": market,
        "total_symbols": len(symbols),
        "successful": len([r for r in results if not r.get("error")]),
        "errors": errors,
        "market_context": market_context,
        "market_phases": market_phases,
        "results": results,
        "leaders": [r.get("summary") for r in leaders if r.get("summary")],
        "summary_table": _build_summary_table(results),
    }


def _summarize_phases(phases: list[dict]) -> str:
    """Create a human-readable summary of recent market phases."""
    if not phases:
        return "No clear market phases detected"
    recent = phases[-3:]
    parts = []
    for p in recent:
        parts.append(f"{p['phase'].title()} ({p['start_date']} → {p['end_date']}, {p['change_pct']:+.1f}%)")
    return " → ".join(parts)


def _build_summary_table(results: list[dict]) -> list[dict]:
    """Build a clean summary table for quick comparison."""
    rows = []
    for r in results:
        if r.get("error"):
            rows.append({"symbol": r.get("symbol", "?"), "error": r["error"]})
            continue
        s = r.get("summary", {})
        rows.append({
            "symbol":         s.get("symbol", r.get("symbol")),
            "price":          s.get("current_price"),
            "ret_20d":        s.get("ret_20d"),
            "ret_60d":        s.get("ret_60d"),
            "rs_score":       s.get("rs_score"),
            "adr_pct":        s.get("adr_pct"),
            "stage":          s.get("stage"),
            "pattern":        s.get("pattern_label"),
            "pattern_score":  s.get("pattern_score"),
            "action":         s.get("action"),
            "action_label":   s.get("action_label"),
            "conviction":     s.get("conviction"),
            "entry":          s.get("entry"),
            "stop":           s.get("stop"),
            "t1":             s.get("t1"),
            "rr_t1":          s.get("rr_t1"),
            "setup":          s.get("setup_type"),
            "is_extended":    s.get("is_extended", False),
            "is_consolidating": s.get("is_consolidating", False),
            "extension_reason": s.get("extension_reason", ""),
            "consol_score":   s.get("consol_score"),
            "vol_dry_up":     s.get("vol_dry_up"),
        })
    return rows

