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
_DEFAULT_RSI_PERIOD = 14
_DEFAULT_BB_PERIOD = 20
_DEFAULT_BB_STD = 2.0
_DEFAULT_SMA_SHORT = 20
_DEFAULT_SMA_MED = 50
_DEFAULT_SMA_LONG = 200
_DEFAULT_ATR_PERIOD = 14
_DEFAULT_LOOKBACK_WINDOW = 5
_MIN_BARS = 210


def _timeframe_params(timeframe: str) -> dict[str, int | float]:
    tf = (timeframe or "daily").strip().lower()
    if tf == "weekly":
        return {
            "sma_short": 10,
            "sma_med": 20,
            "sma_long": 40,
            "bb_period": 10,
            "atr_period": 10,
            "pullback_window": 3,
            "min_bars": 52,
        }
    return {
        "sma_short": _DEFAULT_SMA_SHORT,
        "sma_med": _DEFAULT_SMA_MED,
        "sma_long": _DEFAULT_SMA_LONG,
        "bb_period": _DEFAULT_BB_PERIOD,
        "atr_period": _DEFAULT_ATR_PERIOD,
        "pullback_window": _DEFAULT_LOOKBACK_WINDOW,
        "min_bars": _MIN_BARS,
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

    if len(bars) < int(params["min_bars"]): return None

    closes = [b["close"] for b in bars]
    volumes = [b.get("volume", 0.0) for b in bars]

    sma20 = _sma(closes, sma_short_period)
    sma50 = _sma(closes, sma_med_period)
    sma200 = _sma(closes, sma_long_period)
    rsi_val = _rsi(closes[-(max(_DEFAULT_RSI_PERIOD + 50, sma_med_period + 10)):], _DEFAULT_RSI_PERIOD)
    bb_mid, bb_lower, bb_upper = _bollinger(closes[-(max(60, bb_period_eff + 20)):], bb_period_eff, _DEFAULT_BB_STD)
    atr_val = _atr(bars[-(atr_period_eff + 20):], atr_period_eff)

    current_close = closes[-1]
    if current_close < min_price_floor or sma200 <= 0 or current_close < sma200 * 0.95:
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
    vol_pct = round((vol_ratio - 1.0) * 100.0, 2)
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
        height_pct=pullback_depth_pct, depth_pct=bb_width_pct, length=bars_since_below, vol_pct=vol_pct,
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
    if len(bars) < int(params["min_bars"]):
        return None

    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    volumes = [float(b.get("volume", 0.0)) for b in bars]
    sma50 = _sma(closes, int(params["sma_med"]))
    sma200 = _sma(closes, int(params["sma_long"]))
    atr_val = _atr(bars[-(int(params["atr_period"]) + 20):], int(params["atr_period"]))
    current_close = closes[-1]
    current_high = highs[-1]
    current_low = lows[-1]

    if current_close < min_price_floor or sma200 <= 0 or current_close < sma200 * 0.95:
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
    if len(bars) < int(params["min_bars"]):
        return None

    closes  = [float(b["close"])          for b in bars]
    highs   = [float(b["high"])           for b in bars]
    lows    = [float(b["low"])            for b in bars]
    volumes = [float(b.get("volume", 0.0)) for b in bars]

    sma50   = _sma(closes, int(params["sma_med"]))
    sma200  = _sma(closes, int(params["sma_long"]))
    atr_val = _atr(bars[-(int(params["atr_period"]) + 20):], int(params["atr_period"]))
    current_close = closes[-1]

    if current_close < min_price_floor or sma200 <= 0 or current_close < sma200 * 0.90:
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
        vol_ratio=round(volumes[-1] / avg_vol_20 if avg_vol_20 > 0 else 1.0, 3),
        pullback_vol_ratio=round(pullback_vol_ratio, 3),
        length=bars_since_peak,
    )

    try:
        sig.breakoutDate = bars[breakout_idx]["date"]
    except Exception:
        sig.breakoutDate = None

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
) -> list[dict]:
    """
    Scan a list of symbols for specified setup types using cached CSV bars.
    Returns a list of dicts compatible with the main pipeline CSV_FIELDS schema.
    """
    if setup_types is None:
        setup_types = [_SETUP_TYPE_MR, _SETUP_TYPE_BO, _SETUP_TYPE_ABFP]

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

        for sig in signals:
            if sig.score >= min_score:
                results.append(_signal_to_dict(sig))

    return results


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

    for n in sorted({lookback, 252, 504, 728, 900}):
        p = cache / f"{symbol}_{n}.csv"
        if p.exists():
            try:
                with open(p, newline="") as fh:
                    rows = []
                    for row in csv.DictReader(fh):
                        try:
                            close = float(row.get("close") or 0)
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

                if timeframe == "weekly":
                    rows = aggregate_weekly(rows)

                if len(rows) >= int(_timeframe_params(timeframe)["min_bars"]):
                    return rows
            except Exception:
                continue
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
