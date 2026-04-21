"""Unit tests for the custom alert rule evaluator.

The evaluator is pure (no IO, no cooldown) so we can feed it synthetic
OHLCV rows and assert on the fired alert dict.
"""
from __future__ import annotations

import pytest

from apps.python.lib.breakout_alert_engine import (
    evaluate_custom_rule,
    _resample_daily_to_higher,
    _normalize_timeframe,
)

pytestmark = pytest.mark.unit


def _mk(date, close, volume=1000, open_=None, high=None, low=None):
    o = open_ if open_ is not None else close
    h = high if high is not None else close
    l = low if low is not None else close
    return {"date": date, "datetime": date, "open": o, "high": h,
            "low": l, "close": close, "volume": volume}


# ─── Metric: price / operators ──────────────────────────────────────────────

def test_price_gt_absolute_fires():
    rows = [_mk("2026-04-18", 95), _mk("2026-04-21", 101)]
    rule = {"id": "r1", "name": "px>100", "enabled": True, "timeframe": "1d",
            "metric": "price", "operator": ">", "threshold": 100,
            "reference": "absolute"}
    out = evaluate_custom_rule(rule, rows)
    assert out is not None
    assert out["value"] == 101
    assert out["reference_value"] == 100
    assert out["rule_id"] == "r1"


def test_price_gt_absolute_does_not_fire():
    rows = [_mk("2026-04-18", 95), _mk("2026-04-21", 99)]
    rule = {"id": "r1", "enabled": True, "timeframe": "1d", "metric": "price",
            "operator": ">", "threshold": 100, "reference": "absolute"}
    assert evaluate_custom_rule(rule, rows) is None


def test_price_crosses_above_prev_close():
    # prev bar close 100, latest close 102 with close_prev_bar = 99 → crosses
    rows = [_mk("2026-04-16", 99), _mk("2026-04-17", 100), _mk("2026-04-21", 102)]
    rule = {"id": "x", "enabled": True, "timeframe": "1d", "metric": "price",
            "operator": "crosses_above", "threshold": 100, "reference": "absolute"}
    # prev_lhs is rows[-2] close = 100, rhs = 100 → 100 <= 100 AND 102 > 100 → fires
    assert evaluate_custom_rule(rule, rows) is not None


def test_price_crosses_above_requires_prev_below():
    # prev bar already above threshold → no cross
    rows = [_mk("2026-04-16", 102), _mk("2026-04-17", 103), _mk("2026-04-21", 104)]
    rule = {"id": "x", "enabled": True, "timeframe": "1d", "metric": "price",
            "operator": "crosses_above", "threshold": 100, "reference": "absolute"}
    assert evaluate_custom_rule(rule, rows) is None


def test_disabled_rule_never_fires():
    rows = [_mk("a", 10), _mk("b", 1_000_000)]
    rule = {"id": "x", "enabled": False, "timeframe": "1d", "metric": "price",
            "operator": ">", "threshold": 1, "reference": "absolute"}
    assert evaluate_custom_rule(rule, rows) is None


# ─── Metric: volume / volume_ratio ──────────────────────────────────────────

def test_volume_ratio_vs_avg_fires():
    # 10 bars with vol=1000, latest vol=3000 → ratio 3.0 >= 2.5
    rows = [_mk(f"d{i}", 100, volume=1000) for i in range(10)]
    rows.append(_mk("d10", 101, volume=3000))
    rule = {"id": "v", "enabled": True, "timeframe": "15m",
            "metric": "volume_ratio", "operator": ">=", "threshold": 2.5,
            "reference": "absolute", "reference_bars": 10}
    out = evaluate_custom_rule(rule, rows)
    assert out is not None
    assert out["value"] == 3.0


def test_volume_ratio_below_threshold_noop():
    rows = [_mk(f"d{i}", 100, volume=1000) for i in range(10)]
    rows.append(_mk("d10", 101, volume=2000))
    rule = {"id": "v", "enabled": True, "timeframe": "15m",
            "metric": "volume_ratio", "operator": ">=", "threshold": 2.5,
            "reference": "absolute", "reference_bars": 10}
    assert evaluate_custom_rule(rule, rows) is None


