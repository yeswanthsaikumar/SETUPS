#!/usr/bin/env python3
"""
EMA & ADR Filter Script
-----------------------
Goes through all VCP hits (filtered stocks) and finds those that:
1. Are still "working" (price above 10 EMA and 20 EMA, EMAs stacked correctly)
2. Not too extended from 10 EMA and 20 EMA (within ~3-5% of each)
3. Have strong ADR% values (good daily range for momentum entries)

ADR% = Average Daily Range as a percentage of price (using 20-day lookback)
"""

import csv
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
CACHE_DIR = BASE_DIR / "cache"
VCP_HITS_FILE = BASE_DIR / "output" / "vcp_hits_india_daily_full_LATEST.csv"
WATCHLIST_FILE = BASE_DIR / "output" / "watchlist_india_daily_full_LATEST.csv"


def ema(prices, period):
    """Calculate Exponential Moving Average."""
    if len(prices) < period:
        return None
    multiplier = 2 / (period + 1)
    ema_val = sum(prices[:period]) / period  # SMA seed
    for price in prices[period:]:
        ema_val = (price - ema_val) * multiplier + ema_val
    return ema_val


def calculate_adr_percent(highs, lows, period=20):
    """Calculate Average Daily Range as a percentage of the avg price."""
    if len(highs) < period or len(lows) < period:
        return None
    recent_highs = highs[-period:]
    recent_lows = lows[-period:]
    daily_ranges = []
    for h, l in zip(recent_highs, recent_lows):
        if l > 0:
            daily_ranges.append((h - l) / l * 100)
    if not daily_ranges:
        return None
    return sum(daily_ranges) / len(daily_ranges)


def load_price_data(symbol):
    """Load OHLCV data from cache CSV."""
    # Try .NS suffix first (Indian stocks), then raw symbol
    candidates = [
        CACHE_DIR / f"{symbol}.csv",
        CACHE_DIR / f"{symbol.replace('.NS', '')}.csv",
    ]
    for filepath in candidates:
        if filepath.exists():
            dates, opens, highs, lows, closes, volumes = [], [], [], [], [], []
            with open(filepath, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        dates.append(row["date"])
                        opens.append(float(row["open"]))
                        highs.append(float(row["high"]))
                        lows.append(float(row["low"]))
                        closes.append(float(row["close"]))
                        volumes.append(float(row.get("volume", 0)))
                    except (ValueError, KeyError):
                        continue
            return dates, opens, highs, lows, closes, volumes
    return None


def analyze_stock(symbol, scan_data):
    """Analyze a single stock for EMA proximity and ADR."""
    data = load_price_data(symbol)
    if data is None:
        return None

    dates, opens, highs, lows, closes, volumes = data

    if len(closes) < 50:  # Need enough data
        return None

    # Calculate EMAs on full close series
    ema10 = ema(closes, 10)
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)

    if ema10 is None or ema20 is None:
        return None

    last_close = closes[-1]
    last_date = dates[-1]

    # Distance from EMAs (percentage)
    dist_10ema = ((last_close - ema10) / ema10) * 100
    dist_20ema = ((last_close - ema20) / ema20) * 100

    # ADR%
    adr_pct = calculate_adr_percent(highs, lows, 20)
    if adr_pct is None:
        return None

    # EMA stacking: 10 EMA > 20 EMA (bullish structure)
    ema_stacked = ema10 > ema20

    # Price above both EMAs
    above_10ema = last_close >= ema10 * 0.99  # allow tiny margin
    above_20ema = last_close >= ema20 * 0.99

    # RS score from scan data
    rs_score = scan_data.get("rsScore", "")
    rating = scan_data.get("rating", "")
    setup = scan_data.get("setup", "")
    setup_subtype = scan_data.get("setupSubtype", "")
    score = scan_data.get("score", "")
    entry = scan_data.get("entry", "")
    earnings = scan_data.get("triggerEarningsGrowth", "")

    return {
        "symbol": symbol,
        "close": round(last_close, 2),
        "last_date": last_date,
        "ema10": round(ema10, 2),
        "ema20": round(ema20, 2),
        "dist_10ema_pct": round(dist_10ema, 2),
        "dist_20ema_pct": round(dist_20ema, 2),
        "adr_pct": round(adr_pct, 2),
        "ema_stacked": ema_stacked,
        "above_10ema": above_10ema,
        "above_20ema": above_20ema,
        "ema50": round(ema50, 2) if ema50 else None,
        "rs_score": rs_score,
        "rating": rating,
        "setup": setup,
        "setup_subtype": setup_subtype,
        "score": score,
        "entry": entry,
        "earnings": earnings[:60] if earnings else "",
    }


