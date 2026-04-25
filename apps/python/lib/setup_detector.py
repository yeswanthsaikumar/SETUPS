"""
setup_detector.py
────────────────
Pure-Python setup detector for swing trading, targeting both mean reversion and breakout strategies.

Mean Reversion Strategy
───────────────────────
Detects high-quality mean reversion setups where:
  1. Stock is in a macro uptrend (close > 200-day SMA)
  2. Short-term pullback has driven price into oversold territory
  3. A reversal signal candle appears (BB bounce, MA reclaim, RSI snapback)
  4. Volume dry-up during pullback + moderate increase on signal day

Breakout Strategy
─────────────────
Detects breakout setups and tracks post-breakout highs/lows.

Trade Plan
──────────
Shared trade plan logic for all setup types.
"""

from __future__ import annotations

import csv
import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Union


# ── Constants ─────────────────────────────────────────────────────────────────
_SETUP_TYPE_MR   = "MEAN_REVERSION"
_SETUP_TYPE_BO   = "BREAKOUT"
_SETUP_TYPE_ABFP = "BREAKOUT_PULLBACK"
_SETUP_TYPE_BF   = "BULL_FLAG"
_SETUP_TYPE_EMA_PB = "EMA_PULLBACK"
_SETUP_TYPE_BASE_BO = "BASE_BREAKOUT"
_SETUP_TYPE_FTD  = "FOLLOW_THROUGH"
_DEFAULT_RSI_PERIOD = 14
_DEFAULT_BB_PERIOD = 20
_DEFAULT_BB_STD = 2.0
_DEFAULT_SMA_SHORT = 20
_DEFAULT_SMA_MED = 50
_DEFAULT_SMA_LONG = 200
_DEFAULT_ATR_PERIOD = 14
_DEFAULT_LOOKBACK_WINDOW = 5
_MIN_BARS = 210
_MIN_BARS_IPO = 60   # IPO-friendly: allow stocks with ~3 months of daily history


def _timeframe_params(timeframe: str, ipo_mode: bool = False) -> dict[str, int | float]:
    tf = (timeframe or "daily").strip().lower()
    if tf == "weekly":
        return {
            "sma_short": 10,
            "sma_med": 20,
            "sma_long": 40,
            "bb_period": 10,
            "atr_period": 10,
            "pullback_window": 3,
            "min_bars": 20 if ipo_mode else 52,
        }
    return {
        "sma_short": _DEFAULT_SMA_SHORT,
        "sma_med": _DEFAULT_SMA_MED,
        "sma_long": _DEFAULT_SMA_LONG,
        "bb_period": _DEFAULT_BB_PERIOD,
        "atr_period": _DEFAULT_ATR_PERIOD,
        "pullback_window": _DEFAULT_LOOKBACK_WINDOW,
        "min_bars": _MIN_BARS_IPO if ipo_mode else _MIN_BARS,
    }


@dataclass
class TradeSignal:
    symbol: str
    subtype: str
    setup: str
    window: str = "DAILY"
    rating: str = "B"
    score: float = 0.0
    close: float = 0.0
    entry: float = 0.0
    sl: float = 0.0
    pivot: float = 0.0
    T1: float = 0.0
    T2: float = 0.0
    T3: float = 0.0
    shares: int = 0
    # Common indicators
    rsi: float = 0.0
    sma20: float = 0.0
    sma50: float = 0.0
    sma200: float = 0.0
    atr: float = 0.0
    lower_bb: float = 0.0
    upper_bb: float = 0.0
    bb_pct: float = 0.0
    vol_ratio: float = 0.0
    # Pass-through fields
    listType: str = "BREAKOUT"
    height_pct: float = 0.0
    depth_pct: float = 0.0
    length: int = 0
    ctr: int = 0
    range_pct: float = 0.0
    vol_pct: float = 0.0
    rexp: float = 0.0
    rejection_reason: Optional[str] = None
    # MR-specific fields
    pullback_vol_ratio: Optional[float] = None
    dist_pct: Optional[float] = None
    # BO-specific fields
    max_after_breakout: Optional[float] = None
    min_after_breakout: Optional[float] = None
    # Liquidity / pivot enrichment
    avg_vol_20: float = 0.0
    last_volume: float = 0.0
    avg_dollar_vol_20: float = 0.0
    last_dollar_vol: float = 0.0
    days_above_pivot: int = 0
    distance_from_pivot: float = 0.0


# ── Technical indicator helpers ───────────────────────────────────────────────

def _sma(values: list[float], period: int) -> float:
    if len(values) < period:
        return 0.0
    return sum(values[-period:]) / period


def _ema(values: list[float], period: int) -> float:
    if len(values) < period:
        return 0.0
    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def _ema_series(values: list[float], period: int) -> list[float]:
    """Return the full EMA series (same length as input, 0.0 for insufficient data)."""
    result: list[float] = []
    if len(values) < period:
        return [0.0] * len(values)
    k = 2.0 / (period + 1)
    ema_val = sum(values[:period]) / period
    result.extend([0.0] * (period - 1))
    result.append(ema_val)
    for v in values[period:]:
        ema_val = v * k + ema_val * (1 - k)
        result.append(ema_val)
    return result


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1 + rs))


def _bollinger(closes: list[float], period: int = 20, num_std: float = 2.0) -> tuple[float, float, float]:
    if len(closes) < period:
        mid = closes[-1] if closes else 0.0
        return mid, mid, mid
    window = closes[-period:]
    mid = sum(window) / period
    variance = sum((x - mid) ** 2 for x in window) / period
    std = math.sqrt(variance)
    return mid, mid - num_std * std, mid + num_std * std


