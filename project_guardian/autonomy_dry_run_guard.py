"""Phase 1 dry-run autonomy guard — trace/audit only; no tool or live execution."""

from __future__ import annotations

import copy
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from project_guardian.brain.config import get_brain_pipeline_config
from project_guardian.brain.live_execution_runtime import apply_live_execution_guard_to_context
from project_guardian.governance.live_execution_guard import AUTONOMY_CONTEXT_DENIED

# Bounded cycles per explicit autonomy request (heartbeat / execute-cycle).
max_cycles_per_request = 1

_DEFAULT_AUDIT_PATH = Path("data/runtime/autonomy_dry_run_audit.jsonl")
_KILL_ENV = "ELYSIA_AUTONOMY_KILL"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def autonomy_kill_switch_active() -> bool:
    """True when ``ELYSIA_AUTONOMY_KILL`` or the repo kill-switch file is set."""
    raw = (os.environ.get(_KILL_ENV) or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    switch = _repo_root() / "data" / "runtime" / "autonomy_kill.switch"
    try:
        return switch.is_file()
    except OSError:
        return False


def autonomy_dry_run_only(cfg: Dict[str, Any]) -> bool:
    """Phase 1: dry-run is mandatory whenever autonomy is enabled.

    The config key ``dry_run_only`` is reserved for a future rollout phase and is
    ignored during Phase 1, including explicit ``dry_run_only: false``.
    """
    _ = cfg  # reserved for post-Phase-1 policy; must not disable dry-run in Phase 1
    return True


def append_autonomy_dry_run_audit(record: Dict[str, Any], *, audit_path: Optional[Path] = None) -> bool:
    """Append one compact JSON audit line; returns False on I/O failure."""
    path = audit_path or (_repo_root() / _DEFAULT_AUDIT_PATH)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, default=str)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return True
    except OSError:
        return False


def _evaluate_autonomy_live_execution_guard(
    *,
    proposed_action: str,
    cycle_id: str,
) -> Dict[str, Any]:
    merge: Dict[str, Any] = {
        "dry_run": True,
        "autonomy_context": True,
        "is_autonomy_context": True,
        "source_entrypoint": "autonomy",
        "cycle_id": cycle_id,
    }
    cfg = get_brain_pipeline_config()
    merge, guard_meta = apply_live_execution_guard_to_context(
        merge,
        cfg=cfg,
        source_entrypoint="autonomy",
        observation_text=str(proposed_action or "")[:8000],
    )
    reasons = list(guard_meta.get("reasons") or guard_meta.get("blocked_reasons") or [])
    if AUTONOMY_CONTEXT_DENIED not in reasons:
        reasons.append(AUTONOMY_CONTEXT_DENIED)
    guard_meta = {**guard_meta, "reasons": reasons[:20], "allowed": False}
    merge["dry_run"] = True
    return guard_meta


def _classify_proposed_action_kind(action: str) -> str:
    """Coarse, side-effect-free classification of a proposed action string."""
    a = (action or "").strip()
    if not a:
        return "none"
    if a.startswith("use_capability/"):
        return "use_capability"
    head = a.split("/", 1)[0].strip()
    return head or "none"


def build_dry_run_decision_trace(
    *,
    cycle_id: str,
    source: str,
    proposed_action: Optional[str],
    guard_meta: Optional[Dict[str, Any]] = None,
    extra_block_reasons: Optional[list] = None,
    notes: str = "",
) -> Dict[str, Any]:
    """Build a serializable, observation-only Phase 1 dry-run decision trace.

    This helper has no side effects and must not influence action selection,
    scoring, routing, or execution. Phase 1 invariants are hard-coded: the
    proposed action is never executed and no capability/mutation/proposal/legacy
    path is reachable from here.
    """
    guard_meta = guard_meta or {}
    action = str(proposed_action or "")
    reasons: list = []
    for reason in list(guard_meta.get("reasons") or []) + list(extra_block_reasons or []):
        if reason not in reasons:
            reasons.append(reason)
    return {
        "trace_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "cycle_id": cycle_id,
        "proposed_action": action,
        "proposed_action_kind": _classify_proposed_action_kind(action),
        "proposed_action_summary": action[:80],
        "dry_run": True,
        "executed": False,
        "block_reasons": reasons[:20],
        "live_execution_guard": guard_meta,
        "capability_called": False,
        "mutation_called": False,
        "proposal_implementation_called": False,
        "legacy_executor_reached": False,
        "notes": str(notes or ""),
    }


