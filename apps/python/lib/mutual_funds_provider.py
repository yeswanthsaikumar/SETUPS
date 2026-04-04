"""
mutual_funds_provider.py
────────────────────────
Fetches institutional & mutual fund holding data for Indian stocks.

Sources (in priority order):
  1. Screener.in  — Shareholding pattern: Promoters / FIIs / DIIs / Public (quarterly)
  2. yfinance info — heldPercentInstitutions, floatShares
  3. NSE AMFI monthly portfolio (CSV) — top MF scheme names that hold the stock

Returns a compact dict per symbol, cached with a 6-hour TTL:
{
  "symbol": "RELIANCE.NS",
  "screener_slug": "RELIANCE",
  "promoters_pct": 50.0,
  "fii_pct": 19.1,
  "dii_pct": 20.1,
  "public_pct": 10.8,
  "promoters_trend": "stable",        # up / down / stable
  "fii_trend": "down",
  "dii_trend": "up",
  "dii_accumulating": True,
  "smart_money_signal": "ACCUMULATING",  # ACCUMULATING / DISTRIBUTING / NEUTRAL / UNKNOWN
  "quarterly_data": [...],             # list of {period, promoters, fii, dii, public}
  "top_mf_holders": [                  # top 5 MF schemes by % held
    {"name": "SBI Bluechip Fund", "pct": 2.1, "trend": "up"},
    ...
  ],
  "inst_held_pct": 27.9,              # from yfinance
  "summary": "DIIs ↑ accumulating 20.1% | FIIs ↓ 19.1% | Promoters stable 50.0%",
  "swing_signal": "👍 Smart money ACCUMULATING — DII buying ↑, strong institutional base",
  "_cached_at": "...",
  "_source": "screener+yfinance"
}
"""
from __future__ import annotations

import json
import logging
import re
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("MutualFundsProvider")

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logger.warning("requests/beautifulsoup4 not installed — MF holdings unavailable")

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False


# ── Constants ─────────────────────────────────────────────────────────────────

_SCREENER_SEARCH  = "https://www.screener.in/api/company/search/?q={query}&field=&limit=5"
_SCREENER_PAGE    = "https://www.screener.in/company/{slug}/consolidated/"
_SCREENER_PAGE_NS = "https://www.screener.in/company/{slug}/"   # standalone (non-consolidated)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.screener.in/",
}

