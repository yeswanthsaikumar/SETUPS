#!/usr/bin/env python3
"""Quick test of Groww API connectivity."""
import os, sys, base64, json, datetime

# Load .env manually
with open(os.path.join(os.path.dirname(__file__), '.env')) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip()

key = os.environ.get('GROWW_API_KEY', '')
secret = os.environ.get('GROWW_API_SECRET', '')
access_token = os.environ.get('GROWW_ACCESS_TOKEN', '')

print(f"API Key length: {len(key)}")
print(f"Secret length: {len(secret)}")
print(f"Access Token length: {len(access_token)}")

# Decode JWT payload
if key:
    parts = key.split('.')
    if len(parts) == 3:
        payload = parts[1] + '=' * (4 - len(parts[1]) % 4)
        decoded = json.loads(base64.b64decode(payload))
        exp = decoded.get('exp')
        iat = decoded.get('iat')
        print(f"\nJWT expires: {datetime.datetime.fromtimestamp(exp) if exp else 'N/A'}")
        print(f"JWT issued:  {datetime.datetime.fromtimestamp(iat) if iat else 'N/A'}")
        sub = decoded.get('sub', '')
        if sub:
            try:
                sub_data = json.loads(sub)
                print(f"Role: {sub_data.get('role')}")
                print(f"Vendor: {sub_data.get('vendorName')}")
            except:
                pass

from growwapi import GrowwAPI

# Test 1: Token exchange (api_key + secret -> access_token)
print("\n--- Test 1: Token Exchange ---")
try:
    token = GrowwAPI.get_access_token(api_key=key, secret=secret)
    print(f"SUCCESS! Access token: {str(token)[:80]}...")

    # Use the exchanged token
    client = GrowwAPI(token=token)
    result = client.get_ltp(
        exchange_trading_symbols=('NSE_RELIANCE',),
        segment=GrowwAPI.SEGMENT_CASH,
        timeout=10,
    )
    print(f"LTP with exchanged token: {result}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")

# Test 2: Use API key directly as token
print("\n--- Test 2: API Key as Token ---")
try:
    client = GrowwAPI(token=key)
    result = client.get_ltp(
        exchange_trading_symbols=('NSE_RELIANCE',),
        segment=GrowwAPI.SEGMENT_CASH,
        timeout=10,
    )
    print(f"LTP result: {result}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")

# Test 3: Try OHLC
print("\n--- Test 3: OHLC ---")
try:
    client = GrowwAPI(token=key)
    result = client.get_ohlc(
        exchange_trading_symbols=('NSE_RELIANCE',),
        segment=GrowwAPI.SEGMENT_CASH,
        timeout=10,
    )
    print(f"OHLC result: {result}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")

