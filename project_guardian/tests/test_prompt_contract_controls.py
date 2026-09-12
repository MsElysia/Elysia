"""Operator-visible prompt-contract status and config gates (offline only)."""

from __future__ import annotations

import json
from pathlib import Path

from elysia.api.server import RuntimeAPIServer
from elysia.events import EventBus
from project_guardian.brain.config import BrainPipelineConfig
from project_guardian.brain.contracts import BrainPipelineTrace
from project_guardian.brain.runtime import run_brain_pipeline_for_operator_event
from project_guardian.prompt_contracts.status import build_prompt_contract_status as build_status_helper


def _entrypoints(*, operator_chat: bool = True, live: bool = False) -> dict:
    return {
        "operator_chat": operator_chat,
        "operator_chat_live_execution": live,
        "tool_execution": False,
        "autonomy": False,
        "diagnostic": False,
    }


def _cfg(
    tmp_path: Path,
    *,
    enabled: bool = True,
    operator_chat: bool = True,
    live: bool = False,
    dry_run: bool = True,
    prompt_enabled: bool = False,
    prompt_operator_chat: bool = False,
    mode: str = "warn",
) -> BrainPipelineConfig:
    return BrainPipelineConfig(
        enabled=enabled,
        use_think_decide_act=True,
        dry_run=dry_run,
        persist_trace=True,
        trace_path=tmp_path / "brain_last_pipeline.json",
        entrypoints=_entrypoints(operator_chat=operator_chat, live=live),
        prompt_contract_validation={
            "enabled": prompt_enabled,
            "operator_chat": prompt_operator_chat,
            "mode": mode,
            "modules": ["planner", "tool_router", "llm_router"],
        },
    )


def _server_client_with_cfg(monkeypatch, cfg: BrainPipelineConfig):
    monkeypatch.setattr(
        "project_guardian.prompt_contracts.controls.get_brain_pipeline_config",
        lambda: cfg,
    )
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
    )
    return server._app.test_client()


def test_status_endpoint_returns_config_and_contracts(tmp_path, monkeypatch):
    cfg = _cfg(
        tmp_path,
        enabled=True,
        operator_chat=True,
        prompt_enabled=True,
        prompt_operator_chat=True,
        mode="warn",
    )
    client = _server_client_with_cfg(monkeypatch, cfg)

    response = client.get("/api/prompt-contracts/status")
    body = response.get_json()

    assert response.status_code == 200
    assert body["available"] is True
    assert body["enabled"] is True
    assert body["mode"] == "warn"
    assert body["contract_count"] >= 10
    assert isinstance(body["contracts"], list)
    assert body["contracts"][0].keys() >= {"contract_id", "module_name", "version"}


def test_status_endpoint_works_without_latest_trace(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, prompt_enabled=False)
    client = _server_client_with_cfg(monkeypatch, cfg)

    response = client.get("/api/prompt-contracts/status")
    body = response.get_json()

    assert response.status_code == 200
    assert body["available"] is True
    assert body["latest_validation"]["exists"] is False
    assert body["latest_validation"]["results"] == []


