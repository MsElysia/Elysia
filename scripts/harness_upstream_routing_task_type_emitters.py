#!/usr/bin/env python3
"""
Exercise the three upstream routing_task_type INFO emitters without changing routing logic.

Writes matching lines to data/upstream_routing_harness.log (default).

Usage:
  python scripts/harness_upstream_routing_task_type_emitters.py bridge
  python scripts/harness_upstream_routing_task_type_emitters.py self
  python scripts/harness_upstream_routing_task_type_emitters.py autonomy
  python scripts/harness_upstream_routing_task_type_emitters.py all
"""
from __future__ import annotations

import argparse
import logging
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable, List, Optional
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_OUT = DATA_DIR / "upstream_routing_harness.log"

# Log message substrings we expect from production code (grep-friendly).
MARKERS = (
    "[OrchestrationBridge] routing_task_type",
    "[SelfTasking] routing_task_type",
    "[Autonomy] routing_task_type",
)


class _HarnessLineFilter(logging.Filter):
    """Keep file output narrow: only the three upstream routing_task_type lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return any(m in msg for m in MARKERS)


def _minimal_core_config(mem_file: Path, storage: Path) -> dict:
    return {
        "memory_filepath": str(mem_file),
        "storage_path": str(storage),
        "ui_config": {"enabled": False},
        "defer_heavy_startup": True,
        "_test_skip_external_storage": True,
        "enable_resource_monitoring": False,
        "enable_vector_memory": False,
        "enable_runtime_health_monitoring": False,
    }


def _register_handlers(loggers: Iterable[str], fh: logging.FileHandler) -> List[logging.Logger]:
    out: List[logging.Logger] = []
    for name in loggers:
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        lg.addHandler(fh)
        out.append(lg)
    return out


def _detach_handlers(loggers: List[logging.Logger], fh: logging.FileHandler) -> None:
    for lg in loggers:
        try:
            lg.removeHandler(fh)
        except Exception:
            pass
    try:
        fh.close()
    except Exception:
        pass


def emit_bridge(fh: logging.FileHandler) -> None:
    """project_guardian.orchestration.tools.bridge._merge_payload (task_router + archetype + goal)."""
    loggers = _register_handlers(
        ("project_guardian.orchestration.tools.bridge",),
        fh,
    )
    try:
        from project_guardian.orchestration.tools.schemas import ActionIntent
        from project_guardian.orchestration.tools.bridge import _merge_payload

        intent = ActionIntent(
            action_type="harness_upstream_routing",
            target_kind="module",
            target_name="task_router",
            payload={},
        )
        _merge_payload(
            intent,
            {
                "goal": "fetch https://example.com/harness for orchestration bridge routing inference",
                "archetype": "harness_orchestration_bridge",
                "task_id": "harness_bridge_1",
            },
        )
    finally:
        _detach_handlers(loggers, fh)


def emit_self_tasking(fh: logging.FileHandler) -> None:
    """GuardianCore._run_self_generated_task → module:task_router branch (non-brokered archetype)."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from project_guardian.core import GuardianCore
    from project_guardian.guardian_singleton import reset_singleton
    from project_guardian.self_task_queue import SelfTaskQueue

    loggers = _register_handlers(("project_guardian.core",), fh)
    tmp = Path(tempfile.mkdtemp())
    mem = tmp / "guardian_memory.json"
    mem.write_text("[]", encoding="utf-8")
    qp = tmp / "self_task_queue.harness.json"

    def make_q(**kw: object) -> SelfTaskQueue:
        return SelfTaskQueue(
            storage_path=qp, max_size=int(kw.get("max_size", 24))  # type: ignore[arg-type]
        )

    def fake_exec(guardian: object, kind: str, name: str, inp: dict) -> dict:
        return {"success": True, "result": {"harness": True, "routed_to": "web_search"}}

    tid = "harness_self_routing_1"
    reset_singleton()
    core: Optional[GuardianCore] = None
    try:
        core = GuardianCore(_minimal_core_config(mem, tmp), allow_multiple=True)
        q0 = SelfTaskQueue(storage_path=qp)
        q0.enqueue(
            {
                "task_id": tid,
                "archetype": "upstream_routing_harness",
                "goal": "fetch https://example.com/harness for self-task routing inference",
                "recommended_capabilities": ["module:task_router"],
                "title": "harness_self",
            },
            dedupe_key="harness_upstream_self_task_routing",
            cooldown_sec=0,
        )
        with patch(
            "project_guardian.self_task_queue.SelfTaskQueue", make_q
        ), patch(
            "project_guardian.capability_execution.execute_capability_kind", fake_exec
        ):
            core._run_self_generated_task(tid, time.time(), None)
    finally:
        _detach_handlers(loggers, fh)
        if core is not None:
            try:
                core.shutdown()
            except Exception:
                pass
        reset_singleton()


def emit_autonomy(fh: logging.FileHandler) -> None:
    """GuardianCore.run_autonomous_cycle → use_capability/module/task_router branch."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from project_guardian.core import GuardianCore
    from project_guardian.guardian_singleton import reset_singleton

    loggers = _register_handlers(("project_guardian.core",), fh)
    tmp = Path(tempfile.mkdtemp())
    mem = tmp / "guardian_memory.json"
    mem.write_text("[]", encoding="utf-8")

    autocfg = {
        "enabled": True,
        "allowed_actions": ["consider_learning"],
        "allow_dynamic_capability_actions": True,
        "max_actions_per_hour": 60,
    }

    def fake_load_autonomy() -> dict:
        return autocfg

    def fake_next_action() -> dict:
        return {
            "action": "use_capability/module/task_router",
            "can_auto_execute": True,
            "metadata": {},
            "reason": "harness_upstream_routing",
        }

    def fake_exec(guardian: object, kind: str, name: str, inp: dict) -> dict:
        return {"success": True, "result": {"harness": True}}

    reset_singleton()
    core: Optional[GuardianCore] = None
    try:
        core = GuardianCore(_minimal_core_config(mem, tmp), allow_multiple=True)
        mods = dict(getattr(core, "_modules") or {})
        mods["task_router"] = object()
        core._modules = mods
        core._pre_decision_context = {
            "task_context": (
                "Harness autonomy routing inference context sample text for grep validation."
            )
        }
        with patch.object(core, "_load_autonomy_config", fake_load_autonomy), patch.object(
            core, "get_next_action", fake_next_action
        ), patch(
            "project_guardian.capability_execution.execute_capability_kind", fake_exec
        ):
            core.run_autonomous_cycle()
    finally:
        _detach_handlers(loggers, fh)
        if core is not None:
            try:
                core.shutdown()
            except Exception:
                pass
        reset_singleton()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "mode",
        choices=("bridge", "self", "autonomy", "all"),
        help="Which emitter(s) to run",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Log file path (default: {DEFAULT_OUT})",
    )
    args = p.parse_args()
    sys.path.insert(0, str(PROJECT_ROOT))

    modes = ["bridge", "self", "autonomy"] if args.mode == "all" else [args.mode]

    for i, mode in enumerate(modes):
        fh_mode = "w" if i == 0 else "a"
        path = args.out
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(path, mode=fh_mode, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.addFilter(_HarnessLineFilter())
        fh.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        try:
            if mode == "bridge":
                emit_bridge(fh)
            elif mode == "self":
                emit_self_tasking(fh)
            elif mode == "autonomy":
                emit_autonomy(fh)
        finally:
            try:
                fh.close()
            except Exception:
                pass

    print(f"Wrote filtered harness lines (if any) to: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
