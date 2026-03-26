from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils import to_float as _to_float

ALLOWED_SETUPS = {"VCP", "RANGE_EXPANSION", "MEAN_REVERSION"}


@dataclass
class BriefSummary:
    label: str
    file_used: str
    total_rows: int
    setup_counts: dict[str, int]
    lines: list[str]



def _load_json_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    out: list[dict] = []
    for item in payload:
        if isinstance(item, dict):
            out.append(item)
    return out


def _candidate_latest_files(output_dir: Path, market: str, timeframe: str, setups: str) -> list[Path]:
    label = f"{market}_{timeframe}"
    candidates: list[Path] = []

    if setups == "full":
        candidates.append(output_dir / f"vcp_hits_{label}_full_LATEST.json")
    elif setups == "both":
        candidates.append(output_dir / f"vcp_hits_{label}_LATEST.json")
    else:
        candidates.append(output_dir / f"vcp_hits_{label}_{setups}_LATEST.json")

    # Compatibility fallbacks
    candidates.append(output_dir / f"vcp_hits_{label}_all_LATEST.json")
    candidates.append(output_dir / f"vcp_hits_{label}_full_LATEST.json")
    candidates.append(output_dir / f"vcp_hits_{label}_LATEST.json")

    # De-duplicate while preserving order
    seen = set()
    unique: list[Path] = []
    for c in candidates:
        key = str(c)
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    return unique


def load_latest_scan_rows(output_dir: Path, market: str, timeframe: str, setups: str) -> tuple[list[dict], Path | None]:
    for candidate in _candidate_latest_files(output_dir, market, timeframe, setups):
        rows = _load_json_rows(candidate)
        if rows:
            return rows, candidate
    return [], None


def _setup_of(row: dict) -> str:
    setup = str(row.get("setup", row.get("setupType", "UNKNOWN"))).upper().strip()
    return setup


def _distance_to_pivot_pct(row: dict) -> float:
    # Prefer explicit dist% field from scanner.
    dist = _to_float(row.get("dist%"), default=float("nan"))
    if dist == dist:  # NaN check
        return dist

    close = _to_float(row.get("close"), 0.0)
    pivot = _to_float(row.get("pivot"), 0.0)
    if close <= 0 or pivot <= 0:
        return 0.0
    return ((pivot - close) / pivot) * 100.0


def _risk_reward_hint(row: dict) -> str:
    entry = _to_float(row.get("entry"), 0.0)
    stop = _to_float(row.get("sl"), 0.0)
    t1 = _to_float(row.get("T1"), 0.0)
    if entry <= 0 or stop <= 0 or t1 <= 0 or entry <= stop:
        return "R:R n/a"
    risk = entry - stop
    rr = max(0.0, (t1 - entry) / risk)
    return f"R:R@T1 {rr:.2f}"


def _row_line(row: dict) -> str:
    symbol = str(row.get("symbol", "?")).upper()
    setup = _setup_of(row)
    rating = str(row.get("rating", "N/A")).upper()
    score = _to_float(row.get("score"), 0.0)
    close = _to_float(row.get("close"), 0.0)
    pivot = _to_float(row.get("pivot"), 0.0)
    entry = _to_float(row.get("entry"), 0.0)
    stop = _to_float(row.get("sl"), 0.0)
    t1 = _to_float(row.get("T1"), 0.0)
    dist = _distance_to_pivot_pct(row)

    if dist > 0:
        pivot_state = f"{abs(dist):.2f}% below pivot"
    elif dist < 0:
        pivot_state = f"{abs(dist):.2f}% above pivot"
    else:
        pivot_state = "at pivot"

    return (
        f"{symbol} [{setup}] rating {rating}, score {score:.1f}: "
        f"close {close:.2f}, pivot {pivot:.2f} ({pivot_state}), "
        f"entry {entry:.2f}, stop {stop:.2f}, T1 {t1:.2f}, {_risk_reward_hint(row)}"
    )


def _sort_rows(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: _to_float(r.get("score"), 0.0), reverse=True)


def build_scan_brief(
    output_dir: Path,
    market: str,
    timeframe: str,
    setups: str = "full",
    top_n: int = 12,
) -> BriefSummary:
    market = market.strip().lower()
    timeframe = timeframe.strip().lower()
    setups = setups.strip().lower()

    rows, source_path = load_latest_scan_rows(output_dir, market, timeframe, setups)
    if not rows:
        label = f"{market}_{timeframe}_{setups}"
        return BriefSummary(
            label=label,
            file_used="",
            total_rows=0,
            setup_counts={},
            lines=[f"No scan rows found for {label}."],
        )

    label = f"{market}_{timeframe}_{setups}"
    setup_counts: dict[str, int] = {}
    filtered: list[dict] = []
    for row in rows:
        setup = _setup_of(row)
        setup_counts[setup] = setup_counts.get(setup, 0) + 1
        if setup in ALLOWED_SETUPS:
            filtered.append(row)

    ranked = _sort_rows(filtered)[: max(1, top_n)]

    header = (
        f"Summary for {label}: {len(rows)} total signals. "
        f"Setup mix: "
        + ", ".join(f"{k}:{v}" for k, v in sorted(setup_counts.items(), key=lambda kv: (-kv[1], kv[0])))
    )
    lines = [header]
    for row in ranked:
        lines.append("- " + _row_line(row))

    return BriefSummary(
        label=label,
        file_used=str(source_path.resolve()) if source_path else "",
        total_rows=len(rows),
        setup_counts=setup_counts,
        lines=lines,
    )


def brief_as_text(summary: BriefSummary) -> str:
    return "\n".join(summary.lines) + "\n"


def brief_as_json(summary: BriefSummary) -> dict[str, Any]:
    return {
        "label": summary.label,
        "fileUsed": summary.file_used,
        "totalRows": summary.total_rows,
        "setupCounts": summary.setup_counts,
        "lines": summary.lines,
    }

