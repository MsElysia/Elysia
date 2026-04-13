"""Artifact policy tests for GuardianCore.run_once()."""

import json
from pathlib import Path

import pytest

try:
    from project_guardian.core import GuardianCore
    from project_guardian.trust import TrustDecision, GOVERNANCE_MUTATION
    from project_guardian.memory import MemoryCore
    MODULES_AVAILABLE = True
except ImportError:  # pragma: no cover - module not available in some environments
    MODULES_AVAILABLE = False
    pytestmark = pytest.mark.skip("Core modules not available")


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal tmp project tree rooted at tmp_path."""
    (tmp_path / "TASKS").mkdir()
    (tmp_path / "MUTATIONS").mkdir()
    (tmp_path / "REPORTS").mkdir()

    control = tmp_path / "CONTROL.md"
    control.write_text("CURRENT_TASK: TASK-0001\n")
    return tmp_path


def _make_core(tmp_project):
    """Instantiate GuardianCore rooted at tmp_project."""
    config = {"enable_vector_memory": False, "enable_resource_monitoring": False}
    core = GuardianCore(
        config=config,
        control_path=tmp_project / "CONTROL.md",
        tasks_dir=tmp_project / "TASKS",
        mutations_dir=tmp_project / "MUTATIONS",
    )
    return core


def _write_apply_mutation_task(tmp_project, allow_gov: bool = True):
    task_path = tmp_project / "TASKS" / "TASK-0001.md"
    task_path.write_text(
        "TASK_TYPE: APPLY_MUTATION\n"
        "MUTATION_FILE: MUTATIONS/test.json\n"
        f"ALLOW_GOVERNANCE_MUTATION: {'true' if allow_gov else 'false'}\n"
    )


def _write_mutation_payload(tmp_project, touched_paths, changes):
    payload = {"touched_paths": touched_paths, "changes": changes, "summary": "test"}
    (tmp_project / "MUTATIONS" / "test.json").write_text(json.dumps(payload))


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="Core not available")
class TestArtifactPolicyRunOnce:
    def test_run_once_review_writes_only_run_once_artifacts_and_queue(self, tmp_project, monkeypatch):
        """APPLY_MUTATION review: only run_once artifacts + review queue allowed."""
        _write_apply_mutation_task(tmp_project, allow_gov=True)
        # Protected path so we go through governance path
        _write_mutation_payload(
            tmp_project,
            ["CONTROL.md"],
            [{"path": "CONTROL.md", "content": "CURRENT_TASK: NONE\n"}],
        )

        core = _make_core(tmp_project)

        # Force TrustMatrix review for GOVERNANCE_MUTATION
        def fake_validate(component, action, context):
            if action == GOVERNANCE_MUTATION:
                return TrustDecision(
                    allowed=False,
                    decision="review",
                    reason_code="REVIEW_REQUIRED",
                    message="test review",
                    risk_score=0.6,
                )
            return TrustDecision(True, "allow", "ALLOWED", "", 0.1)

        core.trust.validate_trust_for_action = fake_validate

        result = core.run_once()
        assert result.get("status") == "needs_review"

        reports = tmp_project / "REPORTS"
        # Allowed run_once artifacts
        assert (reports / "run_once_last.json").exists()
        # history directory may or may not exist depending on retention config; if it exists, it should have at least one file
        history_dir = reports / "run_once_history"
        if history_dir.exists():
            assert any(history_dir.iterdir())

        # Review queue artifact allowed
        queue_path = reports / "review_queue.jsonl"
        assert queue_path.exists()
        assert queue_path.read_text(encoding="utf-8").strip()  # at least one line

        # Forbidden artifacts
        assert not (reports / "acceptance_last.json").exists()
        assert not (reports / "acceptance_last.log").exists()
        assert not (reports / "subprocess_background.jsonl").exists()

        approval_store = reports / "approval_store.json"
        # approval store must not be written as a result of a review-only run_once
        assert not approval_store.exists()

        # No backups / file changes
        assert not (tmp_project / "guardian_backups").exists()
        # CONTROL.md unchanged
        assert (tmp_project / "CONTROL.md").read_text() == "CURRENT_TASK: TASK-0001\n"

    def test_run_once_denied_writes_only_run_once_artifacts(self, tmp_project, monkeypatch):
        """APPLY_MUTATION deny: only run_once artifacts allowed, nothing else."""
        _write_apply_mutation_task(tmp_project, allow_gov=True)
        # Use invalid path to trigger path denial early
        _write_mutation_payload(
            tmp_project,
            ["../evil.txt"],
            [{"path": "../evil.txt", "content": "malicious"}],
        )

        core = _make_core(tmp_project)

        result = core.run_once()
        assert result.get("status") == "denied"

        reports = tmp_project / "REPORTS"
        assert (reports / "run_once_last.json").exists()
        history_dir = reports / "run_once_history"
        if history_dir.exists():
            assert any(history_dir.iterdir())

        # No review queue append expected for deny
        queue_path = reports / "review_queue.jsonl"
        if queue_path.exists():
            # If file exists from previous runs, ensure it wasn't modified in this test by checking size is zero or content unchanged.
            # For simplicity in isolated tmp, we expect it not to exist.
            assert False, "review_queue.jsonl should not be created on deny"

        # Forbidden artifacts
        assert not (reports / "acceptance_last.json").exists()
        assert not (reports / "acceptance_last.log").exists()
        assert not (reports / "subprocess_background.jsonl").exists()
        assert not (reports / "approval_store.json").exists()
        assert not (tmp_project / "guardian_backups").exists()

    def test_run_once_allow_mutation_creates_backups_and_changes(self, tmp_project, monkeypatch):
        """APPLY_MUTATION allow: backups + target changes + run_once artifacts allowed."""
        _write_apply_mutation_task(tmp_project, allow_gov=False)
        # Non-protected, safe file
        target = tmp_project / "safe.py"
        target.write_text("print('old')\n")

        _write_mutation_payload(
            tmp_project,
            ["safe.py"],
            [{"path": "safe.py", "content": "print('new')\n"}],
        )

        core = _make_core(tmp_project)

        # Ensure TrustMatrix allows (for non-governance this may not be used, but safe to stub)
        def fake_validate(component, action, context):
            return TrustDecision(True, "allow", "ALLOWED", "", 0.1)

        core.trust.validate_trust_for_action = fake_validate

        result = core.run_once()
        assert result.get("status") == "success"

        reports = tmp_project / "REPORTS"
        assert (reports / "run_once_last.json").exists()
        history_dir = reports / "run_once_history"
        if history_dir.exists():
            assert any(history_dir.iterdir())

        # Backups allowed
        backups_dir = tmp_project / "guardian_backups"
        assert backups_dir.exists()
        assert any(backups_dir.rglob("*.bak.*"))

        # Target changed
        assert target.read_text() == "print('new')\n"