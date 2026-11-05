"""Failed _save_metadata must not destroy authorized on-disk proposal metadata."""

from __future__ import annotations

import json
from pathlib import Path

from elysia.core.proposal_system import ProposalSystem
from elysia.events import EventBus


def _write_regular_proposal(root: Path, proposal_id: str, status: str) -> Path:
    proposal_dir = root / proposal_id
    proposal_dir.mkdir()
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional in-root proposal",
        "status": status,
        "created_by": "probe",
        "created_at": "2026-11-05T00:00:00Z",
        "history": [],
    }
    (proposal_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return proposal_dir


def test_failed_save_preserves_original_authorized_metadata(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    proposal_id = "fictional-save-crash-20261105"
    proposal_dir = _write_regular_proposal(root, proposal_id, "research")
    before = (proposal_dir / "metadata.json").read_text(encoding="utf-8")
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    payload = json.loads(before)
    payload["status"] = "design"
    payload["bad"] = {1, 2, 3}
    ok = system.lifecycle_manager._save_metadata(proposal_id, payload)
    loaded = system.lifecycle_manager._load_metadata(proposal_id)
    after = (proposal_dir / "metadata.json").read_text(encoding="utf-8")

    assert ok is False
    assert loaded is not None
    assert loaded["status"] == "research"
    assert loaded["proposal_id"] == proposal_id
    assert json.loads(after)["status"] == "research"
    assert after == before


def test_failed_save_does_not_leave_temp_or_partial_json(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    proposal_id = "fictional-save-crash-tmp-20261105"
    proposal_dir = _write_regular_proposal(root, proposal_id, "research")
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    ok = system.lifecycle_manager._save_metadata(
        proposal_id,
        {
            "proposal_id": proposal_id,
            "title": "Fictional in-root proposal",
            "status": "design",
            "created_by": "probe",
            "created_at": "2026-11-05T00:00:00Z",
            "history": [],
            "bad": {1, 2, 3},
        },
    )

    assert ok is False
    assert not (proposal_dir / ".metadata.json.tmp").exists()
    disk = json.loads((proposal_dir / "metadata.json").read_text(encoding="utf-8"))
    assert disk["status"] == "research"
    assert "bad" not in disk


def test_failed_save_then_authorized_transition_still_recovers(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    proposal_id = "fictional-save-crash-recover-20261105"
    _write_regular_proposal(root, proposal_id, "research")
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    destroyed = system.lifecycle_manager._save_metadata(
        proposal_id,
        {
            "proposal_id": proposal_id,
            "title": "Fictional in-root proposal",
            "status": "design",
            "created_by": "probe",
            "created_at": "2026-11-05T00:00:00Z",
            "history": [],
            "bad": {object()},
        },
    )
    ok, error = system.transition_status(proposal_id, "design", actor="fictional-actor")
    stored = system.lifecycle_manager._load_metadata(proposal_id)

    assert destroyed is False
    assert ok is True
    assert error is None
    assert stored is not None
    assert stored["status"] == "design"
    assert stored["last_updated_by"] == "fictional-actor"


def test_missing_proposal_failed_save_does_not_leave_corrupt_metadata(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    proposal_id = "fictional-missing-save-crash-20261105"
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    ok = system.lifecycle_manager._save_metadata(
        proposal_id,
        {
            "proposal_id": proposal_id,
            "title": "Fictional missing save",
            "status": "research",
            "created_by": "probe",
            "created_at": "2026-11-05T00:00:00Z",
            "bad": {1, 2, 3},
        },
    )

    assert ok is False
    proposal_dir = root / proposal_id
    assert not (proposal_dir / "metadata.json").exists()
    assert not (proposal_dir / ".metadata.json.tmp").exists()
    assert system.lifecycle_manager._load_metadata(proposal_id) is None


def test_inroot_regular_research_to_design_still_persists(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    proposal_id = "fictional-regular-save-20261105"
    proposal_dir = _write_regular_proposal(root, proposal_id, "research")
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    ok, error = system.transition_status(proposal_id, "design", actor="fictional-actor")
    stored = system.lifecycle_manager._load_metadata(proposal_id)
    disk = json.loads((proposal_dir / "metadata.json").read_text(encoding="utf-8"))

    assert ok is True
    assert error is None
    assert stored is not None
    assert stored["status"] == "design"
    assert stored["last_updated_by"] == "fictional-actor"
    assert disk["status"] == "design"
    assert disk["last_updated_by"] == "fictional-actor"
    assert "updated_at" in disk
    assert not (proposal_dir / ".metadata.json.tmp").exists()


def test_invalid_transition_leaves_disk_unchanged(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    proposal_id = "fictional-invalid-transition-20261105"
    proposal_dir = _write_regular_proposal(root, proposal_id, "research")
    before = (proposal_dir / "metadata.json").read_text(encoding="utf-8")
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    ok, error = system.transition_status(proposal_id, "approved", actor="fictional-actor")
    loaded = system.lifecycle_manager._load_metadata(proposal_id)

    assert ok is False
    assert "Invalid transition" in (error or "")
    assert loaded is not None
    assert loaded["status"] == "research"
    assert (proposal_dir / "metadata.json").read_text(encoding="utf-8") == before
