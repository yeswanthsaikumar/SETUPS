"""
mean_reversion_detector.py
──────────────────────────
Pure-Python mean reversion setup detector for swing trading.

Strategy overview
─────────────────
Detect high-quality mean reversion setups where:
  1. Stock is in a macro uptrend (close > 200-day SMA)
  2. Short-term pullback has driven price into oversold territory
  3. A reversal signal candle appears (BB bounce, MA reclaim, RSI snapback)
  4. Volume dry-up during pullback + moderate increase on signal day

Subtypes
────────
  BB_BOUNCE       – Price touches/crosses below lower Bollinger Band then closes back above it
  MA_RECLAIM      – Price falls below 20-day SMA with RSI<40, then closes back above 20 SMA
  OVERSOLD_SNAP   – RSI drops below 30, then crosses back above 30 with a bullish candle

Trade Plan
──────────
  Entry  = close + 0.10 * ATR14  (slight buffer above signal candle)
  Stop   = min(recent-10-bar-low, close - 2*ATR14)  – below structure
  T1     = 20-day SMA (reversion target / primary)
  T2     = entry + 2 * risk
  T3     = upper Bollinger Band  (or entry + 3 * risk if upper BB unreasonably far)
  Shares = floor(account_size * base_risk_pct / (entry - stop))

Quality Score (0–100)
──────────────────────
  +25  macro uptrend (close > SMA200)
  +15  intermediate uptrend (close > SMA50)
  +20  RSI in sweet zone 25–45
  +15  price at/below lower Bollinger Band
  +10  volume dry-up on pullback (recent avg vol < 70% of 20-bar avg)
  +10  signal candle is a hammer / bullish engulfing / inside-bar breakout
  + 5  moderate signal-bar volume (>=80% of avg) – confirming demand
"""

from __future__ import annotations

import csv
import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


# ── Constants ─────────────────────────────────────────────────────────────────
_SETUP_TYPE = "MEAN_REVERSION"
_DEFAULT_RSI_PERIOD = 14
_DEFAULT_BB_PERIOD = 20
_DEFAULT_BB_STD = 2.0
_DEFAULT_SMA_SHORT = 20
_DEFAULT_SMA_MED = 50
_DEFAULT_SMA_LONG = 200
_DEFAULT_ATR_PERIOD = 14
_DEFAULT_LOOKBACK_WINDOW = 5   # bars to look back for pullback detection
_MIN_BARS = 210                # minimum bars required (200 for SMA200 + buffer)


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
class MeanReversionSignal:
    symbol: str
    subtype: str                     # BB_BOUNCE | MA_RECLAIM | OVERSOLD_SNAP
    setup: str = _SETUP_TYPE
    window: str = "DAILY"
    rating: str = "B"
    score: float = 0.0
    close: float = 0.0
    entry: float = 0.0
    sl: float = 0.0
    pivot: float = 0.0             # = 20-SMA (the "mean" we revert to)
    T1: float = 0.0                # 20-SMA
    T2: float = 0.0                # 2R
    T3: float = 0.0                # 3R or upper BB
    shares: int = 0
    rsi: float = 0.0
    sma20: float = 0.0
    sma50: float = 0.0
    sma200: float = 0.0
    atr: float = 0.0
    lower_bb: float = 0.0
    upper_bb: float = 0.0
    bb_pct: float = 0.0           # (close - lower_bb) / (upper_bb - lower_bb)  * 100
    vol_ratio: float = 0.0        # recent_vol / avg_vol
    pullback_vol_ratio: float = 0.0   # pullback avg vol / avg vol
    dist_pct: float = 0.0         # distance from close to pivot (mean) %
    # pass-through fields so enrich_and_filter_rows works identically
    listType: str = "BREAKOUT"
    height_pct: float = 0.0       # reused as pullback depth %
    depth_pct: float = 0.0        # BB width %
    length: int = 0               # bars since pullback started
    ctr: int = 0                  # not applicable for MR → 0
    range_pct: float = 0.0
    vol_pct: float = 0.0
    rexp: float = 0.0
    rejection_reason: Optional[str] = None


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

    # Initial averages
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
    """Returns (middle, lower, upper) Bollinger Bands."""
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
    trs = []
    for i in range(1, len(bars)):
        high = bars[i].get("high", 0.0)
        low = bars[i].get("low", 0.0)
        prev_close = bars[i - 1].get("close", 0.0)
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if len(trs) < period:
        return statistics.mean(trs) if trs else 0.0
    # Wilder smoothing
    atr_val = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr_val = (atr_val * (period - 1) + tr) / period
    return atr_val


