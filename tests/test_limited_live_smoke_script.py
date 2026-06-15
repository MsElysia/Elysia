"""Tests for scripts/run_limited_live_smoke.py operator command."""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_limited_live_smoke.py"
PYTHON = sys.executable

_REPO_ESCAPE_PATHS = (
    ROOT / "approved_smoke.txt",
    ROOT / "live_smoke_workspace" / "approved_smoke.txt",
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("run_limited_live_smoke", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _smoke_target(workspace: Path) -> Path:
    return workspace / "live_smoke_workspace" / "approved_smoke.txt"


def _list_files_under(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return [p for p in path.rglob("*") if p.is_file()]


@pytest.fixture
def script_module():
    return _load_script_module()


@pytest.fixture
def triple_gates(monkeypatch):
    monkeypatch.setenv("ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED", "true")
    monkeypatch.setenv("ELYSIA_LIVE_EXECUTOR_ENABLED", "true")
    monkeypatch.setenv("ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE", "true")


class TestConfirmationAndProfile:
    def test_missing_confirmation_exits_nonzero_and_writes_nothing(
        self, tmp_path, monkeypatch, script_module
    ):
        monkeypatch.chdir(tmp_path)
        before = _list_files_under(tmp_path)

        summary, code = script_module.run_limited_live_smoke(
            confirm=False,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=tmp_path / "ws_parent",
        )

        after = _list_files_under(tmp_path)
        assert code != 0
        assert summary["preflight_passed"] is False
        assert any("confirm" in err.lower() for err in summary["errors"])
        assert after == before

    def test_wrong_profile_exits_nonzero_and_writes_nothing(
        self, tmp_path, monkeypatch, script_module
    ):
        monkeypatch.chdir(tmp_path)
        before = _list_files_under(tmp_path)

        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile="wrong_profile",
            workspace_parent=tmp_path / "ws_parent",
        )

        after = _list_files_under(tmp_path)
        assert code != 0
        assert summary["preflight_passed"] is False
        assert any("profile" in err.lower() for err in summary["errors"])
        assert after == before


class TestSuccessfulCycle:
    def test_valid_command_completes_and_prints_json_summary(
        self, tmp_path, triple_gates, script_module
    ):
        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=tmp_path,
        )

        assert code == 0
        encoded = json.dumps(summary)
        decoded = json.loads(encoded)
        assert decoded["profile"] == script_module.LIMITED_LIVE_PROFILE_NAME
        assert decoded["safe"] is True
        assert decoded["preflight_passed"] is True
        assert decoded["packet_registered"] is True
        assert decoded["decision_recorded"] is True
        assert decoded["rollback_verified"] is True

    def test_valid_command_writes_exact_smoke_file_during_execution(
        self, tmp_path, triple_gates, script_module
    ):
        workspace = tmp_path / "isolated_smoke_root"
        target = _smoke_target(workspace)

        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=tmp_path,
        )

        assert code == 0
        assert summary["exact_content_verified"] is True
        assert not target.exists()

    def test_rollback_verifies_cleanup(self, tmp_path, triple_gates, script_module):
        workspace = tmp_path / "isolated_smoke_root"
        target = _smoke_target(workspace)

        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=tmp_path,
        )

        assert code == 0
        assert summary["rollback_executed"] is True
        assert summary["rollback_verified"] is True
        assert not target.exists()
        assert not (workspace / "live_smoke_workspace").exists() or not target.exists()


class TestSafetyInvariants:
    def test_config_autonomy_remains_disabled(self, tmp_path, triple_gates, script_module):
        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=tmp_path,
        )

        assert code == 0
        assert summary["config_autonomy_enabled"] is False
        assert summary["autonomy_enabled"] is False

    def test_no_repo_root_user_external_writes(self, tmp_path, triple_gates, script_module):
        for path in _REPO_ESCAPE_PATHS:
            assert not path.exists()

        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=tmp_path,
        )

        assert code == 0
        for path in _REPO_ESCAPE_PATHS:
            assert not path.exists()
        assert summary["safe"] is True

    def test_summary_reports_autonomy_false_and_safe_true(
        self, tmp_path, triple_gates, script_module
    ):
        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=tmp_path,
        )

        assert code == 0
        assert summary["autonomy_enabled"] is False
        assert summary["safe"] is True
        assert summary["readiness_blocked"] is True

    def test_failure_path_never_leaves_target_file_behind(
        self, tmp_path, monkeypatch, script_module
    ):
        monkeypatch.setattr(
            script_module,
            "_read_config_autonomy_enabled",
            lambda: (True, None),
        )

        workspace_parent = tmp_path / "fail_parent"
        target = workspace_parent / "isolated_smoke_root" / "live_smoke_workspace" / (
            "approved_smoke.txt"
        )

        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=workspace_parent,
        )

        assert code != 0
        assert summary["preflight_passed"] is False
        assert summary["executed"] is False
        assert not target.exists()
        for path in _REPO_ESCAPE_PATHS:
            assert not path.exists()


class TestScriptSurface:
    def test_script_does_not_use_shell_network_browser_api_mutation(self):
        tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
        banned_modules = {
            "subprocess",
            "socket",
            "urllib",
            "http",
            "httpx",
            "requests",
            "webbrowser",
            "project_guardian.mutation",
            "project_guardian.mutation_engine",
            "project_guardian.tool_executor",
            "project_guardian.webscout_agent",
            "project_guardian.bounded_browser",
        }
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        for imp in imports:
            root = imp.split(".")[0]
            assert root not in banned_modules, f"unexpected import: {imp}"
            assert imp not in banned_modules, f"unexpected import: {imp}"

    def test_cli_json_run(self, tmp_path, triple_gates):
        result = subprocess.run(
            [
                PYTHON,
                str(SCRIPT_PATH),
                "--profile",
                "operator_approved_harmless_smoke_v1",
                "--confirm-limited-live-smoke",
                "--workspace",
                str(tmp_path),
                "--json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["safe"] is True
        assert payload["executed"] is True
        assert payload["rollback_verified"] is True
