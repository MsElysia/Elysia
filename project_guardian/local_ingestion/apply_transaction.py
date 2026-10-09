"""Recoverable destination-scoped publication for local ChatGPT apply only.

OS locking; readers must participate. No runtime or memory approval.
An unfinished publication is rolled back before cooperating readers/writers run.
Windows uses a global named mutex; directory fsync is POSIX-only. Neither
platform is certified for physical power-loss or noncooperating writers.
"""
from contextlib import contextmanager
from functools import wraps
import json
import hashlib
import os
from pathlib import Path
import shutil
import threading


TRANSACTION_DIR = ".chatgpt_apply_transaction"
_PLATFORM = os.name
_held = threading.local()


class ApplyTransactionError(ValueError):
    pass


def _sync_directory(path):
    if _PLATFORM == "nt":
        # Windows has no os.open/fsync directory equivalent. File bytes are
        # still flushed before publication; process-death recovery is the
        # contract, not persisted directory entries after physical power loss.
        return
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _durable_write(path, data):
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _replace_bytes(path, data):
    """Never truncate the visible file, including during recovery."""
    temp = path.with_name(path.name + ".chatgpt-recovery")
    if temp.is_symlink():
        raise ApplyTransactionError("symlink recovery temporary file")
    _durable_write(temp, data)
    os.replace(temp, path)
    _sync_directory(path.parent)


def _target(dest, relative):
    if type(relative) is not str or not relative:
        raise ApplyTransactionError("invalid transaction target")
    raw = Path(relative)
    if _PLATFORM == "nt":
        from pathlib import PureWindowsPath
        windows = PureWindowsPath(relative)
        if (not windows.parts or windows.drive or windows.root or ".." in windows.parts
                or windows.parts[0].casefold() in (TRANSACTION_DIR, TRANSACTION_DIR + "_cleanup")
                or any(PureWindowsPath(p).is_reserved() or p.endswith((".", " "))
                       or any(c in p for c in '<>:"|?*')
                       or any(ord(c) < 32 for c in p) for p in windows.parts)):
            raise ApplyTransactionError("invalid Windows transaction target")
    if (not raw.parts or raw.is_absolute() or ".." in raw.parts
            or raw.parts[0] in (TRANSACTION_DIR, TRANSACTION_DIR + "_cleanup")):
        raise ApplyTransactionError("transaction target escaped destination")
    path = dest / raw
    if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != dest.parent):
        raise ApplyTransactionError("symlink transaction target")
    if path.resolve() != path:
        raise ApplyTransactionError("noncanonical transaction target")
    return path


def recover(dest):
    """Called only with the destination lock held; repeatable after interruption."""
    root = dest / TRANSACTION_DIR
    garbage = dest / (TRANSACTION_DIR + "_cleanup")
    if garbage.exists():
        if garbage.is_symlink() or not garbage.is_dir():
            raise ApplyTransactionError("invalid transaction cleanup directory")
        shutil.rmtree(garbage)
    if not root.exists():
        return
    if root.is_symlink() or not root.is_dir():
        raise ApplyTransactionError("invalid transaction directory")
    manifest = root / "manifest.json"
    if not manifest.exists():
        # Staging cannot touch published targets before the durable manifest.
        os.replace(root, garbage)
        _sync_directory(dest)
        shutil.rmtree(garbage)
        return
    try:
        if manifest.is_symlink():
            raise ValueError("symlink manifest")
        state = json.loads(manifest.read_text(encoding="utf-8"))
        if (type(state) is not dict or set(state) != {"version", "entries"}
                or type(state["version"]) is not int or state["version"] != 1
                or type(state["entries"]) is not list):
            raise ValueError("invalid manifest")
        targets = set()
        validated = []
        for i, entry in enumerate(state["entries"]):
            if (type(entry) is not dict or set(entry) != {"target", "existed"}
                    or type(entry["existed"]) is not bool):
                raise ValueError("invalid entry")
            path = _target(dest, entry["target"])
            if path in targets:
                raise ValueError("duplicate target")
            targets.add(path)
            backup = root / f"backup-{i}"
            if entry["existed"] and (backup.is_symlink() or not backup.is_file()):
                raise ValueError("missing backup")
            validated.append((path, entry["existed"], backup))
        committed = root / "committed"
        if committed.exists():
            if committed.is_symlink() or committed.read_bytes() != b"committed\n":
                raise ValueError("invalid commit marker")
        else:
            for path, existed, backup in reversed(validated):
                if existed:
                    _replace_bytes(path, backup.read_bytes())
                elif path.exists():
                    path.unlink()
                    _sync_directory(path.parent)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ApplyTransactionError("transaction recovery failed; destination remains blocked") from exc
    # Move the complete journal out of the recovery namespace before deleting
    # backups. Death during cleanup must never look like an incomplete journal.
    os.replace(root, garbage)
    _sync_directory(dest)
    shutil.rmtree(garbage)


def _windows_mutex_name(dest):
    # File identity also unifies case, junction, short-name and drive aliases.
    # Do not key by user/session: all cooperating workers must share one lock.
    try:
        stat = dest.stat()
        if not dest.is_dir() or not stat.st_ino:
            raise OSError("destination directory identity unavailable")
    except OSError as exc:
        raise ApplyTransactionError("Destination apply lock identity unavailable.") from exc
    identity = f"{stat.st_dev}:{stat.st_ino}".encode("ascii")
    return "Global\\Elysia.ChatGPTApply.v1." + hashlib.sha256(identity).hexdigest()


