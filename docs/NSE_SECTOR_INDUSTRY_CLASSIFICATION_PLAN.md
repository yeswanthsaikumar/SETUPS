# NSE Full Market Sector & Industry Classification Plan
## Purpose: Early Trend Detection · Smart Money Tracking · Market Breadth Analysis

**Status:** Planning / In Progress  
**Target:** Cover all ~2,000 active NSE-listed stocks with 2-level taxonomy  
**Date Created:** April 10, 2026

---

## 🎯 Why This Matters

| Signal | How Classification Helps |
|--------|--------------------------|
| **Early trend identification** | When 3+ stocks in a sub-industry break out, the whole sector may be rallying — you see it before the news |
| **Smart money positions** | DIIs/FIIs often accumulate an entire sub-sector, not individual stocks — group-level FII/DII data reveals intent |
| **Market breadth** | How many sub-industries have >50% of stocks above 20/50 MA — breadth narrows before corrections |
| **Relative strength** | Which sub-industry is leading vs lagging the Nifty — rotate to leaders |
| **Volume clusters** | Unusual volume across multiple stocks in one sub-industry = institutional accumulation |

---

## 📐 Taxonomy Design (2 Levels)

```
SECTOR (Broad, ~20 categories)
  └── INDUSTRY (Sub-sector, ~100-120 categories)
        └── Individual Stocks (NSE tickers)
```

### Guiding Principles
1. **SECTOR** = broad theme an investor would think in (Metals, Pharma, IT, FMCG...)
2. **INDUSTRY** = specific business where peers move together (Steel Pipes, Pharma API, Cables & Wires...)
3. Prefer **business similarity** over SEBI/index classification (e.g. Bharatforg + GNA + Sansera all move together as Forgings regardless of their official classification)
4. Max 50 stocks per industry — split if larger
5. Minimum 3 stocks per industry — merge smaller ones into broader category

---

## 📋 TODO List (Ordered by Priority)

### PHASE 1 — Core Index Coverage (Nifty 500) ✅ Partially Done
> ~500 stocks covering ~85% of market cap

- [x] Nifty 50 stocks classified
- [x] Nifty Next 50 stocks classified
- [x] Nifty Midcap 150 — partial (~60% done)
- [ ] Nifty Smallcap 250 — mostly unclassified
- [ ] Complete Nifty 500 coverage

**Action:** Pull Nifty 500 constituent list from NSE → cross-check against `SECTOR_MAP` / `INDUSTRY_MAP` → fill gaps

---

### PHASE 2 — Sector Deep-Dives (by priority for rally detection)

#### 2a. METALS & MINING 🔥 High Priority
Current coverage: ~25 stocks
Target: ~60 stocks

**Sub-industries to fully map:**
- [ ] **Steel — Integrated** (TATASTEEL, JSWSTEEL, SAIL, JSHL)
- [ ] **Steel — Sponge Iron / DRI** (GPIL, HISARMETAL, SRPL, ABHIINV)  
- [ ] **Steel Pipes & Tubes** (APLAPOLLO, RATNAMANI, WELCORP, JINDALSAW, MANALIPETC, SURYA)
- [ ] **Steel — Structural / Rails** (TIGL, GALLANTT)
- [ ] **Metal Forgings & Castings** (BHARATFORG, GNA, SANSERA, NELCAST, SHRIPISTON, CRAFTSMAN, JBMA, SUNDRMFAST, MAHINDRACIE)
- [ ] **Aluminium** (HINDALCO, NALCO, VEDL)
- [ ] **Copper** (HINDCOPPER, STERLITE, HINDALCO)
- [ ] **Zinc & Lead** (HINDZINC)
- [ ] **Graphite & Carbon** (GRAPHITE, HEG, PHILIPCARB)
- [ ] **Iron Ore & Mining** (NMDC, GMDC, MOIL, MSTCLTD, KIOCL)
- [ ] **Specialty Metals** (MIDHANI, MISHRA)
- [ ] **Wire Rods & Fasteners** (NILE, MANAKSIA)

---

