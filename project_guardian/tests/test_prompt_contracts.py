# project_guardian/tests/test_prompt_contracts.py

from __future__ import annotations

import json

import pytest

from project_guardian.brain.contracts import Observation
from project_guardian.brain.memory_module import InMemoryBrainStore
from project_guardian.brain.pipeline import BrainPipeline
from project_guardian.prompt_contracts import (
    contract_to_dict,
    get_module_contract,
    get_prompt_contract,
    list_prompt_contracts,
    parse_json_output,
    render_prompt,
    validate_contract_output,
    validate_module_llm_response,
)


def _valid_planner_dict() -> dict:
    return {
        "goal": "Do the thing",
        "steps": [{"description": "step1"}],
        "constraints": [],
        "risk_level": "low",
        "reason_summary": "straightforward",
        "confidence": 0.7,
    }


def _valid_planner_json() -> str:
    return json.dumps(_valid_planner_dict())


REQUIRED_MODULES = (
    "planner",
    "tool_router",
    "llm_router",
    "risk_checker",
    "memory_ranker",
    "memory_compressor",
    "learning_reviewer",
    "self_improvement_reviewer",
    "think_decide_act_thinker",
    "think_decide_act_proposer",
)


def test_all_required_contracts_exist():
    for m in REQUIRED_MODULES:
        c = get_module_contract(m)
        assert c.module_name == m


def test_each_contract_has_required_fields():
    for c in list_prompt_contracts():
        assert c.contract_id
        assert c.module_name
        assert c.purpose
        assert c.system_prompt
        assert isinstance(c.input_schema, dict)
        assert isinstance(c.output_schema, dict)
        assert c.expected_json_keys
        assert c.allowed_actions
        assert c.forbidden_actions
        assert isinstance(c.risk_notes, tuple)
        assert c.version


def test_render_prompt_includes_system_and_input():
    out = render_prompt("planner.v1", {"observation": "hello", "x": 1})
    c = get_prompt_contract("planner.v1")
    assert c.system_prompt in out
    assert "hello" in out
    assert "INPUT_JSON" in out


def test_valid_json_passes_validation_with_prompt_contract():
    ok, errs = validate_contract_output(get_prompt_contract("planner.v1"), _valid_planner_json())
    assert ok is True
    assert errs == []


def test_valid_dict_passes_validation_with_module_name_string():
    ok, errs = validate_contract_output("planner", _valid_planner_dict())
    assert ok is True
    assert errs == []


def test_valid_dict_passes_with_contract_id_string():
    ok, errs = validate_contract_output("planner.v1", _valid_planner_dict())
    assert ok is True


def test_missing_required_key_fails():
    bad = json.dumps({"goal": "only"})
    ok, errs = validate_contract_output("planner", bad)
    assert ok is False
    assert any("missing_required_key" in e for e in errs)


def test_invalid_confidence_fails():
    d = _valid_planner_dict()
    d["confidence"] = 1.5
    ok, errs = validate_contract_output("planner", json.dumps(d))
    assert ok is False
    assert "confidence_out_of_range" in errs


def test_invalid_risk_level_fails():
    d = _valid_planner_dict()
    d["risk_level"] = "nope"
    ok, errs = validate_contract_output("planner", json.dumps(d))
    assert ok is False
    assert any("invalid_risk_level" in e for e in errs)


@pytest.mark.parametrize(
    "bad_key",
    ["chain_of_thought", "private_reasoning", "scratchpad", "hidden_reasoning"],
)
def test_hidden_reasoning_keys_fail(bad_key):
    d = _valid_planner_dict()
    d[bad_key] = "secret"
    ok, errs = validate_contract_output("planner", json.dumps(d))
    assert ok is False
    assert any("forbidden_key" in e for e in errs)


def test_shell_command_in_nested_step_description_fails_for_planner():
    d = _valid_planner_dict()
    d["steps"] = [{"description": "run rm -rf /tmp"}]
    ok, errs = validate_contract_output("planner", d)
    assert ok is False
    assert any("shell_like" in e for e in errs)


def test_get_module_contract_matches_get_prompt_contract():
    c1 = get_module_contract("planner")
    c2 = get_prompt_contract("planner.v1")
    assert c1 is c2


def test_list_prompt_contracts_returns_all_defaults():
    lst = list_prompt_contracts()
    assert len(lst) == len(REQUIRED_MODULES)
    assert {c.module_name for c in lst} == set(REQUIRED_MODULES)


def test_contract_ids_unique():
    ids = [c.contract_id for c in list_prompt_contracts()]
    assert len(ids) == len(set(ids))


def test_version_present_on_all():
    for c in list_prompt_contracts():
        assert c.version and len(c.version) >= 3


def test_parse_json_output_strips_fences():
    inner = _valid_planner_json()
    wrapped = "```json\n" + inner + "\n```"
    obj, errs = parse_json_output(wrapped)
    assert not errs
    assert obj is not None
    assert obj["goal"] == "Do the thing"


def test_validate_module_llm_response_planner():
    ok, errs = validate_module_llm_response("planner", _valid_planner_json())
    assert ok is True


def test_validate_module_llm_response_accepts_dict():
    ok, errs = validate_module_llm_response("planner", _valid_planner_dict())
    assert ok is True


def test_no_llm_calls_in_registry_and_validation():
    import project_guardian.prompt_contracts.registry as reg
    import project_guardian.prompt_contracts.validation as val

    for mod in (reg, val):
        src = open(mod.__file__, encoding="utf-8").read()
        assert "openai" not in src.lower()
        assert "anthropic" not in src.lower()
        assert "requests.post" not in src


def test_contract_to_dict_serializable():
    c = get_prompt_contract("llm_router.v1")
    d = contract_to_dict(c)
    assert d["contract_id"] == c.contract_id
    json.dumps(d)


def test_brain_memory_ranking_shim_matches_canonical_types():
    import project_guardian.brain.memory_ranking as shim
    import project_guardian.memory_ranking as mr

    assert shim.MemoryRankingInput is mr.MemoryRankingInput


def test_brain_pipeline_optional_dry_planner_validation():
    class StaticLLMRouter:
        def choose_backend(self, *, user_text, router_task_type, risk_level, registry=None):
            return "fake-local", "offline"

    class NoopSI:
        def enqueue(self, *a):
            return None

    mem = InMemoryBrainStore()
    pipe = BrainPipeline(guardian=None, memory=mem, llm_router=StaticLLMRouter(), self_improvement=NoopSI())
    sample = _valid_planner_json()
    trace, _ = pipe.run(
        Observation("user", "noop"),
        context={
            "dry_validate_planner_contract": True,
            "dry_validate_planner_contract_sample": sample,
            "use_think_decide_act": False,
            "dry_run": True,
        },
    )
    v = trace.run_context.get("planner_contract_validation")
    assert v is not None
    assert v.get("ok") is True


def test_project_guardian_memory_module_is_memorycore_file():
    import project_guardian.memory as mem

    from pathlib import Path

    assert hasattr(mem, "MemoryCore")
    assert Path(mem.__file__).name == "memory.py"
