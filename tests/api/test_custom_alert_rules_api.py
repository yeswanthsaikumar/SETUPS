"""API tests for custom alert rule CRUD endpoints.

Covers:
• GET empty list on fresh state
• POST rule — validation, defaults, id assignment
• PATCH rule — partial update
• DELETE rule — 404 when missing
• GET config/status includes custom_rules (via main config endpoint)
• POST with bad timeframe / metric / operator → 400
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


def _valid_rule_payload():
    return {
        "name": "Vol surge 15m",
        "timeframe": "15m",
        "metric": "volume_ratio",
        "operator": ">=",
        "threshold": 2.5,
        "reference": "absolute",
        "reference_bars": 20,
        "cooldown_minutes": 30,
        "channels": ["telegram"],
        "symbol": "",
    }


def test_list_custom_rules_empty_by_default(api_client):
    r = api_client.get("/api/breakout-alerts/custom-rules").json()
    assert r["count"] == 0
    assert r["rules"] == []
    # supported vocabularies must be exposed to the UI
    assert "15m" in r["supported"]["timeframes"]
    assert "volume_ratio" in r["supported"]["metrics"]
    assert "crosses_above" in r["supported"]["operators"]


def test_create_rule_applies_defaults_and_id(api_client):
    payload = _valid_rule_payload()
    # only send the 4 required fields — server should fill the rest
    minimal = {k: payload[k] for k in ("timeframe", "metric", "operator", "threshold")}
    r = api_client.post("/api/breakout-alerts/custom-rules", json=minimal).json()
    assert r["ok"] is True
    rule = r["rule"]
    assert rule["id"] and len(rule["id"]) >= 8
    assert rule["enabled"] is True
    assert rule["reference"] == "absolute"
    assert rule["cooldown_minutes"] == 60
    assert rule["channels"] == ["telegram"]


def test_create_then_list_roundtrip(api_client):
    api_client.post("/api/breakout-alerts/custom-rules",
                     json=_valid_rule_payload())
    listed = api_client.get("/api/breakout-alerts/custom-rules").json()
    assert listed["count"] == 1
    assert listed["rules"][0]["timeframe"] == "15m"
    assert listed["rules"][0]["metric"] == "volume_ratio"


def test_patch_updates_fields_only(api_client):
    created = api_client.post("/api/breakout-alerts/custom-rules",
                               json=_valid_rule_payload()).json()["rule"]
    rid = created["id"]
    patched = api_client.patch(
        f"/api/breakout-alerts/custom-rules/{rid}",
        json={"threshold": 3.0, "enabled": False},
    ).json()
    assert patched["ok"] is True
    assert patched["rule"]["threshold"] == 3.0
    assert patched["rule"]["enabled"] is False
    # unchanged fields preserved
    assert patched["rule"]["metric"] == "volume_ratio"


def test_patch_unknown_id_404(api_client):
    r = api_client.patch("/api/breakout-alerts/custom-rules/does-not-exist",
                          json={"threshold": 1.0})
    assert r.status_code == 404


def test_delete_rule(api_client):
    created = api_client.post("/api/breakout-alerts/custom-rules",
                               json=_valid_rule_payload()).json()["rule"]
    rid = created["id"]
    r = api_client.delete(f"/api/breakout-alerts/custom-rules/{rid}").json()
    assert r["ok"] is True
    assert r["deleted"] == rid
    assert r["remaining"] == 0


def test_delete_unknown_id_404(api_client):
    r = api_client.delete("/api/breakout-alerts/custom-rules/nope")
    assert r.status_code == 404


@pytest.mark.parametrize("bad_field,bad_value", [
    ("timeframe", "1y"),        # unsupported
    ("metric",    "rsi"),        # unsupported
    ("operator",  "contains"),   # unsupported
    ("reference", "yesterdays"), # unsupported
])
def test_create_rule_rejects_invalid_vocab(api_client, bad_field, bad_value):
    payload = _valid_rule_payload()
    payload[bad_field] = bad_value
    r = api_client.post("/api/breakout-alerts/custom-rules", json=payload)
    assert r.status_code == 400


def test_create_rule_requires_core_fields(api_client):
    r = api_client.post("/api/breakout-alerts/custom-rules",
                         json={"name": "orphan"})
    assert r.status_code == 400


def test_create_rule_rejects_unknown_channel(api_client):
    payload = _valid_rule_payload()
    payload["channels"] = ["telegram", "carrier-pigeon"]
    r = api_client.post("/api/breakout-alerts/custom-rules", json=payload)
    assert r.status_code == 400


def test_config_endpoint_includes_custom_rules_list(api_client):
    api_client.post("/api/breakout-alerts/custom-rules",
                     json=_valid_rule_payload())
    status = api_client.get("/api/breakout-alerts/status").json()
    assert "custom_rules" in status["config"]
    assert isinstance(status["config"]["custom_rules"], list)
    assert len(status["config"]["custom_rules"]) == 1


def test_evaluate_now_endpoint_returns_shape(api_client):
    """Dry-run endpoint must always return a list, even with no rules/data."""
    r = api_client.post("/api/breakout-alerts/custom-rules/evaluate-now",
                         json=[]).json()
    assert "fired" in r
    assert "count" in r
    assert r["count"] == 0

