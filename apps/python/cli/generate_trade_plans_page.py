#!/usr/bin/env python3
"""
generate_trade_plans_page.py
Generates a rich standalone HTML Trade Plans page with:
  - All current breakout/VCP signals (daily + weekly)
  - Price sparklines from cached OHLCV data
  - Pivot zones, entries, stops, T1/T2/T3
  - Position sizing, R:R ratios
  - Sector, regime, RS rank
  - Fundamentals-aware scoring
  - Market context banner
Run: python3 apps/python/cli/generate_trade_plans_page.py
"""
from __future__ import annotations
import csv, json, math, re, sys
from datetime import datetime
from functools import lru_cache
from html import escape
from pathlib import Path

ROOT      = Path(__file__).resolve().parents[3]
OUTPUT    = ROOT / "output"
CACHE_DIR = ROOT / "cache"
RUN_HISTORY_JSON = OUTPUT / "trade_plans_run_history.json"
RUN_HISTORY_MAX  = 20   # keep last N runs for appearance tracking
sys.path.insert(0, str(ROOT / "apps" / "python" / "lib"))

from utils import aggregate_weekly_bars, safe_return

try:
    from fundamentals_provider import (
        FundamentalsProvider,
        compact_summary as fundamentals_compact_summary,
        HAS_YFINANCE as _HAS_YFINANCE,
    )
    _FUNDAMENTALS_AVAILABLE = True
except Exception:
    FundamentalsProvider = None
    _FUNDAMENTALS_AVAILABLE = False
    _HAS_YFINANCE = False

    def fundamentals_compact_summary(_f: dict, is_india: bool = True) -> str:
        return "\u2014"

try:
    from mutual_funds_provider import MutualFundsProvider, swing_context as mf_swing_context
    _MF_AVAILABLE = True
except Exception:
    MutualFundsProvider = None
    _MF_AVAILABLE = False

    def mf_swing_context(_d: dict) -> dict:
        return {}

ACCOUNT_SIZE = 1_000_000
RISK_PCT     = 0.01

# ── Sector map (broad category) ──────────────────────────────────────────────
SECTOR_MAP = {
    # Banking
    "HDFCBANK":"Banking","ICICIBANK":"Banking","SBIN":"Banking","AXISBANK":"Banking",
    "KOTAKBANK":"Banking","INDUSINDBK":"Banking","BANDHANBNK":"Banking","FEDERALBNK":"Banking",
    "IDFCFIRSTB":"Banking","AUBANK":"Banking","CANBK":"Banking","BANKBARODA":"Banking",
    "PNB":"Banking","UNIONBANK":"Banking","IDBI":"Banking","RBLBANK":"Banking",
    "DCBBANK":"Banking","KTKBANK":"Banking","KARURVYSYA":"Banking","TVSHLTD":"Banking",
    "INDOTHAI":"Banking","ESAFSFB":"Banking","SURYODAY":"Banking","UJJIVAN":"Banking",
    "EQUITASBNK":"Banking","UTKARSHBNK":"Banking","JANA":"Banking",
    # IT / Technology
    "TCS":"IT","INFY":"IT","WIPRO":"IT","HCLTECH":"IT","TECHM":"IT","LTIM":"IT",
    "MPHASIS":"IT","COFORGE":"IT","PERSISTENT":"IT","KPITTECH":"IT","OFSS":"IT",
    "NINSYS":"IT","MASTEK":"IT","NIITTECH":"IT","INTELLECT":"IT","CMSINFO":"IT",
    "TATAELXSI":"IT","NEWGEN":"IT","TANLA":"IT","LTTS":"IT","ZENSARTECH":"IT",
    # FMCG
    "HINDUNILVR":"FMCG","ITC":"FMCG","NESTLEIND":"FMCG","BRITANNIA":"FMCG",
    "DABUR":"FMCG","MARICO":"FMCG","COLPAL":"FMCG","GODREJCP":"FMCG",
    "ZYDUSWELL":"FMCG","BAJAJCON":"FMCG","CCL":"FMCG","PKTEA":"FMCG",
    "HONASA":"FMCG","GMBREW":"FMCG","HNDFDS":"FMCG","TRAVELFOOD":"FMCG",
    "PRSMJOHNSN":"FMCG","BIKAJI":"FMCG","DEVYANI":"FMCG","SAPPHIRE":"FMCG",
    "WESTLIFE":"FMCG","JUBLFOOD":"FMCG","VARUN":"FMCG","PATANJALI":"FMCG",
    "EMAMILTD":"FMCG","JYOTHYLAB":"FMCG","GILLETTE":"FMCG",
    # Pharma / Healthcare
    "SUNPHARMA":"Pharma","DRREDDY":"Pharma","CIPLA":"Pharma","DIVISLAB":"Pharma",
    "TORNTPHARM":"Pharma","LUPIN":"Pharma","AUROPHARMA":"Pharma","ALKEM":"Pharma",
    "IPCALAB":"Pharma","GLENMARK":"Pharma","GRANULES":"Pharma","LAURUSLABS":"Pharma",
    "AJANTPHARM":"Pharma","NATCOPHARM":"Pharma","EMCURE":"Pharma","JBCHEPHARM":"Pharma",
    "JAGSNPHARM":"Pharma","BLISSGVS":"Pharma","SHILPAMED":"Pharma","SMSPHARMA":"Pharma",
    "VENUSREM":"Pharma","AKUMS":"Pharma","SENORES":"Pharma","ENTERO":"Pharma",
    "MEDPLUS":"Pharma","ALIVUS":"Pharma","ASTERDM":"Pharma","SAILIFE":"Pharma",
    "PFOCUS":"Pharma","SOLARA":"Pharma","BIOCON":"Pharma","SEQUENT":"Pharma",
    "AAVAS":"NBFC","LAURUS":"Pharma","STRIDES":"Pharma","SUDARSCHEM":"Chemicals",
    "NEULANDLAB":"Pharma","PIRAMALPHA":"Pharma","YATHARTH":"Pharma","RAINBOW":"Pharma",
    # Auto & Auto Ancillaries
    "MARUTI":"Auto","TATAMOTORS":"Auto","HEROMOTOCO":"Auto","EICHERMOT":"Auto",
    "TVSMOTOR":"Auto","ASHOKLEY":"Auto","TIINDIA":"Auto","MOTHERSON":"Auto","M&M":"Auto",
    "FORCEMOT":"Auto","GNA":"Auto","SHRIPISTON":"Auto","SANSERA":"Auto",
    "LUMAXTECH":"Auto","PRICOLLTD":"Auto","WHEELS":"Auto","SETCO":"Auto",
    "SONAMLTD":"Auto","CARRARO":"Auto","SCHAEFFLER":"Auto","TIMKEN":"Auto",
    "SPAL":"Auto","APARINDS":"Auto","ENDURANCE":"Auto","MINDA":"Auto",
    "SUPRAJIT":"Auto","CRAFTSMAN":"Auto","STARBUS":"Auto","EXIDEIND":"Auto",
    "AMARON":"Auto","BORORENEW":"Auto","MINDAIND":"Auto","SUBROS":"Auto",
    "FIEM":"Auto","SUNDRMFAST":"Auto","JBMA":"Auto","PRICOL":"Auto",
    # Metals & Mining
    "TATASTEEL":"Metals","HINDALCO":"Metals","JSWSTEEL":"Metals","SAIL":"Metals",
    "VEDL":"Metals","NMDC":"Metals","HINDZINC":"Metals","APLAPOLLO":"Metals",
    "JINDALSTEL":"Metals","HINDCOPPER":"Metals","GPIL":"Metals","WELCORP":"Metals",
    "JINDALSAW":"Metals","NELCAST":"Metals","BHARATFORG":"Metals",
    "GRAPHITE":"Metals","STEELCAS":"Metals","SARDAEN":"Metals","LLOYDSME":"Metals",
    "RATNAMANI":"Metals","TIGL":"Metals","MSTCLTD":"Metals","MOIL":"Metals",
    "GMDC":"Metals","MGEL":"Metals","NILE":"Metals","KALYANKJIL":"Consumer",
    "MANAKSIA":"Metals","JSWHL":"Metals","JSWISPL":"Metals","NSLNISP":"Metals",
    "SSWL":"Metals","SANDUMA":"Metals","SUNFLAG":"Metals",
    # Cables & Wires
    "KEI":"Cables","PRECWIRE":"Cables","STLTECH":"Cables","SUMEETINDS":"Cables",
    "SPECTRUM":"Cables","FINOLEX":"Cables","POLYCAB":"Cables","CABINDIA":"Cables",
    "RR":"Cables","INDOTECH":"Cables",
    # Electronic Components & Defense Electronics
    "CENTUM":"Electronics","SYRMA":"Electronics","DATAPATTNS":"Electronics",
    "AXISCADES":"Electronics","AEROFLEX":"Electronics","VOLTAMP":"Cap Goods",
    "POWERINDIA":"Electronics","TDPOWERSYS":"Cap Goods","KRN":"Electronics",
    "ADVAIT":"Electronics","INOXINDIA":"Electronics","KAYNES":"Electronics",
    "AMBER":"Electronics","PGEL":"Electronics","TEJAS":"Electronics",
    "SGIL":"Electronics","AVALON":"Electronics","ELCOMPCORP":"Electronics",
    "ELIN":"Electronics","VIMTALABS":"Electronics","BHEL":"Electronics",
    # Capital Goods / Engineering
    "ABB":"Cap Goods","CUMMINSIND":"Cap Goods","SIEMENS":"Cap Goods",
    "THERMAX":"Cap Goods","KIRLOSENG":"Cap Goods",
    "RPSGVENT":"Cap Goods","TIIL":"Cap Goods","LOKESHMACH":"Cap Goods","ACI":"Cap Goods",
    "PIXTRANS":"Cap Goods","KMEW":"Cap Goods","AIAENG":"Cap Goods",
    "ELGI":"Cap Goods","GRINDMASTER":"Cap Goods","RITEFIL":"Cap Goods",
    "ISGEC":"Cap Goods","TRIVENIENG":"Cap Goods","TEXRAIL":"Cap Goods",
    "RIIL":"Cap Goods","PATELENG":"Cap Goods","KNRCON":"Infra",
    "DEEDEV":"Cap Goods","CGPOWER":"Cap Goods","GEPIL":"Cap Goods","INOXAIR":"Cap Goods",
    "GRSE":"Cap Goods",
    "MDL":"Cap Goods","COCHINSHIP":"Cap Goods","BEML":"Cap Goods","MAZDOCK":"Cap Goods",
    "SKIPPER":"Cap Goods","KECL":"Cap Goods","KALPATPOWR":"Cap Goods","SANGHVI":"Cap Goods",
    "ELGIEQUIP":"Cap Goods","KIRLOSBROS":"Cap Goods","POWERMECH":"Cap Goods","NRAIL":"Cap Goods",
    "ESAB":"Cap Goods","HONAUT":"Cap Goods","3MINDIA":"Cap Goods",
    # Energy & Power
    "RELIANCE":"Energy","ONGC":"Energy","BPCL":"Energy","IOC":"Energy","HINDPETRO":"Energy",
    "GAIL":"Energy","COALINDIA":"Energy","NTPC":"Energy","POWERGRID":"Energy",
    "TATAPOWER":"Energy","NLCINDIA":"Energy","MRPL":"Energy","CHENNPETRO":"Energy",
    "SPLPETRO":"Energy","ADANIPOWER":"Energy","TORNTPOWER":"Energy",
    "CESC":"Energy","JPPOWER":"Energy","RPOWER":"Energy","GIPCL":"Energy",
    "JSWENERGY":"Energy","INOXWIND":"Energy",
    # Renewable Energy / Solar
    "WAAREEENER":"Renewable","ACMESOLAR":"Renewable","ADANIENSOL":"Renewable",
    "ATHERENERG":"Renewable","PREMIERENE":"Renewable","ADANIGREEN":"Renewable",
    "SUZLON":"Renewable","WINDWORLD":"Renewable","KENERGY":"Renewable",
    "INDIGRID":"Renewable","GREENKO":"Renewable","RATTANINDIA":"Renewable",
    "WEBSOL":"Renewable","PREMIER":"Renewable","REGEN":"Renewable","AVAADA":"Renewable",
    # Chemicals / Specialty Chemicals
    "NAVINFLUOR":"Chemicals","NOCIL":"Chemicals","GUJALKALI":"Chemicals",
    "AETHER":"Chemicals","DCMSHRIRAM":"Chemicals","DENORA":"Chemicals",
    "COMSYN":"Chemicals","PRAJIND":"Chemicals","DEEPINDS":"Chemicals",
    "LINCOLN":"Chemicals","FINEORG":"Chemicals","DEEPAKFERT":"Chemicals",
    "TATACHEM":"Chemicals","AARTI":"Chemicals","VINATI":"Chemicals",
    "CLEAN":"Chemicals","NEOGEN":"Chemicals","GALAXYSURF":"Chemicals",
    "PCBL":"Chemicals","SRF":"Chemicals","ATUL":"Chemicals",
    "FLUOROCHEM":"Chemicals","CAMLIN":"Chemicals","BASF":"Chemicals",
    "ALKYLAMINE":"Chemicals",
    "ROSSARI":"Chemicals","TRANSPEK":"Chemicals","DEEPAKNTR":"Chemicals",
    "EPIGRAL":"Chemicals","CHEMCON":"Chemicals","PAUSHAKLTD":"Chemicals",
    # Sugar
    "RENUKA":"Sugar","TRIVENI":"Sugar","BALRAMCHIN":"Sugar","DALMIASUG":"Sugar",
    "DHAMPURSUG":"Sugar","AVADHSUGAR":"Sugar","MAWANASUG":"Sugar","KMSUGAR":"Sugar",
    "UTTAMSUGAR":"Sugar","UGARSUGAR":"Sugar","DWARKESH":"Sugar",
    "DHAMPUR":"Sugar","SIMBHAOLI":"Sugar",
    # Textiles & Apparel
    "ARVIND":"Textiles","SANGAMIND":"Textiles","RUBYMILLS":"Textiles",
    "SPORTKING":"Textiles","NITINSPIN":"Textiles","NAHARSPING":"Textiles",
    "LGBBROSLTD":"Textiles","NITIRAJ":"Textiles","ABCOTS":"Textiles",
    "ICIL":"Textiles","SALONA":"Textiles","STYLAMIND":"Textiles",
    "STYLEBAAZA":"Textiles","MANOMAY":"Textiles","SHIVAUM":"Textiles",
    "VARDHMAN":"Textiles","ALOKIND":"Textiles","WELSPUNIND":"Textiles",
    "RAYMOND":"Textiles","GRASIM":"Textiles","TRIDENT":"Textiles",
    "PAGES":"Textiles","KITEX":"Textiles","RUPA":"Textiles",
    # Packaging
    "EPL":"Packaging","JINDALPOLY":"Packaging","PREMIERPOL":"Packaging",
    "XPROINDIA":"Packaging","ORICONENT":"Packaging","SESHAPAPER":"Packaging",
    "MKTGCD":"Packaging","UFLEX":"Packaging","HUHTAMAKI":"Packaging",
    "SMVD":"Packaging","KANSAINER":"Packaging",
    # Infrastructure / Construction
    "ADANIENT":"Infra","ADANIPORTS":"Infra","L&T":"Infra","IRB":"Infra",
    "CEIGALL":"Infra","TEXINFRA":"Infra","MANGLMCEM":"Infra","BHAGYANGR":"Infra",
    "GODAVARIB":"Infra","HGINFRA":"Infra","GPPL":"Infra",
    "PNC":"Infra","ASHOKA":"Infra","SADBHAV":"Infra","NBCC":"Infra",
    "RITES":"Infra","IRCON":"Infra","RVNL":"Infra","RAIL":"Infra",
    # Financial Services
    "BAJFINANCE":"Financials","BAJAJFINSV":"Financials","CHOLAFIN":"Financials",
    "M&MFIN":"Financials","MUTHOOTFIN":"Financials","MANAPPURAM":"Financials",
    "LICHSGFIN":"Financials","PFC":"Financials","RECLTD":"Financials",
    "SHRIRAMFIN":"Financials","MCX":"Financials","ANGELONE":"Financials",
    "BSE":"Financials","ANANDRATHI":"Financials","DBSTOCKBRO":"Financials",
    "ABSLAMC":"Financials","MANCREDIT":"Financials","SAMMAANCAP":"Financials",
    "ONELIFECAP":"Financials","TFCILTD":"Financials","STARHEALTH":"Financials",
    "GROWW":"Financials","ICICISEC":"Financials","MOFSL":"Financials",
    "GEOJITFSL":"Financials","SMIFS":"Financials","CHOICEIN":"Financials",
    "HDFCLIFE":"Financials","SBILIFE":"Financials","ICICIPRU":"Financials",
    "NUVAMA":"Financials","MOTILALOFS":"Financials","5PAISA":"Financials",
    "IIFL":"Financials","CREDITACC":"Financials","KFINTECH":"Financials",
    "CAMS":"Financials","SBFC":"Financials","REPCO":"Financials",
    # Consumer Durables / Retail
    "TITAN":"Consumer","ASIANPAINT":"Consumer","PIDILITIND":"Consumer","HAVELLS":"Consumer",
    "VOLTAS":"Consumer","DIXON":"Consumer","CROMPTON":"Consumer","LENSKART":"Consumer",
    "THANGAMAYL":"Consumer","SENCO":"Consumer",
    "VSTIND":"Consumer","BAJAJELECTR":"Consumer","WHIRLPOOL":"Consumer",
    "BLUESTAR":"Consumer","SYMPHONY":"Consumer","ORIENTELEC":"Consumer",
    # Internet / Tech Platforms
    "NAUKRI":"Internet","ZOMATO":"Internet","PAYTM":"Internet","IRCTC":"Internet",
    "SWIGGY":"Internet","MAPMYINDIA":"Internet","INDIAMART":"Internet",
    "POLICYBZR":"Internet","DELHIVERY":"Internet",
    # Real Estate
    "DLF":"RealEstate","GODREJPROP":"RealEstate","OBEROIRLTY":"RealEstate","PRESTIGE":"RealEstate",
    "SOBHA":"RealEstate","BRIGADE":"RealEstate","MACROTECH":"RealEstate",
    "MAHLIFE":"RealEstate","SUNTECK":"RealEstate","KOLTEPATIL":"RealEstate",
    # Shipping & Logistics
    "GESHIP":"Shipping","SEAMECLTD":"Shipping","COASTCORP":"Shipping","JETFREIGHT":"Shipping",
    "SCI":"Shipping","SHREYAS":"Shipping","CONCOR":"Shipping","BLUEDART":"Shipping",
    "MAHLOG":"Shipping","TCI":"Shipping","TCIL":"Shipping",
    # Defense
    "DYNAMATECH":"Defense","MTARTECH":"Defense","BEL":"Defense","HAL":"Defense",
    "BDSL":"Defense","PARAS":"Defense","MIDHANI":"Defense","ASTRA":"Defense",
    "IDEAFORGE":"Defense","ZEN":"Defense","ELCIDSIMP":"Defense",
    # Agri / Food Processing
    "AVANTIFEED":"Agri","TIRUPATIFL":"Agri",
    "KRBL":"Agri","LT":"Agri","LAKSHMI":"Agri",
    "VENKYS":"Agri","SUGARIND":"Agri","SRIKALAHASTHI":"Agri",
    # Other
    "STAR":"Other","SGMART":"Other","MWL":"Other","AVL":"Other",
    "DCI":"Other","SBC":"Other","DBOL":"Other","LEMERITE":"Other","MEGASTAR":"Other",
    "NDLVENTURE":"Other","JPOLYINVST":"Other","TEAMGTY":"Other","SOUTHWEST":"Other",
    "NARMADA":"Other","PASHUPATI":"Other","PRIVISCL":"Other","SAKAR":"Other",
    "AERONEU":"Other","LGEINDIA":"Other","GRMOVER":"Other",
}

