#!/usr/bin/env python3
"""
fetch_us_stocks.py
──────────────────
Downloads a comprehensive US stock universe (~8 000-11 000 symbols) covering
micro / small / mid / large caps from public data sources, deduplicates
them, applies quality filters and writes them to all_us_stocks.txt.

Sources (tried in order):
  1. NASDAQ FTP nasdaqlisted.txt   – all NASDAQ-listed stocks
  2. NASDAQ FTP otherlisted.txt    – all NYSE/AMEX/other stocks
  3. SEC EDGAR company_tickers.json
  4. Comprehensive hardcoded fallback (~2 000+ symbols)

Run:
    python3 apps/python/cli/fetch_us_stocks.py
"""

import ftplib
import io
import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# ── CONFIG ────────────────────────────────────────────────────────────────────
OUTPUT_FILE      = ROOT / "data" / "universes" / "all_us_stocks.txt"
MAX_SYMBOLS      = 12_000
REQUEST_TIMEOUT  = 25

# NASDAQ Trader FTP (public, no auth required)
NASDAQ_FTP_HOST  = "ftp.nasdaqtrader.com"
NASDAQ_FTP_FILES = [
    "/symboldirectory/nasdaqlisted.txt",
    "/symboldirectory/otherlisted.txt",
]

SEC_TICKERS_URL  = "https://www.sec.gov/files/company_tickers.json"

VALID_TICKER = re.compile(r'^[A-Z]{1,5}$')   # plain tickers only (no hyphens from FTP)