def summarize_dry_run_decision_trace(trace: Dict[str, Any]) -> Dict[str, Any]:
    """Derive a human-readable, observation-only summary of a dry-run decision trace.

    Pure function: does not mutate ``trace``, does not execute anything, and tolerates
    missing optional fields. The returned dict is JSON-serializable and deterministic
    given the same input.
    """
    trace = trace if isinstance(trace, dict) else {}

    def _bool(key: str) -> bool:
        return bool(trace.get(key))

    executed = _bool("executed")
    dry_run = trace.get("dry_run", True)
    dry_run = True if dry_run is None else bool(dry_run)
    blocked = (not executed) and dry_run
    block_reasons = [str(r) for r in (trace.get("block_reasons") or [])][:20]

    capability_called = _bool("capability_called")
    mutation_called = _bool("mutation_called")
    proposal_implementation_called = _bool("proposal_implementation_called")
    legacy_executor_reached = _bool("legacy_executor_reached")

    action_kind = str(trace.get("proposed_action_kind") or "none")
    action_summary = str(trace.get("proposed_action_summary") or "")

    if blocked:
        outcome = "dry_run_blocked_not_executed"
    elif executed:
        outcome = "executed"  # not reachable in Phase 1; reported for completeness
    else:
        outcome = "not_executed"

    safety_summary = {
        "capability_called": capability_called,
        "mutation_called": mutation_called,
        "proposal_implementation_called": proposal_implementation_called,
        "legacy_executor_reached": legacy_executor_reached,
    }
    execution_summary = {
        "dry_run": dry_run,
        "executed": executed,
        "blocked": blocked,
    }

    reasons_text = ", ".join(block_reasons) if block_reasons else "none recorded"
    human_summary = (
        f"Dry-run autonomy proposed '{action_summary or action_kind}' "
        f"({action_kind}); outcome={outcome}; "
        f"executed={executed}, dry_run={dry_run}; "
        f"reasons: {reasons_text}."
    )

    return {
        "summary_id": str(uuid.uuid4()),
        "trace_id": str(trace.get("trace_id") or ""),
        "source": str(trace.get("source") or ""),
        "proposed_action_kind": action_kind,
        "proposed_action_summary": action_summary,
        "outcome": outcome,
        "blocked": blocked,
        "block_reasons": block_reasons,
        "safety_summary": safety_summary,
        "execution_summary": execution_summary,
        "human_summary": human_summary,
    }


