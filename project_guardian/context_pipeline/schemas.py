# project_guardian/context_pipeline/schemas.py
"""Shared schema constants and topic buckets for the context → decision pipeline."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, TypedDict

# Archive / routing buckets (stable string ids).
TOPIC_BUCKETS: tuple[str, ...] = (
    "identity",
    "goals",
    "preferences",
    "constraints",
    "unresolved_questions",
    "projects",
    "risks",
    "monetization",
    "autonomy",
    "architecture",
)

SourceType = Literal[
    "user_input",
    "memory",
    "chat_history",
    "log",
    "browser_finding",
    "task_snapshot",
    "monitor_snapshot",
    "planner_snapshot",
    "unknown",
]


class IngestedRecordDict(TypedDict, total=False):
    id: str
    source_type: str
    timestamp: float
    raw_text: str
    tags: List[str]
    session_id: str
    trust_score: float
    initial_importance: float
    metadata: Dict[str, Any]


# JSON-schema-shaped dict for Ollama `format` (subset; Ollama accepts JSON Schema style).
PROMPT_PACKET_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "task_type": {"type": "string"},
        "objective": {"type": "string"},
        "facts": {"type": "array", "items": {"type": "string"}},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "unknowns": {"type": "array", "items": {"type": "string"}},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "record_id": {"type": "string"},
                    "snippet": {"type": "string"},
                    "source_type": {"type": "string"},
                },
                "required": ["snippet"],
            },
        },
        "requested_output_schema": {"type": "string"},
    },
    "required": [
        "task_type",
        "objective",
        "facts",
        "constraints",
        "risks",
        "unknowns",
        "evidence",
        "requested_output_schema",
    ],
}

# Expected shape from remote / structured reasoning step (validated in Python).
STRUCTURED_ONLINE_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {"type": "string"},
        "reasoning": {"type": "string"},
        "confidence": {"type": "number"},
        "missing_info": {"type": "array", "items": {"type": "string"}},
        "next_steps": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decision", "reasoning", "confidence", "missing_info", "next_steps", "risks"],
}
