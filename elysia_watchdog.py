#!/usr/bin/env python3
"""
Elysia Watchdog
===============
Monitors Elysia health and optionally restarts the backend if it becomes unresponsive.
Run in a separate terminal or as a background service.

Usage:
  python elysia_watchdog.py              # Check-only mode (exits after one check)
  python elysia_watchdog.py --daemon      # Loop: check every 5 min, restart if down
  python elysia_watchdog.py --interval 120  # Check every 120 seconds
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent


def check_health() -> bool:
    """Run health check. Returns True if healthy."""
    try:
        from elysia_health_check import check_health
        r = check_health()
        return r["healthy"]
    except Exception as e:
        print(f"[Watchdog] Health check failed: {e}")
        return False


def start_elysia():
    """Start elysia.py in a new process. Returns subprocess.Popen or None."""
    try:
        proc = subprocess.Popen(
            [sys.executable, "elysia.py"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        return proc
    except Exception as e:
        print(f"[Watchdog] Failed to start Elysia: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Elysia health watchdog")
    parser.add_argument("--daemon", action="store_true", help="Run in daemon mode (loop)")
    parser.add_argument("--interval", type=int, default=300, help="Check interval in seconds (default 300)")
    parser.add_argument("--restart", action="store_true", help="Restart Elysia if unhealthy (daemon only)")
    args = parser.parse_args()

    if args.daemon:
        print("[Watchdog] Daemon mode: checking every", args.interval, "seconds")
        if args.restart:
            print("[Watchdog] Restart-on-failure enabled")
        while True:
            if check_health():
                print("[Watchdog] OK at", time.strftime("%Y-%m-%d %H:%M:%S"))
            else:
                print("[Watchdog] UNHEALTHY at", time.strftime("%Y-%m-%d %H:%M:%S"))
                if args.restart:
                    print("[Watchdog] Attempting restart...")
                    start_elysia()
                    time.sleep(30)  # Wait for startup
            time.sleep(args.interval)
    else:
        # Single check
        ok = check_health()
        print("OK" if ok else "UNHEALTHY")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
