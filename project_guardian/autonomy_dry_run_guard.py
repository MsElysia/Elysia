"""Phase 1 dry-run autonomy guard — trace/audit only; no tool or live execution."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

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
        out = {
            "executed": False,
            "action": None,
            "reason": "max_cycles_per_request",
            "dry_run": True,
            "cycle_id": cycle_id,
            "decision_trace": build_dry_run_decision_trace(
                cycle_id=cycle_id,
                source=source,
                proposed_action=None,
                extra_block_reasons=["max_cycles_per_request"],
                notes="cycle budget exhausted for this request",
            ),
        }
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
        }
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
