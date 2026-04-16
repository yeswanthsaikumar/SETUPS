"""
Breakout Candle Alert Engine
============================
Detects breakout candle formations on watchlist stocks with:
  - Price breaking major resistance levels (52w high, consolidation highs, pivot levels)
  - Volume surge confirmation (>1.5x 20-day avg)
  - Candle body strength (wide-range bar, close near high)
  - Multi-timeframe alignment
  - Pivot candle entries (first pullback to breakout level)

Also includes backtesting on historical data to validate detection accuracy.

Alerts via Telegram Bot (free) and Gmail SMTP (free).
"""

from __future__ import annotations

import csv
import json
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

# ─── Configuration ────────────────────────────────────────────────────────────

@dataclass
class AlertConfig:
    """Global alert configuration."""
    enabled: bool = True
    scan_interval_seconds: int = 120        # How often to scan (2 min during market hours)
    # ── Core detection params ─────────────────────────────────────────────
    volume_threshold: float = 2.5           # Candle vol must be >= 2.5x avg of last N bars
    volume_avg_bars: int = 5                # Average volume over last N bars ("few trading days")
    volume_strong_threshold: float = 4.0    # Exceptionally strong volume
    body_ratio_min: float = 0.30            # Candle body must be >30% of range (relaxed)
    close_near_high_pct: float = 0.50       # Close in top 50% of range (relaxed)
    min_base_bars: int = 5                  # Min bars of consolidation before breakout
    max_base_range_pct: float = 20          # Max range% during consolidation
    atr_breakout_multiple: float = 0.0      # 0 = disabled (volume is primary filter)
    lookback_days: int = 252                # Data lookback for level detection
    pivot_entry_window: int = 5             # Days after breakout to watch for pivot re-entry
    # ── Telegram (FREE — recommended) ─────────────────────────────────────
    telegram_enabled: bool = False
    telegram_bot_token: str = ""            # From @BotFather on Telegram
    telegram_chat_id: str = ""              # Your chat ID (use @userinfobot)
    # ── Gmail SMTP (FREE with app password) ───────────────────────────────
    email_enabled: bool = False
    gmail_address: str = ""                 # your.email@gmail.com
    gmail_app_password: str = ""            # 16-char app password (not your login password)
    email_to: str = ""                      # recipient (can be same as gmail_address)
    # ── Deprecated fields kept for config compat ──────────────────────────
    consolidation_days: int = 5
    consolidation_max_range_pct: float = 20
    min_rs_score: float = 0


@dataclass
class BreakoutSignal:
    """A detected breakout or pivot entry signal."""
    symbol: str
    signal_type: str           # "BREAKOUT" | "PIVOT_ENTRY" | "VOLUME_SURGE"
    date: str
    price: float
    close: float
    high: float
    low: float
    open_price: float
    volume: float
    avg_volume_20: float
    volume_ratio: float
    body_ratio: float          # body / range
    close_position: float      # where close is in the range (0=low, 1=high)
    breakout_level: float      # the resistance level being broken
    breakout_level_type: str   # "52W_HIGH" | "CONSOLIDATION_HIGH" | "PIVOT" | "RANGE_HIGH"
    atr_14: float
    atr_multiple: float        # today's range / ATR
    consolidation_days: int    # how many days it consolidated
    consolidation_range_pct: float
    rs_score: Optional[float] = None
    strength_score: float = 0  # 0-100 composite score
    entry_price: float = 0
    stop_loss: float = 0
    target_1: float = 0
    target_2: float = 0
    risk_reward: float = 0
    notes: str = ""
    alerted: bool = False
    alert_time: Optional[str] = None


@dataclass
class BacktestResult:
    """Result of backtesting the breakout detection on historical data."""
    symbol: str
    total_signals: int = 0
    winners: int = 0
    losers: int = 0
    win_rate: float = 0
    avg_gain_pct: float = 0
    avg_loss_pct: float = 0
    max_gain_pct: float = 0
    max_loss_pct: float = 0
    avg_hold_days: float = 0
    expectancy: float = 0      # (win_rate * avg_gain) - ((1-win_rate) * avg_loss)
    profit_factor: float = 0
    trades: list = field(default_factory=list)


# ─── Core Detection Logic ────────────────────────────────────────────────────

def _calc_atr(highs: list, lows: list, closes: list, period: int = 14) -> list:
    """Calculate Average True Range."""
    atrs = [0.0] * len(closes)
    if len(closes) < period + 1:
        return atrs
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
        trs.append(tr)
    # First ATR = simple avg
    if len(trs) >= period:
        atr = sum(trs[:period]) / period
        atrs[period] = atr
        for i in range(period, len(trs)):
            atr = (atr * (period - 1) + trs[i]) / period
            atrs[i + 1] = atr
    return atrs


def _calc_ema(values: list, period: int) -> list:
    result = [0.0] * len(values)
    if len(values) < period:
        return result
    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    result[period - 1] = ema
    for i in range(period, len(values)):
        ema = values[i] * k + ema * (1 - k)
        result[i] = ema
    return result


