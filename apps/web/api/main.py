from __future__ import annotations

import csv
import json
import math
import os
import subprocess
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
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
SECTOR_MACRO_HTML = OUTPUT_DIR / "sector_macro_analysis.html"
GENERATE_SECTOR_MACRO = CLI_DIR / "generate_sector_macro_page.py"
BREADTH_HTML = OUTPUT_DIR / "market_breadth.html"
GENERATE_BREADTH = CLI_DIR / "generate_breadth_dashboard.py"
TRADE_PLANS_HTML = OUTPUT_DIR / "trade_plans_live.html"
GENERATE_TRADE_PLANS = CLI_DIR / "generate_trade_plans_page.py"
WEB_JOBS_DIR = OUTPUT_DIR / "web_jobs"
PERF_TRACKER_JSON = OUTPUT_DIR / "performance_tracker.json"
# Trade data stored in dedicated folder (not output/) so it survives output/ cleanups
TRADE_DATA_DIR = ROOT / "trade_data"
TRADE_BOARD_JSON = TRADE_DATA_DIR / "positions.json"
TRADE_JOURNAL_JSON = TRADE_DATA_DIR / "journal.json"
TRADE_WATCHLIST_JSON = TRADE_DATA_DIR / "watchlist.json"
TRADE_BOARD_JSON_LEGACY = OUTPUT_DIR / "trade_board.json"  # kept for migration only
CACHE_DIR = ROOT / "cache"
REFRESH_CACHE_SCRIPT = ROOT / "scripts" / "refresh_cache.py"
REFRESH_LOG = OUTPUT_DIR / "cache_refresh.log"

sys.path.insert(0, str(PY_LIB_DIR))
from trade_plan_assistant import brief_as_json, build_scan_brief
from stock_analyzer import analyze_stock
import performance_tracker as _pt
from mutual_funds_provider import MutualFundsProvider, swing_context as _mf_swing_context
import watchlist_pattern_engine as _wpe
from breakout_alert_engine import (
    BreakoutScanner, AlertConfig, AlertState,
    scan_stock_for_breakouts, backtest_breakout_detection,
    send_alert, send_telegram_text,
    check_position_ema5_proximity, EmaProximityAlert,
    send_ema5_telegram_alert, _format_ema5_alert_message,
)

_mf_provider = MutualFundsProvider(cache_dir=str(ROOT / "cache"), cache_ttl_hours=6)

# ── Breakout Alert Scanner (singleton) ──────────────────────────────────────
_breakout_scanner = BreakoutScanner(
    data_dir=TRADE_DATA_DIR,
    cache_dir=CACHE_DIR,
)

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
    error: str | None = None


class PartialExit(BaseModel):
    """Record of a partial position exit."""
    date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    quantity: int
    price: float
    reason: str = ""  # e.g. "T1_HIT", "TRAIL", "MANUAL"


class TradeBoardPosition(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    symbol: str
    name: str = ""
    entry: float
    quantity: int = 1
    remaining_quantity: int | None = None  # None = same as quantity (fully open)
    sl: float = 0.0
    t1: float = 0.0
    t2: float = 0.0
    t3: float = 0.0
    setup: str = ""
    rating: str = ""
    notes: str = ""
    entry_date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    status: Literal["OPEN","PARTIAL","CLOSED","SL_HIT","T1_HIT","T2_HIT","T3_HIT"] = "OPEN"
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    partial_exits: list[PartialExit] = Field(default_factory=list)


class PartialExitRequest(BaseModel):
    quantity: int
    price: float
    reason: str = "MANUAL"
    date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))


class TradeBoardUpdate(BaseModel):
    status: Optional[str] = None
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    sl: Optional[float] = None
    t1: Optional[float] = None
    t2: Optional[float] = None
    t3: Optional[float] = None
    entry: Optional[float] = None
    quantity: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None


JOBS_PERSIST_FILE = OUTPUT_DIR / "web_jobs" / "jobs_store.json"


class JobStore:
    """Persistent job store backed by a JSON file so jobs survive API restarts."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._load()

    # ── persistence helpers ──────────────────────────────────────────────────
    def _load(self) -> None:
        try:
            JOBS_PERSIST_FILE.parent.mkdir(parents=True, exist_ok=True)
            if JOBS_PERSIST_FILE.exists():
                raw = json.loads(JOBS_PERSIST_FILE.read_text())
                for rec in raw:
                    try:
                        job = JobRecord(**rec)
                        # Mark running jobs as failed (process died during restart)
                        if job.status in ("queued", "running"):
                            job = JobRecord(**{**rec, "status": "failed",
                                               "error": "API restarted while job was in-flight"})
                        self._jobs[job.id] = job
                    except Exception:
                        pass
        except Exception:
            pass

    def _save(self) -> None:
        try:
            data = [j.model_dump() for j in self._jobs.values()]
            JOBS_PERSIST_FILE.write_text(json.dumps(data, default=str, indent=2))
        except Exception:
            pass

    # ── public API ───────────────────────────────────────────────────────────
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
            self._save()
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
            self._save()


jobs = JobStore()


# ═══════════════════════════════════════════════════════════════════════════════
#  BACKGROUND OHLCV CACHE REFRESH MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class BackgroundCacheRefresher:
    """
    Manages background OHLCV cache refresh.
    • Runs on server startup (unless SETUPS_SKIP_STARTUP_REFRESH=true)
    • Can be triggered via API: POST /api/cache/refresh
    • Status/progress exposed via GET /api/cache/refresh-status
    • Thread-safe: only one refresh runs at a time
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._status: str = "idle"  # idle | running | completed | failed
        self._started_at: Optional[str] = None
        self._finished_at: Optional[str] = None
        self._progress: dict = {}  # refreshed, skipped, errors, no_data, total, current
        self._log_tail: str = ""
        self._thread: Optional[threading.Thread] = None
        self._error: Optional[str] = None
        self._symbols_done: int = 0
        self._symbols_total: int = 0

    @property
    def is_running(self) -> bool:
        return self._status == "running"

    def status_dict(self) -> dict:
        with self._lock:
            return {
                "status": self._status,
                "startedAt": self._started_at,
                "finishedAt": self._finished_at,
                "progress": dict(self._progress),
                "symbolsDone": self._symbols_done,
                "symbolsTotal": self._symbols_total,
                "error": self._error,
                "logTail": self._log_tail[-2000:] if self._log_tail else "",
            }

    def start(self, symbols: list[str] | None = None, force: bool = False,
              indian_only: bool = True, workers: int = 4) -> dict:
        """Launch a background refresh. Returns immediately."""
        with self._lock:
            if self._status == "running":
                return {"ok": False, "message": "Refresh already running",
                        "status": self._status}
            self._status = "running"
            self._started_at = datetime.now().isoformat(timespec="seconds")
            self._finished_at = None
            self._error = None
            self._progress = {"refreshed": 0, "skipped": 0, "errors": 0,
                              "no_data": 0}
            self._symbols_done = 0
            self._symbols_total = 0
            self._log_tail = ""

        self._thread = threading.Thread(
            target=self._run,
            args=(symbols, force, indian_only, workers),
            daemon=True,
        )
        self._thread.start()
        return {"ok": True, "message": "Cache refresh started",
                "status": "running"}

    def _run(self, symbols, force, indian_only, workers):
        """The actual refresh logic, runs in a background thread."""
        try:
            # Import refresh_cache functions
            sys.path.insert(0, str(ROOT / "scripts"))
            import importlib
            # Ensure fresh import
            if "refresh_cache" in sys.modules:
                importlib.reload(sys.modules["refresh_cache"])
            import refresh_cache as _rc

            # 1. Refresh Nifty index first
            self._append_log("🔄 Refreshing Nifty 50 index…\n")
            try:
                _rc.refresh_nifty_index()
                self._append_log("✅ Nifty index done\n")
            except Exception as e:
                self._append_log(f"⚠ Nifty index refresh error: {e}\n")

            # 2. Find stale symbols
            sym_filter = symbols if symbols else None
            stale = _rc._find_stale_caches(sym_filter, indian_only=indian_only)
            with self._lock:
                self._symbols_total = len(stale)

            if not stale:
                self._append_log("✅ All cache files are up-to-date!\n")
                with self._lock:
                    self._status = "completed"
                    self._finished_at = datetime.now().isoformat(timespec="seconds")
                return

            self._append_log(f"  Found {len(stale)} stale symbol(s)\n")
            self._append_log("  Sources: yfinance → NSE India → raw Yahoo v8\n")

            # 3. Process symbols with thread pool
            stats_lock = threading.Lock()

            def _do(item):
                sym, path, ld = item
                try:
                    res = _rc.refresh_symbol(sym, path, ld,
                                             force=force, dry_run=False)
                    st = res["status"]
                    with self._lock:
                        self._symbols_done += 1
                        done = self._symbols_done
                    with stats_lock:
                        if st == "updated":
                            self._progress["refreshed"] += 1
                            self._append_log(
                                f"  [{done:4d}/{len(stale)}] ✅ {sym:<20}  "
                                f"+{res['bars_added']} bars → {res['last_date']}\n")
                        elif st in ("fresh", "skipped"):
                            self._progress["skipped"] += 1
                        elif st == "no_new_data":
                            self._progress["no_data"] = self._progress.get("no_data", 0) + 1
                        else:
                            self._progress["errors"] += 1
                            self._append_log(
                                f"  [{done:4d}/{len(stale)}] ❌ {sym:<20} {st}\n")
                except Exception as ex:
                    with self._lock:
                        self._symbols_done += 1
                        self._progress["errors"] += 1
                    self._append_log(f"  ❌ {sym}: {ex}\n")

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(_do, stale))

            self._append_log(
                f"\n✅ Cache refresh complete!\n"
                f"   Refreshed  : {self._progress.get('refreshed', 0)}\n"
                f"   No new data: {self._progress.get('no_data', 0)}\n"
                f"   Skipped    : {self._progress.get('skipped', 0)}\n"
                f"   Errors     : {self._progress.get('errors', 0)}\n"
            )
            with self._lock:
                self._status = "completed"
                self._finished_at = datetime.now().isoformat(timespec="seconds")

            # Auto-regenerate analysis dashboards after cache refresh
            self._auto_regenerate_dashboards()

        except Exception as e:
            with self._lock:
                self._status = "failed"
                self._error = str(e)
                self._finished_at = datetime.now().isoformat(timespec="seconds")
            self._append_log(f"\n❌ Refresh failed: {e}\n")

    def _auto_regenerate_dashboards(self):
        """
        After cache refresh completes, auto-regenerate Market Breadth and
        Sector Macro analysis pages so they are always fresh on app start.
        Runs sequentially in the same background thread (non-blocking to server).
        """
        scripts = [
            ("Trade Plans",    GENERATE_TRADE_PLANS, TRADE_PLANS_HTML),
            ("Market Breadth", GENERATE_BREADTH, BREADTH_HTML),
            ("Sector Macro",   GENERATE_SECTOR_MACRO, SECTOR_MACRO_HTML),
        ]
        for name, script, output_path in scripts:
            if not script.exists():
                self._append_log(f"⚠ {name} script not found: {script}\n")
                continue
            self._append_log(f"\n📊 Auto-regenerating {name} dashboard…\n")
            try:
                result = subprocess.run(
                    [sys.executable, str(script)],
                    cwd=str(ROOT),
                    capture_output=True, text=True, timeout=300,
                )
                if result.returncode == 0:
                    size = output_path.stat().st_size / 1024 if output_path.exists() else 0
                    self._append_log(f"✅ {name} dashboard generated ({size:.0f} KB)\n")
                else:
                    # Log last few lines of stderr for debugging
                    err_tail = (result.stderr or result.stdout or "unknown error")[-500:]
                    self._append_log(f"❌ {name} generation failed:\n{err_tail}\n")
            except subprocess.TimeoutExpired:
                self._append_log(f"⏰ {name} generation timed out (>300s)\n")
            except Exception as e:
                self._append_log(f"❌ {name} generation error: {e}\n")

    def _append_log(self, text: str):
        with self._lock:
            self._log_tail += text
            # Keep log tail under 10KB
            if len(self._log_tail) > 10000:
                self._log_tail = self._log_tail[-8000:]