def build_dry_run_decision_report(
    *,
    result: Optional[Dict[str, Any]] = None,
    trace: Optional[Dict[str, Any]] = None,
    summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a readable, observation-only dry-run report from a dry-run result.

    Derived purely from the Phase 1 dry-run ``result`` (or an explicit ``trace`` /
    ``summary``). Pure function: does not mutate inputs, does not execute anything,
    tolerates missing optional fields, and returns a JSON-serializable dict.
    """
    result = result if isinstance(result, dict) else {}
    trace = trace if isinstance(trace, dict) else (result.get("decision_trace") or {})
    trace = trace if isinstance(trace, dict) else {}
    summary = summary if isinstance(summary, dict) else (result.get("decision_trace_summary") or {})
    summary = summary if isinstance(summary, dict) else {}

    if not summary and trace:
        summary = summarize_dry_run_decision_trace(trace)

    def _pick(key: str, default: Any = "") -> Any:
        if key in trace:
            return trace.get(key)
        if key in result:
            return result.get(key)
        return default

    executed = bool(_pick("executed", False))
    dry_run_raw = trace.get("dry_run", result.get("dry_run", True))
    dry_run = True if dry_run_raw is None else bool(dry_run_raw)
    blocked = bool(summary.get("blocked", (not executed) and dry_run))

    block_reasons = [str(r) for r in (summary.get("block_reasons") or trace.get("block_reasons") or [])][:20]

    safety_checks = {
        "capability_called": bool(trace.get("capability_called", False)),
        "mutation_called": bool(trace.get("mutation_called", False)),
        "proposal_implementation_called": bool(trace.get("proposal_implementation_called", False)),
        "legacy_executor_reached": bool(trace.get("legacy_executor_reached", False)),
    }
    execution_checks = {
        "dry_run": dry_run,
        "executed": executed,
        "blocked": blocked,
    }

    status = str(summary.get("outcome") or ("dry_run_blocked_not_executed" if blocked else "not_executed"))

    return {
        "report_id": str(uuid.uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(_pick("source", "")),
        "cycle_id": str(_pick("cycle_id", "")),
        "status": status,
        "proposed_action": str(_pick("proposed_action", "") or ""),
        "proposed_action_kind": str(trace.get("proposed_action_kind") or summary.get("proposed_action_kind") or "none"),
        "proposed_action_summary": str(
            trace.get("proposed_action_summary") or summary.get("proposed_action_summary") or ""
        ),
        "dry_run": dry_run,
        "executed": executed,
        "blocked": blocked,
        "block_reasons": block_reasons,
        "safety_checks": safety_checks,
        "execution_checks": execution_checks,
        "human_summary": str(summary.get("human_summary") or ""),
        "raw_trace": dict(trace),
        "raw_summary": dict(summary),
    }


def build_dry_run_observer_envelope(
    batch: Dict[str, Any],
    *,
    mode: str,
    problems: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build passive Safe Observer reporting fields from a dry-run batch.

    Pure function: no side effects, no execution, no file writes. Adds compact
    ``decision_trace_summaries`` and ``observability_warnings`` without duplicating
    full ``batch`` counters already present on the batch dict.
    """
    problems = list(problems or [])
    summaries: List[Dict[str, Any]] = []
    observability_warnings: List[str] = []

    for idx, report in enumerate(batch.get("reports") or [], start=1):
        if not isinstance(report, dict):
            observability_warnings.append(f"cycle_{idx}_report_malformed")
            continue
        raw_summary = report.get("raw_summary")
        if not isinstance(raw_summary, dict) or not raw_summary:
            observability_warnings.append(f"cycle_{idx}_missing_decision_trace_summary")
            raw_summary = {}
        raw_trace = report.get("raw_trace")
        if not isinstance(raw_trace, dict) or not str(raw_trace.get("trace_id") or "").strip():
            observability_warnings.append(f"cycle_{idx}_missing_or_malformed_trace")

        summaries.append(
            {
                "cycle": idx,
                "trace_id": str(raw_summary.get("trace_id") or (raw_trace or {}).get("trace_id") or ""),
                "outcome": str(raw_summary.get("outcome") or report.get("status") or ""),
                "proposed_action_kind": str(
                    raw_summary.get("proposed_action_kind") or report.get("proposed_action_kind") or ""
                ),
                "proposed_action_summary": str(
                    raw_summary.get("proposed_action_summary") or report.get("proposed_action_summary") or ""
                )[:80],
                "blocked": bool(raw_summary.get("blocked", report.get("blocked"))),
            }
        )

    safety_verdict = "SAFE" if not problems else "UNSAFE"
    return {
        "mode": mode,
        "safe": not problems,
        "safety_verdict": safety_verdict,
        "decision_trace_summaries": summaries,
        "observability_warnings": observability_warnings,
    }


class DryRunBatchSafetyError(RuntimeError):
    """Raised when the bounded dry-run batch runner must fail closed."""


def _inspect_dry_run_cycle(cycle_result: Any) -> Tuple[Dict[str, Any], List[str]]:
    """Return (report_copy, problems) for one cycle result. Never mutates input."""
    result = cycle_result if isinstance(cycle_result, dict) else {}
    trace = result.get("decision_trace") if isinstance(result.get("decision_trace"), dict) else {}
    report = result.get("dry_run_report") if isinstance(result.get("dry_run_report"), dict) else {}
    safety = report.get("safety_checks") if isinstance(report.get("safety_checks"), dict) else {}

    problems: List[str] = []
    if not report:
        problems.append("missing_dry_run_report")
    if result.get("executed") is True:
        problems.append("executed_true")
    if result.get("dry_run") is not True:
        problems.append("dry_run_not_true")
    if trace.get("legacy_executor_reached") is True or safety.get("legacy_executor_reached") is True:
        problems.append("legacy_executor_reached")
    for flag in ("capability_called", "mutation_called", "proposal_implementation_called"):
        if trace.get(flag) is True or safety.get(flag) is True:
            problems.append(flag)

    return copy.deepcopy(report), problems


def run_phase1_dry_run_batch(
    run_cycle: Callable[[], Dict[str, Any]],
    *,
    max_cycles: int = 3,
    requested_cycles: int = 3,
    persist: bool = False,
) -> Dict[str, Any]:
    """Run a small, hard-capped batch of injected dry-run cycles and collect evidence.

    ``run_cycle`` is an injected callable returning one Phase 1 dry-run result
    (containing ``decision_trace``, ``decision_trace_summary``, ``dry_run_report``).
    The runner never imports/constructs ``GuardianCore``, never executes tools, never
    loops in the background, and fails closed on any unsafe condition. ``persist`` is
    not implemented here: ``persist=True`` is ignored with a warning (no files written).
    """
    batch_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    warnings: List[str] = []

    if not callable(run_cycle):
        raise DryRunBatchSafetyError("run_cycle must be callable")
    if not isinstance(max_cycles, int) or isinstance(max_cycles, bool) or max_cycles < 0:
        raise DryRunBatchSafetyError("max_cycles must be a non-negative int")
    if not isinstance(requested_cycles, int) or isinstance(requested_cycles, bool):
        raise DryRunBatchSafetyError("requested_cycles must be an int")
    if requested_cycles < 0:
        raise DryRunBatchSafetyError("requested_cycles must not be negative")
    if requested_cycles > max_cycles:
        raise DryRunBatchSafetyError(
            f"requested_cycles {requested_cycles} exceeds max_cycles {max_cycles}"
        )
    if persist:
        warnings.append("persistence_not_implemented_ignored")
        persist = False

    reports: List[Dict[str, Any]] = []
    completed = 0

    for _ in range(requested_cycles):
        cycle_result = run_cycle()
        report_copy, problems = _inspect_dry_run_cycle(cycle_result)
        if problems:
            raise DryRunBatchSafetyError(f"unsafe dry-run cycle: {sorted(set(problems))}")
        reports.append(report_copy)
        completed += 1

    all_dry_run = all(r.get("dry_run") is True for r in reports) if reports else True
    any_executed = any(r.get("executed") is True for r in reports)
    legacy_fallback_reached = any(
        (r.get("safety_checks") or {}).get("legacy_executor_reached") is True for r in reports
    )
    all_blocked = all(r.get("blocked") is True for r in reports) if reports else True

    summary = {
        "requested_cycles": requested_cycles,
        "completed_cycles": completed,
        "all_dry_run": all_dry_run,
        "any_executed": any_executed,
        "all_blocked": all_blocked,
        "execution_call_count": 0,
        "legacy_fallback_reached": legacy_fallback_reached,
        "persisted": persist,
    }

    return {
        "batch_id": batch_id,
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "requested_cycles": requested_cycles,
        "completed_cycles": completed,
        "all_dry_run": all_dry_run,
        "any_executed": any_executed,
        "execution_call_count": 0,
        "legacy_fallback_reached": legacy_fallback_reached,
        "reports": reports,
        "summary": summary,
        "warnings": warnings,
    }


def run_brain_pipeline_for_autonomy_event(
    guardian: Any,
    *,
    next_action: Dict[str, Any],
    cycle_id: str,
    source: str,
) -> Dict[str, Any]:
    """Dry-run autonomy trace hook: guard evaluation only (no BrainPipeline execution)."""
    action = str(next_action.get("action") or "")
    guard_meta = _evaluate_autonomy_live_execution_guard(
        proposed_action=action,
        cycle_id=cycle_id,
    )
    return {
        "dry_run": True,
        "source_entrypoint": "autonomy",
        "cycle_id": cycle_id,
        "source": source,
        "live_execution_guard": guard_meta,
        "proposed_action": action,
    }


def _autonomy_phase1_dry_run(
    guardian: Any,
    cfg: Dict[str, Any],
    *,
    source: str,
) -> Dict[str, Any]:
    """Single bounded dry-run cycle: propose action, guard, audit; never execute."""
    cycle_id = str(uuid.uuid4())
    depth = int(getattr(guardian, "_autonomy_phase1_cycle_depth", 0) or 0)
    if depth >= max_cycles_per_request:
        _decision_trace = build_dry_run_decision_trace(
            cycle_id=cycle_id,
            source=source,
            proposed_action=None,
            extra_block_reasons=["max_cycles_per_request"],
            notes="cycle budget exhausted for this request",
        )
        _decision_summary = summarize_dry_run_decision_trace(_decision_trace)
        out = {
            "executed": False,
            "action": None,
            "reason": "max_cycles_per_request",
            "dry_run": True,
            "cycle_id": cycle_id,
            "decision_trace": _decision_trace,
            "decision_trace_summary": _decision_summary,
        }
        out["dry_run_report"] = build_dry_run_decision_report(
            result=out, trace=_decision_trace, summary=_decision_summary
        )
        append_autonomy_dry_run_audit(
            {
                "cycle_id": cycle_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": source,
                "config_enabled": bool(cfg.get("enabled")),
                "dry_run_only": True,
                "executed": False,
                "reason": "max_cycles_per_request",
            }
        )
        return out

    setattr(guardian, "_autonomy_phase1_cycle_depth", depth + 1)
    try:
        next_result: Dict[str, Any] = {}
        if hasattr(guardian, "get_next_action"):
            next_result = guardian.get_next_action() or {}
        action = next_result.get("action")
        trace = run_brain_pipeline_for_autonomy_event(
            guardian,
            next_action=next_result,
            cycle_id=cycle_id,
            source=source,
        )
        guard_meta = trace.get("live_execution_guard") or {}
        guard_reasons = list(guard_meta.get("reasons") or [])
        decision_trace = build_dry_run_decision_trace(
            cycle_id=cycle_id,
            source=source,
            proposed_action=action,
            guard_meta=guard_meta,
            extra_block_reasons=["dry_run_only"],
        )
        decision_summary = summarize_dry_run_decision_trace(decision_trace)
        out = {
            "executed": False,
            "action": action,
            "reason": "dry_run_only",
            "dry_run": True,
            "cycle_id": cycle_id,
            "trace_id": cycle_id,
            "guard_reasons": guard_reasons,
            "can_auto_execute": bool(next_result.get("can_auto_execute")),
            "live_execution_guard": guard_meta,
            "decision_trace": decision_trace,
            "decision_trace_summary": decision_summary,
        }
        out["dry_run_report"] = build_dry_run_decision_report(
            result=out, trace=decision_trace, summary=decision_summary
        )
        append_autonomy_dry_run_audit(
            {
                "cycle_id": cycle_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": source,
                "config_enabled": bool(cfg.get("enabled")),
                "dry_run_only": True,
                "proposed_action": action,
                "can_auto_execute": bool(next_result.get("can_auto_execute")),
                "executed": False,
                "brain_trace_id": cycle_id,
                "live_execution_guard": {
                    "allowed": False,
                    "reasons": guard_reasons[:20],
                },
                "kill_switch_active": False,
            }
        )
        if hasattr(guardian, "_last_autonomy_next_result"):
            guardian._last_autonomy_next_result = next_result
        if hasattr(guardian, "_last_autonomy_result"):
            guardian._last_autonomy_result = out
        return out
    finally:
        setattr(guardian, "_autonomy_phase1_cycle_depth", depth)


def run_autonomous_phase1_dry_run(guardian: Any, cfg: Dict[str, Any], *, source: str) -> Dict[str, Any]:
    """Public entry used by ``GuardianCore.run_autonomous_cycle`` when dry-run is required."""
    return _autonomy_phase1_dry_run(guardian, cfg, source=source)
