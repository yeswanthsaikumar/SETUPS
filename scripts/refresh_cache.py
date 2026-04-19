#!/usr/bin/env python3
"""
refresh_cache.py  –  Multi-source OHLCV cache refresher
───────────────────────────────────────────────────────
Sources (tried in order per symbol):
  1. yfinance library   (handles Yahoo session/crumb/rate-limits internally)
  2. NSE India API      (direct NSE endpoint – only for .NS stocks)
  3. Raw Yahoo v8 API   (clean session, no crumb – last resort)

Usage:
    python3 scripts/refresh_cache.py
    python3 scripts/refresh_cache.py --workers 4
    python3 scripts/refresh_cache.py --force
    python3 scripts/refresh_cache.py --symbols TATASTEEL,MTARTECH
    python3 scripts/refresh_cache.py --indian-only
    python3 scripts/refresh_cache.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import datetime
import math
import os
import sys
import threading
import time
import urllib.parse
import zoneinfo
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT      = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
DATA_DIR  = ROOT / "data"

# Ensure lib is on path for shared modules
_LIB_DIR = str(ROOT / "apps" / "python" / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
NSE_CLOSE_HOUR, NSE_CLOSE_MIN = 15, 35
MAX_DATA_GAP_DAYS = 10
MAX_RETRIES       = 3
RETRY_DELAY       = 2.0
RATE_LIMIT_DELAY  = 0.5

_throttle_lock = threading.Lock()
_last_req_time: float = 0.0
_MIN_GAP = 0.4


def _throttle():
    global _last_req_time
    with _throttle_lock:
        wait = _MIN_GAP - (time.time() - _last_req_time)
        if wait > 0:
            time.sleep(wait)
        _last_req_time = time.time()


# ═══════════════════════════════════════════════════════════════════════════
#  DATA FRESHNESS
# ═══════════════════════════════════════════════════════════════════════════

def _is_stale(last_date_str: str) -> bool:
    if not last_date_str:
        return True
    try:
        last_date = datetime.date.fromisoformat(last_date_str)
    except ValueError:
        return True
    today = datetime.datetime.now(IST).date()
    days = (today - last_date).days
    if days <= 0:
        return False
    if days > MAX_DATA_GAP_DAYS:
        return True
    biz = sum(1 for d in range(1, days + 1)
              if (last_date + datetime.timedelta(days=d)).weekday() < 5)
    if biz == 0:
        return False
    # Any business day gap means stale — fetch whatever Yahoo has available
    # (Yahoo returns the previous completed trading day's data during market hours)
    return True


def _read_last_date(csv_path: Path) -> str:
    if not csv_path.exists():
        return ""
    try:
        last = ""
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                d = row.get("date", "").strip()
                if not d:
                    continue
                try:
                    cv = float(row.get("close", "nan"))
                    if math.isnan(cv) or cv <= 0:
                        continue
                except (ValueError, TypeError):
                    continue
                last = d
        return last
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════════════════
#  DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════

def _find_stale_caches(symbol_filter=None, indian_only=False):
    sym_files: dict[str, list[Path]] = {}

    for p in CACHE_DIR.glob("*.NS.csv"):
        sym_files.setdefault(p.name.replace(".csv", ""), []).append(p)
    for p in CACHE_DIR.glob("*.BO.csv"):
        sym_files.setdefault(p.name.replace(".csv", ""), []).append(p)

    if not indian_only:
        for p in CACHE_DIR.glob("*.csv"):
            nm = p.name
            if ".NS.csv" in nm or ".BO.csv" in nm or "_" in nm:
                continue
            sym = nm.replace(".csv", "")
            if not sym or sym.startswith("."):
                continue
            sym_files.setdefault(sym, []).append(p)

    for p in CACHE_DIR.glob("*_*.csv"):
        nm = p.name
        for exch in (".NS_", ".BO_"):
            idx = nm.find(exch)
            if idx != -1:
                sym = nm[:idx + len(exch) - 1]
                rest = nm[idx + len(exch):]
                if rest.replace(".csv", "").isdigit():
                    sym_files.setdefault(sym, []).append(p)
                break

    if symbol_filter:
        wanted = {s.upper() for s in symbol_filter}
        sym_files = {k: v for k, v in sym_files.items()
                     if k.split(".")[0].upper() in wanted or k.upper() in wanted}

    stale = []
    for sym, files in sorted(sym_files.items()):
        unified = CACHE_DIR / f"{sym}.csv"
        best = ""
        for f in files:
            ld = _read_last_date(f)
            if ld > best:
                best = ld
        if _is_stale(best):
            stale.append((sym, unified, best))
    return stale


# ═══════════════════════════════════════════════════════════════════════════
#  MULTI-SOURCE FETCH  (yfinance -> NSE India -> raw Yahoo v8)
# ═══════════════════════════════════════════════════════════════════════════

def _fetch_bars(symbol: str, from_date: str | None = None) -> list[dict]:
    """Try every source in priority order: Groww → yfinance → NSE India → raw Yahoo v8.

    When GROWW_ONLY mode is on (default), Indian stocks (.NS/.BO) are
    fetched ONLY from Groww — no silent fallback to geo-blocked Yahoo/NSE
    that would either fail or require a dead free-proxy VPN.
    """
    # 0. Groww API (primary — most reliable for NSE stocks when configured)
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        bars = _fetch_groww(symbol, from_date)
        if bars:
            return bars

    # Groww-only gate: for Indian stocks, stop here if fallbacks are forbidden.
    try:
        import sys as _sys
        from pathlib import Path as _P
        _sys.path.insert(0, str(_P(__file__).resolve().parents[1] / "apps" / "python" / "lib"))
        from groww_client import should_use_non_groww_source
    except Exception:
        should_use_non_groww_source = lambda s: True  # fail-open if import breaks
    if not should_use_non_groww_source(symbol):
        return []

    # 1. yfinance (fallback)
    bars = _fetch_yfinance(symbol, from_date)
    if bars:
        return bars

    # 2. NSE India direct (only for .NS stocks)
    if symbol.endswith(".NS"):
        bars = _fetch_nse_india(symbol, from_date)
        if bars:
            return bars

    # 3. Raw Yahoo v8 (last resort)
    bars = _fetch_raw_yahoo(symbol, from_date)
    return bars


# ── Source 0: Groww API (primary for NSE stocks) ────────────────────────────

def _fetch_groww(symbol, from_date):
    """Fetch historical daily candles from Groww API."""
    try:
        from groww_client import get_groww_client
    except ImportError:
        return []
    client = get_groww_client()
    if not client:
        return []
    try:
        from growwapi import GrowwAPI
        base_sym = symbol.replace(".NS", "").replace(".BO", "")
        exchange = GrowwAPI.EXCHANGE_NSE

        if from_date:
            start_dt = (datetime.date.fromisoformat(from_date)
                        + datetime.timedelta(days=1))
        else:
            start_dt = datetime.date.today() - datetime.timedelta(days=730)
        end_dt = datetime.date.today()

        # Groww expects ISO datetime strings
        start_str = datetime.datetime(start_dt.year, start_dt.month, start_dt.day,
                                      tzinfo=IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")
        end_str = datetime.datetime(end_dt.year, end_dt.month, end_dt.day,
                                    hour=23, minute=59, tzinfo=IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")

        _throttle()
        # Try get_historical_candle_data first (uses trading_symbol directly)
        try:
            data = client.get_historical_candle_data(
                trading_symbol=base_sym,
                exchange=exchange,
                segment=GrowwAPI.SEGMENT_CASH,
                start_time=start_str,
                end_time=end_str,
                interval_in_minutes=None,  # daily
                timeout=15,
            )
        except Exception:
            # Fallback to get_historical_candles (uses groww_symbol)
            data = client.get_historical_candles(
                exchange=exchange,
                segment=GrowwAPI.SEGMENT_CASH,
                groww_symbol=base_sym,
                start_time=start_str,
                end_time=end_str,
                candle_interval=GrowwAPI.CANDLE_INTERVAL_DAY,
                timeout=15,
            )

        if not data:
            return []

        # Parse response - Groww returns candles as list of dicts or nested structure
        candles = []
        if isinstance(data, dict):
            candles = data.get("candles", data.get("data", []))
        elif isinstance(data, list):
            candles = data

        bars = []
        for c in candles:
            try:
                if isinstance(c, dict):
                    dt = c.get("date", c.get("timestamp", c.get("time", "")))
                    o = float(c.get("open", 0))
                    h = float(c.get("high", 0))
                    lo = float(c.get("low", 0))
                    cl = float(c.get("close", 0))
                    v = int(float(c.get("volume", 0)))
                elif isinstance(c, (list, tuple)) and len(c) >= 6:
                    # [timestamp, open, high, low, close, volume]
                    dt = c[0]
                    o, h, lo, cl, v = float(c[1]), float(c[2]), float(c[3]), float(c[4]), int(c[5])
                else:
                    continue

                if isinstance(dt, (int, float)):
                    dt = datetime.datetime.fromtimestamp(dt, IST).strftime("%Y-%m-%d")
                elif isinstance(dt, str) and len(dt) >= 10:
                    dt = dt[:10]
                else:
                    continue

                if o <= 0 or h <= 0 or lo <= 0 or cl <= 0 or v <= 0:
                    continue
                bars.append(dict(date=dt, open=round(o, 5), high=round(h, 5),
                                 low=round(lo, 5), close=round(cl, 5), volume=v))
            except Exception:
                continue

        return sorted(bars, key=lambda b: b["date"])
    except Exception:
        return []


# ── Source 1: yfinance ──────────────────────────────────────────────────────

def _fetch_yfinance(symbol, from_date):
    try:
        import yfinance as yf
    except ImportError:
        return []
    try:
        _throttle()
        if from_date:
            start = (datetime.date.fromisoformat(from_date)
                     + datetime.timedelta(days=1)).isoformat()
        else:
            start = (datetime.date.today()
                     - datetime.timedelta(days=730)).isoformat()
        end = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

        df = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=False)
        if df is None or df.empty:
            return []

        bars = []
        for idx, row in df.iterrows():
            try:
                ds = (idx.strftime("%Y-%m-%d")
                      if hasattr(idx, "strftime") else str(idx)[:10])
                o = float(row.get("Open", float("nan")))
                h = float(row.get("High", float("nan")))
                lo = float(row.get("Low", float("nan")))
                c = float(row.get("Close", float("nan")))
                v = int(row.get("Volume", 0))
                if any(math.isnan(x) for x in (o, h, lo, c)) or v <= 0:
                    continue
                bars.append(dict(date=ds, open=round(o, 5), high=round(h, 5),
                                 low=round(lo, 5), close=round(c, 5),
                                 volume=v))
            except Exception:
                continue
        return sorted(bars, key=lambda b: b["date"])
    except Exception:
        return []


# ── Source 2: NSE India direct ──────────────────────────────────────────────

_nse_session = None
_nse_session_ts: float = 0
_nse_lock = threading.Lock()


def _get_nse_session():
    """Return a requests.Session with NSE cookies (cached 10 min)."""
    import requests
    global _nse_session, _nse_session_ts
    now = time.time()
    with _nse_lock:
        if _nse_session and (now - _nse_session_ts) < 600:
            return _nse_session
        s = requests.Session()
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"),
            "Accept": "text/html,application/xhtml+xml,application/json",
            "Accept-Language": "en-US,en;q=0.9",
        })
        try:
            s.get("https://www.nseindia.com", timeout=10, allow_redirects=True)
        except Exception:
            pass
        _nse_session = s
        _nse_session_ts = now
        return s


def _fetch_nse_india(symbol, from_date):
    """Fetch OHLCV from NSE India's equity historical API."""
    base_sym = symbol.replace(".NS", "")
    if from_date:
        start = (datetime.date.fromisoformat(from_date)
                 + datetime.timedelta(days=1))
    else:
        start = datetime.date.today() - datetime.timedelta(days=365)
    end = datetime.date.today()

    # NSE limits each request to ~90 days, so chunk if needed
    all_bars: list[dict] = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + datetime.timedelta(days=60), end)
        bars = _nse_chunk(base_sym, chunk_start, chunk_end)
        if bars:
            all_bars.extend(bars)
        chunk_start = chunk_end + datetime.timedelta(days=1)
        time.sleep(0.5)

    by_date = {b["date"]: b for b in all_bars}
    return sorted(by_date.values(), key=lambda b: b["date"])