# Singleton refresher
_cache_refresher = BackgroundCacheRefresher()


# ═══════════════════════════════════════════════════════════════════════════════
#  SELECTIVE SYMBOL REFRESH (refresh specific symbols inline, thread-safe)
# ═══════════════════════════════════════════════════════════════════════════════

_symbol_refresh_lock = threading.Lock()
_recently_refreshed: dict[str, float] = {}  # canonical_sym -> timestamp
_SYMBOL_REFRESH_COOLDOWN = 300  # seconds between re-refreshes of same symbol (5 min)

# Ensure scripts/ is on sys.path once at module load
_scripts_path = str(ROOT / "scripts")
if _scripts_path not in sys.path:
    sys.path.insert(0, _scripts_path)


def _canonical_sym(symbol: str) -> str:
    """Return the canonical .NS form for cooldown tracking."""
    base = symbol.upper().replace(".NS", "").replace(".BO", "")
    return base + ".NS"


def _is_price_stale(last_date_str: str) -> bool:
    """
    Proper IST-aware staleness check (mirrors refresh_cache._is_stale logic).
    Returns True if the cache needs refreshing.
    """
    import datetime as _dt
    import zoneinfo as _zi
    if not last_date_str:
        return True
    try:
        last_date = _dt.date.fromisoformat(last_date_str)
    except ValueError:
        return True
    _ist = _zi.ZoneInfo("Asia/Kolkata")
    today = _dt.datetime.now(_ist).date()
    gap = (today - last_date).days
    if gap <= 0:
        return False
    if gap > 10:
        return True
    # Count business days in the gap
    biz = sum(1 for d in range(1, gap + 1)
              if (last_date + _dt.timedelta(days=d)).weekday() < 5)
    if biz == 0:
        return False
    # Any business day gap means stale — refresh immediately
    return True


