"""First heartbeat after start must not report a live runtime as down."""

from __future__ import annotations

import json
import time
from pathlib import Path

from elysia.config import RuntimeConfig
from elysia.runtime import ElysiaRuntime


def _runtime(tmp_path: Path) -> ElysiaRuntime:
    cfg = RuntimeConfig(
        mode="core",
        env="dev",
        proposals_root=tmp_path / "proposals",
        enable_api=False,
        enable_webscout=False,
        log_level="ERROR",
    )
    return ElysiaRuntime(cfg)


def _write_fictional_proposal(root: Path, proposal_id: str, status: str = "research") -> None:
    proposal_dir = root / proposal_id
    proposal_dir.mkdir(parents=True)
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional heartbeat proposal",
        "status": status,
        "created_by": "probe",
        "created_at": "2026-11-06T00:00:00Z",
        "history": [],
    }
    (proposal_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )


def _wait_for_heartbeat(runtime: ElysiaRuntime, timeout: float = 2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        events = [
            evt
            for evt in runtime.event_bus.get_recent_events(limit=50)
            if evt.get("source") == "runtime" and evt.get("type") == "heartbeat"
        ]
        if events:
            return events[0]
        time.sleep(0.01)
    return None


def test_first_heartbeat_after_start_reports_running_true(tmp_path):
    runtime = _runtime(tmp_path)
    assert runtime.get_status()["running"] is False

    runtime.start()
    try:
        first = _wait_for_heartbeat(runtime)
        status = runtime.get_status()

        assert first is not None
        assert first["payload"]["running"] is True
        assert status["running"] is True
    finally:
        runtime.stop()


def test_init_without_start_does_not_claim_running_or_emit_heartbeat(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.init()
    try:
        time.sleep(0.2)
        heartbeats = [
            evt
            for evt in runtime.event_bus.get_recent_events(limit=50)
            if evt.get("source") == "runtime" and evt.get("type") == "heartbeat"
        ]
        assert runtime.get_status()["running"] is False
        assert heartbeats == []
    finally:
        if runtime.proposal_system:
            runtime.proposal_system.shutdown()


def test_stop_clears_running_flag_used_by_status(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.start()
    assert _wait_for_heartbeat(runtime) is not None
    assert runtime.get_status()["running"] is True
    runtime.stop()

    assert runtime.get_status()["running"] is False
    time.sleep(0.2)
    assert runtime.get_status()["running"] is False


def test_started_runtime_still_completes_authorized_status_transition(tmp_path):
    proposal_id = "fictional-heartbeat-transition-20261106"
    _write_fictional_proposal(tmp_path / "proposals", proposal_id)
    runtime = _runtime(tmp_path)
    runtime.start()
    try:
        first = _wait_for_heartbeat(runtime)
        ok, error = runtime.proposal_system.transition_status(
            proposal_id, "design", actor="fictional-actor"
        )
        stored = runtime.proposal_system.get_proposal(proposal_id)

        assert first is not None
        assert first["payload"]["running"] is True
        assert ok is True
        assert error is None
        assert stored is not None
        assert stored["status"] == "design"
        assert stored["last_updated_by"] == "fictional-actor"
        assert runtime.get_status()["running"] is True
        assert runtime.get_status()["proposal_count"] == 1
    finally:
        runtime.stop()


def test_invalid_transition_on_running_runtime_leaves_disk_unchanged(tmp_path):
    proposal_id = "fictional-heartbeat-invalid-20261106"
    _write_fictional_proposal(tmp_path / "proposals", proposal_id, "research")
    before = (tmp_path / "proposals" / proposal_id / "metadata.json").read_text(
        encoding="utf-8"
    )
    runtime = _runtime(tmp_path)
    runtime.start()
    try:
        ok, error = runtime.proposal_system.transition_status(
            proposal_id, "approved", actor="fictional-actor"
        )
        stored = runtime.proposal_system.get_proposal(proposal_id)
        after = (tmp_path / "proposals" / proposal_id / "metadata.json").read_text(
            encoding="utf-8"
        )

        assert runtime.get_status()["running"] is True
        assert ok is False
        assert "Invalid transition" in (error or "")
        assert stored is not None
        assert stored["status"] == "research"
        assert after == before
    finally:
        runtime.stop()


def test_double_start_does_not_reset_running_or_start_time(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.start()
    try:
        first_start = runtime._start_time
        assert _wait_for_heartbeat(runtime) is not None
        runtime.start()
        assert runtime.get_status()["running"] is True
        assert runtime._start_time is first_start
    finally:
        runtime.stop()
