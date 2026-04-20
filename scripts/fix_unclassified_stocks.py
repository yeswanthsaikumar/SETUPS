#!/usr/bin/env python3
"""
fix_unclassified_stocks.py
──────────────────────────
Manually classify the ~1120 stocks that couldn't be auto-classified.
Uses a comprehensive hand-curated mapping plus enhanced name heuristics.
"""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY_CSV = ROOT / "data" / "nse_stock_taxonomy.csv"

# ── Comprehensive manual classification for well-known stocks ────────────
# Format: TICKER -> (sector, industry)
MANUAL_MAP: dict[str, tuple[str, str]] = {
    # Cement
    "ACC": ("Cement", "Cement"),
    "DALBHARAT": ("Cement", "Cement"),
    "ORIENTCEM": ("Cement", "Cement"),
    "SAGCEM": ("Cement", "Cement"),
    "SHREDIGCEM": ("Cement", "Cement"),
    "DECCANCE": ("Cement", "Cement"),
    "20MICRONS": ("Chemicals", "Specialty Minerals"),

    # Auto & Ancillaries
    "BALKRISHNA": ("Auto", "Tyres"),
    "BOSCHLTD": ("Auto", "Auto Ancillaries"),
    "FMGOETZE": ("Auto", "Auto Ancillaries"),
    "FIEMIND": ("Auto", "Auto Ancillaries"),
    "IMPAL": ("Auto", "Auto Ancillaries"),
    "NRBBEARING": ("Auto", "Bearings"),
    "ROLEXRINGS": ("Auto", "Bearings"),
    "SKFINDUS": ("Auto", "Bearings"),
    "SUNDRMBRAK": ("Auto", "Auto Ancillaries"),
    "STUDDS": ("Auto", "Auto Ancillaries"),
    "DIVGIITTS": ("Auto", "Auto Ancillaries"),
    "MANBA": ("Auto", "Auto Ancillaries"),
    "SHARDAMOTR": ("Auto", "Auto Ancillaries"),
    "RAJRATAN": ("Auto", "Auto Ancillaries"),
    "JAYNECOIND": ("Auto", "Auto Ancillaries"),
    "PPAP": ("Auto", "Auto Ancillaries"),
    "MAZDA": ("Auto", "Auto Ancillaries"),
    "MUNJALAU": ("Auto", "Auto Ancillaries - 2W"),
    "MUNJALSHOW": ("Auto", "Auto Ancillaries - 2W"),
    "OLAELEC": ("Auto", "EV"),
    "KROSS": ("Auto", "Auto Ancillaries"),

    # IT / Tech
    "CIGNITITEC": ("IT", "IT Services"),
    "KSOLVES": ("IT", "IT Services"),
    "RSYSTEMS": ("IT", "IT Services"),
    "INFOBEAN": ("IT", "IT Services"),
    "MINDTECK": ("IT", "IT Services"),
    "ONWARDTEC": ("IT", "IT Services"),
    "RAMCOSYS": ("IT", "IT Services"),
    "SUBEXLTD": ("IT", "IT Services"),
    "CALSOFT": ("IT", "IT Services"),
    "COMPUSOFT": ("IT", "IT Services"),
    "EXCELSOFT": ("IT", "IT Services"),
    "KELLTONTEC": ("IT", "IT Services"),
    "TERASOFT": ("IT", "IT Services"),
    "SOFTTECH": ("IT", "IT Services"),
    "PALREDTEC": ("IT", "IT Services"),
    "DRCSYSTEMS": ("IT", "IT Services"),
    "EMUDHRA": ("IT", "IT Security"),
    "FRACTAL": ("IT", "IT - Analytics"),
    "CAPILLARY": ("IT", "IT - SaaS"),
    "ALGOQUANT": ("IT", "IT - Fintech"),
    "RPTECH": ("IT", "IT Distribution"),
    "REDINGTON": ("IT", "IT Distribution"),
    "SYSTMTXC": ("IT", "IT Services"),
    "IVALUE": ("IT", "IT Distribution"),
    "GVPTECH": ("IT", "IT Services"),
    "DOLATALGO": ("IT", "IT - Fintech"),
    "FIRSTCRY": ("IT", "E-Commerce"),
    "MEESHO": ("IT", "E-Commerce"),
    "CCAVENUE": ("IT", "IT - Fintech"),
    "IKS": ("IT", "IT Services"),
    "DIGITIDE": ("IT", "IT Services"),
    "DIGIDRIVE": ("IT", "IT Services"),
    "DIGISPICE": ("IT", "IT Services"),

    # Financials / NBFC / Insurance
    "PIRAMALFIN": ("Financials", "NBFC"),
    "HDBFS": ("Financials", "NBFC"),
    "EDELWEISS": ("Financials", "NBFC"),
    "MASFIN": ("Financials", "NBFC"),
    "AFSL": ("Financials", "NBFC"),
    "ARMANFIN": ("Financials", "NBFC"),
    "CSLFINANCE": ("Financials", "NBFC"),
    "FEDFINA": ("Financials", "NBFC"),
    "FINOPB": ("Financials", "Payments"),
    "POONAWALLA": ("Financials", "NBFC"),
    "INDOSTAR": ("Financials", "NBFC"),
    "MONEYBOXX": ("Financials", "NBFC"),
    "PAISALO": ("Financials", "NBFC"),
    "NBIFIN": ("Financials", "NBFC"),
    "CUB": ("Banking", "Private Banks"),
    "IDBI": ("Banking", "PSU Banks"),
    "IFCI": ("Financials", "DFI"),
    "PFS": ("Financials", "NBFC - Infra"),
    "RELIGARE": ("Financials", "Diversified Financial"),
    "SBICARD": ("Financials", "Credit Cards"),
    "ICICIAMC": ("Financials", "Asset Management"),
    "ICICIPRULI": ("Financials", "Life Insurance"),
    "IEX": ("Financials", "Exchange"),
    "JIOFIN": ("Financials", "Diversified Financial"),
    "IIFLCAPS": ("Financials", "Capital Markets"),
    "DAMCAPITAL": ("Financials", "Capital Markets"),
    "SHAREINDIA": ("Financials", "Stock Broking"),
    "GICHSGFIN": ("Financials", "Housing Finance"),
    "PNBGILTS": ("Financials", "Gilts"),
    "MOTOGENFIN": ("Financials", "NBFC"),
    "MUFIN": ("Financials", "NBFC"),
    "MUTHOOTMF": ("Financials", "NBFC - Microfinance"),
    "NORTHARC": ("Financials", "NBFC"),
    "FIVESTAR": ("Financials", "NBFC"),
    "NIVABUPA": ("Financials", "Health Insurance"),
    "63MOONS": ("Financials", "Fintech"),
    "SECMARK": ("Financials", "Compliance Tech"),
    "BFINVEST": ("Financials", "Investment Holding"),
    "PILANIINVS": ("Financials", "Investment Holding"),
    "BAJAJHLDNG": ("Financials", "Investment Holding"),
    "RANEHOLDIN": ("Financials", "Investment Holding"),
    "INDNIPPON": ("Financials", "Asset Management"),
    "HYBRIDFIN": ("Financials", "NBFC"),

    # Pharma / Healthcare
    "AARTIPHARM": ("Pharma", "Pharma API"),
    "ADVENZYMES": ("Pharma", "Enzymes"),
    "HESTERBIO": ("Pharma", "Veterinary Pharma"),
    "GUFICBIO": ("Pharma", "Pharma Formulations"),
    "PANACEABIO": ("Pharma", "Pharma API"),
    "CONCORDBIO": ("Pharma", "Pharma API"),
    "NATHBIOGEN": ("Pharma", "Biotech"),
    "SYNGENE": ("Pharma", "CRAMS"),
    "FDC": ("Pharma", "Pharma Formulations"),
    "KILITCH": ("Pharma", "Pharma Formulations"),
    "NECLIFE": ("Pharma", "Pharma Formulations"),
    "ANUHPHR": ("Pharma", "Pharma Formulations"),
    "SANOFICONR": ("Pharma", "Pharma MNC"),
    "ALBERTDAVD": ("Pharma", "Pharma Formulations"),
    "AMRUTANJAN": ("Pharma", "OTC Pharma"),
    "BAJAJHCARE": ("Pharma", "OTC Pharma"),
    "BAYERCROP": ("Chemicals", "Agrochemicals"),
    "GAUDIUMIVF": ("Pharma", "Hospitals - IVF"),
    "ARTEMISMED": ("Pharma", "Hospitals"),
    "PARKHOSPS": ("Pharma", "Hospitals"),
    "SHALBY": ("Pharma", "Hospitals"),
    "NEPHROPLUS": ("Pharma", "Dialysis"),
    "NURECA": ("Pharma", "Medical Devices"),
    "TARSONS": ("Pharma", "Lab Equipment"),
    "SIGACHI": ("Pharma", "Pharma Excipients"),
    "KREBSBIO": ("Pharma", "Biotech"),
    "SANSTAR": ("Pharma", "Pharma Excipients"),

    # Energy / Power
    "INOXGREEN": ("Energy", "Renewable Energy"),
    "NTPCGREEN": ("Energy", "Renewable Energy"),
    "CLEANMAX": ("Energy", "Renewable Energy"),
    "RAIN": ("Energy", "Carbon & Petroleum Coke"),
    "AEGISVOPAK": ("Energy", "Oil & Gas - Storage"),
    "GULFPETRO": ("Energy", "Oil & Gas"),
    "CASTROLIND": ("Energy", "Lubricants"),
    "GOACARBON": ("Energy", "Carbon"),
    "PTC": ("Energy", "Power Trading"),
    "HUDCO": ("Financials", "DFI - Housing"),
    "INA": ("Energy", "Oil & Gas"),
    "CONFIPET": ("Energy", "Oil & Gas - Services"),
    "REFEX": ("Energy", "Power Trading"),
    "EXICOM": ("Energy", "EV Charging"),

    # Metals & Mining
    "IMFA": ("Metals", "Ferro Alloys"),
    "MAITHANALL": ("Metals", "Ferro Alloys"),
    "MUKANDLTD": ("Metals", "Steel - Specialty"),
    "RATNAVEER": ("Metals", "Steel"),
    "PRAKASHSTL": ("Metals", "Steel"),
    "SURAJLTD": ("Metals", "Steel - Tubes"),
    "MAHSEAMLES": ("Metals", "Steel - Tubes"),
    "RAJMET": ("Metals", "Steel"),
    "ASHOKAMET": ("Metals", "Non-Ferrous Metals"),
    "ASHAPURMIN": ("Metals", "Mining"),
    "NAVA": ("Metals", "Mining"),
    "HINDCOMPOS": ("Metals", "Composites"),
    "MOLDTECH": ("Cap Goods", "Tooling"),

    # Infrastructure / Construction
    "HCC": ("Infra", "Construction - EPC"),
    "SIMPLEXINF": ("Infra", "Construction - EPC"),
    "MONTECARLO": ("Infra", "Construction - EPC"),
    "CAPACITE": ("Infra", "Construction - Buildings"),
    "MADHUCON": ("Infra", "Construction - EPC"),
    "HECPROJECT": ("Infra", "Construction - EPC"),
    "SEPC": ("Infra", "Construction - EPC"),
    "RKEC": ("Infra", "Construction - EPC"),
    "EPACKPEB": ("Infra", "Pre-Engineered Buildings"),
    "GLOBECIVIL": ("Infra", "Construction - EPC"),
    "INTERARCH": ("Infra", "Pre-Engineered Buildings"),
    "NOIDATOLL": ("Infra", "Roads & Toll"),
    "BDL": ("Defence", "Aerospace & Defense"),
    "DREDGECORP": ("Infra", "Dredging"),
    "DBL": ("Infra", "Roads"),

    # Chemicals / Specialty Chemicals
    "TAINWALCHM": ("Chemicals", "Specialty Chemicals"),
    "KRONOX": ("Chemicals", "Specialty Chemicals"),
    "IONEXCHANG": ("Chemicals", "Water Treatment"),
    "SUDARCOLOR": ("Chemicals", "Paints & Coatings"),
    "CAMLINFINE": ("Chemicals", "Fine Chemicals"),
    "DICIND": ("Chemicals", "Specialty Chemicals"),
    "GSFC": ("Chemicals", "Fertilizers"),
    "ESTER": ("Chemicals", "Specialty Films"),
    "COSMOFIRST": ("Chemicals", "Specialty Films"),
    "KIRIINDUS": ("Chemicals", "Dyes & Pigments"),
    "LINDEINDIA": ("Chemicals", "Industrial Gases"),
    "ALKALI": ("Chemicals", "Chlor-Alkali"),
    "GULPOLY": ("Chemicals", "Polymers"),
    "NACLIND": ("Chemicals", "Chlor-Alkali"),
    "BLUEJET": ("Chemicals", "Specialty Chemicals"),
    "ROSSELLIND": ("Chemicals", "Specialty Chemicals"),
    "RUCHIRA": ("Chemicals", "Paper Chemicals"),
    "ELGIRUBCO": ("Chemicals", "Rubber"),
    "INDOBORAX": ("Chemicals", "Inorganic Chemicals"),
    "DEEPAKFERT": ("Chemicals", "Fertilizers"),
    "SPIC": ("Chemicals", "Fertilizers"),

    # FMCG / Consumer Staples
    "TASTYBITE": ("FMCG", "FMCG - Foods"),
    "EVEREADY": ("FMCG", "Batteries"),
    "PICCADIL": ("FMCG", "FMCG - Foods"),
    "PARAGMILK": ("FMCG", "FMCG - Dairy"),
    "STOVEKRAFT": ("FMCG", "Kitchen Appliances"),
    "BUTTERFLY": ("FMCG", "Kitchen Appliances"),
    "BBTC": ("FMCG", "FMCG - Beverages"),
    "AWFIS": ("Consumer", "Co-working Spaces"),
    "SUNDROP": ("FMCG", "FMCG - Edible Oil"),
    "SULA": ("FMCG", "Alcoholic Beverages"),

    # Consumer Discretionary
    "SAFARI": ("Consumer", "Luggage"),
    "GOCOLORS": ("Consumer", "Retail - Apparel"),
    "REDTAPE": ("Consumer", "Footwear"),
    "CANTABIL": ("Consumer", "Retail - Apparel"),
    "MUFTI": ("Consumer", "Retail - Apparel"),
    "FLAIR": ("Consumer", "Stationery"),
    "DOMS": ("Consumer", "Stationery"),
    "ETHOSLTD": ("Consumer", "Luxury - Watches"),
    "BLUESTONE": ("Consumer", "Retail - Jewellery"),
    "KALAMANDIR": ("Consumer", "Retail - Apparel"),
    "TBZ": ("Consumer", "Retail - Jewellery"),
    "DREAMFOLKS": ("Consumer", "Airport Lounges"),
    "MATRIMONY": ("Consumer", "Internet - Matchmaking"),
    "IMAGICAA": ("Consumer", "Theme Parks"),
    "ADVANIHOTR": ("Consumer", "Hotels"),
    "LEMONTREE": ("Consumer", "Hotels"),
    "SINGERIND": ("Consumer", "Consumer Durables"),
    "ORIENTHOT": ("Consumer", "Hotels"),
    "DEVX": ("Consumer", "Co-working Spaces"),
    "CUPID": ("Consumer", "Healthcare Products"),
    "FILATFASH": ("Consumer", "Retail - Apparel"),
    "BLACKBUCK": ("Logistics", "Fleet Tech"),

    # Electrical / Electronics
    "ELECON": ("Cap Goods", "Gears & Drives"),
    "EIMCOELECO": ("Cap Goods", "Electrical Equipment"),
    "PITTIENG": ("Cap Goods", "Electrical Equipment"),
    "STLNETWORK": ("Telecom", "Fiber & Cables"),
    "DIACABS": ("Cables", "Cables"),
    "PARACABLES": ("Cables", "Cables"),
    "PLAZACABLE": ("Cables", "Cables"),
    "BIRLACABLE": ("Cables", "Cables"),
    "DPWIRES": ("Cables", "Wires"),
    "BANSALWIRE": ("Cables", "Wires"),
    "BHARATWIRE": ("Cables", "Wires"),
    "GEEKAYWIRE": ("Cables", "Wires"),
    "IKIO": ("Electronics", "LED Lighting"),
    "SERVOTECH": ("Electronics", "LED & Solar"),
    "NELCO": ("Electronics", "Satellite Communication"),
    "AVANTEL": ("Electronics", "Defence Electronics"),
    "BLUESTARCO": ("Consumer", "Air Conditioning"),
    "NIPPOBATRY": ("Electronics", "Batteries"),
    "SALZERELEC": ("Cap Goods", "Electrical Equipment"),
    "BPL": ("Consumer", "Consumer Electronics"),
    "DEN": ("Media", "Cable TV"),

    # Cap Goods / Industrial
    "ADOR": ("Cap Goods", "Welding Equipment"),
    "INGR RAND": ("Cap Goods", "Compressors"),
    "LMW": ("Cap Goods", "Textile Machinery"),
    "BOROSCI": ("Cap Goods", "Glassware"),
    "TEGA": ("Cap Goods", "Mining Equipment"),
    "AEQUS": ("Cap Goods", "Aerospace Components"),
    "AJAXENGG": ("Cap Goods", "Industrial Equipment"),
    "SHAKTI PUMP": ("Cap Goods", "Pumps"),
    "IFBIND": ("Consumer", "Home Appliances"),
    "IFBAGRO": ("Agri", "Agri Equipment"),
    "HBLENGINE": ("Cap Goods", "Engines"),
    "CARYSIL": ("Consumer", "Kitchen & Bath"),
    "EUREKAFORB": ("Cap Goods", "Pharma Equipment"),
    "SWELECTES": ("Cap Goods", "Switchgear"),
    "ELECTCAST": ("Cap Goods", "Castings"),
    "INGERRAND": ("Cap Goods", "Compressors"),

    # Telecom
    "MTNL": ("Telecom", "Telecom - PSU"),
    "ITI": ("Telecom", "Telecom Equipment"),
    "TEJASNET": ("Telecom", "Telecom Equipment"),

    # Media
    "JAGRAN": ("Media", "Print Media"),
    "RADIOCITY": ("Media", "Radio"),
    "HMVL": ("Media", "Print Media"),
    "SANDESH": ("Media", "Print Media"),
    "SHEMAROO": ("Media", "Entertainment"),
    "DGCONTENT": ("Media", "Digital Media"),
    "ENIL": ("Media", "Radio"),

    # Real Estate
    "LODHA": ("RealEstate", "Real Estate - Residential"),
    "HUBTOWN": ("RealEstate", "Real Estate - Residential"),
    "MAXESTATES": ("RealEstate", "Real Estate - Commercial"),
    "RUSTOMJEE": ("RealEstate", "Real Estate - Residential"),
    "MARATHON": ("RealEstate", "Real Estate - Residential"),
    "ATALREAL": ("RealEstate", "Real Estate - Residential"),
    "INDIQUBE": ("RealEstate", "Real Estate - Commercial"),
    "ARKADE": ("RealEstate", "Real Estate - Residential"),
    "PURVA": ("RealEstate", "Real Estate - Residential"),
    "PARSVNATH": ("RealEstate", "Real Estate - Residential"),
    "TARC": ("RealEstate", "Real Estate - Residential"),
    "EMAMIREAL": ("RealEstate", "Real Estate - Residential"),

    # Textiles / Apparel
    "SUTLEJTEX": ("Textiles", "Yarn & Fiber"),
    "AYMSYNTEX": ("Textiles", "Synthetic Textiles"),
    "MARALOVER": ("Textiles", "Cotton Textiles"),
    "NAHARINDUS": ("Textiles", "Cotton Textiles"),
    "NAHARPOLY": ("Textiles", "Synthetic Textiles"),
    "EUROTEXIND": ("Textiles", "Home Textiles"),
    "PIONEEREMB": ("Textiles", "Embroidery"),
    "GHCLTEXTIL": ("Textiles", "Cotton Textiles"),
    "MODTHREAD": ("Textiles", "Thread"),
    "BANSWRAS": ("Textiles", "Synthetic Textiles"),

    # Packaging
    "TCPLPACK": ("Packaging", "Packaging - Containers"),
    "EPACK": ("Packaging", "Packaging"),
    "EMMVEE": ("Packaging", "Packaging"),
    "PEARLPOLY": ("Packaging", "Packaging - Films"),
    "SARLAPOLY": ("Packaging", "Packaging - Films"),
    "PAKKA": ("Packaging", "Packaging - Paper"),

    # Paper
    "ANDHRAPAP": ("Paper", "Paper"),
    "ORIENTPPR": ("Paper", "Paper"),
    "EMAMIPAP": ("Paper", "Paper"),

    # Logistics / Shipping
    "ESSARSHPNG": ("Shipping", "Shipping"),
    "SHADOWFAX": ("Logistics", "Last Mile Delivery"),
    "MARINE": ("Shipping", "Shipping"),

    # Agri
    "SARVESHWAR": ("Agri", "Rice"),
    "MUKKA": ("Agri", "Seafood"),
    "SAHYADRI": ("Agri", "Agri Products"),
    "GOPAL": ("Agri", "Agri Products"),
    "JOCIL": ("Agri", "Agri Products"),
    "AWL": ("Agri", "Agri - Warehousing"),
    "OSWALAGRO": ("Agri", "Agri Products"),

    # Building Materials
    "GREENPLY": ("Building Materials", "Plywood"),
    "GREENLAM": ("Building Materials", "Laminates"),
    "ARCHIDPLY": ("Building Materials", "Plywood"),
    "RUSHIL": ("Building Materials", "MDF Board"),
    "POKARNA": ("Building Materials", "Granite & Quartz"),
    "ORIENTCER": ("Building Materials", "Tiles"),
    "REGENCERAM": ("Building Materials", "Tiles"),
    "MURUDCERA": ("Building Materials", "Tiles"),
    "LAOPALA": ("Building Materials", "Glassware"),
    "SIRCA": ("Building Materials", "Wood Finishes"),

    # Cap Goods specific
    "MANINDS": ("Cap Goods", "Industrial Equipment"),
    "QPOWER": ("Energy", "Power Equipment"),  # <-- THE MISSING ONE!
    "CPPLUS": ("Electronics", "Security & Surveillance"),

    # Defence
    "KRISHNADEF": ("Defence", "Aerospace & Defense"),

    # Sugar
    "BANARISUG": ("FMCG", "Sugar"),
    "KCPSUGIND": ("FMCG", "Sugar"),
    "KOTARISUG": ("FMCG", "Sugar"),
    "RAJSREESUG": ("FMCG", "Sugar"),
    "RANASUG": ("FMCG", "Sugar"),
    "SAKHTISUG": ("FMCG", "Sugar"),
    "DAVANGERE": ("FMCG", "Sugar"),

    # Miscellaneous known
    "3IINFOLTD": ("Financials", "Investment Holding"),
    "ITDC": ("Consumer", "Hotels - PSU"),
    "STCINDIA": ("Trading", "Trading - PSU"),
    "EXCEL": ("Chemicals", "Specialty Chemicals"),
    "EXCELINDUS": ("Textiles", "Apparel Export"),
    "WIPRO": ("IT", "IT Services"),
    "ACC": ("Cement", "Cement"),
    "HLVLTD": ("FMCG", "FMCG - Personal Care"),
    "ASIANHOTNR": ("Consumer", "Hotels"),
    "ACE": ("Cap Goods", "Cranes"),
    "ACEINTEG": ("IT", "IT Services"),
    "21STCENMGM": ("Financials", "Asset Management"),
    "BALMLAWRIE": ("Packaging", "Packaging - Barrels"),
    "BEARDSELL": ("Building Materials", "Insulation"),
    "BELLACASA": ("Building Materials", "Tiles"),
    "GLOSTERLTD": ("Textiles", "Jute"),
    "GOODLUCK": ("Metals", "Steel"),
    "SINCLAIR": ("Consumer", "Hotels"),
    "KRYSTAL": ("Infra", "Construction - Buildings"),
    "ADL": ("Cap Goods", "Industrial Equipment"),
    "BOROLTD": ("Consumer", "Consumer Electronics"),
    "ASTRAMICRO": ("Electronics", "Electronic Components"),
    "BBL": ("FMCG", "Alcoholic Beverages"),
    "DCMSIL": ("Chemicals", "Silicone"),
    "FISCHER": ("Cap Goods", "Fasteners"),
    "GATEWAY": ("Logistics", "Logistics"),
    "GARFIBRES": ("Textiles", "Glass Fiber"),
    "GLOTTIS": ("IT", "IT Services"),
    "REPRO": ("Consumer", "Printing"),
    "MPSLTD": ("IT", "IT - BPO"),
}

