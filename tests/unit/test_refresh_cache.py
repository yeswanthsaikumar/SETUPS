"""Unit tests for scripts/refresh_cache.py — the cache staleness + refresh
pipeline that caused the "yesterday-morning partial bar saved as the day's
row" bug.

Critical invariants covered
───────────────────────────
1. `_is_stale` flags
   • weekend / weekday gaps
   • a today-dated row written earlier today (pre-close intraday capture)
   • a today-dated row that is still being written (very fresh mtime) — NOT
     stale, to avoid refresh loops during market hours
   • a today-dated row written before 15:35 when now ≥ 15:35 (intraday leftover)
   • malformed / missing last_date

2. `_strip_intraday_today`
   • drops today's row pre-close
   • keeps today's row post-close (real finalized bar)
   • keeps every row when no "today" date present
   • handles empty input

3. `refresh_symbol` end-to-end (with fetcher mocked)
   • intraday row captured same-day morning is overwritten with finalized close
   • fetcher returning today's partial bar never gets written during session
   • `force=True` bypasses staleness gate
   • `dry_run=True` never writes
   • empty fetch result leaves file untouched
   • merge preserves older rows and updates the most recent one

4. Safety net: pre-existing today-intraday row survives a refresh that returned
   no new data for today — must be trimmed anyway.
"""
from __future__ import annotations

import datetime
import zoneinfo
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


# ── helpers ─────────────────────────────────────────────────────────────────

def _write_csv(path: Path, rows: list[tuple]) -> None:
    lines = ["date,open,high,low,close,volume"]
    for d, o, h, lo, c, v in rows:
        lines.append(f"{d},{o:.5f},{h:.5f},{lo:.5f},{c:.5f},{v}")
    path.write_text("\n".join(lines) + "\n")


def _set_mtime(path: Path, when: datetime.datetime) -> None:
    ts = when.timestamp()
    import os
    os.utime(path, (ts, ts))


@pytest.fixture
def rc(monkeypatch, tmp_path):
    """Import refresh_cache with CACHE_DIR redirected to a temp dir."""
    import refresh_cache as _rc
    monkeypatch.setattr(_rc, "CACHE_DIR", tmp_path, raising=False)
    return _rc


def _freeze_now(monkeypatch, rc_mod, when_ist: datetime.datetime):
    """Freeze `datetime.datetime.now(IST)` inside refresh_cache."""
    real_dt = rc_mod.datetime.datetime

    class _Frozen(real_dt):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            if tz is None:
                return when_ist.replace(tzinfo=None)
            return when_ist.astimezone(tz)

    monkeypatch.setattr(rc_mod.datetime, "datetime", _Frozen)


# ═══════════════════════════════════════════════════════════════════════════
#  _is_stale
# ═══════════════════════════════════════════════════════════════════════════

