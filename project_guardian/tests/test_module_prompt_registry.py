import json

from project_guardian.module_prompt_registry import (
    build_module_llm_messages,
    get_module_prompt_profile,
    run_parallel_llm_analysis,
    run_sequential_llm_chain,
    validate_module_llm_output,
)
from project_guardian.prompt_evolution import should_review_prompt


def test_structured_wire_reply_key_plain_object():
    payload = json.dumps({"summary": "## Hello\n", "extra": 1})
    out = validate_module_llm_output(
        "external_research",
        "webscout_source_summary",
        None,
        payload,
    )
    assert out["valid"] is True
    from project_guardian.module_prompt_registry import structured_reply_text

    assert structured_reply_text(out).startswith("##")


def test_prompt_profile_loading():
    p = get_module_prompt_profile("memory", "condensation")
    assert p["module_name"] == "memory"
    assert p["function_name"] == "condensation"
    assert p["prompt_id"]


def test_missing_prompt_handling():
    try:
        get_module_prompt_profile("nope_module", "x")
        assert False, "expected KeyError"
    except KeyError:
        assert True


def test_build_module_messages_shape():
    msgs = build_module_llm_messages("tool_registry", "tool_selection", None, {"task_id": "t1", "task": {"q": "x"}})
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


def test_malformed_json_rejection():
    out = validate_module_llm_output("memory", "condensation", None, "{not-json")
    assert out["valid"] is False
    assert any("invalid_json" in e for e in out["errors"])


def test_forbidden_output_rejection():
    payload = {"task_id": "x", "result_type": "analysis", "summary": "rm -rf", "data": {}, "recommended_action": {"type": "NO_ACTION"}}
    out = validate_module_llm_output("memory", "relevance_ranking", None, json.dumps(payload))
    assert out["valid"] is False
    assert any("forbidden_output" in e for e in out["errors"])


def test_unknown_tool_rejection():
    payload = {
        "task_id": "x2",
        "result_type": "analysis",
        "summary": "bad action",
        "data": {},
        "recommended_action": {"type": "LAUNCH_NUKE", "target": "none", "arguments": {}},
    }
    out = validate_module_llm_output("tool_registry", "tool_selection", None, json.dumps(payload))
    assert out["valid"] is False
    assert any("unknown_command_type" in e for e in out["errors"])


def test_memory_module_command_restrictions():
    payload = {
        "task_id": "m1",
        "result_type": "analysis",
        "summary": "try patch",
        "data": {},
        "recommended_action": {"type": "PROPOSE_CODE_CHANGE", "target": "file", "arguments": {}},
    }
    out = validate_module_llm_output("memory", "relevance_ranking", None, json.dumps(payload))
    assert out["valid"] is False
    assert any("command_type_not_allowed_for_profile" in e for e in out["errors"])


def test_self_improvement_requires_human_approval_for_code():
    payload = {
        "task_id": "s1",
        "result_type": "proposal",
        "summary": "propose patch",
        "data": {"patch": "..."}, 
        "recommended_action": {"type": "PROPOSE_CODE_CHANGE", "target": "filesystem.patch", "arguments": {}},
    }
    out = validate_module_llm_output("self_improvement", "patch_planning", None, json.dumps(payload))
    assert out["valid"] is True
    assert out["recommended_action"]["needs_human_approval"] is True


def test_parallel_analysis_aggregation():
    good = json.dumps(
        {
            "task_id": "p1",
            "result_type": "analysis",
            "summary": "same",
            "data": {"k": 1},
            "recommended_action": {"type": "RUN_ANALYSIS", "target": None, "arguments": {}},
        }
    )
    r = run_parallel_llm_analysis({"task_id": "p1"}, [lambda **_: good, lambda **_: good], {}, {})
    assert r["agreement_ratio"] >= 1.0
    assert r["disagreement_detected"] is False


def test_sequential_chain_validation_stop():
    good = json.dumps(
        {
            "task_id": "c1",
            "result_type": "analysis",
            "summary": "ok",
            "data": {"step": 1},
            "recommended_action": {"type": "RUN_ANALYSIS", "target": None, "arguments": {}},
        }
    )
    bad = "{oops"
    r = run_sequential_llm_chain({"task_id": "c1"}, ["r1", "r2"], [lambda **_: good, lambda **_: bad], {}, {})
    assert r["success"] is False
    assert r["stopped_at"] == 1


def test_prompt_review_trigger_thresholds():
    m = {
        "calls": 40,
        "valid_json_rate": 0.70,
        "schema_pass_rate": 0.85,
        "retry_rate": 0.5,
        "human_override_rate": 0.4,
        "task_success_rate": 0.7,
        "average_confidence": 0.2,
    }
    assert should_review_prompt("x", 1, m) is True


def test_memory_condense_array_validation_normalizes():
    sample = json.dumps(
        [{"thought": "a", "category": "consensus", "priority": 0.5}]
    )
    out = validate_module_llm_output("memory", "condensation", None, sample)
    assert out["valid"] is True
    assert out.get("normalized_text") == sample
    assert out.get("structured_output_kind") == "memory_condense_array"


def test_memory_condense_array_rejects_non_array():
    out = validate_module_llm_output("memory", "condensation", None, '{"x":1}')
    assert out["valid"] is False
    assert any("expected_json_array" in e for e in out["errors"])


def test_chatlog_reranking_plain_object_accepted():
    sample = json.dumps(
        {
            "rankings": [
                {"file": "a.json", "actionable": True, "priority": 3, "category": "operational", "reason": "ok"},
            ]
        }
    )
    out = validate_module_llm_output("memory", "chatlog_reranking", None, sample)
    assert out["valid"] is True
    assert '"rankings"' in (out.get("normalized_text") or "")


def test_social_response_strategy_plain_object():
    sample = json.dumps(
        {
            "reply_draft": "hi",
            "outreach_draft": "hello",
            "follow_up_questions": ["q1", "q2", "q3"],
            "user_summary": "notes",
        }
    )
    out = validate_module_llm_output("social_intelligence", "response_strategy", None, sample)
    assert out["valid"] is True


def test_sequential_context_compression_plain_object():
    out = validate_module_llm_output(
        "sequential_processing",
        "accumulated_context_compression",
        None,
        json.dumps({"compressed_text": "concise"}),
    )
    assert out["valid"] is True
