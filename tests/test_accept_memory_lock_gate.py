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



@pytest.mark.parametrize("status", ["SKIPPED", "FAIL", "ERROR"])
def test_junit_rejects_nonpassing_status(tmp_path, status):
    path = tmp_path / "junit.xml"
    xml_report(path, ["test_write_restarts_with_authoritative_memory"], status=status)
    cases, errors = gate.summary_from_junit(path)
    _, missing = gate.audit_required_cases(cases)
    assert errors
    assert missing
    assert cases["test_write_restarts_with_authoritative_memory"] == [status]


def test_junit_wrong_file_missing_suite_counts_and_bad_root(tmp_path):
    path = tmp_path / "junit.xml"
    name = "test_write_restarts_with_authoritative_memory"
    xml_report(path, [name])
    tree = ET.parse(path)
    case = next(tree.iter("testcase"))
    case.set("file", "tests/foreign.py")
    tree.write(path)
    _, errors = gate.summary_from_junit(path)
    assert any("file provenance" in value for value in errors)
    tree = ET.parse(path)
    suite = next(tree.iter("testsuite"))
    suite.set("tests", "99")
    tree.write(path)
    _, errors = gate.summary_from_junit(path)
    assert any("counts" in value for value in errors)
    suite.attrib.pop("tests")
    tree.write(path)
    _, errors = gate.summary_from_junit(path)
    assert any("metadata" in value for value in errors)
    ET.ElementTree(ET.Element("not-junit")).write(path)
    with pytest.raises(ValueError, match="root"):
        gate.summary_from_junit(path)


def test_required_case_audit_rejects_zero_missing_deselected_and_duplicates():
    required = [name for scenario in gate.SCENARIOS.values()
                for name, count in scenario.items() for _ in range(count)]
    assert len(required) == 30
    complete = {}
    for name in required:
        complete.setdefault(name, []).append("PASS")
    good, errors = gate.audit_required_cases(complete)
    assert not errors
    assert len(good) == 9
    assert all(entry["status"] == "PASS" for entry in good.values())
    zero, errors = gate.audit_required_cases({})
    assert errors and all(entry["status"] == "FAIL" for entry in zero.values())
    for altered in (required[1:], required + [required[0]], ["renamed_" + value for value in required]):
        observed = {}
        for value in altered:
            observed.setdefault(value, []).append("PASS")
        groups, failures = gate.audit_required_cases(observed)
        assert failures
        assert any(entry["status"] == "FAIL" for entry in groups.values())


def _minimal_synthetic_checkout(tmp_path):
    root = tmp_path / "independent_synthetic_checkout"
    (root / "scripts").mkdir(parents=True)
    (root / "tests").mkdir()
    shutil.copy2(ROOT / "scripts" / "accept_memory_lock.py",
                 root / "scripts" / "accept_memory_lock.py")
    test = root / "tests" / "test_memory_integrity_windows.py"
    test.write_text("def test_real_failure():\n    assert False\n", encoding="utf-8")
    run(["git", "init", "-q"], root)
    run(["git", "config", "user.email", "synthetic@example.invalid"], root)
    run(["git", "config", "user.name", "Synthetic Source"], root)
    run(["git", "add", "scripts/accept_memory_lock.py",
         "tests/test_memory_integrity_windows.py"], root)
    run(["git", "commit", "-qm", "source under synthetic gate"], root)
    sha = run(["git", "rev-parse", "HEAD"], root).stdout.strip()
    return root, sha, test


def _invoke_synthetic(root, sha):
    return subprocess.run(
        [sys.executable, "-I", "-B", "scripts/accept_memory_lock.py",
         "--expected-sha", sha], cwd=root, text=True, capture_output=True,
        timeout=30,
    )


def _sole_report(root):
    docs = list((root / "REPORTS" / "memory-lock").glob("*.json"))
    assert len(docs) == 1
    return json.loads(docs[0].read_text(encoding="utf-8"))


def test_wrong_sha_and_tracked_dirty_exit_before_pytest(tmp_path):
    other = tmp_path / "wrong"
    other.mkdir()
    root, sha, tracked_test = _minimal_synthetic_checkout(other)
    wrong = _invoke_synthetic(root, "0" * 40)
    assert wrong.returncode != 0
    report = _sole_report(root)
    assert report["status"] == "FAIL"
    assert report["tests"] == {}
    assert any("SHA" in x for x in report["errors"])
    # Existing evidence JSON may be left between runs without becoming source.
    tracked_test.write_text("def test_changed():\n    assert False\n", encoding="utf-8")
    dirty = _invoke_synthetic(root, sha)
    assert dirty.returncode != 0
    reports = sorted((root / "REPORTS" / "memory-lock").glob("*.json"))
    assert len(reports) == 2
    last = json.loads(reports[-1].read_text(encoding="utf-8"))
    assert last["source_clean"] is False
    assert last["tests"] == {}


