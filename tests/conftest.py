"""
Shared pytest fixtures & test isolation for the SETUPS suite.

Design principles
─────────────────
1. **Never touch real user data.** `trade_data/` and `cache/` are pointed at
   per-test temp dirs via env vars + monkeypatch on module globals.
2. **Never hit the network.** Requests/yfinance/growwapi are auto-patched to
   raise loudly by default (`block_network` fixture). Opt-in with `-m network`.
3. **Regression shield.** `regression_golden` fixture captures key JSON
   response shapes; a schema drift breaks the test immediately so a new
   feature cannot silently change an existing API's contract.
"""
from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from typing import Any

import pytest

# ── Make app code importable without installing ─────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "apps" / "python" / "lib",
          ROOT / "apps" / "web" / "api",
          ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


# ── 1. Filesystem isolation ─────────────────────────────────────────────────

@pytest.fixture
def tmp_trade_data(tmp_path: Path, monkeypatch) -> Path:
    """Redirect every trade_data/*.json write to a fresh temp dir."""
    td = tmp_path / "trade_data"
    td.mkdir(parents=True, exist_ok=True)
    # Match the shape written by _save_board() in apps/web/api/main.py:
    # a dict with a 'positions' list, not a bare list.
    (td / "positions.json").write_text(
        '{"version": 1, "positions": [], "created": "2026-04-18T00:00:00"}'
    )
    (td / "watchlist.json").write_text("[]")
    (td / "journal.json").write_text("[]")
    monkeypatch.setenv("SETUPS_TRADE_DATA_DIR", str(td))
    return td


@pytest.fixture
def tmp_cache(tmp_path: Path, monkeypatch) -> Path:
    """Redirect cache/ to a fresh temp dir, pre-seeded with a tiny Nifty CSV."""
    cd = tmp_path / "cache"
    cd.mkdir(parents=True, exist_ok=True)
    # Minimal usable bars so breadth / RS code doesn't KeyError
    (cd / "^NSEI.csv").write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2026-04-15,22000,22100,21950,22050,100000\n"
        "2026-04-16,22050,22200,22040,22180,110000\n"
        "2026-04-17,22180,22300,22150,22270,120000\n"
        "2026-04-18,22270,22400,22250,22380,130000\n"
    )
    monkeypatch.setenv("SETUPS_CACHE_DIR", str(cd))
    return cd


# ── 2. Network isolation ────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def block_network(request, monkeypatch):
    """Raise on any TCP connect attempt unless the test is marked @network."""
    if "network" in request.keywords:
        return
    real_connect = socket.socket.connect

    def guarded_connect(self, address, *a, **kw):
        # Allow loopback for FastAPI TestClient + local temp-file operations.
        host = address[0] if isinstance(address, tuple) else ""
        if host in ("127.0.0.1", "::1", "localhost", ""):
            return real_connect(self, address, *a, **kw)
        raise RuntimeError(
            f"Network access blocked in unit test: attempted {address}. "
            f"Mark the test with @pytest.mark.network to allow, or mock the "
            f"call (recommended)."
        )

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


# ── 3. Groww client patching ────────────────────────────────────────────────

@pytest.fixture
def groww_mock(monkeypatch):
    """Inject a fake Groww client that returns deterministic data."""
    import groww_client as gc

    class _FakeGrowwAPI:
        SEGMENT_CASH = "CASH"
        EXCHANGE_NSE = "NSE"
        CANDLE_INTERVAL_DAY = "DAY"

        def get_ltp(self, exchange_trading_symbols, segment, timeout=8):
            return {sym: 1234.5 for sym in exchange_trading_symbols}

        def get_ohlc(self, exchange_trading_symbols, segment, timeout=8):
            return {
                sym: {"open": 1200, "high": 1250, "low": 1190, "close": 1230}
                for sym in exchange_trading_symbols
            }

        def get_quote(self, trading_symbol, exchange, segment, timeout=10):
            return {
                "pe": 22.5, "marketCap": 1.2e12,
                "sector": "Energy", "industry": "Refineries",
                "dividendYield": 0.008, "earningsGrowth": 0.15,
                "revenueGrowth": 0.12,
            }

        def get_historical_candle_data(self, **kw):
            return {"candles": [
                ["2026-04-15T00:00:00+05:30", 100, 105, 99, 104, 10000],
                ["2026-04-16T00:00:00+05:30", 104, 108, 103, 107, 12000],
                ["2026-04-17T00:00:00+05:30", 107, 110, 106, 109, 11000],
            ]}

        get_historical_candles = get_historical_candle_data

    fake = _FakeGrowwAPI()
    monkeypatch.setattr(gc, "_client", fake, raising=False)
    monkeypatch.setattr(gc, "_init_failed", False, raising=False)
    monkeypatch.setattr(gc, "_GROWW_ACCESS_TOKEN", "test-token", raising=False)
    monkeypatch.setattr(gc, "get_groww_client", lambda: fake)
    return fake


