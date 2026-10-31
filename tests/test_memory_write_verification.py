"""Teach/correct operational status requires durable readback verification."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from project_guardian.capability_awareness import (
    discover_capabilities,
    get_execution_evidence_store,
    reset_execution_evidence_for_tests,
)
from project_guardian.local_memory_chat import ManualAuthorization
from project_guardian.restricted_runtime_adapter import (
    OPERATOR_FACT_PERMISSIONS,
    LocalPrincipal,
    RestrictedRuntimeAdapter,
)


def _auth() -> ManualAuthorization:
    return ManualAuthorization("mw", True, True, frozenset({"local.chat", "memory.read"}))


def _adapter(path: Path) -> RestrictedRuntimeAdapter:
    return RestrictedRuntimeAdapter(
        principals=[
            LocalPrincipal("dashboard-operator", "token-secret", OPERATOR_FACT_PERMISSIONS)
        ],
        memory_filepath=str(path),
    )


def _headers() -> dict:
    return {"X-Elysia-Identity": "dashboard-operator", "X-Elysia-Token": "token-secret"}


def _ollama_ok() -> dict:
    return {
        "configured": True,
        "model": "llama3.2:3b",
        "reachable": True,
        "model_installed": True,
        "installed_models": ["llama3.2:3b"],
        "error": None,
        "verified_utc": "2026-10-29T00:00:00Z",
    }


class MemoryWriteVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_execution_evidence_for_tests()

    def tearDown(self) -> None:
        reset_execution_evidence_for_tests()

    def test_teach_verifies_only_after_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = Path(tmp) / "guardian_memory.json"
            mem.write_text("[]", encoding="utf-8")
            adapter = _adapter(mem)
            before = discover_capabilities(
                _auth(), contained=True, memory_attached=True, ollama_probe=_ollama_ok()
            )
            teach_before = next(c for c in before["capabilities"] if c["id"] == "memory.teach")
            self.assertIsNone(teach_before["operational"])

            saved = adapter.handle(
                "POST",
                "/api/restricted/v1/facts",
                headers=_headers(),
                body={"statement": "The fictional crystal owl nests near violet pines."},
            )
            self.assertEqual(saved.status, 201)
            self.assertTrue(saved.body.get("persistence_verified"))
            fact = saved.body["fact"]
            # Authoritative readback via current facts / history.
            history = adapter.handle(
                "GET",
                f"/api/restricted/v1/facts/{fact['fact_id']}/history",
                headers=_headers(),
            )
            self.assertEqual(history.status, 200)
            self.assertEqual(history.body["revisions"][0]["statement"], fact["statement"])
            self.assertEqual(history.body["revisions"][0]["revision"], 1)

            after = discover_capabilities(
                _auth(), contained=True, memory_attached=True, ollama_probe=_ollama_ok()
            )
            teach = next(c for c in after["capabilities"] if c["id"] == "memory.teach")
            self.assertTrue(teach["operational"])
            self.assertEqual(teach["runtime_status"], "verified_operational")
            # Evidence never grants write authorization scopes.
            self.assertTrue(teach["available"])

    def test_correct_verifies_current_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = Path(tmp) / "guardian_memory.json"
            mem.write_text("[]", encoding="utf-8")
            adapter = _adapter(mem)
            saved = adapter.handle(
                "POST",
                "/api/restricted/v1/facts",
                headers=_headers(),
                body={"statement": "The fictional river Zyphora is violet."},
            )
            fact_id = saved.body["fact"]["fact_id"]
            corrected = adapter.handle(
                "POST",
                f"/api/restricted/v1/facts/{fact_id}/corrections",
                headers=_headers(),
                body={"statement": "The fictional river Zyphora is indigo."},
            )
            self.assertEqual(corrected.status, 200)
            self.assertTrue(corrected.body.get("persistence_verified"))
            self.assertEqual(corrected.body["fact"]["revision"], 2)
            history = adapter.handle(
                "GET",
                f"/api/restricted/v1/facts/{fact_id}/history",
                headers=_headers(),
            )
            revs = history.body["revisions"]
            self.assertEqual(len(revs), 2)
            self.assertEqual(revs[0]["statement"], "The fictional river Zyphora is violet.")
            self.assertTrue(revs[1]["current"])
            self.assertEqual(revs[1]["statement"], "The fictional river Zyphora is indigo.")
            snap = discover_capabilities(
                _auth(), contained=True, memory_attached=True, ollama_probe=_ollama_ok()
            )
            correct = next(c for c in snap["capabilities"] if c["id"] == "memory.correct")
            self.assertEqual(correct["runtime_status"], "verified_operational")

    def test_failed_primary_write_not_operational(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = Path(tmp) / "guardian_memory.json"
            mem.write_text("[]", encoding="utf-8")
            adapter = _adapter(mem)

            def _no_persist(**kwargs):
                return {
                    "fact_id": kwargs["fact_id"],
                    "revision": kwargs["revision"],
                    "statement": kwargs["statement"],
                    "operation": kwargs["operation"],
                    "actor": kwargs["actor"],
                    "previous_statement": kwargs["previous_statement"],
                }

            with mock.patch.object(adapter, "_append_event", side_effect=_no_persist):
                result = adapter.handle(
                    "POST",
                    "/api/restricted/v1/facts",
                    headers=_headers(),
                    body={"statement": "The fictional marble fox never persists."},
                )
            self.assertEqual(result.status, 500)
            self.assertEqual(result.body.get("error"), "persistence_unverified")
            snap = discover_capabilities(
                _auth(), contained=True, memory_attached=True, ollama_probe=_ollama_ok()
            )
            teach = next(c for c in snap["capabilities"] if c["id"] == "memory.teach")
            self.assertNotEqual(teach["runtime_status"], "verified_operational")
            self.assertIs(teach["operational"], False)
            # No durable fact committed.
            history_probe = adapter.handle(
                "GET",
                "/api/restricted/v1/facts/fact_aaaaaaaaaaaaaaaa/history",
                headers=_headers(),
            )
            self.assertEqual(history_probe.status, 404)

    def test_failed_correction_preserves_prior(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = Path(tmp) / "guardian_memory.json"
            mem.write_text("[]", encoding="utf-8")
            adapter = _adapter(mem)
            saved = adapter.handle(
                "POST",
                "/api/restricted/v1/facts",
                headers=_headers(),
                body={"statement": "The fictional lantern burns cold blue."},
            )
            fact_id = saved.body["fact"]["fact_id"]
            prior = saved.body["fact"]["statement"]

            def _no_persist(**kwargs):
                return {
                    "fact_id": kwargs["fact_id"],
                    "revision": kwargs["revision"],
                    "statement": kwargs["statement"],
                    "operation": kwargs["operation"],
                    "actor": kwargs["actor"],
                    "previous_statement": kwargs["previous_statement"],
                }

            with mock.patch.object(adapter, "_append_event", side_effect=_no_persist):
                failed = adapter.handle(
                    "POST",
                    f"/api/restricted/v1/facts/{fact_id}/corrections",
                    headers=_headers(),
                    body={"statement": "The fictional lantern burns warm gold."},
                )
            self.assertEqual(failed.status, 500)
            history = adapter.handle(
                "GET",
                f"/api/restricted/v1/facts/{fact_id}/history",
                headers=_headers(),
            )
            self.assertEqual(len(history.body["revisions"]), 1)
            self.assertEqual(history.body["revisions"][0]["statement"], prior)
            self.assertTrue(history.body["revisions"][0]["current"])
            snap = discover_capabilities(
                _auth(), contained=True, memory_attached=True, ollama_probe=_ollama_ok()
            )
            correct = next(c for c in snap["capabilities"] if c["id"] == "memory.correct")
            self.assertNotEqual(correct["runtime_status"], "verified_operational")

    def test_restart_clears_evidence_keeps_durable_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = Path(tmp) / "guardian_memory.json"
            mem.write_text("[]", encoding="utf-8")
            adapter = _adapter(mem)
            saved = adapter.handle(
                "POST",
                "/api/restricted/v1/facts",
                headers=_headers(),
                body={"statement": "The fictional copper bee hums at dawn."},
            )
            fact_id = saved.body["fact"]["fact_id"]
            self.assertTrue(get_execution_evidence_store().get("memory.teach").success)
            reset_execution_evidence_for_tests()
            self.assertIsNone(get_execution_evidence_store().get("memory.teach"))
            # Same durable store still has the fact.
            adapter2 = _adapter(mem)
            history = adapter2.handle(
                "GET",
                f"/api/restricted/v1/facts/{fact_id}/history",
                headers=_headers(),
            )
            self.assertEqual(history.status, 200)
            self.assertEqual(len(history.body["revisions"]), 1)
            snap = discover_capabilities(
                _auth(), contained=True, memory_attached=True, ollama_probe=_ollama_ok()
            )
            teach = next(c for c in snap["capabilities"] if c["id"] == "memory.teach")
            self.assertIsNone(teach["operational"])

    def test_malformed_request_not_operational(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = Path(tmp) / "guardian_memory.json"
            mem.write_text("[]", encoding="utf-8")
            adapter = _adapter(mem)
            bad = adapter.handle(
                "POST",
                "/api/restricted/v1/facts",
                headers=_headers(),
                body={"statement": "short"},
            )
            self.assertEqual(bad.status, 400)
            self.assertIsNone(get_execution_evidence_store().get("memory.teach"))
            snap = discover_capabilities(
                _auth(), contained=True, memory_attached=True, ollama_probe=_ollama_ok()
            )
            teach = next(c for c in snap["capabilities"] if c["id"] == "memory.teach")
            self.assertIsNone(teach["operational"])

    def test_evidence_does_not_grant_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = Path(tmp) / "guardian_memory.json"
            mem.write_text("[]", encoding="utf-8")
            adapter = _adapter(mem)
            adapter.handle(
                "POST",
                "/api/restricted/v1/facts",
                headers=_headers(),
                body={"statement": "The fictional silver moss glows softly."},
            )
            # Snapshot without write scopes still shows teach available via memory_attached,
            # but ManualAuthorization scopes are separate from restricted principal perms.
            snap = discover_capabilities(
                ManualAuthorization("x", True, True, frozenset()),
                contained=True,
                memory_attached=True,
                ollama_probe=_ollama_ok(),
            )
            teach = next(c for c in snap["capabilities"] if c["id"] == "memory.teach")
            self.assertEqual(teach["runtime_status"], "verified_operational")
            # Discovery still does not activate tools / change gates.
            self.assertTrue(snap["read_only"])
            self.assertFalse(snap["activates_tools"])

    def test_unrelated_capabilities_remain(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = Path(tmp) / "guardian_memory.json"
            mem.write_text("[]", encoding="utf-8")
            adapter = _adapter(mem)
            with mock.patch.object(
                adapter,
                "_append_event",
                side_effect=lambda **kwargs: {
                    "fact_id": kwargs["fact_id"],
                    "revision": kwargs["revision"],
                    "statement": kwargs["statement"],
                    "operation": kwargs["operation"],
                    "actor": kwargs["actor"],
                    "previous_statement": kwargs["previous_statement"],
                },
            ):
                adapter.handle(
                    "POST",
                    "/api/restricted/v1/facts",
                    headers=_headers(),
                    body={"statement": "The fictional quartz kite never lands."},
                )
            snap = discover_capabilities(
                _auth(), contained=True, memory_attached=True, ollama_probe=_ollama_ok()
            )
            by_id = {c["id"]: c for c in snap["capabilities"]}
            self.assertTrue(by_id["memory.retrieve"]["available"])
            self.assertTrue(by_id["intelligence.ollama.chat"]["available"])
            self.assertNotEqual(by_id["memory.teach"]["runtime_status"], "verified_operational")


if __name__ == "__main__":
    unittest.main()
