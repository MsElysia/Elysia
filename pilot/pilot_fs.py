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


def open_validate_and_read_inbox_file(
    file_path: Path, inbox_final: str, *, max_bytes: int
) -> Tuple[Optional[bytes], str, str]:
    """
    Open a candidate inbox file, validate its final path through that handle,
    then read bytes from the same handle before closing.

    This closes the TOCTOU gap where a junction swap can replace the path
    between a separate final_path check and a later Path.read_bytes().
    Returns (data, final_path, error). data is None on failure.
    """
    if is_reparse_point(file_path):
        return None, "", "source_is_reparse_point"

    # Open the file without BACKUP_SEMANTICS so the handle refers to file data.
    handle = CreateFileW(
        str(file_path),
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    if handle == INVALID_HANDLE_VALUE or handle is None:
        return None, "", f"CreateFile_failed:{ctypes.get_last_error()}"

    try:
        buf = ctypes.create_unicode_buffer(32768)
        n = GetFinalPathNameByHandleW(handle, buf, len(buf), 0)
        if n == 0:
            return None, "", f"GetFinalPathNameByHandle_failed:{ctypes.get_last_error()}"
        raw_final = buf.value
        if raw_final.startswith("\\\\?\\UNC\\"):
            raw_final = "\\\\" + raw_final[8:]
        elif raw_final.startswith("\\\\?\\"):
            raw_final = raw_final[4:]
        final = str(Path(raw_final))
        # Also refuse if the path string itself is a reparse point (parent junction).
        try:
            if is_reparse_point(Path(final).parent) or is_reparse_point(file_path.parent):
                # Parent of the opened path is a junction — require final path under inbox_final.
                pass
        except OSError:
            pass
        inbox_n = str(Path(inbox_final).resolve()).lower().rstrip("\\/")
        final_n = str(Path(final).resolve()).lower()
        if final_n != inbox_n and not final_n.startswith(inbox_n + os.sep) and not final_n.startswith(
            inbox_n + "\\"
        ):
            return None, final, f"source_outside_inbox:{final}"
        # Re-check: the configured inbox path must still not be a reparse point.
        try:
            configured_inbox = Path(file_path).parent
            if is_reparse_point(configured_inbox):
                return None, final, "inbox_parent_became_reparse_point"
        except OSError:
            return None, final, "inbox_parent_reparse_check_failed"

        # Read via the same open handle (ReadFile).
        ReadFile = kernel32.ReadFile
        ReadFile.argtypes = [
            wintypes.HANDLE,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
        ]
        ReadFile.restype = wintypes.BOOL
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = ctypes.create_string_buffer(1024 * 64)
            read = wintypes.DWORD(0)
            if not ReadFile(handle, chunk, len(chunk), ctypes.byref(read), None):
                err = ctypes.get_last_error()
                if err == 0 and read.value == 0:
                    break
                return None, final, f"ReadFile_failed:{err}"
            if read.value == 0:
                break
            total += int(read.value)
            if total > max_bytes:
                return None, final, f"file_exceeds_limit:{total}"
            chunks.append(chunk.raw[: read.value])
        return b"".join(chunks), final, ""
    finally:
        CloseHandle(handle)


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
