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

# ── DEFAULTS ──────────────────────────────────────────────────────────────────
DEFAULT_SYMBOLS_FILE  = str(ROOT / "data" / "universes" / "all_us_stocks.txt")
FALLBACK_SYMBOLS_FILE = str(ROOT / "data" / "universes" / "us_stocks.txt")
CSV_SYMBOLS_FILE      = str(ROOT / "data" / "universes" / "us_stock_tickers.csv")
INDIA_SYMBOLS_FILE    = str(ROOT / "data" / "universes" / "indian_stock_tickers.csv")
DEFAULT_LOOKBACK      = 252
DEFAULT_RETRIES       = 3
DEFAULT_CACHE_DIR     = str(ROOT / "cache")
DEFAULT_CACHE_TTL_MIN = 360                   # 6 hours
DEFAULT_BATCH_SIZE    = 25                    # symbols per Java process
DEFAULT_WORKERS       = 4                     # concurrent Java processes
SAVE_EVERY_N_HITS     = 20                    # flush CSV every N new hits
SAVE_EVERY_N_BATCHES  = 10                    # refresh output files even if hit count is unchanged
JAVA_TIMEOUT_SEC      = 180                   # kill stalled Java process after 3 min
DEFAULT_LIQ_LOOKBACK  = 20
DEFAULT_ACCOUNT_SIZE  = 100_000.0
DEFAULT_BASE_RISK_PCT = 0.01
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


def parse_args():
    p = argparse.ArgumentParser(description="Full market breakout scan")
    p.add_argument("--symbols",   default=None)
    p.add_argument("--timeframe", choices=["daily", "weekly"], default="daily")
    p.add_argument("--setups", choices=["both", "vcp", "range_expansion"], default="both")
    p.add_argument("--market-label", default=None, help="Optional market label for output names, e.g. us or india")
    p.add_argument("--exchange-suffix", default=None, help="Optional Yahoo suffix override such as .NS or .BO")
    p.add_argument("--lookback",  type=int, default=DEFAULT_LOOKBACK)
    p.add_argument("--retries",   type=int, default=DEFAULT_RETRIES)
    p.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)
    p.add_argument("--cache-ttl", "--cache-ttl-min", dest="cache_ttl", type=int, default=DEFAULT_CACHE_TTL_MIN)
    p.add_argument("--batch",     type=int, default=DEFAULT_BATCH_SIZE)
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


def _to_float(value, default=0.0):
    try:
        if value is None:
            return default
        text = str(value).strip().replace("%", "").replace(",", "")
        return float(text)
    except Exception:
        return default


def _safe_return(closes: list[float], bars: int) -> float:
    if bars <= 0 or len(closes) <= bars:
        return 0.0
    old = closes[-bars - 1]
    now = closes[-1]
    if old <= 0:
        return 0.0
    return (now / old) - 1.0


def _cache_candidates(symbol: str, lookback: int, timeframe: str, cache_dir: str) -> list[Path]:
    cache = Path(cache_dir)
    suffixes = {lookback}
    if timeframe == "weekly":
        suffixes.add(max(lookback * 7, lookback + 60))
    suffixes.update({252, 728})
    files = [cache / f"{symbol}_{n}.csv" for n in sorted(suffixes)]
    existing = [p for p in files if p.exists()]
    if existing:
        return existing
    return sorted(cache.glob(f"{symbol}_*.csv"))


