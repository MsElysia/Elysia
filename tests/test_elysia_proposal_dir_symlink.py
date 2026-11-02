"""Watcher and validator must not follow a planted proposal-directory symlink."""

from __future__ import annotations

import json
from pathlib import Path

from elysia.core.proposal_system import (
    ProposalLifecycleManager,
    ProposalSystem,
    ProposalValidator,
    ProposalWatcher,
    _regular_proposal_dir,
)
from elysia.events import EventBus


def _write_outside_proposal(path: Path, extra: dict | None = None) -> None:
    metadata = {
        "proposal_id": "fictional-dir-symlink-20261102",
        "title": "Fictional directory symlink probe",
        "status": "proposal",
        "created_by": "probe",
        "created_at": "2026-11-02T00:00:00Z",
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
        "created_at": "2026-11-02T00:00:00Z",
        "history": [],
    }
    (proposal_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return proposal_dir


def test_regular_proposal_dir_rejects_directory_symlink(tmp_path):
    outside = tmp_path / "outside-proposal"
    outside.mkdir()
    link = tmp_path / "fictional-dir-symlink-20261102"
    link.symlink_to(outside)

    assert _regular_proposal_dir(link) is None
    assert _regular_proposal_dir(outside) == outside
    assert _regular_proposal_dir(tmp_path / "missing-proposal") == (
        tmp_path / "missing-proposal"
    )


def test_validator_rejects_directory_symlink_without_reading_outside(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "outside-proposal"
    _write_outside_proposal(outside)
    before = (outside / "metadata.json").read_text(encoding="utf-8")
    proposal_dir = _plant_dir_symlink(
        root, outside, "fictional-dir-symlink-20261102"
    )
    validator = ProposalValidator(root)

    valid, error = validator.validate_proposal(proposal_dir)

    assert valid is False
    assert error == "Proposal directory is not a regular directory"
    assert "SHOULD-NOT-BE-READ" not in (error or "")
    assert (outside / "metadata.json").read_text(encoding="utf-8") == before
    assert json.loads(before)["secret_marker"] == "SHOULD-NOT-BE-READ"
    assert proposal_dir.is_symlink()
    assert not (proposal_dir / "metadata.json").is_symlink()


def test_watcher_scan_does_not_emit_created_for_directory_symlink(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "outside-proposal"
    _write_outside_proposal(outside)
    before = (outside / "metadata.json").read_text(encoding="utf-8")
    proposal_id = "fictional-dir-symlink-20261102"
    _plant_dir_symlink(root, outside, proposal_id)
    bus = EventBus()
    events = []
    bus.subscribe(lambda event: events.append(event))
    validator = ProposalValidator(root)
    lifecycle = ProposalLifecycleManager(root, bus)
    watcher = ProposalWatcher(
        root, validator, lifecycle, bus, check_interval=99
    )

    watcher._scan_proposals()

    created = [event for event in events if event.type == "proposal_created"]
    assert created == []
    assert proposal_id not in watcher._known_proposals
    assert all(
        event.payload.get("proposal_id") != proposal_id
        or "SHOULD-NOT-BE-READ" not in str(event.payload)
        for event in events
    )
    assert (outside / "metadata.json").read_text(encoding="utf-8") == before
    assert json.loads(before)["secret_marker"] == "SHOULD-NOT-BE-READ"


def test_watcher_scan_still_detects_regular_inroot_proposal(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "outside-proposal"
    _write_outside_proposal(outside)
    _plant_dir_symlink(root, outside, "fictional-dir-symlink-20261102")
    regular_id = "fictional-regular-20261102"
    _write_regular_proposal(root, regular_id, "research")
    bus = EventBus()
    events = []
    bus.subscribe(lambda event: events.append(event))
    validator = ProposalValidator(root)
    lifecycle = ProposalLifecycleManager(root, bus)
    watcher = ProposalWatcher(
        root, validator, lifecycle, bus, check_interval=99
    )

    watcher._scan_proposals()

    created_ids = [
        event.payload.get("proposal_id")
        for event in events
        if event.type == "proposal_created"
    ]
    assert created_ids == [regular_id]
    assert watcher._known_proposals == {regular_id}


def test_missing_metadata_still_fails_structure_as_missing(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    proposal_dir = root / "fictional-empty-20261102"
    proposal_dir.mkdir()
    validator = ProposalValidator(root)

    valid, error = validator.validate_structure(proposal_dir)

    assert valid is False
    assert error == "metadata.json missing"


def test_inroot_regular_proposal_still_validates(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    proposal_id = "fictional-regular-20261102"
    proposal_dir = _write_regular_proposal(root, proposal_id, "research")
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    valid, error = system.validator.validate_proposal(proposal_dir)

    assert valid is True
    assert error is None
    stored = system.get_proposal(proposal_id)
    assert stored is not None
    assert stored["status"] == "research"
    assert not proposal_dir.is_symlink()
