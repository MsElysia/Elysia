# project_guardian/self_task_execution_outcome.py
# Post-execution verification: distinguish ready vs attempted vs succeeded.

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

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


_SELF_REPORT_KEYS = (
    "state_changed",
    "applied",
    "files_written",
    "files_updated",
    "registry_updated",
    "patch_applied",
    "downstream_result",
    "external_result",
    "memory_written",
)
_FLAG_ONLY_KEYS = frozenset(
    {"state_changed", "applied", "success", "ok", "verified", "memory_written"}
)
_BLOCKED_MARKERS = (
    "authorization",
    "not authorized",
    "unauthor",
    "capability unavailable",
    "required capability",
)
_MAX_ARTIFACT_BYTES = 1_000_000


def _payload_dicts(payload: Any) -> list:
    rows = []
    if isinstance(payload, dict):
        rows.append(payload)
    normalized = normalize_payload(payload)
    if isinstance(normalized, dict) and normalized not in rows:
        rows.append(normalized)
    return rows


def _is_dry_run(payload: Any) -> bool:
    for item in _payload_dicts(payload):
        if item.get("dry_run") is True:
            return True
        result = item.get("dry_run_result")
        if result not in (None, False, "", [], {}):
            return True
    return False


def _self_reported(payload: Any, capability_ex: Optional[Dict[str, Any]], memory_written: bool) -> bool:
    if memory_written:
        return True
    for item in _payload_dicts(payload):
        for key in _SELF_REPORT_KEYS:
            value = item.get(key)
            if value and value not in (False, [], {}, ""):
                return True
        plan = item.get("execution_plan")
        if isinstance(plan, dict) and plan.get("state_changed"):
            return True
    if isinstance(capability_ex, dict):
        result = capability_ex.get("result")
        if isinstance(result, dict) and any(
            result.get(key) for key in ("state_changed", "applied", "registry_updated", "files_written")
        ):
            return True
    return False


def _default_artifact_roots() -> tuple:
    from .self_task_artifacts import CONTRACT_TO_SUBDIR, PROJECT_ROOT

    return tuple(PROJECT_ROOT.joinpath(*parts) for parts in CONTRACT_TO_SUBDIR.values())