#### 2b. CHEMICALS & SPECIALTY CHEMICALS 🔥 High Priority
Current coverage: ~15 stocks
Target: ~50 stocks

- [ ] **Specialty Chemicals — Fluorine** (NAVINFLUOR, SRF, FLUOROCHEM, ROSSARI)
- [ ] **Specialty Chemicals — Agri** (RALLIS, SUMICHEM, BAYER, PI, UPL, DHANU)
- [ ] **Specialty Chemicals — Dyes & Pigments** (ATUL, SUDARSCHEM, COLORMASTER)
- [ ] **Specialty Chemicals — Surfactants** (GALAXYSURF, ALKYLAMINE, NOCIL)
- [ ] **Specialty Chemicals — Performance** (AETHER, CAMLIN, CLEAN, NEOGEN)
- [ ] **Chemicals — Chlor-Alkali** (GUJALKALI, DCW, TATACHEMICAL, DEEPAKFERT)
- [ ] **Specialty Chemicals — Pharma Intermediates** (AARTI, VINATI, DEEPINDS, COMSYN)
- [ ] **Carbon Black** (PCBL, PHILLIPS)
- [ ] **Adhesives & Sealants** (PIDILITIND, FEVICOL)
- [ ] **Ethanol & Bio-Fuels** (PRAJIND, DHAMPUR, TRIVENIENG — ethanol segment)
- [ ] **Gases — Industrial** (LINDE, ATAM, INOX — industrial gases)

---

#### 2c. DEFENSE & AEROSPACE 🔥 High Priority (Major theme)
Current coverage: ~10 stocks
Target: ~25 stocks

- [ ] **Aerospace & Defense — Systems** (HAL, DYNAMATECH, IDEAFORGE, ZEN)
- [ ] **Defense Electronics** (BEL, DATAPATTNS, MTAR, PARAS, ASTRA)
- [ ] **Defense — Shipbuilding** (GRSE, COCHINSHIP, MDL, GARWARSHIP)
- [ ] **Defense — Missiles & Ammunition** (SOLARBOMB, SOLARIND)
- [ ] **Defense — Explosives** (GOCLCORP, NAGAFERT)
- [ ] **Aerospace Alloys** (MIDHANI)
- [ ] **Drone & UAV** (IDEAFORGE, DRONEACHARYA)
- [ ] **Space Tech** (MTAR, CENTUM, SYRMA)

---

#### 2d. CAPITAL GOODS & ENGINEERING
Current coverage: ~15 stocks
Target: ~40 stocks

- [ ] **Heavy Engineering — EPC** (L&T, BHEL, THERMAX, TRIVENIENG, ISGEC)
- [ ] **Pumps & Compressors** (KIRLOSENG, ELGI, KSB, FLOWCONTR)
- [ ] **Valves & Fittings** (TRITON, WALCHAND, VIMETAL)
- [ ] **Boilers & Heat Exchange** (THERMAX, PAHARPUR, TECHNO)
- [ ] **Machine Tools & Precision** (LOKESHMACH, HMT, BHFCL)
- [ ] **Cutting Tools** (AIAENG, KENNAMETAL, MMTC)
- [ ] **Engines & Compressors** (CUMMINSIND, GRINDMASTER, KIRLOSENG)
- [ ] **Power Transmission** (PIXTRANS, GREAVES, REXNORD)
- [ ] **Filtration Equipment** (RITEFIL, INDAG, MAHLE)
- [ ] **Hydraulics** (WIPRO — hydraulics div, YUKEN)
- [ ] **Textile Machinery** (TIIL, LAKSHMI, RIETER)
- [ ] **Weighing & Measuring** (WENDT, SARTORIUS)

---

#### 2e. CABLES, WIRES & ELECTRICAL
Current coverage: ~10 stocks
Target: ~25 stocks

