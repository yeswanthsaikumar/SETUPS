#!/usr/bin/env python3
"""
run_vcp_system.py
─────────────────
Single-command daily system runner for breakout scans.

What it does:
  1. Optionally refreshes the US symbol universe
  2. Compiles Java sources
  3. Runs daily + weekly breakout scans for US and Indian symbols
  4. Writes a combined summary into output/system_run_<timestamp>/

Examples:
    python3 apps/python/cli/run_vcp_system.py
    python3 apps/python/cli/run_vcp_system.py --markets us --timeframes daily,weekly
    python3 apps/python/cli/run_vcp_system.py --workers 6 --batch 30
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CLI_DIR = ROOT / "apps" / "python" / "cli"
DEFAULT_OUTPUT_DIR = ROOT / "output"
DEFAULT_US_SYMBOLS = ROOT / "data" / "universes" / "us_stock_tickers.csv"
DEFAULT_US_FALLBACK = ROOT / "data" / "universes" / "all_us_stocks.txt"
DEFAULT_INDIA_SYMBOLS = ROOT / "data" / "universes" / "indian_stock_tickers.csv"
FETCH_US_SCRIPT = CLI_DIR / "fetch_us_stocks.py"
SCAN_SCRIPT = CLI_DIR / "run_full_us_scan.py"
JAVA_SRC_DIR = ROOT / "src"


def parse_csv_list(value: str, allowed: set[str]) -> list[str]:
    items = [item.strip().lower() for item in value.split(",") if item.strip()]
    if not items:
        raise SystemExit("Empty selection is not allowed.")
    normalized = []
    for item in items:
        if item == "all":
            return sorted(allowed)
        if item not in allowed:
            raise SystemExit(f"Unsupported value: {item}. Allowed: {', '.join(sorted(allowed))}")
        if item not in normalized:
            normalized.append(item)
    return normalized


def normalize_setup_mode(value: str) -> str:
    mode = (value or "").strip().lower()
    if mode == "all":
        return "full"
    return mode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily and weekly VCP + range breakout scans for US and Indian stocks")
    parser.add_argument("--markets", default="us,india", help="Comma-separated: us, india, or all")
    parser.add_argument("--timeframes", default="daily,weekly", help="Comma-separated: daily, weekly, or all")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--batch", type=int, default=40)
    parser.add_argument("--daily-lookback", type=int, default=252, help="Daily bars lookback (default: 252 = ~1 year)")
    parser.add_argument("--weekly-lookback", type=int, default=104, help="Weekly bars lookback (default: 104 = ~2 years)")
    parser.add_argument(
        "--setups",
        default="full",
        choices=["full", "both", "vcp", "range_expansion", "mean_reversion", "all"],
        help="Setup filter: full, both, vcp, range_expansion, mean_reversion, or all (legacy alias for full)",
    )
    parser.add_argument("--cache-dir", default="cache")
    parser.add_argument("--cache-ttl", type=int, default=360)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--us-symbols", default=None, help="Override US symbols file")
    parser.add_argument("--india-symbols", default=None, help="Override Indian symbols file")
    parser.add_argument("--skip-us-refresh", action="store_true", help="Skip US universe refresh (use cached file)")
    parser.add_argument("--force-us-refresh", action="store_true", help="Force refresh of US universe (download fresh)")
    args = parser.parse_args()

    if args.workers <= 0:
        parser.error("--workers must be greater than 0")
    if args.batch <= 0:
        parser.error("--batch must be greater than 0")
    if args.daily_lookback <= 0 or args.weekly_lookback <= 0:
        parser.error("Lookbacks must be greater than 0")

    args.markets = parse_csv_list(args.markets, {"us", "india"})
    args.timeframes = parse_csv_list(args.timeframes, {"daily", "weekly"})
    args.setups = normalize_setup_mode(args.setups)
    args.output_dir = Path(args.output_dir)
    return args


def run_command(command: list[str], explanation: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    print(f"\n▶ {explanation}")
    print("   $ " + " ".join(command))
    result = subprocess.run(command, cwd=cwd, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}")
    return result


def refresh_us_universe(skip: bool, force: bool, refresh_ttl_hours: int = 24):
    """
    Refresh US symbol universe only if needed:
      - skip=True        → skip refresh entirely
      - force=True       → always refresh
      - otherwise        → refresh only if file missing or older than refresh_ttl_hours
    """
    if skip:
        print("   (US universe refresh skipped by --skip-us-refresh)")
        return

    if not FETCH_US_SCRIPT.exists():
        print("   ! fetch_us_stocks.py not found, skipping refresh")
        return

    # Check if we should refresh based on file age
    primary_file = DEFAULT_US_SYMBOLS if DEFAULT_US_SYMBOLS.exists() else DEFAULT_US_FALLBACK
    if not force and primary_file.exists():
        import time
        file_age_hours = (time.time() - primary_file.stat().st_mtime) / 3600
        if file_age_hours < refresh_ttl_hours:
            print(f"   (US universe is fresh: {primary_file.name} updated {file_age_hours:.1f}h ago, skipping refresh)")
            return

    try:
        run_command([sys.executable, str(FETCH_US_SCRIPT)], "Refreshing US symbol universe")
    except Exception as exc:
        print(f"   ! US universe refresh failed, continuing with existing files: {exc}")


def resolve_us_symbols(args: argparse.Namespace) -> Path:
    if args.us_symbols:
        path = Path(args.us_symbols) if Path(args.us_symbols).is_absolute() else (ROOT / args.us_symbols)
        if path.exists():
            return path
        raise FileNotFoundError(f"US symbols file not found: {path}")

    if DEFAULT_US_SYMBOLS.exists():
        return DEFAULT_US_SYMBOLS
    if DEFAULT_US_FALLBACK.exists():
        return DEFAULT_US_FALLBACK
    raise FileNotFoundError("No US symbols file found. Expected us_stock_tickers.csv or all_us_stocks.txt")


def resolve_india_symbols(args: argparse.Namespace) -> Path:
    if args.india_symbols:
        path = Path(args.india_symbols) if Path(args.india_symbols).is_absolute() else (ROOT / args.india_symbols)
        if path.exists():
            return path
        raise FileNotFoundError(f"Indian symbols file not found: {path}")

    if DEFAULT_INDIA_SYMBOLS.exists():
        return DEFAULT_INDIA_SYMBOLS
    raise FileNotFoundError("No Indian symbols file found. Expected indian_stock_tickers.csv")


def compile_java():
    java_files = sorted(str(path) for path in JAVA_SRC_DIR.glob("*.java"))
    if not java_files:
        raise FileNotFoundError("No Java files found under src/")
    run_command(["javac", *java_files], "Compiling Java sources")


def latest_scan_paths(output_dir: Path, market: str, timeframe: str, setups: str) -> dict[str, Path]:
    label = f"{market}_{timeframe}" if setups == "both" else f"{market}_{timeframe}_{setups}"
    return {
        "csv": output_dir / f"vcp_hits_{label}_LATEST.csv",
        "json": output_dir / f"vcp_hits_{label}_LATEST.json",
        "html": output_dir / f"vcp_hits_{label}_LATEST.html",
        "watchlistCsv": output_dir / f"watchlist_{label}_LATEST.csv",
        "watchlistJson": output_dir / f"watchlist_{label}_LATEST.json",
        "watchlistHtml": output_dir / f"watchlist_{label}_LATEST.html",
        "openTradesCsv": output_dir / f"open_trades_{label}_LATEST.csv",
        "openTradesJson": output_dir / f"open_trades_{label}_LATEST.json",
        "openTradesHtml": output_dir / f"open_trades_{label}_LATEST.html",
        "portfolioCsv": output_dir / f"portfolio_shortlist_{label}_LATEST.csv",
        "portfolioJson": output_dir / f"portfolio_shortlist_{label}_LATEST.json",
        "portfolioHtml": output_dir / f"portfolio_shortlist_{label}_LATEST.html",
        "rejectionsCsv": output_dir / f"rejections_{label}_LATEST.csv",
        "rejectionsJson": output_dir / f"rejections_{label}_LATEST.json",
        "manifestJson": output_dir / f"scan_manifest_{label}_LATEST.json",
        "bundleJson": output_dir / f"scan_bundle_{label}_LATEST.json",
    }


def load_hits_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text())
        return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0


def setup_split_counts(output_dir: Path, market: str, timeframe: str, setups: str) -> dict[str, int]:
    if setups not in {"both", "full"}:
        return {}
    out = {}
    for key in ("vcp", "range_expansion"):
        out[key] = load_hits_count(output_dir / f"vcp_hits_{market}_{timeframe}_{key}_LATEST.json")
    if setups == "full":
        out["mean_reversion"] = load_hits_count(output_dir / f"vcp_hits_{market}_{timeframe}_mean_reversion_LATEST.json")
    return out


def variation_breakdown_from_hits(path: Path) -> dict[str, dict[str, int]]:
    if not path.exists():
        return {"setup": {}, "window": {}, "rating": {}}
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, list):
            return {"setup": {}, "window": {}, "rating": {}}

        setup_counts: dict[str, int] = {}
        window_counts: dict[str, int] = {}
        rating_counts: dict[str, int] = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            setup = str(item.get("setup", item.get("setupType", "UNKNOWN"))).upper()
            window = str(item.get("window", "UNKNOWN")).upper()
            rating = str(item.get("rating", item.get("setupRating", "N/A"))).upper()
            setup_counts[setup] = setup_counts.get(setup, 0) + 1
            window_counts[window] = window_counts.get(window, 0) + 1
            rating_counts[rating] = rating_counts.get(rating, 0) + 1

        def _sorted(d: dict[str, int]) -> dict[str, int]:
            return dict(sorted(d.items(), key=lambda kv: (-kv[1], kv[0])))

        return {"setup": _sorted(setup_counts), "window": _sorted(window_counts), "rating": _sorted(rating_counts)}
    except Exception:
        return {"setup": {}, "window": {}, "rating": {}}


def top_counts_line(counts: dict[str, int], top_n: int = 3) -> str:
    if not counts:
        return "-"
    return ", ".join(f"{k}:{v}" for k, v in list(counts.items())[:top_n])


def run_market_timeframe_scan(args: argparse.Namespace, market: str, timeframe: str, symbols_file: Path) -> dict:
    lookback = args.daily_lookback if timeframe == "daily" else args.weekly_lookback
    command = [
        sys.executable,
        str(SCAN_SCRIPT),
        "--symbols", str(symbols_file),
        "--market-label", market,
        "--timeframe", timeframe,
        "--setups", args.setups,
        "--lookback", str(lookback),
        "--workers", str(args.workers),
        "--batch", str(args.batch),
        "--cache-dir", args.cache_dir,
        "--cache-ttl", str(args.cache_ttl),
        "--output-dir", str(args.output_dir),
    ]
    run_command(command, f"Running {market.upper()} {timeframe.upper()} breakout scan")
    latest = latest_scan_paths(args.output_dir, market, timeframe, args.setups)
    hits = load_hits_count(latest["json"])
    watchlist_hits = load_hits_count(latest["watchlistJson"])
    portfolio_hits = load_hits_count(latest["portfolioJson"])
    rejections = load_hits_count(latest["rejectionsJson"])
    return {
        "market": market,
        "timeframe": timeframe,
        "setups": args.setups,
        "symbols_file": str(symbols_file),
        "lookback": lookback,
        "hits": hits,
        "watchlistHits": watchlist_hits,
        "portfolioPicks": portfolio_hits,
        "rejections": rejections,
        "setupBreakdown": setup_split_counts(args.output_dir, market, timeframe, args.setups),
        "variationBreakdown": variation_breakdown_from_hits(latest["json"]),
        "files": {key: str(value) for key, value in latest.items()},
    }


def write_summary(output_dir: Path, results: list[dict]) -> tuple[Path, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    summary_dir = output_dir / f"system_run_{timestamp}"
    summary_dir.mkdir(parents=True, exist_ok=True)

    total_hits = sum(item["hits"] for item in results)

    lines = [
        "# Breakout System Run Summary",
        "",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- Scan groups: {len(results)}",
        f"- Total open-trade hits across all groups: {total_hits}",
        f"- Total watchlist candidates across all groups: {sum(item.get('watchlistHits', 0) for item in results)}",
        f"- Total portfolio picks across all groups: {sum(item.get('portfolioPicks', 0) for item in results)}",
        f"- Total rejections across all groups: {sum(item.get('rejections', 0) for item in results)}",
        "",
        "## Scan Results",
        "",
        "| Market | Timeframe | Setups | Open Trades | Watchlist | Portfolio Picks | Rejections | Symbols File | Latest CSV | Latest HTML |",
        "|---|---|---|---:|---:|---:|---:|---|---|---|",
    ]
    for item in results:
        lines.append(
            f"| {item['market']} | {item['timeframe']} | {item['setups']} | {item['hits']} | {item.get('watchlistHits', 0)} | {item.get('portfolioPicks', 0)} | {item.get('rejections', 0)} | `{item['symbols_file']}` | `{item['files']['csv']}` | `{item['files']['html']}` |"
        )
        variation = item.get("variationBreakdown", {})
        lines.append(f"  - Variations setup: {top_counts_line(variation.get('setup', {}), 3)}")
        lines.append(f"  - Variations window: {top_counts_line(variation.get('window', {}), 3)}")
        lines.append(f"  - Variations rating: {top_counts_line(variation.get('rating', {}), 3)}")

    lines.extend([
        "",
        "## Latest Files",
        "",
    ])
    for item in results:
        lines.append(f"### {item['market'].upper()} {item['timeframe'].upper()}")
        lines.append(f"- CSV: `{item['files']['csv']}`")
        lines.append(f"- JSON: `{item['files']['json']}`")
        lines.append(f"- HTML: `{item['files']['html']}`")
        lines.append(f"- Watchlist CSV: `{item['files']['watchlistCsv']}`")
        lines.append(f"- Watchlist HTML: `{item['files']['watchlistHtml']}`")
        lines.append(f"- Open Trades CSV: `{item['files']['openTradesCsv']}`")
        lines.append(f"- Open Trades HTML: `{item['files']['openTradesHtml']}`")
        lines.append(f"- Portfolio Picks CSV: `{item['files']['portfolioCsv']}`")
        lines.append(f"- Portfolio Picks HTML: `{item['files']['portfolioHtml']}`")
        lines.append(f"- Rejections CSV: `{item['files']['rejectionsCsv']}`")
        lines.append(f"- Scan Manifest: `{item['files']['manifestJson']}`")
        lines.append(f"- Structured Bundle: `{item['files']['bundleJson']}`")
        if item.get("setupBreakdown"):
            lines.append(f"- VCP hits: {item['setupBreakdown'].get('vcp', 0)}")
            lines.append(f"- Range expansion hits: {item['setupBreakdown'].get('range_expansion', 0)}")
            if "mean_reversion" in item["setupBreakdown"]:
                lines.append(f"- Mean reversion hits: {item['setupBreakdown'].get('mean_reversion', 0)}")
        variation = item.get("variationBreakdown", {})
        lines.append(f"- Top setup variations: {top_counts_line(variation.get('setup', {}), 3)}")
        lines.append(f"- Top window variations: {top_counts_line(variation.get('window', {}), 3)}")
        lines.append(f"- Top rating variations: {top_counts_line(variation.get('rating', {}), 3)}")
        lines.append("")

    summary_md = summary_dir / "summary.md"
    summary_md.write_text("\n".join(lines) + "\n")

    summary_json = summary_dir / "summary.json"
    summary_json.write_text(json.dumps({"generatedAt": datetime.now().isoformat(timespec="seconds"), "results": results}, indent=2))

    (output_dir / "system_latest_summary.md").write_text(summary_md.read_text())
    (output_dir / "system_latest_summary.json").write_text(summary_json.read_text())
    return summary_md, summary_json


def main():
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    refresh_us_universe(args.skip_us_refresh, args.force_us_refresh)
    if args.setups != "mean_reversion":
        compile_java()
    else:
        print("   (Java compilation skipped for --setups mean_reversion)")

    symbols_by_market = {}
    if "us" in args.markets:
        symbols_by_market["us"] = resolve_us_symbols(args)
    if "india" in args.markets:
        symbols_by_market["india"] = resolve_india_symbols(args)

    results = []
    total_groups = len(args.markets) * len(args.timeframes)
    done_groups = 0
    for market in args.markets:
        for timeframe in args.timeframes:
            result = run_market_timeframe_scan(args, market, timeframe, symbols_by_market[market])
            done_groups += 1
            variation = result.get("variationBreakdown", {})
            print(
                f"   Progress {done_groups}/{total_groups} | {market.upper()} {timeframe.upper()} open={result['hits']} watch={result.get('watchlistHits', 0)} "
                f"| setup[{top_counts_line(variation.get('setup', {}), 2)}] "
                f"window[{top_counts_line(variation.get('window', {}), 2)}]"
            )
            results.append(result)

    summary_md, summary_json = write_summary(args.output_dir, results)

    print("\n════════════════════════════════════════════════════════════════════════")
    print("VCP SYSTEM RUN COMPLETE")
    print("════════════════════════════════════════════════════════════════════════")
    for item in results:
        print(
            f"- {item['market'].upper()} {item['timeframe'].upper()} ({item['setups']}): "
            f"{item['hits']} open trades, {item.get('watchlistHits', 0)} watchlist, "
            f"{item.get('portfolioPicks', 0)} portfolio picks, {item.get('rejections', 0)} rejections"
        )
        if item.get("setupBreakdown"):
            print(f"  VCP  → {item['setupBreakdown'].get('vcp', 0)}")
            print(f"  REXP → {item['setupBreakdown'].get('range_expansion', 0)}")
            if "mean_reversion" in item["setupBreakdown"]:
                print(f"  MREV → {item['setupBreakdown'].get('mean_reversion', 0)}")
        variation = item.get("variationBreakdown", {})
        print(f"  VAR  → setup[{top_counts_line(variation.get('setup', {}), 2)}] window[{top_counts_line(variation.get('window', {}), 2)}]")
        print(f"  CSV  → {item['files']['csv']}")
        print(f"  HTML → {item['files']['html']}")
        print(f"  WATCH→ {item['files']['watchlistHtml']}")
    print(f"- Summary MD   → {summary_md}")
    print(f"- Summary JSON → {summary_json}")


if __name__ == "__main__":
    main()