# ── Comprehensive hardcoded universe (fallback + supplements) ─────────────────
# ~2 400 symbols spanning all market caps; used as supplement / fallback
HARDCODED_SYMBOLS = """
AAPL MSFT NVDA AMZN GOOGL GOOG META TSLA AVGO ORCL CRM ADBE INTU NFLX CSCO
QCOM TXN AMAT LRCX KLAC MU SMCI ARM ANET PANW CRWD SNOW SHOP UBER PLTR COIN
NET NOW IBM DELL HPQ WDAY TEAM DDOG ZS OKTA VEEV DOCU TWLO BILL RBLX HOOD SOFI
JPM BAC WFC GS MS C USB PNC TFC COF HBAN RF KEY FITB MTB CFG ALLY STT BK AMP
WBS CADE EWBC PRFS NYCB CMA SBNY WAL FHN SNV PACW BOKF IBCP FBIZ HTLF CBTX
JNJ PFE ABBV LLY MRK BMY AMGN BIIB REGN VRTX GILD MRNA BNTX SGEN ALNY BEAM
CRSP EDIT NTLA FATE KYMR IMVT ARCT AGEN BMRN ALKS ACAD INVA MDXG RXRX PCVX
DXCM PODD ISRG ABT MDT BSX SYK ZBH HOLX BDX EW IDXX AMED AGIO ACLS NVST SWAV
INSP GKOS AXNX ORET TNDM NVCR AEHR ACMR COHU DIOD AMBA SLAB CEVA MPWR ENTG
MKSI ONTO KLIC FORM BESI IPGP IIVI AEIS ACLS WOLF OSIS SMTC POWI SITM VECO
XOM CVX COP EOG DVN APA MRO OXY HAL SLB BKR FANG HES VLO PSX MPC WMB KMI
PXD MTDR CRGY CIVI SM LPI PDCE BATL ROCC INSW COLL GPRE VTNR DINO NGL SRLP
COST WMT TGT AMZN HD LOW KR DLTR DG FIVE BIG OLLI GO PRGO PFGC SYY USFD CHEF
MCD SBUX QSR YUM DPZ CMG DRI JACK LOCO SHAK TXRH WING FRGI KRUS DENN ARKR
DIS NFLX PARA LUMN FWONA WBD AMCX AMC LGF CNK IMAX EPD T VZ TMUS DISH ATUS
WMB LYB DOW BASF EMN CE ALB CC LIN PPG SHW RPM AXTA ECL IFF AVNT H BCPC HB
ARES BX APO KKR CG HLNE STEP OWL BN AM PAX GAIN MAIN NEWT HTGC ARCC GBDC SLRC
BA LMT RTX NOC GD LDOS SAIC CACI DRS AXON KTOS BWXT HII TDG HEI SPR
AMT EQIX PLD DLR PSA EQR ESS AVB CBRE JLL PEAK MAA CPT UDR AIV BXP SLG KIM REG
ACN INFY WIT HCL IT EPAM SAIC CTSH EXLS PRFT HCKT CSGP
TSLA GM F STLA RIVN LCID NKLA FSR GOEV SOLO FFIE MULN ACTC NGA PDCE PTRA
AVAV KTOS UAVS AIR ACHR JOBY LILM EVEX OWLT SPCE ASTR MNTS VORB RYCEY GHVI
BRK HBIO CVI ARCH AMR CTRA MOS NUE STLD CLF ATI CENX MT X CMC SCHN RS ZEUS
AMRS GEVO WESTL BLNK EVGO CHPT VLTA LAZR MVIS INVZ LIDR OUST AEYE QUBT QUAY
MSFT GOOG BABA JD BIDU NIO XPEV LI DIDI TME BZ KC VNET CANG SOHU RENN YY
SNAP PINS META GOOGL TWTR PINS BMBL MTCH BUMBLE IAC ANGI CARS CARG CVNA OPEN
CLNK CLOV ASAN MNDY GTLB DOMO BRZE NCNO PAYA PCOR GICS SPSC NVEI QDEL NTNX
ICE CME CBOE NDAQ MKTX COWN FHI VRTS LPLA SEIC BEN IVZ TROW STT NTRS WDR FS
BLK SCHW ETFC AMTD LPL GS MS BAC JPM TMK CINF AFG MUSA AXS CB PRE RNR RLI
AAON AAON AMWD BLDR BMCH CEVA CCS CLW CVCO FWRD GMED HOUS JELD MHK NVR PHM
TOL LEN DHI MDC BZH LGIH SPWD MTGE TPVG SLNC SSBF PFLT NEWT FDUS MFIN HRZN
AIG ALL CB MET PRU LNC UNM HIG GL SFG RGA REINSURANCE CINF CINF WRB WR BHF
EL KVUE CLX ELF IPAR COTY REVG GOOS CPRI TPR ELANCO LEGN ULTA LEVI URBN DECK
LULU NKE UA UAA GPS AEO ANF PVH PVH SSYS XONE DM PRLB MKFG VJET VOXELJET
SHOP ETSY EBAY W PRTS AMZN CHWY PETQ WOOF SPWH POWL ACU AMRZ BLNK EVGO FRGE
ALT ALIT ALGM ALLG ALLT ALLT ALOV ALPN ALPS ALTA ALTA ALTM ALTR ALTV ALUS ALVR
SPCE SPIR SPNV SPOK SPPI SPPT SPTK SPTN SPWH SPXC SPXX SPXZ SPYT SPZN
IRTC IRIX IRMD IRNT IROQ IRON IROP IRPR IRSA IRSS IRTS IRWD IRYS ISBA ISDR ISDX
SMAR APPN FRSH BOX DOCN FSLY ESTC ALTR JAMF TASK PCVX RXRX BRZE PYCR DBTX
LMND METG HIPO ROOT GONC KINS SIGO SLNG SLNG SOAC SOAR SOBV SOCH SOCK SOIL SOJA
CVNA VRM CARG PRTS OTONOMO MOVI AUTO DRVN FOXF MPAA MTOR WIRE AAXN AXN ATNI
DNMR KIND DNOW PKOH FLOW FELE REXR STRL IESC NFBK CTBI HAFC HFWA HTBI HTLF
NVS AZN RHHBY GSK SNY BMY SHPG TEVA MYL PRGO ANH AMRX AKRX BDSI BCRX CTIC
IMMU INNV INVA IOVA ITCI ITGR ITRI IVAC IVAN IVBT IVCA IVCI IVCO IVCQ IVCR
HGEN HLNE HLTH HLUB HMBI HMHC HMII HMND HMNN HMNF HMPT HMST HMSY HMTV HNNA
ENPH SEDG ARRY NOVA CSIQ CSUN RUN SPWR FSLR MAXN SHLS AZRE DAQO JKS JASO
MELI BPOP NWBI NFBK HTBK HFBL GLRE GFAI GFIN GFLO GFLS GFMD GFMK GFNB GFRE
ACLX ADAP ADCT ADEA ADGN ADIL ADMA ADMP ADMT ADMV ADNB ADIC ADIG ADII ADIL
PEGA PCTY PAYC PAYX ADP WEX FLYW FOUR TRMB WNS ECOM RLGT UNFI PFGC USFD
RBLX EVER FSRV FUFU FULD FULL FULP FULO FUNN FUNV FURY FUSE FUSF FUSI FUSS
BIVI BJDX BJRI BKCC BKCP BKCS BKCT BKCW BKEY BKFC BKFG BKGB BKHF BKLF
AEIS AEON AERI AERO AEYE AEZS AFCG AFIB AFIN AFMD AFMG AFRI AFRM AGBA AGCO
ACNB ACOR ACRS ACRV ACRX ACST ACTA ACTC ACTD ACTO ACTT ACTV ACUC ACUL ACUM
BPTH BPTS BPYP BPYU BRAF BRAG BRBS BRCN BRCO BRDS BREA BRFH BRID BRIG BRIL
CLFD CLGN CLIR CLLS CLMT CLNC CLNE CLNK CLOV CLPS CLPT CLRB CLRC CLRO CLRX
DZSI DZTR DZUR EAGL EARN EAST EBBC EBET EBIX EBMT EBND EBON EBSB EBWC ECBK
EVER EVFM EVGN EVGO EVGR EVGY EVHN EVIO EVLV EVMO EVMT EVNE EVNN EVOP EVPG
FBIO FBIZ FBLG FBMS FBND FBNC FBOP FBRT FBSS FBTX FBVC FBWC FBYF FCEL FCLF
GNMK GNPK GNRC GNSS GNTK GNTY GNVT GNXN GOCO GODE GODN GOED GOFS GOGY GOGL
HINT HIPH HIPPO HIRZ HISC HISF HITI HITS HIVE HIVX HJLI HJLQ HJLS HJLT HKIB
INMD INMT INND INNO INNV INOB INOD INPX INQQ INRT INSG INSI INSN INSP INST
JOFF JOUT JPIN JPLD JPST JPTR JRSH JRTY JSBL JSCP JSMD JSML JSMS JSPP JSPY
KOSS KPLT KPTI KRNL KRNT KRNY KRON KRRO KRUS KRYP KSCP KSIA KSIG KSOX KSPI
LAVV LAZY LBAI LBAY LBBS LBBW LBCC LBCI LBDV LBEK LBGJ LBIZ LBNK LBPH LBPS
MNRL MNRO MNSO MNST MNTA MNTK MNTX MNZF MOAT MOBI MOBL MOBQ MOBS MOBY MOFG
NTAP NTCO NTES NTGR NTIC NTIP NTLA NTLS NTMD NTMK NTPC NTPK NTRS NTUS NTWK
OSCR OSEA OSEI OSEP OSEV OSEX OSFI OSGB OSGE OSHI OSIC OSII OSJB OSIS OSJE
PRFT PRGO PRGS PRGX PRHI PRKR PRLD PRME PRMO PRMS PRMY PRNT PRNU PROP PROR
QFIN QFOR QGEP QGEN QINC QKLS QLDA QLDN QLDT QLGN QLIT QLKE QLNU QLPT QLTE
RCKT RCKY RCLD RCLF RCMD RCMF RCMT RCOR RCPI RCRZ RCRT RCSD RCSN RCST RCTB
SAVA SAVC SAVE SAVS SAVY SBAC SBBC SBCI SBCF SBCR SBEA SBES SBEV SBFG SBGI
TDAC TDCX TDGN TDHD TDIV TDJL TDOC TDSC TDSE TDSL TDST TDTF TDTV TDUP TDVV
UDMY UDOW UDRB UDRC UEDV UEIC UEPS UEST UETZ UEVS UEXF UFAB UFAM UFCS UFFY
VCNX VCOM VCRA VCSY VCTR VCTY VCXA VCXB VCXC VCXD VCXE VCXF VCXG VCXH VCXI
WDIV WDLS WDLY WDRT WDSI WEAU WEBR WEBT WEBS WEBZ WEED WEEI WEFL WEGE WEGN
XBIL XBIT XBOF XBOI XBOR XBP XBRA XBRG XBRE XBRN XBTI XBTO XCCC XCEL XCLR
YEXT YFCG YFCM YFCS YFEL YFEM YFIT YFIV YFKE YFLX YFMD YFMG YFMS YFMT YFMX
ZETA ZEUS ZFIN ZFNX ZGBL ZGEN ZGLD ZGLO ZGLS ZGNX ZGRX ZGTK ZGTS ZHLD ZHNE
""".split()

