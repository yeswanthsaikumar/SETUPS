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
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = ROOT / "output"
CLI_DIR = ROOT / "apps" / "python" / "cli"
PY_LIB_DIR = ROOT / "apps" / "python" / "lib"
UI_INDEX = ROOT / "apps" / "web" / "ui" / "index.html"
TRADE_BOARD_UI = ROOT / "apps" / "web" / "ui" / "trade_board.html"
INDUSTRY_GROUPS_UI = ROOT / "apps" / "web" / "ui" / "industry_groups.html"
SECTOR_MACRO_HTML = OUTPUT_DIR / "sector_macro_analysis.html"
GENERATE_SECTOR_MACRO = CLI_DIR / "generate_sector_macro_page.py"
BREADTH_HTML = OUTPUT_DIR / "market_breadth.html"
GENERATE_BREADTH = CLI_DIR / "generate_breadth_dashboard.py"
TRADE_PLANS_HTML = OUTPUT_DIR / "trade_plans_live.html"
GENERATE_TRADE_PLANS = CLI_DIR / "generate_trade_plans_page.py"
WEB_JOBS_DIR = OUTPUT_DIR / "web_jobs"
PERF_TRACKER_JSON = OUTPUT_DIR / "performance_tracker.json"
# Trade data stored in dedicated folder (not output/) so it survives output/ cleanups.
# Honor SETUPS_TRADE_DATA_DIR / SETUPS_CACHE_DIR env vars so tests (and other
# embeddings) can point the app at a clean directory without editing code.
_TD_ENV = os.environ.get("SETUPS_TRADE_DATA_DIR", "").strip()
TRADE_DATA_DIR = Path(_TD_ENV) if _TD_ENV else ROOT / "trade_data"
TRADE_BOARD_JSON = TRADE_DATA_DIR / "positions.json"
TRADE_JOURNAL_JSON = TRADE_DATA_DIR / "journal.json"
TRADE_WATCHLIST_JSON = TRADE_DATA_DIR / "watchlist.json"
TRADE_BOARD_JSON_LEGACY = OUTPUT_DIR / "trade_board.json"  # kept for migration only
_CD_ENV = os.environ.get("SETUPS_CACHE_DIR", "").strip()
CACHE_DIR = Path(_CD_ENV) if _CD_ENV else ROOT / "cache"
REFRESH_CACHE_SCRIPT = ROOT / "scripts" / "refresh_cache.py"
REFRESH_LOG = OUTPUT_DIR / "cache_refresh.log"

sys.path.insert(0, str(PY_LIB_DIR))
from stock_analyzer import analyze_stock
import trading_wisdom
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
from vpn_manager import get_vpn_manager

_mf_provider = MutualFundsProvider(cache_dir=str(ROOT / "cache"), cache_ttl_hours=6)

# ── VPN / Proxy manager (singleton) ────────────────────────────────────────
# Persisted state lives in trade_data/ so it survives output/ cleanups.
_vpn = get_vpn_manager(ROOT / "trade_data" / "vpn_config.json")

# ── Breakout Alert Scanner (singleton) ──────────────────────────────────────
_breakout_scanner = BreakoutScanner(
    data_dir=TRADE_DATA_DIR,
    cache_dir=CACHE_DIR,
)

RUN_VCP_SYSTEM = CLI_DIR / "run_vcp_system.py"
RUN_BACKTEST = CLI_DIR / "run_backtest.py"




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
    kind: Literal["backtest"]
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
    # Captures initial stop so closed-trade R uses original risk, not trailed SL.
    original_sl: Optional[float] = None


class PartialExitRequest(BaseModel):
    quantity: Optional[int] = None
    exit_all: bool = False
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
            # Surface the REAL source priority + live Groww status so log
            # readers know why updates might be empty.
            try:
                sys.path.insert(0, str(ROOT / "apps" / "python" / "lib"))
                from groww_client import (  # type: ignore
                    is_groww_available, groww_only_mode)
                gw_live = is_groww_available()
                gw_only = groww_only_mode()
            except Exception:
                gw_live, gw_only = False, False
            self._append_log(
                f"  Sources: Groww → yfinance → NSE India → raw Yahoo v8"
                f"   [groww_available={gw_live}, groww_only={gw_only}]\n"
            )
            if not gw_live:
                self._append_log(
                    "  ⚠ Groww client unavailable — set GROWW_ACCESS_TOKEN "
                    "(or GROWW_API_KEY + GROWW_API_SECRET) and restart. "
                    "Falling back to rate-limited Yahoo/NSE will mostly return no_data.\n"
                )

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

            # Invalidate industry-groups cache so /api/industry-groups rebuilds
            # using freshly-landed OHLCV data. Runs in a background thread so
            # it doesn't block the HTTP worker.
            try:
                global _INDUSTRY_CACHE_TS
                _INDUSTRY_CACHE_TS = 0
                self._append_log("\n🏭 Invalidating industry-groups cache — recomputing from fresh CSVs…\n")
                _bg_refresh_industry_groups()
            except Exception as _e:
                self._append_log(f"⚠ Industry-groups invalidation error: {_e}\n")

            # Also invalidate the RS-universe scan cache so the next call to
            # the RS leaders endpoint picks up today's closes for CMP / scores.
            try:
                with _rs_scan_lock:
                    _rs_scan_cache["ts"] = 0
                self._append_log("📊 Invalidated RS-universe scan cache (CMP will refresh on next request)\n")
            except Exception as _e:
                self._append_log(f"⚠ RS-scan cache invalidation error: {_e}\n")

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
#  PERIODIC CACHE REFRESH SCHEDULER
#  Triggers a full OHLCV cache refresh every N seconds (default 3600 = 1 hour).
#  The underlying BackgroundCacheRefresher._run also invalidates the
#  industry-groups cache and RS-universe scan cache at the end, so every tick
#  transitively refreshes those derived datasets too.
# ═══════════════════════════════════════════════════════════════════════════════

class PeriodicCacheRefreshScheduler:
    """Fires BackgroundCacheRefresher.start() on a fixed interval.

    • Interval via env SETUPS_REFRESH_INTERVAL_SECONDS (default 3600).
    • Disabled via env SETUPS_DISABLE_PERIODIC_REFRESH=true.
    • Skips a tick if a refresh is already running (no overlap).
    • Daemon thread; stop() is idempotent.
    """

    def __init__(self, refresher: "BackgroundCacheRefresher",
                 interval_seconds: int = 3600):
        self._refresher = refresher
        self._interval = max(60, int(interval_seconds))  # floor 60s
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_tick_at: Optional[str] = None
        self._tick_count: int = 0

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status_dict(self) -> dict:
        return {
            "running": self.is_running,
            "intervalSeconds": self._interval,
            "lastTickAt": self._last_tick_at,
            "tickCount": self._tick_count,
        }

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._loop, name="periodic-cache-refresh", daemon=True)
        self._thread.start()
        print(f"⏱  Periodic cache refresh scheduled every "
              f"{self._interval}s ({self._interval // 60} min)", flush=True)

    def stop(self) -> None:
        self._stop_evt.set()

    def _loop(self) -> None:
        # Wait one full interval before the first scheduled tick — the
        # startup refresh already kicked off once in lifespan().
        while not self._stop_evt.wait(self._interval):
            try:
                if self._refresher.is_running:
                    print("⏱  Periodic tick skipped — refresh still running",
                          flush=True)
                    continue
                self._tick_count += 1
                self._last_tick_at = datetime.now().isoformat(timespec="seconds")
                print(f"⏱  Periodic cache refresh tick #{self._tick_count} "
                      f"at {self._last_tick_at}", flush=True)
                self._refresher.start(indian_only=True, workers=4, force=False)
            except Exception as e:
                print(f"⚠ Periodic refresh tick error: {e}", flush=True)


_periodic_refresher = PeriodicCacheRefreshScheduler(
    _cache_refresher,
    interval_seconds=int(os.environ.get("SETUPS_REFRESH_INTERVAL_SECONDS", "3600")),
)


# ═══════════════════════════════════════════════════════════════════════════════
#  DAILY POST-CLOSE REFRESH SCHEDULER  (wall-clock, IST-pinned)
#
#  The hourly PeriodicCacheRefreshScheduler ticks on elapsed time from startup,
#  which means nothing guarantees a refresh lands *after* NSE's 15:30 close
#  cutoff (15:35 IST in `_is_price_stale`). If the server was started at, say,
#  15:10 IST, the next tick isn't until 16:10 IST, so the Industry Groups page
#  keeps showing pre-close intraday values for up to an hour.
#
#  This scheduler fires a single wall-clock refresh every weekday at
#  SETUPS_POSTCLOSE_REFRESH_IST (default "15:40"), forcing today's finalized
#  close into every CSV. End of that refresh also recomputes industry-groups
#  and RS-scan caches (see BackgroundCacheRefresher._run).
# ═══════════════════════════════════════════════════════════════════════════════

class PostCloseRefreshScheduler:
    """Fires one BackgroundCacheRefresher.start(force=True) per weekday at a
    fixed IST wall-clock time (default 15:40 IST, ~10 min after NSE close).

    • Disabled via env SETUPS_DISABLE_POSTCLOSE_REFRESH=true.
    • Time configurable via env SETUPS_POSTCLOSE_REFRESH_IST="HH:MM".
    • Skips weekends.
    • If the target time has already passed for *today* at startup and no
      refresh has landed after the cutoff, fires once immediately.
    • Daemon thread; stop() is idempotent.
    """

    def __init__(self, refresher: "BackgroundCacheRefresher",
                 ist_hhmm: str = "15:40"):
        self._refresher = refresher
        try:
            hh, mm = ist_hhmm.strip().split(":")
            self._hour = max(0, min(23, int(hh)))
            self._minute = max(0, min(59, int(mm)))
        except Exception:
            self._hour, self._minute = 15, 40
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_fire_at: Optional[str] = None
        self._fire_count: int = 0

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status_dict(self) -> dict:
        return {
            "running": self.is_running,
            "istTime": f"{self._hour:02d}:{self._minute:02d}",
            "lastFireAt": self._last_fire_at,
            "fireCount": self._fire_count,
        }

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._loop, name="postclose-cache-refresh", daemon=True)
        self._thread.start()
        print(f"⏰ Post-close refresh scheduled daily at "
              f"{self._hour:02d}:{self._minute:02d} IST (Mon–Fri)", flush=True)

    def stop(self) -> None:
        self._stop_evt.set()

    def _next_fire_delay(self) -> float:
        """Seconds until the next weekday fire instant in IST."""
        import datetime as _dt
        import zoneinfo as _zi
        ist = _zi.ZoneInfo("Asia/Kolkata")
        now = _dt.datetime.now(ist)
        target = now.replace(hour=self._hour, minute=self._minute,
                             second=0, microsecond=0)
        # If we've already passed today's target, aim for tomorrow.
        if target <= now:
            target = target + _dt.timedelta(days=1)
        # Skip weekends (Sat=5, Sun=6).
        while target.weekday() >= 5:
            target = target + _dt.timedelta(days=1)
        return max(1.0, (target - now).total_seconds())

    def _should_fire_now(self) -> bool:
        """True if we're past today's target on a weekday and no CSV has been
        refreshed since — used for the one-shot catch-up at startup."""
        import datetime as _dt
        import zoneinfo as _zi
        ist = _zi.ZoneInfo("Asia/Kolkata")
        now = ist_now = _dt.datetime.now(ist)
        if now.weekday() >= 5:
            return False
        target = now.replace(hour=self._hour, minute=self._minute,
                             second=0, microsecond=0)
        if now < target:
            return False
        # If any representative CSV in the cache was written after today's
        # target, a post-close refresh already ran — don't duplicate.
        try:
            probe = CACHE_DIR / "RELIANCE.NS.csv"
            if probe.exists():
                mtime = _dt.datetime.fromtimestamp(probe.stat().st_mtime, tz=ist)
                if mtime >= target:
                    return False
        except Exception:
            pass
        return True

    def _loop(self) -> None:
        # One-shot catch-up: if server started after today's close but before
        # any refresh landed, fire immediately (after a brief delay so we
        # don't fight the startup refresh for CPU/network).
        try:
            if self._should_fire_now():
                self._stop_evt.wait(60)
                if not self._stop_evt.is_set():
                    self._fire("startup-catchup")
        except Exception as e:
            print(f"⚠ Post-close startup catch-up error: {e}", flush=True)

        # Daily loop: sleep until next IST target, fire, repeat.
        while not self._stop_evt.is_set():
            delay = self._next_fire_delay()
            if self._stop_evt.wait(delay):
                return
            try:
                self._fire("scheduled")
            except Exception as e:
                print(f"⚠ Post-close fire error: {e}", flush=True)

    def _fire(self, reason: str) -> None:
        if self._refresher.is_running:
            print(f"⏰ Post-close tick ({reason}) skipped — refresh already running",
                  flush=True)
            return
        self._fire_count += 1
        self._last_fire_at = datetime.now().isoformat(timespec="seconds")
        print(f"⏰ Post-close cache refresh fire #{self._fire_count} "
              f"({reason}) at {self._last_fire_at}", flush=True)
        # force=True so yfinance re-fetches today's bar even if the CSV
        # already has a same-date intraday snapshot.
        self._refresher.start(indian_only=True, workers=4, force=True)


_postclose_refresher = PostCloseRefreshScheduler(
    _cache_refresher,
    ist_hhmm=os.environ.get("SETUPS_POSTCLOSE_REFRESH_IST", "15:40"),
)


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


def _is_price_stale(last_date_str: str, csv_path: Path | None = None) -> bool:
    """
    Proper IST-aware staleness check (mirrors refresh_cache._is_stale logic).
    Returns True if the cache needs refreshing.

    Beyond date-gap, also flags intraday snapshots captured during market hours
    as stale once market closes — i.e. if the file's mtime is before 15:35 IST
    on today and we're now past 15:35 IST, the bar is NOT today's final close.
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
    now_ist = _dt.datetime.now(_ist)
    today = now_ist.date()
    gap = (today - last_date).days
    if gap > 0:
        if gap > 10:
            return True
        biz = sum(1 for d in range(1, gap + 1)
                  if (last_date + _dt.timedelta(days=d)).weekday() < 5)
        return biz > 0

    # last_date == today → cache has today's bar. Might be an intraday snapshot.
    if csv_path is not None and today.weekday() < 5:
        close_cutoff = now_ist.replace(hour=15, minute=35, second=0, microsecond=0)
        try:
            mtime = _dt.datetime.fromtimestamp(csv_path.stat().st_mtime, tz=_ist)
        except OSError:
            return False
        if now_ist >= close_cutoff and mtime < close_cutoff:
            return True
        # Pre-close: if the file was written earlier today (not in the last
        # few minutes), treat as stale so reads trigger a refresh that will
        # drop the in-progress bar and pull the finalized prior-day close.
        if now_ist < close_cutoff and mtime.date() == today \
                and (now_ist - mtime).total_seconds() > 300:
            return True
    return False


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
            if force or _is_price_stale(last_date, csv_path):
                result = _rc.refresh_symbol(sym, csv_path, last_date, force=force)
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
    force_env = os.environ.get("SETUPS_STARTUP_FORCE_REFRESH", "").lower()
    if skip_env not in ("true", "1", "yes"):
        # Only auto-refresh if the script hasn't already started one
        if not _cache_refresher.is_running:
            force_flag = force_env in ("true", "1", "yes")
            label = " (FORCE)" if force_flag else ""
            print(f"🔄 Starting background OHLCV cache refresh{label}…", flush=True)
            _cache_refresher.start(indian_only=True, workers=4, force=force_flag)
    else:
        print("⏭  Startup cache refresh skipped (env)", flush=True)

    # ── PERIODIC HOURLY CACHE REFRESH ──
    # Fires BackgroundCacheRefresher every SETUPS_REFRESH_INTERVAL_SECONDS
    # (default 3600). Refresh also invalidates industry-groups + RS-scan caches.
    if os.environ.get("SETUPS_DISABLE_PERIODIC_REFRESH", "").lower() in ("true", "1", "yes"):
        print("⏭  Periodic cache refresh disabled (env)", flush=True)
    else:
        _periodic_refresher.start()

    # ── DAILY POST-CLOSE REFRESH (wall-clock IST) ──
    # Guarantees today's finalized 3:30 PM close lands into CSVs at ~15:40 IST
    # regardless of when the server started. See PostCloseRefreshScheduler.
    if os.environ.get("SETUPS_DISABLE_POSTCLOSE_REFRESH", "").lower() in ("true", "1", "yes"):
        print("⏭  Post-close cache refresh disabled (env)", flush=True)
    else:
        _postclose_refresher.start()

    # ── EARNINGS CACHE PRE-WARM ──
    # Disabled by default — fetching earnings for all watchlist symbols on every
    # startup is noisy and slow (many delisted symbols produce warnings).
    # Set SETUPS_ENABLE_EARNINGS_PREWARM=true to opt back in.
    if os.environ.get("SETUPS_ENABLE_EARNINGS_PREWARM", "").lower() in ("true", "1", "yes"):
        try:
            _prewarm_earnings_cache()
        except Exception as _e:
            print(f"⚠ earnings prewarm skipped: {_e}", flush=True)
    else:
        print("⏭  Earnings prewarm skipped (set SETUPS_ENABLE_EARNINGS_PREWARM=true to enable)", flush=True)

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

    # ── TRADE-DATA BACKUP (once per day — iCloud + Telegram) ──
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from icloud_backup import run_backup_background
        run_backup_background()
    except Exception as e:
        print(f"☁️  Backup init failed: {e}", flush=True)

    yield  # App is running

    # ── SHUTDOWN ──
    _breakout_scanner.stop()
    try:
        _periodic_refresher.stop()
    except Exception:
        pass
    try:
        _postclose_refresher.stop()
    except Exception:
        pass
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

# Mount the UI folder so wisdom.js (and any future static UI assets) are
# reachable by the browser at /ui/wisdom.js.  Kept read-only — anything
# dynamic stays behind an API route.
_UI_DIR = TRADE_BOARD_UI.parent
if _UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(_UI_DIR)), name="ui")


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


# ── Wisdom-layer HTML helper ───────────────────────────────────────────────
# The sector/breadth/trades pages are generated as static HTML by the CLI
# scripts and written into output/.  They don't go through a template engine,
# so we can't add the wisdom <script> tag there without rerunning the scan.
# Instead we inject it at serve time — one line, deterministic, and nothing
# to keep in sync across four generators.
_WISDOM_SCRIPT_TAG = (
    '<script defer src="/ui/wisdom.js"></script>'
    '<!-- injected by serve_with_wisdom() -->'
)


def _serve_with_wisdom(path: Path, media_type: str = "text/html") -> Response:
    """Serve a static HTML file with the wisdom reminder layer injected
    right before </body>.  Falls back to untouched content if </body> isn't
    found — we never want an injection bug to 500 a page.
    """
    try:
        html = path.read_text(encoding="utf-8")
    except Exception:
        raise HTTPException(status_code=500, detail="could not read page")
    if _WISDOM_SCRIPT_TAG not in html:
        idx = html.rfind("</body>")
        if idx != -1:
            html = html[:idx] + _WISDOM_SCRIPT_TAG + html[idx:]
        else:
            html = html + _WISDOM_SCRIPT_TAG
    return Response(content=html, media_type=media_type)


@app.get("/sector")
def sector_macro_page() -> Response:
    """Serve the pre-built Sector Rotation & Macro Analysis HTML page."""
    if not SECTOR_MACRO_HTML.exists():
        raise HTTPException(
            status_code=404,
            detail="Sector macro analysis page not found. Run generate_sector_macro_page.py first.",
        )
    return _serve_with_wisdom(SECTOR_MACRO_HTML)


@app.post("/api/jobs/sector-macro")
def start_sector_macro_job() -> dict:
    """Trigger async regeneration of the Sector Rotation & Macro Analysis page."""
    command = [sys.executable, str(GENERATE_SECTOR_MACRO)]
    job = _submit_job("scan", command)
    return {"job": job, "message": "Sector macro analysis regeneration started"}


@app.get("/breadth")
def breadth_dashboard_page() -> Response:
    """Serve the pre-built Market Breadth & Trend Detection HTML page."""
    if not BREADTH_HTML.exists():
        raise HTTPException(
            status_code=404,
            detail="Market breadth dashboard not found. It will be auto-generated after cache refresh completes, or trigger manually via POST /api/jobs/breadth.",
        )
    return _serve_with_wisdom(BREADTH_HTML)


@app.post("/api/jobs/breadth")
def start_breadth_job() -> dict:
    """Trigger async regeneration of the Market Breadth dashboard."""
    command = [sys.executable, str(GENERATE_BREADTH)]
    job = _submit_job("scan", command)
    return {"job": job, "message": "Market breadth dashboard regeneration started"}


@app.get("/groups")
def industry_groups_page() -> FileResponse:
    """Serve the Industry Groups RS & Rotation UI page."""
    if not INDUSTRY_GROUPS_UI.exists():
        raise HTTPException(status_code=404, detail="Industry groups UI not found")
    return FileResponse(INDUSTRY_GROUPS_UI)


# ── Trading Playbook (daily read) ────────────────────────────────────────────
# Serves docs/TRADING_PLAYBOOK.md (and its evidence companion) through three
# surfaces:
#   GET /playbook                         → styled reader UI (?doc=evidence to
#                                            load the companion document)
#   GET /api/playbook/markdown[?doc=…]    → raw markdown source
#   GET /api/playbook/download[?doc=…]    → self-contained HTML, print-to-PDF
_PLAYBOOK_UI_PATH = ROOT / "apps" / "web" / "ui" / "playbook.html"
# ── _PLAYBOOK_DOCS ────────────────────────────────────────────────────────────
# To add a new blog post / wisdom doc:
#   1. Drop a .md file into docs/
#   2. Add an entry below with category="blog" (category="core" for ref docs).
#   3. Restart the server — the UI auto-discovers it via /api/playbook/meta.
_PLAYBOOK_DOCS: dict[str, dict] = {
    # ── Core reference docs ───────────────────────────────────────────────────
    "playbook": {
        "path":     ROOT / "docs" / "TRADING_PLAYBOOK.md",
        "title":    "The Trading Playbook",
        "dek":      "Why chart patterns work, which ones actually pay, and the "
                    "distilled philosophies of the traders who pioneered them.",
        "file":     "Trading_Playbook.html",
        "category": "core",
        "icon":     "📖",
        "order":    1,
    },
    "evidence": {
        "path":     ROOT / "docs" / "TRADING_PLAYBOOK_EVIDENCE.md",
        "title":    "Trading Playbook · Evidence",
        "dek":      "Hard statistics, audited track records, and academic research "
                    "behind every claim in the playbook.",
        "file":     "Trading_Playbook_Evidence.html",
        "category": "core",
        "icon":     "🔬",
        "order":    2,
    },
    # ── Wisdom blog posts ─────────────────────────────────────────────────────
    "livermore": {
        "path":     ROOT / "docs" / "JESSE_LIVERMORE_WISDOM.md",
        "title":    "Jesse Livermore — The Complete Wisdom",
        "dek":      "Time-tested principles, entries, exits, position sizing, "
                    "psychology, checklists, 50 quotes, and daily affirmations "
                    "from the trader who made $100M shorting the 1929 crash.",
        "file":     "Jesse_Livermore_Wisdom.html",
        "category": "blog",
        "icon":     "🎯",
        "order":    1,
    },
    "impulse-control-trading": {
        "path":     ROOT / "docs" / "IMPULSE_CONTROL_TRADING.md",
        "title":    "The Anti-Impulse Trading Protocol",
        "dek":      "A professional guide to avoiding immediate buys, greedy "
                    "entries, panic selling, phone-driven over-monitoring, and "
                    "emotion-led rule breaks using calm process and Mark Douglas "
                    "style probabilistic thinking.",
        "file":     "Impulse_Control_Trading.html",
        "category": "blog",
        "icon":     "🧠",
        "order":    2,
    },
    "chart-pattern-trade-plans": {
        "path":     ROOT / "docs" / "CHART_PATTERN_TRADE_PLANS.md",
        "title":    "Chart Patterns & Trade Plans",
        "dek":      "A daily price-action and volume playbook covering bull flags, "
                    "triangles, cup-and-handle, VCP, double bottoms, reversals, "
                    "trade plans, stops, targets, invalidation, and pattern failure "
                    "signs.",
        "file":     "Chart_Pattern_Trade_Plans.html",
        "category": "blog",
        "icon":     "📈",
        "order":    3,
    },
}


def _resolve_playbook_doc(doc: str | None) -> dict:
    key = (doc or "playbook").strip().lower()
    if key not in _PLAYBOOK_DOCS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown doc {key!r}; expected one of "
                   f"{sorted(_PLAYBOOK_DOCS)}",
        )
    meta = _PLAYBOOK_DOCS[key]
    if not meta["path"].exists():
        raise HTTPException(
            status_code=404,
            detail=f"source markdown missing: {meta['path'].name}",
        )
    return meta


@app.get("/playbook")
def playbook_page() -> FileResponse:
    """Serve the reader UI. The client picks the doc via ?doc=evidence."""
    if not _PLAYBOOK_UI_PATH.exists():
        raise HTTPException(status_code=404, detail="Playbook UI not found")
    return FileResponse(_PLAYBOOK_UI_PATH, media_type="text/html")


@app.get("/api/playbook/markdown")
def playbook_markdown(doc: str = "playbook") -> Response:
    """Raw markdown source (default: playbook; doc=evidence for companion)."""
    meta = _resolve_playbook_doc(doc)
    text = meta["path"].read_text(encoding="utf-8")
    return Response(
        content=text,
        media_type="text/markdown; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/playbook/meta")
def playbook_meta() -> dict:
    """List available documents grouped by category.

    Each entry includes: key, title, dek, category, icon, order.
    The UI uses category to render Core docs vs Wisdom Blog posts separately.
    Adding a new .md + entry in _PLAYBOOK_DOCS is the only step needed to
    surface a new blog post in the UI.
    """
    docs = [
        {
            "key":      k,
            "title":    v["title"],
            "dek":      v["dek"],
            "category": v.get("category", "core"),
            "icon":     v.get("icon", "📄"),
            "order":    v.get("order", 99),
        }
        for k, v in _PLAYBOOK_DOCS.items()
        if v["path"].exists()
    ]
    docs.sort(key=lambda d: (d["category"] != "core", d["order"]))
    return {"docs": docs}


@app.get("/api/playbook/download")
def playbook_download(doc: str = "playbook") -> Response:
    """Self-contained HTML (no network). Save-as-PDF friendly."""
    meta = _resolve_playbook_doc(doc)
    md = meta["path"].read_text(encoding="utf-8")

    # Tiny server-side markdown → HTML. Handles the subset the playbook uses:
    # # h1 / ## h2 / ### h3 / #### h4, bold/italic/code, blockquote, ordered +
    # unordered lists, fenced code, horizontal rule, GFM tables, inline links.
    # Good enough to produce a clean printable artefact without any third-
    # party deps on the server side.
    import html as _html
    import re as _re

    def _inline(s: str) -> str:
        s = _html.escape(s)
        # code spans first (protect them from further subs)
        s = _re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        # bold, italic
        s = _re.sub(r"\*\*([^\*]+)\*\*", r"<strong>\1</strong>", s)
        s = _re.sub(r"(?<!\w)\*([^\*]+)\*", r"<em>\1</em>", s)
        s = _re.sub(r"(?<!_)_([^_]+)_(?!\w)", r"<em>\1</em>", s)
        # links [text](url)
        s = _re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        return s

    def _slug(text: str) -> str:
        t = _re.sub(r"<[^>]+>", "", text).lower()
        t = _re.sub(r"[^\w\s-]", "", t).strip()
        return _re.sub(r"\s+", "-", t) or "section"

    lines = md.splitlines()
    out: list[str] = []
    i = 0
    in_code = False
    while i < len(lines):
        ln = lines[i]
        stripped = ln.rstrip()
        if stripped.startswith("```"):
            if not in_code:
                out.append("<pre><code>")
                in_code = True
            else:
                out.append("</code></pre>")
                in_code = False
            i += 1
            continue
        if in_code:
            out.append(_html.escape(ln))
            i += 1
            continue
        if not stripped.strip():
            out.append("")
            i += 1
            continue
        # Horizontal rule
        if _re.match(r"^\s*---+\s*$", stripped):
            out.append("<hr/>")
            i += 1
            continue
        # Headings
        m = _re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            text = _inline(m.group(2).rstrip("#").strip())
            slug = _slug(text)
            out.append(f'<h{level} id="{slug}">{text}</h{level}>')
            i += 1
            continue
        # Blockquote (consecutive lines starting with >)
        if stripped.startswith(">"):
            block = []
            while i < len(lines) and lines[i].startswith(">"):
                block.append(_inline(lines[i].lstrip("> ").rstrip()))
                i += 1
            out.append("<blockquote><p>" + "<br/>".join(block) + "</p></blockquote>")
            continue
        # GFM table: header | separator | rows
        if "|" in stripped and i + 1 < len(lines) and _re.match(
                r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
            header_cells = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2  # skip separator row
            rows: list[list[str]] = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            th = "".join(f"<th>{_inline(c)}</th>" for c in header_cells)
            tr_list = []
            for r in rows:
                td = "".join(f"<td>{_inline(c)}</td>" for c in r)
                tr_list.append(f"<tr>{td}</tr>")
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>"
                       f"{''.join(tr_list)}</tbody></table>")
            continue
        # Ordered list
        m = _re.match(r"^(\s*)(\d+)\.\s+(.*)$", stripped)
        if m:
            items = []
            while i < len(lines):
                mm = _re.match(r"^(\s*)(\d+)\.\s+(.*)$", lines[i])
                if not mm:
                    break
                items.append(_inline(mm.group(3)))
                i += 1
            out.append("<ol>" + "".join(f"<li>{x}</li>" for x in items) + "</ol>")
            continue
        # Unordered list
        m = _re.match(r"^(\s*)[\-\*]\s+(.*)$", stripped)
        if m:
            items = []
            while i < len(lines):
                mm = _re.match(r"^(\s*)[\-\*]\s+(.*)$", lines[i])
                if not mm:
                    break
                items.append(_inline(mm.group(2)))
                i += 1
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>")
            continue
        # Paragraph (collapse consecutive non-blank non-special lines)
        para = [_inline(stripped)]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            if not nxt.strip():
                break
            if _re.match(r"^(#{1,6}\s|>|\s*---+\s*$|```|\s*[\-\*]\s|\s*\d+\.\s)",
                         nxt):
                break
            if "|" in nxt and i + 1 < len(lines) and _re.match(
                    r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
                break
            para.append(_inline(nxt.rstrip()))
            i += 1
        out.append("<p>" + " ".join(para) + "</p>")

    body_html = "\n".join(out)

    # Print-friendly shell. No external CSS / JS so it works offline forever.
    page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"/>
<title>{_html.escape(meta['title'])} — Printable Edition</title>
<style>
  @page {{ size: A4; margin: 18mm 16mm 20mm; }}
  html,body{{margin:0;padding:0;background:#fff;color:#111;
    font-family:Georgia,'Times New Roman',serif;font-size:11pt;line-height:1.55}}
  .container{{max-width:760px;margin:24px auto;padding:0 28px}}
  h1,h2,h3,h4{{font-family:Georgia,serif;color:#111;letter-spacing:-.2px}}
  h1{{font-size:26pt;border-bottom:2px solid #b8830c;padding-bottom:8px;margin:28pt 0 14pt;page-break-before:always}}
  h1:first-of-type{{page-break-before:auto;margin-top:0;text-align:center;border:none;font-size:32pt}}
  h2{{font-size:16pt;color:#8a5a00;margin:22pt 0 8pt}}
  h3{{font-size:13pt;margin:16pt 0 6pt}}
  h4{{font-size:11pt;color:#444;margin:12pt 0 4pt}}
  p{{margin:0 0 10pt}}
  ul,ol{{margin:0 0 10pt;padding-left:22pt}}
  li{{margin:3pt 0}}
  blockquote{{margin:10pt 0;padding:8pt 14pt;border-left:3px solid #b8830c;
    background:#faf4e4;font-style:italic;color:#444}}
  code{{font-family:Menlo,Consolas,monospace;background:#f5f2ea;padding:1pt 4pt;
    border-radius:2pt;font-size:.85em}}
  pre{{background:#f5f2ea;border:1px solid #e2dccc;border-radius:4pt;padding:10pt;
    overflow:auto;page-break-inside:avoid}}
  pre code{{background:none;padding:0;font-size:.82em}}
  table{{border-collapse:collapse;width:100%;margin:10pt 0;font-family:Arial,sans-serif;
    font-size:.9em;page-break-inside:avoid}}
  th,td{{border:1px solid #d9d6cc;padding:6pt 8pt;text-align:left;vertical-align:top}}
  th{{background:#f5f2ea;color:#8a5a00;font-weight:700;text-transform:uppercase;font-size:.85em;letter-spacing:.4px}}
  hr{{border:0;border-top:1px solid #d9d6cc;margin:18pt 0}}
  a{{color:#1d4ed8;text-decoration:none}}
  .cover{{text-align:center;margin:0 0 26pt;padding:0 0 20pt;border-bottom:1px solid #d9d6cc}}
  .cover .eyebrow{{font-family:Arial,sans-serif;letter-spacing:3px;text-transform:uppercase;
    color:#b8830c;font-size:9pt;font-weight:700;margin-bottom:8pt}}
  .cover .dek{{font-style:italic;color:#555;font-size:12pt;max-width:520px;margin:10pt auto 0;line-height:1.45}}
  .meta{{font-family:Arial,sans-serif;color:#888;font-size:9pt;margin-top:12pt}}
  .print-hint{{text-align:center;background:#fff5d6;border:1px solid #e8c566;
    border-radius:6pt;padding:10pt 14pt;margin:14pt 0;font-family:Arial,sans-serif;font-size:10pt;color:#7a5a00}}
  @media print {{ .print-hint {{ display:none }} }}
</style>
</head>
<body>
<div class="container">
  <div class="cover">
    <div class="eyebrow">SETUPS · Offline Edition</div>
    <div style="font-size:30pt;font-weight:700;color:#111;font-family:Georgia,serif">{_html.escape(meta['title'])}</div>
    <div class="dek">{_html.escape(meta['dek'])}</div>
    <div class="meta">Generated {_html.escape(datetime.now().strftime('%B %d, %Y'))}
      · source: <code>docs/{_html.escape(meta['path'].name)}</code></div>
  </div>
  <div class="print-hint">💡 This is a self-contained printable copy.
    Press <strong>Cmd+P</strong> (Mac) or <strong>Ctrl+P</strong> (Windows)
    and choose <em>Save as PDF</em> for a permanent offline reference.</div>
  {body_html}
</div>
</body></html>"""

    return Response(
        content=page,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{meta["file"]}"',
            "Cache-Control": "no-store",
        },
    )