# ── Enhanced name-based rules ───────────────────────────────────────────
ENHANCED_RULES: list[tuple[str, str, str]] = [
    # More specific patterns first
    (r"(?i)sugar|sug$", "FMCG", "Sugar"),
    (r"(?i)cement|cem$", "Cement", "Cement"),
    (r"(?i)steel|iron|foundry|forg|cast", "Metals", "Steel"),
    (r"(?i)alum", "Metals", "Non-Ferrous Metals"),
    (r"(?i)copper|zinc|brass|nickel", "Metals", "Non-Ferrous Metals"),
    (r"(?i)gold|silver|jewel|bullion|diamond|gem", "Consumer", "Gems & Jewellery"),
    (r"(?i)pharma|drug|lab|biotech|health|medic|diag|thera|oncol|lifesci", "Pharma", "Pharma"),
    (r"(?i)hospit", "Pharma", "Hospitals"),
    (r"(?i)bank|fin\b|finserv|nbfc|microf", "Financials", "NBFC"),
    (r"(?i)insur|assur", "Financials", "Insurance"),
    (r"(?i)hous.?fin|home.?fin|mortg", "Financials", "Housing Finance"),
    (r"(?i)capital|invest|hold|venture", "Financials", "Investment Holding"),
    (r"(?i)secur|broker", "Financials", "Stock Broking"),
    (r"(?i)mine|mining|mineral|ore\b", "Metals", "Mining"),
    (r"(?i)chem|petro.?chem|polymer|solvent|dye|pigment|resin", "Chemicals", "Chemicals"),
    (r"(?i)agro.?chem|fert|pesti|insect|seed", "Chemicals", "Agrochemicals"),
    (r"(?i)power|energy|electr|generat|transmis|renew|solar|wind|hydro", "Energy", "Power Generation"),
    (r"(?i)oil|gas|petrol|refin|lubric|crude", "Energy", "Oil & Gas"),
    (r"(?i)coal|lignite", "Energy", "Coal"),
    (r"(?i)auto|motor|vehic|tractor|wheel|tyre|tire|brake", "Auto", "Auto Ancillaries"),
    (r"(?i)infra|construct|engineer|road|highway|bridge|tunnel|rail|metro", "Infra", "Construction - Infra"),
    (r"(?i)real.?est|realty|hous|property|township|estate", "RealEstate", "Real Estate - Residential"),
    (r"(?i)hotel|hospit|tourism|travel|resort|leisure", "Consumer", "Hotels & Restaurants"),
    (r"(?i)textile|cotton|yarn|fabric|garment|apparel|silk|wool|denim|jute", "Textiles", "Textiles"),
    (r"(?i)food|dairy|edible|biscuit|confect|beverage|juice|tea|coffee", "FMCG", "FMCG - Foods"),
    (r"(?i)paper|pulp|print", "Paper", "Paper"),
    (r"(?i)packag", "Packaging", "Packaging"),
    (r"(?i)plast|pvc|pipe|tube", "Chemicals", "Plastics & Pipes"),
    (r"(?i)it\b|software|infotech|tech.?sol|digital|data|cloud|cyber|consult", "IT", "IT Services"),
    (r"(?i)telecom|comm.?net|fiber|broadband|tower|5g", "Telecom", "Telecom"),
    (r"(?i)media|entertain|film|broadcast|advertis|news|publish", "Media", "Media & Entertainment"),
    (r"(?i)retail|mart|store|shop|e.?comm", "Consumer", "Retail"),
    (r"(?i)logist|transport|freight|shipping|courier|cargo|port|warehous", "Logistics", "Logistics"),
    (r"(?i)defence|defens|weapon|ammo|missile|naval|armour", "Defence", "Aerospace & Defense"),
    (r"(?i)educat|learn|school|university|tutor|coach", "Consumer", "Education"),
    (r"(?i)ceramic|tile|sanit|glass|marble|granite", "Building Materials", "Building Materials"),
    (r"(?i)paint|coat|adhesive", "Chemicals", "Paints & Coatings"),
    (r"(?i)cable|wire\b", "Cables", "Cables & Wires"),
    (r"(?i)pump|valve|compress|seal", "Cap Goods", "Pumps & Valves"),
    (r"(?i)engg|engineer", "Cap Goods", "Engineering"),
    (r"(?i)crane|lift|hoist", "Cap Goods", "Material Handling"),
    (r"(?i)bearing", "Auto", "Bearings"),
    (r"(?i)rubber", "Chemicals", "Rubber"),
    (r"(?i)agri|farm|crop|rice|wheat|grain|spice|pulses", "Agri", "Agri Products"),
    (r"(?i)ply|plywood|board|laminate|mdf|veneer", "Building Materials", "Plywood & Boards"),
    (r"(?i)leather", "Consumer", "Leather"),
    (r"(?i)shoe|footwear|sandal", "Consumer", "Footwear"),
]


