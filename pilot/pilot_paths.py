"""Absolute paths for the Elysia Verified Pilot installation (Windows)."""
from __future__ import annotations

from pathlib import Path

# Source checkout (this repo / worktree)
PILOT_SOURCE_ROOT = Path(r"C:\Users\Owner\Elysia-Verified-Pilot").resolve()

# Persistent store OUTSIDE the source checkout
PILOT_DATA_ROOT = Path(r"C:\Users\Owner\Elysia-Verified-Pilot-Data").resolve()

# Verified interpreter (read-only use; do not modify this venv from the pilot)
PILOT_PYTHON = Path(r"C:\Users\Owner\Project guardian\.venv\Scripts\python.exe").resolve()

PREFERRED_UI_HOST = "127.0.0.1"
PREFERRED_UI_PORT = 5065
PORT_SCAN_END = 5085

RUNTIME_DIR = PILOT_DATA_ROOT / "runtime"
PID_FILE = RUNTIME_DIR / "pilot.pid"
RUNTIME_JSON = RUNTIME_DIR / "pilot.runtime.json"
LAUNCH_LOG = PILOT_DATA_ROOT / "logs" / "pilot-launch.log"

SOURCE_SHA = "6b03b7d645e092c336564fb65bf2d5339a047c8e"
PILOT_MARKER = "elysia-verified-pilot"
