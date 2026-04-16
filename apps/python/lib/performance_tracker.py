"""
performance_tracker.py
──────────────────────
Tracks live performance of qualifying breakout setups detected by the
scanner over the recent scanner windows (about 1 month daily / ~7 weeks weekly).

On every scan run:
  1. New A / A+ setups from daily + weekly scans are logged (one record per
     symbol+market+timeframe+trade_date, deduplicated by trade ID).
  2. All tracked trades are updated with current price from cache CSVs:
       - current_price, gain_pct, max_gain, min_gain
       - sl_hit, t1_hit, t2_hit, t3_hit  (checked across all bars since entry)
       - still_in_scan  (does the symbol still appear in the latest LATEST.json?)
       - status  → OPEN / SL_HIT / T1_HIT / T2_HIT / T3_HIT / EXPIRED
  3. Trades older than MAX_TRACK_DAYS are marked EXPIRED and moved to an
     archive list inside the same JSON file (max 500 archived entries).

Tracker DB location: output/performance_tracker.json
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────

TRACKER_FILENAME = "performance_tracker.json"
MAX_TRACK_DAYS   = 31
DAILY_TRACK_SESSIONS = 20
WEEKLY_TRACK_SESSIONS = 7
QUALIFYING_RATINGS: set[str] = {"A", "A+", "B"}
ROOT = Path(__file__).resolve().parents[3]
BACKTEST_SCRIPT = ROOT / "apps" / "python" / "cli" / "run_backtest.py"

# ──────────────────────────────────────────────────────────────────────────────
# Numeric helper
# ──────────────────────────────────────────────────────────────────────────────

def _f(v: Any, d: float = 0.0) -> float:
    try:
        if v in (None, "", "N/A"):
            return d
        return float(str(v).strip().replace("%", "").replace(",", "").replace("x", ""))
    except Exception:
        return d


def _today() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _round_or_none(v: Any, digits: int = 2) -> float | None:
    n = _f(v, d=float("nan"))
    if n != n:
        return None
    return round(n, digits)


# ──────────────────────────────────────────────────────────────────────────────
# JSON helpers
# ──────────────────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> list | dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _parse_iso_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip())
    except Exception:
        return None


def _extract_trigger_block(summary: str, label: str) -> str:
    source = str(summary or "")
    if not source:
        return ""
    m = re.search(
        rf"(?:^|\|\s*){re.escape(label)}\s*:\s*(.*?)(?=\s*\|\s*[A-Za-z]+\s*:|$)",
        source,
        flags=re.IGNORECASE,
    )
    return m.group(1).strip() if m else ""


def _normalize_trade_record(trade: dict) -> dict:
    if not isinstance(trade, dict):
        return trade

    normalized = dict(trade)
    trigger_summary = str(normalized.get("triggerSummary", "") or "")
    normalized["fundSummary"] = str(normalized.get("fundSummary", "") or "")
    normalized["triggerSummary"] = trigger_summary
    normalized["entryInstruction"] = str(normalized.get("entryInstruction", "") or "")

    for field, label in {
        "triggerEarningsGrowth": "Earnings",
        "triggerDebtReduction": "Debt",
        "triggerMacroTailwind": "Macro",
        "triggerMarketTailwind": "Market",
    }.items():
        existing = str(normalized.get(field, "") or "").strip()
        normalized[field] = existing or _extract_trigger_block(trigger_summary, label)

    return normalized


def _session_window_for_timeframe(
    timeframe: str,
    daily_sessions: int = DAILY_TRACK_SESSIONS,
    weekly_sessions: int = WEEKLY_TRACK_SESSIONS,
) -> int:
    tf = str(timeframe or "daily").strip().lower()
    if tf == "weekly":
        return max(1, weekly_sessions)
    return max(1, daily_sessions)


def _recent_session_dates(rows: list[dict], session_count: int) -> set[str]:
    valid_dates = sorted({
        str(row.get("entryDate", "")).strip()
        for row in rows
        if _parse_iso_date(row.get("entryDate")) is not None
    })
    if not valid_dates:
        return set()
    return set(valid_dates[-max(1, session_count):])


# ──────────────────────────────────────────────────────────────────────────────
# Store load / save
# ──────────────────────────────────────────────────────────────────────────────

def load_tracker(output_dir: Path) -> dict:
    """Load the tracker JSON or return a fresh empty store."""
    path = output_dir / TRACKER_FILENAME
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "trades" in data:
                data["trades"] = [
                    _normalize_trade_record(t)
                    for t in data.get("trades", [])
                    if isinstance(t, dict)
                ]
                data["archived"] = [
                    _normalize_trade_record(t)
                    for t in data.get("archived", [])
                    if isinstance(t, dict)
                ]
                return data
        except Exception:
            pass
    return {"version": 1, "lastUpdated": _now_iso(), "trades": [], "archived": []}


def save_tracker(output_dir: Path, data: dict) -> None:
    data["lastUpdated"] = _now_iso()
    path = output_dir / TRACKER_FILENAME
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# Trade ID
# ──────────────────────────────────────────────────────────────────────────────

def _make_trade_id(symbol: str, market: str, timeframe: str, trade_date: str) -> str:
    return f"{symbol}|{market}|{timeframe}|{trade_date}"


def _build_trade_record(
    *,
    symbol: str,
    market: str,
    timeframe: str,
    setup: str,
    rating: str,
    window: str,
    trade_date: str,
    scan_timestamp: str,
    scan_file: str,
    entry: Any,
    stop_loss: Any,
    target1: Any,
    target2: Any,
    target3: Any,
    pivot: Any = 0.0,
    score: Any = 0.0,
    close_at_scan: Any = None,
    regime_at_scan: str = "",
    regime_score_at_scan: Any = 0.0,
    rs3m_at_scan: Any = 0.0,
    rs6m_at_scan: Any = 0.0,
    fund_summary: str = "",
    trigger_summary: str = "",
    trigger_earnings_growth: str = "",
    trigger_debt_reduction: str = "",
    trigger_macro_tailwind: str = "",
    trigger_market_tailwind: str = "",
    entry_instruction: str = "",
    still_in_scan: bool = True,
) -> dict:
    trade_id = _make_trade_id(symbol, market, timeframe, trade_date)
    entry_value = _round_or_none(entry)
    return {
        "id":             trade_id,
        "symbol":         symbol,
        "market":         market,
        "timeframe":      timeframe,
        "setup":          str(setup or "").upper(),
        "rating":         str(rating or "").upper().strip(),
        "window":         str(window or ""),
        "tradeDate":      trade_date,
        "scanTimestamp":  scan_timestamp,
        "scanFile":       scan_file,
        "entry":          entry_value,
        "stopLoss":       _round_or_none(stop_loss),
        "target1":        _round_or_none(target1),
        "target2":        _round_or_none(target2),
        "target3":        _round_or_none(target3),
        "pivot":          round(_f(pivot), 2),
        "score":          round(_f(score), 2),
        "closeAtScan":    _round_or_none(close_at_scan if close_at_scan is not None else entry),
        "regimeAtScan":      str(regime_at_scan or ""),
        "regimeScoreAtScan": round(_f(regime_score_at_scan), 2),
        "rs3mAtScan":     round(_f(rs3m_at_scan), 2),
        "rs6mAtScan":     round(_f(rs6m_at_scan), 2),
        "fundSummary":         str(fund_summary or ""),
        "triggerSummary":      str(trigger_summary or ""),
        "triggerEarningsGrowth": str(trigger_earnings_growth or _extract_trigger_block(trigger_summary, "Earnings")),
        "triggerDebtReduction":  str(trigger_debt_reduction or _extract_trigger_block(trigger_summary, "Debt")),
        "triggerMacroTailwind":  str(trigger_macro_tailwind or _extract_trigger_block(trigger_summary, "Macro")),
        "triggerMarketTailwind": str(trigger_market_tailwind or _extract_trigger_block(trigger_summary, "Market")),
        "entryInstruction":    str(entry_instruction or ""),
        "currentPrice":  entry_value,
        "gainPct":       0.0,
        "maxGain":       0.0,
        "minGain":       0.0,
        "daysHeld":      0,
        "slHit":         False,
        "target1Hit":    False,
        "target2Hit":    False,
        "target3Hit":    False,
        "stillInScan":   still_in_scan,
        "status":        "OPEN",
        "sparkline":     [],
        "lastUpdated":   _now_iso(),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Cache helpers
# ──────────────────────────────────────────────────────────────────────────────

def _load_price_rows(symbol: str, cache_dir: Path) -> list[dict]:
    """Load all available OHLCV rows for symbol. Prefers unified file, legacy fallback."""
    def _try_read(p: Path) -> list[dict]:
        if not p.exists():
            return []
        rows: list[dict] = []
        try:
            with open(p, newline="") as fh:
                for row in csv.DictReader(fh):
                    try:
                        cl = float(row.get("close", 0) or 0)
                        if cl <= 0:
                            continue
                        rows.append({
                            "date": row.get("date", "").strip(),
                            "open": float(row.get("open", 0) or 0),
                            "high": float(row.get("high", 0) or 0),
                            "low": float(row.get("low", 0) or 0),
                            "close": cl,
                            "volume": float(row.get("volume", 0) or 0),
                        })
                    except Exception:
                        continue
        except Exception:
            return []
        return rows

    # 1) Try unified file
    for name in [f"{symbol}.csv", f"{symbol}.NS.csv"]:
        rows = _try_read(cache_dir / name)
        if rows:
            return rows

    # 2) Legacy fallback (first found with data)
    for suffix in ["_3528", "_900", "_504", "_252", "_728", "_60"]:
        rows = _try_read(cache_dir / f"{symbol}{suffix}.csv")
        if rows:
            return rows

    return []


def _latest_price_date(symbol: str, cache_dir: Path) -> str | None:
    rows = _load_price_rows(symbol, cache_dir)
    if not rows:
        return None
    last_date = str(rows[-1].get("date", "")).strip()
    return last_date or None


def _rows_since(rows: list[dict], since_date: str) -> list[dict]:
    return [r for r in rows if r["date"] >= since_date]


def _last_n_closes(rows: list[dict], n: int = 60) -> list[float]:
    return [r["close"] for r in rows[-n:] if r["close"] > 0]


# ──────────────────────────────────────────────────────────────────────────────
# Update a single trade from cache
# ──────────────────────────────────────────────────────────────────────────────

def update_trade_performance(trade: dict, cache_dir: Path) -> dict:
    """Refresh a trade's performance fields using latest cache data."""
    symbol     = trade["symbol"]
    entry      = _f(trade.get("entry"))
    sl         = _f(trade.get("stopLoss"))
    t1         = _f(trade.get("target1"))
    t2         = _f(trade.get("target2"))
    t3         = _f(trade.get("target3"))
    trade_date = trade.get("tradeDate", _today())

    all_rows   = _load_price_rows(symbol, cache_dir)
    since_rows = _rows_since(all_rows, trade_date)

    if not since_rows and all_rows:
        last_market_date = str(all_rows[-1].get("date", "")).strip()
        if last_market_date and str(trade_date) > last_market_date:
            trade_date = last_market_date
            trade["tradeDate"] = last_market_date
            since_rows = _rows_since(all_rows, trade_date)

    if not since_rows:
        trade["lastUpdated"] = _now_iso()
        return trade

    current_row   = since_rows[-1]
    current_price = current_row["close"] or current_row["open"]
    all_highs     = [r["high"] for r in since_rows if r["high"] > 0]
    all_lows      = [r["low"]  for r in since_rows if r["low"]  > 0]
    period_high   = max(all_highs) if all_highs else current_price
    period_low    = min(all_lows)  if all_lows  else current_price

    def _pct(curr: float) -> float:
        return ((curr - entry) / entry * 100.0) if entry > 0 else 0.0

    gain_pct  = round(_pct(current_price), 2)
    max_gain  = round(_pct(period_high),   2)
    min_gain  = round(_pct(period_low),    2)

    sl_hit = bool(sl  > 0 and period_low  <= sl)
    t1_hit = bool(t1  > 0 and period_high >= t1)
    t2_hit = bool(t2  > 0 and period_high >= t2)
    t3_hit = bool(t3  > 0 and period_high >= t3)

    try:
        td        = date.fromisoformat(trade_date)
        days_held = (date.today() - td).days
    except Exception:
        days_held = 0

    # Sparkline: last 60 daily closes (or all since trade date)
    sparkline = _last_n_closes(since_rows)

    trade["currentPrice"]  = round(current_price, 2)
    trade["gainPct"]       = gain_pct
    trade["maxGain"]       = max_gain
    trade["minGain"]       = min_gain
    trade["daysHeld"]      = days_held
    trade["slHit"]         = sl_hit
    trade["target1Hit"]    = t1_hit
    trade["target2Hit"]    = t2_hit
    trade["target3Hit"]    = t3_hit
    trade["sparkline"]     = sparkline[-60:]    # keep compact

    if sl_hit:
        trade["status"] = "SL_HIT"
    elif t3_hit:
        trade["status"] = "T3_HIT"
    elif t2_hit:
        trade["status"] = "T2_HIT"
    elif t1_hit:
        trade["status"] = "T1_HIT"
    else:
        trade["status"] = "OPEN"

    trade["lastUpdated"] = _now_iso()
    return trade


