#!/usr/bin/env python3
"""Filesystem containment and cross-process locks for pilot inbox."""
from __future__ import annotations

import ctypes
import msvcrt
import os
from ctypes import wintypes
from pathlib import Path
from typing import Optional, Tuple

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
GENERIC_READ = 0x80000000

GetFileAttributesW = kernel32.GetFileAttributesW
GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
GetFileAttributesW.restype = wintypes.DWORD

CreateFileW = kernel32.CreateFileW
CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
CreateFileW.restype = wintypes.HANDLE

CloseHandle = kernel32.CloseHandle
GetFinalPathNameByHandleW = kernel32.GetFinalPathNameByHandleW
GetFinalPathNameByHandleW.argtypes = [
    wintypes.HANDLE,
    wintypes.LPWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
]
GetFinalPathNameByHandleW.restype = wintypes.DWORD

INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF


def is_reparse_point(path: Path) -> bool:
    attrs = GetFileAttributesW(str(path))
    if attrs == INVALID_FILE_ATTRIBUTES:
        return False
    return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)


def final_path(path: Path) -> Tuple[Optional[str], str]:
    """Return (normalized final path, error). Opens the path to resolve reparse targets."""
    handle = CreateFileW(
        str(path),
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    if handle == INVALID_HANDLE_VALUE or handle is None:
        return None, f"CreateFile_failed:{ctypes.get_last_error()}"
    try:
        buf = ctypes.create_unicode_buffer(32768)
        n = GetFinalPathNameByHandleW(handle, buf, len(buf), 0)
        if n == 0:
            return None, f"GetFinalPathNameByHandle_failed:{ctypes.get_last_error()}"
        raw = buf.value
        # Strip \\?\ or \\?\UNC\ prefixes
        if raw.startswith("\\\\?\\UNC\\"):
            raw = "\\\\" + raw[8:]
        elif raw.startswith("\\\\?\\"):
            raw = raw[4:]
        return str(Path(raw)), ""
    finally:
        CloseHandle(handle)


def assert_physical_inbox_root(inbox_dir: Path) -> Tuple[bool, str]:
    if not inbox_dir.exists():
        return False, "inbox_missing"
    if is_reparse_point(inbox_dir):
        return False, "inbox_root_is_reparse_point"
    final, err = final_path(inbox_dir)
    if err or not final:
        return False, f"inbox_final_path_failed:{err}"
    try:
        configured = str(inbox_dir.resolve())
    except OSError as exc:
        return False, f"inbox_resolve_failed:{exc}"
    # resolve() may follow junctions; if root is not a reparse point, final should match
    if Path(final).resolve() != Path(configured).resolve() and is_reparse_point(inbox_dir):
        return False, "inbox_final_path_escaped"
    return True, final


def assert_file_inside_inbox(file_path: Path, inbox_final: str) -> Tuple[bool, str]:
    if is_reparse_point(file_path):
        return False, "source_is_reparse_point"
    final, err = final_path(file_path)
    if err or not final:
        return False, f"source_final_path_failed:{err}"
    inbox_n = str(Path(inbox_final).resolve()).lower().rstrip("\\/")
    final_n = str(Path(final).resolve()).lower()
    if final_n != inbox_n and not final_n.startswith(inbox_n + os.sep) and not final_n.startswith(inbox_n + "\\"):
        return False, f"source_outside_inbox:{final}"
    return True, final


class ImportFileLock:
    """Exclusive cross-process lock for the full inbox dedupe/RMW critical section."""

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self._fh = None

    def acquire(self, *, blocking: bool = True) -> Tuple[bool, str]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.lock_path, "a+b")
        try:
            # Lock one byte at start of file
            self._fh.seek(0)
            if self._fh.tell() == 0 and self._fh.read(1) == b"":
                self._fh.write(b"0")
                self._fh.flush()
            self._fh.seek(0)
            flags = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
            msvcrt.locking(self._fh.fileno(), flags, 1)
            return True, "acquired"
        except OSError as exc:
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None
            return False, f"lock_failed:{exc}"

    def release(self) -> None:
        if self._fh is not None:
            try:
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None
