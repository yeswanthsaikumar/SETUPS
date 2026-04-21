"""Tests for the hourly PeriodicCacheRefreshScheduler."""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.api


@pytest.fixture
def mod():
    from apps.web.api import main as _m
    return _m


def test_scheduler_interval_env_default(mod):
    sch = mod.PeriodicCacheRefreshScheduler(MagicMock(), interval_seconds=3600)
    assert sch.status_dict()["intervalSeconds"] == 3600


def test_scheduler_interval_floor(mod):
    # Floor at 60s even if caller passes something absurdly small.
    sch = mod.PeriodicCacheRefreshScheduler(MagicMock(), interval_seconds=5)
    assert sch.status_dict()["intervalSeconds"] == 60


def test_scheduler_start_stop_idempotent(mod):
    sch = mod.PeriodicCacheRefreshScheduler(MagicMock(), interval_seconds=3600)
    sch.start()
    assert sch.is_running
    # Double-start is a no-op, not an error.
    sch.start()
    assert sch.is_running
    sch.stop()
    # Thread wakes from wait() immediately on stop and exits.
    for _ in range(50):
        if not sch.is_running:
            break
        time.sleep(0.02)
    assert not sch.is_running


def test_scheduler_fires_refresher_on_tick(mod):
    """With a short interval, at least one tick should invoke refresher.start()."""
    fake = MagicMock()
    fake.is_running = False
    sch = mod.PeriodicCacheRefreshScheduler(fake, interval_seconds=60)
    # Shrink interval past the 60s floor for this test only.
    sch._interval = 0.05  # type: ignore[attr-defined]
    sch.start()
    time.sleep(0.2)
    sch.stop()
    assert fake.start.call_count >= 1
    # Each call must pass indian_only=True + force=False.
    _, kwargs = fake.start.call_args
    assert kwargs.get("indian_only") is True
    assert kwargs.get("force") is False


def test_scheduler_skips_when_refresh_already_running(mod):
    fake = MagicMock()
    fake.is_running = True  # refresher busy
    sch = mod.PeriodicCacheRefreshScheduler(fake, interval_seconds=60)
    sch._interval = 0.05  # type: ignore[attr-defined]
    sch.start()
    time.sleep(0.2)
    sch.stop()
    # Should never have called start() because refresher was always running.
    assert fake.start.call_count == 0


def test_status_endpoint_exposes_periodic(mod):
    status = mod._periodic_refresher.status_dict()
    assert "intervalSeconds" in status
    assert "running" in status
    assert "tickCount" in status
    assert "lastTickAt" in status

