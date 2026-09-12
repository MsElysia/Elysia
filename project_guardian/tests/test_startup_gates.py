# project_guardian/tests/test_startup_gates.py
from __future__ import annotations

from unittest.mock import MagicMock

import project_guardian.cloud_api_state as cas
import project_guardian.ollama_health as ollama_health
from project_guardian import autonomy_antiloop as antiloop
from project_guardian import planner_readiness as pr


def _patch_cloud_credentials(monkeypatch, *, openai=False, openrouter=False, anthropic=False):
    def snap(refresh: bool = False):
        return {
            "openai": openai,
            "openrouter": openrouter,
            "anthropic": anthropic,
            "huggingface": False,
            "cohere": False,
            "source": "test",
        }

    monkeypatch.setattr(cas, "cloud_credentials_snapshot", snap)


def test_monetization_subsystems_ready_requires_all_three():
    g = MagicMock()
    g._modules = {
        "income_generator": MagicMock(get_income_summary=lambda: {}),
        "wallet": MagicMock(get_balance=lambda: {"total_balance": 1}),
        "financial_manager": MagicMock(get_financial_status=lambda: {}),
    }
    ok, d = pr.monetization_subsystems_ready(g)
    assert ok is True
    assert d["income_generator"] and d["wallet"] and d["financial_manager"]


def test_monetization_subsystems_ready_false_without_wallet_hook():
    g = MagicMock()
    g._modules = {"income_generator": MagicMock(get_income_summary=lambda: {}), "wallet": object()}
    ok, d = pr.monetization_subsystems_ready(g)
    assert ok is False
    assert d["wallet"] is False


def test_is_revenue_monetization_archetype():
    assert pr.is_revenue_monetization_archetype("generate_revenue_shortlist") is True
    assert pr.is_revenue_monetization_archetype("validate_tool_registry_snapshot") is False


def test_filter_monetization_pending_tasks_strips_when_not_ready(monkeypatch):
    g = MagicMock()
    g._modules = {}
    tasks = [
        {"archetype": "generate_revenue_shortlist", "task_id": "a"},
        {"archetype": "validate_tool_registry_snapshot", "task_id": "b"},
    ]
    monkeypatch.setattr(pr, "restricted_safe_startup_mode", lambda: False)
    out = pr.filter_monetization_pending_tasks(tasks, g, log_skip=False)
    assert len(out) == 1
    assert out[0]["task_id"] == "b"


def test_filter_monetization_keeps_repair_archetype_when_not_ready(monkeypatch):
    g = MagicMock()
    g._modules = {}
    tasks = [
        {"archetype": "generate_revenue_shortlist", "task_id": "a"},
        {"archetype": "repair_tool_registry_coverage", "task_id": "c"},
    ]
    monkeypatch.setattr(pr, "restricted_safe_startup_mode", lambda: False)
    out = pr.filter_monetization_pending_tasks(tasks, g, log_skip=False)
    ids = {t["task_id"] for t in out}
    assert "c" in ids
    assert "a" not in ids


def test_monetization_priority_skips_downrank_for_repair_archetype():
    g = MagicMock()
    g._modules = {}
    assert pr.monetization_priority_factor("execute_self_task", "validate_tool_registry_snapshot", g) == 1.0


def test_reasoning_capability_sufficient_when_local_staged(monkeypatch):
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: True)
    assert pr.reasoning_capability_sufficient_for_normal_autonomy() is True


def test_restricted_safe_off_when_openrouter_only_cloud(monkeypatch):
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: False)
    _patch_cloud_credentials(monkeypatch, openai=False, openrouter=True, anthropic=False)
    monkeypatch.setattr(cas, "openrouter_usable_for_reasoning", lambda: True)
    monkeypatch.setattr(cas, "openai_usable_for_routing", lambda *a, **k: False)
    monkeypatch.setattr(cas, "anthropic_usable_for_reasoning", lambda: False)
    assert pr.reasoning_capability_sufficient_for_normal_autonomy() is True
    assert pr.restricted_safe_startup_mode() is False


