#!/usr/bin/env python3
"""
Test the Elysia Control Panel endpoints.
Run while Project Guardian is running. Usage: python scripts/test_control_panel.py
"""
import json
import sys
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:5000"
TIMEOUT = 5


def req(path, method="GET", body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    if body:
        req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.getcode(), json.loads(r.read().decode())
    except urllib.error.URLError as e:
        return None, str(e)
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"


def main():
    print("Elysia Control Panel – Endpoint Tests")
    print("=" * 50)
    print("Make sure Project Guardian is running first.\n")

    tests = [
        ("GET", "/api/ping", None, lambda c, d: d.get("ok") and d.get("service") == "elysia-control-panel"),
        ("GET", "/api/debug", None, lambda c, d: d.get("orchestrator") and d.get("has_memory")),
        ("GET", "/api/status", None, lambda c, d: "system" in d and "memory" in d),
        ("POST", "/api/control/pause", {}, lambda c, d: d.get("success") or "paused" in str(d).lower()),
        ("POST", "/api/control/resume", {}, lambda c, d: d.get("success") or "resumed" in str(d).lower()),
        ("GET", "/api/learning/summary", None, lambda c, d: "success" in d or "error" in d),
        ("POST", "/api/learning/test-reddit", {}, lambda c, d: d.get("success") or "error" in d),
    ]
    ok = 0
    for method, path, body, check in tests:
        code, data = req(path, method, body)
        if code == 200 and (callable(check) and check(code, data) if data else True):
            print(f"  [OK] {method} {path}")
            ok += 1
        elif code:
            print(f"  [WARN] {method} {path} -> {code} {str(data)[:60]}")
        else:
            print(f"  [FAIL] {method} {path} -> {data}")
    print()
    if ok == len(tests):
        print("All tests passed. Control panel is available at: " + BASE)
        return 0
    elif ok == 0:
        print("All tests failed. Is Project Guardian running? Start it first.")
        return 1
    else:
        print(f"{ok}/{len(tests)} passed. Check failures above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
