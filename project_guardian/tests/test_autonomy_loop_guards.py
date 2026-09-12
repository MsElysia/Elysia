"""Focused tests for autonomy-loop anti-churn guards and proposal scaffold."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import pytest

from project_guardian import autonomy_antiloop as antiloop
from project_guardian.planner_readiness import (
    apply_autonomy_loop_load_guards,
    autonomy_exploration_log_use_debug,
    autonomy_noop_suppression_factor,
    clear_autonomy_noop_streak,
    equivalent_autonomy_action_key,
    execute_task_system_monitoring_priority_factor,
    fractalmind_planning_repeat_priority_factor,
    harvest_zero_yield_priority_factor,
    income_generator_capability_stale_factor,
    income_pulse_duplicate_priority_factor,
    is_revenue_monetization_archetype,
    process_queue_stale_probe_priority_factor,
    record_autonomy_noop_outcome,
    record_harvest_zero_yield_outcome,
    use_capability_module_stale_factor,
    web_capability_missing_url_priority_factor,
)
from project_guardian.proposal_system import ProposalValidator


class _G:
    """Minimal guardian stub for priority-factor tests."""

    __slots__ = (
        "_execute_task_monitoring_select_streak",
        "_process_queue_unchanged_streak",
        "_process_queue_noop_deprioritize_until",
        "_income_pulse_same_zero_sig_streak",
        "_fractalmind_same_artifact_streak",
        "_fractalmind_repetition_suppress_until",
        "_income_generator_autonomy_cap_streak",
    )

    def __init__(self) -> None:
        self._execute_task_monitoring_select_streak = 0
        self._process_queue_unchanged_streak = 0
        self._process_queue_noop_deprioritize_until = 0.0
        self._income_pulse_same_zero_sig_streak = 0
        self._fractalmind_same_artifact_streak = 0
        self._fractalmind_repetition_suppress_until = 0.0
        self._income_generator_autonomy_cap_streak = 0


def test_execute_task_system_monitoring_downranks_with_streak_and_recent_tail() -> None:
    g = _G()
    g._execute_task_monitoring_select_streak = 3
    cand = {
        "action": "execute_task",
        "metadata": {"name": "system_monitoring"},
        "priority_score": 100.0,
    }
    recent = ["execute_task", "execute_task", "execute_task", "execute_task", "process_queue"]
    m = execute_task_system_monitoring_priority_factor(cand, g, recent)
    assert m < 0.09

    m2 = execute_task_system_monitoring_priority_factor(
        {"action": "execute_task", "metadata": {"name": "other_task"}},
        g,
        recent,
    )
    assert m2 == 1.0


def test_fractalmind_planning_noop_streak_triggers_suppression_window() -> None:
    clear_autonomy_noop_streak("fractalmind_planning")
    for _ in range(3):
        record_autonomy_noop_outcome("fractalmind_planning", reason="test_identical_artifact")
    assert autonomy_noop_suppression_factor("fractalmind_planning") < 1.0
    clear_autonomy_noop_streak("fractalmind_planning")


def test_autonomy_exploration_log_use_debug_when_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    import project_guardian.planner_readiness as pr

    monkeypatch.delenv("ELYSIA_EXPLORATION_INFO_WHEN_READY", raising=False)
    monkeypatch.delenv("ELYSIA_AUTONOMY_ROUTINE_INFO_WHEN_READY", raising=False)
    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    assert autonomy_exploration_log_use_debug() is True
    monkeypatch.setenv("ELYSIA_EXPLORATION_INFO_WHEN_READY", "1")
    assert autonomy_exploration_log_use_debug() is False


def test_autonomy_routine_log_use_debug_alias_points_to_exploration_fn() -> None:
    from project_guardian.planner_readiness import (
        autonomy_exploration_log_use_debug,
        autonomy_routine_log_use_debug,
    )

    assert autonomy_routine_log_use_debug is autonomy_exploration_log_use_debug


def test_autonomy_routine_info_alias_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import project_guardian.planner_readiness as pr

    monkeypatch.delenv("ELYSIA_EXPLORATION_INFO_WHEN_READY", raising=False)
    monkeypatch.delenv("ELYSIA_AUTONOMY_ROUTINE_INFO_WHEN_READY", raising=False)
    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    assert autonomy_exploration_log_use_debug() is True
    monkeypatch.setenv("ELYSIA_AUTONOMY_ROUTINE_INFO_WHEN_READY", "1")
    assert autonomy_exploration_log_use_debug() is False


def test_autonomy_recent_summary_emits_periodically(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import logging
    import threading

    from project_guardian.core import GuardianCore

    monkeypatch.setenv("ELYSIA_AUTONOMY_RECENT_SUMMARY_SEC", "3600")
    monkeypatch.setenv("ELYSIA_AUTONOMY_SUMMARY_MAX_ACTIONS", "8")
    g = GuardianCore.__new__(GuardianCore)
    g._autonomy_summary_lock = threading.Lock()
    g._autonomy_summary_last_emit_ts = 0.0
    g._record_autonomy_execution_for_summary("process_queue")
    g._record_autonomy_execution_for_summary("use_capability/module/income_generator")
    with caplog.at_level(logging.INFO, logger="project_guardian.core"):
        g._maybe_emit_autonomy_recent_summary()
    assert "[AutonomySummary]" in caplog.text
    assert "process_queue" in caplog.text
    assert "uc:module/income_generator" in caplog.text
    before = caplog.text.count("[AutonomySummary]")
    g._maybe_emit_autonomy_recent_summary()
    assert caplog.text.count("[AutonomySummary]") == before


def test_autonomy_recent_summary_concurrent_records() -> None:
    import threading

    from project_guardian.core import GuardianCore

    g = GuardianCore.__new__(GuardianCore)
    g._autonomy_summary_lock = threading.Lock()

    def _run() -> None:
        for i in range(40):
            g._record_autonomy_execution_for_summary(f"action_{i % 5}")

    threads = [threading.Thread(target=_run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ring = g._autonomy_exec_history_ring
    assert ring is not None
    assert len(ring) >= 1


def test_autonomy_recent_summary_disabled_when_interval_zero(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import logging
    import threading

    from project_guardian.core import GuardianCore

    monkeypatch.setenv("ELYSIA_AUTONOMY_RECENT_SUMMARY_SEC", "0")
    g = GuardianCore.__new__(GuardianCore)
    g._autonomy_summary_lock = threading.Lock()
    g._record_autonomy_execution_for_summary("tool_registry_pulse")
    with caplog.at_level(logging.INFO, logger="project_guardian.core"):
        g._maybe_emit_autonomy_recent_summary()
    assert "[AutonomySummary]" not in caplog.text


class _ListHandler(logging.Handler):
    """Capture log records for assertions."""

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
    pr.log_autonomy_routine(lg, "tick %s", "a")
    assert cap.records[-1].levelno == logging.DEBUG

    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "degraded")
    pr.log_autonomy_routine(lg, "tick %s", "b")
    assert cap.records[-1].levelno == logging.INFO

    monkeypatch.setattr(pr, "compute_readiness_label", lambda: "ready")
    monkeypatch.setenv("ELYSIA_AUTONOMY_ROUTINE_INFO_WHEN_READY", "1")
    pr.log_autonomy_routine(lg, "tick %s", "c")
    assert cap.records[-1].levelno == logging.INFO


def test_income_modules_pulse_noop_streak_triggers_suppression_window() -> None:
    clear_autonomy_noop_streak("income_modules_pulse")
    for _ in range(2):
        record_autonomy_noop_outcome("income_modules_pulse", reason="test_repeated_zero_signature")
    assert autonomy_noop_suppression_factor("income_modules_pulse") < 1.0
    clear_autonomy_noop_streak("income_modules_pulse")


def test_harvest_noop_suppresses_equivalent_capability_action() -> None:
    clear_autonomy_noop_streak("harvest_income_report")
    record_autonomy_noop_outcome("harvest_income_report", reason="test_zero_total_zero_sales")
    assert equivalent_autonomy_action_key("use_capability/module/harvest_engine") == "harvest_income_report"
    assert autonomy_noop_suppression_factor("use_capability/module/harvest_engine") < 1.0
    clear_autonomy_noop_streak("harvest_income_report")


def test_direct_web_capability_without_url_is_downranked() -> None:
    bad = {
        "action": "use_capability/tool/elysia_builtin_web",
        "priority_score": 10.0,
        "reason": "Browse whatever is relevant",
    }
    assert web_capability_missing_url_priority_factor(bad) < 0.1
    apply_autonomy_loop_load_guards(None, [bad], [])
    assert bad["priority_score"] == pytest.approx(0.4)

    good = {
        "action": "use_capability/tool/elysia_builtin_web",
        "priority_score": 10.0,
        "metadata": {"url": "https://example.com/feed"},
    }
    assert web_capability_missing_url_priority_factor(good) == 1.0


def test_autonomy_decision_trace_summarizes_selection_and_skipped_top() -> None:
    from project_guardian.core import GuardianCore

    g = GuardianCore.__new__(GuardianCore)
    g._mistral_decision_cycle = 17
    best = {
        "action": "execute_self_task",
        "source": "self_tasking",
        "reason": "Package operator offer page",
        "priority_score": 3.2,
        "metadata": {
            "self_task_archetype": "package_operator_offer_pack",
            "archetype_selection_factor": 0.28,
        },
    }
    candidates = [
        {
            "action": "harvest_income_report",
            "source": "loop",
            "reason": "Refresh income report",
            "priority_score": 5.0,
            "_harvest_zero_yield_penalty": True,
            "_antiloop": {"combined_multiplier": 0.14},
        },
        best,
        {
            "action": "use_capability/tool/elysia_builtin_web",
            "source": "capability",
            "reason": "Browse without URL",
            "priority_score": 0.4,
            "_autonomy_loop_guard": {"combined": 0.04},
        },
    ]
    trace = g._build_autonomy_decision_trace(
        best,
        candidates,
        scored_pick_action="harvest_income_report",
        pick_override={
            "from": "harvest_income_report",
            "to": "execute_self_task",
            "reason": "self_task_priority",
        },
        mistral_decision={"chosen_action": "harvest_income_report", "confidence": 0.74},
        planner_runtime={"autonomy_planner_mode": "normal"},
    )
    assert trace.startswith("[AutonomyDecisionTrace]")
    assert "cycle=17" in trace
    assert "winner=execute_self_task:package_operator_offer_pack@3.200" in trace
    assert "runner=harvest_income_report@5.000" in trace
    assert "skipped_top=harvest_income_report@5.000" in trace
    assert "post_override=harvest_income_report>execute_self_task:self_task_priority" in trace
    assert "arch_factor=0.28" in trace
    assert "harvest0" in trace
    assert "guard=0.04" in trace


def test_mistral_adversarial_gating_empty_runs_raise_priority_penalty() -> None:
    from project_guardian.core import GuardianCore

    g = GuardianCore.__new__(GuardianCore)
    g._adversarial_empty_run_streak = 0
    g._adversarial_low_yield_streak = 0
    g._adversarial_last_fingerprint = None
    g._adversarial_priority_penalty = 0.0
    g._adversarial_low_yield_cooldown_until = None
    cfg: dict = {}
    for _ in range(3):
        g._mistral_update_adversarial_gating(
            {"findings_count": 0, "tasks_created": 0, "top_weakness": None, "top_type": None},
            cfg,
        )
    assert g._adversarial_priority_penalty > 0.9


def test_mistral_adversarial_first_no_task_finding_skips_streak_penalty() -> None:
    from project_guardian.core import GuardianCore

    g = GuardianCore.__new__(GuardianCore)
    g._adversarial_empty_run_streak = 0
    g._adversarial_low_yield_streak = 0
    g._adversarial_last_fingerprint = None
    g._adversarial_priority_penalty = 2.0
    g._adversarial_low_yield_cooldown_until = None
    g._mistral_update_adversarial_gating(
        {
            "findings_count": 2,
            "tasks_created": 0,
            "top_weakness": "Repeated error X",
            "top_type": "error",
        },
        {},
    )
    assert g._adversarial_low_yield_streak == 0
    assert g._adversarial_priority_penalty < 2.0


def test_mistral_adversarial_rotating_no_task_increments_streak() -> None:
    from project_guardian.core import GuardianCore

    g = GuardianCore.__new__(GuardianCore)
    g._adversarial_empty_run_streak = 0
    g._adversarial_low_yield_streak = 0
    g._adversarial_last_fingerprint = "error:oldheadline"
    g._adversarial_priority_penalty = 0.0
    g._adversarial_low_yield_cooldown_until = None
    g._mistral_update_adversarial_gating(
        {
            "findings_count": 1,
            "tasks_created": 0,
            "top_weakness": "New weakness headline",
            "top_type": "error",
        },
        {},
    )
    assert g._adversarial_low_yield_streak == 1
    assert g._adversarial_priority_penalty > 0


def test_fractalmind_repeat_priority_factor_streak_and_tail() -> None:
    g = _G()
    g._fractalmind_same_artifact_streak = 2
    recent = ["fractalmind_planning", "fractalmind_planning", "process_queue"]
    f = fractalmind_planning_repeat_priority_factor(g, recent)
    assert f < 1.0


def test_fractalmind_repeat_priority_factor_cooldown_active_is_strongly_downranked() -> None:
    g = _G()
    g._fractalmind_same_artifact_streak = 5
    g._fractalmind_repetition_suppress_until = time.time() + 300.0
    f = fractalmind_planning_repeat_priority_factor(g, ["fractalmind_planning"] * 4)
    assert f <= 0.018


def test_process_queue_stale_deprioritization() -> None:
    g = _G()
    assert process_queue_stale_probe_priority_factor(g) == 1.0

    g._process_queue_unchanged_streak = 1
    assert process_queue_stale_probe_priority_factor(g) == pytest.approx(0.55)

    g._process_queue_unchanged_streak = 3
    f = process_queue_stale_probe_priority_factor(g)
    assert 0.02 < f < 1.0

    g._process_queue_noop_deprioritize_until = time.time() + 3600.0
    assert process_queue_stale_probe_priority_factor(g) == pytest.approx(0.035)


def test_apply_load_guards_income_only_skips_self_task() -> None:
    g = _G()
    g._income_pulse_same_zero_sig_streak = 3
    cands = [
        {"action": "execute_self_task", "priority_score": 10.0},
        {"action": "income_modules_pulse", "priority_score": 30.0},
    ]
    apply_autonomy_loop_load_guards(g, cands, recent_actions=[])
    assert cands[0]["priority_score"] == 10.0
    assert cands[1]["priority_score"] == pytest.approx(30.0 * (0.4**3))


def test_income_generator_capability_stale_factor() -> None:
    g = _G()
    assert income_generator_capability_stale_factor(g, "use_capability/module/wallet") == 1.0
    g._income_generator_autonomy_cap_streak = 3
    f = income_generator_capability_stale_factor(g, "use_capability/module/income_generator")
    assert f < 0.2


def test_use_capability_module_stale_factor_extra_module_via_config() -> None:
    class _GH:
        __slots__ = ("_use_capability_autonomy_fp_state",)

        def __init__(self) -> None:
            self._use_capability_autonomy_fp_state = {
                "harvest_engine": {"streak": 2, "sig": "abc"},
            }

        def _load_autonomy_config(self) -> dict:
            return {"use_capability_stale_fingerprint_modules": ["harvest_engine"]}

    h = _GH()
    f = use_capability_module_stale_factor(h, "use_capability/module/harvest_engine")
    assert f < 1.0
    assert use_capability_module_stale_factor(h, "use_capability/module/income_generator") == 1.0


def test_antiloop_churn_downranks_income_generator_capability() -> None:
    g = _G()
    g._income_generator_autonomy_cap_streak = 2
    bd = antiloop.compute_antiloop_breakdown_for_action(
        "use_capability/module/income_generator",
        25.0,
        decision_cycle=10,
        recent_actions=[],
        guardian=g,
        metadata={},
    )
    assert float(bd["selector_churn"]) < 1.0
    assert float(bd["final_score"]) < 25.0


def test_builtin_transport_tools_not_direct_autonomy_capability() -> None:
    from project_guardian.capability_registry import CapabilityRegistry

    reg = CapabilityRegistry()
    g = type("G", (), {"_modules": {"tool_registry": object()}})()
    for tool_name in ("elysia_builtin_llm", "elysia_builtin_web"):
        action = reg.capability_entry_to_action(
            {"type": "tool", "name": tool_name},
            g,
        )
        assert action == ""
        assert reg.action_is_executable(f"use_capability/tool/{tool_name}", g) is False


def test_antiloop_churn_downranks_system_monitoring_execute_task() -> None:
    g = _G()
    g._execute_task_monitoring_select_streak = 3
    bd = antiloop.compute_antiloop_breakdown_for_action(
        "execute_task",
        100.0,
        decision_cycle=20,
        recent_actions=["execute_task"] * 5,
        guardian=g,
        metadata={"name": "system_monitoring"},
    )
    assert float(bd["selector_churn"]) < 0.25
    assert float(bd["final_score"]) < 30.0


def test_antiloop_churn_downranks_fractalmind_and_process_queue() -> None:
    g = _G()
    g._fractalmind_same_artifact_streak = 2
    bd_fm = antiloop.compute_antiloop_breakdown_for_action(
        "fractalmind_planning",
        10.0,
        decision_cycle=25,
        recent_actions=["fractalmind_planning", "fractalmind_planning"],
        guardian=g,
        metadata={},
    )
    assert float(bd_fm["selector_churn"]) < 1.0
    assert float(bd_fm["final_score"]) < 10.0

    g2 = _G()
    g2._process_queue_unchanged_streak = 4
    bd_pq = antiloop.compute_antiloop_breakdown_for_action(
        "process_queue",
        40.0,
        decision_cycle=25,
        recent_actions=[],
        guardian=g2,
        metadata={},
    )
    assert float(bd_pq["selector_churn"]) < 1.0
    assert float(bd_pq["final_score"]) < 40.0


def test_antiloop_execute_self_task_never_selector_churn_penalty() -> None:
    g = _G()
    g._execute_task_monitoring_select_streak = 9
    bd = antiloop.compute_antiloop_breakdown_for_action(
        "execute_self_task",
        8.0,
        decision_cycle=5,
        recent_actions=["execute_task"] * 8,
        guardian=g,
        metadata={},
    )
    assert float(bd["selector_churn"]) == 1.0


def test_self_task_beats_heavily_penalized_churn_actions() -> None:
    """After antiloop+churn, execute_self_task should outrank routine monitoring + stale queue."""
    g = _G()
    g._execute_task_monitoring_select_streak = 4
    g._process_queue_unchanged_streak = 5
    recent = ["execute_task", "process_queue", "execute_task", "process_queue"]
    cands = [
        {
            "action": "execute_task",
            "metadata": {"name": "system_monitoring"},
            "priority_score": 50.0,
            "source": "tasks",
            "reason": "monitor",
        },
        {"action": "process_queue", "priority_score": 45.0, "source": "loop", "reason": "probe"},
        {
            "action": "execute_self_task",
            "priority_score": 6.0,
            "source": "self_tasking",
            "reason": "artifact",
            "metadata": {},
        },
    ]
    antiloop.apply_autonomy_antiloop_factors(
        cands, decision_cycle=30, recent_actions=recent, guardian=g, legacy_startup_antithrash_fn=None
    )
    best = max(cands, key=lambda c: float(c.get("priority_score", 0) or 0))
    assert best["action"] == "execute_self_task"


def test_core_execute_self_task_escapes_repeated_system_monitoring() -> None:
    from project_guardian.core import GuardianCore

    g = GuardianCore.__new__(GuardianCore)
    g._execute_task_monitoring_select_streak = 4
    g._decider_recent_actions = [
        "execute_task",
        "process_queue",
        "execute_task",
        "fractalmind_planning",
        "execute_task",
        "execute_task",
    ]
    best = {
        "action": "execute_task",
        "priority_score": 50.0,
        "metadata": {"name": "system_monitoring"},
    }
    candidates = [
        best,
        {"action": "execute_self_task", "priority_score": 4.1, "metadata": {}},
        {"action": "process_queue", "priority_score": 3.5, "metadata": {}},
    ]

    out = g._maybe_suppress_repeated_system_monitoring_task(best, candidates)

    assert out is not None
    assert out["action"] == "execute_self_task"


def test_core_remember_autonomy_event_if_fresh_suppresses_duplicate_memory() -> None:
    from project_guardian.core import GuardianCore

    class _Memory:
        def __init__(self) -> None:
            self.calls = []

        def remember(self, message: str, **kwargs) -> None:
            self.calls.append((message, kwargs))

    g = GuardianCore.__new__(GuardianCore)
    g.memory = _Memory()
    g._autonomy_memory_repeat_guard = {}

    first = g._remember_autonomy_event_if_fresh(
        "fractalmind_artifact",
        "[Autonomy] fractalmind_planning artifact: count=3 low_yield=False",
        signature="abc123",
        min_interval_sec=1800.0,
    )
    second = g._remember_autonomy_event_if_fresh(
        "fractalmind_artifact",
        "[Autonomy] fractalmind_planning artifact: count=3 low_yield=False",
        signature="abc123",
        min_interval_sec=1800.0,
    )

    assert first is True
    assert second is False
    assert len(g.memory.calls) == 1


def test_mission_execute_self_task_escape_boost_on_churn_tail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from project_guardian.mission_autonomy import MissionAutonomyStore

    cfg = tmp_path / "mission_autonomy.json"
    cfg.write_text(json.dumps({"enabled": True, "version": 1, "campaigns": []}), encoding="utf-8")
    monkeypatch.setattr(
        "project_guardian.mission_autonomy.CONFIG_PATH",
        cfg,
    )
    st = tmp_path / "mission_autonomy_state.json"
    st.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "project_guardian.mission_autonomy.STATE_PATH",
        st,
    )
    store = MissionAutonomyStore()
    recent = [
        "execute_task",
        "process_queue",
        "fractalmind_planning",
        "execute_task",
        "process_queue",
        "fractalmind_planning",
        "execute_task",
    ]
    cands = [
        {
            "action": "execute_self_task",
            "source": "self_tasking",
            "reason": "test",
            "priority_score": 2.0,
            "metadata": {},
        },
        {"action": "process_queue", "source": "loop", "reason": "x", "priority_score": 40.0, "metadata": {}},
    ]
    out = store.apply_governance(cands, recent)
    st_cand = next(x for x in out if x.get("action") == "execute_self_task")
    assert st_cand.get("_mission_churn_escape_boost", 0) >= 1.5


def test_mission_execute_self_task_repeat_penalizes_same_archetype(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from project_guardian.mission_autonomy import MissionAutonomyStore

    cfg = tmp_path / "mission_autonomy.json"
    cfg.write_text(json.dumps({"enabled": True, "version": 1, "campaigns": []}), encoding="utf-8")
    monkeypatch.setattr("project_guardian.mission_autonomy.CONFIG_PATH", cfg)
    st = tmp_path / "mission_autonomy_state.json"
    st.write_text(
        json.dumps(
            {
                "last_artifacts": [
                    {
                        "task_id": "a1",
                        "archetype": "generate_revenue_shortlist",
                        "success": True,
                        "useful": True,
                        "objective_advanced": False,
                    },
                    {
                        "task_id": "a2",
                        "archetype": "generate_revenue_shortlist",
                        "success": True,
                        "useful": True,
                        "objective_advanced": False,
                    },
                    {
                        "task_id": "a3",
                        "archetype": "generate_revenue_shortlist",
                        "success": True,
                        "useful": True,
                        "objective_advanced": False,
                    }
                ],
                "archetype_mission_bias": {
                    "generate_revenue_shortlist": 1.6,
                    "identify_capability_gaps": 0.3,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("project_guardian.mission_autonomy.STATE_PATH", st)
    store = MissionAutonomyStore()
    cands = [
        {
            "action": "execute_self_task",
            "source": "self_tasking",
            "reason": "Generate ranked revenue shortlist (local)",
            "priority_score": 5.0,
            "metadata": {"self_task_archetype": "generate_revenue_shortlist"},
        },
        {
            "action": "execute_self_task",
            "source": "self_tasking",
            "reason": "Capability gap report (registry)",
            "priority_score": 5.0,
            "metadata": {"self_task_archetype": "identify_capability_gaps"},
        },
    ]
    out = store.apply_governance(cands, recent_actions=["execute_self_task"])
    by_arch = {
        str((c.get("metadata") or {}).get("self_task_archetype")): c
        for c in out
        if c.get("action") == "execute_self_task"
    }
    assert by_arch["generate_revenue_shortlist"]["priority_score"] < by_arch["identify_capability_gaps"]["priority_score"]
    assert "self_task_archetype_repeat_without_objective_advance" in str(
        by_arch["generate_revenue_shortlist"].get("_mission_drift") or ""
    )


def test_self_task_generator_suppresses_stale_monetization_operator_value_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from project_guardian.self_task_generator import SelfTaskGenerator, build_context_for_guardian

    cfg = tmp_path / "mission_autonomy.json"
    cfg.write_text(json.dumps({"enabled": True, "version": 1, "campaigns": []}), encoding="utf-8")
    monkeypatch.setattr("project_guardian.mission_autonomy.CONFIG_PATH", cfg)
    st = tmp_path / "mission_autonomy_state.json"
    st.write_text(
        json.dumps(
            {
                "last_artifacts": [
                    {
                        "task_id": "m1",
                        "archetype": "generate_revenue_shortlist",
                        "success": True,
                        "useful": True,
                        "objective_advanced": False,
                    },
                    {
                        "task_id": "m2",
                        "archetype": "generate_revenue_shortlist",
                        "success": True,
                        "useful": True,
                        "objective_advanced": False,
                    },
                    {
                        "task_id": "m3",
                        "archetype": "evaluate_existing_objectives_for_monetization",
                        "success": True,
                        "useful": True,
                        "objective_advanced": False,
                    },
                    {
                        "task_id": "m4",
                        "archetype": "evaluate_existing_objectives_for_monetization",
                        "success": True,
                        "useful": True,
                        "objective_advanced": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("project_guardian.mission_autonomy.STATE_PATH", st)

    class _ToolRegistry:
        def ensure_minimal_builtin_tools(self) -> None:
            return None

    class _Guardian:
        def __init__(self) -> None:
            self._modules = {
                "income_generator": object(),
                "longterm_planner": object(),
                "tool_registry": _ToolRegistry(),
            }
            self._self_task_low_confidence_streak = 0
            self._mistral_repeated_action_count = 0
            self._module_last_invoked = {}
            self._last_introspection_result = None

        def get_startup_operational_state(self) -> dict:
            return {}

        def _tool_registry_minimal_capabilities_ok(self, _tool_registry: object) -> bool:
            return True

    guardian = _Guardian()
    ctx = build_context_for_guardian(
        guardian,
        candidates_empty=False,
        mistral_decision=None,
        override_reason=None,
        decider_cfg={},
        self_task_cfg={"enabled": True, "underuse_module_hours": 2.0},
    )
    gen = SelfTaskGenerator({"max_operator_value_tasks_per_cycle": 4})
    tasks = []
    gen._add_operator_value_tasks(guardian, ctx, tasks, lambda mod: mod in guardian._modules)
    arches = {str(t.get("archetype") or "") for t in tasks}
    assert "generate_revenue_shortlist" not in arches
    assert "package_operator_offer_pack" not in arches
    assert "evaluate_existing_objectives_for_monetization" not in arches
    assert "identify_capability_gaps" in arches


def test_operator_offer_pack_is_classified_as_revenue_work() -> None:
    from project_guardian.self_task_generator import _is_monetization_like_archetype
    from project_guardian.self_task_portfolio import infer_portfolio_category
    from project_guardian.self_task_queue import USEFUL_NONADV_SUPPRESSION_ARCHETYPES

    assert is_revenue_monetization_archetype("package_operator_offer_pack")
    assert _is_monetization_like_archetype("package_operator_offer_pack")
    assert infer_portfolio_category("package_operator_offer_pack") == "revenue"
    assert "package_operator_offer_pack" in USEFUL_NONADV_SUPPRESSION_ARCHETYPES


def test_self_task_generator_applies_stale_suppression_to_maintenance_tasks() -> None:
    from project_guardian.self_task_generator import SelfTaskGenerator

    class _ToolRegistry:
        def ensure_minimal_builtin_tools(self) -> None:
            return None

    class _Guardian:
        def __init__(self) -> None:
            self._modules = {
                "tool_registry": _ToolRegistry(),
                "longterm_planner": object(),
            }
            self._module_last_invoked = {}
            self.memory = None

    guardian = _Guardian()
    gen = SelfTaskGenerator(
        {
            "repeated_action_streak_trigger": 3,
            "max_generate_per_cycle": 8,
        }
    )
    ctx = {
        "enabled": True,
        "idle_no_candidates": False,
        "weak_decision": False,
        "low_confidence_streak": 1,
        "repeated_action_streak": 3,
        "stale_self_task_archetypes": [
            "validate_tool_registry_snapshot",
            "refresh_objective_snapshot",
        ],
        "stale_monetization_loop": False,
        "startup_issue": False,
        "tool_registry_weak": False,
        "api_unused_hint": False,
        "underused_modules": [],
        "module_underuse": False,
        "financial_idle": False,
        "learning_digest_worthy": False,
    }
    tasks = gen.build(guardian, ctx)
    arches = {str(t.get("archetype") or "") for t in tasks}
    assert "validate_tool_registry_snapshot" not in arches
    assert "refresh_objective_snapshot" not in arches


def test_harvest_and_income_zero_state_downrank() -> None:
    for _ in range(4):
        record_harvest_zero_yield_outcome(False)
    assert harvest_zero_yield_priority_factor("harvest_income_report") == pytest.approx(0.14)
    assert harvest_zero_yield_priority_factor("use_capability/module/harvest_engine") == pytest.approx(0.14)
    record_harvest_zero_yield_outcome(True)
    assert harvest_zero_yield_priority_factor("harvest_income_report") == 1.0

    g = _G()
    g._income_pulse_same_zero_sig_streak = 2
    assert income_pulse_duplicate_priority_factor(g, "income_modules_pulse") < 1.0
    assert income_pulse_duplicate_priority_factor(g, "harvest_income_report") == 1.0


def test_run_autonomous_cycle_execute_task_system_monitoring_integration() -> None:
    from project_guardian.core import GuardianCore

    class _Memory:
        def __init__(self) -> None:
            self.events = []

        def remember(self, message: str, **kwargs) -> None:
            self.events.append((message, kwargs))

    class _Tasks:
        def __init__(self) -> None:
            self.status_updates = []
            self.log_entries = []

        def get_task(self, tid: int | None) -> dict | None:
            if tid == 7:
                return {"id": 7, "category": "system", "name": "system_monitoring"}
            return None

        def update_task_status(self, tid: int, status: str) -> None:
            self.status_updates.append((tid, status))

        def log_task(self, tid: int, message: str, level: str) -> None:
            self.log_entries.append((tid, message, level))

    class _Monitor:
        @staticmethod
        def get_system_health() -> dict:
            return {"health_score": 0.87, "status": "ok"}

        @staticmethod
        def get_health_summary() -> str:
            return "health summary"

    g = GuardianCore.__new__(GuardianCore)
    g.memory = _Memory()
    g.tasks = _Tasks()
    g.monitor = _Monitor()
    g._module_last_invoked = {}
    g._autonomy_action_times = []
    g._mistral_outcome_boost = {}
    g._load_autonomy_config = lambda: {
        "enabled": True,
        "allowed_actions": ["execute_task"],
        "max_actions_per_hour": 100,
    }
    g._load_mistral_decider_config = lambda: {}
    g.get_next_action = lambda: {
        "action": "execute_task",
        "can_auto_execute": True,
        "reason": "integration test",
        "metadata": {"task_id": 7, "name": "system_monitoring"},
    }
    g._orchestration_log_cycle = lambda *args, **kwargs: None
    g._mistral_reward_successful_action = lambda *args, **kwargs: None
    g._idle_capability_probe_if_needed = lambda *_args, **_kwargs: None

    out = g.run_autonomous_cycle()

    assert out["executed"] is True
    assert out["action"] == "execute_task"
    assert g.tasks.status_updates == [(7, "in_progress"), (7, "pending")]
    assert any("health_score=0.87" in e[1] for e in g.tasks.log_entries)
    assert g._last_execute_task_score == 1.0


def test_run_autonomous_cycle_continue_mission_throttles_log_progress() -> None:
    from project_guardian.core import GuardianCore

    class _Memory:
        def __init__(self) -> None:
            self.events = []

        def remember(self, message: str, **kwargs) -> None:
            self.events.append((message, kwargs))

    class _Missions:
        def __init__(self) -> None:
            self.calls = []

        def get_active_missions(self) -> list[dict]:
            return [{"name": "Alpha"}]

        def log_progress(self, mission_name: str, message: str, progress=None) -> bool:
            self.calls.append((mission_name, message, progress))
            return True

    g = GuardianCore.__new__(GuardianCore)
    g.memory = _Memory()
    g.missions = _Missions()
    g._module_last_invoked = {}
    g._autonomy_action_times = []
    g._continue_mission_last_log_ts = {}
    g._load_autonomy_config = lambda: {
        "enabled": True,
        "allowed_actions": ["continue_mission"],
        "max_actions_per_hour": 100,
        "continue_mission_min_interval_sec": 3600,
    }
    g._load_mistral_decider_config = lambda: {}
    g.get_next_action = lambda: {
        "action": "continue_mission",
        "can_auto_execute": True,
        "reason": "heartbeat",
        "metadata": {"mission": "Alpha"},
    }
    g._orchestration_log_cycle = lambda *args, **kwargs: None
    g._mistral_reward_successful_action = lambda *args, **kwargs: None
    g._idle_capability_probe_if_needed = lambda *_args, **_kwargs: None

    out1 = g.run_autonomous_cycle()
    out2 = g.run_autonomous_cycle()

    assert out1["executed"] is True
    assert out2["executed"] is True
    assert len(g.missions.calls) == 1
    assert "Alpha" in g._continue_mission_last_log_ts


def test_run_autonomous_cycle_work_on_objective_recovers_orphaned_task(tmp_path: Path) -> None:
    from project_guardian.core import GuardianCore
    from project_guardian.longterm_planner import LongTermPlanner, TaskStatus

    class _Memory:
        def __init__(self) -> None:
            self.events = []

        def remember(self, message: str, **kwargs) -> None:
            self.events.append((message, kwargs))

    class _RuntimeStatus:
        value = "in_progress"

    class _RuntimeLoop:
        def __init__(self) -> None:
            self._submitted = 0
            self._statuses = {}

        def submit_task(self, func, priority=5, module="unknown", dependencies=None, deadline=None):  # noqa: ANN001
            self._submitted += 1
            runtime_task_id = f"rt-{self._submitted}"
            self._statuses[runtime_task_id] = _RuntimeStatus()
            return runtime_task_id

        def get_task_status(self, task_id: str):
            return self._statuses.get(task_id)

    runtime_loop = _RuntimeLoop()
    planner = LongTermPlanner(runtime_loop=runtime_loop, storage_path=str(tmp_path / "planner_state.json"))
    objective_id = planner.add_objective(
        name="Recovered objective",
        description="Do one concrete thing.",
        priority=7,
    )
    created_ids = asyncio.run(planner.breakdown_objective(objective_id, strategy="hierarchical"))
    task_id = created_ids[0]
    planner.planned_tasks[task_id].status = TaskStatus.IN_PROGRESS
    planner.planned_tasks[task_id].metadata = {}
    planner.save()

    g = GuardianCore.__new__(GuardianCore)
    g.memory = _Memory()
    g._modules = {"longterm_planner": planner}
    g._module_last_invoked = {}
    g._autonomy_action_times = []
    g._mistral_outcome_boost = {}
    g._load_autonomy_config = lambda: {
        "enabled": True,
        "allowed_actions": ["work_on_objective"],
        "max_actions_per_hour": 100,
    }
    g._load_mistral_decider_config = lambda: {}
    g.get_next_action = lambda: {
        "action": "work_on_objective",
        "can_auto_execute": True,
        "reason": "integration test",
        "metadata": {"objective_id": objective_id},
    }
    g._orchestration_log_cycle = lambda *args, **kwargs: None
    g._mistral_reward_successful_action = lambda *args, **kwargs: None
    g._idle_capability_probe_if_needed = lambda *_args, **_kwargs: None

    out = g.run_autonomous_cycle()

    assert out["executed"] is True
    assert out["action"] == "work_on_objective"
    assert planner.planned_tasks[task_id].status == TaskStatus.IN_PROGRESS
    assert planner.planned_tasks[task_id].metadata.get("runtime_task_id") == "rt-1"
    assert planner.planned_tasks[task_id].metadata.get("runtime_recovery_reason") == "missing_runtime_binding"
    assert g._last_work_on_objective_score == 1.0


def test_run_autonomous_cycle_allows_zero_max_actions_per_hour_without_crash() -> None:
    from project_guardian.core import GuardianCore

    class _Memory:
        def remember(self, message: str, **kwargs) -> None:
            return None

    class _Missions:
        def __init__(self) -> None:
            self.calls = []

        def get_active_missions(self) -> list[dict]:
            return [{"name": "Alpha"}]

        def log_progress(self, mission_name: str, message: str, progress=None) -> bool:
            self.calls.append((mission_name, message, progress))
            return True

    g = GuardianCore.__new__(GuardianCore)
    g.memory = _Memory()
    g.missions = _Missions()
    g._module_last_invoked = {}
    g._autonomy_action_times = []
    g._continue_mission_last_log_ts = {}
    g._load_autonomy_config = lambda: {
        "enabled": True,
        "allowed_actions": ["continue_mission"],
        "max_actions_per_hour": 0,
        "continue_mission_min_interval_sec": 0,
    }
    g._load_mistral_decider_config = lambda: {}
    g.get_next_action = lambda: {
        "action": "continue_mission",
        "can_auto_execute": True,
        "reason": "heartbeat",
        "metadata": {"mission": "Alpha"},
    }
    g._orchestration_log_cycle = lambda *args, **kwargs: None
    g._mistral_reward_successful_action = lambda *args, **kwargs: None
    g._idle_capability_probe_if_needed = lambda *_args, **_kwargs: None

    out = g.run_autonomous_cycle()
    assert out["executed"] is True
    assert len(g.missions.calls) == 1


def test_proposal_scaffold_creates_implementation_and_validates(tmp_path: Path) -> None:
    prop = tmp_path / "prop_scaffold_test"
    prop.mkdir()
    (prop / "research").mkdir()
    (prop / "design").mkdir()
    (prop / "README.md").write_text("# x\n", encoding="utf-8")
    meta = {
        "proposal_id": "p1",
        "title": "t",
        "description": "d",
        "status": "draft",
        "created_by": "test",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "schema_version": 1,
    }
    (prop / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    v = ProposalValidator()
    assert not (prop / "implementation").exists()
    r = v.validate_structure(prop)
    assert (prop / "implementation").is_dir()
    assert r["valid"] is True
    assert any("implementation" in p for p in r.get("scaffolded", []))
