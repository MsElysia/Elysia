#!/usr/bin/env python3
"""
Generate static activation matrix for Project Guardian modules.

The matrix estimates import reachability from:
- Main launcher path: run_elysia_unified.py -> elysia.py
- Orchestrator path: project_guardian/__main__.py
- API path: project_guardian/api_server.py
"""

from __future__ import annotations

import argparse
import ast
import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Set


@dataclass(frozen=True)
class ActivationRow:
    module: str
    booted_from_elysia: int
    booted_from_orchestrator: int
    api_on_demand_only: int
    currently_unwired: int


def _is_intentional_non_runtime_module(module_path: str) -> bool:
    """True when a module is intentionally excluded from runtime wiring."""
    rel = module_path.replace("\\", "/")
    if "elysia_cursor_ready_updated (1)/" in rel:
        return True
    if rel.endswith("/__init__.py"):
        return True
    if rel.endswith("example.py") or rel.endswith("example_advanced.py"):
        return True
    if rel == "project_guardian/orchestration/judge/base.py":
        return True
    return False


def _module_aliases(root: Path, file_path: Path) -> Set[str]:
    rel = file_path.relative_to(root)
    aliases: Set[str] = set()

    if rel.parts[0] == "project_guardian":
        if rel.name == "__init__.py":
            pkg = ".".join(rel.parts[:-1])
            if pkg:
                aliases.add(pkg)
                aliases.add(pkg.replace("project_guardian.", ""))
        else:
            canonical = ".".join(rel.with_suffix("").parts)
            short = canonical.replace("project_guardian.", "")
            aliases.add(canonical)
            aliases.add(short)
            aliases.add(rel.stem)
    else:
        aliases.add(rel.stem)
    return aliases


def _package_parts(root: Path, file_path: Path) -> List[str]:
    rel = file_path.relative_to(root)
    if rel.parts[0] != "project_guardian":
        return []
    if rel.name == "__init__.py":
        return list(rel.parts[:-1])
    return list(rel.with_suffix("").parts[:-1])


def _resolve_from_import(root: Path, file_path: Path, module: str, level: int) -> str:
    pkg = _package_parts(root, file_path)
    if level > 0:
        keep = max(0, len(pkg) - level + 1)
        pkg = pkg[:keep]
    if module:
        if level > 0:
            return ".".join(pkg + module.split("."))
        return module
    return ".".join(pkg)


def _imports_in_file(root: Path, file_path: Path) -> Set[str]:
    imports: Set[str] = set()
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from_import(root, file_path, node.module or "", node.level or 0)
            if base:
                imports.add(base)
            for alias in node.names:
                if alias.name == "*":
                    continue
                imports.add(f"{base}.{alias.name}" if base else alias.name)
    return imports


def _resolve_import_target(module_to_file: Dict[str, Path], import_name: str) -> Path | None:
    if import_name in module_to_file:
        return module_to_file[import_name]
    parts = import_name.split(".")
    for i in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in module_to_file:
            return module_to_file[candidate]
    return None


def _traverse(starts: Iterable[Path], imports_map: Dict[Path, Set[str]], module_to_file: Dict[str, Path]) -> Set[Path]:
    seen: Set[Path] = set()
    queue: List[Path] = [p.resolve() for p in starts if p.exists()]
    while queue:
        current = queue.pop(0).resolve()
        if current in seen:
            continue
        seen.add(current)
        for imp in imports_map.get(current, set()):
            target = _resolve_import_target(module_to_file, imp)
            if target and target not in seen:
                queue.append(target)
    return seen


