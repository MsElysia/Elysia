#!/usr/bin/env python3
"""
Poll the Elysia status HTTP API until the backend is up or timeout.
Used by START_ELYSIA_FULL.bat (do not import heavy project modules before elysia.py is ready).

Env:
  ELYSIA_STARTUP_WAIT_SEC   — max wait seconds (default 300)
  ELYSIA_STARTUP_POLL_SEC   — interval between polls (default 3)
  ELYSIA_STARTUP_GRACE_SEC  — seconds before treating missing elysia.py process as crash (default 20)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from elysia_config import get_status_url
except Exception:
    get_status_url = lambda: "http://127.0.0.1:8888"  # type: ignore


def _status_endpoint() -> str:
    return get_status_url().rstrip("/") + "/status"


def _fetch_status_json() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    url = _status_endpoint()
    req = urllib.request.Request(url, headers={"User-Agent": "ElysiaStartupWait/1"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read().decode("utf-8", errors="replace")
            return json.loads(raw), None
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
            return json.loads(body), f"HTTP {e.code}: {body[:200]}"
        except Exception:
            return None, f"HTTP {e.code}"
    except Exception as e:
        return None, str(e)


def _backend_ready(body: dict) -> bool:
    if not isinstance(body, dict):
        return False
    if body.get("system") == "Unified Elysia System":
        return True
    if "running" in body and "components" in body:
        return True
    return False


def _elysia_backend_process_running_windows() -> bool:
    if sys.platform != "win32":
        return True
    try:
        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" "
            "| Where-Object { $_.CommandLine -match 'elysia\\.py' } "
            "| Select-Object -First 1 -ExpandProperty ProcessId"
        )
        cr = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=cr,
        )
        out = (r.stdout or "").strip()
        return bool(out and out.isdigit())
    except Exception:
        return True


def main() -> int:
    max_wait = float(os.environ.get("ELYSIA_STARTUP_WAIT_SEC", "300"))
    interval = float(os.environ.get("ELYSIA_STARTUP_POLL_SEC", "3"))
    grace = float(os.environ.get("ELYSIA_STARTUP_GRACE_SEC", "20"))

    url = _status_endpoint()
    print(f"Waiting for backend: {url}")
    print(f"  (max {int(max_wait)}s, poll every {interval:.0f}s; grace {grace:.0f}s before crash detection)")
    t0 = time.time()
    attempt = 0
    last_err: Optional[str] = None
    last_body: Optional[Dict[str, Any]] = None

    while time.time() - t0 < max_wait:
        attempt += 1
        elapsed = time.time() - t0
        body, err = _fetch_status_json()
        last_err = err
        if isinstance(body, dict):
            last_body = body
            if _backend_ready(body):
                phase = body.get("startup_phase") or "unknown"
                print(
                    f"  [{elapsed:7.1f}s] attempt {attempt}: OK — backend responding "
                    f"(startup_phase={phase!r})"
                )
                return 0

        err_s = err or "not ready"
        phase_hint = ""
        if isinstance(body, dict):
            phase_hint = body.get("startup_phase") or body.get("deferred_init_state") or ""
            if phase_hint:
                phase_hint = f" phase={phase_hint!r}"

        print(f"  [{elapsed:7.1f}s] attempt {attempt}: waiting… ({err_s}){phase_hint}")

        if elapsed >= grace and sys.platform == "win32":
            if not _elysia_backend_process_running_windows():
                print()
                print("Backend process not found: no python.exe with elysia.py in command line.")
                print("The backend window may have exited. Check the Elysia Backend console for errors.")
                print(f"Last poll error: {last_err}")
                return 2

        time.sleep(interval)

    print()
    print(f"Timeout after {max_wait:.0f}s — status URL never returned a ready JSON payload.")
    print(f"Last error: {last_err}")
    if last_body:
        try:
            print("Last JSON (truncated):", json.dumps(last_body, default=str)[:800])
        except Exception:
            pass
    print("If python elysia.py is still running, it may still be loading (e.g. memory/vectors).")
    print("You can wait and open the interface again, or check logs (elysia_unified.log).")
    return 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(130)