def _nse_chunk(base_sym, start, end):
    try:
        _throttle()
        session = _get_nse_session()
        from_s = start.strftime("%d-%m-%Y")
        to_s = end.strftime("%d-%m-%Y")
        url = (
            f"https://www.nseindia.com/api/historical/cm/equity"
            f"?symbol={urllib.parse.quote(base_sym)}"
            f"&series=[%22EQ%22]"
            f"&from={from_s}&to={to_s}"
        )
        resp = session.get(url, headers={
            "Accept": "application/json",
            "Referer": (
                "https://www.nseindia.com/get-quotes/equity"
                f"?symbol={urllib.parse.quote(base_sym)}"
            ),
        }, timeout=15)
        if not resp.ok:
            return []
        records = resp.json().get("data", [])
        if not records:
            return []
        bars = []
        for rec in records:
            try:
                raw = rec.get("CH_TIMESTAMP", "")
                if not raw:
                    continue
                dt = datetime.date.fromisoformat(raw[:10])
                o = float(rec.get("CH_OPENING_PRICE", 0))
                h = float(rec.get("CH_TRADE_HIGH_PRICE", 0))
                lo = float(rec.get("CH_TRADE_LOW_PRICE", 0))
                c = float(rec.get("CH_CLOSING_PRICE", 0))
                v = int(float(rec.get("CH_TOT_TRADED_QTY", 0)))
                if o <= 0 or h <= 0 or lo <= 0 or c <= 0 or v <= 0:
                    continue
                bars.append(dict(date=dt.isoformat(), open=round(o, 5),
                                 high=round(h, 5), low=round(lo, 5),
                                 close=round(c, 5), volume=v))
            except Exception:
                continue
        return bars
    except Exception:
        return []


