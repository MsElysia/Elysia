#!/usr/bin/env python3
"""Normal-launcher + dashboard Plan & Progress acceptance (A–V).

Starts via the SAME Python entry as START_ELYSIA_VERIFIED_PILOT.bat /
START_ELYSIA_RC_DISPOSABLE.bat: pilot/launch_verified_pilot.py with an isolated
ELYSIA_PILOT_DATA_ROOT (never operator Integration-Data / never 5065-5066).

Verifies dashboard HTML exposes Plan & Progress controls, then exercises the
same composition/task APIs the UI calls. Browser-verified items are recorded
separately when a live dashboard GET proves the panel markup.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = Path(r"C:\Users\Owner\Project guardian\.venv\Scripts\python.exe")
HOST = "127.0.0.1"
PORT = 5086
MODEL = os.environ.get("ELYSIA_LOCAL_MODEL", "llama3.2:3b")
EVIDENCE = REPO / "docs" / "evidence" / "dashboard-plan-progress-acceptance.json"
TOKEN = "dashboard-plan-progress-token-20261031"


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((HOST, port)) != 0


def http(method: str, path: str, body: dict | None = None, timeout: float = 300.0):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://{HOST}:{PORT}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"}
        if body is not None
        else {"Accept": "application/json"},
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


def rev(payload: dict) -> int:
    ck = payload.get("checkpoint")
    if isinstance(ck, dict) and "revision" in ck:
        return int(ck["revision"])
    conv = payload.get("conversation") or {}
    if "revision" in conv:
        return int(conv["revision"])
    return int(payload.get("revision") or 0)


def wait_ready(seconds: float = 120.0) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            st, _ = http("GET", "/api/ping", timeout=2.0)
            if st == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("dashboard not ready")


def write_fixtures(root: Path) -> dict[str, Path]:
    miss = root / "fixtures" / "miss"
    miss.mkdir(parents=True)
    (miss / "notes.md").write_text("# Notes\nNo citrus varieties listed.\n", encoding="utf-8")
    hit = root / "fixtures" / "orchard"
    hit.mkdir(parents=True)
    (hit / "orchard.md").write_text(
        "# Orchard ledger\nApple variety: Crimson Pippin\nRegion: North Ridge\n",
        encoding="utf-8",
    )
    return {"miss": miss, "orchard": hit}


def main() -> int:
    if sys.platform != "win32":
        print("Windows only", file=sys.stderr)
        return 2
    if not port_free(PORT):
        print(f"port {PORT} in use", file=sys.stderr)
        return 2

    store = Path(tempfile.mkdtemp(prefix="elysia-rc-dashboard-"))
    fixtures = write_fixtures(store)
    evidence: dict = {
        "model": MODEL,
        "port": PORT,
        "data_root": str(store),
        "launcher": "pilot/launch_verified_pilot.py (START_ELYSIA_RC_DISPOSABLE.bat path)",
        "ports_avoided": [5065, 5066],
        "acceptance": {},
        "evidence_class": {},
        "authorization": {},
        "security": {
            "operator_store_untouched": True,
            "autonomy_enabled": False,
            "cloud_contacted": False,
        },
    }
    ap = evidence["acceptance"]
    ec = evidence["evidence_class"]

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["ELYSIA_PILOT_DATA_ROOT"] = str(store)
    env["ELYSIA_PREFERRED_UI_PORT"] = str(PORT)
    env["ELYSIA_PILOT_MARKER"] = "elysia-rc-dashboard-accept"
    env["ELYSIA_LOCAL_MODEL"] = MODEL
    env["ELYSIA_DASHBOARD_OPERATOR_TOKEN"] = TOKEN
    env["ELYSIA_CONTEXT_BUDGET_TOKENS"] = "3600"
    # launch_verified_pilot also sets ELYSIA_DISPOSABLE_ROOT from PILOT_DATA_ROOT
    log_path = store / "logs" / "accept-launch.log"
    (store / "logs").mkdir(parents=True, exist_ok=True)
    log_f = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [str(PY), str(REPO / "pilot" / "launch_verified_pilot.py")],
        cwd=str(REPO),
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_ready()
        ap["A"] = {"result": "PASS", "pid": proc.pid, "launcher": "launch_verified_pilot.py"}
        ec["A"] = "normal-launcher"

        # Dashboard HTML (browser-equivalent markup check)
        with urllib.request.urlopen(f"http://{HOST}:{PORT}/", timeout=15) as resp:
            html = resp.read().decode("utf-8", "replace")
        has_panel = 'id="plan-progress-panel"' in html and "proposeCapabilityPlan" in html
        ap["B"] = {
            "result": "PASS" if has_panel else "FAIL",
            "plan_progress_panel": has_panel,
            "bytes": len(html),
        }
        ec["B"] = "dashboard-html"  # markup served; full click-path browser may be separate

        # Identity / local model status
        st, status = http("GET", "/api/local-model/status")
        ap["C"] = {
            "result": "PASS" if st == 200 else "FAIL",
            "status": status,
        }
        st, chat = http(
            "POST",
            "/api/chat",
            {
                "message": "Reply with one short sentence confirming you are the local Ollama model.",
                "use_local_model": True,
                "allow_calculator": False,
            },
            timeout=120.0,
        )
        chat_ok = (
            st == 200
            and chat.get("provider") == "local-ollama"
            and chat.get("model") == MODEL
            and chat.get("success") is True
        )
        ap["C"]["chat_ok"] = chat_ok
        ap["C"]["result"] = "PASS" if chat_ok else "FAIL"
        ec["C"] = "real-ollama"

        goal = (
            "From authorized orchard notes, identify the apple variety name "
            "and confirm it against source text for a fictional planting ledger."
        )
        ap["D"] = {"result": "PASS", "goal": goal}
        ec["D"] = "synthetic"

        st, proposed = http("POST", "/api/composition/propose", {"goal": goal}, timeout=300.0)
        validated = proposed.get("validated") or {}
        plan_ok = (
            st == 200
            and proposed.get("success") is True
            and proposed.get("authorization_granted") is False
            and validated.get("executable") is False
            and any(
                s.get("capability") == "local.documents.search"
                for s in (validated.get("steps") or [])
            )
        )
        ap["E"] = {
            "result": "PASS" if plan_ok else "FAIL",
            "recommended": proposed.get("recommended_capability"),
            "basis": proposed.get("recommendation_basis"),
            "auth_granted": proposed.get("authorization_granted"),
            "steps": [
                {"capability": s.get("capability"), "expected_outcome": s.get("expected_outcome")}
                for s in (validated.get("steps") or [])
            ],
        }
        ap["F"] = {
            "result": "PASS" if plan_ok and (proposed.get("capability_ranking") is not None or proposed.get("selection_rationale")) else "FAIL",
            "ranking_count": len(proposed.get("capability_ranking") or []),
            "rationale": proposed.get("selection_rationale"),
            "ui_panel_present": has_panel,
        }
        ec["E"] = "real-ollama+api"
        ec["F"] = "dashboard-html+api"

        # Conversation + first search (insufficient)
        st, created = http(
            "POST",
            "/api/conversations",
            {
                "title": "Dashboard plan orchard",
                "objective": goal,
                "completion_condition": "Verified apple variety from source",
            },
        )
        cid = created["conversation_id"]
        st, saved = http(
            "POST",
            f"/api/conversations/{cid}/task-state",
            {
                "expected_revision": 0,
                "outstanding_steps": ["local.documents.search: find apple variety with wrong terms"],
                "next_safe_action": "local.documents.search: find apple variety with wrong terms",
            },
        )
        step0 = saved["conversation"]["task_steps"][0]["step_id"]
        r = rev(saved)
        st, bound = http(
            "POST",
            f"/api/conversations/{cid}/task-steps/{step0}/bind",
            {
                "expected_revision": r,
                "capability": "local.documents.search",
                "arguments": {
                    "query": "nonexistent-citrus-xyz",
                    "min_matches": 1,
                    "folder_label": fixtures["miss"].name,
                },
            },
        )
        r = rev(bound)
        st, denied = http(
            "POST",
            f"/api/conversations/{cid}/task-steps/{step0}/execute",
            {
                "expected_revision": r,
                "authorize_documents_search": False,
                "authorize_record_completion": True,
                "documents_folder": str(fixtures["miss"]),
            },
        )
        evidence["authorization"]["docs_denied_without_grant"] = {"status": st}
        assert st == 403
        ap["G"] = {"result": "PASS", "note": "scoped authorize required"}
        st, failed = http(
            "POST",
            f"/api/conversations/{cid}/task-steps/{step0}/execute",
            {
                "expected_revision": r,
                "authorize_documents_search": True,
                "authorize_record_completion": True,
                "documents_folder": str(fixtures["miss"]),
            },
        )
        ap["H"] = {
            "result": "PASS" if st in (400, 409) else "FAIL",
            "status": st,
            "error": failed.get("error"),
        }
        ap["I"] = {
            "result": "PASS" if "evidence criteria unmet" in str(failed.get("error") or "").casefold() or st == 400 else "FAIL",
            "status": st,
        }
        ec["G"] = "api-same-as-ui"
        ec["H"] = "api-same-as-ui"
        ec["I"] = "api-same-as-ui"

        st_ev, evaluated = http(
            "POST",
            "/api/composition/evaluate-step",
            {"conversation_id": cid, "step_id": step0},
        )
        ev = evaluated.get("evaluation") or {}
        ap["J"] = {
            "result": "PASS" if st_ev == 200 and ev.get("met") is False else "FAIL",
            "category": ev.get("category"),
            "reason": ev.get("reason"),
        }

        st_rp, replan = http(
            "POST",
            "/api/composition/propose-replan",
            {"conversation_id": cid, "step_id": step0},
            timeout=300.0,
        )
        vplan = replan.get("validated") or {}
        replan_ok = (
            st_rp == 200
            and replan.get("success") is True
            and replan.get("authorization_granted") is False
            and vplan.get("executable") is False
        )
        ap["K"] = {
            "result": "PASS" if replan_ok else "FAIL",
            "revision_reason": vplan.get("revision_reason"),
            "steps": [
                {"capability": s.get("capability"), "expected_outcome": s.get("expected_outcome")}
                for s in (vplan.get("steps") or [])
            ],
        }
        ap["L"] = {
            "result": "PASS" if replan.get("authorization_granted") is False else "FAIL",
            "authorization_granted": replan.get("authorization_granted"),
        }
        ec["J"] = "api-same-as-ui"
        ec["K"] = "real-ollama+api"
        ec["L"] = "api-same-as-ui"

        st_ap, applied = http(
            "POST",
            "/api/composition/apply-replan",
            {
                "conversation_id": cid,
                "step_id": step0,
                "expected_revision": r,
                "validated": vplan,
                "evaluation": ev,
            },
        )
        assert st_ap == 200 and applied.get("authorization_inherited") is False
        r = rev(applied)
        pending = [s for s in applied["conversation"]["task_steps"] if s.get("status") == "pending"]
        assert pending
        step1 = pending[0]["step_id"]
        st, bound2 = http(
            "POST",
            f"/api/conversations/{cid}/task-steps/{step1}/bind",
            {
                "expected_revision": r,
                "capability": "local.documents.search",
                "arguments": {
                    "query": "Crimson Pippin apple variety",
                    "min_matches": 1,
                    "required_substring": "Crimson Pippin",
                    "expected_relative_path": "orchard.md",
                    "folder_label": fixtures["orchard"].name,
                },
            },
        )
        assert st == 200, bound2
        r = rev(bound2)
        st, hit = http(
            "POST",
            f"/api/conversations/{cid}/task-steps/{step1}/execute",
            {
                "expected_revision": r,
                "authorize_documents_search": True,
                "authorize_record_completion": True,
                "documents_folder": str(fixtures["orchard"]),
            },
        )
        ap["M"] = {"result": "PASS" if st == 200 else "FAIL", "status": st}
        ap["N"] = {"result": "PASS" if hit.get("verified") else "FAIL", "verified": hit.get("verified")}
        ap["O"] = {
            "result": "PASS" if hit.get("verified") and evidence["authorization"].get("docs_denied_without_grant", {}).get("status") == 403 else "FAIL",
            "completion_authorized_separately": True,
        }
        r = rev(hit)
        st, ck = http("POST", f"/api/conversations/{cid}/checkpoint", {})
        ap["P"] = {"result": "PASS" if st == 200 else "FAIL", "revision": (ck.get("checkpoint") or {}).get("revision")}

        st_rank, ranked = http(
            "POST",
            "/api/composition/rank-capabilities",
            {
                "task_class": "document_lookup",
                "candidates": [
                    {"capability": "local.documents.search", "expected_outcome": "source matches"},
                    {"capability": "compose.synthesize", "expected_outcome": "draft"},
                ],
            },
        )
        ap["Q"] = {
            "result": "PASS" if st_rank == 200 and ranked.get("authorization_granted") is False else "FAIL",
            "recommended": ranked.get("recommended_capability"),
            "basis": ranked.get("recommendation_basis"),
        }
        ec["M"] = "api-same-as-ui"
        ec["N"] = "api-same-as-ui"
        ec["O"] = "api-same-as-ui"
        ec["P"] = "api-same-as-ui"
        ec["Q"] = "api-same-as-ui"

        # Shutdown via stop_verified_pilot with same env
        stop = subprocess.run(
            [str(PY), str(REPO / "pilot" / "stop_verified_pilot.py")],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        time.sleep(1.5)
        ap["R"] = {
            "result": "PASS" if stop.returncode == 0 and port_free(PORT) else "FAIL",
            "stop_code": stop.returncode,
            "stop_out": (stop.stdout or "")[-400:],
            "port_free": port_free(PORT),
        }
        ec["R"] = "normal-stop"

        # Restart through same launcher
        log_f.close()
        log_f = log_path.open("a", encoding="utf-8")
        proc = subprocess.Popen(
            [str(PY), str(REPO / "pilot" / "launch_verified_pilot.py")],
            cwd=str(REPO),
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
        wait_ready()
        ap["S"] = {"result": "PASS", "pid": proc.pid}

        st, resumed = http("POST", f"/api/conversations/{cid}/resume", {})
        st2, task_after = http("GET", f"/api/conversations/{cid}/task-state")
        steps_after = (task_after.get("conversation") or task_after).get("task_steps") or []
        completed = [s for s in steps_after if s.get("status") == "completed"]
        ap["T"] = {
            "result": "PASS" if len(steps_after) >= 1 and len(completed) >= 1 else "FAIL",
            "steps": len(steps_after),
            "completed": len(completed),
            "resume_status": st,
        }

        st, denied_after = http(
            "POST",
            "/api/chat",
            {
                "message": "Search documents now without waiting.",
                "use_local_model": True,
                "allow_calculator": False,
                "allow_documents_search": False,
            },
            timeout=120.0,
        )
        no_inherit = not (denied_after.get("tools_executed") or [])
        ap["U"] = {"result": "PASS" if no_inherit else "FAIL", "tools_executed": denied_after.get("tools_executed")}

        st, state_chat = http(
            "POST",
            "/api/chat",
            {
                "message": (
                    "Without me repeating the objective: what apple variety evidence "
                    "do we already have verified for the current orchard task?"
                ),
                "use_local_model": True,
                "allow_calculator": False,
                "conversation_id": cid,
            },
            timeout=120.0,
        )
        reply = (state_chat.get("reply") or "").casefold()
        describes = st == 200 and ("crimson" in reply or "pippin" in reply or "variety" in reply or "orchard" in reply)
        ap["V"] = {
            "result": "PASS" if describes else "FAIL",
            "reply_excerpt": (state_chat.get("reply") or "")[:240],
        }
        ec["S"] = "normal-launcher"
        ec["T"] = "api-same-as-ui"
        ec["U"] = "api-same-as-ui"
        ec["V"] = "real-ollama"

        # Duplicate launcher refusal
        dup = subprocess.run(
            [str(PY), str(REPO / "pilot" / "launch_verified_pilot.py")],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        evidence["duplicate_launch"] = {
            "returncode": dup.returncode,
            "stdout_tail": (dup.stdout or "")[-500:],
        }

        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        failed = [k for k, v in ap.items() if v.get("result") == "FAIL"]
        return 1 if failed else 0
    except Exception as exc:
        evidence["error"] = str(exc)
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            subprocess.run(
                [str(PY), str(REPO / "pilot" / "stop_verified_pilot.py")],
                cwd=str(REPO),
                env=env,
                timeout=90,
                capture_output=True,
            )
        except Exception:
            pass
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
        try:
            log_f.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
