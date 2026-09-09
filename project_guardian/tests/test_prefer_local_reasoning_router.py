# project_guardian/tests/test_prefer_local_reasoning_router.py
"""Tests for opt-in local Ollama preference on reasoning/longform API routing."""

from __future__ import annotations

import project_guardian.cloud_api_state as cas
from project_guardian import planner_readiness as pr

from project_guardian.tests.test_startup_gates import _patch_cloud_credentials


def _base_openai_ok(monkeypatch):
    monkeypatch.setattr(
        "project_guardian.openai_degraded.openai_insufficient_quota_reasoning_blocked",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(
        "project_guardian.openai_degraded.openai_reasoning_long_cooldown_active",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(
        "project_guardian.openai_degraded.is_openai_degraded_active",
        lambda *a, **k: False,
    )
    _patch_cloud_credentials(monkeypatch, openai=True, openrouter=False, anthropic=False)
    monkeypatch.setattr(cas, "openai_usable_for_routing", lambda *a, **k: True)


def _base_openai_openrouter_ok(monkeypatch):
    """OpenAI + OpenRouter keys present for router tests that branch on OpenRouter."""
    monkeypatch.setattr(
        "project_guardian.openai_degraded.openai_insufficient_quota_reasoning_blocked",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(
        "project_guardian.openai_degraded.openai_reasoning_long_cooldown_active",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(
        "project_guardian.openai_degraded.is_openai_degraded_active",
        lambda *a, **k: False,
    )
    _patch_cloud_credentials(monkeypatch, openai=True, openrouter=True, anthropic=False)
    monkeypatch.setattr(cas, "openai_usable_for_routing", lambda *a, **k: True)


def test_reasoning_defaults_to_openai_when_local_ready(monkeypatch):
    """When prefer-local is disabled, planner ready + OpenAI OK routes reasoning to OpenAI."""
    _base_openai_ok(monkeypatch)
    monkeypatch.delenv("ELYSIA_PREFER_LOCAL_REASONING_WHEN_READY", raising=False)
    monkeypatch.delenv("ELYSIA_MAXIMIZE_FREE_TOKENS", raising=False)
    monkeypatch.delenv("ELYSIA_USE_CLOUD_LLM_FIRST", raising=False)
    monkeypatch.delenv("ELYSIA_MAXIMIZE_PAID_API_USAGE", raising=False)
    monkeypatch.delenv("ELYSIA_CLOUD_FIRST_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_PREFER_OPENROUTER_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_OPENROUTER_FIRST_LLM", raising=False)
    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: True)
    monkeypatch.setattr(
        "project_guardian.multi_api_router._prefer_local_reasoning_when_planner_ready_enabled",
        lambda: False,
    )

    from project_guardian.multi_api_router import select_best_api

    r = select_best_api("reasoning", registry=None, reserve_slot=False, log_decision=False)
    assert r.get("chosen") == "openai"


def test_runtime_snapshot_reasoning_sel_matches_prefer_local(monkeypatch):
    """reasoning_provider_selected in [RuntimeDecision] follows the same router as select_best_api."""
    monkeypatch.setenv("ELYSIA_PREFER_LOCAL_REASONING_WHEN_READY", "1")
    _base_openai_ok(monkeypatch)
    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: True)

    d = pr.build_runtime_decision_status_dict(None)
    assert d["reasoning_provider_selected"] == "local"


def test_reasoning_prefers_local_when_flag_and_planner_ready(monkeypatch):
    monkeypatch.setenv("ELYSIA_PREFER_LOCAL_REASONING_WHEN_READY", "1")
    _base_openai_ok(monkeypatch)
    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: True)

    from project_guardian.multi_api_router import select_best_api

    r = select_best_api("reasoning", registry=None, reserve_slot=False, log_decision=False)
    assert r.get("chosen") == "local_mistral"
    assert "prefer_local_reasoning" in str(r.get("reason") or "")


def test_reasoning_stays_openai_when_flag_on_but_planner_not_ready(monkeypatch):
    monkeypatch.setenv("ELYSIA_PREFER_LOCAL_REASONING_WHEN_READY", "1")
    _base_openai_ok(monkeypatch)
    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "degraded")
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: True)

    from project_guardian.multi_api_router import select_best_api

    r = select_best_api("reasoning", registry=None, reserve_slot=False, log_decision=False)
    assert r.get("chosen") == "openai"