- [ ] **Cables & Wires — Power** (KEI, POLYCAB, FINOLEX, CABINDIA, HAVELLS)
- [ ] **Cables & Wires — Specialty** (PRECWIRE, SUMEETINDS, RR, INDOTECH)
- [ ] **Optical Fiber Cables** (STLTECH, HFCL, OPTIEMUS)
- [ ] **Transformers** (VOLTAMP, ELECTROTHERM, BHEL, SIEVERT)
- [ ] **Switchgear & Control Gear** (ABB, SIEMENS, SCHNEIDER, HAVELLS)
- [ ] **Energy Meters** (ELMEASURE, SECURE, GENUS)
- [ ] **EV Charging Infrastructure** (TATAPOWER, CHARGEZONE, VOLTAMP)

---

#### 2f. ELECTRONIC COMPONENTS & PCBA
Current coverage: ~12 stocks
Target: ~30 stocks

- [ ] **PCBs & PCBAs** (SYRMA, KAYNES, CENTUM, ELIN)
- [ ] **Electronic Components — Passive** (AEROFLEX, KRN, ADVAIT)
- [ ] **Consumer Electronics — EMS** (DIXON, AMBER, SYRMA, PGEL, KAYNES)
- [ ] **Semiconductors — Assembly & Test** (MOSCHIP, SPEL)
- [ ] **Display & Lighting** (HALONIX, BAJAJELECTR)
- [ ] **Embedded Systems / IoT** (INTELLECT, TATAELXSI, NEWGEN)

---

#### 2g. PHARMACEUTICALS & HEALTHCARE
Current coverage: ~30 stocks
Target: ~60 stocks

- [ ] **Pharma — Large Cap Formulations** (SUNPHARMA, DRREDDY, CIPLA, LUPIN)
- [ ] **Pharma — Mid Cap Formulations** (TORNTPHARM, ALKEM, GLENMARK, IPCALAB, AJANTPHARM)
- [ ] **Pharma — Export-Focused API** (AUROPHARMA, GRANULES, LAURUSLABS, NEULANDLAB)
- [ ] **Pharma — Domestic CDMO** (AKUMS, ENCUBE, DIVI — CDMO segment)
- [ ] **Pharma API — Fermentation** (BIOCON, SEQUENT, SOLARA)
- [ ] **Pharma — OTC & Consumer** (ZYDUSWELL, EMAMI, HIMALAYA)
- [ ] **Diagnostics** (METROPOLIS, DRLALPATH, THYROCARE, VIJAYALAB)
- [ ] **Hospitals** (APOLLOHOSP, FORTIS, ASTERDM, YATHARTH, RAINBOW, NARAYANA)
- [ ] **Medical Devices** (SHILPAMED, POLYMED, SUTURA, INNVENTMED)
- [ ] **Healthcare IT** (HEALTHSPRING, MEDGENIX)
- [ ] **Pharmacy Retail** (MEDPLUS, APOLLOPHARM)
- [ ] **Veterinary & Animal Health** (SEQUENT, HESTER, VIMTAS)

---

#### 2h. FINANCIALS — Capital Markets Sub-sectors
Current coverage: ~20 stocks
Target: ~35 stocks

- [x] **Capital Markets** (BSE, MCX, ANANDRATHI, SAMMAANCAP, ONELIFECAP)
- [x] **Stock Broking** (ANGELONE, 5PAISA, DBSTOCKBRO, GROWW, ICICISEC, GEOJITFSL)
- [x] **Wealth Management** (NUVAMA, MOTILALOFS, MOFSL, ABSLAMC)
- [ ] **Asset Management — AMCs** (HDFCAMC, NIPPONAMC, ABSLAMC, UTIAMC, SBIMF)
- [ ] **Insurance — Life** (HDFCLIFE, SBILIFE, ICICIPRU, MAXLIFE)
- [ ] **Insurance — Non-Life / Health** (STARHEALTH, NIACINDIA, ORIENTINS)
- [ ] **Insurance — Reinsurance** (GICRE, NIARE)
- [ ] **Power Finance** (PFC, RECLTD, IREDA, NABARD)
- [ ] **Housing Finance** (LICHSGFIN, REPCO, AAVAS, APTUS)
- [ ] **Gold Loans** (MUTHOOTFIN, MANAPPURAM, IIFL — gold div)
- [ ] **Vehicle Finance** (CHOLAFIN, M&MFIN, SHRIRAMFIN, SUNDFINANCE)
- [ ] **Microfinance** (CREDITACC, SPANDANA, UJJIVAN — MFI wing)
- [ ] **Financial Technology** (KFINTECH, CAMS, CDSL, NSDL)
- [ ] **Payments & Fintech** (PAYTM, INFIBEAM, RAZORPAY — if listed)

