import json
import inspect


def test_unified_chat_structured_role_validates_json(monkeypatch):
    from project_guardian.unified_llm_route import unified_chat_completion

    monkeypatch.setattr(
        "project_guardian.unified_llm_route.decide_chat_llm_backend",
        lambda user_text, registry=None, **kwargs: ("openai", "test"),
    )
    monkeypatch.setattr(
        "project_guardian.unified_llm_route.try_chat_capability_execute",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "project_guardian.unified_llm_route.compute_unified_chat_provider_order",
        lambda *a, **k: (["openai"], {}),
    )

    payload = {
        "task_id": "u1",
        "result_type": "analysis",
        "summary": "done",
        "data": {"ok": True},
        "recommended_action": {"type": "RUN_ANALYSIS", "target": None, "arguments": {}},
    }
    reply, err, meta = unified_chat_completion(
        messages=[{"role": "user", "content": "x"}],
        max_tokens=10,
        guardian=None,
        cloud_openai_call=lambda m, mt: (json.dumps(payload), ""),
        cloud_openrouter_call=lambda m, mt: ("", ""),
        module_name="planner",
        structured_role="memory:relevance_ranking",
    )
    assert not err
    row = json.loads(reply)
    assert row["valid"] is True
    assert meta.get("structured_output_valid") is True


def test_unified_chat_structured_role_rejects_free_text(monkeypatch):
    from project_guardian.unified_llm_route import unified_chat_completion

    monkeypatch.setattr(
        "project_guardian.unified_llm_route.decide_chat_llm_backend",
        lambda user_text, registry=None, **kwargs: ("openai", "test"),
    )
    monkeypatch.setattr(
        "project_guardian.unified_llm_route.try_chat_capability_execute",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "project_guardian.unified_llm_route.compute_unified_chat_provider_order",
        lambda *a, **k: (["openai"], {}),
    )

    reply, err, meta = unified_chat_completion(
        messages=[{"role": "user", "content": "x"}],
        max_tokens=10,
        guardian=None,
        cloud_openai_call=lambda m, mt: ("I ran shell commands for you", ""),
        cloud_openrouter_call=lambda m, mt: ("", ""),
        module_name="planner",
        structured_role="decision_gate:approve_reject_defer",
    )
    assert reply == ""
    assert "structured_output_validation_failed" in err
    assert meta.get("structured_output_valid") is False


def test_unified_chat_supports_structured_role_param():
    from project_guardian.unified_llm_route import unified_chat_completion

    sig = inspect.signature(unified_chat_completion)
    assert "structured_role" in sig.parameters


def test_unified_chat_memory_condensation_returns_normalized_array(monkeypatch):
    from project_guardian.unified_llm_route import unified_chat_completion

    monkeypatch.setattr(
        "project_guardian.unified_llm_route.decide_chat_llm_backend",
        lambda user_text, registry=None, **kwargs: ("openai", "test"),
    )
    monkeypatch.setattr(
        "project_guardian.unified_llm_route.try_chat_capability_execute",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "project_guardian.unified_llm_route.compute_unified_chat_provider_order",
        lambda *a, **k: (["openai"], {}),
    )

    arr = [{"thought": "one", "category": "consensus", "priority": 0.5}]
    reply, err, meta = unified_chat_completion(
        messages=[{"role": "user", "content": "condense"}],
        max_tokens=50,
        guardian=None,
        cloud_openai_call=lambda m, mt: (json.dumps(arr), ""),
        cloud_openrouter_call=lambda m, mt: ("", ""),
        module_name="memory_condense",
        structured_role="memory:condensation",
    )
    assert not err
    parsed = json.loads(reply)
    assert isinstance(parsed, list)
    assert parsed[0]["thought"] == "one"
    assert meta.get("structured_output_valid") is True