def test_reasoning_stays_openai_when_flag_on_but_local_unusable(monkeypatch):
    monkeypatch.setenv("ELYSIA_PREFER_LOCAL_REASONING_WHEN_READY", "1")
    _base_openai_ok(monkeypatch)
    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: False)

    from project_guardian.multi_api_router import select_best_api

    r = select_best_api("reasoning", registry=None, reserve_slot=False, log_decision=False)
    assert r.get("chosen") == "openai"


def test_decide_chat_backend_ollama_when_router_chooses_local_mistral(monkeypatch):
    """Unified chat must not override API router local_mistral with OpenAI fallback."""
    monkeypatch.setenv("ELYSIA_PREFER_LOCAL_REASONING_WHEN_READY", "1")
    _base_openai_ok(monkeypatch)
    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: True)

    from project_guardian.unified_llm_route import decide_chat_llm_backend

    backend, reason = decide_chat_llm_backend(
        "x" * 700,
        registry=None,
        require_autonomy_safe=False,
        task_type="reasoning",
    )
    assert backend == "ollama"
    assert "prefer_local_reasoning" in reason


def test_cloud_llm_first_overrides_maximize_free_tokens(monkeypatch):
    """ELYSIA_USE_CLOUD_LLM_FIRST disables local-first even when ELYSIA_MAXIMIZE_FREE_TOKENS is on."""
    monkeypatch.setenv("ELYSIA_USE_CLOUD_LLM_FIRST", "1")
    monkeypatch.setenv("ELYSIA_MAXIMIZE_FREE_TOKENS", "1")
    monkeypatch.delenv("ELYSIA_PREFER_LOCAL_REASONING_WHEN_READY", raising=False)
    monkeypatch.delenv("ELYSIA_PREFER_OPENROUTER_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_OPENROUTER_FIRST_LLM", raising=False)
    _base_openai_ok(monkeypatch)
    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: True)

    from project_guardian.multi_api_router import select_best_api

    r = select_best_api("reasoning", registry=None, reserve_slot=False, log_decision=False)
    assert r.get("chosen") == "openai"


def test_cloud_llm_first_alias_maximize_paid_api_usage(monkeypatch):
    monkeypatch.setenv("ELYSIA_MAXIMIZE_PAID_API_USAGE", "true")
    monkeypatch.setenv("ELYSIA_MAXIMIZE_FREE_TOKENS", "1")
    monkeypatch.delenv("ELYSIA_PREFER_LOCAL_REASONING_WHEN_READY", raising=False)
    monkeypatch.delenv("ELYSIA_PREFER_OPENROUTER_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_OPENROUTER_FIRST_LLM", raising=False)
    _base_openai_ok(monkeypatch)
    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: True)

    from project_guardian.multi_api_router import select_best_api

    r = select_best_api("simple", registry=None, reserve_slot=False, log_decision=False)
    assert r.get("chosen") == "openai"


def test_cloud_credit_deadline_forces_cloud_first(monkeypatch):
    monkeypatch.delenv("ELYSIA_USE_CLOUD_LLM_FIRST", raising=False)
    monkeypatch.delenv("ELYSIA_MAXIMIZE_PAID_API_USAGE", raising=False)
    monkeypatch.delenv("ELYSIA_CLOUD_FIRST_LLM", raising=False)
    monkeypatch.setenv("ELYSIA_CLOUD_CREDIT_USE_DEADLINE", "2099-12-31")
    from project_guardian.multi_api_router import _use_cloud_llm_first_enabled

    assert _use_cloud_llm_first_enabled() is True


def test_cloud_credit_deadline_past_is_inactive(monkeypatch):
    monkeypatch.delenv("ELYSIA_USE_CLOUD_LLM_FIRST", raising=False)
    monkeypatch.delenv("ELYSIA_MAXIMIZE_PAID_API_USAGE", raising=False)
    monkeypatch.setenv("ELYSIA_CLOUD_CREDIT_USE_DEADLINE", "1999-01-01")
    from project_guardian.multi_api_router import _use_cloud_llm_first_enabled

    assert _use_cloud_llm_first_enabled() is False


