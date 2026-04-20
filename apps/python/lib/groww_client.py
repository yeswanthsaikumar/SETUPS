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
import time
import threading
from typing import Optional

_GROWW_API_KEY = os.environ.get("GROWW_API_KEY", "").strip().strip("'\"")
_GROWW_API_SECRET = os.environ.get("GROWW_API_SECRET", "").strip().strip("'\"")
_GROWW_ACCESS_TOKEN = os.environ.get("GROWW_ACCESS_TOKEN", "").strip().strip("'\"")

# Groww-only mode: when ON, Indian stocks ONLY use Groww (no Yahoo/NSE fallback).
# Auto-detected: ON only when Groww credentials are present AND user hasn't set GROWW_ONLY=0.
# If no Groww credentials → always allow fallbacks regardless of env var.
_GROWW_ONLY_ENV = os.environ.get("GROWW_ONLY", "").strip().lower()
_GROWW_HAS_CREDS = bool(_GROWW_ACCESS_TOKEN or _GROWW_API_KEY)
if _GROWW_ONLY_ENV in ("0", "false", "no", "off"):
    _GROWW_ONLY = False
elif _GROWW_ONLY_ENV in ("1", "true", "yes", "on"):
    _GROWW_ONLY = _GROWW_HAS_CREDS  # only enforce if creds exist
else:
    # Not explicitly set → auto: enable only when credentials are available
    _GROWW_ONLY = _GROWW_HAS_CREDS

_client = None
_client_token = None          # the access token the current client was created with
_client_token_ts: float = 0   # when the token was obtained
_TOKEN_REFRESH_INTERVAL = 3600 * 5  # refresh every 5 hours (tokens typically last ~6h)
_init_lock = threading.Lock()
_init_failed = False
_init_fail_ts: float = 0      # when the last init failure happened
_INIT_RETRY_INTERVAL = 60     # retry init after 60 seconds on failure
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
    """
    if not _GROWW_ONLY:
        return True
    if is_indian_symbol(symbol):
        return False
    return True  # non-Indian: nothing else to use


def _detect_auth_type() -> str:
    """Detect whether the API key requires TOTP or approval-based auth.
    Returns 'totp', 'approval', or 'unknown'.
    """
    if not _GROWW_API_KEY:
        return "unknown"
    try:
        import base64, json
        parts = _GROWW_API_KEY.split('.')
        if len(parts) == 3:
            payload = parts[1] + '=' * (4 - len(parts[1]) % 4)
            decoded = json.loads(base64.b64decode(payload))
            sub = decoded.get('sub', '')
            if sub:
                sub_data = json.loads(sub)
                role = sub_data.get('role', '')
                if 'totp' in role.lower():
                    return 'totp'
                if 'approval' in role.lower():
                    return 'approval'
    except Exception:
        pass
    return "unknown"


def _generate_totp(secret_seed: str) -> Optional[str]:
    """Generate a TOTP code from a base32-encoded secret seed."""
    try:
        import hmac, hashlib, struct, time as _time, base64
        # Clean up the secret
        secret_seed = secret_seed.strip().upper().replace(' ', '')
        # Pad to multiple of 8
        missing_padding = len(secret_seed) % 8
        if missing_padding:
            secret_seed += '=' * (8 - missing_padding)
        key = base64.b32decode(secret_seed)
        # TOTP: counter = floor(time / 30)
        counter = int(_time.time()) // 30
        msg = struct.pack('>Q', counter)
        hmac_hash = hmac.new(key, msg, hashlib.sha1).digest()
        offset = hmac_hash[-1] & 0x0F
        code = struct.unpack('>I', hmac_hash[offset:offset + 4])[0]
        code = (code & 0x7FFFFFFF) % 1000000
        return f"{code:06d}"
    except Exception as e:
        print(f"⚠ TOTP generation failed: {type(e).__name__}: {e}", flush=True)
        return None


def _exchange_token() -> Optional[str]:
    """Exchange API key + secret for an access token. Returns token string or None.

    Retries up to 3 times with backoff on transient connection errors.
    """
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            from growwapi import GrowwAPI
            auth_type = _detect_auth_type()

            if auth_type == 'totp':
                # Generate TOTP from the secret seed
                totp_code = _generate_totp(_GROWW_API_SECRET)
                if not totp_code:
                    print("⚠ Could not generate TOTP code from secret", flush=True)
                    return None
                print(f"🔐 Using TOTP auth (code generated)", flush=True)
                result = GrowwAPI.get_access_token(
                    api_key=_GROWW_API_KEY,
                    totp=totp_code,
                )
            else:
                # Approval-based auth
                print(f"🔐 Using approval-based auth", flush=True)
                result = GrowwAPI.get_access_token(
                    api_key=_GROWW_API_KEY,
                    secret=_GROWW_API_SECRET,
                )

            if isinstance(result, str) and result:
                return result
            elif isinstance(result, dict):
                return (result.get("accessToken")
                        or result.get("access_token")
                        or result.get("token", "")) or None
        except (ConnectionError, ConnectionResetError, OSError) as e:
            print(f"⚠ Groww token exchange attempt {attempt}/{max_retries} failed: {type(e).__name__}: {e}", flush=True)
            if attempt < max_retries:
                time.sleep(2 ** attempt)  # 2s, 4s backoff
                continue
            return None
        except Exception as e:
            print(f"⚠ Groww token exchange failed: {type(e).__name__}: {e}", flush=True)
            return None
    return None


def _needs_token_refresh() -> bool:
    """Check if the current client's token should be refreshed."""
    if _client is None:
        return True
    if _client_token_ts and (time.time() - _client_token_ts) > _TOKEN_REFRESH_INTERVAL:
        return True
    return False


