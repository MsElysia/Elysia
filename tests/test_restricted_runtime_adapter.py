# Deterministic tests for the restricted-runtime local API adapter.
# No browser, no network, no model providers. Restart is a new MemoryCore
# on the same filepath.

import json
import sys
import types
from pathlib import Path

# Import MemoryCore without executing project_guardian/__init__.py when that
# package init cannot load (it pulls GuardianCore and provider clients).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _ensure_guardian_submodules():
    if "project_guardian.memory" in sys.modules and "project_guardian" in sys.modules:
        return
    try:
        import project_guardian.memory  # noqa: F401
        return
    except ModuleNotFoundError:
        pass
    if "project_guardian" not in sys.modules:
        package = types.ModuleType("project_guardian")
        package.__path__ = [str(_ROOT / "project_guardian")]
        package.__package__ = "project_guardian"
        sys.modules["project_guardian"] = package


_ensure_guardian_submodules()

from project_guardian.memory import MemoryCore
from project_guardian.restricted_runtime_adapter import (
    HARD_DENY_ROUTES,
    OPERATOR_FACT_PERMISSIONS,
    LocalPrincipal,
    RestrictedRuntimeAdapter,
)

OPERATOR_TOKEN = "local-test-token-not-a-provider-secret"
ORIGINAL = "The harbor city of the fictional country Veridia is Lumenport."
CORRECTED = "The harbor city of the fictional country Veridia is Glasshaven."
OTHER_WORDING = "Which harbor city is in the country Veridia?"


def _operator() -> LocalPrincipal:
    return LocalPrincipal(
        identity="dashboard-operator",
        token=OPERATOR_TOKEN,
        permissions=OPERATOR_FACT_PERMISSIONS,
    )


def _adapter(path: Path, principals=None) -> RestrictedRuntimeAdapter:
    return RestrictedRuntimeAdapter(
        principals=principals if principals is not None else [_operator()],
        memory_filepath=str(path),
    )


def _auth(identity: str = "dashboard-operator", token: str = OPERATOR_TOKEN):
    return {"X-Elysia-Identity": identity, "X-Elysia-Token": token}


def _store_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


class TestFactWorkflow:
    def test_save_retrieve_correct_history_and_reopen(self, tmp_path):
        path = tmp_path / "guardian_memory.json"
        adapter = _adapter(path)
        identity = adapter.store_identity()
        assert identity["module"] == "project_guardian.memory.MemoryCore"
        assert identity["canonical_config_key"] == "memory_filepath"
        assert identity["filepath"] == str(path.resolve())

        saved = adapter.handle(
            "POST",
            "/api/restricted/v1/facts",
            headers=_auth(),
            body={"statement": ORIGINAL},
        )
        assert saved.status == 201
        fact_id = saved.body["fact"]["fact_id"]
        assert saved.body["fact"]["statement"] == ORIGINAL
        assert saved.body["fact"]["revision"] == 1
        assert saved.body["fact"]["current"] is True
        assert saved.body["memory_store"]["filepath"] == identity["filepath"]
        assert OPERATOR_TOKEN not in _store_text(path)

        # The full question is different wording, not a substring of the fact.
        assert OTHER_WORDING.lower() not in ORIGINAL.lower()
        keyword = MemoryCore(filepath=str(path), enable_vector_search=False)
        assert keyword.search_memories(OTHER_WORDING) == []

        found = adapter.handle(
            "POST",
            "/api/restricted/v1/facts/retrieve",
            headers=_auth(),
            body={"query": OTHER_WORDING},
        )
        assert found.status == 200
        assert len(found.body["matches"]) == 1
        assert found.body["matches"][0]["fact_id"] == fact_id
        assert found.body["matches"][0]["statement"] == ORIGINAL
        assert "lumenport" in found.body["matches"][0]["matched_tokens"] or "veridia" in found.body["matches"][0]["matched_tokens"]

        corrected = adapter.handle(
            "POST",
            f"/api/restricted/v1/facts/{fact_id}/corrections",
            headers=_auth(),
            body={"statement": CORRECTED},
        )
        assert corrected.status == 200
        assert corrected.body["fact"]["revision"] == 2
        assert corrected.body["fact"]["statement"] == CORRECTED
        assert corrected.body["fact"]["previous_statement"] == ORIGINAL

        history = adapter.handle(
            "GET",
            f"/api/restricted/v1/facts/{fact_id}/history",
            headers=_auth(),
        )
        assert history.status == 200
        revisions = history.body["revisions"]
        assert [item["statement"] for item in revisions] == [ORIGINAL, CORRECTED]
        assert [item["current"] for item in revisions] == [False, True]
        assert revisions[0]["operation"] == "save"
        assert revisions[1]["operation"] == "correct"
        assert revisions[1]["actor"] == "dashboard-operator"

        # Simulated process restart: drop the adapter and reopen the same file.
        del adapter
        reopened = _adapter(path)
        assert reopened.store_identity()["filepath"] == identity["filepath"]
        again = reopened.handle(
            "POST",
            "/api/restricted/v1/facts/retrieve",
            headers=_auth(),
            body={"query": OTHER_WORDING},
        )
        assert again.status == 200
        assert len(again.body["matches"]) == 1
        assert again.body["matches"][0]["statement"] == CORRECTED
        assert again.body["matches"][0]["revision"] == 2
        assert "Lumenport" not in again.body["matches"][0]["statement"]

        reloaded = json.loads(path.read_text(encoding="utf-8"))
        fact_rows = [
            row for row in reloaded
            if isinstance(row, dict) and (row.get("metadata") or {}).get("kind") == "restricted_fact"
        ]
        assert len(fact_rows) == 2
        assert {row["category"] for row in fact_rows} == {"restricted_fact"}

    def test_reopen_uses_injected_memory_core_same_path(self, tmp_path):
        path = tmp_path / "data" / "guardian_memory.json"
        path.parent.mkdir()
        first_memory = MemoryCore(
            filepath=str(path),
            enable_vector_search=False,
            enable_timeline_logging=False,
        )
        adapter = RestrictedRuntimeAdapter(principals=[_operator()], memory=first_memory)
        saved = adapter.handle(
            "POST",
            "/api/restricted/v1/facts",
            headers=_auth(),
            body={"statement": ORIGINAL},
        )
        fact_id = saved.body["fact"]["fact_id"]
        del adapter
        del first_memory
        second = RestrictedRuntimeAdapter(
            principals=[_operator()],
            memory=MemoryCore(filepath=str(path), enable_vector_search=False),
        )
        history = second.handle(
            "GET",
            f"/api/restricted/v1/facts/{fact_id}/history",
            headers=_auth(),
        )
        assert history.status == 200
        assert history.body["revisions"][0]["statement"] == ORIGINAL


