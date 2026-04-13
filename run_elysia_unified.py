#!/usr/bin/env python3
"""
Unified Elysia Launcher - Delegates to elysia.py
Kept for backward compatibility with batch files and existing scripts.
The main program is now elysia.py with subroutines in elysia_sub_*.py

By default this entrypoint starts the **full backend** (same as Start_Elysia_Backend.cmd):
- Sets ELYSIA_FORCE_FULL_BACKEND so a stray /status on 8888 does not trigger attach-only.
Opt-in attach-only shortcut: set ELYSIA_UNIFIED_ATTACH_IF_BACKEND_UP=1 before running.
"""
import os
import sys
import runpy
import tempfile
import atexit
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

def _acquire_single_instance_lock():
    """
    Prevent duplicate launcher instances from running concurrently.
    On Windows this uses a non-blocking msvcrt lock on a temp lock file.
    """
    lock_path = Path(tempfile.gettempdir()) / "elysia_unified_launcher.lock"
    lock_fh = open(lock_path, "a+")
    try:
        import msvcrt

        lock_fh.seek(0)
        msvcrt.locking(lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock_fh.close()
        return None
    except Exception:
        lock_fh.close()
        return None

    def _release_lock():
        try:
            import msvcrt

            lock_fh.seek(0)
            msvcrt.locking(lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
        try:
            lock_fh.close()
        except Exception:
            pass

    atexit.register(_release_lock)
    return lock_fh


# Run elysia.py directly (avoids import conflict with elysia/ package)
if __name__ == "__main__":
    _attach_if_up = os.environ.get("ELYSIA_UNIFIED_ATTACH_IF_BACKEND_UP", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if _attach_if_up:
        from elysia_config import get_status_url, launch_attach_interface_standalone, probe_backend_alive

        if probe_backend_alive():
            print("[Launcher] ELYSIA_UNIFIED_ATTACH_IF_BACKEND_UP: existing /status — attach-only UI.")
            print(f"Status API: {get_status_url()}/status\n")
            launch_attach_interface_standalone()
            sys.exit(0)

    # Default: same as Start_Elysia_Backend.cmd — full Guardian/backend (probe attach-only skipped in elysia.py).
    os.environ.setdefault("ELYSIA_FORCE_FULL_BACKEND", "1")
    print(
        "[Launcher] run_elysia_unified.py → full backend (ELYSIA_FORCE_FULL_BACKEND=1). "
        "Attach-only if /status up: set ELYSIA_UNIFIED_ATTACH_IF_BACKEND_UP=1"
    )

    lock_handle = _acquire_single_instance_lock()
    if lock_handle is None:
        print(
            "[Launcher] Another run_elysia_unified.py instance holds the launcher lock — exiting.\n"
            "If no Elysia window is open, delete or retry: %TEMP%\\elysia_unified_launcher.lock\n"
            "To start only the UI against a running backend: python elysia_interface.py --attach-only"
        )
        sys.exit(0)
    runpy.run_path(str(PROJECT_ROOT / "elysia.py"), run_name="__main__")