# ── Industry map (sub-sector level) ──────────────────────────────────────────
INDUSTRY_MAP = {
    # Banking - PSU
    "SBIN":"PSU Banks","CANBK":"PSU Banks","BANKBARODA":"PSU Banks","PNB":"PSU Banks",
    "UNIONBANK":"PSU Banks","IDBI":"PSU Banks",
    # Banking - Private
    "HDFCBANK":"Private Banks","ICICIBANK":"Private Banks","AXISBANK":"Private Banks",
    "KOTAKBANK":"Private Banks","INDUSINDBK":"Private Banks","FEDERALBNK":"Private Banks",
    "IDFCFIRSTB":"Private Banks","RBLBANK":"Private Banks",
    # Banking - Small Finance / Regional
    "BANDHANBNK":"Small Finance Banks","AUBANK":"Small Finance Banks",
    "ESAFSFB":"Small Finance Banks","SURYODAY":"Small Finance Banks",
    "UJJIVAN":"Small Finance Banks","EQUITASBNK":"Small Finance Banks",
    "UTKARSHBNK":"Small Finance Banks","JANA":"Small Finance Banks",
    "DCBBANK":"Regional Banks","KTKBANK":"Regional Banks","KARURVYSYA":"Regional Banks",
    "TVSHLTD":"Regional Banks","INDOTHAI":"Regional Banks",
    # IT Services
    "TCS":"IT Services","INFY":"IT Services","WIPRO":"IT Services","HCLTECH":"IT Services",
    "TECHM":"IT Services","LTIM":"IT Services","MPHASIS":"IT Services",
    "COFORGE":"IT Services","PERSISTENT":"IT Services","KPITTECH":"IT Services",
    "OFSS":"IT Services","NINSYS":"IT Services","MASTEK":"IT Services",
    "ZENSARTECH":"IT Services","NIITTECH":"IT Services","CMSINFO":"IT Services",
    "NEWGEN":"IT Services","TANLA":"IT Services","LTTS":"IT Engineering",
    "TATAELXSI":"IT Engineering","INTELLECT":"IT Products","AXISCADES":"IT Engineering",
    # Electronic Components & Defense Electronics
    "CENTUM":"Electronic Components","SYRMA":"Electronic Components",
    "DATAPATTNS":"Defense Electronics","AEROFLEX":"Electronic Components",
    "KRN":"Electronic Components","ADVAIT":"Electronic Components",
    "INOXINDIA":"Electronic Components","KAYNES":"Electronic Components",
    "AMBER":"Electronic Components","PGEL":"Electronic Components",
    "SGIL":"Electronic Components","AVALON":"Electronic Components",
    "ELIN":"Electronic Components","ELCOMPCORP":"Electronic Components",
    "VIMTALABS":"Electronic Components",
    # Electrical Equipment & Cables
    "KEI":"Cables & Wires","PRECWIRE":"Cables & Wires","SUMEETINDS":"Cables & Wires",
    "SPECTRUM":"Cables & Wires","STLTECH":"Optical Fiber Cables",
    "FINOLEX":"Cables & Wires","POLYCAB":"Cables & Wires","CABINDIA":"Cables & Wires",
    "RR":"Cables & Wires","INDOTECH":"Cables & Wires","APARINDS":"Cables & Wires",
    "VOLTAMP":"Transformers","POWERINDIA":"Electrical Equipment",
    "TDPOWERSYS":"Electrical Equipment","ABB":"Electrical Equipment",
    "SIEMENS":"Electrical Equipment","TEJAS":"Optical Networking",
    # FMCG - Personal Care
    "HINDUNILVR":"FMCG - Personal Care","DABUR":"FMCG - Personal Care",
    "MARICO":"FMCG - Personal Care","COLPAL":"FMCG - Personal Care",
    "GODREJCP":"FMCG - Personal Care","BAJAJCON":"FMCG - Personal Care",
    "HONASA":"FMCG - Personal Care","EMAMILTD":"FMCG - Personal Care",
    "JYOTHYLAB":"FMCG - Personal Care","GILLETTE":"FMCG - Personal Care",
    # FMCG - Foods & Beverages / QSR
    "ITC":"FMCG - Foods","NESTLEIND":"FMCG - Foods","BRITANNIA":"FMCG - Foods",
    "ZYDUSWELL":"FMCG - Foods","CCL":"FMCG - Beverages","GMBREW":"FMCG - Beverages",
    "PKTEA":"FMCG - Tea","HNDFDS":"FMCG - Foods","TRAVELFOOD":"FMCG - Foods",
    "PRSMJOHNSN":"FMCG - Foods","BIKAJI":"FMCG - Foods","PATANJALI":"FMCG - Foods",
    "VARUN":"FMCG - Beverages",
    "DEVYANI":"QSR - KFC/Pizza Hut","SAPPHIRE":"QSR","WESTLIFE":"QSR - McDonald's","JUBLFOOD":"QSR - Domino's",
    # Pharma - Formulations
    "SUNPHARMA":"Pharma Formulations","DRREDDY":"Pharma Formulations",
    "CIPLA":"Pharma Formulations","DIVISLAB":"Pharma Formulations",
    "TORNTPHARM":"Pharma Formulations","LUPIN":"Pharma Formulations",
    "ALKEM":"Pharma Formulations","IPCALAB":"Pharma Formulations",
    "GLENMARK":"Pharma Formulations","AJANTPHARM":"Pharma Formulations",
    "NATCOPHARM":"Pharma Formulations","EMCURE":"Pharma Formulations",
    "JBCHEPHARM":"Pharma Formulations","BLISSGVS":"Pharma Formulations",
    "SENORES":"Pharma Formulations","PFOCUS":"Pharma Formulations",
    "SOLARA":"Pharma Formulations","STRIDES":"Pharma Formulations",
    "NEULANDLAB":"Pharma API","PIRAMALPHA":"Pharma Formulations",
    # Pharma - API / Specialty
    "AUROPHARMA":"Pharma API","GRANULES":"Pharma API","LAURUSLABS":"Pharma API",
    "LAURUS":"Pharma API","JAGSNPHARM":"Pharma API","SMSPHARMA":"Pharma API",
    "VENUSREM":"Pharma API","AKUMS":"Pharma Contract Mfg","SUDARSCHEM":"Pharma API",
    "BIOCON":"Pharma API","SEQUENT":"Pharma API",
    # Healthcare Services
    "SHILPAMED":"Medical Devices","ASTERDM":"Hospitals","MEDPLUS":"Pharmacy Retail",
    "SAILIFE":"Healthcare Services","ALIVUS":"Healthcare Services",
    "ENTERO":"Pharma Distribution","YATHARTH":"Hospitals","RAINBOW":"Hospitals",
    # Auto - OEM
    "MARUTI":"Auto OEM - 4W","TATAMOTORS":"Auto OEM - 4W","M&M":"Auto OEM - 4W",
    "HEROMOTOCO":"Auto OEM - 2W","TVSMOTOR":"Auto OEM - 2W","EICHERMOT":"Auto OEM - 2W",
    "ASHOKLEY":"Auto OEM - CV","FORCEMOT":"Auto OEM - CV",
    "TIINDIA":"Auto Ancillaries","MOTHERSON":"Auto Ancillaries",
    "STARBUS":"Auto OEM - CV",
    # Auto Ancillaries - Forgings & Castings
    "BHARATFORG":"Metal Forgings & Castings","GNA":"Metal Forgings & Castings",
    "NELCAST":"Metal Forgings & Castings","SHRIPISTON":"Metal Forgings & Castings",
    "SANSERA":"Metal Forgings & Castings","CARRARO":"Metal Forgings & Castings",
    "CRAFTSMAN":"Metal Forgings & Castings","JBMA":"Metal Forgings & Castings",
    "SUNDRMFAST":"Metal Forgings & Castings",
    # Auto Ancillaries - Other
    "LUMAXTECH":"Auto Ancillaries","PRICOLLTD":"Auto Ancillaries",
    "WHEELS":"Auto Ancillaries","SETCO":"Auto Ancillaries","SONAMLTD":"Auto Ancillaries",
    "ENDURANCE":"Auto Ancillaries","MINDA":"Auto Ancillaries","MINDAIND":"Auto Ancillaries",
    "SUPRAJIT":"Auto Ancillaries","SUBROS":"Auto Ancillaries","FIEM":"Auto Ancillaries",
    "PRICOL":"Auto Ancillaries","SPAL":"Auto Ancillaries",
    "SCHAEFFLER":"Bearings","TIMKEN":"Bearings",
    "EXIDEIND":"Auto Batteries","AMARON":"Auto Batteries",
    # Metals - Steel
    "TATASTEEL":"Steel","JSWSTEEL":"Steel","SAIL":"Steel","JINDALSTEL":"Steel",
    "GPIL":"Steel - Sponge Iron","STEELCAS":"Steel Tubes","LLOYDSME":"Steel",
    "SARDAEN":"Steel","WELCORP":"Steel Pipes","JINDALSAW":"Steel Pipes",
    "APLAPOLLO":"Steel Pipes","RATNAMANI":"Steel Pipes","NSLNISP":"Steel",
    "JSWISPL":"Steel","SUNFLAG":"Steel","SSWL":"Steel - Wheels",
    "MANAKSIA":"Steel","TIGL":"Steel - Structural",
    # Metals - Non-Ferrous / Mining
    "HINDALCO":"Aluminium","VEDL":"Diversified Metals","NMDC":"Metal & Mining",
    "HINDZINC":"Zinc & Lead","HINDCOPPER":"Copper Mining",
    "GRAPHITE":"Graphite Electrodes","MOIL":"Manganese Mining","GMDC":"Coal & Minerals",
    "MSTCLTD":"Metal & Mining","MGEL":"Metal & Mining",
    "KALYANKJIL":"Gold Jewelry",  # (classified under jewelry not metals)
    "NILE":"Metal & Mining","SANDUMA":"Metal & Mining",
    # Energy - Oil & Gas
    "RELIANCE":"Oil & Gas","ONGC":"Oil & Gas","BPCL":"Oil Refining","IOC":"Oil Refining",
    "HINDPETRO":"Oil Refining","GAIL":"Gas Distribution","MRPL":"Oil Refining",
    "CHENNPETRO":"Oil Refining","SPLPETRO":"Petroleum Products",
    # Energy - Power
    "COALINDIA":"Coal & Mining","NTPC":"Power Generation","POWERGRID":"Power Transmission",
    "TATAPOWER":"Power Generation","NLCINDIA":"Power Generation",
    "ADANIPOWER":"Power Generation","TORNTPOWER":"Power Generation",
    "CESC":"Power Generation","JPPOWER":"Power Generation",
    "RPOWER":"Power Generation","GIPCL":"Power Generation",
    "JSWENERGY":"Power Generation",
    # Renewable Energy
    "WAAREEENER":"Solar Panels","ACMESOLAR":"Solar IPP","ADANIENSOL":"Solar IPP",
    "ATHERENERG":"EV Ecosystem","PREMIERENE":"Renewable Energy",
    "ADANIGREEN":"Renewable Energy","SUZLON":"Wind Energy","INOXWIND":"Wind Energy",
    # Chemicals - Specialty
    "NAVINFLUOR":"Specialty Chemicals - Fluorine","NOCIL":"Specialty Chemicals",
    "GUJALKALI":"Specialty Chemicals - Alkali","AETHER":"Specialty Chemicals",
    "DENORA":"Specialty Chemicals","COMSYN":"Specialty Chemicals",
    "PRAJIND":"Ethanol / Bio Energy","DEEPINDS":"Specialty Chemicals",
    "LINCOLN":"Specialty Chemicals","FINEORG":"Specialty Chemicals",
    "VINATI":"Specialty Chemicals","CLEAN":"Specialty Chemicals",
    "NEOGEN":"Specialty Chemicals","GALAXYSURF":"Specialty Chemicals",
    "PCBL":"Carbon Black","SRF":"Specialty Chemicals","ATUL":"Specialty Chemicals",
    "FLUOROCHEM":"Specialty Chemicals - Fluorine","ALKYLAMINE":"Specialty Chemicals",
    "CAMLIN":"Specialty Chemicals","BASF":"Specialty Chemicals",
    "AARTI":"Specialty Chemicals",
    # Agri Chemicals / Fertilisers
    "DCMSHRIRAM":"Agri Chemicals & Fertilisers","TATACHEM":"Agri Chemicals & Fertilisers",
    "DEEPAKFERT":"Agri Chemicals & Fertilisers",
    # Sugar
    "RENUKA":"Sugar","TRIVENI":"Sugar","BALRAMCHIN":"Sugar","DALMIASUG":"Sugar",
    "DHAMPURSUG":"Sugar","AVADHSUGAR":"Sugar","MAWANASUG":"Sugar","KMSUGAR":"Sugar",
    "UTTAMSUGAR":"Sugar","UGARSUGAR":"Sugar","DWARKESH":"Sugar",
    "DHAMPUR":"Sugar","SIMBHAOLI":"Sugar",
    # Textiles - Spinning / Yarn
    "NITINSPIN":"Textiles - Spinning","NAHARSPING":"Textiles - Spinning",
    "SPORTKING":"Textiles - Synthetic","SANGAMIND":"Textiles - Fabric",
    "RUBYMILLS":"Textiles - Fabric","LGBBROSLTD":"Textiles - Fabric",
    "NITIRAJ":"Textiles - Fabric","ICIL":"Textiles - Fabric","SALONA":"Textiles",
    "ABCOTS":"Cotton / Agri","ARVIND":"Textiles - Apparel","SHIVAUM":"Textiles",
    "MANOMAY":"Textiles","STYLAMIND":"Textiles - Home",
    "VARDHMAN":"Textiles - Spinning","ALOKIND":"Textiles - Fabric",
    "WELSPUNIND":"Textiles - Home","RAYMOND":"Textiles - Apparel",
    "GRASIM":"Textiles - Viscose","TRIDENT":"Textiles - Home",
    "KITEX":"Textiles - Apparel","RUPA":"Textiles - Innerwear",
    # Apparel / Retail
    "STYLEBAAZA":"Apparel Retail","PAGES":"Apparel Retail",
    # Packaging
    "EPL":"Packaging - Laminates","JINDALPOLY":"Packaging - Films",
    "PREMIERPOL":"Packaging - Plastics","XPROINDIA":"Packaging - Films",
    "ORICONENT":"Packaging - Containers","SESHAPAPER":"Paper & Packaging",
    "UFLEX":"Packaging - Films","HUHTAMAKI":"Packaging - Laminates",
    # Capital Goods / Engineering
    "CUMMINSIND":"Engines & Compressors","THERMAX":"Heat Exchange & Boilers",
    "KIRLOSENG":"Pumps & Compressors","BHEL":"Heavy Engineering",
    "BEL":"Defense Electronics","TIIL":"Textile Machinery",
    "LOKESHMACH":"Machine Tools","AIAENG":"Cutting Tools",
    "RPSGVENT":"Ventilation Equipment","ACI":"Engineering",
    "PIXTRANS":"Power Transmission","KMEW":"Engineering",
    "ELGI":"Compressors","GRINDMASTER":"Grinders & Machines",
    "ISGEC":"Heavy Engineering","TRIVENIENG":"Engineering",
    "TEXRAIL":"Railway Equipment","RIIL":"Engineering","PATELENG":"EPC",
    "DEEDEV":"Industrial Piping & Pressure Vessels","KNRCON":"Roads & Highways","RITEFIL":"Filtration",
    # Defense
    "DYNAMATECH":"Aerospace & Defense","MTARTECH":"Aerospace & Defense",
    "HAL":"Aerospace & Defense",
    "BDSL":"Defense","PARAS":"Defense","MIDHANI":"Aerospace Alloys",
    "ASTRA":"Defense","IDEAFORGE":"Drones","ZEN":"Defense",
    "GRSE":"Shipbuilding Defense","COCHINSHIP":"Shipbuilding","MDL":"Submarine Builder",
    "ROSSELL":"Aerospace Components","ELCOMPONENT":"Defense Electronics",
    "BEML":"Heavy Engineering Defense","MAZDOCK":"Shipbuilding",
    # Infrastructure
    "ADANIENT":"Diversified Infra","ADANIPORTS":"Ports & Logistics",
    "L&T":"EPC & Construction","IRB":"Roads & Highways",
    "CEIGALL":"Roads & Highways","TEXINFRA":"Construction",
    "MANGLMCEM":"Cement","BHAGYANGR":"Roads & Highways","GODAVARIB":"Irrigation",
    "HGINFRA":"Roads & Highways","PNC":"Roads & Highways",
    "ASHOKA":"Roads & Highways","NBCC":"Govt Construction",
    "RITES":"Railway Consultancy","IRCON":"Railway Construction","RVNL":"Railway Construction",
    "GPPL":"Ports & Logistics","CONCOR":"Rail Logistics","BLUEDART":"Air Logistics",
    "SHREYAS":"Shipping & Logistics","TCI":"Road Logistics","SCI":"Shipping",
    "DELHIVERY":"Last Mile Logistics","MAHLOG":"Logistics",
    "PSPPROJECT":"EPC","LIKHITHA":"Pipeline EPC","WABAG":"Water Treatment",
    "ALLCARGO":"Freight Logistics","GATI":"Road Logistics","SNOWMAN":"Cold Chain",
    "INDIAGRID":"Power Transmission InvIT","KALINDEE":"Rail Electrification",
    "APOLLOPIPE":"CPVC Pipes","PRINCEPIPE":"CPVC Pipes",
    # Cement
    "INDIACEM":"Cement","JKCEMENT":"Cement","RAMCOCEM":"Cement",
    "HEIDELBERG":"Cement","BIRLACORP":"Cement","SHREECEM":"Cement",
    "AMBUJACEM":"Cement","ACCIND":"Cement","DALMIACEM":"Cement",
    "JSWCEM":"Cement","NUVOCO":"Cement","SANGHI":"Cement",
    # Consumer - Retail / QSR / Hotels
    "DMART":"Retail - Hypermarket","VMART":"Value Retail","TRENT":"Retail - Fashion",
    "SPENCERS":"Retail","SHOPSTOP":"Retail - Dept Store",
    
    "BARBEQUE":"Casual Dining","SPECIALITY":"Casual Dining","JUBILANT":"Diversified Consumer",
    "INDHOTELS":"Hotels","EIHOTEL":"Hotels - Oberoi","LEMONTRE":"Budget Hotels",
    "CHALET":"Hotels","TAJGVK":"Hotels","SAMHI":"Hotels","VENTIVE":"Hospitality",
    "GMRINFRA":"Airports","INTERGLOBE":"Aviation","IRCTC":"Online Travel - Rail",
    "EASEMYTRIP":"Online Travel","MAHINDHOLIDAY":"Resorts & Tourism","WONDERLA":"Amusement Parks",
    # Consumer - Electronics / Appliances
    "WHIRLPOOL":"Home Appliances","VOLTAS":"Air Conditioning","CROMPTON":"Consumer Electricals",
    "ORIENTELEC":"Consumer Electricals","VGUARD":"Consumer Electricals","SYMPHONY":"Air Coolers",
    "BAJAJELEC":"Consumer Electricals","HAVELLS":"Consumer Electricals",
    "LLOYDS":"Air Conditioning","GODREJAP":"Home Appliances",
    # Consumer - Jewellery & Accessories
    "DPABHUSHAN":"Jewellery","GOLDIAM":"Jewellery",
    "VAIBHAVGBL":"Jewellery","SENCO":"Gold Jewelry","PCJEWELLER":"Jewellery",
    "THANGAMAYL":"Gold Jewelry","SKYGOLD":"Jewellery",
    # Consumer - Tiles / Sanitaryware / Home
    "CERA":"Sanitaryware","HINDWARE":"Sanitaryware","KAJARIACER":"Tiles",
    "ASIANTILES":"Tiles","SOMANY":"Tiles","ORIENTBELL":"Tiles",
    "GREENPANEL":"Wood Panels","CENTURYPLY":"Plywood","BOROSIL":"Glassware",
    # Consumer - Footwear
    "METRO":"Footwear","CAMPUS":"Footwear","BATA":"Footwear","RELAXO":"Footwear",
    "LIBERTY":"Footwear","KHADIM":"Footwear",
    # Media / Entertainment
    "SAREGAMA":"Music & Content","PVRINOX":"Multiplex","NAZARA":"Gaming",
    "DELTACORP":"Gaming & Casinos","SUNTV":"TV Broadcasting",
    "ZEEL":"TV Broadcasting","NETWORK18":"TV Broadcasting",
    # Financial Services
    "BAJFINANCE":"Consumer Finance","BAJAJFINSV":"Insurance & Finance",
    "CHOLAFIN":"Vehicle Finance","M&MFIN":"Vehicle Finance",
    "MUTHOOTFIN":"Gold Loans","MANAPPURAM":"Gold Loans",
    "LICHSGFIN":"Housing Finance","PFC":"Power Finance","RECLTD":"Power Finance",
    "SHRIRAMFIN":"Vehicle Finance","MANCREDIT":"NBFC","TFCILTD":"NBFC",
    "SAMMAANCAP":"Capital Markets","ONELIFECAP":"Capital Markets",
    "NUVAMA":"Wealth Management","MOTILALOFS":"Wealth Management",
    "MOFSL":"Wealth Management",
    "5PAISA":"Stock Broking","IIFL":"NBFC","CREDITACC":"Microfinance",
    "KFINTECH":"Financial Technology","CAMS":"Financial Technology",
    "SBFC":"NBFC","REPCO":"Housing Finance",
    "SPANDANA":"Microfinance","FUSION":"Microfinance","SATIN":"Microfinance",
    "HDFCAMC":"Asset Management","ABSLAMC":"Asset Management","UTIAMC":"Asset Management",
    "LICI":"Insurance - Life","GICRE":"Insurance - Reinsurance","NIACL":"Insurance - General",
    "HDFCLIFE":"Insurance - Life","SBILIFE":"Insurance - Life","MAXHEALTH":"Hospitals",
    "STARHEALTH":"Insurance - Health","CDSL":"Depository","IRFC":"Railway Finance",
    # Broking & Exchanges — grouped as Capital Markets for rally scanning
    "MCX":"Capital Markets","BSE":"Capital Markets",
    "ANANDRATHI":"Capital Markets",
    "ANGELONE":"Stock Broking","DBSTOCKBRO":"Stock Broking",
    "GROWW":"Stock Broking","ICICISEC":"Stock Broking",
    "GEOJITFSL":"Stock Broking","SMIFS":"Stock Broking","CHOICEIN":"Stock Broking",
    
    # Insurance
    
    "ICICIPRU":"Life Insurance",
    # Consumer
    "TITAN":"Jewelry & Watches",
    
    "ASIANPAINT":"Paints","PIDILITIND":"Adhesives & Chemicals",
    
    "BLUESTAR":"Air Conditioners",
    "BAJAJELECTR":"Consumer Electricals",
    "DIXON":"Consumer Electronics",
    "VSTIND":"Cigarettes",
    "LENSKART":"Eyewear Retail",
    # Internet / Platforms
    "NAUKRI":"Online Recruitment","ZOMATO":"Food Delivery","PAYTM":"Fintech",
    "SWIGGY":"Food Delivery",
    "MAPMYINDIA":"Digital Maps","INDIAMART":"B2B Marketplace",
    "POLICYBZR":"Insurance Technology",
    # Real Estate
    "DLF":"Real Estate - Residential","GODREJPROP":"Real Estate - Residential",
    "OBEROIRLTY":"Real Estate - Premium","PRESTIGE":"Real Estate - Residential",
    "SOBHA":"Real Estate - Residential","BRIGADE":"Real Estate - Residential",
    "MACROTECH":"Real Estate - Residential","MAHLIFE":"Real Estate - Residential",
    "SUNTECK":"Real Estate - Residential","KOLTEPATIL":"Real Estate - Residential",
    # Shipping
    "GESHIP":"Shipping","SEAMECLTD":"Shipping Services",
    "COASTCORP":"Logistics","JETFREIGHT":"Logistics",
    # Agri
    "AVANTIFEED":"Aquaculture / Shrimp Feed","TIRUPATIFL":"Flour Milling",
    "KRBL":"Rice / Agri","VENKYS":"Poultry & Agri",
}

SETUP_META = {
    "VCP":               ("tag-vcp",   "VCP Breakout",       "Buy above pivot on volume >=1.5x avg. Stop below base low."),
    "RANGE_EXPANSION":   ("tag-rexp",  "Range Expansion",    "Buy open next session after wide-range candle clears base. Stop 1 ATR below."),
    "MEAN_REVERSION":    ("tag-mr",    "Mean Reversion",     "Buy as price reclaims SMA20 or bounces off lower BB. Stop 2x ATR below."),
    "BREAKOUT_PULLBACK": ("tag-bp",    "Breakout Pullback",  "Buy first pullback to prior breakout support on dry volume. Stop below BO level."),
    "BREAKOUT":          ("tag-bo",    "Breakout",           "Buy on confirmation close above prior high. Stop below swing low."),
    "BULL_FLAG":         ("tag-bf",    "Bull Flag",          "Sharp pole + tight flag channel. Enter on breakout above flag high. Targets = flagpole measured move."),
}

def _f(v, d=0.0):
    try:
        if v in (None, "", "N/A"):
            return d
        return float(str(v).strip().replace("%", "").replace(",", "").replace("x", ""))
    except Exception:
        return d

def get_sector(symbol: str) -> str:
    base = symbol.replace(".NS","").replace(".BO","")
    return SECTOR_MAP.get(base, "Other")

def get_industry(symbol: str) -> str:
    base = symbol.replace(".NS","").replace(".BO","")
    return INDUSTRY_MAP.get(base, SECTOR_MAP.get(base, "Other"))


def compute_industry_breadth_all(
    ma_short: int = 20, ma_mid: int = 50, ma_long: int = 200
) -> dict[str, dict]:
    """
    For every industry in INDUSTRY_MAP, compute what % of its stocks are
    above 20 / 50 / 200-day MA using locally cached price CSVs.

    Trend stages (based on >20MA breadth):
      EMERGING  25-65%  — early accumulation, best setup zone
      BUILDING  65-80%  — trend gaining momentum
      EXTENDED  >80%    — watch for pullback
      WEAK      <25%    — avoid

    Returns  {industry_name: {total, above_20, pct_20ma, pct_50ma, pct_200ma,
                               stage, stage_color, stage_emoji}}
    """
    # Group INDUSTRY_MAP tickers by industry
    ind_stocks: dict[str, list[str]] = {}
    for ticker, industry in INDUSTRY_MAP.items():
        ind_stocks.setdefault(industry, []).append(ticker)

    result: dict[str, dict] = {}
    for industry, tickers in ind_stocks.items():
        a20 = a50 = a200 = total = 0
        for ticker in tickers:
            # Try NSE suffix first, then bare ticker
            rows: list[dict] = []
            for sym in (f"{ticker}.NS", ticker):
                rows = _load_price_rows_uncached(sym)
                if rows:
                    break
            if len(rows) < ma_short:
                continue
            closes = [_f(r.get("close")) for r in rows if _f(r.get("close")) > 0]
            if len(closes) < ma_short:
                continue
            last = closes[-1]
            total += 1
            if last > sum(closes[-ma_short:]) / ma_short:
                a20 += 1
            if len(closes) >= ma_mid and last > sum(closes[-ma_mid:]) / ma_mid:
                a50 += 1
            if len(closes) >= ma_long and last > sum(closes[-ma_long:]) / ma_long:
                a200 += 1

        if total == 0:
            continue
        pct_20 = round(a20 / total * 100)
        pct_50 = round(a50 / total * 100)
        pct_200 = round(a200 / total * 100)

        if pct_20 >= 80:
            stage, color, emoji = "EXTENDED",  "#f85149", "🔴"
        elif pct_20 >= 65:
            stage, color, emoji = "BUILDING",  "#e3b341", "🟡"
        elif pct_20 >= 25:
            stage, color, emoji = "EMERGING",  "#3fb950", "🟢"
        else:
            stage, color, emoji = "WEAK",      "#475569", "⚫"

        result[industry] = {
            "total":       total,
            "above_20":    a20,
            "pct_20ma":    pct_20,
            "pct_50ma":    pct_50,
            "pct_200ma":   pct_200,
            "stage":       stage,
            "stage_color": color,
            "stage_emoji": emoji,
        }
    return result