# ── Source 3: raw Yahoo v8 (no crumb, clean session) ────────────────────────

def _fetch_raw_yahoo(symbol, from_date):
    import requests
    now_ist = datetime.datetime.now(IST)
    p2 = int(now_ist.timestamp())
    if from_date:
        try:
            dt = (datetime.date.fromisoformat(from_date)
                  + datetime.timedelta(days=1))
            p1 = int(datetime.datetime(dt.year, dt.month, dt.day,
                                       tzinfo=IST).timestamp())
        except Exception:
            p1 = int((now_ist - datetime.timedelta(days=365)).timestamp())
    else:
        p1 = int((now_ist - datetime.timedelta(days=730)).timestamp())

    encoded = urllib.parse.quote(symbol, safe="")
    hosts = ["query2.finance.yahoo.com", "query1.finance.yahoo.com"]
    for attempt in range(1, MAX_RETRIES + 1):
        _throttle()
        host = hosts[(attempt - 1) % len(hosts)]
        try:
            url = (
                f"https://{host}/v8/finance/chart/{encoded}"
                f"?interval=1d&period1={p1}&period2={p2}"
                f"&events=history&includeAdjustedClose=true"
            )
            resp = requests.get(url, headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36"),
                "Accept": "application/json",
                "Referer": "https://finance.yahoo.com",
            }, timeout=15)
            if resp.status_code == 429:
                time.sleep(RETRY_DELAY * (2 ** attempt))
                continue
            if not resp.ok:
                time.sleep(RETRY_DELAY * attempt)
                continue
            result = resp.json().get("chart", {}).get("result", [])
            if not result:
                return []
            return _parse_chart(result[0])
        except Exception:
            time.sleep(RETRY_DELAY * attempt)
    return []


