"""Integration tests for cache staleness + refresh pipeline inside the web API.

These complement `tests/unit/test_refresh_cache.py` (which tests the
script module in isolation) by verifying that:

• `_is_price_stale` in main.py mirrors `refresh_cache._is_stale` for all
  critical cases (weekend, biz-day gap, pre-close intraday, post-close
  intraday, fresh intraday).
• `_refresh_symbol_if_stale` actually calls through to `refresh_cache.refresh_symbol`
  with correct `force` propagation and cooldown behavior.
• The startup lifespan kicks off the background cache refresher (unless
  SETUPS_SKIP_STARTUP_REFRESH is set).
• The `/api/cache/refresh-symbols?force=true` endpoint applies `force` all
  the way down to the underlying refresh call.
"""
from __future__ import annotations

import datetime
import os
import zoneinfo
from pathlib import Path

import pytest

pytestmark = pytest.mark.api

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


def _set_mtime(path: Path, when: datetime.datetime) -> None:
    ts = when.timestamp()
    os.utime(path, (ts, ts))


def _freeze_now(monkeypatch, mod, when_ist: datetime.datetime):
    real_dt = datetime.datetime

    class _Frozen(real_dt):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            if tz is None:
                return when_ist.replace(tzinfo=None)
            return when_ist.astimezone(tz)

    # main.py imports datetime locally inside _is_price_stale, so patch
    # the canonical module that the local `import datetime as _dt` resolves.
    import datetime as _dt_mod
    monkeypatch.setattr(_dt_mod, "datetime", _Frozen)


# ═══════════════════════════════════════════════════════════════════════════
#  _is_price_stale (web layer)
# ═══════════════════════════════════════════════════════════════════════════

class TestIsPriceStaleWeb:
    def test_empty_last_date_stale(self):
        import main as api_main
        assert api_main._is_price_stale("") is True

    def test_malformed_last_date_stale(self):
        import main as api_main
        assert api_main._is_price_stale("garbage") is True

    def test_weekend_gap_not_stale(self, tmp_path, monkeypatch):
        import main as api_main
        _freeze_now(monkeypatch, api_main,
                    datetime.datetime(2026, 4, 18, 10, 0, tzinfo=IST))  # Sat
        p = tmp_path / "X.NS.csv"
        p.write_text("date,open,high,low,close,volume\n"
                     "2026-04-17,1,2,1,2,100\n")
        _set_mtime(p, datetime.datetime(2026, 4, 17, 16, 0, tzinfo=IST))
        assert api_main._is_price_stale("2026-04-17", p) is False

    def test_business_day_gap_stale(self, tmp_path, monkeypatch):
        import main as api_main
        _freeze_now(monkeypatch, api_main,
                    datetime.datetime(2026, 4, 21, 10, 0, tzinfo=IST))  # Tue
        p = tmp_path / "X.NS.csv"
        p.write_text("date,open,high,low,close,volume\n"
                     "2026-04-17,1,2,1,2,100\n")
        assert api_main._is_price_stale("2026-04-17", p) is True

    def test_today_intraday_older_mtime_preclose_is_stale(
            self, tmp_path, monkeypatch):
        """Mirrors the bug case on the web read path."""
        import main as api_main
        now_ist = datetime.datetime(2026, 4, 21, 11, 0, tzinfo=IST)
        _freeze_now(monkeypatch, api_main, now_ist)
        p = tmp_path / "X.NS.csv"
        p.write_text("date,open,high,low,close,volume\n"
                     "2026-04-21,1,2,1,2,100\n")
        _set_mtime(p, datetime.datetime(2026, 4, 21, 10, 0, tzinfo=IST))
        assert api_main._is_price_stale("2026-04-21", p) is True

    def test_today_intraday_just_written_not_stale(self, tmp_path, monkeypatch):
        import main as api_main
        now_ist = datetime.datetime(2026, 4, 21, 11, 0, tzinfo=IST)
        _freeze_now(monkeypatch, api_main, now_ist)
        p = tmp_path / "X.NS.csv"
        p.write_text("date,open,high,low,close,volume\n"
                     "2026-04-21,1,2,1,2,100\n")
        _set_mtime(p, now_ist - datetime.timedelta(seconds=30))
        assert api_main._is_price_stale("2026-04-21", p) is False

    def test_today_intraday_postclose_stale(self, tmp_path, monkeypatch):
        import main as api_main
        _freeze_now(monkeypatch, api_main,
                    datetime.datetime(2026, 4, 21, 16, 0, tzinfo=IST))
        p = tmp_path / "X.NS.csv"
        p.write_text("date,open,high,low,close,volume\n"
                     "2026-04-21,1,2,1,2,100\n")
        _set_mtime(p, datetime.datetime(2026, 4, 21, 13, 30, tzinfo=IST))
        assert api_main._is_price_stale("2026-04-21", p) is True


