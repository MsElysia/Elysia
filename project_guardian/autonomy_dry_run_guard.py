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
    """Phase 1 default: dry-run even when autonomy is enabled in config."""
    if cfg.get("dry_run_only") is False:
        return False
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