def _linked(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def permitted_artifact_file(
    artifact_path: Optional[Path],
    allowed_roots: Optional[Sequence[Path]] = None,
) -> Optional[Path]:
    """Existing file inside an allowed root. A path object alone is not proof."""
    if not isinstance(artifact_path, Path) or _linked(artifact_path):
        return None
    try:
        resolved = artifact_path.resolve()
    except OSError:
        return None
    if _linked(resolved) or not resolved.is_file():
        return None
    roots = allowed_roots if allowed_roots is not None else _default_artifact_roots()
    for root in roots:
        base = Path(root)
        if _linked(base):
            continue
        try:
            root_resolved = base.resolve()
        except OSError:
            continue
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            continue
        return resolved
    return None


def _artifact_digest_matches(path: Path, payload: Any) -> bool:
    claimed = None
    for item in _payload_dicts(payload):
        value = item.get("artifact_sha256")
        if isinstance(value, str):
            claimed = value
            break
    if not isinstance(claimed, str) or re.fullmatch(r"[0-9a-f]{64}", claimed) is None:
        return False
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if not data or len(data) > _MAX_ARTIFACT_BYTES:
        return False
    return hashlib.sha256(data).hexdigest() == claimed


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _host_state_changed(before: Any, after: Any) -> bool:
    """Host snapshots only. Boolean success flags are not a state change."""
    if type(before) is not dict or type(after) is not dict or not before or not after:
        return False
    if set(before) <= _FLAG_ONLY_KEYS or set(after) <= _FLAG_ONLY_KEYS:
        return False
    if all(type(value) is bool for value in before.values()):
        return False
    if all(type(value) is bool for value in after.values()):
        return False
    try:
        return _canonical(before) != _canonical(after)
    except (TypeError, ValueError):
        return False


def _is_blocked(detail: str, capability_ex: Optional[Dict[str, Any]]) -> bool:
    parts = [detail or ""]
    if isinstance(capability_ex, dict) and capability_ex.get("error"):
        parts.append(str(capability_ex.get("error")))
    blob = " ".join(parts).lower()
    return any(marker in blob for marker in _BLOCKED_MARKERS)


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
        if p.get("downstream_result") and not _is_dry_run(p):
            return True
        if arch == "execute_best_opportunity":
            # Builtin revenue_executor often returns plan + summary only — not downstream.
            ig = p.get("opportunities") or p.get("income_snapshot_keys")
            if isinstance(ig, dict) and len(ig) > 0:
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
    allowed_roots: Optional[Sequence[Path]] = None,
    observed_before: Any = None,
    observed_after: Any = None,
) -> Dict[str, Any]:
    """
    Existing outcome fields plus verification_status:
    proposed, attempted, partial, verified, failed, blocked.

    succeeded is only the verified status. Self-reported flags, dry runs,
    memory-write booleans, and a path that was not independently checked
    cannot produce it.
    """
    arch = (archetype or "").lower()
    tier = (execution_tier or "").lower()
    out: Dict[str, Any] = {
        "execution_attempted": False,
        "execution_outcome": "none",
        "execution_reason": "not_execution_stage",
        "execution_artifact": None,
        "execution_followup_needed": False,
        "verification_status": "not_applicable",
    }

    if not is_execution_stage_archetype(arch):
        return out

    out["execution_reason"] = "evaluating"

    if arch in _READINESS_PLAN_ARCHETYPES or arch == "generate_execution_plan":
        out["execution_attempted"] = bool(capability_attempted and tier != "failed")
        out["execution_outcome"] = "readiness_only"
        out["verification_status"] = "proposed"
        out["execution_reason"] = (
            "generate_execution_plan is readiness support only; not an execution success"
        )
        out["execution_followup_needed"] = False
        return out

    out["execution_attempted"] = bool(capability_attempted and tier != "failed")

    if not capability_attempted or tier == "failed" or not capability_ok:
        blocked = _is_blocked(detail, last_capability_ex)
        out["execution_outcome"] = "failed"
        out["verification_status"] = "blocked" if blocked else "failed"
        if not capability_ok and capability_attempted and tier != "failed":
            err = (last_capability_ex or {}).get("error") if last_capability_ex else None
            out["execution_reason"] = str(err or detail or "capability_reported_failure")[:300]
            out["execution_followup_needed"] = bool(out["execution_reason"])
        else:
            out["execution_reason"] = detail[:300] if detail else "no_capability_attempt_or_task_failed"
            out["execution_followup_needed"] = bool(detail and len(detail) > 12)
        return out

    p = normalize_payload(last_result)
    located = permitted_artifact_file(artifact_path, allowed_roots)
    dry_run = _is_dry_run(p) or _is_dry_run(last_capability_ex)
    file_proof = bool(located is not None and not dry_run and _artifact_digest_matches(located, p))
    state_proof = bool(not dry_run and _host_state_changed(observed_before, observed_after))
    proof = file_proof or state_proof
    hint = _has_downstream_action_hint(archetype=arch, payload=p, capability_ex=last_capability_ex)
    reported = _self_reported(p, last_capability_ex, memory_written)

    if proof:
        out["execution_outcome"] = "succeeded"
        out["verification_status"] = "verified"
        out["execution_reason"] = (
            "independent_file_integrity" if file_proof else "independent_state_comparison"
        )
        out["execution_followup_needed"] = False
    elif dry_run:
        out["execution_outcome"] = "partial"
        out["verification_status"] = "partial"
        out["execution_reason"] = "dry_run_not_production_action"
        out["execution_followup_needed"] = True
    elif arch == "execute_best_opportunity":
        out["execution_outcome"] = "partial"
        out["verification_status"] = "partial" if (reported or located is not None or hint) else "attempted"
        out["execution_reason"] = _unproven_reason(reported, located, artifact_path, hint)
        out["execution_followup_needed"] = True
    elif "repair" in arch and "registry" in arch:
        if isinstance(p, dict) and (p.get("proposal") or p.get("patch")):
            out["execution_outcome"] = "partial"
            out["verification_status"] = "partial"
            out["execution_reason"] = "patch_or_proposal_without_apply"
            out["execution_followup_needed"] = True
        elif reported or located is not None or artifact_path is not None:
            out["execution_outcome"] = "partial"
            out["verification_status"] = "partial"
            out["execution_reason"] = _unproven_reason(reported, located, artifact_path, hint)
            out["execution_followup_needed"] = True
        else:
            out["execution_outcome"] = "failed"
            out["verification_status"] = "failed"
            out["execution_reason"] = "no_op_or_error"
            out["execution_followup_needed"] = True
    elif "improvement" in arch:
        if isinstance(p, dict) and p.get("proposal"):
            out["execution_outcome"] = "partial"
            out["verification_status"] = "partial"
            out["execution_reason"] = "proposal_only"
            out["execution_followup_needed"] = True
        elif reported or located is not None or artifact_path is not None:
            out["execution_outcome"] = "partial"
            out["verification_status"] = "partial"
            out["execution_reason"] = _unproven_reason(reported, located, artifact_path, hint)
            out["execution_followup_needed"] = True
        else:
            out["execution_outcome"] = "failed"
            out["verification_status"] = "failed"
            out["execution_reason"] = "no_improvement_evidence"
            out["execution_followup_needed"] = bool(execution_ready)
    else:
        out["execution_outcome"] = "partial"
        out["verification_status"] = "partial" if (reported or located is not None or hint) else "attempted"
        out["execution_reason"] = _unproven_reason(reported, located, artifact_path, hint)
        out["execution_followup_needed"] = True

    if located is not None:
        out["execution_artifact"] = str(located)
    return out


def _unproven_reason(reported: bool, located: Optional[Path], artifact_path: Optional[Path], hint: bool) -> str:
    if artifact_path is not None and located is None:
        return "artifact_missing_or_unpermitted"
    if reported:
        return "self_reported_state_without_corroboration"
    if hint:
        return "weak_signal_no_artifact_or_state_flag"
    return "plan_or_stub_only_no_verified_state_change"
