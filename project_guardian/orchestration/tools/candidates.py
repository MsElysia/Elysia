# project_guardian/orchestration/tools/candidates.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

TargetKind = Literal["module", "tool"]

# Self-task archetypes allowed to use brokered bounded orchestration (keep small).
BROKERED_BOUNDED_SELF_TASK_ARCHETYPES = frozenset(
    {
        "validate_tool_registry_snapshot",
        "evaluate_existing_objectives_for_monetization",
        "exercise_module_longterm_planner",
    }
)

# Default payload keys merged with bridge defaults (task, query, objective, …).
_BASE_PAYLOAD_KEYS = [
    "task",
    "query",
    "objective",
    "self_task_archetype",
    "underused_modules",
    "prompt",
    "method",
    "structured_task",
    "source",
]


@dataclass
class CapabilityCandidate:
    target_kind: TargetKind
    target_name: str
    label: str
    allowed_payload_keys: List[str]
    priority: float
    reason: str

    def key(self) -> str:
        return f"{self.target_kind}:{self.target_name}".lower()

    def to_planner_dict(self) -> Dict[str, Any]:
        return {
            "target_kind": self.target_kind,
            "target_name": self.target_name,
            "label": self.label,
            "priority": round(self.priority, 4),
            "allowed_payload_keys": list(self.allowed_payload_keys),
        }


def _payload_keys_for(kind: str, name: str) -> List[str]:
    n = (name or "").strip().lower()
    keys = list(_BASE_PAYLOAD_KEYS)
    if n == "task_router":
        keys.append("structured_task")
    return keys


def build_capability_candidates(
    *,
    allowed_capabilities: List[str],
    archetype: str,
    max_candidates: int = 5,
    registry_hint: Optional[Dict[str, Any]] = None,
) -> List[CapabilityCandidate]:
    """
    Bounded candidate set only (max N). Sources: recommended/allowed capability strings.
    registry_hint is optional precomputed snapshot; if present, used only to annotate reason.
    """
    max_n = max(1, min(8, int(max_candidates or 5)))
    raw = [str(x).strip() for x in (allowed_capabilities or []) if str(x).strip()]
    out: List[CapabilityCandidate] = []
    seen: set[str] = set()

    reg_note = ""
    if isinstance(registry_hint, dict) and registry_hint:
        reg_note = " (registry snapshot available)"

    for i, cap in enumerate(raw):
        if ":" not in cap:
            continue
        kind, _, name = cap.partition(":")
        kind = kind.strip().lower()
        name = name.strip()
        if kind not in ("module", "tool") or not name:
            continue
        key = f"{kind}:{name}".lower()
        if key in seen:
            continue
        seen.add(key)
        pri = 1.0 - (i * 0.07)
        out.append(
            CapabilityCandidate(
                target_kind=kind,  # type: ignore[arg-type]
                target_name=name,
                label=f"{name} ({kind})",
                allowed_payload_keys=_payload_keys_for(kind, name),
                priority=round(pri, 4),
                reason=f"from_recommended_capabilities[{i}]{reg_note}",
            )
        )
        if len(out) >= max_n:
            break

    out.sort(key=lambda c: -c.priority)
    return out[:max_n]


def candidates_json_for_prompt(candidates: List[CapabilityCandidate]) -> str:
    return json.dumps([c.to_planner_dict() for c in candidates], indent=0)[:6000]
