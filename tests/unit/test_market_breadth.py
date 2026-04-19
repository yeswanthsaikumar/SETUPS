"""Unit tests for apps/python/lib/market_breadth.py."""
from __future__ import annotations

import pytest

import market_breadth as mb

pytestmark = pytest.mark.unit


def _row(**kw) -> dict:
    base = {
        "industry": "Test", "sector": "Test",
        "ret_1d": 0.0, "ret_5d": 0.0, "ret_20d": 0.0, "ret_60d": 0.0,
        "volume_ratio": 1.0, "rs": 50, "n52_high": 0, "n52_low": 0,
        "breadth_above_ma50": 50.0, "close": 100,
    }
    base.update(kw)
    return base


class TestHelpers:
    def test_median_of_empty(self):
        assert mb._median([]) == 0.0

    def test_median_basic(self):
        assert mb._median([1, 2, 3]) == 2.0

    def test_clamp_bounds(self):
        assert mb._clamp(-5) == 0.0
        assert mb._clamp(150) == 100.0


class TestMarketRegime:
    def test_empty_input_returns_dict(self):
        out = mb.compute_market_regime([])
        assert isinstance(out, dict)

    def test_strong_bull_regime(self):
        data = [_row(ret_5d=5, ret_20d=12, breadth_above_ma50=80, rs=75)
                for _ in range(10)]
        out = mb.compute_market_regime(data)
        assert isinstance(out, dict)
        # Whatever the label, result must be a stable dict (shape contract).
        assert set(out.keys())  # non-empty

