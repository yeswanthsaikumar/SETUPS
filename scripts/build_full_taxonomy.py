#!/usr/bin/env python3
"""
build_full_taxonomy.py
──────────────────────
Build a COMPLETE NSE stock taxonomy covering ALL stocks in the cache directory.

Sources (in priority order):
  1. Existing nse_stock_taxonomy.csv (preserve manual classifications)
  2. NSE EQUITY_L.csv (official listing with ISIN + series)
  3. NSE sectoral index constituents (Nifty Bank, IT, Pharma, etc.)
  4. yfinance info.sector / info.industry (batch fallback)
  5. Smart name-based heuristic classification

Output: data/nse_stock_taxonomy.csv (overwritten with full coverage)
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
import warnings
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
DATA_DIR = ROOT / "data"
TAXONOMY_CSV = DATA_DIR / "nse_stock_taxonomy.csv"
AUTO_CACHE = CACHE_DIR / "auto_classify_cache.json"

# ── Sector / industry vocabulary ────────────────────────────────────────────
# Our standard 2-level taxonomy

YF_SECTOR_MAP = {
    "Technology": "IT",
    "Healthcare": "Pharma",
    "Financial Services": "Financials",
    "Basic Materials": "Chemicals",
    "Consumer Cyclical": "Consumer",
    "Consumer Defensive": "FMCG",
    "Industrials": "Cap Goods",
    "Energy": "Energy",
    "Utilities": "Energy",
    "Real Estate": "RealEstate",
    "Communication Services": "Internet",
}

YF_INDUSTRY_MAP = {
    # Technology
    "Software—Application": "IT Services",
    "Software—Infrastructure": "IT Services",
    "Information Technology Services": "IT Services",
    "Electronic Components": "Electronic Components",
    "Semiconductors": "Semiconductors",
    "Computer Hardware": "IT Hardware",
    "Scientific & Technical Instruments": "Electronic Components",
    "Communication Equipment": "Telecom Equipment",
    "Solar": "Renewable Energy",
    # Healthcare
    "Drug Manufacturers—General": "Pharma Formulations",
    "Drug Manufacturers—Specialty & Generic": "Pharma Formulations",
    "Pharmaceutical Retailers": "Pharmacy Retail",
    "Diagnostics & Research": "Diagnostics",
    "Medical Devices": "Medical Devices",
    "Medical Instruments & Supplies": "Medical Devices",
    "Hospitals": "Hospitals",
    "Health Information Services": "IT - Healthcare",
    "Biotechnology": "Biotech",
    # Financials
    "Banks—Regional": "Private Banks",
    "Banks—Diversified": "PSU Banks",
    "Asset Management": "Asset Management",
    "Capital Markets": "Capital Markets",
    "Insurance—Life": "Life Insurance",
    "Insurance—Specialty": "Health Insurance",
    "Insurance—Property & Casualty": "General Insurance",
    "Insurance Brokers": "Insurance",
    "Financial Data & Stock Exchanges": "Stock Exchanges",
    "Credit Services": "NBFC",
    "Mortgage Finance": "Housing Finance",
    "Insurance—Diversified": "General Insurance",
    # Industrials
    "Aerospace & Defense": "Aerospace & Defense",
    "Electrical Equipment & Parts": "Electrical Equipment",
    "Specialty Industrial Machinery": "Cap Goods",
    "Farm & Heavy Construction Machinery": "Cap Goods",
    "Industrial Distribution": "Trading",
    "Engineering & Construction": "Construction - Infra",
    "Building Products & Equipment": "Building Materials",
    "Railroads": "Railways",
    "Marine Shipping": "Shipping",
    "Trucking": "Logistics",
    "Integrated Freight & Logistics": "Logistics",
    "Airports & Air Services": "Aviation",
    "Airlines": "Aviation",
    "Waste Management": "Environment Services",
    "Metal Fabrication": "Cap Goods",
    "Conglomerates": "Conglomerates",
    "Rental & Leasing Services": "Leasing",
    "Staffing & Employment Services": "Staffing",
    "Security & Protection Services": "Security Services",
    "Consulting Services": "Consulting",
    # Materials
    "Steel": "Steel",
    "Specialty Chemicals": "Specialty Chemicals",
    "Chemicals": "Chemicals",
    "Agricultural Inputs": "Agrochemicals",
    "Aluminum": "Non-Ferrous Metals",
    "Copper": "Non-Ferrous Metals",
    "Other Industrial Metals & Mining": "Mining",
    "Gold": "Gold & Precious Metals",
    "Paper & Paper Products": "Paper",
    "Lumber & Wood Production": "Wood & Plywood",
    "Cement": "Cement",
    "Building Materials": "Building Materials",
    "Coking Coal": "Mining",
    # Consumer Cyclical
    "Auto Manufacturers": "Auto OEM - 4W",
    "Auto Parts": "Auto Ancillaries",
    "Residential Construction": "Real Estate - Residential",
    "Textile Manufacturing": "Textiles",
    "Apparel Manufacturing": "Textiles",
    "Footwear & Accessories": "Footwear",
    "Luxury Goods": "Consumer Durables",
    "Home Improvement Retail": "Retail",
    "Specialty Retail": "Retail",
    "Internet Retail": "E-Commerce",
    "Restaurants": "Hotels & Restaurants",
    "Lodging": "Hotels & Restaurants",
    "Resorts & Casinos": "Hotels & Restaurants",
    "Personal Services": "Consumer Services",
    "Leisure": "Media & Entertainment",
    "Gambling": "Media & Entertainment",
    "Packaging & Containers": "Packaging",
    "Furnishings, Fixtures & Appliances": "Consumer Durables",
    "Home Furnishings & Fixtures": "Consumer Durables",
    "Department Stores": "Retail",
    "Apparel Retail": "Retail - Apparel",
    # Consumer Defensive
    "Packaged Foods": "FMCG - Foods",
    "Confectioners": "FMCG - Foods",
    "Beverages—Non-Alcoholic": "FMCG - Beverages",
    "Beverages—Brewers": "Alcoholic Beverages",
    "Beverages—Wineries & Distilleries": "Alcoholic Beverages",
    "Household & Personal Products": "FMCG - Personal Care",
    "Tobacco": "Tobacco",
    "Farm Products": "Agri",
    "Food Distribution": "Agri",
    "Education & Training Services": "Education",
    "Grocery Stores": "Retail - Grocery",
    "Discount Stores": "Retail",
    # Energy
    "Oil & Gas Integrated": "Oil & Gas",
    "Oil & Gas E&P": "Oil & Gas - Exploration",
    "Oil & Gas Refining & Marketing": "Oil Refining",
    "Oil & Gas Equipment & Services": "Oil & Gas - Services",
    "Oil & Gas Midstream": "Oil & Gas - Pipelines",
    "Thermal Coal": "Coal",
    "Uranium": "Nuclear Energy",
    # Utilities
    "Utilities—Regulated Electric": "Power Generation",
    "Utilities—Renewable": "Renewable Energy",
    "Utilities—Independent Power Producers": "Power Generation",
    "Utilities—Diversified": "Power - Transmission",
    "Utilities—Regulated Gas": "Gas Distribution",
    "Utilities—Regulated Water": "Water Utilities",
    # Real Estate
    "Real Estate—Development": "Real Estate - Residential",
    "Real Estate—Diversified": "Real Estate - Commercial",
    "Real Estate Services": "Real Estate - Commercial",
    "REIT—Diversified": "REITs",
    "REIT—Office": "REITs",
    "REIT—Residential": "REITs",
    # Communication
    "Telecom Services": "Telecom",
    "Internet Content & Information": "Internet",
    "Entertainment": "Media & Entertainment",
    "Electronic Gaming & Multimedia": "Media & Entertainment",
    "Broadcasting": "Media & Entertainment",
    "Advertising Agencies": "Advertising",
    "Publishing": "Media & Entertainment",
}

# ── Name-based heuristic rules ──────────────────────────────────────────────
# When yfinance fails, try to guess from the company name / ticker
NAME_RULES: list[tuple[str, str, str]] = [
    # (pattern, sector, industry)
    (r"(?i)pharma|drug|lab|biotech|health|medic|diag|thera|oncol|life.?sci", "Pharma", "Pharma"),
    (r"(?i)bank|fin\.?\s*serv|nbfc|micro.?fin", "Financials", "NBFC"),
    (r"(?i)insur", "Financials", "Insurance"),
    (r"(?i)hous.?fin|home.?fin|mortgage", "Financials", "Housing Finance"),
    (r"(?i)gold|silver|jewel|bullion", "Metals", "Gold & Precious Metals"),
    (r"(?i)steel|iron|metal|alloy|ferro|casting|forg", "Metals", "Steel"),
    (r"(?i)alum", "Metals", "Non-Ferrous Metals"),
    (r"(?i)copper|zinc|nickel|lead|tin", "Metals", "Non-Ferrous Metals"),
    (r"(?i)mine|mining|mineral", "Metals", "Mining"),
    (r"(?i)cement|concr|build.?mat|lime|gyps", "Cement", "Cement"),
    (r"(?i)chem|petro.?chem|polymer|solvent|dye|pigment|resin", "Chemicals", "Chemicals"),
    (r"(?i)agro.?chem|fert|pesti|insect|seed", "Chemicals", "Agrochemicals"),
    (r"(?i)power|energy|electr|generat|transmis|renew|solar|wind|hydro", "Energy", "Power Generation"),
    (r"(?i)oil|gas|petrol|refin|lubric|crude", "Energy", "Oil & Gas"),
    (r"(?i)coal|lignite", "Energy", "Coal"),
    (r"(?i)auto|motor|vehic|tractor|wheel|tyre|tire|brake", "Auto", "Auto Ancillaries"),
    (r"(?i)infra|construct|engineer|road|highway|bridge|tunnel|rail|metro", "Infra", "Construction - Infra"),
    (r"(?i)real.?est|realty|hous|property|township", "RealEstate", "Real Estate - Residential"),
    (r"(?i)hotel|hospit|tourism|travel|resort|leisure", "Consumer", "Hotels & Restaurants"),
    (r"(?i)textile|cotton|yarn|fabric|garment|apparel|silk|wool|denim", "Textiles", "Textiles"),
    (r"(?i)sugar", "FMCG", "Sugar"),
    (r"(?i)food|dairy|edible|biscuit|confect|beverage|juice|tea|coffee", "FMCG", "FMCG - Foods"),
    (r"(?i)paper|pulp|print|packag", "Paper", "Paper"),
    (r"(?i)plast|pvc|pipe|polym|tube|hose", "Chemicals", "Plastics & Pipes"),
    (r"(?i)it\s|software|infotech|tech.?sol|digital|data|cloud|cyber|consult", "IT", "IT Services"),
    (r"(?i)telecom|comm.?net|fiber|broadband|tower|5g", "Telecom", "Telecom"),
    (r"(?i)media|entertain|film|broadcast|advertis|news", "Media", "Media & Entertainment"),
    (r"(?i)retail|mart|store|shop|e.?comm", "Consumer", "Retail"),
    (r"(?i)logist|transport|freight|shipping|courier|cargo|port|warehous", "Logistics", "Logistics"),
    (r"(?i)defence|defens|weapon|ammo|missile|naval|armour", "Defence", "Aerospace & Defense"),
    (r"(?i)educat|learn|school|university|tutor|coachi", "Consumer", "Education"),
    (r"(?i)ceramic|tile|sanit|glass|marble|granite", "Building Materials", "Building Materials"),
    (r"(?i)jewel|gem|diamond", "Consumer", "Gems & Jewellery"),
    (r"(?i)tobacco|cigar", "FMCG", "Tobacco"),
    (r"(?i)paint|coat|adhesive", "Chemicals", "Paints & Coatings"),
    (r"(?i)hospital", "Pharma", "Hospitals"),
]


def _get_cache_tickers() -> list[str]:
    """Get all NSE tickers from cache directory."""
    tickers = []
    for f in CACHE_DIR.glob("*.NS.csv"):
        ticker = f.stem.replace(".NS", "")
        if ticker and not ticker.startswith("^"):
            tickers.append(ticker)
    return sorted(tickers)


def _load_existing_taxonomy() -> dict[str, dict]:
    """Load existing taxonomy CSV into dict keyed by ticker."""
    result = {}
    if TAXONOMY_CSV.exists():
        with open(TAXONOMY_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ticker = row.get("nse_ticker", "").strip().upper()
                if ticker:
                    result[ticker] = {
                        "sector": row.get("sector", "").strip(),
                        "industry": row.get("industry", "").strip(),
                        "notes": row.get("notes", "").strip(),
                    }
    return result


def _load_auto_classify_cache() -> dict[str, dict]:
    """Load the yfinance auto-classify cache."""
    try:
        return json.loads(AUTO_CACHE.read_text())
    except Exception:
        return {}


def _fetch_nse_equity_list() -> dict[str, dict]:
    """Fetch NSE EQUITY_L.csv for official listing data."""
    import requests
    result = {}
    try:
        # NSE official listing CSV
        url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/csv",
        }, timeout=15)
        if resp.ok:
            import io
            reader = csv.DictReader(io.StringIO(resp.text))
            for row in reader:
                sym = row.get("SYMBOL", "").strip().upper()
                name = row.get("NAME OF COMPANY", "").strip()
                if sym:
                    result[sym] = {"name": name, "source": "nse_equity_l"}
            print(f"  [NSE] Fetched {len(result)} stocks from EQUITY_L.csv")
    except Exception as e:
        print(f"  [NSE] Failed to fetch EQUITY_L.csv: {e}")
    return result


def _fetch_nse_index_constituents() -> dict[str, dict]:
    """Fetch Nifty sectoral index constituents for reliable classification."""
    import requests

    INDEX_SECTOR_MAP = {
        "NIFTY BANK": ("Banking", "Private Banks"),
        "NIFTY PSU BANK": ("Banking", "PSU Banks"),
        "NIFTY PRIVATE BANK": ("Banking", "Private Banks"),
        "NIFTY IT": ("IT", "IT Services"),
        "NIFTY PHARMA": ("Pharma", "Pharma"),
        "NIFTY METAL": ("Metals", "Steel"),
        "NIFTY REALTY": ("RealEstate", "Real Estate - Residential"),
        "NIFTY AUTO": ("Auto", "Auto OEM"),
        "NIFTY ENERGY": ("Energy", "Energy"),
        "NIFTY FMCG": ("FMCG", "FMCG"),
        "NIFTY MEDIA": ("Media", "Media & Entertainment"),
        "NIFTY FINANCIAL SERVICES": ("Financials", "Financials"),
        "NIFTY CONSUMER DURABLES": ("Consumer", "Consumer Durables"),
        "NIFTY OIL & GAS": ("Energy", "Oil & Gas"),
        "NIFTY HEALTHCARE INDEX": ("Pharma", "Pharma"),
        "NIFTY INFRASTRUCTURE": ("Infra", "Construction - Infra"),
        "NIFTY COMMODITIES": ("Commodities", "Commodities"),
        "NIFTY MNC": ("MNC", "MNC"),
    }

    result = {}
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com/",
    })

    # Warm session cookies
    try:
        session.get("https://www.nseindia.com/", timeout=10)
    except Exception:
        pass

    for index_name, (sector, industry) in INDEX_SECTOR_MAP.items():
        try:
            import urllib.parse
            url = f"https://www.nseindia.com/api/equity-stockIndices?index={urllib.parse.quote(index_name)}"
            resp = session.get(url, timeout=10)
            if resp.ok:
                data = resp.json().get("data", [])
                for item in data:
                    sym = item.get("symbol", "").strip().upper()
                    if sym and sym != index_name:
                        # Don't overwrite if already classified more specifically
                        if sym not in result:
                            result[sym] = {
                                "sector": sector,
                                "industry": industry,
                                "source": f"nse_index:{index_name}",
                            }
                print(f"  [NSE INDEX] {index_name}: {len(data)-1} stocks")
            time.sleep(0.5)  # Rate limit
        except Exception as e:
            print(f"  [NSE INDEX] {index_name} failed: {e}")

    return result


def _classify_with_yfinance(tickers: list[str], batch_size: int = 10) -> dict[str, dict]:
    """Classify stocks using yfinance in parallel batches."""
    result = {}
    auto_cache = _load_auto_classify_cache()

    # Filter to tickers not in auto-cache
    to_fetch = [t for t in tickers if t not in auto_cache]
    from_cache = {t: auto_cache[t] for t in tickers if t in auto_cache}

    # Map cached results
    for t, c in from_cache.items():
        yf_sec = c.get("yf_sector", "")
        yf_ind = c.get("yf_industry", "")
        sector = c.get("sector") or YF_SECTOR_MAP.get(yf_sec, "Other")
        industry = c.get("industry") or YF_INDUSTRY_MAP.get(yf_ind, sector)
        if sector != "Other" or industry != "Other":
            result[t] = {"sector": sector, "industry": industry, "source": "yf_cache"}

    if not to_fetch:
        return result

    print(f"  [YF] Fetching {len(to_fetch)} stocks via yfinance...")

    def _fetch_one(ticker: str) -> tuple[str, dict | None]:
        try:
            import yfinance as yf
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                info = yf.Ticker(f"{ticker}.NS").info or {}
            yf_sec = info.get("sector", "")
            yf_ind = info.get("industry", "")
            if yf_sec:
                sector = YF_SECTOR_MAP.get(yf_sec, "Other")
                industry = YF_INDUSTRY_MAP.get(yf_ind, sector)
                entry = {
                    "sector": sector, "industry": industry,
                    "yf_sector": yf_sec, "yf_industry": yf_ind,
                    "auto_classified": True,
                }
                return ticker, entry
        except Exception:
            pass
        return ticker, None

    fetched = 0
    with ThreadPoolExecutor(max_workers=batch_size) as pool:
        futures = {pool.submit(_fetch_one, t): t for t in to_fetch}
        for future in as_completed(futures):
            ticker, entry = future.result()
            fetched += 1
            if fetched % 50 == 0:
                print(f"    ... {fetched}/{len(to_fetch)}")
            if entry:
                auto_cache[ticker] = entry
                if entry["sector"] != "Other" or entry["industry"] != "Other":
                    result[ticker] = {
                        "sector": entry["sector"],
                        "industry": entry["industry"],
                        "source": "yfinance",
                    }

    # Save updated auto-cache
    try:
        AUTO_CACHE.parent.mkdir(parents=True, exist_ok=True)
        AUTO_CACHE.write_text(json.dumps(auto_cache, indent=2))
    except Exception:
        pass

    print(f"  [YF] Classified {len(result)} / {len(tickers)} stocks")
    return result


def _classify_by_name(ticker: str, company_name: str = "") -> tuple[str, str] | None:
    """Try to classify by company name / ticker using heuristic rules."""
    text = f"{ticker} {company_name}"
    for pattern, sector, industry in NAME_RULES:
        if re.search(pattern, text):
            return sector, industry
    return None


def _read_ohlcv_last_close(ticker: str) -> float | None:
    """Read the last close price from cache to determine market cap bucket."""
    path = CACHE_DIR / f"{ticker}.NS.csv"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            lines = f.readlines()
            if len(lines) < 2:
                return None
            last = lines[-1].strip().split(",")
            return float(last[4]) if len(last) >= 5 else None
    except Exception:
        return None


def build_taxonomy():
    """Main function: build complete taxonomy."""
    print("=" * 70)
    print("Building Complete NSE Stock Taxonomy")
    print("=" * 70)

    # Step 1: Get all tickers from cache
    cache_tickers = _get_cache_tickers()
    print(f"\n[1] Found {len(cache_tickers)} NSE stocks in cache")

    # Step 2: Load existing taxonomy
    existing = _load_existing_taxonomy()
    print(f"[2] Existing taxonomy: {len(existing)} stocks classified")

    # Step 3: Identify gaps
    missing = [t for t in cache_tickers if t not in existing]
    print(f"[3] Missing from taxonomy: {len(missing)} stocks")

    # Step 4: Fetch NSE equity listing for company names
    print(f"\n[4] Fetching NSE official listings...")
    nse_names = _fetch_nse_equity_list()

    # Step 5: Fetch NSE index constituents
    print(f"\n[5] Fetching NSE sectoral index constituents...")
    nse_index = _fetch_nse_index_constituents()

    # Step 6: Classify missing stocks
    taxonomy: dict[str, dict] = {}

    # Start with existing data
    for t, data in existing.items():
        if data["sector"] and data["industry"]:
            taxonomy[t] = data

    # Apply NSE index classifications (only for missing stocks)
    classified_from_index = 0
    for t in missing:
        if t in nse_index:
            taxonomy[t] = {
                "sector": nse_index[t]["sector"],
                "industry": nse_index[t]["industry"],
                "notes": nse_index[t].get("source", ""),
            }
            classified_from_index += 1
    print(f"\n[6] Classified {classified_from_index} stocks from NSE indices")

    # Step 7: yfinance for remaining
    still_missing = [t for t in missing if t not in taxonomy]
    if still_missing:
        print(f"\n[7] Classifying {len(still_missing)} remaining stocks via yfinance...")
        yf_results = _classify_with_yfinance(still_missing, batch_size=8)
        for t, data in yf_results.items():
            if t not in taxonomy:
                taxonomy[t] = {
                    "sector": data["sector"],
                    "industry": data["industry"],
                    "notes": "auto:yfinance",
                }

    # Step 8: Name-based heuristics for anything still missing
    final_missing = [t for t in cache_tickers if t not in taxonomy]
    name_classified = 0
    for t in final_missing:
        name = nse_names.get(t, {}).get("name", "")
        result = _classify_by_name(t, name)
        if result:
            taxonomy[t] = {
                "sector": result[0],
                "industry": result[1],
                "notes": f"auto:name_rule ({name[:40]})" if name else "auto:name_rule",
            }
            name_classified += 1
    print(f"[8] Name-based heuristics classified {name_classified} more stocks")

    # Step 9: Mark remaining as "Other"
    still_unclassified = [t for t in cache_tickers if t not in taxonomy]
    for t in still_unclassified:
        name = nse_names.get(t, {}).get("name", "")
        taxonomy[t] = {
            "sector": "Other",
            "industry": "Other",
            "notes": f"unclassified ({name[:40]})" if name else "unclassified",
        }
    print(f"[9] {len(still_unclassified)} stocks remain as 'Other'")

    # Step 10: Write output
    print(f"\n[10] Writing {len(taxonomy)} stocks to {TAXONOMY_CSV}")

    # Sort by sector, then industry, then ticker
    rows = sorted(taxonomy.items(), key=lambda x: (x[1]["sector"], x[1]["industry"], x[0]))

    with open(TAXONOMY_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["nse_ticker", "sector", "industry", "notes"])
        for ticker, data in rows:
            writer.writerow([ticker, data["sector"], data["industry"], data.get("notes", "")])

    # Summary
    sectors = {}
    for t, d in taxonomy.items():
        s = d["sector"]
        sectors[s] = sectors.get(s, 0) + 1

    print(f"\n{'=' * 70}")
    print(f"TAXONOMY COMPLETE: {len(taxonomy)} stocks classified")
    print(f"{'=' * 70}")
    print(f"\nSector distribution:")
    for s, c in sorted(sectors.items(), key=lambda x: -x[1]):
        print(f"  {s:25s} {c:5d} stocks")

    coverage = len([t for t in cache_tickers if taxonomy.get(t, {}).get("sector", "Other") != "Other"])
    print(f"\nCoverage: {coverage}/{len(cache_tickers)} ({coverage/len(cache_tickers)*100:.1f}%) properly classified")


if __name__ == "__main__":
    build_taxonomy()

