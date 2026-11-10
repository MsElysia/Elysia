#!/usr/bin/env python3
"""Task 011, DRAFT ONLY: disposable real Elysia HTTP continuity through restart and restore.

This script is NOT part of the installed application and has NOT been executed.
Do not run it on an owner machine without new, specific operator authority.
It calls the existing contained GuardianCore/UI and ops_recovery CLI; no new store.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

sys.dont_write_bytecode = True

PINNED = "f286722736c58b8d626f07e841b29e800efe2d8b"
SOURCE_BLOBS = {
    "project_guardian/memory.py": "9ca048d57de589649a2dd6df97b097d152d9e719",
    "project_guardian/contained_startup.py": "0dd6e923c2ef28149f022e86154a99914d82a2be",
    "project_guardian/restricted_runtime_adapter.py": "df8188fb28934a5b4edaf4b4f9e1a75e1175b730",
    "project_guardian/conversation_continuity.py": "92d6795aa347afe1c65e55aa41c7cd6754a669ec",
    "project_guardian/ui_control_panel.py": "aab128fb4bc8c34894bf8ad45b510012c62c611e",
    "scripts/start_contained_browser_memory.py": "5eb1740db6024649466da2a2ea3489591dc2b0cd",
    "tools/windows_sync/ops_recovery.py": "d41a08badc2ed40b07f29676c5d8216127f7d368",
    "pilot/pilot_exclusion.py": "77a7d0b2c247e071e77e38d1f99ce8e3276f872f",
}
SCRATCH_NAME = "elysia-task011-disposable"
HOST = "127.0.0.1"
PORT = 5078  # inside existing pilot's 5065–5085 listener-inventory window
OLDER = "The fictional Veridia-731 beacon is stored inside the silver tower."
CORRECTED = "The fictional Veridia-731 beacon is stored inside the amber tower."
QUERY = "fictional Veridia-731 beacon amber tower"
NEXT_STEP = "Inspect the fictional amber tower."
CLI = (
    "import sys;sys.path.insert(0,sys.argv[1]);"
    "from tools.windows_sync.ops_recovery import main;"
    "raise SystemExit(main(sys.argv[2:]))"
)


class Stop(Exception):
    """No retry, source replacement, release mutation, or implied acceptance."""


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise Stop(reason)


def sanitized_git_environment() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = "NUL"
    return env


def git(repo: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-c", "protocol.allow=never",
             "-C", str(repo), *arguments],
            env=sanitized_git_environment(), capture_output=True,
            text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("GIT_PRECHECK_UNAVAILABLE") from exc
    require(completed.returncode == 0, "GIT_PRECHECK_FAILED")
    return completed.stdout.strip()


def verify_source(repo: Path) -> None:
    require(repo.is_absolute() and repo.is_dir(), "SOURCE_ABSOLUTE_DIRECTORY_REQUIRED")
    try:
        physical = repo.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise Stop("SOURCE_RESOLUTION_FAILED") from exc
    require(repo == physical, "SOURCE_PATH_ALIAS_FORBIDDEN")
    toplevel = git(repo, "rev-parse", "--show-toplevel")
    require(bool(toplevel) and Path(toplevel).is_absolute(), "SOURCE_GIT_TOPLEVEL_INVALID")
    try:
        top = Path(toplevel).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise Stop("SOURCE_GIT_TOPLEVEL_UNRESOLVED") from exc
    require(top == physical, "GIT_WORKTREE_ROOT_DIFFERS")
    require(git(repo, "rev-parse", "HEAD") == PINNED, "SOURCE_NOT_AT_PINNED_SHA")
    require(not git(repo, "status", "--porcelain=v1", "--untracked-files=all"),
            "SOURCE_WORKTREE_NOT_CLEAN")
    # Ordinary porcelain status omits ignored runtime writes (*.log, *.db,
    # caches, etc.). A clean tracked tree alone cannot certify containment.
    # Insist on a genuinely empty ignored/untracked inventory both at initial
    # preflight and after the last stopped synthetic child, without reading,
    # printing, removing, or hashing private ignored files.
    require(not git(repo, "status", "--porcelain=v1", "--ignored",
                    "--untracked-files=all"),
            "SOURCE_HAS_IGNORED_OR_UNTRACKED_FILES")
    for path, expected in SOURCE_BLOBS.items():
        require(git(repo, "hash-object", path) == expected,
                "SOURCE_FILE_BLOB_MISMATCH")


def port_available() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((HOST, PORT))
        except OSError:
            return False
    return True


def preflight(repo: Path, scratch: Path) -> None:
    require(os.name == "nt", "NATIVE_WINDOWS_REQUIRED")
    require(sys.version_info >= (3, 12), "PYTHON_312_OR_LATER_REQUIRED")
    try:
        admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (OSError, AttributeError) as exc:
        raise Stop("NON_ADMIN_IDENTITY_UNVERIFIABLE") from exc
    require(not admin, "ELEVATED_EXECUTION_FORBIDDEN")
    require(scratch.is_absolute() and scratch.is_dir()
            and scratch.name.lower() == SCRATCH_NAME,
            "NEW_EMPTY_DEDICATED_SCRATCH_REQUIRED")
    verify_source(repo)  # Never import source code before trust checks.
    sys.path.insert(0, str(repo))
    from tools.windows_sync import ops_recovery as ops
    physical = ops._safe_path(scratch)
    require(physical == scratch.resolve(strict=True), "SCRATCH_ALIAS")
    protected = [
        repo,
        Path(r"C:\Users\Owner\Elysia-Windows-Integration-Data"),
        Path(r"C:\Users\Owner\Elysia-Verified-Pilot-Data"),
        Path(r"C:\Users\Owner\Elysia-Windows-Release"),
        Path(r"C:\Users\Owner\Elysia-Verified-Pilot"),
        Path(r"C:\Users\Owner\Elysia-Dev"),
        Path(r"C:\Users\Owner\Project guardian"),
        Path(r"C:\Users\Owner\Elysia-Sync-State"),
    ]
    if os.environ.get("ELYSIA_PILOT_DATA_ROOT"):
        protected.append(Path(os.environ["ELYSIA_PILOT_DATA_ROOT"]))
    for item in protected:
        require(not ops._overlaps(physical, item.resolve(strict=False)),
                "SCRATCH_OVERLAPS_PROTECTED_ROOT")
    require(not any(scratch.iterdir()), "SCRATCH_MUST_BE_EMPTY")
    require(port_available(), "OWNED_TEST_PORT_NOT_FREE")


def private_child_environment(root: Path, token: str, marker: str,
                              shutdown_token: str) -> dict[str, str]:
    # Allowlist, not inheritance of credentials, providers or Git routing.
    keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT",
            "PROCESSOR_ARCHITECTURE", "SYSTEMDRIVE"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    temp = root / "temp"
    temp.mkdir(parents=True, exist_ok=True)
    for folder in ("home", "appdata", "localappdata", "cache"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    env.update({
        "TEMP": str(temp), "TMP": str(temp),
        "HOME": str(root / "home"), "USERPROFILE": str(root / "home"),
        "APPDATA": str(root / "appdata"),
        "LOCALAPPDATA": str(root / "localappdata"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "HF_HOME": str(root / "cache"),
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        "ELYSIA_PILOT_PYTHON": sys.executable,
        "ELYSIA_DISPOSABLE_ROOT": str(root),
        "ELYSIA_PILOT_DATA_ROOT": str(root),
        "ELYSIA_PREFERRED_UI_PORT": str(PORT),
        "ELYSIA_SYNC_ON_LAUNCH": "0",
        "ELYSIA_LOCAL_MODEL": "",  # Restricted deterministic path only.
        "ELYSIA_AUTO_LEARNING": "false",
        "ELYSIA_PILOT_MARKER": marker,
        "ELYSIA_PILOT_SHUTDOWN_TOKEN": shutdown_token,
        "ELYSIA_DASHBOARD_OPERATOR_TOKEN": token,
    })
    return env


@dataclass
class Session:
    process: subprocess.Popen
    root: Path
    token: str
    marker: str
    shutdown_token: str
    stop_requested: bool = False


def http(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    require(path.startswith("/api/") and "://" not in path, "NONLOCAL_HTTP_PATH")
    headers = {
        "Accept": "application/json",
        "X-Elysia-Identity": "dashboard-operator",
        "X-Elysia-Token": token,
    }
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    conn = http.client.HTTPConnection(HOST, PORT, timeout=4)
    try:
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        raw = response.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024, "HTTP_RESPONSE_SIZE_LIMIT")
        parsed = json.loads(raw) if raw else {}
        require(isinstance(parsed, dict), "HTTP_NONOBJECT_RESPONSE")
        return response.status, parsed
    finally:
        conn.close()


def checked_api(method: str, path: str, token: str, body: dict | None = None,
                expected: int = 200) -> dict:
    try:
        code, data = http(method, path, token, body)
    except (OSError, http.client.HTTPException, ValueError,
            UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Stop("LOCAL_HTTP_FAILED") from exc
    require(code == expected and (data.get("ok") is True or data.get("success") is True),
            "APPLICATION_ENDPOINT_UNVERIFIED")
    return data


def start(repo: Path, root: Path, run: Path, phase: str) -> Session:
    require(port_available(), "TEST_PORT_UNEXPECTEDLY_OCCUPIED")
    token = secrets.token_urlsafe(24)
    shutdown_token = secrets.token_hex(16)
    marker = "task011-" + secrets.token_hex(8)
    env = private_child_environment(root, token, marker, shutdown_token)
    command = [
        sys.executable, "-I", "-B",
        str(repo / "scripts" / "start_contained_browser_memory.py"),
        "--disposable-root", str(root),
        "--enable-ui", "--auto-start-ui", "--ui-host", HOST,
        "--ui-port", str(PORT), "--keep-alive",
    ]
    with (run / (phase + ".log")).open("x", encoding="utf-8") as log:
        try:
            proc = subprocess.Popen(
                command, cwd=repo, env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT,
            )
        except OSError as exc:
            raise Stop("CONTAINED_APP_START_FAILED") from exc
    return Session(proc, root, token, marker, shutdown_token)


def await_ready(session: Session) -> None:
    proc, root, token = session.process, session.root, session.token
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        require(proc.poll() is None, "CONTAINED_APP_EXITED_BEFORE_READY")
        try:
            status, data = http("GET", "/api/restricted/v1/memory-store", token)
            store = data.get("memory_store") if isinstance(data, dict) else None
            if status == 200 and data.get("ok") is True and isinstance(store, dict):
                require(store.get("module") == "project_guardian.memory.MemoryCore",
                        "WRONG_APPLICATION_MEMORY_MODULE")
                reported = Path(str(store.get("filepath") or ""))
                require(reported.resolve(strict=False) ==
                        (root / "memory" / "guardian_memory.json").resolve(strict=False),
                        "APPLICATION_MEMORY_ROOT_MISMATCH")
                return
        except (OSError, http.client.HTTPException, ValueError, UnicodeDecodeError,
                json.JSONDecodeError):
            pass
        time.sleep(0.5)
    raise Stop("CONTAINED_APPLICATION_NOT_READY")


def cooperative_stop(session: Session) -> None:
    require(not session.stop_requested, "DUPLICATE_STOP_REQUEST")
    session.stop_requested = True
    require(session.process.poll() is None, "CHILD_EXITED_BEFORE_COOPERATIVE_STOP")
    shutdown = session.root / "runtime" / "shutdown.request"
    require(shutdown.parent.is_dir(), "EXPECTED_CHILD_RUNTIME_DIR_ABSENT")
    shutdown.write_text(json.dumps({
        "marker": session.marker, "shutdown_token": session.shutdown_token,
    }), encoding="utf-8")
    try:
        code = session.process.wait(timeout=45)
    except subprocess.TimeoutExpired as exc:
        raise Stop("COOPERATIVE_SHUTDOWN_TIMED_OUT_CHILD_RETAINED") from exc
    require(code == 0, "COOPERATIVE_SHUTDOWN_NONZERO")
    require(port_available(), "TEST_PORT_STILL_LISTENING_AFTER_STOP")


def fact_history(token: str, fact_id: str) -> None:
    history = checked_api(
        "GET", f"/api/restricted/v1/facts/{fact_id}/history", token,
    )
    rows = history.get("revisions")
    require(isinstance(rows, list) and len(rows) == 2, "FACT_HISTORY_NOT_DURABLE")
    require([row.get("revision") for row in rows] == [1, 2],
            "FACT_REVISION_ORDER_INVALID")
    require(rows[0].get("statement") == OLDER
            and rows[1].get("statement") == CORRECTED
            and rows[1].get("current") is True
            and rows[0].get("current") is False,
            "CURRENT_FACT_CORRECTION_INVALID")


def chat_recall(token: str, fact_id: str) -> None:
    result = checked_api(
        "POST", "/api/chat", token,
        {"message": QUERY, "use_local_model": False, "allow_calculator": False},
    )
    matches = result.get("matches")
    require(result.get("provider") == "restricted-memory"
            and isinstance(matches, list)
            and any(
                row.get("fact_id") == fact_id and row.get("revision") == 2
                and row.get("statement") == CORRECTED
                for row in matches
            ),
            "APP_CHAT_DID_NOT_RECALL_CORRECTED_FACT")
    reply = result.get("reply")
    require(isinstance(reply, str) and CORRECTED in reply
            and OLDER not in reply, "APP_CHAT_REPLY_NOT_CURRENT_FACT")


def resume(token: str, conversation_id: str) -> None:
    result = checked_api(
        "POST", f"/api/conversations/{conversation_id}/resume", token, {},
    )
    require(result.get("conversation_id") == conversation_id
            and result.get("continuity_recovered") is True
            and result.get("next_safe_action") == NEXT_STEP
            and result.get("authorization_inherited") is False,
            "CONVERSATION_CHECKPOINT_NOT_RECOVERED")


def teach_and_checkpoint(token: str) -> tuple[str, str]:
    # A successful status alone never certifies real saved MemoryCore state.
    code, unauth = http("POST", "/api/restricted/v1/facts", "", {"statement": OLDER})
    require(code == 401 and unauth.get("ok") is not True,
            "RESTRICTED_AUTHENTICATION_NOT_ENFORCED")
    forbidden_code, forbidden = http(
        "POST", "/api/restricted/v1/autonomy/activate", token, {},
    )
    require(forbidden_code == 403 and forbidden.get("ok") is not True,
            "CONTAINED_AUTONOMY_HARD_DENY_FAILED")
    taught = checked_api(
        "POST", "/api/restricted/v1/facts", token,
        {"statement": OLDER}, expected=201,
    )
    fact = taught.get("fact")
    require(taught.get("persistence_verified") is True
            and isinstance(fact, dict)
            and isinstance(fact.get("fact_id"), str)
            and re.fullmatch(r"fact_[a-f0-9]{16}", fact["fact_id"]),
            "TEACH_DURABILITY_NOT_VERIFIED")
    fact_id = fact["fact_id"]
    correction = checked_api(
        "POST", f"/api/restricted/v1/facts/{fact_id}/corrections", token,
        {"statement": CORRECTED},
    )
    require(correction.get("persistence_verified") is True,
            "CORRECTION_DURABILITY_NOT_VERIFIED")
    fact_history(token, fact_id)
    chat_recall(token, fact_id)

    created = checked_api(
        "POST", "/api/conversations", token,
        {"title": "Task011 fictional beacon",
         "objective": "Safely inspect a fictional beacon",
         "constraints": ["Synthetic data only"]},
        expected=201,
    )
    conversation_id = created.get("conversation_id")
    require(isinstance(conversation_id, str) and bool(conversation_id),
            "CONVERSATION_CREATE_FAILED")
    checked_api(
        "PATCH", f"/api/conversations/{conversation_id}", token,
        {"completed_work": ["Fictional beacon located"],
         "outstanding_steps": [NEXT_STEP],
         "next_safe_action": NEXT_STEP,
         "confirmed_facts": [CORRECTED]},
    )
    checkpoint = checked_api(
        "POST", f"/api/conversations/{conversation_id}/checkpoint", token, {},
    )
    require(isinstance(checkpoint.get("checkpoint"), dict),
            "CONVERSATION_CHECKPOINT_UNVERIFIED")
    return fact_id, conversation_id


def recovered_application(token: str, fact_id: str, conversation_id: str) -> None:
    fact_history(token, fact_id)
    chat_recall(token, fact_id)
    resume(token, conversation_id)


def ops_cli(repo: Path, active: Path, run: Path, *arguments: str) -> dict:
    env = private_child_environment(
        active, secrets.token_urlsafe(24),
        "task011-ops-" + secrets.token_hex(4), secrets.token_hex(16),
    )
    # No provider requests, explicit source root and only the existing CLI.
    cmd = [sys.executable, "-I", "-B", "-c", CLI, str(repo), *arguments]
    try:
        proc = subprocess.run(
            cmd, cwd=repo, env=env,
            capture_output=True, text=True, timeout=90, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("OFFLINE_RECOVERY_CLI_UNAVAILABLE") from exc
    require(proc.returncode == 0, "OFFLINE_RECOVERY_CLI_REFUSED")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise Stop("OFFLINE_RECOVERY_CLI_BAD_RECEIPT") from exc
    require(isinstance(payload, dict), "OFFLINE_RECOVERY_CLI_BAD_RECEIPT")
    return payload


def sha256(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def run_once(repo: Path, scratch: Path) -> int:
    run = Path(tempfile.mkdtemp(prefix="run-", dir=scratch))
    (run / "TASK011_SYNTHETIC_ONLY.json").write_text(json.dumps({
        "type": "task011.disposable.application-continuity",
        "source_sha": PINNED, "real_data_used": False, "auto_cleanup": False,
    }), encoding="utf-8")
    checks: list[str] = []
    receipt = {
        "status": "STOP", "source_sha": PINNED, "synthetic_only": True,
        "tests": checks, "operational_runtime_tested": False,
        "installed_release_tested": False, "cleanup_performed": False,
    }
    current: Session | None = None
    try:
        active = run / "active"
        active.mkdir()
        current = start(repo, active, run, "initial")
        await_ready(current)
        checks.append("PASS_CONTAINED_APP_INITIAL_START_AND_STORE_IDENTITY")
        fact_id, conversation_id = teach_and_checkpoint(current.token)
        checks.append("PASS_APP_TEACH_CORRECT_CHAT_AND_CHECKPOINT")
        cooperative_stop(current)
        current = None
        checks.append("PASS_COOPERATIVE_SHUTDOWN_ONE")
        current = start(repo, active, run, "normal-restart")
        await_ready(current)
        recovered_application(current.token, fact_id, conversation_id)
        checks.append("PASS_SAME_ROOT_RESTART_FACT_AND_CONVERSATION_RECALL")
        cooperative_stop(current)
        current = None
        checks.append("PASS_COOPERATIVE_SHUTDOWN_TWO")

        # Task009 snapshot is allowed only after stopped-writer verification.
        snapshot = run / "snapshot"
        made = ops_cli(
            repo, active, run, "--snapshot-root", str(active),
            "--to", str(snapshot), "--ack-stopped",
        )
        require(made.get("status") == "SNAPSHOT_CREATED_OFFLINE"
                and made.get("verified") == "VERIFIED_OFFLINE_SNAPSHOT",
                "OFFLINE_SNAPSHOT_NOT_VERIFIED")
        verified = ops_cli(repo, active, run, "--verify", str(snapshot))
        require(verified.get("status") == "VERIFIED_OFFLINE_SNAPSHOT",
                "SNAPSHOT_MANIFEST_VERIFICATION_FAILED")
        checks.append("PASS_STOPPED_APP_OFFLINE_SNAPSHOT")

        recovered = run / "recovered"
        restored = ops_cli(
            repo, active, run, "--restore-from", str(snapshot),
            "--to", str(recovered),
        )
        require(restored.get("status") == "RESTORED_TO_ISOLATED_ROOT",
                "ISOLATED_RECOVERY_NOT_PUBLISHED")
        primary_rel = Path("memory") / "guardian_memory.json"
        source_memory_sha = sha256(active / primary_rel)
        require(source_memory_sha == sha256(recovered / primary_rel)
                and sha256(snapshot / "payload" / primary_rel) ==
                sha256(recovered / primary_rel),
                "RECOVERED_MEMORY_BYTES_DIFFER_FROM_SNAPSHOT")
        checks.append("PASS_SEPARATE_RESTORED_MEMORY_BYTE_IDENTITY")

        # This third process boots ONLY from restored files, not from active.
        current = start(repo, recovered, run, "recovered-start")
        await_ready(current)
        recovered_application(current.token, fact_id, conversation_id)
        checks.append("PASS_APPLICATION_RECALL_FROM_ISOLATED_RESTORE")
        cooperative_stop(current)
        current = None
        checks.append("PASS_COOPERATIVE_SHUTDOWN_RECOVERED_APP")
        require(sha256(active / primary_rel) == source_memory_sha,
                "RECOVERY_CHANGED_ORIGINAL_SYNTHETIC_MEMORY")
        checks.append("PASS_ORIGINAL_SYNTHETIC_MEMORY_UNCHANGED_BY_RECOVERY")

        verify_source(repo)
        checks.append("PASS_PINNED_SOURCE_UNMODIFIED")
        require(port_available(), "TEST_PORT_LEFT_OCCUPIED")
        receipt["status"] = "PASS_SYNTHETIC_APPLICATION_RESTART_AND_RECOVERY"
        return 0
    except (Stop, OSError, ValueError, TypeError, KeyError,
            http.client.HTTPException, json.JSONDecodeError) as exc:
        receipt["stop_code"] = str(exc) if isinstance(exc, Stop) else type(exc).__name__
        return 2
    finally:
        # One cooperative stop for a test-created child, never taskkill/force kill.
        if current is not None and current.process.poll() is None:
            if not current.stop_requested:
                try:
                    cooperative_stop(current)
                except (Stop, OSError):
                    pass
            receipt["test_child_still_running"] = current.process.poll() is None
        else:
            receipt["test_child_still_running"] = False
        (run / "TASK011_RESULT.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "status": receipt["status"], "checks": len(checks),
            "stop_code": receipt.get("stop_code"),
            "test_child_still_running": receipt["test_child_still_running"],
            "receipt": "TASK011_RESULT.json inside new run-* directory",
        }, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--scratch-parent", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true",
                      help="Read-only pinned-source, destination and port inspection")
    mode.add_argument("--execute-synthetic", action="store_true",
                      help="Run real contained app only on disposable synthetic data")
    args = parser.parse_args()
    try:
        preflight(args.source_root, args.scratch_parent)
        if args.preflight:
            print("PASS_READ_ONLY_TASK011_PREFLIGHT; NOTHING_EXECUTED")
            return 0
        return run_once(args.source_root, args.scratch_parent)
    except (Stop, OSError, RuntimeError, ValueError) as exc:
        code = str(exc) if isinstance(exc, Stop) else type(exc).__name__
        print("STOP: " + code, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