def _find_resistance_levels(rows: list[dict], current_idx: int) -> list[dict]:
    """
    Find key resistance levels that matter for breakout trading:
    - Range high (consolidation top — the most common breakout setup)
    - Bull flag channel high (downtrend line after a run-up)
    - Prior swing highs
    - 52-week high
    """
    if current_idx < 10:
        return []

    levels = []
    lookback = min(current_idx, 252)
    window = rows[current_idx - lookback:current_idx]
    if not window:
        return levels

    current_close = rows[current_idx - 1]["close"] if current_idx > 0 else 0
    recent = rows[max(0, current_idx - 60):current_idx]

    # ── 1. Range High / Consolidation top (most important for your style)
    # Look at last 5-60 bars for a tight range, take the high
    for span in [5, 10, 15, 20, 30, 45, 60]:
        if current_idx < span:
            continue
        sub = rows[current_idx - span:current_idx]
        hi = max(r["high"] for r in sub)
        lo = min(r["low"] for r in sub)
        if lo <= 0:
            continue
        range_pct = (hi - lo) / lo * 100
        # Tight range = strong level. < 15% range for 10+ bars is a real base
        if range_pct <= 20 and span >= 5:
            strength = 3 if (range_pct <= 10 and span >= 15) else 2 if range_pct <= 15 else 1
            levels.append({"price": hi, "type": f"RANGE_HIGH_{span}B", "strength": strength})

    # ── 2. Bull flag channel top
    # After an uptrend (20+ bars), price consolidates in a downward channel
    # The top of the flag is the breakout level
    if current_idx >= 30:
        # Check if there was a strong uptrend before the recent consolidation
        trend_start = max(0, current_idx - 60)
        trend_end = max(0, current_idx - 15)
        if trend_end > trend_start:
            trend_bars = rows[trend_start:trend_end]
            flag_bars = rows[trend_end:current_idx]
            if trend_bars and flag_bars:
                trend_gain = (trend_bars[-1]["close"] - trend_bars[0]["close"]) / trend_bars[0]["close"] * 100
                flag_highs = [r["high"] for r in flag_bars]
                flag_lows = [r["low"] for r in flag_bars]
                # Uptrend > 10% followed by a pullback/flag
                if trend_gain > 10 and len(flag_highs) >= 3:
                    # Flag: highs are declining (downward channel)
                    declining_highs = all(flag_highs[i] >= flag_highs[i+1] * 0.99
                                          for i in range(min(3, len(flag_highs)-1)))
                    flag_range = (max(flag_highs) - min(flag_lows)) / min(flag_lows) * 100 if min(flag_lows) > 0 else 99
                    if flag_range < 20:  # Tight flag
                        flag_top = max(flag_highs)
                        levels.append({"price": flag_top, "type": "BULL_FLAG", "strength": 3})

    # ── 3. Swing highs — local maxima with 3+ bars on each side
    search_window = rows[max(0, current_idx - 120):current_idx]
    for i in range(3, len(search_window) - 3):
        h = search_window[i]["high"]
        left = max(r["high"] for r in search_window[max(0, i-3):i])
        right = max(r["high"] for r in search_window[i+1:i+4])
        if h > left and h > right:
            if current_close > 0 and abs(h - current_close) / current_close < 0.08:
                levels.append({"price": h, "type": "SWING_HIGH", "strength": 2})

    # ── 4. 52-week high
    if lookback >= 100:
        high_52w = max(r["high"] for r in window)
        if current_close > 0 and abs(high_52w - current_close) / current_close < 0.05:
            levels.append({"price": high_52w, "type": "52W_HIGH", "strength": 3})

    # Deduplicate levels within 1.5% of each other — keep the stronger one
    levels.sort(key=lambda x: x["price"])
    deduped = []
    for lev in levels:
        if not deduped or abs(lev["price"] - deduped[-1]["price"]) / max(deduped[-1]["price"], 0.01) > 0.015:
            deduped.append(lev)
        elif lev["strength"] > deduped[-1]["strength"]:
            deduped[-1] = lev

    return deduped


def _measure_consolidation(rows: list[dict], end_idx: int, max_days: int = 60) -> tuple[int, float]:
    """
    Measure how long price consolidated before the breakout bar.
    Returns (consolidation_days, consolidation_range_pct).
    A consolidation is a period where price stays within a tight range.
    """
    if end_idx < 5:
        return 0, 100.0

    start = max(0, end_idx - max_days)
    window = rows[start:end_idx]
    if not window:
        return 0, 100.0

    # Walk backward from the breakout bar until range exceeds threshold
    best_days = 0
    best_range = 100.0
    for lookback in range(5, len(window) + 1):
        subset = window[-lookback:]
        hi = max(r["high"] for r in subset)
        lo = min(r["low"] for r in subset)
        if lo <= 0:
            continue
        range_pct = (hi - lo) / lo * 100
        if range_pct <= 20:  # Allow up to 20% range as "consolidation"
            best_days = lookback
            best_range = range_pct
        else:
            break

    return best_days, round(best_range, 2)


def detect_breakout_candle(
    rows: list[dict],
    idx: int,
    config: AlertConfig,
    avg_vol: float,
    atr: float,
) -> Optional[BreakoutSignal]:
    """
    Detect a breakout candle at index `idx`.

    Core criteria (matching your trading style):
    1. Volume >= 2.5x average of last few trading days
    2. Price breaks above a key level (range high, bull flag, swing high)
    3. Bullish candle (close > open, close in upper half of range)
    """
    if idx < 10 or idx >= len(rows):
        return None

    r = rows[idx]
    o, h, l, c, v = r["open"], r["high"], r["low"], r["close"], r["volume"]
    dt = r["date"]

    candle_range = h - l
    if candle_range <= 0 or c <= 0 or avg_vol <= 0:
        return None

    body = abs(c - o)
    body_ratio = body / candle_range
    close_position = (c - l) / candle_range  # 0=low, 1=high

    vol_ratio = v / avg_vol if avg_vol > 0 else 0
    atr_multiple = candle_range / atr if atr > 0 else 0

    # ── PRIMARY FILTER: Volume surge >= 2.5x
    if vol_ratio < config.volume_threshold:
        return None

    # ── Bullish candle: close > open
    if c <= o:
        return None

    # ── Close in upper portion of range (relaxed: top 50%)
    if close_position < config.close_near_high_pct:
        return None

    # ── Body has some substance (relaxed: 30% of range)
    if body_ratio < config.body_ratio_min:
        return None

    # ── Optional ATR filter (disabled by default, vol is primary)
    if config.atr_breakout_multiple > 0 and atr_multiple < config.atr_breakout_multiple:
        return None

    # ── Breaking a key resistance level
    levels = _find_resistance_levels(rows, idx)
    broken_level = None
    prev_close = rows[idx - 1]["close"]
    for lev in sorted(levels, key=lambda x: -x["strength"]):
        level_price = lev["price"]
        # Previous close was at/below the level, current candle breaks above
        if prev_close <= level_price * 1.02 and c > level_price:
            broken_level = lev
            break
        # Or high pierces the level even if close didn't fully clear
        if prev_close <= level_price * 1.01 and h > level_price * 1.005:
            broken_level = lev
            break

    if not broken_level:
        # Even without a clean level break, a massive volume candle (>= 4x)
        # is worth flagging as a VOLUME_SURGE signal
        if vol_ratio >= config.volume_strong_threshold:
            cons_days, cons_range = _measure_consolidation(rows, idx)
            stop_loss = l
            risk = max(c - stop_loss, atr * 0.5)
            return BreakoutSignal(
                symbol=rows[0].get("_symbol", ""),
                signal_type="VOLUME_SURGE",
                date=dt, price=c, close=c, high=h, low=l, open_price=o,
                volume=v, avg_volume_20=avg_vol,
                volume_ratio=round(vol_ratio, 2),
                body_ratio=round(body_ratio, 2),
                close_position=round(close_position, 2),
                breakout_level=0, breakout_level_type="NONE",
                atr_14=round(atr, 2), atr_multiple=round(atr_multiple, 2),
                consolidation_days=cons_days, consolidation_range_pct=cons_range,
                strength_score=round(min(100, vol_ratio * 12 + body_ratio * 10 + close_position * 8), 1),
                entry_price=round(c, 2), stop_loss=round(stop_loss, 2),
                target_1=round(c + risk * 2, 2), target_2=round(c + risk * 3.5, 2),
                risk_reward=round(risk / c * 100, 2) if c > 0 else 0,
                notes=f"🔥 MASSIVE VOL {vol_ratio:.1f}x — watch for follow-through",
            )
        return None

    # ── Consolidation check (relaxed: 5 bars minimum)
    cons_days, cons_range = _measure_consolidation(rows, idx)
    min_base = config.min_base_bars or config.consolidation_days or 5
    max_range = config.max_base_range_pct or config.consolidation_max_range_pct or 20
    # Don't reject if it's breaking a very strong level (52W / bull flag)
    if broken_level["strength"] < 3:
        if cons_days < min_base:
            return None
        if cons_range > max_range:
            return None

    # ── Compute trade plan
    stop_loss = max(l, rows[idx - 1]["low"])
    risk = c - stop_loss
    if risk <= 0:
        risk = atr if atr > 0 else c * 0.03
        stop_loss = c - risk

    target_1 = c + risk * 2
    target_2 = c + risk * 3.5

    # ── Strength score (0-100) — volume-weighted
    score = 0
    score += min(30, vol_ratio * 10)                          # Volume: up to 30 pts (primary)
    score += min(10, body_ratio * 12)                          # Body: up to 10 pts
    score += min(10, close_position * 10)                      # Close position: up to 10 pts
    score += min(10, atr_multiple * 6)                         # ATR expansion: up to 10 pts
    score += min(10, cons_days / 3)                            # Base length: up to 10 pts
    score += broken_level["strength"] * 10                     # Level: up to 30 pts
    score = min(100, round(score, 1))

    # Notes
    notes_parts = []
    if vol_ratio >= config.volume_strong_threshold:
        notes_parts.append(f"🔥 VOL {vol_ratio:.1f}x")
    else:
        notes_parts.append(f"📊 Vol {vol_ratio:.1f}x")
    level_type = broken_level["type"]
    if "52W" in level_type:
        notes_parts.append("🚀 52W HIGH")
    elif "BULL_FLAG" in level_type:
        notes_parts.append("🏁 BULL FLAG BREAK")
    elif "RANGE_HIGH" in level_type:
        notes_parts.append(f"📦 RANGE BREAK ({level_type.split('_')[-1]})")
    elif "SWING" in level_type:
        notes_parts.append("📈 SWING HIGH BREAK")
    if cons_days >= 15:
        notes_parts.append(f"Base {cons_days}d")

    return BreakoutSignal(
        symbol=rows[0].get("_symbol", ""),
        signal_type="BREAKOUT",
        date=dt, price=c, close=c, high=h, low=l, open_price=o,
        volume=v, avg_volume_20=avg_vol,
        volume_ratio=round(vol_ratio, 2),
        body_ratio=round(body_ratio, 2),
        close_position=round(close_position, 2),
        breakout_level=broken_level["price"],
        breakout_level_type=broken_level["type"],
        atr_14=round(atr, 2), atr_multiple=round(atr_multiple, 2),
        consolidation_days=cons_days, consolidation_range_pct=cons_range,
        strength_score=score,
        entry_price=round(c, 2), stop_loss=round(stop_loss, 2),
        target_1=round(target_1, 2), target_2=round(target_2, 2),
        risk_reward=round(risk / c * 100, 2) if c > 0 else 0,
        notes=" | ".join(notes_parts),
    )


