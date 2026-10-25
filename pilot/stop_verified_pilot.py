#!/usr/bin/env python3
"""
Stop only a verified Elysia Verified Pilot instance.

A PID or runtime-record match alone never authorizes termination.
Prefer authenticated cooperative shutdown (shutdown.request + Ctrl+C).
Hard-kill fallback re-verifies live process identity and kills that PID only
(no process-tree /T). Uncertain ownership and PID reuse are refused.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_PILOT_DIR = Path(__file__).resolve().parent
if str(_PILOT_DIR) not in sys.path:
    sys.path.insert(0, str(_PILOT_DIR))

from pilot_identity import (
    clear_shutdown_request,
    load_runtime_record,
    query_process_snapshot,
    send_ctrl_c,
    taskkill_pid_only,
    verify_live_ownership,
    write_shutdown_request,
)
from pilot_paths import (
    PID_FILE,
    PREFERRED_UI_HOST,
    RUNTIME_JSON,
)


def _port_in_use(host: str, port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def _cleanup_stale_records() -> None:
    PID_FILE.unlink(missing_ok=True)
    # Keep runtime.json for audit unless explicitly removed by successful stop
    clear_shutdown_request()


def main() -> int:
    if not PID_FILE.exists():
        print(f"No pilot PID file at {PID_FILE}. Nothing to stop.")
        clear_shutdown_request()
        return 0

    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        print(f"ERROR: invalid PID file {PID_FILE}", file=sys.stderr)
        return 2

    runtime, runtime_err = load_runtime_record(RUNTIME_JSON)
    if runtime_err:
        # Malformed/missing identity record: if process is gone, clean PID only.
        snap = query_process_snapshot(pid)
        if snap is None:
            print(
                f"Pilot PID {pid} is not running; runtime unusable ({runtime_err}). "
                "Cleaning PID file only."
            )
            PID_FILE.unlink(missing_ok=True)
            clear_shutdown_request()
            return 0
        print(
            f"REFUSING to stop PID {pid}: {runtime_err}. "
            "Will not terminate without a complete identity record.",
            file=sys.stderr,
        )
        return 3

    assert runtime is not None
    snap = query_process_snapshot(pid)
    if snap is None:
        print(f"Pilot PID {pid} is not running. Cleaning runtime files.")
        PID_FILE.unlink(missing_ok=True)
        clear_shutdown_request()
        return 0

    verdict = verify_live_ownership(pid, runtime, snapshot=snap)
    if not verdict.owned:
        print(
            f"REFUSING to stop PID {pid}: {verdict.reason}. "
            "Manual review required. Will not kill unidentified or reused PIDs.",
            file=sys.stderr,
        )
        return 3

    token = str(runtime.get("shutdown_token") or "")
    print(f"Verified pilot ownership for PID {pid}. Requesting cooperative shutdown...", flush=True)
    write_shutdown_request(token)
    ctrl_ok, ctrl_msg = send_ctrl_c(pid)
    print(f"Cooperative Ctrl+C: ok={ctrl_ok} ({ctrl_msg})", flush=True)

    # Wait for voluntary exit
    exited = False
    for _ in range(40):
        if query_process_snapshot(pid) is None:
            exited = True
            break
        time.sleep(0.25)

    if not exited:
        # Re-verify before any hard kill — refuse if identity drifted (PID reuse mid-wait)
        snap2 = query_process_snapshot(pid)
        if snap2 is None:
            exited = True
        else:
            verdict2 = verify_live_ownership(pid, runtime, snapshot=snap2)
            if not verdict2.owned:
                print(
                    f"REFUSING hard-kill for PID {pid}: ownership no longer verified "
                    f"({verdict2.reason}).",
                    file=sys.stderr,
                )
                clear_shutdown_request()
                return 3
            print(
                f"Cooperative shutdown timed out; hard-killing verified PID {pid} only (no tree)...",
                flush=True,
            )
            taskkill_pid_only(pid)
            time.sleep(1.0)
            if query_process_snapshot(pid) is not None:
                print(f"ERROR: PID {pid} still present after taskkill.", file=sys.stderr)
                clear_shutdown_request()
                return 1
            exited = True

    port = int(runtime.get("ui_port") or 0)
    host = str(runtime.get("ui_host") or PREFERRED_UI_HOST)
    if port:
        for _ in range(40):
            if not _port_in_use(host, port):
                break
            time.sleep(0.25)
        print(
            f"Port {host}:{port} released={not _port_in_use(host, port)}",
            flush=True,
        )

    PID_FILE.unlink(missing_ok=True)
    clear_shutdown_request()
    # Retain runtime.json with stopped marker for audit
    runtime["stopped_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    runtime["stop_ok"] = True
    try:
        RUNTIME_JSON.write_text(json.dumps(runtime, indent=2), encoding="utf-8")
    except OSError:
        pass
    print("Pilot stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
