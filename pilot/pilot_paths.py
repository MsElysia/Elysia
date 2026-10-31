"""Absolute paths and SHA identity for the Elysia Verified Pilot installation (Windows)."""
from __future__ import annotations

import os
from pathlib import Path

# This checkout. The frozen pilot at Elysia-Verified-Pilot is left untouched.
PILOT_SOURCE_ROOT = Path(__file__).resolve().parents[1]

# Durable store outside source, and outside the already-running verified-pilot data.
# Optional ELYSIA_PILOT_DATA_ROOT enables isolated RC/acceptance stores without
# changing the default production path. Never invent a remote or cloud root.
_DEFAULT_PILOT_DATA_ROOT = Path(r"C:\Users\Owner\Elysia-Windows-Integration-Data")
_data_override = (os.environ.get("ELYSIA_PILOT_DATA_ROOT") or "").strip()
PILOT_DATA_ROOT = (
    Path(_data_override).expanduser().resolve()
    if _data_override
    else _DEFAULT_PILOT_DATA_ROOT.resolve()
)

# Verified interpreter (read-only use; do not modify this venv from the pilot)
PILOT_PYTHON = Path(r"C:\Users\Owner\Project guardian\.venv\Scripts\python.exe").resolve()

PREFERRED_UI_HOST = "127.0.0.1"
_port_override = (os.environ.get("ELYSIA_PREFERRED_UI_PORT") or "").strip()
PREFERRED_UI_PORT = int(_port_override) if _port_override.isdigit() else 5065
PORT_SCAN_END = 5085

RUNTIME_DIR = PILOT_DATA_ROOT / "runtime"
PID_FILE = RUNTIME_DIR / "pilot.pid"
RUNTIME_JSON = RUNTIME_DIR / "pilot.runtime.json"
SHUTDOWN_REQUEST_FILE = RUNTIME_DIR / "shutdown.request"
LAUNCH_LOG = PILOT_DATA_ROOT / "logs" / "pilot-launch.log"

# Operator drop folder for .txt/.md inbox import (outside source checkout).
# Startup/manual scan only — not a background watcher or browser upload.
INBOX_DIR = PILOT_DATA_ROOT / "inbox"
INBOX_STATE_DIR = PILOT_DATA_ROOT / "inbox_state"
INBOX_MANIFEST = INBOX_STATE_DIR / "import_manifest.jsonl"
INBOX_SUPPORTED_EXTENSIONS = frozenset({".txt", ".md"})

# Application product base (contained browser-memory candidate), NOT the pilot delivery commit.
APPLICATION_BASE_SHA = "6b03b7d645e092c336564fb65bf2d5339a047c8e"
# Back-compat alias — prefer APPLICATION_BASE_SHA in new code.
SOURCE_SHA = APPLICATION_BASE_SHA

_marker_override = (os.environ.get("ELYSIA_PILOT_MARKER") or "").strip()
PILOT_MARKER = _marker_override or "elysia-verified-pilot"