def build_matrix(root: Path) -> List[ActivationRow]:
    pg_dir = root / "project_guardian"
    pg_files = sorted(
        p.resolve()
        for p in pg_dir.rglob("*.py")
        if "tests" not in p.parts and "__pycache__" not in p.parts
    )

    scope = set(pg_files)
    scope.update(p.resolve() for p in root.glob("elysia*.py"))
    launcher = root / "run_elysia_unified.py"
    if launcher.exists():
        scope.add(launcher.resolve())
    scope_files = sorted(scope)

    module_to_file: Dict[str, Path] = {}
    for file_path in scope_files:
        for alias in _module_aliases(root, file_path):
            module_to_file.setdefault(alias, file_path)

    imports_map = {p: _imports_in_file(root, p) for p in scope_files}

    elysia_reach = _traverse(
        [root / "run_elysia_unified.py", root / "elysia.py"],
        imports_map,
        module_to_file,
    )
    orchestrator_reach = _traverse(
        [root / "project_guardian" / "__main__.py"],
        imports_map,
        module_to_file,
    )
    api_reach = _traverse(
        [root / "project_guardian" / "api_server.py"],
        imports_map,
        module_to_file,
    )

    rows: List[ActivationRow] = []
    for path in pg_files:
        b_elysia = int(path in elysia_reach)
        b_orch = int(path in orchestrator_reach)
        b_api_only = int(path in api_reach and not b_elysia and not b_orch)
        module_rel = str(path.relative_to(root)).replace("\\", "/")
        technically_unwired = int(not (b_elysia or b_orch or path in api_reach))
        unwired = int(
            technically_unwired and not _is_intentional_non_runtime_module(module_rel)
        )
        rows.append(
            ActivationRow(
                module=module_rel,
                booted_from_elysia=b_elysia,
                booted_from_orchestrator=b_orch,
                api_on_demand_only=b_api_only,
                currently_unwired=unwired,
            )
        )
    return rows


def write_csv(rows: List[ActivationRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "module",
                "booted_from_elysia",
                "booted_from_orchestrator",
                "api_on_demand_only",
                "currently_unwired",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.module,
                    row.booted_from_elysia,
                    row.booted_from_orchestrator,
                    row.api_on_demand_only,
                    row.currently_unwired,
                ]
            )


def _unwired_rows(rows: List[ActivationRow]) -> List[ActivationRow]:
    return [row for row in rows if row.currently_unwired == 1]


def _excluded_non_runtime_rows(rows: List[ActivationRow]) -> List[ActivationRow]:
    excluded: List[ActivationRow] = []
    for row in rows:
        technically_unwired = not (
            row.booted_from_elysia or row.booted_from_orchestrator or row.api_on_demand_only
        )
        if technically_unwired and _is_intentional_non_runtime_module(row.module):
            excluded.append(row)
    return excluded


def _folder_bucket(module_path: str) -> str:
    rel = module_path.replace("\\", "/")
    prefix = "project_guardian/"
    if rel.startswith(prefix):
        rel = rel[len(prefix) :]
    parts = rel.split("/")
    if len(parts) <= 1:
        return "(root)"
    return parts[0] or "(root)"


def write_unwired_by_folder_csv(rows: List[ActivationRow], output_path: Path) -> None:
    folder_map: Dict[str, List[str]] = defaultdict(list)
    for row in _unwired_rows(rows):
        folder_map[_folder_bucket(row.module)].append(row.module)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["folder", "unwired_count", "sample_modules"])
        for folder in sorted(folder_map):
            modules = sorted(folder_map[folder])
            sample = "; ".join(modules[:5])
            writer.writerow([folder, len(modules), sample])


def _priority_for_module(module: str) -> tuple[str, str]:
    rel = module.replace("\\", "/")

    if rel == "project_guardian/orchestration/judge/base.py":
        return "low", "protocol contract module"
    if "elysia_cursor_ready_updated (1)/" in rel:
        return "low", "legacy snapshot subtree"
    if rel.endswith("/__init__.py"):
        return "low", "package marker"
    if rel.endswith("example.py") or rel.endswith("example_advanced.py"):
        return "low", "example-only module"

    high_exact = {
        "project_guardian/mutation_router.py",
        "project_guardian/mutation_review_manager.py",
        "project_guardian/mutation_publisher.py",
        "project_guardian/mutation_sandbox.py",
        "project_guardian/webscout_agent.py",
        "project_guardian/task_assignment_engine.py",
        "project_guardian/tool_executor.py",
        "project_guardian/recovery_vault.py",
        "project_guardian/guardian_layer.py",
        "project_guardian/implementer/implementer_core.py",
    }
    if rel in high_exact:
        return "high", "core workflow candidate"

    if rel.startswith("project_guardian/implementer/"):
        return "medium", "implementer stack member"
    if rel.startswith("project_guardian/proposal_") or rel.endswith("/proposal_system.py"):
        return "medium", "proposal workflow surface"
    if rel.startswith("project_guardian/ui/"):
        return "medium", "ui surface not on boot path"

    medium_exact = {
        "project_guardian/ai_mutation_validator.py",
        "project_guardian/income_executor.py",
        "project_guardian/intelligent_task_distribution.py",
        "project_guardian/slave_deployment.py",
        "project_guardian/digital_safehouse.py",
        "project_guardian/dream_engine.py",
    }
    if rel in medium_exact:
        return "medium", "runtime-adjacent operational module"

    return "low", "utility/optional path"