def test_no_git_identity_and_unwritable_report_exit_nonzero(tmp_path):
    root = tmp_path / "missing_git"
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "accept_memory_lock.py",
                 root / "scripts" / "accept_memory_lock.py")
    attempt = _invoke_synthetic(root, "0" * 40)
    assert attempt.returncode != 0
    assert _sole_report(root)["status"] == "FAIL"

    base = tmp_path / "blocked_evidence"
    base.mkdir()
    checked, sha, _ = _minimal_synthetic_checkout(base)
    (checked / "REPORTS").mkdir()
    (checked / "REPORTS" / "memory-lock").write_text("synthetic obstruction", encoding="utf-8")
    attempt = _invoke_synthetic(checked, sha)
    assert attempt.returncode != 0
    assert "Unable to preserve evidence" in attempt.stderr


def test_missing_and_malformed_junit_is_not_accepted(tmp_path):
    path = tmp_path / "missing.xml"
    with pytest.raises(OSError):
        gate.summary_from_junit(path)
    path.write_text("<not-closed", encoding="utf-8")
    with pytest.raises(ET.ParseError):
        gate.summary_from_junit(path)


def test_ignored_pytest_config_plugin_cannot_forge_full_runner(tmp_path):
    """Actual copied acceptance runner, tracked failing test, ignored ini/plugin.

    Pre-repair runner falsely reports PASS_SCOPED with forged no-op test items.
    Repaired runner must reject the source BEFORE plugin executes.
    """
    root, original_sha, _ = _minimal_synthetic_checkout(tmp_path)
    original = _invoke_synthetic(root, original_sha)
    assert original.returncode != 0, "Real tracked failing test unexpectedly passed"
    assert _sole_report(root)["status"] == "FAIL"
    ignore = root / ".gitignore"
    ignore.write_text("pytest.ini\nextra/\n", encoding="utf-8")
    run(["git", "add", ".gitignore"], root)
    run(["git", "commit", "-qm", "Synthetic ignored config policy"], root)
    sha = run(["git", "rev-parse", "HEAD"], root).stdout.strip()
    (root / "pytest.ini").write_text(
        "[pytest]\npythonpath = extra\naddopts = -p forged_plugin\n", encoding="utf-8"
    )
    plugin_dir = root / "extra"
    plugin_dir.mkdir()
    cases = [
        name + (f"[{n}]" if count > 1 else "")
        for scenario in gate.SCENARIOS.values()
        for name, count in scenario.items()
        for n in range(count)
    ]
    assert len(cases) == 30
    (plugin_dir / "forged_plugin.py").write_text(
        "import pytest\n"
        "from pathlib import Path\n"
        "def pytest_collection_modifyitems(session, config, items):\n"
        "    Path('FORGED_PLUGIN_WAS_INVOKED').write_text('yes', encoding='utf-8')\n"
        "    parent = items[0].parent\n"
        f"    names = {cases!r}\n"
        "    items[:] = [pytest.Function.from_parent(parent, name=name,"
        " callobj=lambda: None) for name in names]\n",
        encoding="utf-8",
    )
    assert run(["git", "check-ignore", "pytest.ini", "extra/forged_plugin.py"],
               root).stdout.count("\n") == 2
    attack = _invoke_synthetic(root, sha)
    assert attack.returncode != 0, (
        "Ignored root pytest.ini plus ignored collection plugin forged PASS_SCOPED: "
        + attack.stdout + attack.stderr
    )
    # A fail-closed source preflight should never even import the hostile plugin.
    assert not (root / "FORGED_PLUGIN_WAS_INVOKED").exists(), (
        "Ignored plugin executed before gate rejected it"
    )
    reports = sorted((root / "REPORTS" / "memory-lock").glob("*.json"))
    assert len(reports) == 2
    report = json.loads(reports[-1].read_text(encoding="utf-8"))
    assert report["status"] == "FAIL"
    assert report["source_clean"] is False
    assert report["source_sha"] == sha
    assert report["tests"] == {}