def test_cloud_credit_deadline_routes_reasoning_to_openai(monkeypatch):
    monkeypatch.setenv("ELYSIA_CLOUD_CREDIT_USE_DEADLINE", "2099-06-15")
    monkeypatch.delenv("ELYSIA_USE_CLOUD_LLM_FIRST", raising=False)
    monkeypatch.delenv("ELYSIA_MAXIMIZE_FREE_TOKENS", raising=False)
    monkeypatch.delenv("ELYSIA_PREFER_OPENROUTER_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_OPENROUTER_FIRST_LLM", raising=False)
    _base_openai_ok(monkeypatch)
    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: True)

    from project_guardian.multi_api_router import select_best_api

    r = select_best_api("reasoning", registry=None, reserve_slot=False, log_decision=False)
    assert r.get("chosen") == "openai"


def test_simple_prefers_openrouter_when_env_and_both_keys(monkeypatch):
    monkeypatch.setenv("ELYSIA_PREFER_OPENROUTER_LLM", "1")
    monkeypatch.delenv("ELYSIA_MAXIMIZE_FREE_TOKENS", raising=False)
    monkeypatch.delenv("ELYSIA_PREFER_LOCAL_SIMPLE_WHEN_READY", raising=False)
    _base_openai_openrouter_ok(monkeypatch)

    from project_guardian.multi_api_router import select_best_api

    r = select_best_api("simple", registry=None, reserve_slot=False, log_decision=False)
    assert r.get("chosen") == "openrouter"
    assert "PREFER_OPENROUTER" in str(r.get("reason") or "")


def test_simple_cost_sensitive_respects_openrouter_first(monkeypatch):
    """Registry passes cost_sensitivity=high for simple; OpenRouter-first must not be short-circuited."""
    monkeypatch.setenv("ELYSIA_PREFER_OPENROUTER_LLM", "1")
    monkeypatch.delenv("ELYSIA_MAXIMIZE_FREE_TOKENS", raising=False)
    monkeypatch.delenv("ELYSIA_PREFER_LOCAL_SIMPLE_WHEN_READY", raising=False)
    _base_openai_openrouter_ok(monkeypatch)

    from project_guardian.multi_api_router import select_best_api

    r = select_best_api(
        "simple",
        cost_sensitivity="high",
        registry=None,
        reserve_slot=False,
        log_decision=False,
    )
    assert r.get("chosen") == "openrouter"


def test_simple_cost_sensitive_respects_cloud_first(monkeypatch):
    monkeypatch.setenv("ELYSIA_USE_CLOUD_LLM_FIRST", "1")
    monkeypatch.delenv("ELYSIA_PREFER_OPENROUTER_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_OPENROUTER_FIRST_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_MAXIMIZE_FREE_TOKENS", raising=False)
    _base_openai_ok(monkeypatch)

    from project_guardian.multi_api_router import select_best_api

    r = select_best_api(
        "simple",
        cost_sensitivity="high",
        registry=None,
        reserve_slot=False,
        log_decision=False,
    )
    assert r.get("chosen") == "openai"


def test_reasoning_prefers_openrouter_when_env_and_both_keys(monkeypatch):
    monkeypatch.setenv("ELYSIA_PREFER_OPENROUTER_LLM", "1")
    monkeypatch.setenv("ELYSIA_USE_CLOUD_LLM_FIRST", "1")
    monkeypatch.delenv("ELYSIA_PREFER_LOCAL_REASONING_WHEN_READY", raising=False)
    monkeypatch.delenv("ELYSIA_MAXIMIZE_FREE_TOKENS", raising=False)
    _base_openai_openrouter_ok(monkeypatch)
    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: True)

    from project_guardian.multi_api_router import select_best_api

    r = select_best_api("reasoning", registry=None, reserve_slot=False, log_decision=False)
    assert r.get("chosen") == "openrouter"


def test_reasoning_prefers_local_via_maximize_free_tokens_env(monkeypatch):
    """ELYSIA_MAXIMIZE_FREE_TOKENS enables local reasoning without ELYSIA_PREFER_LOCAL_*."""
    monkeypatch.setenv("ELYSIA_MAXIMIZE_FREE_TOKENS", "1")
    monkeypatch.delenv("ELYSIA_USE_CLOUD_LLM_FIRST", raising=False)
    monkeypatch.delenv("ELYSIA_MAXIMIZE_PAID_API_USAGE", raising=False)
    monkeypatch.delenv("ELYSIA_PREFER_LOCAL_REASONING_WHEN_READY", raising=False)
    monkeypatch.delenv("ELYSIA_PREFER_OPENROUTER_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_OPENROUTER_FIRST_LLM", raising=False)
    _base_openai_ok(monkeypatch)
    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: True)

    from project_guardian.multi_api_router import select_best_api

    r = select_best_api("reasoning", registry=None, reserve_slot=False, log_decision=False)
    assert r.get("chosen") == "local_mistral"


