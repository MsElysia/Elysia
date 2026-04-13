#!/usr/bin/env python3
"""
Emit fresh logs that mirror live task_router gate + TaskRouter real_route behavior.

Run: python scripts/validate_task_router_gate_live.py
Output: data/task_router_gate_validation.log
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUT = DATA_DIR / "task_router_gate_validation.log"


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT / "core_modules" / "elysia_core_comprehensive"))

    from ai_tool_registry import TaskRouter, ToolRegistry
    from ai_tool_registry import reset_task_router_real_route_metrics
    from project_guardian.capability_execution import (
        execute_capability_kind,
        reset_task_router_gate_metrics,
    )

    reset_task_router_gate_metrics()
    reset_task_router_real_route_metrics()

    root = logging.getLogger("project_guardian.capability_execution")
    tr_log = logging.getLogger("ai_tool_registry")
    for lg in (root, tr_log):
        lg.handlers.clear()
    root.setLevel(logging.DEBUG)
    tr_log.setLevel(logging.INFO)
    fh = logging.FileHandler(OUT, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    root.addHandler(fh)
    tr_log.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    fmt = logging.Formatter("%(message)s")
    sh.setFormatter(fmt)
    root.addHandler(sh)
    tr_log.addHandler(sh)

    reg = ToolRegistry()
    reg.ensure_minimal_builtin_tools()
    router = TaskRouter(reg)

    class G:
        _modules = {"task_router": router}

    g = G()

    # Real task: route metadata success (gate open)
    execute_capability_kind(
        g,
        "module",
        "task_router",
        {"structured_task": {"task_type": "text-gen", "objective": "live validation"}},
    )
    # Real task: TaskRouter direct (metrics + tie line)
    router.route_task("self_task", {"source": "live_validation"})

    # Health probe: must stay failed without payload
    execute_capability_kind(
        g,
        "module",
        "task_router",
        {
            "structured_task": {
                "task_type": "routing_probe",
                "_guardian_router_health_probe": True,
                "objective": "health",
            }
        },
    )

    text = OUT.read_text(encoding="utf-8")
    need = [
        "task_router real_task",
        "ok_gate=True",
        "success_source=route_metadata",
        "task_router health_probe",
        "ok_gate=False",
        "route_metadata_ignored_for_ok",
        "[TaskRouter] real_task_route",
        "tied_at_winner",
    ]
    missing = [s for s in need if s not in text]
    if missing:
        print("FAIL missing:", missing, file=sys.stderr)
        return 1
    print(f"OK wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
