#!/usr/bin/env python3
"""Strict, synthetic-only MemoryCore lock acceptance. No installed Elysia access.

Run from a clean, independent worktree: python -B scripts/accept_memory_lock.py
Creates an evidence JSON under REPORTS/memory-lock; test files live only in a
temporary directory. No cloud/provider/autonomy or operational-data access.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

# The existing memory regression tests are the source of behavioral assertions.
# Expected case counts prevent a renamed, removed, deselected or skipped test
# from silently turning a missing release gate green.
SCENARIOS = {
    "initial_write_and_restart": {"test_write_restarts_with_authoritative_memory": 1},
    "backup_restore_and_sidecar_lifecycle": {
        "test_acceptance_synthetic_snapshot_restore_and_sidecar_lifecycle": 1,
        "test_process_lock_sidecar_reuse_and_hardlink_rejection": 1,
    },
    "two_writers_and_real_process_race": {
        "test_two_loaded_instances_never_erase_external_commit": 1,
        "test_separate_process_writer_commit_survives_stale_parent": 1,
        "test_process_race_after_last_checksum_before_replace": 2,
    },
    "lock_timeout_and_explicit_reload": {
        "test_external_commit_during_temp_write_rechecked_before_replace": 1,
        "test_acceptance_independent_process_held_lock_fences_and_recovers": 1,
    },
    "read_only_sidecar_permissions": {
        "test_acceptance_existing_sidecar_permission_denial_fails_closed": 1,
        "test_acceptance_real_readonly_sidecar_file": 1,
    },
    "read_only_directory_injection": {
        "test_acceptance_directory_permission_denial_fails_closed": 1,
    },
    "primary_repair_and_restart": {
        "test_corrupt_or_malformed_history_never_overwritten": 3,
        "test_recovery_requires_explicit_valid_reload": 1,
        "test_missing_unreadable_file_does_not_automatically_clear_fence": 1,
        "test_missing_primary_after_load_does_not_get_recreated": 1,
        "test_explicit_reload_does_not_accept_missing_previously_loaded_primary": 1,
        "test_corrupt_primary_replacement_preserved_and_reload_required": 1,
        "test_failed_primary_read_fences_until_explicit_reload": 1,
    },
    "write_rollback_and_no_secondary_publication": {
        "test_failed_write_restores_evicted_history_and_does_not_poison_retry": 1,
        "test_stale_eviction_restores_local_snapshot": 1,
        "test_non_stale_replace_failure_allows_safe_retry": 1,
        "test_stale_rejection_never_publishes_vector_or_timeline": 1,
        "test_failed_disk_commit_does_not_publish_secondary_events": 1,
        "test_optional_usb_mirror_failure_does_not_fake_primary_failure": 1,
    },
    "lock_path_and_authority": {
        "test_primary_path_switch_to_identical_bytes_requires_reload": 1,
        "test_stale_forget_and_direct_save_cannot_erase_peer": 1,
        "test_lazy_load_fails_closed_and_reports_not_authoritative": 1,
    },
}


def git(*args: str) -> str:
    result = subprocess.run(["git", "-C", str(ROOT), *args], text=True,
                            capture_output=True, timeout=12, check=True)
    return result.stdout.strip()


def clean_source_issues() -> list[str]:
    """Reject tracked changes, untracked code and ignored executable shadowing.

    Only previous JSON evidence under REPORTS/memory-lock is allowed; it cannot
    enter Python's isolated module search path. Git gives exact -z paths, so
    quoting, spaces and Windows filename escapes cannot bypass this check.
    """
    issues: list[str] = []
    status = git("status", "--porcelain=v1", "-z", "--untracked-files=all")
    for record in status.split("\0"):
        if not record:
            continue
        state = record[:2]
        path = record[3:].replace("\\", "/")
        if (state == "??" and path.startswith("REPORTS/memory-lock/")
                and path.endswith(".json") and ".." not in Path(path).parts):
            continue
        issues.append("Tracked change or untracked source detected")
        break
    # An ignored Python module is also executable source. In particular,
    # git status alone will not reveal ignored ci_stubs/pytest.py.
    ignored = git("ls-files", "--others", "--ignored", "--exclude-standard",
                  "--", "scripts", "tests", "ci_stubs", "*.py")
    for path in ignored.splitlines():
        normalized = path.replace("\\", "/").lower()
        if (normalized.endswith((".py", ".pyw", ".pyi", ".pth", ".pyd", ".so", ".dll"))
                and ("/" not in normalized
                     or normalized.startswith(("scripts/", "tests/", "ci_stubs/")))):
            issues.append("Ignored executable source detected")
            break
    return issues


def isolated_pytest_environment() -> dict[str, str]:
    """Ignore caller-controlled Python/pytest injection while retaining deps."""
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONINSPECT",
                "PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_CURRENT_TEST"):
        env.pop(key, None)
    env.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "OPENROUTER_API_KEY": "",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    })
    return env


def ensure_installed_pytest(env: dict[str, str]) -> None:
    """Require -I to resolve the real installed pytest distribution.

    A repository-local pytest.py or ci_stubs/pytest.py must never be executed.
    """
    check = (
        "import importlib.metadata as m, importlib.util as u, pathlib; "
        "dist=m.distribution('pytest'); "
        "actual=pathlib.Path(u.find_spec('pytest').origin).resolve(); "
        "expected=pathlib.Path(dist.locate_file('pytest/__init__.py')).resolve(); "
        "assert actual==expected, 'pytest distribution origin mismatch'; "
        "print('PYTEST_ORIGIN_OK')"
    )
    result = subprocess.run([sys.executable, "-I", "-B", "-c", check],
                            cwd=ROOT, env=env, capture_output=True,
                            text=True, timeout=15)
    if result.returncode != 0 or result.stdout.strip() != "PYTEST_ORIGIN_OK":
        raise RuntimeError("Installed pytest origin could not be verified")


def summary_from_junit(filename: Path) -> tuple[dict[str, list[str]], list[str]]:
    """Validate actual source provenance, status and declared case totals."""
    found: dict[str, list[str]] = {}
    bad: list[str] = []
    if filename.stat().st_size > 2_000_000:
        raise ValueError("JUnit evidence exceeds bounded size")
    tree = ET.parse(filename)
    root = tree.getroot()
    if root.tag not in ("testsuite", "testsuites"):
        raise ValueError("Unexpected JUnit root")
    suites = list(root.iter("testsuite"))
    if len(suites) != 1:
        raise ValueError("Exactly one pytest JUnit suite required")
    suite = suites[0]
    cases = list(root.iter("testcase"))
    if not cases:
        bad.append("Zero test cases executed")
    for case in cases:
        name = case.get("name") or ""
        classname = case.get("classname") or ""
        path = (case.get("file") or "").replace("\\", "/").lstrip("./")
        if classname not in ("tests.test_memory_integrity_windows",
                             "test_memory_integrity_windows"):
            bad.append("JUnit testcase module provenance mismatch")
        if path and path != "tests/test_memory_integrity_windows.py":
            bad.append("JUnit testcase file provenance mismatch")
        if not name:
            bad.append("Unnamed pytest case")
            continue
        status = "FAIL" if case.find("failure") is not None else (
            "ERROR" if case.find("error") is not None else (
                "SKIPPED" if case.find("skipped") is not None else "PASS"))
        found.setdefault(name.split("[", 1)[0], []).append(status)
        if status != "PASS":
            bad.append(f"{name}: {status}")
    try:
        declared = int(suite.attrib["tests"])
        failures = int(suite.attrib["failures"])
        errors = int(suite.attrib["errors"])
        skipped = int(suite.attrib["skipped"])
    except (KeyError, ValueError) as exc:
        bad.append("JUnit suite status/count metadata missing")
    else:
        if declared != len(cases) or any((failures, errors, skipped)):
            bad.append("JUnit suite counts or status disagree with testcases")
    return found, bad


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha", help="Exact checked-out source SHA, for CI")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    report_dir = ROOT / "REPORTS" / "memory-lock"
    report: dict = {
        "task": "ELYSIA-NATIVE-MEMORY-ACCEPTANCE-001",
        "timestamp_utc": now.isoformat(),
        "source_sha": None,
        "source_clean": None,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "os": os.name,
        "runtime": "github_hosted" if os.environ.get("GITHUB_ACTIONS") == "true" else "local_disposable_checkout",
        "operational_data_used": False,
        "installed_release_tested": False,
        "native_windows_directory_acl_tested": False,
        "permissions_scenarios": "real temporary sidecar read-only mode plus injected directory EACCES; directory ACL unverified",
        "tests": {},
        "errors": [],
        "status": "FAIL",
    }
    errors: list[str] = report["errors"]

    # Never run a synthetic test process from a known installed/data checkout.
    forbidden = {
        "elysia-windows-release", "elysia-windows-integration-data",
        "elysia-verified-pilot", "elysia-verified-pilot-data",
    }
    if forbidden.intersection(p.lower() for p in ROOT.parts):
        errors.append("Refusing installed or operational Elysia source path")
    else:
        try:
            head = git("rev-parse", "HEAD")
            report["source_sha"] = head
            source_issues = clean_source_issues()
            report["source_clean"] = not source_issues
            errors.extend(source_issues)
            if source_issues:
                errors.append("Source cannot be certified: require a clean independent worktree")
            if args.expected_sha and head != args.expected_sha:
                errors.append("Checked-out SHA does not match expected source SHA")
        except (subprocess.SubprocessError, OSError) as exc:
            errors.append(f"Source identity unavailable ({type(exc).__name__})")

    if not errors:
        try:
            with tempfile.TemporaryDirectory(prefix="elysia_memory_lock_accept_") as td:
                temp = Path(td)
                xml = temp / "pytest.xml"
                env = isolated_pytest_environment()
                ensure_installed_pytest(env)
                cmd = [
                    sys.executable, "-I", "-B", "-m", "pytest", "--noconftest", "-q",
                    "-rs", "-p", "no:cacheprovider", f"--basetemp={temp / 'cases'}",
                    f"--junitxml={xml}", "tests/test_memory_integrity_windows.py",
                ]
                completed = subprocess.run(cmd, cwd=ROOT, env=env, text=True,
                                           capture_output=True, timeout=180)
                if completed.returncode != 0:
                    errors.append(f"pytest exited nonzero: {completed.returncode}")
                    print(completed.stdout[-5000:], file=sys.stderr)
                    print(completed.stderr[-1000:], file=sys.stderr)
                if not xml.is_file():
                    errors.append("No junit evidence; pytest may not have run")
                else:
                    cases, bad = summary_from_junit(xml)
                    errors.extend(bad)
                    for label, required in SCENARIOS.items():
                        details = {}
                        for name, count in required.items():
                            observed = cases.get(name, [])
                            details[name] = {
                                "expected": count, "observed": len(observed),
                                "passed": sum(x == "PASS" for x in observed),
                            }
                            if len(observed) != count or any(x != "PASS" for x in observed):
                                errors.append(f"Required acceptance case missing/failed: {name}")
                        report["tests"][label] = {
                            "status": "PASS" if all(
                                value["observed"] == value["expected"]
                                and value["passed"] == value["expected"]
                                for value in details.values()) else "FAIL",
                            "cases": details,
                        }
                    if not cases:
                        errors.append("Zero test cases executed")
        except (OSError, subprocess.SubprocessError, ET.ParseError, ValueError, RuntimeError) as exc:
            errors.append(f"Acceptance runner failed ({type(exc).__name__})")

    report["status"] = "PASS_SCOPED" if not errors else "FAIL"
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
        dest = report_dir / f"memory-lock-{stamp}.json"
        with dest.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
        print(f"MEMORY LOCK ACCEPTANCE {report['status']} sha={report['source_sha']} "
              f"scenarios={len(report['tests'])} evidence={dest.relative_to(ROOT)}")
    except OSError as exc:
        print(f"Unable to preserve evidence ({type(exc).__name__})", file=sys.stderr)
        return 1
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    if not errors:
        print("Scope: disposable MemoryCore only. Windows directory ACL and installed "
              "release compatibility remain NOT VERIFIED.")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
