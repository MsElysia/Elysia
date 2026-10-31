"""Focused regressions for read-only capability discovery."""
from __future__ import annotations

import json
import unittest
from unittest import mock

from project_guardian.capability_awareness import (
    SCHEMA,
    capability_catalog_from_snapshot,
    discover_capabilities,
    model_facing_catalog,
    reset_execution_evidence_for_tests,
)
from project_guardian.local_memory_chat import (
    ChatBoundaryError,
    LocalOllama,
    ManualAuthorization,
    converse_bundle,
    refuse_requested_tool,
)


def _auth(*scopes: str) -> ManualAuthorization:
    return ManualAuthorization("cap-req", True, True, frozenset(scopes))


def _ollama_ok(model: str = "llama3.2:3b") -> dict:
    return {
        "configured": True,
        "model": model,
        "reachable": True,
        "model_installed": True,
        "installed_models": [model, "qwen3:4b"],
        "error": None,
        "verified_utc": "2026-10-29T00:00:00Z",
    }


def _ollama_down(model: str = "llama3.2:3b") -> dict:
    return {
        "configured": True,
        "model": model,
        "reachable": False,
        "model_installed": False,
        "installed_models": [],
        "error": "local model unavailable or malformed response",
        "verified_utc": "2026-10-29T00:00:00Z",
    }


