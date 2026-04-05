# project_guardian/orchestration/tools/schemas.py
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional

TargetKind = Literal["module", "tool", "none"]


@dataclass
class ActionIntent:
    action_type: str
    target_kind: TargetKind
    target_name: Optional[str]
    payload: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    rationale: str = ""


@dataclass
class ExecutionResult:
    success: bool
    target_kind: str
    target_name: str
    payload: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    state_change_evidence: Dict[str, Any] = field(default_factory=dict)

    def result_for_governance(self) -> Any:
        return self.payload.get("result")


ACTION_INTENT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "action_type": {"type": "string"},
        "target_kind": {"type": "string", "enum": ["module", "tool", "none"]},
        "target_name": {"type": "string"},
        "payload": {"type": "object"},
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["action_type", "target_kind", "confidence", "rationale"],
}


def strip_json_fence(text: str) -> str:
    t = (text or "").strip()
    m = re.match(r"^```(?:json)?\s*([\s\S]*?)```$", t, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return t


def parse_action_intent(text: str) -> Optional[ActionIntent]:
    raw = strip_json_fence(text)
    if not raw.strip():
        return None
    try:
        obj = json.loads(raw) if raw.strip().startswith("{") else None
        if not isinstance(obj, dict):
            return None
        tk = str(obj.get("target_kind") or "none").lower()
        if tk not in ("module", "tool", "none"):
            tk = "none"
        return ActionIntent(
            action_type=str(obj.get("action_type") or "unknown"),
            target_kind=tk,  # type: ignore[arg-type]
            target_name=(str(obj["target_name"]).strip() if obj.get("target_name") else None),
            payload=dict(obj.get("payload") or {}) if isinstance(obj.get("payload"), dict) else {},
            confidence=float(obj.get("confidence") or 0.5),
            rationale=str(obj.get("rationale") or "")[:2000],
        )
    except Exception:
        return None


def intent_allowed(intent: ActionIntent, allowed_caps: List[str]) -> bool:
    if not allowed_caps:
        return True
    if intent.target_kind == "none":
        return True
    tn = (intent.target_name or "").strip()
    if not tn:
        return False
    key = f"{intent.target_kind}:{tn}".lower()
    for a in allowed_caps:
        if str(a).strip().lower() == key:
            return True
    return False


def execution_result_to_dict(er: ExecutionResult) -> Dict[str, Any]:
    d = asdict(er)
    return d
