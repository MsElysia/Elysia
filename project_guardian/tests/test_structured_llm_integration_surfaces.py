"""Guardrails: unified / fallback entrypoints expose structured_role for module registry routing."""

from __future__ import annotations

import inspect


def test_elysia_cloud_fallback_accepts_structured_role():
    from project_guardian.elysia_llm_fallback import elysia_cloud_fallback_completion

    assert "structured_role" in inspect.signature(elysia_cloud_fallback_completion).parameters


def test_unified_autonomy_chat_completion_passes_through_structured_role(monkeypatch):
    captured: dict = {}

    def fake_unified(**kwargs):
        captured.update(kwargs)
        return ("", "", {})

    monkeypatch.setattr(
        "project_guardian.unified_llm_route.unified_chat_completion",
        fake_unified,
    )
    from project_guardian.unified_llm_route import unified_autonomy_chat_completion

    unified_autonomy_chat_completion(
        messages=[{"role": "user", "content": "x"}],
        max_tokens=3,
        guardian=None,
        cloud_openai_call=lambda m, t: ("", ""),
        cloud_openrouter_call=lambda m, t: ("", ""),
        module_name="planner",
        structured_role="autonomy:next_action_planning",
    )
    assert captured.get("structured_role") == "autonomy:next_action_planning"


def test_plain_object_profile_registered():
    """Sanity check that supplemental profiles landed in registry."""
    from project_guardian.module_prompt_registry import get_module_prompt_profile

    p = get_module_prompt_profile("memory", "chatlog_reranking")
    assert p.get("structured_output_kind") == "plain_object_keys"
    ps = get_module_prompt_profile("social_intelligence", "response_strategy")
    assert ps.get("structured_output_kind") == "plain_object_keys"
    seq = get_module_prompt_profile("sequential_processing", "accumulated_context_compression")
    assert seq.get("structured_output_kind") == "plain_object_keys"
    imp = get_module_prompt_profile("implementer", "codegen_patch")
    assert imp.get("structured_output_kind") == "plain_object_keys"
    wu = get_module_prompt_profile("external_research", "webscout_url_discovery")
    assert wu.get("structured_output_kind") == "plain_object_keys"