def detect_pivot_entry(
    rows: list[dict],
    breakout_idx: int,
    config: AlertConfig,
) -> Optional[BreakoutSignal]:
    """
    After a breakout candle, detect a pivot re-entry:
    Price pulls back to the breakout level and holds, then resumes.
    This is a lower-risk entry point.
    """
    if breakout_idx + 2 >= len(rows):
        return None

    bo_candle = rows[breakout_idx]
    bo_level = bo_candle["high"]  # breakout level is roughly the high of the BO day
    bo_close = bo_candle["close"]

    # Look for pullback within the window
    for i in range(breakout_idx + 1, min(breakout_idx + config.pivot_entry_window + 1, len(rows))):
        r = rows[i]
        # Pullback criteria: low touches or dips below breakout close but doesn't close below
        if r["low"] <= bo_close * 1.02 and r["close"] > bo_close * 0.97:
            # Check if this is a bullish reversal candle
            body = abs(r["close"] - r["open"])
            rng = r["high"] - r["low"]
            if rng <= 0:
                continue
            if r["close"] > r["open"] and body / rng > 0.4:
                # Pivot entry detected
                stop = min(r["low"], bo_candle["low"])
                risk = r["close"] - stop
                if risk <= 0:
                    continue

                return BreakoutSignal(
                    symbol=rows[0].get("_symbol", ""),
                    signal_type="PIVOT_ENTRY",
                    date=r["date"],
                    price=r["close"],
                    close=r["close"],
                    high=r["high"],
                    low=r["low"],
                    open_price=r["open"],
                    volume=r["volume"],
                    avg_volume_20=0,
                    volume_ratio=0,
                    body_ratio=round(body / rng, 2),
                    close_position=round((r["close"] - r["low"]) / rng, 2),
                    breakout_level=round(bo_close, 2),
                    breakout_level_type="PIVOT",
                    atr_14=0,
                    atr_multiple=0,
                    consolidation_days=0,
                    consolidation_range_pct=0,
                    strength_score=60,
                    entry_price=round(r["close"], 2),
                    stop_loss=round(stop, 2),
                    target_1=round(r["close"] + risk * 2, 2),
                    target_2=round(r["close"] + risk * 3.5, 2),
                    risk_reward=round(risk / r["close"] * 100, 2),
                    notes=f"Pivot re-entry {i - breakout_idx}d after breakout",
                )
    return None


def scan_stock_for_breakouts(
    rows: list[dict],
    symbol: str,
    config: AlertConfig,
    scan_last_n: int = 5,
) -> list[BreakoutSignal]:
    """
    Scan a single stock's OHLCV data for breakout signals.
    By default checks the last 5 bars (configurable).
    Returns list of signals found.
    """
    if len(rows) < 30:
        return []

    # Tag rows with symbol for signal creation
    for r in rows:
        r["_symbol"] = symbol

    closes = [r["close"] for r in rows]
    highs = [r["high"] for r in rows]
    lows = [r["low"] for r in rows]
    volumes = [r["volume"] for r in rows]

    atrs = _calc_atr(highs, lows, closes)

    signals = []
    start_idx = max(20, len(rows) - scan_last_n)

    for idx in range(start_idx, len(rows)):
        # Average volume over last N bars (default 5 = "last few trading days")
        n_bars = config.volume_avg_bars or 5
        vol_window = volumes[max(0, idx - n_bars):idx]
        avg_vol = sum(vol_window) / len(vol_window) if vol_window else 1

        atr = atrs[idx] if idx < len(atrs) else atrs[-1]

        signal = detect_breakout_candle(rows, idx, config, avg_vol, atr)
        if signal:
            signal.symbol = symbol
            signals.append(signal)

            # Also check for pivot entry after this breakout
            pivot = detect_pivot_entry(rows, idx, config)
            if pivot:
                pivot.symbol = symbol
                signals.append(pivot)

    return signals


