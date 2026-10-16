"""Exact-source, temp-only regressions for Guardian objective/task durability.
Loads only the named modules under a test-only package alias: does not initialize GuardianCore.
"""
from __future__ import annotations
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, rel: str):
    full = "isolated_continuity_store_tests." + name
    spec = importlib.util.spec_from_file_location(full, ROOT / rel)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load source: " + rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


class ContinuityStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        package = types.ModuleType("isolated_continuity_store_tests")
        package.__path__ = [str(ROOT / "project_guardian")]
        sys.modules[package.__name__] = package
        stub = types.ModuleType(package.__name__ + ".self_task_execution_outcome")
        stub.is_execution_stage_archetype = lambda _archetype: False
        sys.modules[stub.__name__] = stub
        cls.objective_module = load_module("self_task_objectives", "project_guardian/self_task_objectives.py")
        cls.queue_module = load_module("self_task_queue", "project_guardian/self_task_queue.py")
        cls.ObjectiveStore = cls.objective_module.ObjectiveStore
        cls.SelfTaskQueue = cls.queue_module.SelfTaskQueue

    def test_normal_roundtrip_survives_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            objpath = root / "objective.json"
            qpath = root / "queue.json"
            objectives = self.ObjectiveStore(storage_path=objpath)
            oid = objectives.create_lightweight(title="Fictional inspection", goal="Check synthetic notes")
            self.assertEqual(self.ObjectiveStore(storage_path=objpath).get(oid)["goal"], "Check synthetic notes")
            q = self.SelfTaskQueue(storage_path=qpath)
            self.assertTrue(q.enqueue({"task_id": "fictional-1", "title": "Fictional work"}, dedupe_key="fictional-1", cooldown_sec=0))
            self.assertEqual(self.SelfTaskQueue(storage_path=qpath).get_by_id("fictional-1")["status"], "pending")
            self.assertIsNotNone(q.claim("fictional-1"))
            self.assertEqual(self.SelfTaskQueue(storage_path=qpath).get_by_id("fictional-1")["status"], "in_progress")

    def test_corrupt_objectives_refused_without_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "objectives.json"
            corrupt = b'{"objectives":['
            path.write_bytes(corrupt)
            with self.assertRaises(RuntimeError):
                self.ObjectiveStore(storage_path=path)
            self.assertEqual(path.read_bytes(), corrupt)

    def test_corrupt_task_queue_refused_without_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tasks.json"
            corrupt = b'{"tasks":['
            path.write_bytes(corrupt)
            with self.assertRaises(RuntimeError):
                self.SelfTaskQueue(storage_path=path)
            self.assertEqual(path.read_bytes(), corrupt)

    def test_failed_claim_publication_does_not_admit_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tasks.json"
            q = self.SelfTaskQueue(storage_path=path)
            q.enqueue({"task_id": "fictional-2", "title": "Mock task"}, dedupe_key="fictional-2", cooldown_sec=0)
            before = path.read_bytes()
            with mock.patch.object(self.queue_module.os, "replace", side_effect=OSError("injected fail")):
                with self.assertRaises(OSError):
                    q.claim("fictional-2")
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(q.get_by_id("fictional-2")["status"], "pending")
            self.assertEqual(self.SelfTaskQueue(storage_path=path).get_by_id("fictional-2")["status"], "pending")
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_failed_objective_publication_retains_previous_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "objectives.json"
            q = self.ObjectiveStore(storage_path=path)
            q.create_lightweight(title="Existing fictional goal", goal="Keep it")
            before = path.read_bytes()
            with mock.patch.object(self.objective_module.os, "replace", side_effect=OSError("injected fail")):
                with self.assertRaises(OSError):
                    q.create_lightweight(title="New fictional goal", goal="May not save")
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(len(self.ObjectiveStore(storage_path=path).list_all()), 1)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])
