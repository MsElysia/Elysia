# project_guardian/brain/self_improvement_module.py

from __future__ import annotations

import json
import logging
from pathlib import Path

from .contracts import BrainPipelineTrace, LearningOutcome, SelfImprovementModule

logger = logging.getLogger(__name__)


def _queue_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    d = root / "data" / "runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d / "brain_self_improvement_queue.jsonl"


class JsonlSelfImprovementQueue(SelfImprovementModule):
    """Append-only proposals — does not rewrite core code.

    By default writes only the canonical
    :mod:`project_guardian.self_improvement.proposal_queue` JSONL. Legacy
    ``brain_self_improvement_queue.jsonl`` rows are written only when
    ``ELYSIA_LEGACY_SELF_IMPROVEMENT_QUEUE=1`` (or ``true``/``yes``/``on``).
    """

    def __init__(self, path: Path | None = None, *, canonical_path: Path | None = None) -> None:
        self._path = path or _queue_path()
        self._canonical_path = canonical_path

    def enqueue(self, outcome: LearningOutcome, trace: BrainPipelineTrace) -> None:
        row = {
            "worked": outcome.worked,
            "hints": outcome.improvement_hints,
            "lesson_sample": outcome.lesson[:400],
            "transitions": trace.transitions[-24:],
        }
        try:
            from project_guardian.self_improvement.proposal_queue import (
                append_legacy_brain_row,
                append_proposal,
                create_proposal_from_brain_learning,
                legacy_queue_write_enabled,
            )

            prop = create_proposal_from_brain_learning(outcome, trace)
            append_proposal(prop, path=self._canonical_path)
            if legacy_queue_write_enabled():
                append_legacy_brain_row(row, legacy_path=self._path)
        except Exception as e:
            logger.warning("brain.self_improvement enqueue failed: %s", e)
            return
        logger.info(
            "brain.self_improvement queued canonical=%s legacy_write=%s legacy_path=%s",
            self._canonical_path,
            legacy_queue_write_enabled(),
            self._path,
        )
