# project_guardian/memory_condense_helpers.py
"""Shared task text, output schema, and parsing for memory condensation LLM calls."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

# Reinforces the same contract as legacy inline prompt; injected via build_prompt_bundle output_schema.
MEMORY_CONDENSE_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "thought": {"type": "string"},
            "category": {"type": "string"},
            "priority": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["thought", "category", "priority"],
    },
    "description": "JSON array only. Each object: thought (string), category (string), priority (0.0–1.0).",
}

_MEMORY_CONDENSE_INSTRUCTIONS = """You are condensing a list of memory entries from an AI system. Your task:
1. Merge redundant or very similar items.
2. Keep important facts, events, and decisions.
3. Output ONLY a valid JSON array of objects per OUTPUT CONTRACT (each object: thought, category, priority).
4. Use category "consensus" for summarized/condensed entries. Reduce the list length significantly while preserving meaning.
5. Do not wrap JSON in markdown code fences; respond with raw JSON only."""


def build_memory_condense_prompt_extra(chunk_text: str) -> Dict[str, Any]:
    """
    Fields consumed by unified_chat_completion / elysia_cloud_fallback via prompt_extra.
    Large memory lines stay in task_text (not CONTEXT) to avoid JSON size truncation in prompt_builder.
    """
    task_text = (
        _MEMORY_CONDENSE_INSTRUCTIONS
        + "\n\nMemories to condense (one per line, format: [time] category priority | thought):\n"
        + chunk_text
        + "\n\nOutput the JSON array only, no other text."
    )
    return {
        "task_text": task_text,
        "output_schema": MEMORY_CONDENSE_OUTPUT_SCHEMA,
        "task_type": "memory_condense",
    }


def strip_json_fences(text: str) -> str:
    """Remove common markdown fences from model output."""
    t = text.strip()
    for marker in ("```json", "```"):
        if t.startswith(marker):
            t = t[len(marker) :].strip()
        if t.endswith("```"):
            t = t[:-3].strip()
    return t


def parse_condensed_memory_json(reply: str) -> Tuple[Optional[List[Any]], Optional[str]]:
    """
    Parse LLM reply into a list of dict items. Returns (list, None) on success, (None, error_reason) on failure.
    """
    if not reply or not str(reply).strip():
        return None, "empty_reply"
    text = strip_json_fences(reply.strip())
    try:
        arr = json.loads(text)
    except json.JSONDecodeError:
        return None, "JSON parse failed"
    if not isinstance(arr, list):
        return None, "Response not a list"
    return arr, None
