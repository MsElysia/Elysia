# project_guardian/tests/test_autonomy_safe_fallback.py
"""Autonomy-safe fail-closed paths when unified routing is off or unified raises (root elysia.py)."""

import importlib.util
from pathlib import Path

_ROOT_ELYSIA = Path(__file__).resolve().parents[2] / "elysia.py"


def _load_unified_elysia_system():
    spec = importlib.util.spec_from_file_location("elysia_root_app", _ROOT_ELYSIA)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.UnifiedElysiaSystem


def test_autonomy_safe_llm_fail_closed_when_unified_disabled(monkeypatch):
    UnifiedElysiaSystem = _load_unified_elysia_system()

    inst = UnifiedElysiaSystem.__new__(UnifiedElysiaSystem)
    inst._last_autonomy_unified_meta = None
    inst.guardian = None
    monkeypatch.setattr(inst, "_unified_chat_llm_router_enabled", lambda: False)

    reply, err = UnifiedElysiaSystem._llm_completion(
        inst,
        [{"role": "user", "content": "x"}],
        10,
        module_name="planner",
        require_autonomy_safe_reasoning=True,
    )
    assert reply == ""
    assert err == "autonomy_safe_unified_router_disabled"
    meta = inst._last_autonomy_unified_meta
    assert meta is not None
    assert meta.get("autonomy_reasoning_safe_required") is True
    assert meta.get("autonomy_reasoning_block_reason") == "unified_router_disabled"
    assert meta.get("autonomy_reasoning_actual_backend") == "none"
    assert meta.get("backend") == "none"


def test_autonomy_safe_llm_fail_closed_on_unified_exception(monkeypatch):
    UnifiedElysiaSystem = _load_unified_elysia_system()

    def boom(**kwargs):
        raise RuntimeError("unified_down")

    monkeypatch.setattr("project_guardian.unified_llm_route.unified_chat_completion", boom)

    inst = UnifiedElysiaSystem.__new__(UnifiedElysiaSystem)
    inst._last_autonomy_unified_meta = None
    inst.guardian = None
    monkeypatch.setattr(inst, "_unified_chat_llm_router_enabled", lambda: True)
    monkeypatch.setattr(inst, "_mistral_model_for_chat", lambda: "mistral")
    monkeypatch.setattr(inst, "_llm_completion_cloud_openai", lambda m, t: ("", "skip"))
    monkeypatch.setattr(inst, "_llm_completion_cloud_openrouter", lambda m, t: ("", "skip"))

    reply, err = UnifiedElysiaSystem._llm_completion(
        inst,
        [{"role": "user", "content": "x"}],
        10,
        module_name="planner",
        require_autonomy_safe_reasoning=True,
    )
    assert reply == ""
    assert err == "autonomy_safe_unified_chat_failed"
    meta = inst._last_autonomy_unified_meta
    assert meta.get("autonomy_reasoning_block_reason") == "unified_chat_failed"
    assert meta.get("autonomy_reasoning_actual_backend") == "none"


def test_non_autonomy_llm_still_uses_cloud_fallback_when_unified_disabled(monkeypatch):
    UnifiedElysiaSystem = _load_unified_elysia_system()

    calls: list = []

    def fake_fallback(*args, **kwargs):
        calls.append(kwargs.get("caller", ""))
        return ("fallback_ok", "")

    monkeypatch.setattr(
        "project_guardian.elysia_llm_fallback.elysia_cloud_fallback_completion",
        fake_fallback,
    )

    inst = UnifiedElysiaSystem.__new__(UnifiedElysiaSystem)
    inst._last_autonomy_unified_meta = None
    inst.guardian = None
    monkeypatch.setattr(inst, "_unified_chat_llm_router_enabled", lambda: False)

    reply, err = UnifiedElysiaSystem._llm_completion(
        inst,
        [{"role": "user", "content": "x"}],
        10,
        module_name="planner",
        require_autonomy_safe_reasoning=False,
    )
    assert reply == "fallback_ok" and err == ""
    assert calls and "UnifiedElysiaSystem._llm_completion" in calls[0]


