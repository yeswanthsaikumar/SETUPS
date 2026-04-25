#!/usr/bin/env python3
"""Check what Yahoo Finance has for NSE data since April 11 — full OHLCV including volume."""
import urllib.request
import json
import datetime
import zoneinfo

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
now = datetime.datetime.now(IST)

symbols = ["TATASTEEL.NS", "MTARTECH.NS", "BSE.NS"]

for sym in symbols:
    p1 = int(datetime.datetime(2026, 4, 11, 0, 0, 0, tzinfo=IST).timestamp())
    p2 = int(now.timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?interval=1d&period1={p1}&period2={p2}&events=history&includeAdjustedClose=true")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        result = data.get("chart", {}).get("result", [])
        if result:
            ts_list = result[0].get("timestamp", [])
            q = result[0].get("indicators", {}).get("quote", [{}])[0]
            opens   = q.get("open", [])
            highs   = q.get("high", [])
            lows    = q.get("low", [])
            closes  = q.get("close", [])
            volumes = q.get("volume", [])
            print(f"\n{sym}: {len(ts_list)} timestamps")
            for i, ts in enumerate(ts_list):
                d = datetime.datetime.fromtimestamp(ts, IST).date()
                o = opens[i] if i < len(opens) else None
                h = highs[i] if i < len(highs) else None
                l = lows[i] if i < len(lows) else None
                c = closes[i] if i < len(closes) else None
                v = volumes[i] if i < len(volumes) else None
                print(f"  {d}  O={o}  H={h}  L={l}  C={c}  V={v}")
                # Flag potential filter issues
                if v is None or v == 0:
                    print(f"    ⚠️  VOLUME IS {v} → will be FILTERED by Java scanner!")
        else:
            print(f"{sym}: {data.get('chart', {}).get('error', {})}")
    except Exception as e:
        print(f"{sym}: ERROR {e}")


