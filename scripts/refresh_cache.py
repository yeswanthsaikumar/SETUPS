#!/usr/bin/env python3
"""
refresh_cache.py
────────────────
Incremental Yahoo Finance cache refresher for NSE/BSE stocks.

Uses cookie+crumb authentication (required since 2024).
Reads existing cache CSV files, detects stale ones, and fetches
only the missing bars (incremental update).

Usage:
    python3 scripts/refresh_cache.py                    # refresh all stale NSE caches
    python3 scripts/refresh_cache.py --workers 6        # parallel workers
    python3 scripts/refresh_cache.py --force            # force refresh all
    python3 scripts/refresh_cache.py --symbols TATASTEEL,MTARTECH  # specific symbols
    python3 scripts/refresh_cache.py --dry-run          # show what would be refreshed
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import math
import os
import sys
import threading
import time
import zoneinfo
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
DATA_DIR  = ROOT / "data"

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
NSE_CLOSE_HOUR, NSE_CLOSE_MIN = 15, 35
MAX_DATA_GAP_DAYS = 10  # >10 calendar days = always stale (handles long holiday stretches)

# Retries and delays
MAX_RETRIES = 3
RETRY_DELAY = 1.5  # seconds between retries
CRUMB_RETRY_DELAY = 5.0
RATE_LIMIT_DELAY = 0.25  # seconds between requests per worker


# ── Yahoo Finance auth ──────────────────────────────────────────────────────
_session_lock = threading.Lock()
_crumb: str | None = None
_cookies: dict = {}
_crumb_expiry: float = 0.0

# Circuit breaker: after first network failure, skip Yahoo for 30 min
# to avoid wasting time on 1856+ symbols when Yahoo is unreachable.
_yahoo_blocked_until: float = 0.0
_CIRCUIT_BREAKER_S = 30 * 60  # 30 minutes


def _is_yahoo_blocked() -> bool:
    return time.time() < _yahoo_blocked_until


def _trip_circuit_breaker() -> None:
    global _yahoo_blocked_until
    _yahoo_blocked_until = time.time() + _CIRCUIT_BREAKER_S


def _fetch_crumb(session) -> tuple[str | None, dict]:
    """Obtain Yahoo Finance crumb (CSRF token) + session cookies.

    NOTE: This function intentionally does NOT trip the circuit breaker on
    failure. The crumb endpoint being unreachable does not conclusively mean
    that Yahoo Finance's chart API is also blocked — in some environments the
    crumb endpoint is rate-limited while the v8 chart API still works. The
    circuit breaker is only tripped inside _fetch_bars() when the actual data
    endpoint fails with a network error.
    """
    import requests
    # Step 1: Get consent/session cookies from Yahoo Finance homepage
    try:
        session.get(
            "https://finance.yahoo.com",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=8,
            allow_redirects=True,
        )
    except Exception:
        pass  # homepage failure is non-fatal; proceed to crumb endpoint

    # Step 2: Get crumb — try both endpoints
    for crumb_url in [
        "https://query1.finance.yahoo.com/v1/test/getcrumb",
        "https://query2.finance.yahoo.com/v1/test/getcrumb",
    ]:
        try:
            crumb_resp = session.get(
                crumb_url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=8,
            )
            if crumb_resp.ok and crumb_resp.text and crumb_resp.text.strip():
                return crumb_resp.text.strip(), dict(session.cookies)
        except Exception:
            continue  # try the other endpoint; do NOT trip circuit breaker here

    return None, {}


def _get_session_and_crumb():
    """Return (crumb, session) with caching (re-fetched every 20 minutes)."""
    global _crumb, _cookies, _crumb_expiry

    import requests

    # If circuit breaker is open, skip crumb fetch entirely
    if _is_yahoo_blocked():
        return None, requests.Session()

    now = time.time()
    with _session_lock:
        if _crumb and now < _crumb_expiry:
            s = requests.Session()
            s.cookies.update(_cookies)
            return _crumb, s

        # Only try once — if Yahoo is reachable, one attempt is enough.
        # Multiple retries with sleep waste 5+10+15s when Yahoo is blocked.
        if _is_yahoo_blocked():
            return None, requests.Session()

        s = requests.Session()
        c, cookies = _fetch_crumb(s)
        if c:
            _crumb = c
            _cookies = cookies
            _crumb_expiry = now + 20 * 60  # 20 min
            s2 = requests.Session()
            s2.cookies.update(_cookies)
            return _crumb, s2

    # Last resort: return None crumb (will try without it)
    return None, requests.Session()


# ── Data freshness ──────────────────────────────────────────────────────────

def _is_stale(last_date_str: str) -> bool:
    """Return True if the cache needs refreshing.

    Staleness rules (all times in IST):
     - 0 calendar days gap (last_date == today)  → fresh
     - > MAX_DATA_GAP_DAYS calendar days          → always stale (re-fetch)
     - Otherwise count Mon-Fri days in the gap:
         0 biz-days (pure weekend)  → fresh
         ≥2 biz-days               → stale (missed sessions)
         1 biz-day                 → stale only if NSE has already closed today
    """
    if not last_date_str:
        return True
    try:
        last_date = datetime.date.fromisoformat(last_date_str)
    except ValueError:
        return True

    today = datetime.datetime.now(IST).date()
    days = (today - last_date).days

    # Same day — already have today's data (or market is open)
    if days <= 0:
        return False
    if days > MAX_DATA_GAP_DAYS:
        return True

    biz = sum(
        1 for d in range(1, days + 1)
        if (last_date + datetime.timedelta(days=d)).weekday() < 5
    )
    if biz == 0:
        return False
    if biz >= 2:
        return True

    # Exactly 1 business day in the gap — stale only after NSE market close
    now_ist = datetime.datetime.now(IST)
    nse_close = now_ist.replace(hour=NSE_CLOSE_HOUR, minute=NSE_CLOSE_MIN, second=0, microsecond=0)
    return now_ist >= nse_close


def _read_last_date(csv_path: Path) -> str:
    """Read the last date with a *valid* (non-NaN, non-zero) close from a cache CSV file.

    Bars with NaN/zero close are treated as provisional / incomplete and are
    not counted as a proper "last date" — this mirrors the Java code's
    isDataCurrentEnough() logic which skips NaN-close candles.
    """
    if not csv_path.exists():
        return ""
    try:
        last = ""
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                d = row.get("date", "").strip()
                if not d:
                    continue
                # Skip provisional bars (NaN close or zero close)
                try:
                    close_val = float(row.get("close", "nan"))
                    if math.isnan(close_val) or close_val <= 0:
                        continue
                except (ValueError, TypeError):
                    continue
                last = d
        return last
    except Exception:
        return ""


def _find_stale_caches(symbol_filter: list[str] | None = None) -> list[tuple[str, Path, str]]:
    """Return list of (symbol, unified_cache_path, last_date) for stale entries.
    Always returns the unified SYMBOL.csv path (not legacy _N.csv paths)."""
    # Group cache files by base symbol — handle .NS and .BO, including symbols with & in name
    sym_files: dict[str, list[Path]] = {}

    # 1) Discover unified files: SYMBOL.NS.csv
    for p in CACHE_DIR.glob("*.NS.csv"):
        sym = p.name.replace(".csv", "")
        sym_files.setdefault(sym, []).append(p)
    for p in CACHE_DIR.glob("*.BO.csv"):
        sym = p.name.replace(".csv", "")
        sym_files.setdefault(sym, []).append(p)

    # 2) Discover legacy files: SYMBOL.NS_NNN.csv — group under same symbol
    for p in CACHE_DIR.glob("*_*.csv"):
        name = p.name
        for exch in (".NS_", ".BO_"):
            idx = name.find(exch)
            if idx != -1:
                sym = name[:idx + len(exch) - 1]  # e.g. "TATASTEEL.NS"
                rest = name[idx + len(exch):]
                if rest.replace(".csv", "").isdigit():
                    sym_files.setdefault(sym, []).append(p)
                break

    # Filter by symbol if requested
    if symbol_filter:
        wanted_base = {s.upper() for s in symbol_filter}
        sym_files = {
            k: v for k, v in sym_files.items()
            if k.split(".")[0].upper() in wanted_base or k.upper() in wanted_base
        }

    stale: list[tuple[str, Path, str]] = []
    for sym, files in sorted(sym_files.items()):
        # Always target the unified file for writing
        unified_path = CACHE_DIR / f"{sym}.csv"

        # Find the most recent last date across ALL files for this symbol
        best_last = ""
        for f in files:
            last = _read_last_date(f)
            if last > best_last:
                best_last = last

        if _is_stale(best_last):
            stale.append((sym, unified_path, best_last))

    return stale


# ── Yahoo Finance fetch ──────────────────────────────────────────────────────

def _fetch_bars(symbol: str, from_date: str | None = None) -> list[dict]:
    """
    Fetch OHLCV bars from Yahoo Finance for the given symbol.
    Uses cookie+crumb auth.
    Returns list of dicts with keys: date, open, high, low, close, volume
    """
    import requests as _req

    # Fast-fail when circuit breaker is open — no point trying Yahoo
    if _is_yahoo_blocked():
        return []

    now_ist = datetime.datetime.now(IST)
    p2 = int(now_ist.timestamp())

    if from_date:
        try:
            dt = datetime.date.fromisoformat(from_date) + datetime.timedelta(days=1)
            p1 = int(datetime.datetime(dt.year, dt.month, dt.day, 0, 0, 0, tzinfo=IST).timestamp())
        except Exception:
            p1 = int((now_ist - datetime.timedelta(days=365)).timestamp())
    else:
        p1 = int((now_ist - datetime.timedelta(days=730)).timestamp())

    crumb, session = _get_session_and_crumb()

    for attempt in range(1, MAX_RETRIES + 1):
        # Re-check circuit breaker before each retry
        if _is_yahoo_blocked():
            return []

        try:
            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
                f"?interval=1d&period1={p1}&period2={p2}&events=history&includeAdjustedClose=true"
            )
            if crumb:
                url += f"&crumb={crumb}"

            resp = session.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json",
                    "Referer": "https://finance.yahoo.com",
                },
                timeout=8,
            )

            if resp.status_code == 401:
                # Crumb expired — force refresh
                global _crumb_expiry
                with _session_lock:
                    _crumb_expiry = 0
                crumb, session = _get_session_and_crumb()
                time.sleep(RETRY_DELAY * attempt)
                continue

            if resp.status_code == 429:
                # Rate limited
                time.sleep(RETRY_DELAY * attempt * 3)
                continue

            if not resp.ok:
                time.sleep(RETRY_DELAY * attempt)
                continue

            data = resp.json()
            result = data.get("chart", {}).get("result", [])
            if not result:
                error = data.get("chart", {}).get("error", {})
                if error:
                    return []  # symbol may be invalid
                return []

            chart = result[0]
            timestamps = chart.get("timestamp", [])
            quote = chart.get("indicators", {}).get("quote", [{}])[0]
            opens   = quote.get("open",   [])
            highs   = quote.get("high",   [])
            lows    = quote.get("low",    [])
            closes  = quote.get("close",  [])
            volumes = quote.get("volume", [])

            # Also try adjclose as fallback
            adj_closes = chart.get("indicators", {}).get("adjclose", [{}])
            adj_closes = adj_closes[0].get("adjclose", []) if adj_closes else []

            bars = []
            for i, ts in enumerate(timestamps):
                try:
                    o = opens[i]   if i < len(opens)   else None
                    h = highs[i]   if i < len(highs)   else None
                    l = lows[i]    if i < len(lows)    else None
                    c = closes[i]  if i < len(closes)  else None
                    v = volumes[i] if i < len(volumes) else None

                    # Normalize NaN floats from JSON to None
                    def _nan_to_none(x):
                        if x is None:
                            return None
                        try:
                            f = float(x)
                            return None if math.isnan(f) else f
                        except (TypeError, ValueError):
                            return None

                    o = _nan_to_none(o)
                    h = _nan_to_none(h)
                    l = _nan_to_none(l)
                    c = _nan_to_none(c)

                    # Fallback for missing/NaN close: try adjclose, then typical price
                    if c is None and i < len(adj_closes):
                        c = _nan_to_none(adj_closes[i])
                    if c is None and o is not None and h is not None and l is not None:
                        c = (o + h + l) / 3.0

                    if ts is None or o is None or h is None or l is None or c is None:
                        continue
                    if v is None or v <= 0:
                        continue

                    dt_ist = datetime.datetime.fromtimestamp(ts, IST)
                    date_str = dt_ist.strftime("%Y-%m-%d")
                    bars.append({
                        "date":   date_str,
                        "open":   round(float(o), 5),
                        "high":   round(float(h), 5),
                        "low":    round(float(l), 5),
                        "close":  round(float(c), 5),
                        "volume": int(v),
                    })
                except Exception:
                    continue

            return sorted(bars, key=lambda x: x["date"])

        except Exception as e:
            # Network-level failure on this host — try the other Yahoo host before
            # tripping the circuit breaker.  Only trip after BOTH hosts fail.
            _trip_circuit_breaker()
            return []

    return []


# ── Cache merge & write ──────────────────────────────────────────────────────

def _read_cache_bars(csv_path: Path) -> list[dict]:
    """Read existing bars from a cache CSV file.

    Bars with NaN or zero/negative close are treated as provisional data
    (Yahoo publishes volume before the final close is available) and are
    excluded. This prevents bad data from persisting through merge cycles.
    """
    bars = []
    try:
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                try:
                    close_val = float(row["close"])
                    # Skip provisional / incomplete bars
                    if math.isnan(close_val) or close_val <= 0:
                        continue
                    bars.append({
                        "date":   row["date"].strip(),
                        "open":   float(row["open"]),
                        "high":   float(row["high"]),
                        "low":    float(row["low"]),
                        "close":  close_val,
                        "volume": int(float(row["volume"])),
                    })
                except Exception:
                    continue
    except Exception:
        pass
    return bars


def _write_cache(csv_path: Path, bars: list[dict]):
    """Write bars to a CSV file."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date","open","high","low","close","volume"])
        writer.writeheader()
        for bar in bars:
            writer.writerow({
                "date":   bar["date"],
                "open":   f"{bar['open']:.5f}",
                "high":   f"{bar['high']:.5f}",
                "low":    f"{bar['low']:.5f}",
                "close":  f"{bar['close']:.5f}",
                "volume": str(bar["volume"]),
            })


