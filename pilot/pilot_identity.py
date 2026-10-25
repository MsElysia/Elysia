#!/usr/bin/env python3
"""
Pilot process identity and delivery identity helpers.

Ownership for stop/launch decisions must never rest on PID or runtime marker alone.
Live process executable, entry point, data-root args, and creation time must match.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


ENTRY_REL = Path("scripts") / "start_contained_browser_memory.py"


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    name: str
    executable: str
    command_line: str
    create_filetime: str  # Windows FILETIME as decimal string (exact match)


@dataclass(frozen=True)
class OwnershipVerdict:
    owned: bool
    reason: str
    snapshot: Optional[ProcessSnapshot] = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def expected_entry_path() -> Path:
    return (PILOT_SOURCE_ROOT / ENTRY_REL).resolve()


def read_delivery_identity(source_root: Path = PILOT_SOURCE_ROOT) -> Dict[str, Any]:
    """
    Report actual delivery commit separately from application base.
    Never label a dirty tree as an exact verified delivery SHA.
    """
    info: Dict[str, Any] = {
        "application_base_sha": APPLICATION_BASE_SHA,
        "delivery_commit": None,
        "delivery_tree_clean": False,
        "delivery_status": "unknown",
        "tracked_modifications": [],
        "untracked_product_paths": [],
        "exact_verified_delivery": False,
    }
    git_dir = source_root / ".git"
    if not git_dir.exists() and not (source_root / ".git").is_file():
        # worktree uses .git file
        pass
    try:
        head = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if head.returncode == 0:
            info["delivery_commit"] = (head.stdout or "").strip() or None
        porcelain = subprocess.run(
            ["git", "-C", str(source_root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
        lines = [
            ln for ln in (porcelain.stdout or "").splitlines() if ln.strip()
        ]
        tracked: List[str] = []
        untracked: List[str] = []
        for ln in lines:
            path = ln[3:].strip() if len(ln) > 3 else ln.strip()
            # Keep product-relevant paths visible; still list all porcelain
            if ln.startswith("??"):
                untracked.append(path)
            else:
                tracked.append(f"{ln[:2].strip()} {path}".strip())
        info["tracked_modifications"] = tracked
        info["untracked_product_paths"] = untracked
        info["delivery_tree_clean"] = len(lines) == 0
        if info["delivery_commit"] and info["delivery_tree_clean"]:
            info["delivery_status"] = "clean"
            info["exact_verified_delivery"] = True
        elif info["delivery_commit"]:
            info["delivery_status"] = "modified"
            info["exact_verified_delivery"] = False
        else:
            info["delivery_status"] = "no_git_head"
            info["exact_verified_delivery"] = False
    except OSError as exc:
        info["delivery_status"] = f"git_error:{exc}"
        info["exact_verified_delivery"] = False
    return info


def format_identity_report(info: Dict[str, Any]) -> str:
    lines = [
        f"application_base_sha={info.get('application_base_sha')}",
        f"delivery_commit={info.get('delivery_commit')}",
        f"delivery_status={info.get('delivery_status')}",
        f"exact_verified_delivery={info.get('exact_verified_delivery')}",
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


def _norm_path(value: str) -> str:
    try:
        return str(Path(value).resolve()).lower()
    except OSError:
        return value.replace("/", "\\").lower()


def query_process_snapshot(pid: int) -> Optional[ProcessSnapshot]:
    """Live process identity via Win32_Process + StartTime FILETIME."""
    if pid <= 0:
        return None
    script = f"""
