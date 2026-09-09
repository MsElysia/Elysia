"""make_learning_llm_callback + structured compress extraction."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from project_guardian.auto_learning import (
    compress_with_llm,
    make_learning_llm_callback,
)


def test_make_learning_llm_callback_forwards_structured_kwargs():
    seen: Dict[str, Any] = {}

    class _Fake:
        def _autonomy_llm_completion(
            self,
            messages: List[Dict[str, str]],
            max_tokens: int = 2000,
            *,
            module_name: str = "planner",
            agent_name: str | None = None,
            prompt_extra=None,
            structured_role=None,
            skip_capability_preamble: bool = False,
        ):
            seen["structured_role"] = structured_role
            seen["prompt_extra"] = prompt_extra
            seen["skip"] = skip_capability_preamble
            seen["module"] = module_name
            return (
                json.dumps({"compressed_text": "short"}),
                "",
            )

    cb = make_learning_llm_callback(_Fake())
    txt, err = cb(
        "long prompt blob",
        structured_role="sequential_processing:accumulated_context_compression",
        prompt_extra={"task": {"x": 1}},
        module_name="summarizer",
        agent_name=None,
        max_tokens=900,
    )
    assert err == ""
    assert txt
    assert seen["structured_role"] == "sequential_processing:accumulated_context_compression"
    assert seen["skip"] is True
    assert seen["module"] == "summarizer"


def test_compress_with_llm_extracts_compressed_text_from_structured_reply():
    def cb(msg: str, **kwargs):  # type: ignore[misc]
        payload = {"compressed_text": "Kept facts about shipping and tooling."}
        return json.dumps(payload), ""

    out = compress_with_llm(("x " * 300), cb, module_name="summarizer")
    assert "Kept facts" in out
    assert len(out) <= 800


def test_compress_with_llm_legacy_callback_no_kwargs():
    def cb_legacy(msg: str):
        # Old one-arg signatures still work via TypeError fallback.
        assert len(msg) > 20
        return "fallback plain.", ""

    out = compress_with_llm(("y " * 300), cb_legacy, module_name="summarizer")
    assert "fallback" in out
