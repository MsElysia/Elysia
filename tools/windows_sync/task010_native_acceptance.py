#!/usr/bin/env python3
"""Task 010: owner-Windows disposable, native OS acceptance of existing ops_recovery.

PREPARATION ONLY in GitHub. Do not run without fresh owner authorization.
No production data, cloud, installation, runner reconfiguration, or release writes.
Use from outside the source worktree and pin --source-root to the verified commit.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

PINNED_CANONICAL = "f286722736c58b8d626f07e841b29e800efe2d8b"
PINNED_BLOBS = {
    "pilot/pilot_exclusion.py": "77a7d0b2c247e071e77e38d1f99ce8e3276f872f",
    "scripts/run_windows_intel_rc_tests.py": "6c252cea576cb82439e6638e52abf784dc7aefd7",
    "tests/test_windows_ops_recovery.py": "6a46b7638598d283046ac281c5891a0d158c370d",
    "tools/windows_sync/ops_recovery.py": "d41a08badc2ed40b07f29676c5d8216127f7d368",
}
SCRATCH_NAME = "elysia-task010-disposable"
MARKER = "TASK010_SYNTHETIC_ONLY.json"
CLI = (
    "import sys; sys.path.insert(0, sys.argv[1]); "
    "from tools.windows_sync.ops_recovery import main; "
    "raise SystemExit(main(sys.argv[2:]))"
)
MUTEX_HOLDER = """
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / 'pilot'))
from pilot_exclusion import try_acquire_exclusion
root, ready, release = map(Path, sys.argv[2:5])
hold, reason = try_acquire_exclusion(data_root=root, timeout_ms=0)
if hold is None:
    raise SystemExit(3)
try:
    ready.write_text('held', encoding='ascii')
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and not release.exists():
        time.sleep(0.1)
finally:
    hold.release()
