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


def lifetime_ready_path(data_root: Path = PILOT_DATA_ROOT) -> Path:
    return Path(data_root) / "runtime" / "lifetime.ready"


def launch_claim_path(data_root: Path = PILOT_DATA_ROOT) -> Path:
    return Path(data_root) / "runtime" / "launch.claim"


@dataclass
class LaunchClaim:
    """Exclusive launch reservation spanning spawn until child lifetime mutex is ready."""

    path: Path
    _fh: Any = None

    def release(self) -> None:
        if self._fh is not None:
            try:
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


def launch_claim_is_held(data_root: Path = PILOT_DATA_ROOT) -> bool:
    """True if another process currently holds the launch claim lock."""
    import msvcrt

    path = launch_claim_path(data_root)
    if not path.is_file():
        return False
    try:
        with open(path, "a+b") as fh:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        return False
    except OSError:
        return True


def try_acquire_launch_claim(
    *,
    data_root: Path = PILOT_DATA_ROOT,
    blocking: bool = False,
) -> Tuple[Optional[LaunchClaim], str]:
    """
    Cross-process launch reservation. Held by the launcher from pre-spawn through
    child lifetime.ready — closes the mutex release-before-spawn gap.
    """
    import msvcrt

    path = launch_claim_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    claim = LaunchClaim(path=path)
    try:
        claim._fh = open(path, "a+b")
        claim._fh.seek(0)
        if claim._fh.tell() == 0 and claim._fh.read(1) == b"":
            claim._fh.write(b"claim")
            claim._fh.flush()
        claim._fh.seek(0)
        flags = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
        msvcrt.locking(claim._fh.fileno(), flags, 1)
        # Clear stale ready marker from a previous instance
        lifetime_ready_path(data_root).unlink(missing_ok=True)
        return claim, "acquired"
    except OSError as exc:
        if claim._fh is not None:
            try:
                claim._fh.close()
            except Exception:
                pass
            claim._fh = None
        return None, f"launch_claim_held_or_failed:{exc}"


def wait_for_lifetime_ready(
    *,
    data_root: Path = PILOT_DATA_ROOT,
    timeout_sec: float = 90.0,
) -> bool:
    import time

    ready = lifetime_ready_path(data_root)
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if ready.is_file():
            try:
                raw = ready.read_text(encoding="utf-8").strip()
            except OSError:
                raw = ""
            if raw.startswith("ready:"):
                return True
        time.sleep(0.1)
    return False


def write_lifetime_ready(*, data_root: Path = PILOT_DATA_ROOT) -> Path:
    path = lifetime_ready_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"ready:{os_getpid()}", encoding="utf-8")
    return path


def os_getpid() -> int:
    import os

    return os.getpid()


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
    own_launch_claim: Optional[LaunchClaim] = None,
) -> Dict[str, Any]:
    """
    Fail-closed status for whether it is safe to write the pilot memory store.

    safe_to_write=True only when exclusion mutex can be acquired AND no conflicting
    listener is found AND any pid/runtime record is either absent or clearly dead
    without uncertain ownership.

    Pass own_launch_claim when the caller already holds the launch claim (launcher
    path). A second open/lock of the same claim file always fails under msvcrt, so
    launch_claim_is_held cannot distinguish self vs other for the holder.
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

    if own_launch_claim is None and launch_claim_is_held(data_root):
        result["reason"] = "launch_claim_held_by_other"
        return result

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
