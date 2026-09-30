import datetime
import json
from types import MethodType

import project_guardian.autonomy_antiloop as autonomy_antiloop
import project_guardian.core as core_mod
import project_guardian.mission_autonomy as mission_autonomy
import project_guardian.planner_readiness as planner_readiness
from project_guardian.core import GuardianCore
from project_guardian.missions import MissionDirector


_REQUIRED_RECEIPT_KEYS = {
    "action",
    "objective",
    "success",
    "useful",
    "objective_advanced",
    "evidence_ref",
    "cost",
    "elapsed_sec",
    "reason",
}


def _configure_temp_store(monkeypatch, tmp_path):
    config_path = tmp_path / "mission_autonomy.json"
    state_path = tmp_path / "mission_autonomy_state.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "enabled": True,
                "core_mission": "",
                "standing_priorities": [],
                "campaigns": [],
                "session_objectives": [],
                "action_campaign_map": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mission_autonomy, "CONFIG_PATH", config_path)
    monkeypatch.setattr(mission_autonomy, "STATE_PATH", state_path)
    return state_path


def _strategy_candidates():
    return [
        {
            "action": action,
            "source": "issue_88_test",
            "reason": "",
            "priority_score": 5.0,
            "can_auto_execute": False,
            "metadata": {},
        }
        for action in ("strategy_a", "strategy_b", "strategy_c")
    ]


def _scores(store):
    scored = store.apply_governance(_strategy_candidates(), recent_actions=[])
    return {row["action"]: row["priority_score"] for row in scored}


def test_measured_outcomes_change_ranking_and_survive_restart(monkeypatch, tmp_path):
    state_path = _configure_temp_store(monkeypatch, tmp_path)
    store = mission_autonomy.MissionAutonomyStore()

    before = _scores(store)
    assert len({round(value, 8) for value in before.values()}) == 1

    receipts = []
    for index in range(3):
        receipts.append(
            store.record_outcome_receipt(
                action="strategy_a",
                objective="advance the test objective",
                success=False,
                useful=False,
                objective_advanced=False,
                evidence_ref=f"test://strategy-a/{index}",
                cost=0.10,
                elapsed_sec=1.0,
                reason="no useful progress",
            )
        )
        receipts.append(
            store.record_outcome_receipt(
                action="strategy_b",
                objective="advance the test objective",
                success=True,
                useful=True,
                objective_advanced=True,
                evidence_ref=f"test://strategy-b/{index}",
                cost=0.20,
                elapsed_sec=1.0,
                reason="useful objective progress",
            )
        )

    for index, succeeded in enumerate((True, False, True)):
        receipts.append(
            store.record_outcome_receipt(
                action="strategy_c",
                objective="advance the test objective",
                success=succeeded,
                useful=succeeded,
                objective_advanced=succeeded,
                evidence_ref=f"test://strategy-c/{index}",
                cost=0.90,
                elapsed_sec=4.0,
                reason="higher-cost mixed outcome",
            )
        )

    after_learning = _scores(store)
    assert after_learning["strategy_b"] > after_learning["strategy_c"] > after_learning["strategy_a"]
    assert all(_REQUIRED_RECEIPT_KEYS <= set(receipt) for receipt in receipts)

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["action_priority_bias"]["strategy_b"] > persisted["action_priority_bias"]["strategy_c"]
    assert persisted["action_priority_bias"]["strategy_c"] > persisted["action_priority_bias"]["strategy_a"]
    assert len(persisted["outcome_receipts"]) == len(receipts)

    restarted = mission_autonomy.MissionAutonomyStore()
    after_restart = _scores(restarted)
    assert after_restart["strategy_b"] > after_restart["strategy_c"] > after_restart["strategy_a"]

    # Environment changes: the previously strong strategy fails while a viable alternative succeeds.
    for index in range(5):
        restarted.record_outcome_receipt(
            action="strategy_b",
            objective="advance the test objective",
            success=False,
            useful=False,
            objective_advanced=False,
            evidence_ref=f"test://strategy-b-regression/{index}",
            cost=0.20,
            elapsed_sec=1.0,
            reason="environment changed; no progress",
        )
    for index in range(3):
        restarted.record_outcome_receipt(
            action="strategy_c",
            objective="advance the test objective",
            success=True,
            useful=True,
            objective_advanced=True,
            evidence_ref=f"test://strategy-c-recovery/{index}",
            cost=0.90,
            elapsed_sec=4.0,
            reason="viable higher-cost recovery path",
        )

    after_environment_change = _scores(restarted)
    assert after_environment_change["strategy_c"] > after_environment_change["strategy_b"]
    assert after_environment_change["strategy_b"] < after_restart["strategy_b"]


