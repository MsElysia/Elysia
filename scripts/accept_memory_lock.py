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
    "read_only_sidecar_injection": {
        "test_acceptance_existing_sidecar_permission_denial_fails_closed": 1,
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


def summary_from_junit(filename: Path) -> tuple[dict[str, list[str]], list[str]]:
    found: dict[str, list[str]] = {}
    bad: list[str] = []
    tree = ET.parse(filename)
    for case in tree.iter("testcase"):
        name = case.get("name") or ""
        if not name:
            bad.append("unnamed pytest case")
            continue
        status = "FAIL" if case.find("failure") is not None else (
            "ERROR" if case.find("error") is not None else (
                "SKIPPED" if case.find("skipped") is not None else "PASS"))
        found.setdefault(name.split("[", 1)[0], []).append(status)
        if status != "PASS":
            bad.append(f"{name}: {status}")
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
        "permissions_scenarios": "synthetic injected PermissionError, not native Windows ACL proof",
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
            report["source_clean"] = not bool(git("status", "--porcelain", "--untracked-files=no"))
            if not report["source_clean"]:
                errors.append("Tracked worktree changes present: source cannot be certified")
            if args.expected_sha and head != args.expected_sha:
                errors.append("Checked-out SHA does not match expected source SHA")
        except (subprocess.SubprocessError, OSError) as exc:
            errors.append(f"Source identity unavailable ({type(exc).__name__})")

    if not errors:
        try:
            with tempfile.TemporaryDirectory(prefix="elysia_memory_lock_accept_") as td:
                temp = Path(td)
                xml = temp / "pytest.xml"
                env = os.environ.copy()
                env.update({
                    "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1",
                    "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "",
                    "OPENROUTER_API_KEY": "", "HF_HUB_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                    "PYTHONPATH": str(ROOT / "ci_stubs"),
                })
                cmd = [
                    sys.executable, "-B", "-m", "pytest", "--noconftest", "-q",
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
        except (OSError, subprocess.SubprocessError, ET.ParseError) as exc:
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