def _swing_low(bars: list[dict], lookback: int = 10) -> float:
    recent = bars[-lookback:]
    lows = [b.get("low", b.get("close", 0.0)) for b in recent if b.get("low", b.get("close", 0.0)) > 0]
    return min(lows) if lows else 0.0


def _is_hammer(bar: dict, atr: float) -> bool:
    """True if bar looks like a hammer / dragonfly doji (bullish reversal candle)."""
    o = bar.get("open", 0.0)
    h = bar.get("high", 0.0)
    lo = bar.get("low", 0.0)
    c = bar.get("close", 0.0)
    if o <= 0 or h <= lo:
        return False
    body = abs(c - o)
    lower_shadow = min(o, c) - lo
    upper_shadow = h - max(o, c)
    if body <= 0:
        return False
    # Hammer: lower shadow >= 2x body, upper shadow <= body, close in upper 40%
    return (lower_shadow >= 2.0 * body and upper_shadow <= body and c > (lo + (h - lo) * 0.5))


def _is_bullish_engulfing(bar: dict, prev_bar: dict) -> bool:
    """True if current bar bullishly engulfs the previous bar."""
    po = prev_bar.get("open", 0.0)
    pc = prev_bar.get("close", 0.0)
    co = bar.get("open", 0.0)
    cc = bar.get("close", 0.0)
    if pc <= 0 or cc <= 0:
        return False
    prev_bearish = pc < po
    curr_bullish = cc > co
    engulfs = co <= pc and cc >= po
    return prev_bearish and curr_bullish and engulfs


def _is_inside_bar_breakout(bar: dict, prev_bar: dict, two_bars_ago: dict) -> bool:
    """True if: prev bar was inside bar (relative to 2 bars ago), current bar breaks out bullishly."""
    p2_high = two_bars_ago.get("high", 0.0)
    p2_low = two_bars_ago.get("low", 0.0)
    p_high = prev_bar.get("high", 0.0)
    p_low = prev_bar.get("low", 0.0)
    c_close = bar.get("close", 0.0)
    c_high = bar.get("high", 0.0)
    if p2_high <= 0:
        return False
    inside = p_high <= p2_high and p_low >= p2_low
    breakout = c_close > p2_high or c_high > p2_high
    return inside and breakout


def _rating_from_score(score: float) -> str:
    if score >= 80:
        return "A+"
    if score >= 65:
        return "A"
    if score >= 50:
        return "B"
    if score >= 35:
        return "C"
    return "D"


# ── Main detector ─────────────────────────────────────────────────────────────

