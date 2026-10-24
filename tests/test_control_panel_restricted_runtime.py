# Live panel routes for the restricted runtime adapter.
# Uses the Flask test client. Does not bind a public port or call a provider.

import json
import sys
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _ensure_guardian_submodules():
    """Import panel modules without executing project_guardian/__init__.py."""
    if "project_guardian.memory" in sys.modules and "project_guardian.ui_control_panel" in sys.modules:
        return
    if "project_guardian" not in sys.modules:
        package = types.ModuleType("project_guardian")
        package.__path__ = [str(_ROOT / "project_guardian")]
        package.__package__ = "project_guardian"
        sys.modules["project_guardian"] = package


_ensure_guardian_submodules()

from project_guardian.memory import MemoryCore
from project_guardian.ui_control_panel import UIControlPanel

ORIGINAL = "The harbor city of the fictional country Veridia is Lumenport."
CORRECTED = "The harbor city of the fictional country Veridia is Glasshaven."
OTHER_WORDING = "Which harbor city is in the country Veridia?"


class _Orchestrator:
    def __init__(self, memory, config=None):
        self.memory = memory
        self.config = config if config is not None else {}


class _JsonMemoryHolder:
    def __init__(self, memory):
        self.json_memory = memory


def _memory(path: Path) -> MemoryCore:
    return MemoryCore(
        filepath=str(path),
        timeline_memory=None,
        enable_timeline_logging=False,
        enable_vector_search=False,
    )


def _panel(memory, host="127.0.0.1", config=None) -> UIControlPanel:
    return UIControlPanel(
        orchestrator=_Orchestrator(memory, config=config),
        host=host,
        port=5000,
    )


def _auth(panel: UIControlPanel):
    return {
        "X-Elysia-Identity": "dashboard-operator",
        "X-Elysia-Token": panel._dashboard_operator_token(),
    }


