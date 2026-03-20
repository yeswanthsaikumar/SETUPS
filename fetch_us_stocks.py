#!/usr/bin/env python3
import runpy
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "apps" / "python" / "cli" / "fetch_us_stocks.py"
runpy.run_path(str(SCRIPT), run_name="__main__")

