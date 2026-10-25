#!/usr/bin/env python3
"""
Launch Elysia Verified Pilot (contained runtime + dedicated persistent store).

- Loopback UI only
- Contained disables enforced (autonomy/providers/learning workers off)
- Never attaches to an unidentified listener
- Never terminates unrelated processes when the preferred port is busy
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_PILOT_DIR = Path(__file__).resolve().parent
if str(_PILOT_DIR) not in sys.path:
    sys.path.insert(0, str(_PILOT_DIR))

from pilot_paths import (
    LAUNCH_LOG,
    PID_FILE,
    PILOT_DATA_ROOT,
    PILOT_MARKER,
    PILOT_PYTHON,
    PILOT_SOURCE_ROOT,
    PORT_SCAN_END,
    PREFERRED_UI_HOST,
    PREFERRED_UI_PORT,
    RUNTIME_DIR,
    RUNTIME_JSON,
    SOURCE_SHA,
)


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def _choose_port(host: str) -> int:
    """Prefer PREFERRED_UI_PORT; if busy, scan upward. Never kill holders."""
    if not _port_in_use(host, PREFERRED_UI_PORT):
        return PREFERRED_UI_PORT
    print(
        f"Port {PREFERRED_UI_PORT} on {host} is already in use. "
        f"Scanning {PREFERRED_UI_PORT + 1}-{PORT_SCAN_END} for a free loopback port "
        "(will not stop unidentified listeners).",
        flush=True,
    )
    for port in range(PREFERRED_UI_PORT + 1, PORT_SCAN_END + 1):
        if not _port_in_use(host, port):
            print(f"Using free port {port}.", flush=True)
            return port
    raise SystemExit(
        f"ERROR: no free loopback port in {PREFERRED_UI_PORT}-{PORT_SCAN_END}. "
        "Free a port manually, then relaunch. Refusing to attach to or kill unknown listeners."
    )


def _already_running() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        return False
    # Windows: tasklist
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        line = (out.stdout or "").strip()
        if str(pid) in line and "python" in line.lower():
            return True
    except OSError:
        pass
    return False


def main() -> int:
    if not PILOT_PYTHON.is_file():
        print(f"ERROR: interpreter missing: {PILOT_PYTHON}", file=sys.stderr)
        return 2
    if not PILOT_SOURCE_ROOT.is_dir():
        print(f"ERROR: pilot source missing: {PILOT_SOURCE_ROOT}", file=sys.stderr)
        return 2

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    (PILOT_DATA_ROOT / "logs").mkdir(parents=True, exist_ok=True)
    (PILOT_DATA_ROOT / "temp").mkdir(parents=True, exist_ok=True)
    (PILOT_DATA_ROOT / "memory").mkdir(parents=True, exist_ok=True)

    if _already_running():
        runtime = {}
        if RUNTIME_JSON.exists():
            try:
                runtime = json.loads(RUNTIME_JSON.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                runtime = {}
        port = runtime.get("ui_port", PREFERRED_UI_PORT)
        print(
            f"Pilot already running (pid file {PID_FILE}). "
            f"Open http://{PREFERRED_UI_HOST}:{port}/  — or run STOP_ELYSIA_VERIFIED_PILOT.bat first.",
            flush=True,
        )
        return 0

    host = PREFERRED_UI_HOST
    port = _choose_port(host)

    entry = PILOT_SOURCE_ROOT / "scripts" / "start_contained_browser_memory.py"
    if not entry.is_file():
        print(f"ERROR: contained entry missing: {entry}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["ELYSIA_DISPOSABLE_ROOT"] = str(PILOT_DATA_ROOT)
    env["TEMP"] = str(PILOT_DATA_ROOT / "temp")
    env["TMP"] = str(PILOT_DATA_ROOT / "temp")
    # Marker for stop-script ownership checks (no secrets)
    env["ELYSIA_PILOT_MARKER"] = PILOT_MARKER

    creationflags = 0
    if sys.platform == "win32":
        # New console so the pilot is visible and stoppable without killing the shell
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)

    cmd = [
        str(PILOT_PYTHON),
        str(entry),
        "--disposable-root",
        str(PILOT_DATA_ROOT),
        "--enable-ui",
        "--auto-start-ui",
        "--ui-host",
        host,
        "--ui-port",
        str(port),
        "--keep-alive",
    ]

    log_f = LAUNCH_LOG.open("a", encoding="utf-8")
    log_f.write(f"\n--- launch {datetime.now(timezone.utc).isoformat()} sha={SOURCE_SHA} port={port} ---\n")
    log_f.flush()

    proc = subprocess.Popen(
        cmd,
        cwd=str(PILOT_SOURCE_ROOT),
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )

    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    runtime = {
        "ok": True,
        "marker": PILOT_MARKER,
        "source_sha": SOURCE_SHA,
        "source_root": str(PILOT_SOURCE_ROOT),
        "data_root": str(PILOT_DATA_ROOT),
        "python": str(PILOT_PYTHON),
        "pid": proc.pid,
        "ui_host": host,
        "ui_port": port,
        "url": f"http://{host}:{port}/",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "security_note": (
            "Loopback contained pilot. Privileged routes gated; "
            "legacy dashboard is not claimed fully secure."
        ),
    }
    RUNTIME_JSON.write_text(json.dumps(runtime, indent=2), encoding="utf-8")

    # Wait briefly for listen (do not attach if something else is on the port)
    listening = False
    for _ in range(60):
        if proc.poll() is not None:
            print(
                f"ERROR: pilot process exited early (code {proc.returncode}). See {LAUNCH_LOG}",
                file=sys.stderr,
            )
            return 1
        if _port_in_use(host, port):
            listening = True
            break
        time.sleep(0.5)

    if not listening:
        print(
            f"ERROR: timed out waiting for {host}:{port}. "
            f"Process still running (pid {proc.pid}); use STOP script. Log: {LAUNCH_LOG}",
            file=sys.stderr,
        )
        return 1

    print(json.dumps(runtime, indent=2), flush=True)
    print(f"Pilot listening at http://{host}:{port}/", flush=True)
    print("Stop with STOP_ELYSIA_VERIFIED_PILOT.bat (pilot-owned PID only).", flush=True)

    # Open default browser to the pilot UI (loopback)
    try:
        os.startfile(f"http://{host}:{port}/")  # type: ignore[attr-defined]
    except OSError:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
