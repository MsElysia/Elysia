"""Tests for scripts/run_limited_live_smoke.py operator command."""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
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


def _smoke_escape_paths_under(base: Path) -> tuple[Path, ...]:
    return (
        base / "approved_smoke.txt",
        base / "live_smoke_workspace" / "approved_smoke.txt",
    )


def _escape_paths_exist() -> list[Path]:
    return [path for path in _REPO_ESCAPE_PATHS if path.exists()]


def _list_files_under(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return [p for p in path.rglob("*") if p.is_file()]


def _assert_no_new_escape_files(before: list[Path]) -> None:
    after = _escape_paths_exist()
    assert after == before


def _assert_under_system_temp(path: Path, script_module) -> None:
    resolved = path.resolve()
    system_temp = script_module._get_system_temp_root()
    assert script_module._is_under_path(resolved, system_temp)


def _filesystem_root() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("SystemDrive", "C:") + "\\")
    return Path("/")


@pytest.fixture
def script_module():
    return _load_script_module()


@pytest.fixture
def triple_gates(monkeypatch):
    monkeypatch.setenv("ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED", "true")
    monkeypatch.setenv("ELYSIA_LIVE_EXECUTOR_ENABLED", "true")
    monkeypatch.setenv("ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE", "true")


@pytest.fixture
def safe_temp_parent(tmp_path, script_module):
    _assert_under_system_temp(tmp_path, script_module)
    return tmp_path


class TestConfirmationAndProfile:
    def test_missing_confirmation_exits_nonzero_and_writes_nothing(
        self, safe_temp_parent, monkeypatch, script_module
    ):
        monkeypatch.chdir(safe_temp_parent)
        before = _list_files_under(safe_temp_parent)

        summary, code = script_module.run_limited_live_smoke(
            confirm=False,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent / "ws_parent",
        )

        after = _list_files_under(safe_temp_parent)
        assert code != 0
        assert summary["preflight_passed"] is False
        assert any("confirm" in err.lower() for err in summary["errors"])
        assert after == before

    def test_wrong_profile_exits_nonzero_and_writes_nothing(
        self, safe_temp_parent, monkeypatch, script_module
    ):
        monkeypatch.chdir(safe_temp_parent)
        before = _list_files_under(safe_temp_parent)

        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile="wrong_profile",
            workspace_parent=safe_temp_parent / "ws_parent",
        )

        after = _list_files_under(safe_temp_parent)
        assert code != 0
        assert summary["preflight_passed"] is False
        assert any("profile" in err.lower() for err in summary["errors"])
        assert after == before


class TestDefaultAndSafeWorkspace:
    def test_default_run_uses_temp_workspace_and_passes(
        self, triple_gates, script_module
    ):
        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
        )

        assert code == 0
        assert summary["safe"] is True
        assert summary["workspace_parent"] == ""
        assert summary["workspace_root"]
        workspace_root = Path(summary["workspace_root"])
        _assert_under_system_temp(workspace_root, script_module)
        assert not _smoke_target(workspace_root).exists()

    def test_custom_workspace_inside_system_temp_passes(
        self, safe_temp_parent, triple_gates, script_module
    ):
        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
        )

        assert code == 0
        assert summary["safe"] is True
        assert summary["workspace_parent"] == str(safe_temp_parent)
        assert summary["workspace_root"] == str(
            (safe_temp_parent / "isolated_smoke_root").resolve()
        )
        assert not _smoke_target(Path(summary["workspace_root"])).exists()