def _refresh_symbol_if_stale(symbol: str, force: bool = False) -> bool:
    """
    Check if a symbol's cache is stale; if so, fetch latest data.
    Returns True if data was updated.
    Thread-safe with per-symbol cooldown to avoid hammering Yahoo/NSE.
    """
    canon = _canonical_sym(symbol)
    now = time.time()
    with _symbol_refresh_lock:
        last = _recently_refreshed.get(canon, 0)
        if not force and now - last < _SYMBOL_REFRESH_COOLDOWN:
            return False
        _recently_refreshed[canon] = now  # reserve slot immediately

    try:
        import refresh_cache as _rc

        base = symbol.upper().replace(".NS", "").replace(".BO", "")
        ns = base + ".NS"

        for sym in [ns, base]:
            csv_path = CACHE_DIR / f"{sym}.csv"
            last_date = _rc._read_last_date(csv_path)
            if _is_price_stale(last_date):
                result = _rc.refresh_symbol(sym, csv_path, last_date)
                status = result.get("status", "")
                if status == "updated":
                    return True
                # If no_new_data, the cache is actually fresh (market hasn't moved)
                if status == "no_new_data":
                    return False
            elif last_date:
                return False  # Already fresh

        return False
    except Exception as e:
        # Release cooldown on error so it retries sooner
        with _symbol_refresh_lock:
            _recently_refreshed.pop(canon, None)
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  LIFESPAN (startup / shutdown)
# ═══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan handler.
    On startup: kick off background OHLCV cache refresh (non-blocking).
    On shutdown: clean up.
    """
    # ── STARTUP ──
    skip_env = os.environ.get("SETUPS_SKIP_STARTUP_REFRESH", "").lower()
    if skip_env not in ("true", "1", "yes"):
        # Only auto-refresh if the script hasn't already started one
        if not _cache_refresher.is_running:
            print("🔄 Starting background OHLCV cache refresh…", flush=True)
            _cache_refresher.start(indian_only=True, workers=4)
    else:
        print("⏭  Startup cache refresh skipped (env)", flush=True)

    # ── AUTO-START BREAKOUT ALERT SCANNER ──
    # Wire up dependencies and start the background scanner so alerts
    # are sent automatically (Telegram + Gmail) without manual trigger.
    if _breakout_scanner._read_ohlcv is None:
        _breakout_scanner._read_ohlcv = _read_ohlcv
    if _breakout_scanner._load_positions_fn is None:
        def _load_open_positions_startup():
            data = _load_board()
            return data.get("positions", [])
        _breakout_scanner._load_positions_fn = _load_open_positions_startup
    config = _breakout_scanner.state.load_config()
    if config.enabled:
        print("🔔 Auto-starting breakout alert scanner (Telegram + Gmail)…", flush=True)
        _breakout_scanner.start()
    else:
        print("⏭  Breakout alert scanner disabled in config", flush=True)

    yield  # App is running

    # ── SHUTDOWN ──
    _breakout_scanner.stop()
    print("👋 Shutting down…", flush=True)


app = FastAPI(title="SETUPS Web", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Cannot use credentials=True with allow_origins=["*"] per CORS spec
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_html(request, call_next):
    """Prevent browser caching of HTML pages so UI changes take effect immediately."""
    response = await call_next(request)
    ct = response.headers.get("content-type", "")
    if "text/html" in ct:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
WEB_JOBS_DIR.mkdir(parents=True, exist_ok=True)
TRADE_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Migrate legacy trade_board.json from output/ → trade_data/positions.json
if TRADE_BOARD_JSON_LEGACY.exists() and not TRADE_BOARD_JSON.exists():
    import shutil
    shutil.copy(TRADE_BOARD_JSON_LEGACY, TRADE_BOARD_JSON)

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


@app.get("/sector")
def sector_macro_page() -> FileResponse:
    """Serve the pre-built Sector Rotation & Macro Analysis HTML page."""
    if not SECTOR_MACRO_HTML.exists():
        raise HTTPException(
            status_code=404,
            detail="Sector macro analysis page not found. Run generate_sector_macro_page.py first.",
        )
    return FileResponse(SECTOR_MACRO_HTML, media_type="text/html")


@app.post("/api/jobs/sector-macro")
def start_sector_macro_job() -> dict:
    """Trigger async regeneration of the Sector Rotation & Macro Analysis page."""
    command = [sys.executable, str(GENERATE_SECTOR_MACRO)]
    job = _submit_job("scan", command)
    return {"job": job, "message": "Sector macro analysis regeneration started"}


@app.get("/breadth")
def breadth_dashboard_page() -> FileResponse:
    """Serve the pre-built Market Breadth & Trend Detection HTML page."""
    if not BREADTH_HTML.exists():
        raise HTTPException(
            status_code=404,
            detail="Market breadth dashboard not found. It will be auto-generated after cache refresh completes, or trigger manually via POST /api/jobs/breadth.",
        )
    return FileResponse(BREADTH_HTML, media_type="text/html")


@app.post("/api/jobs/breadth")
def start_breadth_job() -> dict:
    """Trigger async regeneration of the Market Breadth dashboard."""
    command = [sys.executable, str(GENERATE_BREADTH)]
    job = _submit_job("scan", command)
    return {"job": job, "message": "Market breadth dashboard regeneration started"}


@app.get("/trades")
def trade_plans_page() -> FileResponse:
    """Serve the pre-built Live Breakout Trade Plans HTML page."""
    if not TRADE_PLANS_HTML.exists():
        raise HTTPException(
            status_code=404,
            detail="Trade plans page not found. It will be auto-generated after cache refresh completes, or trigger manually via POST /api/jobs/trade-plans. A scan must have run at least once.",
        )
    return FileResponse(TRADE_PLANS_HTML, media_type="text/html")


@app.post("/api/jobs/trade-plans")
def start_trade_plans_job() -> dict:
    """Trigger async regeneration of the Live Breakout Trade Plans page."""
    command = [sys.executable, str(GENERATE_TRADE_PLANS)]
    job = _submit_job("scan", command)
    return {"job": job, "message": "Trade plans page regeneration started"}


@app.post("/api/jobs/regenerate-all-dashboards")
def regenerate_all_dashboards() -> dict:
    """Trigger regeneration of ALL analysis dashboards (trade plans + breadth + sector macro)."""
    results = []
    for name, script in [
        ("trade-plans", GENERATE_TRADE_PLANS),
        ("breadth", GENERATE_BREADTH),
        ("sector-macro", GENERATE_SECTOR_MACRO),
    ]:
        command = [sys.executable, str(script)]
        job = _submit_job("scan", command)
        results.append({"name": name, "job_id": job.id})
    return {"ok": True, "jobs": results, "message": "All dashboards regeneration started"}


@app.get("/")
def ui_index() -> FileResponse:
    """Root page serves the Trade Board directly."""
    if not TRADE_BOARD_UI.exists():
        raise HTTPException(status_code=404, detail="Trade board UI not found")
    return FileResponse(TRADE_BOARD_UI)





@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "root": str(ROOT),
        "python": sys.version.split()[0],
        "javaHome": os.environ.get("JAVA_HOME", ""),
        "cacheRefresh": _cache_refresher.status_dict().get("status", "idle"),
        "growwEnabled": bool(_GROWW_API_KEY),
    }


# ── Cache Refresh API ─────────────────────────────────────────────────────────

class CacheRefreshRequest(BaseModel):
    symbols: list[str] | None = Field(default=None,
        description="Optional: specific symbols to refresh (e.g. ['TATASTEEL','MTARTECH'])")
    force: bool = Field(default=False,
        description="Force refresh even if cache is fresh")
    indian_only: bool = Field(default=True,
        description="Only refresh Indian (.NS/.BO) symbols")
    workers: int = Field(default=4, ge=1, le=12,
        description="Number of parallel workers")


@app.get("/api/cache/refresh-status")
def cache_refresh_status() -> dict:
    """
    Get the current status of the background OHLCV cache refresh.
    Poll this endpoint to track progress.
    """
    return _cache_refresher.status_dict()


@app.post("/api/cache/refresh")
def cache_refresh_trigger(req: CacheRefreshRequest | None = None) -> dict:
    """
    Trigger a background OHLCV cache refresh.
    Returns immediately — poll /api/cache/refresh-status for progress.
    Only one refresh can run at a time.
    """
    if req is None:
        req = CacheRefreshRequest()
    result = _cache_refresher.start(
        symbols=req.symbols,
        force=req.force,
        indian_only=req.indian_only,
        workers=req.workers,
    )
    return result


@app.post("/api/cache/refresh-symbols")
def cache_refresh_specific_symbols(symbols: list[str]) -> dict:
    """
    Synchronously refresh specific symbols' cache (for small lists like watchlist/positions).
    Use this when you need fresh data for a few stocks immediately.
    Max 20 symbols per request.
    """
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols list is empty")
    if len(symbols) > 20:
        raise HTTPException(status_code=400, detail="Max 20 symbols per request")

    results = {}
    for sym in symbols:
        sym_clean = sym.strip().upper()
        if not sym_clean:
            continue
        updated = _refresh_symbol_if_stale(sym_clean)
        results[sym_clean] = "updated" if updated else "fresh_or_cooldown"

    return {"results": results, "count": len(results)}


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

def _read_ohlcv(symbol: str, days: int = 0) -> list[dict]:
    """Read OHLCV from cache. Returns sorted list of dicts with date/open/high/low/close/volume.
    days=0 means return ALL available data.
    Prefers unified SYMBOL.csv; falls back to legacy _N.csv files.
    Triggers a background refresh if data is stale (non-blocking)."""
    base = symbol.upper().replace(".NS", "").replace(".BO", "")
    ns   = base + ".NS"

    def _read_csv(p: Path) -> dict[str, dict]:
        dm: dict[str, dict] = {}
        if not p.exists():
            return dm
        try:
            with open(p, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        d = row.get("date","") or row.get("Date","") or row.get("Datetime","")
                        if not d: continue
                        dt = d[:10]
                        cl = float(row.get("close", row.get("Close", 0)) or 0)
                        if cl <= 0: continue
                        dm[dt] = {
                            "date": dt,
                            "open":   float(row.get("open",  row.get("Open",  0)) or 0),
                            "high":   float(row.get("high",  row.get("High",  0)) or 0),
                            "low":    float(row.get("low",   row.get("Low",   0)) or 0),
                            "close":  cl,
                            "volume": float(row.get("volume",row.get("Volume",0)) or 0),
                        }
                    except Exception:
                        pass
        except Exception:
            pass
        return dm

    date_map: dict[str, dict] = {}
    for prefix in [ns, base]:
        # 1) Try unified single file first
        for fname in [f"{prefix}.csv"]:
            date_map.update(_read_csv(CACHE_DIR / fname))
        if date_map:
            break
        # 2) Legacy fallback: try _N.csv files
        for suffix in ["_5096", "_3528", "_900", "_728", "_504", "_252", "_60"]:
            for fname in [f"{prefix}{suffix}.csv"]:
                date_map.update(_read_csv(CACHE_DIR / fname))
        if date_map:
            break

    rows = sorted(date_map.values(), key=lambda r: r["date"])

    # ── Trigger background refresh if stale ──────────────────────────────
    # Non-blocking: returns current (possibly stale) data immediately;
    # refreshes in background thread so the NEXT read gets fresh data.
    # Uses IST-aware business-day logic matching refresh_cache._is_stale().
    if rows:
        last_date = rows[-1]["date"]
        if _is_price_stale(last_date):
            threading.Thread(
                target=_refresh_symbol_if_stale,
                args=(symbol,),
                daemon=True,
            ).start()
    elif not _cache_refresher.is_running:
        # No cached data at all — fetch in background
        threading.Thread(
            target=_refresh_symbol_if_stale,
            args=(symbol,),
            daemon=True,
        ).start()

    if days and days > 0 and len(rows) > days:
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

# ═══════════════════════════════════════════════════════════════════════════════
#  LIVE PRICE LAYER
# ═══════════════════════════════════════════════════════════════════════════════
# During market hours the OHLCV cache only has a stale snapshot (whatever the
# closing price was when data was last downloaded).  This layer fetches the
# actual *current* market price via NSE / Yahoo and caches it in-memory with a
# short TTL so the CMP shown in the UI stays up-to-date.

import zoneinfo as _zi
_IST = _zi.ZoneInfo("Asia/Kolkata")

_live_cache: dict[str, dict] = {}   # symbol -> {price, prevClose, ts, date}
_live_cache_lock = threading.Lock()
_LIVE_TTL_MARKET = 30    # seconds — during market hours
_LIVE_TTL_OFF = 300      # seconds — outside market hours (5 min, just to get today's close)

# ── Groww API integration ─────────────────────────────────────────────────
# Uses shared groww_client module for singleton initialization.
# Env vars: GROWW_API_KEY, GROWW_API_SECRET, GROWW_ACCESS_TOKEN
_GROWW_API_KEY = os.environ.get("GROWW_API_KEY", "")
_GROWW_API_SECRET = os.environ.get("GROWW_API_SECRET", "")
_GROWW_ACCESS_TOKEN = os.environ.get("GROWW_ACCESS_TOKEN", "")
_groww_client = None
_groww_init_lock = threading.Lock()
_groww_init_failed = False


def _get_groww_client():
    """Lazy-init singleton Groww API client — delegates to shared module."""
    global _groww_client, _groww_init_failed
    if _groww_client is not None:
        return _groww_client
    if _groww_init_failed:
        return None
    try:
        from groww_client import get_groww_client as _shared_get
        client = _shared_get()
        if client:
            _groww_client = client
            print("✅ Groww API client initialized (shared)", flush=True)
        else:
            _groww_init_failed = True
        return _groww_client
    except ImportError:
        # Fallback to inline init if shared module not found
        if not _GROWW_ACCESS_TOKEN and not _GROWW_API_KEY:
            return None
        with _groww_init_lock:
            if _groww_client is not None:
                return _groww_client
            if _groww_init_failed:
                return None
            try:
                from growwapi import GrowwAPI
                token = _GROWW_ACCESS_TOKEN
                if not token and _GROWW_API_KEY and _GROWW_API_SECRET:
                    result = GrowwAPI.get_access_token(
                        api_key=_GROWW_API_KEY, secret=_GROWW_API_SECRET)
                    if isinstance(result, str) and result:
                        token = result
                    elif isinstance(result, dict):
                        token = (result.get("accessToken")
                                 or result.get("access_token")
                                 or result.get("token", ""))
                    if not token:
                        _groww_init_failed = True
                        return None
                elif not token and _GROWW_API_KEY:
                    token = _GROWW_API_KEY
                _groww_client = GrowwAPI(token=token)
                print("✅ Groww API client initialized", flush=True)
                return _groww_client
            except Exception as e:
                print(f"⚠ Groww API init failed: {e}", flush=True)
                _groww_init_failed = True
                return None


def _fetch_live_quote_groww(base_symbol: str) -> Optional[dict]:
    """Fetch live LTP + previous close from Groww API."""
    client = _get_groww_client()
    if not client:
        return None
    try:
        from growwapi import GrowwAPI
        exchange_sym = f"NSE_{base_symbol}"
        ltp_data = client.get_ltp(
            exchange_trading_symbols=(exchange_sym,),
            segment=GrowwAPI.SEGMENT_CASH,
            timeout=8,
        )
        # Groww returns flat dict: {'NSE_SYMBOL': 866.1}
        ltp = None
        if isinstance(ltp_data, dict):
            raw = ltp_data.get(exchange_sym)
            if isinstance(raw, (int, float)) and raw > 0:
                ltp = float(raw)
            elif isinstance(raw, dict):
                ltp = raw.get("ltp") or raw.get("lastPrice")

        if ltp and ltp > 0:
            # Get prev close from OHLC call
            prev = None
            try:
                ohlc_data = client.get_ohlc(
                    exchange_trading_symbols=(exchange_sym,),
                    segment=GrowwAPI.SEGMENT_CASH,
                    timeout=8,
                )
                ohlc = ohlc_data.get(exchange_sym, {}) if isinstance(ohlc_data, dict) else {}
                prev = ohlc.get("close") or ohlc.get("previousClose")
            except Exception:
                pass
            return {"price": ltp, "prevClose": float(prev) if prev else None, "source": "groww"}
    except Exception:
        pass
    return None


def _fetch_groww_quote(base_symbol: str) -> Optional[dict]:
    """Fetch full OHLC quote from Groww API (used as fallback after get_ltp)."""
    client = _get_groww_client()
    if not client:
        return None
    try:
        from growwapi import GrowwAPI
        exchange_sym = f"NSE_{base_symbol}"
        ohlc_data = client.get_ohlc(
            exchange_trading_symbols=(exchange_sym,),
            segment=GrowwAPI.SEGMENT_CASH,
            timeout=8,
        )
        # Groww returns: {'NSE_SYMBOL': {'open':..,'high':..,'low':..,'close':..}}
        if isinstance(ohlc_data, dict):
            ohlc = ohlc_data.get(exchange_sym, {})
            close = ohlc.get("close")
            if close and float(close) > 0:
                return {"price": float(close), "prevClose": None, "source": "groww-ohlc"}
    except Exception:
        pass
    return None


def _is_market_open() -> bool:
    """Check if NSE market is likely open right now (Mon-Fri, 9:15-15:30 IST)."""
    now = datetime.now(_IST)
    if now.weekday() >= 5:  # Sat/Sun
        return False
    t = now.hour * 60 + now.minute
    return 555 <= t <= 930  # 9:15 to 15:30


def _fetch_live_quote_nse(base_symbol: str) -> Optional[dict]:
    """Fetch live quote from NSE India equity quote API."""
    import requests as _req
    try:
        import refresh_cache as _rc
        session = _rc._get_nse_session()
        import urllib.parse
        url = (
            f"https://www.nseindia.com/api/quote-equity"
            f"?symbol={urllib.parse.quote(base_symbol)}"
        )
        resp = session.get(url, headers={
            "Accept": "application/json",
            "Referer": f"https://www.nseindia.com/get-quotes/equity?symbol={urllib.parse.quote(base_symbol)}",
        }, timeout=8)
        if not resp.ok:
            return None
        data = resp.json()
        pi = data.get("priceInfo", {})
        ltp = pi.get("lastPrice")
        prev = pi.get("previousClose") or pi.get("close")
        if ltp and ltp > 0:
            return {"price": float(ltp), "prevClose": float(prev) if prev else None, "source": "nse"}
    except Exception:
        pass
    return None


def _fetch_live_quote_yahoo(symbol: str) -> Optional[dict]:
    """Fetch live quote from Yahoo v8 chart meta.regularMarketPrice."""
    import requests as _req
    import urllib.parse
    encoded = urllib.parse.quote(symbol, safe="")
    hosts = ["query2.finance.yahoo.com", "query1.finance.yahoo.com"]
    for host in hosts:
        try:
            url = f"https://{host}/v8/finance/chart/{encoded}?interval=1d&range=1d"
            resp = _req.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/json",
                "Referer": "https://finance.yahoo.com",
            }, timeout=8)
            if not resp.ok:
                continue
            result = resp.json().get("chart", {}).get("result", [])
            if result:
                meta = result[0].get("meta", {})
                rmp = meta.get("regularMarketPrice")
                pc = meta.get("previousClose", meta.get("chartPreviousClose"))
                if rmp and rmp > 0:
                    return {"price": float(rmp), "prevClose": float(pc) if pc else None, "source": "yahoo"}
        except Exception:
            continue
    return None


def _fetch_live_quote_yfinance(symbol: str) -> Optional[dict]:
    """Fetch live/latest quote via yfinance — tries fast_info then history() fallback."""
    try:
        import yfinance as yf
        tk = yf.Ticker(symbol)
        # Try fast_info first (uses v8 API internally)
        try:
            info = tk.fast_info
            ltp = getattr(info, "last_price", None)
            prev = getattr(info, "previous_close", None) or getattr(info, "regular_market_previous_close", None)
            if ltp and ltp > 0:
                return {"price": float(ltp), "prevClose": float(prev) if prev else None, "source": "yfinance"}
        except Exception:
            pass
        # Fallback: download last 5 days of history
        try:
            df = tk.history(period="5d")
            if df is not None and not df.empty:
                last_close = float(df["Close"].iloc[-1])
                prev_close = float(df["Close"].iloc[-2]) if len(df) >= 2 else None
                if last_close > 0:
                    return {"price": last_close, "prevClose": prev_close, "source": "yfinance-hist"}
        except Exception:
            pass
    except Exception:
        pass
    return None


def _get_live_price(symbol: str) -> Optional[dict]:
    """
    Get the *current* live price for a symbol.
    Returns dict: {price, prevClose, source, cached} or None.

    Priority: Groww → NSE (market hours) → Yahoo v8 → yfinance → CSV cache.
    During market hours: 30s TTL cache.
    Outside market hours: 5min TTL cache.
    """
    canon = _canonical_sym(symbol)
    base = symbol.upper().replace(".NS", "").replace(".BO", "")
    now = time.time()
    market_open = _is_market_open()
    ttl = _LIVE_TTL_MARKET if market_open else _LIVE_TTL_OFF

    # Check in-memory cache first
    with _live_cache_lock:
        cached = _live_cache.get(canon)
        if cached and (now - cached.get("ts", 0)) < ttl:
            return {**cached, "cached": True}

    quote = None

    # 1. Groww API — most reliable when API key is configured
    if not quote:
        quote = _fetch_live_quote_groww(base)
    if not quote:
        quote = _fetch_groww_quote(base)

    # 2. During market hours: try NSE (fast for live intraday)
    if not quote and market_open:
        quote = _fetch_live_quote_nse(base)

    # 3. Yahoo v8
    if not quote:
        ns_sym = base + ".NS"
        quote = _fetch_live_quote_yahoo(ns_sym)

    # 4. yfinance fallback
    if not quote:
        ns_sym = base + ".NS"
        quote = _fetch_live_quote_yfinance(ns_sym)

    if quote:
        quote["ts"] = now
        quote["symbol"] = canon
        with _live_cache_lock:
            _live_cache[canon] = quote
        return {**quote, "cached": False}

    return None


def _get_current_price(symbol: str) -> Optional[float]:
    live = _get_live_price(symbol)
    if live and live.get("price"):
        return live["price"]
    rows = _read_ohlcv(symbol, days=5)
    return rows[-1]["close"] if rows else None


def _get_price_info(symbol: str) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Returns (cmp, prev_close, last_date) for a symbol.

    During market hours: fetches LIVE price from NSE/Yahoo/yfinance APIs (30s TTL).
    Outside market hours: fetches latest close from Yahoo/yfinance (5min TTL),
      falling back to CSV cache if APIs fail.
    Always returns the most current price available.
    """
    rows = _read_ohlcv(symbol, days=5)
    csv_close = rows[-1]["close"] if rows else None
    csv_prev = rows[-2]["close"] if len(rows) >= 2 else None
    csv_date = rows[-1]["date"] if rows else None

    # Try live/latest price (works both during and outside market hours now)
    live = _get_live_price(symbol)
    if live and live.get("price"):
        cmp = live["price"]
        prev = live.get("prevClose") or csv_prev
        return cmp, prev, csv_date
    else:
        return csv_close, csv_prev, csv_date

