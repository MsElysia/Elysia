"""Contract tests for POST /api/webscout/research.

Uses the real RuntimeAPIServer and WebScoutAgent. The fictional topic is not
sent to a search provider. The live case binds the Werkzeug server and posts
over HTTP. A queue-receipt response is checked only as HTTP mapping: this
runtime does not queue research.
"""

import json
import os
import socket
import time
import urllib.error
import urllib.request

import pytest

os.environ.setdefault("ELYSIA_WEBSCOUT_SKIP_GUARDIAN_READER", "1")

from elysia.agents.webscout import WebScoutAgent
from elysia.api.server import RuntimeAPIServer, research_result_response
from elysia.core.proposal_system import ProposalSystem
from elysia.events import EventBus


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_listening(server):
    last_error = None
    for _ in range(40):
        try:
            with socket.create_connection((server.host, server.port), timeout=0.1):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.05)
    pytest.fail(f"API server did not accept connections: {last_error}")


def _agent(tmp_path):
    root = tmp_path / "proposals"
    bus = EventBus()
    proposals = ProposalSystem(root, event_bus=bus, enable_watcher=False)
    agent = WebScoutAgent(
        root,
        proposals,
        event_bus=bus,
        require_api_keys=False,
    )
    return root, agent, bus, proposals


def _assert_real_agent_contract(post, root, agent):
    before = {path.name for path in root.iterdir()} if root.exists() else set()
    agent._webscout_instance = None

    unavailable = post(
        {"topic": "fictional-lattice-routing", "domain": "elysia_core"}
    )
    assert unavailable["status"] == 503
    assert unavailable["content_type"].startswith("application/json")
    assert unavailable["body"]["status"] == "error"
    assert unavailable["body"]["message"] == "WebScout not available"
    assert unavailable["body"]["queued"] is False

    agent._webscout_instance = object()
    not_queued = post(
        {"topic": "fictional-lattice-routing", "domain": "elysia_core"}
    )
    assert not_queued["status"] == 501
    assert not_queued["content_type"].startswith("application/json")
    assert not_queued["body"]["status"] == "not_queued"
    assert not_queued["body"]["queued"] is False
    assert not_queued["body"]["message"] == "Research was not queued"
    assert not_queued["body"]["runtime_message"] == "Research task queued"
    assert not_queued["body"]["topic"] == "fictional-lattice-routing"

    missing = post({"domain": "elysia_core"})
    assert missing["status"] == 400
    assert missing["body"] == {"error": "topic is required"}

    blank = post({"topic": "   "})
    assert blank["status"] == 400
    assert blank["body"] == {"error": "topic is required"}

    not_text = post({"topic": 12})
    assert not_text["status"] == 400
    assert not_text["body"] == {"error": "topic is required"}

    not_object = post(["fictional-lattice-routing"])
    assert not_object["status"] == 400
    assert not_object["body"] == {"error": "request body must be a JSON object"}

    after = {path.name for path in root.iterdir()} if root.exists() else set()
    assert after == before


class TestRuntimeApiWebscout:
    def test_status_contract_through_flask_app(self, tmp_path):
        root, agent, bus, proposals = _agent(tmp_path)
        server = RuntimeAPIServer(
            status_provider=lambda: {"running": True},
            event_bus=bus,
            proposal_system=proposals,
            webscout=agent,
        )
        client = server._app.test_client()

        def post(payload):
            response = client.post("/api/webscout/research", json=payload)
            return {
                "status": response.status_code,
                "body": response.get_json(),
                "content_type": response.headers.get("Content-Type", ""),
            }

        _assert_real_agent_contract(post, root, agent)

    def test_status_contract_through_live_http(self, tmp_path):
        root, agent, bus, proposals = _agent(tmp_path)
        server = RuntimeAPIServer(
            status_provider=lambda: {"running": True},
            event_bus=bus,
            host="127.0.0.1",
            port=_free_port(),
            proposal_system=proposals,
            webscout=agent,
        )
        server.start()
        try:
            _wait_until_listening(server)

            def post(payload):
                url = f"http://{server.host}:{server.port}/api/webscout/research"
                request = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(request, timeout=5) as response:
                        raw = response.read()
                        return {
                            "status": response.status,
                            "body": json.loads(raw.decode("utf-8")),
                            "content_type": response.headers.get("Content-Type", ""),
                        }
                except urllib.error.HTTPError as exc:
                    raw = exc.read()
                    return {
                        "status": exc.code,
                        "body": json.loads(raw.decode("utf-8")),
                        "content_type": exc.headers.get("Content-Type", ""),
                    }

            _assert_real_agent_contract(post, root, agent)
        finally:
            server.stop()

    def test_missing_webscout_is_unavailable(self):
        server = RuntimeAPIServer(
            status_provider=lambda: {"running": True},
            event_bus=EventBus(),
        )
        response = server._app.test_client().post(
            "/api/webscout/research",
            json={"topic": "fictional-lattice-routing"},
        )
        assert response.status_code == 503
        assert response.get_json() == {"error": "WebScout not available"}
        assert response.headers.get("Content-Type", "").startswith("application/json")

    def test_research_exception_is_json(self, tmp_path):
        _root, agent, bus, proposals = _agent(tmp_path)

        def explode(topic, domain="elysia_core"):
            raise RuntimeError(f"fictional failure for {topic}")

        agent.research_topic = explode
        server = RuntimeAPIServer(
            status_provider=lambda: {"running": True},
            event_bus=bus,
            proposal_system=proposals,
            webscout=agent,
        )
        response = server._app.test_client().post(
            "/api/webscout/research",
            json={"topic": "fictional-lattice-routing"},
        )
        assert response.status_code == 500
        assert response.headers.get("Content-Type", "").startswith("application/json")
        assert response.get_json()["status"] == "error"
        assert response.get_json()["queued"] is False
        assert "fictional failure" in response.get_json()["error"]

    def test_queue_receipt_maps_to_http_200(self):
        body, code = research_result_response(
            {
                "status": "accepted",
                "topic": "fictional-lattice-routing",
                "domain": "elysia_core",
                "proposal_id": "fictional-receipt",
                "message": "Research task queued",
            }
        )
        assert code == 200
        assert body["queued"] is True
        assert body["proposal_id"] == "fictional-receipt"
        assert body["status"] == "accepted"
