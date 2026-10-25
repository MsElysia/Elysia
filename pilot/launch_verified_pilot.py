#!/usr/bin/env python3
"""
Launch Elysia Verified Pilot (contained runtime + dedicated persistent store).

- Loopback UI only
- Contained disables enforced (autonomy/providers/learning workers off)
- Never attaches to an unidentified listener
- Never terminates unrelated processes when the preferred port is busy
- Reports application base SHA separately from delivery commit; dirty trees are not
  labeled as an exact verified delivery SHA
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_PILOT_DIR = Path(__file__).resolve().parent
if str(_PILOT_DIR) not in sys.path:
    sys.path.insert(0, str(_PILOT_DIR))

from pilot_identity import (
    expected_entry_path,
    format_identity_report,
    query_process_snapshot,
    read_delivery_identity,
    verify_live_ownership,
)
from pilot_paths import (
    APPLICATION_BASE_SHA,
    INBOX_DIR,
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
    """True only when PID file + runtime identify a live owned pilot instance."""
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        return False
    if not RUNTIME_JSON.is_file():
        return False
    try:
        runtime = json.loads(RUNTIME_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(runtime, dict):
        return False
    verdict = verify_live_ownership(pid, runtime)
    return bool(verdict.owned)


def main() -> int:
    if not PILOT_PYTHON.is_file():
        print(f"ERROR: interpreter missing: {PILOT_PYTHON}", file=sys.stderr)
        return 2
    if not PILOT_SOURCE_ROOT.is_dir():
        print(f"ERROR: pilot source missing: {PILOT_SOURCE_ROOT}", file=sys.stderr)
        return 2

    delivery = read_delivery_identity()
    print(format_identity_report(delivery), flush=True)
    if not delivery.get("exact_verified_delivery"):
        print(
            "NOTE: checkout is not an exact clean delivery SHA "
            f"(status={delivery.get('delivery_status')}). "
            "Do not treat this run as the frozen verified candidate.",
            flush=True,
        )

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    (PILOT_DATA_ROOT / "logs").mkdir(parents=True, exist_ok=True)
    (PILOT_DATA_ROOT / "temp").mkdir(parents=True, exist_ok=True)
    (PILOT_DATA_ROOT / "memory").mkdir(parents=True, exist_ok=True)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)

    # Startup inbox scan (manual/startup only — not a watcher). Before UI spawn so
    # MemoryCore is not shared with a live pilot process.
    try:
        from inbox_import import scan_inbox_to_memory

        inbox_report = scan_inbox_to_memory(apply=True, allow_while_pilot_running=True)
        print(
            f"Inbox scan: scanned={inbox_report['scanned']} "
            f"imported={inbox_report['imported']} "
            f"duplicates={inbox_report['duplicates']} "
            f"rejected={inbox_report['rejected']} "
            f"path={inbox_report['inbox_dir']}",
            flush=True,
        )
        for err in inbox_report.get("errors") or []:
            print(f"Inbox reject: {err}", flush=True)
    except Exception as exc:
        print(f"WARNING: inbox scan skipped ({exc})", flush=True)

    if _already_running():
        runtime = {}
        try:
            runtime = json.loads(RUNTIME_JSON.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            runtime = {}
        port = runtime.get("ui_port", PREFERRED_UI_PORT)
        print(
            f"Pilot already running (verified live ownership; pid file {PID_FILE}). "
            f"Open http://{PREFERRED_UI_HOST}:{port}/  — or run STOP_ELYSIA_VERIFIED_PILOT.bat first.",
            flush=True,
        )
        return 0

    # Stale PID file pointing at unrelated/dead process: clear before launch
    if PID_FILE.exists():
        print(
            "Stale or unverified PID/runtime record present; clearing before launch "
            "(refused to treat as live pilot).",
            flush=True,
        )
        PID_FILE.unlink(missing_ok=True)

    host = PREFERRED_UI_HOST
    port = _choose_port(host)

    entry = expected_entry_path()
    if not entry.is_file():
        print(f"ERROR: contained entry missing: {entry}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["ELYSIA_DISPOSABLE_ROOT"] = str(PILOT_DATA_ROOT)
    env["TEMP"] = str(PILOT_DATA_ROOT / "temp")
    env["TMP"] = str(PILOT_DATA_ROOT / "temp")
    env["ELYSIA_PILOT_MARKER"] = PILOT_MARKER

    creationflags = 0
    if sys.platform == "win32":
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
    log_f.write(
        f"\n--- launch {datetime.now(timezone.utc).isoformat()} "
        f"base={APPLICATION_BASE_SHA} delivery={delivery.get('delivery_commit')} "
        f"status={delivery.get('delivery_status')} port={port} ---\n"
    )
    log_f.flush()

    proc = subprocess.Popen(
        cmd,
        cwd=str(PILOT_SOURCE_ROOT),
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )

    # Capture live identity shortly after spawn (creation time + resolved executable)
    snap = None
    for _ in range(20):
        snap = query_process_snapshot(proc.pid)
        if snap is not None and snap.create_filetime and snap.create_filetime != "0":
            break
        time.sleep(0.1)
    if snap is None:
        print(
            f"ERROR: spawned pid {proc.pid} but could not read process identity. Aborting.",
            file=sys.stderr,
        )
        try:
            proc.terminate()
        except OSError:
            pass
        return 1

    shutdown_token = secrets.token_hex(16)
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    runtime = {
        "ok": True,
        "marker": PILOT_MARKER,
        "application_base_sha": APPLICATION_BASE_SHA,
        "delivery_commit": delivery.get("delivery_commit"),
        "delivery_status": delivery.get("delivery_status"),
        "exact_verified_delivery": bool(delivery.get("exact_verified_delivery")),
        "tracked_modifications": delivery.get("tracked_modifications") or [],
        "untracked_product_paths": delivery.get("untracked_product_paths") or [],
        # Deprecated single field — kept for older readers; equals application base only
        "source_sha": APPLICATION_BASE_SHA,
        "source_root": str(PILOT_SOURCE_ROOT),
        "data_root": str(PILOT_DATA_ROOT),
        "python": str(PILOT_PYTHON),
        "entry_point": str(entry),
        "pid": proc.pid,
        "process_create_filetime": snap.create_filetime,
        "process_executable": snap.executable,
        "command_line": snap.command_line,
        "shutdown_token": shutdown_token,
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
    print(
        "Stop with STOP_ELYSIA_VERIFIED_PILOT.bat "
        "(cooperative shutdown; hard-kill only after live identity re-check).",
        flush=True,
    )

    try:
        os.startfile(f"http://{host}:{port}/")  # type: ignore[attr-defined]
    except OSError:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
