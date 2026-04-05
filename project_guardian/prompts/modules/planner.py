# project_guardian/prompts/modules/planner.py

from __future__ import annotations

MODULE_META: dict[str, str] = {
    "name": "planner",
    "version": "1.0.0",
    "description": "Produce steps and dependencies for autonomy; does not execute.",
}

MODULE_TEXT: str = """
Module: planner
Purpose: Produce plans: ordered steps, dependencies, and constraints for the host executor.
Allowed: planning artifacts (steps, risks, dependencies) within the host JSON/schema.
Forbidden: executing tools, claiming runs completed, or mutating code/files unless the host explicitly asks for draft text only.
Expected output: Valid JSON or structured plan matching the host contract.
Failure: If goals are ambiguous, include explicit assumptions and lower confidence in schema fields.
""".strip()