class _NullMemory:
    def remember(self, *args, **kwargs):
        raise AssertionError("safe decision-only dry-run must not write Guardian memory")


class _NoTasks:
    def get_active_tasks(self):
        return []

    def get_task(self, task_id):
        return None


def _bind(obj, fn):
    return MethodType(fn, obj)


def _safe_decision_guardian(monkeypatch, store):
    # Neutralize unrelated global adaptive/suppression state so the proof is deterministic.
    monkeypatch.setattr(core_mod, "get_execution_policy_effect", lambda guardian: {})
    monkeypatch.setattr(
        core_mod,
        "apply_execution_policy_to_candidates",
        lambda candidates, policy, log_fn=None: (candidates, []),
    )
    monkeypatch.setattr(core_mod, "get_finding_priority_boost", lambda guardian, action: 0.0)

    monkeypatch.setattr(autonomy_antiloop, "apply_autonomy_antiloop_factors", lambda *args, **kwargs: None)
    monkeypatch.setattr(autonomy_antiloop, "compute_selection_override", lambda *args, **kwargs: None)
    monkeypatch.setattr(autonomy_antiloop, "log_autonomy_pick_override", lambda *args, **kwargs: None)
    monkeypatch.setattr(autonomy_antiloop, "log_autonomy_antiloop_selection", lambda *args, **kwargs: None)

    monkeypatch.setattr(planner_readiness, "restricted_safe_startup_mode", lambda: False)
    monkeypatch.setattr(planner_readiness, "autonomy_noop_suppression_factor", lambda action: 1.0)
    monkeypatch.setattr(planner_readiness, "harvest_zero_yield_priority_factor", lambda action: 1.0)
    monkeypatch.setattr(planner_readiness, "boot_low_value_action_factor", lambda action: 1.0)
    monkeypatch.setattr(planner_readiness, "startup_antithrash_priority_factor", lambda *args, **kwargs: 1.0)
    monkeypatch.setattr(planner_readiness, "monetization_priority_factor", lambda *args, **kwargs: 1.0)
    monkeypatch.setattr(planner_readiness, "boost_alternatives_when_autonomy_noop_suppressed", lambda *args, **kwargs: None)
    monkeypatch.setattr(planner_readiness, "apply_autonomy_loop_load_guards", lambda *args, **kwargs: None)

    director = MissionDirector(_NullMemory())
    director.mission_autonomy = store
    director.missions = [
        {
            "id": 0,
            "name": "Issue 88 safe dry-run mission",
            "goal": "prove adaptive decision reachability without live execution",
            "priority": "medium",
            "created": datetime.datetime.now().isoformat(),
            "deadline": None,
            "status": "active",
            "progress": 0.0,
            "log": [],
            "subtasks": [],
        }
    ]

    guardian = GuardianCore.__new__(GuardianCore)
    guardian.missions = director
    guardian.tasks = _NoTasks()
    guardian.elysia_loop = None
    guardian.prompt_evolver = None
    guardian._last_introspection_result = None
    guardian._adversarial_last_run = {"last_run": datetime.datetime.now().isoformat()}
    guardian._modules = {}
    guardian.analysis_engine = None
    guardian.mutation = None
    guardian.dreams = None
    guardian._module_last_invoked = {}
    guardian._decider_recent_actions = []
    guardian._last_returned_action = None
    guardian._mistral_repeated_action_count = 0
    guardian._stagnation_cycles = 0
    guardian._memory_block_cycles_remaining = 0
    guardian._consecutive_memory_actions = 0
    guardian._mistral_decision_cycle = 0
    guardian._mistral_consecutive_override_count = 0
    guardian._last_get_next_had_override = False
    guardian._execute_task_monitoring_select_streak = 0
    guardian._orchestration_registry = None
    guardian._pre_decision_context = {}
    guardian._running = False

    guardian._load_mistral_decider_config = _bind(
        guardian,
        lambda self: {
            "mistral_min_candidates": 0,
            "mistral_exploratory_actions": [],
            "mistral_primary_decider_enabled": False,
            "orchestration_require_executable_candidates": False,
            "mistral_max_repeated_action_count": 99,
            "mistral_force_exploration_stagnation_cycles": 99,
        },
    )
    guardian._load_autonomy_config = _bind(
        guardian,
        lambda self: {
            "enabled": False,
            "auto_execute": False,
            "use_mistral_decision_engine": False,
            "autonomy_auto_execute_guardian_tasks": False,
            "enable_moltbook_direction_guidance": False,
        },
    )
    guardian._openclaw_available = _bind(guardian, lambda self: False)
    guardian._moltbook_openclaw_boost = _bind(guardian, lambda self: 0.0)
    guardian._apply_underused_module_fairness = _bind(guardian, lambda self, *args, **kwargs: None)
    guardian._self_tasking_augment_decision = _bind(
        guardian,
        lambda self, candidates, best, *args, **kwargs: (candidates, best),
    )
    guardian._maybe_suppress_repeated_system_monitoring_task = _bind(
        guardian,
        lambda self, best, candidates: best,
    )
    return guardian


