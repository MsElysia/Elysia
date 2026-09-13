"""Static regression for Issue #39 exact-head CI reachability.

Dependency-light: parses the Autopilot workflow text without PyYAML so the
governance contract suite can prove trigger/permission/breaker invariants.

GitHub Actions branch globs treat '*' as not crossing '/'. Python's fnmatch
does cross '/', so this module uses a GitHub-faithful matcher for negatives.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "elysia-autopilot-ci.yml"


def _workflow_text() -> str:
    assert WORKFLOW.is_file(), f"missing workflow: {WORKFLOW}"
    return WORKFLOW.read_text(encoding="utf-8")


def _section_body(text: str, heading: str) -> str:
    """Return indented body under an `on:` child such as push:/pull_request:."""
    pattern = re.compile(
        rf"(?m)^  {re.escape(heading)}\n((?:(?:    .*)?\n)+)",
    )
    match = pattern.search(text)
    assert match, f"missing on.{heading} section"
    return match.group(1)


def _branch_patterns(section_body: str) -> list[str]:
    # Accept both quoted and unquoted YAML list entries.
    return re.findall(r"^\s+-\s+'?([^'\s#]+)'?", section_body, flags=re.M)


def github_branch_match(name: str, pattern: str) -> bool:
    """Match branch names using GitHub-like globs ('*' does not cross '/')."""
    if pattern == name:
        return True
    parts = pattern.split("/")
    name_parts = name.split("/")
    if len(parts) != len(name_parts):
        return False
    for part_pattern, part_name in zip(parts, name_parts):
        regex = re.escape(part_pattern).replace(r"\*", "[^/]*")
        if re.fullmatch(regex, part_name) is None:
            return False
    return True


def _permissions_block(text: str) -> str:
    match = re.search(r"(?m)^permissions:\n((?:  .*\n)+)", text)
    assert match, "missing top-level permissions block"
    return match.group(0)


@pytest.fixture(scope="module")
def workflow() -> str:
    return _workflow_text()


def test_governance_push_family_is_represented(workflow: str) -> None:
    patterns = _branch_patterns(_section_body(workflow, "push:"))
    assert "*/governance-*" in patterns
    assert github_branch_match("codex/governance-v2-ci-reachability-repair", "*/governance-*")
    assert github_branch_match("cursor/governance-v2-ci-reachability-repair", "*/governance-*")
    # Preserve prior allow-list entries.
    assert "elysia-collective-*" in patterns
    assert "autopilot-*" in patterns
    assert "codex/governance-checkpoint-contract" in patterns


def test_governance_stacked_pr_base_family_is_represented(workflow: str) -> None:
    patterns = _branch_patterns(_section_body(workflow, "pull_request:"))
    assert "*/governance-*" in patterns
    assert github_branch_match(
        "cursor/governance-v2-generation-boundary-repair-1799",
        "*/governance-*",
    )
    assert "main" in patterns
    assert "codex/remote-fix-*" in patterns


def test_unrelated_branch_negative_fixture_excluded(workflow: str) -> None:
    push_patterns = _branch_patterns(_section_body(workflow, "push:"))
    pr_patterns = _branch_patterns(_section_body(workflow, "pull_request:"))
    negative = "feature/random-ui-work"
    assert not any(github_branch_match(negative, pattern) for pattern in push_patterns)
    assert not any(github_branch_match(negative, pattern) for pattern in pr_patterns)
    # New governance family must stay one-segment-prefix narrow.
    assert not github_branch_match("team/codex/governance-nested", "*/governance-*")
    assert not github_branch_match("governance-unprefixed", "*/governance-*")


def test_exact_sha_assertion_present(workflow: str) -> None:
    assert "Assert exact candidate SHA" in workflow
    assert "expected_candidate_sha=" in workflow
    assert "actual_checked_out_sha=" in workflow
    assert "git rev-parse HEAD" in workflow
    assert "github.event.pull_request.head.sha || github.sha" in workflow
    assert "Exact candidate SHA mismatch" in workflow


def test_permissions_remain_contents_read_only(workflow: str) -> None:
    block = _permissions_block(workflow)
    assert "contents: read" in block
    assert "permissions:\n  contents: read\n" in workflow
    assert "contents: write" not in workflow.lower()
    for item in (
        "pull-requests:",
        "actions:",
        "deployments:",
        "packages:",
        "id-token:",
        "security-events:",
    ):
        assert item not in block.lower()


def test_preserved_generation_breaker_included_in_ci(workflow: str) -> None:
    assert "breaker_tests/test_vega_v2_generation.py" in workflow
    assert "python -m pytest -q elysia_collective_seed" in workflow
