# project_guardian/prompts/modules/tool_selection.py

from __future__ import annotations

MODULE_META: dict[str, str] = {
    "name": "tool_selection",
    "version": "1.0.0",
    "description": "Select/rank tools from a catalog; never claim execution.",
}

MODULE_TEXT: str = """
Module: tool_selection
Purpose: Choose or rank tools/actions from the provided catalog to satisfy a goal.
Allowed: tool names and arguments from the catalog only; minimal justification fields if required by schema.
Forbidden: inventing tools, substituting freeform narrative for tool calls, claiming tools executed.
Expected output: JSON matching host schema (e.g. actions list with tool + args).
Failure: If no tool fits, use schema fallback fields and explain the gap briefly.
""".strip()
