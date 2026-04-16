# Web App Runbook — SETUPS Web Console

## Overview

The SETUPS Web Console is a **FastAPI** application that provides a browser-based UI to run scans, backtests, analyze stocks, and view live reports — without using the command line.

- **Backend**: FastAPI + uvicorn (`apps/web/api/main.py`)
- **Frontend**: Static HTML (`apps/web/ui/index.html`)
- **Default URL**: `http://localhost:8000`
- **API Docs**: `http://localhost:8000/docs`

---

## Prerequisites

Ensure the Python virtual environment is set up with the required dependencies:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS

# Create venv (first time only)
python3 -m venv .venv

# Activate venv
source .venv/bin/activate

# Install web dependencies (first time only)
pip install -r requirements-web.txt
```

---

## Starting the Web App

### Option 1 — One-command script (recommended)

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
./run_web.sh
```

This will:
1. Activate the `.venv` automatically
2. Start the FastAPI server on port 8000
3. Auto-open `http://localhost:8000` in your default browser

### Option 2 — Manual uvicorn start

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
source .venv/bin/activate

PYTHONPATH="$(pwd)/apps/python/lib" \
uvicorn apps.web.api.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level info
```

### Option 3 — Custom port

```bash
./run_web.sh --port 8080
```

### Option 4 — Development mode (hot-reload)

```bash
./run_web.sh --reload
```

### Option 5 — Start without auto-opening browser

```bash
./run_web.sh --no-open
```

---

## Stopping the Web App

Press **`Ctrl+C`** in the terminal where the server is running.

To force-kill if it is stuck:

```bash
# Find and kill the process using port 8000
lsof -ti tcp:8000 | xargs kill -9
```

---

## Features Available in the UI

| Feature | Description |
|---|---|
| ▶ **Run Scan** | Trigger India + US scan (VCP, Range, MR, Breakout Pullback) |
| 🔁 **Run Backtest** | Run a 3-year strategy backtest |
| 🔍 **Stock Analyzer** | Analyze any ticker — auto or live mode |
| 📊 **Performance Tracker** | Track open trades with MF Holdings overlay |
| 🏦 **MF / Institutional Data** | Screener.in + yfinance mutual fund data |
| 📈 **Live Report Links** | Links to the latest HTML reports in `output/` |

---

## Checking Server Status

```bash
# Confirm server is running
curl -s http://localhost:8000/ | head -5

# Open interactive API docs in browser
open http://localhost:8000/docs
```

---

## Common Errors & Fixes

### Port already in use

```
ERROR: [Errno 48] error while attempting to bind on address ('0.0.0.0', 8000): address already in use
```

**Fix:**
```bash
lsof -ti tcp:8000 | xargs kill -9
./run_web.sh
```

Or use a different port:
```bash
./run_web.sh --port 8080
```

---

### Module not found / ImportError

```
ModuleNotFoundError: No module named 'fastapi'
```

**Fix:**
```bash
source .venv/bin/activate
pip install -r requirements-web.txt
```

---

### `uvicorn` command not found

```
zsh: command not found: uvicorn
```

**Fix:**
```bash
source .venv/bin/activate
pip install "uvicorn[standard]"
```

---

### Blank page or 404 on browser

Make sure the UI file exists:
```bash
ls apps/web/ui/index.html
```

If missing, restore from git:
```bash
git checkout apps/web/ui/index.html
```

---

## File Structure

```
apps/
└── web/
    ├── api/
    │   └── main.py          ← FastAPI app (all routes)
    └── ui/
        ├── index.html       ← Main web console UI
        └── trade_board.html ← Trade board UI

run_web.sh                   ← One-command start script
requirements-web.txt         ← Python dependencies (fastapi, uvicorn, yfinance)
```

---

## API Endpoints (Quick Reference)

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serves the web UI (`index.html`) |
| `GET` | `/docs` | Interactive API docs (Swagger UI) |
| `POST` | `/api/scan` | Submit a scan job |
| `POST` | `/api/backtest` | Submit a backtest job |
| `GET` | `/api/jobs/{job_id}` | Poll job status and logs |
| `GET` | `/api/reports` | List available HTML reports |
| `GET` | `/api/analyze` | Analyze a stock ticker |
| `GET` | `/api/performance` | Get performance tracker data |
| `GET` | `/api/mutual-funds/{symbol}` | MF holdings for a ticker |

Full interactive docs always available at: **`http://localhost:8000/docs`**

---

## Related Runbooks

- Full pipeline → `docs/runbooks/DAILY_RUNBOOK.md`
- Backtest guide → `docs/runbooks/BACKTEST_RUNBOOK.md`
- Troubleshooting → `docs/runbooks/TROUBLESHOOTING.md`
- Getting started → `docs/GETTING_STARTED.md`

