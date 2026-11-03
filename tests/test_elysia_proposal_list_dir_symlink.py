"""list_proposals/get_proposal must not follow a planted proposal-directory symlink."""

from __future__ import annotations

import json
from pathlib import Path

from elysia.core.proposal_system import ProposalSystem, _regular_proposal_dir
from elysia.events import EventBus


def _write_outside_proposal(path: Path, extra: dict | None = None) -> None:
    metadata = {
        "proposal_id": "fictional-list-dir-symlink-20261103",
        "title": "Fictional directory symlink list/get probe",
        "status": "proposal",
        "created_by": "probe",
        "created_at": "2026-11-03T00:00:00Z",
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
        "created_at": "2026-11-03T00:00:00Z",
        "history": [],
    }
    (proposal_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return proposal_dir


def test_regular_proposal_dir_rejects_directory_symlink(tmp_path):
    outside = tmp_path / "outside-proposal"
    outside.mkdir()
    link = tmp_path / "fictional-list-dir-symlink-20261103"
    link.symlink_to(outside)

    assert _regular_proposal_dir(link) is None
    assert _regular_proposal_dir(outside) == outside
    assert _regular_proposal_dir(tmp_path / "missing-proposal") == (
        tmp_path / "missing-proposal"
    )


def test_get_proposal_returns_none_for_directory_symlink_without_reading_outside(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "outside-proposal"
    _write_outside_proposal(outside)
    before = (outside / "metadata.json").read_text(encoding="utf-8")
    proposal_id = "fictional-list-dir-symlink-20261103"
    proposal_dir = _plant_dir_symlink(root, outside, proposal_id)
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    got = system.get_proposal(proposal_id)

    assert got is None
    assert "SHOULD-NOT-BE-READ" not in json.dumps(got)
    assert (outside / "metadata.json").read_text(encoding="utf-8") == before
    assert json.loads(before)["secret_marker"] == "SHOULD-NOT-BE-READ"
    assert proposal_dir.is_symlink()
    assert not (proposal_dir / "metadata.json").is_symlink()


def test_list_proposals_omits_directory_symlink_and_keeps_regular(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "outside-proposal"
    _write_outside_proposal(outside)
    before = (outside / "metadata.json").read_text(encoding="utf-8")
    _plant_dir_symlink(root, outside, "fictional-list-dir-symlink-20261103")
    regular_id = "fictional-regular-20261103"
    _write_regular_proposal(root, regular_id, "research")
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    listed = system.list_proposals()

    listed_ids = [item.get("proposal_id") for item in listed]
    assert listed_ids == [regular_id]
    assert all(item.get("secret_marker") != "SHOULD-NOT-BE-READ" for item in listed)
    assert "SHOULD-NOT-BE-READ" not in json.dumps(listed)
    assert (outside / "metadata.json").read_text(encoding="utf-8") == before


def test_list_proposals_status_filter_still_matches_regular_only(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "outside-proposal"
    _write_outside_proposal(outside)
    _plant_dir_symlink(root, outside, "fictional-list-dir-symlink-20261103")
    _write_regular_proposal(root, "fictional-regular-20261103", "research")
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    research = system.list_proposals(status_filter="research")
    proposal = system.list_proposals(status_filter="proposal")

    assert [item.get("proposal_id") for item in research] == [
        "fictional-regular-20261103"
    ]
    assert proposal == []


def test_missing_proposal_still_returns_none(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    assert system.get_proposal("fictional-missing-20261103") is None
    assert system.list_proposals() == []


def test_inroot_regular_proposal_still_lists_and_gets(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    proposal_id = "fictional-regular-20261103"
    proposal_dir = _write_regular_proposal(root, proposal_id, "research")
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    stored = system.get_proposal(proposal_id)
    listed = system.list_proposals()

    assert stored is not None
    assert stored["status"] == "research"
    assert stored["proposal_id"] == proposal_id
    assert [item.get("proposal_id") for item in listed] == [proposal_id]
    assert not proposal_dir.is_symlink()
