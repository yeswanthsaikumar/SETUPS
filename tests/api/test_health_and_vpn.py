"""FastAPI TestClient tests for health, VPN, Groww verification.

These guarantee the public JSON contract of every endpoint the UI depends on.
Regression-golden snapshots (tests/_golden/*.json) fail the build if a new
feature accidentally renames or removes a response key.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


class TestHealth:
    def test_health_200(self, api_client):
        r = api_client.get("/api/health")
        assert r.status_code == 200

    def test_health_shape(self, api_client, regression_golden):
        r = api_client.get("/api/health").json()
        regression_golden("health", r)


class TestVpnEndpoints:
    def test_status_disabled_on_boot(self, api_client):
        r = api_client.get("/api/vpn/status").json()
        assert r.get("enabled") is False

    def test_status_shape(self, api_client, regression_golden):
        r = api_client.get("/api/vpn/status").json()
        regression_golden("vpn_status", r)

    def test_disable_idempotent(self, api_client):
        r = api_client.post("/api/vpn/disable").json()
        assert r.get("ok") is True

    def test_config_custom_proxy(self, api_client):
        r = api_client.post("/api/vpn/config",
                            json={"provider": "custom",
                                  "custom_proxy_url": "http://u:p@127.0.0.1:3128"})
        assert r.status_code == 200
        assert r.json().get("ok") is True


class TestGrowwVerify:
    def test_verify_endpoint_returns_structured(self, api_client, groww_mock):
        r = api_client.get("/api/groww/verify?symbol=RELIANCE").json()
        assert "ok" in r
        assert "mode_groww_only" in r or "credentials_set" in r

    def test_verify_shape(self, api_client, groww_mock, regression_golden):
        r = api_client.get("/api/groww/verify?symbol=RELIANCE").json()
        regression_golden("groww_verify", r)

