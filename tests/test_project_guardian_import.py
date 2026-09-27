"""Regression coverage for the supported project_guardian import path.

The package import failed when core.py referenced module_activity and the
planner routine loggers that existed on later branches but were absent from
main. These tests import the package and exercise those restored call sites.
"""

import datetime as dt
import logging

import pytest

import project_guardian
from project_guardian import GuardianCore
from project_guardian.core import (
    _mark_activity_from_execution_payload,
    _mark_capability_activity,
)
from project_guardian.module_activity import (
    activity_age_minutes,
    get_module_last_activity,
    mark_module_activity,
)
from project_guardian.planner_readiness import (
    log_autonomy_exploration_routine,
    log_autonomy_routine,
)
from project_guardian.self_task_generator import _underused_modules


def test_project_guardian_package_import_exposes_public_api():
    assert project_guardian.GuardianCore is GuardianCore
    assert "GuardianCore" in project_guardian.__all__
    public = {}
    exec("from project_guardian import *", public)  # noqa: S102 - asserted import contract
    for name in project_guardian.__all__:
        assert name in public
        assert public[name] is getattr(project_guardian, name)


def test_income_bundle_activity_aliases_cover_member_modules():
    used = {}
    stamp = mark_module_activity(
        used,
        "income_modules",
        when=dt.datetime(2026, 4, 18, 20, 0, 0),
    )

    assert stamp is not None
    assert used["income_generator"] == stamp
    assert used["wallet"] == stamp
    assert used["financial_manager"] == stamp
    assert get_module_last_activity(used, "revenue_creator") == stamp
    assert activity_age_minutes(
        used,
        "income_generator",
        now=dt.datetime(2026, 4, 18, 21, 0, 0),
    ) == 60.0


def test_underused_modules_treat_recent_income_bundle_as_active():
    guardian = type("Guardian", (), {})()
    guardian._modules = {"income_generator": object(), "tool_registry": object()}
    guardian._module_last_invoked = {}
    mark_module_activity(
        guardian._module_last_invoked,
        "income_modules",
        when=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10),
    )

    underused = _underused_modules(guardian, min_hours=2.0)

    assert "income_generator" not in underused
    assert "tool_registry" in underused


def test_underused_module_fairness_boosts_stale_learning_candidates():
    guardian = GuardianCore.__new__(GuardianCore)
    guardian._module_last_invoked = {}
    mark_module_activity(
        guardian._module_last_invoked,
        "learning",
        when=dt.datetime.now() - dt.timedelta(hours=4),
    )
    mark_module_activity(
        guardian._module_last_invoked,
        "fractalmind",
        when=dt.datetime.now() - dt.timedelta(minutes=5),
    )
    candidates = [
        {"action": "consider_learning", "priority_score": 5.0},
        {"action": "fractalmind_planning", "priority_score": 5.0},
    ]

    guardian._apply_underused_module_fairness(
        candidates,
        {
            "mistral_underused_module_boost_minutes": 45,
            "mistral_underused_module_boost_score": 1.75,
            "mistral_starved_module_boost_minutes": 180,
            "mistral_starved_module_boost_score": 3.25,
        },
    )

    assert candidates[0]["priority_score"] == 8.25
    assert candidates[0]["_module_fairness_boost"]["module"] == "learning"
    assert "_module_fairness_boost" not in candidates[1]


def test_direct_self_task_capability_marks_income_bundle_activity():
    used = {}

    stamp = _mark_capability_activity(used, "module", "income_generator")

    assert stamp is not None
    assert used["income_generator"] == stamp
    assert used["wallet"] == stamp
    assert used["financial_manager"] == stamp


def test_orchestration_execution_payload_marks_tool_registry_activity():
    used = {}

    stamp = _mark_activity_from_execution_payload(
        used,
        {
            "target_kind": "tool",
            "target_name": "elysia_builtin_llm",
            "success": True,
        },
    )

    assert stamp is not None
    assert used["tool_registry"] == stamp


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_log_autonomy_routine_level_follows_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    import project_guardian.planner_readiness as pr

    cap = _ListHandler()
    cap.setLevel(logging.DEBUG)
    lg = logging.getLogger("pg_test_autonomy_routine")
    lg.handlers.clear()
    lg.setLevel(logging.DEBUG)
    lg.propagate = False
    lg.addHandler(cap)

    monkeypatch.delenv("ELYSIA_EXPLORATION_INFO_WHEN_READY", raising=False)
    monkeypatch.delenv("ELYSIA_AUTONOMY_ROUTINE_INFO_WHEN_READY", raising=False)
    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    log_autonomy_routine(lg, "tick %s", "a")
    assert cap.records[-1].levelno == logging.DEBUG

    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "degraded")
    log_autonomy_exploration_routine(lg, "[Exploration] tick %s", "b")
    assert cap.records[-1].levelno == logging.INFO
    assert cap.records[-1].getMessage().startswith("[Exploration]")

    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    monkeypatch.setenv("ELYSIA_AUTONOMY_ROUTINE_INFO_WHEN_READY", "1")
    log_autonomy_routine(lg, "tick %s", "c")
    assert cap.records[-1].levelno == logging.INFO
