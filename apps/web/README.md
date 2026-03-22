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
- `GET /api/outputs/scan/latest`
- `GET /api/outputs/scan/manifests`
- `GET /api/outputs/backtest/latest?market=india|us&timeframe=daily|weekly`
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
	"setups": "both",
	"daily_lookback": 252,
	"weekly_lookback": 104,
	"workers": 4,
	"batch": 25,
	"skip_us_refresh": true
  }'
```

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

## Docker Run

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
docker build -t setups-web .
docker run --rm -p 8000:8000 \
  -v "$(pwd)/output:/app/output" \
  -v "$(pwd)/cache:/app/cache" \
  setups-web
```

Open `http://localhost:8000`

## Docker Compose

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
docker compose up --build
```

## Online Hosting Notes

- Container expects writable `/app/output` and `/app/cache`.
- For production, use persistent volumes so reports/logs survive restarts.
- For public deployment, add auth/rate-limits in front of job-start endpoints.
- Health check endpoint for platform probes: `GET /api/health`.

## Output and Logs

- Job logs: `output/web_jobs/`
- Scan summary (latest): `output/system_latest_summary.json`
- Reports are available through `/reports/*` URLs.

Example paths after a run:

- `/reports/system_latest_summary.json`
- `/reports/backtest_india_daily_LATEST.html`
- `/reports/watchlist_india_daily_LATEST.html`

