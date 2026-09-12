# project_guardian/tests/test_unified_llm_route.py
"""Unified chat route: prompt stack parity on cloud paths (no live APIs)."""

import inspect
import json

import pytest


@pytest.fixture
def patch_quota_guards(monkeypatch):
    """Keep OpenAI in the provider order for short prompts."""
    monkeypatch.setattr(
        "project_guardian.openai_degraded.openai_insufficient_quota_reasoning_blocked",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(
        "project_guardian.openai_degraded.openai_reasoning_long_cooldown_active",
        lambda: False,
    )


def test_snapshot_unified_chat_provider_order_has_try_order(patch_quota_guards, monkeypatch):
    from project_guardian.unified_llm_route import snapshot_unified_chat_provider_order

    s = snapshot_unified_chat_provider_order(
        user_text="hi",
        task_type="conversation",
        registry=None,
        require_autonomy_safe_reasoning=False,
        log_quota_skip=False,
    )
    assert s.get("try_order")
    assert s.get("primary")
    assert s.get("route_task_type") == "simple"


def test_unified_chat_openai_prepends_guardian_prompt_stack(patch_quota_guards, monkeypatch):
    from project_guardian.unified_llm_route import unified_chat_completion

    monkeypatch.setattr(
        "project_guardian.unified_llm_route.decide_chat_llm_backend",
        lambda user_text, registry=None, **kwargs: ("openai", "test_route"),
    )
    monkeypatch.setattr(
        "project_guardian.unified_llm_route.try_chat_capability_execute",
        lambda *a, **k: None,
    )

    captured = []

    def openai_capture(messages, max_tokens):
        captured.append(list(messages))
        return "ok", ""

    reply, err, meta = unified_chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=50,
        guardian=None,
        cloud_openai_call=openai_capture,
        cloud_openrouter_call=lambda m, mt: ("", "skip"),
        module_name="planner",
        agent_name="orchestrator",
    )

    assert reply == "ok" and not err
    assert captured
    assert captured[0][0]["role"] == "system"
    body = captured[0][0]["content"].lower()
    assert "planner" in body or "elysia" in body
    assert meta.get("backend") == "openai"


def test_unified_chat_openrouter_prepends_same_stack(patch_quota_guards, monkeypatch):
    from project_guardian.unified_llm_route import unified_chat_completion

    monkeypatch.setattr(
        "project_guardian.unified_llm_route.decide_chat_llm_backend",
        lambda user_text, registry=None, **kwargs: ("openrouter", "or_test"),
    )
    monkeypatch.setattr(
        "project_guardian.unified_llm_route.try_chat_capability_execute",
        lambda *a, **k: None,
    )

    captured = []

    def or_capture(messages, max_tokens):
        captured.append(list(messages))
        return "ok", ""

    reply, err, meta = unified_chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=50,
        guardian=None,
        cloud_openai_call=lambda m, mt: ("", "skip"),
        cloud_openrouter_call=or_capture,
        module_name="planner",
        agent_name="orchestrator",
    )

    assert reply == "ok" and not err
    assert captured[0][0]["role"] == "system"
    assert "planner" in captured[0][0]["content"].lower() or "elysia" in captured[0][0]["content"].lower()
    assert meta.get("backend") == "openrouter"


def test_unified_chat_cloud_logs_prompt_stack_fields(caplog, patch_quota_guards, monkeypatch):
    import logging

    caplog.set_level(logging.INFO)
    from project_guardian.unified_llm_route import unified_chat_completion

    monkeypatch.setattr(
        "project_guardian.unified_llm_route.decide_chat_llm_backend",
        lambda user_text, registry=None, **kwargs: ("openai", "t"),
    )
    monkeypatch.setattr(
        "project_guardian.unified_llm_route.try_chat_capability_execute",
        lambda *a, **k: None,
    )

    unified_chat_completion(
        messages=[{"role": "user", "content": "x"}],
        max_tokens=10,
        guardian=None,
        cloud_openai_call=lambda m, mt: ("r", ""),
        cloud_openrouter_call=lambda m, mt: ("", ""),
        module_name="planner",
        agent_name="orchestrator",
    )
    text = caplog.text
    assert "prompt_core_name=" in text or "prompt_core_name=elysia_core" in text.replace(" ", "")
    assert "legacy_prompt_path=False" in text
    assert "module_name=planner" in text
    assert "call_id=ullm_" in text
    assert "route_task_type=simple" in text
    assert "attempt_index=1" in text
    assert "prompt_hash=" in text