$pidTarget = {int(pid)}
$p = Get-CimInstance Win32_Process -Filter "ProcessId=$pidTarget" -ErrorAction SilentlyContinue
if (-not $p) {{ return }}
$ft = [uint64]0
$exe = [string]$p.ExecutablePath
try {{
  $proc = [System.Diagnostics.Process]::GetProcessById($pidTarget)
  $epoch = [DateTime]'1601-01-01T00:00:00Z'
  $ft = [uint64](($proc.StartTime.ToUniversalTime() - $epoch).Ticks)
  try {{ $exe = $proc.MainModule.FileName }} catch {{ }}
}} catch {{
  if ($p.CreationDate) {{
    $cd = [System.Management.ManagementDateTimeConverter]::ToDateTime($p.CreationDate).ToUniversalTime()
    $epoch = [DateTime]'1601-01-01T00:00:00Z'
    $ft = [uint64](($cd - $epoch).Ticks)
  }}
}}
$obj = [ordered]@{{
  ProcessId = $p.ProcessId
  Name = $p.Name
  ExecutablePath = $exe
  CommandLine = $p.CommandLine
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
        )
    except OSError:
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
    """Return (record, error). error non-empty means malformed/unusable."""
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


def cmdline_has_expected_args(cmdline: str, entry: Path, data_root: Path) -> Tuple[bool, str]:
    cl = cmdline.lower()
    entry_s = _norm_path(str(entry))
    data_s = _norm_path(str(data_root))
    # Command line paths may be quoted and not resolved; compare normalized forms and basename fallbacks
    entry_name = entry.name.lower()
    if entry_s not in _norm_path(cmdline) and entry_name not in cl:
        # also accept forward-slash form in cmdline
        if str(entry).lower().replace("\\", "/") not in cmdline.lower().replace("\\", "/"):
            if entry_name not in cl:
                return False, "command line missing expected entry point"
    if "--disposable-root" not in cl:
        return False, "command line missing --disposable-root"
    # data root must appear after disposable-root
    if data_s not in _norm_path(cmdline) and str(data_root).lower().replace("\\", "/") not in cmdline.lower().replace("\\", "/"):
        return False, "command line missing expected disposable/data root"
    if PILOT_MARKER.lower() not in cl and "elysia_pilot_marker" not in cl:
        # marker is env-only; do not require in cmdline — identity uses entry+data root+create time
        pass
    return True, ""


def verify_live_ownership(
    pid: int,
    runtime: Dict[str, Any],
    *,
    snapshot: Optional[ProcessSnapshot] = None,
) -> OwnershipVerdict:
    """
    Independently verify live process identity against the runtime record.
    PID/marker match alone is never sufficient.
    """
    ok, reason = runtime_identity_complete(runtime)
    if not ok:
        return OwnershipVerdict(False, reason)

    try:
        recorded_pid = int(runtime["pid"])
    except (TypeError, ValueError):
        return OwnershipVerdict(False, "runtime pid is not an integer")
    if recorded_pid != pid:
        return OwnershipVerdict(False, f"pid file {pid} != runtime.pid {recorded_pid}")

    snap = snapshot if snapshot is not None else query_process_snapshot(pid)
    if snap is None:
        return OwnershipVerdict(False, f"unable to query live process identity for pid {pid}")

    if "python" not in snap.name.lower() and "python" not in snap.executable.lower():
        return OwnershipVerdict(False, f"live process is not python ({snap.name!r})", snap)

    recorded_ft = str(runtime.get("process_create_filetime") or "")
    if not recorded_ft or recorded_ft != snap.create_filetime:
        return OwnershipVerdict(
            False,
            "process creation time mismatch (stale or reused PID)",
            snap,
        )

    recorded_exe = _norm_path(str(runtime.get("process_executable") or ""))
    live_exe = _norm_path(snap.executable)
    expected_py = _norm_path(str(runtime.get("python") or PILOT_PYTHON))
    if live_exe != recorded_exe and live_exe != expected_py:
        # venv launcher may resolve to base python.exe — allow if cmdline starts with expected python path
        cl_norm = snap.command_line.lower().replace("/", "\\")
        if expected_py not in cl_norm and Path(expected_py).name.lower() not in cl_norm:
            return OwnershipVerdict(
                False,
                "live executable does not match recorded pilot interpreter",
                snap,
            )

    entry = Path(str(runtime["entry_point"]))
    data_root = Path(str(runtime["data_root"]))
    args_ok, args_reason = cmdline_has_expected_args(snap.command_line, entry, data_root)
    if not args_ok:
        return OwnershipVerdict(False, args_reason, snap)

    # Refuse generic contained-entry substring without disposable-root match (already enforced)
    return OwnershipVerdict(True, "live process identity matches pilot runtime record", snap)


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


def send_ctrl_c(pid: int) -> Tuple[bool, str]:
    """
    Authenticated cooperative shutdown attempt via console Ctrl+C.
    Caller must already have verified ownership.
    """
    # Use PowerShell + Win32 AttachConsole / GenerateConsoleCtrlEvent
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
$ok = [PilotConsoleCtrl]::GenerateConsoleCtrlEvent(0, 0)  # CTRL_C_EVENT
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
        )
    except OSError as exc:
        return False, f"ctrl_c invocation failed: {exc}"
    msg = ((out.stdout or "") + (out.stderr or "")).strip() or f"exit={out.returncode}"
    return out.returncode == 0, msg


def taskkill_pid_only(pid: int, runner=subprocess.run) -> subprocess.CompletedProcess:
    """Termination fallback: single PID only — never /T tree kill."""
    return runner(
        ["taskkill", "/PID", str(int(pid)), "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
