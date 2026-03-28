"""
performance_tracker.py
──────────────────────
Tracks live performance of A and A+ rated breakout setups detected by the
scanner over the last 14 calendar days (2 weeks).

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
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────

TRACKER_FILENAME = "performance_tracker.json"
MAX_TRACK_DAYS   = 14
QUALIFYING_RATINGS: set[str] = {"A", "A+"}

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


# ──────────────────────────────────────────────────────────────────────────────
# Cache helpers
# ──────────────────────────────────────────────────────────────────────────────

def _load_price_rows(symbol: str, cache_dir: Path) -> list[dict]:
    """Load all available OHLCV rows for symbol (longest cache first)."""
    for suffix in ["_3528", "_900", "_504", "_252", "_728", "_60"]:
        p = cache_dir / f"{symbol}{suffix}.csv"
        if not p.exists():
            continue
        rows: list[dict] = []
        try:
            with open(p, newline="") as fh:
                for row in csv.DictReader(fh):
                    try:
                        rows.append({
                            "date":   row.get("date", ""),
                            "open":   float(row.get("open") or 0),
                            "high":   float(row.get("high") or 0),
                            "low":    float(row.get("low") or 0),
                            "close":  float(row.get("close") or 0),
                            "volume": float(row.get("volume") or 0),
                        })
                    except Exception:
                        pass
        except Exception:
            pass
        if rows:
            return rows
    return []


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
    """Build {market_timeframe -> set of A/A+ symbols} from latest LATEST files."""
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


# ──────────────────────────────────────────────────────────────────────────────
# Ingest new A / A+ breakouts from latest scan output
# ──────────────────────────────────────────────────────────────────────────────

def ingest_new_breakouts(
    output_dir: Path,
    markets: list[str] | None = None,
    timeframes: list[str] | None = None,
    existing_ids: set[str] | None = None,
) -> list[dict]:
    """Return new TradeRecord dicts for A/A+ signals not yet in the tracker."""
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
                trade_id = _make_trade_id(symbol, market, timeframe, today)

                if trade_id in existing_ids:
                    continue

                entry = _f(row.get("entry") or row.get("close"))
                sl    = _f(row.get("sl"))
                t1    = _f(row.get("T1"))
                t2    = _f(row.get("T2"))
                t3    = _f(row.get("T3"))

                trade: dict = {
                    "id":             trade_id,
                    "symbol":         symbol,
                    "market":         market,
                    "timeframe":      timeframe,
                    "setup":          setup,
                    "rating":         rating,
                    "window":         str(row.get("window", "")),
                    "tradeDate":      today,
                    "scanTimestamp":  _now_iso(),
                    "scanFile":       scan_file,
                    # Original scan snapshot
                    "entry":          round(entry, 2) if entry else None,
                    "stopLoss":       round(sl, 2)    if sl    else None,
                    "target1":        round(t1, 2)    if t1    else None,
                    "target2":        round(t2, 2)    if t2    else None,
                    "target3":        round(t3, 2)    if t3    else None,
                    "pivot":          round(_f(row.get("pivot")), 2),
                    "score":          round(_f(row.get("score")), 2),
                    "closeAtScan":    round(_f(row.get("close")), 2),
                    # Regime at scan time
                    "regimeAtScan":      str(row.get("regimeState",  regime_at_scan)  or regime_at_scan),
                    "regimeScoreAtScan": round(_f(row.get("regimeScore", regime_score_at)), 2),
                    # RS at scan
                    "rs3mAtScan":     round(_f(row.get("rs3m")), 2),
                    "rs6mAtScan":     round(_f(row.get("rs6m")), 2),
                    # Fundamentals / triggers
                    "fundSummary":         str(row.get("fundSummary",      "") or ""),
                    "triggerSummary":      str(row.get("triggerSummary",   "") or ""),
                    "entryInstruction":    str(row.get("entryInstruction", "") or ""),
                    # Live performance (updated on first cache pass)
                    "currentPrice":  round(entry, 2) if entry else None,
                    "gainPct":       0.0,
                    "maxGain":       0.0,
                    "minGain":       0.0,
                    "daysHeld":      0,
                    "slHit":         False,
                    "target1Hit":    False,
                    "target2Hit":    False,
                    "target3Hit":    False,
                    "stillInScan":   True,
                    "status":        "OPEN",
                    "sparkline":     [],
                    "lastUpdated":   _now_iso(),
                }
                new_trades.append(trade)
                existing_ids.add(trade_id)

    return new_trades


# ──────────────────────────────────────────────────────────────────────────────
# Rotate expired trades to archive
# ──────────────────────────────────────────────────────────────────────────────

def rotate_expired_trades(data: dict, max_days: int = MAX_TRACK_DAYS) -> dict:
    """Move trades older than max_days to the archive list."""
    cutoff  = (date.today() - timedelta(days=max_days)).isoformat()
    active: list[dict] = []
    rotated: list[dict] = []

    for trade in data.get("trades", []):
        trade_date = trade.get("tradeDate", "")
        if trade_date and trade_date < cutoff:
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

    # 1. Ingest new breakouts
    new_trades = ingest_new_breakouts(
        output_dir   = output_dir,
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
    data = rotate_expired_trades(data)

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

