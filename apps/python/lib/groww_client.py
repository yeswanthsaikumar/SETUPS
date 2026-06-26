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

# -------------------------------------------------------------------
# Credentials are read LAZILY inside _get_creds() so that:
#   1) A server restart (or reset_groww_client()) picks up a freshly
#      updated .env without needing a full process restart.
#   2) The module-level booleans (_GROWW_ONLY, _GROWW_HAS_CREDS) still
#      reflect the startup-time env so the routing logic is stable.
# -------------------------------------------------------------------
def _get_creds() -> tuple[str, str, str]:
    """Return (api_key, api_secret, access_token) from the current environment."""
    api_key       = os.environ.get("GROWW_API_KEY",       "").strip().strip("'\"")
    api_secret    = os.environ.get("GROWW_API_SECRET",    "").strip().strip("'\"")
    access_token  = os.environ.get("GROWW_ACCESS_TOKEN",  "").strip().strip("'\"")
    return api_key, api_secret, access_token


# Snapshot at import time (used only for routing / GROWW_ONLY logic)
_GROWW_API_KEY      = os.environ.get("GROWW_API_KEY",      "").strip().strip("'\"")
_GROWW_API_SECRET   = os.environ.get("GROWW_API_SECRET",   "").strip().strip("'\"")
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

# Set to True when a 403 is returned on any Groww data endpoint (live or historical).
# When True, should_use_non_groww_source() returns True so yfinance/NSE India
# take over as fallback.  Resets automatically after _GROWW_DATA_RETRY_INTERVAL
# seconds so a plan upgrade takes effect without a server restart.
_groww_data_forbidden: bool = False
_groww_data_forbidden_ts: float = 0.0
_GROWW_DATA_RETRY_INTERVAL: float = 3600.0   # re-probe Groww data every 1 h

_client = None
_client_token = None          # the access token the current client was created with
_client_token_ts: float = 0   # when the token was obtained
_client_token_exp: float = 0  # when the token expires (parsed from JWT, 0 = unknown)
_TOKEN_REFRESH_INTERVAL = 3600 * 5  # fallback refresh every 5 h if expiry unknown
_init_lock = threading.Lock()
_init_failed = False
_init_fail_ts: float = 0      # when the last init failure happened
_INIT_RETRY_INTERVAL = 60     # retry init after 60 seconds on failure
_last_error: Optional[str] = None


def mark_groww_data_forbidden():
    """Call this when any Groww data endpoint returns 403.

    Sets _groww_data_forbidden so should_use_non_groww_source() returns True,
    allowing yfinance/NSE India to handle price data.

    The flag auto-resets after _GROWW_DATA_RETRY_INTERVAL (1 h) so a plan
    upgrade (or TOTP re-auth) takes effect without a server restart.
    """
    global _groww_data_forbidden, _groww_data_forbidden_ts
    now = time.time()
    already_set = _groww_data_forbidden and (now - _groww_data_forbidden_ts) < _GROWW_DATA_RETRY_INTERVAL
    _groww_data_forbidden = True
    _groww_data_forbidden_ts = now
    if not already_set:
        print(
            "⚠ Groww data APIs returned 403 (plan does not include price data).\n"
            "  ↳ Falling back to yfinance / NSE India for OHLCV cache refresh.\n"
            "  ↳ Subscribe at developer.groww.in (₹499/mo) to use Groww as the\n"
            "    primary price-data source.  Will retry Groww after 1 h.",
            flush=True,
        )


