# US Universe Refresh - Smart Caching Guide

## Problem Solved

Previously, every run of the system would trigger a download of the US stock universe (~10,000 symbols), even if you had just run it moments ago. This was inefficient and unnecessary.

**Solution**: Smart caching with a 24-hour TTL (Time-To-Live). The system now:
- ✅ Skips refresh if the universe file is **younger than 24 hours**
- ✅ Auto-refreshes if the file is **older than 24 hours** or **missing**
- ✅ Allows manual override with `--force-us-refresh` or `--force-fetch`
- ✅ Allows complete skip with `--skip-us-refresh` or `--skip-fetch`

## Usage

### Python Runner: `run_vcp_system.py`

**Default (smart refresh)**:
```bash
python3 apps/python/cli/run_vcp_system.py
# → Skips refresh if file is fresh, downloads if older than 24h
```

**Force a fresh download**:
```bash
python3 apps/python/cli/run_vcp_system.py --force-us-refresh
# → Always downloads fresh universe
```

**Skip refresh entirely**:
```bash
python3 apps/python/cli/run_vcp_system.py --skip-us-refresh
# → Uses existing file, no download
```

### Shell Script: `full_scan.sh`

**Default (smart refresh)**:
```bash
./full_scan.sh
# → Skips fetch if file is fresh, downloads if older than 24h
```

**Force a fresh download**:
```bash
./full_scan.sh --force-fetch
# → Always downloads fresh tickers
```

**Skip fetch entirely**:
```bash
./full_scan.sh --skip-fetch
# → Uses existing file, no download
```

With other options:
```bash
./full_scan.sh --workers 8 --batch 30 --force-fetch
```

## Output

The system now tells you what it's doing:

**When skipping (fresh file)**:
```
(US universe is fresh: us_stock_tickers.csv updated 2.3h ago, skipping refresh)
```

**When downloading (missing file)**:
```
▶ Refreshing US symbol universe
   $ python3 apps/python/cli/fetch_us_stocks.py
```

**When forced**:
```
▶ Refreshing US symbol universe (--force-us-refresh)
   $ python3 apps/python/cli/fetch_us_stocks.py
```

## Why 24 Hours?

- **Short enough**: Ensures you get new IPOs and delistings at least daily
- **Long enough**: Saves bandwidth and time on typical multi-run workflows
- **Customizable**: Edit `refresh_ttl_hours` parameter in `run_vcp_system.py` if needed

## Files Involved

- `apps/python/cli/run_vcp_system.py` - Python runner with smart refresh logic
- `scripts/full_scan.sh` - Shell wrapper with smart fetch logic
- `data/universes/us_stock_tickers.csv` - Primary universe file (if available)
- `data/universes/all_us_stocks.txt` - Fallback universe file

## When to Use Each Option

| Scenario | Command |
|----------|---------|
| Daily routine, multiple runs | Default (smart refresh) ✓ |
| Need latest IPOs/delistings now | `--force-us-refresh` |
| Testing / quick iteration | `--skip-us-refresh` |
| First run / no universe yet | Default (auto-downloads) |
| Bandwidth-limited environment | `--skip-us-refresh` (bring your own file) |

## Technical Details

### Python Implementation
```python
def refresh_us_universe(skip: bool, force: bool, refresh_ttl_hours: int = 24):
    if skip:
        return  # Skip entirely
    
    if force:
        download()  # Always download
        return
    
    if file_exists and file_age < 24_hours:
        return  # File is fresh, skip
    
    download()  # File missing or stale, download now
```

### Shell Implementation
```bash
# Check file age in seconds
FILE_AGE=$(($(date +%s) - $(stat -f%m file.txt)))

# 24 hours = 86400 seconds
if [ $FILE_AGE -lt 86400 ]; then
    skip_fetch  # File is fresh
else
    download    # File is stale
fi
```

## Troubleshooting

**Q: I want to refresh every single run**
```bash
# Use --force-us-refresh flag
python3 apps/python/cli/run_vcp_system.py --force-us-refresh
```

**Q: I keep getting "file not found"**
```bash
# Remove --skip-us-refresh flag, let default smart refresh handle it
python3 apps/python/cli/run_vcp_system.py  # Not --skip-us-refresh
```

**Q: I have my own universe file**
```bash
# Pass it explicitly (skips auto-refresh)
python3 apps/python/cli/run_vcp_system.py --us-symbols my_symbols.txt --skip-us-refresh
```

**Q: How do I change the 24-hour TTL?**

Edit `run_vcp_system.py`, line 95:
```python
def refresh_us_universe(skip: bool, force: bool, refresh_ttl_hours: int = 24):
                                                                       # ↑ Change this
```

Change `24` to your desired hours (e.g., `6`, `12`, `72`).

