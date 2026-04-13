# project_guardian/tests/test_prompted_call.py
"""Tests for llm.prompted_call (no live LLM)."""

import pytest

from project_guardian.llm.prompted_call import (
    flatten_bundle_meta,
    log_prompted_call,
    prepare_prompted_messages,
    prepare_prompted_system,
    require_prompt_profile,
)


def test_require_prompt_profile_raises_when_blank_and_not_legacy():
    with pytest.raises(ValueError, match="module_name"):
        require_prompt_profile("  ", allow_legacy=False)


def test_require_prompt_profile_allow_legacy_no_raise():
    m, a, leg = require_prompt_profile("", allow_legacy=True, caller="test_allow_legacy")
    assert m is None and a is None and leg is True


def test_prepare_prompted_system_has_meta_and_flat_keys():
    p = prepare_prompted_system(
        module_name="router",
        agent_name="orchestrator",
        task_text="Hello",
        caller="test",
    )
    assert p["system_text"] == p["prompt_text"]
    assert "meta" in p and "logging_fields" in p
    lf = p["logging_fields"]
    assert "prompt_core_name" in lf and "prompt_module_version" in lf
    b = flatten_bundle_meta(p["meta"])
    assert b["prompt_core_name"]
    assert b["prompt_module_name"] == "router"


def test_prepare_prompted_messages_prepends_system():
    msgs = [{"role": "user", "content": "hi"}]
    out = prepare_prompted_messages(
        msgs,
        module_name="summarizer",
        task_text="task",
        caller="test",
    )
    assert out["messages"][0]["role"] == "system"
    assert "summarizer" in out["messages"][0]["content"].lower() or "elysia" in out["messages"][0]["content"].lower()
    assert out["messages"][-1]["content"] == "hi"


def test_log_prompted_call_includes_standard_keys(caplog):
    import logging

    caplog.set_level(logging.INFO)
    log_prompted_call(
        module_name="router",
        agent_name=None,
        task_type="t",
        provider="ollama",
        model="m",
        bundle_meta={
            "core": {"name": "elysia_core", "version": "1.0.0"},
            "module": {"name": "router", "version": "1.0.0"},
            "agent": None,
        },
        prompt_length=100,
        legacy_prompt_path=False,
    )
    text = caplog.text
    assert "prompt_core_name=elysia_core" in text
    assert "legacy_prompt_path=False" in text
    assert "prompt_length=100" in text
