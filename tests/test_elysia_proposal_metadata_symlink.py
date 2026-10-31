"""Valid proposal IDs must not follow a planted metadata.json symlink."""

from __future__ import annotations

import json
from pathlib import Path

from elysia.core.proposal_system import ProposalSystem, _regular_metadata_file
from elysia.events import EventBus


def _write_outside_metadata(path: Path, extra: dict | None = None) -> None:
    metadata = {
        "proposal_id": "fictional-symlink-20261031",
        "title": "Fictional symlink probe",
        "status": "proposal",
        "created_by": "probe",
        "created_at": "2026-10-31T00:00:00Z",
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
        "created_at": "2026-10-31T00:00:00Z",
        "history": [],
    }
    (proposal_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return proposal_dir


def test_regular_metadata_file_rejects_symlink_leaf(tmp_path):
    proposal_dir = tmp_path / "fictional-symlink-20261031"
    proposal_dir.mkdir()
    outside = tmp_path / "secret-outside.json"
    outside.write_text("{}", encoding="utf-8")
    (proposal_dir / "metadata.json").symlink_to(outside)

    assert _regular_metadata_file(proposal_dir) is None
    assert _regular_metadata_file(tmp_path / "missing-proposal") == (
        tmp_path / "missing-proposal" / "metadata.json"
    )


def test_get_rejects_metadata_symlink_and_leaves_outside_unread(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "secret-outside.json"
    _write_outside_metadata(outside)
    before = outside.read_text(encoding="utf-8")
    proposal_id = "fictional-symlink-20261031"
    _plant_symlink_proposal(root, outside, proposal_id)
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    got = system.get_proposal(proposal_id)

    assert got is None
    assert outside.read_text(encoding="utf-8") == before
    assert json.loads(before)["secret_marker"] == "SHOULD-NOT-BE-READ"


def test_approve_rejects_metadata_symlink_and_leaves_outside_unchanged(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "secret-outside.json"
    _write_outside_metadata(outside)
    before = outside.read_text(encoding="utf-8")
    proposal_id = "fictional-symlink-20261031"
    proposal_dir = _plant_symlink_proposal(root, outside, proposal_id)
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    ok, error = system.approve_proposal(proposal_id, "fictional-approver")

    assert ok is False
    assert error == "Proposal not found"
    after = json.loads(outside.read_text(encoding="utf-8"))
    assert after["status"] == "proposal"
    assert "approved_by" not in after
    assert after["secret_marker"] == "SHOULD-NOT-BE-READ"
    assert outside.read_text(encoding="utf-8") == before
    assert (proposal_dir / "metadata.json").is_symlink()


def test_save_rejects_metadata_symlink_and_does_not_write_outside(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "secret-outside.json"
    _write_outside_metadata(outside, extra={"status": "research"})
    before = outside.read_text(encoding="utf-8")
    proposal_id = "fictional-symlink-20261031"
    _plant_symlink_proposal(root, outside, proposal_id)
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    ok = system.lifecycle_manager._save_metadata(
        proposal_id,
        {
            "proposal_id": proposal_id,
            "title": "Fictional symlink save",
            "status": "design",
            "created_by": "probe",
            "created_at": "2026-10-31T00:00:00Z",
        },
    )

    assert ok is False
    assert json.loads(outside.read_text(encoding="utf-8"))["status"] == "research"
    assert outside.read_text(encoding="utf-8") == before


def test_list_excludes_symlink_metadata(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "secret-outside.json"
    _write_outside_metadata(outside)
    _plant_symlink_proposal(root, outside, "fictional-symlink-20261031")
    _write_regular_proposal(root, "fictional-regular-20261031", "research")
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    listed = system.list_proposals()

    assert [p["proposal_id"] for p in listed] == ["fictional-regular-20261031"]
    assert all(p.get("secret_marker") != "SHOULD-NOT-BE-READ" for p in listed)


def test_inroot_regular_transition_still_persists(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    proposal_id = "fictional-regular-20261031"
    proposal_dir = _write_regular_proposal(root, proposal_id, "research")
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    ok, error = system.transition_status(proposal_id, "design", actor="fictional-actor")

    assert ok is True
    assert error is None
    stored = system.get_proposal(proposal_id)
    assert stored is not None
    assert stored["status"] == "design"
    assert stored["last_updated_by"] == "fictional-actor"
    disk = json.loads((proposal_dir / "metadata.json").read_text(encoding="utf-8"))
    assert disk["status"] == "design"
    assert disk["last_updated_by"] == "fictional-actor"
    assert not (proposal_dir / "metadata.json").is_symlink()
