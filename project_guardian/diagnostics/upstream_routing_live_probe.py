"""
One-shot live validation for upstream routing_task_type INFO lines in elysia_unified.log.

Gated by environment variables (default: off). Does not change TaskRouter, inference, or providers.

Environment (set before starting Elysia / run_elysia_unified.py):

  ELYSIA_DIAG_UPSTREAM_ROUTING_SELF_TASK=1
      After startup delay, enqueues a diagnostic self-task with
      recommended_capabilities including module:task_router and runs
      GuardianCore._run_self_generated_task so this line can appear:
      [SelfTasking] routing_task_type inferred=...

  ELYSIA_DIAG_UPSTREAM_ROUTING_BRIDGE=1
      After the same scheduled callback (after self-task probe if enabled),
      calls bridge._merge_payload for module task_router so this line can appear:
      [OrchestrationBridge] routing_task_type inferred=...

  ELYSIA_DIAG_UPSTREAM_ROUTING_DELAY_SEC=12
      Seconds to wait after scheduling (float, default 12).

  ELYSIA_DIAG_UPSTREAM_ROUTING_AUTONOMY=1
      After self-task and bridge probes in the same callback (if any), runs
      GuardianCore.run_autonomous_cycle() once with temporary patches so the decider
      appears to have chosen use_capability/module/task_router. Exercises the real
      autonomy branch that logs:
      [Autonomy] routing_task_type inferred=...
      execute_capability_kind is stubbed to a no-op success dict (no provider/tool work).

Grep (after run):

  Select-String -Path "elysia_unified.log" -Pattern "routing_task_type inferred"
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, Optional
from unittest.mock import patch

logger = logging.getLogger(__name__)


def _truthy(raw: Optional[str]) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _run_self_tasking_probe(guardian: Any) -> None:
    from project_guardian.self_task_queue import SelfTaskQueue

    tid = f"diag_upstream_rt_{uuid.uuid4().hex[:12]}"
    st_cfg = guardian._load_self_tasking_config()
    q = SelfTaskQueue(max_size=int(st_cfg.get("max_queue_size", 24)))
    enq = q.enqueue(
        {
            "task_id": tid,
            "archetype": "diag_upstream_routing",
            "goal": (
                "fetch https://example.com/diag for live upstream routing validation"
            ),
            "recommended_capabilities": ["module:task_router"],
            "title": "diag upstream routing",
        },
        dedupe_key=f"diag_upstream_rt_{tid}",
        cooldown_sec=0.0,
    )
    if not enq:
        logger.warning(
            "[diag] upstream routing: self-task enqueue skipped (dedupe/cap) task_id=%s",
            tid,
        )
        return
    logger.info(
        "[diag] upstream routing: running self-task probe task_id=%s",
        tid,
    )
    guardian._run_self_generated_task(tid, time.time(), None)


def _run_bridge_probe() -> None:
    from project_guardian.orchestration.tools.schemas import ActionIntent
    from project_guardian.orchestration.tools.bridge import _merge_payload

    intent = ActionIntent(
        action_type="diag_upstream_routing",
        target_kind="module",
        target_name="task_router",
        payload={},
    )
    _merge_payload(
        intent,
        {
            "goal": "fetch https://example.com/diag for live orchestration bridge validation",
            "archetype": "diag_orchestration_bridge",
            "task_id": f"diag_bridge_{uuid.uuid4().hex[:8]}",
        },
    )
    logger.info("[diag] upstream routing: bridge _merge_payload completed")


def _run_autonomy_probe(guardian: Any) -> None:
    """
    One call through run_autonomous_cycle's use_capability branch (real log line).
    Patches only for this call: autonomy config, get_next_action, execute_capability_kind.
    """
    mods = dict(getattr(guardian, "_modules", None) or {})
    if "task_router" not in mods:
        mods["task_router"] = object()
        guardian._modules = mods
    guardian._pre_decision_context = {
        "task_context": (
            "fetch https://example.com/diag for live autonomy upstream routing diagnostic"
        )
    }

    autocfg = {
        "enabled": True,
        "allowed_actions": ["consider_learning"],
        "allow_dynamic_capability_actions": True,
        "max_actions_per_hour": 60,
    }

    def _fake_load_autonomy() -> Dict[str, Any]:
        return dict(autocfg)

    def _fake_next_action() -> Dict[str, Any]:
        return {
            "action": "use_capability/module/task_router",
            "can_auto_execute": True,
            "metadata": {},
            "reason": "diag_upstream_routing_autonomy",
        }

    def _fake_exec(
        g: Any, kind: str, name: str, inp: Dict[str, Any]
    ) -> Dict[str, Any]:
        return {"success": True, "result": {"diag_autonomy_probe": True}}

    logger.info("[diag] upstream routing: running autonomy run_autonomous_cycle probe")
    with patch.object(guardian, "_load_autonomy_config", _fake_load_autonomy), patch.object(
        guardian, "get_next_action", _fake_next_action
    ), patch(
        "project_guardian.capability_execution.execute_capability_kind", _fake_exec
    ):
        guardian.run_autonomous_cycle()
    logger.info("[diag] upstream routing: autonomy probe completed")


def schedule_upstream_routing_live_probes(guardian: Optional[Any]) -> None:
    """
    If env flags are set, schedule a background timer to emit diagnostic upstream
    routing_task_type logs via real code paths. Safe to no-op when unset.
    """
    self_on = _truthy(os.environ.get("ELYSIA_DIAG_UPSTREAM_ROUTING_SELF_TASK"))
    bridge_on = _truthy(os.environ.get("ELYSIA_DIAG_UPSTREAM_ROUTING_BRIDGE"))
    autonomy_on = _truthy(os.environ.get("ELYSIA_DIAG_UPSTREAM_ROUTING_AUTONOMY"))
    if not self_on and not bridge_on and not autonomy_on:
        return
    if self_on and guardian is None:
        logger.warning(
            "[diag] ELYSIA_DIAG_UPSTREAM_ROUTING_SELF_TASK set but guardian is None; skipping self-task probe"
        )
        self_on = False
    if autonomy_on and guardian is None:
        logger.warning(
            "[diag] ELYSIA_DIAG_UPSTREAM_ROUTING_AUTONOMY set but guardian is None; skipping autonomy probe"
        )
        autonomy_on = False
    if not self_on and not bridge_on and not autonomy_on:
        return

    try:
        delay = float(os.environ.get("ELYSIA_DIAG_UPSTREAM_ROUTING_DELAY_SEC", "12"))
    except (TypeError, ValueError):
        delay = 12.0
    delay = max(1.0, min(delay, 600.0))

    def _callback() -> None:
        try:
            if self_on and guardian is not None:
                _run_self_tasking_probe(guardian)
            if bridge_on:
                _run_bridge_probe()
            if autonomy_on and guardian is not None:
                _run_autonomy_probe(guardian)
        except Exception as e:
            logger.warning("[diag] upstream_routing_live_probe failed: %s", e, exc_info=True)

    t = threading.Timer(delay, _callback)
    t.daemon = True
    t.start()
    logger.info(
        "[diag] Scheduled upstream routing live probe in %.1fs (self_task=%s bridge=%s autonomy=%s)",
        delay,
        self_on,
        bridge_on,
        autonomy_on,
    )
