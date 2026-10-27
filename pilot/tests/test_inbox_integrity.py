"""Inbox containment, durable write acknowledgement, concurrency lock regressions."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PILOT_DIR = Path(__file__).resolve().parents[1]
SRC = PILOT_DIR.parent
sys.path[:0] = [str(PILOT_DIR), str(SRC)]

import inbox_import as inbox  # noqa: E402
from pilot_fs import assert_physical_inbox_root, ImportFileLock  # noqa: E402


class TestInboxIntegrity(unittest.TestCase):
    def _scope(self, root: Path):
        ind = root / "inbox"
        state = root / "inbox_state"
        ind.mkdir(parents=True, exist_ok=True)
        state.mkdir(parents=True, exist_ok=True)
        mem = root / "memory" / "guardian_memory.json"
        mem.parent.mkdir(parents=True, exist_ok=True)
        mem.write_text("[]", encoding="utf-8")
        return ind, state, mem

    def test_junction_inbox_root_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            outside = root / "outside"
            outside.mkdir()
            (outside / "outside.txt").write_text(
                "Fictional outside-only secret: the violet gate opens at dawn.",
                encoding="utf-8",
            )
            junction = root / "junction-inbox"
            out = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
                capture_output=True,
                text=True,
            )
            if out.returncode != 0:
                self.skipTest(f"mklink /J unavailable: {out.stdout}{out.stderr}")
            ok, detail = assert_physical_inbox_root(junction)
            self.assertFalse(ok)
            state = root / "state"
            state.mkdir()
            mem = root / "memory"
            mem.mkdir()
            (mem / "guardian_memory.json").write_text("[]", encoding="utf-8")
            hold = MagicMock()
            with patch.object(inbox, "INBOX_DIR", junction), patch.object(
                inbox, "INBOX_STATE_DIR", state
            ), patch.object(
                inbox, "INBOX_MANIFEST", state / "import_manifest.jsonl"
            ), patch.object(inbox, "PILOT_DATA_ROOT", root), patch.object(
                inbox, "PID_FILE", root / "runtime" / "missing.pid"
            ), patch.object(
                inbox, "RUNTIME_JSON", root / "runtime" / "missing.json"
            ):
                report = inbox.scan_inbox_to_memory(apply=True, exclusion_hold=hold)
            self.assertEqual(report["imported"], 0)
            self.assertFalse(report["ok"])
            self.assertTrue(any("reparse" in e.lower() or "containment" in e.lower() for e in report["errors"]))

    def test_failed_save_not_marked_imported(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ind, state, mem = self._scope(root)
            baseline = [
                {
                    "thought": "Fictional baseline memory must survive.",
                    "category": "acceptance",
                    "metadata": {},
                }
            ]
            mem.write_text(json.dumps(baseline), encoding="utf-8")
            content = "Fictional ghost import identical content after failed persistence."
            (ind / "a.txt").write_text(content, encoding="utf-8")
            (ind / "b.txt").write_text(content, encoding="utf-8")
            hold = MagicMock()
            with patch.object(inbox, "INBOX_DIR", ind), patch.object(
                inbox, "INBOX_STATE_DIR", state
            ), patch.object(
                inbox, "INBOX_MANIFEST", state / "import_manifest.jsonl"
            ), patch.object(inbox, "PILOT_DATA_ROOT", root), patch(
                "project_guardian.memory.os.replace",
                side_effect=OSError("injected durable failure"),
            ):
                failed = inbox.scan_inbox_to_memory(apply=True, exclusion_hold=hold)
            self.assertEqual(failed.get("imported"), 0)
            man = state / "import_manifest.jsonl"
            self.assertFalse(man.exists() and "imported" in man.read_text(encoding="utf-8"))
            self.assertEqual(json.loads(mem.read_text(encoding="utf-8")), baseline)
            # Retry after removing injection must be able to import (no ghost ack).
            with patch.object(inbox, "INBOX_DIR", ind), patch.object(
                inbox, "INBOX_STATE_DIR", state
            ), patch.object(
                inbox, "INBOX_MANIFEST", state / "import_manifest.jsonl"
            ), patch.object(inbox, "PILOT_DATA_ROOT", root):
                retry = inbox.scan_inbox_to_memory(apply=True, exclusion_hold=hold)
            self.assertEqual(retry.get("imported"), 1)

    def test_junction_swap_during_open_read_refused(self):
        """Exact Codex edge-probe pattern: swap after assert_file_inside, before read."""
        import pilot_fs

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ind, state, mem = self._scope(root)
            outside = root / "outside"
            outside.mkdir()
            (outside / "a.txt").write_text(
                "Fictional outside-only content escaped by a junction swap.",
                encoding="utf-8",
            )
            (ind / "a.txt").write_text(
                "Fictional inside-only document before swap.", encoding="utf-8"
            )
            hold = MagicMock()
            original = pilot_fs.assert_file_inside_inbox

            def swap(path, base):
                v = original(path, base)
                if path.name == "a.txt" and (root / "inbox").exists() and not (
                    root / "original-inbox"
                ).exists():
                    (root / "inbox").rename(root / "original-inbox")
                    cp = subprocess.run(
                        ["cmd", "/c", "mklink", "/J", str(root / "inbox"), str(outside)],
                        capture_output=True,
                        text=True,
                    )
                    if cp.returncode != 0:
                        self.skipTest(cp.stdout + cp.stderr)
                return v

            with patch.object(inbox, "INBOX_DIR", ind), patch.object(
                inbox, "INBOX_STATE_DIR", state
            ), patch.object(
                inbox, "INBOX_MANIFEST", state / "import_manifest.jsonl"
            ), patch.object(inbox, "PILOT_DATA_ROOT", root), patch.object(
                pilot_fs, "assert_file_inside_inbox", side_effect=swap
            ):
                report = inbox.scan_inbox_to_memory(apply=True, exclusion_hold=hold)
            self.assertEqual(report.get("imported", 1), 0)
            store = json.loads(mem.read_text(encoding="utf-8"))
            self.assertFalse(
                any("outside-only" in str(m.get("thought", "")) for m in store)
            )

    def test_import_lock_serializes(self):
        with tempfile.TemporaryDirectory() as td:
            lock_path = Path(td) / "import.lock"
            a = ImportFileLock(lock_path)
            b = ImportFileLock(lock_path)
            ok_a, _ = a.acquire(blocking=True)
            self.assertTrue(ok_a)
            ok_b, reason = b.acquire(blocking=False)
            self.assertFalse(ok_b)
            a.release()
            ok_b2, _ = b.acquire(blocking=True)
            self.assertTrue(ok_b2)
            b.release()

    def test_malformed_utf8_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ind, state, mem = self._scope(root)
            (ind / "bad.txt").write_bytes(
                b"Fictional invalid UTF8 sequence " + b"\xff\xfe\x80" + b" stored as data."
            )
            hold = MagicMock()
            with patch.object(inbox, "INBOX_DIR", ind), patch.object(
                inbox, "INBOX_STATE_DIR", state
            ), patch.object(
                inbox, "INBOX_MANIFEST", state / "import_manifest.jsonl"
            ), patch.object(inbox, "PILOT_DATA_ROOT", root):
                report = inbox.scan_inbox_to_memory(apply=True, exclusion_hold=hold)
            self.assertEqual(report["imported"], 0)
            self.assertTrue(
                any(r.get("filename") == "bad.txt" and r.get("status") != "imported" for r in report["results"])
            )


if __name__ == "__main__":
    unittest.main()