def test_run_staged_inference_retry_then_ok(monkeypatch):
    monkeypatch.setenv("ELYSIA_PLANNER_STARTUP_MAX_WAIT_SEC", "10")
    monkeypatch.setenv("ELYSIA_PLANNER_STARTUP_RETRY_INTERVAL_SEC", "0.05")
    monkeypatch.setattr(pr, "planner_startup_require_inference", lambda: True)
    n = {"c": 0}

    def probe(*_a, **_k):
        n["c"] += 1
        return (n["c"] >= 2, "retry" if n["c"] < 2 else "ok")

    monkeypatch.setattr(ollama_health, "planner_lightweight_inference_probe", probe)
    ok, det = pr.run_staged_planner_startup_inference("http://127.0.0.1:11434", "mistral:7b")
    assert ok is True
    assert "ok" in det


def test_antiloop_repeat_penalizes_scores():
    cands = [{"action": "tool_registry_pulse", "priority_score": 10.0}]
    antiloop.apply_autonomy_antiloop_factors(
        cands,
        decision_cycle=2,
        recent_actions=["tool_registry_pulse", "tool_registry_pulse", "tool_registry_pulse"],
        guardian=None,
        legacy_startup_antithrash_fn=None,
    )
    assert cands[0]["priority_score"] < 10.0
    assert "_antiloop" in cands[0]


def test_runtime_decision_snapshot_contains_keys(monkeypatch):
    monkeypatch.setattr(
        "project_guardian.openai_degraded.openai_insufficient_quota_reasoning_blocked",
        lambda *a, **k: False,
    )
    d = pr.build_runtime_decision_status_dict(None)
    assert "planner_readiness" in d
    assert "runtime_alive" in d
    assert "openai_configured" in d
    assert "openrouter_usable" in d
    assert "reasoning_provider_selected" in d
    assert "reasoning_provider_autonomy_safe" in d
    assert "reasoning_cap_ok" in d
    line = pr.format_runtime_decision_snapshot_line(d)
    assert line.startswith("[RuntimeDecision]")
    assert "restricted_safe=" in line
    assert "oa_cfg=" in line and "reasoning_sel=" in line
    assert "reasoning_safe=" in line and "reasoning_cap_ok=" in line
    assert len(line) < 2000


def test_openai_configured_quota_blocked_not_sufficient_alone(monkeypatch):
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: False)
    _patch_cloud_credentials(monkeypatch, openai=True, openrouter=False, anthropic=False)
    monkeypatch.setattr(cas, "openai_usable_for_routing", lambda *a, **k: False)
    monkeypatch.setattr(cas, "openrouter_usable_for_reasoning", lambda: False)
    monkeypatch.setattr(cas, "anthropic_usable_for_reasoning", lambda: False)
    assert pr.reasoning_capability_sufficient_for_normal_autonomy() is False
    t = cas.provider_reasoning_truth_snapshot(refresh=True)
    assert t["openai"]["configured"] is True
    assert t["openai"]["usable"] is False


def test_anthropic_key_without_trust_not_sufficient(monkeypatch):
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: False)
    _patch_cloud_credentials(monkeypatch, openai=False, openrouter=False, anthropic=True)
    monkeypatch.setenv("ELYSIA_ANTHROPIC_REASONING_TRUST", "")
    monkeypatch.setattr(cas, "openrouter_usable_for_reasoning", lambda: False)
    monkeypatch.setattr(cas, "openai_usable_for_routing", lambda *a, **k: False)
    assert pr.reasoning_capability_sufficient_for_normal_autonomy() is False
    t = cas.provider_reasoning_truth_snapshot(refresh=True)
    assert t["anthropic"]["configured"] is True
    assert t["anthropic"]["usable"] is False


def test_openrouter_usable_sufficient_when_openai_blocked(monkeypatch):
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: False)
    _patch_cloud_credentials(monkeypatch, openai=True, openrouter=True, anthropic=False)
    monkeypatch.setattr(cas, "openai_usable_for_routing", lambda *a, **k: False)
    monkeypatch.setattr(cas, "openrouter_usable_for_reasoning", lambda: True)
    monkeypatch.setattr(cas, "anthropic_usable_for_reasoning", lambda: False)
    assert pr.reasoning_capability_sufficient_for_normal_autonomy() is True


