#!/usr/bin/env python3
"""
Contained startup entry for Windows browser-memory acceptance.

Starts a real GuardianCore with disposable-root containment. Does not retarget
the desktop launcher. Dashboard auto-start defaults to off; Codex may enable UI
for independent browser acceptance after containment checks pass.

Example:
  set ELYSIA_DISPOSABLE_ROOT=C:\\Users\\Owner\\Project guardian\\.worktrees\\dev-pr159-windows-browser-memory\\tmp\\disposable-acceptance
  set PYTHONDONTWRITEBYTECODE=1
  set TEMP=%ELYSIA_DISPOSABLE_ROOT%\\temp
  set TMP=%TEMP%
  python scripts/start_contained_browser_memory.py --disposable-root "%ELYSIA_DISPOSABLE_ROOT%"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Contained Guardian startup for browser-memory acceptance")
    parser.add_argument(
        "--disposable-root",
        default=os.environ.get("ELYSIA_DISPOSABLE_ROOT", ""),
        help="Writable disposable root (or set ELYSIA_DISPOSABLE_ROOT)",
    )
    parser.add_argument(
        "--enable-ui",
        action="store_true",
        help="Construct UIControlPanel (does not listen unless --auto-start-ui)",
    )
    parser.add_argument(
        "--auto-start-ui",
        action="store_true",
        help="Bind/start the dashboard (Codex browser acceptance only; not for containment tests)",
    )
    parser.add_argument("--ui-host", default="127.0.0.1")
    parser.add_argument("--ui-port", type=int, default=5000)
    parser.add_argument(
        "--json-status",
        action="store_true",
        help="Print a JSON status blob after startup and exit 0 (no server loop)",
    )
    parser.add_argument(
        "--keep-alive",
        action="store_true",
        help="Keep process alive until Ctrl+C (for Codex browser session)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not args.disposable_root:
        print(
            "ERROR: pass --disposable-root or set ELYSIA_DISPOSABLE_ROOT to a writable "
            "acceptance workspace. Refusing to start without an explicit disposable root.",
            file=sys.stderr,
        )
        return 2

    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    disposable = Path(args.disposable_root)
    disposable.mkdir(parents=True, exist_ok=True)
    temp = disposable / "temp"
    temp.mkdir(parents=True, exist_ok=True)
    os.environ["TEMP"] = str(temp)
    os.environ["TMP"] = str(temp)

    from project_guardian.contained_startup import (
        ContainedStartupError,
        start_contained_guardian,
    )
    from project_guardian.guardian_singleton import reset_singleton

    try:
        guardian, config = start_contained_guardian(
            disposable,
            ui_enabled=bool(args.enable_ui or args.auto_start_ui),
            ui_auto_start=bool(args.auto_start_ui),
            ui_host=args.ui_host,
            ui_port=args.ui_port,
        )
    except ContainedStartupError as e:
        print(f"CONTAINED_STARTUP_FAILED: {e}", file=sys.stderr)
        return 1

    status = {
        "ok": True,
        "contained_startup": True,
        "disposable_root": str(Path(config["disposable_root"]).resolve()),
        "memory_filepath": config["memory_filepath"],
        "autonomy_enabled": guardian._load_autonomy_config().get("enabled", True),
        "ui_enabled": bool(config.get("ui_config", {}).get("enabled")),
        "ui_auto_start": bool(config.get("ui_config", {}).get("auto_start")),
        "ui_panel_present": getattr(guardian, "ui_panel", None) is not None,
        "skip_api_key_load": bool(config.get("_skip_api_key_load")),
        "external_storage_skipped": bool(config.get("_test_skip_external_storage")),
        "background_workers": bool(config.get("start_background_workers")),
        "datetime_fix_included": False,
        "base_sha_note": "Branch cursor/contained-startup-browser-memory-001 from c7f6ad1; Codex dff2ead datetime fix NOT included",
        "security_note": "privileged routes (execute-cycle, autonomy configure, dream-cycle, learning/start) require dashboard-operator auth + enabled/contained checks; other legacy control routes may remain open — do not declare the entire dashboard secure.",
    }

    if args.json_status or not args.keep_alive:
        print(json.dumps(status, indent=2))
        if not args.keep_alive:
            if hasattr(guardian, "shutdown"):
                try:
                    guardian.shutdown()
                except Exception:
                    pass
            reset_singleton()
            return 0

    print(json.dumps(status, indent=2))
    print("Contained Guardian running. Ctrl+C to stop.", flush=True)
    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down contained Guardian...", flush=True)
    finally:
        if hasattr(guardian, "shutdown"):
            try:
                guardian.shutdown()
            except Exception:
                pass
        reset_singleton()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
