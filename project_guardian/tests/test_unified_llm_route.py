# project_guardian/tests/test_unified_llm_route.py
"""Unified chat route: prompt stack parity on cloud paths (no live APIs)."""

import pytest


@pytest.fixture
def patch_quota_guards(monkeypatch):
    """Keep OpenAI in the provider order for short prompts."""
    monkeypatch.setattr(
        "project_guardian.openai_degraded.openai_insufficient_quota_reasoning_blocked",
        lambda: False,
    )
    monkeypatch.setattr(
        "project_guardian.openai_degraded.openai_reasoning_long_cooldown_active",
        lambda: False,
    )


def test_unified_chat_openai_prepends_guardian_prompt_stack(patch_quota_guards, monkeypatch):
    from project_guardian.unified_llm_route import unified_chat_completion

    monkeypatch.setattr(
        "project_guardian.unified_llm_route.decide_chat_llm_backend",
        lambda user_text, registry=None: ("openai", "test_route"),
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
        lambda user_text, registry=None: ("openrouter", "or_test"),
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
        lambda user_text, registry=None: ("openai", "t"),
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

    def capture_backend(user_text, registry=None):
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
