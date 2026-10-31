# project_guardian/self_task_execution_outcome.py
# Post-execution verification: distinguish ready vs attempted vs succeeded.

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

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


def execution_verified(exec_result: Optional[Dict[str, Any]]) -> bool:
    """True only when independent evidence marked the execution verified."""
    result = exec_result or {}
    return (
        str(result.get("verification_status") or "") == "verified"
        and str(result.get("execution_outcome") or "") == "succeeded"
    )


def caller_execution_success(
    archetype: str,
    ok_any: bool,
    useful_any: bool,
    exec_result: Optional[Dict[str, Any]],
) -> Tuple[bool, bool]:
    """Planning may finish on its own. Execution success requires verification."""
    result = exec_result or {}
    if not is_execution_stage_archetype(archetype):
        return bool(ok_any), bool(useful_any)
    if str(result.get("execution_outcome") or "") == "readiness_only":
        return bool(ok_any), bool(useful_any)
    verified = execution_verified(result)
    return verified, bool(useful_any) if verified else False


def host_effect_root(queue_path: Path) -> Optional[Path]:
    """Directory the runner observes. Task payloads cannot choose this path."""
    parent = Path(queue_path).parent
    if _linked(parent):
        return None
    try:
        parent.resolve()
    except OSError:
        return None
    return parent / "self_task_host_effects"


def capture_host_directory_state(root: Optional[Path]) -> Dict[str, Any]:
    """Digest of regular files under root. Links are not followed."""
    records: List[Dict[str, Any]] = []
    if isinstance(root, Path) and not _linked(root):
        try:
            base = root.resolve()
        except OSError:
            base = None
        if base is not None and base.is_dir() and not _linked(base):
            for path in sorted(base.rglob("*")):
                if len(records) >= 64:
                    break
                if _linked(path) or not path.is_file():
                    continue
                try:
                    resolved = path.resolve()
                    relative = resolved.relative_to(base).as_posix()
                    data = resolved.read_bytes()
                except (OSError, ValueError):
                    continue
                if len(data) > _MAX_ARTIFACT_BYTES:
                    digest = ""
                else:
                    digest = hashlib.sha256(data).hexdigest()
                records.append({"path": relative, "size": len(data), "sha256": digest})
    encoded = _canonical(records).encode("ascii")
    return {
        "file_count": len(records),
        "root_digest": hashlib.sha256(encoded).hexdigest(),
    }


_ATTEMPT_ID = re.compile(r"^[0-9a-f]{32}$")
_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")
_CAPABILITY_ID = re.compile(r"^(module|tool):[A-Za-z0-9_]{1,64}$")
_RECEIPT_KEYS = frozenset({"task_id", "attempt_id", "capability_id", "effect_sha256"})
SYNTHETIC_LOCAL_NOTE = "tool:synthetic_local_note"


def authorize_task_capability(task: Dict[str, Any], kind: str, name: str) -> bool:
    """True when this task's own capability list names the exact kind and name."""
    ident = f"{(kind or '').strip().lower()}:{(name or '').strip()}"
    if _CAPABILITY_ID.fullmatch(ident) is None:
        return False
    allowed = task.get("recommended_capabilities") if isinstance(task, dict) else None
    if not isinstance(allowed, list):
        return False
    return ident in {str(item).strip() for item in allowed}


def _sanitize_note(note: str) -> str:
    text = " ".join(str(note or "").split())[:200]
    return text or "local-note"


def begin_task_attempt(task_id: str, capability_id: str, *, note: str) -> Dict[str, Any]:
    """Host-issued attempt. The model does not choose these fields."""
    if _TASK_ID.fullmatch(str(task_id or "")) is None:
        raise ValueError("task_id")
    if _CAPABILITY_ID.fullmatch(str(capability_id or "")) is None:
        raise ValueError("capability_id")
    return {
        "task_id": str(task_id),
        "attempt_id": uuid.uuid4().hex,
        "capability_id": str(capability_id),
        "effect_token": secrets.token_hex(16),
        "expected_note": _sanitize_note(note),
        "consumed": False,
        "preexisting": {"effect.txt": False, "receipt.json": False},
    }


def expected_effect_bytes(attempt: Dict[str, Any]) -> bytes:
    note = str(attempt.get("expected_note") or "")
    token = str(attempt.get("effect_token") or "")
    return f"{note}\n{token}\n".encode("utf-8")


def attempt_effect_dir(root: Optional[Path], attempt: Dict[str, Any]) -> Optional[Path]:
    if not isinstance(root, Path) or not isinstance(attempt, dict):
        return None
    task_id = str(attempt.get("task_id") or "")
    attempt_id = str(attempt.get("attempt_id") or "")
    if _TASK_ID.fullmatch(task_id) is None or _ATTEMPT_ID.fullmatch(attempt_id) is None:
        return None
    if _linked(root):
        return None
    try:
        base = root.resolve()
    except OSError:
        return None
    dest = base / task_id / attempt_id
    try:
        if dest.exists() or dest.parent.exists():
            dest.resolve().relative_to(base)
    except (OSError, ValueError):
        return None
    return dest


def _regular_file(path: Path) -> bool:
    if _linked(path):
        return False
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return resolved.is_file() and not _linked(resolved)


def prepare_task_attempt_dir(root: Optional[Path], attempt: Dict[str, Any]) -> Optional[Path]:
    dest = attempt_effect_dir(root, attempt)
    if dest is None:
        return None
    dest.mkdir(parents=True, exist_ok=True)
    try:
        dest.resolve().relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return None
    attempt["preexisting"] = {
        "effect.txt": _regular_file(dest / "effect.txt"),
        "receipt.json": _regular_file(dest / "receipt.json"),
    }
    attempt["consumed"] = False
    return dest


