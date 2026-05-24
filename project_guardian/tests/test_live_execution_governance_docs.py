"""Static checks for live-execution governance documentation."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = ROOT / "docs" / "LIVE_EXECUTION_GOVERNANCE_PLAN.md"
SMOKE_SCRIPT_PATH = ROOT / "scripts" / "run_safe_stack_smoke_tests.py"


def _doc_text() -> str:
    assert DOC_PATH.is_file()
    return DOC_PATH.read_text(encoding="utf-8").lower()


def test_governance_doc_exists():
    assert DOC_PATH.is_file()


def test_doc_mentions_config_gate():
    text = _doc_text()
    assert "config gate" in text
    assert "config/brain_pipeline.json" in text
    assert "brain_pipeline.enabled" in text


def test_doc_mentions_dry_run_before_live():
    text = _doc_text()
    assert "dry-run-before-live" in text
    assert "dry-run artifact" in text


def test_doc_mentions_blocked_high_risk_cannot_execute():
    text = _doc_text()
    assert "blocked" in text
    assert "high risk" in text
    assert "cannot execute" in text


def test_doc_mentions_operator_confirmation():
    assert "operator confirmation" in _doc_text()


def test_doc_mentions_audit_logging():
    assert "audit logging" in _doc_text()


def test_doc_mentions_rollback_or_undo():
    text = _doc_text()
    assert "rollback" in text or "undo" in text


def test_doc_mentions_executor_allowlist():
    assert "executor allowlist" in _doc_text()


def test_doc_mentions_no_raw_llm_text_to_executable_commands():
    text = _doc_text()
    assert "no raw llm text to executable commands" in text
    assert "free-form user text" in text


def test_doc_mentions_autonomy_remains_excluded():
    assert "autonomy remains excluded" in _doc_text()


def test_doc_does_not_contain_instructions_to_enable_live_execution_now():
    text = _doc_text()
    forbidden = (
        "enable live execution now",
        "turn on live execution now",
        "set `operator_chat_live_execution` to `true`",
        '"operator_chat_live_execution": true',
        "`operator_chat_live_execution`: true",
        "wire autonomy now",
        "press execute to run live",
    )
    for phrase in forbidden:
        assert phrase not in text


def test_smoke_script_includes_governance_docs_test():
    assert "project_guardian/tests/test_live_execution_governance_docs.py" in (
        SMOKE_SCRIPT_PATH.read_text(encoding="utf-8")
    )