def test_no_usable_reasoning_path_insufficient(monkeypatch):
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: False)
    _patch_cloud_credentials(monkeypatch, openai=False, openrouter=False, anthropic=False)
    assert pr.reasoning_capability_sufficient_for_normal_autonomy() is False


def test_restricted_safe_off_when_openrouter_usable_even_if_openai_blocked(monkeypatch):
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: False)
    _patch_cloud_credentials(monkeypatch, openai=True, openrouter=True, anthropic=False)
    monkeypatch.setattr(cas, "openai_usable_for_routing", lambda *a, **k: False)
    monkeypatch.setattr(cas, "openrouter_usable_for_reasoning", lambda: True)
    monkeypatch.setattr(cas, "anthropic_usable_for_reasoning", lambda: False)
    assert pr.restricted_safe_startup_mode() is False


def test_restricted_safe_on_when_only_configured_not_usable(monkeypatch):
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: False)
    _patch_cloud_credentials(monkeypatch, openai=True, openrouter=True, anthropic=True)
    monkeypatch.setattr(cas, "openai_usable_for_routing", lambda *a, **k: False)
    monkeypatch.setattr(cas, "openrouter_usable_for_reasoning", lambda: False)
    monkeypatch.setattr(cas, "anthropic_usable_for_reasoning", lambda: False)
    assert pr.reasoning_capability_sufficient_for_normal_autonomy() is False
    assert pr.restricted_safe_startup_mode() is True


def test_local_planner_truth_inference_pending(monkeypatch):
    monkeypatch.setattr(
        "project_guardian.ollama_model_config.get_canonical_ollama_model",
        lambda log_once=False: "mistral:7b",
    )
    monkeypatch.setattr(pr, "staged_runtime_alive", lambda: True)
    monkeypatch.setattr(pr, "staged_planner_model_available", lambda: True)
    monkeypatch.setattr(pr, "staged_planner_inference_ok", lambda: False)
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: False)
    snap = pr.local_planner_reasoning_truth_snapshot()
    assert snap["configured"] is True
    assert snap["routable"] is True
    assert snap["usable"] is False
    assert snap["autonomy_safe"] is False
    assert snap["blocked_reason"] == "inference_unverified"


def test_runtime_snapshot_shows_provider_distinctions(monkeypatch):
    monkeypatch.setattr(
        "project_guardian.openai_degraded.openai_insufficient_quota_reasoning_blocked",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: False)
    _patch_cloud_credentials(monkeypatch, openai=True, openrouter=True, anthropic=False)
    monkeypatch.setattr(cas, "openai_usable_for_routing", lambda *a, **k: False)
    monkeypatch.setattr(cas, "openrouter_usable_for_reasoning", lambda: True)
    monkeypatch.setattr(cas, "anthropic_usable_for_reasoning", lambda: False)
    monkeypatch.setattr(cas, "anthropic_key_loaded", lambda: False)
    d = pr.build_runtime_decision_status_dict(None)
    assert d["openai_configured"] and d["openai_usable"] is False
    assert d["openrouter_usable"] is True
    assert d["reasoning_provider_selected"] == "openrouter"
    assert d["reasoning_provider_autonomy_safe"] == "openrouter"
    assert d["reasoning_cap_ok"] is True
    line = pr.format_runtime_decision_snapshot_line(d)
    assert "reasoning_sel=openrouter" in line
    assert "reasoning_safe=openrouter" in line
    assert "reasoning_cap_ok=yes" in line
    assert "or_use=yes" in line
    assert "oa_use=no" in line
    assert len(line) < 2000


def test_antiloop_breakdown_expected_components():
    bd = antiloop.compute_antiloop_breakdown_for_action(
        "tool_registry_pulse",
        10.0,
        decision_cycle=50,
        recent_actions=[],
        guardian=None,
        legacy_startup_antithrash_fn=None,
    )
    for k in (
        "base",
        "repeat_penalty",
        "family_repeat_penalty",
        "recent_failure_penalty",
        "no_state_change_penalty",
        "startup_penalty_mult",
        "legacy_antithrash_mult",
        "pre_churn_combined",
        "selector_churn",
        "combined_multiplier",
        "final_score",
    ):
        assert k in bd


