# project_guardian/tests/test_operator_confirmation_context_plan.py
"""Static checks for operator confirmation context plan (planning only)."""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLAN_DOC = _REPO_ROOT / "docs" / "OPERATOR_CONFIRMATION_CONTEXT_PLAN.md"
_SMOKE_SCRIPT = _REPO_ROOT / "scripts" / "run_safe_stack_smoke_tests.py"


def _doc() -> str:
    if not _PLAN_DOC.is_file():
        pytest.fail(f"missing plan doc: {_PLAN_DOC}")
    return _PLAN_DOC.read_text(encoding="utf-8").lower()


def test_plan_doc_exists():
    assert _PLAN_DOC.is_file()


def test_doc_mentions_operator_confirmation_id():
    assert "operator_confirmation_id" in _doc()


def test_doc_mentions_dry_run_trace_id():
    assert "dry_run_trace_id" in _doc()


def test_doc_mentions_confirmation_expiry():
    text = _doc()
    assert "expir" in text
    assert "confirmation" in text


def test_doc_mentions_single_use_confirmation():
    text = _doc()
    assert "single-use" in text or "single use" in text
    assert "reused" in text or "replay" in text


def test_doc_mentions_trace_action_matching():
    text = _doc()
    assert "trace" in text
    assert "action" in text
    assert "mismatch" in text or "fingerprint" in text


def test_doc_says_high_blocked_cannot_be_confirmed():
    text = _doc()
    assert "high" in text and "blocked" in text
    assert "cannot be confirmed" in text or "cannot confirm" in text


def test_doc_says_autonomy_cannot_be_confirmed_through_operator_chat():
    text = _doc()
    assert "autonomy" in text
    assert "operator chat" in text
    assert "cannot" in text


def test_doc_says_self_modification_requires_separate_workflow():
    text = _doc()
    assert "self-modification" in text or "self_modification" in text
    assert "separate" in text


def test_doc_says_no_live_execution_enabled_yet():
    text = _doc()
    assert "do not enable live execution" in text or "not enable live execution" in text
    assert "planning only" in text or "not implemented" in text


def test_doc_includes_future_api_shape_example():
    text = _PLAN_DOC.read_text(encoding="utf-8")
    assert "future" in text.lower()
    assert "live_execution_request" in text
    assert "operator_confirmation_id" in text
    assert "confirmed_action_id" in text


def test_doc_includes_test_plan():
    text = _doc()
    assert "tests to add" in text or "test_" in text
    assert "before implementation" in text


def test_smoke_script_includes_operator_confirmation_context_plan_test():
    assert "project_guardian/tests/test_operator_confirmation_context_plan.py" in (
        _SMOKE_SCRIPT.read_text(encoding="utf-8")
    )
