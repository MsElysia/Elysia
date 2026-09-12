"""Passive harmless live-action smoke approval packet generation.

Builds approval packet metadata for the future smoke write only.
Does not execute actions, call an executor, or create the smoke target file.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from project_guardian.live_action_approval_packet import (
    LiveActionApprovalPacket,
    build_live_action_approval_packet,
    serialize_live_action_approval_packet,
)
from project_guardian.live_action_audit import serialize_live_action_audit_record
from project_guardian.live_action_gate import (
    ActionRiskCategory,
    AllowlistDecision,
    build_approval_request,
)
from project_guardian.live_action_rollback import (
    LiveActionRollbackPlan,
    RollbackAvailability,
    RollbackStrategy,
    summarize_live_action_rollback_plan,
)
from project_guardian.live_action_readiness import evaluate_live_mode_readiness

HARMLESS_LIVE_SMOKE_ACTION_ID = "harmless_live_smoke_v1"
HARMLESS_LIVE_SMOKE_ACTION_KIND = "harmless_live_smoke"
HARMLESS_LIVE_SMOKE_CONTENT = b"ELYSIA_APPROVED_LIVE_SMOKE\n"
HARMLESS_LIVE_SMOKE_CONTENT_MARKER = "ELYSIA_APPROVED_LIVE_SMOKE"
HARMLESS_LIVE_SMOKE_WORKSPACE_SUBDIR = "live_smoke_workspace"
HARMLESS_LIVE_SMOKE_TARGET_FILENAME = "approved_smoke.txt"
HARMLESS_LIVE_SMOKE_RELATIVE_TARGET = (
    f"{HARMLESS_LIVE_SMOKE_WORKSPACE_SUBDIR}/{HARMLESS_LIVE_SMOKE_TARGET_FILENAME}"
)

_USER_DATA_SEGMENTS = frozenset(
    {
        "documents",
        "downloads",
        "desktop",
        "my documents",
    }
)

_NETWORK_TARGET_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


class SmokePathValidationError(str, Enum):
    """Path validation failure codes for harmless smoke packet generation."""

    WORKSPACE_NOT_ABSOLUTE = "WORKSPACE_NOT_ABSOLUTE"
    WORKSPACE_IS_REPO_ROOT = "WORKSPACE_IS_REPO_ROOT"
    TARGET_OUTSIDE_WORKSPACE = "TARGET_OUTSIDE_WORKSPACE"
    PATH_TRAVERSAL = "PATH_TRAVERSAL"
    USER_DATA_PATH = "USER_DATA_PATH"
    EXTERNAL_STORAGE_PATH = "EXTERNAL_STORAGE_PATH"
    NETWORK_PATH = "NETWORK_PATH"
    UNSAFE_ABSOLUTE_TARGET = "UNSAFE_ABSOLUTE_TARGET"


@dataclass(frozen=True)
class SmokePathValidationResult:
    """Outcome of smoke workspace/target path validation."""

    valid: bool
    reasons: Tuple[str, ...]
    resolved_workspace: str
    resolved_target: str


@dataclass(frozen=True)
class HarmlessSmokePacketResult:
    """Passive harmless smoke packet build result (no execution)."""

    packet: LiveActionApprovalPacket
    workspace_root: str
    relative_target_path: str
    content_hash: str
    content_marker: str
    action_kind: str
    audit_preview: Dict[str, Any]
    rollback_summary: Dict[str, Any]
    path_validation: SmokePathValidationResult


def compute_harmless_smoke_content_hash() -> str:
    """Return SHA-256 hex digest of deterministic smoke content bytes."""
    return hashlib.sha256(HARMLESS_LIVE_SMOKE_CONTENT).hexdigest()


def _no_execution_fields() -> Dict[str, bool]:
    return {
        "execution_permitted": False,
        "executed": False,
        "executor_called": False,
    }


def _path_has_traversal(raw: str) -> bool:
    parts = Path(raw.replace("\\", "/")).parts
    return ".." in parts


def _path_has_user_data_segment(path: Path) -> bool:
    for part in path.parts:
        if part.lower() in _USER_DATA_SEGMENTS:
            return True
    return False


def _get_external_storage_dir() -> Optional[Path]:
    try:
        from project_guardian.external_storage import get_configured_external_data_dir

        return get_configured_external_data_dir()
    except Exception:
        return None


def _is_under_or_equal(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def validate_harmless_smoke_paths(
    workspace_root: Union[str, Path],
    *,
    relative_target: str = HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
    repo_root: Optional[Union[str, Path]] = None,
) -> SmokePathValidationResult:
    """Validate isolated smoke workspace and target path. Does not create files."""
    reasons: list[str] = []
    workspace = Path(workspace_root)

    if not workspace.is_absolute():
        reasons.append(SmokePathValidationError.WORKSPACE_NOT_ABSOLUTE.value)

    if _path_has_traversal(str(workspace_root)) or _path_has_traversal(relative_target):
        reasons.append(SmokePathValidationError.PATH_TRAVERSAL.value)

    if _NETWORK_TARGET_RE.match(str(relative_target).strip()):
        reasons.append(SmokePathValidationError.NETWORK_PATH.value)

    if Path(relative_target).is_absolute():
        reasons.append(SmokePathValidationError.UNSAFE_ABSOLUTE_TARGET.value)

    resolved_workspace = workspace.resolve()
    resolved_target = (resolved_workspace / relative_target).resolve()

    if repo_root is not None:
        resolved_repo = Path(repo_root).resolve()
        if resolved_workspace == resolved_repo:
            reasons.append(SmokePathValidationError.WORKSPACE_IS_REPO_ROOT.value)

    if not _is_under_or_equal(resolved_target, resolved_workspace):
        reasons.append(SmokePathValidationError.TARGET_OUTSIDE_WORKSPACE.value)

    if _path_has_user_data_segment(resolved_workspace) or _path_has_user_data_segment(
        resolved_target
    ):
        reasons.append(SmokePathValidationError.USER_DATA_PATH.value)

    external_dir = _get_external_storage_dir()
    if external_dir is not None:
        ext = external_dir.resolve()
        if _is_under_or_equal(resolved_workspace, ext) or _is_under_or_equal(
            resolved_target, ext
        ):
            reasons.append(SmokePathValidationError.EXTERNAL_STORAGE_PATH.value)

    return SmokePathValidationResult(
        valid=not reasons,
        reasons=tuple(reasons),
        resolved_workspace=str(resolved_workspace),
        resolved_target=str(resolved_target),
    )


def build_harmless_smoke_rollback_plan(
    *,
    action_id: str = HARMLESS_LIVE_SMOKE_ACTION_ID,
    relative_target: str = HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
    file_preexists: bool = False,
) -> LiveActionRollbackPlan:
    """Build passive rollback metadata for harmless smoke. Does not execute rollback."""
    strategy = (
        RollbackStrategy.FILE_RESTORE if file_preexists else RollbackStrategy.DELETE_CREATED_FILE
    )
    return LiveActionRollbackPlan(
        action_id=action_id,
        strategy=strategy,
        availability=RollbackAvailability.AVAILABLE,
        target=relative_target,
        backup_path=f"{relative_target}.baseline" if file_preexists else "",
        notes="Passive smoke rollback metadata only; not executed",
    )


def build_harmless_smoke_approval_packet(
    workspace_root: Union[str, Path],
    *,
    repo_root: Optional[Union[str, Path]] = None,
    relative_target: str = HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
    file_preexists: bool = False,
) -> HarmlessSmokePacketResult:
    """Build passive harmless smoke approval packet. Does not write smoke file."""
    path_validation = validate_harmless_smoke_paths(
        workspace_root,
        relative_target=relative_target,
        repo_root=repo_root,
    )
    if not path_validation.valid:
        raise ValueError(
            f"Invalid harmless smoke paths: {', '.join(path_validation.reasons)}"
        )

    content_hash = compute_harmless_smoke_content_hash()
    rollback_plan = build_harmless_smoke_rollback_plan(
        relative_target=relative_target,
        file_preexists=file_preexists,
    )
    request = build_approval_request(
        action_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
        proposed_action=f"{HARMLESS_LIVE_SMOKE_ACTION_KIND}/write_marker",
        reason="harmless live-action smoke approval packet",
        risk_category=ActionRiskCategory.LOCAL_FILE_WRITE,
        target=relative_target,
        expected_result=content_hash,
        rollback_plan=json_plan_notes(rollback_plan),
        touches_autonomy_or_live_execution=False,
        writes_files=True,
        touches_network_api_or_browser=False,
    )
    packet = build_live_action_approval_packet(
        request,
        rollback_plan,
        mode="harmless_live_smoke_packet",
    )

    audit_preview = serialize_live_action_audit_record(packet.audit_record)
    rollback_summary = summarize_live_action_rollback_plan(rollback_plan)

    return HarmlessSmokePacketResult(
        packet=packet,
        workspace_root=path_validation.resolved_workspace,
        relative_target_path=relative_target,
        content_hash=content_hash,
        content_marker=HARMLESS_LIVE_SMOKE_CONTENT_MARKER,
        action_kind=HARMLESS_LIVE_SMOKE_ACTION_KIND,
        audit_preview=audit_preview,
        rollback_summary=rollback_summary,
        path_validation=path_validation,
    )


def json_plan_notes(plan: LiveActionRollbackPlan) -> str:
    """Compact rollback plan label for approval request field."""
    return (
        f"{plan.strategy.value}:{plan.availability.value}:"
        f"{plan.target or HARMLESS_LIVE_SMOKE_RELATIVE_TARGET}"
    )


def serialize_harmless_smoke_packet_response(
    result: HarmlessSmokePacketResult,
    *,
    dry_run_trace_id: str = "",
) -> Dict[str, Any]:
    """Return JSON-safe passive smoke packet response. No execution implied."""
    serialized_packet = serialize_live_action_approval_packet(result.packet)
    return {
        "action_id": HARMLESS_LIVE_SMOKE_ACTION_ID,
        "action_kind": result.action_kind,
        "action_category": ActionRiskCategory.LOCAL_FILE_WRITE.value,
        "workspace_root": result.workspace_root,
        "relative_target_path": result.relative_target_path,
        "proposed_content": HARMLESS_LIVE_SMOKE_CONTENT_MARKER,
        "proposed_content_bytes_preview": HARMLESS_LIVE_SMOKE_CONTENT.decode("utf-8"),
        "content_hash": result.content_hash,
        "allowlist_decision": AllowlistDecision.REQUIRE_APPROVAL.value,
        "packet": serialized_packet,
        "audit_preview": result.audit_preview,
        "rollback_summary": result.rollback_summary,
        "dry_run_trace_id": dry_run_trace_id,
        "path_validation": {
            "valid": result.path_validation.valid,
            "reasons": list(result.path_validation.reasons),
            "resolved_workspace": result.path_validation.resolved_workspace,
            "resolved_target": result.path_validation.resolved_target,
        },
        "ready_for_operator_review": result.packet.ready_for_operator_review,
        "safety_verdict": result.packet.safety_verdict,
        "readiness_blocked": not evaluate_live_mode_readiness().ready_for_limited_live_mode,
        **_no_execution_fields(),
    }
