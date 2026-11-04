"""_load_metadata/_save_metadata must not follow a planted proposal-directory symlink."""

from __future__ import annotations

import json
from pathlib import Path

from elysia.core.proposal_system import ProposalSystem, _regular_proposal_dir
from elysia.events import EventBus


def _write_outside_proposal(path: Path, extra: dict | None = None) -> None:
    metadata = {
        "proposal_id": "fictional-loadsave-dir-symlink-20261104",
        "title": "Fictional directory symlink load/save probe",
        "status": "proposal",
        "created_by": "probe",
        "created_at": "2026-11-04T00:00:00Z",
        "secret_marker": "SHOULD-NOT-BE-READ",
        "history": [],
    }
    if extra:
        metadata.update(extra)
    path.mkdir()
    (path / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def _plant_dir_symlink(root: Path, outside: Path, proposal_id: str) -> Path:
    link = root / proposal_id
    link.symlink_to(outside)
    return link


def _write_regular_proposal(root: Path, proposal_id: str, status: str) -> Path:
    proposal_dir = root / proposal_id
    proposal_dir.mkdir()
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional in-root proposal",
        "status": status,
        "created_by": "probe",
        "created_at": "2026-11-04T00:00:00Z",
        "history": [],
    }
    (proposal_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return proposal_dir


def test_regular_proposal_dir_rejects_directory_symlink(tmp_path):
    outside = tmp_path / "outside-proposal"
    outside.mkdir()
    link = tmp_path / "fictional-loadsave-dir-symlink-20261104"
    link.symlink_to(outside)

    assert _regular_proposal_dir(link) is None
    assert _regular_proposal_dir(outside) == outside
    assert _regular_proposal_dir(tmp_path / "missing-proposal") == (
        tmp_path / "missing-proposal"
    )


def test_load_metadata_returns_none_for_directory_symlink_without_reading_outside(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "outside-proposal"
    _write_outside_proposal(outside)
    before = (outside / "metadata.json").read_text(encoding="utf-8")
    proposal_id = "fictional-loadsave-dir-symlink-20261104"
    proposal_dir = _plant_dir_symlink(root, outside, proposal_id)
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    loaded = system.lifecycle_manager._load_metadata(proposal_id)

    assert loaded is None
    assert "SHOULD-NOT-BE-READ" not in json.dumps(loaded)
    assert (outside / "metadata.json").read_text(encoding="utf-8") == before
    assert json.loads(before)["secret_marker"] == "SHOULD-NOT-BE-READ"
    assert proposal_dir.is_symlink()
    assert not (proposal_dir / "metadata.json").is_symlink()


def test_save_metadata_rejects_directory_symlink_and_does_not_write_outside(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "outside-proposal"
    _write_outside_proposal(outside, extra={"status": "research"})
    before = (outside / "metadata.json").read_text(encoding="utf-8")
    proposal_id = "fictional-loadsave-dir-symlink-20261104"
    proposal_dir = _plant_dir_symlink(root, outside, proposal_id)
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    ok = system.lifecycle_manager._save_metadata(
        proposal_id,
        {
            "proposal_id": proposal_id,
            "title": "Fictional directory symlink save",
            "status": "design",
            "created_by": "probe",
            "created_at": "2026-11-04T00:00:00Z",
        },
    )

    assert ok is False
    assert json.loads((outside / "metadata.json").read_text(encoding="utf-8"))[
        "status"
    ] == "research"
    assert (outside / "metadata.json").read_text(encoding="utf-8") == before
    assert proposal_dir.is_symlink()


def test_approve_rejects_directory_symlink_and_leaves_outside_unchanged(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "outside-proposal"
    _write_outside_proposal(outside)
    before = (outside / "metadata.json").read_text(encoding="utf-8")
    proposal_id = "fictional-loadsave-dir-symlink-20261104"
    proposal_dir = _plant_dir_symlink(root, outside, proposal_id)
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    ok, error = system.approve_proposal(proposal_id, "fictional-approver")

    assert ok is False
    assert error == "Proposal not found"
    after = json.loads((outside / "metadata.json").read_text(encoding="utf-8"))
    assert after["status"] == "proposal"
    assert "approved_by" not in after
    assert after["secret_marker"] == "SHOULD-NOT-BE-READ"
    assert (outside / "metadata.json").read_text(encoding="utf-8") == before
    assert proposal_dir.is_symlink()


def test_missing_proposal_load_still_returns_none(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    assert system.lifecycle_manager._load_metadata("fictional-missing-20261104") is None
    ok, error = system.approve_proposal("fictional-missing-20261104", "fictional-approver")
    assert ok is False
    assert error == "Proposal not found"
    assert list(root.iterdir()) == []


def test_inroot_regular_load_save_and_transition_still_persist(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    proposal_id = "fictional-regular-20261104"
    proposal_dir = _write_regular_proposal(root, proposal_id, "research")
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    loaded = system.lifecycle_manager._load_metadata(proposal_id)
    ok, error = system.transition_status(proposal_id, "design", actor="fictional-actor")

    assert loaded is not None
    assert loaded["status"] == "research"
    assert loaded["proposal_id"] == proposal_id
    assert ok is True
    assert error is None
    stored = system.lifecycle_manager._load_metadata(proposal_id)
    assert stored is not None
    assert stored["status"] == "design"
    assert stored["last_updated_by"] == "fictional-actor"
    disk = json.loads((proposal_dir / "metadata.json").read_text(encoding="utf-8"))
    assert disk["status"] == "design"
    assert disk["last_updated_by"] == "fictional-actor"
    assert not proposal_dir.is_symlink()
    assert not (proposal_dir / "metadata.json").is_symlink()
