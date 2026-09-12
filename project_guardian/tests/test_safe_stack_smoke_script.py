# project_guardian/tests/test_safe_stack_smoke_script.py
"""Tests for scripts/run_safe_stack_smoke_tests.py (smoke runner metadata only)."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "run_safe_stack_smoke_tests.py"


def _load_smoke_module():
    if not SCRIPT_PATH.is_file():
        pytest.skip("run_safe_stack_smoke_tests.py not found")
    spec = importlib.util.spec_from_file_location("run_safe_stack_smoke_tests", SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_smoke_script_exists():
    assert SCRIPT_PATH.is_file()


def test_smoke_script_references_core_test_files():
    mod = _load_smoke_module()
    declared = set(mod.declared_test_paths())
    expected = {
        "project_guardian/tests/test_conversation_store.py",
        "project_guardian/tests/test_control_panel_chat_memory.py",
        "project_guardian/tests/test_control_panel_legacy_history_retirement.py",
        "project_guardian/tests/test_control_panel_operator_chat_helper_integration.py",
        "project_guardian/tests/test_control_panel_brain_visibility.py",
        "project_guardian/tests/test_control_panel_js_smoke.py",
        "project_guardian/tests/test_safe_stack_response_helpers.py",
        "project_guardian/tests/test_operator_chat_helper.py",
        "project_guardian/tests/test_runtime_operator_chat_helper_integration.py",
        "project_guardian/tests/test_brain_trace_visibility.py",
        "project_guardian/tests/test_brain_tda_integration.py",
        "project_guardian/tests/test_self_improvement_proposal_queue.py",
        "project_guardian/tests/test_self_improvement_legacy_queue_retirement.py",
        "project_guardian/tests/test_self_improvement_prompt_export.py",
        "project_guardian/tests/test_prompt_contracts.py",
        "project_guardian/tests/test_prompt_contract_integration.py",
        "project_guardian/tests/test_memory_ranking.py",
        "project_guardian/tests/test_memory_ranking_visibility.py",
        "project_guardian/tests/test_prompt_contract_controls.py",
        "project_guardian/tests/test_api_host_route_parity.py",
    }
    assert expected <= declared


def test_script_handles_tda_trace_and_memory_ranking_alternative_names():
    mod = _load_smoke_module()
    labels = {label: tuple(cands) for label, cands in mod.OPTIONAL_ALTERNATIVES}
    assert {
        "project_guardian/tests/test_tda_trace_fields.py",
        "project_guardian/tests/test_tda_trace_naming.py",
    } <= set(labels["TDA trace naming"])
    assert {
        "project_guardian/tests/test_memory_ranking_imports.py",
        "project_guardian/tests/test_memory_ranking_consolidation.py",
    } <= set(labels["memory ranking imports"])


def test_tda_alternative_prefers_fields_when_both_exist():
    mod = _load_smoke_module()
    paths = mod.resolve_smoke_test_paths(ROOT)
    fields = "project_guardian/tests/test_tda_trace_fields.py"
    naming = "project_guardian/tests/test_tda_trace_naming.py"
    if (ROOT / fields).is_file() and (ROOT / naming).is_file():
        assert fields in paths
        assert naming not in paths


def test_memory_import_alternative_prefers_imports_when_both_exist():
    mod = _load_smoke_module()
    paths = mod.resolve_smoke_test_paths(ROOT)
    imports = "project_guardian/tests/test_memory_ranking_imports.py"
    consolidation = "project_guardian/tests/test_memory_ranking_consolidation.py"
    if (ROOT / imports).is_file() and (ROOT / consolidation).is_file():
        assert imports in paths
        assert consolidation not in paths


def test_build_pytest_command_uses_module_pytest():
    mod = _load_smoke_module()
    cmd = mod.build_pytest_command(["project_guardian/tests/test_conversation_store.py"])
    assert cmd[0]
    assert cmd[1:3] == ["-m", "pytest"]
    assert cmd[-1] == "-q"


def test_script_source_includes_safety_reminders():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "Autonomy is not tested" in text
    assert "Live execution is not tested" in text
    assert "not full CI" in text


def test_script_does_not_use_shell_true():
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            assert not (
                keyword.arg == "shell"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
            )


def test_script_does_not_invoke_autonomy_or_live_execution():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "run_autonomous_cycle",
        "operator_chat_live_execution",
        "autonomy/execute",
        "/api/proposals/",
        "implementer",
    ):
        assert forbidden not in text


def test_missing_required_file_raises(tmp_path):
    mod = _load_smoke_module()
    fake_root = tmp_path / "repo"
    fake_root.mkdir()
    (fake_root / "project_guardian" / "tests").mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="Required smoke test"):
        mod.resolve_smoke_test_paths(fake_root)


def test_list_mode_prints_safety_reminders(capsys):
    mod = _load_smoke_module()
    rc = mod.run_safe_stack_smoke_tests(repo_root=ROOT, list_only=True)
    captured = capsys.readouterr()
    assert rc == 0
    assert "Autonomy is not tested" in captured.out
    assert "Live execution is not tested" in captured.out
    assert "not full CI" in captured.out
