# project_guardian/brain/live_execution_runtime.py
"""Runtime wiring for the live-execution guard (fail-closed; no execution)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from project_guardian.brain.config import BrainPipelineConfig
from project_guardian.governance.live_execution_audit import append_live_execution_guard_audit
from project_guardian.governance.live_execution_guard import (
    LiveExecutionDecision,
    LiveExecutionRequest,
    evaluate_live_execution_request,
)
from project_guardian.governance.operator_confirmation_store import (
    OperatorConfirmationStore,
    confirmation_to_guard_context,
)

_AUDIT_WRITE_FAILED = "audit_write_failed"
_OPERATOR_CONFIRMATION_INVALID = "operator_confirmation_invalid"
_RUNTIME_LIVE_EXECUTION_NOT_ENABLED = "runtime_live_execution_not_enabled"
_OPERATOR_ENTRYPOINTS = frozenset({"operator_chat", "control_panel_operator_chat"})


def _compact_guard_metadata(
    decision: LiveExecutionDecision,
    *,
    forced_dry_run: bool,
    audit_append_ok: bool = True,
) -> Dict[str, Any]:
    reasons = list(decision.reasons)
    if not audit_append_ok and _AUDIT_WRITE_FAILED not in reasons:
        reasons.append(_AUDIT_WRITE_FAILED)
    return {
        "allowed": bool(decision.allowed and audit_append_ok),
        "reason": str(reasons[0] if reasons else "")[:120],
        "reasons": reasons[:20],
        "blocked_reasons": reasons[:20],
        "reason_count": len(reasons),
        "required_next_steps": _required_next_steps(reasons),
        "risk_level": str(decision.risk_level)[:32],
        "executor_name": str(decision.executor_name)[:120],
        "source_entrypoint": str(decision.source_entrypoint)[:120],
        "request_id": str(decision.request_id)[:120],
        "fail_closed": bool(reasons),
        "forced_dry_run": bool(forced_dry_run or reasons),
        "audit_append_ok": bool(audit_append_ok),
        "live_execution_disabled_by_default": True,
    }


def _required_next_steps(reasons: list[str]) -> list[str]:
    steps = []
    if "missing_operator_confirmation" in reasons or _OPERATOR_CONFIRMATION_INVALID in reasons:
        steps.append("record_structured_operator_confirmation")
    if "missing_dry_run_trace" in reasons or "stale_dry_run_trace" in reasons:
        steps.append("complete_fresh_dry_run_trace")
    if "dry_run_trace_mismatch" in reasons or "confirmed_action_mismatch" in reasons:
        steps.append("match_confirmation_to_trace_action")
    if "missing_executor_allowlist" in reasons or "executor_not_allowlisted" in reasons:
        steps.append("review_executor_allowlist")
    if "audit_write_failed" in reasons:
        steps.append("restore_audit_logging")
    if _RUNTIME_LIVE_EXECUTION_NOT_ENABLED in reasons:
        steps.append("keep_runtime_validation_only")
    return steps[:8]


def _context_requests_live_execution(
    merge: Dict[str, Any],
    *,
    cfg: BrainPipelineConfig,
    source_entrypoint: str,
) -> bool:
    if merge.get("live_execution_requested") is True or merge.get("requested_live_execution") is True:
        return True
    if merge.get("dry_run") is False:
        return True
    ep = str(source_entrypoint or "")
    if ep in _OPERATOR_ENTRYPOINTS and bool(cfg.entrypoints.get("operator_chat_live_execution", False)):
        return True
    if ep == "tool_execution" and bool(cfg.entrypoints.get("tool_execution", False)) and not bool(cfg.dry_run):
        return True
    if not bool(cfg.dry_run) and bool(cfg.enabled):
        return True
    return False


def _as_tuple(value: Any) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if str(item).strip())
    return (str(value),)


def _confirmation_store_path(value: Any) -> Optional[Path]:
    if value is None or str(value).strip() == "":
        return None
    return Path(str(value))


def _apply_operator_confirmation_validation(
    merge: Dict[str, Any],
    *,
    source_entrypoint: str,
    cfg: BrainPipelineConfig,
) -> Optional[Dict[str, Any]]:
    confirmation_id = str(merge.get("operator_confirmation_id") or "").strip()
    if not confirmation_id:
        return None

    store = OperatorConfirmationStore(
        _confirmation_store_path(merge.get("operator_confirmation_store_path"))
    )
    record = store.get_operator_confirmation(confirmation_id, now=merge.get("now"))
    dry_run_trace_id = str(
        merge.get("dry_run_trace_id")
        or merge.get("prior_dry_run_trace_id")
        or (record.dry_run_trace_id if record else "")
        or ""
    )
    confirmed_action_id = str(
        merge.get("confirmed_action_id")
        or merge.get("live_execution_confirmed_action_id")
        or (record.confirmed_action_id if record else "")
        or ""
    )
    validation_now = merge.get("now")
    if validation_now is None and record is not None and merge.get("dry_run_trace_age_seconds") is not None:
        validation_now = record.created_at

    validation = store.validate_confirmation(
        confirmation_id,
        dry_run_trace_id=dry_run_trace_id,
        confirmed_action_id=confirmed_action_id,
        medium_risk_approved=merge.get("medium_risk_approved"),
        allow_self_modification_workflow=bool(merge.get("allow_self_modification_workflow")),
        now=validation_now,
    )
    public_valid, public_reason = store.is_confirmation_valid_for_request(
        confirmation_id,
        dry_run_trace_id=dry_run_trace_id,
        confirmed_action_id=confirmed_action_id,
        medium_risk_approved=merge.get("medium_risk_approved"),
        allow_self_modification_workflow=bool(merge.get("allow_self_modification_workflow")),
        now=validation_now,
    )

    if record is not None:
        record_context = confirmation_to_guard_context(
            record,
            source_entrypoint=source_entrypoint,
        )
        for key, value in record_context.items():
            if key in {"operator_confirmed", "operator_confirmation"}:
                continue
            merge[key] = value
        merge["confirmed_action_id"] = record.confirmed_action_id
        merge["operator_confirmation_record_loaded"] = True
    else:
        merge["operator_confirmation_record_loaded"] = False

    if validation.valid:
        merge["operator_confirmed"] = True
    else:
        merge["operator_confirmed"] = False
        merge["operator_confirmation"] = False

    meta = {
        "confirmation_id": confirmation_id[:120],
        "valid": bool(validation.valid and public_valid),
        "reasons": ([str(public_reason)] if public_reason and public_reason != "valid" else [])[:20],
        "raw_reasons": list(validation.reasons)[:20],
        "reason": str(public_reason if public_reason != "valid" else "")[:120],
        "loaded": bool(record is not None),
        "record_loaded": bool(record is not None),
        "dry_run_trace_id": dry_run_trace_id[:120],
        "confirmed_action_id": confirmed_action_id[:160],
        "validation_only": True,
        "marked_used": False,
        "consumed": False,
        "live_execution_disabled_by_config": (
            not bool(cfg.entrypoints.get("operator_chat_live_execution", False))
            or bool(cfg.dry_run)
        ),
    }
    if merge.get("operator_confirmation_store_path"):
        meta["store_path"] = str(merge.get("operator_confirmation_store_path"))[:300]
    merge["operator_confirmation_validation"] = meta
    return meta


def _attach_confirmation_meta_to_guard_meta(
    guard_meta: Dict[str, Any],
    confirmation_meta: Optional[Dict[str, Any]],
    *,
    requested_live: bool,
) -> None:
    if not confirmation_meta:
        return
    guard_meta["operator_confirmation_validation"] = confirmation_meta
    if confirmation_meta.get("valid"):
        return

    extra_reasons = [_OPERATOR_CONFIRMATION_INVALID]
    extra_reasons.extend(str(reason) for reason in (confirmation_meta.get("reasons") or []))
    reasons = list(guard_meta.get("reasons") or [])
    for reason in extra_reasons:
        if reason and reason not in reasons:
            reasons.append(reason)
    guard_meta["reasons"] = reasons[:20]
    guard_meta["blocked_reasons"] = reasons[:20]
    guard_meta["reason_count"] = len(reasons)
    guard_meta["reason"] = str((guard_meta.get("reason") or (reasons[0] if reasons else "")))[:120]
    guard_meta["required_next_steps"] = _required_next_steps(reasons)
    guard_meta["allowed"] = False
    guard_meta["fail_closed"] = True
    if requested_live:
        guard_meta["forced_dry_run"] = True


def _build_guard_request(
    merge: Dict[str, Any],
    *,
    cfg: BrainPipelineConfig,
    source_entrypoint: str,
    observation_text: str,
) -> LiveExecutionRequest:
    ep = str(source_entrypoint or "")
    allowlist = _as_tuple(
        merge.get("live_execution_executor_allowlist")
        or merge.get("executor_allowlist")
        or merge.get("allowed_executors")
    )
    payload = merge.get("live_execution_payload")
    if not isinstance(payload, dict):
        payload = {}
    return LiveExecutionRequest(
        request_id=str(merge.get("live_execution_request_id") or merge.get("request_id") or "")[:120],
        source_entrypoint=ep[:120],
        config_enabled=bool(cfg.enabled),
        entrypoint_enabled=bool(cfg.entrypoint_enabled(ep)),
        live_execution_enabled=bool(
            merge.get("live_execution_enabled")
            if "live_execution_enabled" in merge
            else cfg.entrypoints.get("operator_chat_live_execution", False)
            if ep in _OPERATOR_ENTRYPOINTS
            else cfg.entrypoints.get(f"{ep}_live_execution", False)
        ),
        risk_level=str(merge.get("live_execution_risk_level") or merge.get("risk_level") or "blocked")[:32],
        action_type=str(merge.get("live_execution_action_type") or merge.get("action_type") or "brain_pipeline")[:120],
        target=str(merge.get("live_execution_target") or merge.get("target") or "")[:240],
        executor_name=str(merge.get("live_execution_executor") or merge.get("executor_name") or "")[:120],
        executor_allowlist=allowlist,
        operator_confirmed=bool(merge.get("operator_confirmed") or merge.get("operator_confirmation")),
        operator_confirmation_id=str(merge.get("operator_confirmation_id") or "")[:120],
        explicit_medium_risk_approval=bool(
            merge.get("explicit_medium_risk_approval") or merge.get("medium_risk_approved")
        ),
        dry_run_trace_id=str(merge.get("dry_run_trace_id") or merge.get("prior_dry_run_trace_id") or "")[:120],
        dry_run_trace_completed_at=merge.get("dry_run_trace_completed_at"),
        now=merge.get("now"),
        dry_run_trace_ttl_seconds=int(merge.get("dry_run_trace_ttl_seconds") or 900),
        raw_text=str(observation_text or "")[:1000],
        payload=payload,
        is_self_modification=bool(merge.get("is_self_modification") or merge.get("self_modification")),
        is_autonomy_context=bool(merge.get("is_autonomy_context") or merge.get("autonomy_context"))
        or ep.lower() == "autonomy",
        mutates_files=bool(merge.get("mutates_files")),
        mutates_code=bool(merge.get("mutates_code")),
        rollback_available=bool(merge.get("rollback_available")),
        rollback_plan_id=str(merge.get("rollback_plan_id") or "")[:120],
    )


def apply_live_execution_guard_to_context(
    merge: Dict[str, Any],
    *,
    cfg: BrainPipelineConfig,
    source_entrypoint: str,
    observation_text: str = "",
    conversation_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Evaluate the guard before runtime can pass ``dry_run=False`` to BrainPipeline.

    Mutates and returns ``merge``. Denial or audit failure forces ``dry_run=True``.
    """
    confirmation_meta = _apply_operator_confirmation_validation(
        merge,
        source_entrypoint=source_entrypoint,
        cfg=cfg,
    )
    requested_live = _context_requests_live_execution(merge, cfg=cfg, source_entrypoint=source_entrypoint)
    decision = evaluate_live_execution_request(
        _build_guard_request(
            merge,
            cfg=cfg,
            source_entrypoint=source_entrypoint,
            observation_text=observation_text,
        )
    )
    if requested_live and decision.allowed:
        decision = LiveExecutionDecision(
            allowed=False,
            reasons=(*decision.reasons, _RUNTIME_LIVE_EXECUTION_NOT_ENABLED),
            request_id=decision.request_id,
            risk_level=decision.risk_level,
            executor_name=decision.executor_name,
            source_entrypoint=decision.source_entrypoint,
        )

    audit_ok = True
    if requested_live:
        audit_ok = append_live_execution_guard_audit(
            {
                "event": "live_execution_guard_evaluated",
                "entrypoint": source_entrypoint,
                "conversation_id": conversation_id,
                "requested_live_execution": True,
                "allowed": decision.allowed,
                "reasons": list(decision.reasons),
                "risk_level": decision.risk_level,
                "executor_name": decision.executor_name,
                "request_id": decision.request_id,
                "operator_confirmation_id": merge.get("operator_confirmation_id"),
                "operator_confirmation_validation": confirmation_meta,
            },
            audit_path=Path(str(merge.get("live_execution_guard_audit_path")))
            if merge.get("live_execution_guard_audit_path")
            else None,
        )

    forced_dry_run = bool(requested_live and (not decision.allowed or not audit_ok))
    if forced_dry_run:
        merge["dry_run"] = True
    elif requested_live and decision.allowed and audit_ok:
        ep = str(source_entrypoint or "")
        if ep in _OPERATOR_ENTRYPOINTS:
            if bool(cfg.entrypoints.get("operator_chat_live_execution", False)) and not bool(cfg.dry_run):
                merge["dry_run"] = False
            else:
                merge["dry_run"] = True
                forced_dry_run = True
        elif not bool(cfg.dry_run):
            merge["dry_run"] = False
        else:
            merge["dry_run"] = True
            forced_dry_run = True
    else:
        ep = str(source_entrypoint or "")
        if ep in _OPERATOR_ENTRYPOINTS and not bool(cfg.entrypoints.get("operator_chat_live_execution", False)):
            merge["dry_run"] = True
        elif "dry_run" not in merge:
            merge["dry_run"] = bool(cfg.dry_run)

    meta = _compact_guard_metadata(decision, forced_dry_run=forced_dry_run, audit_append_ok=audit_ok)
    meta["requested_live_execution"] = bool(requested_live)
    _attach_confirmation_meta_to_guard_meta(
        meta,
        confirmation_meta,
        requested_live=bool(requested_live),
    )
    merge["live_execution_guard"] = meta
    warnings = list(merge.get("live_execution_guard_warnings") or [])
    if requested_live and not meta["allowed"]:
        warnings.append(f"live_execution_guard_denied:{meta['reason']}")
    if forced_dry_run:
        warnings.append("live_execution_forced_dry_run")
    if warnings:
        merge["live_execution_guard_warnings"] = warnings[:20]
    return merge, meta
