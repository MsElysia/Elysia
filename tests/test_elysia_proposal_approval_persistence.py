"""Runtime proposal approval must persist identity on the same authorized write."""

from __future__ import annotations

import json
from pathlib import Path

from elysia.core.proposal_system import ProposalSystem
from elysia.events import EventBus


def _write_proposal(root: Path, proposal_id: str, status: str) -> Path:
    proposal_dir = root / proposal_id
    proposal_dir.mkdir()
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional approval probe",
        "status": status,
        "created_by": "probe",
        "created_at": "2026-10-29T00:00:00Z",
        "history": [],
    }
    (proposal_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return proposal_dir


def _load(proposal_dir: Path) -> dict:
    return json.loads((proposal_dir / "metadata.json").read_text(encoding="utf-8"))


def test_approve_persists_approver_and_status(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    proposal_id = "fictional-approval-probe-20261029"
    proposal_dir = _write_proposal(root, proposal_id, "proposal")
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    ok, error = system.approve_proposal(proposal_id, "fictional-approver")

    assert ok is True
    assert error is None
    stored = system.get_proposal(proposal_id)
    assert stored is not None
    assert stored["status"] == "approved"
    assert stored["approval_status"] == "approved"
    assert stored["approved_by"] == "fictional-approver"
    assert stored["approved_at"]
    summaries = [entry["change_summary"] for entry in stored["history"]]
    assert "Proposal approved" in summaries
    assert "Status changed from proposal to approved" in summaries
    disk = _load(proposal_dir)
    assert disk["approved_by"] == "fictional-approver"
    assert disk["status"] == "approved"


def test_reject_persists_reason_and_status(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    proposal_id = "fictional-reject-probe-20261029"
    _write_proposal(root, proposal_id, "proposal")
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    ok, error = system.reject_proposal(
        proposal_id, "fictional mismatch", "fictional-rejector"
    )

    assert ok is True
    assert error is None
    stored = system.get_proposal(proposal_id)
    assert stored["status"] == "rejected"
    assert stored["approval_status"] == "rejected"
    assert stored["rejection_reason"] == "fictional mismatch"
    assert stored["last_updated_by"] == "fictional-rejector"
    summaries = [entry["change_summary"] for entry in stored["history"]]
    assert "Proposal rejected: fictional mismatch" in summaries


def test_invalid_approve_leaves_disk_unchanged(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    proposal_id = "fictional-research-probe-20261029"
    proposal_dir = _write_proposal(root, proposal_id, "research")
    before = (proposal_dir / "metadata.json").read_text(encoding="utf-8")
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    ok, error = system.approve_proposal(proposal_id, "fictional-approver")

    assert ok is False
    assert error == "Invalid transition from research to approved"
    after = _load(proposal_dir)
    assert after["status"] == "research"
    assert "approval_status" not in after
    assert "approved_by" not in after
    assert after["history"] == []
    assert (proposal_dir / "metadata.json").read_text(encoding="utf-8") == before


def test_missing_proposal_does_not_create_files(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    system = ProposalSystem(
        proposals_root=root, event_bus=EventBus(), enable_watcher=False
    )

    ok, error = system.approve_proposal("missing-fictional-proposal", "fictional-approver")

    assert ok is False
    assert error == "Proposal not found"
    assert not (root / "missing-fictional-proposal").exists()
    assert list(root.iterdir()) == []