def write_unwired_priority_csv(rows: List[ActivationRow], output_path: Path) -> None:
    unwired = _unwired_rows(rows)
    ranked = []
    for row in unwired:
        priority, reason = _priority_for_module(row.module)
        ranked.append((priority, reason, row))

    order = {"high": 0, "medium": 1, "low": 2}
    ranked.sort(key=lambda x: (order.get(x[0], 9), x[2].module))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "priority",
                "reason",
                "module",
                "booted_from_elysia",
                "booted_from_orchestrator",
                "api_on_demand_only",
                "currently_unwired",
            ]
        )
        for priority, reason, row in ranked:
            writer.writerow(
                [
                    priority,
                    reason,
                    row.module,
                    row.booted_from_elysia,
                    row.booted_from_orchestrator,
                    row.api_on_demand_only,
                    row.currently_unwired,
                ]
            )


def _wiring_plan_fields(row: ActivationRow) -> tuple[str, str, str, str]:
    module = row.module.replace("\\", "/")

    if "elysia_cursor_ready_updated (1)/" in module:
        return (
            "none",
            "skip",
            "(none)",
            "legacy snapshot subtree; avoid wiring into active runtime",
        )
    if module.endswith("/__init__.py"):
        return (
            "none",
            "skip",
            "(none)",
            "package marker; no direct runtime wiring needed",
        )

    if module == "project_guardian/guardian_layer.py":
        return (
            "GuardianCore",
            "boot",
            "project_guardian/core.py",
            "fingerprint/email side effects; keep alerting behind config flags",
        )
    if module == "project_guardian/webscout_agent.py":
        return (
            "elysia.py integrated modules",
            "on-demand",
            "elysia_sub_modules.py",
            "network-heavy module; must remain opt-in and quota-limited",
        )
    if module == "project_guardian/task_assignment_engine.py":
        return (
            "SystemOrchestrator",
            "deferred",
            "project_guardian/system_orchestrator.py",
            "scheduling behavior changes; add guardrails before auto-routing",
        )
    if module in {
        "project_guardian/mutation_router.py",
        "project_guardian/mutation_review_manager.py",
        "project_guardian/mutation_publisher.py",
        "project_guardian/mutation_sandbox.py",
        "project_guardian/recovery_vault.py",
    }:
        return (
            "SystemOrchestrator compatibility surfaces",
            "on-demand",
            "project_guardian/system_orchestrator.py",
            "mutation path is high-risk; require explicit approval gates",
        )
    if module.startswith("project_guardian/implementer/"):
        return (
            "SystemOrchestrator",
            "on-demand",
            "project_guardian/system_orchestrator.py",
            "codegen/file-write flow; isolate to proposal-approved operations",
        )
    if module.startswith("project_guardian/proposal_") or module.endswith("/proposal_system.py"):
        return (
            "API server + SystemOrchestrator",
            "on-demand",
            "project_guardian/api_server.py",
            "introduces new external control plane routes; validate auth boundaries",
        )
    if module.startswith("project_guardian/ui/"):
        return (
            "api_server UI launcher",
            "on-demand",
            "project_guardian/api_server.py",
            "web surface expansion; enforce CORS/auth and read-only defaults first",
        )
    if module in {
        "project_guardian/tool_executor.py",
        "project_guardian/income_executor.py",
        "project_guardian/intelligent_task_distribution.py",
        "project_guardian/digital_safehouse.py",
        "project_guardian/dream_engine.py",
        "project_guardian/ai_mutation_validator.py",
        "project_guardian/slave_deployment.py",
    }:
        return (
            "SystemOrchestrator",
            "on-demand",
            "project_guardian/system_orchestrator.py",
            "operational surface; add feature flags + health checks before enabling",
        )

    return (
        "none",
        "skip",
        "(none)",
        "optional utility/example path; no immediate runtime wiring required",
    )


