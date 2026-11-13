"""Isolated lifecycle tests for the unified ElysiaRuntime entrypoint.

Uses a disposable proposals directory and no live providers, network clients,
or production ports.
"""

from __future__ import annotations

import json
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


def _write_fictional_proposal(root: Path, proposal_id: str, status: str = "research") -> Path:
    proposal_dir = root / proposal_id
    proposal_dir.mkdir(parents=True)
    metadata_path = proposal_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "proposal_id": proposal_id,
                "title": "Fictional lifecycle probe",
                "status": status,
                "created_by": "lifecycle-test",
                "created_at": "2026-10-28T00:00:00+00:00",
                "history": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return metadata_path


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


def test_start_status_authorized_transition_then_stop(runtime_config):
    proposal_id = "prop-fictional-lifecycle-001"
    metadata_path = _write_fictional_proposal(runtime_config.proposals_root, proposal_id)
    runtime = ElysiaRuntime(runtime_config)
    runtime.start()
    try:
        status = runtime.get_status()
        assert status["running"] is True
        assert status["components"]["proposal_system"] is True
        assert status["components"]["webscout"] is False
        assert status["components"]["api_server"] is False
        assert status["proposal_count"] == 1
        assert _watcher(runtime)._running is True

        ok, error = runtime.proposal_system.transition_status(
            proposal_id, "design", actor="lifecycle-test"
        )
        assert ok is True
        assert error is None
        saved = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert saved["status"] == "design"
    finally:
        runtime.stop()

    assert runtime.get_status()["running"] is False
    assert _watcher(runtime)._running is False
    assert not _watcher_alive(runtime)
    assert json.loads(metadata_path.read_text(encoding="utf-8"))["status"] == "design"


def test_unauthorized_research_to_approved_leaves_disk_unchanged(runtime_config):
    proposal_id = "prop-fictional-lifecycle-unauthorized"
    metadata_path = _write_fictional_proposal(runtime_config.proposals_root, proposal_id)
    before = metadata_path.read_text(encoding="utf-8")
    runtime = ElysiaRuntime(runtime_config)
    runtime.start()
    try:
        ok, error = runtime.proposal_system.transition_status(
            proposal_id, "approved", actor="lifecycle-test"
        )
        assert ok is False
        assert error
        assert "Invalid transition" in error
        assert metadata_path.read_text(encoding="utf-8") == before
        assert json.loads(before)["status"] == "research"
    finally:
        runtime.stop()


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
