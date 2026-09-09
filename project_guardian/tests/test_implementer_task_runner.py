"""Focused tests for plan-aware acceptance criteria in TaskRunner."""

import logging

from project_guardian.implementer.data_models import (
    ImplementationPlan,
    ImplementationStep,
    Task,
    TaskGraph,
    implementation_plan_from_proposal_dict,
)
from project_guardian.implementer.repo_adapter import RepoAdapter, RepoConfig
from project_guardian.implementer.task_runner import Guardrails, TaskRunner


class _RecordingCodeGen:
    def __init__(self):
        self.calls = []

    def generate_patch(self, **kwargs):
        self.calls.append(kwargs)
        return {target: "# generated\n" for target in kwargs["target_files"]}

    def validate_patch(self, patch, target_files):
        return True, None


class _NoopTests:
    def run_tests(self, **kwargs):
        return {"status": "passed", "kwargs": kwargs}


def _build_runner(tmp_path):
    repo = RepoAdapter(
        RepoConfig(
            repo_root=tmp_path,
            allowed_directories=["src", "tests"],
        )
    )
    codegen = _RecordingCodeGen()
    runner = TaskRunner(
        repo_adapter=repo,
        codegen_client=codegen,
        test_runner=_NoopTests(),
        guardrails=Guardrails(dry_run=True, require_tests_pass=False),
    )
    return runner, codegen


def test_task_runner_uses_plan_acceptance_criteria(tmp_path):
    runner, codegen = _build_runner(tmp_path)
    plan = ImplementationPlan(
        proposal_id="prop-1",
        steps=[
            ImplementationStep(
                id="step-1",
                description="Implement the feature module",
                type="code_modify",
                targets=["src/example.py"],
                acceptance_criteria=["Feature works", "Regression tests pass"],
            )
        ],
    )
    task_graph = TaskGraph(
        tasks=[
            Task(
                id="task-1",
                step_id="step-1",
                description="Placeholder description",
                target_files=["src/example.py"],
            )
        ]
    )

    result = runner.execute(task_graph, {"proposal_id": "prop-1"}, plan=plan)

    assert result.tasks_completed == 1
    assert codegen.calls[0]["step_description"] == "Implement the feature module"
    assert codegen.calls[0]["acceptance_criteria"] == ["Feature works", "Regression tests pass"]


def test_task_runner_falls_back_to_default_acceptance_criteria(tmp_path, caplog):
    runner, codegen = _build_runner(tmp_path)
    task_graph = TaskGraph(
        tasks=[
            Task(
                id="task-1",
                step_id="missing-step",
                description="Update fallback path",
                target_files=["src/fallback.py"],
            )
        ]
    )

    with caplog.at_level(logging.DEBUG):
        result = runner.execute(task_graph, {"proposal_id": "prop-2"}, plan=None)

    assert result.tasks_completed == 1
    assert codegen.calls[0]["acceptance_criteria"] == ["Code compiles", "Tests pass"]
    assert "using defaults" in caplog.text


def test_implementation_plan_from_proposal_dict_top_level_steps():
    proposal = {
        "proposal_id": "top-1",
        "steps": [
            {
                "id": "s-top",
                "description": "Top-level steps array",
                "type": "code_modify",
                "targets": ["lib/x.py"],
                "acceptance_criteria": ["Top AC"],
            }
        ],
    }
    plan = implementation_plan_from_proposal_dict(proposal)
    assert plan is not None
    assert plan.steps[0].id == "s-top"
    assert plan.steps[0].acceptance_criteria == ["Top AC"]


def test_implementation_plan_from_proposal_dict_nested_plan():
    proposal = {
        "proposal_id": "disk-1",
        "plan": {
            "steps": [
                {
                    "id": "step-1",
                    "description": "From JSON",
                    "type": "code_modify",
                    "targets": ["src/x.py"],
                    "acceptance_criteria": ["Lint clean"],
                }
            ]
        },
    }
    plan = implementation_plan_from_proposal_dict(proposal)
    assert plan is not None
    assert plan.proposal_id == "disk-1"
    assert len(plan.steps) == 1
    assert plan.steps[0].acceptance_criteria == ["Lint clean"]


def test_task_runner_uses_plan_embedded_in_proposal_without_plan_arg(tmp_path):
    runner, codegen = _build_runner(tmp_path)
    proposal = {
        "proposal_id": "prop-embed",
        "plan": {
            "steps": [
                {
                    "id": "step-1",
                    "description": "Embedded step text",
                    "type": "code_modify",
                    "targets": ["src/embed.py"],
                    "acceptance_criteria": ["Must pass smoke"],
                }
            ]
        },
    }
    task_graph = TaskGraph(
        tasks=[
            Task(
                id="task-1",
                step_id="step-1",
                description="Ignored when plan matches",
                target_files=["src/embed.py"],
            )
        ]
    )

    result = runner.execute(task_graph, proposal, plan=None)

    assert result.tasks_completed == 1
    assert codegen.calls[0]["step_description"] == "Embedded step text"
    assert codegen.calls[0]["acceptance_criteria"] == ["Must pass smoke"]


def test_task_runner_step_level_empty_ac_uses_proposal_level_criteria(tmp_path):
    runner, codegen = _build_runner(tmp_path)
    proposal = {
        "proposal_id": "prop-ac",
        "acceptance_criteria": ["Proposal-level gate"],
        "plan": {
            "steps": [
                {
                    "id": "step-1",
                    "description": "Step with no local AC",
                    "type": "code_modify",
                    "targets": ["src/ac.py"],
                    "acceptance_criteria": [],
                }
            ]
        },
    }
    task_graph = TaskGraph(
        tasks=[
            Task(
                id="task-1",
                step_id="step-1",
                description="Fallback",
                target_files=["src/ac.py"],
            )
        ]
    )

    result = runner.execute(task_graph, proposal, plan=None)

    assert result.tasks_completed == 1
    assert codegen.calls[0]["acceptance_criteria"] == ["Proposal-level gate"]
