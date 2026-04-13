# Tests for task_router module path in execute_capability_kind (route-metadata success rule).

from __future__ import annotations

from project_guardian.capability_execution import (
    execute_capability_kind,
    get_task_router_gate_metrics_snapshot,
    reset_task_router_gate_metrics,
)


class _FakeTaskRouter:
    def __init__(self, result):
        self._result = result
        self.last_task_type = None

    def route_task(self, task_type: str, context=None):
        self.last_task_type = task_type
        return self._result


def _guardian(fake: _FakeTaskRouter):
    return type("G", (), {"_modules": {"task_router": fake}})()


def test_real_task_route_metadata_counts_as_success():
    fake = _FakeTaskRouter(
        {
            "task_type": "text-gen",
            "routed_to": "elysia_builtin_web",
            "score": 60.0,
            "available_tools": 0,
        }
    )
    g = _guardian(fake)
    out = execute_capability_kind(
        g,
        "module",
        "task_router",
        {
            "structured_task": {
                "task_type": "text-gen",
                "objective": "hello",
            }
        },
    )
    assert out["success"] is True
    assert out["result"]["routed_to"] == "elysia_builtin_web"


def test_payload_content_still_success():
    fake = _FakeTaskRouter(
        {
            "task_type": "x",
            "routed_to": "tool_a",
            "score": 10.0,
            "data": {"answer": 1},
        }
    )
    g = _guardian(fake)
    out = execute_capability_kind(
        g,
        "module",
        "task_router",
        {"structured_task": {"task_type": "custom", "objective": "z"}},
    )
    assert out["success"] is True


def test_empty_route_still_failure():
    fake = _FakeTaskRouter(
        {
            "task_type": "text-gen",
            "routed_to": None,
            "score": -1.0,
        }
    )
    g = _guardian(fake)
    out = execute_capability_kind(
        g,
        "module",
        "task_router",
        {"structured_task": {"task_type": "text-gen"}},
    )
    assert out["success"] is False
    assert "task_router_no_matching_tool" in str(out.get("error", ""))


def test_health_probe_route_metadata_does_not_count_as_success():
    fake = _FakeTaskRouter(
        {
            "task_type": "routing_probe",
            "routed_to": "elysia_builtin_llm",
            "score": 60.0,
            "available_tools": 0,
        }
    )
    g = _guardian(fake)
    out = execute_capability_kind(
        g,
        "module",
        "task_router",
        {
            "structured_task": {
                "task_type": "routing_probe",
                "_guardian_router_health_probe": True,
                "objective": "probe",
            }
        },
    )
    assert out["success"] is False


def test_health_probe_with_payload_succeeds():
    fake = _FakeTaskRouter(
        {
            "task_type": "routing_probe",
            "routed_to": "elysia_builtin_llm",
            "score": 60.0,
            "data": {"ok": True},
        }
    )
    g = _guardian(fake)
    out = execute_capability_kind(
        g,
        "module",
        "task_router",
        {
            "structured_task": {
                "task_type": "routing_probe",
                "_guardian_router_health_probe": True,
            }
        },
    )
    assert out["success"] is True


def test_missing_score_fails_even_with_routed_to():
    fake = _FakeTaskRouter(
        {
            "routed_to": "elysia_builtin_llm",
            "score": None,
        }
    )
    g = _guardian(fake)
    out = execute_capability_kind(
        g,
        "module",
        "task_router",
        {"structured_task": {"task_type": "self_task"}},
    )
    assert out["success"] is False


def test_gate_metrics_increment_on_real_task():
    reset_task_router_gate_metrics()
    before = get_task_router_gate_metrics_snapshot()["real_task_events"]
    fake = _FakeTaskRouter(
        {"task_type": "z", "routed_to": "tool_x", "score": 1.0},
    )
    g = _guardian(fake)
    execute_capability_kind(
        g,
        "module",
        "task_router",
        {"structured_task": {"task_type": "custom_tt"}},
    )
    after = get_task_router_gate_metrics_snapshot()
    assert after["real_task_events"] == before + 1
    assert after["ok_route_metadata"] >= 1
    assert after["by_routed_to_on_success"].get("tool_x", 0) >= 1
