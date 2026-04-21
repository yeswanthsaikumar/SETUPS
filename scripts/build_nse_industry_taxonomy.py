#!/usr/bin/env python3
"""
build_nse_industry_taxonomy.py
──────────────────────────────
Fetch the OFFICIAL 4-level NSE industry classification for every NSE
ticker in the cache directory, directly from NSE's public API
(`/api/quote-equity?symbol=X`). This is the same data Zerodha and
Tijori display — the canonical source.

Output columns (data/nse_industry_taxonomy.csv):
    nse_ticker, company_name, macro, sector, industry, basic_industry, source

• `source = "nse_official"` whenever industryInfo was present.
• `source = "missing"`      if NSE returned the symbol but no industryInfo
                             (applies to some ETFs / recently-listed IPOs).
• `source = "error: <code>"` on HTTP/network errors so bad rows are visible.

Idempotent + resumable: writes an intermediate JSON cache
(data/.nse_industry_cache.json) and skips tickers already cached unless
`--force` is passed.

Usage:
    python scripts/build_nse_industry_taxonomy.py              # incremental
    python scripts/build_nse_industry_taxonomy.py --force      # re-fetch all
    python scripts/build_nse_industry_taxonomy.py --workers 8  # faster
    python scripts/build_nse_industry_taxonomy.py --symbols RELIANCE,TCS

After it finishes:
- Merges into the existing data/nse_stock_taxonomy.csv by overwriting the
  `sector`/`industry` columns with the NSE-official values and setting
  `notes = nse_official`. Keeps any row whose ticker isn't in the NSE
  response (preserves untouched legacy).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import requests
except ImportError:
    print("pip install requests", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
DATA_DIR = ROOT / "data"
TAXONOMY_CSV = DATA_DIR / "nse_stock_taxonomy.csv"          # existing 4-col
OUTPUT_CSV = DATA_DIR / "nse_industry_taxonomy.csv"          # new canonical
PROGRESS_CACHE = DATA_DIR / ".nse_industry_cache.json"       # resumable

NSE_BASE = "https://www.nseindia.com"
QUOTE_EQ_URL = NSE_BASE + "/api/quote-equity?symbol={sym}"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0.0.0 Safari/537.36")

# Session cookies expire; rotate every ~8 minutes.
_session_lock = threading.Lock()
_session: requests.Session | None = None
_session_ts: float = 0.0
_SESSION_TTL = 8 * 60

_progress_lock = threading.Lock()


def _get_session(force_new: bool = False) -> requests.Session:
    global _session, _session_ts
    now = time.time()
    with _session_lock:
        if not force_new and _session is not None and (now - _session_ts) < _SESSION_TTL:
            return _session
        s = requests.Session()
        s.headers.update({
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{NSE_BASE}/",
            "X-Requested-With": "XMLHttpRequest",
        })
        # Prime cookies: home + a quote page (required for api/ to return 200).
        try:
            s.get(NSE_BASE + "/", timeout=10)
            time.sleep(0.3)
            s.get(NSE_BASE + "/get-quotes/equity?symbol=RELIANCE", timeout=10)
        except Exception as e:
            print(f"  session prime warning: {e}", flush=True)
        _session = s
        _session_ts = now
        return s


def _collect_ns_tickers(include_legacy: bool = True) -> list[str]:
    """Every .NS.csv in cache/ (minus junk). When include_legacy is True,
    also include any ticker already listed in the existing taxonomy CSV
    (so rows without a matching cache file still get re-classified)."""
    tickers: set[str] = set()
    for p in CACHE_DIR.glob("*.NS.csv"):
        sym = p.stem.replace(".NS", "").upper()
        if not sym or sym.startswith("^") or "_" in sym:
            continue
        tickers.add(sym)
    if include_legacy and TAXONOMY_CSV.exists():
        try:
            with TAXONOMY_CSV.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    t = (row.get("nse_ticker") or "").strip().upper()
                    if t and not t.startswith("^") and "_" not in t:
                        tickers.add(t)
        except Exception as e:
            print(f"  (could not read {TAXONOMY_CSV}: {e})", flush=True)
    return sorted(tickers)


def _fetch_one(sym: str, retries: int = 3) -> dict:
    # URL-encode symbols containing '&' etc. so NSE's API doesn't treat them
    # as query-string separators (e.g. ARE&M, GVT&D, J&KBANK).
    url = QUOTE_EQ_URL.format(sym=urllib.parse.quote(sym, safe=""))
    last_err = None
    for attempt in range(retries):
        s = _get_session(force_new=(attempt > 0))
        try:
            r = s.get(url, timeout=12)
            if r.status_code == 200:
                try:
                    data = r.json()
                except Exception as e:
                    last_err = f"non-json: {e}"
                    time.sleep(0.8)
                    continue
                info = data.get("industryInfo") or {}
                return {
                    "nse_ticker": sym,
                    "company_name": (data.get("info") or {}).get("companyName", ""),
                    "macro":          info.get("macro") or "",
                    "sector":         info.get("sector") or "",
                    "industry":       info.get("industry") or "",
                    "basic_industry": info.get("basicIndustry") or "",
                    "source": "nse_official" if info else "missing",
                }
            elif r.status_code in (401, 403, 429):
                last_err = f"http {r.status_code}"
                time.sleep(1.0 + attempt)  # backoff
                _get_session(force_new=True)  # rotate session
                continue
            else:
                last_err = f"http {r.status_code}"
                break
        except requests.RequestException as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(0.8 + attempt)
    return {"nse_ticker": sym, "source": f"error: {last_err or 'unknown'}"}


def _load_progress() -> dict[str, dict]:
    if not PROGRESS_CACHE.exists():
        return {}
    try:
        return json.loads(PROGRESS_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_progress(prog: dict[str, dict]) -> None:
    PROGRESS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PROGRESS_CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(prog, sort_keys=True), encoding="utf-8")
    tmp.replace(PROGRESS_CACHE)


def _write_output(rows: list[dict]) -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    cols = ["nse_ticker", "company_name", "macro", "sector",
            "industry", "basic_industry", "source"]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in sorted(rows, key=lambda x: x["nse_ticker"]):
            w.writerow({c: r.get(c, "") for c in cols})


def _merge_into_existing(nse_rows: list[dict]) -> tuple[int, int, int]:
    """Overwrite sector/industry in data/nse_stock_taxonomy.csv using NSE.

    Returns (updated, added, kept_legacy). Keeps any legacy row whose ticker
    wasn't returned by NSE (ISIN preserved, etc).
    """
    nse_map = {r["nse_ticker"]: r for r in nse_rows
               if r.get("source") == "nse_official"}
    existing: dict[str, dict] = {}
    header = ["nse_ticker", "sector", "industry", "notes"]
    if TAXONOMY_CSV.exists():
        with TAXONOMY_CSV.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                t = (row.get("nse_ticker") or "").upper().strip()
                if t:
                    existing[t] = row
    updated = added = kept = 0
    for t, r in nse_map.items():
        new_row = {
            "nse_ticker": t,
            "sector":     r.get("sector") or "Other",
            "industry":   r.get("industry") or "Other",
            "notes":      "nse_official",
        }
        if t in existing:
            old = existing[t]
            if (old.get("sector") != new_row["sector"]
                    or old.get("industry") != new_row["industry"]):
                updated += 1
            existing[t] = new_row
        else:
            existing[t] = new_row
            added += 1
    kept = len(existing) - updated - added
    # Write back
    with TAXONOMY_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for t in sorted(existing):
            w.writerow(existing[t])
    return updated, added, kept


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4,
                    help="concurrent fetchers (default 4)")
    ap.add_argument("--force", action="store_true",
                    help="ignore resume cache; re-fetch every ticker")
    ap.add_argument("--symbols", type=str, default="",
                    help="comma-separated list to restrict the run")
    ap.add_argument("--no-merge", action="store_true",
                    help="skip merging into nse_stock_taxonomy.csv")
    ap.add_argument("--cache-only", action="store_true",
                    help="only fetch tickers that have a .NS.csv in cache/ "
                         "(skip legacy rows in nse_stock_taxonomy.csv)")
    args = ap.parse_args()

    all_tickers = _collect_ns_tickers(include_legacy=not args.cache_only)
    if args.symbols:
        wanted = {t.strip().upper() for t in args.symbols.split(",") if t.strip()}
        all_tickers = [t for t in all_tickers if t in wanted]
    if not all_tickers:
        print("No tickers found — is the cache/ directory populated?", file=sys.stderr)
        return 1

    print(f"Tickers to resolve: {len(all_tickers)}")
    progress = {} if args.force else _load_progress()
    print(f"Resumed from cache  : {len(progress)} entries")
    todo = [t for t in all_tickers if t not in progress or not progress[t]
            or (progress[t].get("source") or "").startswith("error")]
    print(f"Still to fetch      : {len(todo)}")

    if todo:
        print(f"\nFetching with {args.workers} workers…")
        done = 0
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_fetch_one, t): t for t in todo}
            for fut in as_completed(futures):
                sym = futures[fut]
                try:
                    result = fut.result()
                except Exception as e:
                    result = {"nse_ticker": sym, "source": f"error: {e}"}
                with _progress_lock:
                    progress[sym] = result
                    done += 1
                    if done % 50 == 0 or done == len(todo):
                        _save_progress(progress)
                        ok = sum(1 for r in progress.values()
                                 if r.get("source") == "nse_official")
                        miss = sum(1 for r in progress.values()
                                   if r.get("source") == "missing")
                        err = sum(1 for r in progress.values()
                                  if (r.get("source") or "").startswith("error"))
                        print(f"  [{done:4d}/{len(todo)}] {sym:<14} "
                              f"ok={ok} missing={miss} err={err}", flush=True)
                        time.sleep(0.05)  # tiny breather
        _save_progress(progress)

    rows = [progress[t] for t in all_tickers if t in progress]
    _write_output(rows)
    print(f"\n✅ Wrote {OUTPUT_CSV.relative_to(ROOT)} ({len(rows)} rows)")

    # Summary
    by_src: dict[str, int] = {}
    for r in rows:
        by_src[r.get("source", "?")] = by_src.get(r.get("source", "?"), 0) + 1
    print("Breakdown by source:")
    for k, v in sorted(by_src.items(), key=lambda x: -x[1]):
        print(f"  {k:<20} {v}")

    if not args.no_merge:
        updated, added, _ = _merge_into_existing(rows)
        print(f"\n🔀 Merged into {TAXONOMY_CSV.relative_to(ROOT)}: "
              f"updated={updated}  added={added}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

