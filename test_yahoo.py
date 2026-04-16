#!/usr/bin/env python3
"""Test Yahoo Finance with requests library."""
import requests
import datetime
import zoneinfo
import json

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
now = datetime.datetime.now(IST)
p1 = int(datetime.datetime(2026, 4, 1, 0, 0, 0, tzinfo=IST).timestamp())
p2 = int(now.timestamp())

url = f"https://query1.finance.yahoo.com/v8/finance/chart/TATASTEEL.NS?interval=1d&period1={p1}&period2={p2}&events=history"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

try:
    r = requests.get(url, headers=headers, timeout=20)
    print(f"Status: {r.status_code}")
    if r.ok:
        data = r.json()
        res = data.get("chart", {}).get("result", [])
        if res:
            ts = res[0].get("timestamp", [])
            closes = res[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
            print(f"Timestamps: {len(ts)}, last close: {closes[-1] if closes else None}")
            for t, c in list(zip(ts, closes))[-5:]:
                d = datetime.datetime.fromtimestamp(t, IST).date()
                print(f"  {d}: {c}")
        else:
            print("No result:", data.get("chart", {}).get("error"))
    else:
        print("Body:", r.text[:500])
except Exception as e:
    print(f"Error: {e}")

