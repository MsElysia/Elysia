# project_guardian/tests/test_prompt_builder.py
"""Unit tests for centralized prompt stack (no live LLM)."""

import pytest

from project_guardian.prompts.prompt_builder import (
    build_prompt,
    build_prompt_bundle,
    validate_prompt_profile,
)
from project_guardian.prompts import prompt_registry


def test_build_prompt_assembles_sections():
    t = build_prompt(
        "router",
        "orchestrator",
        task_text="Route this request.",
        context={"k": "v"},
        extra_rules=["One extra rule."],
        output_schema={"type": "router_decision", "fields": ["a", "b"]},
    )
    assert "Elysia" in t or "elysia" in t.lower() or "Module: router" in t
    assert "TASK / INSTRUCTIONS:" in t
    assert "Route this request." in t
    assert "CONTEXT (structured):" in t
    assert "OUTPUT CONTRACT" in t
    assert "router_decision" in t
    assert "Additional rules:" in t


def test_unknown_module_raises():
    with pytest.raises(KeyError) as ei:
        build_prompt("not_a_real_module_xyz")
    assert "Unknown prompt module" in str(ei.value)


def test_unknown_agent_raises():
    with pytest.raises(KeyError) as ei:
        build_prompt("router", agent_name="not_an_agent")
    assert "Unknown prompt agent" in str(ei.value)


def test_build_prompt_bundle_meta():
    b = build_prompt_bundle("memory", "critic", task_text="Check recall.")
    assert "prompt_text" in b and "meta" in b
    meta = b["meta"]
    assert meta["core"]["name"]
    assert meta["core"]["version"]
    assert meta["module"]["name"] == "memory"
    assert meta["agent"]["name"] == "critic"


def test_list_names_include_expected():
    assert "router" in prompt_registry.list_module_names()
    assert "orchestrator" in prompt_registry.list_agent_names()


def test_validate_prompt_profile_requires_module():
    with pytest.raises(ValueError, match="module_name"):
        validate_prompt_profile(module_name="  ")


def test_validate_prompt_profile_strips_and_none_agent():
    m, a = validate_prompt_profile(module_name=" router ", agent_name="")
    assert m == "router"
    assert a is None
