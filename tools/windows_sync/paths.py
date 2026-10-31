"""Canonical Windows sync / release paths (not operational memory)."""
from __future__ import annotations

import json
import os
from pathlib import Path

# Development workspace (junction or checkout tracking integration/windows-canonical)
DEFAULT_DEV_ROOT = Path(r"C:\Users\Owner\Elysia-Dev")
# Installed verified release (updated only by promote_release after tests)
DEFAULT_RELEASE_ROOT = Path(r"C:\Users\Owner\Elysia-Windows-Release")
# Sync status / lock files — outside operational data and source trees
DEFAULT_STATE_ROOT = Path(r"C:\Users\Owner\Elysia-Sync-State")
# Previous release snapshots (source trees), not user memory
DEFAULT_RELEASE_BACKUP_ROOT = Path(r"C:\Users\Owner\guardian_backups\elysia-release-versions")
# Operational data — NEVER overwritten by sync/promote
OPERATIONAL_DATA_ROOT = Path(r"C:\Users\Owner\Elysia-Windows-Integration-Data")
PRESERVED_PILOT_ROOT = Path(r"C:\Users\Owner\Elysia-Verified-Pilot")
PRESERVED_PILOT_DATA = Path(r"C:\Users\Owner\Elysia-Verified-Pilot-Data")

CANONICAL_BRANCH = "integration/windows-canonical"
REMOTE_NAME = "origin"
GITHUB_REPO = "MsElysia/Elysia"

STATUS_FILE = "sync_status.json"
LAST_CHECK_FILE = "last_check.json"
PROMOTE_LOG = "promote_log.jsonl"


def env_path(name: str, default: Path) -> Path:
    raw = (os.environ.get(name) or "").strip()
    return Path(raw).expanduser().resolve() if raw else default.resolve()


def dev_root() -> Path:
    return env_path("ELYSIA_DEV_ROOT", DEFAULT_DEV_ROOT)


def release_root() -> Path:
    return env_path("ELYSIA_RELEASE_ROOT", DEFAULT_RELEASE_ROOT)


def state_root() -> Path:
    root = env_path("ELYSIA_SYNC_STATE_ROOT", DEFAULT_STATE_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root


def release_backup_root() -> Path:
    root = env_path("ELYSIA_RELEASE_BACKUP_ROOT", DEFAULT_RELEASE_BACKUP_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root


def status_path() -> Path:
    return state_root() / STATUS_FILE


def load_json(path: Path, default: dict | None = None) -> dict:
    if not path.is_file():
        return dict(default or {})
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(default or {})


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
