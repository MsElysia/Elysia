#!/usr/bin/env python3
"""Stop only the Elysia Verified Pilot process recorded in the pilot PID file."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

_PILOT_DIR = Path(__file__).resolve().parent
if str(_PILOT_DIR) not in sys.path:
    sys.path.insert(0, str(_PILOT_DIR))

from pilot_paths import (
    PID_FILE,
    PILOT_MARKER,
    PREFERRED_UI_HOST,
    RUNTIME_JSON,
)


def _tasklist_line(pid: int) -> str:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        return (out.stdout or "").strip()
    except OSError:
        return ""


def _wmic_commandline(pid: int) -> str:
    """Best-effort command line for ownership check (no secrets expected)."""
    try:
        out = subprocess.run(
            [
                "wmic",
                "process",
                "where",
                f"ProcessId={pid}",
                "get",
                "CommandLine",
                "/FORMAT:LIST",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return (out.stdout or "")
    except OSError:
        return ""


def _port_in_use(host: str, port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def main() -> int:
    if not PID_FILE.exists():
        print(f"No pilot PID file at {PID_FILE}. Nothing to stop.")
        return 0

    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        print(f"ERROR: invalid PID file {PID_FILE}", file=sys.stderr)
        return 2

    runtime = {}
    if RUNTIME_JSON.exists():
        try:
            runtime = json.loads(RUNTIME_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            runtime = {}

    line = _tasklist_line(pid)
    if not line or str(pid) not in line:
        print(f"Pilot PID {pid} is not running. Cleaning runtime files.")
        PID_FILE.unlink(missing_ok=True)
        return 0

    if "python" not in line.lower():
        print(
            f"REFUSING to stop PID {pid}: tasklist does not look like python ({line!r}). "
            "Will not terminate unidentified processes.",
            file=sys.stderr,
        )
        return 3

    cmdline = _wmic_commandline(pid)
    # Ownership: must be our contained entry or carry pilot marker / data root
    owned = False
    markers = (
        "start_contained_browser_memory.py",
        PILOT_MARKER,
        "Elysia-Verified-Pilot-Data",
        "Elysia-Verified-Pilot",
    )
    if any(m.lower() in cmdline.lower() for m in markers):
        owned = True
    if runtime.get("marker") == PILOT_MARKER and runtime.get("pid") == pid:
        owned = True

    if not owned:
        print(
            f"REFUSING to stop PID {pid}: command line does not match pilot ownership. "
            "Manual review required. Will not kill unidentified processes.",
            file=sys.stderr,
        )
        return 3

    print(f"Stopping pilot-owned PID {pid}...", flush=True)
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
    time.sleep(1.5)

    still = _tasklist_line(pid)
    if still and str(pid) in still:
        print(f"ERROR: PID {pid} still present after taskkill.", file=sys.stderr)
        return 1

    port = int(runtime.get("ui_port") or 0)
    host = str(runtime.get("ui_host") or PREFERRED_UI_HOST)
    if port:
        # Wait for pilot port release only; do not touch other listeners
        for _ in range(40):
            if not _port_in_use(host, port):
                break
            time.sleep(0.25)
        print(
            f"Port {host}:{port} released={not _port_in_use(host, port)}",
            flush=True,
        )

    PID_FILE.unlink(missing_ok=True)
    print("Pilot stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
