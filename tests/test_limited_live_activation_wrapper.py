"""Tests for scripts/run_limited_live_activation.py operator wrapper."""

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
SCRIPT_PATH = ROOT / "scripts" / "run_limited_live_activation.py"
SMOKE_SCRIPT_PATH = ROOT / "scripts" / "run_limited_live_smoke.py"
PYTHON = sys.executable

_REPO_ESCAPE_PATHS = (
    ROOT / "approved_smoke.txt",
    ROOT / "live_smoke_workspace" / "approved_smoke.txt",
)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _activation_module():
    return _load_module(SCRIPT_PATH, "run_limited_live_activation")


def _smoke_module():
    return _load_module(SMOKE_SCRIPT_PATH, "run_limited_live_smoke")


def _smoke_target(workspace: Path) -> Path:
    return workspace / "live_smoke_workspace" / "approved_smoke.txt"


def _escape_paths_exist() -> list[Path]:
    return [path for path in _REPO_ESCAPE_PATHS if path.exists()]


def _list_files_under(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return [p for p in path.rglob("*") if p.is_file()]


def _assert_under_system_temp(path: Path, smoke_module) -> None:
    resolved = path.resolve()
    system_temp = smoke_module._get_system_temp_root()
    assert smoke_module._is_under_path(resolved, system_temp)


@pytest.fixture
def activation_module():
    return _activation_module()


@pytest.fixture
def smoke_module():
    return _smoke_module()


@pytest.fixture
def triple_gates(monkeypatch):
    monkeypatch.setenv("ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED", "true")
    monkeypatch.setenv("ELYSIA_LIVE_EXECUTOR_ENABLED", "true")
    monkeypatch.setenv("ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE", "true")


@pytest.fixture
def safe_temp_parent(tmp_path, smoke_module):
    _assert_under_system_temp(tmp_path, smoke_module)
    return tmp_path


@pytest.fixture
def activation_ready(monkeypatch, activation_module):
    monkeypatch.setenv(activation_module._SKIP_BRANCH_CHECK_ENV, "true")
    monkeypatch.setattr(
        activation_module,
        "verify_rc_tag",
        lambda **kwargs: (True, activation_module.RC_TAG_TARGET_COMMIT, []),
    )
    monkeypatch.setattr(
        activation_module,
        "verify_index_clean",
        lambda **kwargs: (True, []),
    )


class TestConfirmationAndProfiles:
    def test_missing_confirmation_exits_nonzero_and_writes_nothing(
        self, safe_temp_parent, monkeypatch, activation_module, activation_ready
    ):
        monkeypatch.chdir(safe_temp_parent)
        before = _list_files_under(safe_temp_parent)

        summary, code = activation_module.run_limited_live_activation(
            confirm=False,
            activation_profile=activation_module.ACTIVATION_PROFILE_NAME,
            profile=activation_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent / "ws_parent",
            skip_branch_check=True,
        )

        after = _list_files_under(safe_temp_parent)
        assert code != 0
        assert summary["safe"] is False
        assert summary["smoke_command_invoked"] is False
        assert any("confirm" in err.lower() for err in summary["errors"])
        assert after == before

    def test_wrong_activation_profile_exits_nonzero_and_writes_nothing(
        self, safe_temp_parent, monkeypatch, activation_module, activation_ready
    ):
        monkeypatch.chdir(safe_temp_parent)
        before = _list_files_under(safe_temp_parent)

        summary, code = activation_module.run_limited_live_activation(
            confirm=True,
            activation_profile="wrong_activation_profile",
            profile=activation_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent / "ws_parent",
            skip_branch_check=True,
        )

        after = _list_files_under(safe_temp_parent)
        assert code != 0
        assert summary["safe"] is False
        assert summary["smoke_command_invoked"] is False
        assert any("activation profile" in err.lower() for err in summary["errors"])
        assert after == before

    def test_wrong_limited_live_profile_exits_nonzero_and_writes_nothing(
        self, safe_temp_parent, monkeypatch, activation_module, activation_ready
    ):
        monkeypatch.chdir(safe_temp_parent)
        before = _list_files_under(safe_temp_parent)

        summary, code = activation_module.run_limited_live_activation(
            confirm=True,
            activation_profile=activation_module.ACTIVATION_PROFILE_NAME,
            profile="wrong_profile",
            workspace_parent=safe_temp_parent / "ws_parent",
            skip_branch_check=True,
        )

        after = _list_files_under(safe_temp_parent)
        assert code != 0
        assert summary["safe"] is False
        assert summary["smoke_command_invoked"] is False
        assert any("profile" in err.lower() for err in summary["errors"])
        assert after == before


class TestRcTagAndConfig:
    def test_missing_rc_tag_fails_safely(
        self, safe_temp_parent, monkeypatch, activation_module, activation_ready
    ):
        monkeypatch.setattr(
            activation_module,
            "verify_rc_tag",
            lambda **kwargs: (False, "", ["RC tag verification failed: missing tag"]),
        )
        before = _list_files_under(safe_temp_parent)

        summary, code = activation_module.run_limited_live_activation(
            confirm=True,
            activation_profile=activation_module.ACTIVATION_PROFILE_NAME,
            profile=activation_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
            skip_branch_check=True,
        )

        assert code != 0
        assert summary["rc_tag_verified"] is False
        assert summary["smoke_command_invoked"] is False
        assert _list_files_under(safe_temp_parent) == before

    def test_wrong_rc_tag_target_fails_safely(
        self, safe_temp_parent, monkeypatch, activation_module
    ):
        monkeypatch.setenv(activation_module._SKIP_BRANCH_CHECK_ENV, "true")
        monkeypatch.setattr(
            activation_module,
            "verify_index_clean",
            lambda **kwargs: (True, []),
        )
        monkeypatch.setattr(
            activation_module,
            "verify_rc_tag",
            lambda **kwargs: (
                False,
                "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
                ["RC tag 'limited_live_rc_1' points to deadbeef; expected 236f0b5"],
            ),
        )
        before = _list_files_under(safe_temp_parent)

        summary, code = activation_module.run_limited_live_activation(
            confirm=True,
            activation_profile=activation_module.ACTIVATION_PROFILE_NAME,
            profile=activation_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
            skip_branch_check=True,
        )

        assert code != 0
        assert summary["rc_tag_verified"] is False
        assert summary["smoke_command_invoked"] is False
        assert _list_files_under(safe_temp_parent) == before

    def test_config_autonomy_enabled_simulation_fails_safely(
        self, safe_temp_parent, monkeypatch, activation_module, activation_ready
    ):
        monkeypatch.setattr(
            activation_module,
            "_read_config_autonomy_enabled",
            lambda: (True, None),
        )

        summary, code = activation_module.run_limited_live_activation(
            confirm=True,
            activation_profile=activation_module.ACTIVATION_PROFILE_NAME,
            profile=activation_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
            skip_branch_check=True,
        )

        assert code != 0
        assert summary["config_autonomy_enabled"] is True
        assert summary["smoke_command_invoked"] is False
        assert any("enabled=true" in err for err in summary["errors"])


class TestSuccessfulActivation:
    def test_valid_wrapper_run_emits_json_summary(
        self, safe_temp_parent, triple_gates, activation_module, activation_ready
    ):
        summary, code = activation_module.run_limited_live_activation(
            confirm=True,
            activation_profile=activation_module.ACTIVATION_PROFILE_NAME,
            profile=activation_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
            skip_branch_check=True,
        )

        assert code == 0
        encoded = json.dumps(summary)
        decoded = json.loads(encoded)
        assert decoded["safe"] is True
        assert decoded["activation_profile"] == activation_module.ACTIVATION_PROFILE_NAME
        assert decoded["profile"] == activation_module.LIMITED_LIVE_PROFILE_NAME

    def test_valid_wrapper_verifies_rc_branch_profile_and_config_disabled(
        self, safe_temp_parent, triple_gates, activation_module, activation_ready
    ):
        summary, code = activation_module.run_limited_live_activation(
            confirm=True,
            activation_profile=activation_module.ACTIVATION_PROFILE_NAME,
            profile=activation_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
            skip_branch_check=True,
        )

        assert code == 0
        assert summary["rc_tag_verified"] is True
        assert summary["rc_tag_target"].startswith("236f0b5")
        assert summary["branch_verified"] is True
        assert summary["config_autonomy_enabled"] is False
        assert summary["readiness_blocked"] is True
        assert summary["smoke_command_invoked"] is True

    def test_valid_wrapper_executes_exact_harmless_smoke_only(
        self, safe_temp_parent, triple_gates, activation_module, activation_ready
    ):
        workspace = safe_temp_parent / "isolated_smoke_root"
        target = _smoke_target(workspace)

        summary, code = activation_module.run_limited_live_activation(
            confirm=True,
            activation_profile=activation_module.ACTIVATION_PROFILE_NAME,
            profile=activation_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
            skip_branch_check=True,
        )

        assert code == 0
        assert summary["executed"] is True
        assert not target.exists()

    def test_valid_wrapper_verifies_exact_content(
        self, safe_temp_parent, triple_gates, activation_module, activation_ready
    ):
        summary, code = activation_module.run_limited_live_activation(
            confirm=True,
            activation_profile=activation_module.ACTIVATION_PROFILE_NAME,
            profile=activation_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
            skip_branch_check=True,
        )

        assert code == 0
        assert summary["exact_content_verified"] is True

    def test_valid_wrapper_performs_rollback_and_verifies_cleanup(
        self, safe_temp_parent, triple_gates, activation_module, activation_ready
    ):
        workspace = safe_temp_parent / "isolated_smoke_root"
        target = _smoke_target(workspace)

        summary, code = activation_module.run_limited_live_activation(
            confirm=True,
            activation_profile=activation_module.ACTIVATION_PROFILE_NAME,
            profile=activation_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
            skip_branch_check=True,
        )

        assert code == 0
        assert summary["rollback_verified"] is True
        assert not target.exists()


class TestUnsafeWorkspace:
    def test_unsafe_workspace_rejection_still_works(
        self, triple_gates, activation_module, activation_ready
    ):
        before_escapes = _escape_paths_exist()

        summary, code = activation_module.run_limited_live_activation(
            confirm=True,
            activation_profile=activation_module.ACTIVATION_PROFILE_NAME,
            profile=activation_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=ROOT,
            skip_branch_check=True,
        )

        assert code != 0
        assert summary["unsafe_workspace_rejected"] is True
        assert summary["safe"] is False
        assert summary["smoke_command_invoked"] is False
        assert any("unsafe workspace" in err for err in summary["errors"])
        assert _escape_paths_exist() == before_escapes


class TestSafetyInvariants:
    def test_no_repo_root_user_external_writes(
        self, safe_temp_parent, triple_gates, activation_module, activation_ready
    ):
        for path in _REPO_ESCAPE_PATHS:
            assert not path.exists()

        summary, code = activation_module.run_limited_live_activation(
            confirm=True,
            activation_profile=activation_module.ACTIVATION_PROFILE_NAME,
            profile=activation_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
            skip_branch_check=True,
        )

        assert code == 0
        for path in _REPO_ESCAPE_PATHS:
            assert not path.exists()
        assert summary["safe"] is True
        assert summary["workspace_temp_only"] is True

    def test_readiness_remains_blocked(
        self, safe_temp_parent, triple_gates, activation_module, activation_ready
    ):
        summary, code = activation_module.run_limited_live_activation(
            confirm=True,
            activation_profile=activation_module.ACTIVATION_PROFILE_NAME,
            profile=activation_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
            skip_branch_check=True,
        )

        assert code == 0
        assert summary["readiness_blocked"] is True
        assert summary["safe"] is True

    def test_config_autonomy_json_remains_unchanged(
        self, safe_temp_parent, triple_gates, activation_module, activation_ready
    ):
        config_path = ROOT / "config" / "autonomy.json"
        before = config_path.read_text(encoding="utf-8")

        summary, code = activation_module.run_limited_live_activation(
            confirm=True,
            activation_profile=activation_module.ACTIVATION_PROFILE_NAME,
            profile=activation_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
            skip_branch_check=True,
        )

        after = config_path.read_text(encoding="utf-8")
        assert code == 0
        assert before == after
        assert summary["config_autonomy_enabled"] is False

    def test_branch_check_enforced_in_operator_mode(
        self, safe_temp_parent, monkeypatch, activation_module, activation_ready
    ):
        monkeypatch.delenv(activation_module._SKIP_BRANCH_CHECK_ENV, raising=False)
        monkeypatch.setattr(
            activation_module,
            "verify_branch",
            lambda **kwargs: (False, ["branch must be 'codex/limited-live-activation-wrapper'"]),
        )

        summary, code = activation_module.run_limited_live_activation(
            confirm=True,
            activation_profile=activation_module.ACTIVATION_PROFILE_NAME,
            profile=activation_module.LIMITED_LIVE_PROFILE_NAME,
            workspace_parent=safe_temp_parent,
            skip_branch_check=False,
        )

        assert code != 0
        assert summary["branch_verified"] is False
        assert summary["smoke_command_invoked"] is False


class TestScriptSurface:
    def test_script_does_not_use_shell_network_browser_api_mutation(self):
        tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
        banned_modules = {
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

    def test_cli_json_run_on_expected_branch(self, triple_gates, activation_module):
        result = subprocess.run(
            [
                PYTHON,
                str(SCRIPT_PATH),
                "--activation-profile",
                activation_module.ACTIVATION_PROFILE_NAME,
                "--profile",
                activation_module.LIMITED_LIVE_PROFILE_NAME,
                "--confirm-limited-live-activation",
                "--json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["safe"] is True
        assert payload["rc_tag_verified"] is True
        assert payload["branch_verified"] is True
        assert payload["executed"] is True
        assert payload["rollback_verified"] is True
        assert payload["workspace_temp_only"] is True
