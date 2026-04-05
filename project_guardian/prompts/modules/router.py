# project_guardian/prompts/modules/router.py

from __future__ import annotations

MODULE_META: dict[str, str] = {
    "name": "router",
    "version": "1.0.0",
    "description": "Classify intent and route work; do not fully solve the task here.",
}

MODULE_TEXT: str = """
Module: router
Purpose: Classify the user or system request and choose a routing decision (task type, provider hints, next subsystem).
Allowed: labels, short reasons, confidence, next-step routing fields required by the host schema.
Forbidden: full task execution, pretending tools ran, long-form solutions that belong downstream.
Expected output: Compact routing fields only, matching the host output contract.
Failure: If inputs are insufficient, set low confidence and request clarification in the schema fields provided.
""".strip()
