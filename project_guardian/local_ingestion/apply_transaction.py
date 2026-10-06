"""Recoverable destination-scoped publication for local ChatGPT apply only.

POSIX advisory locking; readers must participate. No runtime or memory approval.
An unfinished publication is rolled back before cooperating readers/writers run.
"""
from contextlib import contextmanager
from functools import wraps
import json
import os
from pathlib import Path
import shutil
import threading


TRANSACTION_DIR = ".chatgpt_apply_transaction"
_held = threading.local()


class ApplyTransactionError(ValueError):
    pass


def _sync_directory(path):
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


@contextmanager
def destination_lock(dest, *, write=False):
    dest = Path(dest).resolve()
    if getattr(_held, "pid", None) != os.getpid():
        _held.pid = os.getpid()
        _held.destinations = set()
    held = getattr(_held, "destinations", set())
    if dest in held:
        if write:
            raise ApplyTransactionError("Destination apply lock refused: nested apply is not allowed.")
        yield
        return
    if not dest.exists() and not write:
        yield
        return
    try:
        import fcntl
    except ImportError as exc:
        if not write and not (dest / TRANSACTION_DIR).exists():
            yield
            return
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
    _held.destinations = held | {dest}
    try:
        recover(dest)
        yield
    finally:
        _held.destinations = held
        os.close(descriptor)


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
