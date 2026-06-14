"""Tests for passive harmless live-action smoke packet generation."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from project_guardian.live_action_smoke_packet import (
    HARMLESS_LIVE_SMOKE_ACTION_ID,
    HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
    HARMLESS_LIVE_SMOKE_TARGET_FILENAME,
    SmokePathValidationError,
    build_harmless_smoke_approval_packet,
    compute_harmless_smoke_content_hash,
    serialize_harmless_smoke_packet_response,
    validate_harmless_smoke_paths,
)
from project_guardian.live_action_readiness import evaluate_live_mode_readiness

ROOT = Path(__file__).resolve().parents[2]
SMOKE_MODULE = ROOT / "project_guardian" / "live_action_smoke_packet.py"


def _smoke_workspace(tmp_path: Path) -> Path:
    return tmp_path / "isolated_smoke_root"


def _target_path(workspace: Path) -> Path:
    return workspace / "live_smoke_workspace" / HARMLESS_LIVE_SMOKE_TARGET_FILENAME


class TestHarmlessSmokePacketGeneration:
    def test_generates_valid_passive_smoke_packet_for_tmp_workspace(self, tmp_path):
        workspace = _smoke_workspace(tmp_path)
        result = build_harmless_smoke_approval_packet(workspace, repo_root=ROOT)
        response = serialize_harmless_smoke_packet_response(result)

        assert result.packet.ready_for_operator_review is True
        assert result.packet.execution_permitted is False
        assert response["action_id"] == HARMLESS_LIVE_SMOKE_ACTION_ID
        assert response["action_kind"] == "harmless_live_smoke"
        assert response["relative_target_path"] == HARMLESS_LIVE_SMOKE_RELATIVE_TARGET

    def test_packet_contains_deterministic_content_hash(self, tmp_path):
        workspace = _smoke_workspace(tmp_path)
        result = build_harmless_smoke_approval_packet(workspace, repo_root=ROOT)
        expected = compute_harmless_smoke_content_hash()

        assert result.content_hash == expected
        assert result.packet.request.expected_result == expected
        assert len(expected) == 64

    def test_packet_contains_rollback_plan_metadata(self, tmp_path):
        workspace = _smoke_workspace(tmp_path)
        result = build_harmless_smoke_approval_packet(workspace, repo_root=ROOT)

        assert result.rollback_summary["strategy"] == "DELETE_CREATED_FILE"
        assert result.rollback_summary["availability"] == "AVAILABLE"
        assert result.rollback_summary["target"] == HARMLESS_LIVE_SMOKE_RELATIVE_TARGET
        assert result.packet.rollback_validation.valid is True

    def test_packet_contains_audit_preview_metadata(self, tmp_path):
        workspace = _smoke_workspace(tmp_path)
        result = build_harmless_smoke_approval_packet(workspace, repo_root=ROOT)
        response = serialize_harmless_smoke_packet_response(result)

        assert result.audit_preview["action_id"] == HARMLESS_LIVE_SMOKE_ACTION_ID
        assert "event_status" in result.audit_preview
        assert "audit_preview" in response
        assert response["audit_preview"]["target"] == HARMLESS_LIVE_SMOKE_RELATIVE_TARGET

    def test_response_has_no_execution_fields(self, tmp_path):
        workspace = _smoke_workspace(tmp_path)
        result = build_harmless_smoke_approval_packet(workspace, repo_root=ROOT)
        response = serialize_harmless_smoke_packet_response(result)

        assert response["execution_permitted"] is False
        assert response["executed"] is False
        assert response["executor_called"] is False
        assert response["packet"]["execution_permitted"] is False

    def test_target_file_is_not_created(self, tmp_path):
        workspace = _smoke_workspace(tmp_path)
        build_harmless_smoke_approval_packet(workspace, repo_root=ROOT)
        target = _target_path(workspace)
        assert not target.exists()
        assert not workspace.exists()

    def test_does_not_mark_readiness_ready(self, tmp_path):
        workspace = _smoke_workspace(tmp_path)
        result = build_harmless_smoke_approval_packet(workspace, repo_root=ROOT)
        response = serialize_harmless_smoke_packet_response(result)
        report = evaluate_live_mode_readiness()

        assert response["readiness_blocked"] is True
        assert report.ready_for_limited_live_mode is False
        assert report.status.value == "BLOCKED"


class TestUnsafePathRejection:
    def test_rejects_repo_root_workspace(self, tmp_path):
        validation = validate_harmless_smoke_paths(ROOT, repo_root=ROOT)
        assert validation.valid is False
        assert SmokePathValidationError.WORKSPACE_IS_REPO_ROOT.value in validation.reasons

        with pytest.raises(ValueError, match="WORKSPACE_IS_REPO_ROOT"):
            build_harmless_smoke_approval_packet(ROOT, repo_root=ROOT)

    def test_rejects_path_traversal_outside_smoke_workspace(self, tmp_path):
        workspace = _smoke_workspace(tmp_path)
        validation = validate_harmless_smoke_paths(
            workspace,
            relative_target="live_smoke_workspace/../../escape.txt",
            repo_root=ROOT,
        )
        assert validation.valid is False
        assert SmokePathValidationError.TARGET_OUTSIDE_WORKSPACE.value in validation.reasons

    def test_rejects_user_data_style_workspace(self, tmp_path):
        workspace = tmp_path / "Users" / "operator" / "Documents" / "smoke"
        validation = validate_harmless_smoke_paths(workspace.resolve(), repo_root=ROOT)
        assert validation.valid is False
        assert SmokePathValidationError.USER_DATA_PATH.value in validation.reasons

    def test_rejects_network_style_target(self, tmp_path):
        workspace = _smoke_workspace(tmp_path)
        validation = validate_harmless_smoke_paths(
            workspace,
            relative_target="https://example.com/approved_smoke.txt",
            repo_root=ROOT,
        )
        assert validation.valid is False
        assert SmokePathValidationError.NETWORK_PATH.value in validation.reasons

    def test_rejects_external_storage_workspace(self, tmp_path, monkeypatch):
        external = tmp_path / "external_volume"
        external.mkdir()
        workspace = external / "smoke_workspace"
        monkeypatch.setattr(
            "project_guardian.live_action_smoke_packet._get_external_storage_dir",
            lambda: external,
        )
        validation = validate_harmless_smoke_paths(workspace.resolve(), repo_root=ROOT)
        assert validation.valid is False
        assert SmokePathValidationError.EXTERNAL_STORAGE_PATH.value in validation.reasons


class TestNoExecutorCall:
    def test_module_has_no_executor_calls(self):
        source = SMOKE_MODULE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {
            "execute_live_action",
            "run_for_proposal",
            "ImplementerAgent",
            "apply_mutation",
            "append_live_action_audit_record",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden

    def test_module_does_not_import_core_or_server(self):
        source = SMOKE_MODULE.read_text(encoding="utf-8")
        assert "project_guardian.core" not in source
        assert "elysia.api.server" not in source
