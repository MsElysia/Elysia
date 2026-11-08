"""Adversarial controls for the trusted-snapshot MemoryCore acceptance command.

All synthetic repositories and forged tests live under pytest's tmp_path.
They never import actual Elysia memory or touch the installed release.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "trusted_memory_acceptance.py"


def _run(args, cwd, *, env=None, check=True):
    return subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True,
                          timeout=50, check=check)


def _repo(base, *, ignore=""):
    base.mkdir(parents=True, exist_ok=True)
    (base / "scripts").mkdir()
    (base / "tests").mkdir()
    (base / "project_guardian").mkdir()
    (base / "project_guardian" / "memory.py").write_text(
        "# Synthetic memory placeholder for negative controls only.\n",
        encoding="utf-8")
    shutil.copy2(RUNNER, base / "scripts" / RUNNER.name)
    (base / "tests" / "test_memory_integrity_windows.py").write_text(
        "def test_real_failure():\n"
        "    assert False, 'original test must really execute'\n", encoding="utf-8")
    if ignore:
        (base / ".gitignore").write_text(ignore, encoding="utf-8")
    _run(["git", "init", "-q"], base)
    _run(["git", "config", "user.email", "synthetic@example.invalid"], base)
    _run(["git", "config", "user.name", "Synthetic Test"], base)
    _run(["git", "add", "."], base)
    _run(["git", "commit", "-qm", "tracked original failing source"], base)
    return _run(["git", "rev-parse", "HEAD"], base).stdout.strip()


def _accept(base, expected, *, extra_env=None, receipt=None):
    env = os.environ.copy()
    env.update(extra_env or {})
    target = receipt or base.parent / (base.name + "-receipt.json")
    command = [sys.executable, "-I", "-B", str(base / "scripts" / RUNNER.name),
               "--expected-sha", expected, "--evidence", str(target)]
    result = _run(command, base, env=env, check=False)
    assert target.is_file(), (result.stdout, result.stderr)
    return result, json.loads(target.read_text(encoding="utf-8"))


def test_control_b_git_environment_cannot_substitute_clean_repo(tmp_path):
    """Dirty B + GIT_DIR/GIT_WORK_TREE pointed at clean A must never certify B."""
    source_a = tmp_path / "A"
    source_b = tmp_path / "B"
    pinned = _repo(source_a)
    shutil.copytree(source_a, source_b)
    modified = source_b / "tests" / "test_memory_integrity_windows.py"
    # Fake every required named case and pad to exactly 30 no-op PASSES,
    # reproducing the prior false-green JUnit shape rather than one green test.
    import runpy
    required = runpy.run_path(str(RUNNER))["REQUIRED"]
    assert sum(required.values()) < 30
    forged = ["import pytest", "from pathlib import Path"]
    for name, count in required.items():
        forged.extend([
            f"@pytest.mark.parametrize('i', range({count}))",
            f"def {name}(i):",
            "    Path('FORGED_TEST_RAN').write_text('bad')",
        ])
    forged.extend([
        f"@pytest.mark.parametrize('i', range({30 - sum(required.values())}))",
        "def test_padding_noop(i):",
        "    assert True",
    ])
    modified.write_text("\n".join(forged) + "\n", encoding="utf-8")
    fake_env = {
        "GIT_DIR": str(source_a / ".git"),
        "GIT_WORK_TREE": str(source_a),
        "GIT_INDEX_FILE": str(source_a / ".git" / "index"),
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.worktree",
        "GIT_CONFIG_VALUE_0": str(source_a),
    }
    outcome, receipt = _accept(source_b, pinned, extra_env=fake_env)
    assert outcome.returncode != 0
    assert receipt["status"] == "FAIL"
    assert not receipt.get("source_clean", True)
    assert not (source_b / "FORGED_TEST_RAN").exists()
    assert receipt.get("cases_passed", 0) == 0


def test_control_c_ignored_pytest_config_and_plugin_never_execute(tmp_path):
    root = tmp_path / "ignored"
    pinned = _repo(root, ignore="pytest.ini\nextra/\n")
    (root / "pytest.ini").write_text(
        "[pytest]\npythonpath = extra\naddopts = -p forged_plugin\n", encoding="utf-8")
    (root / "extra").mkdir()
    (root / "extra" / "forged_plugin.py").write_text(
        "from pathlib import Path\n"
        "Path('FORGED_PLUGIN_IMPORTED').write_text('bad')\n"
        "def pytest_collection_modifyitems(items):\n"
        "    items[:] = []\n", encoding="utf-8")
    result, receipt = _accept(root, pinned)
    assert result.returncode != 0
    assert receipt["status"] == "FAIL"
    assert not (root / "FORGED_PLUGIN_IMPORTED").exists()
    assert receipt.get("cases_passed", 0) == 0
    assert receipt.get("cases_failed", 0) == 1, receipt


@pytest.mark.parametrize("ignored", [False, True])
def test_control_d_fake_pytest_cannot_execute(tmp_path, ignored):
    root = tmp_path / "shadow"
    pinned = _repo(root, ignore="ci_stubs/\n" if ignored else "")
    (root / "ci_stubs").mkdir()
    (root / "ci_stubs" / "pytest.py").write_text(
        "from pathlib import Path\nPath('FAKE_PYTEST_RAN').write_text('bad')\n",
        encoding="utf-8")
    result, receipt = _accept(
        root, pinned, extra_env={
            "PYTHONPATH": str(root / "ci_stubs"),
            "PYTEST_ADDOPTS": "--override-ini addopts=-p forged_plugin",
            "PYTEST_PLUGINS": "forged_plugin",
        })
    assert result.returncode != 0
    assert receipt["status"] == "FAIL"
    assert not (root / "FAKE_PYTEST_RAN").exists()
    assert receipt.get("cases_passed", 0) == 0


def test_dirty_source_and_wrong_sha_fail_closed(tmp_path):
    root = tmp_path / "dirty"
    pinned = _repo(root)
    result, receipt = _accept(root, "0" * 40)
    assert result.returncode != 0
    assert receipt["status"] == "FAIL"
    other = tmp_path / "dirty-second-receipt.json"
    (root / "tests" / "test_memory_integrity_windows.py").write_text(
        "def test_forged_noop():\n    assert True\n", encoding="utf-8")
    result, receipt = _accept(root, pinned, receipt=other)
    assert result.returncode != 0
    assert receipt["status"] == "FAIL"
    assert receipt["source_clean"] is False


def test_clean_but_missing_mandatory_cases_cannot_pass(tmp_path):
    root = tmp_path / "missing-required"
    pinned = _repo(root)
    (root / "tests" / "test_memory_integrity_windows.py").write_text(
        "def test_unrelated_green():\n    assert True\n", encoding="utf-8")
    _run(["git", "add", "."], root)
    _run(["git", "commit", "-qm", "missing memory tests"], root)
    pinned = _run(["git", "rev-parse", "HEAD"], root).stdout.strip()
    result, receipt = _accept(root, pinned)
    assert result.returncode != 0
    assert receipt["status"] == "FAIL"


def test_missing_evidence_and_installed_path_are_rejected(tmp_path):
    root = tmp_path / "safe"
    pinned = _repo(root)
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("sentinel", encoding="utf-8")
    failure = _run([sys.executable, "-I", "-B", str(root / "scripts" / RUNNER.name),
                    "--expected-sha", pinned, "--evidence", str(blocked / "report.json")],
                   root, check=False)
    assert failure.returncode != 0
    assert blocked.read_text(encoding="utf-8") == "sentinel"

    installed = tmp_path / "Elysia-Windows-Release"
    shutil.copytree(root, installed)
    result = _run([sys.executable, "-I", "-B", str(installed / "scripts" / RUNNER.name),
                   "--expected-sha", pinned, "--evidence",
                   str(tmp_path / "installed-report.json")], installed, check=False)
    assert result.returncode != 0
    assert not (tmp_path / "installed-report.json").exists()


def test_control_a_clean_real_canonical_memory_is_covered_in_ci():
    """Hosted CI separately runs the real runner on its exact pinned PR SHA.

    This verifies the sentinel contract exists without invoking a second full
    MemoryCore run for every adversarial fixture.
    """
    assert RUNNER.is_file()
    assert (ROOT / "tests" / "test_memory_integrity_windows.py").is_file()
