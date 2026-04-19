"""Unit tests for apps/python/lib/utils.py pure helpers."""
from __future__ import annotations

import pytest

import utils

pytestmark = pytest.mark.unit


class TestToFloat:
    @pytest.mark.parametrize("raw,expected", [
        ("12.5", 12.5),
        (7, 7.0),
        (None, 0.0),
        ("abc", 0.0),
        ("", 0.0),
    ])
    def test_coercions(self, raw, expected):
        assert utils.to_float(raw) == expected

    def test_default_override(self):
        assert utils.to_float("x", default=-1.0) == -1.0


class TestSafeReturn:
    def test_positive_return(self):
        # safe_return returns a fraction ((last-first)/first), not a percent.
        assert utils.safe_return([100, 105, 110], bars=2) == pytest.approx(0.10, abs=1e-6)

    def test_zero_when_not_enough_bars(self):
        assert utils.safe_return([100], bars=5) == 0.0

    def test_handles_zero_base(self):
        assert utils.safe_return([0, 10], bars=1) == 0.0


class TestClamp:
    def test_within_range(self):
        assert utils.clamp(50) == 50.0

    def test_below(self):
        assert utils.clamp(-5, low=0, high=100) == 0.0

    def test_above(self):
        assert utils.clamp(150, low=0, high=100) == 100.0


class TestMean:
    def test_basic(self):
        assert utils.mean([1, 2, 3, 4]) == 2.5

    def test_empty_returns_zero(self):
        assert utils.mean([]) == 0.0


class TestChunks:
    def test_even_split(self):
        assert list(utils.chunks([1, 2, 3, 4], 2)) == [[1, 2], [3, 4]]

    def test_uneven_split(self):
        assert list(utils.chunks([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]

