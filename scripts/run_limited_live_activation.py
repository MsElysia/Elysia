#!/usr/bin/env python3
"""Operator-only limited-live activation wrapper for harmless smoke path only.

Verifies RC tag, branch, config-disabled state, and explicit operator confirmation,
then delegates to the verified limited-live smoke command logic. Does not enable
broad autonomy, does not modify config/autonomy.json, and does not use
shell/network/browser/API beyond local git read-only checks.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.run_limited_live_smoke import (  # noqa: E402
    LIMITED_LIVE_PROFILE_NAME,
    _read_config_autonomy_enabled,
    run_limited_live_smoke,
    validate_custom_workspace_parent,
)
from project_guardian.live_action_readiness import evaluate_live_mode_readiness  # noqa: E402

ACTIVATION_PROFILE_NAME = "limited_live_harmless_smoke_activation_v1"
EXPECTED_BRANCH = "codex/limited-live-activation-wrapper"
RC_TAG_NAME = "limited_live_rc_1"
RC_TAG_TARGET_COMMIT = "236f0b559974afcd85b812f61ae19244a23a02f1"
_SKIP_BRANCH_CHECK_ENV = "ELYSIA_LIMITED_LIVE_ACTIVATION_SKIP_BRANCH_CHECK"


def _empty_summary(
    *,
    activation_profile: str = "",
    profile: str = "",
) -> Dict[str, Any]:
    return {
        "activation_profile": activation_profile,
        "profile": profile,
        "rc_tag_verified": False,
        "rc_tag_target": "",
        "branch_verified": False,
        "config_autonomy_enabled": False,
        "readiness_blocked": False,
        "smoke_command_invoked": False,
        "executed": False,
        "exact_content_verified": False,
        "rollback_verified": False,
        "workspace_temp_only": False,
        "unsafe_workspace_rejected": False,
        "safe": False,
        "errors": [],
    }


def _run_git(
    args: List[str],
    *,
    repo_root: Path,
) -> Tuple[int, str, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def resolve_rc_tag_commit(
    *,
    repo_root: Path = _REPO_ROOT,
    tag_name: str = RC_TAG_NAME,
) -> Tuple[Optional[str], Optional[str]]:
    """Return (commit_hash, error_message)."""
    code, stdout, stderr = _run_git(
        ["rev-parse", f"{tag_name}^{{commit}}"],
        repo_root=repo_root,
    )
    if code != 0:
        detail = stderr or stdout or f"tag {tag_name!r} not found"
        return None, detail
    return stdout, None


def verify_rc_tag(
    *,
    repo_root: Path = _REPO_ROOT,
    expected_commit: str = RC_TAG_TARGET_COMMIT,
    tag_name: str = RC_TAG_NAME,
) -> Tuple[bool, str, List[str]]:
    errors: List[str] = []
    commit, error = resolve_rc_tag_commit(repo_root=repo_root, tag_name=tag_name)
    if error:
        errors.append(f"RC tag verification failed: {error}")
        return False, "", errors
    assert commit is not None
    short_expected = expected_commit[:7]
    if commit != expected_commit and not commit.startswith(short_expected):
        errors.append(
            f"RC tag {tag_name!r} points to {commit}; expected {expected_commit}"
        )
        return False, commit, errors
    return True, commit, errors


def verify_branch(
    *,
    repo_root: Path = _REPO_ROOT,
    expected_branch: str = EXPECTED_BRANCH,
    skip: bool = False,
) -> Tuple[bool, List[str]]:
    if skip or os.environ.get(_SKIP_BRANCH_CHECK_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True, []
    code, stdout, stderr = _run_git(["branch", "--show-current"], repo_root=repo_root)
    if code != 0:
        detail = stderr or stdout or "cannot determine current branch"
        return False, [f"branch verification failed: {detail}"]
    if stdout != expected_branch:
        return False, [
            f"branch must be {expected_branch!r}; got {stdout!r}"
        ]
    return True, []


def verify_test_py_absent(*, repo_root: Path = _REPO_ROOT) -> Tuple[bool, List[str]]:
    test_py = repo_root / "test.py"
    if test_py.exists():
        return False, ["root test.py must be absent"]
    code, stdout, _stderr = _run_git(["ls-files", "--error-unmatch", "test.py"], repo_root=repo_root)
    if code == 0 and stdout.strip():
        return False, ["root test.py must not be tracked"]
    code, stdout, _stderr = _run_git(
        ["diff", "--cached", "--name-only", "--", "test.py"],
        repo_root=repo_root,
    )
    if code == 0 and stdout.strip():
        return False, ["root test.py must not be staged"]
    return True, []


def verify_index_clean(*, repo_root: Path = _REPO_ROOT) -> Tuple[bool, List[str]]:
    code, stdout, stderr = _run_git(["diff", "--cached", "--name-only"], repo_root=repo_root)
    if code != 0:
        detail = stderr or stdout or "cannot inspect staged files"
        return False, [f"staged-file check failed: {detail}"]
    staged = [line.strip() for line in stdout.splitlines() if line.strip()]
    if staged:
        return False, [f"unexpected staged files: {', '.join(staged)}"]
    return True, []


def run_limited_live_activation(
    *,
    confirm: bool = False,
    activation_profile: str = "",
    profile: str = "",
    workspace_parent: Optional[Union[str, Path]] = None,
    repo_root: Path = _REPO_ROOT,
    skip_branch_check: bool = False,
) -> Tuple[Dict[str, Any], int]:
    """Run activation wrapper. Returns (summary_dict, exit_code)."""
    summary = _empty_summary(activation_profile=activation_profile, profile=profile)
    errors: List[str] = summary["errors"]

    if not confirm:
        errors.append("missing --confirm-limited-live-activation")
        return summary, 2

    if activation_profile != ACTIVATION_PROFILE_NAME:
        errors.append(
            f"activation profile must be {ACTIVATION_PROFILE_NAME!r}; "
            f"got {activation_profile!r}"
        )
        return summary, 2

    if profile != LIMITED_LIVE_PROFILE_NAME:
        errors.append(
            f"profile must be {LIMITED_LIVE_PROFILE_NAME!r}; got {profile!r}"
        )
        return summary, 2

    rc_ok, rc_target, rc_errors = verify_rc_tag(repo_root=repo_root)
    summary["rc_tag_target"] = rc_target
    summary["rc_tag_verified"] = rc_ok
    if rc_errors:
        errors.extend(rc_errors)
        return summary, 2

    branch_ok, branch_errors = verify_branch(
        repo_root=repo_root,
        skip=skip_branch_check,
    )
    summary["branch_verified"] = branch_ok
    if branch_errors:
        errors.extend(branch_errors)
        return summary, 2

    config_enabled, config_error = _read_config_autonomy_enabled()
    summary["config_autonomy_enabled"] = config_enabled
    if config_error:
        errors.append(config_error)
        return summary, 2
    if config_enabled:
        errors.append("config/autonomy.json enabled=true; refusing activation")
        return summary, 2

    readiness = evaluate_live_mode_readiness()
    summary["readiness_blocked"] = readiness.status.value == "BLOCKED"
    if readiness.ready_for_limited_live_mode:
        errors.append("readiness unexpectedly grants limited live mode")
        return summary, 2

    test_py_ok, test_py_errors = verify_test_py_absent(repo_root=repo_root)
    if test_py_errors:
        errors.extend(test_py_errors)
        return summary, 2

    index_ok, index_errors = verify_index_clean(repo_root=repo_root)
    if index_errors:
        errors.extend(index_errors)
        return summary, 2

    if workspace_parent is not None:
        _validated, workspace_error = validate_custom_workspace_parent(workspace_parent)
        if workspace_error:
            summary["unsafe_workspace_rejected"] = True
            errors.append(workspace_error)
            return summary, 2

    summary["smoke_command_invoked"] = True
    smoke_summary, smoke_code = run_limited_live_smoke(
        confirm=True,
        profile=profile,
        workspace_parent=workspace_parent,
    )

    summary["executed"] = bool(smoke_summary.get("executed"))
    summary["exact_content_verified"] = bool(smoke_summary.get("exact_content_verified"))
    summary["rollback_verified"] = bool(smoke_summary.get("rollback_verified"))
    summary["unsafe_workspace_rejected"] = bool(smoke_summary.get("workspace_rejected"))
    summary["config_autonomy_enabled"] = bool(smoke_summary.get("config_autonomy_enabled"))
    summary["readiness_blocked"] = bool(smoke_summary.get("readiness_blocked"))

    workspace_root = str(smoke_summary.get("workspace_root") or "")
    if workspace_root:
        from scripts.run_limited_live_smoke import _get_system_temp_root, _is_under_path

        summary["workspace_temp_only"] = _is_under_path(
            Path(workspace_root).resolve(),
            _get_system_temp_root(),
        )
    else:
        summary["workspace_temp_only"] = not summary["unsafe_workspace_rejected"]

    smoke_errors = list(smoke_summary.get("errors") or [])
    if smoke_errors:
        errors.extend(smoke_errors)

    if smoke_code != 0:
        return summary, smoke_code

    if not summary["executed"]:
        errors.append("smoke command did not execute")
        return summary, 1
    if not summary["exact_content_verified"]:
        errors.append("exact content was not verified")
        return summary, 1
    if not summary["rollback_verified"]:
        errors.append("rollback was not verified")
        return summary, 1
    if not summary["workspace_temp_only"]:
        errors.append("workspace was not temp-only")
        return summary, 1

    summary["safe"] = True
    return summary, 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Operator-only limited-live activation wrapper for harmless smoke only."
        )
    )
    parser.add_argument(
        "--activation-profile",
        required=True,
        help=f"Activation profile name (required: {ACTIVATION_PROFILE_NAME})",
    )
    parser.add_argument(
        "--profile",
        required=True,
        help=f"Limited live profile name (required: {LIMITED_LIVE_PROFILE_NAME})",
    )
    parser.add_argument(
        "--confirm-limited-live-activation",
        action="store_true",
        help="Explicit operator confirmation required to run",
    )
    parser.add_argument(
        "--workspace",
        default="",
        help=(
            "Optional parent directory inside the OS system temp directory only "
            "(unsafe paths are rejected before execution)"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON summary to stdout",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    workspace_parent = args.workspace.strip() or None
    summary, exit_code = run_limited_live_activation(
        confirm=bool(args.confirm_limited_live_activation),
        activation_profile=str(args.activation_profile),
        profile=str(args.profile),
        workspace_parent=workspace_parent,
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("Limited live activation summary")
        print("=" * 40)
        for key, value in summary.items():
            print(f"{key}: {value}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
