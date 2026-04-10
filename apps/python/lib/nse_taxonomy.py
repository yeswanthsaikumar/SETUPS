"""
nse_taxonomy.py
───────────────
Single source of truth for NSE stock sector / industry classification.

Usage:
    from nse_taxonomy import get_sector, get_industry, get_breadth_peers

Loading priority:
  1. CSV master file  data/nse_stock_taxonomy.csv  (editable, version-controlled)
  2. Hardcoded fallback maps in this file (always available, no I/O)
  3. yfinance info.sector / info.industry  (live fallback for unknown tickers)

Design goals:
  - 2-level taxonomy: SECTOR (broad, ~20) → INDUSTRY (sub-sector, ~100-120)
  - Peers in the same INDUSTRY move together → use for breadth / rally detection
  - Editable via CSV without touching Python
  - Auto-classify unknowns via yfinance with caching
"""
from __future__ import annotations

import csv
import json
import logging
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger("NSETaxonomy")

_ROOT      = Path(__file__).resolve().parents[3]   # SETUPS/
_CSV_PATH  = _ROOT / "data" / "nse_stock_taxonomy.csv"
_AUTO_CACHE= _ROOT / "cache" / "auto_classify_cache.json"

# ── yfinance → our taxonomy mapping ──────────────────────────────────────────
# When yfinance returns its own sector/industry, map it to our vocabulary.
_YF_SECTOR_MAP: dict[str, str] = {
    "Technology":              "IT",
    "Healthcare":              "Pharma",
    "Financial Services":      "Financials",
    "Basic Materials":         "Chemicals",
    "Consumer Cyclical":       "Consumer",
    "Consumer Defensive":      "FMCG",
    "Industrials":             "Cap Goods",
    "Energy":                  "Energy",
    "Utilities":               "Energy",
    "Real Estate":             "RealEstate",
    "Communication Services":  "Internet",
}

_YF_INDUSTRY_MAP: dict[str, str] = {
    "Steel":                           "Steel",
    "Specialty Chemicals":             "Specialty Chemicals",
    "Drug Manufacturers—General":      "Pharma Formulations",
    "Drug Manufacturers—Specialty & Generic": "Pharma Formulations",
    "Pharmaceutical Retailers":        "Pharmacy Retail",
    "Diagnostics & Research":          "Diagnostics",
    "Medical Devices":                 "Medical Devices",
    "Hospitals":                       "Hospitals",
    "Banks—Regional":                  "Private Banks",
    "Banks—Diversified":               "PSU Banks",
    "Asset Management":                "Asset Management",
    "Capital Markets":                 "Capital Markets",
    "Insurance—Life":                  "Life Insurance",
    "Insurance—Specialty":             "Health Insurance",
    "Software—Application":            "IT Services",
    "Software—Infrastructure":         "IT Services",
    "Information Technology Services": "IT Services",
    "Electronic Components":           "Electronic Components",
    "Semiconductors":                  "Electronic Components",
    "Auto Manufacturers":              "Auto OEM - 4W",
    "Auto Parts":                      "Auto Ancillaries",
    "Aerospace & Defense":             "Aerospace & Defense",
    "Electrical Equipment & Parts":    "Electrical Equipment",
    "Industrial Distribution":         "Cap Goods",
    "Packaged Foods":                  "FMCG - Foods",
    "Household & Personal Products":   "FMCG - Personal Care",
    "Oil & Gas Integrated":            "Oil & Gas",
    "Oil & Gas Refining & Marketing":  "Oil Refining",
    "Utilities—Regulated Electric":    "Power Generation",
    "Utilities—Renewable":             "Renewable Energy",
    "Real Estate—Development":         "Real Estate - Residential",
    "REIT—Diversified":                "Real Estate - Residential",
}


# ── Hardcoded fallback maps ───────────────────────────────────────────────────
# These are always available and are the baseline.
# If nse_stock_taxonomy.csv exists, it OVERRIDES these entries.
# Keep in sync with generate_trade_plans_page.py until Phase 3 migration.