def test_unified_chat_invalid_module_raises():
    from project_guardian.unified_llm_route import unified_chat_completion

    with pytest.raises(ValueError, match="module_name"):
        unified_chat_completion(
            messages=[{"role": "user", "content": "a"}],
            max_tokens=5,
            guardian=None,
            cloud_openai_call=lambda m, mt: ("", ""),
            cloud_openrouter_call=lambda m, mt: ("", ""),
            module_name="   ",
            agent_name=None,
        )


def test_decide_chat_backend_unchanged_inputs(patch_quota_guards, monkeypatch):
    """Provider selection still uses user_text + registry; only messages to cloud gain the stack."""
    from project_guardian import unified_llm_route as u

    calls = []

    def capture_backend(user_text, registry=None, **kwargs):
        calls.append((user_text, registry))
        return ("openai", "ok")

    monkeypatch.setattr(u, "decide_chat_llm_backend", capture_backend)
    monkeypatch.setattr(u, "try_chat_capability_execute", lambda *a, **k: None)

    u.unified_chat_completion(
        messages=[{"role": "user", "content": "hello world"}],
        max_tokens=20,
        guardian=None,
        cloud_openai_call=lambda m, mt: ("x", ""),
        cloud_openrouter_call=lambda m, mt: ("", ""),
        module_name="planner",
        agent_name="orchestrator",
    )
    assert calls and calls[0][0] == "hello world"


def test_unified_chat_require_autonomy_safe_defaults_false():
    from project_guardian.unified_llm_route import unified_chat_completion

    sig = inspect.signature(unified_chat_completion)
    assert sig.parameters["require_autonomy_safe_reasoning"].default is False


def test_chat_tool_first_skips_builtin_llm_transport(monkeypatch):
    from project_guardian.unified_llm_route import try_chat_capability_execute

    class _Reg:
        def refresh_if_due(self, guardian, min_interval_sec=15.0):
            return {}

        def get_relevant_capabilities(self, text, guardian, snapshot=None, top_k=8):
            return [
                {
                    "name": "elysia_builtin_llm",
                    "type": "tool",
                    "match_score": 99.0,
                    "health": "ok",
                }
            ]

    g = type("G", (), {"_orchestration_registry": _Reg()})()
    called = []

    def fake_execute(*args, **kwargs):
        called.append((args, kwargs))
        return {"success": True, "result": {"data": "should not run"}}

    monkeypatch.setattr("project_guardian.capability_execution.execute_capability_kind", fake_execute)
    assert try_chat_capability_execute("please reason about this", g) is None
    assert called == []


def test_unified_autonomy_chat_completion_delegates_with_safe_flag(monkeypatch):
    captured: dict = {}

    def fake_unified(**kwargs):
        captured.update(kwargs)
        return ("a", "", {"backend": "ollama", "reason": "t"})

    monkeypatch.setattr("project_guardian.unified_llm_route.unified_chat_completion", fake_unified)
    from project_guardian.unified_llm_route import unified_autonomy_chat_completion

    reply, err, meta = unified_autonomy_chat_completion(
        messages=[{"role": "user", "content": "x"}],
        max_tokens=5,
        guardian=None,
        cloud_openai_call=lambda m, t: ("", ""),
        cloud_openrouter_call=lambda m, t: ("", ""),
        module_name="planner",
    )
    assert captured.get("require_autonomy_safe_reasoning") is True
    assert reply == "a" and not err
    assert meta.get("backend") == "ollama"


def test_unified_chat_default_no_autonomy_safe_observability(patch_quota_guards, monkeypatch):
    from project_guardian.unified_llm_route import unified_chat_completion

    monkeypatch.setattr(
        "project_guardian.unified_llm_route.decide_chat_llm_backend",
        lambda user_text, registry=None, **kwargs: ("openai", "test_route"),
    )
    monkeypatch.setattr(
        "project_guardian.unified_llm_route.try_chat_capability_execute",
        lambda *a, **k: None,
    )

    reply, err, meta = unified_chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=50,
        guardian=None,
        cloud_openai_call=lambda m, mt: ("ok", ""),
        cloud_openrouter_call=lambda m, mt: ("", "skip"),
        module_name="planner",
        agent_name="orchestrator",
    )
    assert reply == "ok" and not err
    assert meta.get("autonomy_reasoning_safe_required") is not True
    assert meta.get("autonomy_reasoning_actual_backend") is None