def test_prior_autonomy_meta_cleared_after_non_safe_unified_disabled_fallback(monkeypatch):
    """Non-safe cloud fallback must not leave _last_autonomy_unified_meta from a prior safe call."""
    UnifiedElysiaSystem = _load_unified_elysia_system()

    def ok_unified(**kwargs):
        return ("ok", "", {"backend": "openai", "autonomy_reasoning_safe_required": True})

    monkeypatch.setattr("project_guardian.unified_llm_route.unified_chat_completion", ok_unified)

    inst = UnifiedElysiaSystem.__new__(UnifiedElysiaSystem)
    inst.guardian = None
    monkeypatch.setattr(inst, "_unified_chat_llm_router_enabled", lambda: True)
    monkeypatch.setattr(inst, "_mistral_model_for_chat", lambda: "mistral")
    monkeypatch.setattr(inst, "_llm_completion_cloud_openai", lambda m, t: ("", ""))
    monkeypatch.setattr(inst, "_llm_completion_cloud_openrouter", lambda m, t: ("", ""))

    UnifiedElysiaSystem._llm_completion(
        inst,
        [{"role": "user", "content": "a"}],
        10,
        module_name="planner",
        require_autonomy_safe_reasoning=True,
    )
    assert inst._last_autonomy_unified_meta is not None

    def fake_fallback(*args, **kwargs):
        return ("fallback_ok", "")

    monkeypatch.setattr(
        "project_guardian.elysia_llm_fallback.elysia_cloud_fallback_completion",
        fake_fallback,
    )
    monkeypatch.setattr(inst, "_unified_chat_llm_router_enabled", lambda: False)

    reply, err = UnifiedElysiaSystem._llm_completion(
        inst,
        [{"role": "user", "content": "b"}],
        10,
        module_name="planner",
        require_autonomy_safe_reasoning=False,
    )
    assert reply == "fallback_ok" and err == ""
    assert inst._last_autonomy_unified_meta is None


