import pytest


@pytest.fixture
def patch_quota_guards(monkeypatch):
    monkeypatch.setattr(
        "project_guardian.openai_degraded.openai_insufficient_quota_reasoning_blocked",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(
        "project_guardian.openai_degraded.openai_reasoning_long_cooldown_active",
        lambda: False,
    )


def test_decide_chat_backend_explicit_planning_bypasses_short_prompt_heuristic(
    patch_quota_guards, monkeypatch
):
    from project_guardian.unified_llm_route import decide_chat_llm_backend

    monkeypatch.setattr("project_guardian.cloud_api_state.openai_key_loaded", lambda: True)
    monkeypatch.setattr("project_guardian.cloud_api_state.openai_usable_for_routing", lambda *a, **k: True)
    monkeypatch.setattr("project_guardian.cloud_api_state.openrouter_key_loaded", lambda: False)
    monkeypatch.setattr("project_guardian.cloud_api_state.any_llm_cloud_key_loaded", lambda: True)
    monkeypatch.setattr(
        "project_guardian.cloud_api_state.chat_completion_route_reason_code",
        lambda: "cloud_available",
    )
    monkeypatch.setattr(
        "project_guardian.multi_api_router.evaluate_api_vs_local",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("explicit planning task should not use generic chat heuristics")
        ),
    )

    captured: dict = {}

    def fake_select(task_type, **kwargs):
        captured["task_type"] = task_type
        return {"chosen": "openai", "reason": "planning_route"}

    monkeypatch.setattr("project_guardian.multi_api_router.select_best_api", fake_select)

    backend, reason = decide_chat_llm_backend("plan", task_type="planning")

    assert backend == "openai"
    assert reason == "planning_route"
    assert captured["task_type"] == "planning"


def test_decide_chat_backend_prompt_packet_forces_local_only(monkeypatch):
    from project_guardian.unified_llm_route import decide_chat_llm_backend

    monkeypatch.setattr(
        "project_guardian.multi_api_router.evaluate_api_vs_local",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("prompt packets should not hit generic chat heuristics")
        ),
    )
    monkeypatch.setattr(
        "project_guardian.multi_api_router.select_best_api",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("prompt packets should not be routed to cloud providers")
        ),
    )

    backend, reason = decide_chat_llm_backend("build packet", task_type="prompt_packet")

    assert backend == "ollama"
    assert reason == "prompt_packet_local_only"


def test_unified_chat_memory_condense_does_not_fallback_to_cloud_on_local_failure(
    monkeypatch,
):
    from project_guardian.unified_llm_route import unified_chat_completion

    captured: dict = {}
    openai_calls: list = []
    openrouter_calls: list = []

    monkeypatch.setattr(
        "project_guardian.unified_llm_route.try_chat_capability_execute",
        lambda *a, **k: None,
    )

    def fake_decide(user_text, registry=None, require_autonomy_safe=False, task_type=None):
        captured["task_type"] = task_type
        return ("ollama", "context_compression_local_only")

    monkeypatch.setattr("project_guardian.unified_llm_route.decide_chat_llm_backend", fake_decide)

    def raise_ollama(self, *args, **kwargs):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(
        "project_guardian.mistral_engine.MistralEngine.complete_chat",
        raise_ollama,
    )

    reply, err, meta = unified_chat_completion(
        messages=[{"role": "user", "content": "condense these memories"}],
        max_tokens=50,
        guardian=None,
        cloud_openai_call=lambda m, mt: (openai_calls.append(list(m)) or "cloud", ""),
        cloud_openrouter_call=lambda m, mt: (openrouter_calls.append(list(m)) or "cloud", ""),
        mistral_model="mistral:7b",
        module_name="memory_condense",
        agent_name=None,
        prompt_extra={"task_type": "memory_condense", "task_text": "condense"},
        skip_capability_preamble=True,
    )

    assert reply == ""
    assert err == "ollama down"
    assert meta.get("backend") == "ollama"
    assert captured["task_type"] == "context_compression"
    assert not openai_calls
    assert not openrouter_calls


def test_unified_chat_skips_blocked_openai_in_fallback_order(
    patch_quota_guards, monkeypatch
):
    from project_guardian.unified_llm_route import unified_chat_completion

    openai_calls: list = []
    openrouter_calls: list = []

    monkeypatch.setattr(
        "project_guardian.unified_llm_route.try_chat_capability_execute",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "project_guardian.unified_llm_route.decide_chat_llm_backend",
        lambda *a, **k: ("openrouter", "openrouter_available_reasoning_only"),
    )
    monkeypatch.setattr(
        "project_guardian.cloud_api_state.openai_usable_for_routing",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(
        "project_guardian.cloud_api_state.openrouter_key_loaded",
        lambda: True,
    )
    monkeypatch.setattr(
        "project_guardian.mistral_engine.MistralEngine.complete_chat",
        lambda self, *a, **k: "local_body",
    )

    reply, err, meta = unified_chat_completion(
        messages=[{"role": "user", "content": "Say OK only."}],
        max_tokens=20,
        guardian=None,
        cloud_openai_call=lambda m, mt: (openai_calls.append(list(m)) or "cloud", ""),
        cloud_openrouter_call=lambda m, mt: (openrouter_calls.append(list(m)) or "", "openrouter_failed"),
        module_name="planner",
        agent_name="orchestrator",
    )

    assert reply == "local_body"
    assert err == ""
    assert meta.get("backend") == "ollama"
    assert meta.get("fallback_from") == "openrouter"
    assert len(openrouter_calls) == 1
    assert not openai_calls