def test_safe_dry_run_reaches_normal_candidate_governance_selection_and_persistence(monkeypatch, tmp_path):
    state_path = _configure_temp_store(monkeypatch, tmp_path)
    store = mission_autonomy.MissionAutonomyStore()
    guardian = _safe_decision_guardian(monkeypatch, store)

    # Selection-only dry-run: real core candidate generation -> MissionDirector governance -> selector.
    decision = GuardianCore._get_next_action_impl(guardian)

    assert guardian._running is False
    assert decision["action"] == "continue_mission"
    assert decision["source"] == "missions"
    assert "planner_runtime" not in decision
    selected = next(row for row in decision["candidates"] if row["action"] == decision["action"])
    assert "_mission_governance" in selected

    # Simulated bounded outcome: no action handler or live executor is called.
    receipt = store.record_outcome_receipt(
        action=decision["action"],
        objective=decision["metadata"]["mission"],
        success=True,
        useful=True,
        objective_advanced=True,
        evidence_ref="dry-run://issue-88/normal-decision-pipeline",
        cost=0.0,
        elapsed_sec=0.0,
        reason="simulated test outcome; live execution disabled",
    )
    assert receipt["feedback_applied"] is True

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["outcome_receipts"][-1]["evidence_ref"].startswith("dry-run://")
    assert persisted["action_priority_bias"]["continue_mission"] > 0.0

    restarted = mission_autonomy.MissionAutonomyStore()
    rescored = restarted.apply_governance(
        [
            {
                "action": "continue_mission",
                "source": "missions",
                "reason": "Issue 88 safe dry-run mission",
                "priority_score": 7.0,
                "can_auto_execute": True,
                "metadata": {"mission": "Issue 88 safe dry-run mission"},
            }
        ],
        recent_actions=[],
    )
    assert rescored[0]["_mission_governance"]["feedback_bias"] > 0.0