# ═══════════════════════════════════════════════════════════════════════════
#  _refresh_symbol_if_stale
# ═══════════════════════════════════════════════════════════════════════════

class TestRefreshSymbolIfStale:
    def test_force_propagates_to_refresh_cache(self, tmp_cache, monkeypatch):
        import main as api_main
        import refresh_cache as rc

        # Seed a stale cache so the stale-check gate passes too
        (tmp_cache / "ACME.NS.csv").write_text(
            "date,open,high,low,close,volume\n"
            "2026-04-10,1,2,1,2,100\n")
        monkeypatch.setattr(api_main, "CACHE_DIR", tmp_cache, raising=False)

        calls = []

        def fake_refresh(sym, path, last_date, force=False, dry_run=False):
            calls.append({"sym": sym, "force": force, "last_date": last_date})
            return {"status": "updated", "bars_added": 1, "last_date": "2026-04-20"}

        monkeypatch.setattr(rc, "refresh_symbol", fake_refresh)
        # Clear cooldown to ensure call happens
        api_main._recently_refreshed.clear()

        ok = api_main._refresh_symbol_if_stale("ACME.NS", force=True)
        assert ok is True
        assert calls and calls[0]["force"] is True

    def test_cooldown_blocks_rapid_double_refresh(self, tmp_cache, monkeypatch):
        import main as api_main
        import refresh_cache as rc

        (tmp_cache / "ACME.NS.csv").write_text(
            "date,open,high,low,close,volume\n"
            "2026-04-10,1,2,1,2,100\n")
        monkeypatch.setattr(api_main, "CACHE_DIR", tmp_cache, raising=False)

        count = {"n": 0}

        def fake_refresh(*a, **kw):
            count["n"] += 1
            return {"status": "updated", "bars_added": 1, "last_date": "2026-04-20"}

        monkeypatch.setattr(rc, "refresh_symbol", fake_refresh)
        api_main._recently_refreshed.clear()

        api_main._refresh_symbol_if_stale("ACME.NS", force=False)
        api_main._refresh_symbol_if_stale("ACME.NS", force=False)
        assert count["n"] == 1  # second call blocked by cooldown

    def test_cooldown_bypassed_by_force(self, tmp_cache, monkeypatch):
        import main as api_main
        import refresh_cache as rc

        (tmp_cache / "ACME.NS.csv").write_text(
            "date,open,high,low,close,volume\n"
            "2026-04-10,1,2,1,2,100\n")
        monkeypatch.setattr(api_main, "CACHE_DIR", tmp_cache, raising=False)

        count = {"n": 0}

        def fake_refresh(*a, **kw):
            count["n"] += 1
            return {"status": "updated", "bars_added": 1, "last_date": "2026-04-20"}

        monkeypatch.setattr(rc, "refresh_symbol", fake_refresh)
        api_main._recently_refreshed.clear()

        api_main._refresh_symbol_if_stale("ACME.NS", force=False)
        api_main._refresh_symbol_if_stale("ACME.NS", force=True)
        assert count["n"] == 2