@pytest.fixture
def groww_broken(monkeypatch):
    """Simulate Groww client that fails to initialize (no creds / bad token)."""
    import groww_client as gc
    monkeypatch.setattr(gc, "_client", None, raising=False)
    monkeypatch.setattr(gc, "_init_failed", True, raising=False)
    monkeypatch.setattr(gc, "_GROWW_ACCESS_TOKEN", "", raising=False)
    monkeypatch.setattr(gc, "_GROWW_API_KEY", "", raising=False)
    monkeypatch.setattr(gc, "get_groww_client", lambda: None)
    return gc


# ── 4. FastAPI app factory (TestClient) ─────────────────────────────────────

@pytest.fixture
def api_client(tmp_trade_data, tmp_cache, groww_mock, monkeypatch):
    """Build a FastAPI TestClient with fully isolated state.

    Note: main.py reads paths at import time. We import once, then rebind
    the module-level Path globals so tests don't scribble on real files.
    """
    from fastapi.testclient import TestClient
    import main as api_main  # apps/web/api/main.py

    monkeypatch.setattr(api_main, "TRADE_DATA_DIR", tmp_trade_data, raising=False)
    monkeypatch.setattr(api_main, "TRADE_BOARD_JSON",
                        tmp_trade_data / "positions.json", raising=False)
    monkeypatch.setattr(api_main, "TRADE_JOURNAL_JSON",
                        tmp_trade_data / "journal.json", raising=False)
    monkeypatch.setattr(api_main, "TRADE_WATCHLIST_JSON",
                        tmp_trade_data / "watchlist.json", raising=False)
    monkeypatch.setattr(api_main, "CACHE_DIR", tmp_cache, raising=False)

    with TestClient(api_main.app) as client:
        yield client


# ── 5. Regression golden snapshots ──────────────────────────────────────────

GOLDEN_DIR = Path(__file__).parent / "_golden"


@pytest.fixture
def regression_golden(request):
    """Assert a JSON response shape matches a stored golden snapshot.

    Usage::
        def test_shape(api_client, regression_golden):
            r = api_client.get("/api/health").json()
            regression_golden("health", r)

    On first run (or with UPDATE_GOLDEN=1) it writes the snapshot. Subsequent
    runs compare *keys* (not values) so a new feature that adds a key will
    force you to explicitly update the snapshot — this is the "no old feature
    breaks" safety net.
    """
    GOLDEN_DIR.mkdir(exist_ok=True)
    update = os.environ.get("UPDATE_GOLDEN") == "1"

    def _keyshape(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _keyshape(v) for k, v in sorted(obj.items())}
        if isinstance(obj, list):
            return [_keyshape(obj[0])] if obj else []
        return type(obj).__name__

    def _check(name: str, value: Any):
        shape = _keyshape(value)
        path = GOLDEN_DIR / f"{name}.json"
        if update or not path.exists():
            path.write_text(json.dumps(shape, indent=2))
            return
        stored = json.loads(path.read_text())
        assert shape == stored, (
            f"API response shape drifted for '{name}'. "
            f"Run UPDATE_GOLDEN=1 pytest to accept, or fix the regression.\n"
            f"Expected: {stored}\nGot: {shape}"
        )
    return _check


# ── 6. Helpers ──────────────────────────────────────────────────────────────

@pytest.fixture
def sample_position() -> dict:
    """Payload matching the TradeBoardPosition Pydantic model in main.py."""
    return {
        "symbol": "RELIANCE.NS",
        "name": "Reliance Industries",
        "entry": 1200.0,
        "quantity": 10,
        "sl": 1140.0,
        "t1": 1320.0,
        "t2": 1440.0,
        "t3": 1560.0,
        "setup": "BREAKOUT",
        "rating": "A",
        "notes": "unit-test sample",
        "entry_date": "2026-04-15",
        "status": "OPEN",
        "tags": ["vcp"],
    }