def _compute_board_stats(positions: list[dict]) -> dict:
    """Compute aggregate stats from positions list."""
    open_pos = [p for p in positions if p.get("status") in ("OPEN", "PARTIAL")]
    closed_pos = [p for p in positions if p.get("status") not in ("OPEN", "PARTIAL")]

    total_invested = sum(
        (p.get("entry", 0) * (p.get("remaining_quantity") or p.get("quantity", 1)))
        for p in open_pos
    )
    total_pl = 0.0
    realized_pl = 0.0
    open_risk = 0.0
    locked_profit = 0.0
    day_pl = 0.0

    for p in positions:
        entry = p.get("entry", 0)
        qty   = p.get("quantity", 1)
        remaining = p.get("remaining_quantity") or qty
        cmp   = p.get("cmp", entry)
        exit_price = p.get("exit_price") or cmp
        sl    = p.get("sl", 0)
        status = p.get("status", "OPEN")

        # Add realized P&L from partial exits
        pos_realized = p.get("realized_pl", 0) or 0
        realized_pl += pos_realized

        if status in ("OPEN", "PARTIAL"):
            unrealized = (cmp - entry) * remaining
            total_pl += unrealized + pos_realized
            if sl and sl < entry:
                open_risk += (entry - sl) * remaining
            day_pl += p.get("dayChangeAmt", 0) or 0
        else:
            partial_qty_exited = sum(e.get("quantity", 0) for e in p.get("partial_exits", []))
            exit_qty = qty - partial_qty_exited
            pl = pos_realized + (exit_price - entry) * exit_qty
            total_pl += pl
            if status.startswith("T"):
                locked_profit += pl

    return {
        "total_positions": len(positions),
        "open_positions": len(open_pos),
        "closed_positions": len(closed_pos),
        "total_invested": round(total_invested, 2),
        "total_pl": round(total_pl, 2),
        "realized_pl": round(realized_pl, 2),
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
        remaining = p.get("remaining_quantity") or qty
        if p.get("status") in ("OPEN", "PARTIAL"):
            cmp, prev_close, last_date = _get_price_info(p.get("symbol", ""))
            if cmp:
                p["cmp"] = cmp
                p["gainPct"] = round((cmp - entry) / entry * 100, 2) if entry else 0
                p["gainAmt"] = round((cmp - entry) * remaining, 2) if entry else 0
                p["lastPriceDate"] = last_date
            if cmp and prev_close and prev_close > 0:
                p["dayChangePct"] = round((cmp - prev_close) / prev_close * 100, 2)
                p["dayChangeAmt"] = round((cmp - prev_close) * remaining, 2)
        elif p.get("exit_price") and entry:
            ep = float(p["exit_price"])
            p["gainPct"] = round((ep - entry) / entry * 100, 2)
            pos_realized = p.get("realized_pl", 0) or 0
            partial_qty_exited = sum(e.get("quantity", 0) for e in p.get("partial_exits", []))
            exit_qty = qty - partial_qty_exited
            p["gainAmt"] = round(pos_realized + (ep - entry) * exit_qty, 2)
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
        remaining = p.get("remaining_quantity") or qty
        if p.get("status") in ("OPEN", "PARTIAL"):
            cmp, prev_close, last_date = _get_price_info(p.get("symbol", ""))
            if cmp:
                p["cmp"] = round(cmp, 2)
                p["gainPct"] = round((cmp - entry) / entry * 100, 2) if entry else 0
                p["gainAmt"] = round((cmp - entry) * remaining, 2) if entry else 0
                p["lastPriceDate"] = last_date
            if cmp and prev_close and prev_close > 0:
                p["dayChangePct"] = round((cmp - prev_close) / prev_close * 100, 2)
                p["dayChangeAmt"] = round((cmp - prev_close) * remaining, 2)
        elif p.get("exit_price") and entry:
            # Compute final gain for closed/stopped positions
            ep = float(p["exit_price"])
            p["gainPct"] = round((ep - entry) / entry * 100, 2)
            # For positions with partial exits, total P&L = realized from partials + (exit - entry) * remaining at close
            pos_realized = p.get("realized_pl", 0) or 0
            # remaining_quantity for a fully closed position should be 0; the exit_price covers what was left
            # We need to figure out how many shares the exit_price applies to
            partial_qty_exited = sum(e.get("quantity", 0) for e in p.get("partial_exits", []))
            exit_qty = qty - partial_qty_exited  # shares closed at exit_price
            p["gainAmt"] = round(pos_realized + (ep - entry) * exit_qty, 2)
    if status:
        positions = [p for p in positions if p.get("status") == status]
    # Sort: OPEN/PARTIAL first, then by gain desc
    positions.sort(key=lambda p: (
        0 if p.get("status") in ("OPEN", "PARTIAL") else 1,
        -float(p.get("gainPct", 0) or 0)))
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
                upd = update.model_dump(exclude_unset=True)
                positions[i].update(upd)
                # If status is a closing status and exit_price is set,
                # auto-compute realized_pl for the remaining shares
                new_status = positions[i].get("status", "OPEN")
                closing_statuses = ("CLOSED", "SL_HIT", "T1_HIT", "T2_HIT", "T3_HIT")
                if new_status in closing_statuses and positions[i].get("exit_price"):
                    entry = positions[i].get("entry", 0)
                    total_qty = positions[i].get("quantity", 1)
                    exits = positions[i].get("partial_exits", [])
                    partial_qty = sum(e.get("quantity", 0) for e in exits)
                    remaining = total_qty - partial_qty
                    ep = float(positions[i]["exit_price"])
                    # Realized from partials
                    partial_realized = sum(
                        (e["price"] - entry) * e["quantity"] for e in exits
                    )
                    # Total realized = partials + final exit on remaining
                    positions[i]["realized_pl"] = round(
                        partial_realized + (ep - entry) * remaining, 2
                    )
                    positions[i]["remaining_quantity"] = 0
                    # Auto-set exit_date if not provided
                    if not positions[i].get("exit_date"):
                        positions[i]["exit_date"] = datetime.now().strftime("%Y-%m-%d")
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


@app.post("/api/trade-board/positions/{position_id}/partial-exit")
def trade_board_partial_exit(position_id: str, req: PartialExitRequest) -> dict:
    """Record a partial position exit. Reduces remaining_quantity and logs the exit."""
    with _board_lock:
        data = _load_board()
        positions = data.get("positions", [])
        for i, p in enumerate(positions):
            if p.get("id") != position_id:
                continue
            total_qty = p.get("quantity", 1)
            remaining = p.get("remaining_quantity")
            if remaining is None:
                remaining = total_qty
            # Validate
            if req.quantity <= 0:
                raise HTTPException(status_code=400, detail="quantity must be > 0")
            if req.quantity > remaining:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot exit {req.quantity} shares — only {remaining} remaining")
            # Record partial exit
            exits = p.get("partial_exits", [])
            exits.append({
                "date": req.date,
                "quantity": req.quantity,
                "price": req.price,
                "reason": req.reason,
            })
            remaining -= req.quantity
            positions[i]["partial_exits"] = exits
            positions[i]["remaining_quantity"] = remaining
            # Compute realized P&L from all partial exits
            entry = p.get("entry", 0)
            realized_pl = sum(
                (e["price"] - entry) * e["quantity"] for e in exits
            )
            positions[i]["realized_pl"] = round(realized_pl, 2)
            # Auto-update status
            if remaining <= 0:
                positions[i]["status"] = "CLOSED"
                # Compute weighted avg exit price
                total_exited = sum(e["quantity"] for e in exits)
                if total_exited > 0:
                    wavg = sum(e["price"] * e["quantity"] for e in exits) / total_exited
                    positions[i]["exit_price"] = round(wavg, 2)
                positions[i]["exit_date"] = req.date
            elif remaining < total_qty:
                positions[i]["status"] = "PARTIAL"
            data["positions"] = positions
            _save_board(data)
            return {"position": positions[i], "ok": True,
                    "remaining": remaining, "realized_pl": round(realized_pl, 2)}
    raise HTTPException(status_code=404, detail=f"Position not found: {position_id}")


def _enrich_position_metrics(p: dict) -> dict:
    """Enrich an open/watchlist position with 20EMA extension, volume records, ADR, and surfing data."""
    sym = p.get("symbol", "")
    if not sym:
        return p
    rows = _read_ohlcv(sym, days=300)  # need ~252 for yearly volume analysis
    # Inject live price into the latest bar so EMA/metrics reflect current price
    if rows:
        live = _get_live_price(sym)
        if live and live.get("price") and live["price"] > 0:
            import datetime as _dtmod
            today_str = _dtmod.datetime.now(_IST).strftime("%Y-%m-%d")
            lp = live["price"]
            if rows[-1]["date"] == today_str:
                rows[-1]["close"] = lp
                rows[-1]["high"] = max(rows[-1]["high"], lp)
                rows[-1]["low"] = min(rows[-1]["low"], lp)
            elif rows[-1]["date"] < today_str:
                rows.append({
                    "date": today_str, "open": live.get("prevClose") or rows[-1]["close"],
                    "high": lp, "low": lp, "close": lp, "volume": 0,
                })
    if not rows or len(rows) < 5:
        # Still flag IPO status even with minimal data
        if rows:
            p["ipoFlag"] = len(rows) < 126
            p["daysSinceListing"] = len(rows)
        else:
            p["ipoFlag"] = True
            p["daysSinceListing"] = 0
        return p

    # For stocks with <25 bars, set IPO flag and compute what we can
    if len(rows) < 25:
        p["ipoFlag"] = True
        p["daysSinceListing"] = len(rows)

    closes = [r["close"] for r in rows]
    highs = [r["high"] for r in rows]
    lows = [r["low"] for r in rows]
    volumes = [r["volume"] for r in rows]

    # 20 EMA
    ema20 = _calc_ema(closes, 20)
    ema5 = _calc_ema(closes, 5)
    if ema20[-1] is not None and ema20[-1] > 0:
        ext = round((closes[-1] - ema20[-1]) / ema20[-1] * 100, 2)
        dist_abs = round(closes[-1] - ema20[-1], 2)
        p["ema20"] = round(ema20[-1], 2)
        p["ema20ext"] = ext  # +ve = above, -ve = below
        p["ema20dist"] = dist_abs  # absolute distance in ₹
        # Surfing near 20EMA: price within 3% of 20EMA and above it
        p["surfing20ema"] = 0 <= ext <= 3.0
    else:
        p["ema20"] = None
        p["ema20ext"] = None
        p["ema20dist"] = None
        p["surfing20ema"] = False

    # 5EMA safety check
    if ema5[-1] is not None and ema5[-1] > 0:
        p["ema5"] = round(ema5[-1], 2)
        p["ema5Safe"] = closes[-1] >= ema5[-1]
    else:
        p["ema5"] = None
        p["ema5Safe"] = None

    # ADR (Average Daily Range) — last 20 days
    adr_period = min(20, len(rows))
    if adr_period > 0:
        recent = rows[-adr_period:]
        adr_abs = sum(r["high"] - r["low"] for r in recent) / adr_period
        adr_pct = round(adr_abs / closes[-1] * 100, 2) if closes[-1] else 0
        p["adr"] = round(adr_abs, 2)
        p["adrPct"] = adr_pct
    else:
        p["adr"] = None
        p["adrPct"] = None

    # Volume analysis
    cmp_vol = volumes[-1] if volumes else 0

    # Quarterly highest (last ~63 trading days)
    qtr_vols = volumes[-63:] if len(volumes) >= 63 else volumes
    qtr_max = max(qtr_vols) if qtr_vols else 0
    p["volHighestQtr"] = round(qtr_max)
    p["isVolHighestQtr"] = cmp_vol >= qtr_max and qtr_max > 0

    # Yearly highest (last ~252 trading days)
    yr_vols = volumes[-252:] if len(volumes) >= 252 else volumes
    yr_max = max(yr_vols) if yr_vols else 0
    p["volHighestYr"] = round(yr_max)
    p["isVolHighestYr"] = cmp_vol >= yr_max and yr_max > 0

    # Current volume vs 20-day avg
    avg20 = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else (
        sum(volumes) / len(volumes) if volumes else 1)
    p["volRatio"] = round(cmp_vol / avg20, 2) if avg20 > 0 else 0
    p["lastVol"] = round(cmp_vol)
    p["avgVol20"] = round(avg20)

    # RSI (14-period)
    rsi_vals = _calc_rsi(closes, 14)
    p["rsi"] = rsi_vals[-1] if rsi_vals and rsi_vals[-1] is not None else None

    # 52-week high/low
    yr_data = rows[-252:] if len(rows) >= 252 else rows
    high_52w = max(r["high"] for r in yr_data) if yr_data else 0
    low_52w = min(r["low"] for r in yr_data) if yr_data else 0
    p["high52w"] = round(high_52w, 2)
    p["low52w"] = round(low_52w, 2)
    p["pctFrom52wHigh"] = round((closes[-1] - high_52w) / high_52w * 100, 2) if high_52w else 0

    # SMA 200 position (trend filter)
    sma200 = _calc_sma(closes, 200)
    if sma200[-1] is not None and sma200[-1] > 0:
        p["sma200"] = round(sma200[-1], 2)
        p["aboveSma200"] = closes[-1] >= sma200[-1]
    else:
        p["sma200"] = None
        p["aboveSma200"] = None

    # Accumulation/Distribution day count (last 50 days)
    dist_days = 0
    accum_days = 0
    for i in range(max(0, len(rows) - 50), len(rows)):
        r = rows[i]
        prev = rows[i-1] if i > 0 else r
        if r["close"] < prev["close"] and r["volume"] > avg20:
            dist_days += 1
        elif r["close"] > prev["close"] and r["volume"] > avg20:
            accum_days += 1
    p["accumDays"] = accum_days
    p["distDays"] = dist_days

    # IPO flag — stock with fewer than ~126 trading days of data
    ipo_threshold = 126
    if "ipoFlag" not in p or p.get("ipoFlag") is None:
        p["ipoFlag"] = len(rows) < ipo_threshold
        p["daysSinceListing"] = len(rows)

    return p


@app.get("/api/trade-board/positions/enriched")
def trade_board_positions_enriched(status: str = "") -> dict:
    """Return positions enriched with 20EMA extension + volume records."""
    with _board_lock:
        data = _load_board()
        positions = list(data.get("positions", []))
    for p in positions:
        entry = p.get("entry", 0) or 0
        qty = p.get("quantity", 1) or 1
        remaining = p.get("remaining_quantity") or qty
        st = p.get("status", "OPEN")
        if st in ("OPEN", "PARTIAL"):
            cmp, prev_close, last_date = _get_price_info(p.get("symbol", ""))
            if cmp:
                p["cmp"] = round(cmp, 2)
                p["gainPct"] = round((cmp - entry) / entry * 100, 2) if entry else 0
                p["gainAmt"] = round((cmp - entry) * remaining, 2) if entry else 0
                p["lastPriceDate"] = last_date
            if cmp and prev_close and prev_close > 0:
                p["dayChangePct"] = round((cmp - prev_close) / prev_close * 100, 2)
                p["dayChangeAmt"] = round((cmp - prev_close) * remaining, 2)
            # Enrich with 20EMA extension + volume records + ADR
            _enrich_position_metrics(p)
        elif p.get("exit_price") and entry:
            ep = float(p["exit_price"])
            p["gainPct"] = round((ep - entry) / entry * 100, 2)
            p["gainAmt"] = round((ep - entry) * qty, 2)
    if status:
        positions = [p for p in positions if p.get("status") == status]
    positions.sort(key=lambda p: (
        0 if p.get("status") in ("OPEN", "PARTIAL") else 1,
        -float(p.get("gainPct", 0) or 0)))
    stats = _compute_board_stats(positions)
    return {"positions": positions, "stats": stats,
            "lastUpdated": data.get("lastUpdated"),
            "marketOpen": _is_market_open()}


@app.get("/api/trade-board/watchlist/enriched")
def trade_board_watchlist_enriched() -> dict:
    """Return watchlist items enriched with 20EMA extension + volume records (parallelized)."""
    from concurrent.futures import ThreadPoolExecutor
    with _watchlist_lock:
        items = _load_watchlist()
    sig_index = _load_scan_signals_index()

    def _enrich_wl(item):
        sym = item.get("symbol", "")
        cmp, prev_close, last_date = _get_price_info(sym)
        if cmp:
            item["cmp"] = round(cmp, 2)
            item["lastPriceDate"] = last_date
        if cmp and prev_close and prev_close > 0:
            item["dayChangePct"] = round((cmp - prev_close) / prev_close * 100, 2)
        _enrich_position_metrics(item)
        sig = sig_index.get(sym) or sig_index.get(sym + ".NS") or sig_index.get(sym.replace(".NS", ""))
        if sig:
            item["scanSetup"] = sig.get("setup", "")
            item["scanRating"] = sig.get("rating", "")
            item["scanScore"] = sig.get("rankingScore") or sig.get("score")
            item["scanEntry"] = sig.get("entry")
            item["scanSl"] = sig.get("sl")
            item["rsScore"] = sig.get("rsScore")
            item["regimeState"] = sig.get("regimeState")
            item["entryInstruction"] = sig.get("entryInstruction")
            item["fundSummary"] = sig.get("fundSummary")
            item["inScan"] = True
        else:
            item["inScan"] = False

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_enrich_wl, items))

    return {"items": items, "total": len(items)}


