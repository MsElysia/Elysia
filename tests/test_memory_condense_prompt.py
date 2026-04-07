"""Tests for memory condensation prompt-profile migration (structured JSON contract)."""

from __future__ import annotations

import pytest

from project_guardian.llm.prompted_call import prepare_prompted_bundle
from project_guardian.memory_condense_helpers import (
    MEMORY_CONDENSE_OUTPUT_SCHEMA,
    build_memory_condense_prompt_extra,
    parse_condensed_memory_json,
)
from project_guardian.prompts import prompt_registry


def test_memory_condense_prompt_extra_includes_task_and_schema():
    pe = build_memory_condense_prompt_extra("[t] g 0.5 | hello")
    assert pe["task_type"] == "memory_condense"
    assert "Memories to condense" in pe["task_text"]
    assert "[t] g 0.5 | hello" in pe["task_text"]
    assert pe["output_schema"] == MEMORY_CONDENSE_OUTPUT_SCHEMA


def test_prepare_prompted_bundle_memory_condense_has_output_contract():
    pe = build_memory_condense_prompt_extra("a\nb")
    prep = prepare_prompted_bundle(
        module_name="memory_condense",
        agent_name=None,
        task_text=pe["task_text"],
        output_schema=pe["output_schema"],
        caller="tests.test_memory_condense_prompt",
    )
    text = prep["prompt_text"]
    assert "memory_condense" in text.lower() or "Memory" in text
    assert "OUTPUT CONTRACT" in text
    assert '"thought"' in text or "thought" in text
    assert prep["module_name"] == "memory_condense"
    assert prep["agent_name"] is None
    assert prep["meta"]["module"]["name"] == "memory_condense"


def test_parse_condensed_memory_json_preserves_contract():
    raw = '[{"thought":"x","category":"consensus","priority":0.5}]'
    arr, err = parse_condensed_memory_json(raw)
    assert err is None
    assert arr == [{"thought": "x", "category": "consensus", "priority": 0.5}]


def test_parse_strips_fences():
    raw = '```json\n[{"thought":"a","category":"c","priority":1}]\n```'
    arr, err = parse_condensed_memory_json(raw)
    assert err is None
    assert len(arr) == 1


def test_parse_invalid_json():
    _, err = parse_condensed_memory_json("not json")
    assert err == "JSON parse failed"


def test_unknown_prompt_module_raises():
    with pytest.raises(KeyError) as exc:
        prompt_registry.get_module("definitely_not_a_registered_module_xyz")
    assert "Unknown prompt module" in str(exc.value)


def test_logging_fields_flatten_for_bundle_meta():
    pe = build_memory_condense_prompt_extra("x")
    prep = prepare_prompted_bundle(
        module_name="memory_condense",
        task_text=pe["task_text"],
        output_schema=pe["output_schema"],
        caller="tests",
    )
    from project_guardian.llm.prompted_call import flatten_bundle_meta

    flat = flatten_bundle_meta(prep["meta"])
    assert flat["prompt_module_name"] == "memory_condense"
    assert flat["prompt_module_version"]