class TestIsStale:
    def test_empty_last_date_is_stale(self, rc):
        assert rc._is_stale("", None) is True

    def test_malformed_last_date_is_stale(self, rc):
        assert rc._is_stale("not-a-date", None) is True

    def test_weekend_only_gap_not_stale(self, rc, monkeypatch, tmp_path):
        # Saturday 10 AM IST; last bar Friday → 1 day gap but 0 business days
        _freeze_now(monkeypatch, rc,
                    datetime.datetime(2026, 4, 18, 10, 0, tzinfo=IST))
        p = tmp_path / "X.NS.csv"
        _write_csv(p, [("2026-04-17", 1, 2, 1, 2, 100)])
        _set_mtime(p, datetime.datetime(2026, 4, 17, 16, 0, tzinfo=IST))
        assert rc._is_stale("2026-04-17", p) is False

    def test_business_day_gap_is_stale(self, rc, monkeypatch, tmp_path):
        # Tue 10 AM IST; last bar is Friday → 1 business-day gap (Mon)
        _freeze_now(monkeypatch, rc,
                    datetime.datetime(2026, 4, 21, 10, 0, tzinfo=IST))
        p = tmp_path / "X.NS.csv"
        _write_csv(p, [("2026-04-17", 1, 2, 1, 2, 100)])
        assert rc._is_stale("2026-04-17", p) is True

    def test_today_intraday_captured_earlier_today_preclose_is_stale(
            self, rc, monkeypatch, tmp_path):
        """Bug repro: Tue 11 AM IST, file says last_date=Tue but mtime was
        10 AM (older session). Must be flagged so startup refresh picks it up.
        """
        now_ist = datetime.datetime(2026, 4, 21, 11, 0, tzinfo=IST)
        _freeze_now(monkeypatch, rc, now_ist)
        p = tmp_path / "X.NS.csv"
        _write_csv(p, [("2026-04-21", 1, 2, 1, 2, 100)])
        _set_mtime(p, datetime.datetime(2026, 4, 21, 10, 0, tzinfo=IST))
        assert rc._is_stale("2026-04-21", p) is True

    def test_today_row_just_written_is_not_stale(
            self, rc, monkeypatch, tmp_path):
        """Anti-loop guard: a file whose mtime is within the 5-minute window
        of now must NOT be flagged stale, or refresh would spin."""
        now_ist = datetime.datetime(2026, 4, 21, 11, 0, 0, tzinfo=IST)
        _freeze_now(monkeypatch, rc, now_ist)
        p = tmp_path / "X.NS.csv"
        _write_csv(p, [("2026-04-21", 1, 2, 1, 2, 100)])
        _set_mtime(p, now_ist - datetime.timedelta(seconds=30))
        assert rc._is_stale("2026-04-21", p) is False

    def test_today_row_written_preclose_then_now_postclose_is_stale(
            self, rc, monkeypatch, tmp_path):
        """Classic post-close refresh: file has today's row but it was
        written intraday; after 15:35 we must replace with finalized close."""
        now_ist = datetime.datetime(2026, 4, 21, 16, 0, tzinfo=IST)
        _freeze_now(monkeypatch, rc, now_ist)
        p = tmp_path / "X.NS.csv"
        _write_csv(p, [("2026-04-21", 1, 2, 1, 2, 100)])
        _set_mtime(p, datetime.datetime(2026, 4, 21, 13, 30, tzinfo=IST))
        assert rc._is_stale("2026-04-21", p) is True

    def test_today_row_written_postclose_is_not_stale(
            self, rc, monkeypatch, tmp_path):
        now_ist = datetime.datetime(2026, 4, 21, 17, 0, tzinfo=IST)
        _freeze_now(monkeypatch, rc, now_ist)
        p = tmp_path / "X.NS.csv"
        _write_csv(p, [("2026-04-21", 1, 2, 1, 2, 100)])
        _set_mtime(p, datetime.datetime(2026, 4, 21, 16, 0, tzinfo=IST))
        assert rc._is_stale("2026-04-21", p) is False


# ═══════════════════════════════════════════════════════════════════════════
#  _strip_intraday_today
# ═══════════════════════════════════════════════════════════════════════════

class TestStripIntradayToday:
    def test_drops_today_preclose(self, rc, monkeypatch):
        _freeze_now(monkeypatch, rc,
                    datetime.datetime(2026, 4, 21, 11, 0, tzinfo=IST))
        today = "2026-04-21"
        bars = [
            {"date": "2026-04-20", "close": 100},
            {"date": today, "close": 999},
        ]
        out = rc._strip_intraday_today(bars)
        assert [b["date"] for b in out] == ["2026-04-20"]

    def test_keeps_today_postclose(self, rc, monkeypatch):
        _freeze_now(monkeypatch, rc,
                    datetime.datetime(2026, 4, 21, 16, 0, tzinfo=IST))
        today = "2026-04-21"
        bars = [{"date": today, "close": 999}]
        assert rc._strip_intraday_today(bars) == bars

    def test_empty_input(self, rc):
        assert rc._strip_intraday_today([]) == []

    def test_no_today_row_preclose(self, rc, monkeypatch):
        _freeze_now(monkeypatch, rc,
                    datetime.datetime(2026, 4, 21, 11, 0, tzinfo=IST))
        bars = [{"date": "2026-04-20", "close": 100}]
        assert rc._strip_intraday_today(bars) == bars


# ═══════════════════════════════════════════════════════════════════════════
#  refresh_symbol — end-to-end with fetcher mocked
# ═══════════════════════════════════════════════════════════════════════════

