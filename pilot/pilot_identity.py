#!/usr/bin/env python3
"""
Pilot process identity and delivery identity helpers.

Ownership decisions require exact executable / parsed-argv entry / disposable-root
matches plus OS handle-backed instance identity. PID or runtime marker alone is
never sufficient. Git identity failures fail closed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_PILOT_DIR = Path(__file__).resolve().parent
if str(_PILOT_DIR) not in sys.path:
    sys.path.insert(0, str(_PILOT_DIR))

from pilot_paths import (
    APPLICATION_BASE_SHA,
    PILOT_MARKER,
    PILOT_PYTHON,
    PILOT_SOURCE_ROOT,
    RUNTIME_DIR,
    SHUTDOWN_REQUEST_FILE,
)
from pilot_winprocess import BoundProcess, parse_command_line

ENTRY_REL = Path("scripts") / "start_contained_browser_memory.py"

# Overridable for tests
_GIT_RUNNER: Callable[..., subprocess.CompletedProcess] = subprocess.run
_GIT_TIMEOUT_SEC = 15.0


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    name: str
    executable: str
    command_line: str
    create_filetime: str


@dataclass(frozen=True)
class OwnershipVerdict:
    owned: bool
    reason: str
    snapshot: Optional[ProcessSnapshot] = None
    bound: Optional[BoundProcess] = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def expected_entry_path() -> Path:
    return (PILOT_SOURCE_ROOT / ENTRY_REL).resolve()


def _norm_path(value: str) -> str:
    try:
        return str(Path(value).resolve()).lower()
    except OSError:
        return value.replace("/", "\\").lower()


def read_delivery_identity(source_root: Path = PILOT_SOURCE_ROOT) -> Dict[str, Any]:
    """
    Report delivery commit separately from application base.
    Any failed/unavailable/unreadable/malformed git identity check =>
    exact_verified_delivery=false with diagnostic.
    """
    info: Dict[str, Any] = {
        "application_base_sha": APPLICATION_BASE_SHA,
        "delivery_commit": None,
        "delivery_tree_clean": False,
        "delivery_status": "unknown",
        "tracked_modifications": [],
        "untracked_product_paths": [],
        "exact_verified_delivery": False,
        "identity_diagnostic": "",
    }

    def _fail(status: str, diagnostic: str) -> Dict[str, Any]:
        info["delivery_status"] = status
        info["exact_verified_delivery"] = False
        info["delivery_tree_clean"] = False
        info["identity_diagnostic"] = diagnostic
        return info

    try:
        head = _GIT_RUNNER(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return _fail("git_timeout", "git rev-parse HEAD timed out")
    except OSError as exc:
        return _fail("git_unavailable", f"git rev-parse OSError: {exc}")

    if head.returncode != 0:
        return _fail(
            "git_head_failed",
            f"git rev-parse HEAD rc={head.returncode} stderr={(head.stderr or '').strip()}",
        )
    commit = (head.stdout or "").strip()
    if not commit:
        return _fail("git_head_empty", "git rev-parse HEAD returned empty stdout")
    commit_l = commit.lower()
    if len(commit_l) < 7 or any(c not in "0123456789abcdef" for c in commit_l):
        return _fail("git_head_malformed", f"unexpected HEAD output: {commit!r}")
    info["delivery_commit"] = commit_l

    try:
        porcelain = _GIT_RUNNER(
            ["git", "-C", str(source_root), "status", "--porcelain=v1", "--untracked-files=all"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return _fail("git_timeout", "git status timed out")
    except OSError as exc:
        return _fail("git_unavailable", f"git status OSError: {exc}")

    if porcelain.returncode != 0:
        return _fail(
            "git_status_failed",
            f"git status rc={porcelain.returncode} stderr={(porcelain.stderr or '').strip()}",
        )

    lines = [ln for ln in (porcelain.stdout or "").splitlines() if ln.strip()]
    tracked: List[str] = []
    untracked: List[str] = []
    for ln in lines:
        path = ln[3:].strip() if len(ln) > 3 else ln.strip()
        if ln.startswith("??"):
            untracked.append(path)
        else:
            tracked.append(f"{ln[:2].strip()} {path}".strip())
    info["tracked_modifications"] = tracked
    info["untracked_product_paths"] = untracked
    info["delivery_tree_clean"] = len(lines) == 0
    if info["delivery_tree_clean"]:
        info["delivery_status"] = "clean"
        info["exact_verified_delivery"] = True
        info["identity_diagnostic"] = "ok"
    else:
        info["delivery_status"] = "modified"
        info["exact_verified_delivery"] = False
        info["identity_diagnostic"] = "working_tree_not_clean"
    return info


def format_identity_report(info: Dict[str, Any]) -> str:
    lines = [
        f"application_base_sha={info.get('application_base_sha')}",
        f"delivery_commit={info.get('delivery_commit')}",
        f"delivery_status={info.get('delivery_status')}",
        f"exact_verified_delivery={info.get('exact_verified_delivery')}",
        f"identity_diagnostic={info.get('identity_diagnostic')}",
    ]
    tracked = info.get("tracked_modifications") or []
    untracked = info.get("untracked_product_paths") or []
    if tracked:
        lines.append("tracked_modifications:")
        lines.extend(f"  - {t}" for t in tracked)
    else:
        lines.append("tracked_modifications: (none)")
    if untracked:
        lines.append("untracked_product_paths:")
        lines.extend(f"  - {u}" for u in untracked)
    else:
        lines.append("untracked_product_paths: (none)")
    return "\n".join(lines)


def query_process_snapshot(pid: int) -> Optional[ProcessSnapshot]:
    """
    Single-shot snapshot via one PowerShell CIM query (no mixed late Process API).
    Prefer BoundProcess.open for ownership actions.
    """
    if pid <= 0:
        return None
    script = f"""