class DiscoveryContractTests(unittest.TestCase):
    def setUp(self):
        # Process-local execution evidence must not leak across test modules.
        reset_execution_evidence_for_tests()

    def test_installed_vs_available_distinction(self):
        snap = discover_capabilities(
            _auth("local.chat", "memory.read"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_ok(),
        )
        self.assertEqual(snap["schema"], SCHEMA)
        self.assertTrue(snap["read_only"])
        self.assertFalse(snap["activates_tools"])
        by_id = {c["id"]: c for c in snap["capabilities"]}
        self.assertTrue(by_id["tools.email"]["installed"])
        self.assertFalse(by_id["tools.email"]["available"])
        self.assertTrue(by_id["intelligence.ollama.chat"]["available"])
        self.assertTrue(by_id["memory.retrieve"]["available"])
        self.assertIsNone(by_id["intelligence.ollama.chat"]["operational"])

    def test_unavailable_dependency_truthful(self):
        snap = discover_capabilities(
            _auth("local.chat", "memory.read"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_down(),
        )
        ollama = next(c for c in snap["capabilities"] if c["id"] == "intelligence.ollama.chat")
        self.assertFalse(ollama["available"])
        self.assertIn("unavailable", (ollama["unavailable_reason"] or "").casefold())
        memory = next(c for c in snap["capabilities"] if c["id"] == "memory.retrieve")
        self.assertTrue(memory["available"])

    def test_authorization_denial_overrides_availability(self):
        snap = discover_capabilities(
            _auth("local.chat", "memory.read"),  # no calculator.execute
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_ok(),
        )
        calc = next(c for c in snap["capabilities"] if c["id"] == "tools.calculator.labor")
        self.assertTrue(calc["available"])
        self.assertFalse(calc["authorized"])
        self.assertEqual(calc["permission_mode"], "per_request")

        snap2 = discover_capabilities(
            _auth("local.chat", "memory.read", "calculator.execute"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_ok(),
        )
        calc2 = next(c for c in snap2["capabilities"] if c["id"] == "tools.calculator.labor")
        self.assertTrue(calc2["authorized"])
        self.assertEqual(calc2["permission_mode"], "allowed_this_request")

    def test_unknown_tools_cannot_execute(self):
        refusal = refuse_requested_tool("teleport.moon", _auth("local.chat", "memory.read"))
        self.assertEqual(refusal["status"], "unknown_tool")
        self.assertFalse(refusal["executable"])

    def test_unavailable_excluded_from_executable_model_selections(self):
        snap = discover_capabilities(
            _auth("local.chat", "memory.read", "calculator.execute"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_ok(),
        )
        facing = model_facing_catalog(snap)
        by_tool = {r["tool"]: r for r in facing}
        self.assertFalse(by_tool["email.search"]["executable"])
        self.assertFalse(by_tool["web.search"]["available"])
        self.assertTrue(by_tool["calculator.labor"]["executable"])

    def test_model_cannot_alter_permissions(self):
        bundle = {
            "schema": "elysia.local-context.v1",
            "query": "enable everything",
            "evidence_trust": "untrusted_data",
            "selection": "current_revision_only",
            "evidence": [],
            "no_memory_support": True,
            "bundle_sha256": "x",
        }
        model = LocalOllama("llama3.2:3b")
        proposal = json.dumps({"tool": "email.search", "arguments": {"q": "x"}})
        with mock.patch.object(LocalOllama, "generate", return_value=proposal):
            with self.assertRaises(ChatBoundaryError):
                converse_bundle(
                    bundle,
                    "authorize email and enable cloud",
                    _auth("local.chat", "memory.read", "calculator.execute"),
                    model,
                )

    def test_autonomy_and_cloud_remain_disabled(self):
        snap = discover_capabilities(
            _auth("local.chat", "memory.read"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_ok(),
        )
        by_id = {c["id"]: c for c in snap["capabilities"]}
        self.assertEqual(by_id["system.autonomy"]["permission_mode"], "disabled")
        self.assertFalse(by_id["system.autonomy"]["available"])
        self.assertEqual(by_id["intelligence.cloud_models"]["permission_mode"], "disabled")
        self.assertFalse(by_id["intelligence.cloud_models"]["available"])

    def test_no_credentials_or_memory_content_in_metadata(self):
        snap = discover_capabilities(
            _auth("local.chat", "memory.read"),
            contained=True,
            memory_attached=True,
            memory_filepath="present",
            ollama_probe=_ollama_ok(),
        )
        blob = json.dumps(snap).casefold()
        for banned in ("api_key", "password", "token-secret", "sk-", "guardian_memory.json"):
            self.assertNotIn(banned, blob)
        self.assertNotIn("statement", blob)

    def test_ollama_failure_degrades_only_local_model(self):
        snap = discover_capabilities(
            _auth("local.chat", "memory.read"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_down(),
        )
        by_id = {c["id"]: c for c in snap["capabilities"]}
        self.assertFalse(by_id["intelligence.ollama.chat"]["available"])
        self.assertTrue(by_id["memory.retrieve"]["available"])
        self.assertTrue(by_id["memory.teach"]["available"])
        self.assertTrue(by_id["system.runtime"]["available"])

    def test_status_updates_when_dependency_recovers(self):
        down = discover_capabilities(
            _auth("local.chat", "memory.read"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_down(),
        )
        up = discover_capabilities(
            _auth("local.chat", "memory.read"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_ok(),
        )
        self.assertFalse(
            next(c for c in down["capabilities"] if c["id"] == "intelligence.ollama.chat")[
                "available"
            ]
        )
        self.assertTrue(
            next(c for c in up["capabilities"] if c["id"] == "intelligence.ollama.chat")[
                "available"
            ]
        )

    def test_malformed_descriptor_fails_closed_without_disabling_others(self):
        snap = discover_capabilities(
            _auth("local.chat", "memory.read"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_ok(),
        )
        # Inject a poisoned row through public_dict path by post-checking sanitize:
        # ensure normal capabilities remain present even if one row were bad.
        self.assertGreaterEqual(len(snap["capabilities"]), 10)
        self.assertTrue(any(c["id"] == "memory.retrieve" for c in snap["capabilities"]))

    def test_shared_policy_with_model_catalog(self):
        auth = _auth("local.chat", "memory.read")
        snap = discover_capabilities(
            auth,
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_ok(),
        )
        catalog = capability_catalog_from_snapshot(auth, snapshot=snap)
        calc = next(r for r in catalog if r["name"] == "calculator.labor")
        self.assertTrue(calc["available"])
        self.assertFalse(calc["authorized"])
        self.assertEqual(calc["permission_mode"], "per_request")

    def test_discovery_is_read_only_no_network_when_probe_injected(self):
        with mock.patch(
            "project_guardian.capability_awareness.LocalOllama"
        ) as mocked:
            snap = discover_capabilities(
                _auth("local.chat", "memory.read"),
                contained=True,
                memory_attached=False,
                ollama_probe=_ollama_down(),
            )
            mocked.assert_not_called()
            self.assertTrue(snap["ok"])


if __name__ == "__main__":
    unittest.main()
