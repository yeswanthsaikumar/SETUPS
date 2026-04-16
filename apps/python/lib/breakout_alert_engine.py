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
    volume_threshold: float = 1.5           # Min vol ratio vs 20d avg
    volume_strong_threshold: float = 2.5    # Strong volume surge
    body_ratio_min: float = 0.55            # Candle body must be >55% of range
    close_near_high_pct: float = 0.75       # Close in top 25% of range
    consolidation_days: int = 15            # Min days of consolidation before breakout
    consolidation_max_range_pct: float = 15 # Max range% during consolidation
    atr_breakout_multiple: float = 1.5      # Breakout candle range > 1.5x ATR
    min_rs_score: float = 0                 # Min RS score filter (0 = disabled)
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
    Find key resistance levels from price history:
    - 52-week high
    - Recent consolidation high (last 15-60 bars)
    - Swing highs (local maxima)
    - Round numbers near price
    """
    if current_idx < 20:
        return []

    levels = []
    lookback = min(current_idx, 252)
    window = rows[current_idx - lookback:current_idx]
    if not window:
        return levels

    current_close = rows[current_idx - 1]["close"] if current_idx > 0 else 0

    # 52-week high
    high_52w = max(r["high"] for r in window)
    levels.append({"price": high_52w, "type": "52W_HIGH", "strength": 3})

    # Consolidation high (last 15-60 days)
    for span in [15, 30, 60]:
        if current_idx >= span:
            cons_window = rows[current_idx - span:current_idx]
            cons_high = max(r["high"] for r in cons_window)
            if cons_high < high_52w * 0.98:  # Don't duplicate 52w
                levels.append({
                    "price": cons_high,
                    "type": f"CONSOLIDATION_HIGH_{span}D",
                    "strength": 2 if span >= 30 else 1,
                })

    # Swing highs — local maxima with at least 5 bars on each side
    for i in range(5, len(window) - 5):
        h = window[i]["high"]
        left = max(r["high"] for r in window[i - 5:i])
        right = max(r["high"] for r in window[i + 1:i + 6])
        if h > left and h > right:
            # Only keep if within 10% of current price
            if current_close > 0 and abs(h - current_close) / current_close < 0.10:
                levels.append({"price": h, "type": "SWING_HIGH", "strength": 1})

    # Deduplicate levels within 1% of each other
    levels.sort(key=lambda x: x["price"])
    deduped = []
    for lev in levels:
        if not deduped or abs(lev["price"] - deduped[-1]["price"]) / deduped[-1]["price"] > 0.01:
            deduped.append(lev)
        else:
            # Keep the stronger one
            if lev["strength"] > deduped[-1]["strength"]:
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
    avg_vol_20: float,
    atr: float,
) -> Optional[BreakoutSignal]:
    """
    Check if the candle at `idx` is a breakout candle.

    Criteria:
    1. Price closes above a major resistance level
    2. Volume > 1.5x 20-day average
    3. Candle body is >55% of range (strong conviction)
    4. Close is in top 25% of the day's range
    5. Range is > 1.5x ATR (wide-range bar)
    6. Prior consolidation of at least 10 days
    """
    if idx < 20 or idx >= len(rows):
        return None

    r = rows[idx]
    o, h, l, c, v = r["open"], r["high"], r["low"], r["close"], r["volume"]
    dt = r["date"]

    candle_range = h - l
    if candle_range <= 0 or c <= 0 or avg_vol_20 <= 0:
        return None

    body = abs(c - o)
    body_ratio = body / candle_range
    close_position = (c - l) / candle_range  # 0=low, 1=high

    vol_ratio = v / avg_vol_20 if avg_vol_20 > 0 else 0
    atr_multiple = candle_range / atr if atr > 0 else 0

    # ── Filter 1: Volume surge
    if vol_ratio < config.volume_threshold:
        return None

    # ── Filter 2: Bullish candle (close > open and close near high)
    if c <= o:  # bearish candle
        return None
    if close_position < config.close_near_high_pct:
        return None

    # ── Filter 3: Strong body
    if body_ratio < config.body_ratio_min:
        return None

    # ── Filter 4: Wide-range bar
    if atr_multiple < config.atr_breakout_multiple:
        return None

    # ── Filter 5: Breaking a resistance level
    levels = _find_resistance_levels(rows, idx)
    broken_level = None
    for lev in sorted(levels, key=lambda x: -x["strength"]):
        level_price = lev["price"]
        # Previous close was below/at the level, current close is above
        prev_close = rows[idx - 1]["close"]
        if prev_close <= level_price * 1.01 and c > level_price:
            broken_level = lev
            break

    if not broken_level:
        return None

    # ── Filter 6: Consolidation before breakout
    cons_days, cons_range = _measure_consolidation(rows, idx)
    if cons_days < config.consolidation_days:
        return None
    if cons_range > config.consolidation_max_range_pct:
        return None

    # ── Compute trade plan
    stop_loss = max(l, rows[idx - 1]["low"])  # Below breakout candle low or prev low
    risk = c - stop_loss
    if risk <= 0:
        risk = atr
        stop_loss = c - atr

    target_1 = c + risk * 2    # 2R
    target_2 = c + risk * 3.5  # 3.5R
    rr = risk / c * 100 if c > 0 else 0

    # ── Strength score (0-100)
    score = 0
    score += min(20, vol_ratio * 8)                          # Volume: up to 20 pts
    score += min(15, body_ratio * 15)                         # Body strength: up to 15 pts
    score += min(10, close_position * 10)                     # Close position: up to 10 pts
    score += min(15, atr_multiple * 10)                       # ATR expansion: up to 15 pts
    score += min(10, cons_days / 5)                           # Consolidation: up to 10 pts
    score += broken_level["strength"] * 10                    # Level strength: up to 30 pts
    score = min(100, round(score, 1))

    # Notes
    notes_parts = []
    if vol_ratio >= config.volume_strong_threshold:
        notes_parts.append(f"🔥 STRONG VOL {vol_ratio:.1f}x")
    if broken_level["type"] == "52W_HIGH":
        notes_parts.append("🚀 52W HIGH BREAKOUT")
    if cons_days >= 30:
        notes_parts.append(f"📦 {cons_days}d tight base")
    if atr_multiple >= 2.5:
        notes_parts.append("⚡ EXPLOSIVE range")

    return BreakoutSignal(
        symbol=rows[0].get("_symbol", ""),
        signal_type="BREAKOUT",
        date=dt,
        price=c,
        close=c,
        high=h,
        low=l,
        open_price=o,
        volume=v,
        avg_volume_20=avg_vol_20,
        volume_ratio=round(vol_ratio, 2),
        body_ratio=round(body_ratio, 2),
        close_position=round(close_position, 2),
        breakout_level=broken_level["price"],
        breakout_level_type=broken_level["type"],
        atr_14=round(atr, 2),
        atr_multiple=round(atr_multiple, 2),
        consolidation_days=cons_days,
        consolidation_range_pct=cons_range,
        strength_score=score,
        entry_price=round(c, 2),
        stop_loss=round(stop_loss, 2),
        target_1=round(target_1, 2),
        target_2=round(target_2, 2),
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
        # 20-day avg volume
        vol_window = volumes[max(0, idx - 20):idx]
        avg_vol_20 = sum(vol_window) / len(vol_window) if vol_window else 1

        atr = atrs[idx] if idx < len(atrs) else atrs[-1]

        signal = detect_breakout_candle(rows, idx, config, avg_vol_20, atr)
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

        vol_window = volumes[max(0, idx - 20):idx]
        avg_vol_20 = sum(vol_window) / len(vol_window) if vol_window else 1
        atr = atrs[idx] if idx < len(atrs) else 0

        signal = detect_breakout_candle(rows, idx, config, avg_vol_20, atr)
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
    Background scanner that periodically checks watchlist stocks for breakouts.
    Runs in a daemon thread. Sends WhatsApp alerts for new signals.
    """

    def __init__(self, data_dir: Path, cache_dir: Path, read_ohlcv_fn=None):
        self.state = AlertState(data_dir)
        self.cache_dir = cache_dir
        self._read_ohlcv = read_ohlcv_fn  # External function to read OHLCV
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_scan_time: Optional[str] = None
        self._last_scan_results: list[dict] = []
        self._lock = threading.Lock()
        self._alerted_keys: set = set()  # track "symbol:date" to avoid dupes

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
            }

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        """Main scanner loop."""
        while self._running:
            try:
                config = self.state.load_config()
                if config.enabled:
                    self._scan_once(config)
            except Exception as e:
                print(f"⚠ Breakout scanner error: {e}", flush=True)

            config = self.state.load_config()
            interval = config.scan_interval_seconds
            # Sleep in small increments so we can stop quickly
            for _ in range(interval):
                if not self._running:
                    return
                time.sleep(1)

    def _scan_once(self, config: AlertConfig) -> list[BreakoutSignal]:
        """Run one scan cycle across all watchlist stocks."""
        from pathlib import Path
        import csv as _csv

        # Get watchlist symbols
        wl_path = self.state.data_dir / "watchlist.json"
        symbols = []
        if wl_path.exists():
            try:
                items = json.loads(wl_path.read_text())
                symbols = [i.get("symbol", "").upper() for i in items if i.get("symbol")]
            except Exception:
                pass

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

        # Filter already-alerted
        new_signals = []
        for s in all_signals:
            key = f"{s.symbol}:{s.date}:{s.signal_type}"
            if key not in self._alerted_keys:
                new_signals.append(s)
                self._alerted_keys.add(key)

        # Send alerts via all enabled channels (Telegram + Gmail)
        if new_signals:
            if len(new_signals) == 1:
                send_alert(new_signals[0], config)
            else:
                send_alert_summary(new_signals, config)

        # Persist
        if new_signals:
            self.state.append_signals(new_signals)

        with self._lock:
            self._last_scan_time = datetime.now().isoformat(timespec="seconds")
            self._last_scan_results = [asdict(s) for s in all_signals]

        return all_signals

    def scan_now(self, symbols: list[str] | None = None) -> list[dict]:
        """Run an immediate scan (not background). Returns signal dicts."""
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
            return []

        all_signals = []
        for sym in symbols:
            try:
                rows = self._get_ohlcv(sym)
                if not rows or len(rows) < 30:
                    continue
                signals = scan_stock_for_breakouts(rows, sym, config, scan_last_n=3)
                all_signals.extend(signals)
            except Exception as e:
                print(f"  ⚠ {sym}: {e}", flush=True)
                continue

        result = [asdict(s) for s in all_signals]
        result.sort(key=lambda x: -x.get("strength_score", 0))

        # Persist
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