def test_antiloop_final_score_matches_multiplier_product():
    bd = antiloop.compute_antiloop_breakdown_for_action(
        "tool_registry_pulse",
        5.0,
        decision_cycle=50,
        recent_actions=["tool_registry_pulse", "tool_registry_pulse"],
        guardian=None,
        legacy_startup_antithrash_fn=lambda **_k: 1.0,
    )
    combined = float(bd["combined_multiplier"])
    expected_final = float(bd["base"]) * combined
    assert abs(expected_final - float(bd["final_score"])) < 1e-5
    core = (
        float(bd["repeat_penalty"])
        * float(bd["family_repeat_penalty"])
        * float(bd["recent_failure_penalty"])
        * float(bd["no_state_change_penalty"])
    )
    legacy = float(bd["legacy_antithrash_mult"])
    startup = float(bd["startup_penalty_mult"])
    pre_churn = float(bd["pre_churn_combined"])
    assert abs(pre_churn - core * startup * legacy) < 1e-5
    assert abs(combined - pre_churn * float(bd["selector_churn"])) < 1e-5


def test_antiloop_format_line_compact_and_stable():
    bd = antiloop.compute_antiloop_breakdown_for_action(
        "system_monitoring",
        1.0,
        decision_cycle=99,
        recent_actions=[],
        guardian=None,
        legacy_startup_antithrash_fn=None,
    )
    line = antiloop.format_antiloop_score_log_line(bd)
    assert line.startswith("[AutonomyScore]")
    assert "final=" in line
    assert len(line) < 400


def test_reasoning_provider_selected_follows_api_router(monkeypatch):
    monkeypatch.setattr(
        "project_guardian.openai_degraded.openai_insufficient_quota_reasoning_blocked",
        lambda *a, **k: False,
    )

    def fake_select(*_a, **_k):
        return {"chosen": "anthropic", "reason": "unit_test"}

    monkeypatch.setattr("project_guardian.multi_api_router.select_best_api", fake_select)
    d = pr.build_runtime_decision_status_dict(None)
    assert d["reasoning_provider_selected"] == "anthropic"


def test_openai_truth_blocked_reason_quota(monkeypatch):
    _patch_cloud_credentials(monkeypatch, openai=True, openrouter=False, anthropic=False)
    monkeypatch.setattr(cas, "openai_usable_for_routing", lambda *a, **k: False)
    monkeypatch.setattr(cas, "openai_routing_block_reason", lambda: "openai_insufficient_quota_blocked")
    t = cas.provider_reasoning_truth_snapshot(refresh=True)
    assert t["openai"]["usable"] is False
    assert t["openai"]["autonomy_safe"] is False
    assert t["openai"]["blocked_reason"] == "quota"


def test_openrouter_truth_policy_disabled(monkeypatch):
    _patch_cloud_credentials(monkeypatch, openai=False, openrouter=True, anthropic=False)
    monkeypatch.setattr(cas, "openrouter_routing_disabled_by_policy", lambda: True)
    monkeypatch.setattr(cas, "openrouter_usable_for_reasoning", lambda: False)
    t = cas.provider_reasoning_truth_snapshot(refresh=True)
    assert t["openrouter"]["configured"] is True
    assert t["openrouter"]["usable"] is False
    assert t["openrouter"]["autonomy_safe"] is False
    assert t["openrouter"]["blocked_reason"] == "policy_disabled"


def test_selection_override_when_action_replaced():
    ov = antiloop.compute_selection_override(
        "system_monitoring",
        {"action": "execute_self_task", "source": "self_tasking"},
    )
    assert ov is not None
    assert ov["from"] == "system_monitoring"
    assert ov["to"] == "execute_self_task"
    assert ov["reason"] == "self_task_priority"


def test_selection_override_none_when_unchanged():
    assert antiloop.compute_selection_override("tool_registry_pulse", {"action": "tool_registry_pulse"}) is None


def test_selection_override_none_when_no_prior_scored_pick():
    assert antiloop.compute_selection_override("", {"action": "execute_self_task", "source": "self_tasking"}) is None


