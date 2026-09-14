"""Vega falsification tests for PR #45's static CI safety regression."""

import pytest

from elysia_collective_seed.autopilot.contracts import test_ci_trigger_coverage as ci


def test_static_regression_rejects_generic_codex_family() -> None:
    """An unrelated ``codex/*`` trigger must make the safety test fail."""
    unsafe = ci._workflow_text().replace(
        "      - 'codex/governance-*'",
        "      - 'codex/governance-*'\n      - 'codex/*'",
        1,
    )

    with pytest.raises(AssertionError):
        ci.test_unrelated_branch_negative_fixtures_excluded(unsafe)


def test_static_regression_rejects_any_write_permission() -> None:
    """An unlisted GitHub write scope must make the permission test fail."""
    unsafe = ci._workflow_text().replace(
        "permissions:\n  contents: read",
        "permissions:\n  contents: read\n  issues: write",
        1,
    )

    with pytest.raises(AssertionError):
        ci.test_permissions_remain_contents_read_only(unsafe)


def test_static_regression_rejects_job_write_all_shorthand() -> None:
    """GitHub's canonical job-level ``write-all`` form must fail closed."""
    unsafe = ci._workflow_text().replace(
        "  seed-validation:\n",
        "  seed-validation:\n    permissions: write-all\n",
        1,
    )

    with pytest.raises(AssertionError):
        ci.test_permissions_remain_contents_read_only(unsafe)
