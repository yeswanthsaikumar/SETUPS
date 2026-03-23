# SETUPS Web App

Web wrapper for your existing scan/backtest engine with:

- REST APIs to start jobs and inspect status
- Browser UI dashboard to run scans/backtests
- Docker packaging for local + online hosting

## Architecture

- Strategy engine remains unchanged in existing Java + Python CLI pipeline.
- `apps/web/api/main.py` asynchronously runs:
  - `apps/python/cli/run_vcp_system.py`
  - `apps/python/cli/run_backtest.py`
- UI (`apps/web/ui/index.html`) calls API and links to generated reports under `/reports`.

## Project Files

- `apps/web/api/main.py` - FastAPI backend
- `apps/web/ui/index.html` - Web dashboard
- `apps/web/scripts/smoke_test.py` - API smoke test
- `requirements-web.txt` - Web dependency list
- `Dockerfile` - Container build
- `docker-compose.yml` - Local container orchestration

## API Endpoints

- `GET /api/health`
- `POST /api/jobs/scan`
- `POST /api/jobs/backtest`
- `GET /api/jobs`
- `GET /api/jobs/{jobId}`
- `GET /api/jobs/{jobId}/log`
- `GET /api/stock/analyze?symbol=...&market=india|us&timeframe=daily|weekly&setups=full|both|vcp|range_expansion|mean_reversion|all&source=auto|output|live`
- `GET /api/outputs/scan/latest`
- `GET /api/outputs/scan/manifests`
- `GET /api/outputs/backtest/latest?market=india|us&timeframe=daily|weekly`
- `GET /api/assistant/scan-brief?market=india|us&timeframe=daily|weekly&setups=full|both|vcp|range_expansion|mean_reversion|all&top_n=12`
- `GET /` (UI)
- `GET /reports/*` (generated outputs from `output/`)

## Quick Start (Local, Recommended)

Use a virtual environment to avoid system Python package restrictions.

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-web.txt
uvicorn apps.web.api.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`

## Smoke Test

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
source .venv/bin/activate
python apps/web/scripts/smoke_test.py
```

## API Examples

Start scan job:

```bash
curl -X POST http://localhost:8000/api/jobs/scan \
  -H "Content-Type: application/json" \
  -d '{
	"markets": ["india", "us"],
	"timeframes": ["daily", "weekly"],
	"setups": "full",
	"daily_lookback": 252,
	"weekly_lookback": 104,
	"workers": 4,
	"batch": 25,
	"skip_us_refresh": true
  }'
```

Get LLM-style trade-plan brief:

```bash
curl "http://localhost:8000/api/assistant/scan-brief?market=india&timeframe=daily&setups=full&top_n=5"
```

Analyze a single stock:

```bash
# auto = use latest outputs first, then rerun existing logic if needed
curl "http://localhost:8000/api/stock/analyze?symbol=AAPL&market=us&timeframe=daily&setups=full&source=auto"

# force live = rerun existing scanner logic for just this symbol
curl "http://localhost:8000/api/stock/analyze?symbol=RELIANCE.NS&market=india&timeframe=daily&setups=full&source=live"
```

In the web UI Stock Analyzer, you can now also choose **compare output vs live** to fetch both sources side by side and inspect differences in:

- status / verdict
- setup and rating
- entry / stop / target values
- provenance (saved output vs fresh live logic)

Start backtest job:

```bash
curl -X POST http://localhost:8000/api/jobs/backtest \
  -H "Content-Type: application/json" \
  -d '{
	"market": "india",
	"timeframe": "daily",
	"setups": "both",
	"workers": 4,
	"batch": 20
  }'
```

Check jobs:

```bash
curl http://localhost:8000/api/jobs
```

## Docker Usage

### Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin) installed and running.
- Run commands from project root: `/Users/yeshwantha/IdeaProjects/SETUPS`.

### Build Image

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
docker build -t setups-web .
```

### Run Container (direct `docker run`)

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
docker run --name setups-web --rm -p 8000:8000 \
  -v "$(pwd)/output:/app/output" \
  -v "$(pwd)/cache:/app/cache" \
  setups-web
```

### Verify Service

```bash
curl http://localhost:8000/api/health
```

Open `http://localhost:8000` for UI.

### Stop Service

- If running in foreground: press `Ctrl+C`.
- If running in detached mode: `docker stop setups-web`.

## Docker Compose

### Start

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
docker compose up --build
```

### Start in background

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
docker compose up --build -d
```

### Check logs

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
docker compose logs -f
```

### Stop and remove containers

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
docker compose down
```

## Online Hosting Notes

- Container expects writable `/app/output` and `/app/cache`.
- For production, use persistent volumes so reports/logs survive restarts.
- For public deployment, add auth/rate-limits in front of job-start endpoints.
- Health check endpoint for platform probes: `GET /api/health`.
- Recommended container port: `8000`.
- Keep `output/` and `cache/` on persistent storage; job history and reports are written there.

## Deploy on Render

### Option A: Blueprint (recommended)

This repo now includes `render.yaml` at project root.

1. Push code to GitHub/GitLab.
2. In Render, choose **New +** -> **Blueprint**.
3. Select your repo and apply the blueprint.
4. Render will build from `Dockerfile` and run health check on `/api/health`.

### Option B: Manual Web Service

1. In Render, create **Web Service** from your repo.
2. Environment: **Docker**.
3. Leave build/start commands empty (uses `Dockerfile`).
4. Set Health Check Path: `/api/health`.
5. Create service.

### Render persistence notes

- Current `render.yaml` mounts a disk at `/app/output` to persist reports/logs.
- `cache/` remains ephemeral unless you also persist it in your own custom setup.
- Your app uses Render-provided `PORT` automatically via Docker `CMD`.

### Verify after deploy

```bash
curl https://<your-render-service>.onrender.com/api/health
```

Open:

- `https://<your-render-service>.onrender.com/` (UI)
- `https://<your-render-service>.onrender.com/api/jobs` (jobs)

## Output and Logs

- Job logs: `output/web_jobs/`
- Scan summary (latest): `output/system_latest_summary.json`
- Reports are available through `/reports/*` URLs.

Example paths after a run:

- `/reports/system_latest_summary.json`
- `/reports/backtest_india_daily_LATEST.html`
- `/reports/watchlist_india_daily_LATEST.html`

