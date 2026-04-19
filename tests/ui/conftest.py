"""UI test fixtures — boot the FastAPI app against an ephemeral port
so Playwright can drive the real HTML pages under apps/web/ui/.

The live_server intentionally runs against an ISOLATED trade_data/ +
cache/ directory (set via env vars BEFORE importing main), so tests can
seed positions, journal entries, and cache CSVs without polluting real
user state.
"""
from __future__ import annotations

import importlib
import json
import os
import socket
import sys
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path

import pytest


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def ui_trade_data_dir(tmp_path_factory) -> Path:
    """Session-scoped trade_data/ dir used by the live_server."""
    td = tmp_path_factory.mktemp("ui_trade_data")
    (td / "positions.json").write_text(
        '{"version": 1, "positions": [], "created": "2026-04-18T00:00:00"}'
    )
    (td / "watchlist.json").write_text("[]")
    (td / "journal.json").write_text("[]")
    return td


@pytest.fixture(scope="session")
def ui_cache_dir(tmp_path_factory) -> Path:
    """Session-scoped cache/ dir used by the live_server."""
    cd = tmp_path_factory.mktemp("ui_cache")
    (cd / "^NSEI.csv").write_text(
        "date,open,high,low,close,volume\n"
        "2026-04-15,22000,22100,21950,22050,100000\n"
        "2026-04-16,22050,22200,22040,22180,110000\n"
        "2026-04-17,22180,22300,22150,22270,120000\n"
        "2026-04-18,22270,22400,22250,22380,130000\n"
    )
    return cd


@pytest.fixture(scope="session")
def live_server(ui_trade_data_dir, ui_cache_dir):
    """Run uvicorn in a background thread and yield the base URL.

    CRITICAL: we set the SETUPS_* env vars BEFORE importing main so its
    module-level path globals are bound to the isolated temp dirs. If main
    was already imported by an earlier test, we reload it.
    """
    os.environ["SETUPS_TRADE_DATA_DIR"] = str(ui_trade_data_dir)
    os.environ["SETUPS_CACHE_DIR"] = str(ui_cache_dir)
    # Disable the auto-started breakout alert scanner noise in test logs.
    os.environ.setdefault("SETUPS_DISABLE_BG_JOBS", "1")

    if "main" in sys.modules:
        api_main = importlib.reload(sys.modules["main"])
    else:
        import main as api_main  # noqa: F401

    import uvicorn
    port = _free_port()
    config = uvicorn.Config(api_main.app, host="127.0.0.1", port=port,
                            log_level="warning", access_log=False)
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            with closing(socket.create_connection(("127.0.0.1", port), timeout=0.2)):
                break
        except OSError:
            time.sleep(0.1)
    else:
        raise RuntimeError("uvicorn did not start in time")

    yield base

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def clean_board(ui_trade_data_dir: Path):
    """Reset positions.json to empty before a test that seeds its own data."""
    (ui_trade_data_dir / "positions.json").write_text(
        '{"version": 1, "positions": [], "created": "2026-04-18T00:00:00"}'
    )
    yield ui_trade_data_dir / "positions.json"


@pytest.fixture
def seed_positions(ui_trade_data_dir: Path):
    """Return a helper that writes an arbitrary list of positions into
    the isolated positions.json. Tests call it with the shape they need.
    """
    def _seed(positions: list[dict]):
        payload = {
            "version": 1,
            "positions": positions,
            "created": "2026-04-18T00:00:00",
            "lastUpdated": "2026-04-18T00:00:00",
        }
        (ui_trade_data_dir / "positions.json").write_text(json.dumps(payload))
    return _seed


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Tighten browser defaults."""
    return {**browser_context_args,
            "viewport": {"width": 1440, "height": 900},
            "ignore_https_errors": True}