class TestRefreshSymbol:
    def _preseed(self, tmp_path, rows):
        p = tmp_path / "ACME.NS.csv"
        _write_csv(p, rows)
        return p

    def test_force_refresh_bypasses_staleness(self, rc, monkeypatch, tmp_path):
        """force=True must refresh even if the file looks fresh."""
        _freeze_now(monkeypatch, rc,
                    datetime.datetime(2026, 4, 21, 17, 0, tzinfo=IST))
        p = self._preseed(tmp_path, [
            ("2026-04-20", 100, 105, 99, 104, 10000),
            ("2026-04-21", 104, 110, 103, 108, 20000),
        ])
        _set_mtime(p, datetime.datetime(2026, 4, 21, 16, 0, tzinfo=IST))

        called = {}

        def fake_fetch(sym, from_date=None):
            called["from_date"] = from_date
            return [{
                "date": "2026-04-21", "open": 104, "high": 112,
                "low": 103, "close": 111, "volume": 25000,
            }]

        monkeypatch.setattr(rc, "_fetch_bars", fake_fetch)
        monkeypatch.setattr(rc.time, "sleep", lambda *_: None)

        res = rc.refresh_symbol("ACME.NS", p, "2026-04-21", force=True)
        assert res["status"] == "updated"
        # Row must now reflect the fetcher's finalized close
        last = p.read_text().strip().splitlines()[-1]
        assert last.startswith("2026-04-21")
        assert "111.00000" in last  # new close

    def test_dry_run_never_writes(self, rc, monkeypatch, tmp_path):
        _freeze_now(monkeypatch, rc,
                    datetime.datetime(2026, 4, 21, 11, 0, tzinfo=IST))
        p = self._preseed(tmp_path, [("2026-04-17", 1, 2, 1, 2, 100)])
        before = p.read_text()

        def fake_fetch(*_a, **_kw):
            raise AssertionError("fetcher must not be called in dry_run")

        monkeypatch.setattr(rc, "_fetch_bars", fake_fetch)
        res = rc.refresh_symbol("ACME.NS", p, "2026-04-17",
                                force=False, dry_run=True)
        assert res["status"] == "would_refresh"
        assert p.read_text() == before

    def test_empty_fetch_leaves_file_untouched(self, rc, monkeypatch, tmp_path):
        _freeze_now(monkeypatch, rc,
                    datetime.datetime(2026, 4, 21, 11, 0, tzinfo=IST))
        p = self._preseed(tmp_path, [("2026-04-17", 1, 2, 1, 2, 100)])
        before = p.read_text()
        monkeypatch.setattr(rc, "_fetch_bars", lambda *a, **kw: [])
        monkeypatch.setattr(rc.time, "sleep", lambda *_: None)

        res = rc.refresh_symbol("ACME.NS", p, "2026-04-17")
        assert res["status"] == "no_new_data"
        assert p.read_text() == before

    def test_intraday_morning_row_overwritten_with_finalized_close(
            self, rc, monkeypatch, tmp_path):
        """THE BUG: file written 2026-04-20 13:31 IST with intraday row;
        refresh on Tue 2026-04-21 11:00 IST must replace Mon row with the
        finalized close returned by the fetcher, and MUST NOT write a new
        Tue partial row (session still live).
        """
        now_ist = datetime.datetime(2026, 4, 21, 11, 0, tzinfo=IST)
        _freeze_now(monkeypatch, rc, now_ist)

        p = self._preseed(tmp_path, [
            ("2026-04-17", 185, 205.82, 185, 199.5, 3681490),
            # Monday morning intraday capture — WRONG data
            ("2026-04-20", 229.7, 247.0, 227.02, 236.8, 7423661),
        ])
        _set_mtime(p, datetime.datetime(2026, 4, 20, 13, 31, tzinfo=IST))

        fetched_from = {}

        def fake_fetch(sym, from_date=None):
            fetched_from["v"] = from_date
            # Return finalized Monday + partial Tuesday (simulating live
            # session response). _strip_intraday_today normally filters
            # Tuesday at the _fetch_bars boundary; here we emulate that
            # behavior by not including it.
            return [{
                "date": "2026-04-20", "open": 229.7, "high": 249.89999,
                "low": 227.02, "close": 232.14999, "volume": 18364729,
            }]

        monkeypatch.setattr(rc, "_fetch_bars", fake_fetch)
        monkeypatch.setattr(rc.time, "sleep", lambda *_: None)

        res = rc.refresh_symbol("ACME.NS", p, "2026-04-20")

        # Backup logic must have requested bars BEFORE 2026-04-20 to force
        # a re-fetch of the Monday row.
        assert fetched_from["v"] < "2026-04-20"
        assert res["status"] == "updated"

        lines = p.read_text().strip().splitlines()
        assert lines[0].startswith("date,")
        assert lines[-1].startswith("2026-04-20")
        # Close field (5th col) should be the finalized close 232.14999
        parts = lines[-1].split(",")
        assert parts[4].startswith("232.14999")
        # Volume should be the finalized ~18.3M, not 7.4M
        assert int(parts[5]) > 15_000_000

    def test_fetcher_today_partial_never_written_preclose(
            self, rc, monkeypatch, tmp_path):
        """Even if _fetch_bars somehow leaks a today-dated partial row
        (e.g. a provider bypass), refresh_symbol's post-merge safety net
        must strip it before writing.
        """
        now_ist = datetime.datetime(2026, 4, 21, 11, 0, tzinfo=IST)
        _freeze_now(monkeypatch, rc, now_ist)

        p = self._preseed(tmp_path, [
            ("2026-04-17", 185, 205, 185, 199, 1000),
        ])
        _set_mtime(p, datetime.datetime(2026, 4, 17, 16, 0, tzinfo=IST))

        def leaky_fetch(sym, from_date=None):
            return [
                {"date": "2026-04-20", "open": 230, "high": 250,
                 "low": 227, "close": 232, "volume": 18000000},
                {"date": "2026-04-21", "open": 232, "high": 240,
                 "low": 231, "close": 238, "volume": 500000},  # partial
            ]

        monkeypatch.setattr(rc, "_fetch_bars", leaky_fetch)
        monkeypatch.setattr(rc.time, "sleep", lambda *_: None)

        rc.refresh_symbol("ACME.NS", p, "2026-04-17")

        last = p.read_text().strip().splitlines()[-1]
        # No 2026-04-21 row should ever be persisted pre-close
        assert last.startswith("2026-04-20"), (
            f"partial today bar leaked into cache: {last}")

    def test_preexisting_today_row_trimmed_even_if_no_new_today_bar(
            self, rc, monkeypatch, tmp_path):
        """Safety net: cache already has a today-dated intraday row, fetcher
        returns only yesterday's finalized close. Merge would keep the stale
        today row — the trimmer must remove it pre-close.
        """
        now_ist = datetime.datetime(2026, 4, 21, 11, 0, tzinfo=IST)
        _freeze_now(monkeypatch, rc, now_ist)

        p = self._preseed(tmp_path, [
            ("2026-04-20", 230, 250, 227, 232, 18000000),
            ("2026-04-21", 232, 234, 231, 233, 5000),  # stale partial
        ])
        _set_mtime(p, datetime.datetime(2026, 4, 21, 9, 30, tzinfo=IST))

        def fake_fetch(sym, from_date=None):
            return [{
                "date": "2026-04-20", "open": 230, "high": 251,
                "low": 227, "close": 235, "volume": 19000000,
            }]

        monkeypatch.setattr(rc, "_fetch_bars", fake_fetch)
        monkeypatch.setattr(rc.time, "sleep", lambda *_: None)

        rc.refresh_symbol("ACME.NS", p, "2026-04-21", force=True)

        last = p.read_text().strip().splitlines()[-1]
        assert last.startswith("2026-04-20"), (
            f"pre-existing today partial was not trimmed: {last}")

    def test_backup_triggers_for_previous_day_intraday_capture(
            self, rc, monkeypatch, tmp_path):
        """If last_bar_date is yesterday but file mtime is yesterday before
        close, refresh must request bars from BEFORE that date so the
        fetcher re-covers yesterday.
        """
        _freeze_now(monkeypatch, rc,
                    datetime.datetime(2026, 4, 21, 11, 0, tzinfo=IST))

        p = self._preseed(tmp_path, [
            ("2026-04-20", 100, 105, 99, 102, 1000),
        ])
        _set_mtime(p, datetime.datetime(2026, 4, 20, 10, 0, tzinfo=IST))

        captured = {}

        def fake_fetch(sym, from_date=None):
            captured["from_date"] = from_date
            return [{"date": "2026-04-20", "open": 100, "high": 108,
                     "low": 99, "close": 107, "volume": 5000}]

        monkeypatch.setattr(rc, "_fetch_bars", fake_fetch)
        monkeypatch.setattr(rc.time, "sleep", lambda *_: None)

        rc.refresh_symbol("ACME.NS", p, "2026-04-20")
        assert captured["from_date"] < "2026-04-20", (
            f"backup didn't roll fetch_from before 2026-04-20: {captured}")


# ═══════════════════════════════════════════════════════════════════════════
#  _merge_bars
# ═══════════════════════════════════════════════════════════════════════════

class TestMergeBars:
    def test_new_bar_replaces_old_for_same_date(self, rc):
        old = [{"date": "2026-04-20", "close": 100}]
        new = [{"date": "2026-04-20", "close": 110}]
        merged = rc._merge_bars(old, new)
        assert len(merged) == 1
        assert merged[0]["close"] == 110

    def test_merge_preserves_order_and_dedups(self, rc):
        old = [{"date": "2026-04-18", "close": 1},
               {"date": "2026-04-20", "close": 2}]
        new = [{"date": "2026-04-19", "close": 3},
               {"date": "2026-04-20", "close": 99}]
        merged = rc._merge_bars(old, new)
        assert [b["date"] for b in merged] == [
            "2026-04-18", "2026-04-19", "2026-04-20"]
        assert merged[-1]["close"] == 99

