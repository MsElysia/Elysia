# Canonical routing task_type inference + TaskRouter strict-tag behavior.

from __future__ import annotations

import sys
from pathlib import Path

from project_guardian.routing_task_type import infer_canonical_routing_task_type

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core_modules" / "elysia_core_comprehensive"))

from ai_tool_registry import TaskRouter, ToolRegistry  # noqa: E402


def test_infer_bounded_browse_before_plain_url():
    tt, rsn = infer_canonical_routing_task_type("Explore https://example.com/docs deeply")
    assert tt == "bounded_browse"
    assert rsn == "keyword_bounded_browse"


def test_infer_social_moltbook_before_plain_moltbook():
    tt, rsn = infer_canonical_routing_task_type("Social observe moltbook threads for AI discussion")
    assert tt == "social_moltbook_observe"
    assert rsn == "keyword_social_moltbook_observe"


def test_infer_moltbook_before_bounded_and_fetch():
    tt, rsn = infer_canonical_routing_task_type("Scroll moltbook.com for community posts")
    assert tt == "moltbook_browse"
    assert rsn == "keyword_moltbook"


def test_infer_web_fetch_url():
    tt, rsn = infer_canonical_routing_task_type("Please fetch https://example.com/page")
    assert tt == "fetch"
    assert rsn == "keyword_web"


def test_infer_exec_script():
    tt, rsn = infer_canonical_routing_task_type("Run this command: bash ./setup.sh")
    assert tt == "script"
    assert rsn == "keyword_exec"


def test_infer_llm_completion():
    tt, rsn = infer_canonical_routing_task_type("Summarize the quarterly report")
    assert tt == "completion"
    assert rsn == "keyword_llm"


def test_infer_fallback_generic():
    tt, rsn = infer_canonical_routing_task_type("do something useful")
    assert tt == "self_task"
    assert rsn == "fallback_generic"


def test_task_router_strict_tag_fetch():
    r = ToolRegistry()
    r.ensure_minimal_builtin_tools()
    tr = TaskRouter(r)
    out = tr.route_task("fetch", {})
    assert out["routed_to"] == "elysia_builtin_web"
    assert out["available_tools"] >= 1


def test_task_router_bounded_browse_routes_to_bounded_browser():
    r = ToolRegistry()
    r.ensure_minimal_builtin_tools()
    tr = TaskRouter(r)
    out = tr.route_task("bounded_browse", {})
    assert out["routed_to"] == "elysia_bounded_browser"
    assert out["available_tools"] >= 1


def test_task_router_moltbook_browse_routes_to_moltbook_browser():
    r = ToolRegistry()
    r.ensure_minimal_builtin_tools()
    tr = TaskRouter(r)
    out = tr.route_task("moltbook_browse", {})
    assert out["routed_to"] == "elysia_moltbook_browser"
    assert out["available_tools"] >= 1


def test_task_router_social_moltbook_routes_to_social_intel():
    r = ToolRegistry()
    r.ensure_minimal_builtin_tools()
    tr = TaskRouter(r)
    out = tr.route_task("social_moltbook_observe", {})
    assert out["routed_to"] == "elysia_social_intel"
    assert out["available_tools"] >= 1


def test_task_router_strict_tag_script():
    r = ToolRegistry()
    r.ensure_minimal_builtin_tools()
    tr = TaskRouter(r)
    out = tr.route_task("script", {})
    assert out["routed_to"] == "elysia_builtin_exec"


def test_task_router_strict_tag_completion():
    r = ToolRegistry()
    r.ensure_minimal_builtin_tools()
    tr = TaskRouter(r)
    out = tr.route_task("completion", {})
    assert out["routed_to"] == "elysia_builtin_llm"


def test_self_task_behavior_unchanged_generic():
    r = ToolRegistry()
    r.ensure_minimal_builtin_tools()
    tr = TaskRouter(r)
    out = tr.route_task("self_task", {})
    # tie-break order still applies
    assert out["routed_to"] == "elysia_builtin_web"


def test_bridge_merge_payload_emits_fetch_for_url_goal():
    from project_guardian.orchestration.tools.bridge import _merge_payload
    from project_guardian.orchestration.tools.schemas import ActionIntent

    intent = ActionIntent(
        action_type="probe",
        target_kind="module",
        target_name="task_router",
        payload={},
        confidence=0.5,
        rationale="test",
    )
    ctx = {"goal": "Review https://example.org/path", "archetype": "orch_test", "task_id": "t1"}
    out = _merge_payload(intent, ctx)
    st = out.get("structured_task")
    assert isinstance(st, dict)
    assert st.get("task_type") == "fetch"
    assert st.get("payload", {}).get("routing_inference") == "keyword_web"
