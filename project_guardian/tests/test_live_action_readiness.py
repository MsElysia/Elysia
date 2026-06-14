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


def _item_for(report, check: ReadinessCheck):
    for item in report.items:
        if item.check is check:
            return item
    raise AssertionError(f"missing check {check}")


class TestDefaultReadiness:
    def test_default_is_not_ready(self) -> None:
        report = evaluate_live_mode_readiness()

        assert report.ready_for_limited_live_mode is False
        assert report.status in (ReadinessStatus.NOT_READY, ReadinessStatus.BLOCKED)
        assert report.safety_verdict == "NOT_READY_FOR_LIVE_MODE"

    def test_default_dirty_core_cleaned_passes(self) -> None:
        report = evaluate_live_mode_readiness()
        item = _item_for(report, ReadinessCheck.DIRTY_CORE_CLEANED)

        assert item.passed is True
        assert item.blocker is False
        assert not any("DIRTY_CORE_CLEANED" in blocker for blocker in report.blockers)

    def test_default_dirty_server_cleaned_passes(self) -> None:
        report = evaluate_live_mode_readiness()
        item = _item_for(report, ReadinessCheck.DIRTY_SERVER_CLEANED)

        assert item.passed is True
        assert item.blocker is False
        assert not any("DIRTY_SERVER_CLEANED" in blocker for blocker in report.blockers)

    def test_default_blockers_include_missing_live_executor(self) -> None:
        report = evaluate_live_mode_readiness()
        item = _item_for(report, ReadinessCheck.LIVE_EXECUTOR_IMPLEMENTED)

        assert item.passed is False
        assert item.blocker is True
        assert any("LIVE_EXECUTOR_IMPLEMENTED" in blocker for blocker in report.blockers)

    def test_default_blockers_include_missing_approval_route(self) -> None:
        report = evaluate_live_mode_readiness()
        item = _item_for(report, ReadinessCheck.UI_OR_API_APPROVAL_ROUTE_IMPLEMENTED)

        assert item.passed is False
        assert item.blocker is True
        assert any("UI_OR_API_APPROVAL_ROUTE_IMPLEMENTED" in blocker for blocker in report.blockers)

    def test_default_blockers_include_missing_harmless_live_smoke(self) -> None:
        report = evaluate_live_mode_readiness()
        item = _item_for(report, ReadinessCheck.HARMLESS_LIVE_ACTION_SMOKE_VERIFIED)

        assert item.passed is False
        assert item.blocker is True
        assert any("HARMLESS_LIVE_ACTION_SMOKE_VERIFIED" in blocker for blocker in report.blockers)

    def test_default_full_runtime_tests_classified_passes(self) -> None:
        report = evaluate_live_mode_readiness()
        item = _item_for(report, ReadinessCheck.FULL_RUNTIME_TESTS_CLASSIFIED)

        assert item.passed is True
        assert item.blocker is False
        assert item.status is ReadinessStatus.READY
        assert not any("FULL_RUNTIME_TESTS_CLASSIFIED" in blocker for blocker in report.blockers)

    def test_default_remaining_failures_repaired_or_waived(self) -> None:
        report = evaluate_live_mode_readiness()
        item = _item_for(
            report,
            ReadinessCheck.FULL_RUNTIME_REMAINING_NONCRITICAL_FAILURES_WAIVED_OR_REPAIRED,
        )

        assert item.passed is True
        assert item.blocker is False
        assert item.status is ReadinessStatus.READY
        assert not any(
            "FULL_RUNTIME_REMAINING_NONCRITICAL_FAILURES_NEED_WAIVER_OR_REPAIR" in action
            for action in report.next_required_actions
        )


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
        assert runtime["FULL_RUNTIME_ERROR_COUNT"] == 0
        assert runtime["FULL_RUNTIME_REMAINING_FAILURES_NON_SAFETY_CRITICAL"] is True
        assert runtime["FULL_RUNTIME_PASS_COUNT"] == 439


class TestSerialization:
    def test_serializer_is_json_safe(self) -> None:
        report = evaluate_live_mode_readiness()
        payload = serialize_live_mode_readiness_report(report)

        encoded = json.dumps(payload, ensure_ascii=False)
        decoded = json.loads(encoded)
        assert decoded["ready_for_limited_live_mode"] is False
        assert decoded["safety_verdict"] == "NOT_READY_FOR_LIVE_MODE"
        assert decoded["runtime_test_evidence"]["FULL_RUNTIME_FAILURE_COUNT"] == 0
        assert isinstance(decoded["items"], list)
        assert decoded["items"][0]["check"] in {c.value for c in ReadinessCheck}


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

        stdlib_ok = {
            "__future__",
            "dataclasses",
            "enum",
            "typing",
        }
        for imp in imports:
            assert imp in stdlib_ok, f"unexpected import: {imp}"

        forbidden = (
            "subprocess",
            "httpx",
            "requests",
            "flask",
            "elysia",
            "project_guardian",
        )
        for imp in imports:
            for bad in forbidden:
                assert imp != bad and not imp.startswith(bad + ".")
