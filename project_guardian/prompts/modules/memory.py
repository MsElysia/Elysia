# project_guardian/prompts/modules/memory.py

from __future__ import annotations

MODULE_META: dict[str, str] = {
    "name": "memory",
    "version": "1.0.0",
    "description": "Memory extract/store/retrieve; never invent stored facts.",
}

MODULE_TEXT: str = """
Module: memory
Purpose: Extract, store, retrieve, or rank memory-relevant facts from provided context.
Allowed: structured memory operations as defined by the host (keys, snippets, salience).
Forbidden: inventing past events, user statements, or tool outcomes not present in supplied context.
Expected output: Fields required by the host schema (e.g. memory lines, queries, or retrieval targets).
Failure: If nothing to store or retrieve, return empty structures and a brief honest note per schema.
""".strip()
