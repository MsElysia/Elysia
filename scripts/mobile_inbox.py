"""Manual, archive-only intake of untrusted local files. No Elysia imports."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
import unicodedata
import uuid

EXTENSIONS = frozenset({".txt", ".md", ".vtt", ".srt", ".json", ".pdf", ".jpg", ".jpeg", ".png"})
MARKER = b"elysia-mobile-inbox-archive-v1\n"
REPOSITORY = Path(__file__).resolve().parents[1]
CHUNK = 1024 * 1024


class InboxError(ValueError):
    pass


class Deferred(InboxError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def safe_name(name):
    """Conservative Windows names, also enforced when testing on POSIX."""
    if (not name or name in {".", ".."} or name.startswith((".", "~syncthing~"))
            or name.endswith((".", " ")) or len(name) > 200
            or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} or c in '<>:"/\\|?*' for c in name)
            or re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³]",
                            name.split(".", 1)[0].rstrip(" "), re.I)):
        raise InboxError("unsafe filename")


def transport_entry(path):
    name = path.name
    if (name in {".stfolder", ".stignore", ".stversions"}
            or (name.startswith((".syncthing.", "~syncthing~")) and name.endswith(".tmp"))):
        info = path.lstat()
        # Ignore only genuine transport entries, never links or special files.
        checked(path, directory=stat.S_ISDIR(info.st_mode))
        return True
    return False


def checked(path, *, directory=False):
    """Reject links/reparse points at every component before any resolution."""
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise InboxError("absolute path without traversal required")
    if os.name == "nt":
        if str(path).startswith("\\\\") or any(":" in p for p in path.parts[1:]):
            raise InboxError("UNC, device paths and alternate streams refused")
        import ctypes
        if ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor)) != 3:
            raise InboxError("local fixed disk required")
    for part in reversed((path, *path.parents)):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise InboxError("symlink or reparse point refused")
        if part != path and not stat.S_ISDIR(info.st_mode):
            raise InboxError("non-directory path component")
    info = path.lstat()
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise InboxError("regular file required" if not directory else "directory required")
    if not directory and info.st_nlink != 1:
        raise InboxError("hard-linked file refused")
    return info


def signature(info):
    # CPython Windows lstat/fstat can report different ctime semantics
    # (creation vs change time). Identity, size and mtime remain comparable.
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns if os.name != "nt" else 0)


def overlap(a, b):
    return a == b or a in b.parents or b in a.parents


def repository_roots():
    roots = [REPOSITORY]
    # A worktree must also exclude the original checkout, not just this branch.
    gitfile = REPOSITORY / ".git"
    if gitfile.is_file():
        line = gitfile.read_text(encoding="utf-8").strip()
        if line.startswith("gitdir: "):
            gitdir = (REPOSITORY / line[8:]).resolve()
            common = gitdir / "commondir"
            if common.is_file():
                roots.append((gitdir / common.read_text().strip()).resolve().parent)
    return roots


@contextmanager
def read_only(path):
    """Windows denies concurrent writers/deletion while the source is held."""
    before = checked(path)
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        import msvcrt
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                           wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        close = kernel.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        close.restype = wintypes.BOOL
        handle = create(str(path), 0x80000000, 1, None, 3, 0x00200000, None)
        if handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            close(handle)
            raise
    else:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or signature(opened) != signature(before)
                or signature(checked(path)) != signature(before)):
            raise Deferred("file identity changed while opening")
        yield stream, before


@contextmanager
def archive_lock(archive):
    path = archive / "intake.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        try:
            os.write(fd, b"0")
            os.fsync(fd)
        finally:
            os.close(fd)
    except FileExistsError:
        checked(path)
    checked(path)
    with path.open("r+b") as handle:
        if signature(os.fstat(handle.fileno())) != signature(checked(path)):
            raise InboxError("lock identity changed")
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise InboxError("archive busy or locking unavailable; retry later") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def sync_directory(path):
    # Windows provides no portable directory fsync. No power-loss claim.
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def new_temp(archive):
    checked(archive / "temporary", directory=True)
    path = archive / "temporary" / (uuid.uuid4().hex + ".part")
    return path, path.open("xb")


def publish(temp, target):
    """Same-volume rename under the OS lock; never replace an existing artifact."""
    checked(temp)
    checked(target.parent, directory=True)
    if os.path.lexists(target):
        raise InboxError("publication target already exists")
    os.rename(temp, target)
    sync_directory(target.parent)


def save_receipt(archive, target, record):
    temp, handle = new_temp(archive)
    try:
        with handle:
            handle.write((json.dumps(record, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode())
            handle.flush()
            os.fsync(handle.fileno())
        publish(temp, target)
    finally:
        if temp.exists():
            checked(temp)
            temp.unlink()


def hash_stream(stream, *, limit):
    digest = hashlib.sha256()
    size = 0
    while block := stream.read(CHUNK):
        size += len(block)
        if size > limit:
            raise InboxError("size limit exceeded while reading")
        digest.update(block)
    return digest.hexdigest(), size


def verify_blob(path, digest, size):
    with read_only(path) as (stream, info):
        if (info.st_size != size or hash_stream(stream, limit=size) != (digest, size)
                or signature(os.fstat(stream.fileno())) != signature(info)
                or signature(checked(path)) != signature(info)):
            raise InboxError("archived bytes failed integrity verification; preserve and investigate")


def receipt_fields(pairs):
    record = {}
    for key, value in pairs:
        if key in record:
            raise InboxError("duplicate receipt field")
        record[key] = value
    return record


def validate_receipt(prior, identity, path, info):
    expected = {**identity, "schema": 1, "source_name": path.name,
                "source_ctime_ns": info.st_ctime_ns,
                "object_path": "objects/" + identity["sha256"],
                "trust": "untrusted-data", "live_memory_written": False}
    if (type(prior) is not dict or set(prior) != set(expected) | {"archived_at"}
            or any(type(prior[k]) is not type(v) or prior[k] != v
                   for k, v in expected.items())):
        raise InboxError("receipt integrity/schema mismatch; preserve and investigate")
    # This is a local clock assertion, not authenticated historical metadata.
    value = prior["archived_at"]
    if (type(value) is not str or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{6})?\+00:00", value) is None):
        raise InboxError("invalid receipt archived_at")
    try:
        archived_at = datetime.fromisoformat(value)
    except ValueError as exc:
        raise InboxError("invalid receipt archived_at") from exc
    # Integer arithmetic avoids rounding nanosecond source timestamps.
    delta = archived_at - datetime(1970, 1, 1, tzinfo=timezone.utc)
    archived_ns = ((delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds) * 1000
    if archived_ns < info.st_mtime_ns or archived_ns > time.time_ns():
        raise InboxError("receipt archived_at inconsistent with source/time")


def intake_file(path, archive, initial, max_bytes):
    if signature(checked(path)) != signature(initial):
        raise Deferred("source changed during stability interval")
    temp, handle = new_temp(archive)
    try:
        with handle, read_only(path) as (source, info):
            if signature(info) != signature(initial):
                raise Deferred("source changed before copy")
            digest = hashlib.sha256()
            size = 0
            while block := source.read(CHUNK):
                size += len(block)
                if size > max_bytes:
                    raise InboxError("size limit exceeded during copy")
                handle.write(block)
                digest.update(block)
            handle.flush()
            os.fsync(handle.fileno())
            source.seek(0)
            sha = digest.hexdigest()
            if (size != info.st_size or signature(os.fstat(source.fileno())) != signature(info)
                    or hash_stream(source, limit=max_bytes) != (sha, size)
                    or signature(checked(path)) != signature(info)):
                raise Deferred("source changed during copy/verification")
        # Read back staging bytes before any public receipt or blob is created.
        verify_blob(temp, sha, size)
        checked(archive / "objects", directory=True)
        blob = archive / "objects" / sha
        duplicate = os.path.lexists(blob)
        if duplicate:
            verify_blob(blob, sha, size)
        identity = {"source_path": str(path), "sha256": sha, "size_bytes": size,
                    "source_mtime_ns": info.st_mtime_ns}
        receipt_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        receipt = archive / "receipts" / (receipt_id + ".json")
        if os.path.lexists(receipt):
            with read_only(receipt) as (stream, receipt_info):
                if receipt_info.st_size > 65536:
                    raise InboxError("oversized receipt")
                try:
                    prior = json.load(stream, object_pairs_hook=receipt_fields)
                except (ValueError, UnicodeError) as exc:
                    raise InboxError("invalid receipt JSON; preserve and investigate") from exc
            validate_receipt(prior, identity, path, info)
            if not duplicate:
                raise InboxError("receipt object missing; preserve and investigate")
            status = "already_recorded"
        else:
            if not duplicate:
                publish(temp, blob)
            save_receipt(archive, receipt, {
                **identity, "schema": 1, "source_name": path.name,
                "source_ctime_ns": info.st_ctime_ns, "archived_at": utc_now(),
                "object_path": "objects/" + sha, "trust": "untrusted-data",
                "live_memory_written": False,
            })
            status = "duplicate" if duplicate else "archived"
        return {"source_path": str(path), "status": status, "sha256": sha,
                "size_bytes": size, "receipt_path": str(receipt), "object_path": str(blob)}
    finally:
        if temp.exists():
            checked(temp)
            temp.unlink()


def prepare_archive(archive):
    marker = archive / "archive.kind"
    if not os.path.lexists(marker):
        if any(archive.iterdir()):
            raise InboxError("archive must be empty or an existing mobile inbox archive")
        with marker.open("xb") as handle:
            handle.write(MARKER)
            handle.flush()
            os.fsync(handle.fileno())
    with read_only(marker) as (stream, _):
        if stream.read(len(MARKER) + 1) != MARKER:
            raise InboxError("wrong archive marker")
    allowed = {"archive.kind", "intake.lock", "objects", "receipts", "temporary", "runs"}
    if any(p.name not in allowed for p in archive.iterdir()):
        raise InboxError("unexpected archive entries; refusing unrelated storage")


def run_once(*, inbox, archive, memory_roots, stable_seconds=10.0,
             max_bytes=25 * 1024 * 1024, extensions=EXTENSIONS):
    if (type(max_bytes) is not int or max_bytes <= 0
            or type(stable_seconds) not in {int, float} or not math.isfinite(stable_seconds)
            or not 0 < stable_seconds <= 60 or not memory_roots
            or not extensions or not set(extensions) <= EXTENSIONS):
        raise InboxError("invalid limits, extensions or missing protected memory roots")
    inbox, archive = Path(inbox), Path(archive)
    checked(inbox, directory=True)
    checked(archive, directory=True)
    protected = repository_roots()
    for root in memory_roots:
        root = Path(root)
        checked(root, directory=True)
        protected.append(root)
    inbox, archive = inbox.resolve(), archive.resolve()
    if overlap(inbox, archive) or any(overlap(p, root.resolve()) for p in (inbox, archive) for root in protected):
        raise InboxError("inbox/archive overlap each other, repository or protected memory root")
    prepare_archive(archive)
    report = {"started_at": utc_now(), "inbox": str(inbox), "archive": str(archive),
              "live_memory_written": False, "results": []}
    with archive_lock(archive):
        for name in ("objects", "receipts", "temporary", "runs"):
            (archive / name).mkdir(exist_ok=True)
            checked(archive / name, directory=True)
        snapshots = []
        for path in sorted(inbox.iterdir()):
            try:
                if transport_entry(path):
                    report["results"].append({"source_path": str(path), "status": "ignored_transport"})
                    continue
                safe_name(path.name)
                info = checked(path)
                if path.suffix.lower() not in extensions:
                    raise InboxError("unsupported extension")
                if info.st_size > max_bytes:
                    raise InboxError("size limit exceeded")
                if time.time_ns() - info.st_mtime_ns < stable_seconds * 1e9:
                    raise Deferred("source too recent; wait and rerun")
                snapshots.append((path, info))
            except (InboxError, OSError) as exc:
                report["results"].append(error_result(path, exc))
        if snapshots:
            time.sleep(stable_seconds)
        checked(inbox, directory=True)
        checked(archive, directory=True)
        for path, info in snapshots:
            try:
                report["results"].append(intake_file(path, archive, info, max_bytes))
            except (InboxError, OSError, ValueError) as exc:
                report["results"].append(error_result(path, exc))
        report["finished_at"] = utc_now()
        report["counts"] = {status: sum(r["status"] == status for r in report["results"])
                            for status in ("archived", "duplicate", "already_recorded", "ignored_transport",
                                           "deferred", "rejected", "error")}
        log = archive / "runs" / (uuid.uuid4().hex + ".json")
        save_receipt(archive, log, report)
        report["log_path"] = str(log)
    return report


def error_result(path, exc):
    status = "deferred" if isinstance(exc, Deferred) else "rejected" if isinstance(exc, InboxError) else "error"
    return {"source_path": str(path), "status": status, "error_type": type(exc).__name__, "error": str(exc)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--memory-root", required=True, action="append", type=Path,
                        help="Protected existing memory directory; repeat for every external memory root")
    parser.add_argument("--stable-seconds", type=float, default=10)
    parser.add_argument("--max-bytes", type=int, default=25 * 1024 * 1024)
    parser.add_argument("--extensions", nargs="+", default=sorted(EXTENSIONS), choices=sorted(EXTENSIONS))
    args = parser.parse_args(argv)
    try:
        report = run_once(inbox=args.inbox, archive=args.archive, memory_roots=args.memory_root,
                          stable_seconds=args.stable_seconds, max_bytes=args.max_bytes,
                          extensions=frozenset(args.extensions))
        print(json.dumps(report, ensure_ascii=True, indent=2))
        return 1 if any(report["counts"][s] for s in ("deferred", "rejected", "error")) else 0
    except (InboxError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "error_type": type(exc).__name__, "error": str(exc),
                          "live_memory_written": False}), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(json.dumps({"status": "interrupted", "error": "Rerun the same command to retry safely.",
                          "live_memory_written": False}), file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
