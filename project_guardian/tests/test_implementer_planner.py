"""Tests for Planner preferring embedded proposal plans."""

from project_guardian.implementer.planner import Planner


def test_planner_uses_embedded_plan_instead_of_domain_template():
    proposal = {
        "proposal_id": "p-embed",
        "domain": "elysia_core",
        "plan": {
            "steps": [
                {
                    "id": "custom-a",
                    "description": "Only this step from disk",
                    "type": "code_modify",
                    "targets": ["src/custom.py"],
                    "acceptance_criteria": ["Custom AC"],
                }
            ]
        },
    }
    plan = Planner(api_manager=None).build_plan(proposal)
    assert len(plan.steps) == 1
    assert plan.steps[0].id == "custom-a"
    assert plan.steps[0].targets == ["src/custom.py"]

    graph = Planner(api_manager=None).build_task_graph(plan)
    assert len(graph.tasks) == 1
    assert graph.tasks[0].step_id == "custom-a"


def test_planner_fills_domain_when_embedded_plan_omits_domain():
    proposal = {
        "proposal_id": "p-domain",
        "domain": "hestia_scraping",
        "implementation_plan": {
            "steps": [
                {
                    "id": "s1",
                    "description": "x",
                    "type": "code_add",
                    "targets": ["a.py"],
                    "acceptance_criteria": ["ok"],
                }
            ]
        },
    }
    plan = Planner(api_manager=None).build_plan(proposal)
    assert plan.domain == "hestia_scraping"
