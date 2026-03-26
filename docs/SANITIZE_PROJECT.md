# Sanitize Project

Use this helper to clean generated artifacts and verify core app flows still run.

## What it does

- Deletes generated Java bytecode in `src/*.class` and `bin/*.class`
- Optionally removes stale runtime folders in `output/` (`scan_*`, `system_run_*`)
- Recreates `output/` and `cache/` directories if missing
- Compiles Java sources in `src/`
- Runs smoke tests for scan and backtest modes (sample provider)

## Run

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
bash scripts/sanitize_project.sh
```

## Keep all output folders

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
bash scripts/sanitize_project.sh --no-prune-output
```