def _calc_rsi(closes: list[float], period: int = 14) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * len(closes)
    if len(closes) < period + 1:
        return result
    gains, losses = [], []
    for i in range(1, period + 1):
        delta = closes[i] - closes[i-1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = round(100 - 100 / (1 + rs), 2)
    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i-1]
        avg_gain = (avg_gain * (period - 1) + max(delta, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-delta, 0)) / period
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = round(100 - 100 / (1 + rs), 2)
    return result


def _calc_sma(closes: list[float], period: int) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * len(closes)
    if len(closes) < period:
        return result
    for i in range(period - 1, len(closes)):
        result[i] = round(sum(closes[i - period + 1: i + 1]) / period, 2)
    return result


@app.get("/api/trade-board/chart/{symbol}")
def trade_board_chart(symbol: str, days: int = 252) -> dict:
    rows = _read_ohlcv(symbol, days=max(days, 30) if days > 0 else 0)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}")

    # ── Append / update today's live bar during market hours ──────────────
    # The CSV cache only has completed daily bars.  During market hours the
    # latest bar may be yesterday's close.  Fetch live price and either
    # update today's row (if cache already has today) or append a new one.
    live = _get_live_price(symbol)
    if live and live.get("price") and live["price"] > 0:
        import datetime as _dtmod
        today_str = _dtmod.datetime.now(_IST).strftime("%Y-%m-%d")
        lp = live["price"]
        if rows[-1]["date"] == today_str:
            # Update today's bar with live price (high/low may have moved)
            rows[-1]["close"] = lp
            rows[-1]["high"] = max(rows[-1]["high"], lp)
            rows[-1]["low"] = min(rows[-1]["low"], lp)
        elif rows[-1]["date"] < today_str:
            # Append a synthetic "today" bar using live price
            prev_close = live.get("prevClose") or rows[-1]["close"]
            rows.append({
                "date": today_str,
                "open": prev_close,  # best guess for open
                "high": lp,
                "low": lp,
                "close": lp,
                "volume": 0,  # intraday volume not available from quote API
            })

    closes = [r["close"] for r in rows]
    volumes = [r["volume"] for r in rows]
    ema5   = _calc_ema(closes, 5)
    ema10  = _calc_ema(closes, 10)
    ema20  = _calc_ema(closes, 20)
    ema50  = _calc_ema(closes, 50)
    sma150 = _calc_sma(closes, 150)
    sma200 = _calc_sma(closes, 200)
    rsi14  = _calc_rsi(closes, 14)
    avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else (sum(volumes) / len(volumes) if volumes else 0)
    avg_vol_50 = sum(volumes[-50:]) / 50 if len(volumes) >= 50 else avg_vol

    # Distribution/accumulation day count (last 50 days)
    dist_days = 0
    accum_days = 0
    for i in range(max(0, len(rows) - 50), len(rows)):
        r = rows[i]
        prev = rows[i-1] if i > 0 else r
        if r["close"] < prev["close"] and r["volume"] > avg_vol:
            dist_days += 1
        elif r["close"] > prev["close"] and r["volume"] > avg_vol:
            accum_days += 1

    # 52-week high/low
    yr_data = rows[-252:] if len(rows) >= 252 else rows
    high_52w = max(r["high"] for r in yr_data) if yr_data else 0
    low_52w = min(r["low"] for r in yr_data) if yr_data else 0
    pct_from_52w_high = round((closes[-1] - high_52w) / high_52w * 100, 2) if high_52w else 0

    # ADR (Average Daily Range) — last 20 days
    adr_period = min(20, len(rows))
    if adr_period > 0:
        daily_ranges = [(r["high"] - r["low"]) for r in rows[-adr_period:]]
        adr_abs = sum(daily_ranges) / adr_period
        adr_pct = round(adr_abs / closes[-1] * 100, 2) if closes[-1] else 0
        adr_abs = round(adr_abs, 2)
    else:
        adr_abs, adr_pct = 0, 0

    for i, r in enumerate(rows):
        r["ema5"]  = ema5[i]
        r["ema10"] = ema10[i]
        r["ema20"] = ema20[i]
        r["ema50"] = ema50[i]
        r["sma150"] = sma150[i]
        r["sma200"] = sma200[i]
        r["rsi"]   = rsi14[i]
        r["volRatio"] = round(r["volume"] / avg_vol, 2) if avg_vol else None

    last_date = rows[-1]["date"] if rows else None

    return {
        "symbol": symbol, "days": len(rows), "avgVol20": round(avg_vol, 0),
        "avgVol50": round(avg_vol_50, 0),
        "cmp": closes[-1],
        "lastDate": last_date,
        "high52w": round(high_52w, 2), "low52w": round(low_52w, 2),
        "pctFrom52wHigh": pct_from_52w_high,
        "distDays50": dist_days, "accumDays50": accum_days,
        "rsi": rsi14[-1] if rsi14 and rsi14[-1] is not None else None,
        "adr": adr_abs, "adrPct": adr_pct,
        "candles": rows
    }

