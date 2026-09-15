"""Static regression for Issue #39 exact-head CI reachability + safety finalization.

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

EXPLICIT_GOVERNANCE_FAMILIES = (
    "codex/governance-*",
    "cursor/governance-*",
)
REQUIRED_PUSH_PATTERNS = (
    "elysia-collective-*",
    "autopilot-*",
    "codex/governance-checkpoint-contract",
    *EXPLICIT_GOVERNANCE_FAMILIES,
)
REQUIRED_PR_BASE_PATTERNS = (
    "main",
    "elysia-collective-*",
    "autopilot-*",
    "codex/remote-fix-*",
    *EXPLICIT_GOVERNANCE_FAMILIES,
)
FORBIDDEN_BRANCH_PATTERNS = ("*/governance-*",)

POSITIVE_GOVERNANCE_BRANCHES = (
    "codex/governance-v2-example",
    "cursor/governance-v2-example",
)
NEGATIVE_BRANCHES = (
    "feature/random-ui-work",
    "codex/unrelated-work",
    "cursor/unrelated-work",
    "foo/governance-test",
    "team/governance-test",
    "team/codex/governance-test",
    "governance-unprefixed",
)


def _workflow_text() -> str:
    assert WORKFLOW.is_file(), f"missing workflow: {WORKFLOW}"
    return WORKFLOW.read_text(encoding="utf-8")


def _section_body(text: str, heading: str) -> str:
    pattern = re.compile(rf"(?m)^  {re.escape(heading)}\n((?:(?:    .*)?\n)+)")
    match = pattern.search(text)
    assert match, f"missing on.{heading} section"
    return match.group(1)


def _branch_patterns(section_body: str) -> list[str]:
    return re.findall(r"^\s+-\s+'?([^'\s#]+)'?", section_body, flags=re.M)


def github_branch_match(name: str, pattern: str) -> bool:
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


def _matches_any(name: str, patterns: list[str]) -> bool:
    return any(github_branch_match(name, pattern) for pattern in patterns)


def _permissions_block(text: str) -> str:
    match = re.search(r"(?m)^permissions:\n((?:  .*\n)+)", text)
    assert match, "missing top-level permissions block"
    return match.group(0)


def _assert_no_write_permissions(text: str) -> None:
    """Reject permission maps and scalar `permissions: write-all` at any scope."""
    write_all = re.findall(
        r"(?mi)^\s*permissions\s*:\s*['\"]?write-all['\"]?\s*(?:#.*)?$",
        text,
    )
    assert not write_all, "workflow must not grant scalar permissions: write-all"
    write_entries = re.findall(
        r"(?mi)^\s*([a-z0-9-]+)\s*:\s*['\"]?write['\"]?\s*(?:#.*)?$",
        text,
    )
    assert not write_entries, f"workflow must not grant write permissions: {write_entries}"


@pytest.fixture(scope="module")
def workflow() -> str:
    return _workflow_text()


def test_governance_push_family_is_represented(workflow: str) -> None:
    patterns = _branch_patterns(_section_body(workflow, "push:"))
    for required in REQUIRED_PUSH_PATTERNS:
        assert required in patterns, f"push.branches missing {required!r}: {patterns}"
    for name in POSITIVE_GOVERNANCE_BRANCHES:
        assert _matches_any(name, list(EXPLICIT_GOVERNANCE_FAMILIES)), name


def test_governance_stacked_pr_base_family_is_represented(workflow: str) -> None:
    patterns = _branch_patterns(_section_body(workflow, "pull_request:"))
    for required in REQUIRED_PR_BASE_PATTERNS:
        assert required in patterns, f"pull_request.branches missing {required!r}: {patterns}"
    assert github_branch_match("cursor/governance-v2-generation-boundary-repair-1799", "cursor/governance-*")
    for name in POSITIVE_GOVERNANCE_BRANCHES:
        assert _matches_any(name, list(EXPLICIT_GOVERNANCE_FAMILIES)), name


def test_arbitrary_one_segment_governance_prefix_absent(workflow: str) -> None:
    push_patterns = _branch_patterns(_section_body(workflow, "push:"))
    pr_patterns = _branch_patterns(_section_body(workflow, "pull_request:"))
    for forbidden in FORBIDDEN_BRANCH_PATTERNS:
        assert forbidden not in push_patterns
        assert forbidden not in pr_patterns
        assert f"'{forbidden}'" not in workflow
        assert f'"{forbidden}"' not in workflow


def test_unrelated_branch_negative_fixtures_excluded(workflow: str) -> None:
    push_patterns = _branch_patterns(_section_body(workflow, "push:"))
    pr_patterns = _branch_patterns(_section_body(workflow, "pull_request:"))
    for negative in NEGATIVE_BRANCHES:
        assert not _matches_any(negative, push_patterns), negative
        assert not _matches_any(negative, pr_patterns), negative
        assert not _matches_any(negative, list(EXPLICIT_GOVERNANCE_FAMILIES)), negative


def test_pull_request_target_absent(workflow: str) -> None:
    assert "pull_request_target:" not in workflow
    assert re.search(r"(?m)^\s*pull_request_target\s*:", workflow) is None
    on_match = re.search(r"(?ms)^on:\n(.*?)(?=\npermissions:|\njobs:)", workflow)
    assert on_match is not None, "missing on: block"
    assert "pull_request_target" not in on_match.group(1)


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
    _assert_no_write_permissions(workflow)
    for item in ("pull-requests:", "actions:", "deployments:", "packages:", "id-token:", "security-events:"):
        assert item not in block.lower()


def test_scalar_write_all_rejected_at_workflow_and_job_scope() -> None:
    with pytest.raises(AssertionError, match="permissions: write-all"):
        _assert_no_write_permissions("permissions: write-all\njobs:\n  test:\n    runs-on: ubuntu-latest\n")
    with pytest.raises(AssertionError, match="permissions: write-all"):
        _assert_no_write_permissions(
            "permissions:\n  contents: read\njobs:\n  test:\n    permissions: write-all\n    runs-on: ubuntu-latest\n"
        )


def test_preserved_generation_breaker_included_in_ci(workflow: str) -> None:
    assert "breaker_tests/test_vega_v2_generation.py" in workflow
    assert "python -m pytest -q elysia_collective_seed" in workflow