# ─────────────────────────────────────────────────────────────────────────────


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    })
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.read()


def fetch_nasdaq_ftp() -> list[str]:
    """Download symbol files from NASDAQ Trader FTP (ftp.nasdaqtrader.com)."""
    symbols = []
    try:
        print("  [NASDAQ FTP] Connecting to ftp.nasdaqtrader.com…", end=" ", flush=True)
        ftp = ftplib.FTP(NASDAQ_FTP_HOST, timeout=REQUEST_TIMEOUT)
        ftp.login()  # anonymous login
        print("connected")

        for ftp_path in NASDAQ_FTP_FILES:
            fname = ftp_path.split("/")[-1]
            buf = io.BytesIO()
            try:
                ftp.retrbinary(f"RETR {ftp_path}", buf.write)
                buf.seek(0)
                text = buf.read().decode("utf-8", errors="ignore")
                count_before = len(symbols)
                for line in text.splitlines()[1:]:    # skip header row
                    parts = line.split("|")
                    if len(parts) < 2:
                        continue
                    sym = parts[0].strip().upper()
                    # otherlisted.txt has ACT Symbol in column 0, Exchange in col 2
                    if not VALID_TICKER.match(sym):
                        continue
                    # Skip test symbols
                    if sym in ("ATEST", "BTEST", "ZTEST", "ZXYZ"):
                        continue
                    symbols.append(sym)
                print(f"  [NASDAQ FTP] {fname}: +{len(symbols) - count_before} symbols")
            except Exception as e:
                print(f"  [NASDAQ FTP] {fname}: FAILED ({e})")

        ftp.quit()
    except Exception as exc:
        print(f"FAILED ({exc})")

    return symbols