# ──────────────────────────────────────────────────────────────────────────────
# Check if still in latest scan
# ──────────────────────────────────────────────────────────────────────────────

def _build_scan_symbol_sets(output_dir: Path) -> dict[str, set[str]]:
    """Build {market_timeframe -> set of qualifying-rating symbols} from latest LATEST files."""
    result: dict[str, set[str]] = {}
    for market in ["india", "us"]:
        for timeframe in ["daily", "weekly"]:
            key       = f"{market}_{timeframe}"
            symbols: set[str] = set()
            for fname in [
                f"vcp_hits_{market}_{timeframe}_full_LATEST.json",
                f"vcp_hits_{market}_{timeframe}_LATEST.json",
            ]:
                data = _load_json(output_dir / fname)
                if isinstance(data, list):
                    for row in data:
                        if str(row.get("rating", "")).upper().strip() in QUALIFYING_RATINGS:
                            symbols.add(str(row.get("symbol", "")).upper())
                    if symbols:
                        break
            result[key] = symbols
    return result


def check_still_in_scan(trades: list[dict], output_dir: Path) -> None:
    """Mutate trades in-place, updating stillInScan flag."""
    scan_sets = _build_scan_symbol_sets(output_dir)
    for trade in trades:
        key     = f"{trade.get('market', 'india')}_{trade.get('timeframe', 'daily')}"
        symbols = scan_sets.get(key, set())
        trade["stillInScan"] = trade["symbol"].upper() in symbols


