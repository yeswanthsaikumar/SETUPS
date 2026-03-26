#!/usr/bin/env python3
"""
run_trade_plan_assistant.py
───────────────────────────
CLI wrapper for the trade plan assistant – prints a natural-language scan
summary from the latest scan output files.

Usage:
    python apps/python/cli/run_trade_plan_assistant.py
    python apps/python/cli/run_trade_plan_assistant.py --market india --timeframe daily --setups full
    python apps/python/cli/run_trade_plan_assistant.py --market india --timeframe daily --setups full --format json
    python apps/python/cli/run_trade_plan_assistant.py --top-n 10 --format text
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "python" / "lib"))

from trade_plan_assistant import brief_as_json, brief_as_text, build_scan_brief


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Summarize latest trade plans and pivot distance in natural-language form")
    p.add_argument("--market", choices=["india", "us"], default="india")
    p.add_argument("--timeframe", choices=["daily", "weekly"], default="daily")
    p.add_argument("--setups", choices=["full", "both", "vcp", "range_expansion", "mean_reversion", "all"], default="full")
    p.add_argument("--top-n", type=int, default=12)
    p.add_argument("--output-dir", default=str(ROOT / "output"))
    p.add_argument("--format", choices=["text", "json"], default="text")
    args = p.parse_args()

    if args.top_n <= 0:
        p.error("--top-n must be > 0")

    if args.setups == "all":
        args.setups = "full"

    args.output_dir = Path(args.output_dir)
    return args


def main() -> None:
    args = parse_args()

    summary = build_scan_brief(
        output_dir=args.output_dir,
        market=args.market,
        timeframe=args.timeframe,
        setups=args.setups,
        top_n=args.top_n,
    )

    if args.format == "json":
        print(json.dumps(brief_as_json(summary), indent=2))
    else:
        print(brief_as_text(summary), end="")


if __name__ == "__main__":
    main()