def apply_fixes():
    """Apply manual classifications and enhanced heuristics."""
    # Read current taxonomy
    rows = []
    with open(TAXONOMY_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    fixed = 0
    heuristic = 0

    for row in rows:
        ticker = row.get("nse_ticker", "").strip().upper()

        # 1. Apply manual mapping (overrides everything)
        if ticker in MANUAL_MAP:
            sector, industry = MANUAL_MAP[ticker]
            if row["sector"] == "Other" or row["industry"] == "Other":
                row["sector"] = sector
                row["industry"] = industry
                row["notes"] = "manual"
                fixed += 1
            continue

        # 2. Enhanced heuristics for still-unclassified
        if row.get("sector") == "Other" and row.get("industry") == "Other":
            for pattern, sector, industry in ENHANCED_RULES:
                if re.search(pattern, ticker):
                    row["sector"] = sector
                    row["industry"] = industry
                    row["notes"] = "auto:enhanced_heuristic"
                    heuristic += 1
                    break

    # Write back
    with open(TAXONOMY_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["nse_ticker", "sector", "industry", "notes"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    # Count remaining unclassified
    remaining = sum(1 for r in rows if r.get("sector") == "Other" and r.get("industry") == "Other")
    total = len(rows)
    classified = total - remaining

    print(f"Manual fixes applied: {fixed}")
    print(f"Heuristic fixes: {heuristic}")
    print(f"Remaining unclassified: {remaining} / {total}")
    print(f"Coverage: {classified}/{total} ({classified/total*100:.1f}%)")


if __name__ == "__main__":
    apply_fixes()