def _run_backtest_for_group(
    output_dir: Path,
    cache_dir: Path,
    market: str,
    timeframe: str,
    workers: int,
    batch: int,
    setups: str,
) -> Path | None:
    if not BACKTEST_SCRIPT.exists():
        return None
    command = [
        sys.executable,
        str(BACKTEST_SCRIPT),
        "--market", market,
        "--timeframe", timeframe,
        "--setups", setups,
        "--cache-dir", str(cache_dir),
        "--output-dir", str(output_dir),
        "--workers", str(max(1, workers)),
        "--batch", str(max(1, batch)),
        "--walk-forward-folds", "0",
        "--monte-carlo-iterations", "0",
    ]
    result = subprocess.run(command, cwd=ROOT, text=True)
    if result.returncode != 0:
        return None
    latest_csv = output_dir / f"backtest_{market}_{timeframe}_LATEST.csv"
    return latest_csv if latest_csv.exists() else None


def _ingest_backtest_csv(
    csv_path: Path,
    market: str,
    timeframe: str,
    existing_ids: set[str],
    daily_sessions: int,
    weekly_sessions: int,
) -> list[dict]:
    new_trades: list[dict] = []
    if not csv_path.exists():
        return new_trades

    try:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    except Exception:
        return new_trades

    session_count = _session_window_for_timeframe(
        timeframe,
        daily_sessions=daily_sessions,
        weekly_sessions=weekly_sessions,
    )
    rows_for_rating = [
        row for row in rows
        if str(row.get("setupRating", "")).upper().strip() in QUALIFYING_RATINGS
    ]
    keep_dates = _recent_session_dates(rows_for_rating, session_count)
    if not keep_dates:
        return new_trades

    for row in rows:
        rating = str(row.get("setupRating", "")).upper().strip()
        if rating not in QUALIFYING_RATINGS:
            continue

        trade_date = str(row.get("entryDate", "")).strip()
        trade_day = _parse_iso_date(trade_date)
        if trade_day is None or trade_date not in keep_dates or trade_day > date.today():
            continue

        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            continue

        trade_id = _make_trade_id(symbol, market, timeframe, trade_date)
        if trade_id in existing_ids:
            continue

        entry = _f(row.get("entryPrice"))
        stop = _f(row.get("stopPrice"))
        risk = max(0.0, entry - stop)
        rr1 = _f(row.get("rewardToRiskT1"), 1.0)
        target1 = entry + (risk * rr1) if entry > 0 and risk > 0 else None
        target2 = entry + (risk * 2.0) if entry > 0 and risk > 0 else None
        target3 = entry + (risk * 3.0) if entry > 0 and risk > 0 else None

        new_trades.append(_build_trade_record(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            setup=str(row.get("setupType", "")),
            rating=rating,
            window=str(row.get("windowLabel", "")),
            trade_date=trade_date,
            scan_timestamp=_now_iso(),
            scan_file=csv_path.name,
            entry=entry,
            stop_loss=stop,
            target1=target1,
            target2=target2,
            target3=target3,
            pivot=row.get("pivotPrice"),
            score=row.get("qualityScore"),
            close_at_scan=entry,
            regime_at_scan=str(row.get("entryMarketRegime", "")),
            regime_score_at_scan=row.get("marketStrengthScore"),
            rs3m_at_scan=row.get("relativeStrengthScore"),
            rs6m_at_scan=0.0,
            fund_summary="",
            trigger_summary=str(row.get("macroTrigger", "")),
            entry_instruction=str(row.get("entryInstruction", "")),
            still_in_scan=False,
        ))
        existing_ids.add(trade_id)

    return new_trades


