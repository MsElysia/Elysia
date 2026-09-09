import pytest


@pytest.fixture
def patch_router_defaults(monkeypatch):
    monkeypatch.setattr("project_guardian.cloud_api_state.openai_usable_for_routing", lambda *a, **k: True)
    monkeypatch.setattr("project_guardian.cloud_api_state.openai_key_loaded", lambda: True)
    monkeypatch.setattr("project_guardian.cloud_api_state.openrouter_key_loaded", lambda: True)
    monkeypatch.setattr("project_guardian.cloud_api_state.anthropic_key_loaded", lambda: False)
    monkeypatch.setattr("project_guardian.cloud_api_state.any_llm_cloud_key_loaded", lambda: True)
    monkeypatch.setattr("project_guardian.cloud_api_state.chat_completion_route_reason_code", lambda: "cloud_available")
    monkeypatch.setattr("project_guardian.cloud_api_state.embedding_route_reason_code", lambda: "embed_route")
    monkeypatch.setattr("project_guardian.cloud_api_state.human_openai_routing_message", lambda reason: f"blocked:{reason}")
    monkeypatch.setattr("project_guardian.cloud_api_state.openai_routing_block_reason", lambda: "ok")
    monkeypatch.setattr(
        "project_guardian.openai_degraded.openai_insufficient_quota_reasoning_blocked",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(
        "project_guardian.openai_degraded.is_openai_degraded_active",
        lambda: False,
    )
    monkeypatch.setattr(
        "project_guardian.openai_degraded.openai_reasoning_long_cooldown_active",
        lambda: False,
    )


def test_select_best_api_memory_condense_alias_routes_local_only(patch_router_defaults):
    from project_guardian.multi_api_router import select_best_api

    result = select_best_api("memory_condense", log_decision=False)

    assert result.get("chosen") == "local_mistral"
    assert result.get("task_type") == "context_compression"
    assert "local Ollama" in str(result.get("reason") or "")


def test_select_best_api_decide_next_action_alias_maps_to_planning(patch_router_defaults):
    from project_guardian.multi_api_router import select_best_api

    result = select_best_api("decide_next_action", log_decision=False)

    assert result.get("chosen") == "openai"
    assert result.get("task_type") == "planning"
    assert "OpenAI" in str(result.get("reason") or "")


def test_select_best_api_planning_alias_honors_autonomy_safe_clamp(
    patch_router_defaults, monkeypatch
):
    monkeypatch.setattr(
        "project_guardian.planner_readiness.local_planner_provider_ready",
        lambda: True,
    )

    from project_guardian.multi_api_router import select_best_api

    result = select_best_api(
        "decide_next_action",
        log_decision=False,
        require_autonomy_safe=True,
    )

    assert result.get("chosen") == "local_mistral"
    assert result.get("task_type") == "planning"
