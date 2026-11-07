"""get_status must not count planted symlink proposal folders as in-root."""

from __future__ import annotations

import json
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
        "created_at": "2026-11-07T00:00:00Z",
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
        "created_at": "2026-11-07T00:00:00Z",
        "secret_marker": "SHOULD-NOT-BE-COUNTED",
        "history": [],
    }
    text = json.dumps(metadata, indent=2)
    (path / "metadata.json").write_text(text, encoding="utf-8")
    return text


def test_helper_rejects_directory_symlink_and_accepts_regular(tmp_path):
    outside = tmp_path / "outside-proposal"
    outside.mkdir()
    link = tmp_path / "fictional-dir-symlink-20261107"
    link.symlink_to(outside)
    regular = _write_fictional_proposal(tmp_path, "fictional-regular-20261107")

    assert _is_in_root_proposal_dir(link) is False
    assert _is_in_root_proposal_dir(regular) is True
    assert _is_in_root_proposal_dir(tmp_path / "missing-proposal") is False


def test_helper_rejects_metadata_file_symlink(tmp_path):
    proposal_dir = tmp_path / "fictional-meta-symlink-20261107"
    proposal_dir.mkdir()
    outside_meta = tmp_path / "outside-metadata.json"
    outside_meta.write_text("{}", encoding="utf-8")
    (proposal_dir / "metadata.json").symlink_to(outside_meta)

    assert (proposal_dir / "metadata.json").is_symlink()
    assert _is_in_root_proposal_dir(proposal_dir) is False


def test_get_status_omits_directory_symlink_and_keeps_regular(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "outside-proposal"
    before = _write_outside_proposal(outside, "fictional-dir-symlink-20261107")
    (root / "fictional-dir-symlink-20261107").symlink_to(outside)
    _write_fictional_proposal(root, "fictional-regular-20261107")
    runtime = _runtime(tmp_path)
    runtime.start()
    try:
        status = runtime.get_status()

        assert status["running"] is True
        assert status["proposal_count"] == 1
        assert (outside / "metadata.json").read_text(encoding="utf-8") == before
        assert "SHOULD-NOT-BE-COUNTED" in before
    finally:
        runtime.stop()


def test_get_status_omits_metadata_file_symlink_without_reading_outside(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside_meta = tmp_path / "outside-metadata.json"
    before = json.dumps(
        {
            "proposal_id": "fictional-meta-symlink-20261107",
            "title": "Fictional metadata symlink",
            "status": "proposal",
            "created_by": "probe",
            "created_at": "2026-11-07T00:00:00Z",
            "secret_marker": "SHOULD-NOT-BE-COUNTED-META",
            "history": [],
        },
        indent=2,
    )
    outside_meta.write_text(before, encoding="utf-8")
    planted = root / "fictional-meta-symlink-20261107"
    planted.mkdir()
    (planted / "metadata.json").symlink_to(outside_meta)
    _write_fictional_proposal(root, "fictional-regular-20261107")
    runtime = _runtime(tmp_path)
    runtime.start()
    try:
        status = runtime.get_status()

        assert status["running"] is True
        assert status["proposal_count"] == 1
        assert outside_meta.read_text(encoding="utf-8") == before
        assert (planted / "metadata.json").is_symlink()
    finally:
        runtime.stop()


def test_started_runtime_still_completes_authorized_status_transition(tmp_path):
    proposal_id = "fictional-status-transition-20261107"
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "outside-proposal"
    before = _write_outside_proposal(outside, "fictional-dir-symlink-20261107")
    (root / "fictional-dir-symlink-20261107").symlink_to(outside)
    _write_fictional_proposal(root, proposal_id)
    runtime = _runtime(tmp_path)
    runtime.start()
    try:
        ok, error = runtime.proposal_system.transition_status(
            proposal_id, "design", actor="fictional-actor"
        )
        stored = runtime.proposal_system.get_proposal(proposal_id)
        status = runtime.get_status()

        assert ok is True
        assert error is None
        assert stored is not None
        assert stored["status"] == "design"
        assert stored["last_updated_by"] == "fictional-actor"
        assert status["running"] is True
        assert status["proposal_count"] == 1
        assert (outside / "metadata.json").read_text(encoding="utf-8") == before
    finally:
        runtime.stop()


def test_invalid_transition_on_running_runtime_leaves_disk_unchanged(tmp_path):
    proposal_id = "fictional-status-invalid-20261107"
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
        assert runtime.get_status()["proposal_count"] == 1
        assert ok is False
        assert "Invalid transition" in (error or "")
        assert stored is not None
        assert stored["status"] == "research"
        assert after == before
    finally:
        runtime.stop()


def test_empty_proposals_root_reports_zero(tmp_path):
    (tmp_path / "proposals").mkdir()
    runtime = _runtime(tmp_path)
    runtime.start()
    try:
        status = runtime.get_status()
        assert status["running"] is True
        assert status["proposal_count"] == 0
    finally:
        runtime.stop()
