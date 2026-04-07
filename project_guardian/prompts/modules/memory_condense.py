# project_guardian/prompts/modules/memory_condense.py
"""Prompt module for AI-assisted memory log condensation (strict JSON array output)."""

from __future__ import annotations

MODULE_META: dict[str, str] = {
    "name": "memory_condense",
    "version": "1.0.0",
    "description": "Condense redundant memory entries; emit JSON array only per host schema.",
}

MODULE_TEXT: str = """
Module: memory_condense
Purpose: Merge redundant memory lines while preserving important facts, events, and decisions.
Allowed: deduplication, salience-preserving merge, category normalization per host rules.
Forbidden: inventing facts not supported by supplied memory lines, narrative prose outside the required format.
Expected output: ONLY the JSON structure defined by OUTPUT CONTRACT — no markdown fences, no commentary.
Failure: If input is empty, return [] as JSON array; never freeform chat.
""".strip()