def _parse_chart(chart):
    ts_list = chart.get("timestamp", [])
    q = chart.get("indicators", {}).get("quote", [{}])[0]
    opens = q.get("open", [])
    highs = q.get("high", [])
    lows = q.get("low", [])
    closes = q.get("close", [])
    vols = q.get("volume", [])
    adj = chart.get("indicators", {}).get("adjclose", [{}])
    adj = adj[0].get("adjclose", []) if adj else []

    def _n(x):
        if x is None:
            return None
        try:
            f = float(x)
            return None if math.isnan(f) else f
        except (TypeError, ValueError):
            return None

    bars = []
    for i, ts in enumerate(ts_list):
        try:
            o = _n(opens[i] if i < len(opens) else None)
            h = _n(highs[i] if i < len(highs) else None)
            lo = _n(lows[i] if i < len(lows) else None)
            c = _n(closes[i] if i < len(closes) else None)
            v = vols[i] if i < len(vols) else None
            if c is None and i < len(adj):
                c = _n(adj[i])
            if any(x is None for x in (ts, o, h, lo, c)):
                continue
            if v is None or v <= 0:
                continue
            d = datetime.datetime.fromtimestamp(ts, IST).strftime("%Y-%m-%d")
            bars.append(dict(date=d, open=round(o, 5), high=round(h, 5),
                             low=round(lo, 5), close=round(c, 5),
                             volume=int(v)))
        except Exception:
            continue
    return sorted(bars, key=lambda b: b["date"])


