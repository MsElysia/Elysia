# project_guardian/tests/test_unified_api_budget.py

import pytest

from project_guardian.unified_api_budget import (
    can_spend,
    charge_successful_call,
    enabled,
    flat_units_for_channel,
    max_units_per_period,
    remaining_units,
    reset_period_state_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_ub():
    reset_period_state_for_tests()
    yield
    reset_period_state_for_tests()


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ELYSIA_UNIFIED_BUDGET_ENABLED", raising=False)
    assert enabled() is False
    assert remaining_units() == float("inf")
    assert can_spend(1e9) is True


def test_charge_respects_cap(monkeypatch):
    monkeypatch.setenv("ELYSIA_UNIFIED_BUDGET_ENABLED", "1")
    monkeypatch.setenv("ELYSIA_UNIFIED_BUDGET_MAX_UNITS", "100")
    monkeypatch.setenv("ELYSIA_UNIFIED_BUDGET_PERIOD_SEC", "3600")

    assert enabled() is True
    assert max_units_per_period() == 100.0

    ok1, u1 = charge_successful_call("openai_chat", True, usage={"total_tokens": 40})
    assert ok1 is True and u1 == 40

    ok2, u2 = charge_successful_call("openai_chat", True, usage={"total_tokens": 70})
    assert ok2 is True and u2 == 60

    assert remaining_units() == 0.0
    assert can_spend(1) is False


def test_flat_when_no_usage(monkeypatch):
    monkeypatch.setenv("ELYSIA_UNIFIED_BUDGET_ENABLED", "1")
    monkeypatch.setenv("ELYSIA_UNIFIED_BUDGET_MAX_UNITS", "5000")
    monkeypatch.setenv("ELYSIA_UNIFIED_BUDGET_PERIOD_SEC", "3600")

    assert flat_units_for_channel("brave_search") >= 1
    ok, u = charge_successful_call("brave_search", True, usage=None)
    assert ok is True
    assert u == flat_units_for_channel("brave_search")


def test_effective_chat_preflight_softens_when_surplus(monkeypatch):
    from project_guardian.unified_api_budget import (
        effective_cloud_chat_preflight,
        flat_units_for_channel,
        opportunistic_surplus_available,
        preflight_cloud_chat_estimate,
    )

    monkeypatch.setenv("ELYSIA_UNIFIED_BUDGET_ENABLED", "1")
    monkeypatch.setenv("ELYSIA_UNIFIED_BUDGET_MAX_UNITS", "100000")
    monkeypatch.setenv("ELYSIA_UNIFIED_BUDGET_PERIOD_SEC", "3600")

    full = preflight_cloud_chat_estimate(8192)
    assert opportunistic_surplus_available() is True
    soft = effective_cloud_chat_preflight("openai", 8192)
    assert soft <= full
    assert soft >= flat_units_for_channel("openai_chat")
