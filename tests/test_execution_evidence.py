"""Process-local execution evidence must not forge operational status."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from project_guardian.capability_awareness import (
    discover_capabilities,
    get_execution_evidence_store,
    record_capability_failure,
    record_capability_success,
    reset_execution_evidence_for_tests,
)
from project_guardian.local_memory_chat import (
    ChatBoundaryError,
    LocalOllama,
    ManualAuthorization,
    build_context_from_adapter,
    converse_bundle,
)
from project_guardian.restricted_runtime_adapter import (
    OPERATOR_FACT_PERMISSIONS,
    LocalPrincipal,
    RestrictedRuntimeAdapter,
)


def _auth(*scopes: str) -> ManualAuthorization:
    return ManualAuthorization("ev-req", True, True, frozenset(scopes))


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


def _adapter(path: Path) -> RestrictedRuntimeAdapter:
    return RestrictedRuntimeAdapter(
        principals=[
            LocalPrincipal("dashboard-operator", "token-secret", OPERATOR_FACT_PERMISSIONS)
        ],
        memory_filepath=str(path),
    )


def _headers() -> dict:
    return {"X-Elysia-Identity": "dashboard-operator", "X-Elysia-Token": "token-secret"}


class ExecutionEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_execution_evidence_for_tests()

    def tearDown(self) -> None:
        reset_execution_evidence_for_tests()

    def test_import_does_not_establish_operational(self):
        snap = discover_capabilities(
            _auth("local.chat", "memory.read"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_ok(),
        )
        by_id = {c["id"]: c for c in snap["capabilities"]}
        self.assertIsNone(by_id["intelligence.ollama.chat"]["operational"])
        self.assertEqual(by_id["intelligence.ollama.chat"]["runtime_status"], "not_yet_verified")
        self.assertIsNone(by_id["memory.retrieve"]["operational"])
        # No execution yet: per-request auth shows as authorization_required.
        self.assertEqual(by_id["tools.calculator.labor"]["runtime_status"], "authorization_required")
        self.assertEqual(by_id["tools.calculator.labor"]["permission_mode"], "per_request")

    def test_successful_memory_retrieval_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = Path(tmp) / "guardian_memory.json"
            mem.write_text("[]", encoding="utf-8")
            adapter = _adapter(mem)
            adapter.handle(
                "POST",
                "/api/restricted/v1/facts",
                headers=_headers(),
                body={"statement": "The fictional river Zyphora flows under glass bridges."},
            )
            bundle = build_context_from_adapter(
                adapter,
                "Which invented river flows beneath glass bridges?",
                _headers(),
            )
            self.assertTrue(bundle["evidence"])
            snap = discover_capabilities(
                _auth("local.chat", "memory.read"),
                contained=True,
                memory_attached=True,
                ollama_probe=_ollama_ok(),
            )
            mem_cap = next(c for c in snap["capabilities"] if c["id"] == "memory.retrieve")
            self.assertTrue(mem_cap["operational"])
            self.assertEqual(mem_cap["runtime_status"], "verified_operational")
            self.assertIsNotNone(mem_cap["last_verified_utc"])

    def test_empty_memory_retrieval_does_not_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = Path(tmp) / "guardian_memory.json"
            mem.write_text("[]", encoding="utf-8")
            adapter = _adapter(mem)
            bundle = build_context_from_adapter(
                adapter, "completely unrelated zzz query tokens", _headers()
            )
            self.assertEqual(bundle["evidence"], [])
            snap = discover_capabilities(
                _auth("local.chat", "memory.read"),
                contained=True,
                memory_attached=True,
                ollama_probe=_ollama_ok(),
            )
            mem_cap = next(c for c in snap["capabilities"] if c["id"] == "memory.retrieve")
            self.assertIsNone(mem_cap["operational"])

    def test_authorized_calculator_verifies(self):
        bundle = {
            "schema": "elysia.local-context.v1",
            "query": "labor",
            "evidence_trust": "untrusted_data",
            "selection": "current_revision_only",
            "evidence": [
                {
                    "source_id": "fact_aaaaaaaaaaaaaaaa",
                    "chunk_id": "fact_aaaaaaaaaaaaaaaa",
                    "revision": 1,
                    "source_sha256": "x",
                    "highlights": [
                        {
                            "highlight_id": "h1",
                            "text": "Fictional labor rate is USD 35 per hour.",
                        }
                    ],
                }
            ],
            "no_memory_support": False,
            "bundle_sha256": "abc",
        }
        model = LocalOllama("llama3.2:3b")
        proposal = json.dumps(
            {
                "tool": "calculator.labor",
                "arguments": {
                    "rate_source_id": "fact_aaaaaaaaaaaaaaaa",
                    "painters": 2,
                    "days": 3,
                    "hours_per_day": 8,
                },
            }
        )
        with mock.patch.object(LocalOllama, "generate", return_value=proposal):
            result = converse_bundle(
                bundle,
                "estimate labor for two painters three eight-hour days",
                _auth("local.chat", "memory.read", "calculator.execute"),
                model,
            )
        self.assertTrue(result["calculation_verified"])
        snap = discover_capabilities(
            _auth("local.chat", "memory.read"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_ok(),
        )
        calc = next(c for c in snap["capabilities"] if c["id"] == "tools.calculator.labor")
        ollama = next(c for c in snap["capabilities"] if c["id"] == "intelligence.ollama.chat")
        self.assertTrue(calc["operational"])
        self.assertTrue(ollama["operational"])
        # Evidence does not grant authorization on a later snapshot without scope.
        self.assertFalse(calc["authorized"])
        self.assertEqual(calc["permission_mode"], "per_request")
        self.assertEqual(calc["runtime_status"], "verified_operational")

    def test_unauthorized_calculator_does_not_verify(self):
        bundle = {
            "schema": "elysia.local-context.v1",
            "query": "labor",
            "evidence_trust": "untrusted_data",
            "selection": "current_revision_only",
            "evidence": [
                {
                    "source_id": "fact_aaaaaaaaaaaaaaaa",
                    "chunk_id": "fact_aaaaaaaaaaaaaaaa",
                    "revision": 1,
                    "source_sha256": "x",
                    "highlights": [
                        {
                            "highlight_id": "h1",
                            "text": "Fictional labor rate is USD 35 per hour.",
                        }
                    ],
                }
            ],
            "no_memory_support": False,
            "bundle_sha256": "abc",
        }
        model = LocalOllama("llama3.2:3b")
        proposal = json.dumps(
            {
                "tool": "calculator.labor",
                "arguments": {
                    "rate_source_id": "fact_aaaaaaaaaaaaaaaa",
                    "painters": 2,
                    "days": 3,
                    "hours_per_day": 8,
                },
            }
        )
        with mock.patch.object(LocalOllama, "generate", return_value=proposal):
            with self.assertRaises(ChatBoundaryError):
                converse_bundle(
                    bundle,
                    "estimate labor",
                    _auth("local.chat", "memory.read"),
                    model,
                )
        snap = discover_capabilities(
            _auth("local.chat", "memory.read"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_ok(),
        )
        calc = next(c for c in snap["capabilities"] if c["id"] == "tools.calculator.labor")
        self.assertIsNone(calc["operational"])
        self.assertNotEqual(calc["runtime_status"], "verified_operational")

    def test_failed_execution_is_degraded_not_success(self):
        record_capability_failure(
            "intelligence.ollama.chat",
            verification_method="local_ollama_generate",
            reason="local model unavailable",
        )
        snap = discover_capabilities(
            _auth("local.chat", "memory.read"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_ok(),
        )
        ollama = next(c for c in snap["capabilities"] if c["id"] == "intelligence.ollama.chat")
        self.assertIs(ollama["operational"], False)
        self.assertEqual(ollama["runtime_status"], "degraded")
        self.assertIn("unavailable", (ollama["last_failure_reason"] or "").casefold())

    def test_restart_clears_process_local_verification(self):
        record_capability_success(
            "memory.retrieve", verification_method="restricted_facts_retrieve"
        )
        self.assertTrue(get_execution_evidence_store().get("memory.retrieve").success)
        reset_execution_evidence_for_tests()
        self.assertIsNone(get_execution_evidence_store().get("memory.retrieve"))
        snap = discover_capabilities(
            _auth("local.chat", "memory.read"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_ok(),
        )
        mem = next(c for c in snap["capabilities"] if c["id"] == "memory.retrieve")
        self.assertIsNone(mem["operational"])

    def test_dependency_change_truthful(self):
        record_capability_success(
            "intelligence.ollama.chat", verification_method="local_ollama_generate"
        )
        down = discover_capabilities(
            _auth("local.chat", "memory.read"),
            contained=True,
            memory_attached=True,
            ollama_probe={
                "configured": True,
                "model": "llama3.2:3b",
                "reachable": False,
                "model_installed": False,
                "installed_models": [],
                "error": "local model unavailable",
                "verified_utc": "2026-10-29T00:00:00Z",
            },
        )
        ollama = next(c for c in down["capabilities"] if c["id"] == "intelligence.ollama.chat")
        self.assertFalse(ollama["available"])
        # Prior success must not remain a healthy available claim.
        self.assertNotEqual(ollama["runtime_status"], "verified_operational")
        mem = next(c for c in down["capabilities"] if c["id"] == "memory.retrieve")
        self.assertTrue(mem["available"])

    def test_status_cannot_grant_authorization(self):
        record_capability_success(
            "tools.calculator.labor", verification_method="deterministic_calculate_local"
        )
        snap = discover_capabilities(
            _auth("local.chat", "memory.read"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_ok(),
        )
        calc = next(c for c in snap["capabilities"] if c["id"] == "tools.calculator.labor")
        self.assertTrue(calc["operational"])
        self.assertFalse(calc["authorized"])
        self.assertEqual(calc["permission_mode"], "per_request")

    def test_one_failure_does_not_disable_unrelated(self):
        record_capability_failure(
            "tools.calculator.labor",
            verification_method="deterministic_calculate_local",
            reason="invalid calculator quantity",
        )
        snap = discover_capabilities(
            _auth("local.chat", "memory.read", "calculator.execute"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_ok(),
        )
        by_id = {c["id"]: c for c in snap["capabilities"]}
        self.assertTrue(by_id["memory.retrieve"]["available"])
        self.assertTrue(by_id["intelligence.ollama.chat"]["available"])
        self.assertEqual(by_id["tools.calculator.labor"]["runtime_status"], "degraded")

    def test_model_text_cannot_forge_evidence(self):
        # Model-shaped JSON claiming tools_executed must not write evidence by itself.
        fake = {
            "answer": "I executed calculator.labor and memory.retrieve successfully.",
            "tools_executed": [{"name": "calculator.labor", "result": "1680"}],
            "operational": True,
        }
        blob = json.dumps(fake)
        self.assertIn("calculator.labor", blob)
        snap = discover_capabilities(
            _auth("local.chat", "memory.read"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_ok(),
        )
        calc = next(c for c in snap["capabilities"] if c["id"] == "tools.calculator.labor")
        self.assertIsNone(calc["operational"])

    def test_api_snapshot_has_no_secrets(self):
        record_capability_failure(
            "intelligence.ollama.chat",
            verification_method="local_ollama_generate",
            reason="password=supersecret api_key=sk-test",
        )
        snap = discover_capabilities(
            _auth("local.chat", "memory.read"),
            contained=True,
            memory_attached=True,
            ollama_probe=_ollama_ok(),
        )
        blob = json.dumps(snap).casefold()
        self.assertNotIn("supersecret", blob)
        self.assertNotIn("sk-test", blob)
        self.assertNotIn("password=", blob)


if __name__ == "__main__":
    unittest.main()