# ── Quarterly Earnings Results Dashboard ─────────────────────────────────────
# Aggregates historical + upcoming earnings for positions / watchlist / custom
# symbol sets into three actionable buckets:
#   • UPCOMING within N days  → AVOID (volatility risk)
#   • BEAT (surprise ≥ +5% or gap ≥ +4%) → PEG / post-earnings-drift candidates
#   • MISS (surprise ≤ −5% or gap ≤ −4%) → AVOID / EXIT
# The idea: stay out of results, enter after they print strong.
_EARNINGS_UI_PATH = ROOT / "apps" / "web" / "ui" / "earnings.html"
_EARNINGS_CACHE_PATH = TRADE_DATA_DIR / "earnings_cache.json"
_NSE_EARNINGS_CACHE_PATH = TRADE_DATA_DIR / "nse_events_cache.json"
_earnings_provider = None  # lazy — avoid import cost at module load


def _get_earnings_provider():
    global _earnings_provider
    if _earnings_provider is None:
        from earnings_provider import EarningsProvider
        _earnings_provider = EarningsProvider(
            cache_path=_EARNINGS_CACHE_PATH,
            ttl_hours=24.0,
            max_workers=3,
            revalidate_after_hours=6.0,
            # NSE India merge — authoritative source for Indian tickers.
            nse_cache_path=_NSE_EARNINGS_CACHE_PATH,
            # Let NSE-only events be classified via our local OHLCV cache —
            # no extra Yahoo round-trip needed.
            ohlcv_reader=_read_ohlcv,
        )
    return _earnings_provider


def _prewarm_earnings_cache() -> None:
    """Kick off a background fetch of every symbol in positions + watchlist
    on server boot. Non-blocking — uses the provider's internal daemon thread.
    """
    try:
        raw = _collect_scope_symbols("all")
        if not raw:
            return
        names: dict[str, str] = {}
        for bare, name in raw:
            yf_sym = _normalise_symbol_for_yf(bare)
            names[yf_sym] = name or bare
        _get_earnings_provider().prewarm(list(names), names=names)
        print(f"📊 earnings prewarm: scheduled {len(names)} symbols", flush=True)
    except Exception as e:  # pragma: no cover
        print(f"⚠ earnings prewarm failed: {e}", flush=True)


def _collect_scope_symbols(scope: str) -> list[tuple[str, str]]:
    """Return ``[(symbol, display_name), …]`` for the requested scope.

    ``scope`` ∈ {"positions", "watchlist", "all"}. Unknown → "all".
    """
    pairs: dict[str, str] = {}  # symbol → name (last-wins)

    if scope in {"positions", "all"}:
        try:
            data = json.loads(TRADE_BOARD_JSON.read_text(encoding="utf-8"))
            for p in data.get("positions", []) or []:
                sym = (p.get("symbol") or "").strip()
                if not sym:
                    continue
                pairs[sym] = p.get("name") or sym
        except Exception:
            pass

    if scope in {"watchlist", "all"}:
        try:
            items = json.loads(TRADE_WATCHLIST_JSON.read_text(encoding="utf-8"))
            if isinstance(items, list):
                for w in items:
                    sym = (w.get("symbol") or "").strip()
                    if not sym:
                        continue
                    pairs[sym] = w.get("name") or sym
        except Exception:
            pass

    return [(s, n) for s, n in pairs.items()]


def _normalise_symbol_for_yf(symbol: str, market_hint: str | None = None) -> str:
    """Append ``.NS`` for Indian tickers missing a suffix.

    Positions store bare ``MTARTECH``; yfinance expects ``MTARTECH.NS``. US
    tickers already lack a suffix and Yahoo accepts them as-is.
    """
    s = symbol.strip().upper()
    if "." in s or "-" in s:
        return s
    # Heuristic: alphabetic-only tickers of length ≤5 and confirmed US market
    # stay unsuffixed; anything else (likely India) gets .NS.
    if market_hint and market_hint.lower() == "us":
        return s
    return s + ".NS"


@app.get("/earnings")
def earnings_page() -> FileResponse:
    """Serve the quarterly results dashboard UI."""
    if not _EARNINGS_UI_PATH.exists():
        raise HTTPException(status_code=404, detail="Earnings dashboard UI not found")
    return FileResponse(_EARNINGS_UI_PATH, media_type="text/html")


@app.get("/api/earnings/quarterly")
def earnings_quarterly(
    scope: str = "all",
    days_ahead: int = 14,
    days_back: int = 45,
    force: bool = False,
) -> dict:
    """Return classified earnings events for the requested scope.

    Parameters
    ----------
    scope : {"positions", "watchlist", "all"}
    days_ahead : events scheduled within this many days → ``UPCOMING``
    days_back  : events reported within this many days → ``BEAT|MISS|INLINE``
    force      : bypass the 12h cache and refetch from Yahoo
    """
    from earnings_provider import summarize
    scope = (scope or "all").lower()
    if scope not in {"positions", "watchlist", "all"}:
        scope = "all"

    raw = _collect_scope_symbols(scope)
    if not raw:
        return {
            "scope": scope, "symbols": 0, "totals": {},
            "buckets": {"upcoming": [], "beats": [], "misses": [], "inline": []},
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "note": "No symbols in scope — add positions or watchlist entries.",
        }

    # Map bare → yfinance-suffixed; keep display name off the bare symbol.
    yf_map: dict[str, str] = {}  # yf_sym → display
    display_by_bare: dict[str, str] = {}  # bare → name
    for bare, name in raw:
        yf_sym = _normalise_symbol_for_yf(bare)
        yf_map[yf_sym] = name or bare
        display_by_bare[bare] = name or bare

    provider = _get_earnings_provider()
    events = provider.fetch_many(list(yf_map), names=yf_map, force=force)

    # Restrict to the caller's window
    today = datetime.utcnow().date()
    kept = []
    # Track the newest known event per symbol so we can report coverage gaps.
    latest_by_sym: dict[str, tuple[str, int]] = {}  # bare → (date, days_until)
    for e in events:
        try:
            d = datetime.fromisoformat(e.date).date()
        except Exception:
            continue
        delta = (d - today).days
        bare = e.symbol.replace(".NS", "")
        # Record latest known event for coverage reporting
        prev = latest_by_sym.get(bare)
        if prev is None or d.isoformat() > prev[0]:
            latest_by_sym[bare] = (d.isoformat(), delta)
        if delta > days_ahead or delta < -days_back:
            continue
        # Re-expose a bare-symbol-friendly alias for the UI
        e.symbol = bare  # type: ignore[misc]
        if not e.name and bare in display_by_bare:
            e.name = display_by_bare[bare]
        kept.append(e)

    summary = summarize(kept)

    # Build a "stale coverage" list: symbols that exist in scope + have
    # some cached data, but whose latest event is outside the days_back
    # window. Lets the user see WHY a name (e.g. ANANDRATHI) is missing.
    stale: list[dict] = []
    for bare, display in display_by_bare.items():
        latest = latest_by_sym.get(bare)
        if not latest:
            # No events ever fetched — covered by a separate "no_coverage"
            # list below, not stale.
            continue
        latest_date, latest_delta = latest
        # If latest event is within window (upcoming or recent), it's already
        # in the buckets → skip.
        if -days_back <= latest_delta <= days_ahead:
            continue
        stale.append({
            "symbol": bare,
            "name": display,
            "latest_known_date": latest_date,
            "days_since": -latest_delta if latest_delta < 0 else 0,
            "days_until": latest_delta if latest_delta > 0 else 0,
        })
    stale.sort(key=lambda x: x["days_since"])

    # Symbols Yahoo has never returned any data for (delisted / uncovered)
    no_coverage = sorted(
        bare for bare in display_by_bare
        if bare not in latest_by_sym
    )

    return {
        "scope": scope,
        "symbols": len(yf_map),
        "days_ahead": days_ahead,
        "days_back": days_back,
        "stale_coverage": stale,
        "no_coverage": no_coverage,
        **summary,
    }


@app.post("/api/earnings/refresh")
def earnings_refresh(scope: str = "all") -> dict:
    """Force-refresh the earnings cache for the given scope."""
    return earnings_quarterly(scope=scope, days_ahead=30, days_back=60, force=True)


# ── Industry Groups API ──────────────────────────────────────────────────────
# Provides live industry-level RS ranking, breadth, 52WH counts, volume profiles,
# custom group management, and group detail drilldown.

import json as _json_mod
_CUSTOM_GROUPS_PATH = TRADE_DATA_DIR / "custom_groups.json"
_INDUSTRY_CACHE: dict = {}
_INDUSTRY_CACHE_TS: float = 0
_INDUSTRY_DISK_TS: float = 0  # last on-disk snapshot timestamp (for UI staleness display)
_INDUSTRY_CACHE_TTL = 600  # seconds (10 min — data doesn't change fast)
_INDUSTRY_DISK_PATH = TRADE_DATA_DIR / "industry_groups_cache.json"

# Thread-local flag: when set, _read_ohlcv skips its inline per-symbol
# stale-refresh thread spawn. Used by bulk callers (industry-groups compute)
# to avoid flooding the machine with thousands of refresh threads.
_bulk_read_ctx = threading.local()


def _bulk_skip_stale() -> bool:
    """True if the current thread is inside a bulk-read context."""
    return bool(getattr(_bulk_read_ctx, "skip_stale_refresh", False))


def _ig_worker_init():
    """ThreadPoolExecutor initializer — propagates the bulk-read flag into
    pool worker threads (thread-locals don't inherit automatically)."""
    _bulk_read_ctx.skip_stale_refresh = True


# ── Taxonomy cache (expensive to rebuild per request) ─────────────────────
_TAXONOMY_CACHE: dict | None = None
_TAXONOMY_CACHE_TS: float = 0
_TAXONOMY_CACHE_TTL = 1800  # 30 min — taxonomy CSV rarely changes at runtime
_TAXONOMY_LOCK = threading.Lock()


def _load_taxonomy_cached() -> dict:
    """Thread-safe cached load of the NSE sector/industry taxonomy.

    Previously each industry-groups API call rebuilt the sector/industry maps
    and re-read the 2600-line CSV — a measurable latency hit on hot endpoints
    (/api/industry-groups, /api/industry-groups/{name}, /rs-history). Now we
    load once per process and refresh after TTL."""
    global _TAXONOMY_CACHE, _TAXONOMY_CACHE_TS
    now = time.time()
    if _TAXONOMY_CACHE is not None and (now - _TAXONOMY_CACHE_TS) < _TAXONOMY_CACHE_TTL:
        return _TAXONOMY_CACHE
    with _TAXONOMY_LOCK:
        if _TAXONOMY_CACHE is not None and (time.time() - _TAXONOMY_CACHE_TS) < _TAXONOMY_CACHE_TTL:
            return _TAXONOMY_CACHE
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python" / "lib"))
            import nse_taxonomy
            # reload() clears every enriched map (macro/basic/themes/name)
            # and re-populates _SECTOR_MAP/_INDUSTRY_MAP from nse_stock_taxonomy.csv
            # followed by nse_stock_enriched.csv — so downstream multi-level
            # endpoints (/api/groups, /api/sector-rotation) see today's CSVs.
            if hasattr(nse_taxonomy, "reload"):
                nse_taxonomy.reload()
            else:
                nse_taxonomy._SECTOR_MAP, nse_taxonomy._INDUSTRY_MAP = nse_taxonomy._build_maps()
            _TAXONOMY_CACHE = nse_taxonomy.load_taxonomy() or {}
        except Exception as e:
            print(f"⚠ Failed to load taxonomy: {e}", flush=True)
            _TAXONOMY_CACHE = {}
        _TAXONOMY_CACHE_TS = time.time()
        return _TAXONOMY_CACHE


@app.post("/api/taxonomy/reload")
def reload_taxonomy() -> dict:
    """Force-reload the NSE sector/industry taxonomy from disk and invalidate
    downstream caches (industry groups + RS scan) so the UI picks up the new
    classifications on the next request.

    Useful after running `scripts/build_nse_industry_taxonomy.py` — lets you
    refresh the in-memory taxonomy without restarting the web server.
    """
    global _TAXONOMY_CACHE, _TAXONOMY_CACHE_TS, _INDUSTRY_CACHE_TS
    with _TAXONOMY_LOCK:
        _TAXONOMY_CACHE = None
        _TAXONOMY_CACHE_TS = 0
    tax = _load_taxonomy_cached()
    _INDUSTRY_CACHE_TS = 0  # force industry-groups recompute on next hit
    # Also clear the multi-level groups cache (macro/sector/basic_industry/
    # theme) and the industry-groups disk snapshot — otherwise stale
    # classifications survive the reload for up to 10 minutes.
    try:
        with _GROUPS_LEVEL_LOCK:
            _GROUPS_LEVEL_CACHE.clear()
    except Exception:
        pass
    try:
        if _INDUSTRY_DISK_PATH.exists():
            _INDUSTRY_DISK_PATH.unlink()
    except Exception:
        pass
    # Drop auto-classify cache so any yfinance overrides from a prior taxonomy
    # don't win against the fresh enriched CSV.
    try:
        _auto_cache = ROOT / "cache" / "auto_classify_cache.json"
        if _auto_cache.exists():
            _auto_cache.unlink()
    except Exception:
        pass
    try:
        with _rs_scan_lock:
            _rs_scan_cache["ts"] = 0
    except Exception:
        pass
    _bg_refresh_industry_groups()
    return {
        "ok": True,
        "taxonomyEntries": len(tax),
        "message": "Taxonomy reloaded; industry-groups + multi-level groups + "
                   "RS-scan + auto-classify caches invalidated. A background "
                   "recompute of /api/industry-groups has been kicked off.",
    }


def _load_industry_cache_from_disk():
    """Load industry groups from disk cache on startup for instant first load.

    IMPORTANT: We deliberately set _INDUSTRY_CACHE_TS = 0 (not the saved ts) so
    the *first* /api/industry-groups call after web-app startup serves this
    snapshot instantly AND triggers a background recompute against whatever
    fresh CSV data the startup OHLCV refresh has landed. Without this, a cache
    saved < TTL (10 min) before shutdown would be considered 'fresh' and the
    UI would show yesterday's prices until TTL expires.
    """
    global _INDUSTRY_CACHE, _INDUSTRY_CACHE_TS, _INDUSTRY_DISK_TS
    try:
        if _INDUSTRY_DISK_PATH.exists():
            data = _json_mod.loads(_INDUSTRY_DISK_PATH.read_text())
            groups = data.get("groups", [])
            disk_ts = float(data.get("ts", 0) or 0)
            if groups:
                _INDUSTRY_CACHE = {"groups": groups}
                _INDUSTRY_CACHE_TS = 0  # force stale → background refresh on first hit
                _INDUSTRY_DISK_TS = disk_ts
                print(f"✅ Loaded {len(groups)} industry groups from disk cache "
                      f"(marked stale; will auto-refresh on first request)", flush=True)
    except Exception as e:
        print(f"⚠ Failed to load industry disk cache: {e}", flush=True)


def _save_industry_cache_to_disk(groups: list[dict]):
    """Persist industry groups to disk for fast startup."""
    try:
        _INDUSTRY_DISK_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Strip members to keep file small (~50KB vs ~5MB) for fast load
        lite = []
        for g in groups:
            gc = dict(g)
            gc.pop("members", None)
            lite.append(gc)
        _INDUSTRY_DISK_PATH.write_text(_json_mod.dumps({"ts": time.time(), "groups": lite}, separators=(',', ':')))
    except Exception as e:
        print(f"⚠ Failed to save industry disk cache: {e}", flush=True)


# Load from disk on module import (instant first request)
_load_industry_cache_from_disk()


def _load_custom_groups() -> list[dict]:
    try:
        return _json_mod.loads(_CUSTOM_GROUPS_PATH.read_text()) if _CUSTOM_GROUPS_PATH.exists() else []
    except Exception:
        return []


def _save_custom_groups(groups: list[dict]) -> None:
    _CUSTOM_GROUPS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CUSTOM_GROUPS_PATH.write_text(_json_mod.dumps(groups, indent=2))


def _compute_group_metrics(group_name: str, tickers: list[str], sector: str = "",
                           preloaded: dict = None, nifty_returns: dict = None) -> dict:
    """Compute RS (vs Nifty), breadth, volume, 52WH metrics for a group of tickers.
    If preloaded dict {sym: rows} is passed, skip I/O entirely.
    If nifty_returns {'r5':..., 'r20':..., 'r60':...} is passed, RS is true vs Nifty."""

    n = 0
    above_20 = above_50 = above_200 = 0
    at_52wh = 0
    vol_expanding = 0
    ret_5d_list = []
    ret_20d_list = []
    ret_60d_list = []
    vol_ratios = []
    members = []

    for sym in tickers:
        if preloaded is not None:
            rows = preloaded.get(sym)
        else:
            rows = _read_ohlcv(sym, days=300)
        if not rows or len(rows) < 20:
            continue
        closes = [r["close"] for r in rows]
        volumes = [r["volume"] for r in rows]
        n += 1
        last = closes[-1]

        if len(closes) >= 20:
            ma20 = sum(closes[-20:]) / 20
            if last > ma20: above_20 += 1
        if len(closes) >= 50:
            ma50 = sum(closes[-50:]) / 50
            if last > ma50: above_50 += 1
        if len(closes) >= 200:
            ma200 = sum(closes[-200:]) / 200
            if last > ma200: above_200 += 1

        high_52w = max(closes[-252:]) if len(closes) >= 252 else max(closes)
        pct_from_52wh = round((last / high_52w - 1) * 100, 2) if high_52w > 0 else 0
        if last >= high_52w * 0.95:
            at_52wh += 1

        if len(volumes) >= 50:
            avg_vol = sum(volumes[-50:]) / 50
            recent_vol = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else volumes[-1]
            if avg_vol > 0:
                vr = recent_vol / avg_vol
                vol_ratios.append(vr)
                if vr > 1.2: vol_expanding += 1

        if len(closes) >= 6:
            ret_5d_list.append((last / closes[-6] - 1) * 100)
        if len(closes) >= 21:
            ret_20d_list.append((last / closes[-21] - 1) * 100)
        if len(closes) >= 61:
            ret_60d_list.append((last / closes[-61] - 1) * 100)

        day_chg = round((closes[-1] / closes[-2] - 1) * 100, 2) if len(closes) >= 2 else 0
        # Guard against stale data: if last 2 bars are > 5 calendar days apart,
        # day_chg is meaningless (gap between e.g. last Wednesday and this Monday).
        if len(rows) >= 2:
            from datetime import datetime as _dt
            try:
                d1 = _dt.strptime(rows[-1]["date"][:10], "%Y-%m-%d")
                d2 = _dt.strptime(rows[-2]["date"][:10], "%Y-%m-%d")
                if (d1 - d2).days > 5:
                    day_chg = 0.0  # stale gap — don't show misleading %
            except Exception:
                pass
        members.append({
            "symbol": sym,
            "close": round(last, 2),
            "dayChangePct": day_chg,
            "pctFrom52wHigh": pct_from_52wh,
            "volRatio": round(vol_ratios[-1], 2) if vol_ratios and vol_ratios[-1] == (recent_vol / avg_vol if avg_vol > 0 else 1) else None,
        })

    if n == 0:
        return {"group": group_name, "sector": sector, "stockCount": 0}

    pct_20 = round(above_20 / n * 100, 1)
    pct_50 = round(above_50 / n * 100, 1)
    pct_200 = round(above_200 / n * 100, 1)
    breadth_score = round(pct_20 * 0.3 + pct_50 * 0.4 + pct_200 * 0.3, 1)
    avg_vr = round(sum(vol_ratios) / len(vol_ratios), 2) if vol_ratios else 1.0
    avg_ret_5d = round(sum(ret_5d_list) / len(ret_5d_list), 2) if ret_5d_list else 0
    avg_ret_20d = round(sum(ret_20d_list) / len(ret_20d_list), 2) if ret_20d_list else 0
    avg_ret_60d = round(sum(ret_60d_list) / len(ret_60d_list), 2) if ret_60d_list else 0

    if avg_vr >= 1.3 and avg_ret_20d > 0:
        vol_pattern = "ACCUMULATION"
    elif avg_vr >= 1.3 and avg_ret_20d < -2:
        vol_pattern = "DISTRIBUTION"
    elif avg_vr < 0.8:
        vol_pattern = "DRY"
    else:
        vol_pattern = "NEUTRAL"

    rs_score = round(avg_ret_20d * 0.4 + avg_ret_60d * 0.3 + (pct_50 - 50) * 0.3, 2)

    # True Relative Strength vs Nifty: excess return over benchmark
    # rs_vs_nifty is positive when group outperforms Nifty, negative when it lags
    if nifty_returns:
        nifty_r5 = nifty_returns.get("r5", 0) or 0
        nifty_r20 = nifty_returns.get("r20", 0) or 0
        nifty_r60 = nifty_returns.get("r60", 0) or 0
        excess_5d = avg_ret_5d - nifty_r5
        excess_20d = avg_ret_20d - nifty_r20
        excess_60d = avg_ret_60d - nifty_r60
        # Weighted excess return — weight medium-term more (20d/60d)
        rs_score = round(excess_5d * 0.15 + excess_20d * 0.45 + excess_60d * 0.40, 2)
    else:
        excess_5d = excess_20d = excess_60d = 0.0

    return {
        "group": group_name, "sector": sector, "stockCount": n,
        "pctAbove20ma": pct_20, "pctAbove50ma": pct_50, "pctAbove200ma": pct_200,
        "breadthScore": breadth_score, "at52wHighCount": at_52wh,
        "pct52wHigh": round(at_52wh / n * 100, 1),
        "avgVolRatio": avg_vr, "volExpandingPct": round(vol_expanding / n * 100, 1),
        "volPattern": vol_pattern,
        "avgRet5d": avg_ret_5d, "avgRet20d": avg_ret_20d, "avgRet60d": avg_ret_60d,
        "excessRet5d": round(excess_5d, 2), "excessRet20d": round(excess_20d, 2), "excessRet60d": round(excess_60d, 2),
        "rsScore": rs_score,
        "members": sorted(members, key=lambda m: -(m.get("dayChangePct") or 0)),
    }


def _compute_all_industry_groups() -> list[dict]:
    """Return industry-group metrics. Never blocks the caller.

    Strategy (stale-while-revalidate, even on cold start):
    - Fresh in-memory cache (< TTL) → return it directly.
    - Stale in-memory cache (from disk or previous compute) → return it AND
      kick a single background recompute.
    - No cache at all (very first run, no disk snapshot) → return [] and kick a
      background compute. Callers (e.g. the HTTP handler) will surface
      `bgRefreshing=true` so the UI can show a "computing…" state instead of
      hanging on a 30-60s request.
    """
    global _INDUSTRY_CACHE, _INDUSTRY_CACHE_TS
    now = time.time()
    if _INDUSTRY_CACHE and (now - _INDUSTRY_CACHE_TS) < _INDUSTRY_CACHE_TTL:
        return _INDUSTRY_CACHE.get("groups", [])

    # Stale or empty → refresh in background, return whatever we have now.
    _bg_refresh_industry_groups()
    return _INDUSTRY_CACHE.get("groups", []) if _INDUSTRY_CACHE else []


_INDUSTRY_BG_LOCK = threading.Lock()
_INDUSTRY_BG_RUNNING = False

