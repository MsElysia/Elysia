"""Proposal IDs must stay inside proposals_root on load, save, and get."""

from __future__ import annotations

import json
from pathlib import Path

from elysia.core.proposal_system import ProposalSystem, _confined_proposal_dir
from elysia.events import EventBus


def _write_proposal(root: Path, proposal_id: str, status: str, extra: dict | None = None) -> Path:
    proposal_dir = root / proposal_id
    proposal_dir.mkdir()
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional confinement probe",
        "status": status,
        "created_by": "probe",
        "created_at": "2026-10-30T00:00:00Z",
        "history": [],
    }
    if extra:
        metadata.update(extra)
    (proposal_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return proposal_dir


def test_confined_dir_rejects_separators_and_parent(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    assert _confined_proposal_dir(root, "fictional-inroot-20261030") == (root / "fictional-inroot-20261030").resolve()
    assert _confined_proposal_dir(root, "../secret-outside") is None
    assert _confined_proposal_dir(root, "..\\secret-outside") is None
    assert _confined_proposal_dir(root, "nested/id") is None
    assert _confined_proposal_dir(root, str(tmp_path / "secret-outside")) is None
    assert _confined_proposal_dir(root, "") is None
    assert _confined_proposal_dir(root, ".") is None
    assert _confined_proposal_dir(root, "..") is None
    # Substring dots are a legal single path component, not a traversal.
    dotted = _confined_proposal_dir(root, "foo..bar")
    assert dotted == (root / "foo..bar").resolve()


def test_get_rejects_parent_escape_and_leaves_outside_unread(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "secret-outside"
    _write_proposal(
        tmp_path,
        "secret-outside",
        "proposal",
        extra={"secret_marker": "SHOULD-NOT-BE-READ"},
    )
    before = (outside / "metadata.json").read_text(encoding="utf-8")
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    got = system.get_proposal("../secret-outside")

    assert got is None
    assert (outside / "metadata.json").read_text(encoding="utf-8") == before
    assert list(root.iterdir()) == []


def test_approve_rejects_parent_escape_and_leaves_outside_unchanged(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    outside = tmp_path / "secret-outside"
    _write_proposal(tmp_path, "secret-outside", "proposal")
    before = (outside / "metadata.json").read_text(encoding="utf-8")
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    ok, error = system.approve_proposal("../secret-outside", "fictional-approver")

    assert ok is False
    assert error == "Proposal not found"
    after = json.loads((outside / "metadata.json").read_text(encoding="utf-8"))
    assert after["status"] == "proposal"
    assert "approved_by" not in after
    assert (outside / "metadata.json").read_text(encoding="utf-8") == before
    assert not (root / "secret-outside").exists()


def test_save_rejects_parent_escape_and_does_not_mkdir_outside(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    ok = system.lifecycle_manager._save_metadata(
        "../mkdir-escape",
        {
            "proposal_id": "mkdir-escape",
            "title": "Fictional mkdir escape",
            "status": "research",
            "created_by": "probe",
            "created_at": "2026-10-30T00:00:00Z",
        },
    )

    assert ok is False
    assert not (tmp_path / "mkdir-escape").exists()
    assert list(root.iterdir()) == []


def test_inroot_transition_still_persists(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    proposal_id = "fictional-inroot-20261030"
    proposal_dir = _write_proposal(root, proposal_id, "research")
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
