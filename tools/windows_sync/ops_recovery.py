"""Stopped-pilot, local-only operational-root backup and isolated restore.

No automatic promotion, live-data restore, background worker, USB discovery, or
cloud/network operation. A manifest-only release backup is NOT a data backup.
The supported scope is exactly pilot_paths.PILOT_DATA_ROOT (contained pilot);
external paths used by other Guardian modes are deliberately NOT certified.
"""
from __future__ import annotations

import argparse
import ctypes
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import tempfile

_REPO = Path(__file__).resolve().parents[2]
_SCHEMA = "elysia.stopped_pilot_snapshot.v1"
_DB_HEADER = b"SQLite format 3\x00"
_SQLITE_EXTS = (".db", ".sqlite", ".sqlite3")


class RecoveryBlocked(RuntimeError):
    """Explicit fail-closed refusal, not a partial backup success."""


def _expected_root() -> Path:
    from pilot.pilot_paths import PILOT_DATA_ROOT
    return PILOT_DATA_ROOT.resolve(strict=False)


def _safe_path(value: Path | str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() or ".." in path.parts:
        raise RecoveryBlocked("absolute, non-traversing path required")
    for node in (path, *path.parents):
        try:
            meta = node.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(meta.st_mode) or node.is_symlink():
            raise RecoveryBlocked("symlink in path")
        if os.name == "nt":
            if not hasattr(node, "is_junction") or node.is_junction():
                raise RecoveryBlocked("junction in path or junction check unavailable")
            if getattr(meta, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise RecoveryBlocked("Windows reparse point in path")
    resolved = path.resolve(strict=False)
    if os.name == "nt":
        # No mapped network/UNC/removable volume: this is LOCAL-only recovery.
        root = Path(resolved.anchor)
        if not root.anchor:
            raise RecoveryBlocked("unknown local volume")
        try:
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(root))
        except (AttributeError, OSError) as exc:
            raise RecoveryBlocked("cannot establish local fixed disk") from exc
        if drive_type != 3:  # DRIVE_FIXED
            raise RecoveryBlocked("network/removable/unknown volume refused")
    return resolved


def _overlaps(a: Path, b: Path) -> bool:
    return a == b or a in b.parents or b in a.parents


def _new_destination(path: Path | str, *, protected: tuple[Path, ...]) -> Path:
    dest = _safe_path(path)
    if dest.exists() or dest.is_symlink():
        raise RecoveryBlocked("destination must not exist")
    if not dest.parent.is_dir():
        raise RecoveryBlocked("destination parent must already exist")
    if _overlaps(dest, _REPO):
        raise RecoveryBlocked("destination overlaps Elysia source")
    for item in protected:
        if _overlaps(dest, _safe_path(item)):
            raise RecoveryBlocked("destination overlaps operational or protected data")
    return dest


def _tree(root: Path) -> tuple[list[str], list[dict]]:
    """Exact, bounded rooted inventory. Never follow links or accept hardlinks."""
    dirs: list[str] = []
    files: list[dict] = []
    if not root.is_dir():
        raise RecoveryBlocked("root missing or not a directory")
    pending = [root]
    while pending:
        folder = pending.pop()
        with os.scandir(folder) as entries:
            ordered = sorted(entries, key=lambda e: e.name)
        for entry in ordered:
            path = Path(entry.path)
            meta = path.lstat()
            if stat.S_ISLNK(meta.st_mode) or path.is_symlink():
                raise RecoveryBlocked("link within operational tree")
            if os.name == "nt":
                if not hasattr(path, "is_junction") or path.is_junction():
                    raise RecoveryBlocked("junction within operational tree")
                if getattr(meta, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    raise RecoveryBlocked("reparse point within operational tree")
            name = path.relative_to(root).as_posix()
            if stat.S_ISDIR(meta.st_mode):
                dirs.append(name)
                pending.append(path)
            elif stat.S_ISREG(meta.st_mode):
                if meta.st_nlink != 1:
                    raise RecoveryBlocked("hard-linked operational file")
                if path.name.lower().endswith(("-wal", "-shm", "-journal")):
                    raise RecoveryBlocked("SQLite WAL/SHM/journal present, offline consistency unproved")
                files.append({
                    "path": name, "size": meta.st_size, "mtime_ns": meta.st_mtime_ns,
                    "dev": meta.st_dev, "ino": meta.st_ino,
                })
            else:
                raise RecoveryBlocked("non-regular operational entry")
            if len(dirs) + len(files) > 100000:
                raise RecoveryBlocked("inventory size cap exceeded")
    if sum(row["size"] for row in files) > 10 * 1024**3:
        raise RecoveryBlocked("operational snapshot exceeds 10 GiB safety budget")
    return sorted(dirs), sorted(files, key=lambda r: r["path"])


def _copy_verified(src: Path, dst: Path, identity: dict) -> dict:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(src, flags), "rb") as input_file:
        before = os.fstat(input_file.fileno())
        if (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size, before.st_nlink) != (
            identity["dev"], identity["ino"], identity["mtime_ns"], identity["size"], 1
        ):
            raise RecoveryBlocked("source changed during snapshot")
        h = hashlib.sha256()
        first = b""
        with dst.open("xb") as output:
            while True:
                chunk = input_file.read(1024 * 1024)
                if not chunk:
                    break
                if not first:
                    first = chunk[:16]
                h.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        after = os.fstat(input_file.fileno())
        if (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size) != (
            before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size
        ):
            raise RecoveryBlocked("source changed while copying")
    if first == _DB_HEADER or src.suffix.lower() in _SQLITE_EXTS:
        _check_sqlite(dst)
    return {"path": identity["path"], "size": identity["size"], "sha256": h.hexdigest()}


def _check_sqlite(db: Path) -> None:
    uri = db.resolve(strict=True).as_uri() + "?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=1.0)
        try:
            row = connection.execute("PRAGMA quick_check").fetchone()
            if row != ("ok",):
                raise RecoveryBlocked("SQLite quick_check failed")
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise RecoveryBlocked("SQLite consistency could not be established") from exc


@contextmanager
def _hold_stopped(root: Path):
    """Existing Windows pilot writer-exclusion mutex held across entire read.

    This is not proof against arbitrary noncooperating writers. A full tree
    before/after inventory and content hashes also guard against accidental
    concurrent mutation, but cannot prove multi-file atomicity under races.
    """
    if os.name != "nt":
        raise RecoveryBlocked("native Windows pilot stopped-writer guard unavailable")
    pilot_path = _REPO / "pilot"
    if str(pilot_path) not in sys.path:
        sys.path.insert(0, str(pilot_path))
    try:
        from pilot_exclusion import writer_exclusion_status
        response = writer_exclusion_status(
            entry=_REPO / "scripts" / "start_contained_browser_memory.py",
            data_root=root, pid_file=root / "runtime" / "pilot.pid",
            runtime_json=root / "runtime" / "pilot.runtime.json",
        )
    except Exception as exc:
        raise RecoveryBlocked("pilot writer exclusion status unavailable") from exc
    hold = response.get("hold")
    if not response.get("safe_to_write") or hold is None:
        raise RecoveryBlocked("pilot stopped-writer exclusion unverified")
    try:
        yield
    finally:
        hold.release()


def _validate_manifest(snapshot: Path) -> tuple[list[str], list[dict]]:
    root = _safe_path(snapshot)
    if not root.is_dir():
        raise RecoveryBlocked("snapshot directory absent")
    path = root / "manifest.json"
    if not path.is_file():
        raise RecoveryBlocked("missing snapshot manifest")
    if _safe_path(path) != path or _safe_path(root / "payload") != root / "payload":
        raise RecoveryBlocked("snapshot manifest/payload path alias")
    meta = path.lstat()
    if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or meta.st_size > 8 * 1024 * 1024:
        raise RecoveryBlocked("unsafe snapshot manifest")
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryBlocked("invalid snapshot manifest") from exc
    if not isinstance(info, dict) or info.get("schema") != _SCHEMA:
        raise RecoveryBlocked("unknown snapshot schema")
    if set(info) != {"schema", "created_utc", "directories", "files", "runtime"}:
        raise RecoveryBlocked("unexpected snapshot manifest keys")
    dirs, files = info.get("directories"), info.get("files")
    if not isinstance(dirs, list) or not isinstance(files, list):
        raise RecoveryBlocked("invalid snapshot inventory")
    if len(dirs) + len(files) > 100000:
        raise RecoveryBlocked("snapshot inventory size cap exceeded")
    if not all(isinstance(name, str) for name in dirs) or not all(isinstance(row, dict) for row in files):
        raise RecoveryBlocked("malformed snapshot inventory")
    names = dirs + [row.get("path") for row in files]
    if not all(isinstance(name, str) for name in names) or len(set(names)) != len(names):
        raise RecoveryBlocked("snapshot inventory incomplete or duplicate")
    for name in names:
        if not isinstance(name, str) or not name or "\\" in name:
            raise RecoveryBlocked("invalid snapshot path")
        parts = Path(name).parts
        if Path(name).is_absolute() or any(x in (".", "..") for x in parts):
            raise RecoveryBlocked("snapshot path escape")
    for row in files:
        if not isinstance(row, dict) or set(row) != {"path", "size", "sha256"}:
            raise RecoveryBlocked("invalid snapshot file row")
        if type(row["size"]) is not int or row["size"] < 0:
            raise RecoveryBlocked("invalid snapshot file size")
        if (not isinstance(row["sha256"], str) or len(row["sha256"]) != 64
                or any(char not in "0123456789abcdef" for char in row["sha256"])):
            raise RecoveryBlocked("invalid snapshot hash")
    if {entry.name for entry in root.iterdir()} != {"payload", "manifest.json"}:
        raise RecoveryBlocked("unexpected snapshot top-level entry")
    payload = root / "payload"
    real_dirs, real_files = _tree(payload)
    if real_dirs != sorted(dirs) or [f["path"] for f in real_files] != sorted(r["path"] for r in files):
        raise RecoveryBlocked("snapshot contains missing/extra entries")
    by_path = {r["path"]: r for r in files}
    for row in real_files:
        actual = payload / row["path"]
        if row["size"] != by_path[row["path"]]["size"]:
            raise RecoveryBlocked("snapshot file size mismatch")
        with actual.open("rb") as fh:
            signature = fh.read(16)
            fh.seek(0)
            hashval = hashlib.file_digest(fh, "sha256").hexdigest()
        if hashval != by_path[row["path"]]["sha256"]:
            raise RecoveryBlocked("snapshot file hash mismatch")
        if signature == _DB_HEADER or actual.suffix.lower() in _SQLITE_EXTS:
            _check_sqlite(actual)
    return dirs, files


def verify_snapshot(snapshot: Path | str) -> dict:
    dirs, files = _validate_manifest(Path(snapshot))
    return {"status": "VERIFIED_OFFLINE_SNAPSHOT", "files": len(files), "dirs": len(dirs)}


def _publish(stage: Path, dest: Path) -> None:
    """Commit only if the destination is ABSENT, including at rename time.

    Windows os.rename refuses existing targets. Linux renameat2 with
    RENAME_NOREPLACE avoids overwriting an empty directory raced into place.
    Other platforms fail closed instead of risking an implicit replacement.
    """
    if dest.exists() or dest.is_symlink():
        raise RecoveryBlocked("destination changed before commit")
    if os.name == "nt":
        os.rename(stage, dest)
        return
    if not sys.platform.startswith("linux"):
        raise RecoveryBlocked("atomic no-replace rename unavailable")
    libc = ctypes.CDLL(None, use_errno=True)
    operation = getattr(libc, "renameat2", None)
    if operation is None:
        raise RecoveryBlocked("atomic no-replace rename unavailable")
    operation.argtypes = [
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
    ]
    operation.restype = ctypes.c_int
    rc = operation(-100, os.fsencode(stage), -100, os.fsencode(dest), 1)
    if rc != 0:
        raise RecoveryBlocked("atomic snapshot destination publish refused")


def create_snapshot(source: Path | str, destination: Path | str, *, acknowledge_stopped: bool = False) -> dict:
    """Explicit stopped-pilot snapshot. Never automatically called by promote."""
    if not acknowledge_stopped:
        raise RecoveryBlocked("explicit stopped-runtime acknowledgement required")
    root = _safe_path(source)
    if _overlaps(root, _REPO):
        raise RecoveryBlocked("operational root overlaps executing source")
    if root != _expected_root():
        raise RecoveryBlocked("only configured contained pilot root is supported")
    dest = _new_destination(destination, protected=(root, _expected_root()))
    stage = None
    with _hold_stopped(root):
        first_dirs, first_files = _tree(root)
        if "memory/guardian_memory.json" not in {x["path"] for x in first_files}:
            raise RecoveryBlocked("authoritative contained MemoryCore file missing")
        try:
            stage = Path(tempfile.mkdtemp(dir=dest.parent, prefix=".elysia-ops-stage-"))
            payload = stage / "payload"
            payload.mkdir()
            for name in first_dirs:
                (payload / name).mkdir(parents=True, exist_ok=False)
            saved = []
            for file in first_files:
                output = payload / file["path"]
                output.parent.mkdir(parents=True, exist_ok=True)
                saved.append(_copy_verified(root / file["path"], output, file))
            if (first_dirs, first_files) != _tree(root):
                raise RecoveryBlocked("source inventory changed during snapshot")
            manifest = {"schema": _SCHEMA, "created_utc": datetime.now(timezone.utc).isoformat(),
                        "directories": first_dirs, "files": saved, "runtime": "stopped-pilot"}
            (stage / "manifest.json").write_text(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            _validate_manifest(stage)
            _publish(stage, dest)
            stage = None
        finally:
            if stage is not None and stage.exists():
                shutil.rmtree(stage)
    verification = verify_snapshot(dest)
    return {"status": "SNAPSHOT_CREATED_OFFLINE", "verified": verification["status"],
            "files": verification["files"], "dirs": verification["dirs"]}


def restore_isolated(snapshot: Path | str, destination: Path | str) -> dict:
    """Restore into a NEW, separate directory only; NEVER over operational root."""
    snap = _safe_path(snapshot)
    dest = _new_destination(destination, protected=(snap, _expected_root()))
    dirs, files = _validate_manifest(snap)
    stage = None
    try:
        stage = Path(tempfile.mkdtemp(dir=dest.parent, prefix=".elysia-restore-stage-"))
        for name in dirs:
            (stage / name).mkdir(parents=True, exist_ok=False)
        for row in files:
            target = stage / row["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            source = snap / "payload" / row["path"]
            shutil.copyfile(source, target, follow_symlinks=False)
            if hashlib.sha256(target.read_bytes()).hexdigest() != row["sha256"]:
                raise RecoveryBlocked("restored file integrity mismatch")
        # Re-check backup bytes and tree before publishing, fail closed if changed.
        _validate_manifest(snap)
        restored_dirs, restored_files = _tree(stage)
        if restored_dirs != sorted(dirs) or [r["path"] for r in restored_files] != sorted(r["path"] for r in files):
            raise RecoveryBlocked("restored tree incomplete")
        for row in files:
            restored_path = stage / row["path"]
            if restored_path.suffix.lower() in _SQLITE_EXTS:
                _check_sqlite(restored_path)
        _publish(stage, dest)
        stage = None
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)
    return {"status": "RESTORED_TO_ISOLATED_ROOT", "files": len(files), "dirs": len(dirs)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Contained Elysia pilot stopped-data snapshot and isolated restore")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--snapshot-root")
    group.add_argument("--verify")
    group.add_argument("--restore-from")
    parser.add_argument("--to", help="new destination directory, outside source and operational root")
    parser.add_argument("--ack-stopped", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.snapshot_root is not None:
            if not args.to:
                raise RecoveryBlocked("--to destination required")
            report = create_snapshot(args.snapshot_root, args.to, acknowledge_stopped=args.ack_stopped)
        elif args.restore_from is not None:
            if not args.to:
                raise RecoveryBlocked("--to destination required")
            report = restore_isolated(args.restore_from, args.to)
        else:
            report = verify_snapshot(args.verify)
    except (RecoveryBlocked, OSError, ValueError) as exc:
        # Do not echo private file paths, sensitive contents, or exception chains.
        print("BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