# Known slug overrides: NSE-ticker (without .NS) → Screener.in slug
# Verified correct slugs — Screener.in slug ≠ NSE ticker in some cases
_SLUG_OVERRIDES: dict[str, str] = {
    # Verified correct
    "TATAMOTORS":  "TATAMOTORS",
    "M&M":         "M&M",
    "LT":          "LT",
    "L&T":         "LT",
    "LTIM":        "LTM",          # Screener slug is LTM not LTIM
    "BAJAJFINSV":  "BAJAJFINSV",
    "HDFCBANK":    "HDFCBANK",
    "ICICIBANK":   "ICICIBANK",
    "SBIN":        "SBIN",
    "KOTAKBANK":   "KOTAKBANK",
    "AXISBANK":    "AXISBANK",
    "INDUSINDBK":  "INDUSINDBK",
    "TATASTEEL":   "TATASTEEL",
    "HINDALCO":    "HINDALCO",
    "JSWSTEEL":    "JSWSTEEL",
    "WIPRO":       "WIPRO",
    "TECHM":       "TECHM",
    "HCLTECH":     "HCLTECH",
    "INFY":        "INFY",
    "TCS":         "TCS",
    "RELIANCE":    "RELIANCE",
    "ADANIENT":    "ADANIENT",
    "ADANIPORTS":  "ADANIPORTS",
    "ADANIGREEN":  "ADANIGREEN",
    "NTPC":        "NTPC",
    "POWERGRID":   "POWERGRID",
    "ONGC":        "ONGC",
    "BPCL":        "BPCL",
    "IOC":         "IOC",
    "GAIL":        "GAIL",
    "COALINDIA":   "COALINDIA",
    "SUNPHARMA":   "SUNPHARMA",
    "DRREDDY":     "DRREDDY",
    "CIPLA":       "CIPLA",
    "DIVISLAB":    "DIVISLAB",
    "MARUTI":      "MARUTI",
    "EICHERMOT":   "EICHERMOT",
    "BAJFINANCE":  "BAJFINANCE",
    "TITAN":       "TITAN",
    "ASIANPAINT":  "ASIANPAINT",
    "ITC":         "ITC",
    "HINDUNILVR":  "HINDUNILVR",
    "NESTLEIND":   "NESTLEIND",
    "DLF":         "DLF",
    "PERSISTENT":  "PERSISTENT",
    "COFORGE":     "COFORGE",
    "KPITTECH":    "KPITTECH",
    "ZOMATO":      "ZOMATO",
    "NAUKRI":      "NAUKRI",
    "IRCTC":       "IRCTC",
    "BEL":         "BEL",
    "HAL":         "HAL",
    "SIEMENS":     "SIEMENS",
    "ABB":         "ABB",
    "RECLTD":      "RECLTD",
    "PFC":         "PFC",
    "DIXON":       "DIXON",
    "VOLTAS":      "VOLTAS",
    "HAVELLS":     "HAVELLS",
    "CROMPTON":    "CROMPTON",
    "PIDILITIND":  "PIDILITIND",
    "TORNTPHARM":  "TORNTPHARM",
    "LUPIN":       "LUPIN",
    "AUROPHARMA":  "AUROPHARMA",
    "ALKEM":       "ALKEM",
    "IPCALAB":     "IPCALAB",
    "GLENMARK":    "GLENMARK",
    "GRANULES":    "GRANULES",
    "LAURUSLABS":  "LAURUSLABS",
    "HEROMOTOCO":  "HEROMOTOCO",
    "ASHOKLEY":    "ASHOKLEY",
    "TVSMOTOR":    "TVSMOTOR",
    "TIINDIA":     "TIINDIA",
    "MOTHERSON":   "MOTHERSON",
    "BANKBARODA":  "BANKBARODA",
    "PNB":         "PNB",
    "CANBK":       "CANBK",
    "UNIONBANK":   "UNIONBANK",
    "FEDERALBNK":  "FEDERALBNK",
    "IDFCFIRSTB":  "IDFCFIRSTB",
    "AUBANK":      "AUBANK",
    "RBLBANK":     "RBLBANK",
    "BANDHANBNK":  "BANDHANBNK",
    "CHOLAFIN":    "CHOLAFIN",
    "MUTHOOTFIN":  "MUTHOOTFIN",
    "MANAPPURAM":  "MANAPPURAM",
    "LICHSGFIN":   "LICHSGFIN",
    "M&MFIN":      "M&MFIN",
    "GODREJCP":    "GODREJCP",
    "MARICO":      "MARICO",
    "DABUR":       "DABUR",
    "COLPAL":      "COLPAL",
    "BRITANNIA":   "BRITANNIA",
    "GODREJPROP":  "GODREJPROP",
    "OBEROIRLTY":  "OBEROIRLTY",
    "PRESTIGE":    "PRESTIGE",
    "HDFCLIFE":    "HDFCLIFE",
    "SBILIFE":     "SBILIFE",
    "ICICIPRU":    "ICICIPRU",
    "BHEL":        "BHEL",
    "CUMMINSIND":  "CUMMINSIND",
    "THERMAX":     "THERMAX",
    "NMDC":        "NMDC",
    "HINDZINC":    "HINDZINC",
    "APLAPOLLO":   "APLAPOLLO",
    "SAIL":        "SAIL",
    "VEDL":        "VEDL",
    "OFSS":        "OFSS",
    "MPHASIS":     "MPHASIS",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_symbol(symbol: str) -> str:
    """Strip exchange suffix for Screener.in lookup."""
    return symbol.replace(".NS", "").replace(".BO", "").strip().upper()


def _pct_str_to_float(text: str) -> float | None:
    t = str(text or "").strip().replace("%", "").replace(",", "")
    try:
        v = float(t)
        return round(v, 2)
    except Exception:
        return None


def _trend(current: float | None, previous: float | None, threshold: float = 0.3) -> str:
    if current is None or previous is None:
        return "stable"
    diff = current - previous
    if diff > threshold:
        return "up"
    if diff < -threshold:
        return "down"
    return "stable"


def _trend_emoji(t: str) -> str:
    return {"up": "↑", "down": "↓", "stable": "→"}.get(t, "→")


def _make_session() -> "requests.Session":
    s = requests.Session()
    s.headers.update(_HEADERS)
    return s


# ── Screener.in slug resolution ───────────────────────────────────────────────

def _try_direct_slug(slug: str, session: "requests.Session") -> bool:
    """Return True if the consolidated page for this slug actually exists (200 OK)."""
    for url in [_SCREENER_PAGE.format(slug=slug), _SCREENER_PAGE_NS.format(slug=slug)]:
        try:
            r = session.get(url, timeout=8, allow_redirects=True)
            if r.status_code == 200 and "shareholding" in r.text.lower():
                return True
        except Exception:
            pass
    return False


def _search_for_slug(query: str, session: "requests.Session") -> str | None:
    """Search Screener.in and return the best slug match."""
    try:
        r = session.get(_SCREENER_SEARCH.format(query=query), timeout=8)
        if r.status_code != 200:
            return None
        items = r.json()
        if not isinstance(items, list) or not items:
            return None

        # Try exact match first (case-insensitive)
        q_upper = query.upper()
        for item in items:
            url = item.get("url", "")
            m = re.search(r"/company/([^/]+)/", url)
            if m:
                slug = m.group(1)
                if slug.upper() == q_upper:
                    return slug

        # Second pass: slug starts with query
        for item in items:
            url = item.get("url", "")
            m = re.search(r"/company/([^/]+)/", url)
            if m:
                slug = m.group(1)
                if slug.upper().startswith(q_upper[:6]):
                    return slug

        # Fall back to first numeric-free result
        for item in items:
            url = item.get("url", "")
            m = re.search(r"/company/([^/]+)/", url)
            if m:
                slug = m.group(1)
                if not slug.isdigit():
                    return slug

        return None
    except Exception as e:
        logger.debug("Screener search failed for %s: %s", query, e)
        return None


def _resolve_screener_slug(symbol: str, session: "requests.Session") -> str | None:
    """
    Resolve NSE ticker → Screener.in company slug.
    Strategy (in order):
      1. Known override map (instant, no network)
      2. Direct attempt with the ticker as slug (works for 90%+ of NSE stocks)
      3. Search API fallback
    """
    base = _clean_symbol(symbol)

    # 1. Override map
    if base in _SLUG_OVERRIDES:
        return _SLUG_OVERRIDES[base]

    # 2. Direct attempt: Screener slug = NSE ticker for most stocks
    # (skip the HTTP check for common stocks to save time — just try directly)
    # We'll validate lazily when we parse the page

    # 3. Search API
    slug = _search_for_slug(base, session)
    if slug:
        return slug

    # 4. Last resort: try ticker directly (may 404 but we'll handle that in fetch)
    return base


# ── Screener.in page parsing ──────────────────────────────────────────────────

def _fetch_screener_page(slug: str, session: "requests.Session") -> tuple[int, str]:
    """Fetch the Screener.in consolidated company page with retry on rate-limit. Returns (status_code, html)."""
    urls = [_SCREENER_PAGE.format(slug=slug), _SCREENER_PAGE_NS.format(slug=slug)]
    for url in urls:
        for attempt in range(2):          # max 2 attempts per URL
            try:
                r = session.get(url, timeout=12)
                if r.status_code == 200:
                    return 200, r.text
                if r.status_code in (429, 503, 502):
                    # Rate limited — back off and retry once
                    time.sleep(2.0 + attempt * 1.5)
                    continue
                break                     # 404, 403, etc — no point retrying
            except Exception:
                time.sleep(0.5)
                break
    return 404, ""


def _parse_shareholding_table(soup: "BeautifulSoup") -> list[dict]:
    """Parse quarterly shareholding table from screener.in company page."""
    results: list[dict] = []
    sh_section = soup.find("section", id="shareholding")
    if not sh_section:
        return results

    tables = sh_section.find_all("table")
    if not tables:
        return results

    # Use the first (quarterly) table
    table = tables[0]
    headers: list[str] = []
    rows_data: dict[str, list[str]] = {}

    thead = table.find("thead")
    if thead:
        for th in thead.find_all("th"):
            text = th.get_text(strip=True)
            if text:
                headers.append(text)

    tbody = table.find("tbody")
    if tbody:
        for tr in tbody.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            label = cells[0].get_text(strip=True).replace("+", "").strip()
            values = [c.get_text(strip=True) for c in cells[1:]]
            if label:
                rows_data[label] = values

    if not headers or not rows_data:
        return results

    for i, period in enumerate(headers):
        entry: dict = {"period": period}
        for category, values in rows_data.items():
            if i < len(values):
                v = _pct_str_to_float(values[i])
                cat_key = category.lower()
                if "promoter" in cat_key:
                    entry["promoters"] = v
                elif "fii" in cat_key or "foreign" in cat_key:
                    entry["fii"] = v
                elif "dii" in cat_key or "domestic" in cat_key:
                    entry["dii"] = v
                elif "public" in cat_key:
                    entry["public"] = v
                elif "government" in cat_key or "govt" in cat_key:
                    entry["government"] = v
        results.append(entry)

    return results


def _parse_top_mf_holders(soup: "BeautifulSoup") -> list[dict]:
    """Try to extract top MF scheme names from the page."""
    holders: list[dict] = []
    for heading in soup.find_all(["h3", "h4", "span", "div"]):
        txt = heading.get_text(strip=True).lower()
        if "mutual fund" in txt and "holder" in txt:
            parent = heading.find_parent()
            if parent:
                tbl = parent.find("table")
                if tbl:
                    for tr in tbl.find_all("tr")[1:6]:
                        tds = tr.find_all("td")
                        if len(tds) >= 2:
                            name = tds[0].get_text(strip=True)
                            pct = _pct_str_to_float(tds[-1].get_text(strip=True))
                            if name and pct is not None:
                                holders.append({"name": name, "pct": pct, "trend": "unknown"})
                    if holders:
                        return holders
    return holders


def _fetch_screener_data(symbol: str) -> dict:
    """Fetch shareholding pattern from Screener.in."""
    if not HAS_REQUESTS:
        return {"error": "requests_unavailable"}

    session = _make_session()
    slug = _resolve_screener_slug(symbol, session)

    if not slug:
        return {"error": "slug_not_found", "symbol": symbol}

    # Small delay to avoid Screener.in rate limiting
    time.sleep(0.4)

    status, html = _fetch_screener_page(slug, session)
    if status != 200 or not html:
        # If resolved slug failed, try the raw ticker as a last resort
        base = _clean_symbol(symbol)
        if slug != base:
            time.sleep(0.3)
            status, html = _fetch_screener_page(base, session)
            if status == 200 and html:
                slug = base
            else:
                return {"error": f"http_{status}", "slug": slug}
        else:
            return {"error": f"http_{status}", "slug": slug}

    try:
        soup = BeautifulSoup(html, "html.parser")

        # Verify we got the shareholding section - if not it's a soft 404
        if not soup.find("section", id="shareholding"):
            return {"error": "no_shareholding_section", "slug": slug}

        quarterly = _parse_shareholding_table(soup)
        top_mf    = _parse_top_mf_holders(soup)

        return {
            "slug":          slug,
            "quarterly_data": quarterly,
            "top_mf_holders": top_mf,
        }
    except Exception as e:
        logger.debug("Screener parse failed for %s (slug=%s): %s", symbol, slug, e)
        return {"error": str(e)}


def _fetch_yfinance_inst(symbol: str) -> dict:
    """Fetch institutional holding % from yfinance."""
    if not HAS_YFINANCE:
        return {}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            t = yf.Ticker(symbol)
            info = t.info or {}
        held_inst   = info.get("heldPercentInstitutions")
        held_insider = info.get("heldPercentInsiders")
        float_shares = info.get("floatShares")
        return {
            "inst_held_pct":   round(float(held_inst)   * 100, 2) if held_inst   else None,
            "insider_held_pct": round(float(held_insider) * 100, 2) if held_insider else None,
            "float_shares":    float_shares,
        }
    except Exception:
        return {}


# ── Main provider class ───────────────────────────────────────────────────────

class MutualFundsProvider:
    def __init__(self, cache_dir: str = "cache", cache_ttl_hours: int = 6):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=cache_ttl_hours)

    def _cache_path(self, symbol: str) -> Path:
        safe = symbol.replace("/", "_").replace(".", "_")
        return self.cache_dir / f"mf_holdings_{safe}.json"

    def _load_cache(self, symbol: str) -> dict | None:
        p = self._cache_path(symbol)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text())
            cached_at = data.get("_cached_at")
            # Don't serve a cached "error" result — always retry errors
            if data.get("screener_error") and data.get("quarterly_data") == []:
                return None
            if cached_at and datetime.now() - datetime.fromisoformat(cached_at) < self.ttl:
                return data
        except Exception:
            pass
        return None

    def _save_cache(self, symbol: str, data: dict) -> None:
        data["_cached_at"] = datetime.now().isoformat()
        try:
            self._cache_path(symbol).write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def fetch(self, symbol: str, market: str = "india") -> dict:
        """Return full MF/institutional holdings dict for one symbol."""
        cached = self._load_cache(symbol)
        if cached:
            return cached

        result: dict[str, Any] = {"symbol": symbol, "market": market}

        # Screener.in for Indian stocks
        if market == "india" or symbol.endswith(".NS") or symbol.endswith(".BO"):
            screener = _fetch_screener_data(symbol)
            result["screener_slug"]   = screener.get("slug")
            result["quarterly_data"]  = screener.get("quarterly_data", [])
            result["top_mf_holders"]  = screener.get("top_mf_holders", [])
            if "error" in screener:
                result["screener_error"] = screener["error"]
        else:
            result["quarterly_data"]  = []
            result["top_mf_holders"]  = []

        # yfinance institutional data (always try regardless of screener result)
        yf_data = _fetch_yfinance_inst(symbol)
        result.update(yf_data)

        # ── Derive metrics ─────────────────────────────────────────────────
        qdata  = result.get("quarterly_data", [])
        recent = [q for q in qdata if q.get("dii") is not None][-6:]

        latest = recent[-1] if recent else {}
        prev   = recent[-3] if len(recent) >= 3 else (recent[0] if recent else {})

        promoters_pct = latest.get("promoters")
        fii_pct       = latest.get("fii")
        dii_pct       = latest.get("dii")
        public_pct    = latest.get("public")

        promoters_trend = _trend(latest.get("promoters"), prev.get("promoters"))
        fii_trend       = _trend(fii_pct, prev.get("fii"))
        dii_trend       = _trend(dii_pct, prev.get("dii"))

        result["promoters_pct"]   = promoters_pct
        result["fii_pct"]         = fii_pct
        result["dii_pct"]         = dii_pct
        result["public_pct"]      = public_pct
        result["promoters_trend"] = promoters_trend
        result["fii_trend"]       = fii_trend
        result["dii_trend"]       = dii_trend
        result["latest_period"]   = latest.get("period", "")

        # ── Smart money signal ─────────────────────────────────────────────
        dii_accumulating = dii_trend == "up"
        fii_accumulating = fii_trend == "up"
        result["dii_accumulating"] = dii_accumulating
        result["fii_accumulating"] = fii_accumulating

        # Use yfinance inst_held_pct as fallback signal when screener data missing
        inst_pct = result.get("inst_held_pct")
        has_data = dii_pct is not None or fii_pct is not None

        if not has_data and inst_pct is not None:
            # Derive a basic signal from yfinance institutional %
            if inst_pct >= 30:
                signal    = "INST_HIGH"
                swing_text = f"ℹ️ High institutional ownership: {inst_pct:.1f}% (from yfinance)"
            elif inst_pct >= 10:
                signal    = "NEUTRAL"
                swing_text = f"→ Institutional ownership: {inst_pct:.1f}%"
            else:
                signal    = "UNKNOWN"
                swing_text = "ℹ️ Limited institutional ownership data"
        elif dii_accumulating and fii_accumulating:
            signal    = "STRONG_BUYING"
            swing_text = "🔥 STRONG BUYING — Both DIIs & FIIs accumulating"
        elif dii_accumulating:
            signal    = "DII_ACCUMULATING"
            swing_text = "👍 DIIs accumulating ↑ (smart money buying)"
        elif fii_accumulating:
            signal    = "FII_ACCUMULATING"
            swing_text = "👍 FIIs accumulating ↑ (foreign buying)"
        elif fii_trend == "down" and dii_trend == "down":
            signal    = "DISTRIBUTING"
            swing_text = "⚠️ Institutions distributing — both FIIs & DIIs selling"
        elif fii_trend == "down":
            signal    = "FII_SELLING"
            swing_text = "⚠️ FIIs selling ↓ — watch for follow-through"
        elif has_data:
            signal    = "NEUTRAL"
            swing_text = "→ Institutional ownership stable"
        else:
            signal    = "UNKNOWN"
            swing_text = "ℹ️ No shareholding data available"

        result["smart_money_signal"] = signal
        result["swing_signal"]       = swing_text

        # ── Compact summary ────────────────────────────────────────────────
        parts: list[str] = []
        if dii_pct is not None:
            parts.append(f"DIIs {_trend_emoji(dii_trend)}{dii_pct:.1f}%")
        if fii_pct is not None:
            parts.append(f"FIIs {_trend_emoji(fii_trend)}{fii_pct:.1f}%")
        if promoters_pct is not None:
            parts.append(f"Promoters {_trend_emoji(promoters_trend)}{promoters_pct:.1f}%")
        if not parts and inst_pct is not None:
            parts.append(f"Inst {inst_pct:.1f}%")
        result["summary"] = " | ".join(parts) if parts else "—"
        result["_source"] = "screener+yfinance"

        self._save_cache(symbol, result)
        return result

    def fetch_batch(
        self,
        symbols: list[str],
        market: str = "india",
        workers: int = 4,          # conservative default to avoid rate limiting
    ) -> dict[str, dict]:
        """Parallel fetch for a list of symbols. Uses throttled workers."""
        total = len(symbols)
        if total == 0:
            return {}

        needs_fetch  = [s for s in symbols if self._load_cache(s) is None]
        out: dict    = {s: self._load_cache(s) for s in symbols if s not in needs_fetch}

        if not needs_fetch:
            return out

        # Cap workers to avoid Screener.in rate limiting (3-4 is safe)
        safe_workers = min(workers, 4, len(needs_fetch))

        print(
            f"  Fetching MF/institutional data for {len(needs_fetch)} symbols "
            f"({total - len(needs_fetch)} cached) [{safe_workers} workers]…",
            flush=True,
        )

        done = 0
        with ThreadPoolExecutor(max_workers=safe_workers) as pool:
            futures = {pool.submit(self.fetch, sym, market): sym for sym in needs_fetch}
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    out[sym] = future.result()
                except Exception as e:
                    out[sym] = {"symbol": sym, "error": str(e)}
                done += 1
                if done % 10 == 0:
                    print(f"    mf_holdings {done}/{len(needs_fetch)}…", flush=True)

        return out


