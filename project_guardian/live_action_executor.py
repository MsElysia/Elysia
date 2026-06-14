"""Live action executor — disabled by default; harmless smoke write when enabled.

Supports only the harmless smoke single-file write inside an isolated workspace.
Does not use shell, network, browser, API, or mutation paths.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from project_guardian.live_action_smoke_packet import (
    HARMLESS_LIVE_SMOKE_ACTION_ID,
    HARMLESS_LIVE_SMOKE_ACTION_KIND,
    HARMLESS_LIVE_SMOKE_CONTENT,
    HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
    compute_harmless_smoke_content_hash,
    validate_harmless_smoke_paths,
)

_EXECUTOR_ENABLED_TRUTHY = frozenset({"1", "true", "yes", "on"})
_HARMLESS_SMOKE_CATEGORIES = frozenset({"harmless_live_smoke"})


class LiveExecutorFailureCode(str, Enum):
    """Executor failure codes."""

    EXECUTOR_DISABLED = "EXECUTOR_DISABLED"
    APPROVAL_MISSING = "APPROVAL_MISSING"
    OPERATOR_DECISION_NOT_APPROVED = "OPERATOR_DECISION_NOT_APPROVED"
    ACTION_NOT_ALLOWLISTED = "ACTION_NOT_ALLOWLISTED"
    TARGET_OUTSIDE_SMOKE_WORKSPACE = "TARGET_OUTSIDE_SMOKE_WORKSPACE"
    CONTENT_HASH_MISMATCH = "CONTENT_HASH_MISMATCH"
    PACKET_EXPIRED = "PACKET_EXPIRED"
    ROLLBACK_PLAN_MISSING = "ROLLBACK_PLAN_MISSING"
    AUDIT_MISSING = "AUDIT_MISSING"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"
    ROLLBACK_SUCCEEDED = "ROLLBACK_SUCCEEDED"


class LiveExecutorStatus(str, Enum):
    """Executor result status values."""

    EXECUTOR_DISABLED = "EXECUTOR_DISABLED"
    EXECUTION_DENIED = "EXECUTION_DENIED"
    EXECUTION_SUCCEEDED = "EXECUTION_SUCCEEDED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    ROLLBACK_SUCCEEDED = "ROLLBACK_SUCCEEDED"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"


def is_live_executor_enabled() -> bool:
    """Return True only when ``ELYSIA_LIVE_EXECUTOR_ENABLED`` is explicitly truthy."""
    raw = os.environ.get("ELYSIA_LIVE_EXECUTOR_ENABLED", "").strip().lower()
    return raw in _EXECUTOR_ENABLED_TRUTHY


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc_iso(value: str) -> Optional[datetime]:
    if not value or not str(value).strip():
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _is_expired(expires_at: str) -> bool:
    parsed = _parse_utc_iso(expires_at)
    if parsed is None:
        return False
    return datetime.now(timezone.utc) >= parsed


def _file_sha256(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class LiveActionExecutionRequest:
    """Inputs for a live action execution attempt."""

    approval_packet_id: str = ""
    operator_decision_id: str = ""
    operator_decision: str = ""
    action_id: str = ""
    action_category: str = ""
    target_path: str = ""
    workspace_root: str = ""
    expected_content_hash: str = ""
    rollback_plan_id: str = ""
    audit_record_id: str = ""
    dry_run_trace_id: str = ""
    expires_at: str = ""
    repo_root: str = ""


@dataclass(frozen=True)
class LiveActionExecutionResult:
    """Execution result for a live action attempt."""

    status: str
    action_id: str
    action_category: str
    approval_packet_id: str
    operator_decision_id: str
    target_path: str
    workspace_root: str
    before_hash: Optional[str]
    after_hash: Optional[str]
    rollback_plan_id: str
    audit_record_id: str
    dry_run_trace_id: str
    executed_at: str
    executed: bool
    dry_run: bool
    execution_permitted: bool
    executor_called: bool
    safety_verdict: str
    failure_code: Optional[str]
    detail: Optional[str]
    rollback_summary: Optional[Dict[str, Any]] = None


def _base_result_fields(request: LiveActionExecutionRequest) -> Dict[str, Any]:
    return {
        "action_id": request.action_id or HARMLESS_LIVE_SMOKE_ACTION_ID,
        "action_category": request.action_category or HARMLESS_LIVE_SMOKE_ACTION_KIND,
        "approval_packet_id": request.approval_packet_id,
        "operator_decision_id": request.operator_decision_id,
        "target_path": request.target_path,
        "workspace_root": request.workspace_root,
        "rollback_plan_id": request.rollback_plan_id,
        "audit_record_id": request.audit_record_id,
        "dry_run_trace_id": request.dry_run_trace_id,
        "executed_at": _utc_now_iso(),
        "executor_called": True,
    }


def _disabled_result(request: LiveActionExecutionRequest) -> LiveActionExecutionResult:
    base = _base_result_fields(request)
    return LiveActionExecutionResult(
        status=LiveExecutorStatus.EXECUTOR_DISABLED.value,
        before_hash=None,
        after_hash=None,
        executed=False,
        dry_run=True,
        execution_permitted=False,
        safety_verdict="EXECUTOR_DISABLED",
        failure_code=LiveExecutorFailureCode.EXECUTOR_DISABLED.value,
        detail="Live executor is disabled by default",
        **base,
    )


def _denied_result(
    request: LiveActionExecutionRequest,
    *,
    failure_code: LiveExecutorFailureCode,
    detail: str,
) -> LiveActionExecutionResult:
    base = _base_result_fields(request)
    return LiveActionExecutionResult(
        status=LiveExecutorStatus.EXECUTION_DENIED.value,
        before_hash=None,
        after_hash=None,
        executed=False,
        dry_run=True,
        execution_permitted=False,
        safety_verdict="EXECUTION_DENIED",
        failure_code=failure_code.value,
        detail=detail,
        **base,
    )


def _validate_enabled_request(
    request: LiveActionExecutionRequest,
) -> Optional[Tuple[LiveExecutorFailureCode, str]]:
    if not request.approval_packet_id.strip():
        return LiveExecutorFailureCode.APPROVAL_MISSING, "approval_packet_id is required"
    if not request.operator_decision_id.strip():
        return (
            LiveExecutorFailureCode.OPERATOR_DECISION_NOT_APPROVED,
            "operator_decision_id is required",
        )
    if str(request.operator_decision).strip().upper() != "APPROVE":
        return (
            LiveExecutorFailureCode.OPERATOR_DECISION_NOT_APPROVED,
            "operator decision must be APPROVE",
        )
    if request.action_id != HARMLESS_LIVE_SMOKE_ACTION_ID:
        return LiveExecutorFailureCode.ACTION_NOT_ALLOWLISTED, "action_id not allowlisted"
    if request.action_category not in _HARMLESS_SMOKE_CATEGORIES:
        return (
            LiveExecutorFailureCode.ACTION_NOT_ALLOWLISTED,
            "action_category must be harmless_live_smoke",
        )
    if request.target_path != HARMLESS_LIVE_SMOKE_RELATIVE_TARGET:
        return (
            LiveExecutorFailureCode.TARGET_OUTSIDE_SMOKE_WORKSPACE,
            "target_path must be harmless smoke relative target",
        )
    expected = compute_harmless_smoke_content_hash()
    if request.expected_content_hash != expected:
        return LiveExecutorFailureCode.CONTENT_HASH_MISMATCH, "expected_content_hash mismatch"
    if not request.rollback_plan_id.strip():
        return LiveExecutorFailureCode.ROLLBACK_PLAN_MISSING, "rollback_plan_id is required"
    if not request.audit_record_id.strip():
        return LiveExecutorFailureCode.AUDIT_MISSING, "audit_record_id is required"
    if _is_expired(request.expires_at):
        return LiveExecutorFailureCode.PACKET_EXPIRED, "approval packet expired"
    if not request.workspace_root.strip():
        return (
            LiveExecutorFailureCode.TARGET_OUTSIDE_SMOKE_WORKSPACE,
            "workspace_root is required",
        )

    repo_root = request.repo_root or None
    path_validation = validate_harmless_smoke_paths(
        request.workspace_root,
        relative_target=request.target_path,
        repo_root=repo_root,
    )
    if not path_validation.valid:
        return (
            LiveExecutorFailureCode.TARGET_OUTSIDE_SMOKE_WORKSPACE,
            f"unsafe path: {', '.join(path_validation.reasons)}",
        )
    return None


def _resolved_target(request: LiveActionExecutionRequest) -> Path:
    workspace = Path(request.workspace_root).resolve()
    return (workspace / request.target_path).resolve()


def execute_live_action(
    request: LiveActionExecutionRequest,
) -> LiveActionExecutionResult:
    """Execute harmless smoke write when enabled and fully validated."""
    if not is_live_executor_enabled():
        return _disabled_result(request)

    validation_error = _validate_enabled_request(request)
    if validation_error is not None:
        code, detail = validation_error
        return _denied_result(request, failure_code=code, detail=detail)

    target = _resolved_target(request)
    before_hash = _file_sha256(target)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(HARMLESS_LIVE_SMOKE_CONTENT)
    except OSError as exc:
        base = _base_result_fields(request)
        return LiveActionExecutionResult(
            status=LiveExecutorStatus.EXECUTION_FAILED.value,
            before_hash=before_hash,
            after_hash=None,
            executed=False,
            dry_run=False,
            execution_permitted=False,
            safety_verdict="EXECUTION_FAILED",
            failure_code=LiveExecutorFailureCode.EXECUTION_FAILED.value,
            detail=str(exc),
            rollback_summary={
                "strategy": "DELETE_CREATED_FILE",
                "availability": "AVAILABLE",
                "target": request.target_path,
            },
            **base,
        )

    after_hash = _file_sha256(target)
    base = _base_result_fields(request)
    return LiveActionExecutionResult(
        status=LiveExecutorStatus.EXECUTION_SUCCEEDED.value,
        before_hash=before_hash,
        after_hash=after_hash,
        executed=True,
        dry_run=False,
        execution_permitted=True,
        safety_verdict="EXECUTION_SUCCEEDED",
        failure_code=None,
        detail=None,
        rollback_summary={
            "strategy": "DELETE_CREATED_FILE" if before_hash is None else "FILE_RESTORE",
            "availability": "AVAILABLE",
            "target": request.target_path,
            "backup_path": f"{request.target_path}.baseline" if before_hash else "",
        },
        **base,
    )


def rollback_harmless_smoke_write(
    *,
    workspace_root: str = "",
    target_path: str = HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
    rollback_plan_id: str = "",
    repo_root: str = "",
    prior_content: Optional[bytes] = None,
) -> LiveActionExecutionResult:
    """Rollback harmless smoke write: delete created file or restore prior content."""
    request = LiveActionExecutionRequest(
        workspace_root=workspace_root,
        target_path=target_path,
        rollback_plan_id=rollback_plan_id or HARMLESS_LIVE_SMOKE_ACTION_ID,
        action_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
        action_category=HARMLESS_LIVE_SMOKE_ACTION_KIND,
        repo_root=repo_root,
    )
    if not is_live_executor_enabled():
        return _disabled_result(request)

    if target_path != HARMLESS_LIVE_SMOKE_RELATIVE_TARGET:
        return _denied_result(
            request,
            failure_code=LiveExecutorFailureCode.TARGET_OUTSIDE_SMOKE_WORKSPACE,
            detail="rollback target must be harmless smoke relative target",
        )

    path_validation = validate_harmless_smoke_paths(
        workspace_root,
        relative_target=target_path,
        repo_root=repo_root or None,
    )
    if not path_validation.valid:
        return _denied_result(
            request,
            failure_code=LiveExecutorFailureCode.TARGET_OUTSIDE_SMOKE_WORKSPACE,
            detail=f"unsafe rollback path: {', '.join(path_validation.reasons)}",
        )

    target = Path(path_validation.resolved_target)
    before_hash = _file_sha256(target)

    try:
        if prior_content is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(prior_content)
        elif target.is_file():
            target.unlink()
        after_hash = _file_sha256(target)
    except OSError as exc:
        base = _base_result_fields(request)
        return LiveActionExecutionResult(
            status=LiveExecutorStatus.ROLLBACK_FAILED.value,
            before_hash=before_hash,
            after_hash=_file_sha256(target),
            executed=False,
            dry_run=False,
            execution_permitted=False,
            safety_verdict="ROLLBACK_FAILED",
            failure_code=LiveExecutorFailureCode.ROLLBACK_FAILED.value,
            detail=str(exc),
            **base,
        )

    base = _base_result_fields(request)
    return LiveActionExecutionResult(
        status=LiveExecutorStatus.ROLLBACK_SUCCEEDED.value,
        before_hash=before_hash,
        after_hash=after_hash,
        executed=False,
        dry_run=False,
        execution_permitted=False,
        safety_verdict="ROLLBACK_SUCCEEDED",
        failure_code=LiveExecutorFailureCode.ROLLBACK_SUCCEEDED.value,
        detail=None,
        rollback_summary={
            "strategy": "FILE_RESTORE" if prior_content is not None else "DELETE_CREATED_FILE",
            "availability": "AVAILABLE",
            "target": target_path,
        },
        **base,
    )


def serialize_live_action_execution_result(
    result: LiveActionExecutionResult,
) -> Dict[str, Any]:
    """Return a JSON-safe plain dict for an execution result."""
    payload: Dict[str, Any] = {
        "status": result.status,
        "action_id": result.action_id,
        "action_category": result.action_category,
        "approval_packet_id": result.approval_packet_id,
        "operator_decision_id": result.operator_decision_id,
        "target_path": result.target_path,
        "workspace_root": result.workspace_root,
        "before_hash": result.before_hash,
        "after_hash": result.after_hash,
        "rollback_plan_id": result.rollback_plan_id,
        "audit_record_id": result.audit_record_id,
        "dry_run_trace_id": result.dry_run_trace_id,
        "executed_at": result.executed_at,
        "executed": result.executed,
        "dry_run": result.dry_run,
        "execution_permitted": result.execution_permitted,
        "executor_called": result.executor_called,
        "safety_verdict": result.safety_verdict,
        "failure_code": result.failure_code,
        "detail": result.detail,
    }
    if result.rollback_summary is not None:
        payload["rollback_summary"] = result.rollback_summary
    return payload


def serialize_live_action_execution_result_json(
    result: LiveActionExecutionResult,
) -> str:
    """Return JSON string for an execution result."""
    return json.dumps(serialize_live_action_execution_result(result), ensure_ascii=False)