@app.get("/api/trade-board/equity")
def trade_board_equity() -> dict:
    """Compute equity curve from closed+open positions, including partial exits."""
    with _board_lock:
        data = _load_board()
        positions = data.get("positions", [])
    curve = []
    total = 0.0

    # Collect all exit events (full closes + partial exits)
    events: list[dict] = []
    for p in positions:
        entry = p.get("entry", 0)
        qty = p.get("quantity", 1)
        status = p.get("status", "OPEN")
        sym = p.get("symbol", "")

        # Add partial exit events
        for pe in p.get("partial_exits", []):
            pl = (pe["price"] - entry) * pe["quantity"]
            events.append({
                "date": pe.get("date", p.get("entry_date", "")),
                "symbol": sym,
                "pl": round(pl, 2),
                "status": f"PARTIAL ({pe.get('reason', '')})",
                "type": "partial",
            })

        # Add full close event (only for fully closed, not already counted via partials)
        if status not in ("OPEN", "PARTIAL"):
            partial_qty = sum(pe["quantity"] for pe in p.get("partial_exits", []))
            if partial_qty == 0:
                # Full close without partial exits
                exit_p = p.get("exit_price") or entry
                pl = (exit_p - entry) * qty
                events.append({
                    "date": p.get("exit_date") or p.get("entry_date", ""),
                    "symbol": sym,
                    "pl": round(pl, 2),
                    "status": status,
                    "type": "close",
                })
            # If partials covered full qty, they're already in events

    events.sort(key=lambda e: e.get("date", ""))
    for ev in events:
        total += ev["pl"]
        curve.append({**ev, "cumPl": round(total, 2)})

    return {"curve": curve, "totalPl": round(total, 2)}

@app.get("/api/trade-board/scan-signals")
def trade_board_scan_signals(market: str = "india", timeframe: str = "daily") -> dict:
    """Return top open trade signals from scan output for quick import, enriched with vol/RS data."""
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
                # Normalize and enrich fields
                for s in signals:
                    if "rankingScore" not in s:
                        s["rankingScore"] = s.get("score", 0)
                    # Normalize vol% field
                    vol_raw = s.get("vol%", s.get("vol_pct"))
                    try:
                        s["volPct"] = round(float(vol_raw), 1) if vol_raw not in (None, "", "0.0") else None
                    except (ValueError, TypeError):
                        s["volPct"] = None
                    # Normalize dist% field
                    dist_raw = s.get("distFromPivot%", s.get("dist%", s.get("distance_from_pivot_pct", s.get("distFromPivot%"))))
                    try:
                        s["distPct"] = round(float(dist_raw), 1) if dist_raw not in (None, "", "0.0") else None
                    except (ValueError, TypeError):
                        s["distPct"] = None
                    # Avg volume
                    try:
                        s["avgVol20"] = round(float(s.get("avgVol20", 0))) if s.get("avgVol20") else None
                    except (ValueError, TypeError):
                        s["avgVol20"] = None
                    try:
                        s["lastVol"] = round(float(s.get("lastVol", 0))) if s.get("lastVol") else None
                    except (ValueError, TypeError):
                        s["lastVol"] = None
                    # RS data
                    try:
                        s["rsScore"] = round(float(s.get("rsScore", 0)), 1) if s.get("rsScore") else None
                    except (ValueError, TypeError):
                        s["rsScore"] = None
                    try:
                        s["rs3m"] = round(float(s.get("rs3m", 0)), 1) if s.get("rs3m") else None
                    except (ValueError, TypeError):
                        s["rs3m"] = None
                    try:
                        s["rs6m"] = round(float(s.get("rs6m", 0)), 1) if s.get("rs6m") else None
                    except (ValueError, TypeError):
                        s["rs6m"] = None

                signals.sort(key=lambda x: -float(x.get("rankingScore") or x.get("score") or 0))
                return {"signals": signals[:40], "total": len(signals), "source": json_path.name}
        except Exception:
            pass
    return {"signals": [], "total": 0}


# ── Trade Journal ──────────────────────────────────────────────────────────────
_journal_lock = threading.Lock()

def _load_journal() -> list:
    if not TRADE_JOURNAL_JSON.exists():
        return []
    try:
        return json.loads(TRADE_JOURNAL_JSON.read_text(encoding="utf-8"))
    except Exception:
        return []