$pidTarget = {int(pid)}
$p = Get-CimInstance Win32_Process -Filter "ProcessId=$pidTarget" -ErrorAction SilentlyContinue
if (-not $p) {{ return }}
$ft = [uint64]0
if ($p.CreationDate) {{
  $cd = [System.Management.ManagementDateTimeConverter]::ToDateTime($p.CreationDate).ToUniversalTime()
  $epoch = [DateTime]'1601-01-01T00:00:00Z'
  $ft = [uint64](($cd - $epoch).Ticks)
}}
$obj = [ordered]@{{
  ProcessId = $p.ProcessId
  Name = $p.Name
  ExecutablePath = [string]$p.ExecutablePath
  CommandLine = [string]$p.CommandLine
  CreateFiletime = "$ft"
}}
$obj | ConvertTo-Json -Compress
"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    raw = (out.stdout or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not data or not data.get("ProcessId"):
        return None
    return ProcessSnapshot(
        pid=int(data["ProcessId"]),
        name=str(data.get("Name") or ""),
        executable=str(data.get("ExecutablePath") or ""),
        command_line=str(data.get("CommandLine") or ""),
        create_filetime=str(data.get("CreateFiletime") or ""),
    )


def load_runtime_record(path: Path) -> Tuple[Optional[Dict[str, Any]], str]:
    if not path.is_file():
        return None, "runtime record missing"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"runtime record unreadable: {exc}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"runtime record malformed JSON: {exc}"
    if not isinstance(data, dict):
        return None, "runtime record is not an object"
    return data, ""


REQUIRED_RUNTIME_FIELDS = (
    "marker",
    "pid",
    "python",
    "entry_point",
    "data_root",
    "process_create_filetime",
    "process_executable",
    "shutdown_token",
    "application_base_sha",
    "delivery_commit",
)


def runtime_identity_complete(runtime: Dict[str, Any]) -> Tuple[bool, str]:
    missing = [k for k in REQUIRED_RUNTIME_FIELDS if not runtime.get(k) and runtime.get(k) != 0]
    if missing:
        return False, f"runtime missing required identity fields: {', '.join(missing)}"
    if runtime.get("marker") != PILOT_MARKER:
        return False, "runtime marker is not the verified pilot marker"
    return True, ""