def _load_price_rows_uncached(symbol: str) -> list[dict]:
    """Load price rows preferring the file with the most recent data date."""
    candidates: list[Path] = []
    for suffix in ["_5096", "_3528", "_900", "_728", "_504", "_252", "_60"]:
        p = CACHE_DIR / f"{symbol}{suffix}.csv"
        if p.exists():
            candidates.append(p)

    best_rows: list[dict] = []
    best_date: str = ""

    for p in candidates:
        rows: list[dict] = []
        last_date = ""
        try:
            with open(p) as f:
                for row in csv.DictReader(f):
                    d = row.get("date", "")
                    if d:
                        last_date = d
                    rows.append({
                        "date":   d,
                        "open":   _f(row.get("open")),
                        "high":   _f(row.get("high")),
                        "low":    _f(row.get("low")),
                        "close":  _f(row.get("close")),
                        "volume": _f(row.get("volume")),
                    })
        except Exception:
            rows = []
        if rows and last_date > best_date:
            best_rows = rows
            best_date = last_date

    return best_rows


@lru_cache(maxsize=8192)
def load_price_rows(symbol: str, weekly: bool = False) -> list[dict]:
    rows = _load_price_rows_uncached(symbol)
    if not rows:
        return []
    return aggregate_weekly_bars(rows) if weekly else rows


def load_sparkline(symbol: str, n: int = 60) -> list[float]:
    """Load last n closes for sparkline from cached daily rows."""
    rows = load_price_rows(symbol, weekly=False)
    closes = [_f(r.get("close")) for r in rows if _f(r.get("close")) > 0]
    return closes[-n:] if closes else []


def current_expansion_metrics(rows: list[dict], lookback: int = 20) -> tuple[float | None, float | None]:
    if len(rows) < 2:
        return None, None
    current = rows[-1]
    current_close = _f(current.get("close"))
    current_high = _f(current.get("high"), current_close)
    current_low = _f(current.get("low"), current_close)
    if current_close <= 0:
        return None, None

    current_range = max(0.0, current_high - current_low)
    prior = rows[-(lookback + 1):-1]
    prior_ranges = [max(0.0, _f(r.get("high")) - _f(r.get("low"))) for r in prior]
    prior_ranges = [r for r in prior_ranges if r > 0]
    avg_range = (sum(prior_ranges) / len(prior_ranges)) if prior_ranges else 0.0
    rexp = (current_range / avg_range) if avg_range > 0 and current_range > 0 else None

    current_vol = _f(current.get("volume"))
    prior_vols = [_f(r.get("volume")) for r in prior]
    prior_vols = [v for v in prior_vols if v > 0]
    avg_vol = (sum(prior_vols) / len(prior_vols)) if prior_vols else 0.0
    vol_pct = (((current_vol / avg_vol) - 1.0) * 100.0) if avg_vol > 0 and current_vol > 0 else None
    return vol_pct, rexp


def compute_rs_metrics(rows: list[dict], weekly: bool) -> tuple[float | None, float | None]:
    closes = [_f(r.get("close")) for r in rows if _f(r.get("close")) > 0]
    if not closes:
        return None, None
    rs3_bars, rs6_bars = (13, 26) if weekly else (63, 126)
    rs3 = safe_return(closes, rs3_bars) * 100.0 if len(closes) > rs3_bars else None
    rs6 = safe_return(closes, rs6_bars) * 100.0 if len(closes) > rs6_bars else None
    return rs3, rs6


def pick_metric(primary: float, fallback: float | None, zero_is_missing: bool = True) -> float | None:
    if primary == 0.0 and zero_is_missing:
        return fallback
    return primary if primary == primary else fallback


def fmt_pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "&mdash;"
    if abs(value) < 0.05:
        return "&mdash;"
    return f"{value:+.1f}%" if signed else f"{value:.1f}%"


def fmt_x(value: float | None) -> str:
    if value is None:
        return "&mdash;"
    if abs(value) < 0.05:
        return "&mdash;"
    return f"{value:.2f}x"


# ── Run-history helpers ──────────────────────────────────────────────────────

def load_run_history() -> dict:
    """Load the persisted run-history JSON (last RUN_HISTORY_MAX runs)."""
    if not RUN_HISTORY_JSON.exists():
        return {"runs": []}
    try:
        return json.loads(RUN_HISTORY_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"runs": []}


def save_run_history(history: dict) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    RUN_HISTORY_JSON.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def update_run_history(signals: list[dict]) -> dict:
    """
    Append the current run's symbols to the history, trimming to RUN_HISTORY_MAX.
    Returns the updated history dict.
    """
    history = load_run_history()
    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "symbols": sorted({s.get("symbol", "") for s in signals if s.get("symbol")}),
    }
    runs: list[dict] = history.get("runs", [])
    runs.append(entry)
    # Keep only the most recent RUN_HISTORY_MAX runs
    history["runs"] = runs[-RUN_HISTORY_MAX:]
    save_run_history(history)
    return history


def count_appearances(symbol: str, history: dict) -> tuple[int, int]:
    """
    Return (count, total_runs) where count = number of runs in history
    that contain this symbol.
    """
    runs = history.get("runs", [])
    count = sum(1 for r in runs if symbol in r.get("symbols", []))
    return count, len(runs)


# ── Price-performance helpers ────────────────────────────────────────────────

def compute_price_performance(rows: list[dict]) -> dict:
    """
    Given daily OHLCV rows (sorted oldest→newest), compute price returns
    for 1W (5 bars), 1M (21 bars), 3M (63 bars), 6M (126 bars).
    Returns dict with keys: ret_1w, ret_1m, ret_3m, ret_6m (float|None).
    """
    closes = [_f(r.get("close")) for r in rows if _f(r.get("close")) > 0]
    if not closes:
        return {"ret_1w": None, "ret_1m": None, "ret_3m": None, "ret_6m": None}

    def _ret(bars: int) -> float | None:
        if len(closes) <= bars:
            return None
        base = closes[-(bars + 1)]
        if base <= 0:
            return None
        return (closes[-1] / base - 1.0) * 100.0

    return {
        "ret_1w": _ret(5),
        "ret_1m": _ret(21),
        "ret_3m": _ret(63),
        "ret_6m": _ret(126),
    }


def fmt_perf(value: float | None) -> str:
    """Format a performance return value as coloured HTML span."""
    if value is None:
        return '<span class="perf-na">—</span>'
    cls = "perf-up" if value >= 0 else "perf-dn"
    sign = "+" if value >= 0 else ""
    return f'<span class="{cls}">{sign}{value:.1f}%</span>'


def extract_pct(text: str, keys: list[str]) -> float | None:
    source = str(text or "")
    for key in keys:
        m = re.search(rf"{re.escape(key)}\s*[:=]\s*([+-]?\d+(?:\.\d+)?)%", source, flags=re.IGNORECASE)
        if m:
            return _f(m.group(1), 0.0)
    return None


def extract_debt_change(text: str) -> float | None:
    source = str(text or "")
    m = re.search(r"Debt[^\d+-]*([+-]?\d+(?:\.\d+)?)%", source, flags=re.IGNORECASE)
    if not m:
        return None
    val = _f(m.group(1), 0.0)
    if "↑" in source or "UP" in source.upper():
        return abs(val)
    if "↓" in source or "DOWN" in source.upper():
        return -abs(val)
    return val


def fmt_metric(value: float | None, signed: bool = True) -> str:
    if value is None:
        return "—"
    return f"{value:+.1f}%" if signed else f"{value:.1f}%"


def classify_trigger(text: str) -> str:
    t = str(text or "").upper()
    if any(k in t for k in ["POSITIVE", "TAILWIND", "STRONG", "IMPROVING", "SUPPORTIVE"]):
        return "pill-pos"
    if any(k in t for k in ["WEAK", "RISK", "HEADWIND", "UNFAVORABLE", "NEGATIVE"]):
        return "pill-neg"
    return "pill-neu"


def _has_value(v) -> bool:
    t = str(v or "").strip()
    return t not in {"", "\u2014", "UNKNOWN", "N/A", "NONE", "NULL"}


def _fundamentals_completeness(row: dict) -> tuple[int, float]:
    score = 0
    if _has_value(row.get("fundSummary")):
        score += 2
    if _has_value(row.get("triggerEarningsGrowth")):
        score += 2
    if _has_value(row.get("triggerDebtReduction")):
        score += 2
    if _has_value(row.get("triggerMacroTailwind") or row.get("macroTrigger") or row.get("triggerMacro")):
        score += 1
    if _has_value(row.get("triggerMarketTailwind") or row.get("marketTrigger") or row.get("triggerMarket")):
        score += 1
    return score, _f(row.get("score", 0))


def _pick_better_row(current: dict, candidate: dict) -> dict:
    c_key = _fundamentals_completeness(current)
    n_key = _fundamentals_completeness(candidate)
    return candidate if n_key > c_key else current


def _derive_macro_market(sig: dict) -> tuple[str, str]:
    regime_support = str(sig.get("regimeSupport") or "").upper()
    weekly_agreement = str(sig.get("weeklyAgreement") or "").upper()
    rs_score = _f(sig.get("rsScore"), 0.0)

    macro_trigger = "TAILWIND" if regime_support in {"STRONG", "SUPPORTIVE"} else "NEUTRAL_OR_HEADWIND"
    market_trigger = "TAILWIND" if weekly_agreement in {"STRONG", "SUPPORTIVE"} and rs_score > 0 else "MIXED"
    return macro_trigger, market_trigger


def _format_pct_trigger(prefix: str, value: float | None) -> str:
    if value is None:
        return f"{prefix}:UNKNOWN"
    sign = "+" if value >= 0 else ""
    return f"{prefix}:{sign}{value:.1f}%"


def _earnings_trigger_from_fundamentals(fund: dict | None) -> str:
    if not fund or fund.get("error"):
        return "UNKNOWN"

    eps_yoy = _f(fund.get("eps_yoy"), float("nan"))
    eps_qoq = _f(fund.get("eps_qoq"), float("nan"))
    rev_yoy = _f(fund.get("rev_yoy"), float("nan"))

    eps_yoy = None if eps_yoy != eps_yoy else eps_yoy
    eps_qoq = None if eps_qoq != eps_qoq else eps_qoq
    rev_yoy = None if rev_yoy != rev_yoy else rev_yoy

    strong = (eps_yoy is not None and eps_yoy >= 15.0) or (rev_yoy is not None and rev_yoy >= 12.0)
    weak = (eps_yoy is not None and eps_yoy <= -10.0) or (rev_yoy is not None and rev_yoy <= -5.0)

    parts: list[str] = []
    if eps_yoy is not None:
        parts.append(_format_pct_trigger("EPS_YOY", eps_yoy))
    if eps_qoq is not None:
        parts.append(_format_pct_trigger("EPS_QOQ", eps_qoq))
    if rev_yoy is not None:
        parts.append(_format_pct_trigger("REV_YOY", rev_yoy))

    if not parts:
        return "UNKNOWN"
    if strong:
        return "POSITIVE " + " / ".join(parts)
    if weak:
        return "WEAK " + " / ".join(parts)
    return "MIXED " + " / ".join(parts)


def _debt_trigger_from_fundamentals(fund: dict | None) -> str:
    if not fund or fund.get("error"):
        return "UNKNOWN"
    debt_trend = _f(fund.get("debt_trend_pct"), float("nan"))
    if debt_trend != debt_trend:
        return "UNKNOWN"
    if debt_trend <= -5.0:
        return f"POSITIVE Debt\u2193 {abs(debt_trend):.1f}%"
    if debt_trend >= 5.0:
        return f"RISK Debt\u2191 {debt_trend:.1f}%"
    return f"STABLE Debt {debt_trend:+.1f}%"


def hydrate_missing_fundamentals(signals: list[dict]) -> dict:
    stats = {
        "signals": len(signals or []),
        "needs_fundamentals": 0,
        "fund_summary_filled": 0,
        "earnings_filled": 0,
        "debt_filled": 0,
        "still_missing_summary": 0,
        "still_missing_earnings": 0,
        "still_missing_debt": 0,
        "fundamentals_available": _FUNDAMENTALS_AVAILABLE,
        "yfinance_available": _HAS_YFINANCE,
    }
    if not signals:
        return stats

    for sig in signals:
        if not _has_value(sig.get("triggerMacroTailwind")):
            macro, _ = _derive_macro_market(sig)
            sig["triggerMacroTailwind"] = macro
        if not _has_value(sig.get("triggerMarketTailwind")):
            _, market = _derive_macro_market(sig)
            sig["triggerMarketTailwind"] = market

    if not _FUNDAMENTALS_AVAILABLE:
        return stats

    to_fetch: list[str] = []
    for sig in signals:
        needs_summary = not _has_value(sig.get("fundSummary"))
        needs_eps = not _has_value(sig.get("triggerEarningsGrowth"))
        needs_debt = not _has_value(sig.get("triggerDebtReduction"))
        if needs_summary or needs_eps or needs_debt:
            stats["needs_fundamentals"] += 1
            sym = str(sig.get("symbol", "")).strip().upper()
            if sym:
                to_fetch.append(sym)

    if not to_fetch:
        return stats

    provider = FundamentalsProvider(cache_dir=str(CACHE_DIR), cache_ttl_hours=24)
    fetched = provider.fetch_batch(sorted(set(to_fetch)), workers=min(12, max(1, len(to_fetch))), show_progress=False)

    for sig in signals:
        sym = str(sig.get("symbol", "")).strip().upper()
        fund = fetched.get(sym) or {}
        is_india = sym.endswith(".NS") or sym.endswith(".BO")

        if not _has_value(sig.get("fundSummary")):
            before = sig.get("fundSummary")
            sig["fundSummary"] = fundamentals_compact_summary(fund, is_india=is_india)
            if _has_value(sig.get("fundSummary")) and not _has_value(before):
                stats["fund_summary_filled"] += 1
        if not _has_value(sig.get("triggerEarningsGrowth")):
            before = sig.get("triggerEarningsGrowth")
            sig["triggerEarningsGrowth"] = _earnings_trigger_from_fundamentals(fund)
            if _has_value(sig.get("triggerEarningsGrowth")) and not _has_value(before):
                stats["earnings_filled"] += 1
        if not _has_value(sig.get("triggerDebtReduction")):
            before = sig.get("triggerDebtReduction")
            sig["triggerDebtReduction"] = _debt_trigger_from_fundamentals(fund)
            if _has_value(sig.get("triggerDebtReduction")) and not _has_value(before):
                stats["debt_filled"] += 1

    for sig in signals:
        if not _has_value(sig.get("fundSummary")):
            stats["still_missing_summary"] += 1
        if not _has_value(sig.get("triggerEarningsGrowth")):
            stats["still_missing_earnings"] += 1
        if not _has_value(sig.get("triggerDebtReduction")):
            stats["still_missing_debt"] += 1

    return stats

def load_signals() -> list[dict]:
    files = [
        ("vcp_hits_india_daily_full_LATEST.json",       "Daily"),
        ("vcp_hits_india_weekly_full_LATEST.json",      "Weekly"),
        ("portfolio_shortlist_india_daily_full_LATEST.json",  "Daily Portfolio"),
        ("vcp_hits_india_daily_vcp_LATEST.json",        "Daily VCP"),
        ("vcp_hits_india_daily_range_expansion_LATEST.json", "Daily RExp"),
    ]
    seen: dict[str, dict] = {}
    # Track all unique (setup_type, tf_label) pairs per symbol
    seen_setups: dict[str, list[tuple[str, str]]] = {}

    for fname, label in files:
        p = OUTPUT / fname
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
            if not isinstance(data, list):
                continue
            for row in data:
                sym = row.get("symbol", "")
                if not sym:
                    continue
                row["_tf_label"] = label
                setup = row.get("setup", "")
                if sym in seen:
                    seen[sym] = _pick_better_row(seen[sym], row)
                    # Accumulate additional setups (avoid strict duplicates)
                    existing = seen_setups.setdefault(sym, [])
                    if (setup, label) not in existing:
                        existing.append((setup, label))
                else:
                    seen[sym] = row
                    seen_setups[sym] = [(setup, label)]
        except Exception:
            pass

    # Attach the consolidated multi-setup list to each winning row
    for sym, row in seen.items():
        all_s = seen_setups.get(sym, [(row.get("setup", ""), row.get("_tf_label", ""))])
        # Deduplicate by setup type (keep first occurrence of each type)
        seen_types: set[str] = set()
        unique: list[tuple[str, str]] = []
        for st, lbl in all_s:
            if st and st not in seen_types:
                seen_types.add(st)
                unique.append((st, lbl))
        row["_all_setups"] = unique  # list of (setup_type, tf_label)

    return sorted(seen.values(), key=lambda x: -_f(x.get("score", 0)))

def build_position_plan(sig: dict) -> dict:
    entry = _f(sig.get("entry") or sig.get("close"))
    sl    = _f(sig.get("sl"))
    t1    = _f(sig.get("T1"))
    t2    = _f(sig.get("T2"))
    t3    = _f(sig.get("T3"))
    risk  = entry - sl if sl and sl < entry else entry * 0.03
    if risk <= 0: risk = entry * 0.03

    shares  = int(math.floor(ACCOUNT_SIZE * RISK_PCT / risk)) if risk > 0 else 0
    capital = shares * entry
    rr_t1   = (t1 - entry) / risk if risk > 0 and t1 else 0
    rr_t2   = (t2 - entry) / risk if risk > 0 and t2 else 0
    rr_t3   = (t3 - entry) / risk if risk > 0 and t3 else 0
    max_loss = shares * risk
    t1_profit = shares * (t1 - entry) if t1 else 0
    t2_profit = shares * (t2 - entry) if t2 else 0
    t3_profit = shares * (t3 - entry) if t3 else 0

    return {
        "entry": entry, "sl": sl, "t1": t1, "t2": t2, "t3": t3,
        "risk": round(risk, 2), "shares": shares,
        "capital": round(capital, 0), "max_loss": round(max_loss, 0),
        "rr_t1": round(rr_t1, 2), "rr_t2": round(rr_t2, 2), "rr_t3": round(rr_t3, 2),
        "t1_profit": round(t1_profit, 0), "t2_profit": round(t2_profit, 0), "t3_profit": round(t3_profit, 0),
    }

def sparkline_svg(closes: list[float], width=120, height=40) -> str:
    if not closes or len(closes) < 2:
        return f'<svg width="{width}" height="{height}"><text x="5" y="20" fill="#555" font-size="10">N/A</text></svg>'
    mn, mx = min(closes), max(closes)
    span = mx - mn if mx != mn else 1.0
    pad = 4
    w, h = width - 2*pad, height - 2*pad

    pts = []
    for i, v in enumerate(closes):
        x = pad + i / max(len(closes) - 1, 1) * w
        y = pad + (1 - (v - mn) / span) * h
        pts.append(f"{x:.1f},{y:.1f}")

    color = "#3fb950" if closes[-1] >= closes[0] else "#f85149"
    fill_color = "#3fb95022" if closes[-1] >= closes[0] else "#f8514922"

    # Close polygon for fill
    fill_pts = pts + [f"{pad+w:.1f},{pad+h:.1f}", f"{pad:.1f},{pad+h:.1f}"]

    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            f'<polygon points="{" ".join(fill_pts)}" fill="{fill_color}" stroke="none"/>'
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="1.5"/>'
            f'</svg>')

def _build_bf_html(sig: dict) -> str:
    """Render the Bull Flag detail panel embedded in a signal card."""
    pole_gain    = _f(sig.get("bfPoleGain%")   or sig.get("height%"))
    flag_decline = _f(sig.get("bfFlagDecline%") or sig.get("depth%"))
    flag_bars    = sig.get("bfFlagBars")   or sig.get("len") or "—"
    flag_vol     = _f(sig.get("bfFlagVolRatio") or sig.get("mrPullbackVolRatio"))
    tightness    = _f(sig.get("bfTightnessRatio") or 0)
    pole_vol     = _f(sig.get("bfPoleVolRatio")   or 0)
    flag_high    = _f(sig.get("bfFlagHigh")  or sig.get("pivot"))
    flag_low     = _f(sig.get("bfFlagLow")   or sig.get("sl"))
    pole_start   = sig.get("bfPoleStartDate", "")
    pole_top     = sig.get("bfPoleTopDate",   "")
    t1           = _f(sig.get("T1"))
    t2           = _f(sig.get("T2"))
    t3           = _f(sig.get("T3"))
    subtype      = str(sig.get("setupSubtype") or "")

    # Subtype badge
    if subtype == "FLAG_BREAKOUT":
        st_cls, st_lbl = "bf-st-breakout", "🚀 Breaking Out"
    else:
        st_cls, st_lbl = "bf-st-forming",  "⏳ Flag Forming"

    # Format helpers
    def pct(v): return f"{v:.1f}%" if v else "—"
    def px(v):  return f"₹{v:.2f}" if v else "—"
    def ratio(v): return f"{v:.2f}×" if v else "—"

    vol_color = "#4ade80" if flag_vol and flag_vol < 0.75 else "#e3b341" if flag_vol and flag_vol < 0.9 else "#f87171"

    dates_html = ""
    if pole_start or pole_top:
        dates_html = (
            f'<div style="font-size:.62em;color:#6e7681;margin-top:4px">'
            f'Pole: {escape(str(pole_start))} → {escape(str(pole_top))}</div>'
        )

    return f"""<div class="bf-panel">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <span style="font-size:.7em;color:#34d399;font-weight:700;letter-spacing:.3px">🏴 BULL FLAG METRICS</span>
    <span class="bf-subtype {st_cls}">{st_lbl}</span>
  </div>
  <div class="bf-row">
    <div class="bf-cell">
      <div class="bf-lbl">Pole Gain</div>
      <div class="bf-val bf-pole">{pct(pole_gain)}</div>
    </div>
    <div class="bf-cell">
      <div class="bf-lbl">Flag Decline</div>
      <div class="bf-val bf-flag">{pct(flag_decline)}</div>
    </div>
    <div class="bf-cell">
      <div class="bf-lbl">Flag Bars</div>
      <div class="bf-val" style="color:#94a3b8">{flag_bars}</div>
    </div>
    <div class="bf-cell">
      <div class="bf-lbl">Vol Dry-up</div>
      <div class="bf-val" style="color:{vol_color}">{ratio(flag_vol)}</div>
    </div>
    <div class="bf-cell">
      <div class="bf-lbl">Tightness</div>
      <div class="bf-val bf-vol">{ratio(tightness)}</div>
    </div>
    <div class="bf-cell">
      <div class="bf-lbl">Pole Vol</div>
      <div class="bf-val" style="color:#c084fc">{ratio(pole_vol)}</div>
    </div>
  </div>
  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:4px;font-size:.7em;color:#6e7681">
    <span>Flag High: <b style="color:#e2e8f0">{px(flag_high)}</b></span>
    <span>Flag Low: <b style="color:#e2e8f0">{px(flag_low)}</b></span>
  </div>
  <div class="bf-targets">
    <span style="color:#6e7681;font-size:.88em;align-self:center">Targets:</span>
    <span class="bf-t bf-t1">T1 {px(t1)}</span>
    <span class="bf-t bf-t2">T2 {px(t2)}</span>
    <span class="bf-t bf-t3">T3 {px(t3)}</span>
  </div>
  {dates_html}
</div>"""