def test_autonomy_safe_completion_sets_actual_backend_observability(patch_quota_guards, monkeypatch):
    from project_guardian.unified_llm_route import unified_chat_completion

    monkeypatch.setattr(
        "project_guardian.unified_llm_route.decide_chat_llm_backend",
        lambda user_text, registry=None, **kwargs: ("openai", "test_route"),
    )
    monkeypatch.setattr(
        "project_guardian.unified_llm_route.try_chat_capability_execute",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "project_guardian.planner_readiness.select_autonomy_safe_reasoning_route",
        lambda: {"provider": "openai", "block_reason": None},
    )

    reply, err, meta = unified_chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=50,
        guardian=None,
        cloud_openai_call=lambda m, mt: ("ok", ""),
        cloud_openrouter_call=lambda m, mt: ("", "skip"),
        module_name="planner",
        agent_name="orchestrator",
        require_autonomy_safe_reasoning=True,
    )
    assert reply == "ok" and not err
    assert meta.get("autonomy_reasoning_safe_required") is True
    assert meta.get("autonomy_reasoning_actual_backend") == "openai"
    assert meta.get("backend") == "openai"


def test_unified_autonomy_safe_local_route_skips_cloud_transports(patch_quota_guards, monkeypatch):
    openai_calls: list = []
    or_calls: list = []

    def dec(user_text, registry=None, **kw):
        assert kw.get("require_autonomy_safe") is True
        return ("ollama", "local_pref")

    monkeypatch.setattr("project_guardian.unified_llm_route.decide_chat_llm_backend", dec)
    monkeypatch.setattr(
        "project_guardian.unified_llm_route.try_chat_capability_execute",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "project_guardian.planner_readiness.select_autonomy_safe_reasoning_route",
        lambda: {"provider": None, "block_reason": "no_safe_provider"},
    )

    def oa(m, t):
        openai_calls.append(1)
        return "", ""

    def oor(m, t):
        or_calls.append(1)
        return "", ""

    monkeypatch.setattr(
        "project_guardian.mistral_engine.MistralEngine.complete_chat",
        lambda self, *a, **k: "local_body",
    )

    from project_guardian.unified_llm_route import unified_autonomy_chat_completion

    reply, err, meta = unified_autonomy_chat_completion(
        messages=[{"role": "user", "content": "short"}],
        max_tokens=30,
        guardian=None,
        cloud_openai_call=oa,
        cloud_openrouter_call=oor,
        module_name="planner",
    )
    assert reply == "local_body"
    assert not openai_calls and not or_calls
    assert meta.get("autonomy_reasoning_actual_backend") == "ollama"


def test_llm_trace_jsonl_appends_when_env_set(tmp_path, patch_quota_guards, monkeypatch):
    """Optional Langfuse-style JSONL trace (ELYSIA_LLM_TRACE_JSONL)."""
    trace_path = tmp_path / "llm_trace.jsonl"
    monkeypatch.setenv("ELYSIA_LLM_TRACE_JSONL", str(trace_path))
    monkeypatch.setenv("ELYSIA_LLM_TRACE_PROJECT", "pytest")

    from project_guardian.unified_llm_route import unified_chat_completion

    monkeypatch.setattr(
        "project_guardian.unified_llm_route.decide_chat_llm_backend",
        lambda user_text, registry=None, **kwargs: ("openai", "test_route"),
    )
    monkeypatch.setattr(
        "project_guardian.unified_llm_route.try_chat_capability_execute",
        lambda *a, **k: None,
    )

    reply, err, meta = unified_chat_completion(
        messages=[{"role": "user", "content": "trace me"}],
        max_tokens=20,
        guardian=None,
        cloud_openai_call=lambda m, mt: ("ok", ""),
        cloud_openrouter_call=lambda m, mt: ("", "skip"),
        module_name="planner",
        agent_name="orchestrator",
    )
    assert reply == "ok" and not err
    assert meta.get("llm_call_id", "").startswith("ullm_")
    assert meta.get("route_task_type") == "simple"
    assert meta.get("provider_order")
    assert meta.get("attempted_backends") == ["openai"]
    raw = trace_path.read_text(encoding="utf-8").strip()
    assert raw
    row = json.loads(raw.splitlines()[-1])
    assert row["event"] == "unified_chat_completion"
    assert row["project"] == "pytest"
    assert row["module_name"] == "planner"
    assert row["agent_name"] == "orchestrator"
    assert row["backend"] == "openai"
    assert row["llm_call_id"] == meta["llm_call_id"]
    assert row["provider_order"] == meta["provider_order"]
    assert row["attempted_backends"] == meta["attempted_backends"]
    assert row["success"] is True
    assert row["user_chars"] == len("trace me")
    assert len(row.get("user_text_fp16") or "") == 16
