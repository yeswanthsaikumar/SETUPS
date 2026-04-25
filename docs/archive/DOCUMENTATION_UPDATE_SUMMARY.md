# Documentation Update Summary

**Date:** March 23, 2026
**Scope:** HLD + LLD + System Design + Runbooks + Entry Docs
**Status:** Completed

## What Was Updated

### 1) Core Entry Docs

- `docs/README.md`
- `docs/INDEX.md`
- `docs/GETTING_STARTED.md`

Changes:

- standardized on `--setups full` as canonical mode
- documented setup normalization (`all -> full`)
- updated command examples and output naming (`*_full_LATEST.*`)
- added clear navigation to architecture and runbooks

### 2) Architecture and Design Docs

- `docs/reference/HLD_SWING_TRADING_SYSTEM.md`
- `docs/reference/LLD_SWING_TRADING_SYSTEM.md`
- `docs/reference/SYSTEM_DESIGN.md`

Changes:

- aligned architecture to hybrid flow (Java VCP/RE + Python MR)
- documented current module contracts and mode routing
- refreshed rules/pipeline narrative for multi-setup engine
- clarified that live signal selection is formula-based (no ML)

### 3) Operational Runbooks

- `docs/runbooks/DAILY_RUNBOOK.md` (rewritten)
- `docs/runbooks/UNIFIED_FULL_MODE_RUNBOOK.md` (new)
- `docs/runbooks/TROUBLESHOOTING.md` (new)

Changes:

- daily operational sequence centered on full mode
- explicit verification checks and artifact expectations
- fallback execution path when orchestrator compile fails
- troubleshooting playbooks for compile, zero-hit, stale output, and runtime issues

## Canonical Runtime Contract (Documented)

- orchestrator: `apps/python/cli/run_vcp_system.py`
- grouped scanner: `apps/python/cli/run_full_us_scan.py`
- mean reversion detector: `apps/python/lib/mean_reversion_detector.py`
- Java core: `src/*.java`

## Output Contract (Documented)

- combined full outputs: `vcp_hits_*_full_LATEST.*` and companion artifacts
- setup split latest files in full mode:
  - `_vcp_`
  - `_range_expansion_`
  - `_mean_reversion_`
- system summary:
  - `output/system_latest_summary.md`
  - `output/system_latest_summary.json`

## Notes

- docs now reflect current full-mode behavior and command surface
- runbooks now include direct scanner continuity commands for operational resilience