def is_groww_data_forbidden() -> bool:
    """Return True if Groww data endpoints are currently forbidden.

    Automatically returns False (allowing a retry) after the retry interval
    elapses so that a plan upgrade is picked up without a server restart.
    """
    global _groww_data_forbidden
    if not _groww_data_forbidden:
        return False
    if (time.time() - _groww_data_forbidden_ts) >= _GROWW_DATA_RETRY_INTERVAL:
        # Retry interval elapsed — probe again
        _groww_data_forbidden = False
        print("ℹ Groww data retry window elapsed — will probe data endpoints again.", flush=True)
        return False
    return True


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

    Logic:
    • GROWW_ONLY=0 (or not set + no creds)  → always allow fallbacks.
    • GROWW_ONLY=1 AND Groww data is working → block fallbacks for Indian stocks
      so we always use the more reliable Groww price feed.
    • GROWW_ONLY=1 AND Groww data is forbidden (403, free plan) → allow fallbacks
      so yfinance/NSE India provide the OHLCV data transparently.
    """
    # If Groww data APIs are currently unavailable (e.g. free plan), allow fallbacks
    if is_groww_data_forbidden():
        return True
    if not _GROWW_ONLY:
        return True
    if is_indian_symbol(symbol):
        return False
    return True  # non-Indian: nothing else to use


def _detect_auth_type(api_key: str) -> str:
    """Detect whether the API key requires TOTP or approval-based auth.
    Returns 'totp', 'approval', or 'unknown'.
    """
    if not api_key:
        return "unknown"
    try:
        import base64, json
        parts = api_key.split('.')
        if len(parts) == 3:
            payload = parts[1] + '=' * (4 - len(parts[1]) % 4)
            decoded = json.loads(base64.b64decode(payload + '=='))
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


def _parse_token_expiry(token: str) -> float:
    """Parse the 'exp' claim from a JWT access token.
    Returns the expiry timestamp (seconds since epoch), or 0 if parsing fails.
    """
    try:
        import base64, json
        parts = token.split('.')
        if len(parts) == 3:
            payload = parts[1] + '=' * (4 - len(parts[1]) % 4)
            decoded = json.loads(base64.b64decode(payload + '=='))
            exp = decoded.get('exp', 0)
            if exp and isinstance(exp, (int, float)) and exp > time.time():
                return float(exp)
    except Exception:
        pass
    return 0.0


def _exchange_token(api_key: str, api_secret: str) -> Optional[str]:
    """Exchange API key + secret for an access token. Returns token string or None.

    Retries up to 3 times with backoff on transient connection errors.
    """
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            from growwapi import GrowwAPI
            auth_type = _detect_auth_type(api_key)

            if auth_type == 'totp':
                # Generate TOTP from the secret seed
                totp_code = _generate_totp(api_secret)
                if not totp_code:
                    print("⚠ Could not generate TOTP code from secret", flush=True)
                    return None
                print(f"🔐 Using TOTP auth (code generated)", flush=True)
                result = GrowwAPI.get_access_token(
                    api_key=api_key,
                    totp=totp_code,
                )
            else:
                # Approval-based auth
                print(f"🔐 Using approval-based auth", flush=True)
                result = GrowwAPI.get_access_token(
                    api_key=api_key,
                    secret=api_secret,
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
            err_name = type(e).__name__
            err_str = str(e)
            print(f"⚠ Groww token exchange failed: {err_name}: {err_str}", flush=True)
            # 401 = the GROWW_API_KEY session was invalidated by Groww.
            # Guide the user to refresh it.
            if "Authentication" in err_name or "401" in err_str:
                print(
                    "  ↳ Your GROWW_API_KEY session has been invalidated by Groww.\n"
                    "  ↳ Steps to fix:\n"
                    "     1. Open the Groww app / developer.groww.in\n"
                    "     2. Re-authenticate to get a fresh API key (TOTP session token)\n"
                    "     3. Update GROWW_API_KEY in your .env file\n"
                    "     4. Restart the server  (or call /api/groww/reset)",
                    flush=True,
                )
            return None
    return None


def _needs_token_refresh() -> bool:
    """Check if the current client's token should be refreshed."""
    if _client is None:
        return True
    # If we know the exact expiry, refresh 15 minutes before it expires
    if _client_token_exp > 0:
        return time.time() >= (_client_token_exp - 900)
    # Fallback: time-based interval
    if _client_token_ts and (time.time() - _client_token_ts) > _TOKEN_REFRESH_INTERVAL:
        return True
    return False


