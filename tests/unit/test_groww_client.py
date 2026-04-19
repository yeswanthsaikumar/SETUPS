"""Unit tests for apps/python/lib/groww_client.py.

These tests lock down the *Groww-only enforcement* contract so no future
feature can silently re-introduce a non-Groww data source for Indian
symbols.
"""
from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.unit


def _reload_gc(monkeypatch, **env):
    """Reload groww_client with a controlled environment."""
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    import groww_client
    return importlib.reload(groww_client)


class TestSymbolClassification:
    def test_nse_symbol_is_indian(self):
        import groww_client as gc
        assert gc.is_indian_symbol("RELIANCE.NS") is True

    def test_bse_symbol_is_indian(self):
        import groww_client as gc
        assert gc.is_indian_symbol("RELIANCE.BO") is True

    def test_us_symbol_is_not_indian(self):
        import groww_client as gc
        assert gc.is_indian_symbol("AAPL") is False

    def test_empty_symbol(self):
        import groww_client as gc
        assert gc.is_indian_symbol("") is False
        assert gc.is_indian_symbol(None) is False  # type: ignore[arg-type]


class TestGrowwOnlyGate:
    def test_indian_symbol_blocks_external_sources_when_groww_only(self, monkeypatch):
        gc = _reload_gc(monkeypatch, GROWW_ONLY="1")
        assert gc.groww_only_mode() is True
        assert gc.should_use_non_groww_source("RELIANCE.NS") is False
        assert gc.should_use_non_groww_source("TCS.BO") is False

    def test_us_symbol_always_allows_fallback(self, monkeypatch):
        gc = _reload_gc(monkeypatch, GROWW_ONLY="1")
        assert gc.should_use_non_groww_source("AAPL") is True

    def test_groww_only_off_allows_everything(self, monkeypatch):
        gc = _reload_gc(monkeypatch, GROWW_ONLY="0")
        assert gc.groww_only_mode() is False
        assert gc.should_use_non_groww_source("RELIANCE.NS") is True


class TestClientInit:
    def test_returns_none_without_credentials(self, monkeypatch):
        gc = _reload_gc(monkeypatch,
                        GROWW_ACCESS_TOKEN="", GROWW_API_KEY="", GROWW_API_SECRET="")
        assert gc.get_groww_client() is None
        assert gc.is_groww_available() is False

    def test_groww_mock_fixture_returns_fake_client(self, groww_mock):
        import groww_client as gc
        client = gc.get_groww_client()
        assert client is groww_mock
        assert client.get_ltp(["RELIANCE"], segment="CASH") == {"RELIANCE": 1234.5}