class TestRequestChecks:
    def test_invalid_statement_does_not_write(self, tmp_path):
        path = tmp_path / "guardian_memory.json"
        adapter = _adapter(path)
        response = adapter.handle(
            "POST",
            "/api/restricted/v1/facts",
            headers=_auth(),
            body={"statement": "too short"},
        )
        assert response.status == 400
        assert response.body["error"] == "invalid_request"
        assert not path.exists() or json.loads(path.read_text(encoding="utf-8")) == []

    def test_missing_permission_cannot_save(self, tmp_path):
        path = tmp_path / "guardian_memory.json"
        reader = LocalPrincipal(
            identity="dashboard-reader",
            token="reader-token",
            permissions=frozenset({"facts.retrieve", "facts.history", "runtime.inspect"}),
        )
        adapter = _adapter(path, principals=[reader])
        response = adapter.handle(
            "POST",
            "/api/restricted/v1/facts",
            headers=_auth("dashboard-reader", "reader-token"),
            body={"statement": ORIGINAL},
        )
        assert response.status == 403
        assert response.body["error"] == "forbidden"
        assert not path.exists() or json.loads(path.read_text(encoding="utf-8")) == []

    def test_unknown_fact_history(self, tmp_path):
        adapter = _adapter(tmp_path / "guardian_memory.json")
        response = adapter.handle(
            "GET",
            "/api/restricted/v1/facts/fact_0123456789abcdef/history",
            headers=_auth(),
        )
        assert response.status == 404


class TestSecurityDenials:
    def _assert_denied(self, adapter, path, headers, body, expected_status, store: Path):
        before = _store_text(store)
        response = adapter.handle("POST", path, headers=headers, body=body)
        assert response.status == expected_status
        assert response.body["ok"] is False
        assert response.body["error"] in {"unauthorized", "forbidden"}
        leaked = json.dumps(response.body)
        for secret in ("sk-live-should-not-land", "import os; os.system", "enabled"):
            if secret in (body or {}).values() or any(
                isinstance(value, str) and secret in value for value in (body or {}).values()
            ):
                assert secret not in leaked
        assert _store_text(store) == before
        return response

    def test_unauthorized_and_operator_cannot_perform_forbidden_operations(self, tmp_path):
        path = tmp_path / "guardian_memory.json"
        adapter = _adapter(path)
        # Seed one fact so a denial cannot be confused with an empty store.
        seeded = adapter.handle(
            "POST",
            "/api/restricted/v1/facts",
            headers=_auth(),
            body={"statement": ORIGINAL},
        )
        assert seeded.status == 201

        payloads = {
            "/api/restricted/v1/autonomy/activate": {"enabled": True},
            "/api/restricted/v1/tasks/unrestricted": {
                "code": "import os; os.system('echo unrestricted')"
            },
            "/api/restricted/v1/credentials": {
                "name": "openai_api_key",
                "value": "sk-live-should-not-land",
            },
        }
        callers = (
            ({}, 401),
            (_auth(token="wrong-token"), 401),
            (_auth(identity="someone-else"), 401),
            (_auth(), 403),
        )
        for route, body in payloads.items():
            assert ("POST", route) in HARD_DENY_ROUTES
            for headers, status in callers:
                denied = self._assert_denied(adapter, route, headers, body, status, path)
                if status == 401:
                    assert denied.body["error"] == "unauthorized"
                else:
                    assert denied.body["error"] == "forbidden"

        # Credential and task writes also stay refused for PUT/PATCH aliases.
        for method in ("PUT", "PATCH"):
            denied = adapter.handle(
                method,
                "/api/restricted/v1/credentials",
                headers=_auth(),
                body={"value": "sk-live-should-not-land"},
            )
            assert denied.status == 403

        still = adapter.handle(
            "POST",
            "/api/restricted/v1/facts/retrieve",
            headers=_auth(),
            body={"query": OTHER_WORDING},
        )
        assert still.status == 200
        assert still.body["matches"][0]["statement"] == ORIGINAL
