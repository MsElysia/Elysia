# project_guardian/tests/test_elysia_llm_fallback.py
"""Elysia cloud-only fallback uses Guardian prompt stack (no elysia.py import)."""

import pytest

from project_guardian.elysia_llm_fallback import elysia_cloud_fallback_completion


def test_elysia_cloud_fallback_prepends_system_and_calls_transport():
    captured = []

    def fake_preferred(messages, max_tokens):
        captured.append((list(messages), max_tokens))
        return "ok", ""

    reply, err = elysia_cloud_fallback_completion(
        [{"role": "user", "content": "hello"}],
        100,
        cloud_preferred=fake_preferred,
        caller="test_elysia_cloud_fallback",
    )
    assert reply == "ok" and err == ""
    assert captured
    msgs, mt = captured[0]
    assert mt == 100
    assert msgs[0]["role"] == "system"
    body = msgs[0]["content"].lower()
    assert "planner" in body or "elysia" in body


def test_elysia_cloud_fallback_logs_stack_fields(caplog):
    import logging

    caplog.set_level(logging.INFO)

    def fake_preferred(messages, max_tokens):
        return "x", ""

    elysia_cloud_fallback_completion(
        [{"role": "user", "content": "a"}],
        10,
        cloud_preferred=fake_preferred,
        caller="test_log",
    )
    assert "legacy_prompt_path=False" in caplog.text
    assert "task_type=elysia_cloud_fallback" in caplog.text or "elysia_cloud_fallback" in caplog.text


def test_elysia_cloud_fallback_invalid_module_raises():
    with pytest.raises(ValueError, match="module_name"):
        elysia_cloud_fallback_completion(
            [{"role": "user", "content": "a"}],
            5,
            cloud_preferred=lambda m, mt: ("", ""),
            caller="test_bad",
            module_name="   ",
        )


def test_cloud_preferred_order_unchanged():
    """Transport order remains OpenAI then OpenRouter (tested at unit level via single stub)."""
    calls = []

    def fake_preferred(messages, max_tokens):
        calls.append("preferred")
        return "r", ""

    elysia_cloud_fallback_completion(
        [{"role": "user", "content": "z"}],
        20,
        cloud_preferred=fake_preferred,
        caller="test_order",
    )
    assert calls == ["preferred"]
