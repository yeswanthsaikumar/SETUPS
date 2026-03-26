#!/usr/bin/env python3
"""
run_full_us_scan.py
───────────────────
Runs breakout detection (VCP and/or range-expansion setups) across a stock
universe in parallel Java batches and writes structured output files. It
supports both US and Indian universes, and both daily and weekly scans.

Features:
  • Parallel Java workers  (default: 4 workers x 25 symbols = 100 symbols/round)
  • Rolling CSV auto-save  (every SAVE_EVERY_N_HITS hits)
  • Resume-friendly        (symbols with fresh cache files are detected quickly)
  • Per-batch log          (output/scan_<TIMESTAMP>/batch_log.txt)
  • Summary HTML report    (output/scan_<TIMESTAMP>/summary.html)
  • Daily and weekly scan support
  • Progress bar with ETA

Usage:
    python3 apps/python/cli/run_full_us_scan.py [--symbols data/universes/us_stock_tickers.csv] [--workers 4] [--batch 25] [--setups both]
"""

import argparse
import csv
import html
import json
import logging
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[3]
LIB_DIR = ROOT / "apps" / "python" / "lib"
import sys as _sys
if str(LIB_DIR) not in _sys.path:
    _sys.path.insert(0, str(LIB_DIR))

from setup_detector import (
    detect_mean_reversion,
    detect_breakout_pullback,
    scan_symbols as py_scan_symbols,
    _load_bars as _mr_load_bars,
    _signal_to_dict as _mr_signal_to_dict,
)
from utils import (
    to_float as _to_float,
    safe_return as _safe_return,
    clamp as _clamp,
    mean as _mean,
    chunks,
    aggregate_weekly_bars,
    load_cached_bars,
    progress_bar,
)

_MR_AVAILABLE = True
_PY_BO_AVAILABLE = True


def scan_symbols_for_mean_reversion(symbols, cache_dir, lookback, timeframe, account_size, base_risk_pct, min_price_floor, min_score=35.0):
    """Scan symbols for mean-reversion setups using the unified setup_detector."""
    return py_scan_symbols(
        symbols, cache_dir, lookback,
        timeframe=timeframe,
        account_size=account_size,
        base_risk_pct=base_risk_pct,
        min_price_floor=min_price_floor,
        min_score=min_score,
        setup_types=["MEAN_REVERSION"],
    )


def scan_symbols_for_breakout_pullback(symbols, cache_dir, lookback, timeframe, account_size, base_risk_pct, min_price_floor, min_score=40.0):
    """Scan symbols for first-pullback-after-breakout setups using the unified setup_detector."""
    return py_scan_symbols(
        symbols, cache_dir, lookback,
        timeframe=timeframe,
        account_size=account_size,
        base_risk_pct=base_risk_pct,
        min_price_floor=min_price_floor,
        min_score=min_score,
        setup_types=["BREAKOUT_PULLBACK"],
    )

# ── DEFAULTS ──────────────────────────────────────────────────────────────────
DEFAULT_SYMBOLS_FILE  = str(ROOT / "data" / "universes" / "all_us_stocks.txt")
FALLBACK_SYMBOLS_FILE = str(ROOT / "data" / "universes" / "us_stocks.txt")
CSV_SYMBOLS_FILE      = str(ROOT / "data" / "universes" / "us_stock_tickers.csv")
INDIA_SYMBOLS_FILE    = str(ROOT / "data" / "universes" / "indian_stock_tickers.csv")
DEFAULT_LOOKBACK      = 252
DEFAULT_RETRIES       = 3
DEFAULT_CACHE_DIR     = str(ROOT / "cache")
DEFAULT_CACHE_TTL_MIN = 360                   # 6 hours
DEFAULT_BATCH_SIZE    = 40                    # symbols per Java process (larger = fewer JVM launches)
DEFAULT_WORKERS       = 6                     # concurrent Java processes
SAVE_EVERY_N_HITS     = 30                    # flush CSV every N new hits
SAVE_EVERY_N_BATCHES  = 15                    # refresh output files even if hit count is unchanged
JAVA_TIMEOUT_SEC      = 240                   # kill stalled Java process after 4 min (larger batches)
# JVM flags: -client + TieredStopAtLevel=1 disables full JIT for short-lived batch processes
# This cuts JVM startup from ~2s to ~0.5s at the cost of peak throughput (irrelevant for batch mode)
JVM_FAST_FLAGS        = ["-XX:+TieredCompilation", "-XX:TieredStopAtLevel=1", "-Xms32m", "-Xmx256m"]
DEFAULT_LIQ_LOOKBACK  = 20
DEFAULT_ACCOUNT_SIZE  = 100_000.0
DEFAULT_BASE_RISK_PCT = 0.01
WATCHLIST_RANK_WEIGHTS = {
    "quality": 0.32,
    "pivotProximity": 0.18,
    "rsStrength": 0.18,
    "regimeQuality": 0.12,
    "weeklyAgreement": 0.10,
    "volumeDryUp": 0.06,
    "pivotFreshness": 0.04,
}
WATCHLIST_NEAR_PIVOT_BAND_PCT = 0.025
WATCHLIST_PIVOT_TOUCH_BAND_PCT = 0.01
# ─────────────────────────────────────────────────────────────────────────────

lock = threading.Lock()

EXCLUDED_NAME_TERMS = (
    " warrant",
    " warrants",
    " right",
    " rights",
    " unit",
    " units",
    " preferred",
    " depositary",
    " etf",
    " etn",
    " fund",
    " trust",
)

YAHOO_SUFFIXES = (".NS", ".BO")


def normalize_setups_mode(value: str) -> str:
    mode = (value or "").strip().lower()
    if mode == "all":
        return "full"
    return mode