def _save_journal(entries: list) -> None:
    TRADE_JOURNAL_JSON.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")

class JournalEntry(BaseModel):
    symbol: str = ""
    date: str = ""
    title: str = ""
    body: str = ""
    mood: str = ""   # bullish/bearish/neutral
    tags: list[str] = Field(default_factory=list)

@app.get("/api/trade-journal")
def get_journal(symbol: str = "", limit: int = 100) -> dict:
    with _journal_lock:
        entries = _load_journal()
    if symbol:
        entries = [e for e in entries if e.get("symbol","").upper() == symbol.upper()]
    entries.sort(key=lambda e: e.get("date",""), reverse=True)
    return {"entries": entries[:limit], "total": len(entries)}

@app.post("/api/trade-journal")
def add_journal_entry(entry: JournalEntry) -> dict:
    with _journal_lock:
        entries = _load_journal()
        rec = entry.model_dump()
        rec["id"] = str(uuid.uuid4())
        rec["created_at"] = datetime.now().isoformat(timespec="seconds")
        if not rec.get("date"):
            rec["date"] = datetime.now().strftime("%Y-%m-%d")
        entries.append(rec)
        _save_journal(entries)
    return {"ok": True, "entry": rec}

@app.delete("/api/trade-journal/{entry_id}")
def delete_journal_entry(entry_id: str) -> dict:
    with _journal_lock:
        entries = _load_journal()
        before = len(entries)
        entries = [e for e in entries if e.get("id") != entry_id]
        if len(entries) == before:
            raise HTTPException(status_code=404, detail="Journal entry not found")
        _save_journal(entries)
    return {"ok": True, "deleted": entry_id}


# ── Trade Watchlist ────────────────────────────────────────────────────────────
_watchlist_lock = threading.Lock()

def _load_watchlist() -> list:
    if not TRADE_WATCHLIST_JSON.exists():
        return []
    try:
        return json.loads(TRADE_WATCHLIST_JSON.read_text(encoding="utf-8"))
    except Exception:
        return []

def _save_watchlist(items: list) -> None:
    TRADE_WATCHLIST_JSON.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

class WatchlistItem(BaseModel):
    symbol: str
    name: str = ""
    notes: str = ""
    alert_price: Optional[float] = None
    setup: str = ""

@app.get("/api/trade-board/watchlist")
def get_watchlist() -> dict:
    with _watchlist_lock:
        items = _load_watchlist()
    # Enrich with CMP, day change, and scan signal data
    sig_index = _load_scan_signals_index()
    for item in items:
        sym = item.get("symbol", "")
        cmp, prev_close, last_date = _get_price_info(sym)
        if cmp:
            item["cmp"] = round(cmp, 2)
            item["lastPriceDate"] = last_date
        if cmp and prev_close and prev_close > 0:
            item["dayChangePct"] = round((cmp - prev_close) / prev_close * 100, 2)
        # Merge scan signal data if available
        sig = sig_index.get(sym) or sig_index.get(sym + ".NS") or sig_index.get(sym.replace(".NS", ""))
        if sig:
            item["scanSetup"] = sig.get("setup", "")
            item["scanRating"] = sig.get("rating", "")
            item["scanScore"] = sig.get("rankingScore") or sig.get("score")
            item["scanEntry"] = sig.get("entry")
            item["scanSl"] = sig.get("sl")
            item["rsScore"] = sig.get("rsScore")
            item["regimeState"] = sig.get("regimeState")
            item["entryInstruction"] = sig.get("entryInstruction")
            item["inScan"] = True
        else:
            item["inScan"] = False
    return {"items": items, "total": len(items)}

@app.post("/api/trade-board/watchlist")
def add_watchlist_item(item: WatchlistItem) -> dict:
    with _watchlist_lock:
        items = _load_watchlist()
        # Check for duplicate
        if any(i.get("symbol","").upper() == item.symbol.upper() for i in items):
            raise HTTPException(status_code=409, detail=f"{item.symbol} already in watchlist")
        rec = item.model_dump()
        rec["id"] = str(uuid.uuid4())
        rec["added_at"] = datetime.now().isoformat(timespec="seconds")
        items.append(rec)
        _save_watchlist(items)
    return {"ok": True, "item": rec}

@app.delete("/api/trade-board/watchlist/{item_id}")
def remove_watchlist_item(item_id: str) -> dict:
    with _watchlist_lock:
        items = _load_watchlist()
        before = len(items)
        items = [i for i in items if i.get("id") != item_id]
        if len(items) == before:
            raise HTTPException(status_code=404, detail="Watchlist item not found")
        _save_watchlist(items)
    return {"ok": True, "deleted": item_id}


# ── Market Overview ────────────────────────────────────────────────────────────

def _load_scan_signals_index(market: str = "india", timeframe: str = "daily") -> dict[str, dict]:
    """Load latest scan signals into a symbol → record dict for quick lookup."""
    suffix = f"{market}_{timeframe}_full"
    for name in [f"open_trades_{suffix}_LATEST.json", f"vcp_hits_{suffix}_LATEST.json"]:
        p = OUTPUT_DIR / name
        if not p.exists():
            continue
        try:
            signals = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(signals, list) and signals:
                return {s.get("symbol", ""): s for s in signals}
        except Exception:
            pass
    return {}


@app.get("/api/trade-board/market-overview")
def trade_board_market_overview(market: str = "india", timeframe: str = "daily") -> dict:
    """Compact market regime + breadth + scan hit counts for the board strip."""
    result: dict = {"regime": None, "summary": None}

    # Regime from scan bundle
    bundle_path = OUTPUT_DIR / f"scan_bundle_{market}_{timeframe}_full_LATEST.json"
    if bundle_path.exists():
        try:
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            result["regime"] = bundle.get("meta", {}).get("regime")
            result["generatedAt"] = bundle.get("generatedAt")
            result["counts"] = bundle.get("counts")
        except Exception:
            pass

    # Hit counts from system summary
    summary_path = OUTPUT_DIR / "system_latest_summary.json"
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            for r in summary.get("results", []):
                if r.get("market") == market and r.get("timeframe") == timeframe:
                    result["summary"] = {
                        "hits": r.get("hits", 0),
                        "watchlistHits": r.get("watchlistHits", 0),
                        "portfolioPicks": r.get("portfolioPicks", 0),
                        "setupBreakdown": r.get("variationBreakdown", {}).get("setup", {}),
                        "ratingBreakdown": r.get("variationBreakdown", {}).get("rating", {}),
                    }
                    break
        except Exception:
            pass

    return result


@app.get("/api/trade-board/price-debug")
def price_debug(symbols: str = "") -> dict:
    """
    Debug endpoint: shows exactly where each symbol's price comes from.
    ?symbols=MTARTECH,ATHERENERG  or leave blank for open positions + watchlist.
    """
    if symbols:
        sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    else:
        with _board_lock:
            board = _load_board()
        with _watchlist_lock:
            wl = _load_watchlist()
        pos_syms = [p["symbol"] for p in board.get("positions", [])
                    if p.get("status") in ("OPEN", "PARTIAL") and p.get("symbol")]
        wl_syms = [w["symbol"] for w in wl if w.get("symbol")]
        sym_list = list(dict.fromkeys(pos_syms + wl_syms))

    results = []
    for sym in sym_list[:20]:
        canon = _canonical_sym(sym)
        # Flush in-memory cache to force a fresh fetch
        with _live_cache_lock:
            _live_cache.pop(canon, None)

        live = _get_live_price(sym)

        rows = _read_ohlcv(sym, days=3)
        csv_close = rows[-1]["close"] if rows else None
        csv_date  = rows[-1]["date"]  if rows else None

        results.append({
            "symbol":       sym,
            "live_price":   live.get("price")     if live else None,
            "prev_close":   live.get("prevClose")  if live else None,
            "source":       live.get("source")     if live else "none — CSV cache used",
            "cached":       live.get("cached")     if live else None,
            "csv_close":    csv_close,
            "csv_date":     csv_date,
            "market_open":  _is_market_open(),
        })

    return {
        "results":            results,
        "groww_enabled":      bool(_GROWW_API_KEY or _GROWW_ACCESS_TOKEN),
        "groww_client_ready": _groww_client is not None,
        "groww_init_failed":  _groww_init_failed,
        "market_open":        _is_market_open(),
    }


# ── Trade Board Export / Backup ────────────────────────────────────────────────
@app.get("/api/trade-board/export")
def export_trade_data() -> dict:
    """Export all trade data (positions + journal + watchlist) as one JSON bundle."""
    with _board_lock:
        positions = _load_board()
    with _journal_lock:
        journal = _load_journal()
    with _watchlist_lock:
        watchlist = _load_watchlist()
    return {
        "exported_at": datetime.now().isoformat(),
        "positions": positions,
        "journal": journal,
        "watchlist": watchlist,
    }


# ── Force Price Refresh ────────────────────────────────────────────────────────

@app.post("/api/trade-board/refresh-prices")
def refresh_prices_now() -> dict:
    """
    Force-refresh live prices for all OPEN positions + watchlist symbols.

    • Flushes the in-memory live price cache so next API call fetches fresh quotes.
    • During market hours: NSE/Yahoo live quotes update within the next request.
    • Also kicks off background OHLCV cache refresh for stale symbols.
    """
    # Collect symbols
    with _board_lock:
        board_data = _load_board()
        positions = board_data.get("positions", [])
    open_syms = [
        p["symbol"] for p in positions
        if p.get("status") in ("OPEN", "PARTIAL") and p.get("symbol")
    ]
    with _watchlist_lock:
        watchlist = _load_watchlist()
    wl_syms = [w["symbol"] for w in watchlist if w.get("symbol")]

    # Deduplicate (max 30)
    all_syms = list({s.upper() for s in (open_syms + wl_syms)})[:30]

    if not all_syms:
        return {"ok": True, "symbols": [], "count": 0, "message": "Nothing to refresh"}

    # 1. Flush the live price cache so next read gets fresh quotes
    with _live_cache_lock:
        for sym in all_syms:
            canon = _canonical_sym(sym)
            _live_cache.pop(canon, None)

    # 2. Also clear OHLCV refresh cooldown and kick off background CSV update
    with _symbol_refresh_lock:
        for sym in all_syms:
            canon = _canonical_sym(sym)
            _recently_refreshed.pop(canon, None)

    def _run_bg():
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(4, len(all_syms))) as pool:
            pool.map(lambda s: _refresh_symbol_if_stale(s, force=True), all_syms)

    threading.Thread(target=_run_bg, daemon=True).start()

    return {
        "ok": True,
        "symbols": all_syms,
        "count": len(all_syms),
        "marketOpen": _is_market_open(),
        "message": f"Live cache flushed for {len(all_syms)} symbols — prices refresh on next load",
    }


