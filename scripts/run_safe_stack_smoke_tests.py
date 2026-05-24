#!/usr/bin/env python3
"""Run the safe Elysia / Project Guardian architecture pytest slice.

Verifies conversation memory, brain trace visibility, TDA naming, self-improvement
proposals, prompt export, prompt contracts, and memory ranking — without enabling autonomy or live execution.

This is a focused smoke slice, not full CI. Tests use mocks/offline paths; no real LLM calls.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TEST_PATHS: Tuple[str, ...] = (
    "project_guardian/tests/test_conversation_store.py",
    "project_guardian/tests/test_control_panel_chat_memory.py",
    "project_guardian/tests/test_control_panel_legacy_history_retirement.py",
    "project_guardian/tests/test_control_panel_brain_visibility.py",
    "project_guardian/tests/test_control_panel_js_smoke.py",
    "project_guardian/tests/test_brain_trace_visibility.py",
    "project_guardian/tests/test_brain_tda_integration.py",
    "project_guardian/tests/test_self_improvement_proposal_queue.py",
    "project_guardian/tests/test_self_improvement_legacy_queue_retirement.py",
    "project_guardian/tests/test_self_improvement_prompt_export.py",
    "project_guardian/tests/test_prompt_contracts.py",
    "project_guardian/tests/test_prompt_contract_integration.py",
    "project_guardian/tests/test_memory_ranking.py",
    "project_guardian/tests/test_memory_ranking_visibility.py",
    "project_guardian/tests/test_prompt_contract_controls.py",
    "project_guardian/tests/test_api_host_route_parity.py",
    "project_guardian/tests/test_safe_stack_response_helpers.py",
    "project_guardian/tests/test_safe_stack_gitignore.py",
    "project_guardian/tests/test_operator_chat_helper.py",
    "project_guardian/tests/test_runtime_operator_chat_helper_integration.py",
    "project_guardian/tests/test_control_panel_operator_chat_helper_integration.py",
    "project_guardian/tests/test_control_panel_ui_clarity.py",
    "project_guardian/tests/test_one_shot_ui_scripts_quarantined.py",
    "project_guardian/tests/test_live_execution_governance_docs.py",
    "project_guardian/tests/test_live_execution_guard.py",
    "project_guardian/tests/test_live_execution_guard_runtime_integration.py",
    "project_guardian/tests/test_operator_confirmation_context_plan.py",
    "project_guardian/tests/test_operator_confirmation_store.py",
    "project_guardian/tests/test_operator_confirmation_guard_integration.py",
    "project_guardian/tests/test_operator_confirmation_visibility.py",
)

OPTIONAL_ALTERNATIVES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "TDA trace naming",
        (
            "project_guardian/tests/test_tda_trace_fields.py",
            "project_guardian/tests/test_tda_trace_naming.py",
        ),
    ),
    (
        "memory ranking imports",
        (
            "project_guardian/tests/test_memory_ranking_imports.py",
            "project_guardian/tests/test_memory_ranking_consolidation.py",
        ),
    ),
)

SAFETY_REMINDERS: Tuple[str, ...] = (
    "Autonomy is not tested or enabled by this script.",
    "Live execution is not tested or enabled by this script.",
    "This smoke slice is not full CI — run the full test suite separately.",
)


def declared_test_paths() -> List[str]:
    """All declared paths (required + every alternative candidate)."""
    paths = list(REQUIRED_TEST_PATHS)
    for _, candidates in OPTIONAL_ALTERNATIVES:
        paths.extend(candidates)
    return paths


def resolve_smoke_test_paths(repo_root: Path | None = None) -> List[str]:
    """Return ordered pytest paths (posix-style relative to repo root)."""
    root = repo_root or ROOT
    resolved: List[str] = []
    missing_required: List[str] = []

    for rel in REQUIRED_TEST_PATHS:
        if (root / rel).is_file():
            resolved.append(rel.replace("\\", "/"))
        else:
            missing_required.append(rel)

    if missing_required:
        raise FileNotFoundError(
            "Required smoke test file(s) missing:\n  "
            + "\n  ".join(missing_required)
        )

    for label, candidates in OPTIONAL_ALTERNATIVES:
        chosen: str | None = None
        for rel in candidates:
            if (root / rel).is_file():
                chosen = rel.replace("\\", "/")
                break
        if chosen is None:
            raise FileNotFoundError(
                f"No test file found for {label}. Tried:\n  "
                + "\n  ".join(candidates)
            )
        resolved.append(chosen)

    return resolved


def build_pytest_command(test_paths: Sequence[str], *, python: str | None = None) -> List[str]:
    exe = python or sys.executable
    return [exe, "-m", "pytest", *test_paths, "-q"]


def format_command(cmd: Sequence[str]) -> str:
    return " ".join(cmd)


def _print_reminders() -> None:
    print("\nReminders:")
    for line in SAFETY_REMINDERS:
        print(f"  • {line}")


def run_safe_stack_smoke_tests(
    *,
    repo_root: Path | None = None,
    python: str | None = None,
    list_only: bool = False,
) -> int:
    root = repo_root or ROOT
    try:
        test_paths = resolve_smoke_test_paths(root)
    except FileNotFoundError as exc:
        print("Safe stack smoke tests: FAILED (setup)", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        _print_reminders()
        return 2

    if list_only:
        for path in test_paths:
            print(path)
        _print_reminders()
        return 0

    cmd = build_pytest_command(test_paths, python=python)

    print("Elysia safe architecture stack — smoke tests")
    print("=" * 50)
    print("\nTest files included:")
    for path in test_paths:
        print(f"  - {path}")
    print("\nCommand:")
    print(f"  {format_command(cmd)}")
    print()

    result = subprocess.run(
        cmd,
        cwd=str(root),
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode == 0:
        print("\n--- pytest PASSED ---")
    else:
        print("\n--- pytest FAILED ---", file=sys.stderr)
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        print(f"\nExit code: {result.returncode}", file=sys.stderr)

    _print_reminders()
    return int(result.returncode)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=ROOT,
        help="Repository root (default: parent of scripts/).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List resolved test paths without running pytest.",
    )
    args = parser.parse_args(argv)
    return run_safe_stack_smoke_tests(
        repo_root=args.repo_root.resolve(),
        list_only=args.list,
    )


if __name__ == "__main__":
    raise SystemExit(main())
