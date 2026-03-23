# Trade Plan Assistant Guide

## What It Does

The Trade Plan Assistant gives an LLM-style natural-language summary from your latest scan outputs.

This assistant is intentionally **output-based** for speed. For **single-symbol live analysis using the existing scanner logic**, use `GET /api/stock/analyze` with `source=auto|output|live` from the web API.

It summarizes:

- setup type (`VCP`, `RANGE_EXPANSION`, `MEAN_REVERSION`)
- quality (`rating`, `score`)
- trade plan (`entry`, `sl`, `T1`)
- how far price is from pivot (`dist%` or derived from close/pivot)
- quick risk/reward hint at T1

## Inputs

It reads `*_LATEST.json` files in `output/`, prioritizing setup-mode specific files:

- `vcp_hits_{market}_{timeframe}_full_LATEST.json`
- fallback to legacy names if needed

## CLI Usage

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_trade_plan_assistant.py --market india --timeframe daily --setups full --top-n 12
```

JSON format:

```bash
python3 apps/python/cli/run_trade_plan_assistant.py --market india --timeframe daily --setups full --top-n 12 --format json
```

## API Usage

Endpoint:

- `GET /api/assistant/scan-brief`

Query params:

- `market`: `india|us`
- `timeframe`: `daily|weekly`
- `setups`: `full|both|vcp|range_expansion|mean_reversion|all`
- `top_n`: integer > 0

Example:

```bash
curl "http://localhost:8000/api/assistant/scan-brief?market=india&timeframe=daily&setups=full&top_n=5"
```

## Related: Live Single-Stock Analyzer

If you want the system to analyze a symbol by rerunning the existing logic instead of only reading saved `output/*_LATEST.json`, use:

```bash
# auto: latest outputs first, then live rule execution if missing
curl "http://localhost:8000/api/stock/analyze?symbol=AAPL&market=us&timeframe=daily&setups=full&source=auto"

# live: always rerun the existing single-symbol scan logic
curl "http://localhost:8000/api/stock/analyze?symbol=RELIANCE.NS&market=india&timeframe=daily&setups=full&source=live"

# output: only use latest saved outputs
curl "http://localhost:8000/api/stock/analyze?symbol=HINDCOPPER.NS&market=india&timeframe=daily&setups=full&source=output"
```

`source` modes:

- `output` — fastest; reads latest saved scan artifacts only
- `live` — reruns the existing scan logic for the requested symbol
- `auto` — tries latest outputs first, then falls back to live analysis when needed

## Notes

- This assistant is deterministic and formula-based (not generative AI model inference).
- It is designed for fast operational summaries from existing scanner outputs.
- If no rows are found, it returns a friendly "No scan rows found" message.
- The single-stock analyzer shares the same deterministic rule engine, but can now run in live mode as well.