def test_simple_routes_local_when_maximize_free_and_planner_ready(monkeypatch):
    monkeypatch.setenv("ELYSIA_MAXIMIZE_FREE_TOKENS", "1")
    monkeypatch.delenv("ELYSIA_USE_CLOUD_LLM_FIRST", raising=False)
    monkeypatch.delenv("ELYSIA_MAXIMIZE_PAID_API_USAGE", raising=False)
    monkeypatch.delenv("ELYSIA_CLOUD_FIRST_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_PREFER_OPENROUTER_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_OPENROUTER_FIRST_LLM", raising=False)
    _base_openai_ok(monkeypatch)
    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: True)

    from project_guardian.multi_api_router import select_best_api

    r = select_best_api("simple", registry=None, reserve_slot=False, log_decision=False)
    assert r.get("chosen") == "local_mistral"


def test_simple_stays_openai_when_maximize_free_but_local_unusable(monkeypatch):
    monkeypatch.setenv("ELYSIA_MAXIMIZE_FREE_TOKENS", "1")
    monkeypatch.delenv("ELYSIA_USE_CLOUD_LLM_FIRST", raising=False)
    monkeypatch.delenv("ELYSIA_MAXIMIZE_PAID_API_USAGE", raising=False)
    monkeypatch.delenv("ELYSIA_CLOUD_FIRST_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_PREFER_OPENROUTER_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_OPENROUTER_FIRST_LLM", raising=False)
    _base_openai_ok(monkeypatch)
    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: False)

    from project_guardian.multi_api_router import select_best_api

    r = select_best_api("simple", registry=None, reserve_slot=False, log_decision=False)
    assert r.get("chosen") == "openai"


def test_high_quality_anthropic_unaffected_by_prefer_local(monkeypatch):
    monkeypatch.setenv("ELYSIA_PREFER_LOCAL_REASONING_WHEN_READY", "1")
    _base_openai_ok(monkeypatch)
    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: True)
    _patch_cloud_credentials(monkeypatch, openai=True, openrouter=False, anthropic=True)
    monkeypatch.setattr(cas, "anthropic_usable_for_reasoning", lambda: True)

    from project_guardian.multi_api_router import select_best_api

    r = select_best_api(
        "reasoning",
        quality_requirement="high",
        registry=None,
        reserve_slot=False,
        log_decision=False,
    )
    assert r.get("chosen") == "anthropic"


def test_decide_chat_short_prompt_keeps_openrouter_when_router_prefers_it(monkeypatch):
    """Trivial user text must not downgrade OpenRouter after select_best_api (OpenRouter-first)."""
    monkeypatch.setenv("ELYSIA_PREFER_OPENROUTER_LLM", "1")
    monkeypatch.delenv("ELYSIA_MAXIMIZE_FREE_TOKENS", raising=False)
    monkeypatch.delenv("ELYSIA_PREFER_LOCAL_SIMPLE_WHEN_READY", raising=False)
    monkeypatch.delenv("ELYSIA_USE_CLOUD_LLM_FIRST", raising=False)
    _base_openai_openrouter_ok(monkeypatch)

    from project_guardian.unified_llm_route import decide_chat_llm_backend

    backend, _reason = decide_chat_llm_backend("hi", registry=None, task_type=None)
    assert backend == "openrouter"


def test_decide_chat_short_prompt_keeps_openai_under_cloud_first(monkeypatch):
    """Trivial text must not force Ollama when paid-first / cloud routing picks OpenAI."""
    monkeypatch.setenv("ELYSIA_USE_CLOUD_LLM_FIRST", "1")
    monkeypatch.delenv("ELYSIA_PREFER_OPENROUTER_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_OPENROUTER_FIRST_LLM", raising=False)
    _base_openai_ok(monkeypatch)

    from project_guardian.unified_llm_route import decide_chat_llm_backend

    backend, _reason = decide_chat_llm_backend("hi", registry=None, task_type=None)
    assert backend == "openai"


