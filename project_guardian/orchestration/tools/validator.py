# project_guardian/orchestration/tools/validator.py
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Literal, Optional, Set

from .candidates import CapabilityCandidate
from .schemas import ActionIntent

logger = logging.getLogger(__name__)

FallbackMode = Literal["legacy_capability_loop", "model_only", "none"]


def _coerce_fallback(mode: str, default: FallbackMode = "legacy_capability_loop") -> FallbackMode:
    if mode in ("legacy_capability_loop", "model_only", "none"):
        return mode  # type: ignore[return-value]
    return default


@dataclass
class ValidatedActionIntent:
    valid: bool
    normalized_intent: Optional[ActionIntent]
    fallback_mode: FallbackMode
    reason: str
    chosen_target_in_candidates: bool = False


def _action_type_compatible(action_type: str, target_kind: str) -> bool:
    at = (action_type or "").strip().lower()
    tk = (target_kind or "").lower()
    if tk == "none":
        return True
    if tk == "module":
        if at in ("tool_call", "bounded_tool", "invoke_tool"):
            return False
    if tk == "tool":
        if at in ("module_call", "bounded_module", "invoke_module"):
            return False
    return True


def _find_candidate(
    candidates: List[CapabilityCandidate], kind: str, name: str
) -> Optional[CapabilityCandidate]:
    k = (kind or "").lower().strip()
    n = (name or "").strip().lower()
    if not n:
        return None
    for c in candidates:
        if c.target_kind == k and c.target_name.strip().lower() == n:
            return c
    return None


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9_\-]+", "_", (name or "").strip().lower())[:80]


def validate_action_intent(
    intent: Optional[ActionIntent],
    candidates: List[CapabilityCandidate],
    *,
    min_confidence: float = 0.35,
    invalid_fallback: str = "legacy_capability_loop",
) -> ValidatedActionIntent:
    inv_fb = _coerce_fallback(invalid_fallback)
    if not candidates:
        return ValidatedActionIntent(
            valid=False,
            normalized_intent=None,
            fallback_mode="legacy_capability_loop",
            reason="no_candidates_built",
            chosen_target_in_candidates=False,
        )

    if intent is None:
        return ValidatedActionIntent(
            valid=False,
            normalized_intent=None,
            fallback_mode=inv_fb,
            reason="unparseable_intent",
            chosen_target_in_candidates=False,
        )

    tk = intent.target_kind
    if tk not in ("module", "tool", "none"):
        return ValidatedActionIntent(
            valid=False,
            normalized_intent=None,
            fallback_mode=inv_fb,
            reason="invalid_target_kind",
            chosen_target_in_candidates=False,
        )

    conf = float(intent.confidence or 0.0)
    if conf < float(min_confidence) and tk != "none":
        return ValidatedActionIntent(
            valid=False,
            normalized_intent=intent,
            fallback_mode=inv_fb,
            reason="below_min_confidence",
            chosen_target_in_candidates=False,
        )

    if tk == "none":
        ni = ActionIntent(
            action_type=intent.action_type or "model_only",
            target_kind="none",
            target_name=None,
            payload={},
            confidence=conf,
            rationale=intent.rationale,
        )
        return ValidatedActionIntent(
            valid=True,
            normalized_intent=ni,
            fallback_mode="none",
            reason="explicit_model_only",
            chosen_target_in_candidates=False,
        )

    tn = (intent.target_name or "").strip()
    if not tn:
        return ValidatedActionIntent(
            valid=False,
            normalized_intent=intent,
            fallback_mode=inv_fb,
            reason="empty_target_name",
            chosen_target_in_candidates=False,
        )

    cand = _find_candidate(candidates, tk, tn)
    if cand is None:
        cand_alt = _find_candidate(candidates, tk, _normalize_name(tn))
        cand = cand_alt
    if cand is None:
        return ValidatedActionIntent(
            valid=False,
            normalized_intent=intent,
            fallback_mode=inv_fb,
            reason="target_not_in_candidate_set",
            chosen_target_in_candidates=False,
        )

    if not _action_type_compatible(intent.action_type, tk):
        return ValidatedActionIntent(
            valid=False,
            normalized_intent=intent,
            fallback_mode=inv_fb,
            reason="action_type_incompatible_with_target_kind",
            chosen_target_in_candidates=True,
        )

    allowed: Set[str] = set(cand.allowed_payload_keys)
    raw_pl = dict(intent.payload or {}) if isinstance(intent.payload, dict) else {}
    filtered = {k: v for k, v in raw_pl.items() if k in allowed}
    dropped = [k for k in raw_pl if k not in allowed]

    ni = ActionIntent(
        action_type=intent.action_type or "bounded_capability",
        target_kind=tk,  # type: ignore[arg-type]
        target_name=cand.target_name,
        payload=filtered,
        confidence=conf,
        rationale=intent.rationale,
    )

    if dropped:
        logger.debug("[validator] dropped payload keys: %s", dropped[:12])

    return ValidatedActionIntent(
        valid=True,
        normalized_intent=ni,
        fallback_mode="none",
        reason="ok",
        chosen_target_in_candidates=True,
    )