def argv_matches_expected(
    cmdline: str,
    *,
    expected_python: Path,
    expected_entry: Path,
    expected_data_root: Path,
    recorded_executable: str = "",
) -> Tuple[bool, str]:
    """Exact parsed-argv checks — no basename-only or decoy substring acceptance."""
    try:
        argv = list(parse_command_line(cmdline))
    except OSError as exc:
        return False, f"cmdline_parse_failed:{exc}"
    if len(argv) < 4:
        return False, "cmdline_too_short"

    py_n = _norm_path(str(expected_python))
    entry_n = _norm_path(str(expected_entry))
    data_n = _norm_path(str(expected_data_root))
    recorded_n = _norm_path(recorded_executable) if recorded_executable else ""

    argv0 = _norm_path(argv[0])
    if argv0 not in {py_n, recorded_n} and Path(argv0).name not in {
        Path(py_n).name,
        "python.exe",
        "pythonw.exe",
    }:
        # Allow venv launcher vs base image only when entry/data-root exact below
        if recorded_n and argv0 != recorded_n and py_n not in argv0:
            pass  # continue to entry checks; executable checked separately via handle
    entry_indexes = [i for i, a in enumerate(argv) if _norm_path(a) == entry_n]
    if len(entry_indexes) != 1:
        return False, "exact_entry_path_not_in_argv"

    root_indexes = [i for i, a in enumerate(argv) if a.lower() == "--disposable-root"]
    if len(root_indexes) != 1:
        return False, "expected_exactly_one_disposable_root_flag"
    ri = root_indexes[0]
    if ri + 1 >= len(argv):
        return False, "disposable_root_missing_value"
    if _norm_path(argv[ri + 1]) != data_n:
        return False, "disposable_root_value_mismatch"
    return True, ""


def verify_live_ownership(
    pid: int,
    runtime: Dict[str, Any],
    *,
    snapshot: Optional[ProcessSnapshot] = None,
    bound: Optional[BoundProcess] = None,
) -> OwnershipVerdict:
    ok, reason = runtime_identity_complete(runtime)
    if not ok:
        return OwnershipVerdict(False, reason)

    try:
        recorded_pid = int(runtime["pid"])
    except (TypeError, ValueError):
        return OwnershipVerdict(False, "runtime pid is not an integer")
    if recorded_pid != pid:
        return OwnershipVerdict(False, f"pid file {pid} != runtime.pid {recorded_pid}")

    snap = snapshot
    action_bound = bound
    opened_here = False

    def _reject(msg: str, s: Optional[ProcessSnapshot] = None) -> OwnershipVerdict:
        if opened_here and action_bound is not None:
            action_bound.close()
        return OwnershipVerdict(False, msg, s)

    if action_bound is not None and snap is None:
        # Caller supplied handle: derive identity from handle + one CIM cmdline query
        cim = query_process_snapshot(pid)
        if cim is None:
            return _reject("cmdline_query_failed_after_handle_bind")
        if cim.pid != pid:
            return _reject(f"cim pid {cim.pid} != requested pid {pid}")
        snap = ProcessSnapshot(
            pid=action_bound.pid,
            name=cim.name or Path(action_bound.image_path).name,
            executable=action_bound.image_path,
            command_line=cim.command_line,
            create_filetime=action_bound.create_filetime,
        )
    elif action_bound is None and snap is None:
        action_bound, berr = BoundProcess.open(pid)
        if action_bound is None:
            return OwnershipVerdict(False, f"unable to bind live process handle: {berr}")
        opened_here = True
        cim = query_process_snapshot(pid)
        if cim is None:
            return _reject("cmdline_query_failed_after_handle_bind")
        snap = ProcessSnapshot(
            pid=action_bound.pid,
            name=cim.name or Path(action_bound.image_path).name,
            executable=action_bound.image_path,
            command_line=cim.command_line,
            create_filetime=action_bound.create_filetime,
        )

    if snap is None:
        return _reject("no process snapshot")

    if snap.pid != pid:
        return _reject(f"snapshot pid {snap.pid} != requested pid {pid}", snap)

    if not snap.executable:
        return _reject("executable path empty", snap)

    recorded_ft = str(runtime.get("process_create_filetime") or "")
    if not recorded_ft or recorded_ft != snap.create_filetime:
        return _reject("process creation time mismatch (stale or reused PID)", snap)

    recorded_exe = _norm_path(str(runtime.get("process_executable") or ""))
    live_exe = _norm_path(snap.executable)
    expected_py = _norm_path(str(runtime.get("python") or PILOT_PYTHON))
    # Exact executable match against recorded image and/or configured interpreter path.
    # Never accept merely because the command line mentions the interpreter string.
    if live_exe != recorded_exe and live_exe != expected_py:
        return _reject("live executable does not match recorded pilot interpreter", snap)

    entry = Path(str(runtime["entry_point"]))
    data_root = Path(str(runtime["data_root"]))
    if not snap.command_line:
        return _reject("command line empty", snap)
    args_ok, args_reason = argv_matches_expected(
        snap.command_line,
        expected_python=Path(str(runtime.get("python") or PILOT_PYTHON)),
        expected_entry=entry,
        expected_data_root=data_root,
        recorded_executable=str(runtime.get("process_executable") or ""),
    )
    if not args_ok:
        return _reject(args_reason, snap)

    return OwnershipVerdict(
        True,
        "live process identity matches pilot runtime record",
        snap,
        action_bound,
    )