def test_startup_antithrash_repeats_downrank():
    assert (
        pr.startup_antithrash_priority_factor(
            "fractalmind_planning",
            decision_cycle=2,
            recent_actions=["x", "fractalmind_planning", "fractalmind_planning"],
        )
        < 1.0
    )


def test_router_anthropic_vs_autonomy_safe_mismatch(monkeypatch):
    """API router may pick Anthropic from key alone; autonomy_safe stays false without trust."""
    monkeypatch.setattr(
        "project_guardian.openai_degraded.openai_insufficient_quota_reasoning_blocked",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: False)
    _patch_cloud_credentials(monkeypatch, openai=False, openrouter=False, anthropic=True)
    monkeypatch.setenv("ELYSIA_ANTHROPIC_REASONING_TRUST", "")
    monkeypatch.setattr(cas, "openrouter_usable_for_reasoning", lambda: False)
    monkeypatch.setattr(cas, "openai_usable_for_routing", lambda *a, **k: False)

    def fake_select(*_a, **_k):
        return {"chosen": "anthropic", "reason": "unit_router"}

    monkeypatch.setattr("project_guardian.multi_api_router.select_best_api", fake_select)
    d = pr.build_runtime_decision_status_dict(None)
    assert d["reasoning_provider_selected"] == "anthropic"
    assert d["reasoning_provider_autonomy_safe"] == "none"
    assert d["reasoning_cap_ok"] is False
    assert d["anthropic_autonomy_safe"] is False
    line = pr.format_runtime_decision_snapshot_line(d)
    assert "reasoning_sel=anthropic" in line
    assert "reasoning_safe=none" in line
    assert "reasoning_cap_ok=no" in line


def test_capability_snapshot_includes_autonomy_safe_per_provider(monkeypatch):
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: False)
    _patch_cloud_credentials(monkeypatch, openai=True, openrouter=True, anthropic=True)
    monkeypatch.setenv("ELYSIA_ANTHROPIC_REASONING_TRUST", "")
    monkeypatch.setattr(cas, "openai_usable_for_routing", lambda *a, **k: False)
    monkeypatch.setattr(cas, "openrouter_usable_for_reasoning", lambda: True)
    monkeypatch.setattr(cas, "anthropic_usable_for_reasoning", lambda: False)
    cap = pr.reasoning_provider_capability_snapshot()
    for name in ("local", "openai", "openrouter", "anthropic"):
        row = cap.get(name)
        assert isinstance(row, dict)
        assert "autonomy_safe" in row
        assert "blocked_reason" in row
    assert cap["openrouter"]["autonomy_safe"] is True
    assert cap["anthropic"]["autonomy_safe"] is False


def test_select_best_api_require_autonomy_safe_clamps_untrusted_anthropic(monkeypatch):
    monkeypatch.setattr(
        "project_guardian.openai_degraded.openai_insufficient_quota_reasoning_blocked",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: False)
    _patch_cloud_credentials(monkeypatch, openai=False, openrouter=True, anthropic=True)
    monkeypatch.setenv("ELYSIA_ANTHROPIC_REASONING_TRUST", "")
    monkeypatch.setattr(cas, "openrouter_usable_for_reasoning", lambda: True)
    monkeypatch.setattr(cas, "openai_usable_for_routing", lambda *a, **k: False)
    from project_guardian.multi_api_router import select_best_api

    r_unsafe = select_best_api(
        "reasoning",
        quality_requirement="high",
        registry=None,
        reserve_slot=False,
        log_decision=False,
        require_autonomy_safe=False,
    )
    assert r_unsafe.get("chosen") == "anthropic"
    r_safe = select_best_api(
        "reasoning",
        quality_requirement="high",
        registry=None,
        reserve_slot=False,
        log_decision=False,
        require_autonomy_safe=True,
    )
    assert r_safe.get("chosen") == "openrouter"