def load_cached_bars(symbol: str, lookback: int, timeframe: str, cache_dir: str) -> list[dict]:
    for path in _cache_candidates(symbol, lookback, timeframe, cache_dir):
        try:
            rows = []
            with open(path, newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    rows.append({
                        "close": _to_float(row.get("close")),
                        "volume": _to_float(row.get("volume")),
                    })
            if len(rows) >= 30:
                return rows
        except Exception:
            continue
    return []


def build_market_regime(symbols: list[str], args) -> dict:
    if args.regime_mode == "off":
        return {"mode": "off", "favorable": True, "breadth50": 1.0, "breadth200": 1.0, "score": 1.0, "sampled": 0}

    sample = symbols[: max(10, min(len(symbols), args.regime_sample))]
    above50 = 0
    above200 = 0
    valid = 0
    rs_pool_3m: list[float] = []
    rs_pool_6m: list[float] = []
    rs_pool_12m: list[float] = []

    for sym in sample:
        bars = load_cached_bars(sym, args.lookback, args.timeframe, args.cache_dir)
        if len(bars) < 210:
            continue
        closes = [b["close"] for b in bars if b.get("close", 0) > 0]
        if len(closes) < 210:
            continue
        close = closes[-1]
        ma50 = sum(closes[-50:]) / 50
        ma200 = sum(closes[-200:]) / 200
        valid += 1
        if close > ma50:
            above50 += 1
        if close > ma200:
            above200 += 1
        rs_pool_3m.append(_safe_return(closes, 63))
        rs_pool_6m.append(_safe_return(closes, 126))
        rs_pool_12m.append(_safe_return(closes, 252))

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

        quality = _to_float(row.get("score"))
        rank_score = quality + (args.rs_weight * rs_score)
        if regime.get("mode") == "soft" and not regime.get("favorable", True):
            rank_score -= 10.0
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
    cumulative = 0.0
    denom = args.account_size * args.base_risk_pct
    for row in sorted_rows:
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
    return shortlist


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


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def scan_batch(batch: list[str], args) -> list[str]:
    """Invoke Java scanner for one batch; return raw hit lines."""
    cmd = [
        "java", "-cp", "src", "Main",
        "--mode=scan",
        "--provider=yahoo",
        f"--timeframe={args.timeframe}",
        f"--setups={args.setups}",
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
    cmd = [
        "java", "-cp", "src", "Main",
        "--mode=watchlist",
        "--provider=yahoo",
        f"--timeframe={args.timeframe}",
        f"--setups={args.setups}",
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
        return []
    except Exception as exc:
        with lock:
            print(f"  [WARN] batch error: {exc}", flush=True)
        return []


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
    "symbol", "listType", "setup", "window", "height%", "depth%", "len", "ctr", "dist%", "rating", "close", "pivot", "entry", "score",
    "range%", "vol%", "rexp", "shares", "sl", "T1", "T2", "T3", "avgVol20", "avgDollarVol20", "rs3m", "rs6m", "rs12m", "rsScore",
    "regimeState", "regimeScore", "rankingScore", "riskR", "heatAfterR"
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
        out.append(item)
    return out


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

        setup_desc = (
            "VCP — Volatility Contraction Pattern with tightening range waves into pivot"
            if setup == "VCP"
            else "Range Expansion Breakout — narrow base with wide-range breakout candle above pivot"
        )
        lines = [
            f"Setup: {setup_desc}",
            f"Rating: {rating}  |  Window: {window}  |  Quality Score: {score}",
            f"Base Height: {height}%  |  Contraction Depth: {depth}%  |  Contraction Pairs: {ctr}",
            f"Range Expansion: {rexp}x  |  Volume vs Avg: {vol}%",
            f"Pivot: {pivot}  |  Entry: {entry}  |  Stop Loss: {sl}",
            f"Targets → T1(1R): {t1}  |  T2(2R): {t2}  |  T3(3R): {t3}",
            f"Distance to Pivot: {dist}%",
        ]
        return " &#10; ".join(lines)

    # Build table rows with data attributes
    rows_html = ""
    for r in rows:
        symbol = html.escape(r.get("symbol", ""))
        setup_type = (r.get("setup", "")).upper()
        rating_val = str(r.get("rating", "")).upper()
        score_val = float(r.get("score", 0))

        price_link, fund_link = chart_links(r.get("symbol", ""))
        rating_chip = rating_badge(rating_val)
        reason_tooltip = build_scan_reason(r)
        list_type_raw = str(r.get('listType', 'BREAKOUT')).upper()
        list_type_css = f"list-badge list-{list_type_raw.lower()}"
        list_type_chip = f"<span class='{list_type_css}'>{html.escape(list_type_raw)}</span>"
        score_chip = f"<span class='score-chip'>{html.escape(str(r.get('score','')))}</span>"

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
            f"<td>{html.escape(str(r.get('height%','')))}</td>"
            f"<td>{html.escape(str(r.get('depth%','')))}</td>"
            f"<td>{html.escape(str(r.get('len','')))}</td>"
            f"<td>{html.escape(str(r.get('ctr','')))}</td>"
            f"<td>{html.escape(str(r.get('dist%','')))}</td>"
            f"<td>{rating_chip}</td>"
            f"<td>{html.escape(str(r.get('close','')))}</td>"
            f"<td>{html.escape(str(r.get('pivot','')))}</td>"
            f"<td>{html.escape(str(r.get('entry','')))}</td>"
            f"<td>{score_chip}</td>"
            f"<td>{html.escape(str(r.get('range%','')))}</td>"
            f"<td>{html.escape(str(r.get('vol%','')))}</td>"
            f"<td>{html.escape(str(r.get('rexp','')))}</td>"
            f"<td>{html.escape(str(r.get('shares','')))}</td>"
            f"<td>{html.escape(str(r.get('sl','')))}</td>"
            f"<td>{html.escape(str(r.get('T1','')))}</td>"
            f"<td>{html.escape(str(r.get('T2','')))}</td>"
            f"<td>{html.escape(str(r.get('T3','')))}</td>"
            f"<td class='links'>{price_link}</td>"
            f"<td class='links'>{fund_link}</td>"
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
      #dataTable th:nth-child(20), #dataTable td:nth-child(20),
      #dataTable th:nth-child(21), #dataTable td:nth-child(21),
      #dataTable th:nth-child(22), #dataTable td:nth-child(22),
      #dataTable th:nth-child(24), #dataTable td:nth-child(24) {{ display: none; }}

      body.show-advanced #dataTable th:nth-child(5), body.show-advanced #dataTable td:nth-child(5),
      body.show-advanced #dataTable th:nth-child(6), body.show-advanced #dataTable td:nth-child(6),
      body.show-advanced #dataTable th:nth-child(7), body.show-advanced #dataTable td:nth-child(7),
      body.show-advanced #dataTable th:nth-child(8), body.show-advanced #dataTable td:nth-child(8),
      body.show-advanced #dataTable th:nth-child(15), body.show-advanced #dataTable td:nth-child(15),
      body.show-advanced #dataTable th:nth-child(16), body.show-advanced #dataTable td:nth-child(16),
      body.show-advanced #dataTable th:nth-child(17), body.show-advanced #dataTable td:nth-child(17),
      body.show-advanced #dataTable th:nth-child(18), body.show-advanced #dataTable td:nth-child(18),
      body.show-advanced #dataTable th:nth-child(20), body.show-advanced #dataTable td:nth-child(20),
      body.show-advanced #dataTable th:nth-child(21), body.show-advanced #dataTable td:nth-child(21),
      body.show-advanced #dataTable th:nth-child(22), body.show-advanced #dataTable td:nth-child(22),
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
        <th>Symbol</th><th>List Type</th><th>Setup</th><th>Window</th><th>Base Height %</th><th>Contraction Depth %</th><th>Base Length</th><th>Contraction Pairs</th><th>Pivot Distance %</th><th>Rating</th><th>Last Close</th><th>Pivot Price</th><th>Planned Entry</th><th>Quality Score</th>
        <th>Range Contraction %</th><th>Volume Contraction %</th><th>Range Expansion x</th><th>Position Size</th><th>Stop Loss</th>
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
        'Rating', 'Close', 'Pivot', 'Entry', 'Score', 'Range%', 'Vol%', 'RExp', 'Shares', 'Stop', 'T1', 'T2', 'T3'];

      let csv = headers.join(',') + '\\n';
      rows.forEach(row => {{
        const cells = Array.from(row.cells).slice(0, 22).map(cell => {{
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


def progress_bar(done: int, total: int, width: int = 40) -> str:
    pct   = done / total if total else 0
    filled = int(width * pct)
    bar   = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {done}/{total} ({pct*100:.1f}%)"


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
        hits = scan_batch(batch, args)
        watchlist_hits = [] if args.no_watchlist else scan_watchlist_batch(batch, args)
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
        elapsed_snapshot = str(timedelta(seconds=int(time.time() - start_time)))
        meta_snapshot = {
            "finished": datetime.now().isoformat(timespec="seconds"),
            "total_scanned": scanned_count,
            "elapsed": elapsed_snapshot,
        }
        save_csv(snapshot, csv_path)
        save_json(snapshot, json_path)
        save_html(snapshot, html_path, meta_snapshot)
        save_csv(open_trade_snapshot, open_trades_csv_path)
        save_json(open_trade_snapshot, open_trades_json_path)
        save_html(open_trade_snapshot, open_trades_html_path, meta_snapshot)
        save_csv(watch_snapshot, watchlist_csv_path)
        save_json(watch_snapshot, watchlist_json_path)
        save_html(watch_snapshot, watchlist_html_path, meta_snapshot)
        save_csv(shortlist_snapshot, shortlist_csv_path)
        save_json(shortlist_snapshot, shortlist_json_path)
        save_html(shortlist_snapshot, shortlist_html_path, meta_snapshot)
        save_variation_summary(snapshot, variation_summary_path, meta_snapshot)
        save_csv(snapshot, latest_csv)
        save_json(snapshot, latest_json)
        save_html(snapshot, latest_html, meta_snapshot)
        save_csv(open_trade_snapshot, latest_open_trades_csv)
        save_json(open_trade_snapshot, latest_open_trades_json)
        save_html(open_trade_snapshot, latest_open_trades_html, meta_snapshot)
        save_csv(watch_snapshot, latest_watchlist_csv)
        save_json(watch_snapshot, latest_watchlist_json)
        save_html(watch_snapshot, latest_watchlist_html, meta_snapshot)
        save_csv(shortlist_snapshot, latest_shortlist_csv)
        save_json(shortlist_snapshot, latest_shortlist_json)
        save_html(shortlist_snapshot, latest_shortlist_html, meta_snapshot)
        save_variation_summary(snapshot, latest_variation_summary, meta_snapshot)
        save_csv(snapshot, generic_latest_csv)
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
    all_watchlist.sort(key=safe_rank, reverse=True)
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

    # Also keep split setup lists for quick daily review when scanning in both mode.
    if args.setups == "both":
        for setup in ("VCP", "RANGE_EXPANSION"):
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