---

#### 2i. RENEWABLE ENERGY & NEW ENERGY
Current coverage: ~8 stocks
Target: ~20 stocks

- [ ] **Solar — Manufacturers** (WAAREEENER, PREMIER, GOLDI)
- [ ] **Solar — IPP / Developers** (ACMESOLAR, ADANIENSOL, ADANIGREEN, GREENKO)
- [ ] **Wind Energy** (SUZLON, INOXWIND, WINDWORLD)
- [ ] **EV — Vehicles** (TATAMOTORS EV, OLECTRA, PMI, JBMA EV)
- [ ] **EV — Batteries** (AMARA, EXIDE EV, GREENENERG)
- [ ] **EV — Charging** (CHARGEZONE, TATAPOWER, VOLTAMP)
- [ ] **Green Hydrogen** (RELIANCE, ADANIGREEN — H2 projects, NTPC)
- [ ] **Energy Storage** (AMARA, SOLARIND — storage)

---

#### 2j. TEXTILES & APPAREL (Complete mapping)
Current coverage: ~18 stocks
Target: ~35 stocks

- [ ] **Spinning & Yarn** (NITINSPIN, NAHARSPING, VARDHMAN, SPORTKING, NAHAREXP)
- [ ] **Synthetic Textiles** (RELIANCE — polyester, SRF — technical textiles)
- [ ] **Technical Textiles** (GARWARE, HIMATSEIDE, ALOK)
- [ ] **Home Textiles** (WELSPUNIND, TRIDENT, STYLAMIND, RAYMOND — home)
- [ ] **Apparel — Value** (ARVIND, GOKALDAS, KITEX)
- [ ] **Apparel — Premium Retail** (STYLEBAAZA, VCUSTOMS, VEDANT, PAGES)
- [ ] **Innerwear & Hosiery** (RUPA, LUX, DOLLAR)
- [ ] **Technical Apparel** (SPORTKING — synthetic)

---

### PHASE 3 — Build the Classification Engine in Code

#### 3a. Python Data File
```
apps/python/lib/nse_taxonomy.py
```
Replace the dictionaries in `generate_trade_plans_page.py` with imports from a dedicated module:

```python
# nse_taxonomy.py
SECTOR_MAP: dict[str, str] = { ... }   # NSE_ticker → Sector
INDUSTRY_MAP: dict[str, str] = { ... } # NSE_ticker → Industry

# Future: Auto-load from CSV for easy maintenance
def load_from_csv(path: str) -> tuple[dict, dict]: ...
```

#### 3b. CSV Master File for Easy Editing
```
data/nse_stock_taxonomy.csv
```
Columns:
```
nse_ticker, company_name, sector, industry, sub_industry, nifty_index, market_cap_category
```

Benefits:
- Edit in Excel/Sheets without touching Python
- Easy bulk updates when companies change business
- Can be sourced from NSE/BSE official sector lists and override as needed

#### 3c. Auto-Classification Fallback
When a stock is NOT in the manual map:
1. Check yfinance `info["sector"]` and `info["industry"]`
2. Map yfinance categories → our taxonomy
3. Cache result to avoid repeated API calls
4. Flag as "auto-classified" for manual review

```python
def auto_classify(symbol: str) -> tuple[str, str]:
    """Fallback: yfinance → our taxonomy mapping"""
    ...
```

---

### PHASE 4 — Market Breadth Dashboard

#### 4a. Per-Industry Breadth Metrics
For each industry, compute daily:
- **% stocks above 20 MA** — short-term breadth
- **% stocks above 50 MA** — medium-term breadth  
- **% stocks above 200 MA** — long-term / trend breadth
- **% stocks at 52W high** — momentum breadth
- **Average RS vs Nifty 50** — relative strength of the group
- **FII/DII net for group** — aggregate smart money flow