def write_wiring_plan_csv(rows: List[ActivationRow], output_path: Path) -> None:
    unwired = _unwired_rows(rows)
    plan_rows = []
    order = {"high": 0, "medium": 1, "low": 2}
    for row in unwired:
        priority, reason = _priority_for_module(row.module)
        surface, mode, target, risk = _wiring_plan_fields(row)
        plan_rows.append((priority, reason, row.module, surface, mode, target, risk))

    plan_rows.sort(key=lambda x: (order.get(x[0], 9), x[2]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "priority",
                "reason",
                "module",
                "recommended_integration_surface",
                "activation_mode",
                "first_patch_target_file",
                "risk_note",
            ]
        )
        for item in plan_rows:
            writer.writerow(list(item))


def write_excluded_non_runtime_csv(rows: List[ActivationRow], output_path: Path) -> None:
    excluded = []
    for row in _excluded_non_runtime_rows(rows):
        priority, reason = _priority_for_module(row.module)
        excluded.append((priority, reason, row.module))

    order = {"high": 0, "medium": 1, "low": 2}
    excluded.sort(key=lambda x: (order.get(x[0], 9), x[2]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["priority", "reason", "module"])
        for item in excluded:
            writer.writerow(list(item))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate static activation matrix CSV.")
    parser.add_argument(
        "--output",
        default="data/activation_matrix.csv",
        help="Output CSV path relative to repo root.",
    )
    parser.add_argument(
        "--unwired-output",
        default="data/activation_unwired.csv",
        help="Output CSV path for only currently unwired modules.",
    )
    parser.add_argument(
        "--unwired-by-folder-output",
        default="data/activation_unwired_by_folder.csv",
        help="Output CSV path for currently unwired modules grouped by folder.",
    )
    parser.add_argument(
        "--unwired-priority-output",
        default="data/activation_unwired_priority.csv",
        help="Output CSV path for currently unwired modules ranked by priority.",
    )
    parser.add_argument(
        "--wiring-plan-output",
        default="data/activation_wiring_plan.csv",
        help="Output CSV path for recommended runtime wiring plan.",
    )
    parser.add_argument(
        "--excluded-output",
        default="data/activation_unwired_excluded.csv",
        help="Output CSV path for intentionally excluded non-runtime modules.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    rows = build_matrix(root)
    output_path = (root / args.output).resolve()
    write_csv(rows, output_path)
    unwired_output_path = (root / args.unwired_output).resolve()
    write_csv(_unwired_rows(rows), unwired_output_path)
    unwired_by_folder_output_path = (root / args.unwired_by_folder_output).resolve()
    write_unwired_by_folder_csv(rows, unwired_by_folder_output_path)
    unwired_priority_output_path = (root / args.unwired_priority_output).resolve()
    write_unwired_priority_csv(rows, unwired_priority_output_path)
    wiring_plan_output_path = (root / args.wiring_plan_output).resolve()
    write_wiring_plan_csv(rows, wiring_plan_output_path)
    excluded_output_path = (root / args.excluded_output).resolve()
    write_excluded_non_runtime_csv(rows, excluded_output_path)

    total = len(rows)
    b_elysia = sum(r.booted_from_elysia for r in rows)
    b_orch = sum(r.booted_from_orchestrator for r in rows)
    b_api = sum(r.api_on_demand_only for r in rows)
    b_unwired = sum(r.currently_unwired for r in rows)
    b_excluded = len(_excluded_non_runtime_rows(rows))
    b_tech_unwired = b_unwired + b_excluded
    print(f"Wrote activation matrix: {output_path}")
    print(f"Wrote currently-unwired matrix: {unwired_output_path}")
    print(f"Wrote unwired-by-folder summary: {unwired_by_folder_output_path}")
    print(f"Wrote unwired priority ranking: {unwired_priority_output_path}")
    print(f"Wrote activation wiring plan: {wiring_plan_output_path}")
    print(f"Wrote excluded unwired list: {excluded_output_path}")
    print(f"project_guardian_modules={total}")
    print(f"booted_from_elysia={b_elysia}")
    print(f"booted_from_orchestrator={b_orch}")
    print(f"api_on_demand_only={b_api}")
    print(f"currently_unwired={b_unwired}")
    print(f"excluded_non_runtime_unwired={b_excluded}")
    print(f"technically_unwired_total={b_tech_unwired}")


if __name__ == "__main__":
    main()

