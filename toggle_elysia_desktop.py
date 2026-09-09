#!/usr/bin/env python3
"""
Desktop one-click toggle: if Elysia backend answers GET /status, POST /shutdown (graceful).
Otherwise start START_ELYSIA_UNIFIED.bat (backend window + wait + attach UI).

If elysia_config.API_TOKEN is set, POST /shutdown sends Authorization: Bearer <token>.

Desktop shortcuts (see create_elysia_desktop_shortcut.ps1):
  - Start: START_ELYSIA_UNIFIED.bat
  - Toggle (stop else start): TOGGLE_ELYSIA_DESKTOP.bat
  - Stop only: STOP_ELYSIA_DESKTOP.bat  (python toggle_elysia_desktop.py --stop-only)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from elysia_config import API_TOKEN, get_status_url, probe_backend_alive  # noqa: E402


def _post_shutdown() -> tuple[bool, str]:
    url = f"{get_status_url()}/shutdown"
    req = urllib.request.Request(
        url,
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    if API_TOKEN:
        req.add_header("Authorization", f"Bearer {API_TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=8.0) as r:
            raw = r.read().decode("utf-8", errors="replace")
            if getattr(r, "status", 200) != 200:
                return False, f"HTTP {getattr(r, 'status', '?')}"
            data = json.loads(raw) if raw else {}
            if isinstance(data, dict) and data.get("ok"):
                return True, "shutdown accepted"
            return False, raw[:200]
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        return False, f"HTTP {e.code} {body}"
    except Exception as e:
        return False, str(e)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Desktop toggle or stop-only for Elysia backend.")
    p.add_argument(
        "--stop-only",
        action="store_true",
        help="If backend is up, POST /shutdown; if already off, exit without starting.",
    )
    if argv is None:
        argv = sys.argv[1:]
    args = p.parse_args(argv)

    if probe_backend_alive(timeout=2.5):
        ok, detail = _post_shutdown()
        if ok:
            print("[Elysia toggle] Backend was running — graceful shutdown requested.")
            print("              (Backend console window should close shortly.)")
            return 0
        print("[Elysia toggle] Could not shut down via POST /shutdown:", detail)
        print("              Close the 'Elysia Backend' console or press Ctrl+C there.")
        return 1

    if args.stop_only:
        print("[Elysia toggle] Stop-only: backend not responding on /status — nothing to shut down.")
        return 0

    bat = PROJECT_ROOT / "START_ELYSIA_UNIFIED.bat"
    if not bat.is_file():
        print("[Elysia toggle] Missing:", bat)
        return 2

    if os.name == "nt":
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", str(bat)],
            cwd=str(PROJECT_ROOT),
            shell=False,
        )
    else:
        subprocess.Popen(["/bin/bash", str(bat)], cwd=str(PROJECT_ROOT))
    print("[Elysia toggle] Starting Elysia (unified launcher)...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