# Cap concurrency for the bulk OHLCV preload so the industry-groups compute
# never saturates the box. Leaves headroom for request handlers, the OHLCV
# cache refresher, and other background jobs — keeps the app smooth even
# during a full recompute.
_IG_WORKERS = max(2, min(8, (os.cpu_count() or 4) // 2 or 2))


def _bg_refresh_industry_groups():
    """Trigger a background refresh of industry groups cache."""
    global _INDUSTRY_BG_RUNNING
    if _INDUSTRY_BG_RUNNING:
        return
    def _run():
        global _INDUSTRY_BG_RUNNING
        try:
            _do_compute_industry_groups()
        finally:
            _INDUSTRY_BG_RUNNING = False
    with _INDUSTRY_BG_LOCK:
        if _INDUSTRY_BG_RUNNING:
            return
        _INDUSTRY_BG_RUNNING = True
    threading.Thread(target=_run, daemon=True).start()


def _do_compute_industry_groups() -> list[dict]:
    """Actually compute all industry groups and update cache."""
    global _INDUSTRY_CACHE, _INDUSTRY_CACHE_TS
    import time as _t
    t0 = _t.time()

    # Suppress inline per-symbol refresh-thread spawning for the duration of
    # this bulk load. With 2000+ CSVs we'd otherwise spawn thousands of
    # threads that all hit Yahoo, choking CPU + network and making this
    # compute take 30-60s instead of 3-5s. The global OHLCV refresher
    # (_cache_refresher) handles keeping the on-disk cache fresh.
    _bulk_read_ctx.skip_stale_refresh = True
    try:
        return _do_compute_industry_groups_inner(t0)
    finally:
        _bulk_read_ctx.skip_stale_refresh = False


def _do_compute_industry_groups_inner(t0: float) -> list[dict]:
    global _INDUSTRY_CACHE, _INDUSTRY_CACHE_TS
    import time as _t

    try:
        taxonomy = _load_taxonomy_cached()
    except Exception:
        return []

    industry_tickers: dict[str, list[str]] = {}
    industry_sectors: dict[str, str] = {}
    for ticker, tax_vals in taxonomy.items():
        sector = tax_vals[0] if tax_vals else "Other"
        # Use basic_industry (index 2, finest level with custom sub-classification
        # overrides) instead of industry (index 1, coarse NSE level).
        industry = tax_vals[2] if len(tax_vals) > 2 and tax_vals[2] else (
                   tax_vals[1] if len(tax_vals) > 1 else "Other")
        # Skip unclassified rows: any ticker that NSE couldn't bucket into
        # a concrete industry is noise for RS/breadth aggregation.
        if not industry or industry == "Other":
            continue
        industry_tickers.setdefault(industry, []).append(ticker)
        if industry not in industry_sectors:
            industry_sectors[industry] = sector or "Other"

    groups_to_compute = [(ind, tks) for ind, tks in industry_tickers.items() if len(tks) >= 2]

    # Collect ALL unique tickers across all groups and bulk-load in one parallel pass
    all_syms = set()
    for _, tks in groups_to_compute:
        all_syms.update(tks)

    from concurrent.futures import ThreadPoolExecutor

    def _load_one(sym):
        rows = _read_ohlcv(sym, days=300)
        return (sym, rows) if rows and len(rows) >= 20 else (sym, None)

    preloaded: dict = {}
    try:
        with ThreadPoolExecutor(max_workers=_IG_WORKERS, initializer=_ig_worker_init) as pool:
            for sym, rows in pool.map(_load_one, all_syms):
                if rows:
                    preloaded[sym] = rows
    except RuntimeError as e:
        # During interpreter shutdown, background daemon workers can still race
        # with executor creation/submission. Avoid noisy tracebacks at exit.
        if "interpreter shutdown" in str(e).lower():
            return []
        raise

    # ── Freshness check: if many CSVs are stale-for-today, delegate one
    # consolidated refresh to the OHLCV cache refresher (pooled, cooldowned).
    # When that finishes it auto-invalidates this cache and kicks a recompute —
    # so the next request will serve today's prices without any thread-storm.
    # We can't let individual _read_ohlcv calls spawn refreshes (thread storm),
    # so this is how freshness propagates during bulk compute.
    try:
        stale_syms: list[str] = []
        sample = list(preloaded.items())[:150]  # sample — full stat scan is expensive
        for sym, rows in sample:
            if not rows:
                continue
            last_date = rows[-1]["date"]
            csv_path = CACHE_DIR / f"{sym}.NS.csv"
            if not csv_path.exists():
                csv_path = CACHE_DIR / f"{sym}.csv"
            if _is_price_stale(last_date, csv_path):
                stale_syms.append(sym)
        # If ≥10% of sample is stale and no refresh is in flight, kick one.
        if sample and len(stale_syms) >= max(5, len(sample) // 10):
            if not _cache_refresher.is_running:
                print(f"🔄 Industry compute: {len(stale_syms)}/{len(sample)} sampled "
                      f"CSVs are stale — kicking OHLCV cache refresh", flush=True)
                _cache_refresher.start(indian_only=True, workers=4)
    except Exception as _e:
        print(f"⚠ Industry compute freshness probe error: {_e}", flush=True)

    # Compute Nifty's returns for true RS-vs-benchmark calculation
    nifty_returns = None
    nifty_rows = _read_ohlcv("^NSEI", days=300)
    if nifty_rows and len(nifty_rows) >= 61:
        nc = [r["close"] for r in nifty_rows]
        nifty_returns = {
            "r5":  (nc[-1] / nc[-6] - 1) * 100  if len(nc) >= 6  else 0,
            "r20": (nc[-1] / nc[-21] - 1) * 100 if len(nc) >= 21 else 0,
            "r60": (nc[-1] / nc[-61] - 1) * 100 if len(nc) >= 61 else 0,
        }

    # Now compute metrics for each group — pure CPU, no I/O
    results = []
    for ind, tickers in groups_to_compute:
        r = _compute_group_metrics(ind, tickers, industry_sectors.get(ind, ""),
                                   preloaded=preloaded, nifty_returns=nifty_returns)
        if r.get("stockCount", 0) >= 2:
            results.append(r)

    results.sort(key=lambda x: -(x.get("rsScore") or 0))

    for i, r in enumerate(results):
        r["rsRank"] = i + 1

    _INDUSTRY_CACHE = {"groups": results}
    _INDUSTRY_CACHE_TS = _t.time()
    globals()["_INDUSTRY_DISK_TS"] = _INDUSTRY_CACHE_TS
    _save_industry_cache_to_disk(results)
    elapsed = _t.time() - t0
    print(f"✅ Industry groups computed: {len(results)} groups, {len(preloaded)} tickers in {elapsed:.1f}s", flush=True)
    return results


# ── Periodic self-refresher ─────────────────────────────────────────────────
# Keeps the industry-groups cache warm even when no one is hitting the
# endpoint, so the UI never has to wait on a full recompute. Runs at half the
# TTL interval, single-threaded, low priority (best-effort nice).
_INDUSTRY_PERIODIC_STARTED = False


def _start_periodic_industry_refresher():
    global _INDUSTRY_PERIODIC_STARTED
    if _INDUSTRY_PERIODIC_STARTED:
        return
    _INDUSTRY_PERIODIC_STARTED = True

    def _loop():
        # Be a good neighbour: lower process-wide priority is too aggressive,
        # but we can sleep a bit at startup so we don't fight with the
        # startup OHLCV refresh for CPU/network.
        try:
            time.sleep(30)
        except Exception:
            pass
        interval = max(60, _INDUSTRY_CACHE_TTL // 2)
        while True:
            try:
                now = time.time()
                # Only refresh if cache is actually stale; otherwise just idle.
                if not _INDUSTRY_CACHE or (now - _INDUSTRY_CACHE_TS) >= _INDUSTRY_CACHE_TTL:
                    _bg_refresh_industry_groups()
            except Exception as e:
                print(f"⚠ Industry periodic refresher error: {e}", flush=True)
            try:
                time.sleep(interval)
            except Exception:
                return

    threading.Thread(target=_loop, name="industry-periodic-refresh", daemon=True).start()


# Kick the periodic refresher now that all the helpers exist.
if os.environ.get("SETUPS_SKIP_STARTUP_REFRESH", "").lower() not in ("true", "1", "yes"):
    _start_periodic_industry_refresher()


# ─────────────────────────────────────────────────────────────────────────────
#  Multi-level groups  (macro / sector / industry / basic_industry / theme)
# ─────────────────────────────────────────────────────────────────────────────
# The existing /api/industry-groups endpoint groups stocks by NSE `industry`
# only. For sector-rotation and relative-strength analysis we want to look at
# the same RS metrics at multiple classification layers simultaneously:
#
#   macro           → NSE macro-economic sector (~20 buckets) — broadest rotation lens
#   sector          → NSE sector (~55)  — standard Nifty-index bucketing
#   industry        → NSE industry (~250) — what /api/industry-groups already serves
#   basic_industry  → NSE basic_industry (~200) — finest NSE level, pure-play peers
#   theme           → Curated thematic overlay (~30) — cuts across NSE hierarchy
#                     (Defense, EV, Renewables, Railways, PSU Capex, CDMO, …)
#
# Themes are multi-label (a stock can live in several themes, e.g. RELIANCE
# sits in both oil_upstream + oil_downstream). Every other level is single-
# label. Theme rules live in data/themes.json; membership is precomputed by
# scripts/apply_themes.py into data/nse_stock_enriched.csv.
#
# Caching is per-level with its own TTL timestamp. We reuse the industry cache
# for level="industry" so existing callers benefit from the same disk-warmed
# snapshot and periodic refresher.
# ─────────────────────────────────────────────────────────────────────────────

_GROUPS_LEVEL_CACHE: dict[str, dict] = {}   # level → {"groups": [...], "ts": float}
_GROUPS_LEVEL_LOCK = threading.Lock()
_VALID_LEVELS = ("macro", "sector", "industry", "basic_industry", "theme")


def _taxonomy_module():
    """Return the live nse_taxonomy module (imported once)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python" / "lib"))
    import nse_taxonomy  # noqa: F401
    return nse_taxonomy


def _compute_groups_for_level(level: str) -> list[dict]:
    """Compute RS/breadth/volume metrics for every group at the given level.

    Mirrors _do_compute_industry_groups_inner's algorithm but groups tickers
    by the requested classification level. The expensive work — loading OHLCV
    for ~2,500 tickers in parallel and computing Nifty baseline returns — is
    shared across all groups within a single call. Results are cached per
    level with a 10-min TTL.
    """
    import time as _t
    if level not in _VALID_LEVELS:
        raise ValueError(f"unknown level {level!r}")

    t0 = _t.time()
    tax_mod = _taxonomy_module()
    groups_map = tax_mod.group_tickers_by(level)          # {group → [tickers]}
    parent_map = tax_mod.group_parent_map(level)          # {group → parent_name}
    theme_meta = {m["key"]: m for m in tax_mod.list_themes()} if level == "theme" else {}

    # Filter groups worth computing
    groups_to_compute = [(g, tks) for g, tks in groups_map.items() if len(tks) >= 2]

    # Bulk-load OHLCV in parallel (shared across all groups)
    all_syms = set()
    for _, tks in groups_to_compute:
        all_syms.update(tks)

    from concurrent.futures import ThreadPoolExecutor

    def _load_one(sym):
        rows = _read_ohlcv(sym, days=300)
        return (sym, rows) if rows and len(rows) >= 20 else (sym, None)

    preloaded: dict = {}
    with ThreadPoolExecutor(max_workers=_IG_WORKERS,
                            initializer=_ig_worker_init) as pool:
        for sym, rows in pool.map(_load_one, all_syms):
            if rows:
                preloaded[sym] = rows

    # Nifty baseline returns (for true RS-vs-benchmark)
    nifty_returns = None
    nifty_rows = _read_ohlcv("^NSEI", days=300)
    if nifty_rows and len(nifty_rows) >= 61:
        nc = [r["close"] for r in nifty_rows]
        nifty_returns = {
            "r5":  (nc[-1] / nc[-6]  - 1) * 100 if len(nc) >= 6  else 0,
            "r20": (nc[-1] / nc[-21] - 1) * 100 if len(nc) >= 21 else 0,
            "r60": (nc[-1] / nc[-61] - 1) * 100 if len(nc) >= 61 else 0,
        }

    # Per-group metrics
    results = []
    for g, tickers in groups_to_compute:
        parent = parent_map.get(g, "")
        r = _compute_group_metrics(g, tickers, parent,
                                   preloaded=preloaded, nifty_returns=nifty_returns)
        if r.get("stockCount", 0) < 2:
            continue
        r["level"]  = level
        r["parent"] = parent   # industry's sector, basic's industry, etc.
        if level == "theme":
            meta = theme_meta.get(g, {})
            r["themeName"]        = meta.get("name", g)
            r["themeDescription"] = meta.get("description", "")
        results.append(r)

    # Rotation score: catches nascent leadership changes. Positive = group's
    # 1M outperformance has accelerated versus its 3M trend. Negative = momentum
    # is cooling, even if 3M still looks strong. Ranked independently of rsScore.
    for r in results:
        r5  = r.get("return5d")  or 0
        r20 = r.get("return20d") or 0
        r60 = r.get("return60d") or 0
        nr  = nifty_returns or {}
        # RS-vs-Nifty over each horizon
        rs5  = r5  - (nr.get("r5")  or 0)
        rs20 = r20 - (nr.get("r20") or 0)
        rs60 = r60 - (nr.get("r60") or 0)
        # Rotation = short-term RS acceleration vs medium-term RS
        # Positive → momentum accelerating (emerging leader)
        # Negative → momentum cooling (leader → laggard transition)
        r["rotationScore"] = round(rs20 - (rs60 / 3), 2)
        r["rsVsNifty5d"]   = round(rs5, 2)
        r["rsVsNifty20d"]  = round(rs20, 2)
        r["rsVsNifty60d"]  = round(rs60, 2)

    results.sort(key=lambda x: -(x.get("rsScore") or 0))
    for i, r in enumerate(results):
        r["rsRank"] = i + 1

    elapsed = _t.time() - t0
    print(f"✅ Groups[{level}] computed: {len(results)} groups, "
          f"{len(preloaded)} tickers in {elapsed:.1f}s", flush=True)
    return results


def _get_level_groups(level: str, max_age: int = 600) -> list[dict]:
    """Cached accessor. For level='industry' we piggyback on the existing
    _INDUSTRY_CACHE so warmth is shared with /api/industry-groups."""
    now = time.time()

    if level == "industry":
        # Reuse existing industry cache (already disk-warmed at startup).
        if _INDUSTRY_CACHE and (now - _INDUSTRY_CACHE_TS) < max_age:
            return _INDUSTRY_CACHE.get("groups", [])
        # Fall through to the existing path (handles disk snapshot, bg refresh).
        return _compute_all_industry_groups()

    cached = _GROUPS_LEVEL_CACHE.get(level)
    if cached and (now - cached["ts"]) < max_age:
        return cached["groups"]

    with _GROUPS_LEVEL_LOCK:
        cached = _GROUPS_LEVEL_CACHE.get(level)
        if cached and (time.time() - cached["ts"]) < max_age:
            return cached["groups"]
        groups = _compute_groups_for_level(level)
        _GROUPS_LEVEL_CACHE[level] = {"groups": groups, "ts": time.time()}
        return groups


@app.get("/api/groups/levels")
def api_groups_levels() -> dict:
    """List the classification levels available to /api/groups, plus theme
    metadata. Use this to populate a level-selector dropdown in the UI."""
    tax_mod = _taxonomy_module()
    return {
        "levels": [
            {"key": "macro",          "name": "Macro Sector",
             "description": "NSE macro-economic sector (broadest)",
             "count": len(tax_mod.list_macros())},
            {"key": "sector",         "name": "Sector",
             "description": "NSE sector (standard index bucketing)",
             "count": len(tax_mod.list_sectors())},
            {"key": "industry",       "name": "Industry",
             "description": "NSE industry (default grouping)",
             "count": len(tax_mod.list_industries())},
            {"key": "basic_industry", "name": "Basic Industry",
             "description": "NSE basic_industry (finest official level)",
             "count": len(tax_mod.list_basic_industries())},
            {"key": "theme",          "name": "Theme",
             "description": "Curated thematic overlay (multi-label)",
             "count": len(tax_mod.list_themes())},
        ],
        "themes": tax_mod.list_themes(),
    }


@app.get("/api/groups")
def api_groups(level: str = "basic_industry", min_stocks: int = 2,
               sort_by: str = "rsScore") -> dict:
    """Unified multi-level groups endpoint for relative-strength & rotation.

    Query params:
      level   : one of macro | sector | industry | basic_industry | theme
      min_stocks : drop groups smaller than this (default 2)
      sort_by : rsScore (default) | rotationScore | breadthScore | return20d
    """
    if level not in _VALID_LEVELS:
        raise HTTPException(status_code=400,
                            detail=f"level must be one of {_VALID_LEVELS}")
    groups = _get_level_groups(level)
    groups = [g for g in groups if g.get("stockCount", 0) >= min_stocks]

    # Sorting
    key = sort_by if sort_by in ("rsScore", "rotationScore", "breadthScore",
                                 "return5d", "return20d", "return60d") else "rsScore"
    groups = sorted(groups, key=lambda g: -(g.get(key) or 0))

    # Strip heavy member arrays (same lite convention as /api/industry-groups)
    lite = []
    for g in groups:
        gc = dict(g)
        gc.pop("members", None)
        lite.append(gc)

    ts = (_INDUSTRY_CACHE_TS if level == "industry"
          else _GROUPS_LEVEL_CACHE.get(level, {}).get("ts", 0))
    return {
        "level":      level,
        "sortBy":     key,
        "groups":     lite,
        "total":      len(lite),
        "cachedAt":   ts or None,
        "cacheAgeSec": round(time.time() - ts) if ts else None,
        "timestamp":  time.time(),
    }


@app.post("/api/groups/refresh")
def api_groups_refresh(level: str | None = None) -> dict:
    """Invalidate the multi-level groups cache (all levels if none given)."""
    global _INDUSTRY_CACHE_TS
    with _GROUPS_LEVEL_LOCK:
        if level is None:
            _GROUPS_LEVEL_CACHE.clear()
            _INDUSTRY_CACHE_TS = 0
            return {"cleared": "all"}
        if level not in _VALID_LEVELS:
            raise HTTPException(status_code=400,
                                detail=f"level must be one of {_VALID_LEVELS}")
        if level == "industry":
            _INDUSTRY_CACHE_TS = 0
        _GROUPS_LEVEL_CACHE.pop(level, None)
        return {"cleared": level}


@app.get("/api/sector-rotation")
def api_sector_rotation(level: str = "sector", top_n: int = 10) -> dict:
    """Sector / theme rotation dashboard.

    Returns the strongest and weakest groups at the chosen level sorted by
    *rotationScore* (not rsScore). rotationScore = rsVsNifty20d - rsVsNifty60d/3,
    so positive = outperformance accelerating (emerging leadership) and
    negative = outperformance cooling (leaders rolling over). Pair this with
    /api/groups?sort_by=rsScore to see absolute vs directional strength.
    """
    if level not in _VALID_LEVELS:
        raise HTTPException(status_code=400,
                            detail=f"level must be one of {_VALID_LEVELS}")
    groups = _get_level_groups(level)
    groups = [g for g in groups if g.get("stockCount", 0) >= 3]
    by_rot = sorted(groups, key=lambda g: -(g.get("rotationScore") or 0))

    def _slim(g: dict) -> dict:
        return {
            "name":           g.get("name") or g.get("industry"),
            "parent":         g.get("parent") or g.get("sector", ""),
            "stockCount":     g.get("stockCount"),
            "rsScore":        g.get("rsScore"),
            "rotationScore":  g.get("rotationScore"),
            "rsVsNifty5d":    g.get("rsVsNifty5d"),
            "rsVsNifty20d":   g.get("rsVsNifty20d"),
            "rsVsNifty60d":   g.get("rsVsNifty60d"),
            "return5d":       g.get("return5d"),
            "return20d":      g.get("return20d"),
            "return60d":      g.get("return60d"),
            "breadthScore":   g.get("breadthScore"),
            "pctAbove50ma":   g.get("pctAbove50ma"),
            "themeName":      g.get("themeName"),
        }

    return {
        "level":     level,
        "timestamp": time.time(),
        "emerging":  [_slim(g) for g in by_rot[:top_n]],       # accelerating
        "cooling":   [_slim(g) for g in by_rot[-top_n:][::-1]],# decelerating
    }


@app.get("/api/industry-groups")
def get_industry_groups(min_stocks: int = 2) -> dict:
    groups = _compute_all_industry_groups()
    filtered = [g for g in groups if g.get("stockCount", 0) >= min_stocks]
    lite = []
    for g in filtered:
        gc = dict(g)
        gc.pop("members", None)
        lite.append(gc)
    # Include cache age so frontend can show staleness warning.
    # Prefer in-memory TS (post-compute); fall back to disk TS so a fresh
    # startup can still tell the UI when the snapshot was made.
    effective_ts = _INDUSTRY_CACHE_TS or _INDUSTRY_DISK_TS
    cache_age = round(time.time() - effective_ts) if effective_ts else None
    # Expose OHLCV refresh status so UI can show "pulling today's closes…"
    # and poll faster while it's in flight.
    ohlcv_status = _cache_refresher.status_dict()
    ohlcv_running = ohlcv_status.get("status") == "running"
    ohlcv_progress = None
    if ohlcv_running:
        done = ohlcv_status.get("symbolsDone", 0)
        total = ohlcv_status.get("symbolsTotal", 0)
        ohlcv_progress = {"done": done, "total": total,
                          "pct": round(done / total * 100, 1) if total else 0}
    return {"groups": lite, "total": len(lite), "timestamp": time.time(),
            "cachedAt": effective_ts or None, "cacheAgeSec": cache_age,
            "bgRefreshing": _INDUSTRY_BG_RUNNING,
            "ohlcvRefreshing": ohlcv_running,
            "ohlcvProgress": ohlcv_progress,
            "fromDiskSnapshot": bool(_INDUSTRY_CACHE) and _INDUSTRY_CACHE_TS == 0}


@app.post("/api/industry-groups/refresh")
def refresh_industry_groups(force: bool = False, prices: bool = True) -> dict:
    """Invalidate the industry-groups cache and kick a background recompute
    against the latest CSV cache. Returns immediately; poll /api/industry-groups
    with `cacheAgeSec` to know when the new snapshot lands.

    When prices=True (default), also kicks the OHLCV cache refresher so today's
    closing bars are pulled into the CSVs before the recompute runs. This is
    how the manual 🔄 Refresh button gets today's prices into the page when the
    startup refresh didn't run (or hasn't run since market close).
    """
    global _INDUSTRY_CACHE_TS
    _INDUSTRY_CACHE_TS = 0

    # Kick OHLCV refresh first — when it finishes it will auto-invalidate
    # and recompute industry groups (see BackgroundCacheRefresher._run).
    ohlcv_started = False
    if prices and not _cache_refresher.is_running:
        try:
            _cache_refresher.start(indian_only=True, workers=4)
            ohlcv_started = True
        except Exception as e:
            print(f"⚠ OHLCV refresh kick failed: {e}", flush=True)

    if force:
        # Blocking full recompute (used by tests / manual debugging)
        groups = _do_compute_industry_groups()
        return {"ok": True, "mode": "sync", "count": len(groups),
                "ohlcvRefreshStarted": ohlcv_started}
    _bg_refresh_industry_groups()
    return {"ok": True, "mode": "async", "bgRunning": _INDUSTRY_BG_RUNNING,
            "ohlcvRefreshStarted": ohlcv_started,
            "message": "Industry groups recompute started in background"
                       + (" (after OHLCV refresh)" if ohlcv_started else "")}


@app.get("/api/industry-groups/{group_name}")
def get_industry_group_detail(group_name: str, fresh: bool = True,
                               level: str = "basic_industry") -> dict:
    """Return metrics + member list for a group at any classification level.

    `level` can be one of: macro, sector, industry, basic_industry, theme.
    By default (`fresh=True`) recomputes the group from the latest CSV data.
    Pass `fresh=false` to return the possibly-cached snapshot instead.
    """
    import urllib.parse
    decoded = urllib.parse.unquote(group_name)

    # Ensure taxonomy is reloaded/fresh — this populates _BASIC_INDUSTRY_MAP
    # with custom sub-classification overrides before we call group_tickers_by.
    taxonomy = _load_taxonomy_cached()

    # Use group_tickers_by(level) for a direct, level-aware lookup — handles
    # macro, sector, industry, basic_industry and theme uniformly.
    tickers: list[str] = []
    sector = ""
    try:
        tax_mod = _taxonomy_module()
        lvl = level if level in ("macro", "sector", "industry", "basic_industry", "theme") else "basic_industry"
        groups_map = tax_mod.group_tickers_by(lvl)
        tickers = list(groups_map.get(decoded, []))
        # Determine display sector from the first member
        if tickers:
            for t in tickers[:5]:
                tv = taxonomy.get(t)
                if tv and tv[0]:
                    sector = tv[0]
                    break
    except Exception as e:
        print(f"⚠ group_tickers_by failed: {e}", flush=True)

    # Legacy fallback: search taxonomy tuples directly
    if not tickers:
        taxonomy = _load_taxonomy_cached()
        for t, tax_vals in taxonomy.items():
            sec = tax_vals[0] if tax_vals else "Other"
            bi  = tax_vals[2] if len(tax_vals) > 2 else ""
            ind = tax_vals[1] if len(tax_vals) > 1 else "Other"
            match_val = bi if bi else ind
            if match_val == decoded:
                tickers.append(t)
                if not sector:
                    sector = sec

    if not tickers:
        # Also try matching by sector (index 0)
        taxonomy = _load_taxonomy_cached()
        for t, tax_vals in taxonomy.items():
            sec = tax_vals[0] if tax_vals else "Other"
            if sec == decoded:
                tickers.append(t)
                if not sector:
                    sector = sec

    if not tickers:
        # Final fallback: pre-computed industry-level cache
        groups = _compute_all_industry_groups()
        for g in groups:
            if g.get("group") == decoded:
                return g
        raise HTTPException(status_code=404, detail=f"Industry group '{decoded}' not found")

    if fresh:
        # Pass Nifty returns for true RS-vs-benchmark calc.
        # Bulk-read guard: prevent per-symbol refresh-thread storm while
        # _compute_group_metrics walks members. For a small group (≤30 members)
        # this is safe because the worst case is 30 refresh threads — well
        # within the machine's tolerance and gives the user up-to-date prices.
        use_bulk_flag = len(tickers) > 30
        if use_bulk_flag:
            _bulk_read_ctx.skip_stale_refresh = True
        try:
            nifty_rows = _read_ohlcv("^NSEI", days=300)
            nifty_returns = None
            if nifty_rows and len(nifty_rows) >= 61:
                nc = [r["close"] for r in nifty_rows]
                nifty_returns = {
                    "r5":  (nc[-1] / nc[-6] - 1) * 100  if len(nc) >= 6  else 0,
                    "r20": (nc[-1] / nc[-21] - 1) * 100 if len(nc) >= 21 else 0,
                    "r60": (nc[-1] / nc[-61] - 1) * 100 if len(nc) >= 61 else 0,
                }
            result = _compute_group_metrics(decoded, tickers, sector,
                                            nifty_returns=nifty_returns)
        finally:
            if use_bulk_flag:
                _bulk_read_ctx.skip_stale_refresh = False

        # For small groups (where we allowed per-symbol refresh), also probe
        # for overall staleness and delegate to the OHLCV refresher so the
        # NEXT click gets today's closes — the per-symbol threads take care
        # of this group's symbols, but a consolidated refresh covers the rest.
        if not use_bulk_flag and not _cache_refresher.is_running:
            try:
                stale_count = 0
                for sym in tickers:
                    csv_path = CACHE_DIR / f"{sym}.NS.csv"
                    if not csv_path.exists():
                        csv_path = CACHE_DIR / f"{sym}.csv"
                    if not csv_path.exists():
                        continue
                    import refresh_cache as _rc
                    ld = _rc._read_last_date(csv_path)
                    if _is_price_stale(ld, csv_path):
                        stale_count += 1
                if stale_count >= max(1, len(tickers) // 3):
                    print(f"🔄 Drilldown {decoded!r}: {stale_count}/{len(tickers)} "
                          f"stale — kicking OHLCV refresh", flush=True)
                    _cache_refresher.start(indian_only=True, workers=4)
            except Exception:
                pass
        # Attach rsRank from cached list if present (cheap metadata)
        for g in _INDUSTRY_CACHE.get("groups", []):
            if g.get("group") == decoded:
                result["rsRank"] = g.get("rsRank")
                break
        return result

    # Non-fresh path: return cached snapshot if available
    groups = _compute_all_industry_groups()
    for g in groups:
        if g.get("group") == decoded:
            if not g.get("members"):
                # Disk cache stripped members — recompute this one group
                return _compute_group_metrics(decoded, tickers, sector)
            return g
    raise HTTPException(status_code=404, detail=f"Industry group '{decoded}' not found")


@app.get("/api/industry-groups/{group_name}/rs-history")
def get_industry_group_rs_history(group_name: str, days: int = 120,
                                   level: str = "basic_industry") -> dict:
    import urllib.parse
    decoded = urllib.parse.unquote(group_name)

    # Ensure taxonomy is fresh (loads custom sub-classification overrides)
    taxonomy = _load_taxonomy_cached()

    # Use group_tickers_by(level) for level-aware lookup
    members: list[str] = []
    try:
        tax_mod = _taxonomy_module()
        lvl = level if level in ("macro", "sector", "industry", "basic_industry", "theme") else "basic_industry"
        groups_map = tax_mod.group_tickers_by(lvl)
        members = list(groups_map.get(decoded, []))
    except Exception:
        pass

    # Legacy fallback: search taxonomy tuples
    if not members:
        try:
            # Search basic_industry (tv[2]) first, then industry (tv[1])
            members = [
                t for t, tv in taxonomy.items()
                if (tv[2] if len(tv) > 2 else tv[1] if len(tv) > 1 else "") == decoded
            ]
            if not members:
                members = [t for t, tv in taxonomy.items() if len(tv) > 1 and tv[1] == decoded]
            if not members:
                members = [t for t, tv in taxonomy.items() if tv[0] == decoded]
        except Exception:
            pass

    # Legacy fallback: search pre-computed industry-level cache
    if not members:
        groups = _compute_all_industry_groups()
        target = None
        for g in groups:
            if g.get("group") == decoded:
                target = g
                break
        if not target:
            raise HTTPException(status_code=404, detail=f"Group '{decoded}' not found")
        members = [m["symbol"] for m in target.get("members", [])]

    if not members:
        return {"group": decoded, "rsLine": []}

    # Read in bulk without spawning per-symbol refresh threads.
    _bulk_read_ctx.skip_stale_refresh = True
    try:
        nifty_rows = _read_ohlcv("^NSEI", days=days + 50)
        nifty_map = {r["date"]: r["close"] for r in nifty_rows} if nifty_rows else {}

        all_dates: dict[str, list[float]] = {}
        for sym in members[:30]:
            rows = _read_ohlcv(sym, days=days + 50)
            if not rows or len(rows) < 20:
                continue
            base_close = rows[0]["close"]
            for r in rows:
                d = r["date"]
                normed = (r["close"] / base_close) * 100
                all_dates.setdefault(d, []).append(normed)
    finally:
        _bulk_read_ctx.skip_stale_refresh = False

    if not all_dates:
        return {"group": decoded, "rsLine": []}

    sorted_dates = sorted(all_dates.keys())
    if len(sorted_dates) > days:
        sorted_dates = sorted_dates[-days:]

    nifty_base = nifty_map.get(sorted_dates[0], 100) if nifty_map else 100
    rs_line = []
    for d in sorted_dates:
        group_avg = sum(all_dates[d]) / len(all_dates[d])
        nifty_normed = (nifty_map.get(d, nifty_base) / nifty_base) * 100 if nifty_base > 0 else 100
        rs_val = round(group_avg / nifty_normed * 100, 2) if nifty_normed > 0 else 100
        rs_line.append({"date": d, "rs": rs_val, "groupReturn": round(group_avg - 100, 2), "niftyReturn": round(nifty_normed - 100, 2)})

    return {"group": decoded, "rsLine": rs_line}


@app.get("/api/stock-group-lookup")
def stock_group_lookup(q: str = "") -> dict:
    """Search for a stock by ticker or company name and return which groups it
    belongs to at every classification level.
    Query param ``q`` is matched case-insensitively against the ticker and
    company_name fields in the enriched taxonomy."""
    q = q.strip()
    if not q:
        raise HTTPException(status_code=400, detail="query param 'q' is required")

    _load_taxonomy_cached()
    tax_mod = _taxonomy_module()

    # Build a quick name→ticker reverse index from _NAME_MAP
    q_upper = q.upper()
    q_lower = q.lower()

    # Collect matching tickers (exact ticker match first, then name search)
    matches: list[dict] = []
    seen: set[str] = set()

    # 1. Exact ticker match (with .NS stripping)
    clean_q = q_upper.replace(".NS", "").replace(".BO", "")
    for candidate in [clean_q, q_upper]:
        name = tax_mod.get_company_name(candidate)
        sector = tax_mod.get_sector(candidate)
        if sector and sector != "Other":
            if candidate not in seen:
                seen.add(candidate)
                matches.append({"ticker": candidate, "name": name or candidate})

    # 2. Fuzzy / substring match on company name & ticker
    if hasattr(tax_mod, "_NAME_MAP"):
        for ticker, name in tax_mod._NAME_MAP.items():
            if ticker in seen:
                continue
            if q_lower in ticker.lower() or q_lower in name.lower():
                matches.append({"ticker": ticker, "name": name})
                seen.add(ticker)
                if len(matches) >= 25:
                    break

    # For each match, look up groups at all levels
    results = []
    for m in matches:
        t = m["ticker"]
        entry = {
            "ticker": t,
            "companyName": m["name"],
            "macro": tax_mod.get_macro(t),
            "sector": tax_mod.get_sector(t),
            "industry": tax_mod.get_industry(t),
            "basicIndustry": tax_mod.get_basic_industry(t),
            "themes": tax_mod.get_themes(t),
        }
        results.append(entry)

    return {"query": q, "results": results}


@app.get("/api/custom-groups")
def list_custom_groups() -> dict:
    return {"groups": _load_custom_groups()}


@app.post("/api/custom-groups")
def create_custom_group(body: dict) -> dict:
    name = body.get("name", "").strip()
    tickers = body.get("tickers", [])
    if not name or not tickers:
        raise HTTPException(status_code=400, detail="name and tickers required")
    groups = _load_custom_groups()
    if any(g["name"] == name for g in groups):
        raise HTTPException(status_code=409, detail=f"Group '{name}' already exists")
    group = {"name": name, "tickers": [t.upper() for t in tickers], "created": datetime.now().isoformat()}
    groups.append(group)
    _save_custom_groups(groups)
    return {"ok": True, "group": group}


@app.delete("/api/custom-groups/{name}")
def delete_custom_group(name: str) -> dict:
    import urllib.parse
    decoded = urllib.parse.unquote(name)
    groups = _load_custom_groups()
    groups = [g for g in groups if g["name"] != decoded]
    _save_custom_groups(groups)
    return {"ok": True}


@app.get("/api/custom-groups/{name}/metrics")
def custom_group_metrics(name: str) -> dict:
    import urllib.parse
    decoded = urllib.parse.unquote(name)
    groups = _load_custom_groups()
    target = next((g for g in groups if g["name"] == decoded), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Custom group '{decoded}' not found")
    return _compute_group_metrics(decoded, target["tickers"], "Custom")


@app.get("/trades")
def trade_plans_page() -> Response:
    """Serve the pre-built Live Breakout Trade Plans HTML page."""
    if not TRADE_PLANS_HTML.exists():
        raise HTTPException(
            status_code=404,
            detail="Trade plans page not found. It will be auto-generated after cache refresh completes, or trigger manually via POST /api/jobs/trade-plans. A scan must have run at least once.",
        )
    return _serve_with_wisdom(TRADE_PLANS_HTML)


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
    status = _cache_refresher.status_dict()
    status["periodic"] = _periodic_refresher.status_dict()
    status["postClose"] = _postclose_refresher.status_dict()
    return status


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
def cache_refresh_specific_symbols(symbols: list[str], force: bool = False) -> dict:
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
        updated = _refresh_symbol_if_stale(sym_clean, force=force)
        results[sym_clean] = "updated" if updated else "fresh_or_cooldown"

    return {"results": results, "count": len(results)}


@app.post("/api/cache/fix-intraday")
def cache_fix_intraday_snapshots(
    dry_run: bool = False,
    workers: int = 8,
) -> dict:
    """
    Scan every Indian OHLCV cache file for an "intraday snapshot" — i.e. the
    CSV's last row is dated D and the file mtime is on D but before the 15:35
    IST market close. Those rows contain an intraday price, not the finalized
    close, and the normal "+1 day" fetcher logic would never re-query that
    date. This endpoint lists every affected file and (unless `dry_run=true`)
    kicks a forced refresh against them via the BackgroundCacheRefresher,
    which uses the intraday-aware back-up logic in refresh_symbol() to pull
    the finalized close and overwrite the bad row.

    Returns immediately; poll /api/cache/refresh-status for progress.
    """
    import datetime as _dt, zoneinfo as _zi
    _ist = _zi.ZoneInfo("Asia/Kolkata")

    affected: list[dict] = []
    for p in sorted(CACHE_DIR.glob("*.NS.csv")):
        try:
            sym = p.name.replace(".csv", "")
            # Cheap last-date read via refresh_cache helper
            try:
                import refresh_cache as _rc
                last_date_str = _rc._read_last_date(p)
            except Exception:
                last_date_str = ""
            if not last_date_str:
                continue
            try:
                last_date = _dt.date.fromisoformat(last_date_str)
            except ValueError:
                continue
            mtime = _dt.datetime.fromtimestamp(p.stat().st_mtime, tz=_ist)
            # Only flag if the file's last-row date matches the mtime date
            # AND the file was written before market close (15:35 IST).
            if mtime.date() != last_date:
                continue
            cutoff = mtime.replace(hour=15, minute=35, second=0, microsecond=0)
            if mtime < cutoff:
                affected.append({
                    "symbol": sym,
                    "last_date": last_date_str,
                    "mtime": mtime.strftime("%Y-%m-%d %H:%M IST"),
                })
        except Exception:
            pass

    if dry_run:
        return {
            "ok": True, "mode": "dry_run",
            "count": len(affected),
            "affected": affected[:500],
            "truncated": len(affected) > 500,
        }

    if not affected:
        return {"ok": True, "mode": "idle", "count": 0,
                "message": "No intraday-stuck CSVs found"}

    syms = [a["symbol"] for a in affected]
    # Force-refresh via the background manager. Its _run() reload()s
    # refresh_cache before executing, so the intraday back-up logic in the
    # latest refresh_symbol() is guaranteed to apply even without a server
    # restart.
    start_result = _cache_refresher.start(
        symbols=syms, force=True, indian_only=True, workers=workers,
    )
    return {
        "ok": True, "mode": "async",
        "count": len(affected),
        "affected_preview": affected[:50],
        "truncated": len(affected) > 50,
        "refresher": start_result,
        "message": f"Force-refreshing {len(affected)} intraday-stuck CSV(s) — "
                   f"poll /api/cache/refresh-status for progress.",
    }


# ── VPN / Proxy Toggle API ────────────────────────────────────────────────────
# Free-proxy-based outbound routing. Toggle enables/disables routing all
# outbound HTTP(S) traffic (Yahoo, NSE, yfinance, Groww, …) through a proxy.
# Providers:
#   • free   — rotated from public proxy lists (no account needed)
#   • custom — user-supplied URL, e.g. http://user:pass@host:port

class VpnConfigRequest(BaseModel):
    provider: Optional[Literal["free", "custom"]] = None
    custom_proxy_url: Optional[str] = None


@app.get("/api/vpn/status")
def vpn_status() -> dict:
    """Current VPN/proxy status — enabled flag, provider, active proxy, last test."""
    return _vpn.status()


@app.get("/api/groww/verify")
def groww_verify(symbol: str = "RELIANCE") -> dict:
    """End-to-end Groww health check. Returns whether Groww-only mode is on,
    whether credentials are set, whether the client initialized, and a
    live LTP probe for the given NSE symbol (default RELIANCE).

    Use this to debug "no data in UI" when GROWW_ONLY mode is enforced.
    """
    try:
        from groww_client import verify_groww_live
        return verify_groww_live(probe_symbol=symbol.upper())
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@app.post("/api/vpn/toggle")
def vpn_toggle() -> dict:
    """Flip VPN enabled state. Picks a fresh free proxy on enable."""
    try:
        return _vpn.toggle()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vpn/enable")
def vpn_enable() -> dict:
    try:
        return _vpn.enable()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vpn/disable")
def vpn_disable() -> dict:
    return _vpn.disable()


@app.post("/api/vpn/config")
def vpn_config(req: VpnConfigRequest) -> dict:
    """Update provider and/or custom proxy URL."""
    try:
        return _vpn.set_config(
            provider=req.provider,
            custom_proxy_url=req.custom_proxy_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vpn/rotate")
def vpn_rotate() -> dict:
    """Pick a new working free proxy (provider=free only)."""
    return _vpn.rotate()


@app.post("/api/vpn/test")
def vpn_test() -> dict:
    """Test current outbound routing — returns external IP seen by api.ipify.org."""
    return _vpn.test()


@app.post("/api/vpn/refresh-pool")
def vpn_refresh_pool() -> dict:
    """Force refresh of the free public proxy list."""
    return _vpn.refresh_free_pool()


@app.post("/api/vpn/health")
def vpn_health() -> dict:
    """Parallel health check: direct network vs through the VPN proxy.

    Returns latency (ms), download speed (KB/s), external IP, and reachability
    for the app's own data sources (Yahoo, NSE) for each route plus a
    comparison summary (slowdown %, verdict, IP-masked flag).
    """
    return _vpn.health_check()




# ── iCloud Backup ──────────────────────────────────────────────────────────

@app.get("/api/backup/status")
def backup_status() -> dict:
    """Get the last backup status."""
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from icloud_backup import get_backup_status
        return get_backup_status()
    except Exception as e:
        return {"configured": False, "error": str(e)}

@app.post("/api/backup/trigger")
def backup_trigger(force: bool = False) -> dict:
    """Manually trigger an iCloud backup."""
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from icloud_backup import run_backup
        result = run_backup(force=force)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




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
    market_prices = _get_fresh_nifty_benchmark(days=max(days, 252))
    if not market_prices:
        # Degrade gracefully for UI/tests when upstream data providers are unavailable.
        return {
            "nifty_current": None,
            "nifty_dates": [],
            "nifty_closes": [],
            "phases": [],
            "phase_summary": "Nifty data unavailable",
            "phase_count": 0,
            "recent_phases": [],
            "data_unavailable": True,
        }

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


def _recompute_position_realized_pl(p: dict) -> float:
    """Recompute total realized P&L including partial exits + final close leg."""
    entry = float(p.get("entry", 0) or 0)
    qty = int(p.get("quantity", 1) or 1)
    exits = p.get("partial_exits", []) or []
    partial_qty = sum(int(e.get("quantity", 0) or 0) for e in exits)
    partial_realized = sum(
        (float(e.get("price", 0) or 0) - entry) * int(e.get("quantity", 0) or 0)
        for e in exits
    )
    remaining_for_final = max(0, qty - partial_qty)
    exit_price = float(p.get("exit_price", entry) or entry)
    realized = partial_realized + (exit_price - entry) * remaining_for_final
    p["realized_pl"] = round(realized, 2)
    return p["realized_pl"]


def _compute_trailing_sl_candidate(p: dict, cmp: float) -> float | None:
    """1R trailing stop: trail to (highest-high since entry - initial risk)."""
    # If the user manually updated SL, do not override it with automation.
    # We still allow SL_HIT auto-close on breach; we only skip *trailing*.
    if p.get("sl_manual") is True:
        return None
    entry = float(p.get("entry", 0) or 0)
    sl = float(p.get("sl", 0) or 0)
    if entry <= 0 or sl <= 0:
        return None

    if not p.get("original_sl"):
        p["original_sl"] = sl
    initial_sl = float(p.get("original_sl", sl) or sl)
    initial_risk = max(0.0, entry - initial_sl)
    if initial_risk <= 0:
        return None

    rows = _read_ohlcv(p.get("symbol", ""), days=0)
    entry_date = (p.get("entry_date") or "")[:10]
    highs = [r.get("high", 0) for r in rows if (not entry_date or r.get("date", "") >= entry_date)]
    peak = max([cmp] + [float(h or 0) for h in highs])
    candidate = round(peak - initial_risk, 2)
    # Never trail SL above entry price — automation only trails to break-even max.
    # Moving SL above entry is a manual decision; auto-trailing beyond that would
    # close the position on normal pullbacks while still in profit.
    candidate = min(candidate, entry)
    if candidate > sl and candidate < cmp:
        return candidate
    return None


def _apply_trailing_stop_automation(data: dict) -> dict:
    """Auto-trail SL for open positions and auto-close when SL is breached."""
    positions = data.get("positions", []) or []
    changed = False
    trailed = 0
    closed = 0
    today = datetime.now().strftime("%Y-%m-%d")

    for p in positions:
        status = p.get("status", "OPEN")
        if status not in ("OPEN", "PARTIAL"):
            continue

        qty = int(p.get("quantity", 1) or 1)
        if p.get("remaining_quantity") is None:
            p["remaining_quantity"] = qty
            changed = True

        cmp, prev_close, last_date = _get_price_info(p.get("symbol", ""))
        if not cmp:
            continue

        p["cmp"] = round(cmp, 2)
        p["lastPriceDate"] = last_date
        if prev_close and prev_close > 0:
            rem = p.get("remaining_quantity") if p.get("remaining_quantity") is not None else qty
            p["dayChangePct"] = round((cmp - prev_close) / prev_close * 100, 2)
            p["dayChangeAmt"] = round((cmp - prev_close) * rem, 2)

        new_sl = _compute_trailing_sl_candidate(p, cmp)
        if new_sl is not None:
            p["sl"] = new_sl
            trailed += 1
            changed = True

        remaining = int(p.get("remaining_quantity") or p.get("quantity", 1) or 1)
        live_sl = float(p.get("sl", 0) or 0)
        entry_price = float(p.get("entry", 0) or 0)
        # ── SL arming ──────────────────────────────────────────────────────
        # Avoid instantly auto-closing a newly-added position if current price
        # is already at/below the user-entered SL (common when adding during
        # volatility or using stale quotes). We "arm" the SL only after the
        # price has traded above the SL at least once.
        if live_sl > 0:
            if p.get("sl_armed") is None:
                # Backward-compat: if a position predates this feature, treat it as armed
                # only if it's currently above SL; otherwise keep unarmed until it trades above.
                p["sl_armed"] = bool(cmp > live_sl)
                changed = True
            elif p.get("sl_armed") is False and cmp > live_sl:
                p["sl_armed"] = True
                changed = True
        # Only auto-close when:
        #  1. SL is set and CMP has breached it, AND
        #  2. The SL is at or below entry price (normal protective stop).
        # If SL has been trailed above entry (profit-lock zone), skip auto-close —
        # that is a manual decision; automation must not close profitable positions.
        # NOTE: We use a strict breach (cmp < sl). Touching the SL is not an exit.
        if (live_sl > 0 and p.get("sl_armed") is True and cmp < live_sl
                and remaining > 0 and (entry_price <= 0 or live_sl <= entry_price)):
            p["status"] = "SL_HIT"
            p["exit_price"] = round(cmp, 2)
            p["exit_date"] = today
            p["remaining_quantity"] = 0
            _recompute_position_realized_pl(p)
            closed += 1
            changed = True

    if changed:
        data["positions"] = positions
        _save_board(data)
    return {"changed": changed, "trailed": trailed, "closed": closed}

# ── Price / Chart helpers ──────────────────────────────────────────────────────

def _read_ohlcv(symbol: str, days: int = 0, market: str = "india") -> list[dict]:
    """Read OHLCV from cache. Returns sorted list of dicts with date/open/high/low/close/volume.
    days=0 means return ALL available data.
    • market="india"  → prefers SYMBOL.NS.csv, falls back to SYMBOL.csv (legacy).
    • market="us"     → reads SYMBOL.csv directly (no .NS).
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
    # For US symbols (ADRs etc.) skip the .NS prefix entirely so we don't
    # pick up a same-named Indian stock by accident (e.g. INFY vs INFY.NS).
    prefixes = [base] if market == "us" else [ns, base]
    for prefix in prefixes:
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
    #
    # BUT: when a bulk caller (industry-groups compute) has set the
    # skip_stale_refresh thread-local flag, suppress the spawn — otherwise
    # a single compute over 2000+ tickers would launch thousands of daemon
    # threads that saturate CPU / lock / Yahoo. The periodic OHLCV refresher
    # (_cache_refresher) handles on-disk freshness for that path.
    if _bulk_skip_stale():
        pass
    elif rows:
        last_date = rows[-1]["date"]
        # Prefer the actual CSV file used for the read (falls back to .NS.csv)
        _csv_for_stale = CACHE_DIR / f"{base}.NS.csv"
        if not _csv_for_stale.exists():
            _csv_for_stale = CACHE_DIR / f"{base}.csv"
        if _is_price_stale(last_date, _csv_for_stale):
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


# ── Fresh Nifty benchmark helper ──────────────────────────────────────────
# Every page that shows a "Nifty asof" or relies on the Nifty benchmark
# must route through this function so they all share the same source and
# freshness semantics:
#   1. Primary:  OHLCV CSV cache (cache/^NSEI.csv) — same source as stock
#                data, kept fresh by BackgroundCacheRefresher + the IST-aware
#                staleness check.
#   2. If the OHLCV bar is stale (past-close intraday, or >0 biz-day gap),
#      do a SYNCHRONOUS refresh_nifty_index() call — single symbol, ≤2 s —
#      then re-read the cache. Guarantees nifty_asof == current trading day
#      by the time the calling endpoint returns.
#   3. If the OHLCV cache stays empty after refresh, fall back to
#      _wpe.fetch_market_prices (yfinance side-cache). Whichever has the
#      newer last-date wins.
_NIFTY_BENCHMARK_LOCK = threading.Lock()
_NIFTY_LAST_SYNC_TS: float = 0
_NIFTY_SYNC_COOLDOWN = 60  # seconds — avoid hammering refresh_nifty_index
_NIFTY_RESULT_CACHE: dict = {}  # days → {"data": dict, "ts": float, "asof": str}
_NIFTY_RESULT_TTL = 30         # seconds — memoize helper output to amortize fallback cost


def _get_fresh_nifty_benchmark(days: int = 260) -> dict | None:
    """Return a Nifty50 price dict in wpe format with the freshest possible
    last-date. See section header above for the source-priority rules.

    Safe to call from any endpoint — the sync refresh is cooldowned
    (`_NIFTY_SYNC_COOLDOWN` seconds) so bursts of parallel requests don't
    each trigger a Yahoo hit.
    """
    global _NIFTY_LAST_SYNC_TS

    # Fast path: recent memoized result.
    cached = _NIFTY_RESULT_CACHE.get(days)
    if cached and (time.time() - cached.get("ts", 0)) < _NIFTY_RESULT_TTL:
        return cached["data"]

    def _read_csv_rows() -> list[dict]:
        try:
            return _read_ohlcv("^NSEI", days=days, market="us") or []
        except Exception:
            return []

    rows = _read_csv_rows()
    nifty_csv = CACHE_DIR / "^NSEI.csv"

    # Sync refresh if stale — but only once per cooldown window per process.
    ran_sync_refresh = False
    try:
        if rows and _is_price_stale(rows[-1]["date"], nifty_csv):
            with _NIFTY_BENCHMARK_LOCK:
                now_ts = time.time()
                if now_ts - _NIFTY_LAST_SYNC_TS >= _NIFTY_SYNC_COOLDOWN:
                    _NIFTY_LAST_SYNC_TS = now_ts
                    ran_sync_refresh = True
                    try:
                        sys.path.insert(0, str(ROOT / "scripts"))
                        import refresh_cache as _rc
                        _rc.refresh_nifty_index()
                        rows = _read_csv_rows()
                    except Exception as _e:
                        print(f"⚠ _get_fresh_nifty_benchmark sync refresh failed: {_e}", flush=True)
                    # Only kick the full OHLCV refresher when we actually ran a
                    # sync refresh AND it didn't produce fresh bars (likely Yahoo
                    # doesn't have today's close yet or network issue).
                    if (not rows or _is_price_stale(rows[-1]["date"], nifty_csv)) \
                            and not _cache_refresher.is_running:
                        _cache_refresher.start(indian_only=True, workers=4)
    except Exception:
        pass

    primary = None
    if rows and len(rows) >= 20:
        primary = {
            "symbol": "^NSEI", "yf_symbol": "^NSEI",
            "dates":  [r["date"]  for r in rows],
            "open":   [r["open"]  for r in rows],
            "high":   [r["high"]  for r in rows],
            "low":    [r["low"]   for r in rows],
            "close":  [r["close"] for r in rows],
            "volume": [r["volume"] for r in rows],
        }

    # Fallback + newer-source check: only hit the yfinance side-cache when
    # the primary is empty OR we just tried a sync refresh and it failed to
    # advance the date. Otherwise we'd pay yfinance latency on every request.
    result = primary
    try:
        primary_stale = bool(rows) and _is_price_stale(rows[-1]["date"], nifty_csv)
        if (primary is None) or (primary_stale and ran_sync_refresh):
            alt = _wpe.fetch_market_prices(days=days)
            if alt and alt.get("dates"):
                if primary is None or alt["dates"][-1] > primary["dates"][-1]:
                    if primary is not None:
                        print(f"🔁 Nifty benchmark: using _wpe source (asof={alt['dates'][-1]}) "
                              f"over OHLCV (asof={primary['dates'][-1]})", flush=True)
                    result = alt
    except Exception:
        pass

    if result is not None:
        _NIFTY_RESULT_CACHE[days] = {
            "data": result,
            "ts": time.time(),
            "asof": (result.get("dates") or [None])[-1],
        }
    return result


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
_nse_fetch_lock = threading.Lock()   # serialize NSE requests to avoid rate-limiting
_LIVE_TTL_MARKET = 30    # seconds — during market hours
_LIVE_TTL_OFF = 300      # seconds — outside market hours (5 min, just to get today's close)

# ── Groww API integration ─────────────────────────────────────────────────
# Uses shared groww_client module for singleton initialization.
# Env vars: GROWW_API_KEY, GROWW_API_SECRET, GROWW_ACCESS_TOKEN
_GROWW_API_KEY = os.environ.get("GROWW_API_KEY", "").strip().strip("'\"")
_GROWW_API_SECRET = os.environ.get("GROWW_API_SECRET", "").strip().strip("'\"")
_GROWW_ACCESS_TOKEN = os.environ.get("GROWW_ACCESS_TOKEN", "").strip().strip("'\"")
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
                    # Auto-detect TOTP vs approval auth from JWT payload
                    auth_kwargs = {"secret": _GROWW_API_SECRET}
                    try:
                        import base64 as _b64, json as _j
                        parts = _GROWW_API_KEY.split('.')
                        if len(parts) == 3:
                            payload = parts[1] + '=' * (4 - len(parts[1]) % 4)
                            sub = _j.loads(_j.loads(_b64.b64decode(payload)).get('sub', '{}'))
                            if 'totp' in sub.get('role', '').lower():
                                import hmac, hashlib, struct, time as _tm
                                seed = _GROWW_API_SECRET.strip().upper().replace(' ', '')
                                missing = len(seed) % 8
                                if missing:
                                    seed += '=' * (8 - missing)
                                key_bytes = _b64.b32decode(seed)
                                counter = int(_tm.time()) // 30
                                h = hmac.new(key_bytes, struct.pack('>Q', counter), hashlib.sha1).digest()
                                o = h[-1] & 0x0F
                                code = (struct.unpack('>I', h[o:o+4])[0] & 0x7FFFFFFF) % 1000000
                                auth_kwargs = {"totp": f"{code:06d}"}
                    except Exception:
                        pass
                    result = GrowwAPI.get_access_token(
                        api_key=_GROWW_API_KEY, **auth_kwargs)
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


def _reset_groww_on_auth_error(e: Exception):
    """If Groww returns forbidden/auth error, reset client so token gets refreshed."""
    err_str = str(e).lower()
    if "forbidden" in err_str or "authoris" in err_str or "unauthori" in err_str:
        try:
            from groww_client import reset_groww_client
            reset_groww_client()
            global _groww_client, _groww_init_failed
            _groww_client = None
            _groww_init_failed = False
            print(f"⚠ Groww auth error — will refresh token: {e}", flush=True)
        except Exception:
            pass


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
    except Exception as e:
        _reset_groww_on_auth_error(e)
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
    except Exception as e:
        _reset_groww_on_auth_error(e)
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
    with _nse_fetch_lock:  # serialize to avoid NSE rate-limiting
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

    # Groww-only gate: for Indian symbols, forbid silent fallback to
    # geo-blocked Yahoo/NSE. If Groww failed, surface the failure (cache
    # CSV fallback happens at caller layer, which is fine).
    try:
        from groww_client import should_use_non_groww_source
        _allow_fallback = should_use_non_groww_source(base + ".NS")
    except Exception:
        _allow_fallback = True

    # 2. During market hours: try NSE (fast for live intraday)
    if not quote and market_open and _allow_fallback:
        quote = _fetch_live_quote_nse(base)

    # 3. Yahoo v8
    if not quote and _allow_fallback:
        ns_sym = base + ".NS"
        quote = _fetch_live_quote_yahoo(ns_sym)

    # 4. yfinance fallback
    if not quote and _allow_fallback:
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


def _get_price_info(symbol: str, market: str = "india") -> tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Returns (cmp, prev_close, last_date) for a symbol.

    During market hours: fetches LIVE price from NSE/Yahoo/yfinance APIs (30s TTL).
    Outside market hours: fetches latest close from Yahoo/yfinance (5min TTL),
      falling back to CSV cache if APIs fail.
    Always returns the most current price available.
    """
    rows = _read_ohlcv(symbol, days=5, market=market)
    csv_close = rows[-1]["close"] if rows else None
    csv_prev = rows[-2]["close"] if len(rows) >= 2 else None
    csv_date = rows[-1]["date"] if rows else None

    # Skip live-quote fetch for US symbols (Groww/NSE not applicable); use CSV.
    if market == "us":
        return csv_close, csv_prev, csv_date

    # Try live/latest price (works both during and outside market hours now)
    live = _get_live_price(symbol)
    if live and live.get("price"):
        cmp = live["price"]
        prev = live.get("prevClose") or csv_prev
        # Use today's date when live price is available so frontend doesn't flag as stale
        today_str = datetime.now(_IST).strftime("%Y-%m-%d")
        return cmp, prev, today_str
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
        remaining = p.get("remaining_quantity") if p.get("remaining_quantity") is not None else qty
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
            # Closed position: use realized_pl if available (already includes
            # partial exits + final close), else compute from exit_price
            if pos_realized:
                pl = pos_realized
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
    from concurrent.futures import ThreadPoolExecutor
    with _board_lock:
        data = _load_board()
        _apply_trailing_stop_automation(data)
        positions = data.get("positions", [])
    # Parallel live price pre-warm
    open_syms = list({p.get("symbol", "") for p in positions
                      if p.get("status") in ("OPEN", "PARTIAL") and p.get("symbol")})
    if open_syms:
        with ThreadPoolExecutor(max_workers=min(8, len(open_syms))) as pool:
            list(pool.map(_get_live_price, open_syms))
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


@app.get("/api/trade-board/positions/fast")
def trade_board_positions_fast(status: str = "") -> dict:
    """Ultra-fast positions endpoint: returns raw data from disk with CSV-cached
    prices only (no live API calls). ~50ms. Use for initial UI render."""
    with _board_lock:
        data = _load_board()
        _apply_trailing_stop_automation(data)
        positions = list(data.get("positions", []))
    for p in positions:
        entry = p.get("entry", 0) or 0
        qty   = p.get("quantity", 1) or 1
        remaining = p.get("remaining_quantity") or qty
        if p.get("status") in ("OPEN", "PARTIAL"):
            # CSV-only price (no live API calls)
            rows = _read_ohlcv(p.get("symbol", ""), days=5)
            cmp = rows[-1]["close"] if rows else None
            prev_close = rows[-2]["close"] if len(rows) >= 2 else None
            last_date = rows[-1]["date"] if rows else None
            if cmp:
                p["cmp"] = round(cmp, 2)
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
    if status:
        positions = [p for p in positions if p.get("status") == status]
    positions.sort(key=lambda p: (
        0 if p.get("status") in ("OPEN", "PARTIAL") else 1,
        -float(p.get("gainPct", 0) or 0)))
    stats = _compute_board_stats(positions)
    return {"positions": positions, "stats": stats, "lastUpdated": data.get("lastUpdated")}


@app.get("/api/trade-board/watchlist/fast")
def get_watchlist_fast() -> dict:
    """Ultra-fast watchlist endpoint: returns raw data from disk with CSV-cached
    prices only (no live API calls). ~100ms. Use for initial UI render."""
    with _watchlist_lock:
        items = _load_watchlist()
    sig_index = _load_scan_signals_index()
    for item in items:
        sym = item.get("symbol", "")
        mkt = item.get("market") or "india"
        # CSV-only price (no live API calls)
        rows = _read_ohlcv(sym, days=5, market=mkt)
        cmp = rows[-1]["close"] if rows else None
        prev_close = rows[-2]["close"] if len(rows) >= 2 else None
        last_date = rows[-1]["date"] if rows else None
        if cmp:
            item["cmp"] = round(cmp, 2)
            item["lastPriceDate"] = last_date
        if cmp and prev_close and prev_close > 0:
            item["dayChangePct"] = round((cmp - prev_close) / prev_close * 100, 2)
        ap = item.get("add_price")
        if cmp and ap and ap > 0:
            item["returnSinceAddPct"] = round((cmp - ap) / ap * 100, 2)
            item["returnSinceAddAbs"] = round(cmp - ap, 2)
        # Scan signal enrichment (no network calls)
        sig = sig_index.get(sym) or sig_index.get(sym + ".NS") or sig_index.get(sym.replace(".NS", ""))
        if sig:
            item["scanSetup"] = sig.get("setup", "")
            item["scanRating"] = sig.get("rating", "")
            item["scanScore"] = sig.get("rankingScore") or sig.get("score")
            item["scanEntry"] = sig.get("entry")
            item["scanSl"] = sig.get("sl")
            item["rsScore"] = sig.get("rsScore")
            item["inScan"] = True
        else:
            item["inScan"] = False
    return {
        "items": items, "total": len(items),
        "buckets": WATCHLIST_BUCKETS, "setups": WATCHLIST_SETUPS,
    }


@app.get("/api/trade-board/positions")
def trade_board_positions(status: str = "") -> dict:
    from concurrent.futures import ThreadPoolExecutor
    with _board_lock:
        data = _load_board()
        _apply_trailing_stop_automation(data)
        positions = list(data.get("positions", []))
    # Parallel live price pre-warm for open positions
    open_syms = list({p.get("symbol", "") for p in positions
                      if p.get("status") in ("OPEN", "PARTIAL") and p.get("symbol")})
    if open_syms:
        with ThreadPoolExecutor(max_workers=min(8, len(open_syms))) as pool:
            list(pool.map(_get_live_price, open_syms))
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
    if (pos_dict.get("sl") or 0) > 0 and not pos_dict.get("original_sl"):
        pos_dict["original_sl"] = pos_dict["sl"]
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
                if "sl" in upd and upd.get("sl") is not None and not positions[i].get("original_sl"):
                    positions[i]["original_sl"] = upd.get("sl")
                # If user explicitly set SL via update endpoint, treat it as manual
                # so trailing automation doesn't immediately overwrite it.
                if "sl" in upd and upd.get("sl") is not None:
                    positions[i]["sl_manual"] = bool(float(upd.get("sl") or 0) > 0)
                # If status is a closing status and exit_price is set,
                # auto-compute realized_pl for the remaining shares
                new_status = positions[i].get("status", "OPEN")
                closing_statuses = ("CLOSED", "SL_HIT", "T1_HIT", "T2_HIT", "T3_HIT")
                if new_status in closing_statuses and positions[i].get("exit_price"):
                    _recompute_position_realized_pl(positions[i])
                    positions[i]["remaining_quantity"] = 0
                    # Auto-set exit_date if not provided
                    if not positions[i].get("exit_date"):
                        positions[i]["exit_date"] = datetime.now().strftime("%Y-%m-%d")
                elif new_status in ("OPEN", "PARTIAL"):
                    qty = int(positions[i].get("quantity", 1) or 1)
                    exits = positions[i].get("partial_exits", []) or []
                    partial_qty = sum(int(e.get("quantity", 0) or 0) for e in exits)
                    remaining = max(0, qty - partial_qty)

                    if remaining <= 0:
                        # All shares were exited via partial_exits — full undo: clear them and restore full qty.
                        positions[i]["partial_exits"] = []
                        remaining = qty

                    # Restore remaining quantity, clear close metadata.
                    positions[i]["remaining_quantity"] = remaining
                    positions[i]["exit_price"] = None
                    positions[i]["exit_date"] = None

                    # Recompute realized from whatever partial exits remain.
                    remaining_exits = positions[i].get("partial_exits", []) or []
                    partial_realized = sum(
                        (float(e.get("price", 0) or 0) - float(positions[i].get("entry", 0) or 0))
                        * int(e.get("quantity", 0) or 0)
                        for e in remaining_exits
                    )
                    positions[i]["realized_pl"] = round(partial_realized, 2)

                    # Normalize status: PARTIAL if some shares already booked, else OPEN.
                    if remaining < qty:
                        positions[i]["status"] = "PARTIAL"
                    else:
                        positions[i]["status"] = "OPEN"
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
            if req.price <= 0:
                raise HTTPException(status_code=400, detail="price must be > 0")

            # Resolve quantity: explicit shares or full remaining via exit_all.
            exit_qty = remaining if req.exit_all else (req.quantity or 0)

            # Validate
            if exit_qty <= 0:
                raise HTTPException(status_code=400, detail="quantity must be > 0")
            if exit_qty > remaining:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot exit {exit_qty} shares — only {remaining} remaining")
            # Record partial exit
            exits = p.get("partial_exits", [])
            exits.append({
                "date": req.date,
                "quantity": exit_qty,
                "price": req.price,
                "reason": req.reason,
            })
            remaining -= exit_qty
            positions[i]["partial_exits"] = exits
            positions[i]["remaining_quantity"] = remaining
            # Compute realized P&L from all partial exits
            entry = p.get("entry", 0)
            realized_pl = sum((e["price"] - entry) * e["quantity"] for e in exits)
            positions[i]["realized_pl"] = round(realized_pl, 2)
            # Auto-update status
            if remaining <= 0:
                positions[i]["status"] = "CLOSED"
                # Compute weighted avg exit price
                total_exited = sum(e["quantity"] for e in exits)
                if total_exited > 0:
                    wavg = sum(e["price"] * e["quantity"] for e in exits) / total_exited
                    positions[i]["exit_price"] = round(wavg, 2)
                _recompute_position_realized_pl(positions[i])
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
    mkt = p.get("market") or "india"
    rows = _read_ohlcv(sym, days=300, market=mkt)  # need ~252 for yearly volume analysis
    # Inject live price into the latest bar so EMA/metrics reflect current price
    if rows:
        live = _get_live_price(sym) if mkt != "us" else None
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
    """Return positions enriched with 20EMA extension + volume records.
    Live prices are fetched in parallel (ThreadPoolExecutor) for speed."""
    from concurrent.futures import ThreadPoolExecutor
    with _board_lock:
        data = _load_board()
        trail_state = _apply_trailing_stop_automation(data)
        positions = list(data.get("positions", []))

    # ── PARALLEL live price pre-warm for all open positions ──────────────
    open_positions = [p for p in positions if p.get("status") in ("OPEN", "PARTIAL")]
    open_syms = list({p.get("symbol", "") for p in open_positions if p.get("symbol")})
    if open_syms:
        with ThreadPoolExecutor(max_workers=min(8, len(open_syms))) as pool:
            list(pool.map(_get_live_price, open_syms))

    # ── Enrichment helper (called per position in parallel) ─────────────
    def _enrich_one(p):
        entry = p.get("entry", 0) or 0
        qty = p.get("quantity", 1) or 1
        remaining = p.get("remaining_quantity") if p.get("remaining_quantity") is not None else qty
        st = p.get("status", "OPEN")
        if st in ("OPEN", "PARTIAL"):
            cmp, prev_close, last_date = _get_price_info(p.get("symbol", ""))
            if cmp:
                p["cmp"] = round(cmp, 2)
                p["gainPct"] = round((cmp - entry) / entry * 100, 2) if entry else 0
                unrealized = (cmp - entry) * remaining
                pos_realized = p.get("realized_pl", 0) or 0
                p["gainAmt"] = round(unrealized + pos_realized, 2) if entry else 0
                p["lastPriceDate"] = last_date
            if cmp and prev_close and prev_close > 0:
                p["dayChangePct"] = round((cmp - prev_close) / prev_close * 100, 2)
                p["dayChangeAmt"] = round((cmp - prev_close) * remaining, 2)
            _enrich_position_metrics(p)
        elif entry:
            pos_realized = p.get("realized_pl", 0) or 0
            ep = float(p.get("exit_price") or entry)
            if pos_realized:
                p["gainAmt"] = round(pos_realized, 2)
                p["gainPct"] = round(pos_realized / (entry * qty) * 100, 2) if entry and qty else 0
            elif ep:
                p["gainPct"] = round((ep - entry) / entry * 100, 2)
                p["gainAmt"] = round((ep - entry) * qty, 2)

    # Run enrichment in parallel threads (mostly I/O bound — CSV reads + cached price lookups)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_enrich_one, positions))

    if status:
        positions = [p for p in positions if p.get("status") == status]
    positions.sort(key=lambda p: (
        0 if p.get("status") in ("OPEN", "PARTIAL") else 1,
        -float(p.get("gainPct", 0) or 0)))
    stats = _compute_board_stats(positions)
    return {"positions": positions, "stats": stats,
            "lastUpdated": data.get("lastUpdated"),
            "marketOpen": _is_market_open(),
            "trailing": trail_state}


@app.get("/api/trade-board/watchlist/enriched")
def trade_board_watchlist_enriched() -> dict:
    """Return watchlist items enriched with CMP, day-change, return-since-add,
    cross-market pair, scan signal, 20EMA extension & volume records (parallelized)."""
    from concurrent.futures import ThreadPoolExecutor
    with _watchlist_lock:
        items = _load_watchlist()
    sig_index = _load_scan_signals_index()

    # ── PARALLEL live price pre-warm (batch up to 10 concurrent) ─────────
    india_syms = list({item.get("symbol", "") for item in items
                       if item.get("symbol") and (item.get("market") or "india") != "us"})
    if india_syms:
        with ThreadPoolExecutor(max_workers=min(10, len(india_syms))) as pool:
            list(pool.map(_get_live_price, india_syms))

    def _enrich_wl(item):
        _enrich_watchlist_item_lite(item, sig_index)
        # Heavy metrics (EMA20, vol records, ADR, RSI, SMA200…)
        _enrich_position_metrics(item)
        # fundSummary is only exposed via the enriched variant
        sym = item.get("symbol", "")
        sig = sig_index.get(sym) or sig_index.get(sym + ".NS") or sig_index.get(sym.replace(".NS", ""))
        if sig and sig.get("fundSummary"):
            item["fundSummary"] = sig.get("fundSummary")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_enrich_wl, items))

    return {
        "items": items, "total": len(items),
        "buckets": WATCHLIST_BUCKETS, "setups": WATCHLIST_SETUPS,
        "marketOpen": _is_market_open(),
    }


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


# Mini-chart RS benchmarks (Yahoo / cache tickers; mid/small verified via yfinance)
_RS_CHART_NIFTY50 = "^NSEI"
_RS_CHART_MIDCAP100 = "NIFTY_MIDCAP_100.NS"
_RS_CHART_MIDCAP_ALT = "^NSMIDCAP"  # Yahoo Nifty Midcap 150 if .NS cache missing
_RS_CHART_SMLCAP100 = "^CNXSC"


def _normalized_close_series(rows: list[dict]) -> list[tuple[str, float]]:
    """Return date-sorted unique (date, close) pairs with valid positive closes."""
    by_date: dict[str, float] = {}
    for r in rows or []:
        d = str(r.get("date", ""))[:10]
        c = r.get("close")
        if not d or c is None:
            continue
        try:
            cv = float(c)
        except (TypeError, ValueError):
            continue
        if cv > 0:
            by_date[d] = cv
    return sorted(by_date.items(), key=lambda x: x[0])


def _date_lag_days(newer: str, older: str) -> Optional[int]:
    try:
        nd = datetime.strptime(newer, "%Y-%m-%d")
        od = datetime.strptime(older, "%Y-%m-%d")
        return (nd - od).days
    except Exception:
        return None


def _rs_line_vs_benchmark(stock_rows: list[dict], bench_rows: list[dict]) -> list[dict]:
    """Relative strength vs index: first aligned session = 100; then (s/s0)/(i/i0)*100."""
    stock = _normalized_close_series(stock_rows)
    bench = _normalized_close_series(bench_rows)
    if len(stock) < 2 or len(bench) < 2:
        return []

    aligned: list[tuple[str, float, float]] = []
    j = 0
    max_lag_days = 7  # allow normal holiday/weekend gaps between stock/index sessions
    for d, sc in stock:
        while j + 1 < len(bench) and bench[j + 1][0] <= d:
            j += 1
        bd, bc = bench[j]
        if bd > d or bc <= 0:
            continue
        lag = _date_lag_days(d, bd)
        if lag is not None and lag > max_lag_days:
            continue
        aligned.append((d, sc, bc))

    if len(aligned) < 2:
        return []

    _d0, s0, b0 = aligned[0]
    if s0 <= 0 or b0 <= 0:
        return []
    out: list[dict] = []
    for d, s, b in aligned:
        if b <= 0:
            continue
        rs = (s / s0) / (b / b0) * 100.0
        out.append({"time": d, "value": round(rs, 4)})
    return out


def _build_rs_snapshot(rs_lines: dict[str, list[dict]]) -> dict:
    """Compact RS summary for UI badges/details from per-benchmark RS lines."""
    labels = {
        "nifty50": "Nifty 50",
        "niftyMidcap100": "Nifty Midcap 100",
        "niftySmallcap100": "Nifty Smallcap 100",
    }
    bench_stats: dict[str, dict] = {}
    for key, pts in (rs_lines or {}).items():
        if not isinstance(pts, list) or len(pts) < 2:
            continue
        vals = [p.get("value") for p in pts if isinstance(p, dict) and p.get("value") is not None]
        if len(vals) < 2:
            continue
        last = float(vals[-1])
        prev_5 = float(vals[max(0, len(vals) - 6)])
        prev_20 = float(vals[max(0, len(vals) - 21)])
        d5 = round(last - prev_5, 2)
        d20 = round(last - prev_20, 2)
        trend = "up" if d5 > 0.75 else "down" if d5 < -0.75 else "flat"
        bench_stats[key] = {
            "label": labels.get(key, key),
            "last": round(last, 2),
            "delta5": d5,
            "delta20": d20,
            "trend": trend,
            "points": len(vals),
        }
    if not bench_stats:
        return {}
    leader_key = max(bench_stats.keys(), key=lambda k: bench_stats[k]["last"])
    return {
        "leader": leader_key,
        "leaderLabel": bench_stats[leader_key]["label"],
        "leaderLast": bench_stats[leader_key]["last"],
        "leaderDelta20": bench_stats[leader_key]["delta20"],
        "benchmarks": bench_stats,
    }


@app.get("/api/trade-board/chart/{symbol}")
def trade_board_chart(symbol: str, days: int = 252, market: str = "india") -> dict:
    mkt = (market or "india").lower()
    if mkt not in ("india", "us"):
        mkt = "india"
    rows = _read_ohlcv(
        symbol,
        days=max(days, 30) if days > 0 else 0,
        market=mkt,
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}")

    # ── Append / update today's live bar during market hours ──────────────
    # The CSV cache only has completed daily bars.  During market hours the
    # latest bar may be yesterday's close.  Fetch live price and either
    # update today's row (if cache already has today) or append a new one.
    # US symbols: skip Groww/NSE live merge (quotes target .NS); CSV bar is enough.
    live = None if mkt == "us" else _get_live_price(symbol)
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

    rs_lines: dict[str, list[dict]] = {}
    rs_snapshot: dict = {}
    if mkt == "india":
        # Full history for indices so every bar in `rows` can align (trim is cheap).
        try:
            n50 = _read_ohlcv(_RS_CHART_NIFTY50, days=0, market="us") or []
            mid = _read_ohlcv(_RS_CHART_MIDCAP100, days=0, market="india") or []
            if len(mid) < 20:
                mid = _read_ohlcv(_RS_CHART_MIDCAP_ALT, days=0, market="us") or []
            sml = _read_ohlcv(_RS_CHART_SMLCAP100, days=0, market="us") or []
            rs_lines["nifty50"] = _rs_line_vs_benchmark(rows, n50)
            rs_lines["niftyMidcap100"] = _rs_line_vs_benchmark(rows, mid)
            rs_lines["niftySmallcap100"] = _rs_line_vs_benchmark(rows, sml)
            rs_snapshot = _build_rs_snapshot(rs_lines)
        except Exception:
            rs_lines = {}
            rs_snapshot = {}

    return {
        "symbol": symbol, "market": mkt, "days": len(rows), "avgVol20": round(avg_vol, 0),
        "avgVol50": round(avg_vol_50, 0),
        "cmp": closes[-1],
        "lastDate": last_date,
        "high52w": round(high_52w, 2), "low52w": round(low_52w, 2),
        "pctFrom52wHigh": pct_from_52w_high,
        "distDays50": dist_days, "accumDays50": accum_days,
        "rsi": rsi14[-1] if rsi14 and rsi14[-1] is not None else None,
        "adr": adr_abs, "adrPct": adr_pct,
        "rsLines": rs_lines,
        "rsSnapshot": rs_snapshot,
        "candles": rows
    }

@app.get("/api/trade-board/equity")
def trade_board_equity() -> dict:
    """Compute equity curve from closed+open positions, including partial exits."""
    with _board_lock:
        data = _load_board()
        _apply_trailing_stop_automation(data)
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

        # Add full close event for any remaining shares not covered by partial exits.
        if status not in ("OPEN", "PARTIAL"):
            partial_qty = sum(pe["quantity"] for pe in p.get("partial_exits", []))
            remaining_at_close = max(0, qty - partial_qty)
            if remaining_at_close > 0:
                exit_p = p.get("exit_price") or entry
                pl = (exit_p - entry) * remaining_at_close
                events.append({
                    "date": p.get("exit_date") or p.get("entry_date", ""),
                    "symbol": sym,
                    "pl": round(pl, 2),
                    "status": status,
                    "type": "close",
                })

    events.sort(key=lambda e: e.get("date", ""))

    # IMPORTANT: LightweightCharts requires strictly ascending, UNIQUE time
    # values. When multiple exits share a date (e.g. two T3 hits same day, or
    # a full close + a partial on the same day), we MUST aggregate them into
    # a single curve point — otherwise the chart silently fails to draw any
    # line/area (axis still renders, so the bug is easy to miss visually).
    daily_pl: dict[str, float] = {}
    daily_symbols: dict[str, list[str]] = {}
    daily_events: dict[str, list[dict]] = {}
    for ev in events:
        d = ev.get("date") or ""
        daily_pl[d] = daily_pl.get(d, 0.0) + ev["pl"]
        daily_symbols.setdefault(d, []).append(ev.get("symbol", ""))
        daily_events.setdefault(d, []).append(ev)

    for d in sorted(daily_pl.keys()):
        pl = round(daily_pl[d], 2)
        total += pl
        # Keep per-day events for drill-down, but the top-level curve is
        # date-unique so the frontend chart library is happy.
        curve.append({
            "date": d,
            "pl": pl,
            "cumPl": round(total, 2),
            "symbol": ", ".join(sorted(set(s for s in daily_symbols[d] if s))),
            "status": daily_events[d][-1].get("status", ""),
            "type": "aggregate" if len(daily_events[d]) > 1 else daily_events[d][0].get("type", "close"),
            "events": daily_events[d],
        })

    return {"curve": curve, "totalPl": round(total, 2)}



# ── Trade Journal ──────────────────────────────────────────────────────────────
_journal_lock = threading.Lock()

def _load_journal() -> list:
    if not TRADE_JOURNAL_JSON.exists():
        return []
    try:
        raw = json.loads(TRADE_JOURNAL_JSON.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        normalized: list[dict] = []
        for e in raw:
            if not isinstance(e, dict):
                continue
            x = dict(e)
            # Backward/forward-compatible normalization for evolving journal schema.
            x.setdefault("symbol", "")
            x.setdefault("one_line_summary", "")
            x.setdefault("observations", "")
            x.setdefault("action_plan", "")
            x.setdefault("anchor_thought", "")
            x.setdefault("mood", "")
            x.setdefault("moods", [])
            if not isinstance(x.get("moods"), list):
                x["moods"] = []
            if not x["moods"] and isinstance(x.get("mood"), str) and x.get("mood"):
                x["moods"] = [x["mood"]]
            normalized.append(x)
        return normalized
    except Exception:
        return []

def _save_journal(entries: list) -> None:
    TRADE_JOURNAL_JSON.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")

class JournalEntry(BaseModel):
    symbol: str = ""
    date: str = ""
    title: str = ""
    body: str = ""
    mood: str = ""   # bullish/bearish/neutral/fearful/greedy/disciplined/fomo/revenge
    moods: list[str] = Field(default_factory=list)  # allow multi-select overall mood
    tags: list[str] = Field(default_factory=list)
    # ── Advanced journal fields ──
    category: str = ""  # trade_entry/trade_exit/trade_review/market_analysis/cash_decision/lesson/mistake/rules
    entry_type: str = ""  # pre_trade/during_trade/post_trade/daily_review/weekly_review
    # Trade context
    trade_id: str = ""  # Link to a position
    direction: str = ""  # long/short
    setup_type: str = ""  # VCP/breakout/bull_flag etc
    entry_price: float = 0
    exit_price: float = 0
    stop_loss: float = 0
    position_size: int = 0
    risk_amount: float = 0
    risk_pct: float = 0  # % of capital risked
    # Decision framework
    thesis: str = ""  # Why entering/exiting
    conviction: int = 0  # 1-5 scale
    followed_rules: bool = True
    rule_violations: list[str] = Field(default_factory=list)
    # Emotional state
    emotions: list[str] = Field(default_factory=list)
    stress_level: int = 0  # 1-5
    # Outcome & lessons
    outcome: str = ""  # win/loss/breakeven/avoided
    pnl_amount: float = 0
    r_multiple: float = 0
    lesson_learned: str = ""
    what_went_well: str = ""
    what_went_wrong: str = ""
    would_take_again: bool = True
    # Screenshots (stored as base64 data URLs or file paths)
    screenshots: list[str] = Field(default_factory=list)
    # Rating
    execution_rating: int = 0  # 1-5 stars
    # ── New advanced fields ──
    market_condition: str = ""  # trending_up/trending_down/range_bound/volatile/uncertain
    sector_strength: str = ""  # strong/neutral/weak
    timeframe: str = ""  # intraday/swing/positional
    pre_trade_checklist: list[str] = Field(default_factory=list)
    capital_deployed_pct: float = 0  # % of total capital in this trade
    account_balance: float = 0  # account balance at time of entry
    # Readability / blog-style helpers
    one_line_summary: str = ""
    observations: str = ""
    action_plan: str = ""
    anchor_thought: str = ""

@app.get("/api/trade-journal")
def get_journal(symbol: str = "", limit: int = 200, category: str = "", search: str = "", date_from: str = "", date_to: str = "") -> dict:
    with _journal_lock:
        entries = _load_journal()
    if symbol:
        entries = [e for e in entries if e.get("symbol","").upper() == symbol.upper()]
    if category:
        entries = [e for e in entries if e.get("category","") == category]
    if search:
        q = search.lower()
        entries = [e for e in entries if q in (e.get("title","") + " " + e.get("body","") + " " + e.get("thesis","") + " " + e.get("symbol","") + " " + e.get("lesson_learned","")).lower()]
    if date_from:
        entries = [e for e in entries if e.get("date","") >= date_from]
    if date_to:
        entries = [e for e in entries if e.get("date","") <= date_to]
    entries.sort(key=lambda e: e.get("date",""), reverse=True)

    # ── Compute comprehensive journal analytics ──
    total = len(entries)
    moods = {}
    categories = {}
    emotions_count = {}
    rules_followed = 0
    rules_broken = 0
    # Trade performance
    wins = 0; losses = 0; breakevens = 0; avoided = 0
    total_pnl = 0.0; win_pnl = 0.0; loss_pnl = 0.0
    r_multiples = []
    # Setup performance
    setup_stats = {}  # {setup: {wins, losses, total_pnl, r_multiples}}
    # Monthly breakdown
    monthly = {}  # {YYYY-MM: {entries, wins, losses, pnl}}
    # Date heatmap (entries per date)
    date_counts = {}
    # Emotion-outcome correlation
    emotion_outcomes = {}  # {emotion: {win, loss, total}}
    # Conviction-outcome correlation
    conviction_outcomes = {}  # {level: {win, loss, total}}
    # Best/worst trades
    best_trade = None; worst_trade = None
    best_pnl = 0; worst_pnl = 0

    for e in entries:
        mood_list = e.get("moods", []) or []
        if mood_list:
            for m in mood_list:
                if m:
                    moods[m] = moods.get(m, 0) + 1
        else:
            m = e.get("mood", "")
            if m:
                moods[m] = moods.get(m, 0) + 1
        c = e.get("category", "")
        if c:
            categories[c] = categories.get(c, 0) + 1
        for em in e.get("emotions", []):
            emotions_count[em] = emotions_count.get(em, 0) + 1
        if e.get("followed_rules") is True:
            rules_followed += 1
        elif e.get("followed_rules") is False:
            rules_broken += 1

        # Date heatmap
        d = e.get("date", "")
        if d:
            date_counts[d] = date_counts.get(d, 0) + 1

        # Trade outcomes
        outcome = e.get("outcome", "")
        pnl = e.get("pnl_amount", 0) or 0
        rm = e.get("r_multiple", 0) or 0
        setup = e.get("setup_type", "")

        if outcome == "win":
            wins += 1; win_pnl += pnl
        elif outcome == "loss":
            losses += 1; loss_pnl += pnl
        elif outcome == "breakeven":
            breakevens += 1
        elif outcome == "avoided":
            avoided += 1

        if outcome in ("win", "loss", "breakeven"):
            total_pnl += pnl
            if rm: r_multiples.append(rm)
            if pnl > best_pnl:
                best_pnl = pnl; best_trade = {"symbol": e.get("symbol",""), "pnl": pnl, "date": d, "title": e.get("title","")}
            if pnl < worst_pnl:
                worst_pnl = pnl; worst_trade = {"symbol": e.get("symbol",""), "pnl": pnl, "date": d, "title": e.get("title","")}

            # Setup performance
            if setup:
                if setup not in setup_stats:
                    setup_stats[setup] = {"wins": 0, "losses": 0, "total_pnl": 0, "r_multiples": [], "count": 0}
                setup_stats[setup]["count"] += 1
                setup_stats[setup]["total_pnl"] += pnl
                if rm: setup_stats[setup]["r_multiples"].append(rm)
                if outcome == "win": setup_stats[setup]["wins"] += 1
                elif outcome == "loss": setup_stats[setup]["losses"] += 1

            # Emotion-outcome correlation
            for em in e.get("emotions", []):
                if em not in emotion_outcomes:
                    emotion_outcomes[em] = {"win": 0, "loss": 0, "total": 0}
                emotion_outcomes[em]["total"] += 1
                if outcome == "win": emotion_outcomes[em]["win"] += 1
                elif outcome == "loss": emotion_outcomes[em]["loss"] += 1

            # Conviction-outcome
            conv = e.get("conviction", 0)
            if conv:
                ck = str(conv)
                if ck not in conviction_outcomes:
                    conviction_outcomes[ck] = {"win": 0, "loss": 0, "total": 0, "pnl": 0}
                conviction_outcomes[ck]["total"] += 1
                conviction_outcomes[ck]["pnl"] += pnl
                if outcome == "win": conviction_outcomes[ck]["win"] += 1
                elif outcome == "loss": conviction_outcomes[ck]["loss"] += 1

        # Monthly
        if d and len(d) >= 7:
            ym = d[:7]
            if ym not in monthly:
                monthly[ym] = {"entries": 0, "wins": 0, "losses": 0, "pnl": 0}
            monthly[ym]["entries"] += 1
            if outcome == "win": monthly[ym]["wins"] += 1
            elif outcome == "loss": monthly[ym]["losses"] += 1
            if outcome in ("win", "loss", "breakeven"):
                monthly[ym]["pnl"] += pnl

    # Computed metrics
    total_trades = wins + losses + breakevens
    win_rate = round(wins / total_trades * 100, 1) if total_trades else 0
    avg_r = round(sum(r_multiples) / len(r_multiples), 2) if r_multiples else 0
    avg_win = round(win_pnl / wins, 2) if wins else 0
    avg_loss = round(loss_pnl / losses, 2) if losses else 0
    expectancy = round(avg_r, 2) if avg_r else (round((win_rate/100 * avg_win + (1-win_rate/100) * avg_loss), 2) if total_trades else 0)
    profit_factor = round(abs(win_pnl / loss_pnl), 2) if loss_pnl else (999 if win_pnl > 0 else 0)

    # Streak
    dates_sorted = sorted(set(e.get("date","") for e in entries if e.get("date","")), reverse=True)
    streak = 0
    for i, d in enumerate(dates_sorted):
        expected = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        if d == expected: streak += 1
        else: break

    # Setup stats: compute win rate and avg R for each
    for k, v in setup_stats.items():
        t = v["wins"] + v["losses"]
        v["win_rate"] = round(v["wins"] / t * 100, 1) if t else 0
        v["avg_r"] = round(sum(v["r_multiples"]) / len(v["r_multiples"]), 2) if v["r_multiples"] else 0
        del v["r_multiples"]  # don't send raw list

    stats = {
        "total": total,
        "moods": moods,
        "categories": categories,
        "emotions": emotions_count,
        "rules_followed": rules_followed,
        "rules_broken": rules_broken,
        # Trade performance
        "wins": wins, "losses": losses, "breakevens": breakevens, "avoided": avoided,
        "total_trades": total_trades, "win_rate": win_rate,
        "total_pnl": round(total_pnl, 2), "avg_win": avg_win, "avg_loss": avg_loss,
        "avg_r": avg_r, "expectancy": expectancy, "profit_factor": profit_factor,
        "r_multiples": r_multiples[-50:],  # last 50 for chart
        "best_trade": best_trade, "worst_trade": worst_trade,
        # Breakdowns
        "setup_performance": setup_stats,
        "monthly": dict(sorted(monthly.items())),
        "date_counts": date_counts,
        "emotion_outcomes": emotion_outcomes,
        "conviction_outcomes": conviction_outcomes,
        "streak": streak,
    }
    return {"entries": entries[:limit], "total": total, "stats": stats}

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

@app.put("/api/trade-journal/{entry_id}")
def update_journal_entry(entry_id: str, entry: JournalEntry) -> dict:
    with _journal_lock:
        entries = _load_journal()
        idx = next((i for i, e in enumerate(entries) if e.get("id") == entry_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail="Journal entry not found")
        rec = entry.model_dump()
        prev = entries[idx]
        # Guard against accidental empty-string overwrites from UI state drift.
        # If user did not actually provide these fields in a meaningful way,
        # preserve existing non-empty values.
        for key in ("anchor_thought", "action_plan", "one_line_summary", "observations"):
            if isinstance(rec.get(key), str) and not rec.get(key).strip() and isinstance(prev.get(key), str) and prev.get(key).strip():
                rec[key] = prev[key]
        # Preserve symbol if incoming payload leaves it blank.
        if isinstance(rec.get("symbol"), str) and not rec.get("symbol").strip() and isinstance(prev.get("symbol"), str) and prev.get("symbol").strip():
            rec["symbol"] = prev["symbol"]
        rec["id"] = entry_id
        rec["created_at"] = prev.get("created_at", datetime.now().isoformat(timespec="seconds"))
        rec["updated_at"] = datetime.now().isoformat(timespec="seconds")
        # Preserve screenshots from existing entry if not provided in update
        if not rec.get("screenshots") and prev.get("screenshots"):
            rec["screenshots"] = prev["screenshots"]
        entries[idx] = rec
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

@app.get("/api/trade-journal/export")
def export_journal():
    """Export journal entries as CSV for analysis"""
    import io
    entries = _load_journal()
    if not entries:
        raise HTTPException(status_code=404, detail="No entries to export")
    fields = ["date","symbol","category","title","one_line_summary","outcome","pnl_amount","r_multiple",
              "setup_type","entry_price","exit_price","stop_loss","position_size",
              "risk_amount","risk_pct","conviction","execution_rating","stress_level",
              "mood","moods","emotions","followed_rules","rule_violations","thesis",
              "what_went_well","what_went_wrong","lesson_learned","market_condition",
              "timeframe","observations","action_plan","anchor_thought","tags","body"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for e in sorted(entries, key=lambda x: x.get("date",""), reverse=True):
        row = dict(e)
        row["moods"] = "; ".join(row.get("moods", []))
        row["emotions"] = "; ".join(row.get("emotions", []))
        row["rule_violations"] = "; ".join(row.get("rule_violations", []))
        row["tags"] = "; ".join(row.get("tags", []))
        writer.writerow(row)
    from fastapi.responses import StreamingResponse
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=trading_journal_export.csv"}
    )


# ── Trade Watchlist 2.0 ────────────────────────────────────────────────────────
# Adds manual categorization (bucket), entry-style setup, cross-market pairing
# (RS stock ↔ ADR), return-since-add tracking, conviction, tags, and a
# market-health strip endpoint that powers the top of the Watchlist UI.
_watchlist_lock = threading.Lock()

WATCHLIST_BUCKETS: list[dict] = [
    {"slug": "rs_leaders",      "label": "RS Leaders",         "icon": "🏆", "hint": "Outperformers holding up vs market"},
    {"slug": "adr_pairs",       "label": "ADR Pairs",          "icon": "🌐", "hint": "Indian stock ↔ US ADR cross-listing"},
    {"slug": "long_term",       "label": "Long-term / SIP",    "icon": "🏛️", "hint": "Multi-year compounders"},
    {"slug": "sector_rotators", "label": "Sector Rotators",    "icon": "🔄", "hint": "Rotation candidates"},
    {"slug": "macro_hedge",     "label": "Macro / Hedge",      "icon": "🛡️", "hint": "Gold, defensives, yields"},
    {"slug": "setup_vcp",       "label": "Setup · VCP",        "icon": "🧲", "hint": "Volatility Contraction"},
    {"slug": "setup_pullback",  "label": "Setup · Pullback",   "icon": "⤵️", "hint": "Buy on orderly retrace"},
    {"slug": "setup_breakout",  "label": "Setup · Breakout",   "icon": "🚀", "hint": "Range high break + volume"},
    {"slug": "setup_range_exp", "label": "Setup · Range Exp.", "icon": "📐", "hint": "Range expansion / trend day"},
    {"slug": "setup_mean_rev",  "label": "Setup · Mean Rev.",  "icon": "↩️", "hint": "Oversold bounce"},
    {"slug": "setup_bull_flag", "label": "Setup · Bull Flag",  "icon": "🏁", "hint": "Flag / pennant"},
    {"slug": "setup_ema_pb",    "label": "Setup · EMA Pullback", "icon": "📉", "hint": "Pullback to rising EMA (5/10/20/50)"},
    {"slug": "setup_base_bo",   "label": "Setup · Base Breakout", "icon": "📦", "hint": "Flat base / cup breakout on volume"},
    {"slug": "setup_ftd",       "label": "Setup · Follow-Through", "icon": "📈", "hint": "Follow-through day after correction"},
    {"slug": "setup_earnings",  "label": "Setup · Earnings",   "icon": "💼", "hint": "Pre / post earnings swing"},
    {"slug": "setup_ipo_base",  "label": "Setup · IPO Base",   "icon": "🆕", "hint": "First base after listing"},
    {"slug": "watching",        "label": "Just Watching",      "icon": "👀", "hint": "No setup yet, monitoring"},
]

WATCHLIST_SETUPS: list[str] = [
    "VCP", "Pullback", "Breakout", "Range Expansion", "Mean Reversion",
    "Bull Flag", "EMA Pullback", "Base Breakout", "Follow-Through Day",
    "Base Building", "Earnings Swing", "IPO Base",
    "Cup & Handle", "Darvas Box", "Gap-n-Go", "Watching",
]

# Known India ↔ US ADR cross-listings (NSE symbol → US ADR, and inverse).
ADR_HINTS: dict[str, dict] = {
    "INFY":       {"adr_symbol": "INFY", "adr_market": "us"},
    "WIPRO":      {"adr_symbol": "WIT",  "adr_market": "us"},
    "HDFCBANK":   {"adr_symbol": "HDB",  "adr_market": "us"},
    "ICICIBANK":  {"adr_symbol": "IBN",  "adr_market": "us"},
    "DRREDDY":    {"adr_symbol": "RDY",  "adr_market": "us"},
    "TATAMOTORS": {"adr_symbol": "TTM",  "adr_market": "us"},
    "VEDL":       {"adr_symbol": "VEDL", "adr_market": "us"},
    "MAKEMYTRIP": {"adr_symbol": "MMYT", "adr_market": "us"},
    "WIT":  {"adr_symbol": "WIPRO",     "adr_market": "india"},
    "HDB":  {"adr_symbol": "HDFCBANK",  "adr_market": "india"},
    "IBN":  {"adr_symbol": "ICICIBANK", "adr_market": "india"},
    "RDY":  {"adr_symbol": "DRREDDY",   "adr_market": "india"},
    "TTM":  {"adr_symbol": "TATAMOTORS","adr_market": "india"},
    "MMYT": {"adr_symbol": "MAKEMYTRIP","adr_market": "india"},
}


def _migrate_watchlist_item(raw: dict) -> dict:
    """Upgrade a v1 watchlist entry to v2+ schema (idempotent)."""
    raw.setdefault("bucket",      "watching")
    raw.setdefault("market",      "india")
    raw.setdefault("setup",       raw.get("setup", ""))
    raw.setdefault("conviction",  3)
    raw.setdefault("tags",        [])
    raw.setdefault("add_price",   None)
    raw.setdefault("add_date",    (raw.get("added_at") or "")[:10] or None)
    raw.setdefault("pair_symbol", None)
    raw.setdefault("pair_market", None)
    raw.setdefault("source",      "manual")   # "manual" | "auto_rs"
    raw.setdefault("priority",    None)        # P1 / P2 / P3 (auto-computed)
    return raw


def _load_watchlist() -> list:
    if not TRADE_WATCHLIST_JSON.exists():
        return []
    try:
        raw = json.loads(TRADE_WATCHLIST_JSON.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [_migrate_watchlist_item(dict(x)) for x in raw]
        return []
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
    # ── v2 additions ──
    market: Literal["india", "us"] = "india"
    bucket: str = "watching"
    conviction: int = Field(default=3, ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    add_price: Optional[float] = None       # anchor price captured at add-time
    add_date: Optional[str] = None          # YYYY-MM-DD (auto → today)
    pair_symbol: Optional[str] = None       # cross-market pair (e.g. ADR)
    pair_market: Optional[Literal["india", "us"]] = None
    source: Literal["manual", "auto_rs"] = "manual"  # provenance flag
    priority: Optional[str] = None          # P1 / P2 / P3 (auto-computed)


class WatchlistItemUpdate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None
    alert_price: Optional[float] = None
    setup: Optional[str] = None
    bucket: Optional[str] = None
    conviction: Optional[int] = None
    tags: Optional[list[str]] = None
    add_price: Optional[float] = None
    add_date: Optional[str] = None
    pair_symbol: Optional[str] = None
    pair_market: Optional[Literal["india", "us"]] = None
    priority: Optional[str] = None


# ── Smart categorization helpers ─────────────────────────────────────────────

# Maps scan setup types → best-fit watchlist bucket slug
_SETUP_TO_BUCKET: dict[str, str] = {
    "VCP":                "setup_vcp",
    "BREAKOUT":           "setup_breakout",
    "BREAKOUT_PULLBACK":  "setup_pullback",
    "RANGE_EXPANSION":    "setup_range_exp",
    "MEAN_REVERSION":     "setup_mean_rev",
    "BULL_FLAG":          "setup_bull_flag",
    "EMA_PULLBACK":       "setup_ema_pb",
    "BASE_BREAKOUT":      "setup_base_bo",
    "FOLLOW_THROUGH":     "setup_ftd",
    "EARNINGS":           "setup_earnings",
    "IPO_BASE":           "setup_ipo_base",
    "GAP_AND_GO":         "setup_breakout",
    "CUP_HANDLE":         "setup_base_bo",
    "DARVAS":             "setup_breakout",
}


def _resolve_best_bucket(scan_setup: str | None, is_ipo: bool = False,
                          rs_score: int = 0) -> str:
    """Pick the best bucket for an auto RS-leader based on scan signal data.

    Priority order:
    1. If the stock has a scan setup → use its matching setup_* bucket
    2. If it's an IPO with no scan setup → setup_ipo_base
    3. Otherwise → rs_leaders (catch-all for strong RS without a specific pattern)
    """
    if scan_setup:
        bucket = _SETUP_TO_BUCKET.get(scan_setup.upper().replace(" ", "_"))
        if bucket:
            return bucket
    if is_ipo:
        return "setup_ipo_base"
    return "rs_leaders"


def _compute_priority(
    conviction: int = 3,
    rs_score: float | None = None,
    scan_rating: str = "",
    swing_score: float | None = None,
    in_scan: bool = False,
) -> str:
    """Compute P1 / P2 / P3 priority tier for a watchlist item.

    P1 (🔥 Actionable NOW) — high conviction + strong ranking + scan-confirmed
    P2 (👀 Watch Closely)  — decent conviction + solid fundamentals
    P3 (📋 On Radar)       — tracking, not yet ready
    """
    _rs = rs_score or 0
    _sw = swing_score or 0
    _rating_strong = scan_rating in ("A+", "A")

    # P1: conviction ≥ 4 AND (elite RS ≥ 85 OR A+/A scan rating) AND in scan
    if conviction >= 4 and (_rs >= 85 or _rating_strong) and in_scan:
        return "P1"
    # Also P1: swing ≥ 85 AND scan confirmed regardless of conviction
    if _sw >= 85 and _rating_strong and in_scan:
        return "P1"
    # P2: conviction ≥ 3 AND RS ≥ 70 (or in scan)
    if conviction >= 3 and (_rs >= 70 or in_scan):
        return "P2"
    # P3: everything else
    return "P3"


def _enrich_watchlist_priority(item: dict) -> None:
    """Dynamically recompute priority based on latest enrichment data."""
    item["priority"] = _compute_priority(
        conviction=item.get("conviction", 3),
        rs_score=item.get("rs_score") or item.get("rsScore"),
        scan_rating=item.get("scanRating", ""),
        swing_score=item.get("swing_score"),
        in_scan=item.get("inScan", False),
    )


def _enrich_watchlist_item_lite(item: dict, sig_index: dict) -> None:
    """Light-weight enrichment (CMP, day-change, return-since-add, pair, scan, priority).
    Shared between /watchlist and /watchlist/enriched."""
    sym = item.get("symbol", "")
    mkt = item.get("market") or "india"
    cmp, prev_close, last_date = _get_price_info(sym, market=mkt)
    if cmp:
        item["cmp"] = round(cmp, 2)
        item["lastPriceDate"] = last_date
    if cmp and prev_close and prev_close > 0:
        item["dayChangePct"] = round((cmp - prev_close) / prev_close * 100, 2)
    ap = item.get("add_price")
    if cmp and ap and ap > 0:
        item["returnSinceAddPct"] = round((cmp - ap) / ap * 100, 2)
        item["returnSinceAddAbs"] = round(cmp - ap, 2)
    pair_sym = item.get("pair_symbol")
    if pair_sym:
        pmkt = item.get("pair_market") or "india"
        pcmp, pprev, pdate = _get_price_info(pair_sym, market=pmkt)
        item["pair"] = {
            "symbol": pair_sym, "market": pmkt,
            "cmp": round(pcmp, 2) if pcmp else None,
            "dayChangePct": round((pcmp - pprev) / pprev * 100, 2) if pcmp and pprev else None,
            "lastPriceDate": pdate,
        }
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

    # ── Priority tier (dynamic, recalculated each fetch) ──────────────────
    _enrich_watchlist_priority(item)

    # ── Entry proximity % (how close CMP is to scan entry price) ──────────
    cmp_val = item.get("cmp")
    scan_entry = item.get("scanEntry")
    if cmp_val and scan_entry:
        try:
            se = float(scan_entry)
            if se > 0:
                dist = (cmp_val - se) / se * 100
                item["entryDistPct"] = round(dist, 2)
                # Near-entry flag (within ±2%)
                item["nearEntry"] = abs(dist) <= 2.0
        except (ValueError, TypeError):
            pass


@app.get("/api/trade-board/watchlist")
def get_watchlist() -> dict:
    from concurrent.futures import ThreadPoolExecutor
    with _watchlist_lock:
        items = _load_watchlist()
    sig_index = _load_scan_signals_index()
    # Parallel live price pre-warm
    india_syms = list({item.get("symbol", "") for item in items
                       if item.get("symbol") and (item.get("market") or "india") != "us"})
    if india_syms:
        with ThreadPoolExecutor(max_workers=min(10, len(india_syms))) as pool:
            list(pool.map(_get_live_price, india_syms))
    for item in items:
        _enrich_watchlist_item_lite(item, sig_index)
    return {
        "items": items, "total": len(items),
        "buckets": WATCHLIST_BUCKETS, "setups": WATCHLIST_SETUPS,
    }


@app.post("/api/trade-board/watchlist")
def add_watchlist_item(item: WatchlistItem) -> dict:
    with _watchlist_lock:
        items = _load_watchlist()
        sym_u = item.symbol.upper()
        # Duplicate guard — symbol + market must be unique
        if any(i.get("symbol","").upper() == sym_u
               and (i.get("market") or "india") == item.market
               for i in items):
            raise HTTPException(status_code=409, detail=f"{item.symbol} ({item.market}) already in watchlist")
        rec = item.model_dump()
        rec["symbol"] = sym_u
        rec["id"] = str(uuid.uuid4())
        rec["added_at"] = datetime.now().isoformat(timespec="seconds")
        if not rec.get("add_date"):
            rec["add_date"] = datetime.now().strftime("%Y-%m-%d")
        # Auto-capture current price as anchor if not given
        if rec.get("add_price") in (None, 0, 0.0):
            cmp, _, _ = _get_price_info(sym_u, market=rec.get("market") or "india")
            if cmp:
                rec["add_price"] = round(float(cmp), 2)
        # Auto-suggest ADR pair if user didn't set one
        if not rec.get("pair_symbol"):
            hint = ADR_HINTS.get(sym_u)
            if hint:
                rec["pair_symbol"] = hint["adr_symbol"]
                rec["pair_market"] = hint["adr_market"]
        items.append(rec)
        _save_watchlist(items)
    return {"ok": True, "item": rec}


@app.patch("/api/trade-board/watchlist/{item_id}")
def update_watchlist_item(item_id: str, patch: WatchlistItemUpdate) -> dict:
    """Edit any editable field (bucket, setup, pair, notes, conviction,
    add_price, add_date, tags, alert_price, name). Symbol/market are
    immutable — delete and re-add to change them."""
    with _watchlist_lock:
        items = _load_watchlist()
        for i, it in enumerate(items):
            if it.get("id") == item_id:
                changes = {k: v for k, v in patch.model_dump(exclude_unset=True).items()
                           if v is not None}
                items[i] = {**it, **changes}
                _save_watchlist(items)
                return {"ok": True, "item": items[i]}
    raise HTTPException(status_code=404, detail="Watchlist item not found")


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


@app.get("/api/trade-board/watchlist/categories")
def watchlist_categories() -> dict:
    """Canonical bucket + setup vocabulary + ADR pairing hints.
    The UI pulls from here so both sides stay in lock-step."""
    return {"buckets": WATCHLIST_BUCKETS, "setups": WATCHLIST_SETUPS, "adr_hints": ADR_HINTS}


@app.get("/api/trade-board/watchlist/market-health")
def watchlist_market_health() -> dict:
    """Compact market-health snapshot for the top of the Watchlist page.
    Aggregates Nifty spot + trend + phase, regime from scan bundle, and breadth
    hit-counts from the latest system summary. Every piece degrades gracefully
    if its underlying artifact is missing."""
    out: dict = {"generatedAt": datetime.now().isoformat(timespec="seconds")}
    # Nifty spot + phase
    try:
        prices = _get_fresh_nifty_benchmark(days=260)
        if prices:
            closes = prices.get("close", []) or []
            dates  = prices.get("dates", []) or []
            if closes:
                cur  = closes[-1]
                prev = closes[-2]  if len(closes) >= 2   else cur
                d20  = closes[-21] if len(closes) >= 21  else cur
                d50  = closes[-51] if len(closes) >= 51  else cur
                d252 = closes[0]
                out["nifty"] = {
                    "value":     round(cur, 2),
                    "changePct": round((cur - prev) / prev * 100, 2) if prev else 0,
                    "change20d": round((cur - d20) / d20 * 100, 2) if d20 else 0,
                    "change50d": round((cur - d50) / d50 * 100, 2) if d50 else 0,
                    "change52w": round((cur - d252) / d252 * 100, 2) if d252 else 0,
                    "asOf":      dates[-1] if dates else None,
                }
            phases = _wpe.detect_market_phases(prices) or []
            if phases:
                out["currentPhase"] = phases[-1]
                out["phaseSummary"] = _wpe._summarize_phases(phases)
    except Exception as e:
        out["phaseError"] = str(e)
    # Regime + breadth from scan artifacts
    try:
        bundle = _read_json_if_exists(OUTPUT_DIR / "scan_bundle_india_daily_full_LATEST.json") or {}
        if isinstance(bundle, dict):
            out["regime"]     = (bundle.get("meta") or {}).get("regime")
            out["scanCounts"] = bundle.get("counts")
    except Exception:
        pass
    try:
        summary = _read_json_if_exists(OUTPUT_DIR / "system_latest_summary.json") or {}
        for r in summary.get("results", []) or []:
            if r.get("market") == "india" and r.get("timeframe") == "daily":
                out["summary"] = {
                    "hits":            r.get("hits", 0),
                    "watchlistHits":   r.get("watchlistHits", 0),
                    "portfolioPicks":  r.get("portfolioPicks", 0),
                    "setupBreakdown":  (r.get("variationBreakdown") or {}).get("setup", {}),
                    "ratingBreakdown": (r.get("variationBreakdown") or {}).get("rating", {}),
                }
                break
    except Exception:
        pass
    # One-line verdict for the top strip
    phase = (out.get("currentPhase") or {}).get("type")
    _reg = out.get("regime")
    if isinstance(_reg, dict):
        _reg = _reg.get("state") or _reg.get("label") or ""
    regime = str(_reg or "").lower()
    if phase == "decline":
        verdict = "⚠ Defense mode — Nifty in decline phase"
    elif phase == "consolidation":
        verdict = "⏸ Consolidation — wait for leadership / breakouts"
    elif phase == "recovery":
        verdict = "✅ Recovery leg — lean into RS leaders"
    elif "bull" in regime:
        verdict = "✅ Bullish regime — offense mode"
    elif "bear" in regime:
        verdict = "⚠ Bearish regime — defense mode"
    else:
        verdict = "⚖ Neutral — selective, setup-dependent"
    out["verdict"] = verdict
    return out


# ── Automated RS-Leader Detection ─────────────────────────────────────────────
# Scans every Indian cache file, computes IBD-style Relative Strength vs Nifty
# 50 for each stock, ranks them, and surfaces the top N. The scan is cached for
# 30 minutes because it's a pure read over the CSV cache (no network) and
# stable within a trading session.

_rs_scan_cache: dict = {"ts": 0, "data": None}
_rs_scan_lock = threading.Lock()
_RS_SCAN_TTL = 30 * 60  # seconds


def _list_india_cache_symbols() -> list[str]:
    """Return every NSE symbol present in the OHLCV cache (base names, no .NS)."""
    out: list[str] = []
    try:
        for p in CACHE_DIR.glob("*.NS.csv"):
            out.append(p.stem.replace(".NS", ""))
    except Exception:
        pass
    return sorted(set(out))


def _compute_rs_universe(
    top_n: int = 35,
    min_price: float = 50.0,
    min_bars: int = 150,
    max_symbols: int = 0,       # 0 = all
    ipo_only: bool = False,     # return only IPO stocks (<126 bars)
    sort_by: str = "swing",     # "swing" | "rs" | "adr" | "volume"
    min_adr: float = 0.0,       # filter: minimum ADR% (e.g. 2.0 for ≥2%)
    min_avg_vol: int = 0,       # filter: minimum 20d avg volume (e.g. 100000)
) -> dict:
    """
    Rank every Indian stock in the cache by IBD-style RS vs Nifty 50, enriched
    with ADR%, volume metrics, trend data, sector/industry tags, and a composite
    swing score designed to surface explosive-move candidates.

    Returns a dict with {top, total_scanned, computed, nifty_asof, generatedAt}.
    Thread-safe, memoized for _RS_SCAN_TTL seconds.
    """
    now = time.time()

    # Fetch freshest-possible Nifty benchmark (shared helper — same source as
    # every other page that shows "Nifty asof"). Triggers a sync index refresh
    # if the OHLCV cache is stale; falls back to yfinance side-cache if needed.
    market_prices = _get_fresh_nifty_benchmark(days=260)
    live_nifty_asof = (market_prices or {}).get("dates", [None])[-1] if market_prices else None

    _cache_key = (top_n, min_price, min_bars, max_symbols, ipo_only, sort_by, min_adr, min_avg_vol)
    with _rs_scan_lock:
        cached = _rs_scan_cache.get("data")
        if cached and (now - _rs_scan_cache.get("ts", 0)) < _RS_SCAN_TTL \
                and cached.get("_params") == _cache_key:
            # Bypass the TTL if the live ^NSEI CSV has a newer last-date than
            # what the cached scan was computed against.
            cached_asof = cached.get("nifty_asof")
            if (not live_nifty_asof) or (not cached_asof) or live_nifty_asof <= cached_asof:
                return cached
            print(f"🔁 RS-universe cache asof={cached_asof} < live ^NSEI {live_nifty_asof} "
                  f"— invalidating and recomputing", flush=True)
            _rs_scan_cache["ts"] = 0  # force recompute below

    if not market_prices or not market_prices.get("close"):
        raise HTTPException(status_code=503, detail="Could not fetch Nifty50 data for RS benchmark")

    # ── Sector/industry taxonomy (loaded once, cached 30 min)
    taxonomy = {}
    try:
        taxonomy = _load_taxonomy_cached() or {}
    except Exception:
        pass

    # 2. Universe = all cached NSE symbols (excluding Nifty itself)
    universe = [s for s in _list_india_cache_symbols() if s.upper() != "^NSEI"]
    if max_symbols and len(universe) > max_symbols:
        universe = universe[:max_symbols]

    from concurrent.futures import ThreadPoolExecutor

    def _ema(src: list[float], period: int) -> float:
        """Exponential moving average — standard formula."""
        k = 2 / (period + 1)
        e = src[0]
        for v in src[1:]:
            e = v * k + e * (1 - k)
        return e

    def _score_one(sym: str) -> Optional[dict]:
        rows = _read_ohlcv(sym, days=260, market="india")
        if not rows:
            return None

        n_bars = len(rows)
        last_close = rows[-1]["close"]
        if last_close < min_price:
            return None

        # ── IPO detection: <126 trading days ≈ listed within ~6 months
        is_ipo = n_bars < 126

        # For non-IPO: respect min_bars; for IPO: need at least 15 bars
        if is_ipo:
            if n_bars < 15:
                return None
        else:
            if n_bars < min_bars:
                return None

        closes = [r["close"] for r in rows]
        highs  = [r["high"]  for r in rows]
        lows   = [r["low"]   for r in rows]
        vols   = [r.get("volume", 0) or 0 for r in rows]
        dates  = [r["date"]  for r in rows]

        stock_prices = {"close": closes, "dates": dates}

        # ── RS Score — IPO gets shorter periods (1M/2M/3M), normal gets standard
        try:
            if is_ipo:
                rs = _wpe.compute_rs_score(
                    stock_prices, market_prices,
                    periods=[21, 42, 63],
                    weights=[0.50, 0.30, 0.20],
                )
            else:
                rs = _wpe.compute_rs_score(stock_prices, market_prices)
        except Exception:
            return None

        score = rs.get("rs_score")
        if score is None:
            return None

        # ── ADR%: Average Daily Range % over last 20 sessions
        adr_period = min(20, n_bars)
        recent = rows[-adr_period:]
        adr_abs = sum(r["high"] - r["low"] for r in recent) / adr_period
        adr_pct = round(adr_abs / last_close * 100, 2) if last_close else 0

        # ── Volume metrics
        vol_period = min(20, n_bars)
        avg_vol_20 = sum(vols[-vol_period:]) / vol_period if vol_period else 0
        last_vol   = vols[-1] if vols else 0
        vol_ratio  = round(last_vol / avg_vol_20, 2) if avg_vol_20 else 1.0
        # 5-day avg volume (recent footprint)
        avg_vol_5 = sum(vols[-5:]) / min(5, n_bars) if n_bars >= 5 else avg_vol_20
        vol_surge_5d = round(avg_vol_5 / avg_vol_20, 2) if avg_vol_20 else 1.0

        # ── Liquidity filter: skip illiquid stocks early
        if min_avg_vol and avg_vol_20 < min_avg_vol:
            return None
        # ── ADR filter: skip low-volatility stocks
        if min_adr and adr_pct < min_adr:
            return None

        # ── Trend: EMA10, EMA21, SMA50
        ema10  = round(_ema(closes, 10), 2)  if n_bars >= 10  else last_close
        ema21  = round(_ema(closes, 21), 2)  if n_bars >= 21  else last_close
        sma50  = round(sum(closes[-50:]) / 50, 2) if n_bars >= 50  else 0

        above_ema21 = last_close >= ema21
        above_sma50 = last_close >= sma50 if sma50 else False
        ema10_gap_pct = round((last_close - ema10) / ema10 * 100, 1) if ema10 else 0
        ema21_gap_pct = round((last_close - ema21) / ema21 * 100, 1) if ema21 else 0

        # ── 52-week high/low proximity
        lookback = rows[-252:] if n_bars >= 252 else rows
        hi52  = max(r["high"] for r in lookback)
        lo52  = min(r["low"]  for r in lookback)
        pct_from_hi  = round((last_close - hi52) / hi52 * 100, 2) if hi52 else 0
        pct_from_lo  = round((last_close - lo52) / lo52 * 100, 2) if lo52 else 0

        # ── IPO-specific: % gain from listing price (first close)
        listing_gain_pct = round((last_close - closes[0]) / closes[0] * 100, 1) if is_ipo and closes[0] else None

        # ── Sector / industry tag from taxonomy
        tax_entry = taxonomy.get(sym)
        sector         = tax_entry[0] if tax_entry else "Other"
        industry       = tax_entry[1] if tax_entry else "Other"
        basic_industry = tax_entry[2] if tax_entry and len(tax_entry) > 2 else industry

        # ── SWING SCORE (0-100)
        # Designed to surface explosive-move candidates for swing trading:
        #   RS strength  (40pts): core momentum vs market
        #   ADR bonus    (20pts): higher ADR → bigger moves per day
        #   Vol surge    (20pts): 5d avg vol vs 20d avg vol — accumulation signal
        #   Near 52w hi  (20pts): price discovering highs — momentum confirmation
        rs_pts   = min(score, 99) / 99 * 40           # 0-40
        adr_pts  = min(adr_pct / 4.0, 1.0) * 20       # 2%→10, 4%+→20
        vs_pts   = min((vol_surge_5d - 1.0) / 2.0, 1.0) * 20 if vol_surge_5d > 1 else 0  # 1.5x→5, 3x+→20
        hi_pts   = max(0, (1 - abs(pct_from_hi) / 20.0)) * 20  # within 5%→15-20
        swing_score = round(rs_pts + adr_pts + vs_pts + hi_pts, 1)

        # ── IPO bonus: freshly-listed strong RS gets extra weight (recency premium)
        if is_ipo:
            swing_score = round(min(swing_score * 1.15, 100), 1)

        return {
            "symbol":           sym,
            "market":           "india",
            "is_ipo":           is_ipo,
            "bars":             n_bars,
            "lastDate":         rows[-1]["date"],
            # Sector / industry
            "sector":           sector,
            "industry":         industry,
            "basicIndustry":    basic_industry,
            # RS
            "rs_score":         score,
            "rs_label":         rs.get("rs_label"),
            "rs_color":         rs.get("rs_color"),
            "excess_pct":       rs.get("weighted_excess_pct"),
            "period_returns":   rs.get("period_returns", {}),
            # Price
            "cmp":              round(last_close, 2),
            "pctFrom52wHigh":   pct_from_hi,
            "pctFrom52wLow":    pct_from_lo,
            "listingGainPct":   listing_gain_pct,
            # ADR
            "adrPct":           adr_pct,
            # Volume / liquidity
            "avgVol20":         round(avg_vol_20),
            "volRatio":         vol_ratio,
            "volSurge5d":       vol_surge_5d,
            # Trend
            "ema10":            ema10,
            "ema21":            ema21,
            "ema10GapPct":      ema10_gap_pct,
            "ema21GapPct":      ema21_gap_pct,
            "aboveEma21":       above_ema21,
            "aboveSma50":       above_sma50,
            # Composite
            "swingScore":       swing_score,
        }

    scored: list[dict] = []
    # Use the bulk-read initializer so pool workers don't each spawn per-symbol
    # refresh threads (5000+ symbols × stale → thread-storm freeze).
    with ThreadPoolExecutor(max_workers=12, initializer=_ig_worker_init) as pool:
        for res in pool.map(_score_one, universe):
            if res is not None:
                scored.append(res)

    # ── Freshness probe ──────────────────────────────────────────────────
    # The bulk-read flag above prevents _read_ohlcv from spawning per-symbol
    # refresh threads (thread-storm), but that means CMP in the RS leaders
    # table reflects whatever's on disk — which is yesterday's close if the
    # OHLCV refresher hasn't run since market close. Delegate one consolidated
    # refresh to the OHLCV cache refresher when we detect staleness. When it
    # finishes we invalidate the RS scan cache so the next call recomputes.
    try:
        stale_count = 0
        sample = scored[:150]
        for row in sample:
            sym = row["symbol"]
            csv_path = CACHE_DIR / f"{sym}.NS.csv"
            if not csv_path.exists():
                csv_path = CACHE_DIR / f"{sym}.csv"
            if _is_price_stale(row.get("lastDate", ""), csv_path):
                stale_count += 1
        if sample and stale_count >= max(5, len(sample) // 10):
            if not _cache_refresher.is_running:
                print(f"🔄 RS-universe: {stale_count}/{len(sample)} sampled "
                      f"CSVs are stale — kicking OHLCV cache refresh", flush=True)
                _cache_refresher.start(indian_only=True, workers=4)
    except Exception as _e:
        print(f"⚠ RS-universe freshness probe error: {_e}", flush=True)

    # ── Optional IPO-only filter
    if ipo_only:
        scored = [s for s in scored if s.get("is_ipo")]

    # ── Sort by chosen strategy
    _sort_keys = {
        "swing":  lambda x: (x.get("swingScore") or 0, x.get("rs_score") or 0),
        "rs":     lambda x: (x.get("rs_score") or 0, x.get("excess_pct") or 0),
        "adr":    lambda x: (x.get("adrPct") or 0, x.get("rs_score") or 0),
        "volume": lambda x: (x.get("volSurge5d") or 0, x.get("rs_score") or 0),
    }
    scored.sort(key=_sort_keys.get(sort_by, _sort_keys["swing"]), reverse=True)
    top = scored[:top_n]
    # Add rank
    for i, s in enumerate(top, start=1):
        s["rank"] = i

    data = {
        "generatedAt":   datetime.now().isoformat(timespec="seconds"),
        "top":           top,
        "top_n":         top_n,
        "total_scanned": len(universe),
        "total_computed": len(scored),
        "min_price":     min_price,
        "min_bars":      min_bars,
        "sort_by":       sort_by,
        "ipo_only":      ipo_only,
        "nifty_asof":    (market_prices.get("dates") or [None])[-1],
        "_params":       _cache_key,
    }
    with _rs_scan_lock:
        _rs_scan_cache["data"] = data
        _rs_scan_cache["ts"]   = now
    return data


@app.get("/api/trade-board/watchlist/rs-leaders/preview")
def rs_leaders_preview(
    top: int = 35,
    min_price: float = 50.0,
    min_bars: int = 150,
    refresh: bool = False,
    ipo_only: bool = False,
    sort_by: str = "swing",     # swing | rs | adr | volume
    min_adr: float = 0.0,       # minimum ADR% filter (e.g. 2.0)
    min_avg_vol: int = 0,       # minimum 20d avg volume filter
) -> dict:
    """
    Rank every Indian stock by IBD-style RS + swing composite score vs Nifty 50.

    Each result includes: rs_score, swingScore, adrPct, avgVol20, volSurge5d,
    sector, industry, EMA trend data, and 52-week proximity.

    sort_by options:
      swing  – composite score (RS 40% + ADR 20% + vol-surge 20% + 52wHigh 20%) [default]
      rs     – pure IBD-style RS score (3M/6M/9M/12M excess vs Nifty)
      adr    – highest ADR% first (most volatile / explosive)
      volume – strongest 5d vs 20d volume surge (accumulation signal)

    ipo_only=true  → only stocks with <126 bars; scored with short 1M/2M/3M RS periods.
    min_adr=2.0    → filter out stocks with ADR% < 2% (low-volatility names).
    min_avg_vol=100000 → filter out illiquid micro-caps.
    """
    if top <= 0 or top > 500:
        raise HTTPException(status_code=400, detail="top must be between 1 and 500")
    if refresh:
        with _rs_scan_lock:
            _rs_scan_cache["ts"] = 0
    return _compute_rs_universe(
        top_n=top, min_price=min_price, min_bars=min_bars,
        ipo_only=ipo_only, sort_by=sort_by, min_adr=min_adr, min_avg_vol=min_avg_vol,
    )


class RsLeaderAutoAddRequest(BaseModel):
    top:       int = Field(default=35, ge=1, le=500)
    min_price: float = 50.0
    min_bars:  int = 150
    refresh:   bool = False
    replace_existing_auto: bool = True  # wipe prior auto_rs items first
    ipo_only:  bool = False
    sort_by:   str = "swing"     # swing | rs | adr | volume
    min_adr:   float = 0.0
    min_avg_vol: int = 0


@app.post("/api/trade-board/watchlist/rs-leaders/auto-add")
def rs_leaders_auto_add(req: Optional[RsLeaderAutoAddRequest] = None) -> dict:
    """
    Compute the top-N RS leaders (vs Nifty 50) and insert them into the
    watchlist with bucket="rs_leaders" and source="auto_rs".

    • Manual entries (source="manual") are NEVER touched.
    • By default any previously-inserted auto_rs entries are wiped first, so
      calling this endpoint again gives you a fresh top-N snapshot.
    • If a symbol already exists as a manual entry, we skip it (no duplicate,
      no overwrite of your notes/conviction/etc).
    • Anchor price defaults to the current CMP; ADR pair auto-suggested if
      known (INFY, WIPRO, HDFCBANK, …).
    """
    if req is None:
        req = RsLeaderAutoAddRequest()
    if req.refresh:
        with _rs_scan_lock:
            _rs_scan_cache["ts"] = 0

    ranking = _compute_rs_universe(
        top_n=req.top, min_price=req.min_price, min_bars=req.min_bars,
        ipo_only=req.ipo_only, sort_by=req.sort_by,
        min_adr=req.min_adr, min_avg_vol=req.min_avg_vol,
    )
    leaders = ranking["top"]

    added: list[dict] = []
    skipped_manual: list[str] = []
    removed_auto:  list[str] = []
    today = datetime.now().strftime("%Y-%m-%d")
    # Load scan signals for smart bucket assignment
    sig_index = _load_scan_signals_index()

    with _watchlist_lock:
        items = _load_watchlist()
        # 1. Remove stale auto_rs entries first
        if req.replace_existing_auto:
            kept = []
            for it in items:
                if it.get("source") == "auto_rs":
                    removed_auto.append(it.get("symbol", "?"))
                else:
                    kept.append(it)
            items = kept
        # 2. Insert fresh leaders, skipping any symbol already tracked manually
        existing_syms = {(it.get("symbol") or "").upper(): it for it in items}
        for row in leaders:
            sym_u = row["symbol"].upper()
            # Look up scan signal for this symbol
            sig = (sig_index.get(sym_u) or sig_index.get(sym_u + ".NS")
                   or sig_index.get(sym_u.replace(".NS", "")))
            scan_setup = (sig.get("setup", "") if sig else "")
            scan_rating = (sig.get("rating", "") if sig else "")
            in_scan = bool(sig)

            # Smart bucket: prefer setup_* bucket from scan signal, else rs_leaders
            best_bucket = _resolve_best_bucket(
                scan_setup, is_ipo=row.get("is_ipo", False),
                rs_score=row.get("rs_score", 0),
            )
            # Derive friendly setup name from scan
            best_setup = scan_setup.replace("_", " ").title() if scan_setup else ""
            # Compute conviction + priority
            _conviction = max(3, min(5, int((row["rs_score"] or 50) / 20)))
            _priority = _compute_priority(
                conviction=_conviction, rs_score=row.get("rs_score"),
                scan_rating=scan_rating,
                swing_score=row.get("swingScore"), in_scan=in_scan,
            )

            if sym_u in existing_syms:
                existing = existing_syms[sym_u]
                if existing.get("source") == "manual":
                    skipped_manual.append(sym_u)
                    continue
                # It's an auto entry we kept — refresh rank, bucket, priority
                existing["conviction"] = _conviction
                existing["priority"] = _priority
                existing["bucket"] = best_bucket
                existing["setup"] = best_setup or existing.get("setup", "")
                _tags = {"rs_leader", f"rs{row['rs_score']}", f"rank{row['rank']}"}
                if row.get("is_ipo"):
                    _tags.add("ipo")
                if row.get("sector") and row["sector"] != "Other":
                    _tags.add(row["sector"].lower().replace(" ", "_"))
                if _priority == "P1":
                    _tags.add("p1")
                existing["tags"] = list({*existing.get("tags", []), *_tags})
                existing["notes"] = (
                    f"Auto RS-Leader rank #{row['rank']}  ·  RS {row['rs_score']} {row.get('rs_label','')}"
                    f"  ·  Swing {row.get('swingScore', '')}  ·  ADR {row.get('adrPct', '')}%"
                    f"  ·  {row.get('sector', '')}"
                )
                added.append(existing)
                continue
            # Fresh insert
            hint = ADR_HINTS.get(sym_u) or {}
            _tags = ["rs_leader", f"rs{row['rs_score']}", f"rank{row['rank']}"]
            if row.get("is_ipo"):
                _tags.append("ipo")
            if row.get("sector") and row["sector"] != "Other":
                _tags.append(row["sector"].lower().replace(" ", "_"))
            if _priority == "P1":
                _tags.append("p1")
            rec = {
                "id":          str(uuid.uuid4()),
                "symbol":      sym_u,
                "market":      "india",
                "name":        "",
                "bucket":      best_bucket,
                "setup":       best_setup,
                "conviction":  _conviction,
                "tags":        _tags,
                "add_price":   row.get("cmp"),
                "add_date":    today,
                "added_at":    datetime.now().isoformat(timespec="seconds"),
                "alert_price": float(sig["entry"]) if sig and sig.get("entry") else None,
                "pair_symbol": hint.get("adr_symbol"),
                "pair_market": hint.get("adr_market"),
                "notes":       (
                    f"Auto RS-Leader rank #{row['rank']}  ·  RS {row['rs_score']} {row.get('rs_label','')}"
                    f"  ·  Swing {row.get('swingScore', '')}  ·  ADR {row.get('adrPct', '')}%"
                    f"  ·  {row.get('sector', '')}"
                ),
                "source":      "auto_rs",
                "priority":    _priority,
                # extra diagnostic fields (preserved in JSON)
                "rs_score":    row["rs_score"],
                "rs_rank":     row["rank"],
                "rs_excess_pct": row.get("excess_pct"),
                "swing_score":   row.get("swingScore"),
                "adr_pct":       row.get("adrPct"),
                "sector":        row.get("sector"),
                "industry":      row.get("industry"),
                "is_ipo":        row.get("is_ipo", False),
            }
            items.append(rec)
            added.append(rec)
        _save_watchlist(items)

    return {
        "ok":              True,
        "top":             req.top,
        "added_count":     len(added),
        "removed_auto":    removed_auto,
        "skipped_manual":  skipped_manual,
        "leaders":         added,
        "generatedAt":     ranking["generatedAt"],
        "nifty_asof":      ranking.get("nifty_asof"),
        "total_scanned":   ranking["total_scanned"],
        "total_computed":  ranking["total_computed"],
    }


@app.delete("/api/trade-board/watchlist/rs-leaders/auto")
def rs_leaders_remove_auto() -> dict:
    """Remove every auto-generated RS-Leader entry (keeps manual entries)."""
    with _watchlist_lock:
        items = _load_watchlist()
        before = len(items)
        kept   = [it for it in items if it.get("source") != "auto_rs"]
        removed = [it.get("symbol") for it in items if it.get("source") == "auto_rs"]
        _save_watchlist(kept)
    return {"ok": True, "removed_count": before - len(kept), "removed": removed}


# ── Market Overview ────────────────────────────────────────────────────────────

def _load_scan_signals_index(market: str = "india", timeframe: str = "daily") -> dict[str, dict]:
    """Load latest scan signals into a symbol → record dict for quick lookup.
    Also merges weekly signals when loading daily, tagging with timeframe_alignment."""
    index: dict[str, dict] = {}

    # Load primary timeframe
    suffix = f"{market}_{timeframe}_full"
    for name in [f"open_trades_{suffix}_LATEST.json", f"vcp_hits_{suffix}_LATEST.json"]:
        p = OUTPUT_DIR / name
        if not p.exists():
            continue
        try:
            signals = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(signals, list) and signals:
                for s in signals:
                    sym = s.get("symbol", "")
                    if sym:
                        s["_timeframe"] = timeframe
                        index[sym] = s
        except Exception:
            pass

    # If loading daily, also check weekly signals for multi-timeframe alignment
    if timeframe == "daily":
        weekly_suffix = f"{market}_weekly_full"
        weekly_syms: set[str] = set()
        for name in [f"open_trades_{weekly_suffix}_LATEST.json", f"vcp_hits_{weekly_suffix}_LATEST.json"]:
            p = OUTPUT_DIR / name
            if not p.exists():
                continue
            try:
                signals = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(signals, list):
                    for s in signals:
                        sym = s.get("symbol", "")
                        if sym:
                            weekly_syms.add(sym)
            except Exception:
                pass

        # Tag daily entries that also have weekly confirmation
        for sym in index:
            if sym in weekly_syms:
                index[sym]["timeframe_alignment"] = "BOTH_ALIGNED"
            else:
                index[sym]["timeframe_alignment"] = "DAILY_ONLY"

    if not index:
        # Fallback to original behavior
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

    return index


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
        trail_state = _apply_trailing_stop_automation(board_data)
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
        "trailing": trail_state,
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
                "isStale": _is_price_stale(
                    last_date,
                    CACHE_DIR / f"{sym.upper().replace('.NS','').replace('.BO','')}.NS.csv",
                ) if last_date else True,
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
    # Custom rules replace-all (optional bulk update)
    custom_rules: Optional[list[dict]] = None


class CustomAlertRulePayload(BaseModel):
    """Schema for creating/updating one custom alert rule.

    All fields optional on PATCH; on POST `timeframe`, `metric`,
    `operator`, `threshold` are required (validated at handler).
    """
    id: Optional[str] = None
    name: Optional[str] = None
    enabled: Optional[bool] = None
    symbol: Optional[str] = None                 # "" or "*" = watchlist-wide
    timeframe: Optional[str] = None              # 5m/15m/30m/1h/1d/1wk/1mo
    metric: Optional[str] = None                 # price|volume|volume_ratio|price_pct_change
    operator: Optional[str] = None               # >|>=|<|<=|==|crosses_above|crosses_below
    threshold: Optional[float] = None
    reference: Optional[str] = None              # absolute|avg|prev_close|prev_high|prev_low|highest|lowest
    reference_bars: Optional[int] = None
    cooldown_minutes: Optional[int] = None
    channels: Optional[list[str]] = None         # subset of ["telegram","email"]


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


# ── Custom per-timeframe alert rules CRUD ──────────────────────────────────

_VALID_TIMEFRAMES = {"5m", "15m", "30m", "60m", "1h", "1d", "1wk", "1mo"}
_VALID_METRICS = {"price", "volume", "volume_ratio", "price_pct_change"}
_VALID_OPERATORS = {">", ">=", "<", "<=", "==", "crosses_above", "crosses_below"}
_VALID_REFERENCES = {"absolute", "avg", "prev_close", "prev_high", "prev_low",
                      "highest", "lowest"}
_VALID_CHANNELS = {"telegram", "email"}


def _validate_rule(rule: dict, partial: bool = False) -> None:
    """Raise HTTPException on invalid rule payload."""
    from fastapi import HTTPException
    required = ("timeframe", "metric", "operator", "threshold")
    if not partial:
        for k in required:
            if rule.get(k) in (None, ""):
                raise HTTPException(400, f"Field '{k}' is required")
    if "timeframe" in rule and rule["timeframe"] and rule["timeframe"] not in _VALID_TIMEFRAMES:
        raise HTTPException(400, f"timeframe must be one of {sorted(_VALID_TIMEFRAMES)}")
    if "metric" in rule and rule["metric"] and rule["metric"] not in _VALID_METRICS:
        raise HTTPException(400, f"metric must be one of {sorted(_VALID_METRICS)}")
    if "operator" in rule and rule["operator"] and rule["operator"] not in _VALID_OPERATORS:
        raise HTTPException(400, f"operator must be one of {sorted(_VALID_OPERATORS)}")
    if "reference" in rule and rule["reference"] and rule["reference"] not in _VALID_REFERENCES:
        raise HTTPException(400, f"reference must be one of {sorted(_VALID_REFERENCES)}")
    if "channels" in rule and rule["channels"]:
        bad = [c for c in rule["channels"] if c not in _VALID_CHANNELS]
        if bad:
            raise HTTPException(400, f"unknown channels: {bad}")


@app.get("/api/breakout-alerts/custom-rules")
def list_custom_alert_rules() -> dict:
    """Return every persisted custom alert rule."""
    config = _breakout_scanner.state.load_config()
    return {"rules": list(config.custom_rules or []),
            "count": len(config.custom_rules or []),
            "supported": {
                "timeframes": sorted(_VALID_TIMEFRAMES),
                "metrics": sorted(_VALID_METRICS),
                "operators": sorted(_VALID_OPERATORS),
                "references": sorted(_VALID_REFERENCES),
                "channels": sorted(_VALID_CHANNELS),
            }}


@app.post("/api/breakout-alerts/custom-rules")
def create_custom_alert_rule(payload: CustomAlertRulePayload) -> dict:
    """Create a new custom alert rule. Returns the stored rule with its id."""
    import uuid
    from dataclasses import asdict as _asdict
    rule = {k: v for k, v in payload.model_dump(exclude_unset=True).items()
            if v is not None}
    _validate_rule(rule, partial=False)
    rule.setdefault("id", uuid.uuid4().hex[:12])
    rule.setdefault("name", f"{rule.get('metric','')}-{rule.get('timeframe','')}")
    rule.setdefault("enabled", True)
    rule.setdefault("symbol", "")
    rule.setdefault("reference", "absolute")
    rule.setdefault("reference_bars", 20)
    rule.setdefault("cooldown_minutes", 60)
    rule.setdefault("channels", ["telegram"])

    config = _breakout_scanner.state.load_config()
    rules = list(config.custom_rules or [])
    rules.append(rule)
    data = _asdict(config)
    data["custom_rules"] = rules
    _breakout_scanner.state.save_config(AlertConfig(**data))
    return {"ok": True, "rule": rule}


@app.patch("/api/breakout-alerts/custom-rules/{rule_id}")
def update_custom_alert_rule(rule_id: str, payload: CustomAlertRulePayload) -> dict:
    """Partially update a rule by id."""
    from fastapi import HTTPException
    from dataclasses import asdict as _asdict
    patch = {k: v for k, v in payload.model_dump(exclude_unset=True).items()
             if v is not None and k != "id"}
    _validate_rule(patch, partial=True)

    config = _breakout_scanner.state.load_config()
    rules = list(config.custom_rules or [])
    for i, r in enumerate(rules):
        if r.get("id") == rule_id:
            rules[i] = {**r, **patch}
            data = _asdict(config)
            data["custom_rules"] = rules
            _breakout_scanner.state.save_config(AlertConfig(**data))
            return {"ok": True, "rule": rules[i]}
    raise HTTPException(404, f"rule {rule_id} not found")


@app.delete("/api/breakout-alerts/custom-rules/{rule_id}")
def delete_custom_alert_rule(rule_id: str) -> dict:
    """Delete a rule by id."""
    from fastapi import HTTPException
    from dataclasses import asdict as _asdict
    config = _breakout_scanner.state.load_config()
    rules = list(config.custom_rules or [])
    new_rules = [r for r in rules if r.get("id") != rule_id]
    if len(new_rules) == len(rules):
        raise HTTPException(404, f"rule {rule_id} not found")
    data = _asdict(config)
    data["custom_rules"] = new_rules
    _breakout_scanner.state.save_config(AlertConfig(**data))
    return {"ok": True, "deleted": rule_id, "remaining": len(new_rules)}


@app.post("/api/breakout-alerts/custom-rules/evaluate-now")
def evaluate_custom_rules_now(symbols: list[str] | None = None) -> dict:
    """Dry-run every enabled rule (ignores cooldown). Returns list of fired alerts."""
    if _breakout_scanner._read_ohlcv is None:
        _breakout_scanner._read_ohlcv = _read_ohlcv
    fired = _breakout_scanner.evaluate_custom_rules_now(symbols=symbols)
    return {"fired": fired, "count": len(fired),
            "evaluatedAt": datetime.now().isoformat(timespec="seconds")}


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


# ── Watchlist Entry Proximity Alerts ──────────────────────────────────────────

_entry_alerted_keys: set = set()


@app.get("/api/alerts/entry-proximity/check")
def entry_proximity_check(threshold: float = 2.0) -> dict:
    """
    Check all watchlist items for entry price proximity.
    Returns items where CMP is within `threshold`% of their scan entry price.
    Useful for entry timing on setup/breakout triggers.
    """
    with _watchlist_lock:
        items = _load_watchlist()
    sig_index = _load_scan_signals_index()
    for item in items:
        _enrich_watchlist_item_lite(item, sig_index)

    alerts = []
    for item in items:
        cmp = item.get("cmp")
        scan_entry_raw = item.get("scanEntry")
        if not cmp or not scan_entry_raw:
            continue
        try:
            se = float(scan_entry_raw)
        except (ValueError, TypeError):
            continue
        if se <= 0:
            continue
        dist = (cmp - se) / se * 100
        if abs(dist) > threshold:
            continue
        scan_sl = float(item.get("scanSl", 0) or 0)
        risk = round(se - scan_sl, 2) if scan_sl > 0 else 0
        rr = round((se * 1.15 - se) / (se - scan_sl), 1) if scan_sl > 0 and se > scan_sl else 0
        tier = "AT_ENTRY" if abs(dist) <= 0.5 else ("NEAR_ENTRY" if dist <= 0 else "ABOVE_ENTRY")
        alerts.append({
            "symbol": item.get("symbol", ""),
            "name": item.get("name", ""),
            "tier": tier,
            "cmp": cmp,
            "scanEntry": se,
            "scanSl": scan_sl,
            "distPct": round(dist, 2),
            "riskPerShare": risk,
            "rr": rr,
            "setup": item.get("scanSetup") or item.get("setup", ""),
            "rating": item.get("scanRating", ""),
            "bucket": item.get("bucket", ""),
            "priority": item.get("priority", "P3"),
            "conviction": item.get("conviction", 3),
            "sector": item.get("sector", ""),
            "rs_score": item.get("rs_score"),
            "swing_score": item.get("swing_score"),
            "dayChangePct": item.get("dayChangePct"),
            "id": item.get("id", ""),
        })

    # Sort: AT_ENTRY first, then NEAR_ENTRY, then ABOVE_ENTRY; within tier by priority
    priority_order = {"P1": 0, "P2": 1, "P3": 2}
    tier_order = {"AT_ENTRY": 0, "NEAR_ENTRY": 1, "ABOVE_ENTRY": 2}
    alerts.sort(key=lambda a: (tier_order.get(a["tier"], 9),
                                priority_order.get(a["priority"], 9),
                                abs(a["distPct"])))
    return {
        "alerts": alerts,
        "count": len(alerts),
        "threshold": threshold,
        "totalWatchlist": len(items),
        "checkedAt": datetime.now().isoformat(timespec="seconds"),
    }


@app.post("/api/alerts/entry-proximity/scan-send")
def entry_proximity_scan_and_alert(threshold: float = 2.0) -> dict:
    """
    Scan watchlist for entry proximity AND send Telegram alerts for new ones.
    Deduplicates: won't re-alert same symbol+tier+date combo.
    """
    global _entry_alerted_keys
    check_result = entry_proximity_check(threshold)
    alerts = check_result.get("alerts", [])
    config = _breakout_scanner.state.load_config()
    today = datetime.now().strftime("%Y-%m-%d")

    new_alerts = []
    for a in alerts:
        key = f"{a['symbol']}:{today}:{a['tier']}"
        if key not in _entry_alerted_keys:
            _entry_alerted_keys.add(key)
            new_alerts.append(a)

    sent_count = 0
    if config.telegram_enabled and new_alerts:
        for a in new_alerts:
            emoji = "🎯" if a["tier"] == "AT_ENTRY" else "📍" if a["tier"] == "NEAR_ENTRY" else "📊"
            tier_label = a["tier"].replace("_", " ")
            text = (
                f"{emoji} *ENTRY ALERT — {a['symbol']}*\n"
                f"Tier: {tier_label} | Priority: {a['priority']}\n"
                f"CMP: ₹{a['cmp']:,.2f} | Entry: ₹{a['scanEntry']:,.2f}\n"
                f"Distance: {a['distPct']:+.1f}%\n"
                f"Setup: {a['setup']} | Rating: {a['rating']}\n"
                f"SL: ₹{a['scanSl']:,.2f} | Risk/sh: ₹{a['riskPerShare']}"
                + (f" | R:R {a['rr']}x" if a['rr'] else "")
                + (f"\nSector: {a['sector']}" if a['sector'] else "")
            )
            ok = send_telegram_text(text, config)
            if ok:
                sent_count += 1
                print(f"  🎯 Entry alert sent: {a['symbol']} {a['tier']} ₹{a['cmp']}", flush=True)

    return {
        "alerts": alerts,
        "newAlerts": len(new_alerts),
        "telegramSent": sent_count,
        "checkedAt": datetime.now().isoformat(timespec="seconds"),
    }


# ── Trading wisdom / daily reminders ───────────────────────────────────────
# These endpoints power the always-on nudge layer in the UI: quote-of-the-day
# panel, page-contextual reminders, psychology pings on open positions, etc.
# All data is served from trading_wisdom.QUOTES (pure-data, see lib module).
#
# NOTE: every endpoint returns JSONResponse with Cache-Control: no-store.
# Without that header browsers (especially Safari) were caching responses
# aggressively, so navigating between pages or hitting the rotate button
# silently replayed stale quotes — the #1 complaint from the first rollout.

_WISDOM_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _wisdom_json(payload: dict, status_code: int = 200):
    from fastapi.responses import JSONResponse
    return JSONResponse(payload, status_code=status_code,
                        headers=_WISDOM_NO_CACHE_HEADERS)


@app.get("/api/wisdom/quote-of-the-day")
def wisdom_qotd():
    """Deterministic-by-date quote. Same date → same quote on every device."""
    q = trading_wisdom.quote_of_the_day()
    return _wisdom_json({**q, "date": datetime.now().strftime("%Y-%m-%d")})


@app.get("/api/wisdom/random")
def wisdom_random(tags: str = "", exclude: str = ""):
    """Random quote, optionally filtered by comma-separated tags / authors."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] or None
    ex_list = [a.strip() for a in exclude.split(",") if a.strip()] or None
    q = trading_wisdom.random_quote(tags=tag_list, exclude_authors=ex_list)
    if not q:
        return _wisdom_json({"detail": "no quotes match"}, status_code=404)
    return _wisdom_json(q)


@app.get("/api/wisdom/for-page")
def wisdom_for_page(page: str = "home", regime: str = "unknown",
                    count: int = 3):
    """Contextual nudges for a page + market-regime combination.

    regime: 'bull' | 'bear' | 'neutral' | 'unknown'

    Returns a FRESH random mix on every call (no date-seed lock-in) — that
    is what makes the panel feel alive as the user moves between pages.
    """
    count = max(1, min(count, 10))
    items = trading_wisdom.reminders_for_page(
        page=page, market_regime=regime, count=count)
    return _wisdom_json({"page": page, "regime": regime,
                         "count": len(items), "items": items})


@app.get("/api/wisdom/stats")
def wisdom_stats():
    """Totals, per-author & per-tag counts — used by tests and an About page."""
    return _wisdom_json(trading_wisdom.stats())


# ═══════════════════════════════════════════════════════════════════════════════
# ── EDUCATION / SWING TRADING GUIDE ────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/education/modules")
def education_modules():
    """Static educational content for the Learn page — swing trading fundamentals."""
    modules = [
        {
            "id": "market_phases",
            "title": "📈 Gain Expectations by Market Phase",
            "icon": "📈",
            "sections": [
                {"phase": "Stage 1 — Accumulation / Base Building", "regime": "sideways", "color": "#f59e0b",
                 "expected_gain": "0–5% (no trend — WAIT)", "position_size": "0% — CASH",
                 "hold_period": "N/A — wait for Stage 2 pivot",
                 "rules": ["DO NOT enter Stage 1.", "Build watchlist, study charts.", "Long Stage 1 base → explosive Stage 2 breakout."]},
                {"phase": "Stage 2 — Uptrend (The Money Stage)", "regime": "bull", "color": "#22c55e",
                 "expected_gain": "20%–200%+ per swing leader",
                 "position_size": "Full size (1–2% risk per trade, up to 6 positions)",
                 "hold_period": "Weeks to months — trail with EMA until Stage 3",
                 "rules": ["Go aggressive. Press winners. Add on follow-through.", "Trail 21-EMA normal / 10-EMA fast movers.", "Target 3R min. Let leaders run to 5R–10R.", "FII net buyers + breadth > 60% above 50-DMA."]},
                {"phase": "Stage 3 — Distribution / Top", "regime": "topping", "color": "#ef4444",
                 "expected_gain": "Negative — EXIT ALL LONGS",
                 "position_size": "0–25% — reduce aggressively",
                 "hold_period": "Exit on first crack of key support",
                 "rules": ["4+ distribution days in 4 weeks = market TOPPED.", "Sell weakest first, then trim strongest.", "Climax run (25%+ in 1–2 weeks from extended base) = SELL.", "FII selling + rupee falling = follow them out."]},
                {"phase": "Stage 4 — Downtrend", "regime": "bear", "color": "#475569",
                 "expected_gain": "Negative for longs — CASH stage",
                 "position_size": "0% longs — max cash",
                 "hold_period": "Wait for confirmed Follow-Through Day",
                 "rules": ["Zero longs in Stage 4.", "Use downtime to journal, study, update WL.", "Follow-Through Day (Day 4+, up 1.25%+ on volume) = first buy signal."]},
            ]
        },
        {
            "id": "trail_methodology",
            "title": "🎯 Trail Methodology",
            "icon": "🎯",
            "sections": [
                {"method": "10-EMA Trail", "best_for": "Fast movers, momentum stocks, IPO breakouts", "color": "#22c55e",
                 "rules": ["Stop = 10-EMA each day.", "Exit on daily close below 10-EMA on volume > 1.5× avg.", "Grace one low-volume test.", "ADR ≥ 4% required."]},
                {"method": "21-EMA Trail", "best_for": "Standard swings, 2–6 week holds", "color": "#06b6d4",
                 "rules": ["Stop = 21-EMA (weekly close basis).", "Two consecutive weekly closes below = EXIT.", "Average up only while price > 21-EMA."]},
                {"method": "50-EMA Trail", "best_for": "Leaders, 1–3 month trend trades", "color": "#8b5cf6",
                 "rules": ["Stop = 50-EMA. Allow 15–20% pullbacks.", "Exit on 50-EMA breach high volume OR climax run.", "Weekly chart check every Sunday for Stage 2 integrity."]},
                {"method": "Key-Level / Structure Stop", "best_for": "VCPs, Bull Flags, tight setups", "color": "#f59e0b",
                 "rules": ["After breakout: stop = below breakout candle low.", "Update stop each time a new base forms.", "Never move structure stop more than 0.5×ATR above entry in first week."]},
            ]
        },
        {
            "id": "position_sizing",
            "title": "⚖️ Position Sizing",
            "icon": "⚖️",
            "sections": [
                {"mode": "AGGRESSIVE — Strong Bull", "color": "#22c55e",
                 "risk_per_trade": "1.5–2% per trade", "max_open_risk": "8–10% total", "max_positions": "5–6",
                 "formula": "Shares = (Capital × 2%) ÷ (Entry − SL)",
                 "conditions": ["Nifty above 50-EMA+200-EMA", "A/D > 1.5 for 10+ days", "FII net buyers 5+ sessions", "70%+ above 50-DMA"]},
                {"mode": "STANDARD — Neutral / Mixed", "color": "#06b6d4",
                 "risk_per_trade": "1% per trade", "max_open_risk": "5–6% total", "max_positions": "4–5",
                 "formula": "Shares = (Capital × 1%) ÷ (Entry − SL)",
                 "conditions": ["Nifty above 200-EMA, choppy", "A/D 0.8–1.5", "FII mixed"]},
                {"mode": "DEFENSIVE — Bear / Correction", "color": "#ef4444",
                 "risk_per_trade": "0.5% per trade", "max_open_risk": "2–3% total", "max_positions": "1–2 (RS leaders only)",
                 "formula": "Shares = (Capital × 0.5%) ÷ (Entry − SL)",
                 "conditions": ["Nifty below 200-EMA", "A/D < 0.8", "FII net sellers 5+ sessions", "<30% above 50-DMA"]},
            ]
        },
        {
            "id": "swing_length",
            "title": "⏱️ Swing Length Benchmarks",
            "icon": "⏱️",
            "sections": [
                {"type": "Micro Swing", "duration": "2–5 days", "target_gain": "3–8%", "trail": "10-EMA / 2-day low",
                 "best_for": "Range expansions, episodic pivots, news gaps",
                 "early_signals": ["First 45-min tight range then expansion", "Volume surge > 3× on trigger candle"]},
                {"type": "Standard Swing", "duration": "1–3 weeks", "target_gain": "8–20%", "trail": "21-EMA",
                 "best_for": "Bull flags, VCPs, breakouts from tight bases",
                 "early_signals": ["Volume dry-up 3+ sessions before breakout", "RS line new high before price"]},
                {"type": "Trend Ride", "duration": "1–3 months", "target_gain": "25–80%", "trail": "50-EMA",
                 "best_for": "Stage 2 leaders, sector themes, FII momentum plays",
                 "early_signals": ["Pocket pivot — up day on vol > any down-vol in prior 10 sessions", "Weekly marubozu from base"]},
                {"type": "Super-Performance", "duration": "3–18 months", "target_gain": "100–500%+", "trail": "Weekly 50-EMA",
                 "best_for": "IPO momentum, turnaround, new sector leaders (Pradeep Bonde style)",
                 "early_signals": ["EPS acceleration 3+ quarters", "RS line at all-time high", "First stage-2 breakout post-IPO"]},
            ]
        }
    ]
    return {"modules": modules, "count": len(modules)}


# ═══════════════════════════════════════════════════════════════════════════════
# ── IBD BACKTESTER ─────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_scan_dir_date(dirname: str) -> str | None:
    """Extract YYYYMMDD from a scan dir name like scan_india_daily_full_20260415_2331."""
    parts = dirname.rsplit("_", 2)
    if len(parts) >= 2:
        datepart = parts[-2]
        if len(datepart) == 8 and datepart.isdigit():
            return f"{datepart[:4]}-{datepart[4:6]}-{datepart[6:8]}"
    return None


def _collect_scan_history(market: str = "india", timeframe: str = "daily") -> list[dict]:
    """Collect all scan runs from output directories. Returns list of {date, dir, items}."""
    import glob
    pattern = str(OUTPUT_DIR / f"scan_{market}_{timeframe}_full_*")
    dirs = sorted(glob.glob(pattern))
    runs = []
    seen_dates = set()
    for d in dirs:
        dirname = Path(d).name
        scan_date = _parse_scan_dir_date(dirname)
        if not scan_date:
            continue
        # Keep latest scan per date
        if scan_date in seen_dates:
            # Replace with later scan
            runs = [r for r in runs if r["date"] != scan_date]
        seen_dates.add(scan_date)
        # Try watchlist JSON first, then vcp_hits
        items = []
        for prefix in ["watchlist", "vcp_hits"]:
            pattern_json = list(Path(d).glob(f"{prefix}_*.json"))
            if pattern_json:
                try:
                    data = json.loads(pattern_json[0].read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        items = data
                        break
                except Exception:
                    pass
        runs.append({"date": scan_date, "dir": d, "items": items, "count": len(items)})
    return runs


@app.get("/api/ibd-backtest/scan-dates")
def ibd_backtest_scan_dates(market: str = "india", timeframe: str = "daily") -> dict:
    """List all available scan dates for the backtester date picker."""
    runs = _collect_scan_history(market, timeframe)
    dates = [{"date": r["date"], "count": r["count"]} for r in runs]
    return {"dates": dates, "total": len(dates)}


def _run_account_simulator(
    filtered_runs: list[dict],
    results: list[dict],
    market: str,
    starting_capital: float = 100_000.0,
    max_open_risk_pct: float = 6.0,
) -> dict:
    """
    Simulate a real trading account over scan history.
    Rules:
    - Per-trade risk: 1% (B/C) / 2% (A) / 3% (A+) of current capital
    - Max 6% total open risk at any time
    - Best R:R trades picked first each scan
    - Exits tracked via OHLCV (SL hit / T2 / T3 / end of period)
    """
    from statistics import mean

    results_by_sym = {r["symbol"]: r for r in results}

    def _trade_risk_pct(rating: str) -> float:
        return 3.0 if rating == "A+" else 2.0 if rating == "A" else 1.0

    # State as mutable containers (avoids nonlocal issues)
    state = {"capital": starting_capital}
    open_positions: list[dict] = []
    closed_trades: list[dict] = []
    equity_curve: list[dict] = []

    # OHLCV cache
    ohlcv_cache: dict[str, list[dict]] = {}

    def _get_ohlcv(sym: str) -> list[dict]:
        if sym not in ohlcv_cache:
            ohlcv_cache[sym] = _read_ohlcv(sym, days=0, market=market) or []
        return ohlcv_cache[sym]

    def _price_on_date(sym: str, dt: str) -> float:
        rows = _get_ohlcv(sym)
        last = 0.0
        for row in rows:
            if row["date"] == dt:
                return float(row["close"])
            if row["date"] < dt:
                last = float(row["close"])
            else:
                break
        return last

    def _bar_on_date(sym: str, dt: str):
        for row in _get_ohlcv(sym):
            if row["date"] == dt:
                return row
        return None

    # Build trading calendar from Nifty or first symbol
    all_dates: set[str] = set()
    for run in filtered_runs:
        all_dates.add(run["date"])
    cal_sym = "^NSEI" if market == "india" else (results[0]["symbol"] if results else "")
    if cal_sym and filtered_runs:
        first_dt = filtered_runs[0]["date"]
        for row in _get_ohlcv(cal_sym):
            if row["date"] >= first_dt:
                all_dates.add(row["date"])
    sorted_dates = sorted(all_dates)

    scan_date_set = {run["date"] for run in filtered_runs}
    scan_items_by_date = {run["date"]: run["items"] for run in filtered_runs}

    def _open_risk_pct() -> float:
        return sum(p["risk_pct"] for p in open_positions)

    def _close_trade(pos: dict, exit_price: float, exit_reason: str, dt: str):
        pnl_per = exit_price - pos["entry"]
        pnl = round(pnl_per * pos["qty"], 2)
        pnl_pct = round(pnl_per / pos["entry"] * 100, 2) if pos["entry"] else 0
        rr = round(pnl / pos["risk_amt"], 2) if pos["risk_amt"] else 0
        state["capital"] += pnl
        holding = sum(1 for d in sorted_dates if pos["date"] < d <= dt)
        closed_trades.append({
            "symbol": pos["symbol"],
            "displaySymbol": pos["displaySymbol"],
            "setup": pos["setup"],
            "rating": pos["rating"],
            "entry": pos["entry"],
            "exit": round(exit_price, 2),
            "qty": pos["qty"],
            "pnl": pnl,
            "pnlPct": pnl_pct,
            "riskPct": pos["risk_pct"],
            "rrAchieved": rr,
            "exitReason": exit_reason,
            "entryDate": pos["date"],
            "exitDate": dt,
            "holdingDays": holding,
        })

    for dt in sorted_dates:
        # 1. Check exits
        still_open = []
        for pos in open_positions:
            bar = _bar_on_date(pos["symbol"], dt)
            if not bar:
                still_open.append(pos)
                continue
            lo, hi = float(bar.get("low", 0)), float(bar.get("high", 0))
            if pos["sl"] > 0 and lo <= pos["sl"]:
                _close_trade(pos, pos["sl"], "SL_HIT", dt)
            elif pos["t3"] > 0 and hi >= pos["t3"]:
                _close_trade(pos, pos["t3"], "T3_HIT", dt)
            elif pos["t2"] > 0 and hi >= pos["t2"]:
                _close_trade(pos, pos["t2"], "T2_HIT", dt)
            else:
                still_open.append(pos)
        open_positions.clear()
        open_positions.extend(still_open)

        # 2. Enter trades on scan dates
        if dt in scan_date_set:
            open_syms = {p["symbol"] for p in open_positions}
            candidates = []
            for item in scan_items_by_date.get(dt, []):
                sym = item.get("symbol", "")
                if not sym or sym in open_syms:
                    continue
                if sym not in results_by_sym:
                    continue
                try:
                    entry = float(item.get("entry") or item.get("close") or 0)
                    sl = float(item.get("sl") or 0)
                    t1 = float(item.get("T1") or item.get("t1") or 0)
                    t2 = float(item.get("T2") or item.get("t2") or 0)
                    t3 = float(item.get("T3") or item.get("t3") or 0)
                except (ValueError, TypeError):
                    continue
                if entry <= 0 or sl <= 0 or sl >= entry:
                    continue
                risk_per = entry - sl
                rr = (t1 - entry) / risk_per if t1 > entry and risk_per > 0 else 0
                if rr < 1.0:
                    continue
                score = float(item.get("score") or item.get("rsScore") or 0)
                candidates.append({
                    "symbol": sym,
                    "displaySymbol": results_by_sym[sym]["displaySymbol"],
                    "entry": entry, "sl": sl, "t1": t1, "t2": t2, "t3": t3,
                    "risk_per": risk_per, "rr": round(rr, 2),
                    "rating": item.get("rating", ""),
                    "setup": item.get("setup", ""),
                    "score": score,
                })
            candidates.sort(key=lambda c: (-c["rr"], -c["score"]))
            cap = state["capital"]
            for cand in candidates:
                if _open_risk_pct() >= max_open_risk_pct:
                    break
                trade_risk = _trade_risk_pct(cand["rating"])
                avail_risk = max_open_risk_pct - _open_risk_pct()
                trade_risk = min(trade_risk, avail_risk)
                if trade_risk < 0.5:
                    break
                risk_amt = cap * trade_risk / 100.0
                qty = max(1, int(risk_amt / cand["risk_per"]))
                pos_size = qty * cand["entry"]
                if pos_size > cap * 0.25:
                    qty = max(1, int(cap * 0.25 / cand["entry"]))
                    pos_size = qty * cand["entry"]
                if pos_size > cap * 0.95:
                    continue
                open_positions.append({
                    "symbol": cand["symbol"],
                    "displaySymbol": cand["displaySymbol"],
                    "entry": cand["entry"],
                    "sl": cand["sl"], "t1": cand["t1"],
                    "t2": cand["t2"], "t3": cand["t3"],
                    "qty": qty,
                    "risk_pct": trade_risk,
                    "risk_amt": round(risk_amt, 2),
                    "date": dt,
                    "rating": cand["rating"],
                    "setup": cand["setup"],
                })
                open_syms.add(cand["symbol"])

        # 3. Mark-to-market equity snapshot
        cap = state["capital"]
        mtm = sum(
            pos["qty"] * (_price_on_date(pos["symbol"], dt) or pos["entry"])
            for pos in open_positions
        )
        invested = sum(p["qty"] * p["entry"] for p in open_positions)
        equity_curve.append({
            "date": dt,
            "equity": round(cap + (mtm - invested), 2),
            "cash": round(cap, 2),
            "openRiskPct": round(_open_risk_pct(), 2),
            "openPositions": len(open_positions),
            "invested": round(invested, 2),
        })

    # Close all remaining positions at last known price
    final_dt = sorted_dates[-1] if sorted_dates else ""
    for pos in list(open_positions):
        price = _price_on_date(pos["symbol"], final_dt) or pos["entry"]
        _close_trade(pos, price, "STILL_OPEN", final_dt)
    open_positions.clear()

    # ── Summary ───────────────────────────────────────────────────────────────
    total = len(closed_trades)
    winners = [t for t in closed_trades if t["pnl"] > 0]
    losers  = [t for t in closed_trades if t["pnl"] <= 0]
    final_eq = equity_curve[-1]["equity"] if equity_curve else starting_capital
    total_return = round((final_eq - starting_capital) / starting_capital * 100, 2)

    max_eq = starting_capital
    max_dd = 0.0
    for pt in equity_curve:
        max_eq = max(max_eq, pt["equity"])
        dd = (pt["equity"] - max_eq) / max_eq * 100
        max_dd = min(max_dd, dd)

    gross_w = round(sum(t["pnl"] for t in winners), 2)
    gross_l = round(sum(t["pnl"] for t in losers), 2)
    pf = round(gross_w / abs(gross_l), 2) if gross_l else 999

    max_ws = max_ls = cur_w = cur_l = 0
    for t in closed_trades:
        if t["pnl"] > 0:
            cur_w += 1; cur_l = 0; max_ws = max(max_ws, cur_w)
        else:
            cur_l += 1; cur_w = 0; max_ls = max(max_ls, cur_l)

    setup_stats: dict[str, dict] = {}
    for t in closed_trades:
        s = t["setup"] or "Unknown"
        ss = setup_stats.setdefault(s, {"count": 0, "wins": 0, "totalPnl": 0.0, "pnls": []})
        ss["count"] += 1
        ss["totalPnl"] += t["pnl"]
        ss["pnls"].append(t["pnlPct"])
        if t["pnl"] > 0:
            ss["wins"] += 1
    setup_breakdown = [
        {
            "setup": s,
            "count": ss["count"],
            "winRate": round(ss["wins"] / ss["count"] * 100) if ss["count"] else 0,
            "totalPnl": round(ss["totalPnl"], 2),
            "avgPnl": round(mean(ss["pnls"]), 2) if ss["pnls"] else 0,
        }
        for s, ss in sorted(setup_stats.items(), key=lambda x: -x[1]["count"])
    ]
    best  = max(closed_trades, key=lambda t: t["pnlPct"]) if closed_trades else {}
    worst = min(closed_trades, key=lambda t: t["pnlPct"]) if closed_trades else {}

    return {
        "startingCapital": starting_capital,
        "finalEquity": final_eq,
        "totalReturn": total_return,
        "totalPnl": round(sum(t["pnl"] for t in closed_trades), 2),
        "maxDrawdown": round(max_dd, 2),
        "totalTrades": total,
        "winners": len(winners),
        "losers": len(losers),
        "winRate": round(len(winners) / total * 100) if total else 0,
        "avgWinner": round(mean([t["pnlPct"] for t in winners]), 2) if winners else 0,
        "avgLoser":  round(mean([t["pnlPct"] for t in losers]),  2) if losers  else 0,
        "avgRR": round(mean([t["rrAchieved"] for t in closed_trades]), 2) if closed_trades else 0,
        "avgHoldDays": round(mean([t["holdingDays"] for t in closed_trades]), 1) if closed_trades else 0,
        "profitFactor": pf,
        "grossWinners": gross_w,
        "grossLosers": gross_l,
        "maxWinStreak": max_ws,
        "maxLossStreak": max_ls,
        "maxOpenRisk": max_open_risk_pct,
        "bestTrade":  {"symbol": best.get("displaySymbol",""),  "pnlPct": best.get("pnlPct",0),  "pnl": best.get("pnl",0)}  if best  else {},
        "worstTrade": {"symbol": worst.get("displaySymbol",""), "pnlPct": worst.get("pnlPct",0), "pnl": worst.get("pnl",0)} if worst else {},
        "setupBreakdown": setup_breakdown,
        "trades": closed_trades[-200:],
        "equityCurve": equity_curve,
    }


@app.get("/api/ibd-backtest/run")
def ibd_backtest_run(
    market: str = "india",
    timeframe: str = "daily",
    start_date: str = "",
    end_date: str = "",
    preset: str = "",  # 1d, 1w, 1m, 3m, 6m, 1y, ytd, all
    min_appearances: int = 1,
    setup_filter: str = "",
    rating_filter: str = "",
    sector_filter: str = "",
) -> dict:
    """
    Run IBD-style backtest over scan history.

    Returns per-symbol analytics: return from scan entry, return till date,
    RS changes, scan appearances, sector, setup type, and more.
    """
    from datetime import date as _date

    today = _date.today()

    # Resolve date range
    if preset:
        end = today
        if preset == "1d":
            start = today - timedelta(days=1)
        elif preset == "1w":
            start = today - timedelta(days=7)
        elif preset == "1m":
            start = today - timedelta(days=30)
        elif preset == "3m":
            start = today - timedelta(days=90)
        elif preset == "6m":
            start = today - timedelta(days=180)
        elif preset == "1y":
            start = today - timedelta(days=365)
        elif preset == "ytd":
            start = _date(today.year, 1, 1)
        else:  # "all"
            start = _date(2020, 1, 1)
        start_str = start.isoformat()
        end_str = end.isoformat()
    else:
        start_str = start_date or "2020-01-01"
        end_str = end_date or today.isoformat()

    runs = _collect_scan_history(market, timeframe)
    # Filter to date range
    filtered_runs = [r for r in runs if start_str <= r["date"] <= end_str]

    if not filtered_runs:
        return {
            "dateRange": {"start": start_str, "end": end_str},
            "totalScans": 0,
            "symbols": [],
            "summary": {},
            "sectorBreakdown": [],
            "setupBreakdown": [],
            "ratingBreakdown": [],
        }

    # Aggregate per symbol across all scans in range
    symbol_data: dict[str, dict] = {}
    scan_dates_used = []

    for run in filtered_runs:
        scan_dates_used.append(run["date"])
        for item in run["items"]:
            sym = item.get("symbol", "")
            if not sym:
                continue
            setup = item.get("setup", "")
            rating = item.get("rating", "")

            # Apply filters
            if setup_filter and setup.upper() != setup_filter.upper():
                continue
            if rating_filter and rating.upper() != rating_filter.upper():
                continue

            if sym not in symbol_data:
                symbol_data[sym] = {
                    "symbol": sym,
                    "appearances": [],
                    "setups": [],
                    "ratings": [],
                    "rsScores": [],
                    "rs3m": [],
                    "rs6m": [],
                    "rs12m": [],
                    "entries": [],
                    "targets": {"t1": [], "t2": [], "t3": []},
                    "stops": [],
                    "regimeStates": [],
                    "rankingScores": [],
                    "firstScanDate": run["date"],
                    "lastScanDate": run["date"],
                    "firstEntry": None,
                    "firstClose": None,
                }

            sd = symbol_data[sym]
            sd["appearances"].append(run["date"])
            sd["lastScanDate"] = run["date"]
            if setup and setup not in sd["setups"]:
                sd["setups"].append(setup)
            if rating and rating not in sd["ratings"]:
                sd["ratings"].append(rating)

            # RS scores over time
            rs = item.get("rsScore")
            if rs is not None:
                try:
                    sd["rsScores"].append({"date": run["date"], "value": round(float(rs), 1)})
                except (ValueError, TypeError):
                    pass
            for rk in ["rs3m", "rs6m", "rs12m"]:
                val = item.get(rk)
                if val is not None:
                    try:
                        sd[rk].append({"date": run["date"], "value": round(float(val), 1)})
                    except (ValueError, TypeError):
                        pass

            # Entry/SL/Targets
            entry = item.get("entry")
            if entry:
                try:
                    ev = float(entry)
                    sd["entries"].append({"date": run["date"], "value": ev})
                    if sd["firstEntry"] is None:
                        sd["firstEntry"] = ev
                except (ValueError, TypeError):
                    pass
            close_val = item.get("close")
            if close_val:
                try:
                    sd["firstClose"] = sd["firstClose"] or float(close_val)
                except (ValueError, TypeError):
                    pass
            for tk in ["T1", "T2", "T3"]:
                tv = item.get(tk) or item.get(tk.lower())
                if tv:
                    try:
                        sd["targets"][tk.lower()].append(float(tv))
                    except (ValueError, TypeError):
                        pass
            sl_val = item.get("sl")
            if sl_val:
                try:
                    sd["stops"].append(float(sl_val))
                except (ValueError, TypeError):
                    pass
            regime = item.get("regimeState")
            if regime and regime not in sd["regimeStates"]:
                sd["regimeStates"].append(regime)
            rs_rank = item.get("rankingScore")
            if rs_rank is not None:
                try:
                    sd["rankingScores"].append(round(float(rs_rank), 1))
                except (ValueError, TypeError):
                    pass

    # Now enrich with current price data and sector info
    taxonomy = {}
    try:
        taxonomy = _load_taxonomy_cached() or {}
    except Exception:
        pass

    results = []
    for sym, sd in symbol_data.items():
        # Get OHLCV for returns computation
        base = sym.replace(".NS", "").replace(".BO", "")
        rows = _read_ohlcv(sym, days=0, market=market)
        current_price = 0
        first_scan_price = 0
        price_on_first_scan = 0
        price_history = []

        if rows:
            current_price = rows[-1]["close"]
            # Find price on first scan date
            first_date = sd["firstScanDate"]
            last_date = sd["lastScanDate"]
            for r in rows:
                if r["date"] == first_date:
                    price_on_first_scan = r["close"]
                    break
                if r["date"] < first_date:
                    price_on_first_scan = r["close"]  # use last available before scan
            if not price_on_first_scan and rows:
                # Fallback: use closest available
                for r in rows:
                    if r["date"] >= first_date:
                        price_on_first_scan = r["close"]
                        break
            # Build mini price series from first scan date
            for r in rows:
                if r["date"] >= first_date:
                    price_history.append({"date": r["date"], "close": r["close"]})

        entry_price = sd["firstEntry"] or sd["firstClose"] or price_on_first_scan or 0
        # Returns
        return_from_entry = 0
        return_from_scan = 0
        if entry_price > 0 and current_price > 0:
            return_from_entry = round((current_price - entry_price) / entry_price * 100, 2)
        if price_on_first_scan > 0 and current_price > 0:
            return_from_scan = round((current_price - price_on_first_scan) / price_on_first_scan * 100, 2)

        # Max gain / max drawdown since first scan
        max_gain = 0
        max_drawdown = 0
        if price_history and entry_price > 0:
            for ph in price_history:
                g = (ph["close"] - entry_price) / entry_price * 100
                max_gain = max(max_gain, g)
                max_drawdown = min(max_drawdown, g)

        # Sector info from taxonomy
        sector = "Other"
        industry = "Other"
        basic_industry = "Other"
        tax_entry = taxonomy.get(base)
        if tax_entry:
            sector = tax_entry[0] or "Other"
            industry = tax_entry[1] or "Other"
            basic_industry = tax_entry[2] if len(tax_entry) > 2 else industry

        # Apply sector filter
        if sector_filter and sector.upper() != sector_filter.upper():
            continue

        # Average RS score
        avg_rs = 0
        if sd["rsScores"]:
            avg_rs = round(sum(x["value"] for x in sd["rsScores"]) / len(sd["rsScores"]), 1)
        latest_rs = sd["rsScores"][-1]["value"] if sd["rsScores"] else 0
        first_rs = sd["rsScores"][0]["value"] if sd["rsScores"] else 0
        rs_change = round(latest_rs - first_rs, 1) if sd["rsScores"] else 0

        # Best targets
        avg_t1 = round(sum(sd["targets"]["t1"]) / len(sd["targets"]["t1"]), 2) if sd["targets"]["t1"] else 0
        avg_t2 = round(sum(sd["targets"]["t2"]) / len(sd["targets"]["t2"]), 2) if sd["targets"]["t2"] else 0
        avg_t3 = round(sum(sd["targets"]["t3"]) / len(sd["targets"]["t3"]), 2) if sd["targets"]["t3"] else 0
        avg_sl = round(sum(sd["stops"]) / len(sd["stops"]), 2) if sd["stops"] else 0
        avg_rank = round(sum(sd["rankingScores"]) / len(sd["rankingScores"]), 1) if sd["rankingScores"] else 0

        # Risk/Reward
        risk = abs(entry_price - avg_sl) if entry_price and avg_sl else 0
        rr_ratio = round((avg_t1 - entry_price) / risk, 1) if risk > 0 and avg_t1 else 0

        # T1/T2/T3 hit status
        t1_hit = current_price >= avg_t1 > 0 if avg_t1 else False
        t2_hit = current_price >= avg_t2 > 0 if avg_t2 else False
        t3_hit = current_price >= avg_t3 > 0 if avg_t3 else False
        sl_hit = current_price <= avg_sl > 0 if avg_sl and current_price else False

        # Outcome
        outcome = "open"
        if sl_hit:
            outcome = "sl_hit"
        elif t3_hit:
            outcome = "t3_hit"
        elif t2_hit:
            outcome = "t2_hit"
        elif t1_hit:
            outcome = "t1_hit"
        elif return_from_entry > 0:
            outcome = "profit"
        elif return_from_entry < 0:
            outcome = "loss"

        results.append({
            "symbol": sym,
            "displaySymbol": base,
            "sector": sector,
            "industry": industry,
            "basicIndustry": basic_industry,
            "appearances": len(sd["appearances"]),
            "scanDates": sd["appearances"],
            "firstScanDate": sd["firstScanDate"],
            "lastScanDate": sd["lastScanDate"],
            "setups": sd["setups"],
            "ratings": sd["ratings"],
            "bestRating": "A+" if "A+" in sd["ratings"] else "A" if "A" in sd["ratings"] else (sd["ratings"][0] if sd["ratings"] else "—"),
            "entryPrice": round(entry_price, 2),
            "currentPrice": round(current_price, 2),
            "scanDayPrice": round(price_on_first_scan, 2),
            "returnFromEntry": return_from_entry,
            "returnFromScan": return_from_scan,
            "maxGain": round(max_gain, 2),
            "maxDrawdown": round(max_drawdown, 2),
            "avgRs": avg_rs,
            "latestRs": latest_rs,
            "rsChange": rs_change,
            "rsHistory": sd["rsScores"][-10:],  # last 10 data points
            "rs3mHistory": sd["rs3m"][-10:],
            "rs6mHistory": sd["rs6m"][-10:],
            "rs12mHistory": sd["rs12m"][-10:],
            "avgT1": avg_t1,
            "avgT2": avg_t2,
            "avgT3": avg_t3,
            "avgSl": avg_sl,
            "avgRankScore": avg_rank,
            "riskReward": rr_ratio,
            "t1Hit": t1_hit,
            "t2Hit": t2_hit,
            "t3Hit": t3_hit,
            "slHit": sl_hit,
            "outcome": outcome,
            "regimeStates": sd["regimeStates"],
            "priceHistory": price_history[-60:],  # last 60 data points for sparkline
        })

    # Sort by return descending
    results.sort(key=lambda x: -(x.get("returnFromEntry") or 0))

    # Summary stats
    total = len(results)
    winners = [r for r in results if r["returnFromEntry"] > 0]
    losers = [r for r in results if r["returnFromEntry"] < 0]
    avg_return = round(sum(r["returnFromEntry"] for r in results) / total, 2) if total else 0
    median_return = 0
    if results:
        sorted_rets = sorted(r["returnFromEntry"] for r in results)
        mid = len(sorted_rets) // 2
        median_return = sorted_rets[mid] if len(sorted_rets) % 2 else round((sorted_rets[mid-1] + sorted_rets[mid]) / 2, 2)
    avg_winner = round(sum(r["returnFromEntry"] for r in winners) / len(winners), 2) if winners else 0
    avg_loser = round(sum(r["returnFromEntry"] for r in losers) / len(losers), 2) if losers else 0
    t1_hits = sum(1 for r in results if r["t1Hit"])
    t2_hits = sum(1 for r in results if r["t2Hit"])
    t3_hits = sum(1 for r in results if r["t3Hit"])
    sl_hits = sum(1 for r in results if r["slHit"])

    # Sector breakdown
    sector_map: dict[str, list] = {}
    for r in results:
        s = r["sector"]
        sector_map.setdefault(s, []).append(r)
    sector_breakdown = []
    for s, items in sorted(sector_map.items(), key=lambda x: -len(x[1])):
        avg_ret = round(sum(i["returnFromEntry"] for i in items) / len(items), 2) if items else 0
        w = sum(1 for i in items if i["returnFromEntry"] > 0)
        sector_breakdown.append({
            "sector": s,
            "count": len(items),
            "avgReturn": avg_ret,
            "winRate": round(w / len(items) * 100) if items else 0,
            "symbols": [i["displaySymbol"] for i in items[:10]],
        })

    # Setup breakdown
    setup_map: dict[str, list] = {}
    for r in results:
        for s in r["setups"]:
            setup_map.setdefault(s, []).append(r)
    setup_breakdown = []
    for s, items in sorted(setup_map.items(), key=lambda x: -len(x[1])):
        avg_ret = round(sum(i["returnFromEntry"] for i in items) / len(items), 2) if items else 0
        w = sum(1 for i in items if i["returnFromEntry"] > 0)
        setup_breakdown.append({
            "setup": s,
            "count": len(items),
            "avgReturn": avg_ret,
            "winRate": round(w / len(items) * 100) if items else 0,
        })

    # Rating breakdown
    rating_map: dict[str, list] = {}
    for r in results:
        br = r["bestRating"]
        rating_map.setdefault(br, []).append(r)
    rating_breakdown = []
    for rt, items in sorted(rating_map.items()):
        avg_ret = round(sum(i["returnFromEntry"] for i in items) / len(items), 2) if items else 0
        w = sum(1 for i in items if i["returnFromEntry"] > 0)
        rating_breakdown.append({
            "rating": rt,
            "count": len(items),
            "avgReturn": avg_ret,
            "winRate": round(w / len(items) * 100) if items else 0,
        })

    summary = {
        "totalSymbols": total,
        "totalScans": len(filtered_runs),
        "scanDatesUsed": scan_dates_used,
        "winners": len(winners),
        "losers": len(losers),
        "winRate": round(len(winners) / total * 100) if total else 0,
        "avgReturn": avg_return,
        "medianReturn": median_return,
        "avgWinner": avg_winner,
        "avgLoser": avg_loser,
        "bestReturn": max((r["returnFromEntry"] for r in results), default=0),
        "worstReturn": min((r["returnFromEntry"] for r in results), default=0),
        "avgMaxGain": round(sum(r["maxGain"] for r in results) / total, 2) if total else 0,
        "avgMaxDrawdown": round(sum(r["maxDrawdown"] for r in results) / total, 2) if total else 0,
        "t1HitRate": round(t1_hits / total * 100) if total else 0,
        "t2HitRate": round(t2_hits / total * 100) if total else 0,
        "t3HitRate": round(t3_hits / total * 100) if total else 0,
        "slHitRate": round(sl_hits / total * 100) if total else 0,
        "avgAppearances": round(sum(r["appearances"] for r in results) / total, 1) if total else 0,
    }

    # ── Account Simulator ───────────────────────────────────────────────────────
    account_sim = {}
    try:
        account_sim = _run_account_simulator(
            filtered_runs, results, market, 100_000.0,
            max_open_risk_pct=6.0,
        )
    except Exception as _sim_e:
        print(f"⚠ account simulator failed: {_sim_e}", flush=True)
        import traceback; traceback.print_exc()
        account_sim = {"error": str(_sim_e)}

    # ── Scan-by-scan history (for "By Scan Date" view) ──────────────────────────
    results_by_sym = {r["symbol"]: r for r in results}
    scan_history = []
    for run in filtered_runs:
        run_date = run["date"]
        picks = []
        for item in run["items"]:
            sym = item.get("symbol", "")
            if not sym:
                continue
            r = results_by_sym.get(sym)
            if not r:
                continue  # filtered out by sector/setup/rating filter
            # Per-scan-date entry price (price when this specific scan ran)
            scan_entry = 0.0
            try:
                scan_entry = float(item.get("entry") or item.get("close") or 0)
            except (ValueError, TypeError):
                pass
            scan_return = 0.0
            cur = r["currentPrice"]
            if scan_entry > 0 and cur > 0:
                scan_return = round((cur - scan_entry) / scan_entry * 100, 2)
            picks.append({
                "symbol": sym,
                "displaySymbol": r["displaySymbol"],
                "sector": r["sector"],
                "setup": item.get("setup", ""),
                "rating": item.get("rating", ""),
                "rsScore": round(float(item.get("rsScore") or 0), 1),
                "scanEntry": round(scan_entry, 2),
                "currentPrice": round(cur, 2),
                "returnFromDate": scan_return,
                "outcome": r["outcome"],
            })
        picks.sort(key=lambda x: -(x.get("returnFromDate") or 0))
        w = sum(1 for p in picks if p["returnFromDate"] > 0)
        scan_history.append({
            "date": run_date,
            "count": len(picks),
            "winners": w,
            "losers": len(picks) - w,
            "winRate": round(w / len(picks) * 100) if picks else 0,
            "avgReturn": round(sum(p["returnFromDate"] for p in picks) / len(picks), 2) if picks else 0,
            "picks": picks,
        })

    return {
        "dateRange": {"start": start_str, "end": end_str},
        "totalScans": len(filtered_runs),
        "symbols": results,
        "summary": summary,
        "sectorBreakdown": sector_breakdown,
        "setupBreakdown": setup_breakdown,
        "ratingBreakdown": rating_breakdown,
        "scanHistory": scan_history,
        "accountSim": account_sim,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  RS SCAN AS-OF DATE — Run RS leaders scan using data only up to a past date,
#  then calculate returns from that date to today.
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/rs-scan-asof")
def rs_scan_asof(
    scan_date: str = "",            # YYYY-MM-DD — the "as-of" date
    end_date: str = "",             # YYYY-MM-DD — forward perf cutoff (default: latest)
    top_n: int = 50,
    min_price: float = 50.0,
    min_bars: int = 150,
    sort_by: str = "swing",         # swing | rs | adr | volume
    min_adr: float = 0.0,
    min_avg_vol: int = 0,
) -> dict:
    """
    Run the RS-leaders scan as if today were *scan_date*, using only OHLCV data
    up to that date. Then for each leader, compute the return from scan-date
    close to the most recent close (i.e. forward return till now).

    This lets users ask: "If I picked the RS top-50 on date X, how would they
    have done?"
    """
    from datetime import date as _date

    if not scan_date:
        raise HTTPException(status_code=400, detail="scan_date is required (YYYY-MM-DD)")

    try:
        sd = _date.fromisoformat(scan_date)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {scan_date}")

    today = _date.today()
    if sd >= today:
        raise HTTPException(status_code=400, detail="scan_date must be in the past")

    # ── end_date validation
    end_date_str = ""
    if end_date:
        try:
            ed = _date.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid end_date format: {end_date}")
        if ed <= sd:
            raise HTTPException(status_code=400, detail="end_date must be after scan_date")
        end_date_str = end_date  # YYYY-MM-DD string for filtering

    # ── Load Nifty benchmark — need enough history before scan_date for RS calc
    # RS needs ~260 trading bars before scan_date. Calculate how many calendar
    # days back from today we need to cover scan_date + 260 trading days of history.
    days_since_scan = (today - sd).days
    nifty_fetch_days = max(days_since_scan + 400, 520)  # +400 for ~260 trading day buffer
    market_prices_full = _get_fresh_nifty_benchmark(days=nifty_fetch_days)
    if not market_prices_full or not market_prices_full.get("close"):
        # Fallback: try loading with days=0 (all data)
        nifty_rows = _read_ohlcv("^NSEI", days=0, market="us")
        if nifty_rows and len(nifty_rows) >= 20:
            market_prices_full = {
                "dates": [r["date"] for r in nifty_rows],
                "close": [r["close"] for r in nifty_rows],
            }
        else:
            raise HTTPException(status_code=503, detail="Could not fetch Nifty50 data")

    # Truncate Nifty benchmark to scan_date (keep data UP TO and including scan_date)
    nifty_dates = market_prices_full["dates"]
    nifty_closes = market_prices_full["close"]
    cut_idx = len(nifty_dates)  # default: use all
    for i, d in enumerate(nifty_dates):
        if d > scan_date:
            cut_idx = i
            break

    if cut_idx < 60:
        raise HTTPException(status_code=400, detail=f"Not enough Nifty data before {scan_date} for RS computation (need ≥60 bars, have {cut_idx})")

    market_prices_trunc = {
        "dates": nifty_dates[:cut_idx],
        "close": nifty_closes[:cut_idx],
    }

    # Get Nifty close on scan_date and end_date (or latest) for benchmark return
    nifty_scan_close = nifty_closes[cut_idx - 1] if cut_idx > 0 else nifty_closes[0]
    if end_date_str:
        nifty_end_idx = len(nifty_dates) - 1
        for i, d in enumerate(nifty_dates):
            if d > end_date_str:
                nifty_end_idx = max(0, i - 1)
                break
        nifty_now_close = nifty_closes[nifty_end_idx]
    else:
        nifty_now_close = nifty_closes[-1]
    nifty_return_pct = round((nifty_now_close - nifty_scan_close) / nifty_scan_close * 100, 2) if nifty_scan_close else 0

    # ── Taxonomy
    taxonomy = {}
    try:
        taxonomy = _load_taxonomy_cached() or {}
    except Exception:
        pass

    universe = [s for s in _list_india_cache_symbols() if s.upper() != "^NSEI"]

    def _ema(src: list[float], period: int) -> float:
        k = 2 / (period + 1)
        e = src[0]
        for v in src[1:]:
            e = v * k + e * (1 - k)
        return e

    def _score_one(sym: str):
        rows_full = _read_ohlcv(sym, days=0, market="india")
        if not rows_full:
            return None

        # Truncate to scan_date
        rows = [r for r in rows_full if r["date"] <= scan_date]
        if not rows:
            return None

        n_bars = len(rows)
        last_close = rows[-1]["close"]
        if last_close < min_price:
            return None

        # ── IPO detection: <126 trading days as of scan_date ≈ listed within ~6 months
        is_ipo = n_bars < 126

        # For non-IPO: respect min_bars; for IPO: need at least 15 bars
        if is_ipo:
            if n_bars < 15:
                return None
        else:
            if n_bars < min_bars:
                return None

        closes = [r["close"] for r in rows]
        highs  = [r["high"]  for r in rows]
        lows   = [r["low"]   for r in rows]
        vols   = [r.get("volume", 0) or 0 for r in rows]
        dates  = [r["date"]  for r in rows]

        stock_prices = {"close": closes, "dates": dates}

        # ── RS Score — IPO gets shorter periods (1M/2M/3M), normal gets standard
        try:
            if is_ipo:
                rs = _wpe.compute_rs_score(
                    stock_prices, market_prices_trunc,
                    periods=[21, 42, 63],
                    weights=[0.50, 0.30, 0.20],
                )
            else:
                rs = _wpe.compute_rs_score(stock_prices, market_prices_trunc)
        except Exception:
            return None

        score = rs.get("rs_score")
        if score is None:
            return None

        # ADR%
        adr_period = min(20, n_bars)
        recent = rows[-adr_period:]
        adr_abs = sum(r["high"] - r["low"] for r in recent) / adr_period
        adr_pct = round(adr_abs / last_close * 100, 2) if last_close else 0

        # Volume
        vol_period = min(20, n_bars)
        avg_vol_20 = sum(vols[-vol_period:]) / vol_period if vol_period else 0
        last_vol   = vols[-1] if vols else 0
        vol_ratio  = round(last_vol / avg_vol_20, 2) if avg_vol_20 else 1.0
        avg_vol_5 = sum(vols[-5:]) / min(5, n_bars) if n_bars >= 5 else avg_vol_20
        vol_surge_5d = round(avg_vol_5 / avg_vol_20, 2) if avg_vol_20 else 1.0

        if min_avg_vol and avg_vol_20 < min_avg_vol:
            return None
        if min_adr and adr_pct < min_adr:
            return None

        # Trend
        ema10  = round(_ema(closes, 10), 2)  if n_bars >= 10  else last_close
        ema21  = round(_ema(closes, 21), 2)  if n_bars >= 21  else last_close
        sma50  = round(sum(closes[-50:]) / 50, 2) if n_bars >= 50  else 0

        above_ema21 = last_close >= ema21
        above_sma50 = last_close >= sma50 if sma50 else False

        # 52wk
        lookback = rows[-252:] if n_bars >= 252 else rows
        hi52  = max(r["high"] for r in lookback)
        lo52  = min(r["low"]  for r in lookback)
        pct_from_hi  = round((last_close - hi52) / hi52 * 100, 2) if hi52 else 0

        # Swing score
        rs_pts   = min(score, 99) / 99 * 40
        adr_pts  = min(adr_pct / 4.0, 1.0) * 20
        vs_pts   = min((vol_surge_5d - 1.0) / 2.0, 1.0) * 20 if vol_surge_5d > 1 else 0
        hi_pts   = max(0, (1 - abs(pct_from_hi) / 20.0)) * 20
        swing_score = round(rs_pts + adr_pts + vs_pts + hi_pts, 1)

        # ── IPO bonus: freshly-listed strong RS gets extra weight (recency premium)
        if is_ipo:
            swing_score = round(min(swing_score * 1.15, 100), 1)

        # ── IPO-specific: % gain from listing price (first close)
        listing_gain_pct = round((last_close - closes[0]) / closes[0] * 100, 1) if is_ipo and closes[0] else None

        tax_entry = taxonomy.get(sym)
        sector         = tax_entry[0] if tax_entry else "Other"
        industry       = tax_entry[1] if tax_entry else "Other"
        basic_industry = tax_entry[2] if tax_entry and len(tax_entry) > 2 else industry

        # ── Forward return: scan_date close → end_date close (or latest)
        if end_date_str:
            end_rows = [r for r in rows_full if r["date"] <= end_date_str]
            current_close = end_rows[-1]["close"] if end_rows else 0
            current_date = end_rows[-1]["date"] if end_rows else ""
        else:
            current_close = rows_full[-1]["close"] if rows_full else 0
            current_date = rows_full[-1]["date"] if rows_full else ""
        scan_close = last_close  # close on/before scan_date
        fwd_return_pct = round((current_close - scan_close) / scan_close * 100, 2) if scan_close > 0 and current_close > 0 else 0

        # Max gain & max drawdown since scan_date (up to end_date if set)
        if end_date_str:
            fwd_rows = [r for r in rows_full if scan_date < r["date"] <= end_date_str]
        else:
            fwd_rows = [r for r in rows_full if r["date"] > scan_date]
        max_gain = 0.0
        max_dd = 0.0
        if fwd_rows and scan_close > 0:
            for fr in fwd_rows:
                g = (fr["close"] - scan_close) / scan_close * 100
                max_gain = max(max_gain, g)
                max_dd = min(max_dd, g)

        return {
            "symbol":           sym,
            "sector":           sector,
            "industry":         industry,
            "basicIndustry":    basic_industry,
            "is_ipo":           is_ipo,
            "bars":             n_bars,
            "rs_score":         score,
            "rs_label":         rs.get("rs_label"),
            "excess_pct":       rs.get("weighted_excess_pct"),
            "scanClose":        round(scan_close, 2),
            "currentClose":     round(current_close, 2),
            "currentDate":      current_date,
            "fwdReturnPct":     fwd_return_pct,
            "maxGainPct":       round(max_gain, 2),
            "maxDrawdownPct":   round(max_dd, 2),
            "adrPct":           adr_pct,
            "avgVol20":         round(avg_vol_20),
            "volSurge5d":       vol_surge_5d,
            "aboveEma21":       above_ema21,
            "aboveSma50":       above_sma50,
            "swingScore":       swing_score,
            "pctFrom52wHigh":   pct_from_hi,
            "listingGainPct":   listing_gain_pct,
        }

    from concurrent.futures import ThreadPoolExecutor

    scored: list[dict] = []
    with ThreadPoolExecutor(max_workers=12, initializer=_ig_worker_init) as pool:
        for res in pool.map(_score_one, universe):
            if res is not None:
                scored.append(res)

    # Sort
    _sort_keys = {
        "swing":  lambda x: (x.get("swingScore") or 0, x.get("rs_score") or 0),
        "rs":     lambda x: (x.get("rs_score") or 0, x.get("excess_pct") or 0),
        "adr":    lambda x: (x.get("adrPct") or 0, x.get("rs_score") or 0),
        "volume": lambda x: (x.get("volSurge5d") or 0, x.get("rs_score") or 0),
    }
    scored.sort(key=_sort_keys.get(sort_by, _sort_keys["swing"]), reverse=True)
    top = scored[:top_n]
    for i, s in enumerate(top, start=1):
        s["rank"] = i

    # Summary stats
    total = len(top)
    winners = [s for s in top if s["fwdReturnPct"] > 0]
    losers  = [s for s in top if s["fwdReturnPct"] < 0]
    avg_ret = round(sum(s["fwdReturnPct"] for s in top) / total, 2) if total else 0
    median_ret = 0
    if top:
        srt = sorted(s["fwdReturnPct"] for s in top)
        mid = len(srt) // 2
        median_ret = srt[mid] if len(srt) % 2 else round((srt[mid - 1] + srt[mid]) / 2, 2)
    avg_winner = round(sum(s["fwdReturnPct"] for s in winners) / len(winners), 2) if winners else 0
    avg_loser  = round(sum(s["fwdReturnPct"] for s in losers) / len(losers), 2) if losers else 0
    avg_max_gain = round(sum(s["maxGainPct"] for s in top) / total, 2) if total else 0
    avg_max_dd   = round(sum(s["maxDrawdownPct"] for s in top) / total, 2) if total else 0

    # Sector breakdown
    sec_map: dict[str, list] = {}
    for s in top:
        sec_map.setdefault(s["sector"], []).append(s)
    sec_breakdown = []
    for sec, items in sorted(sec_map.items(), key=lambda x: -len(x[1])):
        ar = round(sum(i["fwdReturnPct"] for i in items) / len(items), 2) if items else 0
        w = sum(1 for i in items if i["fwdReturnPct"] > 0)
        sec_breakdown.append({
            "sector": sec, "count": len(items), "avgReturn": ar,
            "winRate": round(w / len(items) * 100) if items else 0,
        })

    return {
        "scanDate":         scan_date,
        "endDate":          end_date_str or None,
        "generatedAt":      datetime.now().isoformat(timespec="seconds"),
        "sortBy":           sort_by,
        "topN":             top_n,
        "totalScanned":     len(universe),
        "totalComputed":    len(scored),
        "leaders":          top,
        "niftyReturnPct":   nifty_return_pct,
        "summary": {
            "total":        total,
            "winners":      len(winners),
            "losers":       len(losers),
            "winRate":      round(len(winners) / total * 100) if total else 0,
            "avgReturn":    avg_ret,
            "medianReturn": median_ret,
            "avgWinner":    avg_winner,
            "avgLoser":     avg_loser,
            "avgMaxGain":   avg_max_gain,
            "avgMaxDD":     avg_max_dd,
        },
        "sectorBreakdown":  sec_breakdown,
    }


