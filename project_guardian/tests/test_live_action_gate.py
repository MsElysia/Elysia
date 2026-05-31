"""Tests for passive Phase 2 live-action gate scaffolding."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from project_guardian.live_action_gate import (
    PHASE2_POLICY,
    ActionRiskCategory,
    AllowlistDecision,
    LiveActionApprovalRequest,
    build_approval_request,
    policy_decision_for_category,
    validate_live_action_request,
)

ROOT = Path(__file__).resolve().parents[2]
GATE_MODULE = ROOT / "project_guardian" / "live_action_gate.py"


def _request(category: ActionRiskCategory, **overrides) -> LiveActionApprovalRequest:
    base = build_approval_request(
        proposed_action=f"test:{category.value.lower()}",
        reason="unit test",
        risk_category=category,
        target="test-target",
        expected_result="none",
        rollback_plan="none",
    )
    if not overrides:
        return base
    return LiveActionApprovalRequest(
        action_id=overrides.get("action_id", base.action_id),
        proposed_action=overrides.get("proposed_action", base.proposed_action),
        reason=overrides.get("reason", base.reason),
        risk_category=overrides.get("risk_category", base.risk_category),
        target=overrides.get("target", base.target),
        expected_result=overrides.get("expected_result", base.expected_result),
        rollback_plan=overrides.get("rollback_plan", base.rollback_plan),
        touches_autonomy_or_live_execution=overrides.get(
            "touches_autonomy_or_live_execution", base.touches_autonomy_or_live_execution
        ),
        writes_files=overrides.get("writes_files", base.writes_files),
        touches_network_api_or_browser=overrides.get(
            "touches_network_api_or_browser", base.touches_network_api_or_browser
        ),
        allowlist_decision=overrides.get("allowlist_decision", base.allowlist_decision),
    )


class TestPhase2PolicyTable:
    def test_policy_covers_every_risk_category(self) -> None:
        assert set(PHASE2_POLICY.keys()) == set(ActionRiskCategory)
        assert len(PHASE2_POLICY) == len(ActionRiskCategory)

    @pytest.mark.parametrize(
        "category,expected",
        [
            (ActionRiskCategory.READ_ONLY, AllowlistDecision.ALLOW_LOGGED),
            (ActionRiskCategory.WRITE_REPORT, AllowlistDecision.REQUIRE_APPROVAL),
            (ActionRiskCategory.MEMORY_WRITE, AllowlistDecision.REQUIRE_APPROVAL),
            (ActionRiskCategory.LOCAL_FILE_WRITE, AllowlistDecision.REQUIRE_APPROVAL),
            (ActionRiskCategory.LOCAL_FILE_MODIFY, AllowlistDecision.REQUIRE_APPROVAL),
            (ActionRiskCategory.SHELL_COMMAND, AllowlistDecision.BLOCKED),
            (ActionRiskCategory.NETWORK_REQUEST, AllowlistDecision.BLOCKED),
            (ActionRiskCategory.API_CALL, AllowlistDecision.BLOCKED),
            (ActionRiskCategory.BROWSER_OR_WEBSCOUT, AllowlistDecision.BLOCKED),
            (ActionRiskCategory.CODE_CHANGE, AllowlistDecision.REQUIRE_APPROVAL),
            (ActionRiskCategory.PROPOSAL_IMPLEMENTATION, AllowlistDecision.BLOCKED),
            (ActionRiskCategory.CONFIG_CHANGE, AllowlistDecision.REQUIRE_APPROVAL),
            (ActionRiskCategory.AUTONOMY_CONFIG_CHANGE, AllowlistDecision.BLOCKED),
        ],
    )
    def test_policy_decision_matches_design(
        self, category: ActionRiskCategory, expected: AllowlistDecision
    ) -> None:
        assert policy_decision_for_category(category) is expected


class TestValidateLiveActionRequest:
    def test_read_only_allowed_logged(self) -> None:
        result = validate_live_action_request(_request(ActionRiskCategory.READ_ONLY))
        assert result.allowed is True
        assert result.requires_approval is False
        assert result.blocked is False
        assert result.decision is AllowlistDecision.ALLOW_LOGGED
        assert result.safety_verdict == "SAFE"

    @pytest.mark.parametrize(
        "category",
        [
            ActionRiskCategory.WRITE_REPORT,
            ActionRiskCategory.LOCAL_FILE_WRITE,
            ActionRiskCategory.CODE_CHANGE,
        ],
    )
    def test_requires_approval_categories(self, category: ActionRiskCategory) -> None:
        result = validate_live_action_request(_request(category))
        assert result.allowed is False
        assert result.requires_approval is True
        assert result.blocked is False
        assert result.decision is AllowlistDecision.REQUIRE_APPROVAL
        assert result.safety_verdict == "SAFE"

    @pytest.mark.parametrize(
        "category",
        [
            ActionRiskCategory.SHELL_COMMAND,
            ActionRiskCategory.NETWORK_REQUEST,
            ActionRiskCategory.API_CALL,
            ActionRiskCategory.BROWSER_OR_WEBSCOUT,
            ActionRiskCategory.PROPOSAL_IMPLEMENTATION,
            ActionRiskCategory.AUTONOMY_CONFIG_CHANGE,
        ],
    )
    def test_blocked_categories(self, category: ActionRiskCategory) -> None:
        result = validate_live_action_request(_request(category))
        assert result.blocked is True
        assert result.allowed is False
        assert result.requires_approval is False
        assert result.decision is AllowlistDecision.BLOCKED
        assert result.safety_verdict == "BLOCKED"
        assert result.reasons

    def test_touches_autonomy_or_live_execution_blocks_read_only(self) -> None:
        result = validate_live_action_request(
            _request(
                ActionRiskCategory.READ_ONLY,
                touches_autonomy_or_live_execution=True,
            )
        )
        assert result.blocked is True
        assert "touches_autonomy_or_live_execution" in result.reasons

    def test_build_approval_request_sets_allowlist_decision(self) -> None:
        req = build_approval_request(
            proposed_action="write_report:weekly",
            reason="operator digest",
            risk_category=ActionRiskCategory.WRITE_REPORT,
            target="REPORTS/weekly.md",
            expected_result="file created",
            rollback_plan="delete file",
            writes_files=True,
        )
        assert req.allowlist_decision is AllowlistDecision.REQUIRE_APPROVAL
        assert req.action_id


class TestPassiveModule:
    def test_module_does_not_import_execution_systems(self) -> None:
        tree = ast.parse(GATE_MODULE.read_text(encoding="utf-8"))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        forbidden = (
            "subprocess",
            "httpx",
            "requests",
            "flask",
            "elysia",
            "project_guardian.capability_execution",
            "project_guardian.tool_executor",
            "project_guardian.webscout_agent",
            "project_guardian.bounded_browser",
        )
        for imp in imports:
            for bad in forbidden:
                assert imp != bad and not imp.startswith(bad + ".")

    def test_validator_is_pure_no_side_effects(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        before = set(tmp_path.iterdir())
        result = validate_live_action_request(_request(ActionRiskCategory.READ_ONLY))
        after = set(tmp_path.iterdir())
        assert before == after
        assert result.allowed is True
