"""Isolated lifecycle tests for the unified ElysiaRuntime entrypoint.

Uses a disposable proposals directory and no live providers, network clients,
or production ports.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.request
from pathlib import Path

import pytest

from elysia import cli
from elysia.config import RuntimeConfig
from elysia.runtime import ElysiaRuntime


@pytest.fixture
def runtime_config(tmp_path, monkeypatch):
    monkeypatch.setattr("elysia.runtime.setup_logging", lambda *a, **k: None)
    monkeypatch.setattr("elysia.runtime.ElysiaRuntime._load_api_keys", lambda self: None)
    return RuntimeConfig(
        mode="core",
        env="dev",
        proposals_root=tmp_path / "proposals-fictional",
        log_level="WARNING",
        enable_api=False,
        enable_webscout=False,
        require_api_keys=False,
    )


def _watcher(runtime: ElysiaRuntime):
    assert runtime.proposal_system is not None
    assert runtime.proposal_system.watcher is not None
    return runtime.proposal_system.watcher


def _watcher_alive(runtime: ElysiaRuntime) -> bool:
    watcher = _watcher(runtime)
    return bool(watcher._thread and watcher._thread.is_alive())


def test_stop_after_init_without_start_stops_watcher(runtime_config):
    runtime = ElysiaRuntime(runtime_config)
    runtime.init()
    watcher = _watcher(runtime)
    assert watcher._running is True
    assert _watcher_alive(runtime)

    runtime.stop()

    assert runtime._running is False
    assert watcher._running is False
    assert not _watcher_alive(runtime)
    types = [evt["type"] for evt in runtime.event_bus.get_recent_events(limit=50)]
    assert "stopped" in types


def test_start_status_stop_happy_path(runtime_config):
    runtime = ElysiaRuntime(runtime_config)
    runtime.start()
    try:
        status = runtime.get_status()
        assert status["running"] is True
        assert status["components"]["proposal_system"] is True
        assert status["components"]["webscout"] is False
        assert status["components"]["api_server"] is False
        assert status["proposal_count"] == 0
        assert _watcher(runtime)._running is True
    finally:
        runtime.stop()

    assert runtime.get_status()["running"] is False
    assert _watcher(runtime)._running is False
    assert not _watcher_alive(runtime)


def test_stop_after_interrupted_start_stops_heartbeat_and_watcher(runtime_config):
    runtime = ElysiaRuntime(runtime_config)
    original_heartbeat = runtime._start_heartbeat

    def boom():
        original_heartbeat()
        raise KeyboardInterrupt("fictional interrupt during start")

    runtime._start_heartbeat = boom
    with pytest.raises(KeyboardInterrupt):
        runtime.start()

    assert runtime._running is False
    assert runtime._initialized is True
    assert _watcher(runtime)._running is True
    assert runtime._heartbeat_thread is not None
    assert runtime._heartbeat_thread.is_alive()

    runtime.stop()

    assert _watcher(runtime)._running is False
    assert not _watcher_alive(runtime)
    assert not runtime._heartbeat_thread.is_alive()


def test_stop_never_initialized_is_noop(runtime_config):
    runtime = ElysiaRuntime(runtime_config)
    runtime.stop()
    assert runtime._running is False
    assert runtime._initialized is False
    assert runtime.proposal_system is None
    assert runtime.event_bus.get_recent_events(limit=10) == []


def test_stop_is_idempotent_after_init(runtime_config):
    runtime = ElysiaRuntime(runtime_config)
    runtime.init()
    runtime.stop()
    runtime.stop()
    assert _watcher(runtime)._running is False
    assert not _watcher_alive(runtime)


def test_start_after_stop_restarts_watcher(runtime_config):
    runtime = ElysiaRuntime(runtime_config)
    runtime.start()
    runtime.stop()
    assert _watcher(runtime)._running is False

    runtime.start()
    try:
        assert runtime._running is True
        assert _watcher(runtime)._running is True
        assert _watcher_alive(runtime)
        assert runtime.get_status()["running"] is True
    finally:
        runtime.stop()


def test_cli_run_calls_stop_when_start_raises_keyboardinterrupt(monkeypatch, runtime_config):
    calls = []

    class FakeRuntime:
        def __init__(self, cfg):
            self.cfg = cfg

        def start(self):
            calls.append("start")
            raise KeyboardInterrupt

        def stop(self):
            calls.append("stop")

    monkeypatch.setattr(cli, "ElysiaRuntime", FakeRuntime)
    monkeypatch.setattr(cli, "load_runtime_config", lambda **kwargs: runtime_config)

    cli.main(["run", "--no-api", "--no-webscout"])
    assert calls == ["start", "stop"]


def test_cli_run_calls_stop_when_loop_raises_keyboardinterrupt(monkeypatch, runtime_config):
    calls = []

    class FakeRuntime:
        def __init__(self, cfg):
            self.cfg = cfg

        def start(self):
            calls.append("start")

        def stop(self):
            calls.append("stop")

    monkeypatch.setattr(cli, "ElysiaRuntime", FakeRuntime)
    monkeypatch.setattr(cli, "load_runtime_config", lambda **kwargs: runtime_config)
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()))

    cli.main(["run", "--no-api", "--no-webscout"])
    assert calls == ["start", "stop"]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_start_local_status_request_then_stop(runtime_config, tmp_path):
    """Startup → local authorized status read → stop, no live providers."""
    proposal_id = "prop-fictional-lifecycle-001"
    proposal_dir = runtime_config.proposals_root / proposal_id
    proposal_dir.mkdir(parents=True)
    (proposal_dir / "metadata.json").write_text(
        json.dumps(
            {
                "proposal_id": proposal_id,
                "title": "Fictional lifecycle probe",
                "status": "research",
                "created_by": "lifecycle-test",
                "created_at": "2026-10-28T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    port = _free_port()
    runtime_config.enable_api = True
    runtime_config.api_host = "127.0.0.1"
    runtime_config.api_port = port
    runtime = ElysiaRuntime(runtime_config)
    runtime.start()
    try:
        body = None
        url = f"http://127.0.0.1:{port}/api/status"
        deadline = time.time() + 3
        last_error = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=0.5) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    break
            except Exception as exc:
                last_error = exc
                time.sleep(0.05)
        assert body is not None, f"status endpoint not reachable: {last_error}"
        assert body["running"] is True
        assert body["proposal_count"] == 1
        assert body["components"]["proposal_system"] is True
    finally:
        runtime.stop()

    assert runtime.get_status()["running"] is False
    assert _watcher(runtime)._running is False
    assert not _watcher_alive(runtime)
    assert Path(tmp_path / "proposals-fictional" / proposal_id / "metadata.json").exists()
