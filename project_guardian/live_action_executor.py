"""Disabled-by-default live action executor scaffold.

Defines the executor entry point and result schema only.
Does not write files, execute rollback, or perform live actions.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from project_guardian.live_action_smoke_packet import HARMLESS_LIVE_SMOKE_ACTION_ID


class LiveExecutorFailureCode(str, Enum):
    """Executor failure codes (passive labels; scaffold denies all execution)."""

    EXECUTOR_DISABLED = "EXECUTOR_DISABLED"
    EXECUTION_NOT_IMPLEMENTED = "EXECUTION_NOT_IMPLEMENTED"


class LiveExecutorStatus(str, Enum):
    """Executor result status values."""

    EXECUTOR_DISABLED = "EXECUTOR_DISABLED"
    EXECUTION_DENIED = "EXECUTION_DENIED"


_EXECUTOR_ENABLED_TRUTHY = frozenset({"1", "true", "yes", "on"})


def is_live_executor_enabled() -> bool:
    """Return True only when ``ELYSIA_LIVE_EXECUTOR_ENABLED`` is explicitly truthy."""
    raw = os.environ.get("ELYSIA_LIVE_EXECUTOR_ENABLED", "").strip().lower()
    return raw in _EXECUTOR_ENABLED_TRUTHY


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LiveActionExecutionRequest:
    """Inputs for a live action execution attempt."""

    approval_packet_id: str = ""
    operator_decision_id: str = ""
    action_id: str = ""
    action_category: str = ""
    target_path: str = ""
    workspace_root: str = ""
    expected_content_hash: str = ""
    rollback_plan_id: str = ""
    audit_record_id: str = ""
    dry_run_trace_id: str = ""


@dataclass(frozen=True)
class LiveActionExecutionResult:
    """Passive execution result. Scaffold always denies with zero side effects."""

    status: str
    action_id: str
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


def _disabled_result(request: LiveActionExecutionRequest) -> LiveActionExecutionResult:
    return LiveActionExecutionResult(
        status=LiveExecutorStatus.EXECUTOR_DISABLED.value,
        action_id=request.action_id or HARMLESS_LIVE_SMOKE_ACTION_ID,
        approval_packet_id=request.approval_packet_id,
        operator_decision_id=request.operator_decision_id,
        target_path=request.target_path,
        workspace_root=request.workspace_root,
        before_hash=None,
        after_hash=None,
        rollback_plan_id=request.rollback_plan_id,
        audit_record_id=request.audit_record_id,
        dry_run_trace_id=request.dry_run_trace_id,
        executed_at=_utc_now_iso(),
        executed=False,
        dry_run=True,
        execution_permitted=False,
        executor_called=True,
        safety_verdict="EXECUTOR_DISABLED",
        failure_code=LiveExecutorFailureCode.EXECUTOR_DISABLED.value,
        detail="Live executor is disabled by default",
    )


def _not_implemented_result(request: LiveActionExecutionRequest) -> LiveActionExecutionResult:
    """Enabled flag set but execution path not implemented in this milestone."""
    return LiveActionExecutionResult(
        status=LiveExecutorStatus.EXECUTION_DENIED.value,
        action_id=request.action_id or HARMLESS_LIVE_SMOKE_ACTION_ID,
        approval_packet_id=request.approval_packet_id,
        operator_decision_id=request.operator_decision_id,
        target_path=request.target_path,
        workspace_root=request.workspace_root,
        before_hash=None,
        after_hash=None,
        rollback_plan_id=request.rollback_plan_id,
        audit_record_id=request.audit_record_id,
        dry_run_trace_id=request.dry_run_trace_id,
        executed_at=_utc_now_iso(),
        executed=False,
        dry_run=True,
        execution_permitted=False,
        executor_called=True,
        safety_verdict="EXECUTION_DENIED",
        failure_code=LiveExecutorFailureCode.EXECUTION_NOT_IMPLEMENTED.value,
        detail="Enabled execution path is not implemented in this scaffold milestone",
    )


def execute_live_action(
    request: LiveActionExecutionRequest,
) -> LiveActionExecutionResult:
    """Attempt live action execution. Scaffold refuses all execution with no side effects."""
    if not is_live_executor_enabled():
        return _disabled_result(request)
    return _not_implemented_result(request)


def rollback_harmless_smoke_write(
    *,
    workspace_root: str = "",
    target_path: str = "",
    rollback_plan_id: str = "",
) -> LiveActionExecutionResult:
    """Rollback scaffold stub. Does not modify filesystem."""
    request = LiveActionExecutionRequest(
        workspace_root=workspace_root,
        target_path=target_path,
        rollback_plan_id=rollback_plan_id,
        action_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
    )
    if not is_live_executor_enabled():
        return _disabled_result(request)
    return _not_implemented_result(request)


def serialize_live_action_execution_result(
    result: LiveActionExecutionResult,
) -> Dict[str, Any]:
    """Return a JSON-safe plain dict for an execution result."""
    return {
        "status": result.status,
        "action_id": result.action_id,
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


def serialize_live_action_execution_result_json(
    result: LiveActionExecutionResult,
) -> str:
    """Return JSON string for an execution result."""
    return json.dumps(serialize_live_action_execution_result(result), ensure_ascii=False)
