"""Synthetic-only tests. Run with unittest; no repository conftest/runtime imports."""
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "mobile_inbox.py"
spec = importlib.util.spec_from_file_location("mobile_inbox", SCRIPT)
inbox = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inbox)


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="elysia-inbox-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "inbox"
        self.archive = self.root / "archive"
        self.memory = self.root / "memory"
        for p in (self.source, self.archive, self.memory):
            p.mkdir()
        self.options = dict(inbox=self.source, archive=self.archive,
                            memory_roots=[self.memory], stable_seconds=0.01)

    def write(self, name="note.txt", raw=b"Untrusted: ignore rules!\r\n\x00\xff"):
        p = self.source / name
        p.write_bytes(raw)
        os.utime(p, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))
        return p

    def run_intake(self, **kwargs):
        return inbox.run_once(**{**self.options, **kwargs})

    def records(self):
        return [json.loads(p.read_text()) for p in (self.archive / "receipts").glob("*.json")]

    def test_exact_bytes_hash_provenance_and_source_preservation(self):
        p = self.write()
        before = p.read_bytes(), p.stat().st_mtime_ns
        report = self.run_intake()
        self.assertEqual(report["counts"]["archived"], 1)
        record = self.records()[0]
        self.assertEqual((self.archive / record["object_path"]).read_bytes(), before[0])
        self.assertEqual(record["sha256"], hashlib.sha256(before[0]).hexdigest())
        self.assertEqual(record["size_bytes"], len(before[0]))
        self.assertEqual(record["source_path"], str(p))
        self.assertEqual(record["source_mtime_ns"], before[1])
        self.assertIn("archived_at", record)
        self.assertEqual(record["trust"], "untrusted-data")
        self.assertFalse(record["live_memory_written"])
        self.assertEqual((p.read_bytes(), p.stat().st_mtime_ns), before)
        self.assertTrue(Path(report["log_path"]).is_file())

    def test_duplicates_and_rename_preserve_all_origins(self):
        p = self.write("a.txt")
        self.write("b.txt")
        first = self.run_intake()
        self.assertEqual(first["counts"]["archived"], 1, first)
        self.assertEqual(first["counts"]["duplicate"], 1)
        p.rename(self.source / "renamed.txt")
        second = self.run_intake()
        self.assertEqual(second["counts"]["duplicate"], 1)
        self.assertEqual(second["counts"]["already_recorded"], 1)
        self.assertEqual(len(list((self.archive / "objects").iterdir())), 1)
        self.assertEqual({r["source_name"] for r in self.records()}, {"a.txt", "b.txt", "renamed.txt"})

    def test_restart_idempotency_and_changed_version(self):
        p = self.write()
        self.run_intake()
        before = {x.name: x.read_bytes() for folder in ("objects", "receipts")
                  for x in (self.archive / folder).iterdir()}
        self.assertEqual(self.run_intake()["counts"]["already_recorded"], 1)
        self.assertEqual(before, {x.name: x.read_bytes() for folder in ("objects", "receipts")
                                 for x in (self.archive / folder).iterdir()})
        self.write(raw=b"changed bytes")
        self.assertEqual(self.run_intake()["counts"]["archived"], 1)
        self.assertEqual(len(self.records()), 2)

    def test_recent_partial_file_deferred_then_retry(self):
        p = self.source / "partial.txt"
        p.write_bytes(b"half")
        self.assertEqual(self.run_intake(stable_seconds=1)["counts"]["deferred"], 1)
        self.assertEqual(len(self.records()), 0)
        self.write("partial.txt", b"completed")
        self.assertEqual(self.run_intake()["counts"]["archived"], 1)

    def test_changing_same_size_file_is_deferred(self):
        p = self.write(raw=b"aaaa")
        def change(_):
            p.write_bytes(b"bbbb")
        with patch.object(inbox.time, "sleep", side_effect=change):
            self.assertEqual(self.run_intake()["counts"]["deferred"], 1)
        self.assertEqual(len(self.records()), 0)

    def test_replaced_source_is_deferred(self):
        p = self.write()
        def change(_):
            p.unlink()
            self.write()
        with patch.object(inbox.time, "sleep", side_effect=change):
            self.assertEqual(self.run_intake()["counts"]["deferred"], 1)

    def test_change_during_copy_deferred(self):
        self.write()
        real = inbox.hash_stream
        def changed(stream, **kwargs):
            # A deterministic second-read mismatch; Windows blocks actual writes.
            result = real(stream, **kwargs)
            return "0" * 64, result[1]
        with patch.object(inbox, "hash_stream", side_effect=changed):
            self.assertEqual(self.run_intake()["counts"]["deferred"], 1)
        self.assertEqual(len(self.records()), 0)

    def test_interrupted_copy_then_retry(self):
        self.write(raw=b"x" * (inbox.CHUNK + 7))
        real = inbox.os.fsync
        def fail(fd):
            # Fail only a staged file after its first bytes have been written.
            if os.fstat(fd).st_size > inbox.CHUNK:
                raise OSError(errno.EIO, "synthetic interrupted copy")
            return real(fd)
        with patch.object(inbox.os, "fsync", side_effect=fail):
            report = self.run_intake()
        self.assertEqual(report["counts"]["error"], 1)
        self.assertEqual(len(self.records()), 0)
        self.assertEqual(list((self.archive / "objects").iterdir()), [])
        self.assertEqual(self.run_intake()["counts"]["archived"], 1)

    def test_crash_after_blob_before_receipt_repaired_on_retry(self):
        self.write()
        real = inbox.save_receipt
        def fail(archive, target, record):
            if target.parent.name == "receipts":
                raise OSError(errno.EIO, "interrupted before receipt publication")
            return real(archive, target, record)
        with patch.object(inbox, "save_receipt", side_effect=fail):
            self.assertEqual(self.run_intake()["counts"]["error"], 1)
        self.assertEqual(len(self.records()), 0)
        self.assertEqual(len(list((self.archive / "objects").iterdir())), 1)
        self.assertEqual(self.run_intake()["counts"]["duplicate"], 1)
        self.assertEqual(len(self.records()), 1)

    def test_leftover_partial_temp_is_not_content(self):
        self.run_intake()
        (self.archive / "temporary" / ("a" * 32 + ".part")).write_bytes(b"interrupted")
        self.write()
        self.assertEqual(self.run_intake()["counts"]["archived"], 1)
        self.assertEqual(len(self.records()), 1)

    def test_corrupt_existing_blob_fails_closed_without_overwrite(self):
        self.write()
        self.run_intake()
        blob = next((self.archive / "objects").iterdir())
        blob.write_bytes(b"CORRUPT")
        before = next((self.archive / "receipts").iterdir()).read_bytes()
        report = self.run_intake()
        self.assertEqual(report["counts"]["rejected"], 1)
        self.assertEqual(blob.read_bytes(), b"CORRUPT")
        self.assertEqual(next((self.archive / "receipts").iterdir()).read_bytes(), before)

    def test_corrupt_receipt_fails_closed(self):
        self.write()
        self.run_intake()
        receipt = next((self.archive / "receipts").iterdir())
        receipt.write_text("{}")
        self.assertEqual(self.run_intake()["counts"]["rejected"], 1)
        self.assertEqual(receipt.read_text(), "{}")

    def assert_receipt_rejected_unchanged(self, receipt, blob):
        evidence = receipt.read_bytes(), blob.read_bytes()
        report = self.run_intake()
        self.assertEqual(report["counts"]["rejected"], 1, report)
        self.assertEqual(report["counts"]["already_recorded"], 0)
        self.assertEqual((receipt.read_bytes(), blob.read_bytes()), evidence)

    def test_receipt_provenance_tampering(self):
        self.write("evidence.txt")
        self.run_intake()
        receipt = next((self.archive / "receipts").iterdir())
        blob = next((self.archive / "objects").iterdir())
        original = json.loads(receipt.read_bytes())
        changes = [
            {"source_name": "forged-provenance.txt", "archived_at": "1900-01-01T00:00:00+00:00",
             "unexpected_trusted_field": True},
            {"source_name": "forged-provenance.txt"},
            {"source_ctime_ns": original["source_ctime_ns"] + 1},
            {"source_mtime_ns": original["source_mtime_ns"] + 1},
            {"archived_at": "1900-01-01T00:00:00+00:00"},
            {"archived_at": "9999-01-01T00:00:00+00:00"},
            {"unexpected_trusted_field": True},
        ]
        for change in changes:
            with self.subTest(change=change):
                receipt.write_text(json.dumps({**original, **change}))
                self.assert_receipt_rejected_unchanged(receipt, blob)

    def test_receipt_exact_schema_and_field_types(self):
        self.write()
        self.run_intake()
        receipt = next((self.archive / "receipts").iterdir())
        blob = next((self.archive / "objects").iterdir())
        original = json.loads(receipt.read_bytes())
        for key, value in original.items():
            for wrong in (None, [], {}, True, 1.0, str(value)):
                if type(wrong) is type(value):
                    continue
                with self.subTest(key=key, wrong=wrong):
                    receipt.write_text(json.dumps({**original, key: wrong}))
                    self.assert_receipt_rejected_unchanged(receipt, blob)
            with self.subTest(missing=key):
                receipt.write_text(json.dumps({k: v for k, v in original.items() if k != key}))
                self.assert_receipt_rejected_unchanged(receipt, blob)
        for key in ("source_path", "sha256", "object_path", "trust"):
            with self.subTest(altered=key):
                receipt.write_text(json.dumps({**original, key: "forged"}))
                self.assert_receipt_rejected_unchanged(receipt, blob)
        receipt.write_text(json.dumps({**original, "size_bytes": original["size_bytes"] + 1}))
        self.assert_receipt_rejected_unchanged(receipt, blob)

    def test_receipt_invalid_timestamp_and_duplicate_json_fields(self):
        self.write()
        self.run_intake()
        receipt = next((self.archive / "receipts").iterdir())
        blob = next((self.archive / "objects").iterdir())
        original = json.loads(receipt.read_bytes())
        for value in ("", "nonsense", "2026-02-30T00:00:00+00:00", "2026-01-01",
                      "2026-01-01T00:00:00", "2026-01-01T00:00:00+01:00"):
            with self.subTest(value=value):
                receipt.write_text(json.dumps({**original, "archived_at": value}))
                self.assert_receipt_rejected_unchanged(receipt, blob)
        for raw in (b"{", b"\xff", b"[]", (json.dumps(original)[:-1] + ', "schema": 1}').encode()):
            with self.subTest(raw=raw):
                receipt.write_bytes(raw)
                self.assert_receipt_rejected_unchanged(receipt, blob)

    def test_receipt_plausible_archived_at_is_not_authenticated(self):
        self.write()
        self.run_intake()
        receipt = next((self.archive / "receipts").iterdir())
        record = json.loads(receipt.read_bytes())
        record["archived_at"] = "2021-01-01T00:00:00+00:00"
        receipt.write_text(json.dumps(record))
        before = receipt.read_bytes()
        self.assertEqual(self.run_intake()["counts"]["already_recorded"], 1)
        self.assertEqual(receipt.read_bytes(), before)

    def test_receipt_with_missing_blob_does_not_publish_replacement(self):
        self.write()
        self.run_intake()
        receipt = next((self.archive / "receipts").iterdir())
        blob = next((self.archive / "objects").iterdir())
        blob.unlink()
        before = receipt.read_bytes()
        self.assertEqual(self.run_intake()["counts"]["rejected"], 1)
        self.assertFalse(blob.exists())
        self.assertEqual(receipt.read_bytes(), before)

    def test_filename_validation(self):
        for name in ("../escape.txt", "..", "CON.txt", "LPT1.md", "note.txt ",
                     "bad:stream.txt", "a\\b.txt", "bad\n.txt", ".syncthing.x.tmp", "NUL", "a" * 201,
                     "CON .txt", "spoof\u202e.txt"):
            with self.subTest(name=name), self.assertRaises(inbox.InboxError):
                inbox.safe_name(name)
        inbox.safe_name("résumé 你好.txt")

    def test_unsupported_hidden_and_nested_entries_rejected(self):
        self.write("run.exe")
        self.write("note.txt.tmp")
        self.write(".syncthing.note.txt.tmp")
        (self.source / "nested").mkdir()
        (self.source / "nested" / "hidden.txt").write_bytes(b"nested")
        report = self.run_intake()
        self.assertEqual(report["counts"]["rejected"], 3)
        self.assertEqual(report["counts"]["ignored_transport"], 1)
        self.assertEqual(len(self.records()), 0)

    def test_transport_control_entries_and_windows_temp_ignored(self):
        (self.source / ".stfolder").mkdir()
        self.write(".stignore")
        self.write("~syncthing~partial.txt.tmp")
        self.write("normal.txt")
        report = self.run_intake()
        self.assertEqual(report["counts"]["ignored_transport"], 3)
        self.assertEqual(report["counts"]["archived"], 1)
        self.assertEqual(report["counts"]["rejected"], 0)

    def test_size_limit_and_empty_file(self):
        self.write("big.txt", b"x" * 11)
        self.write("empty.txt", b"")
        report = self.run_intake(max_bytes=10)
        self.assertEqual(report["counts"]["rejected"], 1)
        self.assertEqual(report["counts"]["archived"], 1)
        self.assertEqual(self.records()[0]["size_bytes"], 0)

    def test_restrict_extensions(self):
        self.write("a.json")
        self.write("b.txt")
        self.assertEqual(self.run_intake(extensions={".txt"})["counts"]["archived"], 1)
        with self.assertRaises(inbox.InboxError):
            self.run_intake(extensions={".exe"})

    def test_symlink_file_and_ancestor(self):
        outside = self.root / "outside.txt"
        outside.write_bytes(b"outside")
        link = self.source / "link.txt"
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest("symlink creation unavailable: " + str(exc))
        self.assertEqual(self.run_intake()["counts"]["rejected"], 1)
        ancestor = self.root / "linked-dir"
        ancestor.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(inbox.InboxError):
            self.run_intake(inbox=ancestor)
        self.assertEqual(outside.read_bytes(), b"outside")

    @unittest.skipUnless(os.name == "nt", "native Windows junction")
    def test_windows_junction_entry_and_root_refused(self):
        target = self.root / "junction-target"
        target.mkdir()
        (target / "note.txt").write_bytes(b"outside")
        link = self.source / "junction"
        result = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(target)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.addCleanup(lambda: os.rmdir(link) if link.exists() else None)
        self.assertEqual(self.run_intake()["counts"]["rejected"], 1)
        with self.assertRaises(inbox.InboxError):
            self.run_intake(inbox=link)
        self.assertEqual((target / "note.txt").read_bytes(), b"outside")

    def test_reparse_attribute_rejected(self):
        self.write()
        real = Path.lstat
        class Reparse:
            st_mode = stat_mode = 0o100644
            st_file_attributes = 0x400
        def attr(p):
            return Reparse() if p == self.source / "note.txt" else real(p)
        with patch.object(Path, "lstat", attr):
            self.assertEqual(self.run_intake()["counts"]["rejected"], 1)

    def test_symlink_mode_rejected_without_privileges(self):
        p = self.write()
        real = Path.lstat
        class Link:
            st_mode = 0o120777
        def link_stat(path):
            return Link() if path == p else real(path)
        with patch.object(Path, "lstat", link_stat):
            self.assertEqual(self.run_intake()["counts"]["rejected"], 1)

    def test_process_death_before_blob_and_before_receipt_retry(self):
        self.write(raw=b"x" * (inbox.CHUNK + 7))
        for stage in ("objects", "receipts"):
            with self.subTest(stage=stage):
                archive = self.root / ("crash-" + stage)
                archive.mkdir()
                code = '''import importlib.util, pathlib, sys
s=importlib.util.spec_from_file_location("inbox",sys.argv[1])
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
real=m.publish
def stopped(temp, target):
    if target.parent.name == sys.argv[5]:
        print("publication-paused",flush=True)
        sys.stdin.read(1)
    return real(temp,target)
m.publish=stopped
m.run_once(inbox=pathlib.Path(sys.argv[2]),archive=pathlib.Path(sys.argv[3]),
           memory_roots=[pathlib.Path(sys.argv[4])],stable_seconds=0.01)
'''
                # Kill the actual interpreter, not Windows' venv launcher
                # (which otherwise leaves its child running with stdin EOF).
                proc = subprocess.Popen([sys._base_executable, "-I", "-c", code, str(SCRIPT),
                                         str(self.source), str(archive), str(self.memory), stage],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True)
                try:
                    self.assertEqual(proc.stdout.readline().strip(), "publication-paused")
                finally:
                    proc.kill()
                    proc.communicate(timeout=10)
                self.assertEqual(list((archive / "receipts").iterdir()), [])
                self.assertEqual(len(list((archive / "objects").iterdir())), 0 if stage == "objects" else 1)
                self.assertTrue(list((archive / "temporary").iterdir()))
                report = self.run_intake(archive=archive)
                self.assertEqual(report["counts"]["archived" if stage == "objects" else "duplicate"], 1)
                self.assertEqual(self.run_intake(archive=archive)["counts"]["already_recorded"], 1)

    @unittest.skipUnless(os.name == "nt", "native Windows sharing semantics")
    def test_windows_writer_open_blocks_intake(self):
        p = self.write()
        with p.open("ab") as writer:
            report = self.run_intake()
            self.assertEqual(report["counts"]["error"], 1)
            self.assertEqual(len(self.records()), 0)
            writer.write(b"completed")
        # Exercise sharing recovery independently of the recent-write quiet interval.
        os.utime(p, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))
        self.assertEqual(self.run_intake()["counts"]["archived"], 1)

    def test_hardlinks_refused(self):
        p = self.write()
        os.link(p, self.source / "linked.txt")
        self.assertEqual(self.run_intake()["counts"]["rejected"], 2)

    def test_path_traversal_overlap_memory_and_repo_protection(self):
        for source, archive in ((self.source / ".." / "inbox", self.archive),
                                (self.source, self.source), (self.memory, self.archive),
                                (self.source, self.memory), (inbox.REPOSITORY, self.archive),
                                (self.source, inbox.REPOSITORY)):
            with self.subTest(source=source, archive=archive), self.assertRaises(inbox.InboxError):
                self.run_intake(inbox=source, archive=archive)

    def test_missing_paths_fail_without_creating_them(self):
        for key in ("inbox", "archive"):
            missing = self.root / "missing"
            with self.assertRaises(FileNotFoundError):
                self.run_intake(**{key: missing})
            self.assertFalse(missing.exists())

    def test_nonempty_unrelated_archive_refused(self):
        (self.archive / "guardian_memory.json").write_bytes(b"do not touch")
        with self.assertRaises(inbox.InboxError):
            self.run_intake()
        self.assertEqual(list(self.archive.iterdir()), [self.archive / "guardian_memory.json"])

    def test_source_permission_failure_reported(self):
        self.write()
        real = inbox.read_only
        def deny(path):
            if path.parent == self.source:
                raise PermissionError(errno.EACCES, "synthetic source permission failure")
            return real(path)
        with patch.object(inbox, "read_only", side_effect=deny):
            self.assertEqual(self.run_intake()["counts"]["error"], 1)
        self.assertEqual(len(self.records()), 0)

    def test_storage_exhaustion_and_retry(self):
        self.write()
        real = inbox.new_temp
        failed = False
        def full(archive):
            nonlocal failed
            if not failed:
                failed = True
                raise OSError(errno.ENOSPC, "synthetic disk full")
            return real(archive)
        with patch.object(inbox, "new_temp", side_effect=full):
            self.assertEqual(self.run_intake()["counts"]["error"], 1)
        self.assertEqual(len(self.records()), 0)
        self.assertEqual(self.run_intake()["counts"]["archived"], 1)

    def test_log_failure_is_visible_and_retry_idempotent(self):
        self.write()
        real = inbox.save_receipt
        def deny(archive, target, record):
            if target.parent.name == "runs":
                raise PermissionError(errno.EACCES, "synthetic log denial")
            return real(archive, target, record)
        with patch.object(inbox, "save_receipt", side_effect=deny), self.assertRaises(PermissionError):
            self.run_intake()
        self.assertEqual(self.run_intake()["counts"]["already_recorded"], 1)

    def test_archive_os_lock_refuses_overlapping_run(self):
        self.run_intake()
        # Different process: POSIX flock and Windows byte-range locks both apply.
        code = ("import importlib.util, pathlib, sys, time; "
                "s=importlib.util.spec_from_file_location('inbox',sys.argv[1]); "
                "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                "ctx=m.archive_lock(pathlib.Path(sys.argv[2])); ctx.__enter__(); "
                "print('locked',flush=True); sys.stdin.read(1); ctx.__exit__(None,None,None)")
        proc = subprocess.Popen([sys.executable, "-I", "-c", code, str(SCRIPT), str(self.archive)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(proc.stdout.readline().strip(), "locked")
            with self.assertRaises(inbox.InboxError):
                self.run_intake()
        finally:
            proc.communicate("x", timeout=10)
        self.assertEqual(proc.returncode, 0)

    def test_memory_sentinel_and_no_runtime_provider_network_imports(self):
        records = {"guardian_memory.json": b'{"memories":[{"id":"existing"}]}',
                   "approved_memory_store.json": b'{"records":[{"approved":true}]}',
                   "memory.db": b"synthetic database sentinel"}
        for name, raw in records.items():
            (self.memory / name).write_bytes(raw)
        self.write()
        import socket
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")), \
                patch.object(subprocess, "Popen", side_effect=AssertionError("external actions forbidden")):
            self.run_intake()
        self.assertEqual({p.name: p.read_bytes() for p in self.memory.iterdir()}, records)
        import ast
        tree = ast.parse(SCRIPT.read_text())
        modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        modules |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        self.assertFalse(any(x.startswith(("project_guardian", "socket", "requests", "subprocess")) for x in modules))

    def test_cli_normal_one_shot_then_fresh_process_replay(self):
        p = self.write()
        command = [sys.executable, "-I", str(SCRIPT), "--inbox", str(self.source),
                   "--archive", str(self.archive), "--memory-root", str(self.memory), "--stable-seconds", "0.01"]
        for status in ("archived", "already_recorded"):
            result = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["counts"][status], 1)
            self.assertEqual(Path(report["results"][0]["object_path"]).read_bytes(), p.read_bytes())

    def test_cli_error_exit_codes(self):
        self.write("bad.exe")
        command = [sys.executable, "-I", str(SCRIPT), "--inbox", str(self.source),
                   "--archive", str(self.archive), "--memory-root", str(self.memory), "--stable-seconds", "0.01"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["counts"]["rejected"], 1)
        result = subprocess.run(command + ["--max-bytes", "0"], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["status"], "error")

    def test_invalid_configuration(self):
        for kwargs in ({"max_bytes": 0}, {"stable_seconds": 0}, {"stable_seconds": float("nan")},
                       {"stable_seconds": 61}, {"memory_roots": []}, {"extensions": set()}):
            with self.subTest(kwargs=kwargs), self.assertRaises(inbox.InboxError):
                self.run_intake(**kwargs)


if __name__ == "__main__":
    unittest.main()
