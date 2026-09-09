"""Structured validation for implementer.codegen_patch profile."""

from __future__ import annotations

import json

from project_guardian.module_prompt_registry import (
    build_module_llm_messages,
    structured_reply_text,
    validate_module_llm_output,
)


def test_codegen_patch_accepts_patch_document():
    body = "FILE: foo.py\nprint(1)\n"
    payload = json.dumps({"patch_document": body})
    out = validate_module_llm_output("implementer", "codegen_patch", None, payload)
    assert out["valid"] is True
    assert out["data"]["patch_document"] == body
    assert structured_reply_text(out) == body


def test_codegen_patch_rejects_missing_key():
    out = validate_module_llm_output("implementer", "codegen_patch", None, json.dumps({"x": 1}))
    assert out["valid"] is False


def test_codegen_patch_messages_mention_patch_document():
    msgs = build_module_llm_messages(
        "implementer",
        "codegen_patch",
        None,
        {"task_id": "t1", "task": {"step_description": "add logging"}},
    )
    blob = "\n".join(m.get("content", "") for m in msgs)
    assert "patch_document" in blob