def backfill_recent_breakouts_from_backtest(
    data: dict,
    output_dir: Path,
    cache_dir: Path,
    markets: list[str] | None = None,
    timeframes: list[str] | None = None,
    daily_sessions: int = DAILY_TRACK_SESSIONS,
    weekly_sessions: int = WEEKLY_TRACK_SESSIONS,
    workers: int = 4,
    batch: int = 20,
    setups: str = "both",
) -> dict:
    if daily_sessions <= 0 and weekly_sessions <= 0:
        return data

    markets = markets or ["india"]
    timeframes = timeframes or ["daily", "weekly"]
    existing_ids = {t["id"] for t in data.get("trades", []) if "id" in t}
    appended: list[dict] = []

    for market in markets:
        for timeframe in timeframes:
            if timeframe == "daily" and daily_sessions <= 0:
                continue
            if timeframe == "weekly" and weekly_sessions <= 0:
                continue
            csv_path = _run_backtest_for_group(output_dir, cache_dir, market, timeframe, workers, batch, setups)
            if not csv_path:
                continue
            appended.extend(
                _ingest_backtest_csv(
                    csv_path,
                    market,
                    timeframe,
                    existing_ids,
                    daily_sessions,
                    weekly_sessions,
                )
            )

    if appended:
        data.setdefault("trades", []).extend(appended)
    return data


