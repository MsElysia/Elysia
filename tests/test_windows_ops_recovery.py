"""Task 009: synthetic stopped-pilot snapshot and isolated restore.

Only pytest tmp_path is read/written. No user root, GitHub/cloud, live Pilot,
provider, installed release, or operational backup is touched.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from tools.windows_sync import ops_recovery as ops


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    root = tmp_path / "pilot-data"
    (root / "memory").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "inbox_state").mkdir()
    (root / "empty-leaf").mkdir()
    memory = root / "memory" / "guardian_memory.json"
    memory.write_text('[{"thought":"synthetic amber-91"}]', encoding="utf-8")
    (root / "memory" / "guardian_memory.json.memorycore.lock").write_bytes(b"\x00")
    (root / "data" / "enhanced_tasks.json").write_text('{"tasks":[]}', encoding="utf-8")
    (root / "inbox_state" / "import_manifest.jsonl").write_text(
        '{"status":"imported","sha256":"fake"}\n', encoding="utf-8"
    )
    db = root / "data" / "elysia_timeline.db"
    connection = sqlite3.connect(db)
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("CREATE TABLE synthetic (id INTEGER, note TEXT)")
    connection.execute("INSERT INTO synthetic VALUES(1,'fictional')")
    connection.commit()
    connection.close()

    @contextmanager
    def stopped(_root):
        assert _root == root
        yield

    monkeypatch.setattr(ops, "_expected_root", lambda: root)
    monkeypatch.setattr(ops, "_hold_stopped", stopped)
    return {"root": root, "memory": memory, "tmp": tmp_path, "snapshot": tmp_path / "snapshot",
            "restored": tmp_path / "restored"}


def source_bytes(root):
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*") if p.is_file()
    }


def make_snapshot(item):
    return ops.create_snapshot(
        item["root"], item["snapshot"], acknowledge_stopped=True
    )


def test_complete_snapshot_verified_and_restored_into_new_root(isolated):
    before = source_bytes(isolated["root"])
    result = make_snapshot(isolated)
    assert result["status"] == "SNAPSHOT_CREATED_OFFLINE"
    assert result["verified"] == "VERIFIED_OFFLINE_SNAPSHOT"
    assert result["files"] == len(before)
    assert result["dirs"] >= 4
    assert ops.verify_snapshot(isolated["snapshot"])["files"] == len(before)
    restoration = ops.restore_isolated(isolated["snapshot"], isolated["restored"])
    assert restoration["status"] == "RESTORED_TO_ISOLATED_ROOT"
    assert source_bytes(isolated["restored"]) == before
    assert source_bytes(isolated["root"]) == before
    assert (isolated["restored"] / "empty-leaf").is_dir()
    with sqlite3.connect(isolated["restored"] / "data" / "elysia_timeline.db") as db:
        assert db.execute("SELECT note FROM synthetic").fetchone() == ("fictional",)


def test_default_denies_without_stopped_ack_and_no_output(isolated):
    with pytest.raises(ops.RecoveryBlocked, match="acknowledgement"):
        ops.create_snapshot(isolated["root"], isolated["snapshot"])
    assert not isolated["snapshot"].exists()


def test_unknown_runtime_root_is_blocked_even_with_ack(isolated, monkeypatch):
    monkeypatch.setattr(ops, "_expected_root", lambda: isolated["tmp"] / "different-root")
    with pytest.raises(ops.RecoveryBlocked, match="configured contained pilot root"):
        make_snapshot(isolated)
    assert not isolated["snapshot"].exists()


def test_stopped_writer_fence_unavailable_is_blocked(isolated, monkeypatch):
    @contextmanager
    def no_guard(_root):
        raise ops.RecoveryBlocked("writer active or uncertain")
        yield
    monkeypatch.setattr(ops, "_hold_stopped", no_guard)
    with pytest.raises(ops.RecoveryBlocked, match="writer active"):
        make_snapshot(isolated)
    assert not isolated["snapshot"].exists()


def test_running_sqlite_wal_or_shm_fails_before_copy(isolated):
    (isolated["root"] / "data" / "elysia_timeline.db-wal").write_bytes(b"synthetic WAL")
    with pytest.raises(ops.RecoveryBlocked, match="SQLite WAL"):
        make_snapshot(isolated)
    assert not isolated["snapshot"].exists()


def test_source_link_to_external_is_refused_without_reading_it(isolated):
    external = isolated["tmp"] / "private-external.txt"
    external.write_text("external sentinel, do not copy", encoding="utf-8")
    link = isolated["root"] / "data" / "redirected.txt"
    try:
        link.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("unprivileged file symlink unavailable")
    with pytest.raises(ops.RecoveryBlocked, match="link"):
        make_snapshot(isolated)
    assert not isolated["snapshot"].exists()
    assert external.read_text(encoding="utf-8") == "external sentinel, do not copy"


def test_source_hardlinked_file_refused(isolated):
    import os
    peer = isolated["root"] / "data" / "aliased-memory.json"
    try:
        os.link(isolated["memory"], peer)
    except OSError:
        pytest.skip("same-volume hardlink unavailable")
    with pytest.raises(ops.RecoveryBlocked, match="hard-linked"):
        make_snapshot(isolated)
    assert not isolated["snapshot"].exists()


def test_snapshot_destination_within_source_refused(isolated):
    destination = isolated["root"] / "backups"
    with pytest.raises(ops.RecoveryBlocked, match="overlaps"):
        ops.create_snapshot(isolated["root"], destination, acknowledge_stopped=True)
    assert not destination.exists()


def test_failure_during_copy_leaves_no_published_snapshot(isolated, monkeypatch):
    original = ops._copy_verified
    seen = {"count": 0}
    before = source_bytes(isolated["root"])

    def interrupt(src, dst, identity):
        seen["count"] += 1
        if seen["count"] == 2:
            raise OSError("synthetic interrupted copy")
        return original(src, dst, identity)

    monkeypatch.setattr(ops, "_copy_verified", interrupt)
    with pytest.raises(OSError, match="interrupted"):
        make_snapshot(isolated)
    assert seen["count"] == 2
    assert not isolated["snapshot"].exists()
    assert not list(isolated["tmp"].glob(".elysia-ops-stage-*"))
    assert source_bytes(isolated["root"]) == before


def test_source_change_during_copy_blocks_publication(isolated, monkeypatch):
    original = ops._copy_verified
    moved = {"done": False}

    def concurrent_writer(src, dst, identity):
        result = original(src, dst, identity)
        if not moved["done"]:
            moved["done"] = True
            (isolated["root"] / "data" / "new-writer-file.txt").write_text(
                "synthetic interrupted writer", encoding="utf-8"
            )
        return result

    monkeypatch.setattr(ops, "_copy_verified", concurrent_writer)
    with pytest.raises(ops.RecoveryBlocked, match="inventory changed"):
        make_snapshot(isolated)
    assert moved["done"]
    assert not isolated["snapshot"].exists()


@pytest.mark.parametrize("mutation", ["corrupt", "missing", "extra", "top_extra", "path_escape", "hash_tamper"])
def test_corrupt_or_tampered_snapshot_cannot_restore(isolated, mutation):
    make_snapshot(isolated)
    snap = isolated["snapshot"]
    manifest = snap / "manifest.json"
    contents = json.loads(manifest.read_text(encoding="utf-8"))
    memory = snap / "payload" / "memory" / "guardian_memory.json"
    if mutation == "corrupt":
        memory.write_bytes(b"tampered without manifest update")
    elif mutation == "missing":
        memory.unlink()
    elif mutation == "extra":
        (snap / "payload" / "extra.txt").write_text("surprise", encoding="utf-8")
    elif mutation == "top_extra":
        (snap / "stray-snapshot-file.txt").write_text("surprise", encoding="utf-8")
    elif mutation == "path_escape":
        contents["files"][0]["path"] = "../outside.txt"
        manifest.write_text(json.dumps(contents), encoding="utf-8")
    elif mutation == "hash_tamper":
        contents["files"][0]["sha256"] = "f" * 64
        manifest.write_text(json.dumps(contents), encoding="utf-8")
    with pytest.raises(ops.RecoveryBlocked):
        ops.restore_isolated(snap, isolated["restored"])
    assert not isolated["restored"].exists()


def test_refuse_restore_into_existing_target_or_original_operation_root(isolated):
    make_snapshot(isolated)
    isolated["restored"].mkdir()
    sentinel = isolated["restored"] / "keep.txt"
    sentinel.write_text("existing untouched", encoding="utf-8")
    with pytest.raises(ops.RecoveryBlocked, match="must not exist"):
        ops.restore_isolated(isolated["snapshot"], isolated["restored"])
    assert sentinel.read_text(encoding="utf-8") == "existing untouched"
    with pytest.raises(ops.RecoveryBlocked):
        ops.restore_isolated(isolated["snapshot"], isolated["root"])


def test_restore_failure_rolls_back_staging_only(isolated, monkeypatch):
    make_snapshot(isolated)
    original = ops.shutil.copyfile
    attempts = {"count": 0}

    def interrupted(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 2:
            raise OSError("synthetic restore interruption")
        return original(*args, **kwargs)

    monkeypatch.setattr(ops.shutil, "copyfile", interrupted)
    with pytest.raises(OSError, match="interruption"):
        ops.restore_isolated(isolated["snapshot"], isolated["restored"])
    assert attempts["count"] == 2
    assert not isolated["restored"].exists()
    assert not list(isolated["tmp"].glob(".elysia-restore-stage-*"))


def test_sqlite_corruption_is_refused_even_if_manifest_hash_updated(isolated):
    make_snapshot(isolated)
    snap = isolated["snapshot"]
    db = snap / "payload" / "data" / "elysia_timeline.db"
    db.write_bytes(b"not an SQLite database")
    manifest = snap / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    for row in payload["files"]:
        if row["path"] == "data/elysia_timeline.db":
            row["size"] = db.stat().st_size
            row["sha256"] = hashlib.sha256(db.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ops.RecoveryBlocked, match="SQLite"):
        ops.verify_snapshot(snap)



def test_snapshot_existing_destination_never_overwritten(isolated):
    isolated["snapshot"].mkdir()
    marker = isolated["snapshot"] / "marker"
    marker.write_text("preserve this", encoding="utf-8")
    with pytest.raises(ops.RecoveryBlocked, match="must not exist"):
        make_snapshot(isolated)
    assert marker.read_text(encoding="utf-8") == "preserve this"


def test_snapshot_publish_race_preserves_new_competing_target(isolated, monkeypatch):
    original = ops._publish
    def competing_writer(stage, dest):
        dest.mkdir()
        (dest / "competing.txt").write_text("do not replace", encoding="utf-8")
        original(stage, dest)
    monkeypatch.setattr(ops, "_publish", competing_writer)
    with pytest.raises(ops.RecoveryBlocked, match="destination changed"):
        make_snapshot(isolated)
    assert (isolated["snapshot"] / "competing.txt").read_text(encoding="utf-8") == "do not replace"
    assert not list(isolated["tmp"].glob(".elysia-ops-stage-*"))


def test_snapshot_refuses_missing_primary_memory(isolated):
    isolated["memory"].unlink()
    with pytest.raises(ops.RecoveryBlocked, match="authoritative contained MemoryCore"):
        make_snapshot(isolated)
    assert not isolated["snapshot"].exists()