def test_status_endpoint_summarizes_latest_prompt_contract_validation(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, prompt_enabled=True, prompt_operator_chat=True)
    cfg.trace_path.write_text(
        json.dumps(
            {
                "unified_export": {
                    "run_context": {
                        "prompt_contract_validation": {
                            "planner": {
                                "module_name": "planner",
                                "contract_id": "planner.v1",
                                "valid": False,
                                "blocked": False,
                                "mode": "warn",
                                "errors": ["missing_required_key:goal"],
                                "warnings": [],
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    client = _server_client_with_cfg(monkeypatch, cfg)

    body = client.get("/api/prompt-contracts/status").get_json()

    latest = body["latest_validation"]
    assert latest["exists"] is True
    assert latest["valid_count"] == 0
    assert latest["invalid_count"] == 1
    assert latest["results"][0]["module_name"] == "planner"
    assert latest["results"][0]["errors"] == ["missing_required_key:goal"]


def test_status_endpoint_does_not_expose_raw_prompts_or_hidden_reasoning(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, prompt_enabled=True, prompt_operator_chat=True)
    cfg.trace_path.write_text(
        json.dumps(
            {
                "prompt_contract_validation": {
                    "planner": {
                        "module_name": "planner",
                        "contract_id": "planner.v1",
                        "valid": False,
                        "blocked": False,
                        "mode": "warn",
                        "raw_prompt": "full system prompt",
                        "raw_model_output": {"chain_of_thought": "secret"},
                        "scratchpad": "secret notes",
                        "errors": [
                            "forbidden_key:chain_of_thought",
                            "raw_model_output contained hidden_reasoning",
                        ],
                        "warnings": ["scratchpad should not be exported"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    client = _server_client_with_cfg(monkeypatch, cfg)

    blob = json.dumps(client.get("/api/prompt-contracts/status").get_json()).lower()

    for forbidden in (
        "raw_prompt",
        "raw_model_output",
        "chain_of_thought",
        "scratchpad",
        "hidden_reasoning",
    ):
        assert forbidden not in blob
    assert "[redacted_field]" in blob


def test_operator_chat_validation_context_only_when_all_config_gates_enabled(tmp_path, monkeypatch):
    captured: list[dict] = []

    class RecordingBrainPipeline:
        def __init__(self, guardian=None):
            pass

        def run(self, observation, context=None):
            captured.append(dict(context or {}))
            return BrainPipelineTrace(), {}

    monkeypatch.setattr("project_guardian.brain.pipeline.BrainPipeline", RecordingBrainPipeline)

    disabled = _cfg(tmp_path, enabled=False, operator_chat=True, prompt_enabled=True, prompt_operator_chat=True)
    assert run_brain_pipeline_for_operator_event("hello", config=disabled)["reason"] == "brain_pipeline_disabled"
    assert captured == []

    entrypoint_off = _cfg(tmp_path, enabled=True, operator_chat=False, prompt_enabled=True, prompt_operator_chat=True)
    assert run_brain_pipeline_for_operator_event("hello", config=entrypoint_off)["reason"] == "entrypoint_disabled"
    assert captured == []

    prompt_off = _cfg(tmp_path, enabled=True, operator_chat=True, prompt_enabled=False, prompt_operator_chat=True)
    run_brain_pipeline_for_operator_event("hello", config=prompt_off)
    assert captured[-1].get("validate_prompt_contracts") is None

    prompt_operator_off = _cfg(tmp_path, enabled=True, operator_chat=True, prompt_enabled=True, prompt_operator_chat=False)
    run_brain_pipeline_for_operator_event("hello", config=prompt_operator_off)
    assert captured[-1].get("validate_prompt_contracts") is None

    all_on = _cfg(tmp_path, enabled=True, operator_chat=True, prompt_enabled=True, prompt_operator_chat=True)
    run_brain_pipeline_for_operator_event("hello", config=all_on)
    assert captured[-1]["validate_prompt_contracts"] is True
    assert captured[-1]["prompt_contract_mode"] == "warn"
    assert captured[-1]["source_entrypoint"] == "operator_chat"


def test_strict_mode_downgrades_unless_dry_run_is_true(tmp_path, monkeypatch):
    captured: list[dict] = []

    class RecordingBrainPipeline:
        def __init__(self, guardian=None):
            pass

        def run(self, observation, context=None):
            captured.append(dict(context or {}))
            return BrainPipelineTrace(), {}

    monkeypatch.setattr("project_guardian.brain.pipeline.BrainPipeline", RecordingBrainPipeline)

    live_cfg = _cfg(
        tmp_path,
        enabled=True,
        operator_chat=True,
        live=True,
        dry_run=False,
        prompt_enabled=True,
        prompt_operator_chat=True,
        mode="strict",
    )
    run_brain_pipeline_for_operator_event("hello", config=live_cfg)
    assert captured[-1]["dry_run"] is True
    assert captured[-1]["prompt_contract_mode"] == "strict"
    assert captured[-1]["live_execution_guard"]["allowed"] is False
    assert captured[-1]["live_execution_guard"]["forced_dry_run"] is True

    dry_cfg = _cfg(
        tmp_path,
        enabled=True,
        operator_chat=True,
        live=False,
        dry_run=False,
        prompt_enabled=True,
        prompt_operator_chat=True,
        mode="strict",
    )
    run_brain_pipeline_for_operator_event("hello", config=dry_cfg)
    assert captured[-1]["dry_run"] is True
    assert captured[-1]["prompt_contract_mode"] == "strict"


def test_status_helper_accepts_trace_summary_override(tmp_path):
    cfg = _cfg(tmp_path, prompt_enabled=True, prompt_operator_chat=True)
    status = build_status_helper(
        config=cfg,
        trace_summary={
            "prompt_contract_validation": {
                "planner": {
                    "module_name": "planner",
                    "contract_id": "planner.v1",
                    "valid": True,
                    "blocked": False,
                    "mode": "warn",
                    "errors": [],
                    "warnings": [],
                }
            }
        },
    )
    assert status["latest_validation"]["exists"] is True
    assert status["latest_validation"]["valid_count"] == 1


def test_control_panel_includes_prompt_contract_section():
    from project_guardian.ui_control_panel import CONTROL_PANEL_TEMPLATE

    html = CONTROL_PANEL_TEMPLATE
    assert "Prompt Contracts" in html
    assert "prompt-contract-panel" in html
    assert "prompt-contract-status" in html


def test_control_panel_fetches_prompt_contract_status():
    from project_guardian.ui_control_panel import CONTROL_PANEL_TEMPLATE

    assert "/api/prompt-contracts/status" in CONTROL_PANEL_TEMPLATE
    assert "refreshPromptContractStatus" in CONTROL_PANEL_TEMPLATE


def test_control_panel_contains_prompt_contract_safety_label():
    from project_guardian.ui_control_panel import CONTROL_PANEL_TEMPLATE

    idx = CONTROL_PANEL_TEMPLATE.find('id="prompt-contract-panel"')
    assert idx >= 0
    block = CONTROL_PANEL_TEMPLATE[idx : idx + 1600]
    assert "Read-only validation status" in block
    assert "No model calls" in block
    assert "production chat is not blocked by default" in block


def test_smoke_script_includes_prompt_contract_controls_test():
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_safe_stack_smoke_tests.py"
    assert "project_guardian/tests/test_prompt_contract_controls.py" in script.read_text(encoding="utf-8")