def _atr(bars: list[dict], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs = [max(b['high'] - b['low'], abs(b['high'] - bars[i-1]['close']), abs(b['low'] - bars[i-1]['close'])) for i, b in enumerate(bars) if i > 0]
    if not trs:
        return 0.0
    if len(trs) < period:
        return statistics.mean(trs)
    atr_val = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr_val = (atr_val * (period - 1) + tr) / period
    return atr_val


def _current_bar_expansion_metrics(bars: list[dict], lookback: int = 20) -> tuple[float, float, float]:
    if not bars:
        return 0.0, 0.0, 0.0
    current = bars[-1]
    current_close = float(current.get("close", 0.0) or 0.0)
    current_high = float(current.get("high", current_close) or current_close)
    current_low = float(current.get("low", current_close) or current_close)
    current_range = max(0.0, current_high - current_low)
    range_pct = (current_range / current_close * 100.0) if current_close > 0 else 0.0

    prev_bars = bars[-(lookback + 1):-1] if len(bars) > 1 else []
    prev_ranges = [
        max(0.0, float(b.get("high", 0.0) or 0.0) - float(b.get("low", 0.0) or 0.0))
        for b in prev_bars
    ]
    prev_ranges = [r for r in prev_ranges if r > 0]
    avg_range = statistics.mean(prev_ranges) if prev_ranges else 0.0
    rexp = (current_range / avg_range) if avg_range > 0 and current_range > 0 else 0.0

    current_vol = float(current.get("volume", 0.0) or 0.0)
    prev_vols = [float(b.get("volume", 0.0) or 0.0) for b in prev_bars]
    prev_vols = [v for v in prev_vols if v > 0]
    avg_vol = statistics.mean(prev_vols) if prev_vols else 0.0
    vol_pct = (((current_vol / avg_vol) - 1.0) * 100.0) if avg_vol > 0 and current_vol > 0 else 0.0

    return round(range_pct, 2), round(vol_pct, 2), round(rexp, 2)


def _swing_low(bars: list[dict], lookback: int = 10) -> float:
    lows = [b.get("low", b.get("close", 0.0)) for b in bars[-lookback:] if b.get("low", b.get("close", 0.0)) > 0]
    return min(lows) if lows else 0.0


def _is_hammer(bar: dict, atr: float) -> bool:
    o, h, lo, c = bar.get("open", 0.0), bar.get("high", 0.0), bar.get("low", 0.0), bar.get("close", 0.0)
    if o <= 0 or h <= lo: return False
    body = abs(c - o)
    if body <= 0: return False
    lower_shadow = min(o, c) - lo
    upper_shadow = h - max(o, c)
    return (lower_shadow >= 2.0 * body and upper_shadow <= body and c > (lo + (h - lo) * 0.5))


def _is_bullish_engulfing(bar: dict, prev_bar: dict) -> bool:
    po, pc = prev_bar.get("open", 0.0), prev_bar.get("close", 0.0)
    co, cc = bar.get("open", 0.0), bar.get("close", 0.0)
    if pc <= 0 or cc <= 0: return False
    return pc < po and cc > co and co <= pc and cc >= po


def _is_inside_bar_breakout(bar: dict, prev_bar: dict, two_bars_ago: dict) -> bool:
    p2_high, p2_low = two_bars_ago.get("high", 0.0), two_bars_ago.get("low", 0.0)
    p_high, p_low = prev_bar.get("high", 0.0), prev_bar.get("low", 0.0)
    c_close, c_high = bar.get("close", 0.0), bar.get("high", 0.0)
    if p2_high <= 0: return False
    inside = p_high <= p2_high and p_low >= p2_low
    breakout = c_close > p2_high or c_high > p2_high
    return inside and breakout


def _rating_from_score(score: float) -> str:
    if score >= 80: return "A+"
    if score >= 65: return "A"
    if score >= 50: return "B"
    if score >= 35: return "C"
    return "D"


def _is_ipo_stock(bars: list[dict], timeframe: str) -> bool:
    """Return True if the stock has limited trading history (IPO / recently listed)."""
    threshold = 26 if (timeframe or "daily").strip().lower() == "weekly" else 126
    return len(bars) < threshold


def _ipo_trend_ma(closes: list[float], params: dict) -> float:
    """Return the best available trend MA for IPO-friendly validation.

    For stocks with enough history, use sma_long (200).
    For IPOs, fall back to sma_med (50), then sma_short (20), then 0.
    """
    sma_long = int(params["sma_long"])
    sma_med = int(params["sma_med"])
    sma_short = int(params["sma_short"])
    ma = _sma(closes, sma_long)
    if ma > 0:
        return ma
    ma = _sma(closes, sma_med)
    if ma > 0:
        return ma
    ma = _sma(closes, sma_short)
    return ma


# ── Setup detectors ───────────────────────────────────────────────────────────

def detect_mean_reversion(
    symbol: str,
    bars: list[dict],
    timeframe: str,
    params: dict,
    account_size: float,
    base_risk_pct: float,
    min_price_floor: float,
) -> Optional[TradeSignal]:
    """Detects mean reversion setups."""
    sma_short_period = int(params["sma_short"])
    sma_med_period = int(params["sma_med"])
    sma_long_period = int(params["sma_long"])
    bb_period_eff = int(params["bb_period"])
    atr_period_eff = int(params["atr_period"])
    pullback_window_eff = int(params["pullback_window"])

    ipo = _is_ipo_stock(bars, timeframe)
    ipo_params = _timeframe_params(timeframe, ipo_mode=True) if ipo else params
    if len(bars) < int(ipo_params["min_bars"]): return None

    closes = [b["close"] for b in bars]
    volumes = [b.get("volume", 0.0) for b in bars]

    sma20 = _sma(closes, sma_short_period)
    sma50 = _sma(closes, sma_med_period)
    sma200 = _sma(closes, sma_long_period)
    trend_ma = _ipo_trend_ma(closes, params) if ipo else sma200
    rsi_val = _rsi(closes[-(max(_DEFAULT_RSI_PERIOD + 50, sma_med_period + 10)):], _DEFAULT_RSI_PERIOD)
    bb_mid, bb_lower, bb_upper = _bollinger(closes[-(max(60, bb_period_eff + 20)):], bb_period_eff, _DEFAULT_BB_STD)
    atr_val = _atr(bars[-(atr_period_eff + 20):], atr_period_eff)

    current_close = closes[-1]
    if current_close < min_price_floor or trend_ma <= 0 or current_close < trend_ma * 0.95:
        return None

    # Volume analysis
    avg_vol_20 = _sma(volumes[-21:-1], 20) if len(volumes) >= 21 else _sma(volumes, len(volumes))
    pullback_vol_recent = _sma(volumes[-(pullback_window_eff + 1):-1], pullback_window_eff) if len(volumes) > pullback_window_eff else avg_vol_20
    vol_ratio = (volumes[-1] / avg_vol_20) if avg_vol_20 > 0 else 1.0
    pullback_vol_ratio = (pullback_vol_recent / avg_vol_20) if avg_vol_20 > 0 else 1.0
    # Dollar volume (price * volume)
    dollar_vols = [c * v for c, v in zip(closes, volumes)]
    avg_dollar_vol_20 = _sma(dollar_vols[-21:-1], 20) if len(dollar_vols) >= 21 else _sma(dollar_vols, len(dollar_vols))

    # Pullback detection
    recent_rsis = [_rsi(closes[-(max(_DEFAULT_RSI_PERIOD + 50, sma_med_period + 10) + i): -i], _DEFAULT_RSI_PERIOD) for i in range(pullback_window_eff, 0, -1)]
    recent_closes = closes[-(pullback_window_eff + 1):-1]
    recent_lowers = [_bollinger(closes[-(max(60, bb_period_eff + 20) + i):-i], bb_period_eff, _DEFAULT_BB_STD)[1] for i in range(pullback_window_eff, 0, -1)]

    rsi_dipped_below_40 = any(r < 40 for r in recent_rsis) or rsi_val < 40
    rsi_dipped_below_30 = any(r < 30 for r in recent_rsis) or rsi_val < 30
    price_crossed_lower_bb = any(c <= lb * 1.01 for c, lb in zip(recent_closes, recent_lowers)) or current_close <= bb_lower * 1.01
    price_below_sma20 = any(c < sma20 * 0.995 for c in recent_closes) or (current_close < sma20 * 1.01)

    # Signal detection
    bullish_reversal_bar = current_close >= closes[-2] or bars[-1]['close'] >= bars[-1]['open']
    subtype = None
    if price_crossed_lower_bb and current_close > bb_lower * 0.995 and current_close <= bb_mid * 1.05 and rsi_dipped_below_40:
        subtype = "BB_BOUNCE"
    elif rsi_dipped_below_30 and rsi_val >= 30 and bullish_reversal_bar:
        subtype = "OVERSOLD_SNAP"
    elif price_below_sma20 and rsi_dipped_below_40 and current_close >= sma20 * 0.995 and bullish_reversal_bar:
        subtype = "MA_RECLAIM"

    if not subtype: return None

    # Scoring
    score = 0.0
    if current_close > sma200: score += 25.0 + (5.0 if current_close > sma200 * 1.05 else 0)
    if current_close > sma50: score += 15.0
    elif current_close > sma50 * 0.98: score += 8.0
    if 25 <= rsi_val <= 45: score += 20.0
    elif 20 <= rsi_val < 25 or 45 < rsi_val <= 55: score += 10.0
    if current_close <= bb_lower: score += 15.0
    elif current_close <= bb_mid * 1.05 and bb_upper > bb_lower:
        score += max(0.0, (1.0 - ((current_close - bb_lower) / ((bb_upper - bb_lower) / 2.0))) * 10.0)
    if pullback_vol_ratio < 0.70: score += 10.0
    elif pullback_vol_ratio < 0.85: score += 5.0
    if _is_hammer(bars[-1], atr_val) or _is_bullish_engulfing(bars[-1], bars[-2]) or _is_inside_bar_breakout(bars[-1], bars[-2], bars[-3]): score += 10.0
    elif current_close > closes[-2]: score += 4.0
    if vol_ratio >= 0.80: score += 5.0

    # Trade Plan
    if atr_val <= 0: return None
    entry = current_close + 0.10 * atr_val
    sl = max(_swing_low(bars, 10) - 0.50 * atr_val, current_close - 2.0 * atr_val)
    if sl >= entry or entry <= 0 or sl <= 0: return None
    risk = entry - sl
    shares = max(1, int(math.floor((account_size * base_risk_pct) / risk)))
    t1 = max(sma20, entry + risk)
    t2 = t1 + risk
    t3 = max(bb_upper, entry + 3 * risk)

    # Final metrics
    bb_range = (bb_upper - bb_lower) if (bb_upper > bb_lower) else 1.0
    bb_pct = ((current_close - bb_lower) / bb_range) * 100.0
    recent_high = max(b.get("high", b.get("close", 0.0)) for b in bars[-20:])
    pullback_depth_pct = round(((recent_high - current_close) / recent_high * 100.0) if recent_high > 0 else 0.0, 2)
    bb_width_pct = round((bb_upper - bb_lower) / bb_mid * 100.0 if bb_mid > 0 else 0.0, 2)
    dist_pct = round(((sma20 - current_close) / current_close * 100.0) if current_close > 0 and sma20 > current_close else 0.0, 2)
    current_range_pct, current_vol_pct, current_rexp = _current_bar_expansion_metrics(bars)
    vol_pct = round((vol_ratio - 1.0) * 100.0, 2) if avg_vol_20 > 0 else current_vol_pct
    bars_since_below = next((i for i, b in enumerate(reversed(bars[:-1])) if b.get("close", 0.0) < sma20), len(bars)-1)
    # Days above pivot (consecutive from latest)
    days_above = 0
    for x in reversed(closes):
        if x >= sma20:
            days_above += 1
        else:
            break

    distance_from_pivot = ((current_close - sma20) / sma20 * 100.0) if sma20 > 0 else 0.0

    return TradeSignal(
        symbol=symbol, subtype=subtype, setup=_SETUP_TYPE_MR, window=timeframe.upper(), rating=_rating_from_score(score),
        score=round(score, 2), close=round(current_close, 4), entry=round(entry, 4), sl=round(sl, 4),
        pivot=round(sma20, 4), T1=round(t1, 4), T2=round(t2, 4), T3=round(t3, 4), shares=shares,
        rsi=round(rsi_val, 2), sma20=round(sma20, 4), sma50=round(sma50, 4), sma200=round(sma200, 4),
        atr=round(atr_val, 4), lower_bb=round(bb_lower, 4), upper_bb=round(bb_upper, 4), bb_pct=round(bb_pct, 2),
        vol_ratio=round(vol_ratio, 3), pullback_vol_ratio=round(pullback_vol_ratio, 3), dist_pct=dist_pct,
        height_pct=pullback_depth_pct, depth_pct=bb_width_pct, length=bars_since_below,
        range_pct=current_range_pct, vol_pct=vol_pct, rexp=current_rexp,
        avg_vol_20=round(avg_vol_20, 2), last_volume=round(volumes[-1], 2), avg_dollar_vol_20=round(avg_dollar_vol_20, 2), last_dollar_vol=round(dollar_vols[-1], 2),
        days_above_pivot=days_above, distance_from_pivot=round(distance_from_pivot, 2)
    )


def detect_breakout(
    symbol: str,
    bars: list[dict],
    timeframe: str,
    params: dict,
    account_size: float,
    base_risk_pct: float,
    min_price_floor: float,
) -> Optional[TradeSignal]:
    """Detects breakout setups and tracks post-breakout highs/lows.

    Improvements:
    - Search for a breakout that may have occurred within the last few bars (not only on the last bar)
    - Accept breakouts that had a mild pullback as long as the lowest low since the breakout
      remains above the breakout level (i.e., 'pullback still above breakout day high')
    - Populate breakoutDate, max_after_breakout, min_after_breakout and subtype
    """
    ipo = _is_ipo_stock(bars, timeframe)
    ipo_params = _timeframe_params(timeframe, ipo_mode=True) if ipo else params
    if len(bars) < int(ipo_params["min_bars"]):
        return None

    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    volumes = [float(b.get("volume", 0.0)) for b in bars]
    sma50 = _sma(closes, int(params["sma_med"]))
    sma200 = _sma(closes, int(params["sma_long"]))
    trend_ma = _ipo_trend_ma(closes, params) if ipo else sma200
    atr_val = _atr(bars[-(int(params["atr_period"]) + 20):], int(params["atr_period"]))
    current_close = closes[-1]
    current_high = highs[-1]
    current_low = lows[-1]

    if current_close < min_price_floor or trend_ma <= 0 or current_close < trend_ma * 0.95:
        return None

    # Parameters for breakout detection
    lookback = 20                     # how many bars to consider for the prior high
    search_back = 5                   # how many recent bars to search for a breakout bar
    pullback_tolerance = 0.01         # allow up to 1% retest below breakout level and still accept

    # Helper to compute prior high before an index
    def prior_high_before(idx: int) -> float:
        start = max(0, idx - lookback)
        return max(highs[start:idx]) if idx > start else 0.0

    breakout_idx = None
    breakout_level = None  # prior high that was breached
    breakout_bar_high = None

    # Search for a breakout within the last `search_back` bars (including the last bar)
    for offset in range(search_back, 0, -1):
        idx = len(bars) - offset  # index of candidate breakout bar
        if idx <= 0:
            continue
        prior_high = prior_high_before(idx)
        if prior_high <= 0:
            continue
        bar_high = highs[idx]
        bar_close = closes[idx]
        # breakout if bar's close or high breached the prior high
        if bar_close > prior_high or bar_high > prior_high:
            breakout_idx = idx
            breakout_level = prior_high
            breakout_bar_high = max(bar_high, bar_close)
            break

    if breakout_idx is None:
        # No recent breakout found
        return None

    # Evaluate post-breakout behaviour (from breakout bar up to current)
    post_lows = lows[breakout_idx:]
    post_highs = highs[breakout_idx:]
    min_after = min(post_lows) if post_lows else current_low
    max_after = max(post_highs) if post_highs else current_high

    # Acceptance logic (broadened): allow the breakout when ANY of the
    # following is true:
    #  - The lowest low since breakout stayed above the PRIOR breakout level
    #  - The current price remains above the prior breakout level (still holding)
    #  - The instrument made follow-through after breakout (max_after cleared the breakout bar high)
    #  - The lowest low stayed above the breakout BAR high within a small tolerance
    if breakout_level is None:
        return None

    held_above_prior = min_after >= breakout_level * (1.0 - pullback_tolerance)
    current_above_prior = current_close >= breakout_level
    follow_through = (max_after is not None and breakout_bar_high is not None and max_after >= breakout_bar_high)
    held_above_breakout_bar = breakout_bar_high is not None and min_after >= breakout_bar_high * (1.0 - pullback_tolerance)

    if not (held_above_prior or current_above_prior or follow_through or held_above_breakout_bar):
        # breakout failed or pulled back too far without follow-through
        return None

    # Entry and stop: use breakout level as a reference
    # Entry slightly above breakout_level (or current_close if higher)
    entry = max(current_close, breakout_level * 1.005)
    # SL is below the lowest low since breakout (conservative) or 2*ATR below entry
    sl_candidate = min_after - 0.5 * atr_val if atr_val > 0 else min_after
    sl = min(sl_candidate, entry - 2 * atr_val) if atr_val > 0 else sl_candidate

    if sl >= entry or entry <= 0 or sl <= 0:
        return None

    risk = entry - sl
    shares = max(1, int(math.floor((account_size * base_risk_pct) / risk)))

    # Score: reward clean breakouts, follow-through, and staying above prior high
    score = 50.0
    # bonus if current price significantly cleared prior high
    if current_close > breakout_level * 1.03:
        score += 15.0
    elif current_close > breakout_level * 1.01:
        score += 8.0
    # trend context
    if current_close > sma50:
        score += 8.0
    if current_close > sma200:
        score += 7.0
    # volume confirmation relative to recent average
    avg_vol_20 = _sma(volumes[-21:-1], 20) if len(volumes) >= 21 else _sma(volumes, len(volumes))
    if avg_vol_20 > 0 and volumes[-1] > 1.5 * avg_vol_20:
        score += 10.0
    elif avg_vol_20 > 0 and volumes[-1] > 1.2 * avg_vol_20:
        score += 4.0

    # Dollar volume (price * volume)
    dollar_vols = [c * v for c, v in zip(closes, volumes)]
    avg_dollar_vol_20 = _sma(dollar_vols[-21:-1], 20) if len(dollar_vols) >= 21 else _sma(dollar_vols, len(dollar_vols))


    current_range_pct, current_vol_pct, current_rexp = _current_bar_expansion_metrics(bars)

    # Compose TradeSignal with breakout-specific fields populated
    subtype = "BREAKOUT_RETEST" if min_after < breakout_bar_high else "BREAKOUT"
    sig = TradeSignal(
        symbol=symbol,
        subtype=subtype,
        setup=_SETUP_TYPE_BO,
        window=timeframe.upper(),
        rating=_rating_from_score(score),
        score=round(score, 2),
        close=round(current_close, 4),
        entry=round(entry, 4),
        sl=round(sl, 4),
        shares=shares,
        atr=round(atr_val, 4),
        sma50=round(sma50, 4),
        sma200=round(sma200, 4),
        pivot=round(breakout_level, 4),
        range_pct=current_range_pct,
        vol_pct=current_vol_pct,
        rexp=current_rexp,
        # breakout-specific
        max_after_breakout=round(max_after, 4),
        min_after_breakout=round(min_after, 4),
        # liquidity/pivot enrichment
        avg_vol_20=round(avg_vol_20, 2),
        last_volume=round(volumes[-1], 2),
        avg_dollar_vol_20=round(avg_dollar_vol_20, 2),
        last_dollar_vol=round(dollar_vols[-1], 2),
        days_above_pivot=(sum(1 for x in closes[-20:] if breakout_level and x >= breakout_level)),
        distance_from_pivot=round(((current_close - breakout_level) / breakout_level * 100.0) if breakout_level and breakout_level > 0 else 0.0, 2),
    )

    # Attach breakoutDate as an attribute passed-through in dict conversion
    # We'll add breakoutDate to the dataclass via dynamic attribute so _signal_to_dict can pick it up
    try:
        sig.breakoutDate = bars[breakout_idx]["date"]
    except Exception:
        sig.breakoutDate = None

    return sig


def detect_breakout_pullback(
    symbol: str,
    bars: list[dict],
    timeframe: str,
    params: dict,
    account_size: float,
    base_risk_pct: float,
    min_price_floor: float,
) -> Optional[TradeSignal]:
    """
    First Pullback After Breakout (BREAKOUT_PULLBACK / ABFP) setup.

    Identifies stocks that:
    1. Had a confirmed breakout 5–50 bars ago (closed above a 20-bar high on volume).
    2. Made follow-through highs after the breakout (breakout was "real").
    3. Are now in a FIRST controlled pullback (3–25 bars, 2–15 % depth).
    4. Pullback is holding ABOVE the original breakout level (former resistance → support).
    5. Volume is drying up during the pullback (healthy consolidation).

    Entry logic:
    - Enter just above current price as price firms up.
    - Stop below the breakout level (the support line) - 0.5 ATR.
    - T1 at the prior post-breakout peak; T2/T3 project beyond it.
    """
    ipo = _is_ipo_stock(bars, timeframe)
    ipo_params = _timeframe_params(timeframe, ipo_mode=True) if ipo else params
    if len(bars) < int(ipo_params["min_bars"]):
        return None

    closes  = [float(b["close"])          for b in bars]
    highs   = [float(b["high"])           for b in bars]
    lows    = [float(b["low"])            for b in bars]
    volumes = [float(b.get("volume", 0.0)) for b in bars]

    sma50   = _sma(closes, int(params["sma_med"]))
    sma200  = _sma(closes, int(params["sma_long"]))
    trend_ma = _ipo_trend_ma(closes, params) if ipo else sma200
    atr_val = _atr(bars[-(int(params["atr_period"]) + 20):], int(params["atr_period"]))
    current_close = closes[-1]

    if current_close < min_price_floor or trend_ma <= 0 or current_close < trend_ma * 0.90:
        return None

    avg_vol_20 = _sma(volumes[-21:-1], 20) if len(volumes) >= 21 else _sma(volumes, len(volumes))
    if avg_vol_20 <= 0:
        return None

    # ── Step 1: Find a confirmed breakout 5–50 bars ago ──────────────────────
    BO_MIN, BO_MAX = 5, 50
    n = len(bars)

    breakout_idx          = None
    breakout_level        = None
    breakout_bar_vol_ratio = 0.0

    for offset in range(BO_MIN, min(BO_MAX + 1, n - 24)):
        idx = n - offset
        if idx < 21:
            continue
        prior_high = max(highs[max(0, idx - 20):idx])
        if prior_high <= 0:
            continue
        bar_close  = closes[idx]
        bar_high   = highs[idx]
        bar_vol    = volumes[idx]
        pre_avg    = _sma(volumes[max(0, idx - 21):idx - 1], min(20, idx - 1)) if idx >= 2 else 0.0
        vol_at_bo  = bar_vol / pre_avg if pre_avg > 0 else 1.0
        # Breakout: bar cleared prior resistance on above-average volume
        if (bar_close > prior_high * 1.003 or bar_high > prior_high * 1.003) and vol_at_bo >= 1.1:
            breakout_idx           = idx
            breakout_level         = prior_high
            breakout_bar_vol_ratio = vol_at_bo
            break  # most-recent qualifying breakout

    if breakout_idx is None:
        return None

    # ── Step 2: Confirm post-breakout follow-through ──────────────────────────
    post_start  = breakout_idx + 1
    post_n      = n - post_start
    if post_n < 3:
        return None

    post_highs  = highs[post_start:]
    post_lows   = lows[post_start:]
    post_closes = closes[post_start:]
    post_vols   = volumes[post_start:]

    peak_high             = max(post_highs)
    peak_local_idx        = post_highs.index(peak_high)
    breakout_bar_high     = highs[breakout_idx]

    # Follow-through requires peak at least 1 % above the breakout bar's high
    if peak_high < breakout_bar_high * 1.01:
        return None

    # ── Step 3: Confirm first controlled pullback ─────────────────────────────
    bars_since_peak     = post_n - 1 - peak_local_idx
    pullback_depth_pct  = (peak_high - current_close) / peak_high if peak_high > 0 else 0.0

    if pullback_depth_pct < 0.02 or pullback_depth_pct > 0.15:
        return None
    if bars_since_peak < 3 or bars_since_peak > 25:
        return None
    # Must still be above the breakout support level
    if current_close < breakout_level * 0.985:
        return None
    # Low of current bar must not violate support
    if lows[-1] < breakout_level * 0.97:
        return None

    # ── Step 4: Volume dry-up during pullback ─────────────────────────────────
    pullback_vols      = post_vols[peak_local_idx:]
    pullback_vol_avg   = statistics.mean(pullback_vols) if pullback_vols else avg_vol_20
    pullback_vol_ratio = pullback_vol_avg / avg_vol_20 if avg_vol_20 > 0 else 1.0
    vol_dry_up         = pullback_vol_ratio < 0.85

    # ── Step 5: Scoring ───────────────────────────────────────────────────────
    score = 50.0

    if current_close > sma50:  score += 8.0
    if current_close > sma200: score += 8.0

    # Original breakout volume quality
    if breakout_bar_vol_ratio >= 2.0:   score += 12.0
    elif breakout_bar_vol_ratio >= 1.5: score += 8.0
    elif breakout_bar_vol_ratio >= 1.2: score += 4.0

    # Volume dry-up during pullback (most important quality indicator)
    if vol_dry_up:                     score += 12.0
    elif pullback_vol_ratio < 1.0:     score += 5.0

    # Shallow pullback (tighter = more bullish)
    if pullback_depth_pct < 0.05:      score += 8.0
    elif pullback_depth_pct < 0.08:    score += 4.0

    # Proximity to breakout level (near support = lower-risk entry)
    dist_from_bo = (current_close - breakout_level) / breakout_level if breakout_level > 0 else 0.1
    if dist_from_bo < 0.03:   score += 5.0
    elif dist_from_bo < 0.06: score += 2.0

    # Shorter pullback duration is more bullish
    if bars_since_peak <= 8:    score += 5.0
    elif bars_since_peak <= 15: score += 2.0

    # Current bar not collapsing
    if closes[-1] >= closes[-2] * 0.998: score += 2.0

    # ── Step 6: Trade plan ────────────────────────────────────────────────────
    if atr_val <= 0:
        return None

    entry = current_close + 0.15 * atr_val
    sl    = breakout_level - 0.5 * atr_val
    if sl <= 0 or sl >= entry:
        sl = entry - 2.0 * atr_val
    if sl >= entry or entry <= 0 or sl <= 0:
        return None

    risk   = entry - sl
    shares = max(1, int(math.floor((account_size * base_risk_pct) / risk)))

    t1 = max(peak_high,          entry + risk)
    t2 = max(peak_high * 1.05,   entry + 2 * risk)
    t3 = entry + 3 * risk

    # ── Step 7: Build signal ──────────────────────────────────────────────────
    dollar_vols       = [c * v for c, v in zip(closes, volumes)]
    avg_dollar_vol_20 = _sma(dollar_vols[-21:-1], 20) if len(dollar_vols) >= 21 else _sma(dollar_vols, len(dollar_vols))
    min_after         = min(post_lows) if post_lows else lows[-1]
    days_above_pivot  = sum(1 for x in closes[-20:] if breakout_level and x >= breakout_level)
    run_from_bo_pct   = (peak_high - breakout_level) / breakout_level * 100.0 if breakout_level > 0 else 0.0

    current_range_pct, current_vol_pct, current_rexp = _current_bar_expansion_metrics(bars)

    sig = TradeSignal(
        symbol=symbol,
        subtype="FIRST_PULLBACK",
        setup=_SETUP_TYPE_ABFP,
        window=timeframe.upper(),
        rating=_rating_from_score(score),
        score=round(score, 2),
        close=round(current_close, 4),
        entry=round(entry, 4),
        sl=round(sl, 4),
        pivot=round(breakout_level, 4),
        T1=round(t1, 4),
        T2=round(t2, 4),
        T3=round(t3, 4),
        shares=shares,
        atr=round(atr_val, 4),
        sma50=round(sma50, 4),
        sma200=round(sma200, 4),
        max_after_breakout=round(peak_high, 4),
        min_after_breakout=round(min_after, 4),
        avg_vol_20=round(avg_vol_20, 2),
        last_volume=round(volumes[-1], 2),
        avg_dollar_vol_20=round(avg_dollar_vol_20, 2),
        last_dollar_vol=round(dollar_vols[-1], 2),
        days_above_pivot=days_above_pivot,
        distance_from_pivot=round(dist_from_bo * 100.0, 2),
        height_pct=round(pullback_depth_pct * 100.0, 2),  # depth of pullback from post-breakout peak
        depth_pct=round(run_from_bo_pct, 2),               # run from BO level to peak (extension)
        range_pct=current_range_pct,
        vol_pct=current_vol_pct,
        rexp=current_rexp,
        vol_ratio=round(volumes[-1] / avg_vol_20 if avg_vol_20 > 0 else 1.0, 3),
        pullback_vol_ratio=round(pullback_vol_ratio, 3),
        length=bars_since_peak,
    )

    try:
        sig.breakoutDate = bars[breakout_idx]["date"]
    except Exception:
        sig.breakoutDate = None

    return sig


def detect_bull_flag(
    symbol: str,
    bars: list[dict],
    timeframe: str,
    params: dict,
    account_size: float,
    base_risk_pct: float,
    min_price_floor: float,
) -> Optional[TradeSignal]:
    """
    Bull Flag (BULL_FLAG) setup detector.

    Three-phase pattern:
    ┌─────────────────────────────────────────────────────────────────────┐
    │ Phase 1 – Flagpole                                                   │
    │   Sharp upward impulse: ≥10 % gain in 3–25 bars, above-avg volume.  │
    │   Majority (≥50 %) of pole bars close up.                           │
    │                                                                     │
    │ Phase 2 – Flag (Consolidation Channel)                              │
    │   5–30 bar tight consolidation after the pole top.                  │
    │   • Slope slightly negative to flat  (-1.5 % to +0.5 % / bar)      │
    │   • Retraces ≤ 50 % of the pole height                             │
    │   • Current close ≤ 15 % below the pole top                        │
    │   • Volume dries up  (flag avg vol < 85 % of 20-bar avg)           │
    │   • Candle ranges narrow vs. the pre-flag bars (tightness_ratio)   │
    │                                                                     │
    │ Phase 3 – Breakout signal                                           │
    │   Price is in the upper half of the flag channel, or within 3 %    │
    │   of the flag high, signalling imminent continuation.               │
    └─────────────────────────────────────────────────────────────────────┘

    Trade plan
    ──────────
    Entry  : just above the flag high (breakout trigger level)
    Stop   : below the flag low  − 0.5 × ATR
    T1/T2/T3: classic flagpole measured-move projections (50 / 75 / 100 % of pole)

    Subtypes
    ────────
    FLAG_BREAKOUT – price is already at/through the flag high
    FLAG_FORMING  – price is approaching the flag high (pre-breakout alert)
    """
    ipo = _is_ipo_stock(bars, timeframe)
    ipo_params = _timeframe_params(timeframe, ipo_mode=True) if ipo else params
    if len(bars) < int(ipo_params["min_bars"]):
        return None

    closes  = [float(b["close"])            for b in bars]
    highs   = [float(b["high"])             for b in bars]
    lows    = [float(b["low"])              for b in bars]
    volumes = [float(b.get("volume", 0.0))  for b in bars]

    sma50   = _sma(closes, int(params["sma_med"]))
    sma200  = _sma(closes, int(params["sma_long"]))
    trend_ma = _ipo_trend_ma(closes, params) if ipo else sma200
    atr_val = _atr(bars[-(int(params["atr_period"]) + 20):], int(params["atr_period"]))
    current_close = closes[-1]

    if current_close < min_price_floor or trend_ma <= 0 or current_close < trend_ma * 0.85:
        return None

    avg_vol_20 = _sma(volumes[-21:-1], 20) if len(volumes) >= 21 else _sma(volumes, len(volumes))
    if avg_vol_20 <= 0:
        return None

    # ── Configuration ────────────────────────────────────────────────────────
    POLE_MIN_GAIN_PCT = 0.08   # flagpole must gain at least 8 %
    POLE_MIN_BARS     = 3      # pole forms in at least 3 bars
    POLE_MAX_BARS     = 30     # pole forms in at most 30 bars
    FLAG_MIN_BARS     = 3      # flag consolidates for at least 3 bars (very tight flags)
    FLAG_MAX_BARS     = 35     # flag consolidates for at most 35 bars
    MAX_RETRACE_PCT   = 0.55   # flag may retrace at most 55 % of pole height
    MAX_DECLINE_PCT   = 0.18   # current close must not drop > 18 % from pole top

    n = len(bars)

    # ── Step 1: Locate the pole top and pole bottom ───────────────────────────
    # The pole top must have formed FLAG_MIN_BARS … FLAG_MAX_BARS+POLE_MAX_BARS
    # bars ago so that a flag has had time to develop after it.
    pole_top_idx      = None
    pole_bottom_idx   = None
    pole_gain_pct     = 0.0
    pole_high         = 0.0
    pole_bottom_price = 0.0

    for pt_offset in range(FLAG_MIN_BARS, FLAG_MAX_BARS + POLE_MAX_BARS + 1):
        pt_idx = n - 1 - pt_offset
        if pt_idx < POLE_MAX_BARS + 1:
            break

        candidate_high = highs[pt_idx]
        # Allow price to be up to 5 % above the pole top — tight flags sit right at the highs
        # and can even have the current price fractionally above the pole bar's high.
        if current_close > candidate_high * 1.05:
            continue

        # Search for a qualifying pole bottom
        for pb_back in range(POLE_MIN_BARS, POLE_MAX_BARS + 1):
            pb_idx = pt_idx - pb_back
            if pb_idx < 0:
                break

            pb_low = lows[pb_idx]
            if pb_low <= 0:
                continue

            gain_pct = (candidate_high - pb_low) / pb_low
            if gain_pct < POLE_MIN_GAIN_PCT:
                continue

            # Quality gate: majority of pole bars should close up
            pole_closes = closes[pb_idx: pt_idx + 1]
            up_bars  = sum(1 for i in range(1, len(pole_closes)) if pole_closes[i] >= pole_closes[i - 1])
            up_ratio = up_bars / (len(pole_closes) - 1) if len(pole_closes) > 1 else 0.0
            if up_ratio < 0.50:
                continue

            pole_top_idx      = pt_idx
            pole_bottom_idx   = pb_idx
            pole_gain_pct     = gain_pct
            pole_high         = candidate_high
            pole_bottom_price = pb_low
            break

        if pole_top_idx is not None:
            break

    if pole_top_idx is None:
        return None

    # ── Step 2: Analyse the flag (pole_top+1 → current bar) ──────────────────
    flag_start_idx = pole_top_idx + 1
    flag_length    = n - flag_start_idx  # bars in the flag (including current)

    if flag_length < FLAG_MIN_BARS or flag_length > FLAG_MAX_BARS:
        return None

    flag_closes = closes  [flag_start_idx:]
    flag_highs  = highs   [flag_start_idx:]
    flag_lows   = lows    [flag_start_idx:]
    flag_vols   = volumes [flag_start_idx:]

    flag_high_val = max(flag_highs)
    flag_low_val  = min(flag_lows)

    # ① Retrace gate: flag low must not exceed 50 % of pole height
    pole_height     = pole_high - pole_bottom_price
    max_allowed_low = pole_high - MAX_RETRACE_PCT * pole_height
    if flag_low_val < max_allowed_low:
        return None

    # ② Decline gate: current close not too far below pole top
    flag_decline_pct = (pole_high - current_close) / pole_high if pole_high > 0 else 0.0
    if flag_decline_pct > MAX_DECLINE_PCT:
        return None

    # ③ Slope gate: flag channel is slightly down to flat (linear regression)
    n_f    = len(flag_closes)
    x_mean = (n_f - 1) / 2.0
    y_mean = sum(flag_closes) / n_f
    denom  = sum((i - x_mean) ** 2 for i in range(n_f))
    slope  = (sum((i - x_mean) * (flag_closes[i] - y_mean) for i in range(n_f)) / denom
              if denom > 0 else 0.0)
    slope_pct_per_bar = slope / current_close if current_close > 0 else 0.0
    # Short flags (≤7 bars) can be steeper; longer flags must be more gradual
    max_decline_slope = -0.045 if flag_length <= 7 else -0.015
    if slope_pct_per_bar < max_decline_slope or slope_pct_per_bar > 0.010:
        return None

    # ④ Volume dry-up inside the flag
    flag_vol_avg   = statistics.mean(flag_vols) if flag_vols else avg_vol_20
    flag_vol_ratio = flag_vol_avg / avg_vol_20 if avg_vol_20 > 0 else 1.0
    vol_dry_up     = flag_vol_ratio < 0.85

    # ⑤ Candle tightness: flag candles narrower than pre-flag bars
    flag_ranges     = [flag_highs[i] - flag_lows[i] for i in range(len(flag_highs))]
    pre_flag_bars_w = bars[max(0, flag_start_idx - 20): flag_start_idx]
    pre_flag_ranges = [float(b["high"]) - float(b["low"]) for b in pre_flag_bars_w]
    flag_avg_range  = statistics.mean(flag_ranges)     if flag_ranges     else atr_val
    pre_avg_range   = statistics.mean(pre_flag_ranges) if pre_flag_ranges else atr_val
    tightness_ratio = flag_avg_range / pre_avg_range if pre_avg_range > 0 else 1.0
    tight_candles   = tightness_ratio < 0.80

    # ── Step 3: Position check – price still inside the flag channel ──────────
    # Accept any bar that hasn't collapsed below the flag low.
    # For short flags (≤7 bars) this is the primary quality gate; longer flags
    # need to be in the upper half to show the base is holding.
    still_in_flag  = current_close >= flag_low_val * 0.995   # within 0.5% of flag low
    above_flag_midpoint = current_close >= (flag_high_val + flag_low_val) / 2.0
    near_flag_top  = current_close >= flag_high_val * 0.95   # within 5% of flag high

    if flag_length <= 7:
        # Short tight flag: just need to still be inside the channel
        if not still_in_flag:
            return None
    else:
        # Longer flag: require price in upper half or close to the flag high
        if not (above_flag_midpoint or near_flag_top):
            return None

    # ── Step 4: Scoring ───────────────────────────────────────────────────────
    score = 45.0

    # Pole strength
    if   pole_gain_pct >= 0.40: score += 15.0
    elif pole_gain_pct >= 0.25: score += 10.0
    elif pole_gain_pct >= 0.10: score +=  5.0

    # Volume dry-up in flag (primary quality indicator)
    if   flag_vol_ratio < 0.60: score += 15.0
    elif flag_vol_ratio < 0.75: score += 10.0
    elif flag_vol_ratio < 0.85: score +=  5.0

    # Candle tightness
    if   tightness_ratio < 0.50: score += 10.0
    elif tightness_ratio < 0.70: score +=  6.0
    elif tight_candles:           score +=  3.0

    # Shallow flag decline (tighter = more bullish)
    if   flag_decline_pct < 0.05: score +=  8.0
    elif flag_decline_pct < 0.10: score +=  4.0

    # Proximity to flag high (near breakout trigger)
    if near_flag_top:         score += 5.0
    elif above_flag_midpoint: score += 2.0

    # Trend context
    if current_close > sma200: score += 5.0
    if current_close > sma50:  score += 3.0

    # Pole volume quality (institutional buying during impulse)
    pole_vols      = volumes[pole_bottom_idx: pole_top_idx + 1]
    pole_vol_avg   = statistics.mean(pole_vols) if pole_vols else avg_vol_20
    pole_vol_ratio = pole_vol_avg / avg_vol_20  if avg_vol_20 > 0 else 1.0
    if   pole_vol_ratio >= 2.0: score += 5.0
    elif pole_vol_ratio >= 1.5: score += 3.0
    elif pole_vol_ratio >= 1.2: score += 1.0

    # ── Step 5: Trade plan ────────────────────────────────────────────────────
    if atr_val <= 0:
        return None

    breakout_level = flag_high_val          # flag high = breakout trigger
    entry          = max(current_close + 0.10 * atr_val, breakout_level * 1.002)
    sl             = flag_low_val - 0.50 * atr_val
    if sl <= 0 or sl >= entry:
        sl = entry - 2.0 * atr_val
    if sl >= entry or entry <= 0 or sl <= 0:
        return None

    risk   = entry - sl
    shares = max(1, int(math.floor((account_size * base_risk_pct) / risk)))

    # Measured-move targets (flagpole height projected from breakout level)
    t1 = entry + pole_height * 0.50   # 50 % of pole  – conservative target
    t2 = entry + pole_height * 0.75   # 75 % of pole
    t3 = entry + pole_height          # full pole projection (textbook measured move)

    # ── Step 6: Build signal ──────────────────────────────────────────────────
    dollar_vols       = [c * v for c, v in zip(closes, volumes)]
    avg_dollar_vol_20 = (_sma(dollar_vols[-21:-1], 20) if len(dollar_vols) >= 21
                         else _sma(dollar_vols, len(dollar_vols)))
    rsi_val           = _rsi(closes[-(max(_DEFAULT_RSI_PERIOD + 50, 60)):], _DEFAULT_RSI_PERIOD)
    current_range_pct, current_vol_pct, current_rexp = _current_bar_expansion_metrics(bars)
    current_vol_ratio = volumes[-1] / avg_vol_20 if avg_vol_20 > 0 else 1.0

    subtype = "FLAG_BREAKOUT" if current_close >= breakout_level * 0.998 else "FLAG_FORMING"

    sig = TradeSignal(
        symbol   = symbol,
        subtype  = subtype,
        setup    = _SETUP_TYPE_BF,
        window   = timeframe.upper(),
        rating   = _rating_from_score(score),
        score    = round(score, 2),
        close    = round(current_close, 4),
        entry    = round(entry, 4),
        sl       = round(sl, 4),
        pivot    = round(breakout_level, 4),   # flag high = breakout level
        T1       = round(t1, 4),
        T2       = round(t2, 4),
        T3       = round(t3, 4),
        shares   = shares,
        atr      = round(atr_val, 4),
        rsi      = round(rsi_val, 2),
        sma50    = round(sma50, 4),
        sma200   = round(sma200, 4),
        vol_ratio          = round(current_vol_ratio, 3),
        pullback_vol_ratio = round(flag_vol_ratio, 3),  # flag vol / avg = dry-up ratio
        # height_pct = pole gain %, depth_pct = flag decline %, length = flag bars
        height_pct = round(pole_gain_pct    * 100.0, 2),
        depth_pct  = round(flag_decline_pct * 100.0, 2),
        length     = flag_length,
        # Reuse max/min_after_breakout for flag high / flag low
        max_after_breakout = round(flag_high_val, 4),
        min_after_breakout = round(flag_low_val,  4),
        # Liquidity / pivot enrichment
        avg_vol_20        = round(avg_vol_20, 2),
        last_volume       = round(volumes[-1], 2),
        avg_dollar_vol_20 = round(avg_dollar_vol_20, 2),
        last_dollar_vol   = round(dollar_vols[-1], 2),
        days_above_pivot  = sum(1 for x in closes[-20:] if x >= breakout_level),
        distance_from_pivot = round(
            ((current_close - breakout_level) / breakout_level * 100.0)
            if breakout_level > 0 else 0.0, 2),
        range_pct = current_range_pct,
        vol_pct   = current_vol_pct,
        rexp      = current_rexp,
    )

    # Dynamic attributes for BF-specific CSV columns
    try:
        sig.bfPoleStartDate = bars[pole_bottom_idx]["date"]
        sig.bfPoleTopDate   = bars[pole_top_idx]["date"]
    except Exception:
        sig.bfPoleStartDate = None
        sig.bfPoleTopDate   = None
    sig.bfTightnessRatio = round(tightness_ratio, 3)
    sig.bfPoleVolRatio   = round(pole_vol_ratio,   3)

    return sig


# ── EMA Pullback detector ────────────────────────────────────────────────────

def detect_ema_pullback(
    symbol: str,
    bars: list[dict],
    timeframe: str,
    params: dict,
    account_size: float,
    base_risk_pct: float,
    min_price_floor: float,
    time_window: int = 5,
) -> Optional[TradeSignal]:
    """
    Detects pullback-to-EMA setups across EMA 5/10/20/50.

    Triggers when price pulls back to within 1 ATR of a rising EMA in an uptrend,
    then shows a bounce (close above the EMA or bullish bar).

    Subtypes: EMA5_BOUNCE, EMA10_BOUNCE, EMA20_BOUNCE, EMA50_BOUNCE
    Priority: shorter EMA bounces (EMA5) require tighter trend; longer (EMA50) = deeper pullback.
    """
    ipo = _is_ipo_stock(bars, timeframe)
    ipo_params = _timeframe_params(timeframe, ipo_mode=True) if ipo else params
    if len(bars) < int(ipo_params["min_bars"]):
        return None

    closes  = [float(b["close"]) for b in bars]
    highs   = [float(b["high"])  for b in bars]
    lows    = [float(b["low"])   for b in bars]
    volumes = [float(b.get("volume", 0.0)) for b in bars]

    sma50  = _sma(closes, int(params["sma_med"]))
    sma200 = _sma(closes, int(params["sma_long"]))
    trend_ma = _ipo_trend_ma(closes, params) if ipo else sma200
    atr_val = _atr(bars[-(int(params["atr_period"]) + 20):], int(params["atr_period"]))
    current_close = closes[-1]

    if current_close < min_price_floor or trend_ma <= 0 or current_close < trend_ma * 0.92:
        return None
    if atr_val <= 0:
        return None

    avg_vol_20 = _sma(volumes[-21:-1], 20) if len(volumes) >= 21 else _sma(volumes, len(volumes))
    if avg_vol_20 <= 0:
        return None

    # Compute EMA series for 5, 10, 20, 50
    ema_periods = [5, 10, 20, 50]
    ema_map: dict[int, list[float]] = {}
    for p in ema_periods:
        ema_map[p] = _ema_series(closes, p)

    # Check each EMA for a pullback bounce within the time_window
    search_range = min(time_window, len(bars) - 1)
    best_subtype = None
    best_ema_period = 0
    best_ema_val = 0.0
    best_score = 0.0

    for ema_p in ema_periods:
        ema_s = ema_map[ema_p]
        if len(ema_s) < 2 or ema_s[-1] <= 0:
            continue
        ema_now = ema_s[-1]
        ema_prev = ema_s[-2] if len(ema_s) >= 2 else ema_now

        # EMA must be rising (bullish trend context for this EMA)
        if ema_now < ema_prev * 0.999:
            continue

        # EMA stack check: shorter EMAs should be >= longer EMAs for strong trend
        # Relaxed for EMA50 (deeper pullback allowed)
        if ema_p <= 20:
            ema20_val = ema_map[20][-1] if len(ema_map[20]) > 0 and ema_map[20][-1] > 0 else 0
            if ema20_val > 0 and current_close < ema20_val * 0.95:
                continue

        # Search within time_window for a touch-and-bounce
        touched = False
        bounced = False
        touch_low = 0.0

        for offset in range(search_range, 0, -1):
            idx = len(bars) - offset
            if idx < 1 or idx >= len(ema_s):
                continue
            bar_low = lows[idx]
            bar_close = closes[idx]
            ema_at_bar = ema_s[idx]
            if ema_at_bar <= 0:
                continue

            # Touch: bar low came within 1 ATR of the EMA (or dipped below it)
            dist_to_ema = bar_low - ema_at_bar
            if dist_to_ema <= atr_val * 1.0 and dist_to_ema >= -atr_val * 0.5:
                touched = True
                touch_low = bar_low

        # Bounce: current close is above the EMA and above the touch low
        if touched and current_close > ema_now and current_close > touch_low:
            bounced = True

        if not (touched and bounced):
            continue

        # Score this EMA pullback
        score = 40.0

        # Trend context
        if current_close > sma200: score += 12.0
        elif current_close > sma200 * 0.97: score += 5.0
        if current_close > sma50: score += 8.0

        # EMA stack quality (all shorter EMAs above longer ones = strong trend)
        ema5_v  = ema_map[5][-1]  if ema_map[5][-1]  > 0 else 0
        ema10_v = ema_map[10][-1] if ema_map[10][-1] > 0 else 0
        ema20_v = ema_map[20][-1] if ema_map[20][-1] > 0 else 0
        ema50_v = ema_map[50][-1] if ema_map[50][-1] > 0 else 0
        if ema5_v > ema10_v > ema20_v > ema50_v > 0:
            score += 15.0  # perfect bullish stack
        elif ema10_v > ema20_v > ema50_v > 0:
            score += 10.0
        elif ema20_v > ema50_v > 0:
            score += 5.0

        # Bounce quality
        if current_close > closes[-2]:
            score += 5.0
        if bars[-1]["close"] > bars[-1]["open"]:  # green candle
            score += 3.0

        # Volume on bounce
        vol_ratio_val = volumes[-1] / avg_vol_20 if avg_vol_20 > 0 else 1.0
        if vol_ratio_val >= 1.3: score += 8.0
        elif vol_ratio_val >= 1.0: score += 4.0

        # RSI not overbought
        rsi_val = _rsi(closes[-(max(_DEFAULT_RSI_PERIOD + 50, 60)):], _DEFAULT_RSI_PERIOD)
        if 35 <= rsi_val <= 60: score += 5.0
        elif rsi_val > 70: score -= 5.0

        # Prefer shorter-EMA bounces (tighter trends)
        if ema_p == 5:  score += 5.0
        elif ema_p == 10: score += 3.0

        if score > best_score:
            best_score = score
            best_ema_period = ema_p
            best_ema_val = ema_now
            best_subtype = f"EMA{ema_p}_BOUNCE"

    if best_subtype is None:
        return None

    # Trade plan
    rsi_val = _rsi(closes[-(max(_DEFAULT_RSI_PERIOD + 50, 60)):], _DEFAULT_RSI_PERIOD)
    entry = current_close + 0.10 * atr_val
    sl = best_ema_val - 1.0 * atr_val
    if sl <= 0 or sl >= entry:
        sl = entry - 2.0 * atr_val
    if sl >= entry or entry <= 0 or sl <= 0:
        return None

    risk = entry - sl
    shares = max(1, int(math.floor((account_size * base_risk_pct) / risk)))

    # Targets based on recent swing highs
    recent_high = max(highs[-20:])
    t1 = max(recent_high, entry + risk)
    t2 = entry + 2.0 * risk
    t3 = entry + 3.0 * risk

    vol_ratio_val = volumes[-1] / avg_vol_20 if avg_vol_20 > 0 else 1.0
    dollar_vols = [c * v for c, v in zip(closes, volumes)]
    avg_dollar_vol_20 = _sma(dollar_vols[-21:-1], 20) if len(dollar_vols) >= 21 else _sma(dollar_vols, len(dollar_vols))
    current_range_pct, current_vol_pct, current_rexp = _current_bar_expansion_metrics(bars)

    dist_pct = round(((current_close - best_ema_val) / best_ema_val * 100.0) if best_ema_val > 0 else 0.0, 2)
    days_above = sum(1 for x in closes[-20:] if x >= best_ema_val)

    sma20 = _sma(closes, int(params["sma_short"]))

    sig = TradeSignal(
        symbol=symbol,
        subtype=best_subtype,
        setup=_SETUP_TYPE_EMA_PB,
        window=timeframe.upper(),
        rating=_rating_from_score(best_score),
        score=round(best_score, 2),
        close=round(current_close, 4),
        entry=round(entry, 4),
        sl=round(sl, 4),
        pivot=round(best_ema_val, 4),
        T1=round(t1, 4),
        T2=round(t2, 4),
        T3=round(t3, 4),
        shares=shares,
        rsi=round(rsi_val, 2),
        sma20=round(sma20, 4),
        sma50=round(sma50, 4),
        sma200=round(sma200, 4),
        atr=round(atr_val, 4),
        vol_ratio=round(vol_ratio_val, 3),
        avg_vol_20=round(avg_vol_20, 2),
        last_volume=round(volumes[-1], 2),
        avg_dollar_vol_20=round(avg_dollar_vol_20, 2),
        last_dollar_vol=round(dollar_vols[-1], 2),
        days_above_pivot=days_above,
        distance_from_pivot=dist_pct,
        height_pct=round(best_ema_period, 2),  # store which EMA
        depth_pct=dist_pct,
        range_pct=current_range_pct,
        vol_pct=current_vol_pct,
        rexp=current_rexp,
    )
    sig.emaPeriod = best_ema_period
    sig.emaValue = round(best_ema_val, 4)
    return sig


# ── Base Breakout detector ───────────────────────────────────────────────────

def detect_base_breakout(
    symbol: str,
    bars: list[dict],
    timeframe: str,
    params: dict,
    account_size: float,
    base_risk_pct: float,
    min_price_floor: float,
    time_window: int = 5,
) -> Optional[TradeSignal]:
    """
    Detects flat base / cup-with-handle breakout setups.

    A proper base breakout differs from a simple 20-bar high break:
    1. Find a consolidation lasting 25–150 bars with depth 10–35%
    2. Verify volume dry-up during the base (avg volume < 80% of pre-base avg)
    3. Confirm price breaking above the base ceiling with volume expansion
    4. The breakout bar (within time_window) clears the base high on above-avg volume

    Subtypes: FLAT_BASE_BO, CUP_BASE_BO
    """
    ipo = _is_ipo_stock(bars, timeframe)
    ipo_params = _timeframe_params(timeframe, ipo_mode=True) if ipo else params
    if len(bars) < int(ipo_params["min_bars"]):
        return None

    closes  = [float(b["close"]) for b in bars]
    highs   = [float(b["high"])  for b in bars]
    lows    = [float(b["low"])   for b in bars]
    volumes = [float(b.get("volume", 0.0)) for b in bars]

    sma50  = _sma(closes, int(params["sma_med"]))
    sma200 = _sma(closes, int(params["sma_long"]))
    trend_ma = _ipo_trend_ma(closes, params) if ipo else sma200
    atr_val = _atr(bars[-(int(params["atr_period"]) + 20):], int(params["atr_period"]))
    current_close = closes[-1]

    if current_close < min_price_floor or trend_ma <= 0 or current_close < trend_ma * 0.85:
        return None
    if atr_val <= 0:
        return None

    avg_vol_20 = _sma(volumes[-21:-1], 20) if len(volumes) >= 21 else _sma(volumes, len(volumes))
    if avg_vol_20 <= 0:
        return None

    n = len(bars)

    # Configuration (daily defaults; weekly uses shorter)
    is_weekly = (timeframe or "daily").strip().lower() == "weekly"
    BASE_MIN_BARS = 5 if is_weekly else 25
    BASE_MAX_BARS = 40 if is_weekly else 150
    BASE_MIN_DEPTH = 0.08   # 8% minimum depth
    BASE_MAX_DEPTH = 0.38   # 38% maximum depth

    # Search for a base pattern ending within time_window of the current bar
    best_base = None

    for bo_offset in range(1, min(time_window + 1, n - BASE_MIN_BARS)):
        bo_idx = n - bo_offset  # candidate breakout bar index

        # Try various base lengths
        for base_len in range(BASE_MIN_BARS, min(BASE_MAX_BARS + 1, bo_idx)):
            base_start = bo_idx - base_len
            if base_start < 1:
                continue

            base_highs = highs[base_start:bo_idx]
            base_lows  = lows[base_start:bo_idx]
            base_vols  = volumes[base_start:bo_idx]

            base_ceiling = max(base_highs)
            base_floor   = min(base_lows)

            if base_ceiling <= 0 or base_floor <= 0:
                continue

            depth = (base_ceiling - base_floor) / base_ceiling
            if depth < BASE_MIN_DEPTH or depth > BASE_MAX_DEPTH:
                continue

            # Verify volume dry-up during base
            pre_base_vols = volumes[max(0, base_start - 20):base_start]
            pre_base_avg = statistics.mean(pre_base_vols) if pre_base_vols else avg_vol_20
            base_vol_avg = statistics.mean(base_vols) if base_vols else avg_vol_20
            base_vol_ratio = base_vol_avg / pre_base_avg if pre_base_avg > 0 else 1.0

            # Breakout confirmation: close or high above ceiling
            bo_close = closes[bo_idx] if bo_idx < n else current_close
            bo_high  = highs[bo_idx] if bo_idx < n else current_close
            bo_vol   = volumes[bo_idx] if bo_idx < n else volumes[-1]

            if bo_close < base_ceiling * 0.995 and bo_high < base_ceiling:
                continue  # no breakout

            # Volume expansion on breakout
            bo_vol_ratio = bo_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0

            # Current price still holding above base ceiling
            if current_close < base_ceiling * 0.97:
                continue

            # Determine subtype
            # Cup pattern: base has a U-shape (mid-point lows are lower than start/end)
            mid_point = len(base_lows) // 2
            first_half_low = min(base_lows[:mid_point]) if mid_point > 0 else base_floor
            second_half_low = min(base_lows[mid_point:]) if mid_point < len(base_lows) else base_floor
            is_cup = (first_half_low < base_ceiling * 0.95 and
                      second_half_low < base_ceiling * 0.95 and
                      abs(base_lows[0] - base_lows[-1]) / base_ceiling < 0.05)
            subtype = "CUP_BASE_BO" if is_cup else "FLAT_BASE_BO"

            best_base = {
                "base_start": base_start, "base_len": base_len,
                "ceiling": base_ceiling, "floor": base_floor,
                "depth": depth, "base_vol_ratio": base_vol_ratio,
                "bo_vol_ratio": bo_vol_ratio, "bo_idx": bo_idx,
                "subtype": subtype,
            }
            break  # found a valid base for this breakout bar

        if best_base is not None:
            break

    if best_base is None:
        return None

    # Scoring
    score = 45.0
    depth = best_base["depth"]
    base_vol_ratio = best_base["base_vol_ratio"]
    bo_vol_ratio = best_base["bo_vol_ratio"]
    base_ceiling = best_base["ceiling"]

    # Trend
    if current_close > sma200: score += 10.0
    if current_close > sma50:  score += 7.0

    # Base quality: volume dry-up
    if base_vol_ratio < 0.60: score += 15.0
    elif base_vol_ratio < 0.75: score += 10.0
    elif base_vol_ratio < 0.85: score += 5.0

    # Breakout volume expansion
    if bo_vol_ratio >= 2.0: score += 15.0
    elif bo_vol_ratio >= 1.5: score += 10.0
    elif bo_vol_ratio >= 1.2: score += 5.0

    # Depth quality (10-20% ideal depth)
    if 0.10 <= depth <= 0.20: score += 8.0
    elif 0.08 <= depth <= 0.25: score += 4.0

    # Base length (longer = more significant)
    if best_base["base_len"] >= 60: score += 5.0
    elif best_base["base_len"] >= 35: score += 3.0

    # Price clearing the ceiling cleanly
    clearance = (current_close - base_ceiling) / base_ceiling if base_ceiling > 0 else 0
    if clearance > 0.03: score += 5.0
    elif clearance > 0.01: score += 2.0

    # Trade plan
    entry = max(current_close, base_ceiling * 1.002) + 0.10 * atr_val
    sl = best_base["floor"] - 0.5 * atr_val
    if sl <= 0 or sl >= entry:
        sl = entry - 2.5 * atr_val
    if sl >= entry or entry <= 0 or sl <= 0:
        return None

    risk = entry - sl
    shares = max(1, int(math.floor((account_size * base_risk_pct) / risk)))
    base_height = base_ceiling - best_base["floor"]
    t1 = entry + base_height * 0.50
    t2 = entry + base_height * 0.75
    t3 = entry + base_height

    rsi_val = _rsi(closes[-(max(_DEFAULT_RSI_PERIOD + 50, 60)):], _DEFAULT_RSI_PERIOD)
    dollar_vols = [c * v for c, v in zip(closes, volumes)]
    avg_dollar_vol_20 = _sma(dollar_vols[-21:-1], 20) if len(dollar_vols) >= 21 else _sma(dollar_vols, len(dollar_vols))
    current_range_pct, current_vol_pct, current_rexp = _current_bar_expansion_metrics(bars)
    vol_ratio_val = volumes[-1] / avg_vol_20 if avg_vol_20 > 0 else 1.0
    sma20 = _sma(closes, int(params["sma_short"]))

    sig = TradeSignal(
        symbol=symbol,
        subtype=best_base["subtype"],
        setup=_SETUP_TYPE_BASE_BO,
        window=timeframe.upper(),
        rating=_rating_from_score(score),
        score=round(score, 2),
        close=round(current_close, 4),
        entry=round(entry, 4),
        sl=round(sl, 4),
        pivot=round(base_ceiling, 4),
        T1=round(t1, 4),
        T2=round(t2, 4),
        T3=round(t3, 4),
        shares=shares,
        rsi=round(rsi_val, 2),
        sma20=round(sma20, 4),
        sma50=round(sma50, 4),
        sma200=round(sma200, 4),
        atr=round(atr_val, 4),
        vol_ratio=round(vol_ratio_val, 3),
        pullback_vol_ratio=round(base_vol_ratio, 3),
        height_pct=round(depth * 100.0, 2),
        depth_pct=round(depth * 100.0, 2),
        length=best_base["base_len"],
        avg_vol_20=round(avg_vol_20, 2),
        last_volume=round(volumes[-1], 2),
        avg_dollar_vol_20=round(avg_dollar_vol_20, 2),
        last_dollar_vol=round(dollar_vols[-1], 2),
        max_after_breakout=round(base_ceiling, 4),
        min_after_breakout=round(best_base["floor"], 4),
        days_above_pivot=sum(1 for x in closes[-20:] if x >= base_ceiling),
        distance_from_pivot=round(clearance * 100.0, 2),
        range_pct=current_range_pct,
        vol_pct=current_vol_pct,
        rexp=current_rexp,
    )
    sig.baseBars = best_base["base_len"]
    sig.baseDepthPct = round(depth * 100.0, 2)
    sig.baseVolDryUp = round(base_vol_ratio, 3)
    sig.boVolExpansion = round(bo_vol_ratio, 3)
    return sig


# ── Follow-Through Day detector ──────────────────────────────────────────────

def detect_follow_through(
    symbol: str,
    bars: list[dict],
    timeframe: str,
    params: dict,
    account_size: float,
    base_risk_pct: float,
    min_price_floor: float,
    time_window: int = 10,
) -> Optional[TradeSignal]:
    """
    Detects Follow-Through Day (FTD) setups.

    An FTD occurs when after a correction (≥5% decline), the stock makes a strong
    up-day (≥1.5% gain with above-average volume) 4–10 days after a rally attempt
    (first day the stock closes up after the correction low).

    This confirms the correction is likely over and a new uptrend is starting.

    Subtypes: FTD_CONFIRMED, FTD_EARLY (rally attempt started but not yet 4+ days)
    """
    ipo = _is_ipo_stock(bars, timeframe)
    ipo_params = _timeframe_params(timeframe, ipo_mode=True) if ipo else params
    if len(bars) < int(ipo_params["min_bars"]):
        return None

    closes  = [float(b["close"]) for b in bars]
    highs   = [float(b["high"])  for b in bars]
    lows    = [float(b["low"])   for b in bars]
    volumes = [float(b.get("volume", 0.0)) for b in bars]

    sma50  = _sma(closes, int(params["sma_med"]))
    sma200 = _sma(closes, int(params["sma_long"]))
    atr_val = _atr(bars[-(int(params["atr_period"]) + 20):], int(params["atr_period"]))
    current_close = closes[-1]

    if current_close < min_price_floor or atr_val <= 0:
        return None

    avg_vol_20 = _sma(volumes[-21:-1], 20) if len(volumes) >= 21 else _sma(volumes, len(volumes))
    if avg_vol_20 <= 0:
        return None

    n = len(bars)

    # Step 1: Find a recent correction (peak → trough, ≥5% decline)
    # Look back up to 60 bars for the correction trough
    CORRECTION_MIN_PCT = 0.05
    CORRECTION_LOOKBACK = 60

    correction_low_idx = None
    correction_low = None
    pre_correction_high = None

    for trough_offset in range(time_window, min(CORRECTION_LOOKBACK, n - 20)):
        trough_idx = n - 1 - trough_offset
        if trough_idx < 20:
            break
        trough_val = lows[trough_idx]

        # Find the peak before this trough
        peak_range = highs[max(0, trough_idx - 40):trough_idx]
        if not peak_range:
            continue
        peak_val = max(peak_range)

        decline_pct = (peak_val - trough_val) / peak_val if peak_val > 0 else 0
        if decline_pct >= CORRECTION_MIN_PCT:
            # Verify this is actually a local low (lower than neighbors)
            neighbor_lows = lows[max(0, trough_idx - 2):min(n, trough_idx + 3)]
            if trough_val <= min(neighbor_lows) * 1.005:
                correction_low_idx = trough_idx
                correction_low = trough_val
                pre_correction_high = peak_val
                break

    if correction_low_idx is None:
        return None

    # Step 2: Find the rally attempt day (first close-up day after correction low)
    rally_attempt_idx = None
    for i in range(correction_low_idx + 1, min(n, correction_low_idx + 15)):
        if closes[i] > closes[i - 1]:
            rally_attempt_idx = i
            break

    if rally_attempt_idx is None:
        return None

    # Step 3: Check for FTD within 4–10 days after rally attempt
    days_since_rally = (n - 1) - rally_attempt_idx
    last_bar_idx = n - 1

    # FTD criteria: ≥1.5% gain on above-average volume, 4–10 days after rally attempt
    ftd_idx = None
    subtype = "FTD_EARLY"

    for check_offset in range(min(time_window, days_since_rally + 1)):
        check_idx = last_bar_idx - check_offset
        if check_idx <= rally_attempt_idx:
            break

        days_from_rally = check_idx - rally_attempt_idx
        bar_gain_pct = (closes[check_idx] - closes[check_idx - 1]) / closes[check_idx - 1] if closes[check_idx - 1] > 0 else 0
        bar_vol = volumes[check_idx]
        vol_ratio_ftd = bar_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0

        if bar_gain_pct >= 0.015 and vol_ratio_ftd >= 1.0:
            if days_from_rally >= 4:
                ftd_idx = check_idx
                subtype = "FTD_CONFIRMED"
                break
            elif days_from_rally >= 2:
                ftd_idx = check_idx
                subtype = "FTD_EARLY"
                # Don't break, keep looking for a confirmed one

    if ftd_idx is None:
        return None

    # Step 4: Scoring
    score = 40.0

    decline_pct = (pre_correction_high - correction_low) / pre_correction_high if pre_correction_high > 0 else 0
    ftd_gain = (closes[ftd_idx] - closes[ftd_idx - 1]) / closes[ftd_idx - 1] if closes[ftd_idx - 1] > 0 else 0
    ftd_vol_ratio = volumes[ftd_idx] / avg_vol_20 if avg_vol_20 > 0 else 1.0

    # FTD quality
    if ftd_gain >= 0.03: score += 15.0
    elif ftd_gain >= 0.02: score += 10.0
    else: score += 5.0

    if ftd_vol_ratio >= 2.0: score += 12.0
    elif ftd_vol_ratio >= 1.5: score += 8.0
    elif ftd_vol_ratio >= 1.2: score += 4.0

    # Confirmed vs early
    if subtype == "FTD_CONFIRMED": score += 10.0
    else: score += 3.0

    # Correction quality (moderate correction = better setup)
    if 0.08 <= decline_pct <= 0.20: score += 8.0
    elif 0.05 <= decline_pct <= 0.30: score += 4.0

    # Price reclaiming key MAs
    if current_close > sma50: score += 5.0
    if current_close > sma200: score += 5.0

    # Recovery from correction low
    recovery_pct = (current_close - correction_low) / correction_low if correction_low > 0 else 0
    if recovery_pct > 0.10: score += 5.0
    elif recovery_pct > 0.05: score += 2.0

    # Trade plan
    entry = current_close + 0.10 * atr_val
    sl = correction_low - 0.5 * atr_val
    if sl <= 0 or sl >= entry:
        sl = entry - 2.5 * atr_val
    if sl >= entry or entry <= 0 or sl <= 0:
        return None

    risk = entry - sl
    shares = max(1, int(math.floor((account_size * base_risk_pct) / risk)))
    correction_depth = pre_correction_high - correction_low
    t1 = entry + correction_depth * 0.50
    t2 = entry + correction_depth * 0.75
    t3 = max(pre_correction_high, entry + correction_depth)

    rsi_val = _rsi(closes[-(max(_DEFAULT_RSI_PERIOD + 50, 60)):], _DEFAULT_RSI_PERIOD)
    dollar_vols = [c * v for c, v in zip(closes, volumes)]
    avg_dollar_vol_20 = _sma(dollar_vols[-21:-1], 20) if len(dollar_vols) >= 21 else _sma(dollar_vols, len(dollar_vols))
    current_range_pct, current_vol_pct, current_rexp = _current_bar_expansion_metrics(bars)
    vol_ratio_val = volumes[-1] / avg_vol_20 if avg_vol_20 > 0 else 1.0
    sma20 = _sma(closes, int(params["sma_short"]))
    days_since = (n - 1) - rally_attempt_idx

    sig = TradeSignal(
        symbol=symbol,
        subtype=subtype,
        setup=_SETUP_TYPE_FTD,
        window=timeframe.upper(),
        rating=_rating_from_score(score),
        score=round(score, 2),
        close=round(current_close, 4),
        entry=round(entry, 4),
        sl=round(sl, 4),
        pivot=round(pre_correction_high, 4),
        T1=round(t1, 4),
        T2=round(t2, 4),
        T3=round(t3, 4),
        shares=shares,
        rsi=round(rsi_val, 2),
        sma20=round(sma20, 4),
        sma50=round(sma50, 4),
        sma200=round(sma200, 4),
        atr=round(atr_val, 4),
        vol_ratio=round(vol_ratio_val, 3),
        height_pct=round(decline_pct * 100.0, 2),  # correction depth
        depth_pct=round(recovery_pct * 100.0, 2),   # recovery so far
        length=days_since,
        avg_vol_20=round(avg_vol_20, 2),
        last_volume=round(volumes[-1], 2),
        avg_dollar_vol_20=round(avg_dollar_vol_20, 2),
        last_dollar_vol=round(dollar_vols[-1], 2),
        max_after_breakout=round(pre_correction_high, 4),
        min_after_breakout=round(correction_low, 4),
        days_above_pivot=sum(1 for x in closes[-20:] if x >= pre_correction_high),
        distance_from_pivot=round(((current_close - pre_correction_high) / pre_correction_high * 100.0)
                                   if pre_correction_high > 0 else 0.0, 2),
        range_pct=current_range_pct,
        vol_pct=current_vol_pct,
        rexp=current_rexp,
    )
    sig.ftdGainPct = round(ftd_gain * 100.0, 2)
    sig.ftdVolRatio = round(ftd_vol_ratio, 3)
    sig.correctionPct = round(decline_pct * 100.0, 2)
    sig.daysSinceRally = days_since
    try:
        sig.correctionLowDate = bars[correction_low_idx]["date"]
        sig.rallyAttemptDate = bars[rally_attempt_idx]["date"]
        sig.ftdDate = bars[ftd_idx]["date"]
    except Exception:
        pass
    return sig


# ── Batch scanner ─────────────────────────────────────────────────────────────

def scan_symbols(
    symbols: list[str],
    cache_dir: str,
    lookback: int,
    timeframe: str = "daily",
    account_size: float = 100_000.0,
    base_risk_pct: float = 0.01,
    min_price_floor: float = 5.0,
    min_score: float = 35.0,
    setup_types: list[str] | None = None,
    time_window: int = 5,
) -> list[dict]:
    """
    Scan a list of symbols for specified setup types using cached CSV bars.
    Returns a list of dicts compatible with the main pipeline CSV_FIELDS schema.

    time_window: how many recent bars to search for a setup trigger (default 5).
    """
    if setup_types is None:
        setup_types = [
            _SETUP_TYPE_MR, _SETUP_TYPE_BO, _SETUP_TYPE_ABFP, _SETUP_TYPE_BF,
            _SETUP_TYPE_EMA_PB, _SETUP_TYPE_BASE_BO, _SETUP_TYPE_FTD,
        ]

    cache = Path(cache_dir)
    results: list[dict] = []
    params = _timeframe_params(timeframe)

    for symbol in symbols:
        bars = _load_bars(symbol, lookback, timeframe, cache)
        if not bars:
            continue

        signals: list[TradeSignal] = []
        if _SETUP_TYPE_MR in setup_types:
            sig = detect_mean_reversion(symbol, bars, timeframe, params, account_size, base_risk_pct, min_price_floor)
            if sig: signals.append(sig)

        if _SETUP_TYPE_BO in setup_types:
            sig = detect_breakout(symbol, bars, timeframe, params, account_size, base_risk_pct, min_price_floor)
            if sig: signals.append(sig)

        if _SETUP_TYPE_ABFP in setup_types:
            sig = detect_breakout_pullback(symbol, bars, timeframe, params, account_size, base_risk_pct, min_price_floor)
            if sig: signals.append(sig)

        if _SETUP_TYPE_BF in setup_types:
            sig = detect_bull_flag(symbol, bars, timeframe, params, account_size, base_risk_pct, min_price_floor)
            if sig: signals.append(sig)

        if _SETUP_TYPE_EMA_PB in setup_types:
            sig = detect_ema_pullback(symbol, bars, timeframe, params, account_size, base_risk_pct, min_price_floor, time_window=time_window)
            if sig: signals.append(sig)

        if _SETUP_TYPE_BASE_BO in setup_types:
            sig = detect_base_breakout(symbol, bars, timeframe, params, account_size, base_risk_pct, min_price_floor, time_window=time_window)
            if sig: signals.append(sig)

        if _SETUP_TYPE_FTD in setup_types:
            sig = detect_follow_through(symbol, bars, timeframe, params, account_size, base_risk_pct, min_price_floor, time_window=time_window)
            if sig: signals.append(sig)

        for sig in signals:
            if sig.score >= min_score:
                results.append(_signal_to_dict(sig))

    return results


def scan_symbols_multi_timeframe(
    symbols: list[str],
    cache_dir: str,
    lookback: int,
    account_size: float = 100_000.0,
    base_risk_pct: float = 0.01,
    min_price_floor: float = 5.0,
    min_score: float = 35.0,
    setup_types: list[str] | None = None,
    time_window: int = 5,
) -> list[dict]:
    """
    Scan across both DAILY and WEEKLY timeframes, merge results by symbol,
    and attach timeframe_alignment metadata.

    When both daily and weekly fire for the same symbol+setup, the daily result
    gets a score bonus (+15) and a 'BOTH_ALIGNED' tag.
    """
    daily_results = scan_symbols(
        symbols=symbols, cache_dir=cache_dir, lookback=lookback,
        timeframe="daily", account_size=account_size, base_risk_pct=base_risk_pct,
        min_price_floor=min_price_floor, min_score=min_score,
        setup_types=setup_types, time_window=time_window,
    )
    weekly_results = scan_symbols(
        symbols=symbols, cache_dir=cache_dir, lookback=lookback,
        timeframe="weekly", account_size=account_size, base_risk_pct=base_risk_pct,
        min_price_floor=min_price_floor, min_score=max(25.0, min_score - 10),
        setup_types=setup_types, time_window=max(2, time_window // 3),
    )

    # Build weekly index: symbol → set of setup types
    weekly_index: dict[str, set[str]] = {}
    weekly_by_key: dict[str, dict] = {}
    for r in weekly_results:
        sym = r.get("symbol", "")
        setup = r.get("setup", "")
        weekly_index.setdefault(sym, set()).add(setup)
        weekly_by_key[f"{sym}:{setup}"] = r

    merged: list[dict] = []
    seen_keys: set[str] = set()

    for r in daily_results:
        sym = r.get("symbol", "")
        setup = r.get("setup", "")
        key = f"{sym}:{setup}"

        if setup in weekly_index.get(sym, set()):
            r["timeframe_alignment"] = "BOTH_ALIGNED"
            # Score bonus for multi-timeframe confirmation
            try:
                old_score = float(r.get("score", 0))
                r["score"] = str(round(old_score + 15.0, 2))
                r["rating"] = _rating_from_score(old_score + 15.0)
            except (ValueError, TypeError):
                pass
        else:
            r["timeframe_alignment"] = "DAILY_ONLY"

        merged.append(r)
        seen_keys.add(key)

    # Add weekly-only results
    for r in weekly_results:
        sym = r.get("symbol", "")
        setup = r.get("setup", "")
        key = f"{sym}:{setup}"
        if key not in seen_keys:
            r["timeframe_alignment"] = "WEEKLY_ONLY"
            merged.append(r)

    return merged


def _load_bars(symbol: str, lookback: int, timeframe: str, cache: Path) -> list[dict]:
    """Load and optionally aggregate bars from cache."""

    def aggregate_weekly(rows: list[dict]) -> list[dict]:
        weekly: list[dict] = []
        if not rows: return weekly

        current_key, current = None, None
        for row in rows:
            try:
                dt = datetime.fromisoformat(str(row.get("date", "")).strip()).date()
                key = (dt.isocalendar().year, dt.isocalendar().week)
            except (ValueError, TypeError):
                continue

            if key != current_key:
                if current: weekly.append(current)
                current_key = key
                current = {
                    "date": dt.isoformat(), "open": float(row["open"]), "high": float(row["high"]),
                    "low": float(row["low"]), "close": float(row["close"]), "volume": float(row["volume"])
                }
            else:
                current["high"] = max(current["high"], float(row["high"]))
                current["low"] = min(current["low"], float(row["low"]))
                current["close"] = float(row["close"])
                current["volume"] += float(row["volume"])
                current["date"] = dt.isoformat()
        if current: weekly.append(current)
        return weekly

    def _try_read(p: Path) -> list[dict]:
        rows = []
        try:
            with open(p, newline="") as fh:
                for row in csv.DictReader(fh):
                    try:
                        import math
                        _c = row.get("close")
                        close = float(_c) if _c not in (None, "", "nan", "NaN") else 0.0
                        if math.isnan(close):
                            close = 0.0
                    except (ValueError, TypeError):
                        continue
                    if close <= 0:
                        continue
                    rows.append({
                        "date":   str(row.get("date") or "").strip(),
                        "open":   float(row.get("open") or 0),
                        "high":   float(row.get("high") or 0),
                        "low":    float(row.get("low") or 0),
                        "close":  close,
                        "volume": float(row.get("volume") or 0),
                    })
        except Exception:
            return []
        return rows

    min_bars = int(_timeframe_params(timeframe)["min_bars"])
    min_bars_ipo = int(_timeframe_params(timeframe, ipo_mode=True)["min_bars"])

    # 1) Try unified file first
    unified = cache / f"{symbol}.csv"
    if unified.exists():
        rows = _try_read(unified)
        if timeframe == "weekly":
            rows = aggregate_weekly(rows)
        if len(rows) >= min_bars or len(rows) >= min_bars_ipo:
            return rows

    # 2) Legacy fallback
    for n in sorted({lookback, 252, 504, 728, 900}):
        p = cache / f"{symbol}_{n}.csv"
        if p.exists():
            rows = _try_read(p)
            if timeframe == "weekly":
                rows = aggregate_weekly(rows)
            if len(rows) >= min_bars or len(rows) >= min_bars_ipo:
                return rows
    return []


def _signal_to_dict(sig: TradeSignal) -> dict:
    """Convert TradeSignal to a dict for CSV output."""
    data = {
        "symbol": sig.symbol, "listType": sig.listType, "setup": sig.setup, "setupSubtype": sig.subtype,
        "window": sig.window, "rating": sig.rating, "score": str(sig.score), "close": str(sig.close),
        "pivot": str(sig.pivot), "entry": str(sig.entry), "sl": str(sig.sl), "shares": str(sig.shares),
        "T1": str(sig.T1), "T2": str(sig.T2), "T3": str(sig.T3),
        "height%": str(sig.height_pct), "depth%": str(sig.depth_pct), "len": str(sig.length),
        "ctr": str(sig.ctr), "dist%": str(sig.dist_pct or ""), "range%": str(sig.range_pct),
        "vol%": str(sig.vol_pct), "rexp": str(sig.rexp),
    }
    # Add setup-specific fields
    if sig.setup == _SETUP_TYPE_MR:
        data.update({
            "mrRsi": str(sig.rsi), "mrSma20": str(sig.sma20), "mrSma50": str(sig.sma50), "mrSma200": str(sig.sma200),
            "mrAtr": str(sig.atr), "mrLowerBB": str(sig.lower_bb), "mrUpperBB": str(sig.upper_bb),
            "mrBbPct": str(sig.bb_pct), "mrVolRatio": str(sig.vol_ratio),
            "mrPullbackVolRatio": str(sig.pullback_vol_ratio or ""), "mrSubtype": sig.subtype,
        })
    # Add breakout-specific fields
    if sig.setup == _SETUP_TYPE_BO:
        data.update({
            "boMaxAfter": str(sig.max_after_breakout or ""), "boMinAfter": str(sig.min_after_breakout or ""),
        })
    # Add ABFP-specific fields
    if sig.setup == _SETUP_TYPE_ABFP:
        data.update({
            "abfpPeakHigh":       str(sig.max_after_breakout or ""),
            "abfpPullbackDepth%": str(sig.height_pct),
            "abfpRunFromBO%":     str(sig.depth_pct),
            "abfpBarsSincePeak":  str(sig.length),
            "abfpPullbackVolRatio": str(sig.pullback_vol_ratio or ""),
            "abfpBreakoutDate":   str(getattr(sig, "breakoutDate", "") or ""),
        })
    # Add Bull Flag-specific fields
    if sig.setup == _SETUP_TYPE_BF:
        data.update({
            "bfPoleGain%":       str(sig.height_pct),
            "bfFlagDecline%":    str(sig.depth_pct),
            "bfFlagBars":        str(sig.length),
            "bfFlagVolRatio":    str(sig.pullback_vol_ratio or ""),
            "bfTightnessRatio":  str(getattr(sig, "bfTightnessRatio", "") or ""),
            "bfPoleVolRatio":    str(getattr(sig, "bfPoleVolRatio",   "") or ""),
            "bfFlagHigh":        str(sig.max_after_breakout or ""),
            "bfFlagLow":         str(sig.min_after_breakout or ""),
            "bfPoleStartDate":   str(getattr(sig, "bfPoleStartDate",  "") or ""),
            "bfPoleTopDate":     str(getattr(sig, "bfPoleTopDate",    "") or ""),
        })
    # Add EMA Pullback-specific fields
    if sig.setup == _SETUP_TYPE_EMA_PB:
        data.update({
            "emaPeriod":    str(getattr(sig, "emaPeriod", "") or ""),
            "emaValue":     str(getattr(sig, "emaValue", "") or ""),
            "emaRsi":       str(sig.rsi),
            "emaVolRatio":  str(sig.vol_ratio),
        })
    # Add Base Breakout-specific fields
    if sig.setup == _SETUP_TYPE_BASE_BO:
        data.update({
            "baseBars":       str(getattr(sig, "baseBars", "") or ""),
            "baseDepthPct":   str(getattr(sig, "baseDepthPct", "") or ""),
            "baseVolDryUp":   str(getattr(sig, "baseVolDryUp", "") or ""),
            "boVolExpansion": str(getattr(sig, "boVolExpansion", "") or ""),
            "baseCeiling":    str(sig.max_after_breakout or ""),
            "baseFloor":      str(sig.min_after_breakout or ""),
        })
    # Add Follow-Through Day-specific fields
    if sig.setup == _SETUP_TYPE_FTD:
        data.update({
            "ftdGainPct":         str(getattr(sig, "ftdGainPct", "") or ""),
            "ftdVolRatio":        str(getattr(sig, "ftdVolRatio", "") or ""),
            "correctionPct":      str(getattr(sig, "correctionPct", "") or ""),
            "daysSinceRally":     str(getattr(sig, "daysSinceRally", "") or ""),
            "correctionLowDate":  str(getattr(sig, "correctionLowDate", "") or ""),
            "rallyAttemptDate":   str(getattr(sig, "rallyAttemptDate", "") or ""),
            "ftdDate":            str(getattr(sig, "ftdDate", "") or ""),
        })
    # Add liquidity / pivot enrichment fields
    data.update({
        "avgVol20": str(sig.avg_vol_20 if getattr(sig, 'avg_vol_20', None) is not None else ""),
        "lastVol": str(sig.last_volume if getattr(sig, 'last_volume', None) is not None else ""),
        "avgDollarVol20": str(sig.avg_dollar_vol_20 if getattr(sig, 'avg_dollar_vol_20', None) is not None else ""),
        "lastDollarVol": str(sig.last_dollar_vol if getattr(sig, 'last_dollar_vol', None) is not None else ""),
        "daysAbovePivot": str(sig.days_above_pivot if getattr(sig, 'days_above_pivot', None) is not None else ""),
        "distFromPivot%": str(sig.distance_from_pivot if getattr(sig, 'distance_from_pivot', None) is not None else ""),
    })
    return data
