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
        return ("hi", "", {"backend": "openai"})

    monkeypatch.setattr("project_guardian.unified_llm_route.unified_chat_completion", fake_unified)

    inst = UnifiedElysiaSystem.__new__(UnifiedElysiaSystem)
    inst.guardian = None
    monkeypatch.setattr(inst, "_unified_chat_llm_router_enabled", lambda: True)
    monkeypatch.setattr(inst, "_mistral_model_for_chat", lambda: "mistral")
    monkeypatch.setattr(inst, "_llm_completion_cloud_openai", lambda m, t: ("", ""))
    monkeypatch.setattr(inst, "_llm_completion_cloud_openrouter", lambda m, t: ("", ""))

    reply, err = UnifiedElysiaSystem.chat_with_llm(inst, "hello")
    assert reply == "hi" and not err
    assert captured.get("safe") is not True