@app.get("/api/trade-board/price-data")
def get_price_data_for_symbols(symbols: str = "") -> dict:
    """
    Get current CMP + day-change for a comma-separated list of symbols.
    Reads directly from cache — call after refresh-prices completes.
    """
    if not symbols:
        return {"prices": {}}
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    prices: dict[str, dict] = {}
    for sym in sym_list[:30]:
        cmp, prev, last_date = _get_price_info(sym)
        if cmp:
            prices[sym] = {
                "cmp": round(cmp, 2),
                "prevClose": round(prev, 2) if prev else None,
                "dayChangePct": round((cmp - prev) / prev * 100, 2) if prev and prev > 0 else None,
                "lastDate": last_date,
                "isStale": _is_price_stale(last_date) if last_date else True,
            }
    return {"prices": prices, "count": len(prices)}


# ═══════════════════════════════════════════════════════════════════════════════
#  BREAKOUT CANDLE ALERT SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

class BreakoutAlertConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    scan_interval_seconds: Optional[int] = None
    volume_threshold: Optional[float] = None
    volume_avg_bars: Optional[int] = None
    volume_strong_threshold: Optional[float] = None
    body_ratio_min: Optional[float] = None
    close_near_high_pct: Optional[float] = None
    min_base_bars: Optional[int] = None
    max_base_range_pct: Optional[float] = None
    consolidation_days: Optional[int] = None
    consolidation_max_range_pct: Optional[float] = None
    atr_breakout_multiple: Optional[float] = None
    # Telegram (free)
    telegram_enabled: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    # Gmail (free)
    email_enabled: Optional[bool] = None
    gmail_address: Optional[str] = None
    gmail_app_password: Optional[str] = None
    email_to: Optional[str] = None


@app.get("/api/breakout-alerts/status")
def breakout_alert_status() -> dict:
    """Get breakout alert scanner status and configuration."""
    config = _breakout_scanner.state.load_config()
    from dataclasses import asdict as _asdict
    return {
        "scanner": _breakout_scanner.status(),
        "config": {k: v for k, v in _asdict(config).items()
                   if k not in ("gmail_app_password",)},  # hide secret
        "marketOpen": _is_market_open(),
    }


@app.post("/api/breakout-alerts/config")
def update_breakout_alert_config(update: BreakoutAlertConfigUpdate) -> dict:
    """Update breakout alert configuration."""
    config = _breakout_scanner.state.load_config()
    from dataclasses import asdict as _asdict
    data = _asdict(config)
    for k, v in update.model_dump(exclude_unset=True).items():
        if k in data:
            data[k] = v
    new_config = AlertConfig(**data)
    _breakout_scanner.state.save_config(new_config)
    return {"ok": True, "config": {k: v for k, v in _asdict(new_config).items()
                                    if k not in ("gmail_app_password",)}}


@app.post("/api/breakout-alerts/scan-now")
def breakout_scan_now(symbols: list[str] | None = None, intraday: bool = True) -> dict:
    """Run an immediate breakout scan. intraday=True uses live 15-min candles."""
    if _breakout_scanner._read_ohlcv is None:
        _breakout_scanner._read_ohlcv = _read_ohlcv
    results = _breakout_scanner.scan_now(symbols=symbols, intraday=intraday)
    return {
        "signals": results,
        "count": len(results),
        "mode": "intraday_15m" if intraday else "daily",
        "scannedAt": datetime.now().isoformat(timespec="seconds"),
    }


@app.post("/api/breakout-alerts/start")
def breakout_scanner_start() -> dict:
    """Start the background breakout scanner."""
    if _breakout_scanner._read_ohlcv is None:
        _breakout_scanner._read_ohlcv = _read_ohlcv
    if _breakout_scanner._load_positions_fn is None:
        def _load_open_positions():
            with _board_lock:
                data = _load_board()
                return data.get("positions", [])
        _breakout_scanner._load_positions_fn = _load_open_positions
    _breakout_scanner.start()
    return {"ok": True, "message": "Breakout scanner started"}


@app.post("/api/breakout-alerts/stop")
def breakout_scanner_stop() -> dict:
    """Stop the background breakout scanner."""
    _breakout_scanner.stop()
    return {"ok": True, "message": "Breakout scanner stopped"}


@app.get("/api/breakout-alerts/signals")
def breakout_alert_signals(limit: int = 50) -> dict:
    """Get recent breakout signals (persisted history)."""
    signals = _breakout_scanner.state.load_signals()
    signals.sort(key=lambda s: s.get("detected_at", ""), reverse=True)
    return {"signals": signals[:limit], "total": len(signals)}


@app.post("/api/breakout-alerts/backtest")
def breakout_backtest(
    symbols: list[str] | None = None,
    hold_days: int = 20,
) -> dict:
    """
    Backtest breakout detection on watchlist stocks.
    Validates that the detection criteria work on historical data.
    Returns win rate, expectancy, profit factor, and individual trades.
    """
    if _breakout_scanner._read_ohlcv is None:
        _breakout_scanner._read_ohlcv = _read_ohlcv
    result = _breakout_scanner.backtest_watchlist(symbols=symbols, hold_days=hold_days)
    return result


@app.get("/api/breakout-alerts/backtest-results")
def breakout_backtest_results() -> dict:
    """Get cached backtest results."""
    return _breakout_scanner.state.load_backtest()


@app.post("/api/breakout-alerts/test-alert")
def test_alert_channels() -> dict:
    """Send a test alert via all enabled channels (Telegram / Gmail)."""
    config = _breakout_scanner.state.load_config()
    results = {}

    if config.telegram_enabled:
        ok = send_telegram_text(
            "🧪 *SETUPS Breakout Alert System — TEST*\n\n"
            "✅ Telegram alerts are working!\n"
            "You'll receive breakout candle alerts here when detected on your watchlist.",
            config,
        )
        results["telegram"] = "sent" if ok else "failed"
    else:
        results["telegram"] = "disabled"

    if config.email_enabled:
        from breakout_alert_engine import BreakoutSignal, send_email_alert
        test_signal = BreakoutSignal(
            symbol="TEST", signal_type="BREAKOUT",
            date=datetime.now().strftime("%Y-%m-%d"),
            price=100.0, close=100.0, high=102.0, low=95.0, open_price=96.0,
            volume=1000000, avg_volume_20=500000, volume_ratio=2.0,
            body_ratio=0.71, close_position=0.85,
            breakout_level=98.0, breakout_level_type="52W_HIGH",
            atr_14=3.5, atr_multiple=2.0,
            consolidation_days=25, consolidation_range_pct=8.5,
            strength_score=82, entry_price=100.0, stop_loss=95.0,
            target_1=110.0, target_2=117.5, risk_reward=5.0,
            notes="🧪 TEST ALERT — Breakout Alert System working!",
        )
        ok = send_email_alert(test_signal, config)
        results["email"] = "sent" if ok else "failed"
    else:
        results["email"] = "disabled"

    any_sent = any(v == "sent" for v in results.values())
    return {
        "ok": any_sent,
        "results": results,
        "message": "Test alert sent!" if any_sent else "No channels enabled or all failed. Configure Telegram or Gmail first.",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ── Position 5 EMA Proximity Alerts ──────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

# Track alerted position EMA keys to avoid duplicate alerts
_ema5_alerted_keys: set = set()


@app.get("/api/position-alerts/ema5-check")
def position_ema5_check(threshold: float = 1.5) -> dict:
    """
    Check all open positions for 5 EMA proximity.
    Returns alerts for positions where price is approaching/touching/below 5 EMA.
    """
    with _board_lock:
        data = _load_board()
        positions = data.get("positions", [])

    open_positions = [p for p in positions if p.get("status") in ("OPEN", "PARTIAL")]
    if not open_positions:
        return {"alerts": [], "message": "No open positions", "checkedAt": datetime.now().isoformat(timespec="seconds")}

    alerts = []
    for p in open_positions:
        sym = p.get("symbol", "")
        entry = p.get("entry", 0)
        if not sym or not entry:
            continue
        try:
            rows = _read_ohlcv(sym, days=60)
            if not rows or len(rows) < 10:
                continue
            alert = check_position_ema5_proximity(rows, sym, entry, threshold_pct=threshold)
            if alert:
                from dataclasses import asdict as _ad
                d = _ad(alert)
                d["position_id"] = p.get("id", "")
                d["sl"] = p.get("sl", 0)
                d["remaining_qty"] = p.get("remaining_quantity") or p.get("quantity", 1)
                alerts.append(d)
        except Exception as e:
            print(f"  ⚠ EMA5 check {sym}: {e}", flush=True)

    # Sort: broken > touched > approaching
    priority = {"EMA5_BROKEN": 0, "EMA5_TOUCHED": 1, "EMA5_APPROACHING": 2}
    alerts.sort(key=lambda a: priority.get(a.get("alert_type", ""), 9))

    return {
        "alerts": alerts,
        "count": len(alerts),
        "totalOpen": len(open_positions),
        "checkedAt": datetime.now().isoformat(timespec="seconds"),
    }


@app.post("/api/position-alerts/ema5-scan-send")
def position_ema5_scan_and_alert(threshold: float = 1.5) -> dict:
    """
    Scan open positions for 5 EMA proximity AND send Telegram alerts for new ones.
    Deduplicates: won't re-alert the same symbol+type+date combo.
    """
    global _ema5_alerted_keys
    check_result = position_ema5_check(threshold)
    alerts = check_result.get("alerts", [])
    config = _breakout_scanner.state.load_config()

    new_alerts = []
    for a in alerts:
        key = f"{a['symbol']}:{a['date']}:{a['alert_type']}"
        if key not in _ema5_alerted_keys:
            _ema5_alerted_keys.add(key)
            new_alerts.append(a)

    sent_count = 0
    for a in new_alerts:
        alert_obj = EmaProximityAlert(
            symbol=a["symbol"], alert_type=a["alert_type"],
            price=a["price"], ema5=a["ema5"], ema5_dist_pct=a["ema5_dist_pct"],
            ema20=a["ema20"], ema20_dist_pct=a["ema20_dist_pct"],
            entry_price=a["entry_price"], gain_pct=a["gain_pct"],
            adr_pct=a["adr_pct"], date=a["date"], notes=a["notes"],
        )
        ok = send_ema5_telegram_alert(alert_obj, config)
        if ok:
            sent_count += 1
            print(f"  📉 EMA5 alert sent: {a['symbol']} {a['alert_type']} ₹{a['price']}", flush=True)

    return {
        "alerts": alerts,
        "newAlerts": len(new_alerts),
        "telegramSent": sent_count,
        "checkedAt": datetime.now().isoformat(timespec="seconds"),
    }