def get_groww_client():
    """Lazy-init singleton Groww API client. Returns None if unavailable.

    Automatically refreshes the access token when it's about to expire.
    Retries initialization after transient failures (60s cooldown).
    Credentials are re-read from the environment on each init attempt so
    that an updated .env + server restart (or reset_groww_client()) is
    sufficient to pick up a new GROWW_API_KEY without a full re-deploy.
    """
    global _client, _client_token, _client_token_ts, _client_token_exp
    global _init_failed, _init_fail_ts, _last_error

    # Fast path: client exists and token is fresh
    if _client is not None and not _needs_token_refresh():
        return _client

    # If init failed previously, retry after cooldown
    if _init_failed and (time.time() - _init_fail_ts) < _INIT_RETRY_INTERVAL:
        return None

    # Re-read credentials from env (picks up updates after reset/restart)
    api_key, api_secret, access_token = _get_creds()

    if not access_token and not api_key:
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
            token = access_token

            # Exchange API key + secret for access token
            if not token and api_key and api_secret:
                token = _exchange_token(api_key, api_secret)
                if not token:
                    _init_failed = True
                    _init_fail_ts = time.time()
                    _last_error = "Groww token exchange returned empty token."
                    return None
            elif not token and api_key:
                # Use API key directly (not recommended but supported)
                token = api_key

            if not token:
                _init_failed = True
                _init_fail_ts = time.time()
                _last_error = "No valid Groww token available."
                return None

            _client = GrowwAPI(token=token)
            _client_token = token
            _client_token_ts = time.time()
            # Parse real expiry from the JWT so we know exactly when to refresh
            _client_token_exp = _parse_token_expiry(token)
            _init_failed = False
            _last_error = None
            action = "refreshed" if _client_token else "initialized"
            exp_info = ""
            if _client_token_exp > 0:
                import datetime
                exp_dt = datetime.datetime.fromtimestamp(_client_token_exp)
                exp_info = f" (expires {exp_dt.strftime('%H:%M:%S')})"
            print(f"✅ Groww API client {action} (token exchange){exp_info}", flush=True)
            return _client
        except Exception as e:
            _init_failed = True
            _init_fail_ts = time.time()
            _last_error = f"{type(e).__name__}: {e}"
            print(f"⚠ Groww API init failed: {_last_error}", flush=True)
            return None


def reset_groww_client():
    """Force re-initialization on next call (e.g. after auth error).

    Credentials will be re-read from the environment, so updating .env
    and calling this function is sufficient to pick up a new GROWW_API_KEY.
    """
    global _client, _client_token, _client_token_ts, _client_token_exp, _init_failed
    with _init_lock:
        _client = None
        _client_token = None
        _client_token_ts = 0
        _client_token_exp = 0
        _init_failed = False


def is_groww_available() -> bool:
    """Check if Groww API credentials are configured."""
    api_key, api_secret, access_token = _get_creds()
    return bool(access_token or api_key)


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
        err_str  = str(e).lower()
        err_type = type(e).__name__.lower()
        is_auth  = "authentication" in err_type or "401" in err_str
        is_perm  = ("authoris" in err_type or "authoriz" in err_type
                    or "forbidden" in err_str or "403" in err_str)

        if is_perm and not is_auth:
            # 403: token is valid but the API key lacks market-data scope.
            # Do NOT reset — a fresh token will have the same permissions.
            result["error"] = (
                "Groww returned 403 Forbidden. "
                "Your API key does not have market-data permission. "
                "Enable 'Market Data' scope at developer.groww.in."
            )
        elif is_auth:
            # 401: token expired or invalidated — force re-exchange on next call
            reset_groww_client()
            result["error"] = f"Groww auth error (token refreshed, retry shortly): {e}"
        else:
            result["error"] = f"Groww probe raised {type(e).__name__}: {e}"
    return result

