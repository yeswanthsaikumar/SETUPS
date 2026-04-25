#!/usr/bin/env python3
"""Debug Groww token exchange."""
import os, sys, uuid, requests

# Load .env
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip().strip("'\"")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'apps', 'python', 'lib'))
from groww_client import _GROWW_API_KEY, _GROWW_API_SECRET, _generate_totp

totp = _generate_totp(_GROWW_API_SECRET)
print(f'TOTP: {totp}')

url = 'https://api.groww.in/v1/token/api/access'
headers = {
    'x-request-id': str(uuid.uuid4()),
    'Authorization': 'Bearer ' + _GROWW_API_KEY,
    'Content-Type': 'application/json',
    'x-client-id': 'growwapi',
    'x-client-platform': 'growwapi-python-client',
    'x-client-platform-version': '1.5.0',
    'x-api-version': '1.0',
}
data = {'key_type': 'totp', 'totp': totp}
print(f'Request data: {data}')

resp = requests.post(url, headers=headers, json=data, timeout=15)
print(f'Status: {resp.status_code}')
print(f'Response: {resp.text[:500]}')

if resp.ok:
    token = resp.json().get('token', '')
    print(f'\nAccess token: {token[:80]}...')
    # Try LTP with the token
    from growwapi import GrowwAPI
    client = GrowwAPI(token=token)
    result = client.get_ltp(
        exchange_trading_symbols=('NSE_RELIANCE',),
        segment=GrowwAPI.SEGMENT_CASH, timeout=10)
    print(f'LTP: {result}')