def detect_mean_reversion(
    symbol: str,
    bars: list[dict],
    *,
    timeframe: str = "daily",
    account_size: float = 100_000.0,
    base_risk_pct: float = 0.01,
    min_price_floor: float = 5.0,
    rsi_period: int = _DEFAULT_RSI_PERIOD,
    bb_period: int = _DEFAULT_BB_PERIOD,
    bb_std: float = _DEFAULT_BB_STD,
    pullback_window: int = _DEFAULT_LOOKBACK_WINDOW,
) -> Optional[MeanReversionSignal]:
    """
    Returns a MeanReversionSignal if a valid mean reversion setup is found,
    otherwise returns None with no side effects.
    """
    params = _timeframe_params(timeframe)
    sma_short_period = int(params["sma_short"])
    sma_med_period = int(params["sma_med"])
    sma_long_period = int(params["sma_long"])
    bb_period_eff = int(params["bb_period"])
    atr_period_eff = int(params["atr_period"])
    pullback_window_eff = int(params["pullback_window"])

    if len(bars) < int(params["min_bars"]):
        return None

    closes = [b["close"] for b in bars]
    volumes = [b.get("volume", 0.0) for b in bars]

    # ── Indicators ────────────────────────────────────────────────────────────
    sma20 = _sma(closes, sma_short_period)
    sma50 = _sma(closes, sma_med_period)
    sma200 = _sma(closes, sma_long_period)
    rsi_window = max(rsi_period + 50, sma_med_period + 10)
    rsi_val = _rsi(closes[-rsi_window:], rsi_period)
    bb_window = max(60, bb_period_eff + 20)
    bb_mid, bb_lower, bb_upper = _bollinger(closes[-bb_window:], bb_period_eff, bb_std)
    atr_val = _atr(bars[-(atr_period_eff + 20):], atr_period_eff)

    current_close = closes[-1]
    current_bar = bars[-1]
    prev_bar = bars[-2] if len(bars) >= 2 else bars[-1]
    prev_prev_bar = bars[-3] if len(bars) >= 3 else bars[-1]

    if current_close < min_price_floor:
        return None

    # ── Filter 1: Macro uptrend required ─────────────────────────────────────
    if sma200 <= 0 or current_close < sma200 * 0.95:
        return None     # too far below 200-SMA, not an uptrend reversion

    # ── Volume averages ───────────────────────────────────────────────────────
    avg_vol_20 = _sma(volumes[-21:-1], 20) if len(volumes) >= 21 else _sma(volumes, len(volumes))
    pullback_vol_recent = _sma(volumes[-(pullback_window_eff + 1):-1], pullback_window_eff) if len(volumes) > pullback_window_eff else avg_vol_20
    signal_vol = volumes[-1]
    vol_ratio = (signal_vol / avg_vol_20) if avg_vol_20 > 0 else 1.0
    pullback_vol_ratio = (pullback_vol_recent / avg_vol_20) if avg_vol_20 > 0 else 1.0

    # ── Pullback-zone detection (look back pullback_window bars) ──────────────
    recent_rsis = []
    for i in range(pullback_window_eff, 0, -1):
        rsi_i = _rsi(closes[-(rsi_window + i): -i], rsi_period)
        recent_rsis.append(rsi_i)

    recent_closes = closes[-(pullback_window_eff + 1):-1]
    recent_lowers = []
    for i in range(pullback_window_eff, 0, -1):
        _, lb, _ = _bollinger(closes[-(bb_window + i):-i], bb_period_eff, bb_std)
        recent_lowers.append(lb)

    rsi_dipped_below_40 = any(r < 40 for r in recent_rsis) or rsi_val < 40
    rsi_dipped_below_30 = any(r < 30 for r in recent_rsis) or rsi_val < 30
    price_crossed_lower_bb = any(c <= lb * 1.01 for c, lb in zip(recent_closes, recent_lowers)) or current_close <= bb_lower * 1.01
    price_below_sma20 = any(c < sma20 * 0.995 for c in recent_closes) or (current_close < sma20 * 1.01)

    # ── Signal detection ──────────────────────────────────────────────────────
    prev_close = closes[-2] if len(closes) >= 2 else closes[-1]
    _, prev_lower, _ = _bollinger(closes[-(bb_window + 1):-1], bb_period_eff, bb_std)
    bullish_reversal_bar = current_close >= prev_close or current_bar.get("close", 0.0) >= current_bar.get("open", 0.0)

    # Sub-type determination (priority order)
    subtype = None
    # BB_BOUNCE: price was below/at lower BB and now closes back above it
    was_at_lower_bb = price_crossed_lower_bb
    now_above_lower_bb = current_close > bb_lower * 0.995 and current_close <= bb_mid * 1.05
    if was_at_lower_bb and now_above_lower_bb and rsi_dipped_below_40:
        subtype = "BB_BOUNCE"

    # OVERSOLD_SNAP: RSI was <30 and now crosses back above 30
    if subtype is None and rsi_dipped_below_30 and rsi_val >= 30 and bullish_reversal_bar:
        subtype = "OVERSOLD_SNAP"

    # MA_RECLAIM: price fell below 20 SMA, RSI <40, now closes back above 20 SMA
    if subtype is None and price_below_sma20 and rsi_dipped_below_40 and current_close >= sma20 * 0.995 and bullish_reversal_bar:
        subtype = "MA_RECLAIM"

    if subtype is None:
        return None

    # ── Candle pattern bonus ──────────────────────────────────────────────────
    hammer_signal = _is_hammer(current_bar, atr_val)
    engulfing_signal = _is_bullish_engulfing(current_bar, prev_bar)
    inside_breakout = _is_inside_bar_breakout(current_bar, prev_bar, prev_prev_bar)
    candle_quality = hammer_signal or engulfing_signal or inside_breakout

    # ── Quality Score ─────────────────────────────────────────────────────────
    score = 0.0

    # Macro uptrend
    if current_close > sma200:
        score += 25.0
        if current_close > sma200 * 1.05:  # healthy margin above 200
            score += 5.0

    # Intermediate trend
    if current_close > sma50:
        score += 15.0
    elif current_close > sma50 * 0.98:
        score += 8.0

    # RSI in sweet spot
    if 25 <= rsi_val <= 45:
        score += 20.0
    elif 20 <= rsi_val < 25 or 45 < rsi_val <= 55:
        score += 10.0

    # BB position
    if current_close <= bb_lower:
        score += 15.0  # below lower BB — ideal entry
    elif current_close <= bb_mid * 1.05:
        bb_range = bb_upper - bb_lower
        if bb_range > 0:
            pct_in_lower_half = 1.0 - ((current_close - bb_lower) / (bb_range / 2.0))
            score += max(0.0, pct_in_lower_half * 10.0)

    # Volume dry-up on pullback
    if pullback_vol_ratio < 0.70:
        score += 10.0
    elif pullback_vol_ratio < 0.85:
        score += 5.0

    # Candle quality
    if candle_quality:
        score += 10.0
    elif current_close > prev_close:  # at least bullish bar
        score += 4.0

    # Signal bar volume confirmation
    if vol_ratio >= 0.80:
        score += 5.0

    score = min(score, 100.0)
    rating = _rating_from_score(score)

    # ── Trade Plan ────────────────────────────────────────────────────────────
    if atr_val <= 0:
        return None

    entry = current_close + 0.10 * atr_val
    swing_low = _swing_low(bars, 10)
    stop_by_structure = swing_low - 0.50 * atr_val
    stop_by_atr = current_close - 2.0 * atr_val
    sl = max(stop_by_structure, stop_by_atr)  # use the less extreme of the two

    if sl >= entry:
        return None     # degenerate risk
    if entry <= 0 or sl <= 0:
        return None

    risk = entry - sl
    if risk <= 0:
        return None

    shares = max(1, int(math.floor((account_size * base_risk_pct) / risk)))

    # Targets
    t1 = sma20   # primary: revert to mean
    t2 = entry + 2.0 * risk
    t3_candidate = bb_upper
    t3 = t3_candidate if t3_candidate > t2 else entry + 3.0 * risk

    # If T1 is below entry, adjust (e.g. price already above SMA20 in MA_RECLAIM)
    if t1 <= entry:
        t1 = entry + 1.0 * risk
    if t2 <= t1:
        t2 = t1 + risk

    # BB percentage position
    bb_range = (bb_upper - bb_lower) if (bb_upper > bb_lower) else 1.0
    bb_pct = ((current_close - bb_lower) / bb_range) * 100.0

    # Pullback depth % (from recent high to close)
    recent_high = max(b.get("high", b.get("close", 0.0)) for b in bars[-20:])
    pullback_depth_pct = round(((recent_high - current_close) / recent_high * 100.0) if recent_high > 0 else 0.0, 2)

    # BB width as depth%
    bb_width_pct = round((bb_upper - bb_lower) / bb_mid * 100.0 if bb_mid > 0 else 0.0, 2)

    dist_pct = round(((sma20 - current_close) / current_close * 100.0) if current_close > 0 else 0.0, 2)
    if dist_pct < 0:
        dist_pct = 0.0  # already above mean

    # Volume % vs average
    vol_pct = round((vol_ratio - 1.0) * 100.0, 2)

    # Bars since price was below SMA20 (base length proxy)
    bars_since_below = 0
    for b in reversed(bars[:-1]):
        if b.get("close", 0.0) < sma20:
            break
        bars_since_below += 1

    return MeanReversionSignal(
        symbol=symbol,
        subtype=subtype,
        setup=_SETUP_TYPE,
        window=timeframe.upper(),
        rating=rating,
        score=round(score, 2),
        close=round(current_close, 4),
        entry=round(entry, 4),
        sl=round(sl, 4),
        pivot=round(sma20, 4),       # the mean = T1 pivot
        T1=round(t1, 4),
        T2=round(t2, 4),
        T3=round(t3, 4),
        shares=shares,
        rsi=round(rsi_val, 2),
        sma20=round(sma20, 4),
        sma50=round(sma50, 4),
        sma200=round(sma200, 4),
        atr=round(atr_val, 4),
        lower_bb=round(bb_lower, 4),
        upper_bb=round(bb_upper, 4),
        bb_pct=round(bb_pct, 2),
        vol_ratio=round(vol_ratio, 3),
        pullback_vol_ratio=round(pullback_vol_ratio, 3),
        dist_pct=dist_pct,
        height_pct=pullback_depth_pct,
        depth_pct=bb_width_pct,
        length=bars_since_below,
        vol_pct=vol_pct,
    )


