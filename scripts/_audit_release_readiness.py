#!/usr/bin/env python3
"""One-off audit helper for SAFE_STACK_RELEASE_READINESS_AUDIT (not CI)."""
from __future__ import annotations

import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def normalize_path(path: str) -> str:
    return path.strip().strip('"').strip("'").replace("\\", "/")


def bucket(path: str) -> str:
    p = normalize_path(path)
    if p.startswith("data/") or p.startswith("deployments/") or p.startswith("REPORTS/"):
        return "runtime_data"
    if any(x in p for x in ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache")):
        return "caches"
    safe_prod_keys = (
        "safe_stack",
        "governance/",
        "operator_confirmation",
        "live_execution_guard",
        "live_execution_audit",
        "live_execution_runtime",
        "conversation_store",
        "memory_ranking/",
        "prompt_contracts/",
        "self_improvement/",
        "trace_visibility",
        "brain/live_execution",
        "brain/trace_visibility",
        "brain/tda_trace",
        "brain/pipeline",
        "brain/runtime",
        "brain/config",
        "brain/think_decide_act",
    )
    if p.startswith("project_guardian/") and any(k in p for k in safe_prod_keys):
        return "prod_safe_stack"
    if p in ("elysia/api/server.py", "project_guardian/ui_control_panel.py"):
        return "prod_safe_stack"
    if "maintenance/one_shot" in p or p == "scripts/run_safe_stack_smoke_tests.py":
        return "scripts_ci_safe_stack"
    if p.startswith(".github/workflows/") and "safe-stack" in p:
        return "scripts_ci_safe_stack"
    if p.startswith("docs/") and any(
        m in p
        for m in (
            "SAFE_STACK",
            "LIVE_EXECUTION",
            "API_HOST_FINAL",
            "CONTROL_PANEL_CONVERSATION",
            "SELF_IMPROVEMENT",
            "OPERATOR_CONFIRMATION",
            "ELYSIA_ARCHITECTURE",
        )
    ):
        return "docs_safe_stack"
    if p.startswith("docs/"):
        return "docs_other"
    if p in ("config/brain_pipeline.json", "config/memory_ranking.json"):
        return "config_safe_stack"
    if p.startswith("config/"):
        return "config_other"
    if "/tests/test_" in p and any(
        k in p
        for k in (
            "conversation_store",
            "control_panel",
            "brain_trace",
            "brain_tda",
            "self_improvement",
            "prompt_contract",
            "memory_ranking",
            "api_host_route",
            "safe_stack",
            "operator_chat",
            "live_execution",
            "operator_confirmation",
            "one_shot_ui",
            "tda_trace",
        )
    ):
        return "tests_safe_stack"
    if p.startswith("project_guardian/tests/") or p.startswith("tests/"):
        return "tests_other"
    if p.startswith("project_guardian/") or p.startswith("elysia/"):
        return "prod_unrelated"
    if p.startswith("core_modules/"):
        return "prod_unrelated"
    if p.endswith((".bat", ".cmd", ".ps1")):
        return "launchers"
    if p.startswith("scripts/"):
        return "scripts_other"
    return "other"


def _git_lines(args: list[str]) -> list[str]:
    return subprocess.check_output(["git", *args], text=True, cwd=ROOT).splitlines()


def main() -> None:
    status_lines = _git_lines(["status", "--short"])
    untracked = _git_lines(["ls-files", "--others", "--exclude-standard"])
    diff = _git_lines(["diff", "--name-only"])

    modified: list[str] = []
    untracked_status: list[str] = []
    for line in status_lines:
        line = line.rstrip("\r\n")
        if len(line) < 4:
            continue
        path = normalize_path(line[3:])
        if line.startswith("??"):
            untracked_status.append(path)
        else:
            modified.append(path)
    untracked_all = list(dict.fromkeys([*untracked, *untracked_status]))

    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"modified": 0, "untracked": 0, "diff": 0})
    for p in modified:
        if p:
            counts[bucket(p)]["modified"] += 1
    for p in untracked_all:
        if p:
            counts[bucket(p)]["untracked"] += 1
    for p in diff:
        if p:
            counts[bucket(p)]["diff"] += 1

    print(f"parsed modified={len(modified)} untracked={len(untracked_all)} diff={len(diff)}")
    print("bucket | modified | untracked | diff")
    for k in sorted(counts):
        v = counts[k]
        if sum(v.values()):
            print(f"{k:24} {v['modified']:8} {v['untracked']:9} {v['diff']:4}")

    for label, paths in (
        ("SAFE_STACK prod (untracked)", [p for p in untracked_all if bucket(p) == "prod_safe_stack"]),
        ("SAFE_STACK prod (modified+diff)", sorted({p for p in modified + diff if bucket(p) == "prod_safe_stack"})),
        ("SAFE_STACK tests (untracked)", [p for p in untracked_all if bucket(p) == "tests_safe_stack"]),
        ("SAFE_STACK docs (untracked)", [p for p in untracked_all if bucket(p) == "docs_safe_stack"]),
    ):
        print(f"\n{label} ({len(paths)})")
        for p in paths[:40]:
            print(f"  {p}")
        if len(paths) > 40:
            print(f"  ... +{len(paths) - 40}")


if __name__ == "__main__":
    main()
