#!/usr/bin/env python3
"""
Elysia Health Check
===================
Lightweight script to verify Elysia subsystems are responding.
Run periodically (e.g. via Task Scheduler) to monitor system health.
Exit 0 = healthy, 1 = unhealthy (for automation).
"""
import json
import sys
from pathlib import Path

def check_health() -> dict:
    """Check Elysia health. Returns dict with status and subsystem details."""
    try:
        from elysia_config import get_status_url
        base = get_status_url()
    except Exception:
        base = "http://127.0.0.1:8888"

    result = {"healthy": False, "subsystems": {}, "error": None}
    try:
        import urllib.request
        # Quick health ping
        req = urllib.request.Request(f"{base}/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            health = json.loads(r.read().decode())
            result["subsystems"]["health"] = health.get("status", "ok")
            result["subsystems"]["running"] = health.get("running", False)

        # Full status for subsystem details
        req = urllib.request.Request(f"{base}/status", method="GET")
        with urllib.request.urlopen(req, timeout=10) as r:
            status = json.loads(r.read().decode())
            comps = status.get("components", {})
            result["subsystems"]["architect"] = comps.get("architect_core", False)
            result["subsystems"]["guardian"] = comps.get("guardian_core", False)
            result["subsystems"]["runtime_loop"] = comps.get("runtime_loop", False)
            result["subsystems"]["modules"] = comps.get("integrated_modules", 0)
            result["uptime"] = status.get("uptime", "N/A")
            result["running"] = status.get("running", False)

        all_ok = (
            result["subsystems"].get("architect") and
            result["subsystems"].get("guardian") and
            result["subsystems"].get("runtime_loop") and
            result["running"]
        )
        result["healthy"] = all_ok
    except Exception as e:
        result["error"] = str(e)
        result["healthy"] = False
    return result


if __name__ == "__main__":
    r = check_health()
    if r["healthy"]:
        print("OK", r.get("uptime", ""), "|", r["subsystems"])
        sys.exit(0)
    else:
        print("UNHEALTHY:", r.get("error", r["subsystems"]))
        sys.exit(1)
