"""Watcher and validator must not follow a planted metadata.json symlink."""

from __future__ import annotations

import json
from pathlib import Path

from elysia.core.proposal_system import (
    ProposalLifecycleManager,
    ProposalSystem,
    ProposalValidator,
    ProposalWatcher,
    _regular_metadata_file,
)
from elysia.events import EventBus


def _write_outside_metadata(path: Path, extra: dict | None = None) -> None:
    metadata = {
        "proposal_id": "fictional-watch-symlink-20261101",
        "title": "Fictional watcher symlink probe",
        "status": "proposal",
        "created_by": "probe",
        "created_at": "2026-11-01T00:00:00Z",
        "secret_marker": "SHOULD-NOT-BE-READ",
        "history": [],
    }
    if extra:
        metadata.update(extra)
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def _plant_symlink_proposal(root: Path, outside: Path, proposal_id: str) -> Path:
    proposal_dir = root / proposal_id
    proposal_dir.mkdir()
    (proposal_dir / "metadata.json").symlink_to(outside)
    return proposal_dir


def _write_regular_proposal(root: Path, proposal_id: str, status: str) -> Path:
    proposal_dir = root / proposal_id
    proposal_dir.mkdir()
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional in-root proposal",
        "status": status,
        "created_by": "probe",
        "created_at": "2026-11-01T00:00:00Z",
        "history": [],
    }
    (proposal_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return proposal_dir


def test_regular_metadata_file_rejects_symlink_leaf(tmp_path):
    proposal_dir = tmp_path / "fictional-watch-symlink-20261101"
    proposal_dir.mkdir()
    outside = tmp_path / "secret-outside.json"
    outside.write_text("{}", encoding="utf-8")
    (proposal_dir / "metadata.json").symlink_to(outside)

    assert _regular_metadata_file(proposal_dir) is None
    assert _regular_metadata_file(tmp_path / "missing-proposal") == (
        tmp_path / "missing-proposal" / "metadata.json"
    )


def test_validator_rejects_metadata_symlink_without_reading_outside(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "secret-outside.json"
    _write_outside_metadata(outside)
    before = outside.read_text(encoding="utf-8")
    proposal_dir = _plant_symlink_proposal(
        root, outside, "fictional-watch-symlink-20261101"
    )
    validator = ProposalValidator(root)

    valid, error = validator.validate_proposal(proposal_dir)

    assert valid is False
    assert error == "metadata.json is not a regular file"
    assert "SHOULD-NOT-BE-READ" not in (error or "")
    assert outside.read_text(encoding="utf-8") == before
    assert json.loads(before)["secret_marker"] == "SHOULD-NOT-BE-READ"
    assert (proposal_dir / "metadata.json").is_symlink()


def test_watcher_scan_does_not_emit_created_for_metadata_symlink(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "secret-outside.json"
    _write_outside_metadata(outside)
    before = outside.read_text(encoding="utf-8")
    proposal_id = "fictional-watch-symlink-20261101"
    _plant_symlink_proposal(root, outside, proposal_id)
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
    assert outside.read_text(encoding="utf-8") == before
    assert json.loads(before)["secret_marker"] == "SHOULD-NOT-BE-READ"


def test_watcher_scan_still_detects_regular_inroot_proposal(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "secret-outside.json"
    _write_outside_metadata(outside)
    _plant_symlink_proposal(root, outside, "fictional-watch-symlink-20261101")
    regular_id = "fictional-regular-20261101"
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
    proposal_dir = root / "fictional-empty-20261101"
    proposal_dir.mkdir()
    validator = ProposalValidator(root)

    valid, error = validator.validate_structure(proposal_dir)

    assert valid is False
    assert error == "metadata.json missing"


def test_inroot_regular_proposal_still_validates(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    proposal_id = "fictional-regular-20261101"
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
    assert not (proposal_dir / "metadata.json").is_symlink()
