# project_guardian/prompts/modules/summarizer.py

from __future__ import annotations

MODULE_META: dict[str, str] = {
    "name": "summarizer",
    "version": "1.0.0",
    "description": "Compress text while preserving critical facts.",
}

MODULE_TEXT: str = """
Module: summarizer
Purpose: Compress long text to a shorter form without dropping safety-critical or task-critical facts.
Allowed: summaries, bullet extractions, salience-ranked snippets as requested by the host.
Forbidden: adding facts not present in source material, speculative claims.
Expected output: Length-bounded summary per host instructions.
Failure: If input is empty or too short to summarize, return a faithful short note.
""".strip()
