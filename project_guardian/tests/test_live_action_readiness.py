"""Tests for passive Phase 2 live-mode readiness evaluation."""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path

from project_guardian.live_action_readiness import (
    DEFAULT_EVIDENCE,
    ReadinessCheck,
    ReadinessStatus,
    evaluate_live_mode_readiness,
    serialize_live_mode_readiness_report,
)

ROOT = Path(__file__).resolve().parents[2]
READINESS_MODULE = ROOT / "project_guardian" / "live_action_readiness.py"

_REMAINING_BLOCKER_KEYS = (
    "PRODUCTION_LIVE_EXECUTION_DISABLED_BY_DEFAULT",
    "AUTONOMY_CONFIG_DISABLED",
)

_STALE_BLOCKER_KEYS = (
    "LIMITED_LIVE_PROFILE_NOT_DECLARED",
    "OPERATOR_LIMITED_LIVE_RUNBOOK_MISSING",
)


def _item_for(report, check: ReadinessCheck):
    for item in report.items:
        if item.check is check:
            return item
    raise AssertionError(f"missing check {check}")


def _has_remaining_limited_live_blocker(report) -> bool:
    return any(
        any(key in blocker for key in _REMAINING_BLOCKER_KEYS)
        for blocker in report.blockers
    )


class TestDefaultReadiness:
    def test_default_is_blocked_not_ready(self) -> None:
        report = evaluate_live_mode_readiness()

        assert report.ready_for_limited_live_mode is False
        assert report.status is ReadinessStatus.BLOCKED
        assert report.safety_verdict == "NOT_READY_FOR_LIVE_MODE"
        assert report.status is not ReadinessStatus.READY

    def test_default_route_execution_wiring_evidence(self) -> None:
        report = evaluate_live_mode_readiness()

        wired = _item_for(report, ReadinessCheck.APPROVAL_ROUTE_EXECUTION_WIRED)
        triple = _item_for(report, ReadinessCheck.APPROVAL_ROUTE_EXECUTION_TRIPLE_GATED)
        decision_only = _item_for(report, ReadinessCheck.APPROVAL_ROUTE_DEFAULT_DECISION_ONLY)
        non_approve = _item_for(report, ReadinessCheck.APPROVAL_ROUTE_NON_APPROVE_NEVER_EXECUTES)
        tmp_workspace = _item_for(
            report, ReadinessCheck.APPROVAL_ROUTE_EXECUTION_VERIFIED_IN_TMP_WORKSPACE
        )

        assert wired.passed is True
        assert triple.passed is True
        assert decision_only.passed is True
        assert non_approve.passed is True
        assert tmp_workspace.passed is True
        assert not any("APPROVAL_ROUTE_NOT_WIRED_TO_EXECUTOR" in b for b in report.blockers)

    def test_default_verified_executor_smoke_and_rollback(self) -> None:
        report = evaluate_live_mode_readiness()

        executor_item = _item_for(report, ReadinessCheck.LIVE_EXECUTOR_IMPLEMENTED)
        smoke_item = _item_for(report, ReadinessCheck.HARMLESS_LIVE_ACTION_SMOKE_VERIFIED)
        rollback_item = _item_for(report, ReadinessCheck.HARMLESS_LIVE_ACTION_ROLLBACK_VERIFIED)

        assert executor_item.passed is True
        assert smoke_item.passed is True
        assert rollback_item.passed is True

    def test_default_profile_and_runbook_declared(self) -> None:
        report = evaluate_live_mode_readiness()

        profile_item = _item_for(report, ReadinessCheck.LIMITED_LIVE_PROFILE_DECLARED)
        runbook_item = _item_for(report, ReadinessCheck.OPERATOR_LIMITED_LIVE_RUNBOOK_PRESENT)

        assert profile_item.passed is True
        assert runbook_item.passed is True
        assert profile_item.blocker is False
        assert runbook_item.blocker is False
        assert not any(key in b for b in report.blockers for key in _STALE_BLOCKER_KEYS)

    def test_default_limited_live_smoke_command_evidence(self) -> None:
        report = evaluate_live_mode_readiness()

        present = _item_for(report, ReadinessCheck.LIMITED_LIVE_SMOKE_COMMAND_PRESENT)
        verified = _item_for(report, ReadinessCheck.LIMITED_LIVE_SMOKE_COMMAND_VERIFIED)
        temp_only = _item_for(report, ReadinessCheck.LIMITED_LIVE_SMOKE_WORKSPACE_TEMP_ONLY)
        unsafe_rejected = _item_for(
            report, ReadinessCheck.LIMITED_LIVE_SMOKE_UNSAFE_WORKSPACES_REJECTED
        )
        rollback = _item_for(report, ReadinessCheck.LIMITED_LIVE_SMOKE_ROLLBACK_VERIFIED)

        assert present.passed is True
        assert verified.passed is True
        assert temp_only.passed is True
        assert unsafe_rejected.passed is True
        assert rollback.passed is True
        for item in (present, verified, temp_only, unsafe_rejected, rollback):
            assert item.blocker is False

    def test_default_limited_live_activation_wrapper_evidence(self) -> None:
        report = evaluate_live_mode_readiness()

        present = _item_for(report, ReadinessCheck.LIMITED_LIVE_ACTIVATION_WRAPPER_PRESENT)
        verified = _item_for(report, ReadinessCheck.LIMITED_LIVE_ACTIVATION_WRAPPER_VERIFIED)
        confirmation = _item_for(
            report, ReadinessCheck.LIMITED_LIVE_ACTIVATION_OPERATOR_CONFIRMATION_REQUIRED
        )
        profile = _item_for(report, ReadinessCheck.LIMITED_LIVE_ACTIVATION_PROFILE_REQUIRED)
        rc_tag = _item_for(
            report, ReadinessCheck.LIMITED_LIVE_ACTIVATION_RC_TAG_VALIDATION_PRESENT
        )
        config_disabled = _item_for(
            report, ReadinessCheck.LIMITED_LIVE_ACTIVATION_CONFIG_DISABLED_VALIDATION_PRESENT
        )
        rollback = _item_for(report, ReadinessCheck.LIMITED_LIVE_ACTIVATION_ROLLBACK_VERIFIED)

        assert present.passed is True
        assert verified.passed is True
        assert confirmation.passed is True
        assert profile.passed is True
        assert rc_tag.passed is True
        assert config_disabled.passed is True
        assert rollback.passed is True
        for item in (present, verified, confirmation, profile, rc_tag, config_disabled, rollback):
            assert item.blocker is False

        assert report.ready_for_limited_live_mode is False
        assert report.status is ReadinessStatus.BLOCKED
        assert _has_remaining_limited_live_blocker(report)

    def test_default_prior_route_wiring_evidence_still_true(self) -> None:
        report = evaluate_live_mode_readiness()

        wired = _item_for(report, ReadinessCheck.APPROVAL_ROUTE_EXECUTION_WIRED)
        triple = _item_for(report, ReadinessCheck.APPROVAL_ROUTE_EXECUTION_TRIPLE_GATED)

        assert wired.passed is True
        assert triple.passed is True

    def test_default_remaining_limited_live_blockers(self) -> None:
        report = evaluate_live_mode_readiness()

        assert _has_remaining_limited_live_blocker(report)
        assert any("PRODUCTION_LIVE_EXECUTION_DISABLED_BY_DEFAULT" in b for b in report.blockers)
        assert any("AUTONOMY_CONFIG_DISABLED" in b for b in report.blockers)
        assert not any(key in b for b in report.blockers for key in _STALE_BLOCKER_KEYS)

    def test_default_autonomy_config_safety_verification_passes(self) -> None:
        report = evaluate_live_mode_readiness()
        item = _item_for(report, ReadinessCheck.AUTONOMY_CONFIG_DEFAULT_DISABLED)

        assert item.passed is True
        assert item.blocker is False

    def test_default_dirty_core_cleaned_passes(self) -> None:
        report = evaluate_live_mode_readiness()
        item = _item_for(report, ReadinessCheck.DIRTY_CORE_CLEANED)

        assert item.passed is True
        assert item.blocker is False

    def test_default_dirty_server_cleaned_passes(self) -> None:
        report = evaluate_live_mode_readiness()
        item = _item_for(report, ReadinessCheck.DIRTY_SERVER_CLEANED)

        assert item.passed is True
        assert item.blocker is False

    def test_default_full_runtime_tests_classified_passes(self) -> None:
        report = evaluate_live_mode_readiness()
        item = _item_for(report, ReadinessCheck.FULL_RUNTIME_TESTS_CLASSIFIED)

        assert item.passed is True
        assert item.blocker is False
        assert item.status is ReadinessStatus.READY

    def test_default_remaining_failures_repaired_or_waived(self) -> None:
        report = evaluate_live_mode_readiness()
        item = _item_for(
            report,
            ReadinessCheck.FULL_RUNTIME_REMAINING_NONCRITICAL_FAILURES_WAIVED_OR_REPAIRED,
        )

        assert item.passed is True
        assert item.blocker is False
        assert item.status is ReadinessStatus.READY


