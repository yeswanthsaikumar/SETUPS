#!/usr/bin/env python3
"""Orchestrate taxonomy refresh end-to-end with safe defaults.

Runs:
1) scripts/build_nse_industry_taxonomy.py
2) scripts/apply_themes.py
3) scripts/test_taxonomy_fixes.py (optional)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _run(cmd: list[str]) -> None:
    pretty = " ".join(cmd)
    print(f"\n→ {pretty}", flush=True)
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Force full NSE refetch")
    ap.add_argument("--workers", type=int, default=6, help="Fetch worker count")
    ap.add_argument(
        "--symbols",
        default="",
        help="Comma-separated symbols for partial rebuild (passed to fetch step)",
    )
    ap.add_argument("--skip-tests", action="store_true", help="Skip taxonomy validation tests")
    args = ap.parse_args()

    build_cmd = [sys.executable, str(SCRIPTS / "build_nse_industry_taxonomy.py"), "--workers", str(args.workers)]
    if args.force:
        build_cmd.append("--force")
    if args.symbols.strip():
        build_cmd.extend(["--symbols", args.symbols.strip()])
    _run(build_cmd)

    _run([sys.executable, str(SCRIPTS / "apply_themes.py")])

    if not args.skip_tests:
        _run([sys.executable, str(SCRIPTS / "test_taxonomy_fixes.py")])

    print("\nTaxonomy upgrade complete.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        print(f"\nStep failed with exit code {e.returncode}: {e.cmd}", file=sys.stderr)
        raise SystemExit(e.returncode)
