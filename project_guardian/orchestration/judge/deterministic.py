# project_guardian/orchestration/judge/deterministic.py
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..types import NodeResult, TaskRequest


def _as_text(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output.strip()
    try:
        return json.dumps(output)
    except Exception:
        return str(output)


def _json_score(text: str, rubric_keys: Optional[List[str]] = None) -> tuple[float, str]:
    t = (text or "").strip()
    if not t:
        return 0.0, "empty"
    score = 0.25
    # crude JSON extraction
    blob = t
    if "{" in t:
        start = t.index("{")
        end = t.rindex("}") + 1
        blob = t[start:end]
    try:
        obj = json.loads(blob)
        if isinstance(obj, dict):
            score += 0.35
            keys = set(obj.keys())
            if rubric_keys:
                hit = sum(1 for k in rubric_keys if k in keys)
                score += min(0.35, hit * 0.12)
            else:
                score += 0.2
            return min(1.0, score), "ok_json"
    except Exception:
        pass
    if 20 < len(t) < 120_000:
        score += 0.1
    return min(0.85, score), "partial_text"


class DeterministicJudge:
    """Length / non-empty / JSON / rubric keys. Returns a NodeResult summarizing verdict."""

    def __init__(self, rubric_keys: Optional[List[str]] = None) -> None:
        self.rubric_keys = rubric_keys or ["chosen_action", "reasoning", "confidence"]

    async def compare(self, outputs: List[NodeResult], request: TaskRequest) -> NodeResult:
        if not outputs:
            return NodeResult(
                node_id="deterministic_judge",
                provider="deterministic",
                model="rules",
                output="",
                success=False,
                latency_ms=0.0,
                review_verdict="no_outputs",
                outcome_score=0.0,
                error="no_outputs",
            )

        rubric = self.rubric_keys
        meta = request.metadata or {}
        rk = meta.get("review_rubric_keys")
        if isinstance(rk, list) and rk:
            rubric = [str(x) for x in rk]

        best: Optional[NodeResult] = None
        best_score = -1.0
        best_reason = ""

        for nr in outputs:
            text = _as_text(nr.output)
            sc, why = _json_score(text, rubric)
            if sc > best_score:
                best_score = sc
                best = nr
                best_reason = why

        assert best is not None
        inconclusive = len(outputs) > 1 and best_score < 0.62
        verdict = "inconclusive" if inconclusive else ("accepted" if best_score >= 0.62 else "rejected")

        return NodeResult(
            node_id="deterministic_judge",
            provider="deterministic",
            model="rules",
            output=best.output,
            success=best_score >= 0.55,
            latency_ms=0.0,
            review_verdict=verdict,
            outcome_score=round(best_score, 4),
            error=None if best_score >= 0.55 else "low_score",
        )


def pick_best_node(outputs: List[NodeResult], rubric_keys: Optional[List[str]] = None) -> NodeResult:
    keys = rubric_keys or ["chosen_action", "reasoning", "confidence"]
    best = outputs[0]
    best_s = -1.0
    for nr in outputs:
        sc, _ = _json_score(_as_text(nr.output), keys)
        if sc > best_s:
            best_s = sc
            best = nr
    return best


def strip_json_fence(text: str) -> str:
    t = (text or "").strip()
    m = re.match(r"^```(?:json)?\s*([\s\S]*?)```$", t, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return t