class TestLivePanelRestrictedRoutes:
    def test_fact_workflow_uses_the_same_memory_core(self, tmp_path):
        path = tmp_path / "guardian_memory.json"
        memory = _memory(path)
        panel = _panel(memory, config={"memory_filepath": str(path)})
        client = panel.app.test_client()
        headers = _auth(panel)

        missing = client.post(
            "/api/restricted/v1/facts",
            json={"statement": ORIGINAL},
        )
        assert missing.status_code == 401
        assert missing.get_json()["error"] == "unauthorized"

        store = client.get("/api/restricted/v1/memory-store", headers=headers)
        assert store.status_code == 200
        body = store.get_json()
        assert body["memory_store"]["module"] == "project_guardian.memory.MemoryCore"
        assert body["memory_store"]["filepath"] == str(path.resolve())
        assert body["memory_store"]["canonical_config_key"] == "memory_filepath"
        assert panel._restricted_adapter().memory is memory

        saved = client.post(
            "/api/restricted/v1/facts",
            json={"statement": ORIGINAL},
            headers=headers,
        )
        assert saved.status_code == 201
        fact = saved.get_json()["fact"]
        fact_id = fact["fact_id"]
        assert fact["revision"] == 1
        assert fact["statement"] == ORIGINAL
        assert panel._dashboard_operator_token() not in path.read_text(encoding="utf-8")

        keyword = client.get(
            "/api/memory/search",
            query_string={"q": OTHER_WORDING},
        )
        assert keyword.status_code == 200
        assert keyword.get_json()["results"] == []

        found = client.post(
            "/api/restricted/v1/facts/retrieve",
            json={"query": OTHER_WORDING},
            headers=headers,
        )
        assert found.status_code == 200
        matches = found.get_json()["matches"]
        assert len(matches) == 1
        assert matches[0]["fact_id"] == fact_id
        assert matches[0]["statement"] == ORIGINAL

        corrected = client.post(
            f"/api/restricted/v1/facts/{fact_id}/corrections",
            json={"statement": CORRECTED},
            headers=headers,
        )
        assert corrected.status_code == 200
        assert corrected.get_json()["fact"]["revision"] == 2
        assert corrected.get_json()["fact"]["previous_statement"] == ORIGINAL

        history = client.get(
            f"/api/restricted/v1/facts/{fact_id}/history",
            headers=headers,
        )
        assert history.status_code == 200
        revisions = history.get_json()["revisions"]
        assert [item["statement"] for item in revisions] == [ORIGINAL, CORRECTED]
        assert [item["current"] for item in revisions] == [False, True]

        rows = json.loads(path.read_text(encoding="utf-8"))
        fact_rows = [
            row for row in rows
            if isinstance(row, dict) and (row.get("metadata") or {}).get("fact_id") == fact_id
        ]
        assert len(fact_rows) == 2

    def test_enhanced_memory_reuses_json_memory(self, tmp_path):
        path = tmp_path / "data" / "guardian_memory.json"
        path.parent.mkdir()
        memory = _memory(path)
        holder = _JsonMemoryHolder(memory)
        panel = UIControlPanel(
            orchestrator=_Orchestrator(
                holder,
                config={"memory_filepath": str(tmp_path / "other" / "guardian_memory.json")},
            ),
            host="127.0.0.1",
            port=5000,
        )
        saved = panel.app.test_client().post(
            "/api/restricted/v1/facts",
            json={"statement": ORIGINAL},
            headers=_auth(panel),
        )
        assert saved.status_code == 201
        assert panel._restricted_adapter().memory is memory
        assert path.exists()
        assert not (tmp_path / "other" / "guardian_memory.json").exists()

    def test_hard_deny_and_loopback_guards(self, tmp_path):
        path = tmp_path / "guardian_memory.json"
        memory = _memory(path)
        panel = _panel(memory)
        client = panel.app.test_client()
        headers = _auth(panel)
        statement = {"statement": ORIGINAL}

        denied = client.post(
            "/api/restricted/v1/autonomy/activate",
            json={"enabled": True},
            headers=headers,
        )
        assert denied.status_code == 403
        assert denied.get_json()["error"] == "forbidden"

        credentials = client.put(
            "/api/restricted/v1/credentials",
            json={"token": "should-not-be-stored"},
            headers=headers,
        )
        assert credentials.status_code == 403

        remote = client.post(
            "/api/restricted/v1/facts",
            json=statement,
            headers=headers,
            environ_overrides={"REMOTE_ADDR": "203.0.113.8"},
        )
        assert remote.status_code == 403
        assert remote.get_json()["detail"] == "restricted runtime is loopback only"
        assert not path.exists()

        slash = client.post(
            "/api/restricted/v1/facts/",
            json=statement,
            headers=headers,
        )
        assert slash.status_code == 400

        queried = client.post(
            "/api/restricted/v1/facts?extra=1",
            json=statement,
            headers=headers,
        )
        assert queried.status_code == 400

        invalid = client.post(
            "/api/restricted/v1/facts",
            data="[",
            headers={**headers, "Content-Type": "application/json"},
        )
        assert invalid.status_code == 400
        assert invalid.get_json()["error"] == "invalid_request"

    def test_routes_are_not_mounted_off_loopback(self, tmp_path):
        path = tmp_path / "guardian_memory.json"
        panel = _panel(_memory(path), host="0.0.0.0")
        client = panel.app.test_client()
        response = client.post(
            "/api/restricted/v1/facts",
            json={"statement": ORIGINAL},
            headers=_auth(panel),
        )
        assert response.status_code == 404
        page = client.get("/")
        assert page.status_code == 200
        html = page.get_data(as_text=True)
        assert "RESTRICTED_IDENTITY" in html
        assert panel._dashboard_operator_token() not in html
        assert not path.exists()

    def test_page_sends_operator_headers_on_loopback(self, tmp_path):
        panel = _panel(_memory(tmp_path / "guardian_memory.json"))
        html = panel.app.test_client().get("/").get_data(as_text=True)
        assert "Save fact" in html
        assert "X-Elysia-Identity" in html
        assert "X-Elysia-Token" in html
        assert "dashboard-operator" in html
        assert panel._dashboard_operator_token() in html
        assert "searchMemories" in html
        assert "/api/memory/search" in html