def _build_rexp_html(sig: dict) -> str:
    """Render the Range Expansion detail panel embedded in a signal card."""
    rexp_val     = _f(sig.get("rexp") or 0)
    vol_pct      = _f(sig.get("vol%") or 0)
    range_pct    = _f(sig.get("range%") or sig.get("rangePct") or 0)
    height_pct   = _f(sig.get("height%") or 0)
    base_len     = sig.get("len") or sig.get("windowDays") or "—"
    subtype      = str(sig.get("setupSubtype") or "")
    pivot        = _f(sig.get("pivot") or 0)
    t1           = _f(sig.get("T1") or 0)
    t2           = _f(sig.get("T2") or 0)
    t3           = _f(sig.get("T3") or 0)
    dist_pct     = _f(sig.get("distFromPivot%") or sig.get("dist%") or 0)
    days_above   = sig.get("daysAbovePivot") or "—"

    def pct(v):   return f"{v:.1f}%" if v else "—"
    def px(v):    return f"₹{v:.2f}" if v else "—"
    def ratio(v): return f"{v:.2f}×" if v else "—"
    def spct(v, pos_good=True):
        if not v: return "—"
        cls = "rexp-pos" if (v >= 0) == pos_good else "rexp-neg"
        sign = "+" if v >= 0 else ""
        return f'<span class="{cls}">{sign}{v:.1f}%</span>'

    # Colour the RExp ratio: >2x = green, 1.5-2x = yellow, <1.5x = muted
    rexp_color = "#4ade80" if rexp_val >= 2.0 else "#e3b341" if rexp_val >= 1.5 else "#94a3b8"
    vol_color  = "#4ade80" if vol_pct >= 100 else "#e3b341" if vol_pct >= 50 else "#94a3b8"

    # Subtype badge
    st_map = {
        "RANGE_EXPANSION_BREAKOUT": ("rexp-st-bo",  "🚀 Breakout Bar"),
        "WATCHLIST":                ("rexp-st-wl",  "⏳ Pre-Breakout"),
    }
    st_cls, st_lbl = st_map.get(subtype, ("rexp-st-bo", f"📊 {subtype}" if subtype else "📊 Expansion"))

    return f"""<div class="rexp-panel">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <span style="font-size:.7em;color:#86efac;font-weight:700;letter-spacing:.3px">📊 RANGE EXPANSION METRICS</span>
    <span class="rexp-subtype {st_cls}">{st_lbl}</span>
  </div>
  <div class="rexp-row">
    <div class="rexp-cell">
      <div class="rexp-lbl">RExp Ratio</div>
      <div class="rexp-val" style="color:{rexp_color}">{ratio(rexp_val)}</div>
    </div>
    <div class="rexp-cell">
      <div class="rexp-lbl">Vol Spike</div>
      <div class="rexp-val" style="color:{vol_color}">{spct(vol_pct)}</div>
    </div>
    <div class="rexp-cell">
      <div class="rexp-lbl">Bar Range</div>
      <div class="rexp-val" style="color:#94a3b8">{pct(range_pct)}</div>
    </div>
    <div class="rexp-cell">
      <div class="rexp-lbl">Base Height</div>
      <div class="rexp-val" style="color:#7dd3fc">{pct(height_pct)}</div>
    </div>
    <div class="rexp-cell">
      <div class="rexp-lbl">Base Len</div>
      <div class="rexp-val" style="color:#94a3b8">{base_len}d</div>
    </div>
    <div class="rexp-cell">
      <div class="rexp-lbl">Dist Pivot</div>
      <div class="rexp-val" style="color:#c084fc">{pct(dist_pct)}</div>
    </div>
  </div>
  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:4px;font-size:.7em;color:#6e7681">
    <span>Pivot: <b style="color:#e2e8f0">{px(pivot)}</b></span>
    <span>Days above pivot: <b style="color:#86efac">{days_above}</b></span>
  </div>
  <div class="rexp-targets">
    <span style="color:#6e7681;font-size:.88em;align-self:center">Targets:</span>
    <span class="rexp-t rexp-t1">T1 {px(t1)}</span>
    <span class="rexp-t rexp-t2">T2 {px(t2)}</span>
    <span class="rexp-t rexp-t3">T3 {px(t3)}</span>
  </div>
</div>"""


def _build_bp_html(sig: dict) -> str:
    """Render the Breakout Pullback detail panel embedded in a signal card."""
    bo_date       = str(sig.get("abfpBreakoutDate") or "")
    bo_level      = _f(sig.get("pivot") or 0)
    peak_high     = _f(sig.get("abfpPeakHigh") or sig.get("max_after_breakout") or 0)
    pullback_dep  = _f(sig.get("abfpPullbackDepth%") or sig.get("height%") or 0)
    run_from_bo   = _f(sig.get("abfpRunFromBO%")     or sig.get("depth%") or 0)
    bars_since    = sig.get("abfpBarsSincePeak")      or sig.get("len") or "—"
    vol_ratio     = _f(sig.get("abfpPullbackVolRatio") or sig.get("pullback_vol_ratio") or 0)
    days_above    = sig.get("daysAbovePivot") or "—"
    dist_from_bo  = _f(sig.get("distFromPivot%") or 0)
    t1            = _f(sig.get("T1") or 0)
    t2            = _f(sig.get("T2") or 0)
    t3            = _f(sig.get("T3") or 0)
    subtype       = str(sig.get("setupSubtype") or "FIRST_PULLBACK")

    def pct(v):   return f"{v:.1f}%" if v else "—"
    def px(v):    return f"₹{v:.2f}" if v else "—"
    def ratio(v): return f"{v:.2f}×" if v else "—"

    # Volume dry-up quality
    if vol_ratio > 0:
        if vol_ratio < 0.70:
            vol_color = "#4ade80"
            vol_label = "Excellent Dry-up"
        elif vol_ratio < 0.85:
            vol_color = "#86efac"
            vol_label = "Good Dry-up"
        elif vol_ratio < 1.00:
            vol_color = "#e3b341"
            vol_label = "Mild Dry-up"
        else:
            vol_color = "#f87171"
            vol_label = "No Dry-up"
    else:
        vol_color, vol_label = "#94a3b8", "—"

    # Pullback depth quality
    if pullback_dep < 5.0:
        dep_color = "#4ade80"   # very tight
    elif pullback_dep < 8.0:
        dep_color = "#e3b341"   # acceptable
    else:
        dep_color = "#f87171"   # too deep

    return f"""<div class="bp-panel">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <span style="font-size:.7em;color:#d8b4fe;font-weight:700;letter-spacing:.3px">🔁 BREAKOUT PULLBACK METRICS</span>
    <span class="bp-subtype">⏪ {subtype.replace('_',' ').title()}</span>
  </div>
  <div class="bp-row">
    <div class="bp-cell">
      <div class="bp-lbl">BO Support</div>
      <div class="bp-val" style="color:#79c0ff">{px(bo_level)}</div>
    </div>
    <div class="bp-cell">
      <div class="bp-lbl">Post-BO Peak</div>
      <div class="bp-val" style="color:#4ade80">{px(peak_high)}</div>
    </div>
    <div class="bp-cell">
      <div class="bp-lbl">Run from BO</div>
      <div class="bp-val" style="color:#86efac">+{pct(run_from_bo)}</div>
    </div>
    <div class="bp-cell">
      <div class="bp-lbl">Pullback</div>
      <div class="bp-val" style="color:{dep_color}">-{pct(pullback_dep)}</div>
    </div>
    <div class="bp-cell">
      <div class="bp-lbl">Bars Since Peak</div>
      <div class="bp-val" style="color:#94a3b8">{bars_since}d</div>
    </div>
    <div class="bp-cell">
      <div class="bp-lbl">Vol Dry-up</div>
      <div class="bp-val" style="color:{vol_color}" title="{vol_label}">{ratio(vol_ratio)}</div>
    </div>
  </div>
  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:4px;font-size:.7em;color:#6e7681">
    <span>BO Date: <b style="color:#e2e8f0">{bo_date or '—'}</b></span>
    <span>Days above BO: <b style="color:#d8b4fe">{days_above}</b></span>
    <span>Dist from BO: <b style="color:#7dd3fc">{pct(dist_from_bo)}</b></span>
  </div>
  <div class="bp-targets">
    <span style="color:#6e7681;font-size:.88em;align-self:center">Targets:</span>
    <span class="bp-t bp-t1">T1 {px(t1)}</span>
    <span class="bp-t bp-t2">T2 {px(t2)}</span>
    <span class="bp-t bp-t3">T3 {px(t3)}</span>
  </div>
</div>"""


def _build_mf_html(mf_ctx: dict, sym: str) -> str:
    """Build the MF/Institutional holdings panel HTML for one signal card."""
    if not mf_ctx:
        return ""
    signal = mf_ctx.get("signal", "UNKNOWN")

    # Determine if we have ANY data worth showing
    dii_pct_val  = (mf_ctx.get("dii") or {}).get("pct")
    fii_pct_val  = (mf_ctx.get("fii") or {}).get("pct")
    pro_pct_val  = (mf_ctx.get("promoters") or {}).get("pct")
    inst_pct_val = mf_ctx.get("inst_held_pct")
    top_mf_val   = mf_ctx.get("top_mf") or []
    has_any_data = any(v is not None for v in (dii_pct_val, fii_pct_val, pro_pct_val, inst_pct_val)) or bool(top_mf_val)

    if not has_any_data:
        err = mf_ctx.get("screener_error", "")
        if err and "not_listed" in str(err):
            return ""   # private/unlisted company — truly no data
        # Show a minimal "data loading" panel for Indian stocks instead of hiding
        if sym.endswith(".NS") or sym.endswith(".BO"):
            return (f'<div class="mf-panel">'
                    f'<div class="mf-hdr" onclick="this.nextElementSibling.classList.toggle(\'open\')">'
                    f'<span class="mf-hdr-lbl">🏦 Institutional</span>'
                    f'<span class="mf-sig mf-sig-neutral">⟳ Fetching</span></div>'
                    f'<div class="mf-body">'
                    f'<div class="mf-swing" style="color:#64748b;font-size:.68em">Shareholding data will appear on next run after Screener.in cache warms up.</div>'
                    f'</div></div>')
        return ""

    sig_labels = {
        "STRONG_BUYING":    ("mf-sig-strong",   "🔥 Strong Buying"),
        "DII_ACCUMULATING": ("mf-sig-dii",      "↑ DIIs Buying"),
        "FII_ACCUMULATING": ("mf-sig-fii",      "↑ FIIs Buying"),
        "DISTRIBUTING":     ("mf-sig-dist",     "⚠ Distributing"),
        "FII_SELLING":      ("mf-sig-dist",     "⚠ FIIs Selling"),
        "NEUTRAL":          ("mf-sig-neutral",  "→ Stable"),
        "INST_HIGH":        ("mf-sig-fii",      "ℹ Inst. Held"),
        "PROMOTER_HELD":    ("mf-sig-neutral",  "🏢 Promoter Held"),
        "UNKNOWN":          ("mf-sig-neutral",  "⟳ Partial Data"),
    }
    sig_cls, sig_label = sig_labels.get(signal, ("mf-sig-neutral", signal))

    dii = mf_ctx.get("dii") or {}
    fii = mf_ctx.get("fii") or {}
    pro = mf_ctx.get("promoters") or {}
    pub = mf_ctx.get("public") or {}
    period      = escape(mf_ctx.get("latest_period") or "")
    conviction  = mf_ctx.get("conviction", "NEUTRAL")
    conv_cls    = {"HIGH": "mf-conv-high", "MEDIUM": "mf-conv-medium",
                   "LOW": "mf-conv-low"}.get(conviction, "mf-conv-neu")
    inst_pct    = mf_ctx.get("inst_held_pct")
    mf_sub_pct  = mf_ctx.get("mutual_funds_pct")
    screener_err = mf_ctx.get("screener_error")

    def fmt(v, suffix="%"):
        return f"{v:.1f}{suffix}" if v is not None else "—"

    def fmt_chg(v):
        if v is None: return ""
        sign = "+" if v >= 0 else ""
        cls  = "mf-up" if v > 0.1 else ("mf-dn" if v < -0.1 else "mf-st")
        return f' <span class="{cls}" style="font-size:.82em">({sign}{v:.1f}%)</span>'

    def trend_arrow(t):
        return {"up": "↑", "down": "↓"}.get(t or "", "→")

    def trend_cls(t):
        return {"up": "mf-up", "down": "mf-dn"}.get(t or "", "mf-st")

    dii_pct  = fmt(dii.get("pct"))
    fii_pct  = fmt(fii.get("pct"))
    pro_pct  = fmt(pro.get("pct"))
    pub_pct  = fmt(pub.get("pct"))

    dii_chg_html = fmt_chg(dii.get("change_2q"))
    fii_chg_html = fmt_chg(fii.get("change_2q"))

    swing_text = escape(mf_ctx.get("text") or mf_ctx.get("summary") or "")

    # Quarterly DII trend mini-bar (last 6 quarters)
    history = mf_ctx.get("dii_trend_history", [])
    trend_bar_html = ""
    if history:
        dii_vals = [h.get("dii") for h in history if h.get("dii") is not None]
        if dii_vals:
            mn, mx = min(dii_vals), max(dii_vals)
            span   = mx - mn if mx != mn else 1.0
            segs   = []
            for v in dii_vals[-6:]:
                h_px = max(4, int((v - mn) / span * 18) + 2)
                clr  = "#2dd4bf"
                segs.append(f'<span class="mf-bar-seg" style="height:{h_px}px;background:{clr}" title="DII {v:.1f}%"></span>')
            trend_bar_html = (
                f'<div style="margin-bottom:5px">'
                f'<div style="font-size:.62em;color:#64748b;margin-bottom:2px">DII trend ({len(dii_vals)}Q)</div>'
                f'<div class="mf-dii-trend-bar">{"".join(segs)}</div>'
                f'</div>'
            )

    # MF sub-% and inst_held note
    extra_html = ""
    if mf_sub_pct is not None:
        extra_html += f'<div style="margin-top:4px;font-size:.65em;color:#7dd3fc">Mutual Funds (of DII): <b>{mf_sub_pct:.1f}%</b></div>'
    if inst_pct is not None:
        extra_html += (
            f'<div style="margin-top:2px;font-size:.62em;color:#64748b">'
            f'Institutional (float): {inst_pct:.1f}%</div>'
        )
    if screener_err and screener_err not in ("not_listed_on_screener",):
        src_label = "yfinance only" if signal in ("INST_HIGH", "NEUTRAL", "UNKNOWN") else "Screener.in"
        extra_html += (
            f'<div style="margin-top:2px;font-size:.58em;color:#475569">'
            f'⚠ Screener error ({screener_err}) — Source: {src_label}</div>'
        )

    top_mf = (mf_ctx.get("top_mf") or [])[:5]
    top_mf_html = ""
    if top_mf:
        items = "".join(
            f'<div class="mf-scheme"><span class="mf-scheme-name">{escape(m["name"])}</span>'
            f'<span class="mf-scheme-pct">{fmt(m.get("pct"))}</span></div>'
            for m in top_mf
        )
        lbl = "Top Shareholders (yfinance)" if mf_ctx.get("_top_holders_source") == "yfinance" else "Top Shareholders"
        top_mf_html = f'<div class="mf-top"><div class="mf-top-lbl">{lbl}</div>{items}</div>'

    src_note = "yfinance" if screener_err else "Screener.in"
    return f"""<div class="mf-panel">
  <div class="mf-hdr" onclick="this.nextElementSibling.classList.toggle('open')">
    <span class="mf-hdr-lbl">🏦 Institutional{' · ' + period if period else ''}</span>
    <span class="mf-sig {sig_cls}">{sig_label}</span>
  </div>
  <div class="mf-body">
    <div class="mf-swing">{swing_text}</div>
    {trend_bar_html}
    <div class="mf-own-grid">
      <div><span class="mf-own-lbl">DIIs</span><span class="{trend_cls(dii.get('trend'))} mf-own-val">{trend_arrow(dii.get('trend'))} {dii_pct}{dii_chg_html}</span></div>
      <div><span class="mf-own-lbl">FIIs</span><span class="{trend_cls(fii.get('trend'))} mf-own-val">{trend_arrow(fii.get('trend'))} {fii_pct}{fii_chg_html}</span></div>
      <div><span class="mf-own-lbl">Promoters</span><span class="{trend_cls(pro.get('trend'))} mf-own-val">{trend_arrow(pro.get('trend'))} {pro_pct}</span></div>
      <div><span class="mf-own-lbl">Public</span><span class="mf-st mf-own-val">→ {pub_pct}</span></div>
    </div>
    {extra_html}
    {top_mf_html}
    <div style="margin-top:4px;font-size:.6em;color:#475569">Conviction: <span class="{conv_cls}">{conviction}</span> · Source: {src_note}</div>
  </div>
</div>"""