def get_groww_client():
    """Lazy-init singleton Groww API client. Returns None if unavailable.

    Automatically refreshes the access token when it's about to expire.
    Retries initialization after transient failures (60s cooldown).
    """
    global _client, _client_token, _client_token_ts, _init_failed, _init_fail_ts, _last_error

    # Fast path: client exists and token is fresh
    if _client is not None and not _needs_token_refresh():
        return _client

    # If init failed previously, retry after cooldown
    if _init_failed and (time.time() - _init_fail_ts) < _INIT_RETRY_INTERVAL:
        return None

    if not _GROWW_ACCESS_TOKEN and not _GROWW_API_KEY:
        _last_error = ("No Groww credentials set. Export GROWW_ACCESS_TOKEN "
                       "(preferred) or GROWW_API_KEY+GROWW_API_SECRET.")
        return None

    with _init_lock:
        # Re-check after acquiring lock
        if _client is not None and not _needs_token_refresh():
            return _client
        if _init_failed and (time.time() - _init_fail_ts) < _INIT_RETRY_INTERVAL:
            return None

        try:
            from growwapi import GrowwAPI
            token = _GROWW_ACCESS_TOKEN

            # Exchange API key + secret for access token
            if not token and _GROWW_API_KEY and _GROWW_API_SECRET:
                token = _exchange_token()
                if not token:
                    _init_failed = True
                    _init_fail_ts = time.time()
                    _last_error = "Groww token exchange returned empty token."
                    return None
            elif not token and _GROWW_API_KEY:
                # Use API key directly (not recommended but supported)
                token = _GROWW_API_KEY

            if not token:
                _init_failed = True
                _init_fail_ts = time.time()
                _last_error = "No valid Groww token available."
                return None

            _client = GrowwAPI(token=token)
            _client_token = token
            _client_token_ts = time.time()
            _init_failed = False
            _last_error = None
            action = "refreshed" if _client_token else "initialized"
            print(f"✅ Groww API client {action} (token exchange)", flush=True)
            return _client
        except Exception as e:
            _init_failed = True
            _init_fail_ts = time.time()
            _last_error = f"{type(e).__name__}: {e}"
            print(f"⚠ Groww API init failed: {_last_error}", flush=True)
            return None


def reset_groww_client():
    """Force re-initialization on next call (e.g. after auth error)."""
    global _client, _client_token, _client_token_ts, _init_failed
    with _init_lock:
        _client = None
        _client_token = None
        _client_token_ts = 0
        _init_failed = False


def is_groww_available() -> bool:
    """Check if Groww API credentials are configured."""
    return bool(_GROWW_ACCESS_TOKEN or _GROWW_API_KEY)


def verify_groww_live(probe_symbol: str = "RELIANCE") -> dict:
    """End-to-end health check: init client, fetch a known-good LTP."""
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
        err_str = str(e).lower()
        if "forbidden" in err_str or "authoris" in err_str or "unauthori" in err_str:
            # Token expired or invalid — force refresh on next call
            reset_groww_client()
            result["error"] = f"Groww auth error (will retry): {e}"
        else:
            result["error"] = f"Groww probe raised {type(e).__name__}: {e}"
    return result

