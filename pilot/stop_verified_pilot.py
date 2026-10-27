#!/usr/bin/env python3
"""
Stop only a handle-verified Elysia Verified Pilot instance.

PID/runtime-marker match alone never authorizes termination.
Prefer cooperative shutdown.request (polled by owned runtime). Hard termination
uses the same OpenProcess handle that passed verification — never a fresh
numeric-PID taskkill after a reuse window. Uncertain absence/ownership fails closed.
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
    send_ctrl_c,
    verify_live_ownership,
    write_shutdown_request,
)
from pilot_paths import (
    PID_FILE,
    PREFERRED_UI_HOST,
    RUNTIME_JSON,
)
from pilot_winprocess import BoundProcess


def _port_in_use(host: str, port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


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
        bound, berr = BoundProcess.open(pid)
        if berr == "not_found":
            print(
                f"Pilot PID {pid} is not running; runtime unusable ({runtime_err}). "
                "Cleaning PID file only."
            )
            PID_FILE.unlink(missing_ok=True)
            clear_shutdown_request()
            return 0
        if bound is not None:
            bound.close()
        print(
            f"REFUSING to stop PID {pid}: {runtime_err} "
            f"(process_open={berr or 'open'}). "
            "Will not terminate without a complete identity record.",
            file=sys.stderr,
        )
        return 3

    assert runtime is not None

    # Bind OS handle FIRST — all subsequent actions use this handle.
    bound, berr = BoundProcess.open(pid)
    if berr == "not_found":
        print(f"Pilot PID {pid} is not running (OpenProcess not_found). Cleaning runtime files.")
        PID_FILE.unlink(missing_ok=True)
        clear_shutdown_request()
        return 0
    if bound is None:
        print(
            f"REFUSING to stop PID {pid}: cannot establish process handle ({berr}). "
            "Uncertain ownership — not treating as absent.",
            file=sys.stderr,
        )
        return 3

    try:
        # Cross-check recorded creation time against handle before ownership verdict
        if not bound.refresh_times_match(str(runtime.get("process_create_filetime") or "")):
            print(
                f"REFUSING to stop PID {pid}: handle creation time does not match runtime "
                "(stale or reused PID).",
                file=sys.stderr,
            )
            return 3

        verdict = verify_live_ownership(pid, runtime, bound=bound)
        # verify_live_ownership may close bound on failure; re-check
        if not verdict.owned:
            print(
                f"REFUSING to stop PID {pid}: {verdict.reason}. "
                "Manual review required.",
                file=sys.stderr,
            )
            return 3

        # Prefer the bound returned/retained by verify; fall back to our handle
        action_bound = verdict.bound if verdict.bound is not None else bound
        bound = None  # ownership transferred

        token = str(runtime.get("shutdown_token") or "")
        print(
            f"Verified pilot ownership for PID {pid} via process handle. "
            "Requesting cooperative shutdown...",
            flush=True,
        )
        write_shutdown_request(token)
        # Optional console signal (runtime must also poll shutdown.request)
        ctrl_ok, ctrl_msg = send_ctrl_c(pid)
        print(f"Cooperative Ctrl+C: ok={ctrl_ok} ({ctrl_msg})", flush=True)

        exited = action_bound.wait(timeout_ms=15000)
        if not exited and action_bound.is_still_running():
            print(
                "Cooperative shutdown timed out; terminating via verified process handle "
                "(not numeric PID taskkill)...",
                flush=True,
            )
            tok, tmsg = action_bound.terminate()
            print(f"Handle terminate: ok={tok} ({tmsg})", flush=True)
            if not tok:
                print(
                    f"REFUSING success: safe termination could not be established ({tmsg}).",
                    file=sys.stderr,
                )
                clear_shutdown_request()
                return 3
            exited = action_bound.wait(timeout_ms=10000)

        if not exited and action_bound.is_still_running():
            print(
                f"ERROR: PID {pid} still running after handle terminate. "
                "Reporting failure; not claiming stop_ok.",
                file=sys.stderr,
            )
            clear_shutdown_request()
            return 1

        port = int(runtime.get("ui_port") or 0)
        host = str(runtime.get("ui_host") or PREFERRED_UI_HOST)
        port_released = True
        if port:
            port_released = False
            for _ in range(40):
                if not _port_in_use(host, port):
                    port_released = True
                    break
                time.sleep(0.25)
            print(f"Port {host}:{port} released={port_released}", flush=True)
            if not port_released:
                print(
                    f"ERROR: process exited but port {host}:{port} still listening. "
                    "Not claiming successful stop.",
                    file=sys.stderr,
                )
                clear_shutdown_request()
                return 1

        PID_FILE.unlink(missing_ok=True)
        clear_shutdown_request()
        runtime["stopped_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        runtime["stop_ok"] = True
        try:
            RUNTIME_JSON.write_text(json.dumps(runtime, indent=2), encoding="utf-8")
        except OSError:
            pass
        print("Pilot stopped.")
        return 0
    finally:
        if bound is not None:
            bound.close()
        # action_bound closed by wait/terminate path — close if still open
        try:
            if "action_bound" in locals() and action_bound is not None:
                action_bound.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