# ──────────────────────────────────────────────────────────────────────────────
# Ingest new qualifying breakouts from latest scan output
# ──────────────────────────────────────────────────────────────────────────────

def ingest_new_breakouts(
    output_dir: Path,
    cache_dir: Path,
    markets: list[str] | None = None,
    timeframes: list[str] | None = None,
    existing_ids: set[str] | None = None,
) -> list[dict]:
    """Return new TradeRecord dicts for qualifying signals not yet in the tracker."""
    markets       = markets    or ["india"]
    timeframes    = timeframes or ["daily", "weekly"]
    existing_ids  = existing_ids or set()
    today         = _today()
    new_trades: list[dict] = []

    for market in markets:
        for timeframe in timeframes:
            rows: list[dict] | None = None
            scan_file: str = ""
            for fname in [
                f"vcp_hits_{market}_{timeframe}_full_LATEST.json",
                f"vcp_hits_{market}_{timeframe}_LATEST.json",
            ]:
                data = _load_json(output_dir / fname)
                if isinstance(data, list) and data:
                    rows      = data
                    scan_file = fname
                    break

            if not rows:
                continue

            # Also try to get the regime snapshot from bundle
            regime_at_scan  = ""
            regime_score_at = 0.0
            bundle = _load_json(output_dir / f"scan_bundle_{market}_{timeframe}_full_LATEST.json")
            if isinstance(bundle, dict):
                regime_at_scan  = str(bundle.get("regimeState",  bundle.get("marketRegimeState", "")) or "")
                regime_score_at = _f(bundle.get("regimeScore", bundle.get("marketRegimeScore", 0)))

            for row in rows:
                rating = str(row.get("rating", "")).upper().strip()
                if rating not in QUALIFYING_RATINGS:
                    continue

                symbol   = str(row.get("symbol", ""))
                setup    = str(row.get("setup", "")).upper()
                trade_date = _latest_price_date(symbol, cache_dir) or today
                trade_id = _make_trade_id(symbol, market, timeframe, trade_date)

                if trade_id in existing_ids:
                    continue

                entry = _f(row.get("entry") or row.get("close"))
                sl    = _f(row.get("sl"))
                t1    = _f(row.get("T1"))
                t2    = _f(row.get("T2"))
                t3    = _f(row.get("T3"))
                trade: dict = _build_trade_record(
                    symbol=symbol,
                    market=market,
                    timeframe=timeframe,
                    setup=setup,
                    rating=rating,
                    window=str(row.get("window", "")),
                    trade_date=trade_date,
                    scan_timestamp=_now_iso(),
                    scan_file=scan_file,
                    entry=entry,
                    stop_loss=sl,
                    target1=t1,
                    target2=t2,
                    target3=t3,
                    pivot=row.get("pivot"),
                    score=row.get("score"),
                    close_at_scan=row.get("close"),
                    regime_at_scan=str(row.get("regimeState", regime_at_scan) or regime_at_scan),
                    regime_score_at_scan=row.get("regimeScore", regime_score_at),
                    rs3m_at_scan=row.get("rs3m"),
                    rs6m_at_scan=row.get("rs6m"),
                    fund_summary=str(row.get("fundSummary", "") or ""),
                    trigger_summary=str(row.get("triggerSummary", "") or ""),
                    trigger_earnings_growth=str(row.get("triggerEarningsGrowth", "") or ""),
                    trigger_debt_reduction=str(row.get("triggerDebtReduction", "") or ""),
                    trigger_macro_tailwind=str(row.get("triggerMacroTailwind", "") or ""),
                    trigger_market_tailwind=str(row.get("triggerMarketTailwind", "") or ""),
                    entry_instruction=str(row.get("entryInstruction", "") or ""),
                    still_in_scan=True,
                )
                new_trades.append(trade)
                existing_ids.add(trade_id)

    return new_trades


