#!/usr/bin/env python3
"""
Trade Data Backup via iCloud Drive
────────────────────────────────────
Copies all trade_data/ JSON files as a dated zip to ~/Library/Mobile Documents/
com~apple~CloudDocs/SETUPS_Backups/ — automatically synced by iCloud.

Zero setup. No APIs, no tokens, no billing. Just works on macOS.

Runs automatically as a background thread when the web app starts.
Keeps the last 7 backups and deletes older ones.
"""

from __future__ import annotations

import json
import shutil
import threading
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[1]
TRADE_DATA_DIR = ROOT / "trade_data"
BACKUP_STATE_FILE = TRADE_DATA_DIR / ".backup_state.json"

ICLOUD_BASE = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
BACKUP_DIR = ICLOUD_BASE / "SETUPS_Backups"

BACKUP_INTERVAL_HOURS = 24
MAX_BACKUPS = 7  # keep last N zips


def _load_state() -> dict:
    if BACKUP_STATE_FILE.exists():
        try:
            return json.loads(BACKUP_STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict) -> None:
    try:
        BACKUP_STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception:
        pass


def _should_backup() -> bool:
    state = _load_state()
    last = state.get("last_backup")
    if not last:
        return True
    try:
        return datetime.now() - datetime.fromisoformat(last) > timedelta(hours=BACKUP_INTERVAL_HOURS)
    except Exception:
        return True


def _cleanup_old_backups() -> None:
    """Remove old backups, keep only the last MAX_BACKUPS."""
    if not BACKUP_DIR.exists():
        return
    zips = sorted(BACKUP_DIR.glob("SETUPS_backup_*.zip"))
    for old in zips[:-MAX_BACKUPS]:
        try:
            old.unlink()
        except Exception:
            pass


def run_backup(force: bool = False) -> dict:
    """Backup trade_data/ as a zip to iCloud Drive."""

    # Check iCloud Drive exists
    if not ICLOUD_BASE.exists():
        return {
            "status": "not_configured",
            "reason": "iCloud Drive not found. Make sure iCloud Drive is enabled in System Settings → Apple ID → iCloud → iCloud Drive.",
        }

    if not force and not _should_backup():
        state = _load_state()
        return {
            "status": "skipped",
            "reason": f"Already backed up today at {state.get('last_backup', '?')}",
        }

    # Collect files
    json_files = sorted(f for f in TRADE_DATA_DIR.glob("*.json") if not f.name.startswith("."))
    if not json_files:
        return {"status": "skipped", "reason": "No JSON files in trade_data/"}

    # Create backup dir
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Create zip
    today = datetime.now().strftime("%Y-%m-%d_%H%M")
    filename = f"SETUPS_backup_{today}.zip"
    zip_path = BACKUP_DIR / filename

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fpath in json_files:
                zf.write(fpath, fpath.name)
    except Exception as e:
        return {"status": "error", "reason": f"Failed to create zip: {e}"}

    size_kb = zip_path.stat().st_size / 1024
    files = [f.name for f in json_files]

    # Cleanup old backups
    _cleanup_old_backups()

    # Save state
    state = {
        "last_backup": datetime.now().isoformat(timespec="seconds"),
        "method": "icloud",
        "files_count": len(files),
        "files": files,
        "size_kb": round(size_kb, 1),
        "backup_path": str(zip_path),
    }
    _save_state(state)
    print(f"☁️  iCloud backup saved: {len(files)} files ({size_kb:.1f} KB) → {zip_path.name}", flush=True)
    return {"status": "success", **state}


def run_backup_background() -> None:
    """Run backup in a background thread (non-blocking)."""
    def _worker():
        try:
            result = run_backup()
            s = result["status"]
            if s in ("skipped", "not_configured"):
                print(f"☁️  Backup: {result.get('reason', s)}", flush=True)
        except Exception as e:
            print(f"❌ Backup error: {e}", flush=True)

    t = threading.Thread(target=_worker, name="icloud-backup", daemon=True)
    t.start()


def get_backup_status() -> dict:
    """Return backup state for the API."""
    state = _load_state()
    return {
        "configured": ICLOUD_BASE.exists(),
        "method": "icloud",
        "last_backup": state.get("last_backup"),
        "files_count": state.get("files_count", 0),
        "files": state.get("files", []),
        "size_kb": state.get("size_kb", 0),
        "backup_path": state.get("backup_path", ""),
    }


# ── CLI usage ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if "--force" in sys.argv:
        r = run_backup(force=True)
    elif "--status" in sys.argv:
        r = get_backup_status()
    else:
        r = run_backup()
    print(json.dumps(r, indent=2))