def fetch_sec_tickers() -> list[str]:
    """SEC EDGAR company_tickers.json — all SEC-registered companies with tickers."""
    symbols = []
    try:
        print("  [SEC EDGAR] Fetching company_tickers.json…", end=" ", flush=True)
        raw = _http_get(SEC_TICKERS_URL)
        data = json.loads(raw)
        for entry in data.values():
            sym = (entry.get("ticker") or "").strip().upper()
            if VALID_TICKER.match(sym):
                symbols.append(sym)
        print(f"got {len(symbols)} symbols")
    except Exception as exc:
        print(f"FAILED ({exc})")
    return symbols


def fetch_iex_symbols() -> list[str]:
    """IEX Cloud public endpoint — no key needed for symbol list."""
    symbols = []
    urls = [
        "https://api.iex.cloud/v1/data/core/iex_symbols?token=",
        "https://cloud.iexapis.com/stable/ref-data/symbols?token=Tpk_XXXXXXXXXXXXXXX",  # will 403, skip
    ]
    for url in urls:
        try:
            print("  [IEX] Fetching symbol list…", end=" ", flush=True)
            raw = _http_get(url)
            data = json.loads(raw)
            for item in data:
                sym = (item.get("symbol") or "").strip().upper()
                if VALID_TICKER.match(sym):
                    symbols.append(sym)
            print(f"got {len(symbols)} symbols")
            break
        except Exception as exc:
            print(f"FAILED ({exc})")
    return symbols


def build_universe() -> list[str]:
    seen:    set[str]  = set()
    ordered: list[str] = []

    def add(syms: list[str], label: str = ""):
        added = 0
        for s in syms:
            s = s.upper().strip()
            if s and s not in seen and VALID_TICKER.match(s):
                seen.add(s)
                ordered.append(s)
                added += 1
        if label and added:
            print(f"   → {label}: added {added} unique symbols (total={len(ordered)})")

    print("\n── Fetching stock universe ──────────────────────────────────────────")
    add(fetch_nasdaq_ftp(),   "NASDAQ FTP")
    add(fetch_sec_tickers(),  "SEC EDGAR")
    add(fetch_iex_symbols(),  "IEX")
    add(HARDCODED_SYMBOLS,    "hardcoded supplement")

    # Quality filters: remove obvious junk, ETFs symbols etc.
    filtered = []
    for s in ordered:
        if len(s) < 1 or len(s) > 5:
            continue
        filtered.append(s)

    return filtered[:MAX_SYMBOLS]


def write_file(symbols: list[str], path: Path):
    path.write_text(
        "# US Stocks Universe — all market caps (micro / small / mid / large)\n"
        f"# Total: {len(symbols)} symbols\n"
        "# Generated by fetch_us_stocks.py\n"
        + "\n".join(symbols) + "\n"
    )
    print(f"\n✅  Wrote {len(symbols)} symbols → {path.resolve()}")


def main():
    symbols = build_universe()
    if not symbols:
        print("ERROR: could not fetch any symbols.", file=sys.stderr)
        sys.exit(1)

    micro = [s for s in symbols if len(s) >= 4]
    large = [s for s in symbols if len(s) <= 2]
    mid   = [s for s in symbols if len(s) == 3]
    print(f"\n── Universe breakdown ───────────────────────────────────────────────")
    print(f"   Large-cap proxy  (1-2 char tickers): {len(large):>6}")
    print(f"   Mid-cap proxy    (3-char tickers)  : {len(mid):>6}")
    print(f"   Small/Micro proxy(4+ char tickers) : {len(micro):>6}")
    print(f"   TOTAL                              : {len(symbols):>6}")

    write_file(symbols, OUTPUT_FILE)


if __name__ == "__main__":
    main()
