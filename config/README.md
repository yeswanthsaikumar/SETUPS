# Trade Data Backup — iCloud Drive

## Setup: NONE required! 🎉

Backups are saved automatically to **iCloud Drive** — zero config, zero APIs, zero tokens.

Your trade data (positions, watchlist, journal, alerts) is zipped and copied to:
```
~/Library/Mobile Documents/com~apple~CloudDocs/SETUPS_Backups/
```
Which appears in Finder as: **iCloud Drive → SETUPS_Backups**

## How it works

- Runs automatically **once per day** when the web app starts
- Keeps the **last 7 backups**, deletes older ones
- You can also trigger manually via the web UI or API

## Manual commands

```bash
# Run backup now
python3 scripts/icloud_backup.py --force

# Check status
python3 scripts/icloud_backup.py --status
```

## API endpoints

- `GET /api/backup/status` — check last backup info
- `POST /api/backup/trigger?force=true` — trigger backup manually

## Requirements

- macOS with iCloud Drive enabled (System Settings → Apple ID → iCloud → iCloud Drive)
- That's it.