def test_volume_gt_avg_reference():
    # Latest volume compared to avg-of-last-5 (=1000) must be > 2500
    rows = [_mk(f"d{i}", 100, volume=1000) for i in range(5)]
    rows.append(_mk("d5", 101, volume=3000))
    rule = {"id": "v", "enabled": True, "timeframe": "1d",
            "metric": "volume", "operator": ">", "threshold": 2.5,
            "reference": "avg", "reference_bars": 5}
    out = evaluate_custom_rule(rule, rows)
    # lhs = 3000, rhs = avg(1000)*1 = 1000 → 3000 > 1000 fires
    assert out is not None
    assert out["reference_value"] == 1000


# ─── Metric: price_pct_change ───────────────────────────────────────────────

def test_price_pct_change_gt_5pct():
    rows = [_mk("d1", 100), _mk("d2", 106)]
    rule = {"id": "p", "enabled": True, "timeframe": "1d",
            "metric": "price_pct_change", "operator": ">", "threshold": 5,
            "reference": "absolute"}
    out = evaluate_custom_rule(rule, rows)
    assert out is not None
    assert round(out["value"], 1) == 6.0


# ─── Reference: prev_high / prev_low / highest ──────────────────────────────

def test_price_gt_prev_high_fires():
    rows = [_mk("d1", 95, high=98), _mk("d2", 101, high=101)]
    rule = {"id": "h", "enabled": True, "timeframe": "1d", "metric": "price",
            "operator": ">", "reference": "prev_high", "threshold": 0}
    out = evaluate_custom_rule(rule, rows)
    assert out is not None
    assert out["reference_value"] == 98


def test_price_gt_highest_20_fires():
    rows = [_mk(f"d{i}", 100 + i, high=100 + i) for i in range(20)]  # highs 100..119
    rows.append(_mk("latest", 130, high=130))
    rule = {"id": "h", "enabled": True, "timeframe": "1d", "metric": "price",
            "operator": ">", "reference": "highest", "reference_bars": 20,
            "threshold": 0}
    out = evaluate_custom_rule(rule, rows)
    assert out is not None
    # Last 20 of prev_rows is the full 20 input rows → max high = 119
    assert out["reference_value"] == 119


# ─── Edge cases ─────────────────────────────────────────────────────────────

def test_empty_rows_returns_none():
    rule = {"id": "x", "enabled": True, "timeframe": "1d", "metric": "price",
            "operator": ">", "threshold": 1, "reference": "absolute"}
    assert evaluate_custom_rule(rule, []) is None
    assert evaluate_custom_rule(rule, [_mk("d1", 10)]) is None  # single bar


def test_unknown_operator_does_not_fire():
    rows = [_mk("d1", 100), _mk("d2", 200)]
    rule = {"id": "x", "enabled": True, "timeframe": "1d", "metric": "price",
            "operator": "~~~", "threshold": 50, "reference": "absolute"}
    assert evaluate_custom_rule(rule, rows) is None


# ─── Timeframe normalization + weekly resample ──────────────────────────────

def test_normalize_timeframe_aliases():
    assert _normalize_timeframe("1H") == "60m"
    assert _normalize_timeframe("1h") == "60m"
    assert _normalize_timeframe("1d") == "1d"
    assert _normalize_timeframe("") == "1d"
    assert _normalize_timeframe("unknown") == "1d"


def test_weekly_resample_from_daily():
    # 5 daily bars Mon–Fri in ISO week 2026-W17
    daily = [
        _mk("2026-04-20", 100, volume=1000, high=102, low=99),
        _mk("2026-04-21", 103, volume=1500, high=105, low=101),
        _mk("2026-04-22", 104, volume=2000, high=106, low=103),
        _mk("2026-04-23", 102, volume=1200, high=104, low=100),
        _mk("2026-04-24", 108, volume=3000, high=110, low=101),
    ]
    weekly = _resample_daily_to_higher(daily, "1wk")
    assert len(weekly) == 1
    w = weekly[0]
    assert w["open"] == 100          # first bar's open
    assert w["high"] == 110           # max of highs
    assert w["low"] == 99             # min of lows
    assert w["close"] == 108          # last bar's close
    assert w["volume"] == 8700        # sum of vols

