"""Adversarial, synthetic-only verification of the MemoryCore acceptance gate.

Never imports Elysia memory or touches any installed data. The synthetic repo
contains a deliberately failing tracked test and an untracked fake pytest.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("memory_acceptance_gate", ROOT / "scripts" / "accept_memory_lock.py")
assert SPEC and SPEC.loader
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def run(command, cwd, **kwargs):
    return subprocess.run(command, cwd=cwd, check=True, text=True,
                          capture_output=True, timeout=15, **kwargs)


@pytest.mark.parametrize("git_ignored", [False, True])
def test_untracked_fake_pytest_never_gets_invoked(tmp_path, git_ignored):
    """Reproduces independent 2 TEST false-green, including ignored executable."""
    repo = tmp_path / "disposable_repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "ci_stubs").mkdir()
    shutil.copy2(ROOT / "scripts" / "accept_memory_lock.py", repo / "scripts" / "accept_memory_lock.py")
    (repo / "tests" / "test_memory_integrity_windows.py").write_text(
        "def test_genuinely_failing():\n    assert False, 'synthetic original must fail'\n",
        encoding="utf-8",
    )
    if git_ignored:
        (repo / ".gitignore").write_text("ci_stubs/pytest.py\n", encoding="utf-8")
    run(["git", "init", "-q"], repo)
    run(["git", "config", "user.email", "synthetic@example.invalid"], repo)
    run(["git", "config", "user.name", "Synthetic Acceptance Test"], repo)
    tracked = ["scripts/accept_memory_lock.py", "tests/test_memory_integrity_windows.py"]
    if git_ignored:
        tracked.append(".gitignore")
    run(["git", "add", *tracked], repo)
    run(["git", "commit", "-qm", "synthetic tracked failing source"], repo)
    sha = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    # One complete JUnit testcase for each expected case, as the false-green
    # attacker did. This is test-generated source, never a real pytest package.
    case_names = [name for items in gate.SCENARIOS.values() for name, count in items.items() for _ in range(count)]
    module = f"""import sys
from pathlib import Path
import xml.etree.ElementTree as ET
Path("FAKE_PYTEST_WAS_EXECUTED").write_text("bad", encoding="utf-8")
xml = next(arg.split("=", 1)[1] for arg in sys.argv if arg.startswith("--junitxml="))
root = ET.Element("testsuites")
suite = ET.SubElement(root, "testsuite", tests=str(len({case_names!r})))
for name in {case_names!r}:
    ET.SubElement(suite, "testcase", classname="tests.test_memory_integrity_windows", name=name)
ET.ElementTree(root).write(xml, encoding="utf-8", xml_declaration=True)
"""
    (repo / "ci_stubs" / "pytest.py").write_text(module, encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "ci_stubs")
    attempt = subprocess.run(
        [sys.executable, "-B", "scripts/accept_memory_lock.py", "--expected-sha", sha],
        cwd=repo, env=env, text=True, capture_output=True, timeout=35,
    )
    assert attempt.returncode != 0, (
        "Untracked fake pytest turned deliberately failing test into PASS: "
        + attempt.stdout + attempt.stderr
    )
    assert not (repo / "FAKE_PYTEST_WAS_EXECUTED").exists(), (
        "Shadow pytest executed before source gate rejected it"
    )
    reports = list((repo / "REPORTS" / "memory-lock").glob("*.json"))
    assert len(reports) == 1
    result = json.loads(reports[0].read_text(encoding="utf-8"))
    assert result["status"] == "FAIL"
    assert result["source_sha"] == sha
    assert result["source_clean"] is False


def xml_report(path: Path, names, *, classname="tests.test_memory_integrity_windows", status="PASS"):
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite", name="pytest", tests=str(len(names)),
                          failures="0", errors="0", skipped="0")
    for name in names:
        entry = ET.SubElement(suite, "testcase", classname=classname, name=name,
                              file="tests/test_memory_integrity_windows.py")
        if status != "PASS":
            ET.SubElement(entry, {"SKIPPED": "skipped", "FAIL": "failure",
                                  "ERROR": "error"}[status])
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def test_junit_rejects_foreign_test_module_and_skipped_case(tmp_path):
    name = "test_write_restarts_with_authoritative_memory"
    path = tmp_path / "junit.xml"
    xml_report(path, [name], classname="foreign.fake_tests")
    _, errors = gate.summary_from_junit(path)
    assert errors and any("module" in x.lower() or "classname" in x.lower() for x in errors)
    xml_report(path, [name], status="SKIPPED")
    _, errors = gate.summary_from_junit(path)
    assert errors and any("SKIPPED" in x for x in errors)


def test_junit_missing_or_duplicate_required_test_is_not_accepted(tmp_path):
    path = tmp_path / "junit.xml"
    name = "test_write_restarts_with_authoritative_memory"
    xml_report(path, [name, name])
    cases, errors = gate.summary_from_junit(path)
    assert errors or len(cases[name]) != gate.SCENARIOS["initial_write_and_restart"][name]
    path.unlink()
    with pytest.raises((OSError, ET.ParseError)):
        gate.summary_from_junit(path)


def test_genuine_pytest_is_not_imported_from_repository_shadow(tmp_path):
    # The runner uses -I and discards PYTHONPATH before subprocess invocation.
    # A fake stub path may exist, but the isolated interpreter must resolve the
    # installed pytest distribution, never repo ci_stubs/pytest.py.
    (tmp_path / "pytest.py").write_text("raise RuntimeError('shadow')", encoding="utf-8")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(tmp_path)
    checked = subprocess.run([sys.executable, "-I", "-B", "-c",
                              "import pytest; print(pytest.__file__)"],
                             cwd=tmp_path, env=environment, text=True,
                             capture_output=True, timeout=15, check=True)
    assert str(tmp_path) not in checked.stdout
    assert "site-packages" in checked.stdout or "dist-packages" in checked.stdout
