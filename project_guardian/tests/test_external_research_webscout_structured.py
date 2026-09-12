"""Validation for WebScout external_research prompt profiles."""

from __future__ import annotations

import json

from project_guardian.module_prompt_registry import (
    structured_reply_text,
    validate_module_llm_output,
)


def test_webscout_url_discovery_accepts_urls_list():
    payload = json.dumps({"urls": ["https://a.example/doc", "https://b.example/ref"]})
    out = validate_module_llm_output("external_research", "webscout_url_discovery", None, payload)
    assert out["valid"] is True
    wire = structured_reply_text(out)
    assert "https://a.example/doc" in wire


def test_webscout_source_summary_wire_is_markdown_string():
    payload = json.dumps({"summary": "## Findings\n\n- item\n"})
    out = validate_module_llm_output("external_research", "webscout_source_summary", None, payload)
    assert out["valid"] is True
    assert structured_reply_text(out).startswith("##")


def test_webscout_llm_only_requires_summary_and_sources():
    payload = json.dumps(
        {
            "summary": "Overview",
            "sources": [
                {
                    "url": "https://x.example",
                    "title": "X",
                    "relevance": "high",
                    "extracted_patterns": ["p1"],
                    "summary": "s",
                }
            ],
        }
    )
    out = validate_module_llm_output("external_research", "webscout_llm_only_research", None, payload)
    assert out["valid"] is True
    assert "Overview" in out["normalized_text"]