# ═══════════════════════════════════════════════════════════════════════════
#  CACHE READ / WRITE / MERGE
# ═══════════════════════════════════════════════════════════════════════════

def _read_cache_bars(csv_path):
    bars = []
    try:
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                try:
                    cv = float(row["close"])
                    if math.isnan(cv) or cv <= 0:
                        continue
                    bars.append(dict(
                        date=row["date"].strip(),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=cv,
                        volume=int(float(row["volume"])),
                    ))
                except Exception:
                    continue
    except Exception:
        pass
    return bars


def _write_cache(csv_path, bars):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "date", "open", "high", "low", "close", "volume"])
        w.writeheader()
        for b in bars:
            w.writerow(dict(
                date=b["date"],
                open=f"{b['open']:.5f}",
                high=f"{b['high']:.5f}",
                low=f"{b['low']:.5f}",
                close=f"{b['close']:.5f}",
                volume=str(b["volume"]),
            ))


def _merge_bars(old, new):
    by_date = {}
    for b in old:
        by_date[b["date"]] = b
    for b in new:
        by_date[b["date"]] = b
    return sorted(by_date.values(), key=lambda x: x["date"])


# ═══════════════════════════════════════════════════════════════════════════
#  PER-SYMBOL REFRESH
# ═══════════════════════════════════════════════════════════════════════════

def _find_legacy(sym):
    legacy = []
    for p in CACHE_DIR.glob(f"{sym}_*.csv"):
        idx = p.name.rfind("_")
        if idx > 0 and p.name[idx + 1:].replace(".csv", "").isdigit():
            legacy.append(p)
    return sorted(legacy, key=lambda p: p.stat().st_size, reverse=True)


def refresh_symbol(sym, cache_path, last_date, force=False, dry_run=False):
    result = {"symbol": sym, "status": "skipped",
              "bars_added": 0, "last_date": last_date}
    if not force and not _is_stale(last_date):
        result["status"] = "fresh"
        return result
    if dry_run:
        result["status"] = "would_refresh"
        return result

    existing = _read_cache_bars(cache_path) if cache_path.exists() else []
    legacy = _find_legacy(sym)
    for lf in legacy:
        existing.extend(_read_cache_bars(lf))
    by_date = {b["date"]: b for b in existing}
    existing = sorted(by_date.values(), key=lambda b: b["date"])
    fetch_from = existing[-1]["date"] if existing else None

    new_bars = _fetch_bars(sym, from_date=fetch_from)
    time.sleep(RATE_LIMIT_DELAY)

    if not new_bars:
        if legacy and existing:
            _write_cache(cache_path, existing)
            for lf in legacy:
                try:
                    lf.unlink()
                except Exception:
                    pass
        result["status"] = "no_new_data"
        return result

    merged = _merge_bars(existing, new_bars)
    _write_cache(cache_path, merged)
    for lf in legacy:
        try:
            lf.unlink()
        except Exception:
            pass
    result.update(
        status="updated",
        bars_added=len(new_bars),
        last_date=merged[-1]["date"] if merged else last_date,
    )
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  BATCH REFRESH
# ═══════════════════════════════════════════════════════════════════════════

