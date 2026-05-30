#!/usr/bin/env python3
"""Safe operator command: run a bounded Phase 1 dry-run batch and print a report.

This is the first practical "run Elysia safely" command. It executes ZERO tools or
actions: it does not enable autonomy, does not start the server, and does not call
WebScout/browser/proposal-implementation/mutation. It uses the committed bounded
dry-run helper (`run_phase1_dry_run_batch`) with a deterministic, in-memory stub
cycle built from the committed dry-run observation helpers. No files are written.

Exit code is 0 only when every safety invariant holds; nonzero otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from project_guardian.autonomy_dry_run_guard import (  # noqa: E402
    DryRunBatchSafetyError,
    build_dry_run_decision_report,
    build_dry_run_decision_trace,
    run_phase1_dry_run_batch,
    summarize_dry_run_decision_trace,
)

HARD_MAX_CYCLES = 3
VALID_MODES = ("stub", "real-planning")
_AUTONOMY_CONFIG_PATH = _REPO_ROOT / "config" / "autonomy.json"


def _make_stub_cycle() -> Dict[str, Any]:
    """Build one safe, deterministic Phase 1 dry-run cycle result (no execution)."""
    cycle_id = str(uuid.uuid4())
    trace = build_dry_run_decision_trace(
        cycle_id=cycle_id,
        source="run_elysia_dry_run_report",
        proposed_action="use_capability/observe",
        guard_meta={"allowed": False, "reasons": ["live_execution_disabled"]},
        extra_block_reasons=["dry_run_only"],
    )
    summary = summarize_dry_run_decision_trace(trace)
    out: Dict[str, Any] = {
        "executed": False,
        "action": "use_capability/observe",
        "reason": "dry_run_only",
        "dry_run": True,
        "cycle_id": cycle_id,
        "decision_trace": trace,
        "decision_trace_summary": summary,
    }
    out["dry_run_report"] = build_dry_run_decision_report(result=out, trace=trace, summary=summary)
    return out


def _assert_committed_config_disabled() -> None:
    """Fail closed unless committed config/autonomy.json has enabled=false."""
    try:
        committed = json.loads(_AUTONOMY_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - any read/parse failure must fail closed
        raise DryRunBatchSafetyError(f"cannot read committed autonomy config: {exc}")
    if committed.get("enabled") is True:
        raise DryRunBatchSafetyError(
            "config/autonomy.json is enabled; refusing real-planning dry-run"
        )


def _make_real_planning_cycle() -> Callable[[], Dict[str, Any]]:
    """Build a run_cycle that drives the committed Phase 1 dry-run planning path.

    Uses a minimal ``object.__new__(GuardianCore)`` instance with injected,
    dry-run-only, in-memory config/stubs (never touching config/autonomy.json or
    full app/server boot). The committed ``run_autonomous_cycle`` routes through
    ``run_autonomous_phase1_dry_run`` and produces the dry-run observation stack.
    """
    try:
        from project_guardian.core import GuardianCore
    except Exception as exc:  # noqa: BLE001 - import side effects must fail closed
        raise DryRunBatchSafetyError(f"GuardianCore cannot be safely imported: {exc}")

    def run_cycle() -> Dict[str, Any]:
        try:
            stub = object.__new__(GuardianCore)
        except Exception as exc:  # noqa: BLE001
            raise DryRunBatchSafetyError(f"GuardianCore cannot be safely instantiated: {exc}")

        # Isolated, in-memory, dry-run-only config (Phase 1 forces dry-run regardless).
        stub._load_autonomy_config = lambda: {  # type: ignore[attr-defined]
            "enabled": True,
            "dry_run_only": False,
            "allowed_actions": ["use_capability/observe"],
            "max_actions_per_hour": 40,
            "allow_dynamic_capability_actions": True,
        }
        stub.get_next_action = lambda: {  # type: ignore[attr-defined]
            "action": "use_capability/observe",
            "can_auto_execute": True,
            "metadata": {},
        }
        stub._load_mistral_decider_config = lambda: {}  # type: ignore[attr-defined]
        stub._autonomy_action_times = []  # type: ignore[attr-defined]
        return GuardianCore.run_autonomous_cycle(stub)

    return run_cycle


def _run_batch_for_mode(mode: str, *, requested: int) -> Dict[str, Any]:
    """Run the bounded batch for a given mode, guarding execution methods."""
    if mode == "stub":
        return run_phase1_dry_run_batch(
            _make_stub_cycle, max_cycles=HARD_MAX_CYCLES, requested_cycles=requested
        )

    # real-planning: fail closed before doing anything if committed config is enabled.
    _assert_committed_config_disabled()
    run_cycle = _make_real_planning_cycle()

    def _boom_capability(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("execute_capability_kind reached during dry-run real-planning")

    with patch(
        "project_guardian.capability_execution.execute_capability_kind",
        side_effect=_boom_capability,
    ):
        return run_phase1_dry_run_batch(
            run_cycle, max_cycles=HARD_MAX_CYCLES, requested_cycles=requested
        )


def evaluate_batch_safety(batch: Dict[str, Any]) -> List[str]:
    """Return a list of safety problems; empty list means the batch is safe."""
    problems: List[str] = []
    reports = batch.get("reports") or []
    if batch.get("all_dry_run") is not True:
        problems.append("not_all_dry_run")
    if batch.get("any_executed") is True:
        problems.append("execution_detected")
    if int(batch.get("execution_call_count", 0) or 0) != 0:
        problems.append("execution_call_count_nonzero")
    if batch.get("legacy_fallback_reached") is True:
        problems.append("legacy_fallback_reached")
    if batch.get("completed_cycles") != batch.get("requested_cycles"):
        problems.append("incomplete_cycles")
    for idx, report in enumerate(reports):
        if not isinstance(report, dict) or not report:
            problems.append(f"missing_report[{idx}]")
            continue
        if report.get("dry_run") is not True:
            problems.append(f"report_not_dry_run[{idx}]")
        if report.get("executed") is True:
            problems.append(f"report_executed[{idx}]")
        if report.get("blocked") is not True:
            problems.append(f"report_not_blocked[{idx}]")
    return problems


def build_text_report(batch: Dict[str, Any], problems: List[str], *, mode: str = "stub") -> str:
    lines: List[str] = []
    lines.append("Elysia safe dry-run report")
    lines.append("=" * 40)
    lines.append(f"mode: {mode}")
    lines.append(f"batch_id: {batch.get('batch_id', '')}")
    lines.append(
        f"cycles: requested={batch.get('requested_cycles')} completed={batch.get('completed_cycles')}"
    )
    lines.append(f"all_dry_run: {batch.get('all_dry_run')}")
    lines.append(f"any_executed: {batch.get('any_executed')}")
    lines.append(f"execution_call_count: {batch.get('execution_call_count')}")
    lines.append(f"legacy_fallback_reached: {batch.get('legacy_fallback_reached')}")
    lines.append("")
    lines.append("Per-cycle:")
    for idx, report in enumerate(batch.get("reports") or [], start=1):
        if not isinstance(report, dict):
            lines.append(f"  cycle {idx}: <invalid report>")
            continue
        lines.append(
            f"  cycle {idx}: kind={report.get('proposed_action_kind', '?')} "
            f"summary={report.get('proposed_action_summary', '')!r} "
            f"blocked={report.get('blocked')} executed={report.get('executed')}"
        )
    lines.append("")
    verdict = "SAFE" if not problems else "UNSAFE"
    lines.append(f"final safety verdict: {verdict}")
    if problems:
        lines.append("problems:")
        for p in problems:
            lines.append(f"  - {p}")
    lines.append("")
    lines.append("Note: no tools, capabilities, mutation, proposal implementation,")
    lines.append("WebScout, browser, server, or live execution were run.")
    return "\n".join(lines)


def run_report(*, cycles: int = HARD_MAX_CYCLES, mode: str = "stub") -> Dict[str, Any]:
    """Run the bounded dry-run batch and return {batch, problems, safe, mode}."""
    if mode not in VALID_MODES:
        raise DryRunBatchSafetyError(f"invalid mode: {mode!r}")
    requested = min(int(cycles), HARD_MAX_CYCLES)
    if requested < 0:
        requested = 0
    batch = _run_batch_for_mode(mode, requested=requested)
    problems = evaluate_batch_safety(batch)
    return {"mode": mode, "batch": batch, "problems": problems, "safe": not problems}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run a bounded Elysia dry-run batch and print a report.")
    parser.add_argument(
        "--cycles",
        type=int,
        default=HARD_MAX_CYCLES,
        help=f"number of bounded dry-run cycles (hard-capped at {HARD_MAX_CYCLES})",
    )
    parser.add_argument(
        "--mode",
        choices=list(VALID_MODES),
        default="stub",
        help="cycle source: 'stub' (default, deterministic) or 'real-planning' (committed dry-run path)",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON output")
    args = parser.parse_args(argv)

    try:
        result = run_report(cycles=args.cycles, mode=args.mode)
    except DryRunBatchSafetyError as exc:
        if args.json:
            print(json.dumps({"mode": args.mode, "safe": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"mode: {args.mode}\nfinal safety verdict: UNSAFE\nerror: {exc}")
        return 2

    batch = result["batch"]
    problems = result["problems"]

    if args.json:
        print(json.dumps(result, ensure_ascii=False, default=str))
    else:
        print(build_text_report(batch, problems, mode=result["mode"]))

    return 0 if result["safe"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
