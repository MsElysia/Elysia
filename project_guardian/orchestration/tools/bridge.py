# project_guardian/orchestration/tools/bridge.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .schemas import ActionIntent, ExecutionResult, intent_allowed

logger = logging.getLogger(__name__)


def _merge_payload(intent: ActionIntent, task_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    base: Dict[str, Any] = dict(intent.payload or {})
    ctx = task_context or {}
    goal = str(ctx.get("goal") or "")[:500]
    arch = str(ctx.get("archetype") or "")
    base.setdefault("task", goal)
    base.setdefault("query", goal[:400])
    base.setdefault("objective", goal)
    base.setdefault("self_task_archetype", arch)
    if isinstance(ctx.get("underused_modules"), list):
        base.setdefault("underused_modules", list(ctx.get("underused_modules") or []))
    if arch and intent.target_kind == "module" and (intent.target_name or "") == "task_router":
        base.setdefault(
            "structured_task",
            {
                "task_type": "self_task",
                "objective": goal,
                "payload": {
                    "source": "orchestration_bridge",
                    "format_version": 1,
                    "task_id": str(ctx.get("task_id") or ""),
                },
            },
        )
    return base


def execute_action_intent(
    guardian: Any,
    intent: ActionIntent,
    *,
    allowed_capabilities: Optional[List[str]] = None,
    task_context: Optional[Dict[str, Any]] = None,
) -> ExecutionResult:
    """
    Thin wrapper over capability_execution.execute_capability_kind.
    Does not invent a parallel execution system.
    """
    if intent.target_kind == "none":
        return ExecutionResult(
            success=False,
            target_kind="none",
            target_name="",
            payload={},
            error="target_kind_none_use_model_path",
            state_change_evidence={"skipped_bridge": True},
        )

    if not intent.target_name or not str(intent.target_name).strip():
        return ExecutionResult(
            success=False,
            target_kind=intent.target_kind,
            target_name="",
            payload={},
            error="missing_target_name",
            state_change_evidence={},
        )

    allowed = list(allowed_capabilities or [])
    if allowed and not intent_allowed(intent, allowed):
        return ExecutionResult(
            success=False,
            target_kind=intent.target_kind,
            target_name=intent.target_name or "",
            payload={},
            error="target_not_in_allowed_capabilities",
            state_change_evidence={"allowed": allowed},
        )

    try:
        from ...capability_execution import execute_capability_kind
    except Exception as e:
        logger.debug("bridge import execute_capability_kind: %s", e)
        return ExecutionResult(
            success=False,
            target_kind=intent.target_kind,
            target_name=intent.target_name or "",
            payload={},
            error="import_failed",
            state_change_evidence={},
        )

    kind = intent.target_kind
    name = str(intent.target_name).strip()
    inp = _merge_payload(intent, task_context)

    try:
        ex = execute_capability_kind(guardian, kind, name, inp)
    except Exception as e:
        return ExecutionResult(
            success=False,
            target_kind=kind,
            target_name=name,
            payload={},
            error=str(e)[:500],
            state_change_evidence={"exception": True},
        )

    if not isinstance(ex, dict):
        return ExecutionResult(
            success=False,
            target_kind=kind,
            target_name=name,
            payload={"raw": ex},
            error="non_dict_response",
            state_change_evidence={},
        )

    ok = bool(ex.get("success"))
    res = ex.get("result")
    evidence: Dict[str, Any] = {
        "executor_success": ok,
        "has_result": res is not None,
    }
    if isinstance(res, dict):
        evidence["result_keys"] = list(res.keys())[:24]

    return ExecutionResult(
        success=ok,
        target_kind=kind,
        target_name=name,
        payload={"result": res, "executor_response": ex},
        error=(str(ex.get("error"))[:500] if ex.get("error") else None),
        state_change_evidence=evidence,
    )