def refresh_all(symbol_filter=None, workers=4, force=False,
                dry_run=False, indian_only=False):
    print("\n🔄 Scanning cache directory for stale files…", flush=True)
    stale = _find_stale_caches(symbol_filter, indian_only=indian_only)
    if not stale:
        print("✅ All cache files are up-to-date!", flush=True)
        return {"refreshed": 0, "skipped": 0, "errors": 0}

    print(f"  Found {len(stale)} stale symbol(s)", flush=True)
    if dry_run:
        for sym, _, ld in stale[:20]:
            print(f"    {sym}  (last: {ld or 'none'})", flush=True)
        if len(stale) > 20:
            print(f"    … and {len(stale) - 20} more", flush=True)
        return {"refreshed": 0, "skipped": len(stale), "errors": 0}

    print("  Sources: yfinance → NSE India → raw Yahoo v8", flush=True)
    stats = {"refreshed": 0, "skipped": 0, "errors": 0, "no_data": 0}
    lock = threading.Lock()
    done = 0
    total = len(stale)

    def _do(item):
        nonlocal done
        sym, path, ld = item
        try:
            res = refresh_symbol(sym, path, ld,
                                 force=force, dry_run=dry_run)
            with lock:
                done += 1
                pct = done / total * 100
                st = res["status"]
                if st == "updated":
                    stats["refreshed"] += 1
                    print(
                        f"  [{done:4d}/{total}] ✅ {sym:<20}  "
                        f"+{res['bars_added']} bars → {res['last_date']}"
                        f"  ({pct:.0f}%)",
                        flush=True)
                elif st in ("fresh", "skipped"):
                    stats["skipped"] += 1
                elif st == "no_new_data":
                    stats["no_data"] += 1
                    if done <= 30 or done % 200 == 0:
                        print(
                            f"  [{done:4d}/{total}] ⏭  {sym:<20}  "
                            f"no new data  ({pct:.0f}%)",
                            flush=True)
                else:
                    stats["errors"] += 1
                    print(
                        f"  [{done:4d}/{total}] ❌ {sym:<20}  "
                        f"{st}  ({pct:.0f}%)",
                        flush=True)
        except Exception as ex:
            with lock:
                done += 1
                stats["errors"] += 1
                print(f"  [{done:4d}/{total}] ❌ {sym}: {ex}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_do, stale))

    print(f"\n{'=' * 60}", flush=True)
    print("✅ Cache refresh complete!", flush=True)
    print(f"   Refreshed  : {stats['refreshed']}", flush=True)
    print(f"   No new data: {stats['no_data']}", flush=True)
    print(f"   Skipped    : {stats['skipped']}", flush=True)
    print(f"   Errors     : {stats['errors']}", flush=True)
    return stats


def refresh_nifty_index():
    nifty_path = CACHE_DIR / "^NSEI.csv"
    existing = _read_cache_bars(nifty_path) if nifty_path.exists() else []
    legacy = sorted(CACHE_DIR.glob("^NSEI_*.csv"),
                    key=lambda p: p.stat().st_size, reverse=True)
    for lf in legacy:
        existing.extend(_read_cache_bars(lf))
    by_date = {b["date"]: b for b in existing}
    existing = sorted(by_date.values(), key=lambda b: b["date"])
    last_date = existing[-1]["date"] if existing else ""

    if not _is_stale(last_date):
        print(f"✅ Nifty cache is fresh (last: {last_date})", flush=True)
        if legacy:
            _write_cache(nifty_path, existing)
            for lf in legacy:
                try:
                    lf.unlink()
                except Exception:
                    pass
        return

    print(
        f"🔄 Refreshing Nifty 50 index (last: {last_date or 'none'})…",
        flush=True)
    new = _fetch_bars("^NSEI", from_date=last_date if existing else None)
    if new:
        merged = _merge_bars(existing, new)
        _write_cache(nifty_path, merged)
        for lf in legacy:
            try:
                lf.unlink()
            except Exception:
                pass
        print(
            f"✅ Nifty updated: +{len(new)} bars → {merged[-1]['date']}",
            flush=True)
    else:
        if legacy and existing:
            _write_cache(nifty_path, existing)
            for lf in legacy:
                try:
                    lf.unlink()
                except Exception:
                    pass
        print("⚠ No new Nifty bars fetched", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="Multi-source OHLCV cache refresher")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--symbols", default=None,
                    help="Comma-separated (e.g. TATASTEEL,MTARTECH)")
    ap.add_argument("--no-nifty", action="store_true")
    ap.add_argument("--indian-only", action="store_true",
                    help="Only refresh .NS / .BO symbols")
    args = ap.parse_args()

    sym_filter = ([s.strip() for s in args.symbols.split(",")]
                  if args.symbols else None)
    if not args.no_nifty:
        refresh_nifty_index()
    stats = refresh_all(
        symbol_filter=sym_filter,
        workers=args.workers,
        force=args.force,
        dry_run=args.dry_run,
        indian_only=args.indian_only,
    )
    sys.exit(1 if stats.get("errors", 0) > 0 else 0)


if __name__ == "__main__":
    main()

