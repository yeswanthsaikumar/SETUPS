from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = ROOT / "output"
CLI_DIR = ROOT / "apps" / "python" / "cli"
PY_LIB_DIR = ROOT / "apps" / "python" / "lib"
UI_INDEX = ROOT / "apps" / "web" / "ui" / "index.html"
TRADE_BOARD_UI = ROOT / "apps" / "web" / "ui" / "trade_board.html"
WEB_JOBS_DIR = OUTPUT_DIR / "web_jobs"
PERF_TRACKER_JSON = OUTPUT_DIR / "performance_tracker.json"
TRADE_BOARD_JSON = OUTPUT_DIR / "trade_board.json"   # ← new trade board store
CACHE_DIR = ROOT / "cache"

sys.path.insert(0, str(PY_LIB_DIR))
from trade_plan_assistant import brief_as_json, build_scan_brief
from stock_analyzer import analyze_stock
import performance_tracker as _pt
from mutual_funds_provider import MutualFundsProvider, swing_context as _mf_swing_context
import watchlist_pattern_engine as _wpe

_mf_provider = MutualFundsProvider(cache_dir=str(ROOT / "cache"), cache_ttl_hours=6)

RUN_VCP_SYSTEM = CLI_DIR / "run_vcp_system.py"
RUN_BACKTEST = CLI_DIR / "run_backtest.py"


class ScanJobRequest(BaseModel):
    markets: list[Literal["india", "us"]] = Field(default_factory=lambda: ["india", "us"])
    timeframes: list[Literal["daily", "weekly"]] = Field(default_factory=lambda: ["daily", "weekly"])
    setups: Literal["full", "both", "vcp", "range_expansion", "mean_reversion", "breakout_pullback", "bull_flag", "all"] = "full"
    daily_lookback: int = 252
    weekly_lookback: int = 104
    workers: int = 6
    batch: int = 40
    skip_us_refresh: bool = True


class BacktestJobRequest(BaseModel):
    market: Literal["india", "us"] = "india"
    timeframe: Literal["daily", "weekly"] = "daily"
    setups: Literal["both", "vcp", "range_expansion"] = "both"
    lookback: int | None = None
    hold_bars: int | None = None
    workers: int = 4
    batch: int = 20


class JobRecord(BaseModel):
    id: str
    kind: Literal["scan", "backtest"]
    command: list[str]
    status: Literal["queued", "running", "succeeded", "failed"]
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    return_code: int | None = None
    log_file: str


