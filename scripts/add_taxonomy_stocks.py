#!/usr/bin/env python3
"""
add_taxonomy_stocks.py
Adds missing NSE stocks to the taxonomy CSV without duplicates.
Run: python3 scripts/add_taxonomy_stocks.py
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "nse_stock_taxonomy.csv"

NEW_STOCKS = [
    # (nse_ticker, sector, industry, notes)
    # Pharma - missing
    ("APOLLOHOSP",  "Pharma",       "Hospitals",                        ""),
    ("ENCUBE",      "Pharma",       "Pharma Contract Mfg",              ""),
    ("PIRAMAL",     "Pharma",       "Pharma Formulations",              ""),
    # Metals - missing
    ("HEG",         "Metals",       "Graphite Electrodes",              ""),
    ("VSTL",        "Metals",       "Steel",                            ""),
    ("MAHSEAMLES",  "Metals",       "Steel Pipes",                      ""),
    ("RAJRATAN",    "Metals",       "Steel",                            ""),
    # Capital Goods - missing
    ("GRINDWELL",   "Cap Goods",    "Cutting Tools",                    ""),
    ("LMWLTD",      "Cap Goods",    "Textile Machinery",                ""),
    ("SWRAJENG",    "Cap Goods",    "Pumps & Compressors",              ""),
    ("JYOTI",       "Cap Goods",    "Machine Tools",                    ""),
    ("ESABINDIA",   "Cap Goods",    "Engineering",                      ""),
    # Cables & Electrical - missing
    ("GENUS",       "Cables",       "Energy Meters",                    ""),
    ("SECURE",      "Cables",       "Energy Meters",                    ""),
    ("ELMEASURE",   "Cables",       "Energy Meters",                    ""),
    # FMCG - missing
    ("VBL",         "FMCG",         "FMCG - Beverages",                 ""),
    ("TATACONSUM",  "FMCG",         "FMCG - Beverages",                 ""),
    ("BECTORFOOD",  "FMCG",         "FMCG - Foods",                     ""),
    ("PRATAAP",     "FMCG",         "FMCG - Foods",                     ""),
    ("GOPAL",       "FMCG",         "FMCG - Foods",                     ""),
    ("PGHH",        "FMCG",         "FMCG - Personal Care",             ""),
    # Consumer - missing
    ("DMART",       "Consumer",     "Retail",                           ""),
    ("VMART",       "Consumer",     "Retail",                           ""),
    ("CENTURYPLY",  "Consumer",     "Building Materials",               ""),
    ("GREENPANEL",  "Consumer",     "Building Materials",               ""),
    ("BATAINDIA",   "Consumer",     "Footwear",                         ""),
    ("METROBRAND",  "Consumer",     "Footwear",                         ""),
    ("RELAXO",      "Consumer",     "Footwear",                         ""),
    ("CAMPUSSHOE",  "Consumer",     "Footwear",                         ""),
    ("HINDWAREAP",  "Consumer",     "Consumer Appliances",              ""),
    # Textiles - missing
    ("ABFRL",       "Textiles",     "Apparel Retail",                   ""),
    ("KPRMILL",     "Textiles",     "Textiles - Spinning",              ""),
    # Chemicals - missing
    ("TATVA",       "Chemicals",    "Specialty Chemicals - Fluorine",   ""),
    ("SHARDACROP",  "Chemicals",    "Specialty Chemicals - Agri",       ""),
    ("MEGHMANI",    "Chemicals",    "Specialty Chemicals - Agri",       ""),
    ("RFCL",        "Chemicals",    "Agri Chemicals & Fertilisers",     ""),
    # Renewable - missing
    ("SWANENERGY",  "Renewable",    "Renewable Energy",                 ""),
    # Financials - missing
    ("IIFLWAM",     "Financials",   "Wealth Management",                ""),
    ("JIOFIN",      "Financials",   "NBFC",                             ""),
    # Real Estate - missing
    ("ANANTRAJ",    "RealEstate",   "Real Estate - Residential",        ""),
    # Infra - missing
    ("KERNEX",      "Infra",        "Railway Signaling",                ""),
    ("CERA",        "Infra",        "Sanitaryware",                     ""),
    ("PRINCEPIPE",  "Infra",        "Pipes & Fittings",                 ""),
    # Packaging - missing
    ("FILATEX",     "Packaging",    "Packaging - Films",                ""),
    # Shipping - missing
    ("MAHINDLOG",   "Shipping",     "Logistics",                        ""),
    # Energy - missing
    ("INDIGRID",    "Energy",       "Power Transmission",               ""),
    # IT - missing
    ("VINDHYATEL",  "IT",           "Telecom Infrastructure",           ""),
    # Sugar - missing
    ("SHREERENUKA", "Sugar",        "Sugar",                            ""),
    # Agri - missing
    ("VSTTILLERS",  "Agri",         "Agri Equipment",                   ""),
    # Auto - missing
    ("ESCORTS",     "Auto",         "Auto OEM - 4W",                    ""),
    # Additional important Nifty 500 stocks
    ("LAURUSLABS",  "Pharma",       "Pharma API",                       ""),
    ("APLAPOLLO",   "Metals",       "Steel Pipes",                      ""),
    ("RATNAMANI",   "Metals",       "Steel Pipes",                      ""),
    ("WELCORP",     "Metals",       "Steel Pipes",                      ""),
    ("JINDALSAW",   "Metals",       "Steel Pipes",                      ""),
    ("MANALIPETC",  "Metals",       "Steel Pipes",                      ""),
    ("SURYA",       "Metals",       "Steel Pipes",                      ""),
    ("WELSPUNSP",   "Metals",       "Steel Pipes",                      ""),
    ("GPIL",        "Metals",       "Steel - Sponge Iron",              ""),
    ("HISARMETAL",  "Metals",       "Steel - Sponge Iron",              ""),
    ("SRPL",        "Metals",       "Steel - Sponge Iron",              ""),
    ("ABHIINV",     "Metals",       "Steel - Sponge Iron",              ""),
    ("GALLANTT",    "Metals",       "Steel - Structural",               ""),
    ("TIGL",        "Metals",       "Steel - Structural",               ""),
    ("GRAPHITE",    "Metals",       "Graphite Electrodes",              ""),
    ("PHILIPCARB",  "Metals",       "Graphite Electrodes",              ""),
    ("MOIL",        "Metals",       "Manganese Mining",                 ""),
    ("NMDC",        "Metals",       "Metal & Mining",                   ""),
    ("KIOCL",       "Metals",       "Iron Ore & Mining",                ""),
    ("MIDHANI",     "Defense",      "Aerospace Alloys",                 ""),
    ("HAL",         "Defense",      "Aerospace & Defense",              ""),
    ("DYNAMATECH",  "Defense",      "Aerospace & Defense",              ""),
    ("GRSE",        "Defense",      "Shipbuilding",                     ""),
    ("COCHINSHIP",  "Defense",      "Shipbuilding",                     ""),
    ("MAZDOCK",     "Defense",      "Shipbuilding",                     ""),
    ("SOLARIND",    "Defense",      "Defense - Ammunition",             ""),
    ("SOLARBOMB",   "Defense",      "Defense - Ammunition",             ""),
    ("GOCLCORP",    "Defense",      "Defense - Explosives",             ""),
    ("NAGAFERT",    "Defense",      "Defense - Explosives",             ""),
    ("IDEAFORGE",   "Defense",      "Drones",                           ""),
    ("DRONEACHARYA","Defense",      "Drones",                           ""),
    ("DATAPATTNS",  "Electronics",  "Defense Electronics",              ""),
    ("BEL",         "Defense",      "Defense Electronics",              ""),
    ("PARAS",       "Defense",      "Defense",                          ""),
    ("ASTRA",       "Defense",      "Defense",                          ""),
    ("ZEN",         "Defense",      "Defense",                          ""),
    ("BDSL",        "Defense",      "Defense",                          ""),
    ("MTARTECH",    "Defense",      "Aerospace & Defense",              ""),
]

# Read existing tickers
existing = set()
with open(CSV_PATH, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        t = row.get("nse_ticker", "").strip().upper()
        if t:
            existing.add(t)

# Append only genuinely new ones
added = 0
with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    for ticker, sector, industry, notes in NEW_STOCKS:
        if ticker.upper() not in existing:
            w.writerow([ticker, sector, industry, notes])
            existing.add(ticker.upper())
            added += 1
        # else: silently skip duplicates

print(f"✅ Added {added} new stocks. Total in CSV: {len(existing)}")