# ──────────────────────────────────────────────────────────────────────────────
# Rotate expired trades to archive
# ──────────────────────────────────────────────────────────────────────────────

def rotate_expired_trades(
    data: dict,
    max_days: int = MAX_TRACK_DAYS,
    daily_sessions: int = DAILY_TRACK_SESSIONS,
    weekly_sessions: int = WEEKLY_TRACK_SESSIONS,
) -> dict:
    """Move trades outside configured recent session windows to archive."""
    # Fallback calendar cutoff kept for malformed dates with missing timeframe context.
    cutoff = (date.today() - timedelta(days=max_days)).isoformat()
    group_dates: dict[tuple[str, str], list[str]] = {}
    for trade in data.get("trades", []):
        td = str(trade.get("tradeDate", "")).strip()
        if _parse_iso_date(td) is None:
            continue
        key = (str(trade.get("market", "india")), str(trade.get("timeframe", "daily")))
        group_dates.setdefault(key, []).append(td)

    keep_dates_by_group: dict[tuple[str, str], set[str]] = {}
    for key, values in group_dates.items():
        unique_dates = sorted(set(values))
        keep_n = _session_window_for_timeframe(
            key[1],
            daily_sessions=daily_sessions,
            weekly_sessions=weekly_sessions,
        )
        keep_dates_by_group[key] = set(unique_dates[-keep_n:])

    active: list[dict] = []
    rotated: list[dict] = []

    for trade in data.get("trades", []):
        trade_date = str(trade.get("tradeDate", "")).strip()
        key = (str(trade.get("market", "india")), str(trade.get("timeframe", "daily")))
        keep_dates = keep_dates_by_group.get(key, set())
        should_rotate = False
        if keep_dates and trade_date:
            should_rotate = trade_date not in keep_dates
        elif trade_date and trade_date < cutoff:
            should_rotate = True

        if should_rotate:
            if trade.get("status") == "OPEN":
                trade["status"] = "EXPIRED"
            rotated.append(trade)
        else:
            active.append(trade)

    data["trades"] = active
    archived = data.get("archived", [])
    archived.extend(rotated)
    data["archived"] = archived[-500:]     # cap at 500 to keep file small
    return data