_FALLBACK_SECTOR: dict[str, str] = {
    # Banking
    "HDFCBANK":"Banking","ICICIBANK":"Banking","SBIN":"Banking","AXISBANK":"Banking",
    "KOTAKBANK":"Banking","INDUSINDBK":"Banking","BANDHANBNK":"Banking",
    "FEDERALBNK":"Banking","IDFCFIRSTB":"Banking","AUBANK":"Banking",
    "CANBK":"Banking","BANKBARODA":"Banking","PNB":"Banking",
    "UNIONBANK":"Banking","IDBI":"Banking","RBLBANK":"Banking",
    "DCBBANK":"Banking","KTKBANK":"Banking","KARURVYSYA":"Banking",
    "ESAFSFB":"Banking","SURYODAY":"Banking","UJJIVAN":"Banking",
    "EQUITASBNK":"Banking","UTKARSHBNK":"Banking","JANA":"Banking",
    # (see generate_trade_plans_page.py for full list — will be replaced by CSV)
}

_FALLBACK_INDUSTRY: dict[str, str] = {
    "SBIN":"PSU Banks","CANBK":"PSU Banks","BANKBARODA":"PSU Banks",
    "PNB":"PSU Banks","UNIONBANK":"PSU Banks","IDBI":"PSU Banks",
    "HDFCBANK":"Private Banks","ICICIBANK":"Private Banks","AXISBANK":"Private Banks",
    "KOTAKBANK":"Private Banks","INDUSINDBK":"Private Banks",
    "FEDERALBNK":"Private Banks","IDFCFIRSTB":"Private Banks","RBLBANK":"Private Banks",
    "BANDHANBNK":"Small Finance Banks","AUBANK":"Small Finance Banks",
    "ESAFSFB":"Small Finance Banks","SURYODAY":"Small Finance Banks",
    "UJJIVAN":"Small Finance Banks","EQUITASBNK":"Small Finance Banks",
    # (see generate_trade_plans_page.py for full list — will be replaced by CSV)
}


# ── Map loading ───────────────────────────────────────────────────────────────