# ─── Backtesting ─────────────────────────────────────────────────────────────

def backtest_breakout_detection(
    rows: list[dict],
    symbol: str,
    config: AlertConfig,
    hold_days: int = 20,
    stop_loss_pct: float = 0,  # 0 = use signal's SL
) -> BacktestResult:
    """
    Backtest the breakout detection on historical data.
    For each detected breakout, simulate entry at close and measure outcome after hold_days.
    Uses signal's stop loss if stop_loss_pct=0.
    """
    if len(rows) < 60:
        return BacktestResult(symbol=symbol)

    for r in rows:
        r["_symbol"] = symbol

    closes = [r["close"] for r in rows]
    highs = [r["high"] for r in rows]
    lows = [r["low"] for r in rows]
    volumes = [r["volume"] for r in rows]
    atrs = _calc_atr(highs, lows, closes)

    trades = []
    skip_until = 0

    for idx in range(30, len(rows) - hold_days):
        if idx < skip_until:
            continue

        n_bars = config.volume_avg_bars or 5
        vol_window = volumes[max(0, idx - n_bars):idx]
        avg_vol = sum(vol_window) / len(vol_window) if vol_window else 1
        atr = atrs[idx] if idx < len(atrs) else 0

        signal = detect_breakout_candle(rows, idx, config, avg_vol, atr)
        if not signal:
            continue

        # Simulate trade
        entry = rows[idx]["close"]
        sl = signal.stop_loss if not stop_loss_pct else entry * (1 - stop_loss_pct / 100)
        best_price = entry
        worst_price = entry
        exit_price = entry
        exit_reason = "HOLD_EXPIRED"
        exit_idx = idx + hold_days

        for j in range(idx + 1, min(idx + hold_days + 1, len(rows))):
            if rows[j]["low"] <= sl:
                exit_price = sl
                exit_reason = "SL_HIT"
                exit_idx = j
                break
            if rows[j]["high"] > best_price:
                best_price = rows[j]["high"]
            if rows[j]["low"] < worst_price:
                worst_price = rows[j]["low"]
            exit_price = rows[j]["close"]

        gain_pct = round((exit_price - entry) / entry * 100, 2)
        max_fav = round((best_price - entry) / entry * 100, 2)
        max_adv = round((worst_price - entry) / entry * 100, 2)

        trades.append({
            "symbol": symbol,
            "entry_date": rows[idx]["date"],
            "exit_date": rows[min(exit_idx, len(rows) - 1)]["date"],
            "entry": round(entry, 2),
            "exit": round(exit_price, 2),
            "sl": round(sl, 2),
            "gain_pct": gain_pct,
            "max_favorable_pct": max_fav,
            "max_adverse_pct": max_adv,
            "exit_reason": exit_reason,
            "hold_days": exit_idx - idx,
            "volume_ratio": signal.volume_ratio,
            "strength_score": signal.strength_score,
            "level_type": signal.breakout_level_type,
        })

        # Skip forward to avoid double-counting
        skip_until = idx + 3

    # Compute stats
    result = BacktestResult(symbol=symbol, total_signals=len(trades), trades=trades)
    if not trades:
        return result

    wins = [t for t in trades if t["gain_pct"] > 0]
    losses = [t for t in trades if t["gain_pct"] <= 0]
    result.winners = len(wins)
    result.losers = len(losses)
    result.win_rate = round(len(wins) / len(trades) * 100, 1)

    if wins:
        result.avg_gain_pct = round(sum(t["gain_pct"] for t in wins) / len(wins), 2)
        result.max_gain_pct = round(max(t["gain_pct"] for t in wins), 2)
    if losses:
        result.avg_loss_pct = round(sum(t["gain_pct"] for t in losses) / len(losses), 2)
        result.max_loss_pct = round(min(t["gain_pct"] for t in losses), 2)

    result.avg_hold_days = round(sum(t["hold_days"] for t in trades) / len(trades), 1)

    # Expectancy
    avg_w = result.avg_gain_pct if result.avg_gain_pct else 0
    avg_l = abs(result.avg_loss_pct) if result.avg_loss_pct else 0
    wr = result.win_rate / 100
    result.expectancy = round(wr * avg_w - (1 - wr) * avg_l, 2)

    # Profit factor
    gross_profit = sum(t["gain_pct"] for t in wins) if wins else 0
    gross_loss = abs(sum(t["gain_pct"] for t in losses)) if losses else 0.01
    result.profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 999

    return result


# ─── Alert Message Formatting ────────────────────────────────────────────────

def _format_signal_message(signal: BreakoutSignal, html: bool = False) -> str:
    """Format a breakout signal into a readable alert message."""
    emoji = "🚀" if signal.signal_type == "BREAKOUT" else "🔄"
    vol_emoji = "🔥" if signal.volume_ratio >= 2.5 else "📊"
    b = "<b>" if html else "*"
    be = "</b>" if html else "*"
    nl = "<br>" if html else "\n"
    line = "━" * 18

    return (
        f"{emoji} {b}{signal.signal_type}: {signal.symbol}{be}{nl}"
        f"{line}{nl}"
        f"💰 Price: ₹{signal.close:.2f}{nl}"
        f"📈 Breaking: ₹{signal.breakout_level:.2f} ({signal.breakout_level_type}){nl}"
        f"{vol_emoji} Volume: {signal.volume_ratio:.1f}x avg ({signal.volume:,.0f}){nl}"
        f"📊 Body: {signal.body_ratio:.0%} | ATR: {signal.atr_multiple:.1f}x{nl}"
        f"📦 Base: {signal.consolidation_days}d ({signal.consolidation_range_pct:.1f}%){nl}"
        f"⭐ Score: {signal.strength_score:.0f}/100{nl}"
        f"{line}{nl}"
        f"🎯 Entry: ₹{signal.entry_price:.2f}{nl}"
        f"🛑 SL: ₹{signal.stop_loss:.2f} ({signal.risk_reward:.1f}%){nl}"
        f"✅ T1: ₹{signal.target_1:.2f}{nl}"
        f"✅ T2: ₹{signal.target_2:.2f}{nl}"
        + (f"{nl}💡 {signal.notes}" if signal.notes else "")
    )


def _format_summary_message(signals: list[BreakoutSignal], html: bool = False) -> str:
    b = "<b>" if html else "*"
    be = "</b>" if html else "*"
    nl = "<br>" if html else "\n"
    lines = [f"🔔 {b}{len(signals)} Breakout Alert(s){be}{nl}"]
    for s in sorted(signals, key=lambda x: -x.strength_score):
        emoji = "🚀" if s.signal_type == "BREAKOUT" else "🔄"
        lines.append(
            f"{emoji} {b}{s.symbol}{be} ₹{s.close:.0f} | "
            f"Vol {s.volume_ratio:.1f}x | Score {s.strength_score:.0f} | "
            f"SL ₹{s.stop_loss:.0f}"
        )
    return nl.join(lines)


