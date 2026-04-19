"""Unit tests for apps/python/lib/setup_detector.py internal math.

We test pure-function indicators (SMA/EMA/RSI/ATR/Bollinger) because a
regression in these silently miscalibrates every scanner.  The high-level
detect_* functions are covered at the API layer via /api/jobs/scan.
"""
from __future__ import annotations

import pytest

import setup_detector as sd

pytestmark = pytest.mark.unit


class TestMovingAverages:
    def test_sma_basic(self):
        assert sd._sma([1, 2, 3, 4, 5], 5) == 3.0

    def test_sma_period_gt_len_returns_zero(self):
        assert sd._sma([1, 2], 5) == 0.0

    def test_ema_converges(self):
        # Flat series → EMA equals the constant.
        out = sd._ema([10, 10, 10, 10, 10, 10, 10, 10, 10, 10], 3)
        assert out == pytest.approx(10.0, abs=1e-9)

    def test_ema_monotonic_on_uptrend(self):
        vals = list(range(1, 30))
        out = sd._ema(vals, 5)
        assert out > sd._sma(vals[-5:], 5) * 0.8  # EMA tracks recent prices


class TestRsi:
    def test_all_gains_near_100(self):
        closes = list(range(100, 130))   # pure uptrend
        assert sd._rsi(closes) > 70

    def test_all_losses_near_0(self):
        closes = list(range(130, 100, -1))
        assert sd._rsi(closes) < 30


class TestBollinger:
    def test_flat_series_zero_band_width(self):
        lo, mid, hi = sd._bollinger([100] * 25, period=20)
        assert mid == pytest.approx(100.0)
        assert hi == pytest.approx(100.0)
        assert lo == pytest.approx(100.0)


class TestAtr:
    def test_positive_on_varying_bars(self):
        bars = [{"open": 100 + i, "high": 101 + i, "low": 99 + i,
                 "close": 100 + i, "volume": 1000}
                for i in range(20)]
        atr = sd._atr(bars, period=14)
        assert atr > 0


class TestRating:
    def test_rating_monotonic(self):
        assert sd._rating_from_score(95) in ("A+", "A")
        assert sd._rating_from_score(5) in ("C", "D", "F")

