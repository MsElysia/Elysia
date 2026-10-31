#!/usr/bin/env python3
"""Native Windows acceptance for process-local execution evidence (port 5069)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = Path(r"C:\Users\Owner\Project guardian\.venv\Scripts\python.exe")
HOST = "127.0.0.1"
PORT = 5069
MODEL = os.environ.get("ELYSIA_LOCAL_MODEL", "llama3.2:3b")
EVIDENCE = ROOT / "docs" / "evidence" / "native-windows-execution-evidence.json"


def http_json(method: str, path: str, body: dict | None = None, timeout: float = 120.0):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://{HOST}:{PORT}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": raw}
        return int(exc.code), payload


def wait_ready(proc: subprocess.Popen, seconds: float = 90.0) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"exited {proc.returncode}")
        try:
            status, body = http_json("GET", "/api/local-model/capabilities", timeout=3.0)
            if status == 200 and body.get("ok"):
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("not ready")


def main() -> int:
    if sys.platform != "win32":
        return 2
    sys.path.insert(0, str(ROOT))
    results = {"model": MODEL, "port": PORT, "acceptance": {}}

    store = Path(tempfile.mkdtemp(prefix="elysia-exec-evidence-"))
    results["disposable_store"] = str(store)
    env = os.environ.copy()
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "ELYSIA_DISPOSABLE_ROOT": str(store),
            "TEMP": str(store / "temp"),
            "TMP": str(store / "temp"),
            "ELYSIA_LOCAL_MODEL": MODEL,
            "ELYSIA_DASHBOARD_OPERATOR_TOKEN": "accept-execution-evidence-20261029",
        }
    )
    (store / "temp").mkdir(parents=True, exist_ok=True)
    (store / "memory").mkdir(parents=True, exist_ok=True)
    cmd = [
        str(PY),
        str(ROOT / "scripts" / "start_contained_browser_memory.py"),
        "--disposable-root",
        str(store),
        "--enable-ui",
        "--auto-start-ui",
        "--ui-host",
        HOST,
        "--ui-port",
        str(PORT),
        "--keep-alive",
    ]
    log_f = (store / "accept.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=log_f, stderr=subprocess.STDOUT)
    token = env["ELYSIA_DASHBOARD_OPERATOR_TOKEN"]
    headers = {
        "Content-Type": "application/json",
        "X-Elysia-Identity": "dashboard-operator",
        "X-Elysia-Token": token,
    }

    try:
        wait_ready(proc)
        status0, caps0 = http_json("GET", "/api/local-model/capabilities")
        by0 = {c["id"]: c for c in caps0.get("capabilities") or []}
        # Before work: not yet verified for ollama/memory/calculator
        pre_ok = (
            status0 == 200
            and by0.get("intelligence.ollama.chat", {}).get("runtime_status") == "not_yet_verified"
            and by0.get("memory.retrieve", {}).get("runtime_status") == "not_yet_verified"
            and by0.get("tools.calculator.labor", {}).get("runtime_status")
            == "authorization_required"
        )
        results["acceptance"]["pre_unknown"] = {
            "result": "PASS" if pre_ok else "FAIL",
            "ollama": by0.get("intelligence.ollama.chat"),
            "memory": by0.get("memory.retrieve"),
            "calculator": by0.get("tools.calculator.labor"),
        }

        # Teach + retrieve memory (non-empty)
        urllib.request.urlopen(
            urllib.request.Request(
                f"http://{HOST}:{PORT}/api/restricted/v1/facts",
                data=json.dumps(
                    {"statement": "Fictional labor rate is USD 35 per hour."}
                ).encode("utf-8"),
                method="POST",
                headers=headers,
            ),
            timeout=30,
        )
        status_m, body_m = http_json(
            "POST", "/api/chat", {"message": "What is the fictional labor rate?"}
        )
        status1, caps1 = http_json("GET", "/api/local-model/capabilities")
        by1 = {c["id"]: c for c in caps1.get("capabilities") or []}
        mem_ok = (
            status_m == 200
            and body_m.get("provider") == "restricted-memory"
            and (body_m.get("matches") or [])
            and by1.get("memory.retrieve", {}).get("runtime_status") == "verified_operational"
        )
        results["acceptance"]["memory_verified"] = {
            "result": "PASS" if mem_ok else "FAIL",
            "memory": by1.get("memory.retrieve"),
            "matches": len(body_m.get("matches") or []),
        }

        # Unauthorized calculator must not verify
        status_u, body_u = http_json(
            "POST",
            "/api/chat",
            {
                "message": (
                    "Use calculator.labor for two painters working three eight-hour days "
                    "using my saved fictional labor rate."
                ),
                "use_local_model": True,
                "allow_calculator": False,
            },
        )
        status2, caps2 = http_json("GET", "/api/local-model/capabilities")
        by2 = {c["id"]: c for c in caps2.get("capabilities") or []}
        unauth_ok = not (body_u.get("tools_executed") or []) and by2.get(
            "tools.calculator.labor", {}
        ).get("runtime_status") != "verified_operational"
        results["acceptance"]["unauthorized_not_verified"] = {
            "result": "PASS" if unauth_ok else "FAIL",
            "tools_executed": body_u.get("tools_executed"),
            "calculator": by2.get("tools.calculator.labor"),
            "status": status_u,
        }

        # Authorized calculator + local model
        status_a, body_a = http_json(
            "POST",
            "/api/chat",
            {
                "message": (
                    "Use calculator.labor for two painters working three eight-hour days "
                    "using my saved fictional labor rate."
                ),
                "use_local_model": True,
                "allow_calculator": True,
            },
        )
        status3, caps3 = http_json("GET", "/api/local-model/capabilities")
        by3 = {c["id"]: c for c in caps3.get("capabilities") or []}
        auth_ok = (
            body_a.get("calculation_verified") is True
            and (body_a.get("tools_executed") or [{}])[0].get("result") == "1680"
            and by3.get("tools.calculator.labor", {}).get("runtime_status")
            == "verified_operational"
            and by3.get("intelligence.ollama.chat", {}).get("runtime_status")
            == "verified_operational"
        )
        results["acceptance"]["authorized_verified"] = {
            "result": "PASS" if auth_ok else "FAIL",
            "reply": (body_a.get("reply") or body_a.get("error") or "")[:300],
            "calculator": by3.get("tools.calculator.labor"),
            "ollama": by3.get("intelligence.ollama.chat"),
            "status": status_a,
        }

        # Secrets check
        blob = json.dumps(caps3).casefold()
        secrets_ok = not any(
            t in blob for t in ("api_key", "password", "accept-execution", "sk-", "token-secret")
        )
        results["acceptance"]["no_secrets"] = {"result": "PASS" if secrets_ok else "FAIL"}

        # Inspection does not execute tools (capabilities GET leaves evidence unchanged count)
        before = len(caps3.get("execution_evidence") or [])
        http_json("GET", "/api/local-model/capabilities")
        status4, caps4 = http_json("GET", "/api/local-model/capabilities")
        after = len(caps4.get("execution_evidence") or [])
        results["acceptance"]["inspection_no_execute"] = {
            "result": "PASS" if before == after else "FAIL",
            "before": before,
            "after": after,
        }

    finally:
        try:
            proc.terminate()
            proc.wait(timeout=20)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            log_f.close()
        except Exception:
            pass

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    fails = [k for k, v in results["acceptance"].items() if v.get("result") != "PASS"]
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
