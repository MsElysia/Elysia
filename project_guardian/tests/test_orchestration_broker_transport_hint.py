# project_guardian/tests/test_orchestration_broker_transport_hint.py
from __future__ import annotations

from project_guardian.mistral_engine import orchestration_broker_suggests_transport_failure
from project_guardian.orchestration.types import NodeResult, PipelineResult


def test_orchestration_broker_suggests_transport_from_ollama_node_error() -> None:
    pr = PipelineResult(
        task_id="t",
        pipeline_id="serial_plan_execute_review",
        success=False,
        final_output=None,
        node_results=[
            NodeResult(
                node_id="plan",
                provider="ollama",
                model="m",
                output="",
                success=False,
                latency_ms=1.0,
                error="httpx.ReadTimeout: timed out",
            )
        ],
        error="bounded_action_incomplete",
    )
    assert orchestration_broker_suggests_transport_failure(pr) is True


def test_orchestration_broker_soft_pipeline_error_only_no_ollama_errors() -> None:
    pr = PipelineResult(
        task_id="t",
        pipeline_id="serial_plan_execute_review",
        success=False,
        final_output=None,
        node_results=[],
        error="bounded_action_incomplete",
    )
    assert orchestration_broker_suggests_transport_failure(pr) is False


def test_orchestration_broker_exception_message() -> None:
    assert orchestration_broker_suggests_transport_failure(None, RuntimeError("Connection refused (111)")) is True
