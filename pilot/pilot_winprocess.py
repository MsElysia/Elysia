#!/usr/bin/env python3
"""
Windows process handle binding for pilot ownership actions.

Numeric PID alone must never authorize termination. Callers open a process
handle first, verify identity through that handle, then signal/terminate via
the same handle so PID reuse cannot retarget the action.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from typing import Optional, Tuple  # noqa: used throughout

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
SYNCHRONIZE = 0x00100000

WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102

ERROR_INVALID_PARAMETER = 87
ERROR_ACCESS_DENIED = 5
STILL_ACTIVE = 259

OpenProcess = kernel32.OpenProcess
OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
OpenProcess.restype = wintypes.HANDLE

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

GetProcessId = kernel32.GetProcessId
GetProcessId.argtypes = [wintypes.HANDLE]
GetProcessId.restype = wintypes.DWORD

TerminateProcess = kernel32.TerminateProcess
TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
TerminateProcess.restype = wintypes.BOOL

WaitForSingleObject = kernel32.WaitForSingleObject
WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
WaitForSingleObject.restype = wintypes.DWORD

GetExitCodeProcess = kernel32.GetExitCodeProcess
GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
GetExitCodeProcess.restype = wintypes.BOOL


class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


GetProcessTimes = kernel32.GetProcessTimes
GetProcessTimes.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(FILETIME),
    ctypes.POINTER(FILETIME),
    ctypes.POINTER(FILETIME),
    ctypes.POINTER(FILETIME),
]
GetProcessTimes.restype = wintypes.BOOL

QueryFullProcessImageNameW = kernel32.QueryFullProcessImageNameW
QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
QueryFullProcessImageNameW.restype = wintypes.BOOL

CommandLineToArgvW = shell32.CommandLineToArgvW
CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)

LocalFree = kernel32.LocalFree
LocalFree.argtypes = [wintypes.HLOCAL]
LocalFree.restype = wintypes.HLOCAL


def _filetime_to_uint64(ft: FILETIME) -> int:
    return (int(ft.dwHighDateTime) << 32) | int(ft.dwLowDateTime)


def last_error() -> int:
    return ctypes.get_last_error()


def parse_command_line(cmdline: str) -> Tuple[str, ...]:
    """Parse a Windows command line into argv via CommandLineToArgvW."""
    if not cmdline:
        return tuple()
    argc = ctypes.c_int(0)
    argv_ptr = CommandLineToArgvW(cmdline, ctypes.byref(argc))
    if not argv_ptr:
        raise OSError(f"CommandLineToArgvW failed ({last_error()})")
    try:
        return tuple(argv_ptr[i] for i in range(argc.value))
    finally:
        LocalFree(argv_ptr)


@dataclass
class BoundProcess:
    """Process instance pinned by an open OS handle."""

    handle: int
    pid: int
    create_filetime: str
    image_path: str

    @classmethod
    def open(cls, pid: int) -> Tuple[Optional["BoundProcess"], str]:
        """Open a handle to pid. Returns (bound, error_code_string)."""
        if pid <= 0:
            return None, "invalid_pid"
        access = PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE | SYNCHRONIZE
        handle = OpenProcess(access, False, int(pid))
        if not handle:
            err = last_error()
            if err in (ERROR_INVALID_PARAMETER,):
                return None, "not_found"
            if err == ERROR_ACCESS_DENIED:
                return None, "access_denied"
            return None, f"open_failed:{err}"

        bound, verr = cls._from_handle(int(handle), expected_pid=int(pid))
        if bound is None:
            CloseHandle(handle)
            return None, verr
        return bound, ""

    @classmethod
    def _from_handle(
        cls, handle: int, *, expected_pid: int
    ) -> Tuple[Optional["BoundProcess"], str]:
        live_pid = int(GetProcessId(handle) or 0)
        if live_pid != expected_pid:
            return None, f"handle_pid_mismatch:{live_pid}!={expected_pid}"

        creation = FILETIME()
        exit_t = FILETIME()
        kernel_t = FILETIME()
        user_t = FILETIME()
        if not GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_t),
            ctypes.byref(kernel_t),
            ctypes.byref(user_t),
        ):
            return None, f"GetProcessTimes_failed:{last_error()}"

        buf = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buf))
        if not QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return None, f"QueryFullProcessImageName_failed:{last_error()}"

        return (
            cls(
                handle=handle,
                pid=live_pid,
                create_filetime=str(_filetime_to_uint64(creation)),
                image_path=buf.value,
            ),
            "",
        )

    def refresh_times_match(self, expected_filetime: str) -> bool:
        creation = FILETIME()
        exit_t = FILETIME()
        kernel_t = FILETIME()
        user_t = FILETIME()
        if not GetProcessTimes(
            self.handle,
            ctypes.byref(creation),
            ctypes.byref(exit_t),
            ctypes.byref(kernel_t),
            ctypes.byref(user_t),
        ):
            return False
        return str(_filetime_to_uint64(creation)) == str(expected_filetime)

    def exit_state(self) -> Tuple[str, Optional[int]]:
        """
        Return (state, exit_code_or_None).

        state is one of: 'running', 'exited', 'query_failed'.
        GetExitCodeProcess failure must NOT be treated as exited.
        """
        code = wintypes.DWORD()
        if not GetExitCodeProcess(self.handle, ctypes.byref(code)):
            return "query_failed", None
        value = int(code.value)
        if value == STILL_ACTIVE:
            return "running", None
        return "exited", value

    def is_still_running(self) -> bool:
        state, _ = self.exit_state()
        return state == "running"

    def wait(self, timeout_ms: int) -> str:
        """
        Wait for handle signal. Returns 'exited', 'timeout', or 'wait_failed'.
        """
        rc = WaitForSingleObject(self.handle, int(timeout_ms))
        if rc == WAIT_OBJECT_0:
            state, _ = self.exit_state()
            if state == "exited":
                return "exited"
            if state == "query_failed":
                return "wait_failed"
            # Signaled but still reports running — treat as uncertain
            return "wait_failed"
        if rc == WAIT_TIMEOUT:
            return "timeout"
        return "wait_failed"

    def terminate(self) -> Tuple[bool, str]:
        """Terminate via this handle only (never a fresh PID lookup)."""
        if not self.refresh_times_match(self.create_filetime):
            return False, "creation_time_changed_on_handle"
        if not self.is_still_running():
            return True, "already_exited"
        if not TerminateProcess(self.handle, 1):
            return False, f"TerminateProcess_failed:{last_error()}"
        return True, "terminated_via_handle"

    def close(self) -> None:
        if self.handle:
            CloseHandle(self.handle)
            self.handle = 0