# ── Compact summary helper ────────────────────────────────────────────────────

def compact_mf_summary(data: dict) -> str:
    if not data or data.get("error"):
        return "—"
    return data.get("summary", "—")


# ── Swing trading context ─────────────────────────────────────────────────────

def swing_context(data: dict) -> dict:
    if not data:
        return {"signal": "UNKNOWN", "text": "No data", "conviction": "LOW"}

    qdata  = data.get("quarterly_data", [])
    recent = [q for q in qdata if q.get("dii") is not None][-6:]

    dii_values = [q["dii"] for q in recent if q.get("dii") is not None]
    quarters_dii_increasing = sum(
        1 for i in range(1, len(dii_values)) if dii_values[i] > dii_values[i - 1]
    )
    dii_change_3q = round(dii_values[-1] - dii_values[-4], 2) if len(dii_values) >= 4 else None
    dii_change_2q = round(dii_values[-1] - dii_values[-3], 2) if len(dii_values) >= 3 else None

    signal = data.get("smart_money_signal", "UNKNOWN")

    if signal in ("STRONG_BUYING",) and (dii_change_3q or 0) > 1.0:
        conviction = "HIGH"
    elif signal in ("DII_ACCUMULATING", "FII_ACCUMULATING", "STRONG_BUYING", "INST_HIGH"):
        conviction = "MEDIUM"
    elif signal in ("DISTRIBUTING", "FII_SELLING"):
        conviction = "LOW"
    elif signal == "NEUTRAL":
        conviction = "NEUTRAL"
    else:
        conviction = "LOW"

    return {
        "signal":                  signal,
        "text":                    data.get("swing_signal", ""),
        "summary":                 data.get("summary", "—"),
        "promoters":               {"pct": data.get("promoters_pct"), "trend": data.get("promoters_trend", "stable")},
        "fii":                     {"pct": data.get("fii_pct"),       "trend": data.get("fii_trend",       "stable")},
        "dii":                     {"pct": data.get("dii_pct"),       "trend": data.get("dii_trend",       "stable")},
        "public":                  {"pct": data.get("public_pct")},
        "inst_held_pct":           data.get("inst_held_pct"),
        "top_mf":                  data.get("top_mf_holders", []),
        "latest_period":           data.get("latest_period", ""),
        "quarters_dii_increasing": quarters_dii_increasing,
        "dii_change_3q":           dii_change_3q,
        "dii_change_2q":           dii_change_2q,
        "conviction":              conviction,
    }