def test_decide_chat_trivial_prompt_routes_local_when_default_free_first(monkeypatch):
    """Very short chat uses local when not cloud-first / not OpenRouter-first (router trivial rule)."""
    monkeypatch.delenv("ELYSIA_USE_CLOUD_LLM_FIRST", raising=False)
    monkeypatch.delenv("ELYSIA_MAXIMIZE_PAID_API_USAGE", raising=False)
    monkeypatch.delenv("ELYSIA_CLOUD_FIRST_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_PREFER_OPENROUTER_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_OPENROUTER_FIRST_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_MAXIMIZE_FREE_TOKENS", raising=False)
    monkeypatch.delenv("ELYSIA_PREFER_LOCAL_SIMPLE_WHEN_READY", raising=False)
    _base_openai_ok(monkeypatch)

    from project_guardian.unified_llm_route import decide_chat_llm_backend

    backend, reason = decide_chat_llm_backend("hi", registry=None, task_type=None)
    assert backend == "ollama"
    assert "trivial" in reason.lower()


def test_select_best_api_simple_trivial_respects_openrouter_pref(monkeypatch):
    monkeypatch.setenv("ELYSIA_PREFER_OPENROUTER_LLM", "1")
    monkeypatch.delenv("ELYSIA_MAXIMIZE_FREE_TOKENS", raising=False)
    monkeypatch.delenv("ELYSIA_PREFER_LOCAL_SIMPLE_WHEN_READY", raising=False)
    _base_openai_openrouter_ok(monkeypatch)

    from project_guardian.multi_api_router import select_best_api

    r = select_best_api(
        "simple",
        registry=None,
        reserve_slot=False,
        log_decision=False,
        prompt_preview="hi",
    )
    assert r.get("chosen") == "openrouter"


def test_select_best_api_simple_trivial_skipped_when_cloud_first(monkeypatch):
    monkeypatch.setenv("ELYSIA_USE_CLOUD_LLM_FIRST", "1")
    monkeypatch.delenv("ELYSIA_PREFER_OPENROUTER_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_OPENROUTER_FIRST_LLM", raising=False)
    _base_openai_ok(monkeypatch)

    from project_guardian.multi_api_router import select_best_api

    r = select_best_api(
        "simple",
        registry=None,
        reserve_slot=False,
        log_decision=False,
        prompt_preview="hi",
    )
    assert r.get("chosen") == "openai"


def test_pipeline_maximize_free_tokens_false_when_cloud_first(monkeypatch):
    monkeypatch.setenv("ELYSIA_USE_CLOUD_LLM_FIRST", "1")
    monkeypatch.setenv("ELYSIA_MAXIMIZE_FREE_TOKENS", "1")
    from project_guardian.multi_api_router import pipeline_maximize_free_tokens

    assert pipeline_maximize_free_tokens({"maximize_free_tokens": True}) is False


def test_pipeline_maximize_free_tokens_true_from_env(monkeypatch):
    monkeypatch.delenv("ELYSIA_USE_CLOUD_LLM_FIRST", raising=False)
    monkeypatch.delenv("ELYSIA_MAXIMIZE_PAID_API_USAGE", raising=False)
    monkeypatch.delenv("ELYSIA_CLOUD_FIRST_LLM", raising=False)
    monkeypatch.setenv("ELYSIA_MAXIMIZE_FREE_TOKENS", "1")
    from project_guardian.multi_api_router import pipeline_maximize_free_tokens

    assert pipeline_maximize_free_tokens({}) is True


def test_pipeline_maximize_free_tokens_true_from_cfg_only(monkeypatch):
    monkeypatch.delenv("ELYSIA_USE_CLOUD_LLM_FIRST", raising=False)
    monkeypatch.delenv("ELYSIA_MAXIMIZE_PAID_API_USAGE", raising=False)
    monkeypatch.delenv("ELYSIA_CLOUD_FIRST_LLM", raising=False)
    monkeypatch.delenv("ELYSIA_MAXIMIZE_FREE_TOKENS", raising=False)
    from project_guardian.multi_api_router import pipeline_maximize_free_tokens

    assert pipeline_maximize_free_tokens({"maximize_free_tokens": True}) is True
