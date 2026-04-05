# project_guardian/self_task_execution_outcome.py
# Post-execution verification: distinguish ready vs attempted vs succeeded.

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .self_task_output_contracts import normalize_payload

logger = logging.getLogger(__name__)

# Tasks that represent real execution attempts (vs planning/readiness-only).
_EXECUTION_ATTEMPT_ARCHETYPES = frozenset(
    {
        "execute_best_opportunity",
        "repair_tool_registry_coverage",
    }
)

# Planning / readiness-only for execution domain (never "execution succeeded").
_READINESS_PLAN_ARCHETYPES = frozenset(
    {
        "generate_execution_plan",
    }
)


def is_execution_stage_archetype(archetype: str) -> bool:
    """True if this archetype participates in execution outcome tracking."""
    a = (archetype or "").lower()
    if a in _EXECUTION_ATTEMPT_ARCHETYPES or a in _READINESS_PLAN_ARCHETYPES:
        return True
    if "execute" in a and "diagnostic" not in a and "digest" not in a:
        return True
    if a.startswith("repair_") and ("registry" in a or "tool" in a):
        return True
    if "system_improvement" in a or "improvement_proposal" in a:
        return True
    return False


def _has_state_change_evidence(
    *,
    archetype: str,
    payload: Any,
    artifact_path: Optional[Path],
    memory_written: bool,
    capability_ex: Optional[Dict[str, Any]],
) -> bool:
    if artifact_path is not None:
        return True
    if memory_written:
        return True
    p = normalize_payload(payload)
    if isinstance(p, dict):
        for k in (
            "state_changed",
            "applied",
            "dry_run_result",
            "files_written",
            "files_updated",
            "registry_updated",
            "patch_applied",
            "downstream_result",
            "external_result",
        ):
            v = p.get(k)
            if v and v not in (False, [], {}, ""):
                return True
        ep = p.get("execution_plan")
        if isinstance(ep, dict) and ep.get("state_changed"):
            return True
    if capability_ex:
        err = capability_ex.get("error")
        if err:
            return False
        r = capability_ex.get("result")
        if isinstance(r, dict) and any(
            r.get(k) for k in ("state_changed", "applied", "registry_updated", "files_written")
        ):
            return True
    return False


def _has_downstream_action_hint(
    *,
    archetype: str,
    payload: Any,
    capability_ex: Optional[Dict[str, Any]],
) -> bool:
    """Heuristic: tool/module reported something beyond a bare plan dict."""
    p = normalize_payload(payload)
    arch = (archetype or "").lower()
    if isinstance(p, dict):
        if p.get("downstream_result") or p.get("dry_run_result"):
            return True
        if arch == "execute_best_opportunity":
            # Builtin revenue_executor often returns plan + summary only — not downstream.
            ig = p.get("opportunities") or p.get("income_snapshot_keys")
            if isinstance(ig, dict) and len(ig) > 0:
                return True
            if p.get("execution_plan") and _has_state_change_evidence(
                archetype=archetype,
                payload=p,
                artifact_path=None,
                memory_written=False,
                capability_ex=capability_ex,
            ):
                return True
    return False


def evaluate_execution_outcome(
    *,
    archetype: str,
    execution_ready: bool,
    execution_tier: str,
    capability_attempted: bool,
    capability_ok: bool,
    last_result: Any,
    artifact_path: Optional[Path],
    memory_written: bool,
    last_capability_ex: Optional[Dict[str, Any]],
    detail: str,
) -> Dict[str, Any]:
    """
    Phase 1 fields:
    - execution_attempted
    - execution_outcome: succeeded | partial | failed | none
    - execution_reason
    - execution_artifact (optional path string)
    - execution_followup_needed
    """
    arch = (archetype or "").lower()
    tier = (execution_tier or "").lower()
    out: Dict[str, Any] = {
        "execution_attempted": False,
        "execution_outcome": "none",
        "execution_reason": "not_execution_stage",
        "execution_artifact": None,
        "execution_followup_needed": False,
    }

    if not is_execution_stage_archetype(arch):
        return out

    out["execution_reason"] = "evaluating"

    if arch in _READINESS_PLAN_ARCHETYPES or arch == "generate_execution_plan":
        out["execution_attempted"] = bool(capability_attempted and tier != "failed")
        out["execution_outcome"] = "readiness_only"
        out["execution_reason"] = (
            "generate_execution_plan is readiness support only; not an execution success"
        )
        out["execution_followup_needed"] = False
        return out

    out["execution_attempted"] = bool(capability_attempted and tier != "failed")

    if not capability_attempted or tier == "failed":
        out["execution_outcome"] = "failed"
        out["execution_reason"] = detail[:300] if detail else "no_capability_attempt_or_task_failed"
        out["execution_followup_needed"] = bool(detail and len(detail) > 12)
        return out

    if not capability_ok:
        out["execution_outcome"] = "failed"
        err = (last_capability_ex or {}).get("error") if last_capability_ex else None
        out["execution_reason"] = str(err or detail or "capability_reported_failure")[:300]
        out["execution_followup_needed"] = bool(out["execution_reason"])
        return out

    p = normalize_payload(last_result)
    ev = _has_state_change_evidence(
        archetype=arch,
        payload=p,
        artifact_path=artifact_path,
        memory_written=memory_written,
        capability_ex=last_capability_ex,
    )
    hint = _has_downstream_action_hint(archetype=arch, payload=p, capability_ex=last_capability_ex)

    if arch == "execute_best_opportunity":
        if ev:
            out["execution_outcome"] = "succeeded"
            out["execution_reason"] = "verified_state_change_or_artifact_or_signal"
        else:
            out["execution_outcome"] = "partial"
            out["execution_reason"] = (
                "plan_or_stub_only_no_verified_state_change"
                if not hint
                else "weak_signal_no_artifact_or_state_flag"
            )
            out["execution_followup_needed"] = True
    elif "repair" in arch and "registry" in arch:
        if ev:
            out["execution_outcome"] = "succeeded"
            out["execution_reason"] = "registry_or_artifact_evidence"
        elif isinstance(p, dict) and (p.get("proposal") or p.get("patch")):
            out["execution_outcome"] = "partial"
            out["execution_reason"] = "patch_or_proposal_without_apply"
            out["execution_followup_needed"] = True
        else:
            out["execution_outcome"] = "failed"
            out["execution_reason"] = "no_op_or_error"
            out["execution_followup_needed"] = True
    elif "improvement" in arch:
        if ev:
            out["execution_outcome"] = "succeeded"
            out["execution_reason"] = "state_or_artifact_changed"
        elif isinstance(p, dict) and p.get("proposal"):
            out["execution_outcome"] = "partial"
            out["execution_reason"] = "proposal_only"
            out["execution_followup_needed"] = True
        else:
            out["execution_outcome"] = "failed"
            out["execution_reason"] = "no_improvement_evidence"
            out["execution_followup_needed"] = bool(execution_ready)
    else:
        if ev:
            out["execution_outcome"] = "succeeded"
            out["execution_reason"] = "evidence_of_state_or_artifact"
        elif hint:
            out["execution_outcome"] = "partial"
            out["execution_reason"] = "weak_downstream_signal"
            out["execution_followup_needed"] = True
        else:
            out["execution_outcome"] = "partial"
            out["execution_reason"] = "no_verified_state_change"
            out["execution_followup_needed"] = True

    if artifact_path is not None:
        out["execution_artifact"] = str(artifact_path)

    return out
