"""Contract tests for GET /api/events on the runtime API server.

Uses a real EventBus and RuntimeAPIServer. The live case also binds the
Werkzeug server and requests it over HTTP. External services are not called.
"""

import json
import socket
import time
import urllib.error
import urllib.request

import pytest

from elysia.api.server import RuntimeAPIServer
from elysia.events import EventBus


def _bus_with_notes(count, buffer_size=200):
    bus = EventBus(buffer_size=buffer_size)
    for n in range(count):
        bus.emit("fixture", "note", {"n": n, "label": "fictional"})
    return bus


def _server(bus, port=0):
    return RuntimeAPIServer(
        status_provider=lambda: {"running": True, "components": {"api_server": True}},
        event_bus=bus,
        host="127.0.0.1",
        port=port,
    )


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _assert_contract(get):
    missing = get("/api/events")
    assert missing["status"] == 200
    assert missing["body"]["limit"] == 50
    assert [item["payload"]["n"] for item in missing["body"]["events"]] == list(range(200, 250))

    one = get("/api/events?limit=1")
    assert one["status"] == 200
    assert one["body"]["limit"] == 1
    assert [item["payload"]["n"] for item in one["body"]["events"]] == [249]

    zero = get("/api/events?limit=0")
    assert zero["status"] == 200
    assert zero["body"] == {"events": [], "limit": 0}

    negative = get("/api/events?limit=-1")
    assert negative["status"] == 400
    assert negative["body"]["error"] == "limit must be a non-negative integer"
    assert "events" not in negative["body"]

    invalid = get("/api/events?limit=nope")
    assert invalid["status"] == 400
    assert invalid["body"]["error"] == "limit must be a non-negative integer"
    assert invalid["content_type"].startswith("application/json")

    capped = get("/api/events?limit=999")
    assert capped["status"] == 200
    assert capped["body"]["limit"] == 200
    numbers = [item["payload"]["n"] for item in capped["body"]["events"]]
    assert numbers[0] == 50
    assert numbers[-1] == 249
    assert len(numbers) == 200


class TestRuntimeApiEvents:
    def test_limit_contract_through_flask_app(self):
        bus = _bus_with_notes(250, buffer_size=250)
        server = _server(bus)
        client = server._app.test_client()

        def get(path):
            response = client.get(path)
            content_type = response.headers.get("Content-Type", "")
            return {
                "status": response.status_code,
                "body": response.get_json(),
                "content_type": content_type,
            }

        _assert_contract(get)

    def test_limit_contract_through_live_http(self):
        bus = _bus_with_notes(250, buffer_size=250)
        server = _server(bus, port=_free_port())
        server.start()
        try:
            _wait_until_listening(server)

            def get(path):
                url = f"http://{server.host}:{server.port}{path}"
                request = urllib.request.Request(url)
                try:
                    with urllib.request.urlopen(request, timeout=5) as response:
                        payload = response.read()
                        return {
                            "status": response.status,
                            "body": json.loads(payload.decode("utf-8")),
                            "content_type": response.headers.get("Content-Type", ""),
                        }
                except urllib.error.HTTPError as exc:
                    payload = exc.read()
                    return {
                        "status": exc.code,
                        "body": json.loads(payload.decode("utf-8")),
                        "content_type": exc.headers.get("Content-Type", ""),
                    }

            _assert_contract(get)
        finally:
            server.stop()


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