def write_shutdown_request(token: str) -> Path:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "marker": PILOT_MARKER,
        "shutdown_token": token,
        "requested_utc": utc_now_iso(),
    }
    SHUTDOWN_REQUEST_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return SHUTDOWN_REQUEST_FILE


def clear_shutdown_request() -> None:
    try:
        SHUTDOWN_REQUEST_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def read_shutdown_request() -> Optional[Dict[str, Any]]:
    if not SHUTDOWN_REQUEST_FILE.is_file():
        return None
    try:
        data = json.loads(SHUTDOWN_REQUEST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def send_ctrl_c(pid: int) -> Tuple[bool, str]:
    """
    Best-effort console Ctrl+C. Prefer shutdown.request polling in the owned runtime.
    Does not authorize termination by itself.
    """
    script = f"""
$pidTarget = {int(pid)}
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class PilotConsoleCtrl {{
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool AttachConsole(uint dwProcessId);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool FreeConsole();
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool GenerateConsoleCtrlEvent(uint dwCtrlEvent, uint dwProcessGroupId);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool SetConsoleCtrlHandler(IntPtr handler, bool add);
}}
"@
[void][PilotConsoleCtrl]::FreeConsole()
if (-not [PilotConsoleCtrl]::AttachConsole([uint32]$pidTarget)) {{
  Write-Output "attach_failed:$([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
  exit 1
}}
[void][PilotConsoleCtrl]::SetConsoleCtrlHandler([IntPtr]::Zero, $true)
$ok = [PilotConsoleCtrl]::GenerateConsoleCtrlEvent(0, 0)
$err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
[void][PilotConsoleCtrl]::FreeConsole()
if ($ok) {{ Write-Output "ctrl_c_sent"; exit 0 }}
Write-Output "ctrl_c_failed:$err"
exit 1
"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"ctrl_c_invocation_failed:{exc}"
    msg = ((out.stdout or "") + (out.stderr or "")).strip() or f"exit={out.returncode}"
    return out.returncode == 0, msg


def taskkill_pid_only(pid: int, runner=subprocess.run) -> subprocess.CompletedProcess:
    """Deprecated for ownership stops — prefer BoundProcess.terminate(). Kept for tests."""
    return runner(
        ["taskkill", "/PID", str(int(pid)), "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
