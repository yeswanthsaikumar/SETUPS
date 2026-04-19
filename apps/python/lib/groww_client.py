"""
groww_client.py
───────────────
Shared Groww API client singleton.
Reads credentials from environment variables:
  GROWW_ACCESS_TOKEN  — direct access token
  GROWW_API_KEY       — API key (exchanged for token with secret)
  GROWW_API_SECRET    — API secret
  GROWW_ONLY          — "1" (default) means: for Indian stocks (.NS/.BO),
                        NEVER fall back to yfinance / NSE / Yahoo. If Groww
                        fails, data is reported missing (so the user knows
                        to fix credentials) instead of silently using a
                        blocked external source.
                        Set GROWW_ONLY=0 to restore the legacy multi-source
                        chain.
"""
from __future__ import annotations

import os
import threading
from typing import Optional

_GROWW_API_KEY = os.environ.get("GROWW_API_KEY", "")
_GROWW_API_SECRET = os.environ.get("GROWW_API_SECRET", "")
_GROWW_ACCESS_TOKEN = os.environ.get("GROWW_ACCESS_TOKEN", "")

# Groww-only mode is ON by default. Disable by setting GROWW_ONLY=0.
_GROWW_ONLY = os.environ.get("GROWW_ONLY", "1").strip().lower() not in ("0", "false", "no", "off", "")

_client = None
_init_lock = threading.Lock()
_init_failed = False
_last_error: Optional[str] = None


def groww_only_mode() -> bool:
    """Return True if Groww-only enforcement is active."""
    return _GROWW_ONLY


def is_indian_symbol(symbol: str) -> bool:
    """Return True for NSE/BSE stocks. Groww only serves these."""
    if not symbol:
        return False
    s = symbol.upper()
    return s.endswith(".NS") or s.endswith(".BO")


def should_use_non_groww_source(symbol: str) -> bool:
    """Central gate used by every data fetcher.

    Returns True  → caller may try yfinance / NSE / Yahoo / screener etc.
    Returns False → caller must NOT use any external source other than Groww.

    Rule:
      * When GROWW_ONLY mode is on AND the symbol is Indian (.NS/.BO):
        external sources other than Groww are forbidden. Data must come
        from Groww or not at all — this prevents silently pulling from
        geo-blocked Yahoo/NSE that break when VPN is off or misconfigured.
      * For non-Indian symbols (e.g. US), Groww cannot serve them, so
        fallbacks are always allowed (they have no alternative).
      * When GROWW_ONLY mode is off, all fallbacks are allowed (legacy).
    """
    if not _GROWW_ONLY:
        return True
    if is_indian_symbol(symbol):
        return False
    return True  # non-Indian: nothing else to use


def get_groww_client():
    """Lazy-init singleton Groww API client. Returns None if unavailable."""
    global _client, _init_failed, _last_error
    if _client is not None:
        return _client
    if _init_failed:
        return None
    if not _GROWW_ACCESS_TOKEN and not _GROWW_API_KEY:
        _last_error = ("No Groww credentials set. Export GROWW_ACCESS_TOKEN "
                       "(preferred) or GROWW_API_KEY+GROWW_API_SECRET.")
        return None
    with _init_lock:
        if _client is not None:
            return _client
        if _init_failed:
            return None
        try:
            from growwapi import GrowwAPI
            token = _GROWW_ACCESS_TOKEN
            if not token and _GROWW_API_KEY and _GROWW_API_SECRET:
                result = GrowwAPI.get_access_token(
                    api_key=_GROWW_API_KEY,
                    secret=_GROWW_API_SECRET,
                )
                if isinstance(result, str) and result:
                    token = result
                elif isinstance(result, dict):
                    token = (result.get("accessToken")
                             or result.get("access_token")
                             or result.get("token", ""))
                if not token:
                    _init_failed = True
                    _last_error = "Groww token exchange returned empty token."
                    return None
            elif not token and _GROWW_API_KEY:
                token = _GROWW_API_KEY
            _client = GrowwAPI(token=token)
            _last_error = None
            return _client
        except Exception as e:
            _init_failed = True
            _last_error = f"{type(e).__name__}: {e}"
            return None


def is_groww_available() -> bool:
    """Check if Groww API credentials are configured."""
    return bool(_GROWW_ACCESS_TOKEN or _GROWW_API_KEY)


def verify_groww_live(probe_symbol: str = "RELIANCE") -> dict:
    """End-to-end health check: init client, fetch a known-good LTP.

    Returns a dict the UI can render:
      {
        "ok": bool,
        "mode_groww_only": bool,
        "credentials_set": bool,
        "client_initialized": bool,
        "probe_symbol": str,
        "probe_price": float | None,
        "error": str | None,
      }
    """
    result = {
        "ok": False,
        "mode_groww_only": _GROWW_ONLY,
        "credentials_set": is_groww_available(),
        "client_initialized": False,
        "probe_symbol": probe_symbol,
        "probe_price": None,
        "error": None,
    }
    if not result["credentials_set"]:
        result["error"] = ("No Groww credentials. Set GROWW_ACCESS_TOKEN "
                           "(or GROWW_API_KEY + GROWW_API_SECRET) in the "
                           "environment and restart.")
        return result

    client = get_groww_client()
    if client is None:
        result["error"] = _last_error or "Groww client failed to initialize."
        return result
    result["client_initialized"] = True

    try:
        from growwapi import GrowwAPI
        exchange_sym = f"NSE_{probe_symbol}"
        ltp_data = client.get_ltp(
            exchange_trading_symbols=(exchange_sym,),
            segment=GrowwAPI.SEGMENT_CASH,
            timeout=8,
        )
        ltp = None
        if isinstance(ltp_data, dict):
            raw = ltp_data.get(exchange_sym)
            if isinstance(raw, (int, float)) and raw > 0:
                ltp = float(raw)
            elif isinstance(raw, dict):
                v = raw.get("ltp") or raw.get("lastPrice")
                if v:
                    ltp = float(v)
        if ltp and ltp > 0:
            result["ok"] = True
            result["probe_price"] = ltp
        else:
            result["error"] = ("Groww returned no LTP for the probe symbol. "
                               "Token may be expired or rate-limited.")
    except Exception as e:
        result["error"] = f"Groww probe raised {type(e).__name__}: {e}"
    return result


