#!/usr/bin/env python3
"""
Emit post-fix tool_registry_pulse / registry_router_health_probe log lines to a fresh file.

Run from project root:  python scripts/validate_tool_registry_pulse_postfix.py

Confirms (without full Elysia startup) that log formats match project_guardian.core exploration paths.
Output: data/tool_registry_pulse_validation.log
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUT_LOG = DATA_DIR / "tool_registry_pulse_validation.log"


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT / "core_modules" / "elysia_core_comprehensive"))

    from ai_tool_registry import TaskRouter, ToolRegistry
    from project_guardian.core import GuardianCore

    root = logging.getLogger("project_guardian.core")
    root.handlers.clear()
    root.setLevel(logging.INFO)
    fh = logging.FileHandler(OUT_LOG, mode="w", encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    root.addHandler(fh)
    # Also echo so CI / terminal sees pass/fail
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(sh)

    tr = ToolRegistry()
    tr.ensure_minimal_builtin_tools()
    router = TaskRouter(tr)

    class _M:
        def get_active_missions(self):
            return []

    g = GuardianCore.__new__(GuardianCore)
    g._modules = {"tool_registry": tr, "task_router": router}
    g.missions = _M()
    g._pre_decision_context = {}

    n, _names, diag = GuardianCore._tool_registry_pulse_metrics(g, tr)
    surf = diag.get("surface") if isinstance(diag.get("surface"), dict) else {}
    excl = diag.get("exclusion_hint") or surf.get("filter_reason") or ""
    if excl == "ok":
        excl = ""
    # Must match exploration branch in project_guardian/core.py (tool_registry_pulse)
    root.info(
        "[Exploration] tool_registry_pulse diag id=%s cls=%s raw_list_len=%s map=%s usable=%s "
        "return_type=%s raw_first=%s coerced_first=%s filter=%s coerce=%s",
        diag.get("registry_id"),
        diag.get("registry_class"),
        diag.get("raw_list_tools_len"),
        diag.get("raw_tools_map_count"),
        n,
        diag.get("list_tools_return_type"),
        diag.get("raw_first_names"),
        diag.get("first_names"),
        excl or "(none)",
        (diag.get("coerce_suffix") or "")[:160],
    )

    task = GuardianCore._structured_router_probe_task(g)
    r = router.route_task(task["task_type"], task)
    route_to = r.get("routed_to") if isinstance(r, dict) else None
    route_hint = f" route_registry_health->{route_to}"
    tied = r.get("diagnostic_tied_tools_at_winner_score") if isinstance(r, dict) else None
    pick_rule = (r.get("diagnostic_pick_rule") or "") if isinstance(r, dict) else ""
    root.info(
        "[Exploration] registry_router_health_probe (task_type=routing_probe) "
        "reply routed_to=%s score=%s tied_at_winner_score=%s pick_rule=%s "
        "(health check only — no web/exec execution; tie-break policy, not tool visibility)",
        route_to,
        r.get("score") if isinstance(r, dict) else None,
        tied,
        pick_rule,
    )
    root.info("[Exploration] tool_registry_pulse: %d usable tools%s", n, route_hint)

    text = OUT_LOG.read_text(encoding="utf-8")
    required = [
        "[Exploration] tool_registry_pulse diag",
        "usable=",
        "[Exploration] tool_registry_pulse:",
        "usable tools",
        "registry_router_health_probe (task_type=routing_probe)",
        "tie-break policy, not tool visibility",
    ]
    missing = [s for s in required if s not in text]
    if missing:
        print("FAIL missing substrings:", missing, file=sys.stderr)
        return 1
    print(f"OK wrote {OUT_LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
