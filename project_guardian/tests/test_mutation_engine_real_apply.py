"""Regression tests for the legacy mutation engine's real apply/rollback path."""

from pathlib import Path

from project_guardian.mutation import MutationResult
from project_guardian.mutation_engine import MutationEngine, MutationStatus


def _build_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    (project_root / "project_guardian").mkdir(parents=True)
    (project_root / "data").mkdir(parents=True)
    target_file = project_root / "project_guardian" / "sample_module.py"
    target_file.write_text(
        "def greeting():\n    return 'hello'\n",
        encoding="utf-8",
    )
    return project_root


def test_legacy_mutation_engine_applies_and_rolls_back_real_file(tmp_path):
    project_root = _build_project(tmp_path)
    storage_path = project_root / "data" / "mutations.json"
    target_module = "project_guardian/sample_module.py"

    engine = MutationEngine(
        storage_path=str(storage_path),
        repo_root=str(project_root),
    )

    mutation_id = engine.propose_mutation(
        target_module=target_module,
        mutation_type="bug_fix",
        description="Update sample greeting",
        proposed_code="def greeting():\n    return 'mutated'\n",
        original_code="def greeting():\n    return 'hello'\n",
    )
    assert engine.review_mutation(mutation_id, approved=True, reviewer="pytest")
    assert engine.apply_mutation(mutation_id) is True

    target_file = project_root / target_module
    proposal = engine.get_mutation(mutation_id)
    assert proposal is not None
    assert proposal.status == MutationStatus.APPLIED
    assert target_file.read_text(encoding="utf-8") == "def greeting():\n    return 'mutated'\n"
    assert proposal.metadata["backup_paths"]
    assert Path(proposal.metadata["backup_paths"][0]).exists()

    assert engine.rollback_mutation(mutation_id) is True
    proposal = engine.get_mutation(mutation_id)
    assert proposal is not None
    assert proposal.status == MutationStatus.ROLLED_BACK
    assert target_file.read_text(encoding="utf-8") == "def greeting():\n    return 'hello'\n"


def test_legacy_mutation_engine_delegates_to_live_backend(tmp_path):
    project_root = _build_project(tmp_path)
    storage_path = project_root / "data" / "mutations.json"

    class _LiveBackend:
        def __init__(self):
            self.calls = []

        def apply(self, filename, new_code, **kwargs):
            self.calls.append(
                {
                    "filename": filename,
                    "new_code": new_code,
                    "kwargs": kwargs,
                }
            )
            return MutationResult(
                ok=True,
                changed_files=[filename],
                backup_paths=["backup-file"],
                summary="delegated",
            )

    live_backend = _LiveBackend()
    engine = MutationEngine(
        storage_path=str(storage_path),
        repo_root=str(project_root),
        live_mutation_engine=live_backend,
    )

    mutation_id = engine.propose_mutation(
        target_module="project_guardian/sample_module.py",
        mutation_type="feature_add",
        description="Delegate apply through live backend",
        proposed_code="def greeting():\n    return 'delegated'\n",
        original_code="def greeting():\n    return 'hello'\n",
    )
    assert engine.review_mutation(mutation_id, approved=True, reviewer="pytest")
    assert engine.apply_mutation(mutation_id) is True

    assert len(live_backend.calls) == 1
    assert live_backend.calls[0]["filename"] == "project_guardian/sample_module.py"
    assert live_backend.calls[0]["kwargs"]["task_id"] == mutation_id
    proposal = engine.get_mutation(mutation_id)
    assert proposal is not None
    assert proposal.metadata["apply_summary"] == "delegated"
