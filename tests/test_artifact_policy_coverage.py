"""Meta-tests to ensure artifact/no-side-effects coverage for task types and gateway actions.

If new task types or gateway actions are introduced without corresponding tests,
these tests will fail with actionable output.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Set, Dict

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = PROJECT_ROOT / "project_guardian" / "core.py"
TRUST_PATH = PROJECT_ROOT / "project_guardian" / "trust.py"
TESTS_ROOT = PROJECT_ROOT / "tests"


def _collect_task_types_from_core() -> Set[str]:
    """Collect whitelisted task types from core.py via AST + conservative defaults.

    Strategy:
    - Parse core.py
    - Look for string constants used in comparisons against `task_type`
    - Seed with known minimal set to avoid missing existing types
    """
    src = CORE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)

    task_types: Set[str] = set()

    # Seed with known minimal set so historical behavior is locked
    baseline = {"RUN_ACCEPTANCE", "CLEAR_CURRENT_TASK", "APPLY_MUTATION"}
    task_types.update(baseline)

    class TaskTypeVisitor(ast.NodeVisitor):
        def visit_Compare(self, node: ast.Compare) -> None:  # type: ignore[override]
            # Patterns like: task_type not in ["RUN_ACCEPTANCE", ...]
            # or task_type == "RUN_ACCEPTANCE"
            left = node.left
            if isinstance(left, ast.Name) and left.id == "task_type":
                for comp in node.comparators:
                    if isinstance(comp, (ast.List, ast.Tuple, ast.Set)):
                        for elt in comp.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                if elt.value.isupper():
                                    task_types.add(elt.value)
                    elif isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                        if comp.value.isupper():
                            task_types.add(comp.value)
            self.generic_visit(node)

    TaskTypeVisitor().visit(tree)
    return task_types


def _collect_gateway_actions_from_trust() -> Dict[str, str]:
    """Collect gateway action constants from trust.py.

    Returns mapping name -> value (string).
    """
    import importlib

    trust_mod = importlib.import_module("project_guardian.trust")

    actions: Dict[str, str] = {}
    # Prefer known canonical names, but also pick up any additional ALL_CAPS string constants
    preferred = {"NETWORK_ACCESS", "FILE_WRITE", "SUBPROCESS_EXECUTION", "GOVERNANCE_MUTATION"}

    for name in dir(trust_mod):
        if not name.isupper():
            continue
        value = getattr(trust_mod, name)
        if isinstance(value, str) and (name in preferred or name.endswith("_ACCESS") or name.endswith("_EXECUTION") or name.endswith("_MUTATION")):
            actions[name] = value

    return actions


def _scan_tests_for_tokens(tokens: Set[str]) -> Dict[str, Set[Path]]:
    """Scan tests/ for presence of each token (substring match).

    Returns mapping token -> set of files where it appears.
    """
    coverage: Dict[str, Set[Path]] = {t: set() for t in tokens}

    for path in TESTS_ROOT.rglob("test_*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for token in tokens:
            if token in text:
                coverage[token].add(path.relative_to(PROJECT_ROOT))

    return coverage


@pytest.mark.meta
def test_task_types_are_covered_by_policy_tests():
    """Every whitelisted task type must appear in at least one artifact/no-side-effects test.

    Coverage is satisfied if the task type string appears in any test file under tests/.
    This is conservative: adding a new task type without touching tests will fail here.
    """
    task_types = _collect_task_types_from_core()
    assert task_types, "No task types discovered in core.py; meta-test cannot enforce coverage."

    coverage = _scan_tests_for_tokens(task_types)

    missing = {t for t, files in coverage.items() if not files}
    if missing:
        lines = [
            "Missing artifact/no-side-effects coverage for task types:",
            *(f"  - {t}" for t in sorted(missing)),
            "Searched in tests/ under:",
            f"  {TESTS_ROOT}",
            "Hint: add/update artifact/no-side-effects tests that mention these task type strings.",
        ]
        pytest.fail("\n".join(lines))


@pytest.mark.meta
def test_gateway_actions_are_covered_by_policy_tests():
    """Every gateway action constant must be mentioned in at least one policy/no-side-effects test.

    Coverage is satisfied if either the constant name or its string value appears
    in any test file under tests/.
    """
    actions = _collect_gateway_actions_from_trust()
    assert actions, "No gateway actions discovered in trust.py; meta-test cannot enforce coverage."

    # Tokens to search: constant names and their string values (e.g., SUBPROCESS_EXECUTION, "subprocess_execution")
    tokens: Set[str] = set(actions.keys()) | set(actions.values())

    coverage = _scan_tests_for_tokens(tokens)

    missing: Dict[str, Set[str]] = {}
    for const_name, value in actions.items():
        # Consider action covered if either name or value appears somewhere
        files_for_name = coverage.get(const_name, set())
        files_for_value = coverage.get(value, set())
        if not files_for_name and not files_for_value:
            missing[const_name] = {"<no files>"}

    if missing:
        lines = [
            "Missing artifact/no-side-effects coverage for gateway actions:",
        ]
        for const_name in sorted(missing):
            lines.append(f"  - {const_name} (value={actions[const_name]!r})")
        lines.extend(
            [
                "Searched in tests/ under:",
                f"  {TESTS_ROOT}",
                "Hint: add/update artifact/no-side-effects tests mentioning these action constants or their string values.",
            ]
        )
        pytest.fail("\n".join(lines))

