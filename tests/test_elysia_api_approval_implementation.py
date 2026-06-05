"""
Runtime API approval contract tests (passive approval, blocked implement).

Approval records operator consent only; it does not run implementation.
POST /api/proposals/<id>/implement is fail-closed in the current safety phase.
"""

import json

from elysia.api.server import RuntimeAPIServer
from elysia.core.proposal_system import ProposalSystem
from elysia.events import EventBus


class FakeProposalSystem:
    def __init__(self):
        self.approved = []
        self.transitioned = []

    def approve_proposal(self, proposal_id, approver):
        self.approved.append((proposal_id, approver))
        return True, None

    def transition_status(self, proposal_id, new_status, actor):
        self.transitioned.append((proposal_id, new_status, actor))
        return True, None

    def list_proposals(self, status_filter=None):
        return []

    def get_proposal(self, proposal_id):
        return {
            "proposal_id": proposal_id,
            "status": "approved",
            "implementation_status": "not_started",
            "history": [],
        }


class FakeImplementer:
    def __init__(self):
        self.dry_run = False
        self.calls = []

    def run_for_proposal(self, proposal_id):
        self.calls.append((proposal_id, self.dry_run))
        return {
            "success": True,
            "proposal_id": proposal_id,
            "dry_run": self.dry_run,
            "steps_completed": 1,
            "steps_total": 1,
        }


class FakeWebScout:
    def __init__(self):
        self.calls = []

    def research_topic(self, topic, domain, **kwargs):
        self.calls.append((topic, domain, kwargs))
        return {
            "status": "proposal",
            "proposal_id": "webscout-prop",
            "topic": topic,
            "domain": domain,
        }


class FakeArchitect:
    def __init__(self):
        self.calls = []

    def chat(self, message, context="general"):
        self.calls.append((message, context))
        return {
            "response": f"architect says: {message}",
            "context": context,
            "source": "fake_architect",
        }


def _server(*, webscout=None, implementer=None):
    proposals = FakeProposalSystem()
    implementer = implementer or FakeImplementer()
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
        proposal_system=proposals,
        webscout=webscout,
        implementer=implementer,
    )
    return server, proposals, implementer


