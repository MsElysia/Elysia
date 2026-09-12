"""Artifact policy tests for GuardianCore.run_once()."""

import json
from pathlib import Path

import pytest

try:
    from project_guardian.core import GuardianCore
    from project_guardian.trust import TrustDecision, GOVERNANCE_MUTATION
    from project_guardian.review_queue import ReviewQueue
    from project_guardian.approval_store import ApprovalStore
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


def _isolated_core_config() -> dict:
    return {
        "enable_vector_memory": False,
        "enable_resource_monitoring": False,
        "_test_skip_external_storage": True,
    }


def _bind_isolated_reports(core: GuardianCore, tmp_project: Path) -> Path:
    """Point mutation/review paths at tmp_project (not repo REPORTS/)."""
    reports = tmp_project / "REPORTS"
    review_queue = ReviewQueue(
        queue_file=reports / "review_queue.jsonl",
        memory=core.memory,
    )
    approval_store = ApprovalStore(store_file=reports / "approval_store.json")
    core.review_queue = review_queue
    core.approval_store = approval_store
    core.mutation.review_queue = review_queue
    core.mutation.approval_store = approval_store
    core.mutation.repo_root = tmp_project
    return reports


def _make_core(tmp_project):
    """Instantiate GuardianCore rooted at tmp_project with isolated stores."""
    core = GuardianCore(
        config=_isolated_core_config(),
        control_path=tmp_project / "CONTROL.md",
        tasks_dir=tmp_project / "TASKS",
        mutations_dir=tmp_project / "MUTATIONS",
    )
    _bind_isolated_reports(core, tmp_project)
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


def _assert_passive_run_once_result(result: dict) -> None:
    """core.run_once() returns a passive dict; UI writes run_once_last.json separately."""
    assert isinstance(result, dict)
    assert "status" in result
    assert "timestamp" in result


def _assert_no_forbidden_artifacts(reports: Path) -> None:
    assert not (reports / "acceptance_last.json").exists()
    assert not (reports / "acceptance_last.log").exists()
    assert not (reports / "subprocess_background.jsonl").exists()


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="Core not available")
class TestArtifactPolicyRunOnce:
    def test_run_once_review_writes_only_run_once_artifacts_and_queue(self, tmp_project, monkeypatch):
        """APPLY_MUTATION review: passive result + review queue only (no apply)."""
        _write_apply_mutation_task(tmp_project, allow_gov=True)
        _write_mutation_payload(
            tmp_project,
            ["CONTROL.md"],
            [{"path": "CONTROL.md", "content": "CURRENT_TASK: NONE\n"}],
        )

        core = _make_core(tmp_project)

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
        _assert_passive_run_once_result(result)

        reports = tmp_project / "REPORTS"
        # run_once_last.json is written by UI /control/run-once, not core.run_once()
        assert not (reports / "run_once_last.json").exists()

        queue_path = reports / "review_queue.jsonl"
        assert queue_path.exists()
        assert queue_path.read_text(encoding="utf-8").strip()

        _assert_no_forbidden_artifacts(reports)

        approval_store = reports / "approval_store.json"
        assert not approval_store.exists()

        assert not (tmp_project / "guardian_backups").exists()
        assert (tmp_project / "CONTROL.md").read_text() == "CURRENT_TASK: TASK-0001\n"

    def test_run_once_denied_writes_only_run_once_artifacts(self, tmp_project, monkeypatch):
        """APPLY_MUTATION path denial: passive error result, no queue or apply artifacts."""
        _write_apply_mutation_task(tmp_project, allow_gov=True)
        _write_mutation_payload(
            tmp_project,
            ["../evil.txt"],
            [{"path": "../evil.txt", "content": "malicious"}],
        )

        core = _make_core(tmp_project)

        result = core.run_once()
        assert result.get("status") == "error"
        assert result.get("code") == "MUTATION_PAYLOAD_INVALID"
        _assert_passive_run_once_result(result)

        reports = tmp_project / "REPORTS"
        assert not (reports / "run_once_last.json").exists()
        assert not (reports / "review_queue.jsonl").exists()

        _assert_no_forbidden_artifacts(reports)
        assert not (reports / "approval_store.json").exists()
        assert not (tmp_project / "guardian_backups").exists()

    def test_run_once_allow_mutation_creates_backups_and_changes(self, tmp_project, monkeypatch):
        """APPLY_MUTATION allow: backups + target changes under isolated tmp workspace."""
        _write_apply_mutation_task(tmp_project, allow_gov=False)
        target = tmp_project / "safe.py"
        target.write_text("print('old')\n")

        _write_mutation_payload(
            tmp_project,
            ["safe.py"],
            [{"path": "safe.py", "content": "print('new')\n"}],
        )

        core = _make_core(tmp_project)

        def fake_validate(component, action, context):
            return TrustDecision(True, "allow", "ALLOWED", "", 0.1)

        core.trust.validate_trust_for_action = fake_validate

        result = core.run_once()
        assert result.get("status") == "ok"
        _assert_passive_run_once_result(result)

        reports = tmp_project / "REPORTS"
        assert not (reports / "run_once_last.json").exists()

        backups_dir = tmp_project / "guardian_backups"
        assert backups_dir.exists()
        assert any(backups_dir.rglob("*.bak.*"))

        assert target.read_text() == "print('new')\n"