def _load_from_csv(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Load sector + industry maps from the master CSV file."""
    sector_map:   dict[str, str] = {}
    industry_map: dict[str, str] = {}
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ticker   = row.get("nse_ticker", "").strip().upper()
                sector   = row.get("sector",   "").strip()
                industry = row.get("industry", "").strip()
                if ticker and sector:
                    sector_map[ticker]   = sector
                if ticker and industry:
                    industry_map[ticker] = industry
    except Exception as e:
        logger.warning("Could not load taxonomy CSV %s: %s", path, e)
    return sector_map, industry_map


def _build_maps() -> tuple[dict[str, str], dict[str, str]]:
    """Return (sector_map, industry_map) — CSV overrides hardcoded fallbacks."""
    sec  = dict(_FALLBACK_SECTOR)
    ind  = dict(_FALLBACK_INDUSTRY)
    if _CSV_PATH.exists():
        csv_sec, csv_ind = _load_from_csv(_CSV_PATH)
        sec.update(csv_sec)
        ind.update(csv_ind)
        logger.debug("Loaded %d sectors, %d industries from CSV", len(csv_sec), len(csv_ind))
    return sec, ind


# Module-level maps — loaded once at import time
_SECTOR_MAP, _INDUSTRY_MAP = _build_maps()


# ── Public API ────────────────────────────────────────────────────────────────

def _clean(symbol: str) -> str:
    return symbol.replace(".NS", "").replace(".BO", "").strip().upper()


def get_sector(symbol: str) -> str:
    """Return the broad sector for an NSE ticker. Falls back to 'Other'."""
    return _SECTOR_MAP.get(_clean(symbol), "Other")


def get_industry(symbol: str) -> str:
    """Return the sub-industry for an NSE ticker. Falls back to sector or 'Other'."""
    base = _clean(symbol)
    return _INDUSTRY_MAP.get(base, _SECTOR_MAP.get(base, "Other"))


def get_breadth_peers(industry: str) -> list[str]:
    """Return all NSE tickers in the same industry (for breadth computation)."""
    return [ticker for ticker, ind in _INDUSTRY_MAP.items() if ind == industry]


def list_industries() -> list[str]:
    """Return all unique industry names."""
    return sorted(set(_INDUSTRY_MAP.values()))


def list_sectors() -> list[str]:
    """Return all unique sector names."""
    return sorted(set(_SECTOR_MAP.values()))


def get_industry_sector_map() -> dict[str, str]:
    """Return industry → sector mapping (for grouping industries in UI)."""
    result: dict[str, str] = {}
    for ticker, ind in _INDUSTRY_MAP.items():
        if ind not in result:
            result[ind] = _SECTOR_MAP.get(ticker, "Other")
    return result


# ── Auto-classify via yfinance (fallback for unknown tickers) ─────────────────

def _load_auto_cache() -> dict[str, dict]:
    try:
        return json.loads(_AUTO_CACHE.read_text())
    except Exception:
        return {}


def _save_auto_cache(cache: dict) -> None:
    try:
        _AUTO_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _AUTO_CACHE.write_text(json.dumps(cache, indent=2))
    except Exception:
        pass


def auto_classify(symbol: str) -> tuple[str, str]:
    """
    For stocks not in the manual map, try yfinance info.sector / industry.
    Results are cached to disk to avoid repeated API calls.

    Returns (sector, industry) — both default to 'Other' on failure.
    """
    base = _clean(symbol)
    # Check manual map first
    if base in _SECTOR_MAP:
        return _SECTOR_MAP[base], _INDUSTRY_MAP.get(base, _SECTOR_MAP[base])

    # Check auto-cache
    cache = _load_auto_cache()
    if base in cache:
        c = cache[base]
        return c.get("sector", "Other"), c.get("industry", "Other")

    # Try yfinance
    try:
        import yfinance as yf
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            info = yf.Ticker(symbol).info or {}
        yf_sector   = info.get("sector", "")
        yf_industry = info.get("industry", "")
        sector   = _YF_SECTOR_MAP.get(yf_sector,   "Other")
        industry = _YF_INDUSTRY_MAP.get(yf_industry, sector)
        result = {"sector": sector, "industry": industry,
                  "yf_sector": yf_sector, "yf_industry": yf_industry,
                  "auto_classified": True}
        cache[base] = result
        _save_auto_cache(cache)
        logger.debug("Auto-classified %s → %s / %s (yfinance)", symbol, sector, industry)
        return sector, industry
    except Exception:
        return "Other", "Other"


# ── Market breadth computation (Phase 4) ─────────────────────────────────────

def compute_industry_breadth(
    industry: str,
    price_data: dict[str, list[dict]],  # symbol → list of OHLCV dicts
    ma_periods: tuple[int, int, int] = (20, 50, 200),
) -> dict:
    """
    Compute % of stocks in an industry above various moving averages.

    Args:
        industry:   Industry name
        price_data: Dict of symbol → list of daily OHLCV row dicts
        ma_periods: Tuple of MA lengths to compute breadth for

    Returns:
        {
          "industry": str,
          "stock_count": int,
          "pct_above_20ma": float,
          "pct_above_50ma": float,
          "pct_above_200ma": float,
          "pct_at_52wh": float,       # % within 5% of 52W high
          "breadth_score": float,     # composite 0–100
        }
    """
    peers = get_breadth_peers(industry)
    peers_with_data = [p for p in peers if p in price_data and price_data[p]]
    n = len(peers_with_data)

    if n == 0:
        return {"industry": industry, "stock_count": 0, "breadth_score": 0.0}

    above: dict[int, int] = {p: 0 for p in ma_periods}
    at_52wh = 0

    for sym in peers_with_data:
        rows  = price_data[sym]
        closes = [float(r.get("close", 0)) for r in rows if r.get("close")]
        if not closes:
            continue
        last = closes[-1]

        for period in ma_periods:
            if len(closes) >= period:
                ma = sum(closes[-period:]) / period
                if last > ma:
                    above[period] += 1

        # 52W high = max of last 252 sessions
        high_52w = max(closes[-252:]) if len(closes) >= 252 else max(closes)
        if last >= high_52w * 0.95:   # within 5% of 52W high
            at_52wh += 1

    pct = {p: round(above[p] / n * 100, 1) for p in ma_periods}
    # Composite breadth score: weighted average
    short_p, mid_p, long_p = ma_periods
    score = (pct[short_p] * 0.3 + pct[mid_p] * 0.4 + pct[long_p] * 0.3)

    return {
        "industry":        industry,
        "stock_count":     n,
        f"pct_above_{short_p}ma": pct[short_p],
        f"pct_above_{mid_p}ma":  pct[mid_p],
        f"pct_above_{long_p}ma": pct[long_p],
        "pct_at_52wh":     round(at_52wh / n * 100, 1),
        "breadth_score":   round(score, 1),
    }


def compute_all_industry_breadth(
    price_data: dict[str, list[dict]],
    min_stocks: int = 3,
) -> list[dict]:
    """
    Compute breadth for ALL industries that have >= min_stocks with price data.
    Returns list sorted by breadth_score descending.
    """
    industries = list_industries()
    results = []
    for ind in industries:
        bd = compute_industry_breadth(ind, price_data)
        if bd.get("stock_count", 0) >= min_stocks:
            results.append(bd)
    return sorted(results, key=lambda x: -x.get("breadth_score", 0))


# ── Smart money flow by industry (Phase 4c) ───────────────────────────────────

def industry_smart_money(
    industry: str,
    mf_data: dict[str, dict],  # symbol → MF holdings dict from MutualFundsProvider
) -> dict:
    """
    Aggregate FII/DII trends across all stocks in an industry.

    Returns:
        {
          "industry": str,
          "stocks_tracked": int,
          "dii_accumulating": int,    # count with dii_trend == "up"
          "fii_accumulating": int,    # count with fii_trend == "up"
          "avg_dii_change_2q": float, # average DII % change over 2 quarters
          "avg_fii_change_2q": float,
          "conviction": str,          # HIGH / MEDIUM / LOW / NEUTRAL
          "signal": str,              # STRONG_BUYING / DII_ACC / FII_ACC / NEUTRAL / DISTRIBUTING
        }
    """
    peers = get_breadth_peers(industry)
    tracked = [p for p in peers if p in mf_data and mf_data[p]]
    n = len(tracked)
    if n == 0:
        return {"industry": industry, "stocks_tracked": 0, "conviction": "NEUTRAL",
                "signal": "NO_DATA"}

    dii_acc  = sum(1 for s in tracked if mf_data[s].get("dii_trend") == "up")
    fii_acc  = sum(1 for s in tracked if mf_data[s].get("fii_trend") == "up")

    dii_changes = [mf_data[s]["dii_change_2q"] for s in tracked
                   if mf_data[s].get("dii_change_2q") is not None]
    fii_changes = [mf_data[s]["fii_change_2q"] for s in tracked
                   if mf_data[s].get("fii_change_2q") is not None]

    avg_dii = round(sum(dii_changes) / len(dii_changes), 2) if dii_changes else None
    avg_fii = round(sum(fii_changes) / len(fii_changes), 2) if fii_changes else None

    dii_ratio = dii_acc / n
    fii_ratio = fii_acc / n

    if dii_ratio >= 0.6 and fii_ratio >= 0.6:
        signal, conviction = "STRONG_BUYING", "HIGH"
    elif dii_ratio >= 0.5:
        signal, conviction = "DII_ACCUMULATING", "MEDIUM"
    elif fii_ratio >= 0.5:
        signal, conviction = "FII_ACCUMULATING", "MEDIUM"
    elif dii_ratio < 0.3 and fii_ratio < 0.3:
        signal, conviction = "DISTRIBUTING", "LOW"
    else:
        signal, conviction = "NEUTRAL", "NEUTRAL"

    return {
        "industry":          industry,
        "stocks_tracked":    n,
        "dii_accumulating":  dii_acc,
        "fii_accumulating":  fii_acc,
        "avg_dii_change_2q": avg_dii,
        "avg_fii_change_2q": avg_fii,
        "dii_ratio":         round(dii_ratio, 2),
        "fii_ratio":         round(fii_ratio, 2),
        "signal":            signal,
        "conviction":        conviction,
    }