"""


class Stop(Exception):
    pass


def demand(ok: bool, code: str) -> None:
    if not ok:
        raise Stop(code)


def _without_inherited_git_overrides() -> dict[str, str]:
    """Pre-trust environment built only from stdlib, never unverified source."""
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith("GIT_")}
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def git(repo: Path, *args: str) -> str:
    # These commands only read identity, worktree state and file blob hashes.
    env = _without_inherited_git_overrides()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        p = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True,
            env=env, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("GIT_PRECHECK_UNAVAILABLE") from exc
    demand(p.returncode == 0, "GIT_PRECHECK_FAILED")
    return p.stdout.strip()


def preflight(repo: Path, parent: Path) -> None:
    demand(os.name == "nt", "WINDOWS_REQUIRED")
    demand(sys.version_info >= (3, 12), "PYTHON_312_REQUIRED")
    try:
        elevated = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError) as exc:
        raise Stop("CANNOT_VERIFY_NON_ELEVATED_TOKEN") from exc
    demand(not elevated, "ELEVATED_SESSION_NOT_AUTHORIZED")
    demand(repo.is_absolute() and repo.is_dir(), "EXISTING_SOURCE_REQUIRED")
    demand(parent.is_absolute() and parent.name.lower() == SCRATCH_NAME,
           "DEDICATED_SCRATCH_NAME_REQUIRED")
    demand(parent.is_dir(), "CREATE_EMPTY_SCRATCH_PARENT_SEPARATELY")
    # Check the actual worktree root before trusting Git HEAD or importing any
    # code from --source-root. A Git worktree's .git FILE is valid; unrelated
    # GIT_DIR/GIT_WORK_TREE/CONFIG routing and source-path aliases are not.
    try:
        resolved_source = repo.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise Stop("SOURCE_ROOT_UNRESOLVED") from exc
    demand(repo == resolved_source, "SOURCE_PATH_ALIAS")
    toplevel = git(repo, "rev-parse", "--show-toplevel")
    demand(bool(toplevel) and Path(toplevel).is_absolute(),
           "GIT_TOPLEVEL_UNVERIFIED")
    try:
        resolved_top = Path(toplevel).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise Stop("GIT_TOPLEVEL_UNVERIFIED") from exc
    demand(resolved_top == resolved_source, "GIT_TOPLEVEL_DIFFERS_FROM_SOURCE")
    demand(git(repo, "rev-parse", "HEAD") == PINNED_CANONICAL,
           "SOURCE_SHA_NOT_PINNED")
    demand(not git(repo, "status", "--porcelain=v1", "--untracked-files=all"),
           "SOURCE_WORKTREE_NOT_CLEAN")
    for path, expected in PINNED_BLOBS.items():
        demand(git(repo, "hash-object", path) == expected,
               "SOURCE_BLOB_MISMATCH")
    sys.path.insert(0, str(repo))
    from tools.windows_sync import ops_recovery as ops
    checked = ops._safe_path(parent)
    demand(checked == parent.resolve(), "SCRATCH_PATH_ALIAS")
    demand(not ops._overlaps(checked, repo.resolve()), "SCRATCH_OVERLAPS_SOURCE")
    # Explicitly reject operational, installed and preserved local roots.
    protected = [
        r"C:\Users\Owner\Elysia-Windows-Integration-Data",
        r"C:\Users\Owner\Elysia-Verified-Pilot-Data",
        r"C:\Users\Owner\Elysia-Windows-Release",
        r"C:\Users\Owner\Elysia-Verified-Pilot",
        r"C:\Users\Owner\Elysia-Sync-State",
        r"C:\Users\Owner\Project guardian",
        r"C:\Users\Owner\Elysia-Dev",
    ]
    if os.environ.get("ELYSIA_PILOT_DATA_ROOT"):
        protected.append(os.environ["ELYSIA_PILOT_DATA_ROOT"])
    for item in protected:
        demand(not ops._overlaps(checked, Path(item).resolve(strict=False)),
               "SCRATCH_OVERLAPS_PROTECTED_ROOT")
    demand(not any(parent.iterdir()), "SCRATCH_PARENT_MUST_BE_EMPTY")


def fixture(root: Path) -> list[str]:
    (root / "memory").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "inbox_state").mkdir()
    (root / "empty-leaf").mkdir()
    names = [
        "memory/guardian_memory.json",
        "memory/guardian_memory.json.memorycore.lock",
        "data/enhanced_tasks.json",
        "data/elysia_timeline.db",
        "inbox_state/import_manifest.jsonl",
    ]
    (root / names[0]).write_text(
        '[{"thought":"TASK010_SYNTHETIC_NEVER_PERSONAL_91"}]', encoding="utf-8"
    )
    (root / names[1]).write_bytes(b"\0")
    (root / names[2]).write_text('{"tasks":[]}', encoding="utf-8")
    (root / names[4]).write_text('{"status":"synthetic"}\n', encoding="utf-8")
    db = sqlite3.connect(root / names[3])
    try:
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("CREATE TABLE synthetic(id INTEGER, note TEXT)")
        db.execute("INSERT INTO synthetic VALUES(1, 'task010-fictional')")
        db.commit()
    finally:
        db.close()
    return names


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def check_synthetic_tree(root: Path, names: list[str]) -> None:
    files = [p for p in root.rglob("*") if p.is_file()]
    actual = {p.relative_to(root).as_posix() for p in files}
    demand(actual == set(names), "UNEXPECTED_SYNTHETIC_SOURCE_FILE")
    demand(sum(p.stat().st_size for p in files) < 1024 * 1024,
           "SYNTHETIC_SOURCE_SIZE_LIMIT")


def invoke(repo: Path, env: dict[str, str], *args: str) -> tuple[int, dict | None]:
    try:
        p = subprocess.run(
            [sys.executable, "-I", "-B", "-c", CLI, str(repo), *args],
            cwd=repo, env=env, capture_output=True, text=True, timeout=35,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("NATIVE_COMMAND_UNAVAILABLE_OR_TIMED_OUT") from exc
    if p.returncode == 0:
        try:
            payload = json.loads(p.stdout)
        except json.JSONDecodeError as exc:
            raise Stop("INVALID_SUCCESS_RECEIPT") from exc
        demand(isinstance(payload, dict), "INVALID_SUCCESS_RECEIPT")
        return 0, payload
    if p.returncode == 2 and p.stderr.startswith("BLOCKED: "):
        return 2, None
    raise Stop("UNEXPECTED_NATIVE_COMMAND_RESULT")


def blocked(repo: Path, env: dict[str, str], dest: Path, *args: str,
            require_absent: bool = True) -> None:
    code, receipt = invoke(repo, env, *args)
    demand(code == 2 and receipt is None, "UNSAFE_COMMAND_WAS_NOT_BLOCKED")
    if require_absent:
        demand(not dest.exists(), "BLOCKED_COMMAND_CREATED_DESTINATION")


def native_mutex_refusal(repo: Path, env: dict[str, str], run: Path, root: Path) -> None:
    ready, release = run / "mutex.held", run / "mutex.release"
    proc = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", MUTEX_HOLDER,
         str(repo), str(root), str(ready), str(release)],
        cwd=repo, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 8
        while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        demand(ready.is_file() and proc.poll() is None, "NATIVE_MUTEX_HOLDER_FAILED")
        dest = run / "snapshot-while-mutex-held"
        blocked(repo, env, dest, "--snapshot-root", str(root),
                "--to", str(dest), "--ack-stopped")
        demand(proc.poll() is None, "MUTEX_HOLDER_EXITED_BEFORE_CHECK")
    finally:
        release.write_text("release", encoding="ascii")
        try:
            proc.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise Stop("MUTEX_HOLDER_DID_NOT_STOP")
    demand(proc.returncode == 0, "MUTEX_HOLDER_EXIT_FAILURE")


def no_leftover_staging(run: Path) -> None:
    demand(not list(run.glob(".elysia-ops-stage-*")), "SNAPSHOT_STAGE_LEFT_BEHIND")
    demand(not list(run.glob(".elysia-restore-stage-*")), "RESTORE_STAGE_LEFT_BEHIND")


def run_synthetic(repo: Path, parent: Path) -> int:
    # Single run, unique generated workspace. NEVER delete it automatically.
    run = Path(tempfile.mkdtemp(prefix="run-", dir=parent))
    marker = run / MARKER
    marker.write_text(json.dumps({
        "type": "task010.synthetic.disposable", "source_sha": PINNED_CANONICAL,
        "real_data_used": False, "auto_cleanup": False,
    }), encoding="utf-8")
    results: list[str] = []
    receipt = {"status": "STOP", "source_sha": PINNED_CANONICAL,
               "synthetic_only": True, "tests": results,
               "operational_runtime_tested": False, "cleanup_performed": False}
    try:
        root = run / "pilot-data"
        names = fixture(root)
        temp = run / "temp"
        temp.mkdir()
        # Child acceptance processes also must not inherit Git routing that
        # could override later identity checks or accidentally target another
        # local repository. Keep normal Git locking semantics for children.
        env = _without_inherited_git_overrides()
        env["ELYSIA_PILOT_DATA_ROOT"] = str(root)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONNOUSERSITE"] = "1"
        env["TEMP"] = str(temp)
        env["TMP"] = str(temp)
        check_synthetic_tree(root, names)
        before = {name: digest(root / name) for name in names}
        snapshot, restored = run / "verified-snapshot", run / "restored"
        blocked(repo, env, snapshot, "--snapshot-root", str(root), "--to", str(snapshot))
        results.append("PASS_REQUIRE_EXPLICIT_STOPPED_ACK")
        blocked(repo, env, snapshot, "--snapshot-root", str(run / "wrong-root"),
                "--to", str(snapshot), "--ack-stopped")
        results.append("PASS_REFUSE_WRONG_SOURCE_ROOT")
        native_mutex_refusal(repo, env, run, root)
        results.append("PASS_REAL_WINDOWS_MUTEX_REFUSAL_AND_RELEASE")
        check_synthetic_tree(root, names)
        code, info = invoke(repo, env, "--snapshot-root", str(root),
                            "--to", str(snapshot), "--ack-stopped")
        demand(code == 0 and info.get("status") == "SNAPSHOT_CREATED_OFFLINE",
               "REAL_POWERSHELL_OR_SNAPSHOT_UNVERIFIED")
        demand(info.get("verified") == "VERIFIED_OFFLINE_SNAPSHOT",
               "SNAPSHOT_SELF_VERIFICATION_FAILED")
        results.append("PASS_REAL_LISTENER_PROBE_AND_NATIVE_SNAPSHOT")
        code, info = invoke(repo, env, "--verify", str(snapshot))
        demand(code == 0 and info.get("status") == "VERIFIED_OFFLINE_SNAPSHOT",
               "SNAPSHOT_VERIFICATION_FAILED")
        results.append("PASS_MANIFEST_HASH_AND_SQLITE_VERIFICATION")
        code, info = invoke(repo, env, "--restore-from", str(snapshot),
                            "--to", str(restored))
        demand(code == 0 and info.get("status") == "RESTORED_TO_ISOLATED_ROOT",
               "FRESH_ISOLATED_RESTORE_FAILED")
        demand((restored / "empty-leaf").is_dir(), "EMPTY_DIRECTORY_LOST")
        for name in names:
            demand(digest(root / name) == before[name], "ORIGINAL_SYNTHETIC_SOURCE_CHANGED")
            demand(digest(restored / name) == before[name], "RESTORED_BYTES_DIFFER")
        with sqlite3.connect(restored / "data" / "elysia_timeline.db") as db:
            demand(db.execute("PRAGMA quick_check").fetchone() == ("ok",),
                   "RESTORED_SQLITE_INVALID")
            demand(db.execute("SELECT note FROM synthetic").fetchone() ==
                   ("task010-fictional",), "RESTORED_SQLITE_CONTENTS_DIFFER")
        demand(json.loads((restored / names[0]).read_text(encoding="utf-8"))[0]
               ["thought"] == "TASK010_SYNTHETIC_NEVER_PERSONAL_91",
               "RESTORED_SYNTHETIC_MEMORY_CONTENTS_DIFFER")
        results.append("PASS_FRESH_RESTORE_BYTE_MATCH_AND_REOPEN")
        occupied = run / "existing-target"
        occupied.mkdir()
        sentinel = occupied / "DO_NOT_OVERWRITE.txt"
        sentinel.write_text("synthetic sentinel", encoding="ascii")
        blocked(repo, env, occupied, "--restore-from", str(snapshot),
                "--to", str(occupied), require_absent=False)
        demand(sentinel.read_text(encoding="ascii") == "synthetic sentinel"
               and {p.name for p in occupied.iterdir()} == {"DO_NOT_OVERWRITE.txt"},
               "EXISTING_TARGET_CHANGED")
        results.append("PASS_EXISTING_TARGET_UNTOUCHED")
        corrupt = run / "corrupt-copy"
        shutil.copytree(snapshot, corrupt)
        (corrupt / "payload" / names[0]).write_bytes(b"synthetic tamper")
        blocked(repo, env, run / "corrupt-restore", "--restore-from", str(corrupt),
                "--to", str(run / "corrupt-restore"))
        results.append("PASS_CORRUPT_SNAPSHOT_REFUSED")
        wal = root / "data" / "elysia_timeline.db-wal"
        wal.write_bytes(b"synthetic WAL")
        try:
            blocked(repo, env, run / "wal-snapshot", "--snapshot-root", str(root),
                    "--to", str(run / "wal-snapshot"), "--ack-stopped")
        finally:
            wal.unlink(missing_ok=True)  # The file was created by this test only.
        results.append("PASS_SQLITE_WAL_REFUSED")
        no_leftover_staging(run)
        results.append("PASS_NO_STAGE_RESIDUE")
        check_synthetic_tree(root, names)
        demand(git(repo, "rev-parse", "HEAD") == PINNED_CANONICAL
               and not git(repo, "status", "--porcelain=v1", "--untracked-files=all"),
               "SOURCE_CHANGED_DURING_TEST")
        for path, expected in PINNED_BLOBS.items():
            demand(git(repo, "hash-object", path) == expected,
                   "SOURCE_BLOB_CHANGED_DURING_TEST")
        results.append("PASS_SOURCE_GIT_IDENTITY_PRESERVED")
        receipt["status"] = "PASS_SYNTHETIC_NATIVE_SNAPSHOT_RESTORE_ONLY"
        return 0
    except (Stop, OSError, ValueError, sqlite3.Error, KeyError, TypeError) as exc:
        # Never copy stderr, filesystem contents or private paths into receipts.
        receipt["stop_code"] = str(exc) if isinstance(exc, Stop) else type(exc).__name__
        return 2
    finally:
        (run / "TASK010_RESULT.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps({"status": receipt["status"], "checks": len(results),
                          "stop_code": receipt.get("stop_code"),
                          "receipt": "TASK010_RESULT.json under newly created run-* folder"},
                         sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True,
                        help="existing clean checkout at exact tested canonical SHA")
    parser.add_argument("--scratch-parent", type=Path, required=True,
                        help="existing EMPTY local fixed-disk directory named Elysia-Task010-Disposable")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true",
                      help="read-only source/scratch checks; default recommended first action")
    mode.add_argument("--execute-synthetic", action="store_true",
                      help="WRITES disposable synthetic files; requires separate owner authority")
    a = parser.parse_args()
    try:
        repo = a.source_root
        parent = a.scratch_parent
        preflight(repo, parent)
        if a.preflight:
            print("PASS_READ_ONLY_PREFLIGHT; NO TEST EXECUTED; NO FILES CREATED")
            return 0
        return run_synthetic(repo, parent)
    except (Stop, OSError, ValueError, RuntimeError) as exc:
        code = str(exc) if isinstance(exc, Stop) else type(exc).__name__
        print("STOP: " + code, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
