"""
utils.py
────────
Shared utility functions used across the Python pipeline.
Centralises helpers that were previously duplicated across
run_full_us_scan.py, run_backtest.py, stock_analyzer.py and
trade_plan_assistant.py.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


# ── Numeric helpers ───────────────────────────────────────────────────────────

def to_float(value: Any, default: float = 0.0) -> float:
    """Safe coercion to float; strips %, commas and x suffixes."""
    try:
        if value is None:
            return default
        return float(str(value).strip().replace("%", "").replace(",", "").replace("x", ""))
    except Exception:
        return default


def safe_return(closes: list[float], bars: int) -> float:
    """Percentage return over the last *bars* close values (as a decimal, e.g. 0.05 = +5 %)."""
    if bars <= 0 or len(closes) <= bars:
        return 0.0
    old = closes[-bars - 1]
    return 0.0 if old <= 0 else (closes[-1] / old) - 1.0


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


# ── Iteration helpers ─────────────────────────────────────────────────────────

def chunks(lst: list, n: int) -> Iterator[list]:
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


# ── OHLCV bar helpers ─────────────────────────────────────────────────────────

def aggregate_weekly_bars(rows: list[dict]) -> list[dict]:
    """Aggregate daily OHLCV rows into ISO-week bars."""
    weekly: list[dict] = []
    current: dict | None = None
    current_key: tuple | None = None

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
                "open":   to_float(row.get("open")),
                "high":   to_float(row.get("high")),
                "low":    to_float(row.get("low")),
                "close":  to_float(row.get("close")),
                "volume": to_float(row.get("volume")),
            }
        else:
            current["high"]   = max(to_float(current.get("high")), to_float(row.get("high")))
            current["low"]    = min(to_float(current.get("low"), 1e12), to_float(row.get("low"), 1e12))
            current["close"]  = to_float(row.get("close"))
            current["volume"] = to_float(current.get("volume")) + to_float(row.get("volume"))
            current["date"]   = dt.isoformat()

    if current is not None:
        weekly.append(current)
    return weekly


def _cache_candidates(symbol: str, lookback: int, timeframe: str, cache_dir: str) -> list[Path]:
    cache = Path(cache_dir)
    suffixes = {lookback}
    if timeframe == "weekly":
        suffixes.add(max(lookback * 7, lookback + 60))
    suffixes.update({252, 728})
    files = [cache / f"{symbol}_{n}.csv" for n in sorted(suffixes)]
    existing = [p for p in files if p.exists()]
    return existing if existing else sorted(cache.glob(f"{symbol}_*.csv"))


def load_cached_bars(symbol: str, lookback: int, timeframe: str, cache_dir: str) -> list[dict]:
    """Load OHLCV bars for *symbol* from cache CSVs; returns weekly bars if requested."""
    for path in _cache_candidates(symbol, lookback, timeframe, cache_dir):
        try:
            rows: list[dict] = []
            with open(path, newline="") as fh:
                for row in csv.DictReader(fh):
                    rows.append({
                        "date":   str(row.get("date") or "").strip(),
                        "open":   to_float(row.get("open")),
                        "high":   to_float(row.get("high")),
                        "low":    to_float(row.get("low")),
                        "close":  to_float(row.get("close")),
                        "volume": to_float(row.get("volume")),
                    })
            if len(rows) >= 30:
                if timeframe == "weekly":
                    weekly = aggregate_weekly_bars(rows)
                    if len(weekly) >= 10:
                        return weekly
                else:
                    return rows
        except Exception:
            continue
    return []


# ── Progress display ──────────────────────────────────────────────────────────

def progress_bar(done: int, total: int, width: int = 40) -> str:
    """Return an ASCII progress bar string."""
    pct    = done / total if total else 0
    filled = int(width * pct)
    bar    = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {done}/{total} ({pct * 100:.1f}%)"

