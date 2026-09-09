import datetime as dt
from types import SimpleNamespace

from project_guardian.core import (
    GuardianCore,
    _mark_activity_from_execution_payload,
    _mark_capability_activity,
)
from project_guardian.module_activity import (
    activity_age_minutes,
    get_module_last_activity,
    mark_module_activity,
)
from project_guardian.self_task_generator import _underused_modules


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
    guardian = SimpleNamespace(
        _modules={"income_generator": object(), "tool_registry": object()},
        _module_last_invoked={},
    )
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


def test_underused_module_fairness_penalizes_recent_repeat_when_others_starved():
    guardian = GuardianCore.__new__(GuardianCore)
    guardian._module_last_invoked = {}
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
            "mistral_recent_module_repeat_penalty_minutes": 30,
            "mistral_recent_module_repeat_penalty_score": 2.5,
        },
    )

    assert candidates[0]["priority_score"] == 8.25
    assert candidates[1]["priority_score"] == 2.5
    assert candidates[1]["_module_fairness_repeat_penalty"]["module"] == "fractalmind"


def test_underused_module_fairness_penalizes_dynamic_capability_repeat():
    guardian = GuardianCore.__new__(GuardianCore)
    guardian._module_last_invoked = {}
    mark_module_activity(
        guardian._module_last_invoked,
        "income_modules",
        when=dt.datetime.now() - dt.timedelta(minutes=5),
    )
    candidates = [
        {"action": "harvest_income_report", "priority_score": 5.0},
        {"action": "use_capability/module/income_generator", "priority_score": 5.0},
    ]

    guardian._apply_underused_module_fairness(
        candidates,
        {
            "mistral_underused_module_boost_minutes": 45,
            "mistral_underused_module_boost_score": 1.75,
            "mistral_starved_module_boost_minutes": 180,
            "mistral_starved_module_boost_score": 3.25,
            "mistral_recent_module_repeat_penalty_minutes": 30,
            "mistral_recent_module_repeat_penalty_score": 2.5,
        },
    )

    assert candidates[0]["priority_score"] == 8.25
    assert candidates[0]["_module_fairness_boost"]["module"] == "harvest_engine"
    assert candidates[1]["priority_score"] == 2.5
    assert candidates[1]["_module_fairness_repeat_penalty"]["module"] == "income_generator"


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
