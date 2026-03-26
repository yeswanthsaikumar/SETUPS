from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

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
WEB_JOBS_DIR = OUTPUT_DIR / "web_jobs"

sys.path.insert(0, str(PY_LIB_DIR))
from trade_plan_assistant import brief_as_json, build_scan_brief
from stock_analyzer import analyze_stock

RUN_VCP_SYSTEM = CLI_DIR / "run_vcp_system.py"
RUN_BACKTEST = CLI_DIR / "run_backtest.py"


class ScanJobRequest(BaseModel):
    markets: list[Literal["india", "us"]] = Field(default_factory=lambda: ["india", "us"])
    timeframes: list[Literal["daily", "weekly"]] = Field(default_factory=lambda: ["daily", "weekly"])
    setups: Literal["full", "both", "vcp", "range_expansion", "mean_reversion", "breakout_pullback", "all"] = "full"
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
    setups: Literal["full", "both", "vcp", "range_expansion", "mean_reversion", "breakout_pullback", "all"] = "full",
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
    setups: Literal["full", "both", "vcp", "range_expansion", "mean_reversion", "breakout_pullback", "all"] = "full",
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

