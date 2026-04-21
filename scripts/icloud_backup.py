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
import mimetypes
import os
import shutil
import threading
import uuid
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


# ── Telegram upload ──────────────────────────────────────────────────────────

def _load_alert_config() -> dict:
    """Read persisted breakout-alert config to pick up Telegram creds."""
    # The scanner persists its AlertConfig as a flat JSON dict here.
    for name in ("breakout_alert_config.json", "alert_state.json"):
        p = TRADE_DATA_DIR / name
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        # Support both flat {telegram_bot_token:...} and nested {"config": {...}}
        if "telegram_bot_token" in data or "telegram_chat_id" in data:
            return data
        inner = data.get("config")
        if isinstance(inner, dict):
            return inner
    return {}


def _telegram_creds() -> tuple[str, str]:
    """Resolve Telegram bot token + chat id (env first, then alert config)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        cfg = _load_alert_config()
        token = token or str(cfg.get("telegram_bot_token") or "").strip()
        chat = chat or str(cfg.get("telegram_chat_id") or "").strip()
    return token, chat


def _tg_post_multipart(url: str, fields: dict, file_path: Path, timeout: int = 60) -> dict:
    """Minimal stdlib multipart/form-data POST (avoids adding a requests dep)."""
    import urllib.request
    boundary = uuid.uuid4().hex
    sep = f"--{boundary}".encode()
    body = bytearray()
    for key, val in fields.items():
        body += sep + b"\r\n"
        body += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
        body += str(val).encode() + b"\r\n"
    # file part
    mime = mimetypes.guess_type(file_path.name)[0] or "application/zip"
    body += sep + b"\r\n"
    body += (f'Content-Disposition: form-data; name="document"; '
             f'filename="{file_path.name}"\r\n').encode()
    body += f"Content-Type: {mime}\r\n\r\n".encode()
    body += file_path.read_bytes() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        url, data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def send_telegram_backup(zip_path: Path, caption: str = "") -> dict:
    """Upload a backup zip to the configured Telegram chat via sendDocument."""
    token, chat = _telegram_creds()
    if not token or not chat:
        return {"status": "not_configured",
                "reason": "No telegram_bot_token / telegram_chat_id configured "
                          "(set in Alert Center → Config, or env vars)."}
    if not zip_path.exists():
        return {"status": "error", "reason": f"File not found: {zip_path}"}
    try:
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        fields = {"chat_id": chat}
        if caption:
            fields["caption"] = caption[:1024]
        result = _tg_post_multipart(url, fields, zip_path)
        if result.get("ok"):
            return {"status": "success",
                    "message_id": result.get("result", {}).get("message_id"),
                    "bytes": zip_path.stat().st_size}
        return {"status": "error", "reason": result.get("description", "unknown")}
    except Exception as e:
        return {"status": "error", "reason": f"{type(e).__name__}: {e}"}


def run_backup(force: bool = False) -> dict:
    """Backup trade_data/ as a zip to iCloud Drive + Telegram (if configured)."""

    if not force and not _should_backup():
        state = _load_state()
        return {
            "status": "skipped",
            "reason": f"Already backed up at {state.get('last_backup', '?')}",
        }

    # Collect files
    json_files = sorted(f for f in TRADE_DATA_DIR.glob("*.json") if not f.name.startswith("."))
    if not json_files:
        return {"status": "skipped", "reason": "No JSON files in trade_data/"}

    # Always build the zip in a local temp location so Telegram upload works
    # even when iCloud Drive is not available on this machine.
    today = datetime.now().strftime("%Y-%m-%d_%H%M")
    filename = f"SETUPS_backup_{today}.zip"
    icloud_available = ICLOUD_BASE.exists()
    if icloud_available:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        zip_path = BACKUP_DIR / filename
    else:
        local_dir = TRADE_DATA_DIR / ".backups"
        local_dir.mkdir(parents=True, exist_ok=True)
        zip_path = local_dir / filename

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fpath in json_files:
                zf.write(fpath, fpath.name)
    except Exception as e:
        return {"status": "error", "reason": f"Failed to create zip: {e}"}

    size_kb = zip_path.stat().st_size / 1024
    files = [f.name for f in json_files]

    # Cleanup old iCloud backups
    if icloud_available:
        _cleanup_old_backups()

    # ── Ship to Telegram ──
    caption = (f"📦 SETUPS backup {today}\n"
               f"{len(files)} files · {size_kb:.1f} KB")
    tg_result = send_telegram_backup(zip_path, caption=caption)
    tg_status = tg_result.get("status")
    if tg_status == "success":
        print(f"📲 Telegram backup sent: {zip_path.name} "
              f"({size_kb:.1f} KB, msg #{tg_result.get('message_id')})", flush=True)
    elif tg_status == "not_configured":
        print(f"📲 Telegram backup skipped: {tg_result.get('reason')}", flush=True)
    else:
        print(f"⚠ Telegram backup failed: {tg_result.get('reason')}", flush=True)

    # If iCloud wasn't available AND telegram didn't succeed, the zip is orphaned
    # locally. Keep only the 3 most recent local fallbacks to avoid bloat.
    if not icloud_available:
        local_zips = sorted(zip_path.parent.glob("SETUPS_backup_*.zip"))
        for old in local_zips[:-3]:
            try:
                old.unlink()
            except Exception:
                pass

    # Save state
    state = {
        "last_backup": datetime.now().isoformat(timespec="seconds"),
        "method": "icloud+telegram" if icloud_available else "telegram",
        "icloud_status": "success" if icloud_available else "not_configured",
        "telegram_status": tg_status,
        "telegram_reason": tg_result.get("reason", ""),
        "files_count": len(files),
        "files": files,
        "size_kb": round(size_kb, 1),
        "backup_path": str(zip_path),
    }
    _save_state(state)
    if icloud_available:
        print(f"☁️  iCloud backup saved: {len(files)} files ({size_kb:.1f} KB) → {zip_path.name}", flush=True)

    overall = "success" if (icloud_available or tg_status == "success") else "error"
    return {"status": overall, **state}


def run_backup_background() -> None:
    """Run backup in a background thread (non-blocking)."""
    def _worker():
        try:
            result = run_backup()
            s = result.get("status")
            if s == "skipped":
                print(f"☁️  Backup: {result.get('reason', s)}", flush=True)
            elif s == "error":
                print(f"❌ Backup error: {result.get('reason', 'unknown')}", flush=True)
        except Exception as e:
            print(f"❌ Backup error: {e}", flush=True)

    t = threading.Thread(target=_worker, name="setups-backup", daemon=True)
    t.start()


def get_backup_status() -> dict:
    """Return backup state for the API."""
    state = _load_state()
    tg_token, tg_chat = _telegram_creds()
    return {
        "configured": ICLOUD_BASE.exists() or bool(tg_token and tg_chat),
        "icloud_configured": ICLOUD_BASE.exists(),
        "telegram_configured": bool(tg_token and tg_chat),
        "method": state.get("method", "icloud+telegram"),
        "last_backup": state.get("last_backup"),
        "icloud_status": state.get("icloud_status"),
        "telegram_status": state.get("telegram_status"),
        "telegram_reason": state.get("telegram_reason", ""),
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

