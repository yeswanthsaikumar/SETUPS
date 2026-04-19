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

# curl-cffi: bypasses Cloudflare/bot-protection on screener.in
try:
    import curl_cffi.requests as _cffi_requests
    HAS_CURL_CFFI = True
    logger.debug("curl_cffi available — screener.in will use Chrome impersonation")
except ImportError:
    HAS_CURL_CFFI = False
    _cffi_requests = None

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
    "TATAPOWER":   "TATAPOWER",
    "BHARATFORG":  "BHARATFORG",
    "NOCIL":       "NOCIL",
    "IRB":         "IRB",
    "STARHEALTH":  "STARHEALTH",
    "INOXINDIA":   "INOXINDIA",
    "MTARTECH":    "MTARTECH",
    "GPIL":        "GPIL",
    # Corrected slugs — NSE ticker ≠ Screener.in slug
    "APOLLOPIPE":  "APOLLO-PIPES",     # NSE: APOLLOPIPE → Screener: APOLLO-PIPES
    "AIAENG":      "AIA-ENGINEERING",  # NSE: AIAENG → Screener: AIA-ENGINEERING
    "ANANDRATHI":  "ANAND-RATHI-WEALTH-MANAGEMENT",  # NSE: ANANDRATHI
    "ATHERENERG":  "ATHER-ENERGY",     # NSE: ATHERENERG → Screener: ATHER-ENERGY
    "CENTUM":      "CENTUM-ELECTRONICS",  # NSE: CENTUM
    "DALMIASUG":   "DALMIA-BHARAT-SUGAR-AND-INDUSTRIES",  # NSE: DALMIASUG
    "DCI":         "DREDGING-CORPORATION",  # NSE: DCI
    "DEEDEV":      "DEE-DEVELOPMENT-ENGINEERS",  # NSE: DEEDEV
    "DYNAMATECH":  "DYNAMATIC-TECHNOLOGIES",  # NSE: DYNAMATECH → Screener: DYNAMATIC-TECHNOLOGIES
    "LGBBROSLTD":  "LGB-BROTHERS",  # NSE: LGBBROSLTD
    "LLOYDSME":    "LLOYDS-METALS-AND-ENERGY",  # NSE: LLOYDSME
    "NITIRAJ":     "NITIRAJ-ENGINEERS",  # NSE: NITIRAJ
    "POWERINDIA":  "ABB-POWER-PRODUCTS-AND-SYSTEMS-INDIA",  # NSE: POWERINDIA
    "SAKAR":       "SAKAR-HEALTHCARE",  # NSE: SAKAR
    "SHIVAUM":     "SHIVA-UMAMAHESHWARA",  # NSE: SHIVAUM
    "SPORTKING":   "SPORTKING-INDIA",  # NSE: SPORTKING
    "STEELCAS":    "STEELCAST",        # NSE: STEELCAS → Screener: STEELCAST
    "TEXINFRA":    "TEXMACO-INFRASTRUCTURE-AND-HOLDINGS",  # NSE: TEXINFRA
    "TRAVELFOOD":  "TRAVEL-FOOD-SERVICES",  # NSE: TRAVELFOOD
    "UTTAMSUGAR":  "UTTAM-SUGAR-MILLS",   # NSE: UTTAMSUGAR
    "LENSKART":    None,  # Private company — not on Screener.in
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
    """Return a session that can bypass Cloudflare on screener.in.
    Prefers curl-cffi with Chrome impersonation when available."""
    if HAS_CURL_CFFI:
        # curl-cffi impersonates a real Chrome browser — bypasses Cloudflare bot checks
        sess = _cffi_requests.Session(impersonate="chrome120")
        sess.headers.update(_HEADERS)
        return sess
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
      1. Known override map (instant, no network). None = explicitly not listed.
      2. Search API fallback — more reliable for lesser-known stocks
      3. Last resort: try ticker directly (may 404 but we'll handle that in fetch)
    """
    base = _clean_symbol(symbol)

    # 1. Override map — None means explicitly not on Screener
    if base in _SLUG_OVERRIDES:
        return _SLUG_OVERRIDES[base]   # May be None for private companies

    # 2. Search API — try this before guessing, catches odd slug formats
    slug = _search_for_slug(base, session)
    if slug:
        return slug

    # 3. Last resort: try ticker directly (may 404 but we'll handle that in fetch)
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
                    time.sleep(3.0 + attempt * 2.0)
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
            # Strip leading +/- indicators (sub-categories like "+ Mutual Funds")
            label = cells[0].get_text(strip=True).lstrip("+-").strip()
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
                elif "fii" in cat_key or "foreign" in cat_key or "fpi" in cat_key:
                    # FPI = Foreign Portfolio Investors = FII (same category, renamed by SEBI)
                    entry["fii"] = v
                elif ("dii" in cat_key or "domestic" in cat_key) and "mutual" not in cat_key:
                    entry["dii"] = v
                elif "mutual fund" in cat_key or "mutual funds" in cat_key:
                    # Sub-category of DII: individual mutual funds breakdown
                    entry["mutual_funds"] = v
                elif "public" in cat_key:
                    entry["public"] = v
                elif "government" in cat_key or "govt" in cat_key:
                    entry["government"] = v
        results.append(entry)

    # Fill any missing DII by summing known sub-components when scraper gets sub-rows only
    for entry in results:
        if entry.get("dii") is None and entry.get("mutual_funds") is not None:
            entry["dii"] = entry["mutual_funds"]

    return results


def _parse_top_mf_holders(soup: "BeautifulSoup") -> list[dict]:
    """
    Extract top institutional/MF shareholders from the Screener.in shareholding section.
    Screener.in renders a 'Top Shareholders' table in the #shareholding section with
    individual holder names and their %.
    """
    holders: list[dict] = []

    sh_section = soup.find("section", id="shareholding")
    if not sh_section:
        return holders

    # Strategy 1: look for a table that has shareholder names (not the quarterly pattern)
    # The top-shareholders table typically has columns: Name, Shares, %Shares, Quarter
    for table in sh_section.find_all("table"):
        thead = table.find("thead")
        if not thead:
            continue
        header_text = thead.get_text(strip=True).lower()
        # The quarterly table headers are like "Mar 2023 Jun 2023..."
        # The shareholders table has headers like "Name Shares % Shares Quarter" or similar
        if any(kw in header_text for kw in ["name", "shareholder", "holder", "shares"]):
            tbody = table.find("tbody")
            if not tbody:
                continue
            for tr in tbody.find_all("tr")[:10]:
                tds = tr.find_all("td")
                if len(tds) < 2:
                    continue
                name = tds[0].get_text(strip=True)
                # Find the % cell — usually the last or second-to-last column
                pct = None
                for td in reversed(tds[1:]):
                    raw = td.get_text(strip=True)
                    v = _pct_str_to_float(raw)
                    if v is not None and 0 < v <= 100:
                        pct = v
                        break
                if name and pct is not None and len(name) > 2:
                    holders.append({"name": name, "pct": pct, "trend": "unknown"})
            if holders:
                return holders

    # Strategy 2: look for any div/section labelled "Top Shareholders" or "Mutual Funds"
    # and find a list of fund names inside it
    for tag in sh_section.find_all(["h2", "h3", "h4", "th", "span", "b", "strong"]):
        txt = tag.get_text(strip=True).lower()
        if any(kw in txt for kw in ["top shareholder", "top fund", "mutual fund holder",
                                     "institutional holder", "top institution"]):
            parent = tag.find_parent(["table", "div", "section"])
            if not parent:
                continue
            # Find rows in parent
            for tr in parent.find_all("tr")[1:8]:
                tds = tr.find_all("td")
                if len(tds) < 2:
                    continue
                name = tds[0].get_text(strip=True)
                pct = None
                for td in reversed(tds[1:]):
                    raw = td.get_text(strip=True)
                    v = _pct_str_to_float(raw)
                    if v is not None and 0 < v <= 100:
                        pct = v
                        break
                if name and pct is not None and len(name) > 2:
                    holders.append({"name": name, "pct": pct, "trend": "unknown"})
            if holders:
                return holders[:5]

    return holders


def _fetch_screener_data(symbol: str) -> dict:
    """Fetch shareholding pattern from Screener.in."""
    if not HAS_REQUESTS and not HAS_CURL_CFFI:
        return {"error": "requests_unavailable"}

    session = _make_session()
    slug = _resolve_screener_slug(symbol, session)

    # None means explicitly not on Screener (e.g. private company)
    if slug is None:
        return {"error": "not_listed_on_screener", "symbol": symbol}

    if not slug:
        return {"error": "slug_not_found", "symbol": symbol}

    # Small delay to avoid Screener.in rate limiting
        time.sleep(1.0)

    status, html = _fetch_screener_page(slug, session)
    if status != 200 or not html:
        # On 404: try the search API as a last-resort slug fix
        base = _clean_symbol(symbol)
        if base not in _SLUG_OVERRIDES:
            time.sleep(0.5)
            searched_slug = _search_for_slug(base, session)
            if searched_slug and searched_slug != slug:
                time.sleep(0.4)
                status, html = _fetch_screener_page(searched_slug, session)
                if status == 200 and html:
                    slug = searched_slug
        # If still failing, try raw ticker as last resort
        if status != 200:
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
    """
    Fetch institutional holding % and holder lists from yfinance.
    Uses multiple yfinance endpoints for maximum coverage:
    - info: heldPercentInstitutions, heldPercentInsiders
    - major_holders: breakdown table
    - institutional_holders: top institutions with share %
    - mutualfund_holders: top MF schemes with share %
    """
    if not HAS_YFINANCE:
        return {}

    result: dict = {}
    t = None

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            t = yf.Ticker(symbol)
            try:
                info = t.info or {}
            except Exception:
                info = {}
        held_inst    = info.get("heldPercentInstitutions")
        held_insider = info.get("heldPercentInsiders")
        float_shares = info.get("floatShares")
        if held_inst is not None:
            try:
                result["inst_held_pct"] = round(float(held_inst) * 100, 2)
            except Exception:
                pass
        if held_insider is not None:
            try:
                result["insider_held_pct"] = round(float(held_insider) * 100, 2)
            except Exception:
                pass
        result["float_shares"] = float_shares
    except Exception:
        pass

    if t is None:
        return result

    def _pct_col(row, *col_names) -> float | None:
        for col in col_names:
            v = row.get(col)
            if v is None:
                continue
            try:
                fv = float(v)
                # yfinance sometimes returns 0-1 fraction, sometimes 0-100
                return round(fv * 100, 2) if fv <= 1.0 else round(fv, 2)
            except Exception:
                pass
        return None

    # Try institutional holders list
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ih = t.institutional_holders
        if ih is not None and not ih.empty:
            holders = []
            for _, row in ih.head(8).iterrows():
                row_d = row.to_dict()
                name = str(row_d.get("Holder") or row_d.get("holder") or "")
                pct  = _pct_col(row_d, "% Out", "pctHeld", "percentHeld", "% out")
                if name and len(name) > 2 and pct and pct > 0:
                    holders.append({"name": name, "pct": pct, "trend": "unknown"})
            if holders:
                result["top_inst_holders_yf"] = holders
    except Exception:
        pass

    # Try mutual fund holders list
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            mf = t.mutualfund_holders
        if mf is not None and not mf.empty:
            mf_holders = []
            for _, row in mf.head(8).iterrows():
                row_d = row.to_dict()
                name = str(row_d.get("Holder") or row_d.get("holder") or "")
                pct  = _pct_col(row_d, "% Out", "pctHeld", "percentHeld", "% out")
                if name and len(name) > 2 and pct and pct > 0:
                    mf_holders.append({"name": name, "pct": pct, "trend": "unknown"})
            if mf_holders:
                result["top_mf_holders_yf"] = mf_holders
    except Exception:
        pass

    # Try major_holders for India promoter/institution breakdown
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            mh = t.major_holders
        if mh is not None and not mh.empty:
            # major_holders is a 2-col DataFrame: Value | Breakdown
            for _, row in mh.iterrows():
                row_d = row.to_dict()
                vals  = list(row_d.values())
                if len(vals) >= 2:
                    try:
                        pct_val = round(float(vals[0]) * 100, 2)
                        label   = str(vals[1]).lower()
                        if "institution" in label and "inst_held_pct" not in result:
                            result["inst_held_pct"] = pct_val
                        elif "insider" in label and "insider_held_pct" not in result:
                            result["insider_held_pct"] = pct_val
                    except Exception:
                        pass
    except Exception:
        pass

    return result


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
            if not cached_at:
                return None
            age = datetime.now() - datetime.fromisoformat(cached_at)

            has_error = bool(data.get("screener_error") or data.get("error"))
            has_useful_data = bool(
                data.get("quarterly_data")
                or data.get("inst_held_pct") is not None
                or data.get("promoters_pct") is not None
                or data.get("top_mf_holders")
            )

            if has_error and not has_useful_data:
                # Cache pure error/empty results for 2 hours to prevent hammering
                # Screener.in on every run (was the root cause of rate-limiting)
                error_ttl = timedelta(hours=2)
                return data if age < error_ttl else None

            # Good data — use normal TTL. When TTL has expired, return None so
            # fetch() can try for fresh data. If fresh fetch also fails, the
            # "stale-good fallback" in fetch() will preserve this good data.
            if age < self.ttl:
                return data
            return None   # Expired — signal fetch() to try refreshing
        except Exception:
            pass
        return None

    def _load_stale_cache(self, symbol: str) -> dict | None:
        """Load from cache regardless of TTL (stale-ok). Returns data only if it has
        good quarterly data — used to preserve old good data when network is down."""
        p = self._cache_path(symbol)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text())
            if data.get("quarterly_data") and not (data.get("screener_error") or data.get("error")):
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
        """Return full MF/institutional holdings dict for one symbol.

        Honors GROWW_ONLY mode: when on, skips screener.in scrape and
        yfinance institutional fetch for Indian stocks (Groww doesn't
        provide this data, so the panel is simply blank — no silent
        fallback to geo-blocked external sites).
        """
        cached = self._load_cache(symbol)
        if cached:
            return cached

        try:
            from groww_client import should_use_non_groww_source
            _allow_external = should_use_non_groww_source(symbol)
        except Exception:
            _allow_external = True

        result: dict[str, Any] = {"symbol": symbol, "market": market}

        if not _allow_external:
            result.update({
                "screener_slug": None,
                "quarterly_data": [],
                "top_mf_holders": [],
                "screener_error": "groww_only_mode",
                "_hint": ("GROWW_ONLY mode: screener.in + yfinance "
                          "institutional data disabled. Set GROWW_ONLY=0 "
                          "to re-enable."),
            })
            return result

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
        result.update({k: v for k, v in yf_data.items()
                       if k not in ("top_inst_holders_yf", "top_mf_holders_yf")})

        # Use yfinance holder lists as fallback when screener top_mf_holders is empty
        if not result.get("top_mf_holders"):
            yf_holders = (yf_data.get("top_mf_holders_yf")
                          or yf_data.get("top_inst_holders_yf")
                          or [])
            if yf_holders:
                result["top_mf_holders"] = yf_holders
                result["_top_holders_source"] = "yfinance"

        # ── Derive metrics ─────────────────────────────────────────────────
        qdata  = result.get("quarterly_data", [])

        # Use quarters that have ANY shareholding data (not just dii) — small-caps
        # often have no DII row but still have Promoters / FII / Public
        def _has_any_data(q: dict) -> bool:
            return any(q.get(k) is not None for k in ("dii", "fii", "promoters", "public"))

        recent = [q for q in qdata if _has_any_data(q)][-8:]
        latest = recent[-1] if recent else {}
        prev   = recent[-3] if len(recent) >= 3 else (recent[0] if recent else {})

        promoters_pct    = latest.get("promoters")
        fii_pct          = latest.get("fii")
        dii_pct          = latest.get("dii")
        public_pct       = latest.get("public")
        govt_pct         = latest.get("government")
        mutual_funds_pct = latest.get("mutual_funds")   # DII sub-component

        promoters_trend = _trend(promoters_pct, prev.get("promoters"))
        fii_trend       = _trend(fii_pct, prev.get("fii"))
        dii_trend       = _trend(dii_pct, prev.get("dii"))

        # Absolute 2Q changes for the display
        fii_change_2q = round(fii_pct - prev.get("fii"), 2) if (
            fii_pct is not None and prev.get("fii") is not None) else None
        dii_change_2q = round(dii_pct - prev.get("dii"), 2) if (
            dii_pct is not None and prev.get("dii") is not None) else None

        result["promoters_pct"]    = promoters_pct
        result["fii_pct"]          = fii_pct
        result["dii_pct"]          = dii_pct
        result["public_pct"]       = public_pct
        result["govt_pct"]         = govt_pct
        result["mutual_funds_pct"] = mutual_funds_pct
        result["promoters_trend"]  = promoters_trend
        result["fii_trend"]        = fii_trend
        result["dii_trend"]        = dii_trend
        result["fii_change_2q"]    = fii_change_2q
        result["dii_change_2q"]    = dii_change_2q
        result["latest_period"]    = latest.get("period", "")

        # ── Smart money signal ─────────────────────────────────────────────
        dii_accumulating = dii_trend == "up"
        fii_accumulating = fii_trend == "up"
        result["dii_accumulating"] = dii_accumulating
        result["fii_accumulating"] = fii_accumulating

        inst_pct = result.get("inst_held_pct")
        has_dii  = dii_pct is not None
        has_fii  = fii_pct is not None
        has_data = has_dii or has_fii

        # Promoter-held small-cap: no FII/DII data at all
        has_promoter_only = (promoters_pct is not None and not has_data)

        if not has_data and not has_promoter_only and inst_pct is not None:
            # Derive a basic signal from yfinance institutional %
            if inst_pct >= 30:
                signal     = "INST_HIGH"
                swing_text = f"ℹ️ High institutional ownership: {inst_pct:.1f}% (yfinance, of float)"
            elif inst_pct >= 10:
                signal     = "NEUTRAL"
                swing_text = f"→ Institutional ownership: {inst_pct:.1f}% (yfinance, of float)"
            else:
                signal     = "UNKNOWN"
                swing_text = "ℹ️ Limited institutional ownership data"
        elif has_promoter_only and (promoters_pct or 0) >= 60:
            signal     = "PROMOTER_HELD"
            swing_text = f"🏢 Promoter-held {promoters_pct:.1f}% — low FII/DII activity (small-cap)"
        elif dii_accumulating and fii_accumulating:
            signal     = "STRONG_BUYING"
            swing_text = "🔥 STRONG BUYING — Both DIIs & FIIs accumulating"
        elif dii_accumulating:
            chg = f" (+{dii_change_2q:.1f}% in 2Q)" if dii_change_2q and dii_change_2q > 0 else ""
            signal     = "DII_ACCUMULATING"
            swing_text = f"👍 DIIs accumulating ↑{chg} (smart money buying)"
        elif fii_accumulating:
            chg = f" (+{fii_change_2q:.1f}% in 2Q)" if fii_change_2q and fii_change_2q > 0 else ""
            signal     = "FII_ACCUMULATING"
            swing_text = f"👍 FIIs accumulating ↑{chg} (foreign buying)"
        elif fii_trend == "down" and has_dii and dii_trend == "down":
            signal     = "DISTRIBUTING"
            swing_text = "⚠️ Institutions distributing — both FIIs & DIIs selling"
        elif fii_trend == "down" and has_fii:
            chg = f" ({fii_change_2q:.1f}% in 2Q)" if fii_change_2q else ""
            signal     = "FII_SELLING"
            swing_text = f"⚠️ FIIs selling ↓{chg} — watch for follow-through"
        elif has_data:
            signal     = "NEUTRAL"
            swing_text = "→ Institutional ownership stable"
        elif has_promoter_only:
            signal     = "PROMOTER_HELD"
            swing_text = f"🏢 Promoter-held {promoters_pct:.1f}% — limited institutional data"
        else:
            signal     = "UNKNOWN"
            swing_text = "ℹ️ No shareholding data available"

        result["smart_money_signal"] = signal
        result["swing_signal"]       = swing_text

        # ── Compact summary (with proper spaces) ──────────────────────────
        parts: list[str] = []
        if dii_pct is not None:
            chg = f" ({dii_change_2q:+.1f}%)" if dii_change_2q is not None else ""
            parts.append(f"DIIs {_trend_emoji(dii_trend)} {dii_pct:.1f}%{chg}")
        if fii_pct is not None:
            chg = f" ({fii_change_2q:+.1f}%)" if fii_change_2q is not None else ""
            parts.append(f"FIIs {_trend_emoji(fii_trend)} {fii_pct:.1f}%{chg}")
        if promoters_pct is not None:
            parts.append(f"Promoters {_trend_emoji(promoters_trend)} {promoters_pct:.1f}%")
        if not parts and inst_pct is not None:
            parts.append(f"Inst {inst_pct:.1f}% (float)")
        result["summary"] = " | ".join(parts) if parts else "—"
        result["_source"] = "screener+yfinance"

        # ── Stale-good fallback ────────────────────────────────────────────
        # If current fetch failed (screener error, no useful data), check if
        # we have older cached data with quarterly info and reuse it.
        # This preserves data from successful runs when screener.in is temporarily down.
        screener_failed = bool(result.get("screener_error"))
        fresh_has_data  = bool(result.get("quarterly_data") or result.get("promoters_pct") is not None)
        if screener_failed and not fresh_has_data:
            stale = self._load_stale_cache(symbol)
            if stale:
                logger.debug("Using stale-good cache for %s (screener error: %s)",
                             symbol, result.get("screener_error"))
                # Re-stamp the cache time to prevent immediate re-fetch next run
                stale["_cached_at"] = datetime.now().isoformat()
                stale["_stale_reused"] = True
                self._save_cache(symbol, stale)
                return stale

        self._save_cache(symbol, result)
        return result

    def fetch_batch(
        self,
        symbols: list[str],
        market: str = "india",
        workers: int = 2,          # very conservative — Screener.in rate-limits hard
    ) -> dict[str, dict]:
        """Parallel fetch for a list of symbols. Uses throttled workers."""
        total = len(symbols)
        if total == 0:
            return {}

        needs_fetch  = [s for s in symbols if self._load_cache(s) is None]
        out: dict    = {s: self._load_cache(s) for s in symbols if s not in needs_fetch}

        if not needs_fetch:
            return out

        # Cap workers to avoid Screener.in rate limiting (2 is safe, 1 is safest)
        safe_workers = min(workers, 2, len(needs_fetch))

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

    def _has_any(q: dict) -> bool:
        return any(q.get(k) is not None for k in ("dii", "fii", "promoters", "public"))

    recent = [q for q in qdata if _has_any(q)][-8:]

    dii_values = [q["dii"] for q in recent if q.get("dii") is not None]
    fii_values = [q.get("fii") for q in recent if q.get("fii") is not None]

    quarters_dii_increasing = sum(
        1 for i in range(1, len(dii_values)) if dii_values[i] > dii_values[i - 1]
    ) if dii_values else 0

    dii_change_3q = round(dii_values[-1] - dii_values[-4], 2) if len(dii_values) >= 4 else None
    dii_change_2q = round(dii_values[-1] - dii_values[-3], 2) if len(dii_values) >= 3 else None
    fii_change_2q = round(fii_values[-1] - fii_values[-3], 2) if len(fii_values) >= 3 else None
    fii_change_3q = round(fii_values[-1] - fii_values[-4], 2) if len(fii_values) >= 4 else None

    signal = data.get("smart_money_signal", "UNKNOWN")

    if signal == "STRONG_BUYING" and (dii_change_3q or 0) > 1.0:
        conviction = "HIGH"
    elif signal in ("DII_ACCUMULATING", "FII_ACCUMULATING", "STRONG_BUYING", "INST_HIGH"):
        conviction = "MEDIUM"
    elif signal in ("DISTRIBUTING", "FII_SELLING"):
        conviction = "LOW"
    elif signal == "PROMOTER_HELD":
        conviction = "NEUTRAL"
    elif signal == "NEUTRAL":
        conviction = "NEUTRAL"
    else:
        conviction = "LOW"

    # Build quarterly trend bar data (last 6 quarters)
    dii_trend_history = [
        {"period": q.get("period", ""), "dii": q.get("dii"), "fii": q.get("fii"),
         "promoters": q.get("promoters"), "public": q.get("public")}
        for q in recent[-6:]
    ]

    return {
        "signal":                  signal,
        "text":                    data.get("swing_signal", ""),
        "summary":                 data.get("summary", "—"),
        "promoters":               {"pct": data.get("promoters_pct"), "trend": data.get("promoters_trend", "stable")},
        "fii":                     {"pct": data.get("fii_pct"),       "trend": data.get("fii_trend", "stable"),
                                    "change_2q": data.get("fii_change_2q")},
        "dii":                     {"pct": data.get("dii_pct"),       "trend": data.get("dii_trend", "stable"),
                                    "change_2q": data.get("dii_change_2q")},
        "public":                  {"pct": data.get("public_pct")},
        "govt":                    {"pct": data.get("govt_pct")},
        "mutual_funds_pct":        data.get("mutual_funds_pct"),
        "inst_held_pct":           data.get("inst_held_pct"),
        "top_mf":                  data.get("top_mf_holders", []),
        "latest_period":           data.get("latest_period", ""),
        "quarters_dii_increasing": quarters_dii_increasing,
        "dii_change_3q":           dii_change_3q,
        "dii_change_2q":           dii_change_2q,
        "fii_change_2q":           fii_change_2q,
        "fii_change_3q":           fii_change_3q,
        "dii_trend_history":       dii_trend_history,
        "conviction":              conviction,
        "screener_error":          data.get("screener_error"),
        "_top_holders_source":     data.get("_top_holders_source"),
    }

