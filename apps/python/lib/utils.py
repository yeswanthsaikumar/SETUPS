"""
utils.py
────────
Shared utility functions used across the Python pipeline.
"""

from __future__ import annotations

import csv
from datetime import datetime, date, timedelta, timezone
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


# ── Data-date freshness helpers ───────────────────────────────────────────────

_MAX_DATA_GAP_DAYS = 5  # >5 calendar days between last candle and today = definitely stale

try:
    import pytz as _pytz
    _IST = _pytz.timezone("Asia/Kolkata")
except ImportError:
    _IST = None  # fallback: use UTC offset naively

def _ist_now() -> datetime:
    """Current datetime in IST (UTC+5:30)."""
    try:
        if _IST:
            return datetime.now(_IST)
    except Exception:
        pass
    # Fallback: UTC + 5:30
    from datetime import timezone as _tz
    return datetime.now(_tz.utc) + timedelta(hours=5, minutes=30)


def _is_data_current_enough(last_date_str: str) -> bool:
    """
    Return True if the last candle date is 'current enough' — meaning no closed
    NSE trading session is missing from the data.

    Mirrors the logic in YahooFinanceProvider.java::isDataCurrentEnough().

    Rules (in IST):
    - 0–1 calendar days gap → fresh
    - > _MAX_DATA_GAP_DAYS  → stale
    - 2–_MAX_DATA_GAP_DAYS:
        count Mon–Fri days in gap (ignoring holidays — simple heuristic)
        • 0 biz-days (pure weekend) → fresh
        • ≥2 biz-days              → stale
        • 1 biz-day (likely today) → stale only if NSE has closed (≥15:35 IST)
    """
    if not last_date_str:
        return False
    try:
        last_date = datetime.fromisoformat(last_date_str).date()
    except ValueError:
        return False

    today = _ist_now().date()
    days_since = (today - last_date).days

    if days_since <= 1:
        return True
    if days_since > _MAX_DATA_GAP_DAYS:
        return False

    biz_days = sum(
        1 for d in range(1, days_since + 1)
        if (last_date + timedelta(days=d)).weekday() < 5  # Mon=0 … Fri=4
    )

    if biz_days == 0:
        return True   # pure weekend gap
    if biz_days >= 2:
        return False  # missed 2+ business days

    # Exactly 1 biz-day missed: stale only after NSE closes (15:35 IST)
    ist_now = _ist_now()
    nse_close_today = ist_now.replace(hour=15, minute=35, second=0, microsecond=0)
    return ist_now < nse_close_today


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
                "date":   dt.isoformat(),
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
    """
    Return candidate cache file paths in preference order.

    Priority:
    1. Exact-size fresh file  (SYMBOL_{lookback}.csv)
    2. Exact-size stale file  (same, if no fresh one)
    3. Larger files sorted by data freshness first, then by size (smallest adequate)
    """
    cache = Path(cache_dir)
    exact = cache / f"{symbol}_{lookback}.csv"

    # Build superset of candidate sizes
    suffixes: set[int] = {lookback, 252, 728}
    if timeframe == "weekly":
        suffixes.add(max(lookback * 7, lookback + 60))

    named = [cache / f"{symbol}_{n}.csv" for n in sorted(suffixes)]
    named_existing = [p for p in named if p.exists()]

    # Fallback glob
    all_existing = sorted(cache.glob(f"{symbol}_*.csv")) if not named_existing else []

    candidates = named_existing or all_existing

    # Sort: fresh files first (by data date), then by size (smaller = less I/O)
    def sort_key(p: Path):
        try:
            with open(p, newline="") as fh:
                reader = csv.DictReader(fh)
                last_date = ""
                for row in reader:
                    last_date = str(row.get("date", "")).strip()
            # Fresh files score 0, stale score 1 (so fresh sort before stale)
            freshness = 0 if _is_data_current_enough(last_date) else 1
            # Secondary: file size (smaller = prefer)
            try:
                size = p.stat().st_size
            except OSError:
                size = 10 ** 9
            return (freshness, size)
        except Exception:
            return (1, 10 ** 9)

    candidates.sort(key=sort_key)
    return candidates


def load_cached_bars(symbol: str, lookback: int, timeframe: str, cache_dir: str) -> list[dict]:
    """Load OHLCV bars for *symbol* from cache CSVs; returns weekly bars if requested.

    Prefers files whose last candle date is 'current enough' (see _is_data_current_enough).
    Falls back to stale files if no fresh file exists (graceful degradation).
    """
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