def write_authorized_local_note(effect_dir: Path, attempt: Dict[str, Any]) -> None:
    """Write the host note. The caller must already have authorized this attempt."""
    body = expected_effect_bytes(attempt)
    digest = hashlib.sha256(body).hexdigest()
    receipt = {
        "attempt_id": attempt["attempt_id"],
        "capability_id": attempt["capability_id"],
        "effect_sha256": digest,
        "task_id": attempt["task_id"],
    }
    (effect_dir / "effect.txt").write_bytes(body)
    (effect_dir / "receipt.json").write_text(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def attribute_attempt_receipt(root: Optional[Path], attempt: Dict[str, Any]) -> Dict[str, Any]:
    """Re-read the attempt directory. Model fields are not consulted."""
    if not isinstance(attempt, dict):
        return {"attributed": False, "reason": "malformed_receipt"}
    if attempt.get("consumed"):
        return {"attributed": False, "reason": "replayed_receipt"}
    preexisting = attempt.get("preexisting") if isinstance(attempt.get("preexisting"), dict) else {}
    if preexisting.get("effect.txt") or preexisting.get("receipt.json"):
        return {"attributed": False, "reason": "stale_receipt"}
    dest = attempt_effect_dir(root, attempt)
    if dest is None:
        return {"attributed": False, "reason": "malformed_receipt"}
    effect_path = dest / "effect.txt"
    receipt_path = dest / "receipt.json"
    if not _regular_file(effect_path) or not _regular_file(receipt_path):
        return {"attributed": False, "reason": "missing_effect"}
    try:
        data = effect_path.read_bytes()
        parsed = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"attributed": False, "reason": "malformed_receipt"}
    if len(data) > 10000 or not isinstance(parsed, dict) or set(parsed) != _RECEIPT_KEYS:
        return {"attributed": False, "reason": "malformed_receipt"}
    if parsed.get("task_id") != attempt.get("task_id"):
        return {"attributed": False, "reason": "mismatched_task"}
    if parsed.get("attempt_id") != attempt.get("attempt_id"):
        return {"attributed": False, "reason": "replayed_receipt"}
    if parsed.get("capability_id") != attempt.get("capability_id"):
        return {"attributed": False, "reason": "mismatched_capability"}
    if data != expected_effect_bytes(attempt):
        return {"attributed": False, "reason": "forged_receipt"}
    digest = hashlib.sha256(data).hexdigest()
    if parsed.get("effect_sha256") != digest:
        return {"attributed": False, "reason": "forged_receipt"}
    attempt["consumed"] = True
    attempt["effect_sha256"] = digest
    return {"attributed": True, "reason": "task_attributed_host_receipt"}


def audit_attempt_receipt(root: Optional[Path], attempt: Dict[str, Any]) -> Dict[str, Any]:
    """Re-check a receipt that was already accepted. A later edit is not success."""
    if not isinstance(attempt, dict) or not attempt.get("effect_sha256"):
        return {"attributed": False, "reason": "missing_effect"}
    dest = attempt_effect_dir(root, attempt)
    if dest is None:
        return {"attributed": False, "reason": "malformed_receipt"}
    effect_path = dest / "effect.txt"
    if not _regular_file(effect_path):
        return {"attributed": False, "reason": "modified_evidence"}
    try:
        data = effect_path.read_bytes()
    except OSError:
        return {"attributed": False, "reason": "modified_evidence"}
    digest = hashlib.sha256(data).hexdigest()
    if data != expected_effect_bytes(attempt) or digest != attempt.get("effect_sha256"):
        return {"attributed": False, "reason": "modified_evidence"}
    return {"attributed": True, "reason": "task_attributed_host_receipt"}


def first_attributed_attempt(
    root: Optional[Path], attempts: Optional[Sequence[Dict[str, Any]]]
) -> Dict[str, Any]:
    last = {"attributed": False, "reason": "missing_effect"}
    for attempt in attempts or ():
        last = attribute_attempt_receipt(root, attempt)
        if last.get("attributed"):
            return last
    return last


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
    effect_root: Optional[Path] = None,
    host_attempts: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Existing outcome fields plus verification_status:
    proposed, attempted, partial, verified, failed, blocked.

    succeeded is only the verified status. A shared-directory change, a
    self-reported flag, a dry run, or a receipt that does not match the
    host attempt cannot produce it. observed_before and observed_after are
    ignored as proof.
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
    receipt = {"attributed": False, "reason": ""}
    if not dry_run and host_attempts:
        receipt = first_attributed_attempt(effect_root, host_attempts)
    receipt_proof = bool(receipt.get("attributed") and receipt.get("reason") == "task_attributed_host_receipt")
    _ = (observed_before, observed_after)
    proof = file_proof or receipt_proof
    hint = _has_downstream_action_hint(archetype=arch, payload=p, capability_ex=last_capability_ex)
    reported = _self_reported(p, last_capability_ex, memory_written)

    if proof:
        out["execution_outcome"] = "succeeded"
        out["verification_status"] = "verified"
        out["execution_reason"] = (
            "independent_file_integrity" if file_proof else "task_attributed_host_receipt"
        )
        out["execution_followup_needed"] = False
    elif dry_run:
        out["execution_outcome"] = "partial"
        out["verification_status"] = "partial"
        out["execution_reason"] = "dry_run_not_production_action"
        out["execution_followup_needed"] = True
    elif host_attempts and receipt.get("reason"):
        out["execution_outcome"] = "partial"
        out["verification_status"] = "partial"
        out["execution_reason"] = str(receipt.get("reason"))[:300]
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