# ── Batch scanner ─────────────────────────────────────────────────────────────

def scan_symbols_for_mean_reversion(
    symbols: list[str],
    cache_dir: str,
    lookback: int,
    timeframe: str = "daily",
    account_size: float = 100_000.0,
    base_risk_pct: float = 0.01,
    min_price_floor: float = 5.0,
    min_score: float = 35.0,
) -> list[dict]:
    """
    Scan a list of symbols using cached CSV bars.
    Returns a list of dicts compatible with the main pipeline CSV_FIELDS schema.
    """
    cache = Path(cache_dir)
    results: list[dict] = []

    for symbol in symbols:
        bars = _load_bars(symbol, lookback, timeframe, cache)
        if not bars:
            continue

        sig = detect_mean_reversion(
            symbol,
            bars,
            timeframe=timeframe,
            account_size=account_size,
            base_risk_pct=base_risk_pct,
            min_price_floor=min_price_floor,
        )
        if sig is None or sig.score < min_score:
            continue

        results.append(_signal_to_dict(sig))

    return results


def _load_bars(symbol: str, lookback: int, timeframe: str, cache: Path) -> list[dict]:
    """Load bars from cache for a symbol and aggregate to weekly when requested."""

    def aggregate_weekly(rows: list[dict]) -> list[dict]:
        weekly: list[dict] = []
        current: dict | None = None
        current_key = None

        for row in rows:
            date_text = str(row.get("date", "")).strip()
            if not date_text:
                continue
            try:
                dt = datetime.fromisoformat(date_text).date()
            except ValueError:
                continue

            key = (dt.isocalendar().year, dt.isocalendar().week)
            if key != current_key:
                if current is not None:
                    weekly.append(current)
                current_key = key
                current = {
                    "date": dt.isoformat(),
                    "open": float(row.get("open") or 0),
                    "high": float(row.get("high") or 0),
                    "low": float(row.get("low") or 0),
                    "close": float(row.get("close") or 0),
                    "volume": float(row.get("volume") or 0),
                }
            else:
                current["high"] = max(float(current.get("high") or 0), float(row.get("high") or 0))
                current["low"] = min(float(current.get("low") or 10**12), float(row.get("low") or 10**12))
                current["close"] = float(row.get("close") or 0)
                current["volume"] = float(current.get("volume") or 0) + float(row.get("volume") or 0)
                current["date"] = dt.isoformat()

        if current is not None:
            weekly.append(current)
        return weekly

    candidates = sorted({lookback, 252, 504, 728, 900})
    for n in candidates:
        p = cache / f"{symbol}_{n}.csv"
        if p.exists():
            try:
                rows = []
                with open(p, newline="") as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        try:
                            rows.append({
                                "date": str(row.get("date", "")).strip(),
                                "open": float(row.get("open") or 0),
                                "high": float(row.get("high") or 0),
                                "low": float(row.get("low") or 0),
                                "close": float(row.get("close") or 0),
                                "volume": float(row.get("volume") or 0),
                            })
                        except (ValueError, TypeError):
                            continue
                rows = [r for r in rows if r["close"] > 0]
                if timeframe == "weekly":
                    rows = aggregate_weekly(rows)
                if len(rows) >= int(_timeframe_params(timeframe)["min_bars"]):
                    return rows
            except Exception:
                continue
    return []


