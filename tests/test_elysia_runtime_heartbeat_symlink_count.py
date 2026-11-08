"""Heartbeat must not count planted symlink proposal folders as in-root."""

from __future__ import annotations

import json
import time
from pathlib import Path

from elysia.config import RuntimeConfig
from elysia.runtime import ElysiaRuntime, _is_in_root_proposal_dir


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


def _write_fictional_proposal(root: Path, proposal_id: str, status: str = "research") -> Path:
    proposal_dir = root / proposal_id
    proposal_dir.mkdir(parents=True)
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional in-root proposal",
        "status": status,
        "created_by": "probe",
        "created_at": "2026-11-08T00:00:00Z",
        "history": [],
    }
    (proposal_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return proposal_dir


def _write_outside_proposal(path: Path, proposal_id: str) -> str:
    path.mkdir()
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional outside proposal",
        "status": "proposal",
        "created_by": "probe",
        "created_at": "2026-11-08T00:00:00Z",
        "secret_marker": "SHOULD-NOT-BE-COUNTED",
        "history": [],
    }
    text = json.dumps(metadata, indent=2)
    (path / "metadata.json").write_text(text, encoding="utf-8")
    return text


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


def test_helper_rejects_directory_symlink_and_accepts_regular(tmp_path):
    outside = tmp_path / "outside-proposal"
    outside.mkdir()
    link = tmp_path / "fictional-dir-symlink-20261108"
    link.symlink_to(outside)
    regular = _write_fictional_proposal(tmp_path, "fictional-regular-20261108")

    assert _is_in_root_proposal_dir(link) is False
    assert _is_in_root_proposal_dir(regular) is True
    assert _is_in_root_proposal_dir(tmp_path / "missing-proposal") is False


def test_helper_rejects_metadata_file_symlink(tmp_path):
    proposal_dir = tmp_path / "fictional-meta-symlink-20261108"
    proposal_dir.mkdir()
    outside_meta = tmp_path / "outside-metadata.json"
    outside_meta.write_text("{}", encoding="utf-8")
    (proposal_dir / "metadata.json").symlink_to(outside_meta)

    assert (proposal_dir / "metadata.json").is_symlink()
    assert _is_in_root_proposal_dir(proposal_dir) is False


def test_heartbeat_omits_directory_and_metadata_symlinks_keeps_regular(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "outside-proposal"
    before_dir = _write_outside_proposal(outside, "fictional-dir-symlink-20261108")
    (root / "fictional-dir-symlink-20261108").symlink_to(outside)

    outside_meta = tmp_path / "outside-metadata.json"
    before_meta = json.dumps(
        {
            "proposal_id": "fictional-meta-symlink-20261108",
            "title": "Fictional metadata symlink",
            "status": "proposal",
            "created_by": "probe",
            "created_at": "2026-11-08T00:00:00Z",
            "secret_marker": "SHOULD-NOT-BE-COUNTED-META",
            "history": [],
        },
        indent=2,
    )
    outside_meta.write_text(before_meta, encoding="utf-8")
    planted = root / "fictional-meta-symlink-20261108"
    planted.mkdir()
    (planted / "metadata.json").symlink_to(outside_meta)

    _write_fictional_proposal(root, "fictional-regular-20261108")
    runtime = _runtime(tmp_path)
    runtime.start()
    try:
        first = _wait_for_heartbeat(runtime)
        status = runtime.get_status()

        assert first is not None
        assert first["payload"]["proposals"] == 1
        assert status["running"] is True
        assert (outside / "metadata.json").read_text(encoding="utf-8") == before_dir
        assert outside_meta.read_text(encoding="utf-8") == before_meta
        assert (planted / "metadata.json").is_symlink()
        assert "SHOULD-NOT-BE-COUNTED" in before_dir
    finally:
        runtime.stop()
        assert runtime.get_status()["running"] is False


def test_started_runtime_still_completes_authorized_status_transition(tmp_path):
    proposal_id = "fictional-heartbeat-transition-20261108"
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "outside-proposal"
    before = _write_outside_proposal(outside, "fictional-dir-symlink-20261108")
    (root / "fictional-dir-symlink-20261108").symlink_to(outside)
    _write_fictional_proposal(root, proposal_id)
    runtime = _runtime(tmp_path)
    runtime.start()
    try:
        first = _wait_for_heartbeat(runtime)
        ok, error = runtime.proposal_system.transition_status(
            proposal_id, "design", actor="fictional-actor"
        )
        stored = runtime.proposal_system.get_proposal(proposal_id)

        assert first is not None
        assert first["payload"]["proposals"] == 1
        assert ok is True
        assert error is None
        assert stored is not None
        assert stored["status"] == "design"
        assert stored["last_updated_by"] == "fictional-actor"
        assert runtime.get_status()["running"] is True
        assert (outside / "metadata.json").read_text(encoding="utf-8") == before
    finally:
        runtime.stop()


def test_invalid_transition_on_running_runtime_leaves_disk_unchanged(tmp_path):
    proposal_id = "fictional-heartbeat-invalid-20261108"
    _write_fictional_proposal(tmp_path / "proposals", proposal_id, "research")
    before = (tmp_path / "proposals" / proposal_id / "metadata.json").read_text(
        encoding="utf-8"
    )
    runtime = _runtime(tmp_path)
    runtime.start()
    try:
        first = _wait_for_heartbeat(runtime)
        ok, error = runtime.proposal_system.transition_status(
            proposal_id, "approved", actor="fictional-actor"
        )
        stored = runtime.proposal_system.get_proposal(proposal_id)
        after = (tmp_path / "proposals" / proposal_id / "metadata.json").read_text(
            encoding="utf-8"
        )

        assert first is not None
        assert first["payload"]["proposals"] == 1
        assert runtime.get_status()["running"] is True
        assert ok is False
        assert "Invalid transition" in (error or "")
        assert stored is not None
        assert stored["status"] == "research"
        assert after == before
    finally:
        runtime.stop()


def test_empty_proposals_root_heartbeat_reports_zero(tmp_path):
    (tmp_path / "proposals").mkdir()
    runtime = _runtime(tmp_path)
    runtime.start()
    try:
        first = _wait_for_heartbeat(runtime)
        assert first is not None
        assert first["payload"]["proposals"] == 0
        assert runtime.get_status()["running"] is True
    finally:
        runtime.stop()
        assert runtime.get_status()["running"] is False
