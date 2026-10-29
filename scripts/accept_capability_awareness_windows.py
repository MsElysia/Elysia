#!/usr/bin/env python3
"""Native Windows acceptance A–J for capability awareness (disposable store/port)."""
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
PORT = 5068
MODEL = os.environ.get("ELYSIA_LOCAL_MODEL", "llama3.2:3b")
EVIDENCE = ROOT / "docs" / "evidence" / "native-windows-capability-awareness.json"


def http_json(method: str, path: str, body: dict | None = None, timeout: float = 60.0):
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
            raise RuntimeError(f"process exited: {proc.returncode}")
        try:
            status, body = http_json("GET", "/api/local-model/capabilities", timeout=3.0)
            if status == 200 and body.get("ok"):
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("capabilities endpoint not ready")


def main() -> int:
    if sys.platform != "win32":
        print("Windows only", file=sys.stderr)
        return 2
    sys.path.insert(0, str(ROOT))
    results = {"platform": sys.platform, "model": MODEL, "port": PORT, "acceptance": {}}

    store = Path(tempfile.mkdtemp(prefix="elysia-cap-aware-accept-"))
    results["disposable_store"] = str(store)
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["ELYSIA_DISPOSABLE_ROOT"] = str(store)
    env["TEMP"] = str(store / "temp")
    env["TMP"] = str(store / "temp")
    env["ELYSIA_LOCAL_MODEL"] = MODEL
    env["ELYSIA_DASHBOARD_OPERATOR_TOKEN"] = "accept-capability-awareness-20261029"
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
    log_path = store / "accept.log"
    log_f = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=log_f, stderr=subprocess.STDOUT)

    try:
        wait_ready(proc)

        # A — dashboard page + capabilities payload
        status_html, _ = 200, None
        try:
            with urllib.request.urlopen(f"http://{HOST}:{PORT}/", timeout=10) as resp:
                html = resp.read().decode("utf-8", "replace")
                status_html = resp.status
        except Exception as exc:
            html = str(exc)
            status_html = 0
        status_cap, caps = http_json("GET", "/api/local-model/capabilities")
        a_pass = (
            status_html == 200
            and "Capabilities" in html
            and "capabilities-panel" in html
            and status_cap == 200
            and caps.get("ok") is True
            and isinstance(caps.get("capabilities"), list)
            and len(caps["capabilities"]) >= 8
        )
        results["acceptance"]["A"] = {
            "result": "PASS" if a_pass else "FAIL",
            "html_has_panel": "capabilities-panel" in html,
            "capability_count": len(caps.get("capabilities") or []),
        }

        by_id = {c["id"]: c for c in (caps.get("capabilities") or []) if isinstance(c, dict)}

        # B — model recognized
        lm = caps.get("local_model") or {}
        b_pass = lm.get("model") == MODEL and lm.get("installed") is True and lm.get("reachable") is True
        results["acceptance"]["B"] = {
            "result": "PASS" if b_pass else "FAIL",
            "local_model": lm,
        }

        # C — durable memory retrieval available
        mem = by_id.get("memory.retrieve") or {}
        c_pass = mem.get("available") is True and mem.get("installed") is True
        results["acceptance"]["C"] = {"result": "PASS" if c_pass else "FAIL", "memory.retrieve": mem}

        # D — calculator available, per-request auth
        calc = by_id.get("tools.calculator.labor") or {}
        d_pass = (
            calc.get("available") is True
            and calc.get("authorized") is False
            and calc.get("permission_mode") == "per_request"
        )
        results["acceptance"]["D"] = {"result": "PASS" if d_pass else "FAIL", "calculator": calc}

        # E — email/web/finance/calendar not operational
        e_ids = ["tools.email", "tools.web_search", "tools.finance", "tools.calendar"]
        e_pass = all(
            (by_id.get(i) or {}).get("available") is False
            and (by_id.get(i) or {}).get("operational") is not True
            for i in e_ids
        )
        results["acceptance"]["E"] = {
            "result": "PASS" if e_pass else "FAIL",
            "rows": {i: by_id.get(i) for i in e_ids},
        }

        # F — Ollama unavailable degrades model only (synthetic probe via unit path already;
        # here call dead-endpoint LocalOllama and re-check memory chat path)
        from project_guardian.local_memory_chat import LocalOllama, ChatBoundaryError

        dead_ok = False
        try:
            LocalOllama(MODEL, endpoint="http://127.0.0.1:1").installed_models()
        except ChatBoundaryError:
            dead_ok = True
        status_mem, body_mem = http_json("POST", "/api/chat", {"message": "status check memory path"})
        # May 400 if no content words — use a real query
        status_mem, body_mem = http_json(
            "POST", "/api/chat", {"message": "retrieve any fictional labor rate facts"}
        )
        f_pass = dead_ok and status_mem == 200 and body_mem.get("provider") == "restricted-memory"
        results["acceptance"]["F"] = {
            "result": "PASS" if f_pass else "FAIL",
            "dead_endpoint_failed": dead_ok,
            "memory_provider": body_mem.get("provider"),
            "memory_status": status_mem,
        }

        # G — recovery: live capabilities still show model after F probe
        status_cap2, caps2 = http_json("GET", "/api/local-model/capabilities")
        lm2 = caps2.get("local_model") or {}
        g_pass = status_cap2 == 200 and lm2.get("installed") is True and lm2.get("reachable") is True
        results["acceptance"]["G"] = {"result": "PASS" if g_pass else "FAIL", "local_model": lm2}

        # H — authorization denial still effective
        status_h, body_h = http_json(
            "POST",
            "/api/chat",
            {
                "message": (
                    "Use calculator.labor with my saved rate for two painters, three eight-hour days."
                ),
                "use_local_model": True,
                "allow_calculator": False,
            },
            timeout=120.0,
        )
        h_pass = not (body_h.get("tools_executed") or []) and body_h.get("memory_written") is not True
        # Also teach a rate so authorized path can be checked optionally
        results["acceptance"]["H"] = {
            "result": "PASS" if h_pass else "FAIL",
            "status": status_h,
            "tools_executed": body_h.get("tools_executed"),
            "success": body_h.get("success"),
            "error": body_h.get("error"),
        }

        # I — regressions: prior local chat test module import + focused capability tests already separate;
        # here verify autonomy disabled in snapshot + chat memory path.
        autonomy = by_id.get("system.autonomy") or {}
        i_pass = autonomy.get("permission_mode") == "disabled" and autonomy.get("available") is False
        results["acceptance"]["I"] = {
            "result": "PASS" if i_pass else "FAIL",
            "autonomy": autonomy,
            "note": "Focused+pilot pytest run separately in completion evidence",
        }

        # J — no secrets in API response
        blob = json.dumps(caps).casefold()
        j_pass = not any(
            tok in blob
            for tok in (
                "api_key",
                "password",
                "token-secret",
                "accept-capability",
                "sk-",
                "guardian_memory.json",
            )
        )
        results["acceptance"]["J"] = {"result": "PASS" if j_pass else "FAIL"}

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