def _signal_to_dict(sig: MeanReversionSignal) -> dict:
    """Convert MeanReversionSignal to a dict matching the main pipeline schema."""
    return {
        "symbol": sig.symbol,
        "listType": sig.listType,
        "setup": sig.setup,
        "setupSubtype": sig.subtype,
        "window": sig.window,
        "height%": str(sig.height_pct),
        "depth%": str(sig.depth_pct),
        "len": str(sig.length),
        "ctr": str(sig.ctr),
        "dist%": str(sig.dist_pct),
        "rating": sig.rating,
        "close": str(sig.close),
        "pivot": str(sig.pivot),
        "entry": str(sig.entry),
        "score": str(sig.score),
        "range%": str(sig.bb_pct),     # reuse field as BB% position
        "vol%": str(sig.vol_pct),
        "rexp": str(round(sig.vol_ratio, 3)),  # reuse as vol ratio
        "shares": str(sig.shares),
        "sl": str(sig.sl),
        "T1": str(sig.T1),
        "T2": str(sig.T2),
        "T3": str(sig.T3),
        # Extra MR-specific fields
        "mrRsi": str(sig.rsi),
        "mrSma20": str(sig.sma20),
        "mrSma50": str(sig.sma50),
        "mrSma200": str(sig.sma200),
        "mrAtr": str(sig.atr),
        "mrLowerBB": str(sig.lower_bb),
        "mrUpperBB": str(sig.upper_bb),
        "mrBbPct": str(sig.bb_pct),
        "mrVolRatio": str(sig.vol_ratio),
        "mrPullbackVolRatio": str(sig.pullback_vol_ratio),
        "mrSubtype": sig.subtype,
    }

