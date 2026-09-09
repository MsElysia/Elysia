"""Structured output validation for mutation_engine openai_file_rewrite profile."""

from __future__ import annotations

import json

from project_guardian.module_prompt_registry import (
    build_module_llm_messages,
    validate_module_llm_output,
)


def test_openai_file_rewrite_profile_accepts_json():
    payload = json.dumps({"proposed_source": "def x():\n    return 1\n"})
    out = validate_module_llm_output("mutation_engine", "openai_file_rewrite", None, payload)
    assert out["valid"] is True
    assert out["data"]["proposed_source"] == "def x():\n    return 1\n"
    assert json.loads(out["normalized_text"])["proposed_source"] == "def x():\n    return 1\n"


def test_openai_file_rewrite_rejects_missing_key():
    payload = json.dumps({"other": "x"})
    out = validate_module_llm_output("mutation_engine", "openai_file_rewrite", None, payload)
    assert out["valid"] is False


def test_openai_file_rewrite_messages_include_schema_hint():
    msgs = build_module_llm_messages(
        "mutation_engine",
        "openai_file_rewrite",
        None,
        {"task_id": "t1", "task": {"instruction": "fix typo"}},
    )
    assert len(msgs) >= 2
    combined = "\n".join(m.get("content", "") for m in msgs)
    assert "proposed_source" in combined