class TradeBoardPosition(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    symbol: str
    name: str = ""
    entry: float
    quantity: int = 1
    sl: float = 0.0
    t1: float = 0.0
    t2: float = 0.0
    t3: float = 0.0
    setup: str = ""
    rating: str = ""
    notes: str = ""
    entry_date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    status: Literal["OPEN","CLOSED","SL_HIT","T1_HIT","T2_HIT","T3_HIT"] = "OPEN"
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    tags: list[str] = Field(default_factory=list)

class TradeBoardUpdate(BaseModel):
    status: Optional[str] = None
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    sl: Optional[float] = None
    t1: Optional[float] = None
    t2: Optional[float] = None
    t3: Optional[float] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def create(self, kind: Literal["scan", "backtest"], command: list[str], log_file: Path) -> JobRecord:
        job = JobRecord(
            id=str(uuid.uuid4()),
            kind=kind,
            command=command,
            status="queued",
            created_at=datetime.now().isoformat(timespec="seconds"),
            log_file=str(log_file.resolve()),
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def list(self) -> list[JobRecord]:
        with self._lock:
            jobs = list(self._jobs.values())
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def get(self, job_id: str) -> JobRecord:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            raise KeyError(job_id)
        return job

    def update(self, job_id: str, **updates) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            data = job.model_dump()
            data.update(updates)
            self._jobs[job_id] = JobRecord(**data)


jobs = JobStore()
app = FastAPI(title="SETUPS Web", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
WEB_JOBS_DIR.mkdir(parents=True, exist_ok=True)

if OUTPUT_DIR.exists():
    app.mount("/reports", StaticFiles(directory=str(OUTPUT_DIR)), name="reports")


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _run_job(job_id: str, command: list[str], log_file: Path) -> None:
    jobs.update(job_id, status="running", started_at=datetime.now().isoformat(timespec="seconds"))
    _ensure_parent_dir(log_file)
    with open(log_file, "w", encoding="utf-8") as fh:
        fh.write("$ " + " ".join(command) + "\n\n")
        fh.flush()
        proc = subprocess.Popen(command, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT, text=True)
        return_code = proc.wait()
    jobs.update(
        job_id,
        status="succeeded" if return_code == 0 else "failed",
        finished_at=datetime.now().isoformat(timespec="seconds"),
        return_code=return_code,
    )


def _submit_job(kind: Literal["scan", "backtest"], command: list[str]) -> JobRecord:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = WEB_JOBS_DIR / f"{kind}_{timestamp}_{uuid.uuid4().hex[:8]}.log"
    _ensure_parent_dir(log_file)
    job = jobs.create(kind=kind, command=command, log_file=log_file)
    thread = threading.Thread(target=_run_job, args=(job.id, command, log_file), daemon=True)
    thread.start()
    return job


def _read_json_if_exists(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@app.get("/board")
def trade_board_page() -> FileResponse:
    if not TRADE_BOARD_UI.exists():
        raise HTTPException(status_code=404, detail="Trade board UI not found")
    return FileResponse(TRADE_BOARD_UI)


@app.get("/")
def ui_index() -> FileResponse:
    if not UI_INDEX.exists():
        raise HTTPException(status_code=404, detail="UI file not found")
    return FileResponse(UI_INDEX)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "root": str(ROOT),
        "python": sys.version.split()[0],
        "javaHome": os.environ.get("JAVA_HOME", ""),
    }


@app.post("/api/jobs/scan")
def start_scan(req: ScanJobRequest) -> dict:
    setups = "full" if req.setups == "all" else req.setups
    command = [
        sys.executable,
        str(RUN_VCP_SYSTEM),
        "--markets",
        ",".join(req.markets),
        "--timeframes",
        ",".join(req.timeframes),
        "--setups",
        setups,
        "--daily-lookback",
        str(req.daily_lookback),
        "--weekly-lookback",
        str(req.weekly_lookback),
        "--workers",
        str(req.workers),
        "--batch",
        str(req.batch),
        "--output-dir",
        str(OUTPUT_DIR),
    ]
    if req.skip_us_refresh:
        command.append("--skip-us-refresh")
    job = _submit_job("scan", command)
    return {"job": job}


@app.get("/api/assistant/scan-brief")
def assistant_scan_brief(
    market: Literal["india", "us"] = "india",
    timeframe: Literal["daily", "weekly"] = "daily",
    setups: Literal["full", "both", "vcp", "range_expansion", "mean_reversion", "breakout_pullback", "bull_flag", "all"] = "full",
    top_n: int = 12,
) -> dict:
    if top_n <= 0:
        raise HTTPException(status_code=400, detail="top_n must be greater than 0")

    summary = build_scan_brief(
        output_dir=OUTPUT_DIR,
        market=market,
        timeframe=timeframe,
        setups="full" if setups == "all" else setups,
        top_n=top_n,
    )
    return {"brief": brief_as_json(summary)}


@app.post("/api/jobs/backtest")
def start_backtest(req: BacktestJobRequest) -> dict:
    command = [
        sys.executable,
        str(RUN_BACKTEST),
        "--market",
        req.market,
        "--timeframe",
        req.timeframe,
        "--setups",
        req.setups,
        "--workers",
        str(req.workers),
        "--batch",
        str(req.batch),
        "--output-dir",
        str(OUTPUT_DIR),
    ]
    if req.lookback is not None:
        command.extend(["--lookback", str(req.lookback)])
    if req.hold_bars is not None:
        command.extend(["--hold-bars", str(req.hold_bars)])
    job = _submit_job("backtest", command)
    return {"job": job}


@app.get("/api/jobs")
def list_jobs() -> dict:
    return {"jobs": jobs.list()}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    try:
        return {"job": jobs.get(job_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}") from exc


@app.get("/api/jobs/{job_id}/log")
def get_job_log(job_id: str, tail_lines: int = 200) -> dict:
    try:
        job = jobs.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}") from exc

    path = Path(job.log_file)
    if not path.exists():
        return {"jobId": job_id, "log": ""}

    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    tail = "\n".join(lines[-max(1, tail_lines):])
    return {"jobId": job_id, "log": tail}


@app.get("/api/stock/analyze")
def stock_analyze(
    symbol: str,
    market: Literal["india", "us"] = "india",
    timeframe: Literal["daily", "weekly"] = "daily",
    setups: Literal["full", "both", "vcp", "range_expansion", "mean_reversion", "breakout_pullback", "bull_flag", "all"] = "full",
    source: Literal["auto", "output", "live"] = "auto",
) -> dict:
    """Deep-dive analysis of a single stock using saved outputs and/or live scanner logic."""
    if not symbol or not symbol.strip():
        raise HTTPException(status_code=400, detail="symbol is required")
    result = analyze_stock(
        output_dir=OUTPUT_DIR,
        symbol=symbol.strip(),
        market=market,
        timeframe=timeframe,
        setups=setups,
        source=source,
    )
    return {"analysis": result}


@app.get("/api/outputs/scan/latest")
def scan_latest_summary() -> dict:
    summary_json = OUTPUT_DIR / "system_latest_summary.json"
    data = _read_json_if_exists(summary_json)
    if data is None:
        raise HTTPException(status_code=404, detail="No latest scan summary found")
    return {
        "summary": data,
        "summaryJson": f"/reports/{summary_json.name}",
        "summaryMd": "/reports/system_latest_summary.md",
    }


@app.get("/api/outputs/scan/manifests")
def scan_manifests() -> dict:
    manifests = sorted(OUTPUT_DIR.glob("scan_manifest_*_LATEST.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    items: list[dict] = []
    for path in manifests[:30]:
        items.append(
            {
                "name": path.name,
                "updatedAt": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                "url": f"/reports/{path.name}",
                "data": _read_json_if_exists(path),
            }
        )
    return {"items": items}


@app.get("/api/outputs/backtest/latest")
def backtest_latest(market: Literal["india", "us"] = "india", timeframe: Literal["daily", "weekly"] = "daily") -> dict:
    label = f"{market}_{timeframe}"
    html_path = OUTPUT_DIR / f"backtest_{label}_LATEST.html"
    csv_path = OUTPUT_DIR / f"backtest_{label}_LATEST.csv"
    wf_path = OUTPUT_DIR / f"backtest_{label}_walk_forward_LATEST.json"
    mc_path = OUTPUT_DIR / f"backtest_{label}_monte_carlo_LATEST.json"

    if not html_path.exists() and not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"No latest backtest found for {label}")

    return {
        "label": label,
        "html": f"/reports/{html_path.name}" if html_path.exists() else None,
        "csv": f"/reports/{csv_path.name}" if csv_path.exists() else None,
        "walkForward": _read_json_if_exists(wf_path),
        "monteCarlo": _read_json_if_exists(mc_path),
        "walkForwardUrl": f"/reports/{wf_path.name}" if wf_path.exists() else None,
        "monteCarloUrl": f"/reports/{mc_path.name}" if mc_path.exists() else None,
    }


# ── Performance Tracker ──────────────────────────────────────────────────────

def _load_perf_tracker() -> dict:
    if not PERF_TRACKER_JSON.exists():
        return {"version": 1, "lastUpdated": None, "trades": [], "archived": []}
    try:
        return json.loads(PERF_TRACKER_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "lastUpdated": None, "trades": [], "archived": []}


@app.get("/api/performance/summary")
def perf_summary() -> dict:
    """Aggregate performance stats across all tracked trades."""
    data = _load_perf_tracker()
    trades = data.get("trades", [])
    archived = data.get("archived", [])
    stats = _pt.compute_summary_stats(trades)
    return {
        "lastUpdated": data.get("lastUpdated"),
        "stats": stats,
        "archivedCount": len(archived),
        "trackerExists": PERF_TRACKER_JSON.exists(),
    }


@app.get("/api/performance/trades")
def perf_trades(
    market: Literal["india", "us"] = "india",
    timeframe: Literal["daily", "weekly"] = "daily",
    include_expired: bool = False,
    include_archived: bool = False,
) -> dict:
    """Return filtered list of tracked trade records."""
    data = _load_perf_tracker()
    all_trades = data.get("trades", [])
    if include_archived:
        all_trades = all_trades + data.get("archived", [])

    filtered = [
        t for t in all_trades
        if t.get("market") == market and t.get("timeframe") == timeframe
        and (include_expired or t.get("status") != "EXPIRED")
    ]
    filtered.sort(key=lambda t: (
        {"OPEN": 0, "T3_HIT": 1, "T2_HIT": 2, "T1_HIT": 3, "SL_HIT": 4, "EXPIRED": 5}.get(
            t.get("status", "OPEN"), 9),
        -float(t.get("gainPct", 0) or 0),
    ))
    stats = _pt.compute_summary_stats(filtered)
    return {
        "market": market,
        "timeframe": timeframe,
        "count": len(filtered),
        "stats": stats,
        "trades": filtered,
        "lastUpdated": data.get("lastUpdated"),
    }


@app.get("/api/performance/report")
def perf_report(
    market: Literal["india", "us"] = "india",
    timeframe: Literal["daily", "weekly"] = "daily",
) -> FileResponse:
    """Serve the prebuilt performance tracker HTML report."""
    report_path = OUTPUT_DIR / f"performance_tracker_{market}_{timeframe}_LATEST.html"
    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No performance tracker report found for {market}/{timeframe}. "
                   "Run a scan first to generate it.",
        )
    return FileResponse(report_path, media_type="text/html")


# ── Mutual Funds / Institutional Holdings ────────────────────────────────────

@app.get("/api/stock/mf-holdings")
def stock_mf_holdings(
    symbol: str,
    market: Literal["india", "us"] = "india",
    force_refresh: bool = False,
) -> dict:
    """
    Fetch mutual fund & institutional holding data for a stock.
    Returns shareholding pattern (Promoters/FIIs/DIIs/Public),
    trend analysis, smart-money signal, and top MF scheme names.
    """
    if not symbol or not symbol.strip():
        raise HTTPException(status_code=400, detail="symbol is required")

    sym = symbol.strip()
    # Add .NS suffix for Indian stocks if not present
    if market == "india" and not sym.endswith(".NS") and not sym.endswith(".BO"):
        sym_yf = sym + ".NS"
    else:
        sym_yf = sym

    # Force refresh by clearing cache
    if force_refresh:
        cache_file = (ROOT / "cache" / f"mf_holdings_{sym_yf.replace('.', '_')}.json")
        if cache_file.exists():
            cache_file.unlink(missing_ok=True)

    data = _mf_provider.fetch(sym_yf, market=market)
    context = _mf_swing_context(data)

    return {
        "symbol": sym,
        "symbolYf": sym_yf,
        "market": market,
        "holdings": data,
        "swingContext": context,
        "cachedAt": data.get("_cached_at"),
        "source": data.get("_source", "unknown"),
    }


@app.get("/api/performance/trades/with-mf")
def perf_trades_with_mf(
    market: Literal["india", "us"] = "india",
    timeframe: Literal["daily", "weekly"] = "daily",
    include_expired: bool = False,
    include_archived: bool = False,
) -> dict:
    """
    Return performance trades enriched with MF/institutional holding data.
    Fetches MF data in parallel for all active trades.
    """
    data = _load_perf_tracker()
    all_trades = data.get("trades", [])
    if include_archived:
        all_trades = all_trades + data.get("archived", [])

    filtered = [
        t for t in all_trades
        if t.get("market") == market and t.get("timeframe") == timeframe
        and (include_expired or t.get("status") != "EXPIRED")
    ]
    filtered.sort(key=lambda t: (
        {"OPEN": 0, "T3_HIT": 1, "T2_HIT": 2, "T1_HIT": 3, "SL_HIT": 4, "EXPIRED": 5}.get(
            t.get("status", "OPEN"), 9),
        -float(t.get("gainPct", 0) or 0),
    ))

    # Batch-fetch MF data for all symbols
    symbols = list({t["symbol"] for t in filtered})
    if market == "india":
        symbols_yf = [
            (s + ".NS" if not s.endswith(".NS") and not s.endswith(".BO") else s)
            for s in symbols
        ]
    else:
        symbols_yf = symbols

    mf_data: dict = {}
    try:
        raw = _mf_provider.fetch_batch(symbols_yf, market=market, workers=8)
        # Map back to original symbols
        sym_map = {s: sy for s, sy in zip(symbols, symbols_yf)}
        for orig_sym in symbols:
            yf_sym = sym_map.get(orig_sym, orig_sym)
            mf_data[orig_sym] = _mf_swing_context(raw.get(yf_sym, {}))
    except Exception:
        pass

    # Enrich trades
    enriched = []
    for trade in filtered:
        t = dict(trade)
        t["mfHoldings"] = mf_data.get(trade["symbol"], {})
        enriched.append(t)

    stats = _pt.compute_summary_stats(filtered)
    return {
        "market": market,
        "timeframe": timeframe,
        "count": len(enriched),
        "stats": stats,
        "trades": enriched,
        "lastUpdated": data.get("lastUpdated"),
    }


# ── Watchlist Pattern Lab ─────────────────────────────────────────────────────

class WatchlistAnalysisRequest(BaseModel):
    symbols: list[str] = Field(
        default=["SLTTECH", "AEROFLEX", "PFOCUS", "AVANTIFEED", "BAJAJCON", "CENTUM", "ATLANTAELE", "POWERINDIA"],
        description="List of stock symbols to analyze (NSE tickers without .NS suffix for India)"
    )
    market: Literal["india", "us"] = "india"
    workers: int = Field(default=5, ge=1, le=12)
    include_news: bool = True
    include_fundamentals: bool = True
    include_mf: bool = True


@app.post("/api/watchlist/analyze")
def watchlist_analyze(req: WatchlistAnalysisRequest) -> dict:
    """
    Analyze a list of stocks for RS Leader patterns, setups, fundamentals,
    FII/DII activity, news, and generate full trade thesis for each.

    Detects stocks that:
    - Hold / outperform during market declines
    - Consolidate tightly while market corrects
    - Are positioned to lead the next market upleg
    """
    if not req.symbols:
        raise HTTPException(status_code=400, detail="symbols list cannot be empty")

    # Sanitize symbols
    symbols = [s.strip().upper() for s in req.symbols if s.strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="No valid symbols provided")

    result = _wpe.analyze_watchlist(
        symbols=symbols,
        market=req.market,
        workers=req.workers,
        include_news=req.include_news,
        include_fundamentals=req.include_fundamentals,
        include_mf=req.include_mf,
    )
    return result


@app.get("/api/watchlist/analyze-single")
def watchlist_analyze_single(
    symbol: str,
    market: Literal["india", "us"] = "india",
    include_news: bool = True,
    include_fundamentals: bool = True,
    include_mf: bool = True,
) -> dict:
    """Deep-dive RS Leader analysis for a single stock."""
    if not symbol or not symbol.strip():
        raise HTTPException(status_code=400, detail="symbol is required")

    result = _wpe.analyze_single_stock(
        symbol=symbol.strip().upper(),
        market=market,
        include_news=include_news,
        include_fundamentals=include_fundamentals,
        include_mf=include_mf,
    )
    if result.get("error") and not result.get("rs"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/api/watchlist/market-phases")
def market_phases_endpoint(
    days: int = 252,
) -> dict:
    """
    Detect Nifty50 market phases: decline, consolidation, recovery.
    Returns structured phase map for the last `days` trading days.
    """
    market_prices = _wpe.fetch_market_prices(days=max(days, 252))
    if not market_prices:
        raise HTTPException(status_code=503, detail="Could not fetch Nifty50 data")

    phases = _wpe.detect_market_phases(market_prices)
    closes = market_prices.get("close", [])

    return {
        "nifty_current": round(closes[-1], 2) if closes else None,
        "nifty_dates":   market_prices.get("dates", [])[-30:],
        "nifty_closes":  [round(c, 2) for c in closes[-30:]],
        "phases":        phases,
        "phase_summary": _wpe._summarize_phases(phases),
        "phase_count":   len(phases),
        "recent_phases": phases[-5:] if phases else [],
    }


@app.get("/api/watchlist/default-list")
def default_watchlist() -> dict:
    """Return the default example watchlist with context about the RS Leader pattern."""
    return {
        "default_symbols": [
            "SLTTECH", "AEROFLEX", "PFOCUS", "AVANTIFEED",
            "BAJAJCON", "CENTUM", "ATLANTAELE", "POWERINDIA",
            "MATARTECH",
        ],
        "pattern_description": (
            "RS Leader Pattern: These stocks gave 30-50% returns Jan-Feb, "
            "consolidated while the entire market fell in March (Iran-US tensions), "
            "then flew high once macro cleared. "
            "This tool identifies such stocks before the breakout."
        ),
        "key_metrics": [
            "RS Score vs Nifty (IBD-style)",
            "Behavior during market declines",
            "Consolidation tightness & base quality",
            "ADR % — opportunity per trade",
            "FII/DII institutional activity",
            "Earnings & debt trends",
            "News & macro catalysts",
            "Entry / Stop / Targets / Risk:Reward",
        ],
        "pattern_checklist": [
            "Stock held / declined < market during correction",
            "Tight, low-volume consolidation in base",
            "RS line making new highs or holding near highs",
            "Stage 2 uptrend: price > MA50 > MA150 > MA200",
            "DII or smart money accumulating",
            "Positive earnings trajectory (EPS growth QoQ/YoY)",
            "Volume dry-up in base, expansion on breakout",
            "Macro catalyst visible (earnings, sector tailwind, policy)",
        ],
    }


# ── Trade Board Store ──────────────────────────────────────────────────────────

_board_lock = threading.Lock()

def _load_board() -> dict:
    if not TRADE_BOARD_JSON.exists():
        return {"version": 1, "positions": [], "created": datetime.now().isoformat()}
    try:
        return json.loads(TRADE_BOARD_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "positions": [], "created": datetime.now().isoformat()}

def _save_board(data: dict) -> None:
    data["lastUpdated"] = datetime.now().isoformat()
    TRADE_BOARD_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

# ── Price / Chart helpers ──────────────────────────────────────────────────────

def _read_ohlcv(symbol: str, days: int = 90) -> list[dict]:
    """Read OHLCV from cache. Returns sorted list of dicts with date/open/high/low/close/volume."""
    base = symbol.upper().replace(".NS", "").replace(".BO", "")
    ns   = base + ".NS"
    rows: list[dict] = []
    for prefix in [ns, base]:
        for suffix in ["_252", "_504", "_728", "_900", "_3528"]:
            for fname in [f"{prefix}{suffix}.csv", f"{prefix}.NS{suffix}.csv"]:
                p = CACHE_DIR / fname
                if not p.exists():
                    continue
                try:
                    with open(p, newline="", encoding="utf-8") as f:
                        for row in csv.DictReader(f):
                            try:
                                rows.append({
                                    "date": row.get("date","") or row.get("Date","") or row.get("Datetime",""),
                                    "open":   float(row.get("open",  row.get("Open",  0)) or 0),
                                    "high":   float(row.get("high",  row.get("High",  0)) or 0),
                                    "low":    float(row.get("low",   row.get("Low",   0)) or 0),
                                    "close":  float(row.get("close", row.get("Close", 0)) or 0),
                                    "volume": float(row.get("volume",row.get("Volume",0)) or 0),
                                })
                            except Exception:
                                pass
                    if rows:
                        break
                except Exception:
                    pass
            if rows:
                break
        if rows:
            break
    rows = [r for r in rows if r["close"] > 0 and r["date"]]
    rows.sort(key=lambda r: r["date"])
    if days and len(rows) > days:
        rows = rows[-days:]
    return rows

def _calc_ema(closes: list[float], period: int) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * len(closes)
    if len(closes) < period:
        return result
    k = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period
    result[period - 1] = round(ema, 2)
    for i in range(period, len(closes)):
        ema = closes[i] * k + ema * (1 - k)
        result[i] = round(ema, 2)
    return result

def _get_current_price(symbol: str) -> Optional[float]:
    rows = _read_ohlcv(symbol, days=5)
    return rows[-1]["close"] if rows else None

def _get_price_info(symbol: str) -> tuple[Optional[float], Optional[float]]:
    """Returns (cmp, prev_close) from cached OHLCV data."""
    rows = _read_ohlcv(symbol, days=5)
    if not rows:
        return None, None
    cmp = rows[-1]["close"]
    prev_close = rows[-2]["close"] if len(rows) >= 2 else None
    return cmp, prev_close

def _compute_board_stats(positions: list[dict]) -> dict:
    """Compute aggregate stats from positions list."""
    open_pos = [p for p in positions if p.get("status") == "OPEN"]
    closed_pos = [p for p in positions if p.get("status") not in ("OPEN",)]

    total_invested = sum(
        (p.get("entry", 0) * p.get("quantity", 1)) for p in open_pos
    )
    total_pl = 0.0
    open_risk = 0.0
    locked_profit = 0.0
    day_pl = 0.0

    for p in positions:
        entry = p.get("entry", 0)
        qty   = p.get("quantity", 1)
        cmp   = p.get("cmp", entry)
        exit_price = p.get("exit_price") or cmp
        sl    = p.get("sl", 0)
        status = p.get("status", "OPEN")

        if status == "OPEN":
            pl = (cmp - entry) * qty
            total_pl += pl
            if sl and sl < entry:
                open_risk += (entry - sl) * qty
            day_pl += p.get("dayChangeAmt", 0) or 0
        else:
            pl = (exit_price - entry) * qty
            total_pl += pl
            if status.startswith("T"):
                locked_profit += pl

    return {
        "total_positions": len(positions),
        "open_positions": len(open_pos),
        "closed_positions": len(closed_pos),
        "total_invested": round(total_invested, 2),
        "total_pl": round(total_pl, 2),
        "open_risk": round(open_risk, 2),
        "locked_profit": round(locked_profit, 2),
        "day_pl": round(day_pl, 2),
    }


@app.get("/api/trade-board")
def trade_board_ui() -> FileResponse:
    if not TRADE_BOARD_UI.exists():
        raise HTTPException(status_code=404, detail="Trade board UI not found")
    return FileResponse(TRADE_BOARD_UI)

@app.get("/api/trade-board/summary")
def trade_board_summary() -> dict:
    with _board_lock:
        data = _load_board()
        positions = data.get("positions", [])
    # Enrich with CMP and day change for open positions
    for p in positions:
        entry = p.get("entry", 0) or 0
        qty   = p.get("quantity", 1) or 1
        if p.get("status") == "OPEN":
            cmp, prev_close = _get_price_info(p.get("symbol", ""))
            if cmp:
                p["cmp"] = cmp
                p["gainPct"] = round((cmp - entry) / entry * 100, 2) if entry else 0
                p["gainAmt"] = round((cmp - entry) * qty, 2) if entry else 0
            if cmp and prev_close and prev_close > 0:
                p["dayChangePct"] = round((cmp - prev_close) / prev_close * 100, 2)
                p["dayChangeAmt"] = round((cmp - prev_close) * qty, 2)
        elif p.get("exit_price") and entry:
            ep = float(p["exit_price"])
            p["gainPct"] = round((ep - entry) / entry * 100, 2)
            p["gainAmt"] = round((ep - entry) * qty, 2)
    stats = _compute_board_stats(positions)
    return {"stats": stats, "lastUpdated": data.get("lastUpdated")}

@app.get("/api/trade-board/positions")
def trade_board_positions(status: str = "") -> dict:
    with _board_lock:
        data = _load_board()
        positions = list(data.get("positions", []))
    # Enrich with current price and gain
    for p in positions:
        entry = p.get("entry", 0) or 0
        qty   = p.get("quantity", 1) or 1
        if p.get("status") == "OPEN":
            cmp, prev_close = _get_price_info(p.get("symbol", ""))
            if cmp:
                p["cmp"] = round(cmp, 2)
                p["gainPct"] = round((cmp - entry) / entry * 100, 2) if entry else 0
                p["gainAmt"] = round((cmp - entry) * qty, 2) if entry else 0
            if cmp and prev_close and prev_close > 0:
                p["dayChangePct"] = round((cmp - prev_close) / prev_close * 100, 2)
                p["dayChangeAmt"] = round((cmp - prev_close) * qty, 2)
        elif p.get("exit_price") and entry:
            # Compute final gain for closed/stopped positions
            ep = float(p["exit_price"])
            p["gainPct"] = round((ep - entry) / entry * 100, 2)
            p["gainAmt"] = round((ep - entry) * qty, 2)
    if status:
        positions = [p for p in positions if p.get("status") == status]
    # Sort: OPEN first, then by gain desc
    positions.sort(key=lambda p: (p.get("status") != "OPEN", -float(p.get("gainPct", 0) or 0)))
    stats = _compute_board_stats(positions)
    return {"positions": positions, "stats": stats, "lastUpdated": data.get("lastUpdated")}

@app.post("/api/trade-board/positions")
def trade_board_add_position(position: TradeBoardPosition) -> dict:
    pos_dict = position.model_dump()
    with _board_lock:
        data = _load_board()
        positions = data.get("positions", [])
        positions.append(pos_dict)
        data["positions"] = positions
        _save_board(data)
    return {"position": pos_dict, "ok": True}

@app.put("/api/trade-board/positions/{position_id}")
def trade_board_update_position(position_id: str, update: TradeBoardUpdate) -> dict:
    with _board_lock:
        data = _load_board()
        positions = data.get("positions", [])
        for i, p in enumerate(positions):
            if p.get("id") == position_id:
                upd = {k: v for k, v in update.model_dump().items() if v is not None}
                positions[i].update(upd)
                data["positions"] = positions
                _save_board(data)
                return {"position": positions[i], "ok": True}
    raise HTTPException(status_code=404, detail=f"Position not found: {position_id}")

@app.delete("/api/trade-board/positions/{position_id}")
def trade_board_delete_position(position_id: str) -> dict:
    with _board_lock:
        data = _load_board()
        positions = data.get("positions", [])
        before = len(positions)
        positions = [p for p in positions if p.get("id") != position_id]
        if len(positions) == before:
            raise HTTPException(status_code=404, detail=f"Position not found: {position_id}")
        data["positions"] = positions
        _save_board(data)
    return {"ok": True, "deleted": position_id}

@app.get("/api/trade-board/chart/{symbol}")
def trade_board_chart(symbol: str, days: int = 90) -> dict:
    rows = _read_ohlcv(symbol, days=max(days, 30))
    if not rows:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}")
    closes = [r["close"] for r in rows]
    ema5   = _calc_ema(closes, 5)
    ema20  = _calc_ema(closes, 20)
    ema50  = _calc_ema(closes, 50)
    avg_vol = sum(r["volume"] for r in rows[-20:]) / 20 if len(rows) >= 20 else 0
    for i, r in enumerate(rows):
        r["ema5"]  = ema5[i]
        r["ema20"] = ema20[i]
        r["ema50"] = ema50[i]
        r["volRatio"] = round(r["volume"] / avg_vol, 2) if avg_vol else None
    return {
        "symbol": symbol, "days": len(rows), "avgVol20": round(avg_vol, 0),
        "cmp": closes[-1], "candles": rows
    }

@app.get("/api/trade-board/equity")
def trade_board_equity() -> dict:
    """Compute equity curve from closed+open positions."""
    with _board_lock:
        data = _load_board()
        positions = data.get("positions", [])
    curve = []
    total = 0.0
    for p in sorted(positions, key=lambda x: x.get("exit_date") or x.get("entry_date") or ""):
        entry = p.get("entry", 0); qty = p.get("quantity", 1)
        status = p.get("status", "OPEN")
        if status != "OPEN":
            exit_p = p.get("exit_price") or entry
            pl = (exit_p - entry) * qty
            total += pl
            curve.append({
                "date": p.get("exit_date") or p.get("entry_date"),
                "symbol": p.get("symbol",""),
                "pl": round(pl, 2),
                "cumPl": round(total, 2),
                "status": status
            })
    return {"curve": curve, "totalPl": round(total, 2)}

@app.get("/api/trade-board/scan-signals")
def trade_board_scan_signals(market: str = "india", timeframe: str = "daily") -> dict:
    """Return top open trade signals from scan output for quick import."""
    suffix = f"{market}_{timeframe}_full"
    # Try open_trades first, then vcp_hits as fallback
    candidates = [
        OUTPUT_DIR / f"open_trades_{suffix}_LATEST.json",
        OUTPUT_DIR / f"vcp_hits_{suffix}_LATEST.json",
    ]
    for json_path in candidates:
        if not json_path.exists():
            continue
        try:
            signals = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(signals, list) and signals:
                # Normalize score field (may be "rankingScore" or "score", as string or float)
                for s in signals:
                    if "rankingScore" not in s:
                        s["rankingScore"] = s.get("score", 0)
                signals.sort(key=lambda x: -float(x.get("rankingScore") or x.get("score") or 0))
                return {"signals": signals[:30], "total": len(signals), "source": json_path.name}
        except Exception:
            pass
    return {"signals": [], "total": 0}

