#!/usr/bin/env python3
"""
Unified Elysia Launcher - Delegates to elysia.py
Kept for backward compatibility with batch files and existing scripts.
The main program is now elysia.py with subroutines in elysia_sub_*.py
"""
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
    from elysia_config import get_status_url, launch_attach_interface_standalone, probe_backend_alive

    if probe_backend_alive():
        print("[Launcher] Existing backend detected; skipping backend start")
        print("Backend already running — attaching new interface (no second heavy startup).")
        print(f"Status API: {get_status_url()}/status\n")
        launch_attach_interface_standalone()
        sys.exit(0)

    lock_handle = _acquire_single_instance_lock()
    if lock_handle is None:
        print("Elysia unified launcher is already running; skipping duplicate start.")
        sys.exit(0)
    runpy.run_path(str(PROJECT_ROOT / "elysia.py"), run_name="__main__")
