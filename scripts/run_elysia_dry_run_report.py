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
from typing import Any, Dict, List, Optional

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


def build_text_report(batch: Dict[str, Any], problems: List[str]) -> str:
    lines: List[str] = []
    lines.append("Elysia safe dry-run report")
    lines.append("=" * 40)
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


def run_report(*, cycles: int = HARD_MAX_CYCLES) -> Dict[str, Any]:
    """Run the bounded dry-run batch and return (batch, problems) as a dict."""
    requested = min(int(cycles), HARD_MAX_CYCLES)
    if requested < 0:
        requested = 0
    batch = run_phase1_dry_run_batch(
        _make_stub_cycle,
        max_cycles=HARD_MAX_CYCLES,
        requested_cycles=requested,
    )
    problems = evaluate_batch_safety(batch)
    return {"batch": batch, "problems": problems, "safe": not problems}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run a bounded Elysia dry-run batch and print a report.")
    parser.add_argument(
        "--cycles",
        type=int,
        default=HARD_MAX_CYCLES,
        help=f"number of bounded dry-run cycles (hard-capped at {HARD_MAX_CYCLES})",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON output")
    args = parser.parse_args(argv)

    try:
        result = run_report(cycles=args.cycles)
    except DryRunBatchSafetyError as exc:
        if args.json:
            print(json.dumps({"safe": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"final safety verdict: UNSAFE\nerror: {exc}")
        return 2

    batch = result["batch"]
    problems = result["problems"]

    if args.json:
        print(json.dumps(result, ensure_ascii=False, default=str))
    else:
        print(build_text_report(batch, problems))

    return 0 if result["safe"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
