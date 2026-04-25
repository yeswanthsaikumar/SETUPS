#!/usr/bin/env python3
"""Patch main.py to add end_date support to rs_scan_asof."""

import sys

path = "apps/web/api/main.py"
with open(path, "r") as f:
    content = f.read()

# 1. Add end_date validation block after scan_date check
old1 = (
    '    today = _date.today()\n'
    '    if sd >= today:\n'
    '        raise HTTPException(status_code=400, detail="scan_date must be in the past")\n'
    '\n'
    '    # \u2500\u2500 Load Nifty benchmark'
)
new1 = (
    '    today = _date.today()\n'
    '    if sd >= today:\n'
    '        raise HTTPException(status_code=400, detail="scan_date must be in the past")\n'
    '\n'
    '    # \u2500\u2500 end_date validation\n'
    '    end_date_str = ""\n'
    '    if end_date:\n'
    '        try:\n'
    '            ed = _date.fromisoformat(end_date)\n'
    '        except ValueError:\n'
    '            raise HTTPException(status_code=400, detail=f"Invalid end_date format: {end_date}")\n'
    '        if ed <= sd:\n'
    '            raise HTTPException(status_code=400, detail="end_date must be after scan_date")\n'
    '        end_date_str = end_date  # YYYY-MM-DD string for filtering\n'
    '\n'
    '    # \u2500\u2500 Load Nifty benchmark'
)

c1 = content.count(old1)
print(f"Validation block match count: {c1}")
if c1 >= 1:
    content = content.replace(old1, new1, 1)
    print("  Applied validation block")
else:
    # Try finding close match
    idx = content.find('scan_date must be in the past')
    print(f"  'scan_date must be in the past' found at index: {idx}")
    # Show context
    if idx > 0:
        snippet = content[idx-50:idx+200]
        print(f"  Context: {repr(snippet[:100])}")

# 2. Update Nifty return
old2 = '    # Get Nifty close on scan_date and today for benchmark return\n    nifty_scan_close = nifty_closes[cut_idx - 1] if cut_idx > 0 else nifty_closes[0]\n    nifty_now_close = nifty_closes[-1]\n    nifty_return_pct = round((nifty_now_close - nifty_scan_close) / nifty_scan_close * 100, 2) if nifty_scan_close else 0'

new2 = (
    '    # Get Nifty close on scan_date and end_date (or latest) for benchmark return\n'
    '    nifty_scan_close = nifty_closes[cut_idx - 1] if cut_idx > 0 else nifty_closes[0]\n'
    '    if end_date_str:\n'
    '        nifty_end_idx = len(nifty_dates) - 1\n'
    '        for i, d in enumerate(nifty_dates):\n'
    '            if d > end_date_str:\n'
    '                nifty_end_idx = max(0, i - 1)\n'
    '                break\n'
    '        nifty_now_close = nifty_closes[nifty_end_idx]\n'
    '    else:\n'
    '        nifty_now_close = nifty_closes[-1]\n'
    '    nifty_return_pct = round((nifty_now_close - nifty_scan_close) / nifty_scan_close * 100, 2) if nifty_scan_close else 0'
)

c2 = content.count(old2)
print(f"Nifty return match count: {c2}")
if c2 >= 1:
    content = content.replace(old2, new2, 1)
    print("  Applied Nifty return")

# 3. Update forward return in _score_one
old3 = (
    '        # \u2500\u2500 Forward return: scan_date close \u2192 current close\n'
    '        current_close = rows_full[-1]["close"] if rows_full else 0\n'
    '        current_date = rows_full[-1]["date"] if rows_full else ""\n'
    '        scan_close = last_close  # close on/before scan_date\n'
    '        fwd_return_pct = round((current_close - scan_close) / scan_close * 100, 2) if scan_close > 0 and current_close > 0 else 0\n'
    '\n'
    '        # Max gain & max drawdown since scan_date\n'
    '        fwd_rows = [r for r in rows_full if r["date"] > scan_date]'
)

new3 = (
    '        # \u2500\u2500 Forward return: scan_date close \u2192 end_date close (or latest)\n'
    '        if end_date_str:\n'
    '            end_rows = [r for r in rows_full if r["date"] <= end_date_str]\n'
    '            current_close = end_rows[-1]["close"] if end_rows else 0\n'
    '            current_date = end_rows[-1]["date"] if end_rows else ""\n'
    '        else:\n'
    '            current_close = rows_full[-1]["close"] if rows_full else 0\n'
    '            current_date = rows_full[-1]["date"] if rows_full else ""\n'
    '        scan_close = last_close  # close on/before scan_date\n'
    '        fwd_return_pct = round((current_close - scan_close) / scan_close * 100, 2) if scan_close > 0 and current_close > 0 else 0\n'
    '\n'
    '        # Max gain & max drawdown since scan_date (up to end_date if set)\n'
    '        if end_date_str:\n'
    '            fwd_rows = [r for r in rows_full if scan_date < r["date"] <= end_date_str]\n'
    '        else:\n'
    '            fwd_rows = [r for r in rows_full if r["date"] > scan_date]'
)

c3 = content.count(old3)
print(f"Forward return match count: {c3}")
if c3 >= 1:
    content = content.replace(old3, new3, 1)
    print("  Applied forward return")

with open(path, "w") as f:
    f.write(content)

print("\nDone. Verifying...")
with open(path, "r") as f:
    final = f.read()
count = final.count("end_date_str")
print(f"Total 'end_date_str' occurrences: {count}")