```python
# New module: apps/python/lib/market_breadth.py
def compute_industry_breadth(
    industry: str,
    stocks: list[str],
    price_cache: dict,
) -> dict:
    return {
        "industry": industry,
        "stock_count": n,
        "pct_above_20ma": ...,
        "pct_above_50ma": ...,
        "pct_above_200ma": ...,
        "pct_at_52wh": ...,
        "avg_rs_nifty": ...,
        "breadth_score": ...,  # composite 0-100
    }
```

#### 4b. Breadth Heatmap in Trade Plans Page
Extend the existing industry heatmap with MA breadth columns:

```
Industry          Signals  A/A+  >20MA  >50MA  >200MA  RS
Steel Pipes         8       5     87%    62%    45%    +12%
Metal Forgings      6       4     83%    58%    40%    +8%
Cables & Wires      5       3     75%    50%    35%    +5%
```

Color coding:
- 🔴 `>80%` stocks above 20MA = **Extended / watch for pullback**
- 🟡 `50-80%` = **Building / healthy**  
- 🟢 `20-50%` = **Early accumulation phase** ← Best buy zone
- ⚫ `<20%` = **Avoid / distribution**

#### 4c. Smart Money Flow by Industry
Aggregate FII/DII changes across all stocks in an industry:
- Average DII change over last 2 quarters
- Number of stocks with DIIs increasing vs decreasing
- Conviction score = (stocks_dii_up / total) × avg_dii_change

```python
def industry_smart_money_score(
    industry: str,
    mf_data: dict[str, dict],  # symbol → MF holdings dict
) -> dict:
    ...
```

---

### PHASE 5 — Sector Rotation Tracker

Track which sectors are in which stage of the rotation cycle:

```
Early Cycle     → Financials, Consumer Discretionary
Mid Cycle       → IT, Industrials, Materials
Late Cycle      → Energy, Utilities, Healthcare
Recession       → Defensives (FMCG, Pharma, Utilities)
```

Implementation:
- [ ] Track 4-week, 12-week RS of each sector vs Nifty
- [ ] Plot sector rotation wheel (radar chart in HTML)
- [ ] Alert when sector moves from "early" to "mid" (breakout signal)
- [ ] Combine with FII data — FIIs buy early cycle sectors first

---

### PHASE 6 — Auto-Updates & Maintenance

- [ ] **Quarterly review trigger**: After every NSE index rebalancing (Jan/Apr/Jul/Oct), diff the constituent list and add new stocks
- [ ] **New IPO ingestion**: When a new stock appears in scan results with no classification → flag for manual classification
- [ ] **Corporate action handling**: Mergers, demergers, name changes → update map (e.g. HDFC → HDFCBANK post-merger)
- [ ] **yfinance fallback**: For US stocks — auto-use yfinance sector/industry

---

## 🗂️ Complete Sector Taxonomy (Target State)