class TestUnsafeWorkspaceRejection:
    def _assert_unsafe_rejected(
        self,
        script_module,
        workspace_parent,
        *,
        local_watch: Path | None = None,
    ) -> None:
        before_escapes = _escape_paths_exist()
        before_local = _list_files_under(local_watch) if local_watch is not None else []

        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=workspace_parent,
        )

        assert code != 0
        assert summary["safe"] is False
        assert summary["workspace_rejected"] is True
        assert summary["packet_registered"] is False
        assert summary["executed"] is False
        assert any("unsafe workspace" in err for err in summary["errors"])
        _assert_no_new_escape_files(before_escapes)
        if local_watch is not None:
            assert _list_files_under(local_watch) == before_local
        for escape in _smoke_escape_paths_under(ROOT):
            assert not escape.exists()

    def test_repo_root_workspace_rejected(self, triple_gates, script_module):
        self._assert_unsafe_rejected(script_module, ROOT)

    def test_cwd_workspace_rejected(self, monkeypatch, triple_gates, script_module):
        monkeypatch.chdir(ROOT)
        self._assert_unsafe_rejected(script_module, ROOT)

    def test_user_home_workspace_rejected(self, triple_gates, script_module):
        self._assert_unsafe_rejected(script_module, Path.home())

    def test_filesystem_root_workspace_rejected(self, triple_gates, script_module):
        self._assert_unsafe_rejected(script_module, _filesystem_root())

    def test_relative_workspace_rejected(
        self, safe_temp_parent, monkeypatch, triple_gates, script_module
    ):
        monkeypatch.chdir(safe_temp_parent)
        before = _list_files_under(safe_temp_parent)

        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent="relative_workspace",
        )

        assert code != 0
        assert summary["workspace_rejected"] is True
        assert summary["safe"] is False
        assert any("relative path" in err for err in summary["errors"])
        assert _list_files_under(safe_temp_parent) == before

    def test_symlink_workspace_escaping_temp_rejected(
        self, safe_temp_parent, triple_gates, script_module
    ):
        link = safe_temp_parent / "escape_link"
        try:
            link.symlink_to(ROOT, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation not supported in this environment")

        self._assert_unsafe_rejected(
            script_module,
            link,
            local_watch=safe_temp_parent,
        )

    def test_unsafe_workspace_emits_json_summary_and_leaves_no_target(
        self, triple_gates, script_module
    ):
        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=ROOT,
        )

        encoded = json.dumps(summary)
        decoded = json.loads(encoded)
        assert code != 0
        assert decoded["safe"] is False
        assert decoded["workspace_rejected"] is True
        assert decoded["errors"]
        assert not _smoke_target(ROOT).exists()
        for path in _REPO_ESCAPE_PATHS:
            assert not path.exists()


class TestSuccessfulCycle:
    def test_valid_command_completes_and_prints_json_summary(
        self, safe_temp_parent, triple_gates, script_module
    ):
        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
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
        self, safe_temp_parent, triple_gates, script_module
    ):
        workspace = safe_temp_parent / "isolated_smoke_root"
        target = _smoke_target(workspace)

        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
        )

        assert code == 0
        assert summary["exact_content_verified"] is True
        assert not target.exists()

    def test_rollback_verifies_cleanup(self, safe_temp_parent, triple_gates, script_module):
        workspace = safe_temp_parent / "isolated_smoke_root"
        target = _smoke_target(workspace)

        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
        )

        assert code == 0
        assert summary["rollback_executed"] is True
        assert summary["rollback_verified"] is True
        assert not target.exists()


class TestSafetyInvariants:
    def test_config_autonomy_remains_disabled(
        self, safe_temp_parent, triple_gates, script_module
    ):
        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
        )

        assert code == 0
        assert summary["config_autonomy_enabled"] is False
        assert summary["autonomy_enabled"] is False

    def test_no_repo_root_user_external_writes(
        self, safe_temp_parent, triple_gates, script_module
    ):
        for path in _REPO_ESCAPE_PATHS:
            assert not path.exists()

        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
        )

        assert code == 0
        for path in _REPO_ESCAPE_PATHS:
            assert not path.exists()
        assert summary["safe"] is True

    def test_summary_reports_autonomy_false_and_safe_true(
        self, safe_temp_parent, triple_gates, script_module
    ):
        summary, code = script_module.run_limited_live_smoke(
            confirm=True,
            profile=script_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
        )

        assert code == 0
        assert summary["autonomy_enabled"] is False
        assert summary["safe"] is True
        assert summary["readiness_blocked"] is True

    def test_failure_path_never_leaves_target_file_behind(
        self, safe_temp_parent, monkeypatch, script_module
    ):
        monkeypatch.setattr(
            script_module,
            "_read_config_autonomy_enabled",
            lambda: (True, None),
        )

        workspace_parent = safe_temp_parent / "fail_parent"
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

    def test_cli_json_default_run(self, triple_gates):
        result = subprocess.run(
            [
                PYTHON,
                str(SCRIPT_PATH),
                "--profile",
                "operator_approved_harmless_smoke_v1",
                "--confirm-limited-live-smoke",
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
        assert payload["workspace_root"]
        assert Path(payload["workspace_root"]).resolve().is_relative_to(
            Path(tempfile.gettempdir()).resolve()
        )

    def test_cli_json_run_with_safe_workspace(self, safe_temp_parent, triple_gates):
        result = subprocess.run(
            [
                PYTHON,
                str(SCRIPT_PATH),
                "--profile",
                "operator_approved_harmless_smoke_v1",
                "--confirm-limited-live-smoke",
                "--workspace",
                str(safe_temp_parent),
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
