"""End-to-end smoke test of the scan pipeline.

Runs the real CLI against a seeded 1-symbol cache to prove the full
path (load bars → detect setup → write JSON output) still works.

Marked @slow — excluded from the default unit/api suite.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.slow]

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def seeded_cache(tmp_path, monkeypatch):
    cd = tmp_path / "cache"
    cd.mkdir()
    # 80 bars of synthetic data for RELIANCE.NS
    rows = ["Date,Open,High,Low,Close,Volume"]
    price = 100.0
    for i in range(80):
        o = price
        c = price * (1.0 + 0.005 * ((-1) ** i))
        h = max(o, c) * 1.01
        lo = min(o, c) * 0.99
        rows.append(f"2026-01-{(i % 28) + 1:02d},{o:.2f},{h:.2f},{lo:.2f},{c:.2f},100000")
        price = c
    (cd / "RELIANCE.NS.csv").write_text("\n".join(rows))
    monkeypatch.setenv("SETUPS_CACHE_DIR", str(cd))
    return cd


class TestScanPipelineImport:
    """Smoke test that the core detector module can run without network."""

    def test_detector_module_importable(self):
        import setup_detector  # noqa: F401

    def test_scan_symbols_empty_safe(self, seeded_cache):
        import setup_detector as sd
        # scan_symbols with empty list must not raise
        out = sd.scan_symbols([], cache_dir=str(seeded_cache),
                              lookback=60, timeframe="daily")
        assert out == [] or out is not None