# ═══════════════════════════════════════════════════════════════════════════
#  Startup lifespan — background cache refresh
# ═══════════════════════════════════════════════════════════════════════════

class TestStartupRefresh:
    def test_startup_triggers_background_refresh_by_default(
            self, monkeypatch, tmp_trade_data, tmp_cache, groww_mock):
        """Lifespan must call `_cache_refresher.start(...)` when no skip env."""
        from fastapi.testclient import TestClient
        import main as api_main

        monkeypatch.delenv("SETUPS_SKIP_STARTUP_REFRESH", raising=False)
        monkeypatch.delenv("SETUPS_STARTUP_FORCE_REFRESH", raising=False)
        monkeypatch.setattr(api_main, "CACHE_DIR", tmp_cache, raising=False)

        captured = []

        def fake_start(symbols=None, force=False, indian_only=True, workers=4):
            captured.append({"force": force, "indian_only": indian_only,
                             "workers": workers})
            return {"ok": True}

        monkeypatch.setattr(api_main._cache_refresher, "start", fake_start)
        monkeypatch.setattr(type(api_main._cache_refresher), "is_running",
                            property(lambda self: False))

        with TestClient(api_main.app):
            pass  # lifespan runs on enter

        assert captured, "startup did not trigger background cache refresh"
        assert captured[0]["indian_only"] is True
        assert captured[0]["force"] is False

    def test_startup_skipped_when_env_set(
            self, monkeypatch, tmp_trade_data, tmp_cache, groww_mock):
        from fastapi.testclient import TestClient
        import main as api_main

        monkeypatch.setenv("SETUPS_SKIP_STARTUP_REFRESH", "true")
        monkeypatch.setattr(api_main, "CACHE_DIR", tmp_cache, raising=False)

        called = []
        monkeypatch.setattr(api_main._cache_refresher, "start",
                            lambda **kw: called.append(kw) or {"ok": True})

        with TestClient(api_main.app):
            pass
        assert called == [], "startup refresh ran despite skip env"

    def test_startup_force_env_propagates(
            self, monkeypatch, tmp_trade_data, tmp_cache, groww_mock):
        from fastapi.testclient import TestClient
        import main as api_main

        monkeypatch.delenv("SETUPS_SKIP_STARTUP_REFRESH", raising=False)
        monkeypatch.setenv("SETUPS_STARTUP_FORCE_REFRESH", "true")
        monkeypatch.setattr(api_main, "CACHE_DIR", tmp_cache, raising=False)

        captured = []
        monkeypatch.setattr(api_main._cache_refresher, "start",
                            lambda **kw: captured.append(kw) or {"ok": True})
        monkeypatch.setattr(type(api_main._cache_refresher), "is_running",
                            property(lambda self: False))

        with TestClient(api_main.app):
            pass
        assert captured and captured[0]["force"] is True


# ═══════════════════════════════════════════════════════════════════════════
#  End-to-end: /api/cache/refresh-symbols?force=true exercises the chain
# ═══════════════════════════════════════════════════════════════════════════

class TestRefreshSymbolsEndpointE2E:
    def test_force_reaches_refresh_cache_refresh_symbol(
            self, api_client, monkeypatch):
        import refresh_cache as rc

        calls = []

        def fake_refresh(sym, path, last_date, force=False, dry_run=False):
            calls.append({"sym": sym, "force": force})
            return {"status": "updated", "bars_added": 1,
                    "last_date": "2026-04-20"}

        monkeypatch.setattr(rc, "refresh_symbol", fake_refresh)

        import main as api_main
        api_main._recently_refreshed.clear()

        r = api_client.post(
            "/api/cache/refresh-symbols?force=true",
            json=["ACME.NS"])
        assert r.status_code == 200
        assert any(c["force"] is True for c in calls), calls

