#!/usr/bin/env python3
"""Test pinned MemoryCore source from a fresh Git archive, never a live worktree.

Usage: python -I -B scripts/trusted_memory_acceptance.py --expected-sha <40-hex>
Only temporary synthetic memory is used. No installed runtime certification.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    "scripts/trusted_memory_acceptance.py",
    "tests/test_memory_integrity_windows.py",
    "project_guardian/memory.py",
)
# Mandatory evidence from the existing, authoritative canonical test module.
REQUIRED = {
    "test_write_restarts_with_authoritative_memory": 1,
    "test_corrupt_or_malformed_history_never_overwritten": 3,
    "test_recovery_requires_explicit_valid_reload": 1,
    "test_two_loaded_instances_never_erase_external_commit": 1,
    "test_separate_process_writer_commit_survives_stale_parent": 1,
    "test_process_race_after_last_checksum_before_replace": 2,
    "test_process_lock_sidecar_reuse_and_hardlink_rejection": 1,
    "test_external_commit_during_temp_write_rechecked_before_replace": 1,
    "test_failed_write_restores_evicted_history_and_does_not_poison_retry": 1,
    "test_stale_rejection_never_publishes_vector_or_timeline": 1,
    "test_acceptance_synthetic_snapshot_restore_and_sidecar_lifecycle": 1,
    "test_acceptance_existing_sidecar_permission_denial_fails_closed": 1,
    "test_acceptance_directory_permission_denial_fails_closed": 1,
    "test_acceptance_independent_process_held_lock_fences_and_recovers": 1,
    "test_acceptance_real_readonly_sidecar_file": 1,
}
RELEASE_DIRS = {
    "elysia-windows-release", "elysia-windows-integration-data",
    "elysia-verified-pilot", "elysia-verified-pilot-data",
}


def _checked_receipt_destination(requested):
    """Restrict ALL receipts to non-redirected ROOT/REPORTS/trusted-memory/*.json.

    Refuse links, junctions, reparse points and traversal before any write.
    Recheck immediately before exclusive create to catch ordinary changes.
    Concurrent hostile admin path-swapping is outside the declared threat model.
    """
    allowed = ROOT / "REPORTS" / "trusted-memory"
    requested = Path(requested)
    if ".." in requested.parts:
        raise RuntimeError("Unsafe receipt path traversal refused")
    dest = requested if requested.is_absolute() else ROOT / requested
    if dest.parent != allowed or dest.suffix.lower() != ".json":
        raise RuntimeError("Receipt destination outside permitted REPORTS/trusted-memory directory")
    for node in (ROOT, ROOT / "REPORTS", allowed, dest):
        if node.is_symlink():
            raise RuntimeError("Receipt path symlink/referral refused")
        if os.name == "nt":
            junction = getattr(node, "is_junction", None)
            if junction is None:
                raise RuntimeError("Windows receipt junction detection unavailable")
            if junction():
                raise RuntimeError("Receipt path Windows junction refused")
            try:
                attrs = node.lstat().st_file_attributes
            except FileNotFoundError:
                continue
            if attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise RuntimeError("Receipt path reparse point refused")
    # Resolve only after checking each node so symlink escapes cannot quietly
    # become a different allowed directory. This also covers path aliases.
    if allowed.resolve(strict=False) != allowed or dest.resolve(strict=False) != dest:
        raise RuntimeError("Receipt destination resolves through an unsafe path alias")
    return dest


def _git_env():
    # -C never overrides GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE, GIT_CONFIG_*.
    return {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}


def _git(*args, binary=False):
    # Git archive (unlike cat-file) can apply core.autocrlf during export.
    # Disable that conversion ONLY for archive to preserve exact Git blob
    # bytes; status must keep the worktree's normal Windows eol rules.
    options = ["-c", "core.autocrlf=false"] if args and args[0] == "archive" else []
    result = subprocess.run(["git", *options, "-C", str(ROOT), *args], env=_git_env(),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            check=True, timeout=45)
    return result.stdout if binary else result.stdout.decode("utf-8").strip()


def _blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _validate_repo(sha):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("Expected commit must be an explicitly pinned 40-character SHA")
    if any(p.lower() in RELEASE_DIRS for p in ROOT.parts):
        raise RuntimeError("Refusing an installed or protected Elysia runtime path")
    top = Path(_git("rev-parse", "--show-toplevel")).resolve()
    if top != ROOT:
        raise RuntimeError("Runner must reside in the Git worktree root")
    if _git("rev-parse", "HEAD").lower() != sha:
        raise RuntimeError("Checked-out HEAD differs from expected SHA")
    if _git("rev-parse", "--verify", sha + "^{commit}").lower() != sha:
        raise RuntimeError("Expected SHA is not a resolvable commit")
    status = _git("status", "--porcelain=v1", "-z", "--untracked-files=all")
    # Prior generated receipts are non-executable and may remain for comparison.
    for entry in status.split("\0"):
        if not entry:
            continue
        path = entry[3:].replace("\\", "/")
        if entry[:2] == "??" and path.startswith("REPORTS/trusted-memory/") and path.endswith(".json"):
            continue
        raise RuntimeError("Worktree is dirty; refusing to certify different source bytes")


def _extract_pinned(sha, output):
    raw = _git("archive", "--format=zip", sha, binary=True)
    if len(raw) > 180_000_000:
        raise RuntimeError("Pinned Git archive exceeds safety limit")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        seen = set()
        total = 0
        for member in archive.infolist():
            name = member.filename
            parts = PurePosixPath(name).parts
            if not parts or name.startswith("/") or "\\" in name or ":" in name or ".." in parts:
                raise RuntimeError("Unsafe archive path")
            if member.is_dir():
                continue
            if name in seen:
                raise RuntimeError("Duplicate archive entry")
            seen.add(name)
            total += member.file_size
            if total > 300_000_000 or member.file_size > 60_000_000:
                raise RuntimeError("Expanded Git archive exceeds safety limit")
            dest = output.joinpath(*parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, dest.open("xb") as target:
                shutil.copyfileobj(source, target)
    blobs = {}
    for path in SOURCE_FILES:
        line = _git("ls-tree", sha, "--", path)
        matches = re.findall(r"\bblob ([0-9a-f]{40})\t", line)
        if len(matches) != 1:
            raise RuntimeError("Required tracked source blob absent: " + path)
        data = (output / path).read_bytes()
        actual = _blob(data)
        if actual != matches[0]:
            raise RuntimeError("Snapshot bytes differ from pinned Git blob: " + path)
        blobs[path] = actual
    return blobs


def _test_env(home):
    # Do not pass personal paths, secrets, pytest plugins or provider settings.
    keep = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "LD_LIBRARY_PATH"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    for name in ("HOME", "USERPROFILE", "TEMP", "TMP", "TMPDIR"):
        env[name] = str(home)
    env.update({"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1",
                "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    return env


def _test_snapshot(source, temp, report):
    trusted_ini = temp / "pytest-trusted.ini"
    trusted_ini.write_text("[pytest]\naddopts =\n", encoding="utf-8")
    xml = temp / "results.xml"
    cmd = [
        sys.executable, "-I", "-B", "-m", "pytest",
        "-c", str(trusted_ini), "--rootdir", str(source),
        "--noconftest", "-p", "no:cacheprovider", "-q",
        f"--basetemp={temp / 'cases'}", f"--junitxml={xml}",
        "tests/test_memory_integrity_windows.py",
    ]
    ran = subprocess.run(cmd, cwd=source, env=_test_env(temp),
                         capture_output=True, timeout=180)
    report["pytest_exit_code"] = ran.returncode
    if not xml.is_file():
        raise RuntimeError("Pytest produced no JUnit evidence")
    suites = ET.parse(xml).getroot()
    all_suites = list(suites.iter("testsuite"))
    if len(all_suites) != 1:
        raise RuntimeError("Expected exactly one pytest test suite")
    suite = all_suites[0]
    items = list(suite.iter("testcase"))
    outcomes = {}
    failed = skipped = 0
    for item in items:
        classname = item.get("classname", "")
        if classname not in ("test_memory_integrity_windows", "tests.test_memory_integrity_windows"):
            raise RuntimeError("Unexpected test module provenance")
        file = (item.get("file") or "").replace("\\", "/")
        if file and file.lstrip("./") != "tests/test_memory_integrity_windows.py":
            raise RuntimeError("Unexpected testcase file provenance")
        if item.find("failure") is not None or item.find("error") is not None:
            failed += 1
        if item.find("skipped") is not None:
            skipped += 1
        name = (item.get("name") or "").split("[", 1)[0]
        outcomes[name] = outcomes.get(name, 0) + 1
    report.update(cases_total=len(items), cases_passed=len(items) - failed - skipped,
                  cases_failed=failed, cases_skipped=skipped, required=outcomes)
    if (ran.returncode or failed or skipped
            or len(items) != int(suite.get("tests", "-1"))
            or any(int(suite.get(key, "-1")) != 0 for key in ("failures", "errors", "skipped"))):
        raise RuntimeError("Pytest failure, missing case or skipped required assertion")
    for name, expected in REQUIRED.items():
        if outcomes.get(name) != expected:
            raise RuntimeError("Required test missing or wrong parameter count: " + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    sha = args.expected_sha.lower()
    now = datetime.now(timezone.utc)
    evidence = args.evidence or (ROOT / "REPORTS" / "trusted-memory"
                                 / ("receipt-" + now.strftime("%Y%m%dT%H%M%S%fZ") + ".json"))
    report = {"status": "FAIL", "expected_sha": sha, "source_clean": False,
              "snapshot_sha": None, "source_blobs": {},
              "os": platform.platform(), "python": platform.python_version(),
              "timestamp_utc": now.isoformat(), "cases_total": 0,
              "cases_passed": 0, "cases_failed": 0, "cases_skipped": 0,
              "installed_release_tested": False,
              "native_windows_directory_acl_tested": False,
              "operational_data_used": False, "errors": []}
    # An installed source path or redirected report directory is refused
    # BEFORE running tests or creating any file. Unsafe output has no receipt.
    if any(p.lower() in RELEASE_DIRS for p in ROOT.parts):
        print("REFUSED: installed or operational Elysia source path", file=sys.stderr)
        return 1
    try:
        evidence = _checked_receipt_destination(evidence)
    except (OSError, RuntimeError) as exc:
        print(f"REFUSED unsafe receipt destination: {exc}", file=sys.stderr)
        return 1
    try:
        _validate_repo(sha)
        report["source_clean"] = True
        with tempfile.TemporaryDirectory(prefix="elysia_pinned_memory_") as directory:
            temp = Path(directory)
            snapshot = temp / "source"
            snapshot.mkdir()
            report["source_blobs"] = _extract_pinned(sha, snapshot)
            report["snapshot_sha"] = sha
            _test_snapshot(snapshot, temp, report)
        report["status"] = "PASS_SCOPED"
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError,
            zipfile.BadZipFile, ET.ParseError, UnicodeError) as exc:
        report["errors"].append(f"{type(exc).__name__}: {str(exc)[:150]}")
    try:
        evidence = _checked_receipt_destination(evidence)
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence = _checked_receipt_destination(evidence)
        with evidence.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
    except (OSError, RuntimeError) as exc:
        print(f"Could not preserve safe acceptance receipt ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1
    for reason in report["errors"]:
        print("TRUSTED MEMORY REJECTED: " + reason, file=sys.stderr)
    print(f"TRUSTED MEMORY ACCEPTANCE {report['status']} "
          f"sha={sha} cases={report['cases_passed']}/{report['cases_total']} "
          f"receipt={evidence}")
    return 0 if report["status"] == "PASS_SCOPED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
