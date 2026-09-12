# Tie-break behavior for TaskRouter (core_modules ai_tool_registry).

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core_modules" / "elysia_core_comprehensive"))

from ai_tool_registry import TaskRouter, ToolRegistry  # noqa: E402


@pytest.fixture
def builtins_router() -> TaskRouter:
    r = ToolRegistry()
    r.ensure_minimal_builtin_tools()
    return TaskRouter(r)


def test_self_task_stub_tie_prefers_llm_over_url_fetch(builtins_router: TaskRouter):
    """Generic self_task should not prefer the URL fetcher when no URL-bearing payload exists."""
    out = builtins_router.route_task("self_task", {})
    assert out["routed_to"] == "elysia_builtin_llm"
    assert out["score"] == 60.0


def test_text_gen_keyword_prefers_llm(builtins_router: TaskRouter):
    out = builtins_router.route_task("text-gen", {})
    assert out["routed_to"] == "elysia_builtin_llm"


def test_explicit_task_type_web_tag_routes_to_web_tool(builtins_router: TaskRouter):
    """task_type 'web' appears only on builtin web tool's capability list among ties."""
    out = builtins_router.route_task("web", {})
    assert out["routed_to"] == "elysia_builtin_web"


def test_canonical_fetch_task_prefers_builtin_web(builtins_router: TaskRouter):
    out = builtins_router.route_task("fetch", {})
    assert out["routed_to"] == "elysia_builtin_web"


def test_health_probe_map_order_unchanged_llm_first(builtins_router: TaskRouter):
    out = builtins_router.route_task(
        "routing_probe",
        {"_guardian_router_health_probe": True, "objective": "probe"},
    )
    assert out["routed_to"] == "elysia_builtin_llm"
    assert out.get("diagnostic_pick_rule") == "max_score_then_first_in_tools_map_order"


def test_unknown_task_still_routes(builtins_router: TaskRouter):
    out = builtins_router.route_task("totally_unknown_xyz", {})
    assert out["routed_to"] in (
        "elysia_builtin_llm",
        "elysia_builtin_web",
        "elysia_builtin_exec",
    )