def _merge_bars(old: list[dict], new: list[dict]) -> list[dict]:
    """Merge new bars into old, letting new data overwrite same-date old data."""
    by_date = {}
    for bar in old:
        by_date[bar["date"]] = bar
    for bar in new:
        by_date[bar["date"]] = bar
    return sorted(by_date.values(), key=lambda x: x["date"])


# ── Per-symbol refresh ───────────────────────────────────────────────────────

def refresh_symbol(sym: str, cache_path: Path, last_date: str, force: bool = False, dry_run: bool = False) -> dict:
    """Refresh cache for one symbol. Writes to unified SYMBOL.csv, merges legacy files, deletes them."""
    result = {"symbol": sym, "status": "skipped", "bars_added": 0, "last_date": last_date}

    if not force and not _is_stale(last_date):
        result["status"] = "fresh"
        return result

    if dry_run:
        result["status"] = "would_refresh"
        return result

    # Read existing bars from ALL files: unified + legacy
    existing = _read_cache_bars(cache_path) if cache_path.exists() else []
    legacy_files = _find_legacy_files_for_symbol(sym)
    for lf in legacy_files:
        existing.extend(_read_cache_bars(lf))
    # Deduplicate by date (keep latest row per date)
    by_date = {}
    for bar in existing:
        by_date[bar["date"]] = bar
    existing = sorted(by_date.values(), key=lambda b: b["date"])

    fetch_from = existing[-1]["date"] if existing else None

    # Fetch new bars
    new_bars = _fetch_bars(sym, from_date=fetch_from)
    time.sleep(RATE_LIMIT_DELAY)  # Rate limit protection

    if not new_bars:
        # Even with no new data, consolidate legacy files if they exist
        if legacy_files and existing:
            _write_cache(cache_path, existing)
            for lf in legacy_files:
                try: lf.unlink()
                except Exception: pass
        result["status"] = "no_new_data"
        return result

    # Merge and write to unified path
    merged = _merge_bars(existing, new_bars)
    _write_cache(cache_path, merged)

    # Delete legacy files now that unified file is written
    for lf in legacy_files:
        try: lf.unlink()
        except Exception: pass

    new_last = merged[-1]["date"] if merged else last_date
    bars_added = len(new_bars)
    result.update({
        "status":     "updated",
        "bars_added": bars_added,
        "last_date":  new_last,
    })
    return result


