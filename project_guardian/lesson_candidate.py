"""Pure, candidate-only bridge from synthetic task outcomes to existing source memory.

No new store, scheduler, model, task executor, or memory promotion.
A matching hash proves only receipt integrity; it does NOT prove external truth,
authorization, or that the task's self-reported success was independently reviewed.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


class LessonCandidateError(ValueError):
    """A task receipt cannot be admitted as even a synthetic learning candidate."""


def _distinct_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous keys, including Unicode-escaped and nested duplicates."""
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON receipt field")
        obj[key] = value
    return obj


def _reject_json_constant(_value: str) -> None:
    """Reject NaN and Infinity, which are not standard JSON values."""
    raise ValueError("non-finite JSON receipt field")


def prepare_synthetic_lesson_candidate(receipt_bytes: bytes) -> dict[str, Any]:
    """Return source-memory writer inputs, not permission or an accepted fact.

    The caller may separately persist this explicit synthetic *candidate* through
    the existing source-intelligence/transaction path. This function writes nothing.
    """
    if type(receipt_bytes) is not bytes or not (1 <= len(receipt_bytes) <= 8192):
        raise LessonCandidateError("expected bounded exact synthetic receipt bytes")
    try:
        receipt = json.loads(
            receipt_bytes.decode("utf-8"),
            object_pairs_hook=_distinct_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, ValueError) as exc:
        raise LessonCandidateError("invalid UTF-8 JSON receipt") from exc
    if type(receipt) is not dict or receipt.get("schema") != "elysia-synthetic-outcome-v1":
        raise LessonCandidateError("unsupported receipt schema")
    if receipt.get("synthetic_fixture") is not True:
        raise LessonCandidateError("only explicitly synthetic fixtures are admitted")
    task_id = receipt.get("task_id")
    if type(task_id) is not str or re.fullmatch(r"[a-zA-Z0-9_.:-]{1,64}", task_id) is None:
        raise LessonCandidateError("invalid task id")
    if (
        receipt.get("status") != "completed"
        or receipt.get("execution_outcome") != "succeeded"
        or receipt.get("execution_attempted") is not True
        or receipt.get("value_verified") is not True
        or receipt.get("useful") is not True
    ):
        raise LessonCandidateError("no claimed successful, value-verified task outcome")
    lesson = receipt.get("lesson")
    evidence = receipt.get("evidence_text")
    digest = receipt.get("evidence_sha256")
    if (
        type(lesson) is not str or not (1 <= len(lesson.strip()) <= 300)
        or type(evidence) is not str or not (1 <= len(evidence.encode("utf-8")) <= 4096)
        or type(digest) is not str or re.fullmatch(r"[a-f0-9]{64}", digest) is None
    ):
        raise LessonCandidateError("missing bounded lesson or exact evidence digest")
    # No LLM inference: the proposed lesson must appear literally in the recorded evidence.
    if lesson not in evidence:
        raise LessonCandidateError("lesson is not supported by literal receipt evidence")
    if hashlib.sha256(evidence.encode("utf-8")).hexdigest() != digest:
        raise LessonCandidateError("evidence bytes do not match claimed digest")

    # Source identity is content-addressed. Re-applying identical bytes is an
    # idempotent operation in the existing source-intelligence writer.
    raw_sha = hashlib.sha256(receipt_bytes).hexdigest()
    return {
        "raw_bytes": receipt_bytes,
        "source_identity": "elysia-synthetic-lesson-candidate:" + raw_sha,
        "tag_hints": ("lesson_candidate",),
        "candidate_only": True,
    }