def parse_args():
    p = argparse.ArgumentParser(description="Full market breakout scan")
    p.add_argument("--symbols",   default=None)
    p.add_argument("--timeframe", choices=["daily", "weekly"], default="daily")
    p.add_argument("--setups", choices=["both", "vcp", "range_expansion", "mean_reversion", "breakout_pullback", "full", "all"], default="full",
                   help="Setup filter: full|both|vcp|range_expansion|mean_reversion|breakout_pullback|all(legacy alias for full)")
    p.add_argument("--market-label", default=None, help="Optional market label for output names, e.g. us or india")
    p.add_argument("--exchange-suffix", default=None, help="Optional Yahoo suffix override such as .NS or .BO")
    p.add_argument("--lookback",  type=int, default=DEFAULT_LOOKBACK)
    p.add_argument("--retries",   type=int, default=DEFAULT_RETRIES)
    p.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)
    p.add_argument("--cache-ttl", "--cache-ttl-min", dest="cache_ttl", type=int, default=DEFAULT_CACHE_TTL_MIN)
    p.add_argument("--batch",     type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--mr-min-score", type=float, default=35.0, help="Minimum quality score for mean reversion setups (default: 35)")
    p.add_argument("--workers",   type=int, default=DEFAULT_WORKERS)
    p.add_argument("--output-dir", default=str(ROOT / "output"))
    p.add_argument("--no-watchlist", action="store_true", help="Skip watchlist generation and only produce breakout/open-trade hits")
    p.add_argument("--min-price-floor", type=float, default=5.0, help="Minimum latest close required for shortlist eligibility")
    p.add_argument("--min-avg-volume", type=float, default=0.0, help="Minimum average volume over liquidity lookback (0 disables)")
    p.add_argument("--min-avg-dollar-volume", type=float, default=0.0, help="Minimum average dollar volume over liquidity lookback (0 disables)")
    p.add_argument("--liquidity-lookback", type=int, default=DEFAULT_LIQ_LOOKBACK)
    p.add_argument("--regime-mode", choices=["off", "soft", "hard"], default="soft", help="Market regime handling: off, soft-rank-penalty, or hard-filter")
    p.add_argument("--regime-sample", type=int, default=300, help="How many symbols to sample for breadth regime estimation")
    p.add_argument("--regime-min-breadth50", type=float, default=0.50)
    p.add_argument("--regime-min-breadth200", type=float, default=0.45)
    p.add_argument("--rs-weight", type=float, default=0.35, help="Weight for RS score when building rankingScore")
    p.add_argument("--max-portfolio-heat-r", type=float, default=6.0, help="Maximum aggregate portfolio heat in R units for shortlist")
    p.add_argument("--account-size", type=float, default=DEFAULT_ACCOUNT_SIZE)
    p.add_argument("--base-risk-pct", type=float, default=DEFAULT_BASE_RISK_PCT, help="Baseline risk-per-trade used to convert risk amount to R")
    args = p.parse_args()
    args.setups = normalize_setups_mode(args.setups)
    if args.setups in {"mean_reversion", "breakout_pullback", "full"} and not _MR_AVAILABLE:
        p.error("Mean reversion / breakout pullback detector is unavailable; ensure apps/python/lib/setup_detector.py is importable")
    if args.batch <= 0:
        p.error("--batch must be greater than 0")
    if args.workers <= 0:
        p.error("--workers must be greater than 0")
    if args.lookback <= 0:
        p.error("--lookback must be greater than 0")
    if args.liquidity_lookback <= 1:
        p.error("--liquidity-lookback must be greater than 1")
    if args.max_portfolio_heat_r <= 0:
        p.error("--max-portfolio-heat-r must be greater than 0")
    if args.account_size <= 0:
        p.error("--account-size must be greater than 0")
    if args.base_risk_pct <= 0:
        p.error("--base-risk-pct must be greater than 0")
    if args.symbols and not os.path.isabs(args.symbols):
        args.symbols = str((ROOT / args.symbols).resolve())
    return args



def build_market_regime(symbols: list[str], args) -> dict:
    if args.regime_mode == "off":
        return {"mode": "off", "favorable": True, "breadth50": 1.0, "breadth200": 1.0, "score": 1.0, "sampled": 0}

    sample = symbols[: max(10, min(len(symbols), args.regime_sample))]

    def _load_symbol(sym: str):
        bars = load_cached_bars(sym, args.lookback, args.timeframe, args.cache_dir)
        if len(bars) < 210:
            return None
        closes = [b["close"] for b in bars if b.get("close", 0) > 0]
        if len(closes) < 210:
            return None
        close = closes[-1]
        ma50 = sum(closes[-50:]) / 50
        ma200 = sum(closes[-200:]) / 200
        return {
            "above50": close > ma50,
            "above200": close > ma200,
            "rs3m": _safe_return(closes, 63),
            "rs6m": _safe_return(closes, 126),
            "rs12m": _safe_return(closes, 252),
        }

    above50 = 0
    above200 = 0
    valid = 0
    rs_pool_3m: list[float] = []
    rs_pool_6m: list[float] = []
    rs_pool_12m: list[float] = []

    # ⚡ Parallel CSV reads — uses up to min(workers, 16) threads
    regime_workers = min(getattr(args, "workers", DEFAULT_WORKERS), 16)
    with ThreadPoolExecutor(max_workers=regime_workers) as ex:
        for result in ex.map(_load_symbol, sample):
            if result is None:
                continue
            valid += 1
            if result["above50"]:
                above50 += 1
            if result["above200"]:
                above200 += 1
            rs_pool_3m.append(result["rs3m"])
            rs_pool_6m.append(result["rs6m"])
            rs_pool_12m.append(result["rs12m"])

    if valid == 0:
        return {"mode": args.regime_mode, "favorable": True, "breadth50": 1.0, "breadth200": 1.0, "score": 1.0, "sampled": 0,
                "bench3m": 0.0, "bench6m": 0.0, "bench12m": 0.0}

    breadth50 = above50 / valid
    breadth200 = above200 / valid
    favorable = breadth50 >= args.regime_min_breadth50 and breadth200 >= args.regime_min_breadth200
    return {
        "mode": args.regime_mode,
        "favorable": favorable,
        "breadth50": breadth50,
        "breadth200": breadth200,
        "score": (breadth50 + breadth200) / 2.0,
        "sampled": valid,
        "bench3m": statistics.median(rs_pool_3m) if rs_pool_3m else 0.0,
        "bench6m": statistics.median(rs_pool_6m) if rs_pool_6m else 0.0,
        "bench12m": statistics.median(rs_pool_12m) if rs_pool_12m else 0.0,
    }


def _pivot_freshness_from_tests(test_count: int) -> tuple[str, float]:
    if test_count <= 1:
        return "FRESH", 100.0
    if test_count == 2:
        return "ACTIVE", 90.0
    if test_count <= 4:
        return "RETESTED", 75.0
    if test_count <= 6:
        return "WORN", 50.0
    if test_count <= 9:
        return "STALE", 30.0
    return "VERY_STALE", 10.0


def compute_watchlist_enrichment(row: dict, bars: list[dict], regime: dict, args) -> dict:
    pivot = _to_float(row.get("pivot"), 0.0)
    dist_pct = abs(_to_float(row.get("dist%"), 0.0))
    quality = _clamp(_to_float(row.get("score"), 0.0))
    rs_raw = _to_float(row.get("rsScore"), 0.0)
    rs_rank_score = _clamp(50.0 + (rs_raw * 1.5))
    regime_support_score = _clamp(_to_float(regime.get("score"), 1.0) * 100.0)

    if regime_support_score >= 70:
        regime_support = "STRONG"
    elif regime_support_score >= 55:
        regime_support = "SUPPORTIVE"
    elif regime_support_score >= 45:
        regime_support = "NEUTRAL"
    else:
        regime_support = "HEADWIND"

    max_dist_pct = 8.0 if args.timeframe == "weekly" else 6.0
    pivot_proximity_score = _clamp((1.0 - (dist_pct / max_dist_pct)) * 100.0) if max_dist_pct > 0 else 0.0

    days_near_pivot = 0
    pivot_test_count = 0
    if pivot > 0 and bars:
        recent_window = bars[max(0, len(bars) - 10):]
        for bar in recent_window:
            close = _to_float(bar.get("close"))
            high = _to_float(bar.get("high"), close)
            if close <= 0:
                continue
            dist_to_pivot = (pivot - close) / pivot
            near_pivot = 0.0 <= dist_to_pivot <= WATCHLIST_NEAR_PIVOT_BAND_PCT
            shadow_near_pivot = high >= pivot * (1.0 - (WATCHLIST_PIVOT_TOUCH_BAND_PCT / 2.0)) and close <= pivot * 1.01
            if near_pivot or shadow_near_pivot:
                days_near_pivot += 1

        for bar in bars[max(0, len(bars) - 30):-1]:
            close = _to_float(bar.get("close"))
            high = _to_float(bar.get("high"), close)
            if close <= 0:
                continue
            touched = (
                (high >= pivot and close <= pivot * 1.005)
                or abs(close - pivot) <= pivot * WATCHLIST_PIVOT_TOUCH_BAND_PCT
                or abs(high - pivot) <= pivot * WATCHLIST_PIVOT_TOUCH_BAND_PCT
            )
            if touched:
                pivot_test_count += 1

    pivot_freshness, pivot_freshness_score = _pivot_freshness_from_tests(pivot_test_count)

    volume_dry_up_ratio = 1.0
    volume_dry_up_score = 50.0
    if len(bars) >= 25:
        recent_vol = _mean([_to_float(b.get("volume")) for b in bars[-5:]])
        prior_vol = _mean([_to_float(b.get("volume")) for b in bars[-25:-5]])
        if prior_vol > 0:
            volume_dry_up_ratio = recent_vol / prior_vol
            volume_dry_up_score = _clamp(((1.25 - volume_dry_up_ratio) / 0.75) * 100.0)

    weekly_agreement = "UNKNOWN"
    weekly_agreement_score = 50.0
    if args.timeframe == "weekly":
        weekly_agreement = "PRIMARY_TIMEFRAME"
        weekly_agreement_score = 100.0
    else:
        weekly_bars = aggregate_weekly_bars(bars)
        if len(weekly_bars) >= 10:
            weekly_closes = [_to_float(b.get("close")) for b in weekly_bars if _to_float(b.get("close")) > 0]
            weekly_highs = [_to_float(b.get("high")) for b in weekly_bars if _to_float(b.get("high")) > 0]
            if weekly_closes and weekly_highs:
                close = weekly_closes[-1]
                ma10 = _mean(weekly_closes[-10:])
                ma30 = _mean(weekly_closes[-30:]) if len(weekly_closes) >= 30 else _mean(weekly_closes)
                recent_high = max(weekly_highs[-26:]) if len(weekly_highs) >= 26 else max(weekly_highs)
                weekly_agreement_score = 0.0
                if close > ma10:
                    weekly_agreement_score += 35.0
                if close > ma30:
                    weekly_agreement_score += 30.0
                if len(weekly_closes) >= 30 and ma10 > ma30:
                    weekly_agreement_score += 20.0
                if recent_high > 0 and ((recent_high - close) / recent_high) <= 0.08:
                    weekly_agreement_score += 15.0
                if len(weekly_closes) >= 3 and weekly_closes[-1] >= weekly_closes[-3]:
                    weekly_agreement_score += 5.0
                weekly_agreement_score = _clamp(weekly_agreement_score)

                if weekly_agreement_score >= 85:
                    weekly_agreement = "STRONG"
                elif weekly_agreement_score >= 65:
                    weekly_agreement = "SUPPORTIVE"
                elif weekly_agreement_score >= 45:
                    weekly_agreement = "MIXED"
                else:
                    weekly_agreement = "WEAK"

    watchlist_quality_score = (
        WATCHLIST_RANK_WEIGHTS["quality"] * quality
        + WATCHLIST_RANK_WEIGHTS["pivotProximity"] * pivot_proximity_score
        + WATCHLIST_RANK_WEIGHTS["rsStrength"] * rs_rank_score
        + WATCHLIST_RANK_WEIGHTS["regimeQuality"] * regime_support_score
        + WATCHLIST_RANK_WEIGHTS["weeklyAgreement"] * weekly_agreement_score
        + WATCHLIST_RANK_WEIGHTS["volumeDryUp"] * volume_dry_up_score
        + WATCHLIST_RANK_WEIGHTS["pivotFreshness"] * pivot_freshness_score
    )

    return {
        "pivotProximityScore": round(pivot_proximity_score, 2),
        "daysNearPivot": days_near_pivot,
        "pivotFreshness": pivot_freshness,
        "pivotFreshnessScore": round(pivot_freshness_score, 2),
        "regimeSupport": regime_support,
        "regimeSupportScore": round(regime_support_score, 2),
        "weeklyAgreement": weekly_agreement,
        "weeklyAgreementScore": round(weekly_agreement_score, 2),
        "rsRankScore": round(rs_rank_score, 2),
        "volumeDryUpScore": round(volume_dry_up_score, 2),
        "volumeDryUpRatio": round(volume_dry_up_ratio, 3),
        "watchlistQualityScore": round(watchlist_quality_score, 2),
    }


def enrich_and_filter_rows(rows: list[dict], args, regime: dict, list_type: str) -> tuple[list[dict], list[dict], dict[str, str]]:
    kept: list[dict] = []
    rejected: list[dict] = []
    rejected_map: dict[str, str] = {}

    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        bars = load_cached_bars(symbol, args.lookback, args.timeframe, args.cache_dir)
        if len(bars) < max(args.liquidity_lookback, 30):
            reason = "DATA_UNAVAILABLE"
            rejected.append({"symbol": symbol, "reason": reason, "source": list_type, "detail": "cache<lookback"})
            rejected_map[symbol] = reason
            continue

        closes = [b["close"] for b in bars]
        vols = [b["volume"] for b in bars]
        liq_n = min(args.liquidity_lookback, len(bars))
        recent = bars[-liq_n:]
        avg_vol = sum(x["volume"] for x in recent) / liq_n
        avg_dollar = sum(x["volume"] * x["close"] for x in recent) / liq_n
        latest_close = closes[-1]

        row["avgVol20"] = round(avg_vol, 2)
        row["avgDollarVol20"] = round(avg_dollar, 2)
        row["regimeScore"] = round(regime.get("score", 1.0) * 100.0, 2)
        row["regimeState"] = "FAVORABLE" if regime.get("favorable", True) else "UNFAVORABLE"

        rs3 = _safe_return(closes, 63)
        rs6 = _safe_return(closes, 126)
        rs12 = _safe_return(closes, 252)
        rel3 = rs3 - regime.get("bench3m", 0.0)
        rel6 = rs6 - regime.get("bench6m", 0.0)
        rel12 = rs12 - regime.get("bench12m", 0.0)
        rs_score = (rel3 * 0.5 + rel6 * 0.3 + rel12 * 0.2) * 100.0
        row["rs3m"] = round(rs3 * 100.0, 2)
        row["rs6m"] = round(rs6 * 100.0, 2)
        row["rs12m"] = round(rs12 * 100.0, 2)
        row["rsScore"] = round(rs_score, 2)
        row.update(compute_watchlist_enrichment(row, bars, regime, args))

        quality = _to_float(row.get("score"))
        rank_score = quality + (args.rs_weight * rs_score)
        if regime.get("mode") == "soft" and not regime.get("favorable", True):
            rank_score -= 10.0
        if str(row.get("listType", list_type)).upper() == "WATCHLIST":
            rank_score = _to_float(row.get("watchlistQualityScore"), rank_score)
        row["rankingScore"] = round(rank_score, 2)

        if latest_close < args.min_price_floor:
            reason = "LOW_PRICE"
            rejected.append({"symbol": symbol, "reason": reason, "source": list_type, "detail": f"close={latest_close:.2f}"})
            rejected_map[symbol] = reason
            continue
        if args.min_avg_volume > 0 and avg_vol < args.min_avg_volume:
            reason = "LOW_VOLUME"
            rejected.append({"symbol": symbol, "reason": reason, "source": list_type, "detail": f"avgVol={avg_vol:.0f}"})
            rejected_map[symbol] = reason
            continue
        if args.min_avg_dollar_volume > 0 and avg_dollar < args.min_avg_dollar_volume:
            reason = "LOW_ADV"
            rejected.append({"symbol": symbol, "reason": reason, "source": list_type, "detail": f"adv={avg_dollar:.0f}"})
            rejected_map[symbol] = reason
            continue
        if regime.get("mode") == "hard" and not regime.get("favorable", True):
            reason = "REGIME_UNFAVORABLE"
            rejected.append({"symbol": symbol, "reason": reason, "source": list_type, "detail": f"breadth50={regime.get('breadth50', 0):.2f}"})
            rejected_map[symbol] = reason
            continue

        kept.append(row)

    return kept, rejected, rejected_map


def apply_portfolio_heat(rows: list[dict], args) -> list[dict]:
    if not rows:
        return []
    sorted_rows = sorted(rows, key=lambda r: _to_float(r.get("rankingScore"), _to_float(r.get("score"))), reverse=True)
    shortlist: list[dict] = []
    selected_symbols: set[str] = set()
    cumulative = 0.0
    denom = args.account_size * args.base_risk_pct
    for row in sorted_rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        if symbol and symbol in selected_symbols:
            continue
        entry = _to_float(row.get("entry"))
        stop = _to_float(row.get("sl"))
        shares = _to_float(row.get("shares"))
        risk_amount = max(0.0, (entry - stop) * shares)
        risk_r = (risk_amount / denom) if denom > 0 else 0.0
        if risk_r <= 0:
            continue
        if cumulative + risk_r > args.max_portfolio_heat_r:
            continue
        cumulative += risk_r
        item = dict(row)
        item["riskR"] = round(risk_r, 3)
        item["heatAfterR"] = round(cumulative, 3)
        shortlist.append(item)
        if symbol:
            selected_symbols.add(symbol)
    return shortlist


def rank_watchlist_rows(rows: list[dict]) -> list[dict]:
    ranked = sorted(
        rows,
        key=lambda r: (
            _to_float(r.get("watchlistQualityScore"), _to_float(r.get("rankingScore"), _to_float(r.get("score")))),
            _to_float(r.get("score")),
            _to_float(r.get("pivotProximityScore")),
            _to_float(r.get("rsScore")),
            _to_float(r.get("regimeSupportScore")),
            _to_float(r.get("weeklyAgreementScore")),
        ),
        reverse=True,
    )
    for idx, row in enumerate(ranked, start=1):
        row["watchlistRank"] = idx
    return ranked


def build_rejection_rows(symbols: list[str], included: set[str], rejected_map: dict[str, str]) -> list[dict]:
    rows: list[dict] = []
    for sym in symbols:
        if sym in included:
            continue
        rows.append({
            "symbol": sym,
            "reason": rejected_map.get(sym, "NO_BREAKOUT_OR_QUALITY"),
            "source": "UNIVERSE",
            "detail": "",
        })
    return rows


def normalize_symbol(raw: str) -> str:
    symbol = raw.strip().upper()
    if any(symbol.endswith(suffix) for suffix in YAHOO_SUFFIXES):
        base = symbol[:-3].replace(".", "-")
        return base + symbol[-3:]
    return symbol.replace(".", "-")


def is_symbol_candidate(symbol: str) -> bool:
    if not symbol:
        return False
    if len(symbol) > 15:
        return False
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-.")
    return all(ch in allowed for ch in symbol)


def is_common_stock_name(name: str) -> bool:
    lowered = f" {name.strip().lower()} "
    return not any(term in lowered for term in EXCLUDED_NAME_TERMS)


def csv_field(row: dict, *names: str) -> str:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        key = name.strip().lower()
        if key in lowered and lowered[key] is not None:
            return lowered[key]
    return ""


def detect_exchange_suffix(path: str, row: dict, args) -> str:
    if args.exchange_suffix:
        suffix = args.exchange_suffix.strip().upper()
        return suffix if suffix.startswith(".") else f".{suffix}"

    exchange = csv_field(row, "exchange")
    if exchange:
        exchange = exchange.strip().upper()
        if exchange == "BSE":
            return ".BO"
        if exchange in {"NSE", "NSEEQ", "NS"}:
            return ".NS"

    path_name = os.path.basename(path).lower()
    if "indian" in path_name or path_name.endswith(".ns.csv"):
        return ".NS"

    return ""


def normalize_csv_symbol(raw_symbol: str, path: str, row: dict, args) -> str:
    symbol = normalize_symbol(raw_symbol)
    if not symbol:
        return ""
    if any(symbol.endswith(suffix) for suffix in YAHOO_SUFFIXES):
        return symbol
    suffix = detect_exchange_suffix(path, row, args)
    return symbol + suffix if suffix else symbol


def load_symbols_from_csv(path: str, args) -> list[str]:
    symbols, seen = [], set()
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            raw_symbol = csv_field(row, "ticker_symbol", "symbol", "ticker", "SYMBOL")
            company_name = csv_field(row, "company_name", "name", "NAME OF COMPANY")
            series = csv_field(row, "SERIES", " SERIES").strip().upper()
            symbol = normalize_csv_symbol(raw_symbol, path, row, args)
            if not is_symbol_candidate(symbol):
                continue
            if series and series not in {"EQ", "SM", "ST"} and path.lower().endswith("indian_stock_tickers.csv"):
                continue
            if company_name and not is_common_stock_name(company_name):
                continue
            if symbol not in seen:
                seen.add(symbol)
                symbols.append(symbol)
    return symbols


def load_symbols_from_text(path: str) -> list[str]:
    syms, seen = [], set()
    with open(path) as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            symbol = normalize_symbol(line.split()[0])
            if not is_symbol_candidate(symbol):
                continue
            if symbol not in seen:
                seen.add(symbol)
                syms.append(symbol)
    return syms


def write_symbol_universe(path: Path, symbols: list[str], source_path: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Normalized symbol universe for VCP scan\n"
        f"# Source: {source_path}\n"
        f"# Total symbols: {len(symbols)}\n"
        + "\n".join(symbols)
        + "\n"
    )


def load_symbols(args) -> tuple[list[str], str]:
    candidates = []
    if args.symbols:
        candidates = [args.symbols]
    else:
        candidates = [INDIA_SYMBOLS_FILE, CSV_SYMBOLS_FILE, DEFAULT_SYMBOLS_FILE, FALLBACK_SYMBOLS_FILE]

    for path in candidates:
        if not os.path.isabs(path):
            path = str((ROOT / path).resolve())
        if os.path.exists(path):
            if path.lower().endswith(".csv"):
                syms = load_symbols_from_csv(path, args)
            else:
                syms = load_symbols_from_text(path)
            print(f"Loaded {len(syms)} symbols from  {path}")
            return syms, path

    print("ERROR: No symbols file found. Run apps/python/cli/fetch_us_stocks.py first.", file=sys.stderr)
    sys.exit(1)


def infer_market_label(source_path: str) -> str:
    name = os.path.basename(source_path).lower()
    if "indian" in name:
        return "india"
    if "us_" in name or name.startswith("all_us") or name.startswith("us_") or "stocks" in name:
        return "us"
    return "market"



def _java_setups(setups: str) -> str | None:
    """Map --setups value to what Java understands. Returns None to skip Java entirely."""
    if setups in ("mean_reversion", "breakout_pullback"):
        return None   # Python-only; no Java call needed
    if setups == "full":
        return "both"  # Java handles vcp+range_expansion; MR+ABFP handled by Python
    return setups  # both | vcp | range_expansion – pass through unchanged


def _run_mr_scan(symbols: list[str], args) -> list[dict]:
    """Run Python mean reversion scan on all symbols from cache."""
    if not _MR_AVAILABLE:
        print("  [WARN] setup_detector not available – skipping MR scan", flush=True)
        return []
    print(f"\n  Running Python mean reversion scan on {len(symbols)} symbols from cache…", flush=True)
    t0 = time.time()
    mr_hits = scan_symbols_for_mean_reversion(
        symbols,
        cache_dir=args.cache_dir,
        lookback=args.lookback,
        timeframe=args.timeframe,
        account_size=args.account_size,
        base_risk_pct=args.base_risk_pct,
        min_price_floor=args.min_price_floor,
        min_score=getattr(args, "mr_min_score", 35.0),
    )
    elapsed = time.time() - t0
    print(f"  Mean reversion scan done in {elapsed:.1f}s → {len(mr_hits)} hits", flush=True)
    return mr_hits


def _run_abfp_scan(symbols: list[str], args) -> list[dict]:
    """Run Python first-pullback-after-breakout scan on all symbols from cache."""
    if not _PY_BO_AVAILABLE:
        print("  [WARN] setup_detector not available – skipping ABFP scan", flush=True)
        return []
    print(f"\n  Running Python breakout-pullback (ABFP) scan on {len(symbols)} symbols from cache…", flush=True)
    t0 = time.time()
    abfp_hits = scan_symbols_for_breakout_pullback(
        symbols,
        cache_dir=args.cache_dir,
        lookback=args.lookback,
        timeframe=args.timeframe,
        account_size=args.account_size,
        base_risk_pct=args.base_risk_pct,
        min_price_floor=args.min_price_floor,
        min_score=40.0,
    )
    elapsed = time.time() - t0
    print(f"  Breakout-pullback scan done in {elapsed:.1f}s → {len(abfp_hits)} hits", flush=True)
    return abfp_hits


def scan_batch(batch: list[str], args) -> list[str]:
    """Invoke Java scanner for one batch; return raw hit lines."""
    java_setup = _java_setups(args.setups)
    if java_setup is None:
        return []   # mean_reversion only – no Java
    cmd = [
        "java", *JVM_FAST_FLAGS, "-cp", "src", "Main",
        "--mode=scan",
        "--provider=yahoo",
        f"--timeframe={args.timeframe}",
        f"--setups={java_setup}",
        f"--symbols={','.join(batch)}",
        f"--lookback={args.lookback}",
        f"--retries={args.retries}",
        f"--cache-dir={args.cache_dir}",
        f"--cache-ttl-min={args.cache_ttl}",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=JAVA_TIMEOUT_SEC,
            cwd=ROOT,
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if proc.returncode != 0:
            with lock:
                print(f"  [WARN] Java batch exited with code {proc.returncode} for {','.join(batch[:5])}", flush=True)
        hits = [
            line.strip()
            for line in combined.splitlines()
            if " Close " in line and " Pivot " in line and " T1 " in line
        ]
        return hits
    except subprocess.TimeoutExpired:
        with lock:
            print(f"  [WARN] batch timed out after {JAVA_TIMEOUT_SEC}s for {','.join(batch[:5])}", flush=True)
        return []


def scan_watchlist_batch(batch: list[str], args) -> list[str]:
    """Invoke Java watchlist mode for one batch; return raw watchlist lines."""
    java_setup = _java_setups(args.setups)
    if java_setup is None:
        return []   # mean_reversion only – no Java
    cmd = [
        "java", *JVM_FAST_FLAGS, "-cp", "src", "Main",
        "--mode=watchlist",
        "--provider=yahoo",
        f"--timeframe={args.timeframe}",
        f"--setups={java_setup}",
        f"--symbols={','.join(batch)}",
        f"--lookback={args.lookback}",
        f"--retries={args.retries}",
        f"--cache-dir={args.cache_dir}",
        f"--cache-ttl-min={args.cache_ttl}",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=JAVA_TIMEOUT_SEC,
            cwd=ROOT,
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if proc.returncode != 0:
            with lock:
                print(f"  [WARN] Java watchlist batch exited with code {proc.returncode} for {','.join(batch[:5])}", flush=True)
        return [line.strip() for line in combined.splitlines() if "| Type WATCHLIST |" in line and " T1 " in line]
    except subprocess.TimeoutExpired:
        with lock:
            print(f"  [WARN] watchlist batch timed out after {JAVA_TIMEOUT_SEC}s for {','.join(batch[:5])}", flush=True)
        return []
    except Exception as exc:
        with lock:
            print(f"  [WARN] watchlist batch error: {exc}", flush=True)


def scan_combined_batch(batch: list[str], args) -> tuple[list[str], list[str]]:
    """
    ⚡ FAST PATH: Run scan + watchlist in a SINGLE JVM call (--mode=combined).
    This halves the JVM startup overhead vs. two separate calls.
    Returns (scan_hits, watchlist_hits).
    """
    java_setup = _java_setups(args.setups)
    if java_setup is None:
        return [], []   # mean_reversion only – no Java
    cmd = [
        "java", *JVM_FAST_FLAGS, "-cp", "src", "Main",
        "--mode=combined",
        "--provider=yahoo",
        f"--timeframe={args.timeframe}",
        f"--setups={java_setup}",
        f"--symbols={','.join(batch)}",
        f"--lookback={args.lookback}",
        f"--retries={args.retries}",
        f"--cache-dir={args.cache_dir}",
        f"--cache-ttl-min={args.cache_ttl}",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=int(JAVA_TIMEOUT_SEC * 1.5),
            cwd=ROOT,
        )
        combined_output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if proc.returncode != 0:
            with lock:
                print(f"  [WARN] Java combined batch exited with code {proc.returncode} for {','.join(batch[:5])}", flush=True)
        lines = combined_output.splitlines()
        hits = [
            line.strip()
            for line in lines
            if " Close " in line and " Pivot " in line and " T1 " in line
            and "| Type WATCHLIST |" not in line
        ]
        watchlist_hits = [
            line.strip()
            for line in lines
            if "| Type WATCHLIST |" in line and " T1 " in line
        ]
        return hits, watchlist_hits
    except subprocess.TimeoutExpired:
        with lock:
            print(f"  [WARN] combined batch timed out for {','.join(batch[:5])}", flush=True)
        return [], []
    except Exception as exc:
        with lock:
            print(f"  [WARN] combined batch error: {exc}", flush=True)
        return [], []



def parse_hit(line: str) -> dict:
    try:
        if "|" not in line:
            tokens = line.split()
            d = {"symbol": tokens[0] if tokens else line, "raw": line, "listType": "BREAKOUT"}
            pairs = {
                "Type": "listType",
                "Setup": "setup",
                "Window": "window",
                "Height": "height%",
                "Depth": "depth%",
                "Len": "len",
                "Ctr": "ctr",
                "Dist": "dist%",
                "Rating": "rating",
                "Close": "close",
                "Pivot": "pivot",
                "Entry": "entry",
                "Score": "score",
                "Range": "range%",
                "Vol": "vol%",
                "RExp": "rexp",
                "Shares": "shares",
                "SL": "sl",
            }
            for key, out_key in pairs.items():
                m = re.search(rf"\\b{key}\\s+([^\\s]+)", line)
                if m:
                    d[out_key] = m.group(1)

            t = re.search(r"\\bT1\\s+([^\\s]+)\\s+T2\\s+([^\\s]+)\\s+T3\\s+([^\\s]+)", line)
            if t:
                d["T1"], d["T2"], d["T3"] = t.group(1), t.group(2), t.group(3)
            return d

        parts = [p.strip() for p in line.split("|")]
        d = {"symbol": parts[0], "raw": line, "listType": "BREAKOUT"}
        for part in parts[1:]:
            if part.startswith("Type"):
                vals = part.split()
                d["listType"] = vals[-1] if vals else "BREAKOUT"
            if "Setup" in part:
                d["setup"] = part.split()[-1]
            elif "Window" in part:
                d["window"] = part.split()[-1]
            elif "Height" in part:
                d["height%"] = part.split()[-1]
            elif "Depth" in part:
                d["depth%"] = part.split()[-1]
            elif "Len" in part:
                d["len"] = part.split()[-1]
            elif "Ctr" in part:
                d["ctr"] = part.split()[-1]
            elif "Dist" in part:
                d["dist%"] = part.split()[-1]
            elif "Rating" in part:
                d["rating"] = part.split()[-1]
            if   "Close"  in part: d["close"]  = part.split()[-1]
            elif "Pivot"  in part: d["pivot"]  = part.split()[-1]
            elif "Entry"  in part: d["entry"]  = part.split()[-1]
            elif "Score"  in part: d["score"]  = part.split()[-1]
            elif "Range"  in part: d["range%"] = part.split()[-1]
            elif "Vol"    in part: d["vol%"]   = part.split()[-1]
            elif "RExp"   in part: d["rexp"]   = part.split()[-1]
            elif "Shares" in part: d["shares"] = part.split()[-1]
            elif "SL"     in part: d["sl"]     = part.split()[-1]
            elif "T1"     in part:
                vals = part.split()
                d["T1"] = vals[1] if len(vals) > 1 else ""
                d["T2"] = vals[3] if len(vals) > 3 else ""
                d["T3"] = vals[5] if len(vals) > 5 else ""
        return d
    except Exception:
        return {"symbol": line, "raw": line}


CSV_FIELDS = [
    "symbol", "listType", "setup", "setupSubtype", "window", "height%", "depth%", "len", "ctr", "dist%", "rating", "close", "pivot", "entry", "score",
    "watchlistRank", "watchlistQualityScore", "pivotProximityScore", "daysNearPivot", "pivotFreshness", "pivotFreshnessScore",
    "range%", "vol%", "rexp", "shares", "sl", "T1", "T2", "T3", "avgVol20", "avgDollarVol20", "rs3m", "rs6m", "rs12m", "rsScore", "rsRankScore",
    "regimeState", "regimeScore", "regimeSupport", "regimeSupportScore", "weeklyAgreement", "weeklyAgreementScore", "volumeDryUpScore", "volumeDryUpRatio",
    "rankingScore", "riskR", "heatAfterR",
    # Mean reversion specific
    "mrSubtype", "mrRsi", "mrSma20", "mrSma50", "mrSma200", "mrAtr", "mrLowerBB", "mrUpperBB", "mrBbPct", "mrVolRatio", "mrPullbackVolRatio",
    # Breakout pullback (ABFP) specific
    "abfpPeakHigh", "abfpPullbackDepth%", "abfpRunFromBO%", "abfpBarsSincePeak", "abfpPullbackVolRatio", "abfpBreakoutDate",
]



REJECTION_FIELDS = ["symbol", "reason", "source", "detail"]


def setup_run_logger(log_path: Path) -> logging.Logger:
    logger_name = f"scan.{log_path.stem}.{int(time.time())}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(file_handler)
    return logger


def append_event(path: Path, event: str, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": event,
        "payload": payload,
    }
    with open(path, "a") as fh:
        fh.write(json.dumps(record) + "\n")


def validate_rows(rows: list[dict], list_type: str) -> tuple[list[dict], list[dict]]:
    valid: list[dict] = []
    issues: list[dict] = []
    required_numeric = ["close", "pivot", "entry", "score", "shares", "sl", "T1", "T2", "T3"]
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            issues.append({"symbol": "", "reason": "INVALID_SYMBOL", "source": list_type, "detail": "missing symbol"})
            continue
        bad_field = None
        for field in required_numeric:
            val = row.get(field)
            if val in (None, ""):
                continue
            try:
                _ = float(str(val).replace("%", "").replace(",", ""))
            except Exception:
                bad_field = field
                break
        if bad_field:
            issues.append({"symbol": symbol, "reason": "INVALID_NUMERIC", "source": list_type, "detail": bad_field})
            continue

        entry = _to_float(row.get("entry"), 0.0)
        stop = _to_float(row.get("sl"), 0.0)
        shares = _to_float(row.get("shares"), 0.0)
        if entry <= 0 or stop <= 0 or shares <= 0:
            issues.append({"symbol": symbol, "reason": "INVALID_TRADE_PLAN", "source": list_type, "detail": "entry/stop/shares"})
            continue
        if entry <= stop:
            issues.append({"symbol": symbol, "reason": "INVALID_RISK", "source": list_type, "detail": "entry<=stop"})
            continue
        valid.append(row)
    return valid, issues


def save_manifest(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def save_bundle(path: Path, meta: dict, files: dict[str, str], counts: dict[str, int], validation: dict):
    save_manifest(path, {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "meta": meta,
        "counts": counts,
        "validation": validation,
        "files": files,
    })


def as_open_trade_rows(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        item = dict(row)
        item["listType"] = "OPEN_TRADE"
        # Add post-breakout tracking fields
        try:
            entry = float(item.get("entry", 0))
            close = float(item.get("close", 0))
            breakout_date = item.get("breakoutDate") or item.get("date")
            # Distance from breakout (current price vs breakout price)
            item["distance_from_breakout"] = close - entry
            # % gain/loss since breakout
            item["pct_gain_since_breakout"] = ((close - entry) / entry * 100) if entry else 0
            # Days since breakout (if date fields available)
            from datetime import datetime
            if breakout_date:
                try:
                    d0 = datetime.strptime(str(breakout_date), "%Y-%m-%d")
                    d1 = datetime.now()
                    item["days_since_breakout"] = (d1 - d0).days
                except Exception:
                    item["days_since_breakout"] = "?"
            else:
                item["days_since_breakout"] = "?"
            # Placeholder for max/min after breakout (to be filled by further logic if available)
            item["max_after_breakout"] = item.get("max_after_breakout", "")
            item["min_after_breakout"] = item.get("min_after_breakout", "")
        except Exception:
            item["distance_from_breakout"] = "?"
            item["pct_gain_since_breakout"] = "?"
            item["days_since_breakout"] = "?"
            item["max_after_breakout"] = "?"
            item["min_after_breakout"] = "?"
        out.append(item)
    return out
def save_breakout_performance(rows: list[dict], path: Path):
    """Save post-breakout performance tracking to a segregated CSV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Define fields for the performance report
    fields = [
        "symbol", "breakoutDate", "entry", "close", "distance_from_breakout", "pct_gain_since_breakout", "days_since_breakout", "max_after_breakout", "min_after_breakout", "setup", "rating", "window", "listType",
        # enrichment
        "avgVol20", "lastVol", "avgDollarVol20", "lastDollarVol", "daysAbovePivot", "distFromPivot%"
    ]
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def gather_past_breakouts(seed_path: Path, days: int = 30) -> list[dict]:
    """Search for breakout_performance_*.csv files near seed_path and in default output folder,
    return rows whose breakoutDate is within the past `days` days.
    """
    candidates: list[Path] = []
    seen = set()
    # Search the seed directory and its parents up to project root
    p = seed_path
    for _ in range(6):
        if not p:
            break
        try:
            for f in p.glob('breakout_performance_*.csv'):
                if f.exists() and str(f) not in seen:
                    candidates.append(f)
                    seen.add(str(f))
        except Exception:
            pass
        if p.parent == p:
            break
        p = p.parent

    # Also look in the project's default output directory (covers LATEST files)
    try:
        out_root = ROOT / 'output'
        for f in out_root.rglob('breakout_performance_*.csv'):
            if f.exists() and str(f) not in seen:
                candidates.append(f)
                seen.add(str(f))
    except Exception:
        pass

    recent: list[dict] = []
    cutoff = datetime.now().date() - timedelta(days=days)
    for csv_path in candidates:
        try:
            with open(csv_path, newline='') as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    bd = row.get('breakoutDate') or row.get('date')
                    if not bd:
                        continue
                    try:
                        # Accept YYYY-MM-DD or ISO formats
                        d = datetime.fromisoformat(str(bd)).date()
                    except Exception:
                        try:
                            d = datetime.strptime(str(bd), '%Y-%m-%d').date()
                        except Exception:
                            continue
                    if d >= cutoff:
                        # Normalise numeric fields
                        for k in ('pct_gain_since_breakout', 'distance_from_breakout'):
                            try:
                                row[k] = float(str(row.get(k, '')).replace('%', ''))
                            except Exception:
                                pass
                        row['_source_file'] = str(csv_path.name)
                        recent.append(row)
        except Exception:
            continue
    # Deduplicate by symbol+breakoutDate keeping latest seen
    dedup = {}
    for r in recent:
        key = (r.get('symbol'), r.get('breakoutDate'))
        dedup[key] = r
    return list(dedup.values())


def save_csv(rows: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def save_json(rows: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(rows, fh, indent=2)


def save_rejections(rows: list[dict], csv_path: Path, json_path: Path):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REJECTION_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    save_json(rows, json_path)


def summarize_variations(rows: list[dict]) -> dict[str, dict[str, int]]:
    setup_counts: dict[str, int] = {}
    window_counts: dict[str, int] = {}
    rating_counts: dict[str, int] = {}
    for row in rows:
        setup = str(row.get("setup", "UNKNOWN")).upper()
        window = str(row.get("window", "UNKNOWN")).upper()
        rating = str(row.get("rating", "N/A")).upper()
        setup_counts[setup] = setup_counts.get(setup, 0) + 1
        window_counts[window] = window_counts.get(window, 0) + 1
        rating_counts[rating] = rating_counts.get(rating, 0) + 1
    return {
        "setup": dict(sorted(setup_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "window": dict(sorted(window_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "rating": dict(sorted(rating_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


def _fmt_top(counts: dict[str, int], top_n: int = 3) -> str:
    if not counts:
        return "-"
    return ", ".join(f"{k}:{v}" for k, v in list(counts.items())[:top_n])


def save_variation_summary(rows: list[dict], path: Path, meta: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    breakdown = summarize_variations(rows)
    lines = [
        "# Scan Variation Progress",
        "",
        f"- Generated: {meta.get('finished', datetime.now().isoformat(timespec='seconds'))}",
        f"- Symbols scanned: {meta.get('total_scanned', '?')}",
        f"- Elapsed: {meta.get('elapsed', '?')}",
        f"- Hits: {len(rows)}",
        "",
        "## Setup Counts",
    ]
    for key, value in breakdown["setup"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Window Counts"])
    for key, value in breakdown["window"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Rating Counts"])
    for key, value in breakdown["rating"].items():
        lines.append(f"- {key}: {value}")

    path.write_text("\n".join(lines) + "\n")


def save_html(rows: list[dict], path: Path, meta: dict):
    """Generate interactive HTML report with fundamentals, sorting, filtering, and analytics."""
    path.parent.mkdir(parents=True, exist_ok=True)
    now_str = meta.get("finished", datetime.now().isoformat(timespec="seconds"))
    total   = meta.get("total_scanned", "?")
    elapsed = meta.get("elapsed", "?")

    def chart_links(symbol: str) -> tuple[str, str]:
        sym = (symbol or "").strip().upper()
        yahoo_sym = quote(sym)
        yahoo_price = f"https://finance.yahoo.com/quote/{yahoo_sym}/chart"
        yahoo_fund = f"https://finance.yahoo.com/quote/{yahoo_sym}/key-statistics"
        yahoo_financials = f"https://finance.yahoo.com/quote/{yahoo_sym}/financials"
        yahoo_balance = f"https://finance.yahoo.com/quote/{yahoo_sym}/balance-sheet"
        yahoo_cashflow = f"https://finance.yahoo.com/quote/{yahoo_sym}/cash-flow"

        tv_symbol = sym
        if sym.endswith(".NS"):
            tv_symbol = f"NSE:{sym[:-3]}"
        elif sym.endswith(".BO"):
            tv_symbol = f"BSE:{sym[:-3]}"
        tv_price = f"https://www.tradingview.com/chart/?symbol={quote(tv_symbol)}"

        price_link = (
            f"<a class='link-btn' href='{html.escape(yahoo_price)}' target='_blank' rel='noopener noreferrer'>Yahoo</a>"
            f"<a class='link-btn alt' href='{html.escape(tv_price)}' target='_blank' rel='noopener noreferrer'>TradingView</a>"
        )
        fund_link = (
            f"<a class='link-btn' href='{html.escape(yahoo_fund)}' target='_blank' rel='noopener noreferrer'>Stats</a>"
            f"<a class='link-btn' href='{html.escape(yahoo_financials)}' target='_blank' rel='noopener noreferrer'>Financials</a>"
            f"<a class='link-btn' href='{html.escape(yahoo_balance)}' target='_blank' rel='noopener noreferrer'>Balance Sheet</a>"
            f"<a class='link-btn' href='{html.escape(yahoo_cashflow)}' target='_blank' rel='noopener noreferrer'>Cash Flow</a>"
        )
        return price_link, fund_link

    def rating_badge(rating_raw: str) -> str:
        rating = (rating_raw or "").strip().upper()
        css = "rating-na"
        if rating == "A+":
            css = "rating-a-plus"
        elif rating == "A":
            css = "rating-a"
        elif rating == "B":
            css = "rating-b"
        elif rating == "C":
            css = "rating-c"
        elif rating == "D":
            css = "rating-d"
        label = html.escape(rating if rating else "N/A")
        return f"<span class='rating-badge {css}'>{label}</span>"

    # Calculate analytics
    setup_counts = {}
    rating_counts = {}
    scores = []
    risk_rewards = []

    for r in rows:
        setup = (r.get("setup") or "UNKNOWN").upper()
        setup_counts[setup] = setup_counts.get(setup, 0) + 1

        rating = (r.get("rating") or "N/A").upper()
        rating_counts[rating] = rating_counts.get(rating, 0) + 1

        try:
            score = float(r.get("score", 0))
            scores.append(score)

            entry = float(r.get("entry", 0))
            stop = float(r.get("sl", 0))
            target1 = float(r.get("T1", 0))
            if entry > 0 and stop > 0 and target1 > 0:
                risk = entry - stop
                reward = target1 - entry
                if risk > 0:
                    rr = reward / risk
                    risk_rewards.append(rr)
        except (ValueError, TypeError):
            pass

    avg_score = sum(scores) / len(scores) if scores else 0
    avg_rr = sum(risk_rewards) / len(risk_rewards) if risk_rewards else 0
    setup_summary = " | ".join(f"{k}: {v}" for k, v in sorted(setup_counts.items())) or "No hits"

    list_type_counts: dict[str, int] = {}
    dist_values = []
    for r in rows:
        lt = str(r.get("listType", "BREAKOUT")).upper()
        list_type_counts[lt] = list_type_counts.get(lt, 0) + 1
        try:
            dist = float(r.get("dist%", 0))
            dist_values.append(dist)
        except (ValueError, TypeError):
            pass

    top_score = max(scores) if scores else 0
    avg_dist = sum(dist_values) / len(dist_values) if dist_values else 0
    dominant_list_type = max(list_type_counts, key=list_type_counts.get) if list_type_counts else "BREAKOUT"
    page_title = (
        "📌 Watchlist Opportunities"
        if dominant_list_type == "WATCHLIST"
        else ("💼 Open Trades Monitor" if dominant_list_type == "OPEN_TRADE" else "🚀 Breakout Opportunities")
    )

    def build_scan_reason(r: dict) -> str:
        """Generate a hover tooltip describing why this setup was flagged as a breakout."""
        setup = (r.get("setup") or r.get("setupType") or "?").upper()
        subtype = r.get("mrSubtype") or r.get("setupSubtype") or "-"
        rating = r.get("rating") or "?"
        window = r.get("window") or "?"
        height = r.get("height%") or "?"
        depth  = r.get("depth%") or "?"
        score  = r.get("score") or "?"
        ctr    = r.get("ctr") or "?"
        rexp   = r.get("rexp") or "?"
        pivot  = r.get("pivot") or "?"
        entry  = r.get("entry") or "?"
        sl     = r.get("sl") or r.get("stop") or "?"
        t1     = r.get("T1") or "?"
        t2     = r.get("T2") or "?"
        t3     = r.get("T3") or "?"
        dist   = r.get("dist%") or "?"
        vol    = r.get("vol%") or "?"
        watch_rank = r.get("watchlistRank") or "-"
        rank_score = r.get("watchlistQualityScore") or r.get("rankingScore") or "-"
        pivot_prox = r.get("pivotProximityScore") or "-"
        days_near_pivot = r.get("daysNearPivot") or "-"
        pivot_freshness = r.get("pivotFreshness") or "-"
        weekly_agreement = r.get("weeklyAgreement") or "-"
        regime_support = r.get("regimeSupport") or "-"
        rs_score = r.get("rsScore") or "-"
        vol_dry_up = r.get("volumeDryUpScore") or "-"
        mr_rsi = r.get("mrRsi") or "-"
        mr_vol_ratio = r.get("mrVolRatio") or "-"
        mr_pullback_vol_ratio = r.get("mrPullbackVolRatio") or "-"

        if setup == "VCP":
            setup_desc = "VCP — Volatility Contraction Pattern with tightening range waves into pivot"
            lines = [
                f"Setup: {setup_desc}",
                f"Rating: {rating}  |  Window: {window}  |  Quality Score: {score}",
                f"Base Height: {height}%  |  Contraction Depth: {depth}%  |  Contraction Pairs: {ctr}",
                f"Range Expansion: {rexp}x  |  Volume vs Avg: {vol}%",
                f"Pivot: {pivot}  |  Entry: {entry}  |  Stop Loss: {sl}",
                f"Targets → T1(1R): {t1}  |  T2(2R): {t2}  |  T3(3R): {t3}",
                f"Distance to Pivot: {dist}%",
            ]
        elif setup == "MEAN_REVERSION":
            setup_desc = "Mean Reversion — pullback into the mean within a broader uptrend, looking for bullish snap-back"
            lines = [
                f"Setup: {setup_desc}",
                f"Subtype: {subtype}  |  Rating: {rating}  |  Window: {window}  |  Quality Score: {score}",
                f"Pullback Depth: {height}%  |  Band Width: {depth}%  |  RSI: {mr_rsi}",
                f"Mean (Pivot): {pivot}  |  Entry: {entry}  |  Stop Loss: {sl}",
                f"Targets → T1(mean): {t1}  |  T2: {t2}  |  T3: {t3}",
                f"Distance to Mean: {dist}%  |  Signal Volume vs Avg: {mr_vol_ratio}x  |  Pullback Volume vs Avg: {mr_pullback_vol_ratio}x",
            ]
        elif setup == "BREAKOUT_PULLBACK":
            abfp_peak        = r.get("abfpPeakHigh") or "-"
            abfp_pb_depth    = r.get("abfpPullbackDepth%") or height or "-"
            abfp_run         = r.get("abfpRunFromBO%") or depth or "-"
            abfp_bars_peak   = r.get("abfpBarsSincePeak") or r.get("len") or "-"
            abfp_pb_vol      = r.get("abfpPullbackVolRatio") or mr_pullback_vol_ratio or "-"
            abfp_bo_date     = r.get("abfpBreakoutDate") or r.get("breakoutDate") or "-"
            setup_desc = "First Pullback After Breakout — stock cleared prior resistance on volume, ran higher, now in controlled first pullback back to the breakout support zone"
            lines = [
                f"Setup: {setup_desc}",
                f"Rating: {rating}  |  Window: {window}  |  Quality Score: {score}",
                f"Breakout Date: {abfp_bo_date}  |  Breakout Level (Pivot/Support): {pivot}",
                f"Post-Breakout Peak: {abfp_peak}  |  Run from BO to Peak: {abfp_run}%",
                f"Current Pullback Depth (from Peak): {abfp_pb_depth}%  |  Bars Since Peak: {abfp_bars_peak}",
                f"Pullback Volume vs Avg: {abfp_pb_vol}x  (dry-up = healthy consolidation)",
                f"Entry: {entry}  |  Stop Loss (below BO support): {sl}",
                f"Targets → T1(prior peak): {t1}  |  T2: {t2}  |  T3: {t3}",
                f"Distance Above BO Support: {dist}%",
            ]
        else:
            setup_desc = "Range Expansion Breakout — narrow base with wide-range breakout candle above pivot"
            lines = [
                f"Setup: {setup_desc}",
                f"Rating: {rating}  |  Window: {window}  |  Quality Score: {score}",
                f"Base Height: {height}%  |  Contraction Depth: {depth}%  |  Contraction Pairs: {ctr}",
                f"Range Expansion: {rexp}x  |  Volume vs Avg: {vol}%",
                f"Pivot: {pivot}  |  Entry: {entry}  |  Stop Loss: {sl}",
                f"Targets → T1(1R): {t1}  |  T2(2R): {t2}  |  T3(3R): {t3}",
                f"Distance to Pivot: {dist}%",
            ]

        lines.extend([
            f"Watchlist Rank: {watch_rank}  |  Rank Score: {rank_score}",
            f"Pivot Proximity Score: {pivot_prox}  |  Days Near Pivot: {days_near_pivot}  |  Pivot Freshness: {pivot_freshness}",
            f"RS Score: {rs_score}  |  Regime Support: {regime_support}  |  Weekly Agreement: {weekly_agreement}",
            f"Volume Dry-Up Score: {vol_dry_up}",
        ])
        return " &#10; ".join(lines)

    # Build table rows with data attributes
    rows_html = ""
    for r in rows:
        symbol = html.escape(r.get("symbol", ""))
        setup_type = (r.get("setup", "")).upper()
        rating_val = str(r.get("rating", "")).upper()
        score_val = float(r.get("watchlistQualityScore") or r.get("rankingScore") or r.get("score", 0))

        price_link, fund_link = chart_links(r.get("symbol", ""))
        rating_chip = rating_badge(rating_val)
        reason_tooltip = build_scan_reason(r)
        list_type_raw = str(r.get('listType', 'BREAKOUT')).upper()
        list_type_css = f"list-badge list-{list_type_raw.lower()}"
        list_type_chip = f"<span class='{list_type_css}'>{html.escape(list_type_raw)}</span>"
        score_chip = f"<span class='score-chip'>{html.escape(str(r.get('score','')))}</span>"

        # Fallback computations for display when source fields are missing
        def _safe_float(key, default=None):
            try:
                v = r.get(key)
                if v is None or v == "":
                    return default
                return float(str(v).replace('%','').replace(',',''))
            except Exception:
                return default

        close_val = _safe_float('close')
        pivot_val = _safe_float('pivot')
        entry_val = _safe_float('entry')
        dist_pct = r.get('dist%') or r.get('distFromPivot%') or r.get('distFromPivot')
        # compute dist% if missing and pivot available
        if (dist_pct is None or dist_pct == '') and pivot_val and close_val:
            try:
                dist_pct = (close_val - pivot_val) / pivot_val * 100.0
                dist_pct = f"{dist_pct:.2f}%"
            except Exception:
                dist_pct = ''
        # breakout metrics
        pct_gain = r.get('pct_gain_since_breakout')
        days_since_breakout = r.get('days_since_breakout')
        if (not pct_gain or pct_gain == '') and entry_val and close_val:
            try:
                pct_gain = (close_val - entry_val) / entry_val * 100.0
                pct_gain = f"{pct_gain:.2f}%"
            except Exception:
                pct_gain = ''
        if (not days_since_breakout or days_since_breakout == ''):
            bd = r.get('breakoutDate') or r.get('date')
            if bd:
                try:
                    d0 = datetime.fromisoformat(str(bd)).date()
                    days_since_breakout = (datetime.now().date() - d0).days
                except Exception:
                    days_since_breakout = ''

        max_after = r.get('max_after_breakout') or r.get('maxAfterBreakout') or ''
        min_after = r.get('min_after_breakout') or r.get('minAfterBreakout') or ''
        avgVol20 = r.get('avgVol20') or r.get('avgVol') or ''
        lastVol = r.get('lastVol') or r.get('lastVolume') or ''

        # Normalize display strings
        def _disp(x):
            if x is None or x == "":
                return "-"
            return html.escape(str(x))

        rows_html += (
            f"<tr data-symbol='{html.escape(r.get('symbol', ''))}' "
            f"data-setup-type='{setup_type}' "
            f"data-rating='{rating_val}' "
            f"data-list-type='{list_type_raw}' "
            f"data-score='{score_val}'>"
            f"<td><b>{symbol}</b></td>"
            f"<td>{list_type_chip}</td>"
            f"<td>{html.escape(setup_type)}</td>"
            f"<td>{html.escape(str(r.get('window','')))}</td>"
            f"<td>{_disp(r.get('height%'))}</td>"
            f"<td>{_disp(r.get('depth%'))}</td>"
            f"<td>{_disp(r.get('len'))}</td>"
            f"<td>{_disp(r.get('ctr'))}</td>"
            f"<td>{_disp(dist_pct)}</td>"
            f"<td>{rating_chip}</td>"
            f"<td>{_disp(close_val)}</td>"
            f"<td>{_disp(pivot_val)}</td>"
            f"<td>{_disp(entry_val)}</td>"
            f"<td>{score_chip}</td>"
            f"<td>{_disp(r.get('watchlistQualityScore', r.get('rankingScore', '')))}</td>"
            f"<td>{_disp(r.get('pivotProximityScore'))}</td>"
            f"<td>{_disp(r.get('rsScore'))}</td>"
            f"<td>{_disp(r.get('regimeSupport'))}</td>"
            f"<td>{_disp(r.get('weeklyAgreement'))}</td>"
            f"<td>{_disp(r.get('volumeDryUpScore'))}</td>"
            f"<td>{_disp(r.get('daysNearPivot'))}</td>"
            f"<td>{_disp(r.get('pivotFreshness'))}</td>"
            f"<td>{_disp(r.get('range%'))}</td>"
            f"<td>{_disp(r.get('vol%'))}</td>"
            f"<td>{_disp(r.get('rexp'))}</td>"
            f"<td>{_disp(r.get('shares'))}</td>"
            f"<td>{_disp(r.get('sl'))}</td>"
            f"<td>{_disp(r.get('T1'))}</td>"
            f"<td>{_disp(r.get('T2'))}</td>"
            f"<td>{_disp(r.get('T3'))}</td>"
            f"<td class='links'>{price_link}</td>"
            f"<td class='links'>{fund_link}</td>"
            f"<td style='font-size:0.78em;white-space:nowrap;color:#555'>{html.escape(str(r.get('fundSummary') or '—'))}</td>"
            f"<td style='text-align:center'><span class='reason-icon' title='{reason_tooltip}' "
            f"style='cursor:help;font-size:1.1em'>💡</span></td>"
            f"</tr>\n"
        )

    # Build rating distribution HTML
    rating_bars = ""
    for rating in ["A+", "A", "B", "C", "D"]:
        count = rating_counts.get(rating, 0)
        pct = (count / len(rows) * 100) if rows else 0
        rating_bars += f"<div class='bar-item'><span class='bar-label'>{rating}</span><div class='bar'><div class='bar-fill' style='width:{pct}%'></div></div><span class='bar-count'>{count}</span></div>\n"

    setup_pie = ""
    for setup in sorted(setup_counts.keys()):
        count = setup_counts[setup]
        setup_pie += f"<div class='pie-item'><span class='pie-label'>{setup}</span><span class='pie-count'>{count}</span></div>\n"

    # If this report is an Open Trades monitor, accumulate recent breakouts from past performance files
    past_breakouts_html = ""
    try:
        is_open_trades = any(str(r.get('listType','')).upper() == 'OPEN_TRADE' for r in rows)
        if is_open_trades:
            recent = gather_past_breakouts(path, days=30)
            if recent:
                # limit to 20 entries sorted by pct gain desc
                recent_sorted = sorted(recent, key=lambda r: _to_float(r.get('pct_gain_since_breakout'), 0.0), reverse=True)[:20]
                past_rows = []

                def _fmt(val, digits=2, suffix=''):
                    if val is None or val == '':
                        return '-'
                    try:
                        f = float(val)
                        if abs(f) >= 100 or f == int(f):
                            s = f"{int(f)}"
                        else:
                            s = f"{f:.{digits}f}"
                        return html.escape(s) + suffix
                    except Exception:
                        return html.escape(str(val))

                for r in recent_sorted:
                    sym = html.escape(str(r.get('symbol','')))
                    bd = html.escape(str(r.get('breakoutDate') or r.get('date','')))
                    pct = _fmt(r.get('pct_gain_since_breakout'), digits=2, suffix='%')
                    days_sb = _fmt(r.get('days_since_breakout'), digits=0)
                    entry = _fmt(r.get('entry'))
                    close = _fmt(r.get('close'))
                    setup = html.escape(str(r.get('setup','')))
                    rating = html.escape(str(r.get('rating','')))
                    src = html.escape(str(r.get('_source_file','')))
                    max_after = _fmt(r.get('max_after_breakout'))
                    min_after = _fmt(r.get('min_after_breakout'))
                    avgVol20 = _fmt(r.get('avgVol20'), digits=0)
                    lastVol = _fmt(r.get('lastVol'), digits=0)
                    dist_from_pivot = _fmt(r.get('distFromPivot%') or r.get('distFromPivot') or r.get('distFromPivotPercent'))

                    past_rows.append(
                        f"<tr>"
                        f"<td><b>{sym}</b></td>"
                        f"<td>{html.escape(setup)}</td>"
                        f"<td>{bd}</td>"
                        f"<td style='text-align:right'>{entry}</td>"
                        f"<td style='text-align:right'>{close}</td>"
                        f"<td style='text-align:right'>{pct}</td>"
                        f"<td style='text-align:right'>{days_sb}</td>"
                        f"<td style='text-align:right'>{max_after}</td>"
                        f"<td style='text-align:right'>{min_after}</td>"
                        f"<td style='text-align:right'>{avgVol20}</td>"
                        f"<td style='text-align:right'>{lastVol}</td>"
                        f"<td style='text-align:right'>{dist_from_pivot}</td>"
                        f"</tr>"
                    )

                past_breakouts_html = (
                    "<h2>Recent Breakouts (Past 30 days)</h2>"
                    "<div class='table-wrap' style='margin-bottom:12px'>"
                    "<table id='recentBreakouts' style='min-width:900px'>"
                    "<thead><tr><th>Symbol</th><th>Setup</th><th>Breakout Date</th><th>Entry</th><th>Close</th><th>% Gain</th><th>Days</th><th>Max</th><th>Min</th><th>avgVol20</th><th>lastVol</th><th>distFromPivot%</th></tr></thead>"
                    "<tbody>"
                    + "\n".join(past_rows)
                    + "\n</tbody></table></div>"
                )
    except Exception:
        past_breakouts_html = ""

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{page_title} — {now_str}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: radial-gradient(1200px 500px at 10% -5%, #1a2333 0%, #0d1117 45%, #0b1016 100%);
            color: #c9d1d9; margin: 24px; }}
    h1   {{ color: #9ecbff; margin-top: 0; letter-spacing: .2px; }}
    h2   {{ color: #79c0ff; font-size: 1.1em; margin-top: 24px; margin-bottom: 12px; }}
    .meta{{ color: #8b949e; font-size: 0.9em; margin-bottom: 12px; }}
    .summary {{ color: #9ecbff; margin: 8px 0 16px 0; font-size: 0.92em; }}

    .hero {{
      background: linear-gradient(135deg, #111827 0%, #1b263b 100%);
      border: 1px solid #273244;
      border-radius: 14px;
      padding: 16px 18px;
      margin-bottom: 16px;
      box-shadow: 0 8px 24px rgba(0,0,0,.25);
    }}
    .hero-top {{ display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; }}
    .pill-wrap {{ display:flex; gap:8px; flex-wrap:wrap; }}
    .pill {{ border:1px solid #30363d; color:#9ecbff; background:#0f1622; border-radius:999px; padding:4px 10px; font-size:.78em; }}

    /* Controls */
    .controls {{
      display: flex; gap: 16px; align-items: center; margin-bottom: 20px;
      flex-wrap: wrap; padding: 12px; background: rgba(22,27,34,.92); border-radius: 10px;
      border: 1px solid #273244; position: sticky; top: 10px; z-index: 20; backdrop-filter: blur(4px);
    }}
    .control-group {{ display: flex; gap: 8px; align-items: center; }}
    .control-label {{ color: #8b949e; font-size: 0.9em; font-weight: 600; }}
    .search-box {{
      flex: 0 0 200px; padding: 6px 10px; background: #0d1117; border: 1px solid #30363d;
      border-radius: 6px; color: #c9d1d9; font-size: 0.9em;
    }}
    .score-slider {{ flex: 0 0 200px; }}
    .slider {{ width: 100%; height: 4px; border-radius: 3px; background: #30363d;
               outline: none; -webkit-appearance: none; cursor: pointer; }}
    .slider::-webkit-slider-thumb {{ -webkit-appearance: none; appearance: none;
      width: 14px; height: 14px; border-radius: 50%; background: #58a6ff; cursor: pointer; }}
    .slider::-moz-range-thumb {{ width: 14px; height: 14px; border-radius: 50%;
      background: #58a6ff; cursor: pointer; border: none; }}
    .slider-value {{ color: #79c0ff; font-size: 0.9em; min-width: 40px; text-align: center; }}
    .setup-filter {{ display: flex; gap: 8px; }}
    .filter-btn {{
      padding: 6px 12px; border: 1px solid #30363d; border-radius: 6px;
      background: transparent; color: #58a6ff; cursor: pointer; font-size: 0.85em;
      transition: all 0.2s;
    }}
    .filter-btn.active {{ background: #1f6feb; border-color: #58a6ff; }}
    .filter-btn:hover {{ background: #1f6feb33; }}
    .export-btn {{
      padding: 6px 12px; border: 1px solid #30363d; border-radius: 6px;
      background: transparent; color: #7ee787; cursor: pointer; font-size: 0.85em;
      transition: all 0.2s;
    }}
    .export-btn:hover {{ background: #2ea04333; }}
    .reset-btn {{
      padding: 6px 12px; border: 1px solid #30363d; border-radius: 6px;
      background: transparent; color: #f2cc60; cursor: pointer; font-size: 0.85em;
    }}
    .reset-btn:hover {{ background: #f2cc6022; }}
    .select {{
      padding: 6px 8px; background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px;
      font-size: 0.85em;
    }}

    /* Analytics */
    .analytics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                   gap: 16px; margin-bottom: 24px; }}
    .stat-card {{ background: linear-gradient(180deg, #161b22 0%, #121820 100%); padding: 12px; border-radius: 10px; border: 1px solid #273244; }}
    .stat-label {{ color: #8b949e; font-size: 0.85em; margin-bottom: 4px; }}
    .stat-value {{ color: #58a6ff; font-size: 1.4em; font-weight: 700; }}
    .stat-secondary {{ color: #79c0ff; font-size: 0.9em; margin-top: 4px; }}

    /* Charts */
    .chart-container {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                        gap: 16px; margin-bottom: 24px; }}
    .chart {{ background: #161b22; padding: 12px; border-radius: 8px; border: 1px solid #21262d; }}
    .chart-title {{ color: #79c0ff; font-size: 0.95em; font-weight: 600; margin-bottom: 12px; }}
    .bar-item {{ display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }}
    .bar-label {{ width: 40px; color: #8b949e; font-size: 0.85em; }}
    .bar {{ flex: 1; height: 20px; background: #0d1117; border-radius: 3px; position: relative; }}
    .bar-fill {{ height: 100%; background: #58a6ff; border-radius: 3px; }}
    .bar-count {{ width: 30px; text-align: right; font-size: 0.85em; color: #79c0ff; }}
    .pie-item {{ display: flex; justify-content: space-between; padding: 4px 0;
                font-size: 0.85em; border-bottom: 1px solid #21262d; }}
    .pie-label {{ color: #79c0ff; }}
    .pie-count {{ color: #7ee787; font-weight: 600; }}

    /* Table */
    .table-wrap {{ overflow-x: auto; border: 1px solid #273244; border-radius: 10px; box-shadow: 0 8px 18px rgba(0,0,0,.2); position: relative; -webkit-overflow-scrolling: touch; }}
    .table-wrap::before, .table-wrap::after {{
      content: ""; position: sticky; top: 0; width: 14px; height: 100%; display: block; pointer-events: none; z-index: 4;
    }}
    .table-wrap::before {{ left: 0; float: left; background: linear-gradient(to right, rgba(13,17,23,.95), rgba(13,17,23,0)); }}
    .table-wrap::after  {{ right: 0; float: right; background: linear-gradient(to left, rgba(13,17,23,.95), rgba(13,17,23,0)); }}
    table{{ border-collapse: collapse; width: 100%; font-size: 0.88em; min-width: 2250px; }}
    th   {{ background: #161b22; color: #9ecbff; padding: 9px 12px;
            position: sticky; top: 0; text-align: right; cursor: pointer; user-select: none;
            transition: background-color 0.2s, opacity 0.2s; }}
    th:first-child {{ text-align: left; }}
    th:hover {{ background: #1f6feb22; opacity: 0.9; }}
    th::after {{ content: ' ↕'; font-size: 0.7em; opacity: 0; }}
    th.sort-asc::after {{ content: ' ↑'; opacity: 1; }}
    th.sort-desc::after {{ content: ' ↓'; opacity: 1; }}
    td   {{ padding: 9px 12px; border-bottom: 1px solid #1f2937; text-align: right; }}
    td:first-child {{ text-align: left; font-weight: 600; color: #7ee787; }}
    tbody tr:nth-child(even) td {{ background: #0f1520; }}
    tr:hover td    {{ background: #182132 !important; }}
    tr.hidden {{ display: none; }}

    .links {{ text-align: left; white-space: nowrap; }}
    .link-btn {{
      display: inline-block; padding: 4px 8px; margin-right: 6px; border-radius: 6px;
      color: #58a6ff; border: 1px solid #30363d; text-decoration: none; font-size: 0.8em;
    }}
    .link-btn:hover {{ background: #1f6feb22; }}
    .link-btn.alt {{ color: #7ee787; }}
    .rating-badge {{
      display: inline-block; min-width: 34px; text-align: center;
      padding: 2px 8px; border-radius: 999px; font-weight: 700; font-size: 0.80em;
      border: 1px solid transparent;
    }}
    .rating-a-plus {{ color: #2ea043; background: #23863633; border-color: #2ea04399; }}
    .rating-a {{ color: #3fb950; background: #2ea0432b; border-color: #3fb95099; }}
    .rating-b {{ color: #d29922; background: #9e6a032d; border-color: #d2992299; }}
    .rating-c {{ color: #f0883e; background: #bc4c002d; border-color: #f0883e99; }}
    .rating-d {{ color: #f85149; background: #da36332d; border-color: #f8514999; }}
    .rating-na {{ color: #8b949e; background: #6e768133; border-color: #8b949e99; }}

    .row-count {{ color: #8b949e; font-size: 0.9em; margin-top: 8px; }}
    .reason-icon {{ cursor: help; font-size: 1.1em; }}
    .reason-icon:hover {{ opacity: .7; }}

    .list-badge {{ border:1px solid #344254; border-radius:999px; padding:2px 8px; font-size:.76em; color:#9ecbff; }}
    .list-watchlist {{ color:#f2cc60; border-color:#6b5b2a; background:#f2cc6018; }}
    .list-open_trade {{ color:#7ee787; border-color:#285b35; background:#7ee78718; }}
    .score-chip {{ border:1px solid #2f445a; border-radius:8px; padding:2px 7px; color:#a5d6ff; background:#0f1b2a; font-variant-numeric: tabular-nums; }}
    .empty-state {{ display:none; margin-top:12px; border:1px dashed #35506f; border-radius:10px; padding:12px; color:#9ecbff; background:#0f1a28; }}
    .mobile-note {{ display:none; margin-top:8px; color:#8fb9e7; font-size:.85em; }}

    /* Keep key identity columns visible while horizontally scrolling */
    #dataTable th:nth-child(1), #dataTable td:nth-child(1) {{
      position: sticky; left: 0; z-index: 3; background: #111926;
    }}
    #dataTable th:nth-child(2), #dataTable td:nth-child(2) {{
      position: sticky; left: 124px; z-index: 3; background: #111926;
    }}
    #dataTable thead th:nth-child(1), #dataTable thead th:nth-child(2) {{ z-index: 6; }}

    body.compact td {{ padding: 5px 10px; }}
    body.compact th {{ padding: 6px 10px; }}

    @media (max-width: 1100px) {{
      .mobile-note {{ display:block; }}
      .controls {{ gap: 10px; }}
      .control-group {{ flex-wrap: wrap; }}
      .search-box {{ flex: 1 1 180px; }}

      /* Hide advanced columns by default on tablet/mobile */
      #dataTable th:nth-child(5), #dataTable td:nth-child(5),
      #dataTable th:nth-child(6), #dataTable td:nth-child(6),
      #dataTable th:nth-child(7), #dataTable td:nth-child(7),
      #dataTable th:nth-child(8), #dataTable td:nth-child(8),
      #dataTable th:nth-child(15), #dataTable td:nth-child(15),
      #dataTable th:nth-child(16), #dataTable td:nth-child(16),
      #dataTable th:nth-child(17), #dataTable td:nth-child(17),
      #dataTable th:nth-child(18), #dataTable td:nth-child(18),
      #dataTable th:nth-child(19), #dataTable td:nth-child(19),
      #dataTable th:nth-child(20), #dataTable td:nth-child(20),
      #dataTable th:nth-child(21), #dataTable td:nth-child(21),
      #dataTable th:nth-child(22), #dataTable td:nth-child(22),
      #dataTable th:nth-child(23), #dataTable td:nth-child(23),
      #dataTable th:nth-child(24), #dataTable td:nth-child(24) {{ display: none; }}

      body.show-advanced #dataTable th:nth-child(5), body.show-advanced #dataTable td:nth-child(5),
      body.show-advanced #dataTable th:nth-child(6), body.show-advanced #dataTable td:nth-child(6),
      body.show-advanced #dataTable th:nth-child(7), body.show-advanced #dataTable td:nth-child(7),
      body.show-advanced #dataTable th:nth-child(8), body.show-advanced #dataTable td:nth-child(8),
      body.show-advanced #dataTable th:nth-child(15), body.show-advanced #dataTable td:nth-child(15),
      body.show-advanced #dataTable th:nth-child(16), body.show-advanced #dataTable td:nth-child(16),
      body.show-advanced #dataTable th:nth-child(17), body.show-advanced #dataTable td:nth-child(17),
      body.show-advanced #dataTable th:nth-child(18), body.show-advanced #dataTable td:nth-child(18),
      body.show-advanced #dataTable th:nth-child(19), body.show-advanced #dataTable td:nth-child(19),
      body.show-advanced #dataTable th:nth-child(20), body.show-advanced #dataTable td:nth-child(20),
      body.show-advanced #dataTable th:nth-child(21), body.show-advanced #dataTable td:nth-child(21),
      body.show-advanced #dataTable th:nth-child(22), body.show-advanced #dataTable td:nth-child(22),
      body.show-advanced #dataTable th:nth-child(23), body.show-advanced #dataTable td:nth-child(23),
      body.show-advanced #dataTable th:nth-child(24), body.show-advanced #dataTable td:nth-child(24) {{ display: table-cell; }}
    }}

    @media (max-width: 900px) {{
      body {{ margin: 12px; }}
      .controls {{ position: static; }}
      .chart-container {{ grid-template-columns: 1fr; }}
      .analytics {{ grid-template-columns: repeat(2, minmax(120px,1fr)); }}
      #dataTable th:nth-child(2), #dataTable td:nth-child(2) {{ left: 108px; }}
      .row-count {{ font-size: .82em; }}
      .link-btn {{ padding: 6px 8px; }}
    }}
  </style>
</head>
<body>
  <div class="hero">
    <div class="hero-top">
      <h1>{page_title}</h1>
      <div class="pill-wrap">
        <span class="pill">Finished: {now_str}</span>
        <span class="pill">Scanned: {total}</span>
        <span class="pill">Elapsed: {elapsed}</span>
        <span class="pill"><b style="color:#7ee787">Hits: {len(rows)}</b></span>
      </div>
    </div>
  </div>
  <div class="meta">
    Report mode is inferred from row list type and optimized for fast shortlist decisions.
  </div>
  <div class="summary">Shortlist by setup: {html.escape(setup_summary)}</div>
  <div class="summary" style="margin-top:6px">
    Columns: <b>Base Height %</b> (consolidation range height), <b>Contraction Depth %</b> (VCP squeeze depth),
    <b>Base Length</b> (bars), <b>Contraction Pairs</b> (effective range+volume contraction count),
    <b>Range Expansion x</b> (breakout candle expansion factor),
    <b>💡 Trade Reasoning</b> (hover to see full setup logic, entry, stop, and targets).
  </div>
  {past_breakouts_html}

  <!-- Controls -->
  <div class="controls">
    <div class="control-group">
      <label class="control-label">Search:</label>
      <input type="text" class="search-box" id="searchInput" placeholder="Symbol or setup..." autocomplete="off">
    </div>
    <div class="control-group">
      <label class="control-label">Min Score:</label>
      <input type="range" class="slider" id="scoreSlider" min="0" max="100" value="0">
      <span class="slider-value" id="scoreDisplay">0+</span>
    </div>
    <div class="control-group setup-filter">
      <label class="control-label">Setup:</label>
      <button class="filter-btn active" data-setup="all">All</button>
      <button class="filter-btn" data-setup="VCP">VCP</button>
      <button class="filter-btn" data-setup="RANGE_EXPANSION">Range Exp</button>
      <button class="filter-btn" data-setup="MEAN_REVERSION">Mean Rev</button>
    </div>
    <div class="control-group">
      <label class="control-label">List:</label>
      <select id="listTypeFilter" class="select">
        <option value="all">All</option>
        <option value="BREAKOUT">Breakout</option>
        <option value="WATCHLIST">Watchlist</option>
        <option value="OPEN_TRADE">Open Trade</option>
      </select>
    </div>
    <div class="control-group">
      <label class="control-label">Rating:</label>
      <select id="ratingFilter" class="select">
        <option value="all">All</option>
        <option value="A+">A+</option>
        <option value="A">A</option>
        <option value="B">B</option>
        <option value="C">C</option>
        <option value="D">D</option>
      </select>
    </div>
    <button class="export-btn" id="exportBtn">📥 Export Filtered</button>
    <button class="reset-btn" id="resetFiltersBtn">↺ Reset Filters</button>
    <button class="reset-btn" id="compactToggleBtn" title="Toggle compact row density">▦ Compact</button>
    <button class="reset-btn" id="advancedColsToggleBtn" title="Show/hide advanced columns on small screens">☰ Columns</button>
  </div>

  <!-- Analytics -->
  <div class="analytics">
    <div class="stat-card">
      <div class="stat-label">Total Hits</div>
      <div class="stat-value">{len(rows)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Avg Quality Score</div>
      <div class="stat-value">{avg_score:.1f}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Avg Risk/Reward</div>
      <div class="stat-value">{avg_rr:.2f}:1</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Top Quality Score</div>
      <div class="stat-value">{top_score:.1f}</div>
      <div class="stat-secondary">Best candidate in current run</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Avg Pivot Distance</div>
      <div class="stat-value">{avg_dist:.2f}%</div>
      <div class="stat-secondary">Lower is cleaner for entries</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Dominant List Type</div>
      <div class="stat-value">{dominant_list_type}</div>
    </div>
  </div>

  <div class="chart-container">
    <div class="chart">
      <div class="chart-title">📊 Rating Distribution</div>
{rating_bars}    </div>
    <div class="chart">
      <div class="chart-title">🎯 Setup Distribution</div>
{setup_pie}    </div>
  </div>

  <!-- Table -->
  <div class="table-wrap">
  <table id="dataTable">
    <thead>
      <tr>
        <th>Symbol</th><th>List Type</th><th>Setup</th><th>Window</th><th>Base Height %</th><th>Contraction Depth %</th><th>Base Length</th><th>Contraction Pairs</th><th>Pivot Distance %</th><th>Rating</th><th>Last Close</th><th>Pivot Price</th><th>Planned Entry</th><th>Pct since Breakout</th><th>Days since Breakout</th><th>Max After</th><th>Min After</th><th>avgVol20</th><th>lastVol</th><th>Quality Score</th>
        <th>Rank Score</th><th>Pivot Proximity</th><th>RS Score</th><th>Regime Support</th><th>Weekly Agreement</th><th>Volume Dry-Up</th><th>Days Near Pivot</th><th>Pivot Freshness</th><th>Range Contraction %</th><th>Volume Contraction %</th><th>Range Expansion x</th><th>Position Size</th><th>Stop Loss</th>
        <th>Target 1 (1R)</th><th>Target 2 (2R)</th><th>Target 3 (3R)</th><th>Price Charts</th><th>Fundamental Charts</th><th>Trade Reasoning</th>
      </tr>
    </thead>
    <tbody id="tableBody">
{rows_html}    </tbody>
  </table>
  </div>
  <div class="row-count">Showing <span id="visibleCount">{len(rows)}</span> of <span id="totalCount">{len(rows)}</span> rows</div>
  <div class="mobile-note" id="mobileHint">Tip: swipe table horizontally. Use <b>☰ Columns</b> to show advanced fields on tablet/mobile.</div>

  <div id="emptyState" class="empty-state">No rows match current filters. Try lowering Min Score or resetting filters.</div>


  <script>
    // Data for filtering and sorting
    const originalRows = Array.from(document.querySelectorAll('#tableBody tr'));
    let currentSort = {{ column: null, direction: 'asc' }};
    let currentFilters = {{ search: '', score: 0, setup: 'all', rating: 'all', listType: 'all' }};

    // Search functionality
    document.getElementById('searchInput').addEventListener('input', (e) => {{
      currentFilters.search = e.target.value.toLowerCase();
      applyFilters();
    }});

    // Score slider with real-time display
    const scoreSlider = document.getElementById('scoreSlider');
    const scoreDisplay = document.getElementById('scoreDisplay');
    scoreSlider.addEventListener('input', (e) => {{
      const val = parseInt(e.target.value);
      scoreDisplay.textContent = val + '+';
      currentFilters.score = val;
      applyFilters();
    }});

    // Setup filter buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentFilters.setup = btn.dataset.setup;
        applyFilters();
      }});
    }});

    // Rating filter
    document.getElementById('ratingFilter').addEventListener('change', (e) => {{
      currentFilters.rating = e.target.value;
      applyFilters();
    }});

    // List type filter
    document.getElementById('listTypeFilter').addEventListener('change', (e) => {{
      currentFilters.listType = e.target.value;
      applyFilters();
    }});

    // Reset filters
    document.getElementById('resetFiltersBtn').addEventListener('click', () => {{
      currentFilters = {{ search: '', score: 0, setup: 'all', rating: 'all', listType: 'all' }};
      document.getElementById('searchInput').value = '';
      scoreSlider.value = 0;
      scoreDisplay.textContent = '0+';
      document.getElementById('ratingFilter').value = 'all';
      document.getElementById('listTypeFilter').value = 'all';
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      document.querySelector('.filter-btn[data-setup="all"]').classList.add('active');
      applyFilters();
    }});

    // Compact density mode (persisted)
    const compactBtn = document.getElementById('compactToggleBtn');
    const advancedColsBtn = document.getElementById('advancedColsToggleBtn');
    const compactStored = localStorage.getItem('scanUiCompact') === '1';
    const advancedStored = localStorage.getItem('scanUiShowAdvanced') === '1';

    function syncUiToggleButtons() {{
      compactBtn.textContent = document.body.classList.contains('compact') ? '▦ Comfortable' : '▦ Compact';
      advancedColsBtn.textContent = document.body.classList.contains('show-advanced') ? '☰ Basic' : '☰ Columns';
    }}

    if (compactStored) document.body.classList.add('compact');
    if (advancedStored) document.body.classList.add('show-advanced');
    syncUiToggleButtons();

    compactBtn.addEventListener('click', () => {{
      document.body.classList.toggle('compact');
      localStorage.setItem('scanUiCompact', document.body.classList.contains('compact') ? '1' : '0');
      syncUiToggleButtons();
    }});

    advancedColsBtn.addEventListener('click', () => {{
      document.body.classList.toggle('show-advanced');
      localStorage.setItem('scanUiShowAdvanced', document.body.classList.contains('show-advanced') ? '1' : '0');
      syncUiToggleButtons();
    }});

    // Table header sorting - WITH CURSOR FEEDBACK
    document.querySelectorAll('th').forEach((th, idx) => {{
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {{
        const column = th.textContent.trim();
        if (currentSort.column === column) {{
          currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
        }} else {{
          currentSort.column = column;
          currentSort.direction = 'asc';
        }}
        sortTable(idx);
      }});
      th.addEventListener('mouseenter', () => {{ th.style.opacity = '0.8'; }});
      th.addEventListener('mouseleave', () => {{ th.style.opacity = '1'; }});
    }});

    // Export filtered data
    document.getElementById('exportBtn').addEventListener('click', () => {{
      const visibleRows = originalRows.filter(row => !row.classList.contains('hidden'));
      if (visibleRows.length === 0) {{
        alert('No rows to export. Adjust filters and try again.');
        return;
      }}
      const csv = exportToCSV(visibleRows);
      downloadCSV(csv, 'filtered_results.csv');
    }});

    function applyFilters() {{
      let visible = 0;
      originalRows.forEach(row => {{
        const symbol = row.dataset.symbol.toLowerCase();
        const setup = row.dataset['setupType'];
        const rating = row.dataset.rating;
        const listType = row.dataset['listType'];
        const score = parseFloat(row.dataset.score);

        const matchesSearch = !currentFilters.search ||
          symbol.includes(currentFilters.search) ||
          setup.toLowerCase().includes(currentFilters.search);

        const matchesScore = score >= currentFilters.score;
        const matchesSetup = currentFilters.setup === 'all' || setup === currentFilters.setup;
        const matchesRating = currentFilters.rating === 'all' || rating === currentFilters.rating;
        const matchesListType = currentFilters.listType === 'all' || listType === currentFilters.listType;

        if (matchesSearch && matchesScore && matchesSetup && matchesRating && matchesListType) {{
          row.classList.remove('hidden');
          visible++;
        }} else {{
          row.classList.add('hidden');
        }}
      }});
      updateRowCount(visible, originalRows.length);
      document.getElementById('emptyState').style.display = visible === 0 ? 'block' : 'none';
    }}

    function sortTable(colIdx) {{
      const tbody = document.getElementById('tableBody');
      // Get ALL rows (including hidden), sort visible ones, then maintain order
      const allRows = Array.from(tbody.querySelectorAll('tr'));
      const visibleRows = allRows.filter(row => !row.classList.contains('hidden'));

      visibleRows.sort((a, b) => {{
        const aVal = a.cells[colIdx].textContent.trim();
        const bVal = b.cells[colIdx].textContent.trim();

        const aNum = parseFloat(aVal);
        const bNum = parseFloat(bVal);

        let cmp = 0;
        if (!isNaN(aNum) && !isNaN(bNum)) {{
          cmp = aNum - bNum;
        }} else {{
          cmp = aVal.localeCompare(bVal);
        }}

        return currentSort.direction === 'asc' ? cmp : -cmp;
      }});

      // Update UI - show sort direction
      document.querySelectorAll('th').forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
      document.querySelectorAll('th')[colIdx].classList.add(
        currentSort.direction === 'asc' ? 'sort-asc' : 'sort-desc'
      );

      // Reorder visible rows in DOM
      visibleRows.forEach(row => tbody.appendChild(row));
    }}

    function updateRowCount(visible, total) {{
      document.getElementById('visibleCount').textContent = visible;
      document.getElementById('totalCount').textContent = total;
    }}

    function exportToCSV(rows) {{
      const headers = ['Symbol', 'List', 'Setup', 'Window', 'Height%', 'Depth%', 'Len', 'Ctr', 'Dist%',
        'Rating', 'Close', 'Pivot', 'Entry', 'Score', 'RankScore', 'PivotProx', 'RS', 'Regime', 'Weekly', 'VolDryUp', 'DaysNearPivot', 'PivotFreshness', 'Range%', 'Vol%', 'RExp', 'Shares', 'Stop', 'T1', 'T2', 'T3'];

      let csv = headers.join(',') + '\\n';
      rows.forEach(row => {{
        const cells = Array.from(row.cells).slice(0, 30).map(cell => {{
          let text = cell.textContent.trim();
          if (text.includes(',') || text.includes('"')) {{
            text = '"' + text.replace(/"/g, '""') + '"';
          }}
          return text;
        }});
        csv += cells.join(',') + '\\n';
      }});
      return csv;
    }}

    function downloadCSV(csv, filename) {{
      const blob = new Blob([csv], {{ type: 'text/csv;charset=utf-8;' }});
      const link = document.createElement('a');
      const url = URL.createObjectURL(blob);
      link.setAttribute('href', url);
      link.setAttribute('download', filename);
      link.style.visibility = 'hidden';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }}
  </script>
</body>
</html>
"""
    path.write_text(html_doc)



def main():
    args = parse_args()
    if args.timeframe == "weekly" and args.lookback == DEFAULT_LOOKBACK:
        args.lookback = 104

    symbols, source_path = load_symbols(args)
    market_label = (args.market_label or infer_market_label(source_path)).strip().lower().replace(" ", "_")
    setup_label = args.setups
    scan_label = f"{market_label}_{args.timeframe}" if setup_label == "both" else f"{market_label}_{args.timeframe}_{setup_label}"

    # ── Setup output directory ────────────────────────────────────────────────
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir    = Path(args.output_dir) / f"scan_{scan_label}_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path   = out_dir / f"vcp_hits_{scan_label}_{timestamp}.csv"
    json_path  = out_dir / f"vcp_hits_{scan_label}_{timestamp}.json"
    html_path  = out_dir / f"vcp_hits_{scan_label}_{timestamp}.html"
    watchlist_csv_path = out_dir / f"watchlist_{scan_label}_{timestamp}.csv"
    watchlist_json_path = out_dir / f"watchlist_{scan_label}_{timestamp}.json"
    watchlist_html_path = out_dir / f"watchlist_{scan_label}_{timestamp}.html"
    open_trades_csv_path = out_dir / f"open_trades_{scan_label}_{timestamp}.csv"
    open_trades_json_path = out_dir / f"open_trades_{scan_label}_{timestamp}.json"
    open_trades_html_path = out_dir / f"open_trades_{scan_label}_{timestamp}.html"
    variation_summary_path = out_dir / "variation_progress.md"
    shortlist_csv_path = out_dir / f"portfolio_shortlist_{scan_label}_{timestamp}.csv"
    shortlist_json_path = out_dir / f"portfolio_shortlist_{scan_label}_{timestamp}.json"
    shortlist_html_path = out_dir / f"portfolio_shortlist_{scan_label}_{timestamp}.html"
    rejections_csv_path = out_dir / f"rejections_{scan_label}_{timestamp}.csv"
    rejections_json_path = out_dir / f"rejections_{scan_label}_{timestamp}.json"
    manifest_path = out_dir / "scan_manifest.json"
    bundle_path = out_dir / f"scan_bundle_{scan_label}_{timestamp}.json"
    run_log_path = out_dir / "scan.log"
    events_path = out_dir / "events.jsonl"
    log_path   = out_dir / "batch_log.txt"
    latest_csv = Path(args.output_dir) / f"vcp_hits_{scan_label}_LATEST.csv"
    latest_json = Path(args.output_dir) / f"vcp_hits_{scan_label}_LATEST.json"
    latest_html = Path(args.output_dir) / f"vcp_hits_{scan_label}_LATEST.html"
    latest_watchlist_csv = Path(args.output_dir) / f"watchlist_{scan_label}_LATEST.csv"
    latest_watchlist_json = Path(args.output_dir) / f"watchlist_{scan_label}_LATEST.json"
    latest_watchlist_html = Path(args.output_dir) / f"watchlist_{scan_label}_LATEST.html"
    latest_open_trades_csv = Path(args.output_dir) / f"open_trades_{scan_label}_LATEST.csv"
    latest_open_trades_json = Path(args.output_dir) / f"open_trades_{scan_label}_LATEST.json"
    latest_open_trades_html = Path(args.output_dir) / f"open_trades_{scan_label}_LATEST.html"
    latest_variation_summary = Path(args.output_dir) / f"vcp_hits_{scan_label}_variation_LATEST.md"
    latest_shortlist_csv = Path(args.output_dir) / f"portfolio_shortlist_{scan_label}_LATEST.csv"
    latest_shortlist_json = Path(args.output_dir) / f"portfolio_shortlist_{scan_label}_LATEST.json"
    latest_shortlist_html = Path(args.output_dir) / f"portfolio_shortlist_{scan_label}_LATEST.html"
    latest_rejections_csv = Path(args.output_dir) / f"rejections_{scan_label}_LATEST.csv"
    latest_rejections_json = Path(args.output_dir) / f"rejections_{scan_label}_LATEST.json"
    latest_manifest_path = Path(args.output_dir) / f"scan_manifest_{scan_label}_LATEST.json"
    latest_bundle_path = Path(args.output_dir) / f"scan_bundle_{scan_label}_LATEST.json"
    generic_latest_csv = Path(args.output_dir) / "vcp_hits_LATEST.csv"

    total     = len(symbols)
    batches   = list(chunks(symbols, args.batch))
    n_batches = len(batches)
    universe_path = out_dir / f"symbol_universe_{timestamp}.txt"
    write_symbol_universe(universe_path, symbols, source_path)

    print(f"\n{'═'*72}")
    print(f"  {market_label.upper()} {args.timeframe.upper()} BREAKOUT FULL SCAN  ·  {total} symbols  ·  {n_batches} batches")
    print(f"  Setups: {args.setups.upper()}  ·  Workers: {args.workers}  ·  Batch size: {args.batch}  ·  Lookback: {args.lookback} bars")
    print(f"  Source symbols: {source_path}")
    print(f"  Output directory: {out_dir.resolve()}")
    print(f"{'═'*72}\n")

    all_hits: list[dict] = []
    all_watchlist: list[dict] = []
    all_rejections: list[dict] = []
    validation_issues: list[dict] = []
    scanned_count = 0
    batch_done    = 0
    start_time    = time.time()
    last_save_hit = 0
    last_save_batch = 0

    log_fh = open(log_path, "w")
    run_logger = setup_run_logger(run_log_path)
    append_event(events_path, "scan_start", {
        "scanLabel": scan_label,
        "marketLabel": market_label,
        "timeframe": args.timeframe,
        "setups": args.setups,
        "totalSymbols": total,
        "workers": args.workers,
        "batch": args.batch,
    })
    run_logger.info("Scan start label=%s symbols=%s workers=%s batch=%s", scan_label, total, args.workers, args.batch)
    regime = build_market_regime(symbols, args)
    print(f"  Regime mode: {regime.get('mode')} | favorable={regime.get('favorable')} | breadth50={regime.get('breadth50', 1.0):.2f} | breadth200={regime.get('breadth200', 1.0):.2f}")
    run_logger.info("Regime mode=%s favorable=%s breadth50=%.3f breadth200=%.3f sampled=%s",
                    regime.get("mode"), regime.get("favorable"), regime.get("breadth50", 1.0), regime.get("breadth200", 1.0), regime.get("sampled", 0))

    def process_batch(batch_idx_batch):
        idx, batch = batch_idx_batch
        t0   = time.time()
        if args.no_watchlist:
            # scan only — no watchlist needed
            hits = scan_batch(batch, args)
            watchlist_hits = []
        else:
            # ⚡ Combined mode: single JVM call for scan + watchlist
            hits, watchlist_hits = scan_combined_batch(batch, args)
        dur  = time.time() - t0
        parsed = [parse_hit(h) for h in hits]
        parsed_watch = [parse_hit(h) for h in watchlist_hits]
        return idx, batch, parsed, parsed_watch, dur

    def persist_outputs(force: bool = False):
        nonlocal last_save_hit, last_save_batch
        should_save = force or (len(all_hits) - last_save_hit >= SAVE_EVERY_N_HITS) or (batch_done - last_save_batch >= SAVE_EVERY_N_BATCHES)
        if not should_save:
            return

        def safe_score(h):
            try:
                return float(h.get("score", 0))
            except Exception:
                return 0.0

        snapshot = sorted(all_hits, key=safe_score, reverse=True)
        watch_snapshot = sorted(all_watchlist, key=safe_score, reverse=True)
        shortlist_snapshot = apply_portfolio_heat(snapshot, args)
        open_trade_snapshot = as_open_trade_rows(snapshot)


        # Save breakout performance tracking to a segregated file
        breakout_perf_path = out_dir / f"breakout_performance_{scan_label}_{timestamp}.csv"
        latest_breakout_perf_path = Path(args.output_dir) / f"breakout_performance_{scan_label}_LATEST.csv"
        breakout_perf_html_path = out_dir / f"breakout_performance_{scan_label}_{timestamp}.html"
        latest_breakout_perf_html_path = Path(args.output_dir) / f"breakout_performance_{scan_label}_LATEST.html"
        save_breakout_performance(open_trade_snapshot, breakout_perf_path)
        save_breakout_performance(open_trade_snapshot, latest_breakout_perf_path)

        # HTML is expensive to generate — only write on final forced save or every 5th interim
        interim_save_count = (batch_done // SAVE_EVERY_N_BATCHES)
        write_html = force or (interim_save_count % 5 == 0)
        if write_html:
            save_html(snapshot, html_path, meta_snapshot)
            save_html(open_trade_snapshot, open_trades_html_path, meta_snapshot)
            save_html(watch_snapshot, watchlist_html_path, meta_snapshot)
            save_html(shortlist_snapshot, shortlist_html_path, meta_snapshot)
            save_html(snapshot, latest_html, meta_snapshot)
            save_html(open_trade_snapshot, latest_open_trades_html, meta_snapshot)
            save_html(watch_snapshot, latest_watchlist_html, meta_snapshot)
            save_html(shortlist_snapshot, latest_shortlist_html, meta_snapshot)

        elapsed_snapshot = str(timedelta(seconds=int(time.time() - start_time)))
        meta_snapshot = {
            "finished": datetime.now().isoformat(timespec="seconds"),
            "total_scanned": scanned_count,
            "elapsed": elapsed_snapshot,
        }

        # Always write fast CSV + JSON
        save_csv(snapshot, csv_path)
        save_json(snapshot, json_path)
        save_csv(open_trade_snapshot, open_trades_csv_path)
        save_json(open_trade_snapshot, open_trades_json_path)
        save_csv(watch_snapshot, watchlist_csv_path)
        save_json(watch_snapshot, watchlist_json_path)
        save_csv(shortlist_snapshot, shortlist_csv_path)
        save_json(shortlist_snapshot, shortlist_json_path)
        save_variation_summary(snapshot, variation_summary_path, meta_snapshot)
        save_csv(snapshot, latest_csv)
        save_json(snapshot, latest_json)
        save_csv(open_trade_snapshot, latest_open_trades_csv)
        save_json(open_trade_snapshot, latest_open_trades_json)
        save_csv(watch_snapshot, latest_watchlist_csv)
        save_json(watch_snapshot, latest_watchlist_json)
        save_csv(shortlist_snapshot, latest_shortlist_csv)
        save_json(shortlist_snapshot, latest_shortlist_json)
        save_variation_summary(snapshot, latest_variation_summary, meta_snapshot)
        save_csv(snapshot, generic_latest_csv)
        # Now that meta_snapshot is defined and all other saves are done, save breakout performance HTML
        save_html(open_trade_snapshot, breakout_perf_html_path, meta_snapshot)
        save_html(open_trade_snapshot, latest_breakout_perf_html_path, meta_snapshot)

        # ⚡ HTML is expensive to generate — only write on final forced save or every 5th interim
        # This avoids blocking the scan loop with large HTML builds every 30 hits
        interim_save_count = (batch_done // SAVE_EVERY_N_BATCHES)
        write_html = force or (interim_save_count % 5 == 0)
        if write_html:
            save_html(snapshot, html_path, meta_snapshot)
            save_html(open_trade_snapshot, open_trades_html_path, meta_snapshot)
            save_html(watch_snapshot, watchlist_html_path, meta_snapshot)
            save_html(shortlist_snapshot, shortlist_html_path, meta_snapshot)
            save_html(snapshot, latest_html, meta_snapshot)
            save_html(open_trade_snapshot, latest_open_trades_html, meta_snapshot)
            save_html(watch_snapshot, latest_watchlist_html, meta_snapshot)
            save_html(shortlist_snapshot, latest_shortlist_html, meta_snapshot)

        last_save_hit = len(all_hits)
        last_save_batch = batch_done

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_to_idx = {
            pool.submit(process_batch, (idx, batch)): idx
            for idx, batch in enumerate(batches, 1)
        }

        for future in as_completed(future_to_idx):
            try:
                idx, batch, parsed, parsed_watch, dur = future.result()
            except Exception as exc:
                print(f"  [ERR] future failed: {exc}", flush=True)
                run_logger.error("Batch future failed: %s", exc)
                append_event(events_path, "batch_error", {"error": str(exc)})
                continue

            with lock:
                scanned_count += len(batch)
                batch_done    += 1
                all_hits.extend(parsed)
                all_watchlist.extend(parsed_watch)

                # Log
                hit_syms = [h["symbol"] for h in parsed]
                log_line = (
                    f"[{batch_done:4}/{n_batches}]  "
                    f"scanned={scanned_count:5}  "
                    f"hits={len(all_hits):4}  "
                    f"dur={dur:5.1f}s  "
                    f"batch={'|'.join(batch[:3])}{'…' if len(batch)>3 else ''}  "
                    f"hits={hit_syms}"
                )
                log_fh.write(log_line + "\n")
                log_fh.flush()
                run_logger.info(log_line)

                # ETA
                elapsed  = time.time() - start_time
                rate     = scanned_count / elapsed if elapsed > 0 else 0
                remaining = (total - scanned_count) / rate if rate > 0 else 0
                eta_str  = str(timedelta(seconds=int(remaining)))

                # Progress output
                bar = progress_bar(scanned_count, total)
                variation_counts = summarize_variations(all_hits)
                variation_text = (
                    f" setup[{_fmt_top(variation_counts['setup'], 2)}]"
                    f" win[{_fmt_top(variation_counts['window'], 2)}]"
                )
                hit_notice = ""
                if parsed:
                    hit_notice = f"  ✅ {' '.join(hit_syms)}"
                print(
                    f"\r{bar}  hits={len(all_hits)} watch={len(all_watchlist)}  ETA={eta_str}{variation_text}{hit_notice}",
                    end="", flush=True
                )
                if parsed:
                    print()  # newline so hit notices aren't overwritten

                # Rolling save
                persist_outputs()

    log_fh.close()
    append_event(events_path, "scan_batches_complete", {"scanned": scanned_count, "hits": len(all_hits), "watchlist": len(all_watchlist)})
    print()  # final newline after progress bar

    # ── Mean Reversion Python scan (runs on cached bars, no Java needed) ──────
    if args.setups in ("mean_reversion", "full"):
        mr_hits = _run_mr_scan(symbols, args)
        if mr_hits:
            all_hits.extend(mr_hits)
            append_event(events_path, "mr_scan_complete", {"mrHits": len(mr_hits)})

    # ── Breakout Pullback Python scan (ABFP – first pullback after breakout) ──
    if args.setups in ("breakout_pullback", "full"):
        abfp_hits = _run_abfp_scan(symbols, args)
        if abfp_hits:
            # Deduplicate: skip symbols already present from Java/MR scan
            existing = {h.get("symbol") for h in all_hits}
            new_abfp = [h for h in abfp_hits if h.get("symbol") not in existing]
            all_hits.extend(new_abfp)
            append_event(events_path, "abfp_scan_complete", {"abfpHits": len(new_abfp), "abfpTotal": len(abfp_hits)})

    # ── Python breakout detector (optional) ─────────────────────────────────
    # Use the Python breakout detector to catch cases the Java scanner may miss
    # (e.g., breakout followed by a shallow pullback but still above breakout bar high).
    if _PY_BO_AVAILABLE and args.setups in ("full", "both"):
        try:
            py_bo_hits = py_scan_symbols(
                symbols,
                cache_dir=args.cache_dir,
                lookback=args.lookback,
                timeframe=args.timeframe,
                account_size=args.account_size,
                base_risk_pct=args.base_risk_pct,
                min_price_floor=args.min_price_floor,
                min_score=35.0,
                setup_types=["BREAKOUT"],
            )
            # Merge python breakout hits if symbol not already present
            existing = {h.get("symbol") for h in all_hits}
            new_hits = [h for h in py_bo_hits if h.get("symbol") not in existing]
            if new_hits:
                all_hits.extend(new_hits)
                append_event(events_path, "py_bo_scan_complete", {"pyBoHits": len(new_hits)})
        except Exception as exc:
            print(f"[WARN] python breakout scan failed: {exc}", flush=True)

    # ── Final saves ───────────────────────────────────────────────────────────
    elapsed_total = time.time() - start_time
    elapsed_str   = str(timedelta(seconds=int(elapsed_total)))
    meta = {
        "finished":      datetime.now().isoformat(timespec="seconds"),
        "total_scanned": total,
        "elapsed":       elapsed_str,
    }

    valid_hits, issues_hits = validate_rows(all_hits, "HIT")
    valid_watch, issues_watch = validate_rows(all_watchlist, "WATCHLIST")
    validation_issues.extend(issues_hits)
    validation_issues.extend(issues_watch)
    all_hits, rejected_hits, rejected_map_hits = enrich_and_filter_rows(valid_hits, args, regime, "HIT")
    all_watchlist, rejected_watch, rejected_map_watch = enrich_and_filter_rows(valid_watch, args, regime, "WATCHLIST")
    merged_rejected_map = dict(rejected_map_watch)
    merged_rejected_map.update(rejected_map_hits)
    all_rejections.extend(rejected_hits)
    all_rejections.extend(rejected_watch)
    all_rejections.extend(validation_issues)

    def safe_rank(h):
        return _to_float(h.get("rankingScore"), _to_float(h.get("score")))

    all_hits.sort(key=safe_rank, reverse=True)
    all_watchlist = rank_watchlist_rows(all_watchlist)
    open_trades = as_open_trade_rows(all_hits)
    shortlist = apply_portfolio_heat(all_hits, args)
    included_symbols = {r.get("symbol", "") for r in all_hits} | {r.get("symbol", "") for r in all_watchlist}
    all_rejections.extend(build_rejection_rows(symbols, included_symbols, merged_rejected_map))
    run_logger.info("Post-validation kept hits=%s watchlist=%s rejections=%s validationIssues=%s", len(all_hits), len(all_watchlist), len(all_rejections), len(validation_issues))

    save_csv(all_hits,  csv_path)
    save_json(all_hits, json_path)
    save_html(all_hits, html_path, meta)
    save_csv(open_trades, open_trades_csv_path)
    save_json(open_trades, open_trades_json_path)
    save_html(open_trades, open_trades_html_path, meta)
    save_csv(all_watchlist, watchlist_csv_path)
    save_json(all_watchlist, watchlist_json_path)
    save_html(all_watchlist, watchlist_html_path, meta)
    save_csv(shortlist, shortlist_csv_path)
    save_json(shortlist, shortlist_json_path)
    save_html(shortlist, shortlist_html_path, meta)
    save_rejections(all_rejections, rejections_csv_path, rejections_json_path)
    save_variation_summary(all_hits, variation_summary_path, meta)

    manifest_payload = {
        "runId": f"{scan_label}_{timestamp}",
        "generatedAt": meta["finished"],
        "marketLabel": market_label,
        "timeframe": args.timeframe,
        "setups": args.setups,
        "lookback": args.lookback,
        "workers": args.workers,
        "batch": args.batch,
        "regime": regime,
        "filters": {
            "minPriceFloor": args.min_price_floor,
            "minAvgVolume": args.min_avg_volume,
            "minAvgDollarVolume": args.min_avg_dollar_volume,
            "liquidityLookback": args.liquidity_lookback,
            "regimeMode": args.regime_mode,
            "rsWeight": args.rs_weight,
            "watchlistRankingWeights": WATCHLIST_RANK_WEIGHTS,
            "maxPortfolioHeatR": args.max_portfolio_heat_r,
            "accountSize": args.account_size,
            "baseRiskPct": args.base_risk_pct,
        },
        "counts": {
            "symbols": total,
            "hits": len(all_hits),
            "watchlist": len(all_watchlist),
            "shortlist": len(shortlist),
            "rejections": len(all_rejections),
            "validationIssues": len(validation_issues),
        },
        "files": {
            "hitsCsv": str(csv_path.resolve()),
            "hitsJson": str(json_path.resolve()),
            "hitsHtml": str(html_path.resolve()),
            "watchlistCsv": str(watchlist_csv_path.resolve()),
            "watchlistJson": str(watchlist_json_path.resolve()),
            "watchlistHtml": str(watchlist_html_path.resolve()),
            "shortlistCsv": str(shortlist_csv_path.resolve()),
            "shortlistJson": str(shortlist_json_path.resolve()),
            "shortlistHtml": str(shortlist_html_path.resolve()),
            "rejectionsCsv": str(rejections_csv_path.resolve()),
            "rejectionsJson": str(rejections_json_path.resolve()),
            "batchLog": str(log_path.resolve()),
            "runLog": str(run_log_path.resolve()),
            "events": str(events_path.resolve()),
        },
    }
    save_manifest(manifest_path, manifest_payload)
    save_bundle(
        bundle_path,
        meta={"scanLabel": scan_label, "elapsed": elapsed_str, "regime": regime},
        files=manifest_payload["files"],
        counts=manifest_payload["counts"],
        validation={"issues": len(validation_issues)},
    )

    # Copy to latest
    save_csv(all_hits, latest_csv)
    save_json(all_hits, latest_json)
    save_html(all_hits, latest_html, meta)
    save_csv(open_trades, latest_open_trades_csv)
    save_json(open_trades, latest_open_trades_json)
    save_html(open_trades, latest_open_trades_html, meta)
    save_csv(all_watchlist, latest_watchlist_csv)
    save_json(all_watchlist, latest_watchlist_json)
    save_html(all_watchlist, latest_watchlist_html, meta)
    save_csv(shortlist, latest_shortlist_csv)
    save_json(shortlist, latest_shortlist_json)
    save_html(shortlist, latest_shortlist_html, meta)
    save_rejections(all_rejections, latest_rejections_csv, latest_rejections_json)
    save_variation_summary(all_hits, latest_variation_summary, meta)
    save_manifest(latest_manifest_path, manifest_payload)
    save_bundle(
        latest_bundle_path,
        meta={"scanLabel": scan_label, "elapsed": elapsed_str, "regime": regime},
        files=manifest_payload["files"],
        counts=manifest_payload["counts"],
        validation={"issues": len(validation_issues)},
    )
    save_csv(all_hits, generic_latest_csv)

    # Also keep split setup lists for quick daily review.
    if args.setups in {"both", "full", "breakout_pullback"}:
        setup_names = ["VCP", "RANGE_EXPANSION"]
        if args.setups == "full":
            setup_names += ["MEAN_REVERSION", "BREAKOUT_PULLBACK"]
        elif args.setups == "breakout_pullback":
            setup_names = ["BREAKOUT_PULLBACK"]
        for setup in setup_names:
            filtered = [h for h in all_hits if h.get("setup", "").upper() == setup]
            suffix = setup.lower()
            save_csv(filtered, Path(args.output_dir) / f"vcp_hits_{market_label}_{args.timeframe}_{suffix}_LATEST.csv")
            save_json(filtered, Path(args.output_dir) / f"vcp_hits_{market_label}_{args.timeframe}_{suffix}_LATEST.json")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*72}")
    print(f"  SCAN COMPLETE")
    print(f"  Symbols scanned : {total}")
    print(f"  Open trades     : {len(all_hits)}")
    print(f"  Watchlist       : {len(all_watchlist)}")
    print(f"  Portfolio picks : {len(shortlist)} (max heat {args.max_portfolio_heat_r:.2f}R)")
    print(f"  Rejections      : {len(all_rejections)}")
    print(f"  Elapsed         : {elapsed_str}")
    print(f"{'═'*72}")

    if all_hits:
        hdr = (f"{'SYMBOL':<14} {'SETUP':>15} {'WINDOW':>10} {'HEIGHT%':>8} {'DEPTH%':>8} {'LEN':>5} {'CTR':>7} {'RATING':>7} {'CLOSE':>9} {'PIVOT':>9} {'ENTRY':>9} {'SCORE':>7} "
               f"{'RANGE%':>7} {'VOL%':>7} {'REXP':>7} {'SHARES':>7} {'STOP':>9} "
               f"{'T1':>9} {'T2':>9} {'T3':>9}")
        print(hdr)
        print("-" * len(hdr))
        for h in all_hits:
            print(
                f"{h.get('symbol',''):<14} "
                f"{h.get('setup','VCP'):>15} {h.get('window',''):>10} {h.get('height%',''):>8} {h.get('depth%',''):>8} {h.get('len',''):>5} {h.get('ctr',''):>7} {h.get('rating',''):>7} {h.get('close',''):>9} {h.get('pivot',''):>9} "
                f"{h.get('entry',''):>9} {h.get('score',''):>7} {h.get('range%',''):>7} "
                f"{h.get('vol%',''):>7} {h.get('rexp',''):>7} {h.get('shares',''):>7} "
                f"{h.get('sl',''):>9} {h.get('T1',''):>9} "
                f"{h.get('T2',''):>9} {h.get('T3',''):>9}"
            )
        print(f"\n  HITS CSV  → {csv_path.resolve()}")
        print(f"  HITS JSON → {json_path.resolve()}")
        print(f"  HITS HTML → {html_path.resolve()}")
        print(f"  OPEN CSV  → {open_trades_csv_path.resolve()}")
        print(f"  OPEN HTML → {open_trades_html_path.resolve()}")
        print(f"  WATCH CSV → {watchlist_csv_path.resolve()}")
        print(f"  WATCH HTML→ {watchlist_html_path.resolve()}")
        print(f"  SHORT→ {shortlist_csv_path.resolve()}")
        print(f"  REJCT→ {rejections_csv_path.resolve()}")
        print(f"  MANF → {manifest_path.resolve()}")
        print(f"  BNDL → {bundle_path.resolve()}")
        print(f"  LCSV → {latest_csv.resolve()}")
        print(f"  LJSN → {latest_json.resolve()}")
        print(f"  LHTM → {latest_html.resolve()}")
        print(f"  VAR  → {variation_summary_path.resolve()}")
        print(f"  LOG  → {log_path.resolve()}")
        print(f"  UNIV → {universe_path.resolve()}")
    else:
        print("  No filtered breakouts found in today's scan.")
        print(f"  WATCH CNT → {len(all_watchlist)}")
        print(f"  SHORT CNT → {len(shortlist)}")
        print(f"  REJCT CNT → {len(all_rejections)}")
        print(f"  MANF → {manifest_path.resolve()}")
        print(f"  BNDL → {bundle_path.resolve()}")
        print(f"  LCSV → {latest_csv.resolve()}")
        print(f"  LJSN → {latest_json.resolve()}")
        print(f"  LHTM → {latest_html.resolve()}")
        print(f"  VAR  → {variation_summary_path.resolve()}")
        print(f"  UNIV → {universe_path.resolve()}")


if __name__ == "__main__":
    main()