class TestAllChecksPassing:
    def test_all_required_checks_passing_returns_ready_status(self) -> None:
        evidence = {key: True for key in DEFAULT_EVIDENCE}
        report = evaluate_live_mode_readiness(evidence)

        assert report.status is ReadinessStatus.READY
        assert all(item.passed for item in report.items if item.required)
        assert report.blockers == ()
        assert report.safety_verdict == "READY_FOR_LIMITED_LIVE_MODE"
        assert report.ready_for_limited_live_mode is True


class TestPostRepairRuntimeEvidence:
    def test_default_runtime_test_evidence_reflects_post_repair_classification(self) -> None:
        payload = serialize_live_mode_readiness_report(evaluate_live_mode_readiness())
        runtime = payload["runtime_test_evidence"]

        assert runtime["FULL_RUNTIME_CLASSIFIED_POST_REPAIRS"] is True
        assert runtime["FULL_RUNTIME_FAILURE_COUNT"] == 0
        assert runtime["FULL_RUNTIME_REMAINING_FAILURES_REPAIRED"] is True
        assert runtime["HARMLESS_LIVE_ACTION_SMOKE_DESIGNED"] is True
        assert runtime["FULL_RUNTIME_PASS_COUNT"] == 439


class TestSerialization:
    def test_serializer_includes_limited_live_profile_evidence(self) -> None:
        report = evaluate_live_mode_readiness()
        payload = serialize_live_mode_readiness_report(report)

        assert payload["limited_live_profile_evidence"]["LIMITED_LIVE_PROFILE_NAME"] == (
            "operator_approved_harmless_smoke_v1"
        )
        assert payload["limited_live_profile_evidence"]["LIMITED_LIVE_ALLOWED_ACTION"] == (
            "harmless_smoke_only"
        )

    def test_serializer_includes_limited_live_smoke_command_evidence(self) -> None:
        report = evaluate_live_mode_readiness()
        payload = serialize_live_mode_readiness_report(report)
        smoke = payload["limited_live_smoke_command_evidence"]

        assert smoke["LIMITED_LIVE_SMOKE_COMMAND_SCRIPT"] == "scripts/run_limited_live_smoke.py"
        assert smoke["LIMITED_LIVE_SMOKE_WORKSPACE_POLICY"] == "system_temp_only"
        assert smoke["LIMITED_LIVE_SMOKE_UNSAFE_WORKSPACE_REJECTION"] is True
        assert smoke["LIMITED_LIVE_SMOKE_ROLLBACK_VERIFIED_BY_COMMAND"] is True

    def test_serializer_includes_limited_live_activation_wrapper_evidence(self) -> None:
        report = evaluate_live_mode_readiness()
        payload = serialize_live_mode_readiness_report(report)
        wrapper = payload["limited_live_activation_wrapper_evidence"]

        assert wrapper["LIMITED_LIVE_ACTIVATION_WRAPPER_SCRIPT"] == (
            "scripts/run_limited_live_activation.py"
        )
        assert wrapper["LIMITED_LIVE_ACTIVATION_PROFILE_NAME"] == (
            "limited_live_harmless_smoke_activation_v1"
        )
        assert wrapper["LIMITED_LIVE_ACTIVATION_RC_TAG"] == "limited_live_rc_1"
        assert wrapper["LIMITED_LIVE_ACTIVATION_RC_TAG_TARGET"] == "236f0b5"
        assert wrapper["LIMITED_LIVE_ACTIVATION_OPERATOR_CONFIRMATION_FLAG"] == (
            "--confirm-limited-live-activation"
        )
        assert wrapper["LIMITED_LIVE_ACTIVATION_ROLLBACK_VERIFIED_BY_WRAPPER"] is True

    def test_serializer_is_json_safe(self) -> None:
        report = evaluate_live_mode_readiness()
        payload = serialize_live_mode_readiness_report(report)

        encoded = json.dumps(payload, ensure_ascii=False)
        decoded = json.loads(encoded)
        assert decoded["ready_for_limited_live_mode"] is False
        assert decoded["safety_verdict"] == "NOT_READY_FOR_LIVE_MODE"
        assert isinstance(decoded["items"], list)


class TestPassiveModule:
    def test_evaluator_creates_no_files(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        evaluate_live_mode_readiness()
        assert list(tmp_path.iterdir()) == []

    def test_import_creates_no_files(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        importlib.import_module("project_guardian.live_action_readiness")
        assert list(tmp_path.iterdir()) == []

    def test_module_imports_standard_library_only(self) -> None:
        tree = ast.parse(READINESS_MODULE.read_text(encoding="utf-8"))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        stdlib_ok = {"__future__", "dataclasses", "enum", "typing"}
        for imp in imports:
            assert imp in stdlib_ok, f"unexpected import: {imp}"
