#!/usr/bin/env python3
"""
Cross-process exclusion for pilot launch / inbox apply.

Uses a Windows named mutex keyed by the pilot data root so launch, stop
coordination, and manual inbox scans share one exclusion domain.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import subprocess
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from pilot_paths import (
    PILOT_DATA_ROOT,
    PILOT_SOURCE_ROOT,
    PREFERRED_UI_HOST,
    PREFERRED_UI_PORT,
    PORT_SCAN_END,
)
from pilot_winprocess import parse_command_line

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CreateMutexW = kernel32.CreateMutexW
CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
CreateMutexW.restype = wintypes.HANDLE

WaitForSingleObject = kernel32.WaitForSingleObject
WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
WaitForSingleObject.restype = wintypes.DWORD

ReleaseMutex = kernel32.ReleaseMutex
ReleaseMutex.argtypes = [wintypes.HANDLE]
ReleaseMutex.restype = wintypes.BOOL

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x102
WAIT_ABANDONED = 0x80
ERROR_ALREADY_EXISTS = 183


def mutex_name_for_data_root(data_root: Path = PILOT_DATA_ROOT) -> str:
    digest = hashlib.sha256(str(data_root.resolve()).lower().encode("utf-8")).hexdigest()[:24]
    return f"Local\\ElysiaVerifiedPilot-{digest}"


@dataclass
class ExclusionHold:
    handle: int
    name: str

    def release(self) -> None:
        if self.handle:
            try:
                ReleaseMutex(self.handle)
            except Exception:
                pass
            CloseHandle(self.handle)
            self.handle = 0


def try_acquire_exclusion(
    *,
    data_root: Path = PILOT_DATA_ROOT,
    timeout_ms: int = 0,
) -> Tuple[Optional[ExclusionHold], str]:
    """
    Non-blocking (default) acquire of the pilot instance mutex.
    Returns (hold, reason). hold is None if another owner exists or acquire failed.
    """
    name = mutex_name_for_data_root(data_root)
    handle = CreateMutexW(None, False, name)
    if not handle:
        return None, f"CreateMutex_failed:{ctypes.get_last_error()}"
    rc = WaitForSingleObject(handle, int(timeout_ms))
    if rc in (WAIT_OBJECT_0, WAIT_ABANDONED):
        return ExclusionHold(handle=int(handle), name=name), "acquired"
    # Still hold the handle open briefly to observe ALREADY_EXISTS semantics, then close
    CloseHandle(handle)
    if rc == WAIT_TIMEOUT:
        return None, "held_by_other"
    return None, f"WaitForSingleObject:{rc}"


def _norm(p: str) -> str:
    try:
        return str(Path(p).resolve()).lower()
    except OSError:
        return p.replace("/", "\\").lower()


def _cmdline_matches_pilot(cmdline: str, *, entry: Path, data_root: Path) -> bool:
    try:
        argv = parse_command_line(cmdline)
    except OSError:
        return False
    if len(argv) < 4:
        return False
    entry_n = _norm(str(entry))
    data_n = _norm(str(data_root))
    entry_ok = any(_norm(a) == entry_n for a in argv)
    if not entry_ok:
        return False
    for i, a in enumerate(argv):
        if a.lower() == "--disposable-root" and i + 1 < len(argv):
            return _norm(argv[i + 1]) == data_n
    return False


def find_conflicting_listener(
    *,
    entry: Path,
    data_root: Path,
    host: str = PREFERRED_UI_HOST,
) -> Optional[Dict[str, Any]]:
    """Return info if a loopback listener looks like this pilot's contained entry."""
    try:
        out = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"$conns = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | "
                f"Where-Object {{ $_.LocalAddress -in @('127.0.0.1','::1') -and "
                f"$_.LocalPort -ge {PREFERRED_UI_PORT} -and $_.LocalPort -le {PORT_SCAN_END} }}; "
                "foreach ($c in $conns) { "
                "$p = Get-CimInstance Win32_Process -Filter \"ProcessId=$($c.OwningProcess)\" "
                "-ErrorAction SilentlyContinue; "
                "if ($p) { [pscustomobject]@{Pid=$p.ProcessId;Port=$c.LocalPort;"
                "CommandLine=$p.CommandLine;Name=$p.Name} | ConvertTo-Json -Compress } }",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return {"uncertain": True, "reason": "listener_query_failed"}
    raw = (out.stdout or "").strip()
    if not raw:
        return None
    # May be multiple JSON objects newline-separated
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        cl = str(obj.get("CommandLine") or "")
        if _cmdline_matches_pilot(cl, entry=entry, data_root=data_root):
            return {
                "pid": int(obj["Pid"]),
                "port": int(obj["Port"]),
                "command_line": cl,
                "name": obj.get("Name"),
            }
    return None


def writer_exclusion_status(
    *,
    entry: Path,
    data_root: Path = PILOT_DATA_ROOT,
    pid_file: Optional[Path] = None,
    runtime_json: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Fail-closed status for whether it is safe to write the pilot memory store.

    safe_to_write=True only when exclusion mutex can be acquired AND no conflicting
    listener is found AND any pid/runtime record is either absent or clearly dead
    without uncertain ownership.
    """
    from pilot_identity import load_runtime_record, verify_live_ownership
    from pilot_paths import PID_FILE, RUNTIME_JSON
    from pilot_winprocess import BoundProcess

    pid_path = pid_file or PID_FILE
    rt_path = runtime_json or RUNTIME_JSON
    result: Dict[str, Any] = {
        "safe_to_write": False,
        "reason": "",
        "mutex": None,
        "listener": None,
    }

    hold, mutex_reason = try_acquire_exclusion(data_root=data_root, timeout_ms=0)
    result["mutex"] = mutex_reason
    if hold is None:
        result["reason"] = f"exclusion_mutex_unavailable:{mutex_reason}"
        return result

    # We hold the mutex for the check window; caller must release via returned hold
    result["hold"] = hold

    listener = find_conflicting_listener(entry=entry, data_root=data_root)
    result["listener"] = listener
    if listener and listener.get("uncertain"):
        hold.release()
        result.pop("hold", None)
        result["reason"] = "listener_query_uncertain"
        return result
    if listener:
        hold.release()
        result.pop("hold", None)
        result["reason"] = f"conflicting_listener_pid_{listener.get('pid')}"
        return result

    if pid_path.is_file():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except ValueError:
            hold.release()
            result.pop("hold", None)
            result["reason"] = "pid_file_malformed"
            return result
        bound, berr = BoundProcess.open(pid)
        if berr == "not_found" or (bound is not None and not bound.is_still_running()):
            if bound:
                bound.close()
            # stale pid file; safe if mutex held and no listener
        elif berr in ("access_denied",) or berr.startswith("open_failed"):
            hold.release()
            result.pop("hold", None)
            result["reason"] = f"pid_query_uncertain:{berr}"
            return result
        elif bound is not None:
            runtime, rerr = load_runtime_record(rt_path)
            if rerr or runtime is None:
                bound.close()
                hold.release()
                result.pop("hold", None)
                result["reason"] = f"live_pid_without_usable_runtime:{rerr or 'missing'}"
                return result
            verdict = verify_live_ownership(pid, runtime)
            bound.close()
            if verdict.owned:
                hold.release()
                result.pop("hold", None)
                result["reason"] = "verified_pilot_already_running"
                return result
            # Live process at PID but not owned — uncertain exclusion
            hold.release()
            result.pop("hold", None)
            result["reason"] = f"unrelated_or_unverifiable_live_pid:{verdict.reason}"
            return result

    result["safe_to_write"] = True
    result["reason"] = "exclusion_acquired"
    return result
