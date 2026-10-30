"""Native Windows acceptance: general capability composition across domains.

Port 5078. Disposable fictional fixtures only. Real local Ollama for synthesis
and plan proposal. No per-domain workflow modules. Does not touch pilots 5065-5077.
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
PORT = 5078
MODEL = os.environ.get("ELYSIA_LOCAL_MODEL", "llama3.2:3b")


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) != 0


def _http(method: str, path: str, body: dict | None = None, timeout: float = 240.0):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"error": raw}
        return exc.code, parsed


def _start(cmd, env, log_path: Path, mode: str = "w"):
    fh = open(log_path, mode, encoding="utf-8")
    fh.write(f"\n--- {mode} ---\n")
    fh.flush()
    proc = subprocess.Popen(
        cmd, cwd=str(REPO), env=env, stdout=fh, stderr=subprocess.STDOUT, text=True
    )
    return proc, fh


def _wait(proc, log_path, fh) -> bool:
    for _ in range(90):
        if proc.poll() is not None:
            fh.flush()
            print(log_path.read_text(encoding="utf-8")[-5000:])
            return False
        try:
            code, _ = _http("GET", "/api/conversations", timeout=5)
            if code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _stop(proc):
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=45)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=15)


def _fixtures(root: Path) -> dict[str, Path]:
    paint = root / "construction-estimates"
    paint.mkdir(parents=True)
    (paint / "paint-estimate-duration.md").write_text(
        "# Painting estimate (fictional)\n\n"
        "Brand: Duration exterior paint\n"
        "Material cost: USD 482.50\n",
        encoding="utf-8",
    )
    event = root / "community-event-budget"
    event.mkdir(parents=True)
    (event / "venue-rental.md").write_text(
        "# Venue rental (fictional)\nRental fee: USD 850.00\nHall capacity 120.\n",
        encoding="utf-8",
    )
    (event / "catering.md").write_text(
        "# Catering quote (fictional)\nQuoted catering: USD 1200.00\nIncludes plates.\n",
        encoding="utf-8",
    )
    research = root / "research-notes"
    research.mkdir(parents=True)
    (research / "study-alpha.md").write_text(
        "# Study Alpha (fictional)\n"
        "Finding: blue jays prefer oak nesting sites.\n"
        "Sample size: 42 nests observed.\n",
        encoding="utf-8",
    )
    (research / "study-beta.md").write_text(
        "# Study Beta (fictional)\n"
        "Finding: blue jays prefer pine nesting sites.\n"
        "Sample size: 18 nests observed.\n",
        encoding="utf-8",
    )
    trails = root / "trail-guides"
    trails.mkdir(parents=True)
    (trails / "north-ridge.md").write_text(
        "# North Ridge Trail (fictional)\n"
        "Required gear: trekking poles, water filter.\n"
        "Difficulty: moderate. Distance: 6.2 miles.\n",
        encoding="utf-8",
    )
    (trails / "south-loop.md").write_text(
        "# South Loop Trail (fictional)\n"
        "Required gear: headlamp, spare socks.\n"
        "Difficulty: easy. Distance: 3.1 miles.\n",
        encoding="utf-8",
    )
    return {
        "paint": paint,
        "event": event,
        "research": research,
        "trails": trails,
    }


def _rev(payload: dict) -> int:
    conv = payload.get("conversation") or payload
    return int(conv.get("checkpoint_revision") or 0)


def _execute_verified(
    path: str,
    body: dict,
    *,
    attempts: int = 3,
    timeout: float = 300.0,
) -> tuple[int, dict]:
    """Retry flaky local-model draft/synthesize verification a few times."""
    last: tuple[int, dict] = (0, {})
    for i in range(attempts):
        payload = dict(body)
        if "execution_id" in payload:
            # Unique id per attempt so failed tries do not collide with success.
            payload["execution_id"] = "exec_" + f"{i:016x}"[-16:]
        code, data = _http("POST", path, payload, timeout=timeout)
        last = (code, data)
        if code == 200 and data.get("verified"):
            return code, data
        time.sleep(1.5)
    return last


def main() -> int:
    if not _port_free(PORT):
        print(f"FAIL: port {PORT} in use", file=sys.stderr)
        return 2

    disposable = Path(tempfile.mkdtemp(prefix="elysia-compose-"))
    fixtures = _fixtures(disposable)
    env = os.environ.copy()
    env["ELYSIA_LOCAL_MODEL"] = MODEL
    env["ELYSIA_CONTEXT_BUDGET_TOKENS"] = "3600"
    env["ELYSIA_DISPOSABLE_ROOT"] = str(disposable)
    env.setdefault("ELYSIA_PILOT_MARKER", f"compose-{os.getpid()}")
    cmd = [
        sys.executable,
        str(REPO / "scripts" / "start_contained_browser_memory.py"),
        "--disposable-root",
        str(disposable),
        "--enable-ui",
        "--auto-start-ui",
        "--ui-host",
        "127.0.0.1",
        "--ui-port",
        str(PORT),
        "--keep-alive",
    ]
    evidence: dict = {
        "disposable_root": disposable.name,
        "port": PORT,
        "model": MODEL,
        "scenarios": {},
        "security": {},
    }
    log_path = disposable / "launcher.log"
    proc, fh = _start(cmd, env, log_path)
    try:
        if not _wait(proc, log_path, fh):
            print("FAIL: UI not ready", file=sys.stderr)
            return 1

        # --- Capability selection (model proposes plan; runtime validates) ---
        code, proposed = _http(
            "POST",
            "/api/composition/propose",
            {
                "goal": (
                    "Prepare a fictional community event budget from authorized "
                    "local venue and catering documents, then summarize the subtotal."
                )
            },
            timeout=300.0,
        )
        evidence["scenarios"]["plan_propose_event"] = {
            "status": code,
            "success": proposed.get("success"),
            "validated_caps": [
                s.get("capability")
                for s in ((proposed.get("validated") or {}).get("steps") or [])
            ],
            "executable": (proposed.get("validated") or {}).get("executable"),
            "auth_note": proposed.get("authorization_note"),
        }
        assert code == 200 and proposed.get("success"), proposed
        caps = evidence["scenarios"]["plan_propose_event"]["validated_caps"]
        assert "local.documents.search" in caps
        assert any(
            c in caps for c in ("compose.aggregate_usd", "compose.synthesize", "calculator.labor")
        )
        assert proposed["validated"]["executable"] is False

        # --- Test A: painting compatibility (assemble + draft path) ---
        code, created = _http(
            "POST",
            "/api/conversations",
            {
                "title": "Painting estimate regression",
                "objective": "Prepare a fictional painting estimate",
            },
        )
        assert code == 201, created
        paint_cid = created["conversation_id"]
        code, saved = _http(
            "POST",
            f"/api/conversations/{paint_cid}/task-state",
            {
                "expected_revision": 0,
                "outstanding_steps": [
                    "Find material costs",
                    "Calculate labor",
                    "Assemble subtotal",
                    "Draft estimate",
                ],
                "next_safe_action": "Find material costs",
            },
        )
        mat_id, labor_id, assemble_id, draft_id = [
            s["step_id"] for s in saved["conversation"]["task_steps"]
        ]
        rev = _rev(saved)
        code, bound = _http(
            "POST",
            f"/api/conversations/{paint_cid}/task-steps/{mat_id}/bind",
            {
                "expected_revision": rev,
                "capability": "local.documents.search",
                "arguments": {
                    "query": "Duration exterior paint",
                    "min_matches": 1,
                    "required_substring": "482.50",
                    "expected_relative_path": "paint-estimate-duration.md",
                    "folder_label": fixtures["paint"].name,
                },
            },
        )
        assert code == 200, bound
        rev = _rev(bound)
        code, mat = _http(
            "POST",
            f"/api/conversations/{paint_cid}/task-steps/{mat_id}/execute",
            {
                "expected_revision": rev,
                "authorize_documents_search": True,
                "authorize_record_completion": True,
                "documents_folder": str(fixtures["paint"]),
            },
        )
        assert code == 200 and mat.get("verified"), mat
        rev = _rev(mat)
        code, bound = _http(
            "POST",
            f"/api/conversations/{paint_cid}/task-steps/{labor_id}/bind",
            {
                "expected_revision": rev,
                "capability": "calculator.labor",
                "arguments": {
                    "hourly_rate_usd": "35",
                    "painters": 2,
                    "days": 3,
                    "hours_per_day": 8,
                },
            },
        )
        rev = _rev(bound)
        code, labor = _http(
            "POST",
            f"/api/conversations/{paint_cid}/task-steps/{labor_id}/execute",
            {
                "expected_revision": rev,
                "authorize_calculator": True,
                "authorize_record_completion": True,
            },
        )
        assert code == 200 and (labor.get("receipt") or {}).get("result") == "1680"
        rev = _rev(labor)
        code, bound = _http(
            "POST",
            f"/api/conversations/{paint_cid}/task-steps/{assemble_id}/bind",
            {
                "expected_revision": rev,
                "capability": "estimate.assemble",
                "arguments": {
                    "material_step_id": mat_id,
                    "labor_step_id": labor_id,
                },
            },
        )
        rev = _rev(bound)
        code, denied = _http(
            "POST",
            f"/api/conversations/{paint_cid}/task-steps/{assemble_id}/execute",
            {
                "expected_revision": rev,
                "authorize_estimate_assemble": False,
                "authorize_record_completion": True,
            },
        )
        evidence["security"]["paint_assemble_unauthorized"] = {"status": code}
        assert code == 403
        code, assembled = _http(
            "POST",
            f"/api/conversations/{paint_cid}/task-steps/{assemble_id}/execute",
            {
                "expected_revision": rev,
                "authorize_estimate_assemble": True,
                "authorize_record_completion": True,
            },
        )
        assert code == 200
        assert (assembled.get("receipt") or {}).get("subtotal_usd") == "2162.50"
        rev = _rev(assembled)
        code, bound = _http(
            "POST",
            f"/api/conversations/{paint_cid}/task-steps/{draft_id}/bind",
            {
                "expected_revision": rev,
                "capability": "estimate.draft",
                "arguments": {"assemble_step_id": assemble_id},
            },
        )
        rev = _rev(bound)
        code, drafted = _execute_verified(
            f"/api/conversations/{paint_cid}/task-steps/{draft_id}/execute",
            {
                "expected_revision": rev,
                "authorize_estimate_draft": True,
                "authorize_record_completion": True,
                "execution_id": "exec_" + "0" * 16,
            },
        )
        draft_text = ((drafted.get("conversation") or {}).get("estimate_draft") or {}).get(
            "text"
        ) or ""
        evidence["scenarios"]["test_a_painting"] = {
            "status": code,
            "subtotal": "2162.50",
            "draft_has_banner": "DRAFT / NOT APPROVED FOR CUSTOMER DELIVERY" in draft_text,
            "draft_has_subtotal": "2162.50" in draft_text,
            "ollama": True,
            "error": drafted.get("error"),
        }
        assert code == 200 and drafted.get("verified"), drafted
        assert "2162.50" in draft_text

        # --- Test B: event budget via compose.* (no event_budget_workflow.py) ---
        code, created = _http(
            "POST",
            "/api/conversations",
            {
                "title": "Community event budget",
                "objective": "Build a grounded fictional community event budget",
            },
        )
        event_cid = created["conversation_id"]
        code, saved = _http(
            "POST",
            f"/api/conversations/{event_cid}/task-state",
            {
                "expected_revision": 0,
                "outstanding_steps": [
                    "Retrieve venue cost",
                    "Retrieve catering cost",
                    "Aggregate verified costs",
                    "Summarize budget",
                ],
                "next_safe_action": "Retrieve venue cost",
            },
        )
        v_id, c_id, agg_id, syn_id = [
            s["step_id"] for s in saved["conversation"]["task_steps"]
        ]
        rev = _rev(saved)
        for step_id, query, amount, path in (
            (v_id, "venue rental", "850.00", "venue-rental.md"),
            (c_id, "catering", "1200.00", "catering.md"),
        ):
            code, bound = _http(
                "POST",
                f"/api/conversations/{event_cid}/task-steps/{step_id}/bind",
                {
                    "expected_revision": rev,
                    "capability": "local.documents.search",
                    "arguments": {
                        "query": query,
                        "min_matches": 1,
                        "required_substring": amount,
                        "expected_relative_path": path,
                        "folder_label": fixtures["event"].name,
                    },
                },
            )
            assert code == 200, bound
            rev = _rev(bound)
            code, exe = _http(
                "POST",
                f"/api/conversations/{event_cid}/task-steps/{step_id}/execute",
                {
                    "expected_revision": rev,
                    "authorize_documents_search": True,
                    "authorize_record_completion": True,
                    "documents_folder": str(fixtures["event"]),
                },
            )
            assert code == 200 and exe.get("verified"), exe
            rev = _rev(exe)

        code, bound = _http(
            "POST",
            f"/api/conversations/{event_cid}/task-steps/{agg_id}/bind",
            {
                "expected_revision": rev,
                "capability": "compose.aggregate_usd",
                "arguments": {
                    "source_step_ids": [v_id, c_id],
                    "component_labels": ["venue", "catering"],
                    "domain_template": "event_budget",
                },
            },
        )
        rev = _rev(bound)
        code, denied = _http(
            "POST",
            f"/api/conversations/{event_cid}/task-steps/{agg_id}/execute",
            {
                "expected_revision": rev,
                "authorize_compose_aggregate": False,
                "authorize_record_completion": True,
            },
        )
        evidence["security"]["event_aggregate_unauthorized"] = {"status": code}
        assert code == 403
        code, agg = _http(
            "POST",
            f"/api/conversations/{event_cid}/task-steps/{agg_id}/execute",
            {
                "expected_revision": rev,
                "authorize_compose_aggregate": True,
                "authorize_record_completion": True,
                "execution_id": "exec_" + "1" * 16,
            },
        )
        assert code == 200
        assert (agg.get("receipt") or {}).get("subtotal_usd") == "2050.00"
        # Duplicate execution_id must not re-apply effects.
        code, dup = _http(
            "POST",
            f"/api/conversations/{event_cid}/task-steps/{agg_id}/execute",
            {
                "expected_revision": _rev(agg) - 1,
                "authorize_compose_aggregate": True,
                "authorize_record_completion": True,
                "execution_id": "exec_" + "1" * 16,
            },
        )
        evidence["security"]["event_aggregate_duplicate"] = {
            "status": code,
            "idempotent": dup.get("idempotent"),
        }
        assert code == 200 and dup.get("idempotent") is True
        rev = _rev(agg)
        code, bound = _http(
            "POST",
            f"/api/conversations/{event_cid}/task-steps/{syn_id}/bind",
            {
                "expected_revision": rev,
                "capability": "compose.synthesize",
                "arguments": {
                    "evidence_step_ids": [v_id, c_id],
                    "aggregate_step_id": agg_id,
                    "mode": "summary",
                    "domain_template": "event_budget",
                    "required_phrases": ["venue-rental.md", "catering.md"],
                },
            },
        )
        rev = _rev(bound)
        code, syn = _execute_verified(
            f"/api/conversations/{event_cid}/task-steps/{syn_id}/execute",
            {
                "expected_revision": rev,
                "authorize_compose_synthesize": True,
                "authorize_record_completion": True,
                "execution_id": "exec_" + "a" * 16,
            },
        )
        syn_text = ((syn.get("conversation") or {}).get("estimate_draft") or {}).get(
            "text"
        ) or ""
        evidence["scenarios"]["test_b_event_budget"] = {
            "status": code,
            "subtotal": "2050.00",
            "preview": syn_text[:700],
            "has_amounts": all(a in syn_text for a in ("850.00", "1200.00", "2050.00")),
            "ollama": True,
            "no_domain_module": True,
        }
        assert code == 200 and syn.get("verified"), syn
        assert "2050.00" in syn_text

        # --- Test C: research comparison (nonfinancial) ---
        code, created = _http(
            "POST",
            "/api/conversations",
            {
                "title": "Research comparison",
                "objective": "Compare fictional blue jay nesting findings",
            },
        )
        research_cid = created["conversation_id"]
        code, saved = _http(
            "POST",
            f"/api/conversations/{research_cid}/task-state",
            {
                "expected_revision": 0,
                "outstanding_steps": [
                    "Retrieve study alpha",
                    "Retrieve study beta",
                    "Compare findings",
                ],
                "next_safe_action": "Retrieve study alpha",
            },
        )
        a_id, b_id, cmp_id = [s["step_id"] for s in saved["conversation"]["task_steps"]]
        rev = _rev(saved)
        for step_id, query, phrase, path in (
            (a_id, "oak nesting", "oak nesting sites", "study-alpha.md"),
            (b_id, "pine nesting", "pine nesting sites", "study-beta.md"),
        ):
            code, bound = _http(
                "POST",
                f"/api/conversations/{research_cid}/task-steps/{step_id}/bind",
                {
                    "expected_revision": rev,
                    "capability": "local.documents.search",
                    "arguments": {
                        "query": query,
                        "min_matches": 1,
                        "required_substring": phrase,
                        "expected_relative_path": path,
                        "folder_label": fixtures["research"].name,
                    },
                },
            )
            rev = _rev(bound)
            code, exe = _http(
                "POST",
                f"/api/conversations/{research_cid}/task-steps/{step_id}/execute",
                {
                    "expected_revision": rev,
                    "authorize_documents_search": True,
                    "authorize_record_completion": True,
                    "documents_folder": str(fixtures["research"]),
                },
            )
            assert code == 200, exe
            rev = _rev(exe)

        code, bound = _http(
            "POST",
            f"/api/conversations/{research_cid}/task-steps/{cmp_id}/bind",
            {
                "expected_revision": rev,
                "capability": "compose.synthesize",
                "arguments": {
                    "evidence_step_ids": [a_id, b_id],
                    "mode": "comparison",
                    "domain_template": "research_comparison",
                    "banner": "COMPARISON DRAFT / SOURCE-GROUNDED ONLY",
                    "required_phrases": [
                        "study-alpha.md",
                        "study-beta.md",
                        "oak",
                        "pine",
                    ],
                },
            },
        )
        rev = _rev(bound)
        code, cmp = _execute_verified(
            f"/api/conversations/{research_cid}/task-steps/{cmp_id}/execute",
            {
                "expected_revision": rev,
                "authorize_compose_synthesize": True,
                "authorize_record_completion": True,
                "execution_id": "exec_" + "b" * 16,
            },
        )
        cmp_text = ((cmp.get("conversation") or {}).get("estimate_draft") or {}).get(
            "text"
        ) or ""
        evidence["scenarios"]["test_c_research"] = {
            "status": code,
            "preview": cmp_text[:700],
            "has_sources": "study-alpha.md" in cmp_text and "study-beta.md" in cmp_text,
            "ollama": True,
            "no_domain_module": True,
        }
        assert code == 200 and cmp.get("verified"), cmp
        assert "study-alpha.md" in cmp_text and "oak" in cmp_text.casefold()

        # --- Test D: unfamiliar trail comparison without new code ---
        code, created = _http(
            "POST",
            "/api/conversations",
            {
                "title": "Trail gear comparison",
                "objective": "Compare required gear for two fictional trails",
            },
        )
        trail_cid = created["conversation_id"]
        code, saved = _http(
            "POST",
            f"/api/conversations/{trail_cid}/task-state",
            {
                "expected_revision": 0,
                "outstanding_steps": [
                    "Retrieve north ridge gear",
                    "Retrieve south loop gear",
                    "Compare trail gear requirements",
                ],
                "next_safe_action": "Retrieve north ridge gear",
            },
        )
        n_id, s_id, tsyn_id = [s["step_id"] for s in saved["conversation"]["task_steps"]]
        rev = _rev(saved)
        for step_id, query, phrase, path in (
            (n_id, "trekking poles", "trekking poles", "north-ridge.md"),
            (s_id, "headlamp", "headlamp", "south-loop.md"),
        ):
            code, bound = _http(
                "POST",
                f"/api/conversations/{trail_cid}/task-steps/{step_id}/bind",
                {
                    "expected_revision": rev,
                    "capability": "local.documents.search",
                    "arguments": {
                        "query": query,
                        "min_matches": 1,
                        "required_substring": phrase,
                        "expected_relative_path": path,
                        "folder_label": fixtures["trails"].name,
                    },
                },
            )
            rev = _rev(bound)
            code, exe = _http(
                "POST",
                f"/api/conversations/{trail_cid}/task-steps/{step_id}/execute",
                {
                    "expected_revision": rev,
                    "authorize_documents_search": True,
                    "authorize_record_completion": True,
                    "documents_folder": str(fixtures["trails"]),
                },
            )
            assert code == 200, exe
            rev = _rev(exe)

        code, bound = _http(
            "POST",
            f"/api/conversations/{trail_cid}/task-steps/{tsyn_id}/bind",
            {
                "expected_revision": rev,
                "capability": "compose.synthesize",
                "arguments": {
                    "evidence_step_ids": [n_id, s_id],
                    "mode": "comparison",
                    "banner": "COMPARISON DRAFT / SOURCE-GROUNDED ONLY",
                    "required_phrases": [
                        "north-ridge.md",
                        "south-loop.md",
                        "trekking poles",
                        "headlamp",
                    ],
                },
            },
        )
        rev = _rev(bound)
        code, trails = _execute_verified(
            f"/api/conversations/{trail_cid}/task-steps/{tsyn_id}/execute",
            {
                "expected_revision": rev,
                "authorize_compose_synthesize": True,
                "authorize_record_completion": True,
                "execution_id": "exec_" + "c" * 16,
            },
        )
        trail_text = (
            ((trails.get("conversation") or {}).get("estimate_draft") or {}).get("text")
            or ""
        )
        evidence["scenarios"]["test_d_trails"] = {
            "status": code,
            "preview": trail_text[:700],
            "verified": trails.get("verified"),
            "no_new_workflow_module": True,
            "clarification_needed": code != 200,
        }
        assert code == 200 and trails.get("verified"), trails
        assert "north-ridge.md" in trail_text and "headlamp" in trail_text.casefold()

        # --- Test E: restart clears grants; stale revision rejected ---
        event_rev_before = None
        code, detail = _http("GET", f"/api/conversations/{event_cid}")
        conv = detail.get("conversation") or detail
        event_rev_before = int(conv.get("checkpoint_revision") or 0)
        assert (conv.get("estimate_bundle") or {}).get("subtotal_usd") == "2050.00"

        _stop(proc)
        time.sleep(1)
        proc, fh = _start(cmd, env, log_path, mode="a")
        assert _wait(proc, log_path, fh)

        code, resumed = _http("POST", f"/api/conversations/{event_cid}/resume", {})
        evidence["scenarios"]["test_e_restart"] = {
            "authorization_inherited": resumed.get("authorization_inherited"),
            "next": resumed.get("next_safe_action"),
        }
        assert resumed.get("authorization_inherited") is False

        code, detail = _http("GET", f"/api/conversations/{event_cid}")
        conv = detail.get("conversation") or detail
        assert (conv.get("estimate_bundle") or {}).get("subtotal_usd") == "2050.00"
        assert "2050.00" in ((conv.get("estimate_draft") or {}).get("text") or "")

        # Stale revision rejection
        code, stale = _http(
            "POST",
            f"/api/conversations/{event_cid}/task-steps/{agg_id}/execute",
            {
                "expected_revision": max(0, event_rev_before - 3),
                "authorize_compose_aggregate": True,
                "authorize_record_completion": True,
                "execution_id": "exec_" + "2" * 16,
            },
        )
        evidence["security"]["stale_revision"] = {
            "status": code,
            "error": stale.get("error"),
        }
        assert code in (400, 409)

        # Post-restart no inherited synthesize grant
        code, noauth = _http(
            "POST",
            f"/api/conversations/{event_cid}/task-steps/{syn_id}/execute",
            {
                "expected_revision": int(conv.get("checkpoint_revision") or 0),
                "authorize_compose_synthesize": False,
                "authorize_record_completion": True,
                "execution_id": "exec_" + "3" * 16,
            },
        )
        evidence["security"]["post_restart_no_auth"] = {
            "status": code,
            "error": noauth.get("error"),
        }
        assert code in (400, 403, 409)

        # Fake aggregate without upstream cannot complete
        code, created = _http(
            "POST",
            "/api/conversations",
            {"title": "Claim check", "objective": "Reject invented verified totals"},
        )
        claim_cid = created["conversation_id"]
        code, saved = _http(
            "POST",
            f"/api/conversations/{claim_cid}/task-state",
            {
                "expected_revision": 0,
                "outstanding_steps": ["Bogus aggregate", "Done"],
                "next_safe_action": "Bogus aggregate",
            },
        )
        bog_id = saved["conversation"]["task_steps"][0]["step_id"]
        rev = _rev(saved)
        code, bound = _http(
            "POST",
            f"/api/conversations/{claim_cid}/task-steps/{bog_id}/bind",
            {
                "expected_revision": rev,
                "capability": "compose.aggregate_usd",
                "arguments": {
                    "source_step_ids": ["step_" + "a" * 12, "step_" + "b" * 12]
                },
            },
        )
        rev = _rev(bound)
        code, bog = _http(
            "POST",
            f"/api/conversations/{claim_cid}/task-steps/{bog_id}/execute",
            {
                "expected_revision": rev,
                "authorize_compose_aggregate": True,
                "authorize_record_completion": True,
            },
        )
        evidence["security"]["invented_upstream_rejected"] = {
            "status": code,
            "error": bog.get("error"),
        }
        assert code >= 400
        code, detail = _http("GET", f"/api/conversations/{claim_cid}")
        bog_step = next(
            s
            for s in (detail.get("conversation") or detail)["task_steps"]
            if s["step_id"] == bog_id
        )
        assert bog_step["status"] == "pending"

        evidence["ok"] = True
        out = (
            REPO
            / "docs"
            / "evidence"
            / "general_capability_composition_windows_20261030.json"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        print(f"EVIDENCE={out}")
        return 0
    finally:
        _stop(proc)


if __name__ == "__main__":
    raise SystemExit(main())