```
SECTOR              TARGET INDUSTRIES (sub-categories)
────────────────────────────────────────────────────────────────────────────────
Banking             PSU Banks, Private Banks, Small Finance Banks, Regional Banks
Financials          Capital Markets, Stock Broking, Wealth Management,
                    Asset Management, Life Insurance, Non-Life Insurance,
                    Power Finance, Housing Finance, Gold Loans, Vehicle Finance,
                    Microfinance, Financial Technology, NBFC
IT                  IT Services (Large), IT Services (Mid), IT Engineering,
                    IT Products, BPO / KPO
Electronics         Electronic Components, Consumer Electronics EMS,
                    Defense Electronics, PCBs, Semiconductors
Cables              Cables & Wires, Optical Fiber, Transformers,
                    Switchgear, Energy Meters
Cap Goods           Heavy Engineering, Pumps & Compressors, Machine Tools,
                    Cutting Tools, Power Transmission, Boilers,
                    Textile Machinery, Filtration
Defense             Aerospace & Defense, Defense Electronics,
                    Shipbuilding, Drones, Explosives
Energy              Oil & Gas, Oil Refining, Gas Distribution,
                    Coal & Mining, Power Generation, Power Transmission
Renewable           Solar Panels, Solar IPP, Wind Energy,
                    EV Vehicles, EV Batteries, Green Hydrogen
Chemicals           Specialty Chemicals (Fluorine), Specialty Chemicals (Agri),
                    Specialty Chemicals (Dyes), Chlor-Alkali, Carbon Black,
                    Adhesives, Ethanol, Pharma Intermediates
Metals              Steel (Integrated), Steel (Sponge Iron), Steel Pipes,
                    Metal Forgings & Castings, Aluminium, Copper,
                    Zinc & Lead, Graphite, Iron Ore & Mining
Auto                Auto OEM 4W, Auto OEM 2W, Auto OEM CV,
                    Auto Ancillaries, Metal Forgings & Castings,
                    Bearings, Auto Batteries, Tyres
Pharma              Pharma Formulations (Large), Pharma Formulations (Mid),
                    Pharma API, Pharma CDMO, Pharma OTC,
                    Diagnostics, Hospitals, Medical Devices, Pharmacy Retail
FMCG                FMCG Personal Care, FMCG Foods, FMCG Beverages,
                    FMCG Tea, QSR / Restaurant
Consumer            Jewelry & Watches, Paints, Adhesives, Consumer Electricals,
                    Air Conditioners, Consumer Electronics, Eyewear
Textiles            Textiles Spinning, Textiles Synthetic, Textiles Home,
                    Textiles Apparel, Textiles Technical, Innerwear
Packaging           Packaging Laminates, Packaging Films, Packaging Plastics,
                    Packaging Containers, Paper & Packaging
Infra               EPC & Construction, Roads & Highways, Ports & Logistics,
                    Rail Construction, Rail Logistics, Cement, Irrigation
RealEstate          Residential Premium, Residential Affordable,
                    Commercial, REITs
Internet            Food Delivery, Online Recruitment, Fintech,
                    B2B Marketplace, Travel & Hospitality
Sugar               Sugar (all under one industry unless large enough to split)
Shipping            Shipping, Logistics, Air Cargo
Agri                Aquaculture, Flour Milling, Tea Plantations, Poultry
```

---

## 📁 Files to Create / Modify

```
SETUPS/
├── data/
│   └── nse_stock_taxonomy.csv          ← NEW: master classification file
├── apps/python/lib/
│   ├── nse_taxonomy.py                 ← NEW: import maps from CSV, fallback logic
│   └── market_breadth.py              ← NEW: per-industry MA breadth computation
├── apps/python/cli/
│   ├── generate_trade_plans_page.py    ← MODIFY: import from nse_taxonomy.py
│   └── generate_breadth_dashboard.py  ← NEW: standalone breadth heatmap page
└── output/
    ├── trade_plans_live.html           ← existing (enhance heatmap with MA data)
    └── market_breadth.html             ← NEW: dedicated breadth dashboard
```

---

## 🚀 Quick Wins (Can Do Now)

1. **Add missing Nifty 500 stocks** to existing maps in `generate_trade_plans_page.py` — 2-3 hours
2. **Export current maps to CSV** — run once, gives editable baseline
3. **Add `>20MA` / `>50MA` breadth column** to the existing industry heatmap in the trade plans page — extends current infrastructure with minimal new code

---

## 📊 Success Metrics

When fully implemented, the system should be able to answer:

- "Which industry has the most stocks breaking out this week?" ← already partly there
- "Which industry has the highest % of stocks above 50 MA?" ← Phase 4
- "Where are FIIs accumulating at the industry level?" ← Phase 4c  
- "What stage of the sector rotation cycle is Metals in?" ← Phase 5
- "Which industries have seen the most new 52W highs in the last 5 days?" ← Phase 4b
- "What was the first industry to break out before the current Nifty rally?" ← Phase 5 + history

---

*Document maintained by the SETUPS system. Update as new stock data sources or classification schemes are identified.*