# ──────────────────────────────────────────────────────────────────────────────
# Full update cycle
# ──────────────────────────────────────────────────────────────────────────────

def run_performance_update(
    output_dir: Path,
    cache_dir: Path,
    markets: list[str] | None = None,
    timeframes: list[str] | None = None,
    daily_backfill_sessions: int = DAILY_TRACK_SESSIONS,
    weekly_backfill_sessions: int = WEEKLY_TRACK_SESSIONS,
    backtest_workers: int = 4,
    backtest_batch: int = 20,
    backtest_setups: str = "both",
) -> dict:
    """
    Full performance tracking cycle.  Returns the updated tracker data dict.

    Steps:
      1. Load tracker store
      2. Ingest new A/A+ breakouts from latest scan output
      3. Update every active trade from cache
      4. Refresh 'stillInScan' flags
      5. Rotate expired trades
      6. Save and return updated store
    """
    data          = load_tracker(output_dir)
    existing_ids  = {t["id"] for t in data.get("trades", [])}

    # 0. Backfill recent historical breakouts when requested
    if daily_backfill_sessions > 0 or weekly_backfill_sessions > 0:
        data = backfill_recent_breakouts_from_backtest(
            data=data,
            output_dir=output_dir,
            cache_dir=cache_dir,
            markets=markets,
            timeframes=timeframes,
            daily_sessions=daily_backfill_sessions,
            weekly_sessions=weekly_backfill_sessions,
            workers=backtest_workers,
            batch=backtest_batch,
            setups=backtest_setups,
        )
        existing_ids = {t["id"] for t in data.get("trades", [])}

    # 1. Ingest new breakouts
    new_trades = ingest_new_breakouts(
        output_dir   = output_dir,
        cache_dir    = cache_dir,
        markets      = markets,
        timeframes   = timeframes,
        existing_ids = existing_ids,
    )
    data["trades"].extend(new_trades)

    # 2. Update performance for all active trades
    updated: list[dict] = []
    for trade in data["trades"]:
        try:
            updated.append(update_trade_performance(trade, cache_dir))
        except Exception as exc:
            trade["lastUpdated"] = _now_iso()
            trade["_updateError"] = str(exc)
            updated.append(trade)
    data["trades"] = updated

    # 3. Refresh stillInScan
    try:
        check_still_in_scan(data["trades"], output_dir)
    except Exception:
        pass

    # 4. Rotate expired
    data = rotate_expired_trades(
        data,
        daily_sessions=daily_backfill_sessions,
        weekly_sessions=weekly_backfill_sessions,
    )

    # 5. Save
    save_tracker(output_dir, data)

    return data


# ──────────────────────────────────────────────────────────────────────────────
# Summary stats helper (used by API + HTML generator)
# ──────────────────────────────────────────────────────────────────────────────

def compute_summary_stats(trades: list[dict]) -> dict:
    """Compute aggregate stats for a list of trade records."""
    total       = len(trades)
    open_trades = [t for t in trades if t.get("status") == "OPEN"]
    sl_hits     = [t for t in trades if t.get("status") == "SL_HIT"]
    t1_hits     = [t for t in trades if t.get("status") in ("T1_HIT", "T2_HIT", "T3_HIT")]
    in_scan     = [t for t in trades if t.get("stillInScan")]

    gains       = [_f(t.get("gainPct")) for t in trades]
    avg_gain    = round(sum(gains) / len(gains), 2) if gains else 0.0
    winners     = [g for g in gains if g > 0]
    win_rate    = round(len(winners) / len(gains) * 100, 1) if gains else 0.0

    max_gain_trade = max(trades, key=lambda t: _f(t.get("maxGain", 0)), default=None)
    min_gain_trade = min(trades, key=lambda t: _f(t.get("minGain", 0)), default=None)

    return {
        "total":       total,
        "open":        len(open_trades),
        "slHits":      len(sl_hits),
        "targetHits":  len(t1_hits),
        "stillInScan": len(in_scan),
        "avgGainPct":  avg_gain,
        "winRate":     win_rate,
        "bestGain":    round(_f(max_gain_trade.get("maxGain", 0)), 2) if max_gain_trade else 0.0,
        "worstLoss":   round(_f(min_gain_trade.get("minGain", 0)), 2) if min_gain_trade else 0.0,
    }

