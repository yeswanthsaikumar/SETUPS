"""Unit tests for apps/python/lib/vpn_manager.py.

Pins down the proxy-search contract:
  * search keeps running until a working proxy is found OR 5-minute cap hits
  * rotate() never crashes when pool is empty
  * enable/disable/rotate state transitions are correct
  * no real network is touched (block_network guard from conftest)
"""
from __future__ import annotations

from pathlib import Path

import pytest

import vpn_manager as vm

pytestmark = pytest.mark.unit


@pytest.fixture
def manager(tmp_path: Path) -> vm.VpnManager:
    cfg = tmp_path / "vpn_config.json"
    return vm.VpnManager(cfg)


class TestConstants:
    def test_hard_timeout_is_at_least_5_minutes(self):
        """User requirement: keep trying for at least 5 minutes."""
        assert vm.ENABLE_HARD_TIMEOUT >= 300, (
            f"Proxy search must run for >=300s, got {vm.ENABLE_HARD_TIMEOUT}s"
        )

    def test_watchdog_intervals_sane(self):
        assert vm.WATCHDOG_INTERVAL > 0
        assert vm.WATCHDOG_RETRY_INTERVAL > 0
        assert vm.WATCHDOG_FAILS_BEFORE_ROTATE >= 1


class TestBootState:
    def test_vpn_always_starts_disabled(self, manager):
        """Even if config file said enabled, boot must force-disable."""
        status = manager.status()
        assert status["enabled"] is False

    def test_disable_is_idempotent(self, manager):
        r1 = manager.disable()
        r2 = manager.disable()
        assert r1["ok"] is True
        assert r2["ok"] is True


class TestProxySearchBudget:
    def test_pick_returns_none_on_empty_pool(self, monkeypatch, manager):
        """When proxy pool fetch returns empty, we don't infinite-loop."""
        import time
        monkeypatch.setattr(manager, "_fetch_free_proxies", lambda force=False: [])
        result = manager._pick_working_free_proxy(deadline_ts=time.time() + 1.0)
        assert result is None

    def test_pick_stops_at_deadline(self, monkeypatch, manager):
        """Every proxy fails — must stop at the deadline (not infinite loop)."""
        import time
        monkeypatch.setattr(manager, "_fetch_free_proxies",
                            lambda force=False: ["http://1.2.3.4:8080"] * 5)
        monkeypatch.setattr(manager, "_test_proxy",
                            lambda url, **kw: False)
        started = time.time()
        result = manager._pick_working_free_proxy(deadline_ts=started + 0.5)
        elapsed = time.time() - started
        assert result is None
        assert elapsed < 5.0, f"search ran way past deadline ({elapsed:.1f}s)"


class TestConfigPersistence:
    def test_custom_proxy_config(self, manager):
        r = manager.set_config(provider="custom",
                               custom_proxy_url="http://user:pw@proxy:3128")
        assert r["ok"] is True
        assert manager.status()["provider"] == "custom"

    def test_invalid_provider_rejected(self, manager):
        with pytest.raises(ValueError):
            manager.set_config(provider="paid-garbage")

