from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "propose-main-protection.sh"
BASH = shutil.which("bash") or r"C:\Program Files\Git\bin\bash.exe"
HEAD = "1" * 40


def _msys_path(path: Path) -> str:
    absolute = path.resolve()
    if absolute.drive:
        return f"/{absolute.drive[0].lower()}{absolute.as_posix()[2:]}"
    return absolute.as_posix()


def _run(tmp_path: Path, *, pr: dict | None = None, checks: dict | None = None, env: dict | None = None):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "calls.jsonl"
    gh = fake_bin / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$GH_CALLS\"\n"
        "case \" $* \" in *' --method '*|*' PUT '*) exit 99;; esac\n"
        "case \"${2:-}\" in */pulls/*) printf '%s\\n' \"$GH_PR\";; *) printf '%s\\n' \"$GH_CHECKS\";; esac\n",
        encoding="utf-8",
        newline="\n",
    )
    gh.chmod(0o755)
    python3 = fake_bin / "python3"
    python3.write_text(
        f'#!/usr/bin/env bash\n"{Path(sys.executable).as_posix()}" "$@" | tr -d "\\r"\nexit "${{PIPESTATUS[0]}}"\n',
        encoding="utf-8",
        newline="\n",
    )
    python3.chmod(0o755)
    run_env = os.environ.copy()
    run_env.update(
        {
            "GH_CALLS": str(calls),
            "GH_PR": json.dumps(pr or {}),
            "GH_CHECKS": json.dumps(checks or {}),
        }
    )
    if env:
        run_env.update(env)
    result = subprocess.run(
        [
            BASH,
            "-c",
            'export PATH="$1:/usr/bin:$PATH"; exec "$2"',
            "proposal-test",
            _msys_path(fake_bin),
            _msys_path(SCRIPT),
        ],
        text=True,
        capture_output=True,
        env=run_env,
        check=False,
    )
    recorded = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    return result, recorded


def _valid_pr(**overrides):
    payload = {"state": "open", "base": {"ref": "main"}, "head": {"sha": HEAD}}
    payload.update(overrides)
    return payload


def _valid_checks(**overrides):
    check = {
        "name": "verified-ci",
        "head_sha": HEAD,
        "status": "completed",
        "conclusion": "success",
        "app": {"id": 15368},
    }
    check.update(overrides)
    return {"check_runs": [check]}


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"REQUIRED_CHECK_CONTEXT": "verified-ci"},
        {"REQUIRED_CHECK_CONTEXT": "verified-ci", "REQUIRED_CHECK_APP_ID": "not-a-number", "VERIFIED_MAIN_PR_NUMBER": "98"},
        {"REQUIRED_CHECK_CONTEXT": "bad\ncontext", "REQUIRED_CHECK_APP_ID": "15368", "VERIFIED_MAIN_PR_NUMBER": "98"},
    ],
)
def test_invalid_inputs_fail_before_github_calls(tmp_path, env):
    result, calls = _run(tmp_path, env=env)
    assert result.returncode == 2
    assert calls == []


@pytest.mark.parametrize(
    "pr",
    [
        {"state": "closed", "base": {"ref": "main"}, "head": {"sha": HEAD}},
        {"state": "open", "base": {"ref": "develop"}, "head": {"sha": HEAD}},
        {"state": "open", "base": {"ref": "main"}, "head": {"sha": "short"}},
    ],
)
def test_invalid_pr_fails_closed(tmp_path, pr):
    result, calls = _run(
        tmp_path,
        pr=pr,
        env={"REQUIRED_CHECK_CONTEXT": "verified-ci", "REQUIRED_CHECK_APP_ID": "15368", "VERIFIED_MAIN_PR_NUMBER": "98"},
    )
    assert result.returncode == 2
    assert len(calls) == 1


@pytest.mark.parametrize(
    "checks",
    [
        _valid_checks(name="other"),
        _valid_checks(head_sha="2" * 40),
        _valid_checks(status="in_progress"),
        _valid_checks(conclusion="failure"),
        _valid_checks(app={"id": 999}),
    ],
)
def test_stale_or_mismatched_check_fails_closed(tmp_path, checks):
    result, calls = _run(
        tmp_path,
        pr=_valid_pr(),
        checks=checks,
        env={"REQUIRED_CHECK_CONTEXT": "verified-ci", "REQUIRED_CHECK_APP_ID": "15368", "VERIFIED_MAIN_PR_NUMBER": "98"},
    )
    assert result.returncode == 2
    assert len(calls) == 2


def test_success_prints_revalidating_owner_command_without_mutation(tmp_path):
    result, calls = _run(
        tmp_path,
        pr=_valid_pr(),
        checks=_valid_checks(),
        env={"REQUIRED_CHECK_CONTEXT": "verified-ci", "REQUIRED_CHECK_APP_ID": "15368", "VERIFIED_MAIN_PR_NUMBER": "98"},
    )
    assert result.returncode == 0, result.stderr
    assert len(calls) == 2
    assert all("--method" not in call and " PUT " not in f" {call} " for call in calls)
    assert "Proposed owner-only mutation (NOT executed)" in result.stdout
    assert "revalidates the PR and check immediately before PUT" in result.stdout
    assert '"required_approving_review_count": 1' in result.stdout
    assert '"enforce_admins": true' in result.stdout
    assert '"allow_force_pushes": false' in result.stdout
    assert '"allow_deletions": false' in result.stdout
