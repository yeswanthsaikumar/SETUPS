"""
groww_client.py
───────────────
Shared Groww API client singleton.
Reads credentials from environment variables:
  GROWW_ACCESS_TOKEN  — direct access token
  GROWW_API_KEY       — API key (exchanged for token with secret)
  GROWW_API_SECRET    — API secret
"""
from __future__ import annotations

import os
import threading
from typing import Optional

_GROWW_API_KEY = os.environ.get("GROWW_API_KEY", "")
_GROWW_API_SECRET = os.environ.get("GROWW_API_SECRET", "")
_GROWW_ACCESS_TOKEN = os.environ.get("GROWW_ACCESS_TOKEN", "")

_client = None
_init_lock = threading.Lock()
_init_failed = False


def get_groww_client():
    """Lazy-init singleton Groww API client. Returns None if unavailable."""
    global _client, _init_failed
    if _client is not None:
        return _client
    if _init_failed:
        return None
    if not _GROWW_ACCESS_TOKEN and not _GROWW_API_KEY:
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
                    return None
            elif not token and _GROWW_API_KEY:
                token = _GROWW_API_KEY
            _client = GrowwAPI(token=token)
            return _client
        except Exception:
            _init_failed = True
            return None


def is_groww_available() -> bool:
    """Check if Groww API credentials are configured."""
    return bool(_GROWW_ACCESS_TOKEN or _GROWW_API_KEY)