def _windows_api():
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    api.CreateMutexW.restype = wintypes.HANDLE
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.ReleaseMutex.argtypes = [wintypes.HANDLE]
    api.ReleaseMutex.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api


@contextmanager
def _windows_mutex(name):
    try:
        api = _windows_api()
    except (ImportError, AttributeError, OSError) as exc:
        raise ApplyTransactionError("Destination apply locking is unavailable on Windows.") from exc
    # Default ACL, no inheritable handle, no privilege/permission changes.
    handle = api.CreateMutexW(None, False, name)
    if not handle:
        raise ApplyTransactionError("Destination apply lock refused or unavailable on Windows.")
    acquired = False
    try:
        status = api.WaitForSingleObject(handle, 0)
        if status not in (0, 0x80):  # WAIT_OBJECT_0 / WAIT_ABANDONED
            raise ApplyTransactionError("Destination apply lock refused or unavailable; retry after the other import finishes.")
        # Abandonment grants ownership; always recover before serving bytes.
        acquired = True
        yield
    finally:
        try:
            if acquired and not api.ReleaseMutex(handle):
                raise ApplyTransactionError("Destination apply lock release failed on Windows.")
        finally:
            if not api.CloseHandle(handle):
                raise ApplyTransactionError("Destination apply lock handle close failed on Windows.")


@contextmanager
def _posix_lock(dest):
    try:
        import fcntl
    except ImportError as exc:
        raise ApplyTransactionError("Destination apply locking is unavailable on this platform.") from exc
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise ApplyTransactionError("Safe destination directory locking is unavailable.")
    descriptor = None
    try:
        descriptor = os.open(dest, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise ApplyTransactionError("Destination apply lock refused or unavailable; retry after the other import finishes.") from exc
    try:
        yield
    finally:
        os.close(descriptor)


@contextmanager
def destination_lock(dest, *, write=False):
    dest = Path(dest).resolve()
    if not dest.exists() and not write:
        yield
        return
    if getattr(_held, "pid", None) != os.getpid():
        _held.pid = os.getpid()
        _held.destinations = set()
    held = getattr(_held, "destinations", set())
    key = _windows_mutex_name(dest) if _PLATFORM == "nt" else dest
    if key in held:
        if write:
            raise ApplyTransactionError("Destination apply lock refused: nested apply is not allowed.")
        yield
        return
    if _PLATFORM == "nt":
        lock = _windows_mutex(key)
    elif _PLATFORM == "posix":
        lock = _posix_lock(dest)
    else:
        raise ApplyTransactionError("Destination apply locking is unavailable on this platform.")
    with lock:
        _held.destinations = held | {key}
        try:
            recover(dest)
            yield
        finally:
            _held.destinations = held


def consistent_reader(function):
    @wraps(function)
    def guarded(dest_dir, *args, **kwargs):
        with destination_lock(dest_dir):
            return function(dest_dir, *args, **kwargs)
    return guarded


class ApplyTransaction:
    """Stage all bytes, then journal original bytes before replacing any target."""
    def __init__(self, dest):
        self.dest = Path(dest).resolve()
        self.root = self.dest / TRANSACTION_DIR
        self.root.mkdir()
        _sync_directory(self.dest)
        self.entries = {}

    def read(self, path):
        relative = Path(path).relative_to(self.dest).as_posix()
        _target(self.dest, relative)
        if relative in self.entries:
            return (self.root / f"stage-{self.entries[relative]}").read_bytes()
        return Path(path).read_bytes() if Path(path).exists() else b""

    def write(self, path, data):
        try:
            relative = Path(path).relative_to(self.dest).as_posix()
        except ValueError as exc:
            raise ApplyTransactionError("apply output must be inside destination") from exc
        _target(self.dest, relative)
        i = self.entries.setdefault(relative, len(self.entries))
        _durable_write(self.root / f"stage-{i}", data)

    def append(self, path, data):
        self.write(path, self.read(path) + data)

    def commit(self):
        entries = []
        for relative, i in self.entries.items():
            path = _target(self.dest, relative)
            existed = path.exists()
            if existed:
                _durable_write(self.root / f"backup-{i}", path.read_bytes())
            entries.append({"target": relative, "existed": existed})
        _durable_write(self.root / "manifest.tmp", json.dumps({"version": 1, "entries": entries}).encode())
        os.replace(self.root / "manifest.tmp", self.root / "manifest.json")
        _sync_directory(self.root)
        try:
            for relative, i in self.entries.items():
                path = _target(self.dest, relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                # Directory entry durability is required for newly created parents.
                for parent in path.parents:
                    _sync_directory(parent)
                    if parent == self.dest:
                        break
                os.replace(self.root / f"stage-{i}", path)
                _sync_directory(path.parent)
            _durable_write(self.root / "committed.tmp", b"committed\n")
            os.replace(self.root / "committed.tmp", self.root / "committed")
            _sync_directory(self.root)
        except BaseException:
            recover(self.dest)
            raise
        # A committed journal is recoverable even if cleanup is interrupted.
        recover(self.dest)

    def abort(self):
        recover(self.dest)