def main():
    # Load all symbols from VCP hits
    symbols_data = {}

    for filepath in [VCP_HITS_FILE, WATCHLIST_FILE]:
        if not filepath.exists():
            print(f"⚠ File not found: {filepath}")
            continue
        with open(filepath, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = row.get("symbol", "").strip()
                if sym and sym not in symbols_data:
                    symbols_data[sym] = row

    print(f"📊 Analyzing {len(symbols_data)} filtered stocks from scan output...\n")

    results = []
    skipped = 0

    for symbol, scan_data in symbols_data.items():
        result = analyze_stock(symbol, scan_data)
        if result is None:
            skipped += 1
            continue
        results.append(result)

    # ─── FILTER CRITERIA ───
    # 1. Still working: price above both EMAs, EMAs stacked bullish
    # 2. Not too extended: within 0-5% of 10 EMA, within 0-7% of 20 EMA
    # 3. Strong ADR: >= 3% ADR (good intraday range for swing entries)

    MAX_DIST_10EMA = 5.0   # Not more than 5% above 10 EMA
    MAX_DIST_20EMA = 7.0   # Not more than 7% above 20 EMA
    MIN_ADR = 3.0           # At least 3% ADR

    filtered = []
    for r in results:
        if not r["above_10ema"] or not r["above_20ema"]:
            continue
        if not r["ema_stacked"]:
            continue
        if r["dist_10ema_pct"] < -1.0:  # Slightly below 10EMA is ok, but not much
            continue
        if r["dist_10ema_pct"] > MAX_DIST_10EMA:
            continue
        if r["dist_20ema_pct"] > MAX_DIST_20EMA:
            continue
        if r["adr_pct"] < MIN_ADR:
            continue
        filtered.append(r)

    # Sort by: closest to 10EMA first (best entry proximity), then by ADR descending
    filtered.sort(key=lambda x: (x["dist_10ema_pct"], -x["adr_pct"]))

    # ─── OUTPUT ───
    print("=" * 140)
    print(f"  STOCKS STILL WORKING — NEAR 10/20 EMA — STRONG ADR  (Filters: dist_10EMA ≤ {MAX_DIST_10EMA}%, dist_20EMA ≤ {MAX_DIST_20EMA}%, ADR ≥ {MIN_ADR}%)")
    print("=" * 140)
    print(f"  {'#':<4} {'Symbol':<20} {'Close':>10} {'10EMA':>10} {'20EMA':>10} {'Dist10':>8} {'Dist20':>8} {'ADR%':>7} {'Rating':>7} {'Setup':<22} {'Score':>6} {'RS':>6}")
    print("-" * 140)

    for i, r in enumerate(filtered, 1):
        print(
            f"  {i:<4} {r['symbol']:<20} {r['close']:>10.2f} {r['ema10']:>10.2f} {r['ema20']:>10.2f} "
            f"{r['dist_10ema_pct']:>+7.2f}% {r['dist_20ema_pct']:>+7.2f}% {r['adr_pct']:>6.2f}% "
            f"{r['rating']:>7} {r['setup']:<22} {r['score']:>6} {r['rs_score']:>6}"
        )

    print("-" * 140)
    print(f"\n  ✅ {len(filtered)} stocks passed filters out of {len(results)} analyzed ({skipped} had no cache data)")

    # ─── TIER BREAKDOWN ───
    tier1 = [r for r in filtered if r["dist_10ema_pct"] <= 2.0 and r["adr_pct"] >= 4.0]
    tier2 = [r for r in filtered if r not in tier1 and r["dist_10ema_pct"] <= 3.0 and r["adr_pct"] >= 3.5]
    tier3 = [r for r in filtered if r not in tier1 and r not in tier2]

    if tier1:
        print(f"\n{'=' * 140}")
        print(f"  🔥 TIER 1 — BEST ENTRIES (within 2% of 10EMA, ADR ≥ 4%) — {len(tier1)} stocks")
        print(f"{'=' * 140}")
        print(f"  {'#':<4} {'Symbol':<20} {'Close':>10} {'Dist10':>8} {'Dist20':>8} {'ADR%':>7} {'Rating':>7} {'Setup':<22} {'Earnings':<60}")
        print("-" * 140)
        for i, r in enumerate(tier1, 1):
            print(
                f"  {i:<4} {r['symbol']:<20} {r['close']:>10.2f} "
                f"{r['dist_10ema_pct']:>+7.2f}% {r['dist_20ema_pct']:>+7.2f}% {r['adr_pct']:>6.2f}% "
                f"{r['rating']:>7} {r['setup']:<22} {r['earnings']:<60}"
            )

    if tier2:
        print(f"\n{'=' * 140}")
        print(f"  ⚡ TIER 2 — GOOD ENTRIES (within 3% of 10EMA, ADR ≥ 3.5%) — {len(tier2)} stocks")
        print(f"{'=' * 140}")
        print(f"  {'#':<4} {'Symbol':<20} {'Close':>10} {'Dist10':>8} {'Dist20':>8} {'ADR%':>7} {'Rating':>7} {'Setup':<22} {'Earnings':<60}")
        print("-" * 140)
        for i, r in enumerate(tier2, 1):
            print(
                f"  {i:<4} {r['symbol']:<20} {r['close']:>10.2f} "
                f"{r['dist_10ema_pct']:>+7.2f}% {r['dist_20ema_pct']:>+7.2f}% {r['adr_pct']:>6.2f}% "
                f"{r['rating']:>7} {r['setup']:<22} {r['earnings']:<60}"
            )

    print(f"\n{'=' * 140}")
    print("  LEGEND:")
    print("    Dist10/Dist20 = % distance from 10/20 EMA (lower = closer to EMA = better entry)")
    print("    ADR% = Average Daily Range % (higher = more volatile = more R potential)")
    print("    EMA stacked = 10EMA > 20EMA (bullish trend structure)")
    print(f"{'=' * 140}")


if __name__ == "__main__":
    main()

