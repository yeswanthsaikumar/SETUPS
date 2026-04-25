"""One-shot local scrub: remove today-dated intraday rows from Indian caches.

Safe to run pre-close on any trading day. After running, each .NS/.BO cache's
last row will be the most recently *completed* session.
"""
import datetime
import zoneinfo
from pathlib import Path

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
today_str = datetime.datetime.now(IST).date().isoformat()

fixed = 0
scanned = 0
for p in list(Path("cache").glob("*.NS.csv")) + list(Path("cache").glob("*.BO.csv")):
    scanned += 1
    try:
        with open(p) as f:
            lines = f.readlines()
        if len(lines) < 2:
            continue
        if lines[-1].startswith(today_str + ","):
            with open(p, "w") as f:
                f.writelines(lines[:-1])
            fixed += 1
    except Exception:
        pass

print(f"Scanned {scanned} Indian caches, stripped today-dated "
      f"intraday row from {fixed}")