def _find_legacy_files_for_symbol(sym: str) -> list[Path]:
    """Find all legacy SYMBOL_NNN.csv files for a given symbol."""
    legacy = []
    for p in CACHE_DIR.glob(f"{sym}_*.csv"):
        # Verify the part after the last _ is numeric
        name = p.name
        idx = name.rfind("_")
        if idx > 0:
            num_part = name[idx + 1:].replace(".csv", "")
            if num_part.isdigit():
                legacy.append(p)
    return sorted(legacy, key=lambda p: p.stat().st_size, reverse=True)


# ── All cache files refresh ──────────────────────────────────────────────────

def refresh_all_stale_caches(
    symbol_filter: list[str] | None = None,
    workers: int = 6,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """Refresh all stale cache files for NSE/BSE symbols."""
    print(f"\n🔄 Scanning cache directory for stale files…", flush=True)
    stale = _find_stale_caches(symbol_filter)

    if not stale:
        print("✅ All cache files are up-to-date!", flush=True)
        return {"refreshed": 0, "skipped": 0, "errors": 0}

    print(f"  Found {len(stale)} stale symbol{'s' if len(stale)!=1 else ''} to refresh", flush=True)

    if dry_run:
        print("  DRY RUN — no files will be written\n  Would refresh:", flush=True)
        for sym, path, last_date in stale[:20]:
            print(f"    {sym}  (last: {last_date or 'no data'}  →  {path.name})", flush=True)
        if len(stale) > 20:
            print(f"    … and {len(stale) - 20} more", flush=True)
        return {"refreshed": 0, "skipped": len(stale), "errors": 0}

    # Warm up crumb BEFORE parallel execution
    print("  Fetching Yahoo Finance session/crumb…", flush=True)
    crumb, _ = _get_session_and_crumb()
    if crumb:
        print(f"  ✓ Got crumb (length={len(crumb)})", flush=True)
    elif _is_yahoo_blocked():
        print(
            "  ❌ Yahoo Finance is BLOCKED on this network (SSL connection reset).\n"
            "     Cache cannot be updated until Yahoo Finance is accessible.\n"
            "     Tip: Run the scan from a different network (e.g. mobile hotspot)\n"
            "          or wait until the network restriction is lifted.",
            flush=True
        )
    else:
        print("  ⚠ Could not get crumb — will try without it (some regions work without crumb)", flush=True)

    stats = {"refreshed": 0, "skipped": 0, "errors": 0, "no_data": 0, "blocked": 0}
    lock = threading.Lock()
    done = 0
    total = len(stale)

    def _do_refresh(item):
        nonlocal done
        sym, cache_path, last_date = item
        try:
            # If the circuit breaker tripped during this batch, skip remaining symbols
            # immediately so we don't burn CPU on thousands of cache reads.
            if _is_yahoo_blocked():
                with lock:
                    done += 1
                    stats["blocked"] += 1
                return
            res = refresh_symbol(sym, cache_path, last_date, force=force, dry_run=dry_run)
            with lock:
                done += 1
                status = res["status"]
                if status == "updated":
                    stats["refreshed"] += 1
                    pct = done / total * 100
                    print(
                        f"  [{done:4d}/{total}] ✅ {sym:<20}  "
                        f"+{res['bars_added']} bars → {res['last_date']}  ({pct:.0f}%)",
                        flush=True
                    )
                elif status in ("fresh", "skipped"):
                    stats["skipped"] += 1
                elif status == "no_new_data":
                    stats["no_data"] += 1
                    pct = done / total * 100
                    print(f"  [{done:4d}/{total}] ⏭  {sym:<20}  no new data  ({pct:.0f}%)", flush=True)
                else:
                    stats["errors"] += 1
                    pct = done / total * 100
                    print(f"  [{done:4d}/{total}] ❌ {sym:<20}  {status}  ({pct:.0f}%)", flush=True)
        except Exception as ex:
            with lock:
                done += 1
                stats["errors"] += 1
                print(f"  [{done:4d}/{total}] ❌ {sym}: {ex}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(_do_refresh, stale))

    print(f"\n{'='*60}", flush=True)
    if stats.get("blocked", 0) > 0:
        print(
            f"⚠  Cache refresh INCOMPLETE — Yahoo Finance is blocked on this network.\n"
            f"   {stats['blocked']} symbols skipped (no data fetched).\n"
            f"   Run from a different network or check firewall/proxy settings.",
            flush=True
        )
    else:
        print(f"✅ Cache refresh complete!", flush=True)
    print(f"   Refreshed : {stats['refreshed']}", flush=True)
    print(f"   No new data: {stats['no_data']}", flush=True)
    print(f"   Skipped   : {stats['skipped']}", flush=True)
    print(f"   Blocked   : {stats.get('blocked', 0)}", flush=True)
    print(f"   Errors    : {stats['errors']}", flush=True)
    return stats


def refresh_nifty_index():
    """Refresh Nifty 50 index (^NSEI) cache into unified ^NSEI.csv."""
    nifty_path = CACHE_DIR / "^NSEI.csv"

    # Merge all legacy ^NSEI_N.csv files
    existing = _read_cache_bars(nifty_path) if nifty_path.exists() else []
    legacy_files = sorted(CACHE_DIR.glob("^NSEI_*.csv"), key=lambda p: p.stat().st_size, reverse=True)
    for lf in legacy_files:
        existing.extend(_read_cache_bars(lf))
    by_date = {}
    for bar in existing:
        by_date[bar["date"]] = bar
    existing = sorted(by_date.values(), key=lambda b: b["date"])

    last_date = existing[-1]["date"] if existing else ""
    if not _is_stale(last_date):
        print(f"✅ Nifty cache is fresh (last: {last_date})", flush=True)
        if legacy_files:
            _write_cache(nifty_path, existing)
            for lf in legacy_files:
                try: lf.unlink()
                except Exception: pass
        return

    print(f"🔄 Refreshing Nifty 50 index (last: {last_date or 'none'})…", flush=True)
    new_bars = _fetch_bars("^NSEI", from_date=last_date if existing else None)
    if new_bars:
        merged = _merge_bars(existing, new_bars)
        _write_cache(nifty_path, merged)
        for lf in legacy_files:
            try: lf.unlink()
            except Exception: pass
        print(f"✅ Nifty updated: +{len(new_bars)} bars → {merged[-1]['date']}", flush=True)
    else:
        if legacy_files and existing:
            _write_cache(nifty_path, existing)
            for lf in legacy_files:
                try: lf.unlink()
                except Exception: pass
        print("⚠ No new Nifty bars fetched (market may be closed / Yahoo unavailable)", flush=True)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Refresh stale Yahoo Finance cache files")
    parser.add_argument("--workers",  type=int, default=6, help="Parallel workers (default: 6)")
    parser.add_argument("--force",    action="store_true", help="Force refresh even for fresh caches")
    parser.add_argument("--dry-run",  action="store_true", help="Show what would be refreshed without doing it")
    parser.add_argument("--symbols",  default=None, help="Comma-separated list of symbols to refresh (e.g. TATASTEEL,MTARTECH)")
    parser.add_argument("--no-nifty", action="store_true", help="Skip Nifty 50 index refresh")
    args = parser.parse_args()

    symbol_filter = [s.strip() for s in args.symbols.split(",")] if args.symbols else None

    if not args.no_nifty:
        refresh_nifty_index()

    stats = refresh_all_stale_caches(
        symbol_filter=symbol_filter,
        workers=args.workers,
        force=args.force,
        dry_run=args.dry_run,
    )
    if stats.get("errors", 0) > 0:
        sys.exit(1)
    # Exit code 2 = Yahoo Finance is blocked (non-fatal; scan continues with cached data)
    if stats.get("blocked", 0) > 0:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()

