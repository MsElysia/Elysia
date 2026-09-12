# project_guardian/tests/test_safe_stack_gitignore.py
"""Static guards: safe-stack generated runtime data must stay out of git."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GITIGNORE = REPO_ROOT / ".gitignore"


@pytest.fixture(scope="module")
def gitignore_text() -> str:
    assert GITIGNORE.is_file(), "missing .gitignore at repo root"
    return GITIGNORE.read_text(encoding="utf-8")


def _git_ignores(relative_path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", relative_path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _has_line_or_tree_rule(text: str, line: str, *, tree_prefix: str) -> bool:
    """Pattern present as its own rule, or covered by an ignore-directory rule."""
    stripped = {ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")}
    if line in stripped:
        return True
    return tree_prefix.rstrip("/") + "/" in stripped


def test_gitignore_contains_data_runtime_or_equivalent(gitignore_text: str) -> None:
    assert _has_line_or_tree_rule(gitignore_text, "data/runtime/", tree_prefix="data/runtime")


def test_gitignore_covers_data_runtime_conversations(gitignore_text: str) -> None:
    assert (
        "data/runtime/conversations/" in gitignore_text
        or "data/runtime/conversations" in gitignore_text
        or _has_line_or_tree_rule(gitignore_text, "data/runtime/", tree_prefix="data/runtime")
    )
    assert _git_ignores("data/runtime/conversations/panel.jsonl")


def test_gitignore_covers_data_runtime_jsonl_or_equivalent(gitignore_text: str) -> None:
    assert (
        "data/runtime/*.jsonl" in gitignore_text
        or _has_line_or_tree_rule(gitignore_text, "data/runtime/", tree_prefix="data/runtime")
    )
    assert _git_ignores("data/runtime/operator_confirmations.jsonl")


def test_gitignore_covers_brain_last_pipeline_json(gitignore_text: str) -> None:
    assert (
        "data/runtime/brain_last_pipeline.json" in gitignore_text
        or _git_ignores("data/runtime/brain_last_pipeline.json")
    )


def test_gitignore_covers_operator_confirmations_jsonl(gitignore_text: str) -> None:
    assert (
        "data/runtime/operator_confirmations.jsonl" in gitignore_text
        or _git_ignores("data/runtime/operator_confirmations.jsonl")
    )


def test_gitignore_covers_self_improvement_proposals_jsonl(gitignore_text: str) -> None:
    assert (
        "data/runtime/self_improvement_proposals.jsonl" in gitignore_text
        or _git_ignores("data/runtime/self_improvement_proposals.jsonl")
    )


def test_gitignore_covers_deployments(gitignore_text: str) -> None:
    assert _has_line_or_tree_rule(gitignore_text, "deployments/", tree_prefix="deployments")
    assert _git_ignores("deployments/example-id/slave_config.json")


def test_gitignore_covers_tmp_out_and_err(gitignore_text: str) -> None:
    assert "tmp_*.out" in gitignore_text
    assert "tmp_*.err" in gitignore_text
    assert _git_ignores("tmp_smoke.out")
    assert _git_ignores("tmp_smoke.err")


def test_gitignore_covers_mypy_and_ruff_cache(gitignore_text: str) -> None:
    assert ".mypy_cache/" in gitignore_text
    assert ".ruff_cache/" in gitignore_text
    assert _git_ignores(".mypy_cache/missing")
    assert _git_ignores(".ruff_cache/missing")