def test_prior_autonomy_meta_cleared_after_non_safe_unified_exception_fallback(monkeypatch):
    """Non-safe exception→cloud fallback must not retain prior autonomy unified meta."""
    UnifiedElysiaSystem = _load_unified_elysia_system()

    def ok_unified(**kwargs):
        return ("ok", "", {"backend": "openrouter"})

    monkeypatch.setattr("project_guardian.unified_llm_route.unified_chat_completion", ok_unified)

    inst = UnifiedElysiaSystem.__new__(UnifiedElysiaSystem)
    inst.guardian = None
    monkeypatch.setattr(inst, "_unified_chat_llm_router_enabled", lambda: True)
    monkeypatch.setattr(inst, "_mistral_model_for_chat", lambda: "mistral")
    monkeypatch.setattr(inst, "_llm_completion_cloud_openai", lambda m, t: ("", ""))
    monkeypatch.setattr(inst, "_llm_completion_cloud_openrouter", lambda m, t: ("", ""))

    UnifiedElysiaSystem._llm_completion(
        inst,
        [{"role": "user", "content": "a"}],
        10,
        module_name="planner",
        require_autonomy_safe_reasoning=True,
    )
    assert inst._last_autonomy_unified_meta.get("backend") == "openrouter"

    calls = {"n": 0}

    def flaky_unified(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("unified_down")
        return ("z", "", {"backend": "ollama"})

    monkeypatch.setattr("project_guardian.unified_llm_route.unified_chat_completion", flaky_unified)

    def fake_fallback(*args, **kwargs):
        return ("fb_exc", "")

    monkeypatch.setattr(
        "project_guardian.elysia_llm_fallback.elysia_cloud_fallback_completion",
        fake_fallback,
    )

    reply, err = UnifiedElysiaSystem._llm_completion(
        inst,
        [{"role": "user", "content": "b"}],
        10,
        module_name="planner",
        require_autonomy_safe_reasoning=False,
    )
    assert reply == "fb_exc" and err == ""
    assert inst._last_autonomy_unified_meta is None


def test_operator_chat_with_llm_unified_path_unchanged(monkeypatch):
    """Operator path must not force autonomy-safe routing."""
    UnifiedElysiaSystem = _load_unified_elysia_system()

    captured: dict = {}

    def fake_unified(**kwargs):
        captured["safe"] = kwargs.get("require_autonomy_safe_reasoning")
        captured["module_name"] = kwargs.get("module_name")
        captured["agent_name"] = kwargs.get("agent_name")
        captured["prompt_extra"] = kwargs.get("prompt_extra") or {}
        return ("hi", "", {"backend": "openai"})

    monkeypatch.setattr("project_guardian.unified_llm_route.unified_chat_completion", fake_unified)

    inst = UnifiedElysiaSystem.__new__(UnifiedElysiaSystem)
    inst.guardian = None
    monkeypatch.setattr(inst, "_unified_chat_llm_router_enabled", lambda: True)
    monkeypatch.setattr(inst, "_mistral_model_for_chat", lambda: "mistral")
    monkeypatch.setattr(inst, "_llm_completion_cloud_openai", lambda m, t: ("", ""))
    monkeypatch.setattr(inst, "_llm_completion_cloud_openrouter", lambda m, t: ("", ""))
    monkeypatch.setattr(
        inst,
        "_build_operator_chat_context",
        lambda message: {"runtime": {"status": "ok"}, "providers": {"canonical_ollama_model": "mistral:7b"}},
    )

    reply, err = UnifiedElysiaSystem.chat_with_llm(inst, "hello")
    assert reply == "hi" and not err
    assert captured.get("safe") is not True
    assert captured.get("module_name") == "operator_chat"
    assert captured.get("agent_name") is None
    assert captured["prompt_extra"].get("task_type") == "conversation"
    assert captured["prompt_extra"].get("context", {}).get("providers", {}).get("canonical_ollama_model") == "mistral:7b"


def test_build_operator_chat_context_exposes_runtime_facts():
    UnifiedElysiaSystem = _load_unified_elysia_system()

    inst = UnifiedElysiaSystem.__new__(UnifiedElysiaSystem)
    inst.guardian = None
    inst.modules = {}
    inst.get_status = lambda: {
        "status": "running",
        "uptime": "0:01:23",
        "startup_phase": "running",
        "dashboard_ready": True,
        "warnings": ["Last vector rebuild skipped: no rebuild pending or degraded"],
        "components": {"guardian_core": True, "runtime_loop": True},
        "guardian_status": {
            "memory": {"total_memories": 42},
            "planner_runtime_status": {
                "canonical_ollama_model": "mistral:7b",
                "planner_readiness": "ready",
                "ollama_reachable": True,
                "ollama_exact_tag_match": True,
                "planner_startup_stabilization_required": False,
                "early_runtime_budget": False,
                "runtime_decision": {
                    "local_usable": True,
                    "local_block_reason": None,
                    "reasoning_provider_selected": "openai",
                    "reasoning_provider_autonomy_safe": "local",
                    "openai_usable": True,
                    "openrouter_usable": True,
                },
            },
        },
        "income_modules": {
            "income_generator": {"total_earned": 0.0, "active_projects": 3},
            "wallet": {"balance": 0},
        },
    }
    inst._unified_chat_llm_router_enabled = lambda: True
    inst._mistral_model_for_chat = lambda: "mistral:7b"

    ctx = UnifiedElysiaSystem._build_operator_chat_context(inst, "can you use ollama better for elysia program")
    assert ctx["planner_runtime"]["planner_readiness"] == "ready"
    assert ctx["routing"]["local_usable"] is True
    facts = ctx["current_state_facts"]
    assert "unified_chat_llm_router=true" in facts
    assert "canonical_ollama_model=mistral:7b" in facts
    assert "planner_readiness=ready" in facts
    assert "local_usable=true" in facts
