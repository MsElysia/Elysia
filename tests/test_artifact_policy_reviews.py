"""Artifact policy tests for ReviewQueue + ApprovalStore."""

from pathlib import Path

import pytest

try:
    from project_guardian.review_queue import ReviewQueue
    from project_guardian.approval_store import ApprovalStore
    MODULES_AVAILABLE = True
except ImportError:  # pragma: no cover
    MODULES_AVAILABLE = False
    pytestmark = pytest.mark.skip("Review/approval modules not available")


@pytest.fixture
def tmp_reports(tmp_path):
    reports = tmp_path / "REPORTS"
    reports.mkdir()
    return reports


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="Modules not available")
class TestArtifactPolicyReviews:
    def test_approve_changes_only_approval_store_and_queue_status(self, tmp_reports):
        """Approvals may touch approval_store + review_queue status, nothing else."""
        queue_path = tmp_reports / "review_queue.jsonl"

        # Create a pending request
        rq = ReviewQueue(queue_path=str(queue_path))
        request_id = rq.enqueue(
            component="SubprocessRunner",
            action="subprocess_execution",
            context={"example": True},
        )

        # Create ApprovalStore
        store_path = tmp_reports / "approval_store.json"
        approval_store = ApprovalStore(path=str(store_path))

        # Approve the request
        approval_store.approve(
            request_id=request_id,
            context={"component": "SubprocessRunner", "action": "subprocess_execution", "example": True},
            approver="tester",
            notes="ok",
        )

        # Update queue status
        rq.update_status(request_id=request_id, new_status="approved")

        # Allowed artifacts
        assert store_path.exists()
        assert queue_path.exists()

        # Forbidden artifacts in this flow
        # (We only assert that certain well-known ones do not appear under this tmp REPORTS tree.)
        assert not (tmp_reports / "acceptance_last.json").exists()
        assert not (tmp_reports / "acceptance_last.log").exists()
        assert not (tmp_reports / "subprocess_background.jsonl").exists()

        # No backups / guardian_backups created in this tree
        root = tmp_reports.parent
        assert not (root / "guardian_backups").exists()