# ─── Telegram Alerting (FREE) ───────────────────────────────────────────────

def send_telegram_alert(signal: BreakoutSignal, config: AlertConfig) -> bool:
    """Send a Telegram alert for a breakout signal. Completely free."""
    if not config.telegram_enabled:
        return False
    if not config.telegram_bot_token or not config.telegram_chat_id:
        return False
    try:
        import urllib.request, urllib.error
        msg = _format_signal_message(signal, html=False)
        url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
        payload = json.dumps({
            "chat_id": config.telegram_chat_id,
            "text": msg,
            "parse_mode": "Markdown",
        }).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                return result.get("ok", False)
        except urllib.error.HTTPError as e:
            # If Markdown fails, retry without parse_mode
            payload2 = json.dumps({
                "chat_id": config.telegram_chat_id,
                "text": msg.replace("*", ""),
            }).encode()
            req2 = urllib.request.Request(url, data=payload2,
                                          headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                return json.loads(resp2.read()).get("ok", False)
    except Exception as e:
        print(f"⚠ Telegram alert failed: {e}", flush=True)
        return False


def send_telegram_summary(signals: list[BreakoutSignal], config: AlertConfig) -> bool:
    """Send a summary Telegram message."""
    if not config.telegram_enabled or not config.telegram_bot_token or not config.telegram_chat_id:
        return False
    try:
        import urllib.request
        msg = _format_summary_message(signals, html=False)
        url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
        payload = json.dumps({
            "chat_id": config.telegram_chat_id,
            "text": msg,
            "parse_mode": "Markdown",
        }).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except Exception as e:
        print(f"⚠ Telegram summary failed: {e}", flush=True)
        return False


def send_telegram_text(text: str, config: AlertConfig) -> bool:
    """Send a plain text Telegram message (for testing)."""
    if not config.telegram_bot_token or not config.telegram_chat_id:
        return False
    try:
        import urllib.request, urllib.error
        url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
        payload = json.dumps({
            "chat_id": config.telegram_chat_id,
            "text": text,
        }).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
            desc = body.get("description", str(e))
        except Exception:
            desc = str(e)
        hint = ""
        if "chat not found" in desc.lower():
            hint = " → Open Telegram, search for your bot, and press START first!"
        elif "bot was blocked" in desc.lower():
            hint = " → Unblock the bot in Telegram and press START again."
        print(f"⚠ Telegram text failed: {desc}{hint}", flush=True)
        return False
    except Exception as e:
        print(f"⚠ Telegram text failed: {e}", flush=True)
        return False


# ─── Gmail SMTP Alerting (FREE) ─────────────────────────────────────────────

def send_email_alert(signal: BreakoutSignal, config: AlertConfig) -> bool:
    """Send an email alert via Gmail SMTP. Free with Gmail app password."""
    if not config.email_enabled:
        return False
    if not all([config.gmail_address, config.gmail_app_password, config.email_to]):
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        emoji = "🚀" if signal.signal_type == "BREAKOUT" else "🔄"
        subject = f"{emoji} {signal.signal_type}: {signal.symbol} ₹{signal.close:.0f} — Score {signal.strength_score:.0f}"
        body_html = _format_signal_message(signal, html=True)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = config.gmail_address
        msg["To"] = config.email_to
        msg.attach(MIMEText(_format_signal_message(signal, html=False), "plain", "utf-8"))
        msg.attach(MIMEText(f"<html><body style='font-family:monospace;background:#0f172a;color:#e2e8f0;padding:16px;'>{body_html}</body></html>", "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(config.gmail_address, config.gmail_app_password)
            server.sendmail(config.gmail_address, config.email_to, msg.as_string())
        return True
    except Exception as e:
        print(f"⚠ Email alert failed: {e}", flush=True)
        return False


def send_email_summary(signals: list[BreakoutSignal], config: AlertConfig) -> bool:
    """Send a summary email."""
    if not config.email_enabled or not all([config.gmail_address, config.gmail_app_password, config.email_to]):
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        subject = f"🔔 {len(signals)} Breakout Alert(s) — SETUPS Scanner"
        body_text = _format_summary_message(signals, html=False)
        body_html = _format_summary_message(signals, html=True)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = config.gmail_address
        msg["To"] = config.email_to
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(f"<html><body style='font-family:monospace;background:#0f172a;color:#e2e8f0;padding:16px;'>{body_html}</body></html>", "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(config.gmail_address, config.gmail_app_password)
            server.sendmail(config.gmail_address, config.email_to, msg.as_string())
        return True
    except Exception as e:
        print(f"⚠ Email summary failed: {e}", flush=True)
        return False


# ─── Unified Alert Dispatcher ────────────────────────────────────────────────

def send_alert(signal: BreakoutSignal, config: AlertConfig) -> dict:
    """Send alert via all enabled channels. Returns status per channel."""
    results = {}
    if config.telegram_enabled:
        results["telegram"] = send_telegram_alert(signal, config)
    if config.email_enabled:
        results["email"] = send_email_alert(signal, config)
    return results


def send_alert_summary(signals: list[BreakoutSignal], config: AlertConfig) -> dict:
    results = {}
    if config.telegram_enabled:
        results["telegram"] = send_telegram_summary(signals, config)
    if config.email_enabled:
        results["email"] = send_email_summary(signals, config)
    return results


# ─── Intraday 30-min Data Fetching ───────────────────────────────────────────

def _fetch_intraday_30m(symbol: str, days: int = 5) -> list[dict]:
    """
    Fetch 30-min intraday candles for an NSE stock via yfinance.
    Returns list of OHLCV dicts with 'datetime' (ISO str), 'date', etc.
    """
    try:
        import yfinance as yf
        ticker = symbol.upper()
        if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
            ticker = ticker + ".NS"
        df = yf.download(ticker, period=f"{days}d", interval="30m", progress=False)
        if df is None or df.empty:
            return []
        # Handle multi-level columns from yfinance
        if hasattr(df.columns, 'levels') and len(df.columns.levels) > 1:
            df.columns = df.columns.get_level_values(0)
        rows = []
        for ts, row in df.iterrows():
            o = float(row.get("Open", 0) or 0)
            h = float(row.get("High", 0) or 0)
            lo = float(row.get("Low", 0) or 0)
            c = float(row.get("Close", 0) or 0)
            v = float(row.get("Volume", 0) or 0)
            if c <= 0:
                continue
            dt_str = ts.strftime("%Y-%m-%d %H:%M")
            rows.append({
                "datetime": dt_str,
                "date": ts.strftime("%Y-%m-%d"),
                "time": ts.strftime("%H:%M"),
                "open": o, "high": h, "low": lo, "close": c, "volume": v,
            })
        return rows
    except Exception as e:
        print(f"⚠ Intraday fetch failed for {symbol}: {e}", flush=True)
        return []


def _detect_intraday_breakout(
    intraday_rows: list[dict],
    daily_rows: list[dict],
    symbol: str,
    config: AlertConfig,
) -> Optional[BreakoutSignal]:
    """
    Detect breakout on the LATEST 30-min candle:
    1. Volume of this 30-min candle >= 2.5x avg of last N 30-min candles
    2. Price breaks a key daily resistance level
    3. Bullish candle (close > open)
    """
    if len(intraday_rows) < 6:
        return None

    # Latest completed 30-min candle
    candle = intraday_rows[-1]
    o, h, l, c, v = candle["open"], candle["high"], candle["low"], candle["close"], candle["volume"]
    dt = candle.get("datetime", candle["date"])

    candle_range = h - l
    if candle_range <= 0 or c <= 0:
        return None

    body = abs(c - o)
    body_ratio = body / candle_range
    close_position = (c - l) / candle_range

    # Volume: compare to avg of last N 30-min candles (excluding current)
    n_bars = config.volume_avg_bars or 5
    prev_candles = intraday_rows[-(n_bars + 1):-1]
    prev_volumes = [r["volume"] for r in prev_candles if r["volume"] > 0]
    avg_vol = sum(prev_volumes) / len(prev_volumes) if prev_volumes else 1
    vol_ratio = v / avg_vol if avg_vol > 0 else 0

    # PRIMARY: Volume surge
    if vol_ratio < config.volume_threshold:
        return None

    # Bullish
    if c <= o:
        return None

    # Close in upper half
    if close_position < config.close_near_high_pct:
        return None

    # Body substance
    if body_ratio < config.body_ratio_min:
        return None

    # Find key resistance levels from DAILY data (excluding today)
    if not daily_rows or len(daily_rows) < 20:
        return None

    # Exclude today's daily bar so levels aren't distorted by today's move
    today_date = candle.get("date", "")
    daily_for_levels = [r for r in daily_rows if r["date"] < today_date] if today_date else daily_rows
    if len(daily_for_levels) < 20:
        daily_for_levels = daily_rows  # fallback

    for r in daily_for_levels:
        r["_symbol"] = symbol
    levels = _find_resistance_levels(daily_for_levels, len(daily_for_levels))

    # Check: is this candle breaking above a daily resistance level?
    # Use previous day's close as reference (not just prev 30-min candle)
    # because breakouts gap up at open
    prev_30m_close = intraday_rows[-2]["close"] if len(intraday_rows) >= 2 else 0
    # Find the last candle from a different date (previous day's last candle)
    today = candle.get("date", "")
    prev_day_close = daily_rows[-1]["close"] if daily_rows else prev_30m_close
    for r in reversed(intraday_rows[:-1]):
        if r.get("date", "") != today:
            prev_day_close = r["close"]
            break

    broken_level = None
    for lev in sorted(levels, key=lambda x: -x["strength"]):
        level_price = lev["price"]
        # Key check: previous day close was at/below the level, and current 30m candle is above
        if prev_day_close <= level_price * 1.02 and c > level_price:
            broken_level = lev
            break
        # Or: previous 30-min candle was below, and this one breaks above (intraday range expansion)
        if prev_30m_close <= level_price * 1.02 and c > level_price:
            broken_level = lev
            break
        # Or: candle high pierces the level
        if prev_30m_close <= level_price * 1.01 and h > level_price * 1.005 and c > level_price * 0.99:
            broken_level = lev
            break
        # Gap-up breakout: today's open gapped above the level (prev day was below)
        if prev_day_close <= level_price * 1.02 and o > level_price and c > level_price:
            broken_level = lev
            break

    signal_type = "BREAKOUT"
    if not broken_level:
        # No level break — but if volume is extreme (>= 4x), still alert as VOLUME_SURGE
        if vol_ratio >= config.volume_strong_threshold:
            signal_type = "VOLUME_SURGE"
            broken_level = {"price": 0, "type": "NONE", "strength": 0}
        else:
            return None

    # ATR from daily data (excluding today)
    highs = [r["high"] for r in daily_for_levels]
    lows = [r["low"] for r in daily_for_levels]
    closes = [r["close"] for r in daily_for_levels]
    atrs = _calc_atr(highs, lows, closes)
    atr = atrs[-1] if atrs else candle_range

    # Trade plan
    stop_loss = l  # 30-min candle low
    risk = c - stop_loss
    if risk <= 0:
        risk = atr * 0.5
        stop_loss = c - risk

    target_1 = c + risk * 2
    target_2 = c + risk * 3.5
    atr_multiple = candle_range / atr if atr > 0 else 0

    # Consolidation from daily (excluding today)
    cons_days, cons_range = _measure_consolidation(daily_for_levels, len(daily_for_levels))

    # Score — heavily weighted on volume (the primary signal)
    score = 0
    score += min(30, vol_ratio * 10)
    score += min(10, body_ratio * 12)
    score += min(10, close_position * 10)
    score += min(10, atr_multiple * 6)
    score += min(10, cons_days / 3)
    score += broken_level["strength"] * 10
    score = min(100, round(score, 1))

    notes_parts = [f"⏱ 30min candle {candle.get('time', '')}"]
    if vol_ratio >= config.volume_strong_threshold:
        notes_parts.append(f"🔥 VOL {vol_ratio:.1f}x")
    else:
        notes_parts.append(f"📊 Vol {vol_ratio:.1f}x")
    lt = broken_level["type"]
    if "52W" in lt:
        notes_parts.append("🚀 52W HIGH")
    elif "BULL_FLAG" in lt:
        notes_parts.append("🏁 FLAG BREAK")
    elif "RANGE" in lt:
        notes_parts.append(f"📦 RANGE BREAK")
    elif "SWING" in lt:
        notes_parts.append("📈 SWING BREAK")
    elif signal_type == "VOLUME_SURGE":
        notes_parts.append("⚡ MASSIVE VOLUME — watch for follow-through")

    return BreakoutSignal(
        symbol=symbol,
        signal_type=signal_type,
        date=dt,
        price=c, close=c, high=h, low=l, open_price=o,
        volume=v, avg_volume_20=avg_vol,
        volume_ratio=round(vol_ratio, 2),
        body_ratio=round(body_ratio, 2),
        close_position=round(close_position, 2),
        breakout_level=broken_level["price"],
        breakout_level_type=broken_level["type"],
        atr_14=round(atr, 2), atr_multiple=round(atr_multiple, 2),
        consolidation_days=cons_days, consolidation_range_pct=cons_range,
        strength_score=score,
        entry_price=round(c, 2), stop_loss=round(stop_loss, 2),
        target_1=round(target_1, 2), target_2=round(target_2, 2),
        risk_reward=round(risk / c * 100, 2) if c > 0 else 0,
        notes=" | ".join(notes_parts),
    )


# ─── Alert State Persistence ─────────────────────────────────────────────────

class AlertState:
    """Persists alert configuration and signal history to JSON files."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.config_path = data_dir / "breakout_alert_config.json"
        self.signals_path = data_dir / "breakout_alert_signals.json"
        self.backtest_path = data_dir / "breakout_alert_backtest.json"
        self._lock = threading.Lock()
        data_dir.mkdir(parents=True, exist_ok=True)

    def load_config(self) -> AlertConfig:
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text())
                # Load env vars as fallback
                data.setdefault("telegram_bot_token", os.environ.get("TELEGRAM_BOT_TOKEN", ""))
                data.setdefault("telegram_chat_id", os.environ.get("TELEGRAM_CHAT_ID", ""))
                data.setdefault("gmail_address", os.environ.get("GMAIL_ADDRESS", ""))
                data.setdefault("gmail_app_password", os.environ.get("GMAIL_APP_PASSWORD", ""))
                data.setdefault("email_to", os.environ.get("ALERT_EMAIL_TO", ""))
                return AlertConfig(**{k: v for k, v in data.items()
                                      if k in AlertConfig.__dataclass_fields__})
            except Exception:
                pass
        # Default config with env vars
        return AlertConfig(
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
            gmail_address=os.environ.get("GMAIL_ADDRESS", ""),
            gmail_app_password=os.environ.get("GMAIL_APP_PASSWORD", ""),
            email_to=os.environ.get("ALERT_EMAIL_TO", ""),
        )

    def save_config(self, config: AlertConfig):
        with self._lock:
            self.config_path.write_text(json.dumps(asdict(config), indent=2))

    def load_signals(self) -> list[dict]:
        if self.signals_path.exists():
            try:
                return json.loads(self.signals_path.read_text())
            except Exception:
                pass
        return []

    def save_signals(self, signals: list[dict]):
        with self._lock:
            # Keep last 500 signals
            self.signals_path.write_text(
                json.dumps(signals[-500:], indent=2, default=str))

    def append_signals(self, new_signals: list[BreakoutSignal]):
        with self._lock:
            existing = self.load_signals()
            for s in new_signals:
                d = asdict(s)
                d["detected_at"] = datetime.now().isoformat()
                existing.append(d)
            self.signals_path.write_text(
                json.dumps(existing[-500:], indent=2, default=str))

    def save_backtest(self, results: dict):
        with self._lock:
            self.backtest_path.write_text(json.dumps(results, indent=2, default=str))

    def load_backtest(self) -> dict:
        if self.backtest_path.exists():
            try:
                return json.loads(self.backtest_path.read_text())
            except Exception:
                pass
        return {}


# ─── Background Scanner ─────────────────────────────────────────────────────

class BreakoutScanner:
    """
    Background scanner that checks watchlist stocks for breakouts on 30-min candles.
    During market hours: fetches live 30-min intraday data, detects breakouts on each candle close.
    After hours: falls back to daily data scan.
    Sends instant Telegram/Gmail alerts for new signals.
    """

    def __init__(self, data_dir: Path, cache_dir: Path, read_ohlcv_fn=None):
        self.state = AlertState(data_dir)
        self.cache_dir = cache_dir
        self._read_ohlcv = read_ohlcv_fn
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_scan_time: Optional[str] = None
        self._last_scan_results: list[dict] = []
        self._lock = threading.Lock()
        self._alerted_keys: set = set()  # "symbol:datetime:type" to avoid dupes
        self._scan_mode: str = "idle"    # "intraday" | "daily" | "idle"

    @property
    def is_running(self) -> bool:
        return self._running

    def status(self) -> dict:
        with self._lock:
            return {
                "running": self._running,
                "lastScanTime": self._last_scan_time,
                "lastSignalCount": len(self._last_scan_results),
                "alertedCount": len(self._alerted_keys),
                "scanMode": self._scan_mode,
            }

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _is_market_hours(self) -> bool:
        """Check if NSE market is open (9:15 AM - 3:30 PM IST, Mon-Fri)."""
        try:
            from datetime import timezone
            ist = timezone(timedelta(hours=5, minutes=30))
            now = datetime.now(ist)
            if now.weekday() >= 5:  # Sat/Sun
                return False
            market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
            market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
            return market_open <= now <= market_close
        except Exception:
            return False

    def _loop(self):
        """
        Main scanner loop.
        During market hours: scan every 2 min using live 30-min intraday candles.
        After hours: scan once with daily data, then sleep longer.
        """
        while self._running:
            try:
                config = self.state.load_config()
                if config.enabled:
                    if self._is_market_hours():
                        self._scan_mode = "intraday"
                        self._scan_intraday(config)
                    else:
                        self._scan_mode = "daily"
                        self._scan_daily(config)
            except Exception as e:
                print(f"⚠ Breakout scanner error: {e}", flush=True)

            config = self.state.load_config()
            interval = config.scan_interval_seconds if self._is_market_hours() else 300
            for _ in range(interval):
                if not self._running:
                    return
                time.sleep(1)

    def _scan_intraday(self, config: AlertConfig) -> list[BreakoutSignal]:
        """
        LIVE INTRADAY SCAN: Fetch 30-min candles and detect breakouts.
        This runs every ~2 min during market hours.
        """
        symbols = self._get_watchlist_symbols()
        if not symbols:
            return []

        print(f"🔍 Intraday scan: {len(symbols)} stocks at {datetime.now().strftime('%H:%M:%S')}", flush=True)

        all_signals = []
        for sym in symbols:
            try:
                # Fetch live 30-min intraday candles
                intraday = _fetch_intraday_30m(sym, days=5)
                if not intraday or len(intraday) < 6:
                    continue

                # Also get daily data for resistance levels
                daily = self._get_ohlcv(sym, days=252)
                if not daily or len(daily) < 20:
                    continue

                signal = _detect_intraday_breakout(intraday, daily, sym, config)
                if signal:
                    all_signals.append(signal)
            except Exception as e:
                print(f"  ⚠ {sym}: {e}", flush=True)
                continue

        return self._process_signals(all_signals, config)

    def _scan_daily(self, config: AlertConfig) -> list[BreakoutSignal]:
        """After-hours scan using daily data (fallback)."""
        symbols = self._get_watchlist_symbols()
        if not symbols:
            return []

        all_signals = []
        for sym in symbols:
            try:
                rows = self._get_ohlcv(sym)
                if not rows or len(rows) < 30:
                    continue
                signals = scan_stock_for_breakouts(rows, sym, config, scan_last_n=2)
                all_signals.extend(signals)
            except Exception:
                continue

        return self._process_signals(all_signals, config)

    def _process_signals(self, all_signals: list[BreakoutSignal], config: AlertConfig) -> list[BreakoutSignal]:
        """Filter dupes, send alerts, persist."""
        new_signals = []
        for s in all_signals:
            key = f"{s.symbol}:{s.date}:{s.signal_type}"
            if key not in self._alerted_keys:
                new_signals.append(s)
                self._alerted_keys.add(key)

        if new_signals:
            print(f"  🔔 {len(new_signals)} NEW signal(s)!", flush=True)
            for s in new_signals:
                print(f"     {s.signal_type}: {s.symbol} ₹{s.close:.1f} Vol {s.volume_ratio:.1f}x", flush=True)
                # Send individual alert for each signal (for quick action)
                send_alert(s, config)

        if new_signals:
            self.state.append_signals(new_signals)

        with self._lock:
            self._last_scan_time = datetime.now().isoformat(timespec="seconds")
            self._last_scan_results = [asdict(s) for s in all_signals]

        return all_signals

    def _get_watchlist_symbols(self) -> list[str]:
        wl_path = self.state.data_dir / "watchlist.json"
        if wl_path.exists():
            try:
                items = json.loads(wl_path.read_text())
                return [i.get("symbol", "").upper() for i in items if i.get("symbol")]
            except Exception:
                pass
        return []

    def scan_now(self, symbols: list[str] | None = None, intraday: bool = False) -> list[dict]:
        """
        Run an immediate scan. If intraday=True, uses live 30-min candles.
        Returns signal dicts.
        """
        config = self.state.load_config()

        if symbols is None:
            symbols = self._get_watchlist_symbols()
        if not symbols:
            return []

        all_signals = []
        for sym in symbols:
            try:
                if intraday:
                    intra = _fetch_intraday_30m(sym, days=5)
                    daily = self._get_ohlcv(sym, days=252)
                    if intra and len(intra) >= 6 and daily and len(daily) >= 20:
                        signal = _detect_intraday_breakout(intra, daily, sym, config)
                        if signal:
                            all_signals.append(signal)
                else:
                    rows = self._get_ohlcv(sym)
                    if rows and len(rows) >= 30:
                        signals = scan_stock_for_breakouts(rows, sym, config, scan_last_n=3)
                        all_signals.extend(signals)
            except Exception as e:
                print(f"  ⚠ {sym}: {e}", flush=True)
                continue

        result = [asdict(s) for s in all_signals]
        result.sort(key=lambda x: -x.get("strength_score", 0))

        if all_signals:
            self.state.append_signals(all_signals)

        with self._lock:
            self._last_scan_time = datetime.now().isoformat(timespec="seconds")
            self._last_scan_results = result

        return result

    def backtest_watchlist(self, symbols: list[str] | None = None,
                           hold_days: int = 20) -> dict:
        """Backtest breakout detection on watchlist stocks."""
        config = self.state.load_config()

        if symbols is None:
            wl_path = self.state.data_dir / "watchlist.json"
            if wl_path.exists():
                try:
                    items = json.loads(wl_path.read_text())
                    symbols = [i.get("symbol", "").upper() for i in items if i.get("symbol")]
                except Exception:
                    symbols = []

        if not symbols:
            return {"error": "No symbols to backtest"}

        results = {}
        aggregate = BacktestResult(symbol="AGGREGATE")
        all_trades = []

        for sym in symbols:
            try:
                rows = self._get_ohlcv(sym, days=0)  # all data
                if not rows or len(rows) < 60:
                    continue
                bt = backtest_breakout_detection(rows, sym, config, hold_days=hold_days)
                results[sym] = asdict(bt)
                all_trades.extend(bt.trades)
            except Exception as e:
                results[sym] = {"error": str(e)}

        # Aggregate stats
        if all_trades:
            wins = [t for t in all_trades if t["gain_pct"] > 0]
            losses = [t for t in all_trades if t["gain_pct"] <= 0]
            aggregate.total_signals = len(all_trades)
            aggregate.winners = len(wins)
            aggregate.losers = len(losses)
            aggregate.win_rate = round(len(wins) / len(all_trades) * 100, 1)
            if wins:
                aggregate.avg_gain_pct = round(sum(t["gain_pct"] for t in wins) / len(wins), 2)
                aggregate.max_gain_pct = round(max(t["gain_pct"] for t in wins), 2)
            if losses:
                aggregate.avg_loss_pct = round(sum(t["gain_pct"] for t in losses) / len(losses), 2)
                aggregate.max_loss_pct = round(min(t["gain_pct"] for t in losses), 2)
            aggregate.avg_hold_days = round(sum(t["hold_days"] for t in all_trades) / len(all_trades), 1)
            wr = aggregate.win_rate / 100
            aggregate.expectancy = round(
                wr * (aggregate.avg_gain_pct or 0) - (1 - wr) * abs(aggregate.avg_loss_pct or 0), 2)
            gp = sum(t["gain_pct"] for t in wins) if wins else 0
            gl = abs(sum(t["gain_pct"] for t in losses)) if losses else 0.01
            aggregate.profit_factor = round(gp / gl, 2) if gl > 0 else 999
            aggregate.trades = sorted(all_trades, key=lambda t: t["entry_date"], reverse=True)[:50]

        output = {
            "aggregate": asdict(aggregate),
            "bySymbol": results,
            "holdDays": hold_days,
            "symbolCount": len(symbols),
            "generatedAt": datetime.now().isoformat(),
        }

        self.state.save_backtest(output)
        return output

    def _get_ohlcv(self, symbol: str, days: int = 252) -> list[dict]:
        """Read OHLCV data for a symbol."""
        if self._read_ohlcv:
            return self._read_ohlcv(symbol, days)

        # Fallback: read from cache directory
        base = symbol.upper().replace(".NS", "").replace(".BO", "")
        for prefix in [base + ".NS", base]:
            csv_path = self.cache_dir / f"{prefix}.csv"
            if csv_path.exists():
                return self._read_csv(csv_path, days)
        return []

    def _read_csv(self, path: Path, days: int = 252) -> list[dict]:
        rows = []
        try:
            with open(path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        d = row.get("date", "") or row.get("Date", "")
                        if not d:
                            continue
                        cl = float(row.get("close", row.get("Close", 0)) or 0)
                        if cl <= 0:
                            continue
                        rows.append({
                            "date": d[:10],
                            "open": float(row.get("open", row.get("Open", 0)) or 0),
                            "high": float(row.get("high", row.get("High", 0)) or 0),
                            "low": float(row.get("low", row.get("Low", 0)) or 0),
                            "close": cl,
                            "volume": float(row.get("volume", row.get("Volume", 0)) or 0),
                        })
                    except Exception:
                        pass
        except Exception:
            pass
        rows.sort(key=lambda r: r["date"])
        if days and days > 0 and len(rows) > days:
            rows = rows[-days:]
        return rows