def test_chat_endpoint_delegates_to_architect_chat(tmp_path):
    from project_guardian.conversation_store import ConversationStore

    architect = FakeArchitect()
    store = ConversationStore(tmp_path / "conv")
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
        architect=architect,
        conversation_store=store,
    )
    client = server._app.test_client()

    response = client.post(
        "/api/chat",
        json={"message": "let elysia speak", "context": "general"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["response"] == "architect says: let elysia speak"
    assert body["source"] == "fake_architect"
    assert body.get("conversation_id")
    assert architect.calls == [("let elysia speak", "general")]


def test_approve_does_not_implement_by_default():
    server, proposals, implementer = _server()
    client = server._app.test_client()

    response = client.post("/api/proposals/prop-1/approve", json={"approver": "tester"})

    assert response.status_code == 200
    body = response.get_json()
    assert body == {"status": "approved", "proposal_id": "prop-1"}
    assert proposals.approved == [("prop-1", "tester")]
    assert implementer.calls == []


def test_approve_ignores_auto_implement_request_body():
    """Passive approval: auto_implement in JSON does not trigger implementation."""
    server, proposals, implementer = _server()
    client = server._app.test_client()

    response = client.post(
        "/api/proposals/prop-2/approve",
        json={"approver": "tester", "auto_implement": True, "dry_run": True},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body == {"status": "approved", "proposal_id": "prop-2"}
    assert "implementation" not in body
    assert proposals.approved == [("prop-2", "tester")]
    assert implementer.calls == []


def test_approve_never_auto_implements_regardless_of_flags():
    server, proposals, implementer = _server()
    client = server._app.test_client()

    for payload in (
        {"approver": "tester"},
        {"approver": "tester", "auto_implement": True},
        {"approver": "tester", "auto_implement": False},
    ):
        response = client.post("/api/proposals/prop-3/approve", json=payload)
        assert response.status_code == 200
        assert "implementation" not in response.get_json()

    assert implementer.calls == []
    assert len(proposals.approved) == 3


def test_status_transition_does_not_auto_implement():
    server, proposals, implementer = _server()
    client = server._app.test_client()

    response = client.post(
        "/api/proposals/prop-5/status",
        json={"status": "approved", "actor": "tester", "implement": True},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body == {
        "status": "updated",
        "proposal_id": "prop-5",
        "new_status": "approved",
    }
    assert "implementation" not in body
    assert proposals.transitioned == [("prop-5", "approved", "tester")]
    assert implementer.calls == []


def test_implement_endpoint_blocked_does_not_call_injected_implementer():
    server, _proposals, implementer = _server()
    client = server._app.test_client()

    response = client.post(
        "/api/proposals/prop-preview/implement",
        json={"dry_run": True},
    )

    assert response.status_code == 403
    body = response.get_json()
    assert body["status"] == "blocked"
    assert body["executed"] is False
    assert body["blocked"] is True
    assert body["reason"] == "implementation_execution_disabled"
    assert implementer.calls == []


def test_webscout_research_endpoint_passes_topic_and_domain():
    webscout = FakeWebScout()
    server, _proposals, _implementer = _server(webscout=webscout)
    client = server._app.test_client()

    response = client.post(
        "/api/webscout/research",
        json={
            "topic": "Patchable plan",
            "domain": "elysia_core",
            "max_sources": 2,
            "tags": ["elysia_core", "patchable"],
            "implementation_plan": "ignored by current API surface",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["proposal_id"] == "webscout-prop"
    assert webscout.calls == [("Patchable plan", "elysia_core", {})]


def test_approve_then_implement_does_not_mutate_files(tmp_path):
    event_bus = EventBus()
    proposal_system = ProposalSystem(tmp_path / "proposals", event_bus=event_bus, enable_watcher=False)
    proposal_id = "prop-real-implementation"
    proposal_path = proposal_system.proposals_root / proposal_id
    (proposal_path / "design").mkdir(parents=True)

    metadata = {
        "proposal_id": proposal_id,
        "title": "Real implementation proposal",
        "description": "Must not mutate via API in safety phase.",
        "status": "proposal",
        "created_by": "test",
        "created_at": "2026-01-01T00:00:00Z",
        "domain": "elysia_core",
        "implementation_status": "not_started",
        "history": [],
    }
    (proposal_path / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    target = tmp_path / "src" / "example.py"
    target.parent.mkdir()
    target.write_text("VALUE = 1\n", encoding="utf-8")

    (proposal_path / "design" / "implementation_plan.md").write_text(
        """## Step 1: Modify file src/example.py

```python
VALUE = 2
```
""",
        encoding="utf-8",
    )

    implementer = FakeImplementer()
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=event_bus,
        proposal_system=proposal_system,
        implementer=implementer,
    )
    client = server._app.test_client()

    approve = client.post(
        f"/api/proposals/{proposal_id}/approve",
        json={"approver": "tester", "auto_implement": True},
    )
    assert approve.status_code == 200
    assert approve.get_json() == {"status": "approved", "proposal_id": proposal_id}
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert implementer.calls == []

    implement = client.post(f"/api/proposals/{proposal_id}/implement", json={})
    assert implement.status_code == 403
    assert implement.get_json()["executed"] is False
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert implementer.calls == []
    proposal = proposal_system.get_proposal(proposal_id)
    assert proposal["implementation_status"] == "not_started"


def test_implement_dry_run_request_blocked_without_side_effects(tmp_path):
    event_bus = EventBus()
    proposal_system = ProposalSystem(tmp_path / "proposals", event_bus=event_bus, enable_watcher=False)
    proposal_id = "prop-preview-real"
    proposal_path = proposal_system.proposals_root / proposal_id
    (proposal_path / "design").mkdir(parents=True)

    metadata = {
        "proposal_id": proposal_id,
        "title": "Preview implementation proposal",
        "description": "Dry-run implement must remain blocked.",
        "status": "approved",
        "created_by": "test",
        "created_at": "2026-01-01T00:00:00Z",
        "domain": "elysia_core",
        "implementation_status": "not_started",
        "history": [],
    }
    (proposal_path / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    target = tmp_path / "src" / "example.py"
    target.parent.mkdir()
    target.write_text("VALUE = 1\n", encoding="utf-8")

    implementer = FakeImplementer()
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=event_bus,
        proposal_system=proposal_system,
        implementer=implementer,
    )
    client = server._app.test_client()

    response = client.post(
        f"/api/proposals/{proposal_id}/implement",
        json={"dry_run": True},
    )

    assert response.status_code == 403
    body = response.get_json()
    assert body["blocked"] is True
    assert body["executed"] is False
    assert "diff_summary" not in body
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert implementer.calls == []
    proposal = proposal_system.get_proposal(proposal_id)
    assert proposal["status"] == "approved"
    assert proposal["implementation_status"] == "not_started"


def test_implementation_status_get_does_not_run_implementer():
    server, _proposals, implementer = _server()
    client = server._app.test_client()

    response = client.get("/api/proposals/prop-1/implementation")

    assert response.status_code == 200
    body = response.get_json()
    assert "implementation_status" in body
    assert implementer.calls == []