def build_html(signals: list[dict], run_history: dict | None = None) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = len(signals)

    # Sector counts for summary
    sector_counts: dict[str, int] = {}
    setup_counts:  dict[str, int] = {}
    industry_counts: dict[str, int] = {}
    sector_a_counts: dict[str, int] = {}   # A/A+ only
    industry_a_counts: dict[str, int] = {} # A/A+ only
    for s in signals:
        sec = get_sector(s.get("symbol",""))
        ind = get_industry(s.get("symbol",""))
        setup = s.get("setup","Other")
        rating = s.get("rating","")
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
        setup_counts[setup] = setup_counts.get(setup, 0) + 1
        industry_counts[ind] = industry_counts.get(ind, 0) + 1
        if rating in ("A+", "A"):
            sector_a_counts[sec] = sector_a_counts.get(sec, 0) + 1
            industry_a_counts[ind] = industry_a_counts.get(ind, 0) + 1

    top_sectors = sorted(sector_counts.items(), key=lambda x: -x[1])[:8]
    a_plus = sum(1 for s in signals if s.get("rating","") == "A+")
    a_rate  = sum(1 for s in signals if s.get("rating","") in ("A+","A"))

    # ── Compute industry-level MA breadth from ALL cached stocks ──────────────
    print("  Computing industry MA breadth across all tracked stocks…", flush=True)
    industry_breadth = compute_industry_breadth_all()
    tracked_total = sum(v["total"] for v in industry_breadth.values())

    # ── Appearance stats across stored runs
    _rh = run_history or {}
    _rh_total = len(_rh.get("runs", []))
    recurring_count = sum(
        1 for s in signals
        if count_appearances(s.get("symbol",""), _rh)[0] >= max(1, _rh_total // 2)
    ) if _rh_total > 0 else 0
    run_history_note = (
        f"Run history: {_rh_total}/{RUN_HISTORY_MAX} runs stored"
        if _rh_total > 0 else "First run — history starts now"
    )

    # ── Build signal rows
    rows_html = []
    for i, sig in enumerate(signals):
        sym    = sig.get("symbol","")
        setup  = sig.get("setup","")
        rating = sig.get("rating","")
        sector = get_sector(sym)
        industry = get_industry(sym)
        tf_lbl = sig.get("_tf_label","Daily")
        plan   = build_position_plan(sig)
        sparkline_data = load_sparkline(sym)
        svg = sparkline_svg(sparkline_data)
        is_weekly = tf_lbl.lower().startswith("weekly")
        price_rows = load_price_rows(sym, weekly=is_weekly)

        # ── Appearance count over last 20 runs
        app_count, app_total = count_appearances(sym, run_history or {})

        # ── Price performance (always use daily rows for consistent periods)
        daily_rows = load_price_rows(sym, weekly=False)
        perf = compute_price_performance(daily_rows)

        regime     = sig.get("regimeState","")
        regime_str = ("Favorable" if "FAV" in regime and "UNFAV" not in regime
                      else "Unfavorable" if "UNFAV" in regime else "Neutral")
        regime_cls = ("reg-fav" if regime_str == "Favorable"
                      else "reg-unfav" if regime_str == "Unfavorable" else "reg-neu")

        rs3m_raw = _f(sig.get("rs3m"))
        rs6m_raw = _f(sig.get("rs6m"))
        fallback_rs3m, fallback_rs6m = compute_rs_metrics(price_rows, is_weekly)
        rs3m = pick_metric(rs3m_raw, fallback_rs3m)
        rs6m = pick_metric(rs6m_raw, fallback_rs6m)
        rs3m_cls = "rna" if rs3m is None else ("rpl" if rs3m > 0 else "rmi")
        rs6m_cls = "rna" if rs6m is None else ("rpl" if rs6m > 0 else "rmi")

        setup_cls, setup_label, setup_tip = SETUP_META.get(
            setup, ("tag-bo", setup.replace("_"," "), ""))

        # ── All setups this symbol appeared in (multi-setup support)
        all_setups = sig.get("_all_setups") or [(setup, tf_lbl)]

        score = _f(sig.get("score",0))
        pivot = plan["entry"]  # entry IS the pivot area for current signals
        actual_pivot = _f(sig.get("pivot") or plan["entry"])

        width_pct  = min(score, 130) / 130 * 100
        score_color = "#3fb950" if score >= 100 else "#e3b341" if score >= 70 else "#f85149"

        vol_raw = _f(sig.get("vol%"))
        rexp_raw = _f(sig.get("rexp"))
        fallback_vol, fallback_rexp = current_expansion_metrics(price_rows)
        vol_pct = pick_metric(vol_raw, fallback_vol)
        rexp = pick_metric(rexp_raw, fallback_rexp)
        vol_pct_text = fmt_pct(vol_pct)
        rexp_text = fmt_x(rexp)
        rs3m_text = fmt_pct(rs3m, signed=True)
        rs6m_text = fmt_pct(rs6m, signed=True)
        window  = sig.get("window","")
        dist_pivot = _f(sig.get("distFromPivot%") or sig.get("pivotProximityScore"))

        eps_trigger = str(
            sig.get("triggerEarningsGrowth")
            or sig.get("earningsTrigger")
            or sig.get("earnings")
            or "UNKNOWN"
        )
        debt_trigger = str(
            sig.get("triggerDebtReduction")
            or sig.get("debtTrigger")
            or sig.get("debt")
            or "UNKNOWN"
        )
        macro_trigger = str(
            sig.get("triggerMacroTailwind")
            or sig.get("macroTrigger")
            or sig.get("triggerMacro")
            or "NEUTRAL_OR_HEADWIND"
        )
        market_trigger = str(
            sig.get("triggerMarketTailwind")
            or sig.get("marketTrigger")
            or sig.get("triggerMarket")
            or "MIXED"
        )
        fund_summary = str(
            sig.get("fundSummary")
            or sig.get("fundamentalSummary")
            or sig.get("fundamentals")
            or "FUNDAMENTALS_UNAVAILABLE"
        )

        eps_yoy = extract_pct(eps_trigger, ["EPS_YOY", "EPS YOY"])
        eps_qoq = extract_pct(eps_trigger, ["EPS_QOQ", "EPS QOQ"])
        debt_yoy = extract_pct(debt_trigger, ["DEBT_YOY", "DEBT YOY"])
        debt_qoq = extract_pct(debt_trigger, ["DEBT_QOQ", "DEBT QOQ"])
        if debt_yoy is None and debt_qoq is None:
            debt_proxy = extract_debt_change(debt_trigger)
            debt_yoy = debt_proxy

        eps_yoy_text = fmt_metric(eps_yoy)
        eps_qoq_text = fmt_metric(eps_qoq)
        debt_yoy_text = fmt_metric(debt_yoy)
        debt_qoq_text = fmt_metric(debt_qoq)

        eps_cls = "metric-na" if eps_yoy is None and eps_qoq is None else ("metric-pos" if ((eps_yoy or 0) >= 0 or (eps_qoq or 0) >= 0) else "metric-neg")
        debt_cls = "metric-na" if debt_yoy is None and debt_qoq is None else ("metric-neg" if ((debt_yoy or 0) > 0 or (debt_qoq or 0) > 0) else "metric-pos")

        eps_trigger_html = escape(eps_trigger)
        debt_trigger_html = escape(debt_trigger)
        macro_trigger_html = escape(macro_trigger)
        market_trigger_html = escape(market_trigger)
        fund_summary_html = escape(fund_summary)

        # MF / Institutional holdings for this signal (pre-fetched batch)
        mf_ctx = sig.get("_mf_context", {})
        mf_html = _build_mf_html(mf_ctx, sym)

        # Build multi-setup tags HTML
        def _setup_tag_html(st: str, tip: str = "") -> str:
            sc, sl, stip = SETUP_META.get(st, ("tag-bo", st.replace("_", " "), ""))
            tip_attr = f' title="{tip or stip}"' if (tip or stip) else ""
            return f'<span class="{sc} sig-tag"{tip_attr}>{sl}</span>'

        setup_tags_html = "".join(_setup_tag_html(st) for st, _lbl in all_setups)
        # Multi-setup badge if stock shows in more than one setup type
        multi_badge_html = ""
        if len(all_setups) > 1:
            labels_str = " + ".join(SETUP_META.get(st, (None, st.replace("_", " "), None))[1] for st, _ in all_setups)
            multi_badge_html = f'<span class="multi-setup-badge" title="Appears in multiple setups: {labels_str}">🔀 Multi</span>'
        # Pipe-separated list of ALL setup types — enables multi-setup filter in JS
        all_setup_types_pipe = "|".join(st for st, _ in all_setups)
        all_setup_types_set  = {st for st, _ in all_setups}

        rows_html.append(f"""
<div class="sig-card" data-symbol="{sym}" data-setup="{all_setup_types_pipe}" data-rating="{rating}" data-sector="{sector}" data-industry="{industry}" data-appear="{app_count}" data-appear-total="{app_total}">
  <div class="sig-header">
    <div class="sig-left">
      <div class="sig-sym">{sym.replace('.NS','')}</div>
      <div class="sig-meta">
        <span class="badge-sec">{sector}</span>
        <span class="badge-tf">{tf_lbl}</span>
        {setup_tags_html}
        {multi_badge_html}
      </div>
    </div>
    <div class="sig-right">
      <div class="sig-sparkline">{svg}</div>
      <div style="display:flex;gap:5px;align-items:center;justify-content:flex-end;flex-wrap:wrap;">
        <div class="sig-rating {'rat-aplus' if rating=='A+' else 'rat-a' if rating=='A' else 'rat-b'}">{rating}</div>
        {f'<div class="appear-badge {"appear-hot" if app_count >= 15 else "appear-warm" if app_count >= 8 else "appear-cool"}" title="Appeared {app_count} times in last {app_total} runs">&#128257; {app_count}/{app_total}</div>' if app_total > 0 else ''}
      </div>
    </div>
  </div>

  <div class="score-bar-wrap" title="Score: {score:.1f}/130">
    <div class="score-bar-fill" style="width:{width_pct:.0f}%;background:{score_color}"></div>
    <span class="score-label">Score {score:.1f}</span>
  </div>

  <div class="plan-grid">
    <div class="plan-section">
      <div class="plan-title">Entry Zone</div>
      <div class="plan-value entry-val">&#8377;{plan['entry']:.2f}</div>
      <div class="plan-sub">Pivot: {actual_pivot:.2f} &nbsp;|&nbsp; Window: {window}</div>
    </div>
    <div class="plan-section">
      <div class="plan-title">Stop Loss</div>
      <div class="plan-value sl-val">&#8377;{plan['sl']:.2f}</div>
      <div class="plan-sub">Risk/share: &#8377;{plan['risk']:.2f} ({plan['risk']/plan['entry']*100:.1f}%)</div>
    </div>
    <div class="plan-section highlight">
      <div class="plan-title">Position Size</div>
      <div class="plan-value pos-val">{plan['shares']:,} shares</div>
      <div class="plan-sub">Capital: &#8377;{plan['capital']:,.0f} &nbsp;|&nbsp; Max Loss: &#8377;{plan['max_loss']:,.0f}</div>
    </div>
  </div>

  <div class="sig-footer">
    <div class="sig-stat">
      <span class="sstat-label">Regime</span>
      <span class="{regime_cls}">{regime_str}</span>
    </div>
    <div class="sig-stat">
      <span class="sstat-label">RS 3M</span>
      <span class="{rs3m_cls}">{rs3m_text}</span>
    </div>
    <div class="sig-stat">
      <span class="sstat-label">RS 6M</span>
      <span class="{rs6m_cls}">{rs6m_text}</span>
    </div>
    <div class="sig-stat">
      <span class="sstat-label">Vol %</span>
      <span style="color:#79c0ff">{vol_pct_text}</span>
    </div>
    <div class="sig-stat">
      <span class="sstat-label">RExp</span>
      <span style="color:#e3b341">{rexp_text}</span>
    </div>
  </div>

  <!-- Performance row -->
  <div class="perf-row">
    <div class="perf-cell">
      <span class="perf-label">1W</span>
      {fmt_perf(perf['ret_1w'])}
    </div>
    <div class="perf-cell">
      <span class="perf-label">1M</span>
      {fmt_perf(perf['ret_1m'])}
    </div>
    <div class="perf-cell">
      <span class="perf-label">3M</span>
      {fmt_perf(perf['ret_3m'])}
    </div>
    <div class="perf-cell">
      <span class="perf-label">6M</span>
      {fmt_perf(perf['ret_6m'])}
    </div>
    {f'<div class="perf-cell appear-cell"><span class="perf-label">Seen (20d)</span><span class="{"appear-hot" if app_count >= 15 else "appear-warm" if app_count >= 8 else "appear-cool"}">{app_count}/{app_total} runs</span></div>' if app_total > 0 else ''}
  </div>

  <div class="insight-chip" title="Hover card for fundamentals and macro trigger details">Fundamentals + Macro</div>
  <div class="sig-insight">
    <div class="insight-grid">
      <div class="insight-item">
        <div class="insight-label">EPS Growth</div>
        <div class="insight-value {eps_cls}">YoY {eps_yoy_text} &nbsp;|&nbsp; QoQ {eps_qoq_text}</div>
      </div>
      <div class="insight-item">
        <div class="insight-label">Debt Change</div>
        <div class="insight-value {debt_cls}">YoY {debt_yoy_text} &nbsp;|&nbsp; QoQ {debt_qoq_text}</div>
      </div>
      <div class="insight-item">
        <div class="insight-label">Macro Trigger</div>
        <div class="insight-pill {classify_trigger(macro_trigger)}">{macro_trigger_html}</div>
      </div>
      <div class="insight-item">
        <div class="insight-label">Market Trigger</div>
        <div class="insight-pill {classify_trigger(market_trigger)}">{market_trigger_html}</div>
      </div>
    </div>
    <div class="insight-summary" title="Online fundamentals summary">{fund_summary_html}</div>
    <div class="insight-raw">
      <div><b>EPS:</b> {eps_trigger_html}</div>
      <div><b>Debt:</b> {debt_trigger_html}</div>
    </div>
  </div>
  {mf_html}
  {_build_bf_html(sig) if 'BULL_FLAG' in all_setup_types_set else ''}
  {_build_rexp_html(sig) if 'RANGE_EXPANSION' in all_setup_types_set else ''}
  {_build_bp_html(sig) if 'BREAKOUT_PULLBACK' in all_setup_types_set else ''}
</div>""")

    sector_pills = "".join(
        f'<span class="sector-pill" onclick="filterSector(\'{s}\')">{s} <b>{c}</b></span>'
        for s, c in top_sectors
    )

    # ── Build sector rally heatmap ─────────────────────────────────────────────
    sorted_sectors = sorted(sector_counts.items(), key=lambda x: -x[1])
    max_sec = max((v for _, v in sorted_sectors), default=1)

    def _rally_intensity(count: int, max_count: int) -> str:
        r = count / max_count if max_count > 0 else 0
        if r >= 0.6:   return "rally-hot"
        if r >= 0.35:  return "rally-warm"
        if r >= 0.15:  return "rally-cool"
        return "rally-low"

    sector_heatmap_rows = ""
    for sec, cnt in sorted_sectors:
        a_cnt = sector_a_counts.get(sec, 0)
        pct = cnt / total * 100 if total else 0
        bar_w = cnt / max_sec * 100
        cls = _rally_intensity(cnt, max_sec)
        sector_heatmap_rows += (
            f'<div class="rally-row {cls}" onclick="filterSector(\'{sec}\')" title="Click to filter">'
            f'<div class="rally-name">{sec}</div>'
            f'<div class="rally-bar-wrap"><div class="rally-bar-fill" style="width:{bar_w:.0f}%"></div></div>'
            f'<div class="rally-cnt">{cnt} signals</div>'
            f'<div class="rally-a">A/A+: <b>{a_cnt}</b></div>'
            f'<div class="rally-pct">{pct:.0f}%</div>'
            f'</div>'
        )

    # ── Build industry rally heatmap (top 35 industries) ──────────────────────
    sorted_industries = sorted(industry_counts.items(), key=lambda x: -x[1])[:35]
    max_ind = max((v for _, v in sorted_industries), default=1)

    industry_heatmap_rows = ""
    for ind, cnt in sorted_industries:
        a_cnt = industry_a_counts.get(ind, 0)
        bar_w = cnt / max_ind * 100
        cls = _rally_intensity(cnt, max_ind)
        bd = industry_breadth.get(ind, {})
        pct_20  = bd.get("pct_20ma")
        pct_50  = bd.get("pct_50ma")
        pct_200 = bd.get("pct_200ma")
        stage   = bd.get("stage", "")
        stage_color = bd.get("stage_color", "#475569")
        stage_emoji = bd.get("stage_emoji", "")
        bd_total    = bd.get("total", 0)

        # Trend-stage aware bar overlay
        is_emerging = cnt > 0 and stage == "EMERGING"
        is_building = cnt > 0 and stage == "BUILDING"
        row_extra   = "rally-emerging" if is_emerging else ("rally-building" if is_building else "")

        pct_20_str  = f"{pct_20}%"  if pct_20  is not None else "—"
        pct_50_str  = f"{pct_50}%"  if pct_50  is not None else "—"
        pct_200_str = f"{pct_200}%" if pct_200 is not None else "—"

        breadth_tip = (
            f"{ind} | Signals: {cnt} | A/A+: {a_cnt} | "
            f"Stocks tracked: {bd_total} | "
            f">20MA: {pct_20_str} | >50MA: {pct_50_str} | >200MA: {pct_200_str} | "
            f"Stage: {stage}"
        )

        industry_heatmap_rows += (
            f'<div class="rally-row rally-row-ind {cls} {row_extra}" '
            f'onclick="filterIndustry(\'{ind.replace(chr(39), "")}\')"\n'
            f'title="{breadth_tip}">'
            f'<div class="rally-name">{ind}</div>'
            f'<div class="rally-bar-wrap"><div class="rally-bar-fill" style="width:{bar_w:.0f}%"></div></div>'
            f'<div class="rally-cnt">{cnt} <span style="color:#475569;font-size:.9em">sig</span></div>'
            f'<div class="rally-a">A+:<b>{a_cnt}</b></div>'
            f'<div class="rally-ma20" style="color:{stage_color}" title=">20MA breadth: {pct_20_str}">{stage_emoji}{pct_20_str}</div>'
            f'<div class="rally-ma50" title=">50MA breadth: {pct_50_str}">{pct_50_str}</div>'
            f'</div>'
        )

    # ── Build "Emerging Trend Radar" panel ─────────────────────────────────────
    # Industries where: has active signals + breadth in 25-65% zone (EMERGING)
    # or 65-80% zone (BUILDING) — these are the best early trend signals
    emerging_items = []
    building_items = []
    all_breadth_sorted = sorted(
        industry_breadth.items(),
        key=lambda kv: (-(industry_counts.get(kv[0], 0)), -(kv[1].get("pct_20ma") or 0))
    )
    for ind, bd in all_breadth_sorted:
        sig_cnt = industry_counts.get(ind, 0)
        if bd.get("stage") == "EMERGING" and sig_cnt > 0:
            emerging_items.append((ind, sig_cnt, bd))
        elif bd.get("stage") == "BUILDING" and sig_cnt > 0:
            building_items.append((ind, sig_cnt, bd))

    def _trend_chip(ind: str, sig_cnt: int, bd: dict, badge_cls: str, badge_label: str) -> str:
        pct20 = bd.get("pct_20ma", 0)
        pct50 = bd.get("pct_50ma", 0)
        a_c   = industry_a_counts.get(ind, 0)
        safe  = ind.replace("'", "")
        return (
            f'<div class="trend-chip {badge_cls}" onclick="filterIndustry(\'{safe}\')" '
            f'title="{ind} — {sig_cnt} signals | >20MA:{pct20}% | >50MA:{pct50}%">'
            f'<span class="trend-chip-badge">{badge_label}</span>'
            f'<span class="trend-chip-name">{ind}</span>'
            f'<span class="trend-chip-meta">{sig_cnt} sig · {pct20}% &gt;20MA</span>'
            f'<span class="trend-chip-aplus">{a_c} A+</span>'
            f'</div>'
        )

    emerging_html = "".join(
        _trend_chip(ind, sc, bd, "chip-emerging", "⚡ EMERGING")
        for ind, sc, bd in emerging_items[:12]
    )
    building_html = "".join(
        _trend_chip(ind, sc, bd, "chip-building", "🟡 BUILDING")
        for ind, sc, bd in building_items[:8]
    )

    breadth_legend_counts = {
        "EMERGING": sum(1 for _, bd in industry_breadth.items() if bd["stage"] == "EMERGING"),
        "BUILDING": sum(1 for _, bd in industry_breadth.items() if bd["stage"] == "BUILDING"),
        "EXTENDED": sum(1 for _, bd in industry_breadth.items() if bd["stage"] == "EXTENDED"),
        "WEAK":     sum(1 for _, bd in industry_breadth.items() if bd["stage"] == "WEAK"),
    }

    emerging_panel = f"""
<div class="emerging-panel">
  <div class="emerging-header">
    <div>
      <div class="emerging-title">🌱 Sector Trend Radar — Early Opportunities</div>
      <div class="emerging-sub">
        Industries with active breakouts + stocks in 25–65% above 20MA zone (early trend, not yet extended)
        &nbsp;·&nbsp; Tracking <b>{tracked_total}</b> stocks across <b>{len(industry_breadth)}</b> industries
      </div>
    </div>
    <div class="emerging-legend">
      <span>🟢 EMERGING: <b>{breadth_legend_counts["EMERGING"]}</b></span>
      <span>🟡 BUILDING: <b>{breadth_legend_counts["BUILDING"]}</b></span>
      <span>🔴 EXTENDED: <b>{breadth_legend_counts["EXTENDED"]}</b></span>
      <span>⚫ WEAK: <b>{breadth_legend_counts["WEAK"]}</b></span>
    </div>
  </div>
  {"" if emerging_html else '<div class="emerging-empty">No emerging trends with active signals right now — check BUILDING trends below</div>'}
  <div class="trend-chip-row">{emerging_html}</div>
  {"" if not building_html else '<div class="trend-chip-row trend-chip-row-b">' + building_html + '</div>'}
</div>"""

    # ── Build industry filter options ──────────────────────────────────────────
    industry_options = "".join(
        f'<option value="{ind}">{ind} ({cnt})</option>'
        for ind, cnt in sorted_industries
    )

    rows_str = "\n".join(rows_html)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Plans - Live Breakout Signals | {now}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',system-ui,sans-serif;background:#0d1117;color:#c9d1d9;padding:0}}

/* TOP BAR */
.topbar{{background:linear-gradient(135deg,#0d1117,#1a2433);border-bottom:1px solid #21262d;padding:18px 28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;position:sticky;top:0;z-index:50;backdrop-filter:blur(8px)}}
.topbar-title{{color:#79c0ff;font-size:1.3em;font-weight:700}}
.topbar-sub{{color:#8b949e;font-size:.82em;margin-top:3px}}
.topbar-stats{{display:flex;gap:16px;flex-wrap:wrap}}
.tstat{{text-align:center}}
.tstat-v{{font-size:1.4em;font-weight:700;color:#58a6ff}}
.tstat-l{{font-size:.72em;color:#8b949e;text-transform:uppercase;letter-spacing:.5px}}

/* CONTROLS */
.controls-bar{{background:#161b22;border-bottom:1px solid #21262d;padding:14px 28px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;position:sticky;top:72px;z-index:40}}
.search-box,.sel{{padding:8px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:.85em}}
.search-box{{min-width:200px}}
.btn-filter{{padding:7px 14px;border:1px solid #30363d;border-radius:6px;background:transparent;color:#79c0ff;cursor:pointer;font-size:.82em;transition:all .15s}}
.btn-filter:hover,.btn-filter.active{{background:#1f6feb;border-color:#58a6ff;color:#fff}}

/* SECTOR & INDUSTRY RALLY HEATMAP */
.heatmap-section{{padding:16px 28px 20px;background:#0d1117;border-bottom:1px solid #21262d}}
.heatmap-header{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:12px}}
.heatmap-title{{font-size:.95em;font-weight:700;color:#79c0ff}}
.heatmap-sub{{font-size:.75em;color:#8b949e;margin-top:2px}}
.heatmap-header-actions{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
.btn-breadth{{padding:5px 12px;border:1px solid #3fb95055;border-radius:6px;background:#0a1f0e;
  color:#3fb950;cursor:pointer;font-size:.76em;font-weight:600;text-decoration:none;
  display:inline-flex;align-items:center;gap:5px;transition:all .15s}}
.btn-breadth:hover{{background:#3fb95022;border-color:#3fb950;color:#4ade80}}
.heatmap-grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px 28px;margin-bottom:6px}}
@media(max-width:900px){{.heatmap-grid{{grid-template-columns:1fr}}}}
.heatmap-col-title{{font-size:.75em;font-weight:700;color:#8b949e;text-transform:uppercase;
  letter-spacing:.5px;margin-bottom:0;padding-bottom:6px}}
/* Sector rows */
.rally-row{{display:grid;grid-template-columns:136px 1fr 70px 55px 34px;gap:4px 6px;
  align-items:center;padding:5px 8px;border-radius:6px;cursor:pointer;
  transition:background .12s;margin-bottom:2px}}
.rally-row:hover{{background:#131c2e}}
.rally-name{{font-size:.78em;font-weight:600;color:#c9d1d9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.rally-bar-wrap{{background:#0a0f16;border-radius:3px;height:5px;overflow:hidden}}
.rally-bar-fill{{height:100%;border-radius:3px;transition:width .4s}}
.rally-hot  .rally-bar-fill{{background:linear-gradient(90deg,#f85149,#ffa500)}}
.rally-warm .rally-bar-fill{{background:linear-gradient(90deg,#e3b341,#f5a623)}}
.rally-cool .rally-bar-fill{{background:linear-gradient(90deg,#3fb950,#58a6ff)}}
.rally-low  .rally-bar-fill{{background:#2d333b}}
.rally-hot  .rally-name{{color:#ffa07a}}
.rally-warm .rally-name{{color:#e3b341}}
.rally-cool .rally-name{{color:#79c0ff}}
.rally-cnt{{font-size:.7em;color:#8b949e;text-align:right}}
.rally-a{{font-size:.7em;color:#58a6ff;text-align:right}}
.rally-a b{{color:#4ade80}}
.rally-pct{{font-size:.67em;color:#475569;text-align:right}}
/* Industry sub-panel */
.ind-panel-hdr{{display:flex;align-items:center;justify-content:space-between;
  margin-bottom:6px;padding:6px 0 6px;border-bottom:1px solid #21262d}}
.ind-panel-hdr-left{{display:flex;align-items:center;gap:10px}}
.ind-col-title{{font-size:.75em;font-weight:700;color:#8b949e;text-transform:uppercase;letter-spacing:.5px}}
.ind-toggle-btn{{padding:3px 10px;border:1px solid #30363d;border-radius:5px;
  background:transparent;color:#58a6ff;cursor:pointer;font-size:.7em;transition:all .12s}}
.ind-toggle-btn:hover{{background:#1f6feb22;border-color:#58a6ff}}
/* Industry column header row */
.ind-col-hdr{{display:grid;grid-template-columns:148px 1fr 46px 34px 50px 44px;gap:3px 6px;
  padding:2px 8px 5px;margin-bottom:1px}}
.ind-col-hdr span{{font-size:.62em;font-weight:700;color:#475569;text-transform:uppercase;
  letter-spacing:.4px;text-align:right}}
.ind-col-hdr span:first-child{{text-align:left;color:#8b949e}}
.ind-col-hdr span:nth-child(2){{text-align:left}}
/* Industry rows */
.rally-row-ind{{display:grid;grid-template-columns:148px 1fr 46px 34px 50px 44px;gap:3px 6px;
  align-items:center;padding:4px 8px;border-radius:6px;cursor:pointer;
  transition:background .12s,border-left .12s;margin-bottom:2px;
  border-left:3px solid transparent}}
.rally-row-ind:hover{{background:#131c2e}}
.rally-emerging{{border-left-color:#3fb95066!important;background:#050f0722}}
.rally-emerging:hover{{background:#050f07aa}}
.rally-building{{border-left-color:#e3b34166!important;background:#0c0b0022}}
.rally-building:hover{{background:#0c0b00aa}}
.rally-ma20{{font-size:.7em;font-weight:700;text-align:right;white-space:nowrap}}
.rally-ma50{{font-size:.67em;color:#7dd3fc;text-align:right;white-space:nowrap}}
.heatmap-ind-panel{{max-height:360px;overflow-y:auto;scrollbar-width:thin;
  scrollbar-color:#30363d #0d1117;padding-right:2px}}
.heatmap-ind-panel.collapsed{{display:none}}
.heatmap-ind-panel::-webkit-scrollbar{{width:4px}}
.heatmap-ind-panel::-webkit-scrollbar-track{{background:#0d1117}}
.heatmap-ind-panel::-webkit-scrollbar-thumb{{background:#30363d;border-radius:4px}}
.btn-export{{padding:7px 14px;border:1px solid #2ea043;border-radius:6px;background:transparent;color:#3fb950;cursor:pointer;font-size:.82em}}
.btn-export:hover{{background:#2ea04322}}

/* SECTOR PILLS */
.sector-row{{padding:10px 28px;background:#0d1117;border-bottom:1px solid #21262d;display:flex;gap:8px;flex-wrap:wrap;align-items:center}}
.sector-pill{{padding:4px 12px;border-radius:99px;border:1px solid #30363d;color:#8b949e;font-size:.78em;cursor:pointer;transition:all .15s}}
.sector-pill:hover,.sector-pill.active{{border-color:#58a6ff;color:#58a6ff;background:#1f6feb1a}}
.sector-pill b{{color:#c9d1d9}}

/* MAIN GRID */
.main{{padding:20px 28px}}
.signals-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:18px}}

/* SIGNAL CARD */
.sig-card{{background:linear-gradient(180deg,#161b22 0%,#0f141a 100%);border:1px solid #21262d;border-radius:14px;overflow:hidden;transition:all .2s}}
.sig-card:hover{{border-color:#30363d;box-shadow:0 8px 24px rgba(0,0,0,.3);transform:translateY(-2px)}}
.sig-header{{display:flex;justify-content:space-between;align-items:flex-start;padding:14px 16px 8px}}
.sig-left{{flex:1}}
.sig-sym{{font-size:1.2em;font-weight:800;color:#c9d1d9;letter-spacing:-.3px}}
.sig-meta{{display:flex;gap:6px;margin-top:5px;flex-wrap:wrap}}
.badge-sec{{padding:2px 8px;background:#1a2433;border-radius:4px;font-size:.72em;color:#79c0ff;font-weight:500}}
.badge-tf{{padding:2px 8px;background:#2a1a3a;border-radius:4px;font-size:.72em;color:#d2a8ff;font-weight:500}}
.sig-tag{{padding:2px 8px;border-radius:4px;font-size:.72em;font-weight:600}}
.tag-vcp{{background:#1e1b4b;color:#a5b4fc}}
.tag-rexp{{background:#1a2a0a;color:#86efac}}
.tag-mr{{background:#1a2a3a;color:#7dd3fc}}
.tag-bp{{background:#2a1a2a;color:#d8b4fe}}
.tag-bo{{background:#2a1a0a;color:#fbbf24}}
.tag-bf{{background:#0a2a1a;color:#34d399;border:1px solid #34d39944}}

.sig-right{{display:flex;flex-direction:column;align-items:flex-end;gap:6px}}
.sig-sparkline svg{{display:block}}
.sig-rating{{font-size:1em;font-weight:800;padding:2px 8px;border-radius:4px}}
.rat-aplus{{background:#2a2a0a;color:#ffd700;border:1px solid #ffd70044}}
.rat-a{{background:#1e1b4b;color:#a5b4fc;border:1px solid #a5b4fc44}}
.rat-b{{background:#1a2a3a;color:#7dd3fc;border:1px solid #7dd3fc44}}

/* SCORE BAR */
.score-bar-wrap{{margin:0 16px 10px;background:#0d1117;border-radius:4px;height:6px;position:relative}}
.score-bar-fill{{height:100%;border-radius:4px;transition:width .5s}}
.score-label{{position:absolute;right:0;top:-16px;font-size:.7em;color:#8b949e}}

/* PLAN GRID */
.plan-grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:#21262d;margin:0 0 0 0}}
.plan-section{{background:#0f141a;padding:10px 14px}}
.plan-section.highlight{{background:#111a22}}
.plan-title{{font-size:.7em;color:#8b949e;text-transform:uppercase;letter-spacing:.4px;margin-bottom:4px;font-weight:600}}
.plan-title small{{color:#58a6ff;font-size:.9em;text-transform:none;font-weight:600}}
.plan-value{{font-size:1em;font-weight:700;margin-bottom:2px}}
.plan-sub{{font-size:.72em;color:#6e7681}}
.entry-val{{color:#79c0ff}}
.sl-val{{color:#f85149}}
.t1-val{{color:#3fb950}}
.t2-val{{color:#2ea043}}
.t3-val{{color:#1a7431}}
.pos-val{{color:#e3b341}}

/* FOOTER */
.sig-footer{{display:flex;gap:0;border-top:1px solid #21262d;padding:10px 16px;flex-wrap:wrap;gap:12px}}
.sig-stat{{display:flex;flex-direction:column;align-items:center}}
.sstat-label{{font-size:.68em;color:#8b949e;text-transform:uppercase;letter-spacing:.3px}}
.reg-fav{{color:#3fb950;font-weight:600;font-size:.82em}}
.reg-unfav{{color:#f85149;font-weight:600;font-size:.82em}}
.reg-neu{{color:#e3b341;font-weight:600;font-size:.82em}}
.rpl{{color:#3fb950;font-weight:600;font-size:.82em}}
.rmi{{color:#f85149;font-weight:600;font-size:.82em}}
.rna{{color:#8b949e;font-weight:600;font-size:.82em}}

/* HOVER INSIGHTS */
.insight-chip{{margin:8px 16px 0;display:inline-flex;padding:2px 8px;border:1px solid #2f3b4b;border-radius:12px;color:#7dd3fc;font-size:.7em;background:#0f1a26}}
.sig-insight{{max-height:0;opacity:0;overflow:hidden;padding:0 16px;transition:max-height .25s ease,opacity .2s ease,padding .2s ease;border-top:0 solid #21262d}}
.sig-card:hover .sig-insight,.sig-card:focus-within .sig-insight{{max-height:180px;opacity:1;padding:10px 16px 12px;border-top:1px solid #21262d}}
.insight-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px}}
.insight-item{{background:#0d1117;border:1px solid #263344;border-radius:6px;padding:6px 8px}}
.insight-label{{font-size:.64em;color:#8b949e;text-transform:uppercase;letter-spacing:.3px;margin-bottom:2px}}
.insight-value{{font-size:.74em;font-weight:600}}
.metric-pos{{color:#3fb950}}
.metric-neg{{color:#f85149}}
.metric-na{{color:#8b949e}}
.insight-pill{{display:inline-block;padding:2px 6px;border-radius:10px;font-size:.7em;border:1px solid transparent;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.pill-pos{{color:#86efac;background:#102217;border-color:#1f6f3a}}
.pill-neg{{color:#fda4af;background:#261116;border-color:#7a2232}}
.pill-neu{{color:#cbd5e1;background:#18202c;border-color:#334155}}
.insight-summary{{font-size:.72em;color:#94a3b8;line-height:1.35;margin-bottom:4px}}
.insight-raw{{font-size:.68em;color:#7f8a98;line-height:1.35}}

/* PERFORMANCE ROW */
.perf-row{{display:flex;gap:0;border-top:1px solid #21262d;background:#090e14;flex-wrap:wrap}}
.perf-cell{{flex:1;min-width:60px;padding:7px 10px;text-align:center;border-right:1px solid #21262d}}
.perf-cell:last-child{{border-right:none}}
.perf-cell.appear-cell{{flex:1.3;min-width:90px}}
.perf-label{{display:block;font-size:.62em;color:#64748b;text-transform:uppercase;letter-spacing:.4px;margin-bottom:2px;font-weight:600}}
.perf-up{{font-size:.82em;font-weight:700;color:#3fb950}}
.perf-dn{{font-size:.82em;font-weight:700;color:#f85149}}
.perf-na{{font-size:.82em;color:#8b949e}}

/* APPEARANCE BADGE */
.appear-badge{{padding:2px 7px;border-radius:4px;font-size:.68em;font-weight:700;white-space:nowrap}}
.appear-hot{{color:#ffd700;background:#2a2a00;border:1px solid #ffd70044}}
.appear-warm{{color:#fb923c;background:#261400;border:1px solid #fb923c44}}
.appear-cool{{color:#60a5fa;background:#0f1f3a;border:1px solid #1d4ed844}}

/* NO RESULTS */
.no-results{{text-align:center;padding:60px;color:#8b949e;font-size:1.1em}}

/* REGIME BANNER */
.regime-banner{{background:linear-gradient(135deg,#1a1a2e,#2a1a1a);border:1px solid #30363d;border-radius:10px;padding:14px 20px;margin:20px 28px 0;display:flex;align-items:center;gap:16px;flex-wrap:wrap}}
.banner-icon{{font-size:1.5em}}
.banner-text{{flex:1}}
.banner-title{{color:#f85149;font-weight:700;font-size:.95em}}
.banner-desc{{color:#8b949e;font-size:.82em;margin-top:3px;line-height:1.5}}

/* LEGEND */
.legend{{display:flex;gap:16px;flex-wrap:wrap;padding:0 28px;margin-bottom:16px;font-size:.78em}}
.leg-item{{display:flex;align-items:center;gap:6px;color:#8b949e}}
.leg-dot{{width:10px;height:10px;border-radius:2px}}

/* RISK BOX */
.risk-box{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px 20px;margin:16px 28px 0;font-size:.82em;color:#8b949e;line-height:1.8}}
.risk-box strong{{color:#79c0ff}}

@media (max-width: 640px){{
  .insight-grid{{grid-template-columns:1fr}}
  .sig-card:hover .sig-insight,.sig-card:focus-within .sig-insight{{max-height:240px}}
}}

/* MF / INSTITUTIONAL HOLDINGS PANEL */
.mf-panel{{border-top:1px solid #21262d;margin-top:0}}
.mf-hdr{{display:flex;align-items:center;justify-content:space-between;padding:7px 16px 5px;cursor:pointer;user-select:none;background:#0a0f16}}
.mf-hdr:hover{{background:#0d1420}}
.mf-hdr-lbl{{font-size:.71em;color:#7dd3fc;font-weight:700;letter-spacing:.3px}}
.mf-sig{{font-size:.67em;font-weight:700;padding:1px 7px;border-radius:99px}}
.mf-sig-strong{{background:#0a2a14;color:#4ade80;border:1px solid #16a34a44}}
.mf-sig-dii{{background:#0a2220;color:#2dd4bf;border:1px solid #0d948844}}
.mf-sig-fii{{background:#0f1f3a;color:#60a5fa;border:1px solid #1d4ed844}}
.mf-sig-dist{{background:#2a1215;color:#f87171;border:1px solid #dc262644}}
.mf-sig-neutral{{background:#161b22;color:#8b949e;border:1px solid #30363d}}
.mf-body{{display:none;padding:8px 16px 10px;font-size:.7em;background:#080d13}}
.mf-body.open{{display:block}}
.mf-swing{{color:#94a3b8;line-height:1.4;margin-bottom:7px}}
.mf-own-grid{{display:grid;grid-template-columns:1fr 1fr;gap:4px 12px;margin-bottom:7px}}
.mf-own-lbl{{color:#8b949e;font-size:.88em;display:block;margin-bottom:1px}}
.mf-own-val{{font-weight:700;font-size:.95em}}
.mf-up{{color:#4ade80}}.mf-dn{{color:#f87171}}.mf-st{{color:#94a3b8}}
.mf-conv-high{{color:#ffd700;font-weight:700}}.mf-conv-medium{{color:#60a5fa}}.mf-conv-low{{color:#f87171}}.mf-conv-neu{{color:#94a3b8}}
.mf-top{{margin-top:6px;border-top:1px solid #0f172a;padding-top:5px}}
.mf-top-lbl{{font-size:.68em;color:#6e7681;text-transform:uppercase;letter-spacing:.35px;margin-bottom:3px}}
.mf-scheme{{display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid #0f172a}}
.mf-scheme:last-child{{border-bottom:none}}
.mf-scheme-name{{color:#c9d1d9;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:200px}}
.mf-scheme-pct{{color:#7dd3fc;font-weight:700;flex-shrink:0;margin-left:6px}}
.mf-dii-trend-bar{{display:flex;align-items:flex-end;gap:3px;height:22px}}
.mf-bar-seg{{display:inline-block;width:10px;border-radius:2px 2px 0 0;min-height:4px}}

/* BULL FLAG DETAIL PANEL */
.bf-panel{{border-top:1px solid #21262d;background:#070d10;padding:8px 16px 10px}}
.bf-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:4px 10px;margin-bottom:6px}}
.bf-cell{{background:#0b1320;border:1px solid #1a2535;border-radius:5px;padding:5px 8px}}
.bf-lbl{{font-size:.62em;color:#6e7681;text-transform:uppercase;letter-spacing:.35px;margin-bottom:2px}}
.bf-val{{font-size:.82em;font-weight:700}}
.bf-pole{{color:#34d399}}.bf-flag{{color:#fbbf24}}.bf-vol{{color:#60a5fa}}
.bf-targets{{display:flex;gap:6px;flex-wrap:wrap;font-size:.72em}}
.bf-t{{padding:2px 7px;border-radius:4px;font-weight:700}}
.bf-t1{{background:#052e16;color:#4ade80;border:1px solid #16a34a55}}
.bf-t2{{background:#052e16;color:#86efac;border:1px solid #16a34a77}}
.bf-t3{{background:#1a1a00;color:#ffd700;border:1px solid #ffd70055}}
.bf-subtype{{display:inline-flex;padding:1px 7px;border-radius:99px;font-size:.65em;font-weight:700}}
.bf-st-forming{{background:#0f1f3a;color:#60a5fa;border:1px solid #1d4ed855}}
.bf-st-breakout{{background:#0a2a14;color:#4ade80;border:1px solid #16a34a55}}

/* RANGE EXPANSION DETAIL PANEL */
.rexp-panel{{border-top:1px solid #21262d;background:#050e08;padding:8px 16px 10px}}
.rexp-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:4px 10px;margin-bottom:6px}}
.rexp-cell{{background:#0a1510;border:1px solid #1a3020;border-radius:5px;padding:5px 8px}}
.rexp-lbl{{font-size:.62em;color:#6e7681;text-transform:uppercase;letter-spacing:.35px;margin-bottom:2px}}
.rexp-val{{font-size:.82em;font-weight:700}}
.rexp-pos{{color:#4ade80}}.rexp-neg{{color:#f87171}}
.rexp-targets{{display:flex;gap:6px;flex-wrap:wrap;font-size:.72em}}
.rexp-t{{padding:2px 7px;border-radius:4px;font-weight:700}}
.rexp-t1{{background:#052e16;color:#4ade80;border:1px solid #16a34a55}}
.rexp-t2{{background:#052e16;color:#86efac;border:1px solid #16a34a77}}
.rexp-t3{{background:#1a1a00;color:#ffd700;border:1px solid #ffd70055}}
.rexp-subtype{{display:inline-flex;padding:1px 7px;border-radius:99px;font-size:.65em;font-weight:700}}
.rexp-st-bo{{background:#0a2a14;color:#86efac;border:1px solid #16a34a55}}
.rexp-st-wl{{background:#0f1f3a;color:#7dd3fc;border:1px solid #1d4ed855}}

/* BREAKOUT PULLBACK DETAIL PANEL */
.bp-panel{{border-top:1px solid #21262d;background:#0d0813;padding:8px 16px 10px}}
.bp-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:4px 10px;margin-bottom:6px}}
.bp-cell{{background:#120a1a;border:1px solid #2a1535;border-radius:5px;padding:5px 8px}}
.bp-lbl{{font-size:.62em;color:#6e7681;text-transform:uppercase;letter-spacing:.35px;margin-bottom:2px}}
.bp-val{{font-size:.82em;font-weight:700}}
.bp-targets{{display:flex;gap:6px;flex-wrap:wrap;font-size:.72em}}
.bp-t{{padding:2px 7px;border-radius:4px;font-weight:700}}
.bp-t1{{background:#052e16;color:#4ade80;border:1px solid #16a34a55}}
.bp-t2{{background:#052e16;color:#86efac;border:1px solid #16a34a77}}
.bp-t3{{background:#1a1a00;color:#ffd700;border:1px solid #ffd70055}}
.bp-subtype{{display:inline-flex;padding:1px 7px;border-radius:99px;font-size:.65em;font-weight:700;background:#2a1535;color:#d8b4fe;border:1px solid #7c3aed55}}

/* MULTI-SETUP BADGE */
.multi-setup-badge{{padding:2px 8px;border-radius:4px;font-size:.70em;font-weight:700;background:#1e1b4b;color:#a78bfa;border:1px solid #7c3aed55;white-space:nowrap}}
</style>
</head>
<body>

<div class="topbar">
  <div>
    <div class="topbar-title">&#127919; Live Breakout Trade Plans &mdash; NSE India</div>
    <div class="topbar-sub">All active signals from latest scan &bull; {now} &bull; {run_history_note}</div>
  </div>
  <div class="topbar-stats">
    <div class="tstat"><div class="tstat-v">{total}</div><div class="tstat-l">Signals</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#ffd700">{a_plus}</div><div class="tstat-l">A+ Rated</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#a5b4fc">{a_rate}</div><div class="tstat-l">A &amp; Above</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#fb923c">{recurring_count}</div><div class="tstat-l">Recurring</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#86efac">{setup_counts.get('RANGE_EXPANSION',0)}</div><div class="tstat-l">Range Exp</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#a5b4fc">{setup_counts.get('VCP',0)}</div><div class="tstat-l">VCP</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#d8b4fe">{setup_counts.get('BREAKOUT_PULLBACK',0)}</div><div class="tstat-l">BP</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#34d399">{setup_counts.get('BULL_FLAG',0)}</div><div class="tstat-l">Bull Flag</div></div>
  </div>
</div>

<div class="regime-banner">
  <div class="banner-icon">&#9888;</div>
  <div class="banner-text">
    <div class="banner-title">Market Regime: UNFAVORABLE &mdash; Operate with Reduced Size</div>
    <div class="banner-desc">
      Current scan shows UNFAVORABLE regime. Nifty below key moving averages. FII net selling.
      Recommended: Reduce position size to 50% of normal. Only trade A+ rated setups.
      Wait for regime to shift to NEUTRAL or FAVORABLE before deploying full capital.
    </div>
  </div>
</div>

<div class="risk-box">
  <strong>Position Sizing (1% Risk, &#8377;{ACCOUNT_SIZE/100000:.0f}L Account):</strong>
  &nbsp;Shares = floor(Account &times; 1%) / (Entry &minus; Stop)
  &nbsp;|&nbsp; <strong>T1</strong> = Entry + 1.5&times;Risk (35% exit)
  &nbsp;|&nbsp; <strong>T2</strong> = Entry + 2.5&times;Risk (40% exit)
  &nbsp;|&nbsp; <strong>T3</strong> = Entry + 4.0&times;Risk (25% exit)
  &nbsp;|&nbsp; Stop = 10-bar swing low (max 4% below entry)
</div>

<div class="controls-bar">
  <input class="search-box" id="searchBox" placeholder="&#128269; Search symbol, sector, industry..." oninput="applyFilters()">
  <select class="sel" id="setupFilter" onchange="applyFilters()">
    <option value="">All Setups</option>
    <option value="RANGE_EXPANSION">Range Expansion</option>
    <option value="VCP">VCP</option>
    <option value="MEAN_REVERSION">Mean Reversion</option>
    <option value="BREAKOUT_PULLBACK">Breakout Pullback</option>
    <option value="BULL_FLAG">Bull Flag</option>
  </select>
  <select class="sel" id="ratingFilter" onchange="applyFilters()">
    <option value="">All Ratings</option>
    <option value="A+">A+ Only</option>
    <option value="A">A &amp; Above</option>
    <option value="B">B &amp; Above</option>
  </select>
  <select class="sel" id="industryFilter" onchange="activeIndustry=this.value;applyFilters()" title="Filter by sub-sector / industry">
    <option value="">All Industries</option>
    {industry_options}
  </select>
  <select class="sel" id="appearFilter" onchange="applyFilters()" title="Filter by how many of the last {_rh_total} runs the setup appeared in">
    <option value="">All Appearances</option>
    <option value="50">Seen 50%+ runs</option>
    <option value="75">Seen 75%+ runs</option>
    <option value="high">Seen 15+ runs (Hot)</option>
    <option value="warm">Seen 8+ runs</option>
  </select>
  <button class="btn-filter" onclick="toggleSort('score')" id="btn-sort-score">&#128202; Sort: Score</button>
  <button class="btn-filter" onclick="toggleSort('symbol')" id="btn-sort-sym">&#9776; Sort: Symbol</button>
  <button class="btn-filter" onclick="toggleSort('appear')" id="btn-sort-appear">&#128257; Sort: Recurring</button>
  <button class="btn-export" onclick="exportCSV()">&#8659; Export CSV</button>
  <span id="filterCount" style="color:#8b949e;font-size:.83em;margin-left:8px"></span>
</div>

<div class="sector-row">
  <span style="color:#8b949e;font-size:.8em;font-weight:600">Sector:</span>
  <span class="sector-pill active" onclick="filterSector('')">All</span>
  {sector_pills}
</div>

<!-- ── Sector & Industry Rally Heatmap ─────────────────────────────────── -->
<div class="heatmap-section">
  <div class="heatmap-header">
    <div>
      <div class="heatmap-title">🔥 Sector &amp; Industry Rally Radar</div>
      <div class="heatmap-sub">Concentration of breakout signals — click any row to filter signal cards below</div>
    </div>
    <div class="heatmap-header-actions">
      <span style="font-size:.72em;color:#8b949e">
        <span style="color:#ffa07a;font-weight:700">■</span> Hot &nbsp;
        <span style="color:#e3b341;font-weight:700">■</span> Warm &nbsp;
        <span style="color:#79c0ff;font-weight:700">■</span> Building &nbsp;
        <span style="color:#475569;font-weight:700">■</span> Low
      </span>
      <a class="btn-breadth" href="market_breadth.html" target="_blank">📊 Full Breadth Map ↗</a>
      <button class="btn-filter" onclick="resetAllFilters()" style="padding:5px 12px;font-size:.76em">↺ Reset</button>
    </div>
  </div>
  <div class="heatmap-grid">
    <div>
      <div class="heatmap-col-title" style="border-bottom:1px solid #21262d;margin-bottom:6px">📊 Sector Rally (Broad)</div>
      {sector_heatmap_rows}
    </div>
    <div>
      <div class="ind-panel-hdr">
        <div class="ind-panel-hdr-left">
          <span class="ind-col-title">🔬 Sub-Industry Breadth</span>
          <span style="font-size:.66em;color:#475569">(top 35 by signals)</span>
        </div>
        <button class="ind-toggle-btn" id="indToggleBtn" onclick="toggleIndPanel()">▲ Collapse</button>
      </div>
      <div class="ind-col-hdr">
        <span>Industry</span><span></span>
        <span>Sig</span><span>A+</span>
        <span>&gt;20MA</span><span>&gt;50MA</span>
      </div>
      <div class="heatmap-ind-panel" id="indPanel">
        {industry_heatmap_rows}
      </div>
    </div>
  </div>
  <div style="font-size:.66em;color:#475569;margin-top:6px">
    💡 Click sector/industry rows to filter cards · <b style="color:#3fb950">Green left border</b> = EMERGING (25–65% &gt;20MA) · <b style="color:#e3b341">Yellow</b> = BUILDING (65–80%) · <a href="market_breadth.html" target="_blank" style="color:#58a6ff;text-decoration:none">📊 Full Market Breadth Dashboard →</a>
  </div>
</div>

<div class="legend">
  <div class="leg-item"><div class="leg-dot" style="background:#a5b4fc"></div>VCP Breakout</div>
  <div class="leg-item"><div class="leg-dot" style="background:#86efac"></div>Range Expansion</div>
  <div class="leg-item"><div class="leg-dot" style="background:#7dd3fc"></div>Mean Reversion</div>
  <div class="leg-item"><div class="leg-dot" style="background:#d8b4fe"></div>Breakout Pullback</div>
  <div class="leg-item"><div class="leg-dot" style="background:#34d399"></div>Bull Flag</div>
  <div class="leg-item"><div class="leg-dot" style="background:#a78bfa"></div>🔀 Multi-Setup</div>
  <div class="leg-item"><div class="leg-dot" style="background:#ffd700"></div>A+ Rating</div>
  <div class="leg-item"><div class="leg-dot" style="background:#3fb950"></div>RS Positive</div>
  <div class="leg-item"><div class="leg-dot" style="background:#ffd700;border-radius:50%"></div>Hot (15+ runs)</div>
  <div class="leg-item"><div class="leg-dot" style="background:#fb923c;border-radius:50%"></div>Warm (8+ runs)</div>
  <div class="leg-item"><div class="leg-dot" style="background:#60a5fa;border-radius:50%"></div>New (&lt;8 runs)</div>
</div>

<div class="legend">
  <div class="leg-item"><div class="leg-dot" style="background:#a5b4fc"></div>VCP Breakout</div>
  <div class="leg-item"><div class="leg-dot" style="background:#86efac"></div>Range Expansion</div>
  <div class="leg-item"><div class="leg-dot" style="background:#7dd3fc"></div>Mean Reversion</div>
  <div class="leg-item"><div class="leg-dot" style="background:#d8b4fe"></div>Breakout Pullback</div>
  <div class="leg-item"><div class="leg-dot" style="background:#34d399"></div>Bull Flag</div>
  <div class="leg-item"><div class="leg-dot" style="background:#a78bfa"></div>🔀 Multi-Setup</div>
  <div class="leg-item"><div class="leg-dot" style="background:#ffd700"></div>A+ Rating</div>
  <div class="leg-item"><div class="leg-dot" style="background:#3fb950"></div>RS Positive</div>
  <div class="leg-item"><div class="leg-dot" style="background:#ffd700;border-radius:50%"></div>Hot (15+ runs)</div>
  <div class="leg-item"><div class="leg-dot" style="background:#fb923c;border-radius:50%"></div>Warm (8+ runs)</div>
  <div class="leg-item"><div class="leg-dot" style="background:#60a5fa;border-radius:50%"></div>New (&lt;8 runs)</div>
</div>

<!-- ══════════════════════════════════════════════════════════════════════ -->
<!-- ── 🔬 Watchlist Pattern Lab (Integrated) ──────────────────────────── -->
<!-- ══════════════════════════════════════════════════════════════════════ -->
<style>
.wpl-wrap{{margin:0 28px 20px;border:1px solid #21262d;border-radius:10px;overflow:hidden;background:#0d1117}}
.wpl-header{{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:#111820;cursor:pointer;user-select:none;border-bottom:1px solid #21262d}}
.wpl-header-left{{display:flex;align-items:center;gap:10px}}
.wpl-title{{font-size:.95em;font-weight:700;color:#79c0ff}}
.wpl-subtitle{{font-size:.73em;color:#8b949e;margin-left:4px}}
.wpl-toggle-btn{{font-size:.75em;color:#79c0ff;background:#0d1117;border:1px solid #30363d;border-radius:5px;padding:3px 10px;cursor:pointer}}
.wpl-body{{padding:14px 16px;display:none}}
.wpl-body.open{{display:block}}
.wpl-controls-row{{display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap;margin-bottom:10px}}
.wpl-input{{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;border-radius:6px;padding:7px 10px;font-size:.83em;min-width:200px}}
.wpl-textarea{{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;border-radius:6px;padding:7px 10px;font-size:.83em;width:100%;resize:none}}
.wpl-btn{{background:#1f6feb;border:none;color:#fff;padding:7px 16px;border-radius:6px;cursor:pointer;font-weight:700;font-size:.83em;white-space:nowrap}}
.wpl-btn:hover{{background:#388bfd}}
.wpl-btn:disabled{{background:#30363d;cursor:not-allowed}}
.wpl-btn-sm{{padding:4px 10px;font-size:.75em}}
.wpl-btn-teal{{background:#0f766e}}.wpl-btn-teal:hover{{background:#0d9488}}
.wpl-btn-amber{{background:#92400e}}.wpl-btn-amber:hover{{background:#b45309}}
.wpl-mkt-bar{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}}
.wpl-mkt-chip{{background:#0d1117;border:1px solid #21262d;border-radius:7px;padding:6px 12px;text-align:center;min-width:80px}}
.wpl-mkt-chip .v{{font-size:1em;font-weight:800;color:#58a6ff}}
.wpl-mkt-chip .l{{font-size:.65em;color:#8b949e;text-transform:uppercase;letter-spacing:.4px;margin-top:1px}}
.wpl-phase-pill{{display:inline-block;padding:2px 8px;border-radius:99px;font-size:.7em;font-weight:700;margin:2px;border:1px solid transparent}}
.wpl-phase-decline{{background:#450a0a;color:#f87171;border-color:#7f1d1d}}
.wpl-phase-recovery{{background:#052e16;color:#4ade80;border-color:#14532d}}
.wpl-phase-consolidation{{background:#1c1917;color:#fbbf24;border-color:#44403c}}
.wpl-table-wrap{{overflow-x:auto;margin-top:8px}}
.wpl-table{{width:100%;border-collapse:collapse;font-size:.78em}}
.wpl-table th{{background:#111820;border-bottom:2px solid #21262d;padding:6px 8px;text-align:left;color:#79c0ff;font-size:.7em;text-transform:uppercase;letter-spacing:.4px;white-space:nowrap;cursor:pointer}}
.wpl-table th:hover{{color:#c9d1d9}}
.wpl-table td{{border-bottom:1px solid #161b22;padding:6px 8px;vertical-align:middle;white-space:nowrap}}
.wpl-table tr:hover td{{background:#0d1520}}
.wpl-table tr.wpl-leader td{{background:#061218}}
.wpl-sym{{font-weight:800;color:#c9d1d9;cursor:pointer;text-decoration:underline dotted}}
.wpl-sym:hover{{color:#58a6ff}}
.wpl-pos{{color:#4ade80;font-weight:700}}.wpl-neg{{color:#f87171;font-weight:700}}
.wpl-bar{{display:inline-block;width:40px;height:5px;background:#21262d;border-radius:3px;overflow:hidden;vertical-align:middle;margin-left:3px}}
.wpl-bar-fill{{height:100%;border-radius:3px}}
.wpl-badge{{display:inline-block;padding:1px 6px;border-radius:4px;font-size:.7em;font-weight:700}}
.wpl-s2{{background:#052e16;color:#4ade80}}.wpl-s1{{background:#0c1a2e;color:#7dd3fc}}
.wpl-s3{{background:#2a1900;color:#fbbf24}}.wpl-s4{{background:#2a0d0d;color:#f87171}}
.wpl-loading{{display:flex;align-items:center;gap:8px;color:#8b949e;font-size:.83em;padding:12px 0}}
.wpl-spinner{{width:14px;height:14px;border:2px solid #30363d;border-top-color:#58a6ff;border-radius:50%;animation:wplspin .7s linear infinite}}
@keyframes wplspin{{to{{transform:rotate(360deg)}}}}
.wpl-error{{color:#f87171;font-size:.83em;padding:8px;background:#1a0808;border-radius:6px;border:1px solid #7f1d1d;margin-top:6px}}
/* Deep dive drawer */
.wpl-drawer{{background:#111820;border:1px solid #21262d;border-radius:8px;padding:14px;margin-top:10px;display:none}}
.wpl-drawer.open{{display:block}}
.wpl-drawer-tabs{{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #21262d}}
.wpl-dtab{{padding:4px 12px;border-radius:5px;font-size:.75em;cursor:pointer;background:#0d1117;border:1px solid #30363d;color:#8b949e}}
.wpl-dtab.active{{background:#1f6feb;border-color:#388bfd;color:#fff}}
.wpl-dpane{{display:none;font-size:.8em;line-height:1.7;color:#8b949e}}.wpl-dpane.active{{display:block}}
.wpl-plan-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:6px;margin-top:6px}}
.wpl-plan-item{{background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:6px 8px}}
.wpl-plan-label{{font-size:.65em;color:#8b949e;text-transform:uppercase;letter-spacing:.3px}}
.wpl-plan-value{{font-size:.88em;font-weight:700;margin-top:2px}}
.wpl-news-list{{list-style:none;padding:0;margin:0}}
.wpl-news-item{{border-bottom:1px solid #161b22;padding:5px 0}}
.wpl-news-item:last-child{{border-bottom:none}}
.wpl-news-a{{color:#58a6ff;text-decoration:none;font-size:.8em;line-height:1.4}}
.wpl-news-a:hover{{text-decoration:underline}}
.wpl-news-meta{{font-size:.65em;color:#8b949e;margin-top:1px}}
.wpl-phase-tbl{{width:100%;border-collapse:collapse;font-size:.75em}}
.wpl-phase-tbl th{{color:#8b949e;padding:3px 6px;border-bottom:1px solid #21262d;text-align:left;font-size:.7em}}
.wpl-phase-tbl td{{padding:3px 6px;border-bottom:1px solid #0d1117}}
.wpl-checklist{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:5px;list-style:none;padding:0;margin:8px 0}}
.wpl-chk{{display:flex;align-items:center;gap:6px;font-size:.76em;padding:4px 8px;background:#0d1117;border:1px solid #161b22;border-radius:5px}}
</style>

<div class="wpl-wrap">
  <div class="wpl-header" onclick="wplToggle()">
    <div class="wpl-header-left">
      <span class="wpl-title">🔬 Watchlist Pattern Lab</span>
      <span class="wpl-subtitle">— RS Leaders · Phase Behavior · Trade Thesis · News · FII/DII</span>
      <span id="wplStatus" style="font-size:.7em;color:#4ade80;margin-left:8px"></span>
    </div>
    <button class="wpl-toggle-btn" id="wplToggleBtn">▼ Open</button>
  </div>
  <div class="wpl-body" id="wplBody">

    <div style="display:grid;grid-template-columns:1fr auto auto auto auto;gap:8px;align-items:end;margin-bottom:10px">
      <div>
        <div style="font-size:.72em;color:#8b949e;margin-bottom:3px">Stock List <span style="color:#475569">(auto-loaded from this page's signals)</span></div>
        <textarea id="wplSymbols" class="wpl-textarea" rows="2" placeholder="AEROFLEX, CENTUM, PFOCUS..."></textarea>
      </div>
      <div>
        <div style="font-size:.72em;color:#8b949e;margin-bottom:3px">Workers</div>
        <input id="wplWorkers" type="number" value="4" min="1" max="10" class="wpl-input" style="width:56px">
      </div>
      <div style="display:flex;flex-direction:column;gap:4px">
        <button class="wpl-btn" id="wplAnalyzeBtn" onclick="wplAnalyze()">🔍 Analyze</button>
        <button class="wpl-btn wpl-btn-teal wpl-btn-sm" onclick="wplLoadFromPage()">📋 Load From Page</button>
      </div>
      <div style="display:flex;flex-direction:column;gap:4px">
        <button class="wpl-btn wpl-btn-sm" style="background:#21262d" onclick="wplLoadPhases()">📊 Market Phases</button>
        <button class="wpl-btn wpl-btn-amber wpl-btn-sm" onclick="wplExportCSV()">⬇ CSV</button>
      </div>
    </div>

    <div style="display:flex;gap:14px;font-size:.76em;color:#8b949e;flex-wrap:wrap;margin-bottom:10px">
      <label style="display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="wplNews" checked> News</label>
      <label style="display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="wplFund" checked> Fundamentals</label>
      <label style="display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="wplMF" checked> FII/DII</label>
    </div>

    <!-- Market context -->
    <div id="wplMktBar" style="display:none;margin-bottom:10px">
      <div style="font-size:.66em;color:#8b949e;text-transform:uppercase;letter-spacing:.4px;margin-bottom:5px">Nifty50 Phase Map</div>
      <div class="wpl-mkt-bar" id="wplMktChips"></div>
      <div id="wplPhases" style="margin-top:5px"></div>
    </div>

    <!-- Loading -->
    <div id="wplLoading" style="display:none" class="wpl-loading">
      <div class="wpl-spinner"></div>
      <span id="wplLoadingTxt">Fetching price data, computing RS scores, detecting patterns…</span>
    </div>
    <div id="wplError" style="display:none" class="wpl-error"></div>

    <!-- Summary table -->
    <div id="wplResultsWrap" style="display:none">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
        <span style="font-size:.83em;font-weight:700;color:#79c0ff">📋 Watchlist Summary</span>
        <div style="display:flex;gap:5px">
          <button class="wpl-btn wpl-btn-sm" style="background:#21262d" onclick="wplSort('conviction')">Conviction</button>
          <button class="wpl-btn wpl-btn-sm" style="background:#21262d" onclick="wplSort('rs_score')">RS Score</button>
          <button class="wpl-btn wpl-btn-sm" style="background:#21262d" onclick="wplSort('ret_60d')">60d Ret</button>
        </div>
      </div>
      <div class="wpl-table-wrap">
        <table class="wpl-table">
          <thead>
            <tr>
              <th onclick="wplSort('symbol')">Symbol</th>
              <th onclick="wplSort('price')">Price</th>
              <th onclick="wplSort('ret_20d')">20d%</th>
              <th onclick="wplSort('ret_60d')">60d%</th>
              <th onclick="wplSort('rs_score')">RS</th>
              <th onclick="wplSort('adr_pct')">ADR%</th>
              <th onclick="wplSort('stage')">Stage</th>
              <th onclick="wplSort('pattern_score')">Pattern</th>
              <th onclick="wplSort('conviction')">Conv.</th>
              <th>Action</th>
              <th>Entry</th>
              <th>Stop</th>
              <th>T1</th>
              <th>R:R</th>
              <th>Setup</th>
            </tr>
          </thead>
          <tbody id="wplTbody"></tbody>
        </table>
      </div>

      <!-- Deep dive drawer -->
      <div class="wpl-drawer" id="wplDrawer">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <span style="font-weight:700;color:#c9d1d9">🔎 <span id="wplDrawerSym"></span></span>
          <button class="wpl-btn wpl-btn-sm" style="background:#21262d" onclick="document.getElementById('wplDrawer').classList.remove('open')">✕ Close</button>
        </div>
        <div class="wpl-drawer-tabs">
          <button class="wpl-dtab active" onclick="wplDTab(this,'wplDThesis')">📊 Thesis</button>
          <button class="wpl-dtab" onclick="wplDTab(this,'wplDPattern')">🎯 Pattern</button>
          <button class="wpl-dtab" onclick="wplDTab(this,'wplDFund')">📈 Funds</button>
          <button class="wpl-dtab" onclick="wplDTab(this,'wplDMF')">🏦 FII/DII</button>
          <button class="wpl-dtab" onclick="wplDTab(this,'wplDNews')">📰 News</button>
          <button class="wpl-dtab" onclick="wplDTab(this,'wplDPhases')">📉 Phases</button>
        </div>
        <div id="wplDThesis" class="wpl-dpane active"></div>
        <div id="wplDPattern" class="wpl-dpane"></div>
        <div id="wplDFund" class="wpl-dpane"></div>
        <div id="wplDMF" class="wpl-dpane"></div>
        <div id="wplDNews" class="wpl-dpane"></div>
        <div id="wplDPhases" class="wpl-dpane"></div>
      </div>
    </div>

  </div><!-- /.wpl-body -->
</div><!-- /.wpl-wrap -->

<script>
// ── Watchlist Pattern Lab ─────────────────────────────────────────────────────
const WPL_API = 'http://localhost:8000';
let _wplData = null, _wplTable = [], _wplSortCol = 'conviction', _wplSortDir = -1;

function wplToggle() {{
  const body = document.getElementById('wplBody');
  const btn  = document.getElementById('wplToggleBtn');
  const open = body.classList.toggle('open');
  btn.textContent = open ? '▲ Close' : '▼ Open';
  if (open && !_wplData) {{ wplLoadFromPage(); wplLoadPhases(); }}
}}

function wplLoadFromPage() {{
  // Collect all unique symbols currently visible on the page
  const syms = [...new Set(
    [...document.querySelectorAll('.sig-card[data-symbol]')]
      .map(c => c.dataset.symbol.replace(/\\.NS$|\\.BO$/i,''))
      .filter(Boolean)
  )];
  if (syms.length) document.getElementById('wplSymbols').value = syms.slice(0,25).join(', ');
}}

function _wplFmt(v, d=1, sfx='') {{
  if (v == null || v === '') return '—';
  const n = Number(v);
  return isNaN(n) ? String(v) : n.toFixed(d) + sfx;
}}

function _wplRet(v) {{
  if (v == null) return '<span style="color:#8b949e">—</span>';
  const n = Number(v), c = n >= 0 ? 'wpl-pos' : 'wpl-neg';
  return `<span class="${{c}}">${{n>=0?'+':''}}${{n.toFixed(1)}}%</span>`;
}}

function _wplBar(score, color) {{
  const w = Math.min(100, Math.max(0, score||0));
  return `<div class="wpl-bar"><div class="wpl-bar-fill" style="width:${{w}}%;background:${{color||'#58a6ff'}};"></div></div>`;
}}

function _wplStageBadge(stage) {{
  const map = {{1:'wpl-s1',2:'wpl-s2',3:'wpl-s3',4:'wpl-s4'}};
  return stage ? `<span class="wpl-badge ${{map[stage]||'wpl-s1'}}">S${{stage}}</span>` : '—';
}}

function _wplAction(action, label) {{
  if (label) {{
    const c = action==='BUY_NOW'?'#4ade80':action==='WATCH_CLOSELY'?'#facc15':action==='AVOID'?'#f87171':'#7dd3fc';
    return `<span style="font-weight:700;font-size:.78em;color:${{c}};">${{label}}</span>`;
  }}
  const m = {{BUY_NOW:'<span style="color:#4ade80;font-weight:700">🟢 BUY</span>',WATCH_CLOSELY:'<span style="color:#facc15;font-weight:700">🟡 WATCH</span>',WATCH:'<span style="color:#7dd3fc">🔵 WATCH</span>',AVOID:'<span style="color:#f87171">🔴 AVOID</span>'}};
  return m[action] || `<span style="color:#8b949e">${{action||'—'}}</span>`;
}}

async function wplLoadPhases() {{
  const bar = document.getElementById('wplMktBar');
  const chips = document.getElementById('wplMktChips');
  const phases = document.getElementById('wplPhases');
  bar.style.display = 'block';
  chips.innerHTML = '<span style="color:#8b949e;font-size:.78em">Loading Nifty…</span>';
  try {{
    const d = await fetch(WPL_API + '/api/watchlist/market-phases').then(r=>r.json());
    chips.innerHTML = `<div class="wpl-mkt-chip"><div class="v">${{d.nifty_current?.toFixed(0)||'—'}}</div><div class="l">Nifty</div></div>`;
    phases.innerHTML = (d.recent_phases||[]).map(p => {{
      const cls = p.phase==='decline'?'wpl-phase-decline':p.phase==='recovery'?'wpl-phase-recovery':'wpl-phase-consolidation';
      return `<span class="wpl-phase-pill ${{cls}}">${{p.phase.toUpperCase()}} ${{p.start_date}}→${{p.end_date}} ${{p.change_pct>0?'+':''}}${{p.change_pct}}%</span>`;
    }}).join('');
  }} catch(e) {{ chips.innerHTML = `<span style="color:#f87171">API offline: ${{e.message}}</span>`; }}
}}

async function wplAnalyze() {{
  const raw = (document.getElementById('wplSymbols').value||'').trim();
  if (!raw) {{ wplLoadFromPage(); return; }}
  const symbols = raw.split(/[,\\n;]+/).map(s=>s.trim().toUpperCase()).filter(Boolean);
  if (!symbols.length) return;

  const btn = document.getElementById('wplAnalyzeBtn');
  btn.disabled = true; btn.textContent = '⏳ Analyzing…';
  document.getElementById('wplLoading').style.display = 'flex';
  document.getElementById('wplError').style.display = 'none';
  document.getElementById('wplResultsWrap').style.display = 'none';
  document.getElementById('wplStatus').textContent = `Analyzing ${{symbols.length}} stocks…`;

  await wplLoadPhases();

  try {{
    const body = JSON.stringify({{
      symbols, market:'india',
      workers: parseInt(document.getElementById('wplWorkers').value)||4,
      include_news: document.getElementById('wplNews').checked,
      include_fundamentals: document.getElementById('wplFund').checked,
      include_mf: document.getElementById('wplMF').checked,
    }});
    const data = await fetch(WPL_API + '/api/watchlist/analyze', {{
      method:'POST', headers:{{'Content-Type':'application/json'}}, body
    }}).then(r=>{{ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); }});
    _wplData = data;
    _wplTable = data.summary_table || [];
    document.getElementById('wplStatus').textContent = `✅ ${{data.successful}}/${{data.total_symbols}} done`;
    document.getElementById('wplResultsWrap').style.display = 'block';
    wplRenderTable();
  }} catch(e) {{
    document.getElementById('wplError').style.display = 'block';
    document.getElementById('wplError').textContent = '❌ ' + e.message + ' — Is the API server running at localhost:8000?';
  }} finally {{
    btn.disabled = false; btn.textContent = '🔍 Analyze';
    document.getElementById('wplLoading').style.display = 'none';
  }}
}}

function wplSort(col) {{
  if (_wplSortCol===col) _wplSortDir*=-1; else {{_wplSortCol=col;_wplSortDir=-1;}}
  wplRenderTable();
}}

function wplRenderTable() {{
  const sorted = [..._wplTable].sort((a,b)=>{{
    const av = a[_wplSortCol]!=null ? Number(a[_wplSortCol])||a[_wplSortCol] : '';
    const bv = b[_wplSortCol]!=null ? Number(b[_wplSortCol])||b[_wplSortCol] : '';
    return av<bv?_wplSortDir:av>bv?-_wplSortDir:0;
  }});
  const tbody = document.getElementById('wplTbody');
  if (!sorted.length) {{ tbody.innerHTML='<tr><td colspan="15" style="color:#8b949e;padding:12px">No results</td></tr>'; return; }}
  tbody.innerHTML = sorted.map(row=>{{
    if (row.error) return `<tr><td class="wpl-sym">${{row.symbol}}</td><td colspan="14" style="color:#f87171;font-size:.75em">${{row.error}}</td></tr>`;
    const pat = (row.pattern||'').replace(/[🌟🚀✅🔵⚠️]/g,'').trim().slice(0,20);
    const cv = row.conviction||0;
    const cc = cv>=72?'#ffd700':cv>=58?'#4ade80':'#94a3b8';
    const extBadge = row.is_extended ? '<span title="'+( row.extension_reason||'Extended')+ '" style="color:#fb923c;font-size:.65em;margin-left:3px;cursor:help">⏳EXT</span>' : '';
    const restBadge = row.is_consolidating ? '<span title="Resting after move" style="color:#4ade80;font-size:.65em;margin-left:3px;cursor:help">💤REST</span>' : '';
    const setupLbl = row.is_extended?'⏳ EXTENDED':row.is_consolidating?'💤 RESTING':(row.setup||'').replace(/_/g,' ');
    const setupClr = row.is_extended?'#fb923c':row.is_consolidating?'#4ade80':'#8b949e';
    return `<tr class="${{row.action==='BUY_NOW'?'wpl-leader':''}}">
      <td><span class="wpl-sym" onclick="wplDeepDive('${{row.symbol}}')">${{row.symbol}}</span>${{extBadge}}${{restBadge}}</td>
      <td>₹${{_wplFmt(row.price,2)}}</td>
      <td>${{_wplRet(row.ret_20d)}}</td>
      <td>${{_wplRet(row.ret_60d)}}</td>
      <td><span style="font-weight:700;color:${{row.rs_score>=80?'#4ade80':row.rs_score>=60?'#fbbf24':'#8b949e'}}">${{row.rs_score||'—'}}</span>${{_wplBar(row.rs_score,'#4ade80')}}</td>
      <td>${{_wplFmt(row.adr_pct,1,'%')}}</td>
      <td>${{_wplStageBadge(row.stage)}}</td>
      <td style="font-size:.72em;color:#8b949e">${{pat}}</td>
      <td><span style="font-weight:700;color:${{cc}}">${{cv}}</span>${{_wplBar(cv,cc)}}</td>
      <td>${{_wplAction(row.action, row.action_label)}}</td>
      <td style="color:#7dd3fc">₹${{_wplFmt(row.entry,2)}}</td>
      <td style="color:#f87171">₹${{_wplFmt(row.stop,2)}}</td>
      <td style="color:#4ade80">₹${{_wplFmt(row.t1,2)}}</td>
      <td style="color:#fbbf24">${{_wplFmt(row.rr_t1,1)}}:1</td>
      <td style="font-size:.72em;color:${{setupClr}};font-weight:${{row.is_consolidating?'700':'400'}}">${{setupLbl}}</td>
    </tr>`;
  }}).join('');
}}

function wplDeepDive(symbol) {{
  if (!_wplData) return;
  const r = (_wplData.results||[]).find(x=>x.symbol===symbol);
  if (!r) return;
  const drawer = document.getElementById('wplDrawer');
  document.getElementById('wplDrawerSym').textContent = symbol;
  drawer.classList.add('open');
  drawer.scrollIntoView({{behavior:'smooth',block:'nearest'}});
  // Reset tabs
  drawer.querySelectorAll('.wpl-dtab').forEach(t=>t.classList.remove('active'));
  drawer.querySelectorAll('.wpl-dpane').forEach(p=>p.classList.remove('active'));
  drawer.querySelector('.wpl-dtab').classList.add('active');
  document.getElementById('wplDThesis').classList.add('active');
  // Render
  _wplRenderThesis(r); _wplRenderPattern(r); _wplRenderFund(r);
  _wplRenderMF(r); _wplRenderNews(r); _wplRenderPhasesBehav(r);
}}

function wplDTab(btn, paneId) {{
  btn.closest('.wpl-drawer').querySelectorAll('.wpl-dtab').forEach(t=>t.classList.remove('active'));
  btn.closest('.wpl-drawer').querySelectorAll('.wpl-dpane').forEach(p=>p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById(paneId).classList.add('active');
}}

function _wplPI(label, val) {{
  return `<div class="wpl-plan-item"><div class="wpl-plan-label">${{label}}</div><div class="wpl-plan-value">${{val}}</div></div>`;
}}

function _wplRenderThesis(r) {{
  const th=r.thesis||{{}}, s=r.summary||{{}}, rs=r.rs||{{}}, adr=r.adr||{{}}, tr=r.trend||{{}}, con=r.consolidation||{{}};
  const cats=(th.catalysts||[]).map(c=>`<li>${{c}}</li>`).join('');
  document.getElementById('wplDThesis').innerHTML = `
    <div style="font-size:.88em;font-weight:700;margin-bottom:4px">${{th.action_label||''}}</div>
    <div style="color:#8b949e;margin-bottom:10px">${{th.summary||'—'}}</div>
    <div class="wpl-plan-grid">
      ${{_wplPI('Entry (Breakout)','₹'+_wplFmt(th.entry_breakout,2))}}
      ${{_wplPI('Entry (Pullback)','₹'+_wplFmt(th.entry_pullback,2))}}
      ${{_wplPI('Stop Loss','₹'+_wplFmt(th.stop_loss,2)+' (-'+_wplFmt(th.risk_pct,1)+'%)')}}
      ${{_wplPI('T1 (1.5R)','₹'+_wplFmt(th.target1,2))}}
      ${{_wplPI('T2 (2.5R)','₹'+_wplFmt(th.target2,2))}}
      ${{_wplPI('T3 (4R)','₹'+_wplFmt(th.target3,2))}}
      ${{_wplPI('R:R T1/T2',_wplFmt(th.rr_t1,1)+':1 / '+_wplFmt(th.rr_t2,1)+':1')}}
      ${{_wplPI('RS Score',(rs.rs_score||'—')+'/99 — '+(rs.rs_label||''))}}
      ${{_wplPI('ADR%',_wplFmt(adr.adr_pct,1,'%')+' — '+(adr.adr_label||''))}}
      ${{_wplPI('Stage',tr.stage_label||'—')}}
      ${{_wplPI('MA50','₹'+_wplFmt(tr.ma50,2)+(tr.above_ma50?' ✅':' ❌'))}}
      ${{_wplPI('MA200','₹'+_wplFmt(tr.ma200,2)+(tr.above_ma200?' ✅':' ❌'))}}
      ${{_wplPI('From 52W High',_wplFmt(tr.pct_from_52w_high,1,'%'))}}
      ${{_wplPI('Conviction',(th.conviction_score||'—')+'/100')}}
      ${{_wplPI('Setup',( th.setup_type||'—').replace(/_/g,' '))}}
      ${{_wplPI('Pos Size (1% risk ₹10L)',(th.shares_1pct_risk_1M_capital||'—')+' sh')}}
    </div>
    ${{cats?'<div style="margin-top:8px;font-size:.8em;color:#8b949e"><b style="color:#c9d1d9">Catalysts:</b><ul style="padding-left:14px;margin-top:2px">'+cats+'</ul></div>':''}}
  `;
}}

function _wplRenderPattern(r) {{
  const pat=r.pattern||{{}};
  const checks=Object.entries(pat.pattern_checks||{{}}).map(([k,v])=>
    `<li class="wpl-chk"><span style="color:${{v?'#4ade80':'#f87171'}}">${{v?'✅':'❌'}}</span>${{k.replace(/_/g,' ')}}</li>`
  ).join('');
  const sigs=(pat.signals||[]).map(s=>`<li>${{s}}</li>`).join('');
  document.getElementById('wplDPattern').innerHTML = `
    <div style="font-size:.9em;font-weight:700;color:${{pat.pattern_color||'#8b949e'}};margin-bottom:6px">${{pat.pattern_label||'—'}} &nbsp; Score: ${{pat.pattern_score||0}}/100</div>
    <div style="height:6px;background:#21262d;border-radius:3px;max-width:240px;overflow:hidden;margin-bottom:10px">
      <div style="height:100%;border-radius:3px;background:${{pat.pattern_color||'#8b949e'}};width:${{pat.pattern_score||0}}%"></div></div>
    ${{checks?'<div style="font-size:.78em;font-weight:600;color:#8b949e;margin-bottom:5px">Checklist</div><ul class="wpl-checklist">'+checks+'</ul>':''}}
    ${{sigs?'<div style="font-size:.78em;font-weight:600;color:#8b949e;margin:8px 0 4px">Signals</div><ul style="padding-left:14px;font-size:.8em;color:#8b949e;line-height:1.8">'+sigs+'</ul>':''}}
  `;
}}

function _wplRenderFund(r) {{
  const f=r.fundamentals||{{}};
  if (f.error) {{document.getElementById('wplDFund').innerHTML=`<div class="wpl-error">${{f.error}}</div>`; return;}}
  const items=[['Company',f.company_name||'—'],['Sector',f.sector||'—'],['Market Cap',f.mcap_label||'—'],
    ['P/E',_wplFmt(f.pe_ratio,1)],['ROE%',_wplFmt(f.roe_pct,1,'%')],['D/E',_wplFmt(f.debt_to_equity,2)],
    ['EPS TTM',_wplFmt(f.eps_ttm,2)],['EPS QoQ',f.eps_qoq_pct!=null?(f.eps_qoq_pct>=0?'+':'')+_wplFmt(f.eps_qoq_pct,1,'%'):'—'],
    ['Rev YoY',f.revenue_yoy_pct!=null?(f.revenue_yoy_pct>=0?'+':'')+_wplFmt(f.revenue_yoy_pct,1,'%'):'—'],
    ['Debt Trend',f.debt_trend||'—'],['Earnings Quality',f.earnings_quality||'—']];
  document.getElementById('wplDFund').innerHTML = `<div class="wpl-plan-grid">`+
    items.map(([l,v])=>`<div class="wpl-plan-item"><div class="wpl-plan-label">${{l}}</div><div class="wpl-plan-value" style="color:${{String(v).startsWith('+')?'#4ade80':String(v).startsWith('-')?'#f87171':'#c9d1d9'}}">${{v}}</div></div>`).join('')+'</div>';
}}

function _wplRenderMF(r) {{
  const mf=r.mf_holdings||{{}};
  if (mf.error) {{document.getElementById('wplDMF').innerHTML=`<div class="wpl-error">${{mf.error}}</div>`; return;}}
  const sc=mf.smart_money_signal||'UNKNOWN';
  const sc_c={{ACCUMULATING:'#4ade80',DISTRIBUTING:'#f87171',NEUTRAL:'#94a3b8'}}[sc]||'#8b949e';
  const ti=t=>t==='up'?'↑':t==='down'?'↓':'→';
  const tc=t=>t==='up'?'#4ade80':t==='down'?'#f87171':'#8b949e';
  document.getElementById('wplDMF').innerHTML = `
    <div style="font-size:.88em;font-weight:700;color:${{sc_c}};margin-bottom:6px">Signal: ${{sc}}</div>
    <div style="color:#8b949e;margin-bottom:8px;font-size:.8em">${{mf.swing_signal||mf.summary||'—'}}</div>
    <div class="wpl-plan-grid">
      <div class="wpl-plan-item"><div class="wpl-plan-label">Promoters</div><div class="wpl-plan-value">${{_wplFmt(mf.promoters_pct,1,'%')}} ${{ti(mf.promoters_trend)}}</div></div>
      <div class="wpl-plan-item"><div class="wpl-plan-label">FII%</div><div class="wpl-plan-value" style="color:${{tc(mf.fii_trend)}}">${{_wplFmt(mf.fii_pct,1,'%')}} ${{ti(mf.fii_trend)}}</div></div>
      <div class="wpl-plan-item"><div class="wpl-plan-label">DII%</div><div class="wpl-plan-value" style="color:${{tc(mf.dii_trend)}}">${{_wplFmt(mf.dii_pct,1,'%')}} ${{ti(mf.dii_trend)}}</div></div>
      <div class="wpl-plan-item"><div class="wpl-plan-label">DII Accum</div><div class="wpl-plan-value" style="color:${{mf.dii_accumulating?'#4ade80':'#f87171'}}">${{mf.dii_accumulating?'✅ YES':'❌ NO'}}</div></div>
    </div>`;
}}

function _wplRenderNews(r) {{
  const news=r.news||[];
  if (!news.length) {{document.getElementById('wplDNews').innerHTML='<div style="color:#8b949e">No news found.</div>'; return;}}
  document.getElementById('wplDNews').innerHTML = '<ul class="wpl-news-list">'+
    news.map(n=>`<li class="wpl-news-item">
      ${{n.link?`<a class="wpl-news-a" href="${{n.link}}" target="_blank" rel="noopener">${{n.title||'—'}}</a>`:(n.title||'—')}}
      <div class="wpl-news-meta">${{n.source||''}} · ${{n.date||''}}</div>
    </li>`).join('')+'</ul>';
}}

function _wplRenderPhasesBehav(r) {{
  const pb=(r.pattern||{{}}).phase_behavior||[];
  if (!pb.length) {{document.getElementById('wplDPhases').innerHTML='<div style="color:#8b949e">No phase data.</div>'; return;}}
  const rows=pb.map(p=>{{
    const pc=p.phase==='decline'?'wpl-phase-decline':p.phase==='recovery'?'wpl-phase-recovery':'wpl-phase-consolidation';
    return `<tr>
      <td><span class="wpl-phase-pill ${{pc}}" style="font-size:.65em">${{p.phase.toUpperCase()}}</span></td>
      <td style="font-size:.75em">${{p.start_date}}</td><td style="font-size:.75em">${{p.end_date}}</td>
      <td style="color:${{p.market_chg_pct>=0?'#4ade80':'#f87171'}};font-weight:700">${{p.market_chg_pct>=0?'+':''}}${{_wplFmt(p.market_chg_pct,1)}}%</td>
      <td style="color:${{p.stock_chg_pct>=0?'#4ade80':'#f87171'}};font-weight:700">${{p.stock_chg_pct>=0?'+':''}}${{_wplFmt(p.stock_chg_pct,1)}}%</td>
      <td style="color:${{p.excess_pct>=0?'#4ade80':'#f87171'}};font-weight:700">${{p.excess_pct>=0?'+':''}}${{_wplFmt(p.excess_pct,1)}}%</td>
      <td style="font-size:.72em;color:#8b949e">${{p.quality||''}}</td>
    </tr>`;
  }}).join('');
  document.getElementById('wplDPhases').innerHTML = `
    <table class="wpl-phase-tbl">
      <thead><tr><th>Phase</th><th>Start</th><th>End</th><th>Nifty</th><th>Stock</th><th>Excess RS</th><th>Behavior</th></tr></thead>
      <tbody>${{rows}}</tbody>
    </table>
    <div style="margin-top:8px;font-size:.72em;color:#475569">Excess RS = Stock − Market. Positive during declines = RS Leader.</div>`;
}}

function wplExportCSV() {{
  if (!_wplTable.length) return;
  const h=['Symbol','Price','20d%','60d%','RS','ADR%','Stage','Pattern','Conviction','Action','Entry','Stop','T1','R:R','Setup'];
  const rows=_wplTable.map(r=>[r.symbol,r.price,r.ret_20d,r.ret_60d,r.rs_score,r.adr_pct,r.stage,
    (r.pattern||'').replace(/[^\\w\\s]/g,''),r.conviction,r.action,r.entry,r.stop,r.t1,r.rr_t1,r.setup
  ].map(v=>v==null?'':String(v)).join(','));
  const a=document.createElement('a');
  a.href='data:text/csv;charset=utf-8,'+encodeURIComponent([h.join(','),...rows].join('\\n'));
  a.download='wpl_'+new Date().toISOString().slice(0,10)+'.csv';
  a.click();
}}

// Auto-load symbols from page on DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {{ wplLoadFromPage(); }});
</script>

<div class="main">
  <div class="signals-grid" id="signalsGrid">
    {rows_str}
  </div>
  <div class="no-results" id="noResults" style="display:none">No signals match your filters.</div>
</div>

<script>
let activeSector = '';
let activeIndustry = '';
let sortMode = 'score';

function applyFilters() {{
  const q        = document.getElementById('searchBox').value.toLowerCase();
  const setup    = document.getElementById('setupFilter').value;
  const rating   = document.getElementById('ratingFilter').value;
  const appear   = document.getElementById('appearFilter').value;
  const industry = document.getElementById('industryFilter').value || activeIndustry;
  let visible = 0;
  document.querySelectorAll('.sig-card').forEach(card => {{
    const sym    = (card.dataset.symbol||'').toLowerCase();
    const sec    = (card.dataset.sector||'').toLowerCase();
    const ind    = (card.dataset.industry||'').toLowerCase();
    const csetup = card.dataset.setup||'';
    const crate  = card.dataset.rating||'';
    const capp   = parseInt(card.dataset.appear||'0', 10);
    const ctotal = parseInt(card.dataset.appearTotal||'0', 10);
    let show = (sym.includes(q) || sec.includes(q) || ind.includes(q));
    // Multi-setup: data-setup is pipe-separated (e.g. "VCP|RANGE_EXPANSION")
    if(setup && !csetup.split('|').includes(setup)) show = false;
    if(rating === 'A+' && crate !== 'A+') show = false;
    if(rating === 'A'  && crate !== 'A+' && crate !== 'A') show = false;
    if(rating === 'B'  && crate === 'C') show = false;
    if(activeSector && (card.dataset.sector||'') !== activeSector) show = false;
    // Case-insensitive industry match to handle any encoding edge cases
    if(industry && ind !== industry.toLowerCase()) show = false;
    if(appear) {{
      if(appear === 'high'  && capp < 15) show = false;
      if(appear === 'warm'  && capp < 8)  show = false;
      if(appear === '50'    && ctotal > 0 && capp / ctotal < 0.5) show = false;
      if(appear === '75'    && ctotal > 0 && capp / ctotal < 0.75) show = false;
    }}
    card.style.display = show ? '' : 'none';
    if(show) visible++;
  }});
  document.getElementById('filterCount').textContent = visible + ' shown';
  document.getElementById('noResults').style.display = visible === 0 ? '' : 'none';
}}

function filterSector(sec) {{
  activeSector = sec;
  activeIndustry = '';
  document.getElementById('industryFilter').value = '';
  document.querySelectorAll('.sector-pill').forEach(p => p.classList.remove('active'));
  const pills = document.querySelectorAll('.sector-pill');
  pills.forEach(p => {{ if(p.onclick.toString().includes("'" + sec + "'") || (sec==='' && p.onclick.toString().includes("''"))) p.classList.add('active'); }});
  applyFilters();
}}

function filterIndustry(ind) {{
  activeIndustry = ind;
  activeSector = '';
  document.querySelectorAll('.sector-pill').forEach(p => p.classList.remove('active'));
  const sel = document.getElementById('industryFilter');
  if(sel) sel.value = ind;
  applyFilters();
}}

function resetAllFilters() {{
  activeSector = ''; activeIndustry = '';
  document.getElementById('searchBox').value = '';
  document.getElementById('setupFilter').value = '';
  document.getElementById('ratingFilter').value = '';
  document.getElementById('industryFilter').value = '';
  document.getElementById('appearFilter').value = '';
  document.querySelectorAll('.sector-pill').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.sector-pill')[0]?.classList.add('active');
  applyFilters();
}}

function toggleIndPanel() {{
  const panel = document.getElementById('indPanel');
  const btn   = document.getElementById('indToggleBtn');
  if (!panel) return;
  const collapsed = panel.classList.toggle('collapsed');
  btn.textContent = collapsed ? '▼ Expand' : '▲ Collapse';
}}

function toggleSort(mode) {{
  sortMode = mode;
  const grid = document.getElementById('signalsGrid');
  const cards = [...grid.querySelectorAll('.sig-card')];
  cards.sort((a, b) => {{
    if(mode === 'symbol') return (a.dataset.symbol||'').localeCompare(b.dataset.symbol||'');
    if(mode === 'appear') return parseInt(b.dataset.appear||'0',10) - parseInt(a.dataset.appear||'0',10);
    return 0; // score order is default DOM order
  }});
  cards.forEach(c => grid.appendChild(c));
  document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
  const btnMap = {{'score':'btn-sort-score','symbol':'btn-sort-sym','appear':'btn-sort-appear'}};
  const btnId = btnMap[mode];
  if(btnId) document.getElementById(btnId)?.classList.add('active');
}}

function exportCSV() {{
  const rows = [['Symbol','Sector','Setup','Rating','Entry','Stop','Shares','Regime','RS3M','RS6M','VolPct','RExp','1W%','1M%','3M%','6M%','SeenRuns','TotalRuns','EPSGrowth','DebtChange','MacroTrigger','MarketTrigger','FundSummary']];
  document.querySelectorAll('.sig-card').forEach(card => {{
    if(card.style.display === 'none') return;
    const planVals = [...card.querySelectorAll('.plan-value')].map(v => v.textContent.replace(/[₹,]/g,'').trim());
    const stats = [...card.querySelectorAll('.sig-stat span:last-child')].map(v => v.textContent.trim());
    const perfCells = [...card.querySelectorAll('.perf-cell')];
    const p1w = perfCells[0]?.querySelector('span:last-child')?.textContent?.trim() || '';
    const p1m = perfCells[1]?.querySelector('span:last-child')?.textContent?.trim() || '';
    const p3m = perfCells[2]?.querySelector('span:last-child')?.textContent?.trim() || '';
    const p6m = perfCells[3]?.querySelector('span:last-child')?.textContent?.trim() || '';
    const seenRuns   = card.dataset.appear || '0';
    const totalRuns  = card.dataset.appearTotal || '0';
    const epsGrowth    = card.querySelector('.insight-item:nth-child(1) .insight-value')?.textContent?.trim() || '';
    const debtChange   = card.querySelector('.insight-item:nth-child(2) .insight-value')?.textContent?.trim() || '';
    const macroTrigger = card.querySelector('.insight-item:nth-child(3) .insight-pill')?.textContent?.trim() || '';
    const marketTrigger= card.querySelector('.insight-item:nth-child(4) .insight-pill')?.textContent?.trim() || '';
    const fundSummary = card.querySelector('.insight-summary')?.textContent?.trim() || '';
    rows.push([
      card.dataset.symbol,
      card.dataset.sector,
      card.dataset.setup,
      card.dataset.rating,
      planVals[0] || '',
      planVals[1] || '',
      planVals[2] || '',
      stats[0] || '',
      stats[1] || '',
      stats[2] || '',
      stats[3] || '',
      stats[4] || '',
      p1w, p1m, p3m, p6m,
      seenRuns, totalRuns,
      epsGrowth,
      debtChange,
      macroTrigger,
      marketTrigger,
      fundSummary,
    ]);
  }});
  const csv = rows.map(r => r.map(v => '"'+String(v)+'"').join(',')).join('\\n');
  const a = document.createElement('a');
  a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
  a.download = 'trade_plans_' + new Date().toISOString().slice(0,10) + '.csv';
  a.click();
}}

// Initial count
document.addEventListener('DOMContentLoaded', () => {{
  document.getElementById('filterCount').textContent = '{total} shown';
}});
</script>
</body>
</html>"""

def _fetch_mf_holdings_for_signals(signals: list[dict]) -> None:
    """Batch-fetch MF/institutional holdings and inject _mf_context into each signal."""
    if not _MF_AVAILABLE or not signals:
        return
    india_signals = [s for s in signals if
                     str(s.get("symbol","")).endswith(".NS") or str(s.get("symbol","")).endswith(".BO")
                     or not str(s.get("symbol","")).isascii()]
    symbols = list({s["symbol"] for s in india_signals if s.get("symbol")})
    if not symbols:
        return

    print(f"  Fetching MF/institutional holdings for {len(symbols)} symbols…", flush=True)
    try:
        provider = MutualFundsProvider(cache_dir=str(CACHE_DIR), cache_ttl_hours=6)
        raw = provider.fetch_batch(symbols, market="india", workers=2)
        sym_map = {s: raw.get(s, {}) for s in symbols}
        for sig in signals:
            sym = sig.get("symbol", "")
            if sym in sym_map:
                sig["_mf_context"] = mf_swing_context(sym_map[sym])
    except Exception as e:
        print(f"  Warning: MF holdings fetch failed: {e}", flush=True)


def main():
    print("Generating Trade Plans page...")
    signals = load_signals()
    print(f"  Loaded {len(signals)} unique signals")

    # ── Record this run in history (for appearance tracking)
    print(f"  Updating run history ({RUN_HISTORY_MAX}-run window)…")
    run_history = update_run_history(signals)
    print(f"  Run history: {len(run_history.get('runs', []))} stored runs")

    hstats = hydrate_missing_fundamentals(signals)
    if hstats.get("needs_fundamentals", 0) > 0:
        print(
            "  Fundamentals hydration: "
            f"needed={hstats.get('needs_fundamentals', 0)} "
            f"summary+={hstats.get('fund_summary_filled', 0)} "
            f"eps+={hstats.get('earnings_filled', 0)} "
            f"debt+={hstats.get('debt_filled', 0)}"
        )
        if not hstats.get("yfinance_available", False):
            print("  Warning: fundamentals provider unavailable (install yfinance)")
        if hstats.get("still_missing_summary", 0) > 0 or hstats.get("still_missing_earnings", 0) > 0:
            print(
                "  Remaining missing fundamentals: "
                f"summary={hstats.get('still_missing_summary', 0)} "
                f"eps={hstats.get('still_missing_earnings', 0)} "
                f"debt={hstats.get('still_missing_debt', 0)}"
            )

    # Fetch MF/institutional holdings (Screener.in + yfinance, 6h cache)
    _fetch_mf_holdings_for_signals(signals)

    html = build_html(signals, run_history=run_history)
    out = OUTPUT / "trade_plans_live.html"
    out.write_text(html, encoding="utf-8")
    size = out.stat().st_size / 1024
    print(f"  Output: {out}")
    print(f"  Size: {size:.1f} KB")


if __name__ == "__main__":
    main()