def test_select_best_api_require_autonomy_safe_no_safe_cloud_falls_back_local(monkeypatch):
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: False)
    _patch_cloud_credentials(monkeypatch, openai=False, openrouter=False, anthropic=True)
    monkeypatch.setenv("ELYSIA_ANTHROPIC_REASONING_TRUST", "")
    monkeypatch.setattr(cas, "openrouter_usable_for_reasoning", lambda: False)
    monkeypatch.setattr(cas, "openai_usable_for_routing", lambda *a, **k: False)
    from project_guardian.multi_api_router import select_best_api

    r = select_best_api(
        "reasoning",
        quality_requirement="high",
        registry=None,
        reserve_slot=False,
        log_decision=False,
        require_autonomy_safe=True,
    )
    assert r.get("chosen") == "local_mistral"


def test_require_autonomy_safe_prefers_local_when_staged(monkeypatch):
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: True)
    _patch_cloud_credentials(monkeypatch, openai=True, openrouter=True, anthropic=False)
    monkeypatch.setattr(cas, "openai_usable_for_routing", lambda *a, **k: True)
    from project_guardian.multi_api_router import select_best_api

    r = select_best_api(
        "reasoning",
        registry=None,
        reserve_slot=False,
        log_decision=False,
        require_autonomy_safe=True,
    )
    assert r.get("chosen") == "local_mistral"


def test_autonomy_safe_cloud_backend_order_respects_flags(monkeypatch):
    monkeypatch.setattr(pr, "local_planner_provider_ready", lambda: False)
    _patch_cloud_credentials(monkeypatch, openai=True, openrouter=True, anthropic=False)
    monkeypatch.setattr(cas, "openai_usable_for_routing", lambda *a, **k: True)
    monkeypatch.setattr(cas, "openrouter_usable_for_reasoning", lambda: True)
    order = pr.autonomy_safe_cloud_backend_order()
    assert order == ["openrouter", "openai"]


def test_pick_degraded_respects_restricted_pool(monkeypatch):
    monkeypatch.setattr(pr, "restricted_safe_startup_mode", lambda: True)
    cands = [
        {"action": "execute_self_task", "priority_score": 99},
        {"action": "tool_registry_pulse", "priority_score": 1},
    ]
    pick = pr.pick_degraded_autonomy_candidate(cands)
    assert pick and pick["action"] == "tool_registry_pulse"


def test_auto_learning_llm_callback_prefers_autonomy_safe_completion():
    from project_guardian.auto_learning import AutoLearningScheduler

    picks: list = []

    class Sys:
        def chat_with_llm(self, msg):
            picks.append("chat")
            return ("x", "")

        def _autonomy_llm_completion(self, messages, max_tokens=300, **kw):
            picks.append("auto")
            return ("y", "")

    s = AutoLearningScheduler.__new__(AutoLearningScheduler)
    s.system_ref = Sys()
    cb = AutoLearningScheduler._get_llm_callback(s)
    assert cb is not None
    cb("hi")
    assert picks == ["auto"]


def test_auto_learning_llm_callback_uses_safe_llm_not_operator_chat():
    from project_guardian.auto_learning import AutoLearningScheduler

    picks: list = []

    class Sys:
        def chat_with_llm(self, msg):
            picks.append("chat")
            return ("x", "")

        def _llm_completion(self, messages, max_tokens=300, **kw):
            picks.append(("llm", kw.get("require_autonomy_safe_reasoning")))
            return ("y", "")

    s = AutoLearningScheduler.__new__(AutoLearningScheduler)
    s.system_ref = Sys()
    cb = AutoLearningScheduler._get_llm_callback(s)
    assert cb is not None
    cb("hi")
    assert ("llm", True) in picks
    assert "chat" not in picks


def test_auto_learning_llm_callback_fail_closed_when_only_operator_chat():
    from project_guardian.auto_learning import (
        AUTONOMY_LEARNING_NO_SAFE_LLM_PATH,
        AutoLearningScheduler,
    )

    picks: list = []

    class Sys:
        def chat_with_llm(self, msg):
            picks.append("chat")
            return ("x", "")

    s = AutoLearningScheduler.__new__(AutoLearningScheduler)
    s.system_ref = Sys()
    cb = AutoLearningScheduler._get_llm_callback(s)
    assert cb is not None
    reply, err = cb("hi")
    assert reply == ""
    assert err == AUTONOMY_LEARNING_NO_SAFE_LLM_PATH
    assert picks == []
