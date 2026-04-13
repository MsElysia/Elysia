# project_guardian/mission_autonomy.py
# Persistent mission hierarchy + campaign-aware autonomy scoring (Mission Director governance).

from __future__ import annotations

import json
import logging
import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "mission_autonomy.json"
STATE_PATH = PROJECT_ROOT / "data" / "mission_autonomy_state.json"

# Runtime feedback clamps (conservative but faster than hour-scale cooldowns alone)
_CAMPAIGN_ADJUST_MIN = -0.22
_CAMPAIGN_ADJUST_MAX = 0.22
_ACTION_BIAS_MIN = -6.0
_ACTION_BIAS_MAX = 4.5
_ARCH_BIAS_MIN = -2.5
_ARCH_BIAS_MAX = 3.0
_MOMENTUM_MAX = 4.5

_DEFAULT_STATE: Dict[str, Any] = {
    "version": 1,
    "enabled": True,
    "core_mission": "Advance useful autonomy with measurable outcomes.",
    "standing_priorities": [],
    "campaigns": [],
    "session_objectives": [],
    "action_campaign_map": {},
    "artifact_expected_actions": ["execute_self_task", "work_on_objective"],
    "governance_weights": {
        "mission_alignment": 2.0,
        "campaign_contribution": 2.5,
        "usefulness": 1.2,
        "cost": 0.5,
        "repetition_penalty": 1.8,
        "novelty_secondary": 0.3,
        "drift_exploratory_penalty": 2.0,
        "no_artifact_penalty": 1.0,
        "priority_scale": 0.8,
    },
}

# Rough cost tier: higher = more expensive (LLM/API churn)
_ACTION_COST: Dict[str, float] = {
    "execute_self_task": 0.65,
    "fractalmind_planning": 0.75,
    "consider_learning": 0.55,
    "consider_prompt_evolution": 0.6,
    "consider_adversarial_learning": 0.55,
    "consider_dream_cycle": 0.45,
    "work_on_objective": 0.5,
    "harvest_income_report": 0.35,
    "income_modules_pulse": 0.25,
    "tool_registry_pulse": 0.3,
    "rebuild_vector": 0.85,
    "process_queue": 0.4,
    "execute_task": 0.5,
    "mission_deadline": 0.1,
    "continue_mission": 0.35,
    "question_probe": 0.2,
    "code_analysis": 0.5,
    "consider_mutation": 0.5,
}

_USEFULNESS_PRIORS: Dict[str, float] = {
    "execute_self_task": 0.95,
    "work_on_objective": 0.9,
    "process_queue": 0.82,
    "mission_deadline": 1.0,
    "execute_task": 0.88,
    "rebuild_vector": 0.85,
    "continue_mission": 0.75,
    "harvest_income_report": 0.72,
    "fractalmind_planning": 0.55,
    "consider_learning": 0.5,
    "consider_prompt_evolution": 0.48,
    "consider_adversarial_learning": 0.45,
    "question_probe": 0.35,
    "income_modules_pulse": 0.4,
    "tool_registry_pulse": 0.38,
    "consider_dream_cycle": 0.42,
    "code_analysis": 0.5,
    "consider_mutation": 0.45,
}


def _tokenize(text: str) -> List[str]:
    return [t for t in re.split(r"[^\w]+", (text or "").lower()) if len(t) > 2]


def _overlap_score(a: str, b: str) -> float:
    ta, tb = set(_tokenize(a)), set(_tokenize(b))
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return min(1.0, inter / max(6, min(len(ta), len(tb))))


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("[MissionDirector] could not load %s: %s", path, e)
        return None


def _deep_merge_defaults(loaded: Dict[str, Any]) -> Dict[str, Any]:
    base = deepcopy(_DEFAULT_STATE)
    base.update({k: v for k, v in loaded.items() if k != "campaigns"})
    if loaded.get("campaigns"):
        base["campaigns"] = loaded["campaigns"]
    if loaded.get("standing_priorities") is not None:
        base["standing_priorities"] = loaded["standing_priorities"]
    if loaded.get("session_objectives") is not None:
        base["session_objectives"] = loaded["session_objectives"]
    if loaded.get("action_campaign_map"):
        base["action_campaign_map"] = {**base.get("action_campaign_map", {}), **loaded["action_campaign_map"]}
    if loaded.get("governance_weights"):
        gw = dict(base.get("governance_weights", {}))
        gw.update(loaded["governance_weights"])
        base["governance_weights"] = gw
    return base


class MissionAutonomyStore:
    """Loads mission/campaign config + mutable runtime state; governs candidate scoring."""

    def __init__(self) -> None:
        self._config: Dict[str, Any] = deepcopy(_DEFAULT_STATE)
        self._runtime: Dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        cfg = _load_json(CONFIG_PATH)
        if cfg:
            self._config = _deep_merge_defaults(cfg)
        else:
            self._config = deepcopy(_DEFAULT_STATE)
        rt = _load_json(STATE_PATH)
        self._runtime = rt if isinstance(rt, dict) else {}
        self._runtime.setdefault("last_artifacts", [])
        self._runtime.setdefault("recent_action_fingerprints", [])
        self._runtime.setdefault("campaign_priority_adjust", {})
        self._runtime.setdefault("action_priority_bias", {})
        self._runtime.setdefault("noop_streak", {})
        self._runtime.setdefault("execute_self_task_momentum", 0.0)
        self._runtime.setdefault("archetype_mission_bias", {})

    def _save_runtime(self) -> None:
        self._runtime["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(self._runtime, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug("[MissionDirector] state save: %s", e)

    @property
    def enabled(self) -> bool:
        return bool(self._config.get("enabled", True))

    def to_inspectable_dict(self) -> Dict[str, Any]:
        return {
            "config_path": str(CONFIG_PATH),
            "state_path": str(STATE_PATH),
            "enabled": self.enabled,
            "core_mission": self._config.get("core_mission"),
            "campaign_count": len(self._config.get("campaigns") or []),
            "primary_campaign": self.primary_campaign(),
        }

    def _effective_campaign_priority(self, camp: Dict[str, Any]) -> float:
        cid = str(camp.get("id") or "")
        base = float(camp.get("current_priority", 0) or 0)
        adj = float((self._runtime.get("campaign_priority_adjust") or {}).get(cid, 0) or 0)
        return base + adj

    def primary_campaign(self) -> Optional[Dict[str, Any]]:
        camps = [c for c in (self._config.get("campaigns") or []) if isinstance(c, dict)]
        active = [c for c in camps if str(c.get("status", "active")).lower() == "active"]
        if not active:
            return None
        active.sort(key=self._effective_campaign_priority, reverse=True)
        return active[0]

    def _campaign_by_id(self, cid: str) -> Optional[Dict[str, Any]]:
        for c in self._config.get("campaigns") or []:
            if isinstance(c, dict) and str(c.get("id")) == cid:
                return c
        return None

    def score_candidate(
        self,
        candidate: Dict[str, Any],
        recent_actions: List[str],
        *,
        primary: Optional[Dict[str, Any]],
    ) -> Tuple[float, Dict[str, float]]:
        """Returns (priority_delta, breakdown)."""
        gw = self._config.get("governance_weights") or _DEFAULT_STATE["governance_weights"]
        scale = float(gw.get("priority_scale", 0.8) or 0.8)
        act = str(candidate.get("action") or "")
        reason = str(candidate.get("reason") or "")
        meta = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
        exploratory = bool(meta.get("exploratory"))

        core = str(self._config.get("core_mission") or "")
        mission_al = 0.0
        for sp in self._config.get("standing_priorities") or []:
            if isinstance(sp, dict):
                mission_al = max(mission_al, _overlap_score(core + " " + str(sp.get("title", "")), reason + " " + act))
        mission_al = max(mission_al, _overlap_score(core, reason + " " + act))

        camp_contr = 0.15
        pmap = self._config.get("action_campaign_map") or {}
        linked = list(pmap.get(act) or [])
        prim_id = (primary or {}).get("id")
        recommended = list((primary or {}).get("next_recommended_actions") or [])
        if prim_id and prim_id in linked:
            camp_contr = 0.95
        elif linked:
            camp_contr = 0.55
        if act in recommended:
            camp_contr = min(1.0, camp_contr + 0.25)

        useful = float(_USEFULNESS_PRIORS.get(act, 0.5))
        cost = float(_ACTION_COST.get(act, 0.45))
        cost_term = max(0.0, 1.0 - cost)

        rep_pen = 0.0
        tail = recent_actions[-5:] if recent_actions else []
        if tail.count(act) >= 2:
            rep_pen = min(1.0, 0.35 * tail.count(act))
        if act in tail[-3:] and act not in recommended and exploratory:
            rep_pen = min(1.0, rep_pen + 0.4)

        novelty_sec = 0.0
        if exploratory and camp_contr < 0.5:
            novelty_sec = 0.25

        w_ma = float(gw.get("mission_alignment", 2.0) or 2.0)
        w_cc = float(gw.get("campaign_contribution", 2.5) or 2.5)
        w_us = float(gw.get("usefulness", 1.2) or 1.2)
        w_co = float(gw.get("cost", 0.5) or 0.5)
        w_rp = float(gw.get("repetition_penalty", 1.8) or 1.8)
        w_nv = float(gw.get("novelty_secondary", 0.3) or 0.3)

        subtotal = (
            w_ma * mission_al
            + w_cc * camp_contr
            + w_us * useful
            + w_co * cost_term
            + w_nv * novelty_sec
            - w_rp * rep_pen
        )
        delta = subtotal * scale

        breakdown = {
            "mission_alignment": mission_al,
            "campaign_contribution": camp_contr,
            "usefulness_prior": useful,
            "cost_term": cost_term,
            "repetition_penalty": rep_pen,
            "novelty_secondary": novelty_sec,
            "raw_subtotal": subtotal,
            "priority_delta": delta,
        }
        return delta, breakdown

    def drift_adjustment(
        self,
        candidate: Dict[str, Any],
        recent_actions: List[str],
        *,
        primary: Optional[Dict[str, Any]],
    ) -> Tuple[float, Optional[str]]:
        """Returns extra priority delta (negative = downrank) and optional log reason."""
        gw = self._config.get("governance_weights") or {}
        act = str(candidate.get("action") or "")
        meta = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
        exploratory = bool(meta.get("exploratory"))
        pmap = self._config.get("action_campaign_map") or {}
        linked = list(pmap.get(act) or [])
        recommended = list((primary or {}).get("next_recommended_actions") or [])

        drift_pen = 0.0
        reasons: List[str] = []

        if exploratory:
            if not linked:
                p = float(gw.get("drift_exploratory_penalty", 2.0) or 2.0)
                drift_pen -= p * 0.6
                reasons.append("exploratory_no_campaign_map")
            elif act not in recommended and primary:
                drift_pen -= float(gw.get("drift_exploratory_penalty", 2.0) or 2.0) * 0.35
                reasons.append("exploratory_not_primary_recommended")

        tail = recent_actions[-4:] if recent_actions else []
        if tail.count(act) >= 3:
            drift_pen -= 1.6
            reasons.append("repeated_without_evidence")

        art_expect = set(self._config.get("artifact_expected_actions") or [])
        if act in art_expect and exploratory:
            drift_pen -= float(gw.get("no_artifact_penalty", 1.0) or 1.0) * 0.5
            reasons.append("artifact_action_marked_exploratory_only")

        if not linked and not exploratory and act not in ("mission_deadline", "execute_task", "rebuild_vector"):
            drift_pen -= 0.8
            reasons.append("no_active_campaign_link")

        msg = "; ".join(reasons) if reasons else None
        return drift_pen, msg

    # --- Outcome feedback (autonomy cycles → campaign + action bias) ---

    def _decay_feedback_state(self) -> None:
        mom = float(self._runtime.get("execute_self_task_momentum", 0) or 0)
        self._runtime["execute_self_task_momentum"] = round(mom * 0.94, 4)
        biases = self._runtime.setdefault("action_priority_bias", {})
        for k in list(biases.keys()):
            v = float(biases[k] or 0) * 0.997
            if abs(v) < 0.06:
                biases.pop(k, None)
            else:
                biases[k] = round(max(_ACTION_BIAS_MIN, min(_ACTION_BIAS_MAX, v)), 4)
        arch = self._runtime.setdefault("archetype_mission_bias", {})
        for k in list(arch.keys()):
            v = float(arch[k] or 0) * 0.996
            if abs(v) < 0.05:
                arch.pop(k, None)
            else:
                arch[k] = round(max(_ARCH_BIAS_MIN, min(_ARCH_BIAS_MAX, v)), 4)

    def _adjust_campaign_delta(self, campaign_id: str, delta: float, reason: str) -> None:
        adj = self._runtime.setdefault("campaign_priority_adjust", {})
        cur = float(adj.get(campaign_id, 0) or 0)
        new = max(_CAMPAIGN_ADJUST_MIN, min(_CAMPAIGN_ADJUST_MAX, cur + delta))
        if abs(new - cur) < 1e-6:
            return
        adj[campaign_id] = round(new, 4)
        cobj = self._campaign_by_id(campaign_id) or {"id": campaign_id, "current_priority": 0.0}
        eff = self._effective_campaign_priority(cobj)
        tag = "campaign_promoted" if delta > 0 else "campaign_demoted"
        logger.info(
            "[MissionDirector] %s id=%s delta=%+.3f cumulative_adj=%.3f effective_sort=%.3f reason=%s",
            tag,
            campaign_id,
            delta,
            new,
            eff,
            reason[:120],
        )

    def _adjust_action_bias(self, action: str, delta: float, *, reason: str, streak: int) -> None:
        biases = self._runtime.setdefault("action_priority_bias", {})
        cur = float(biases.get(action, 0) or 0)
        new = max(_ACTION_BIAS_MIN, min(_ACTION_BIAS_MAX, cur + delta))
        biases[action] = round(new, 4)
        logger.info(
            "[MissionDirector] no_op_penalty_applied action=%s streak=%d bias_delta=%+.2f cumulative_bias=%.2f reason=%s",
            action,
            streak,
            delta,
            new,
            reason[:120],
        )

    def _noop_streak_inc(self, key: str) -> int:
        ns = self._runtime.setdefault("noop_streak", {})
        n = int(ns.get(key, 0) or 0) + 1
        ns[key] = n
        return n

    def _noop_streak_reset(self, key: str) -> None:
        self._runtime.setdefault("noop_streak", {})[key] = 0

    def feedback_harvest_income_report(self, *, nonzero: bool) -> None:
        self.reload()
        if not self.enabled:
            return
        if nonzero:
            self._noop_streak_reset("harvest_income_report")
            self._adjust_campaign_delta("cmp_revenue_intel", 0.05, "harvest_nonzero_sales_or_total")
            # soften prior harvest downrank
            biases = self._runtime.setdefault("action_priority_bias", {})
            cur = float(biases.get("harvest_income_report", 0) or 0)
            if cur < 0:
                biases["harvest_income_report"] = round(max(_ACTION_BIAS_MIN, cur * 0.45), 4)
            self._save_runtime()
            return
        n = self._noop_streak_inc("harvest_income_report")
        # First zero hits immediately (aggressive vs cooldown-only); ramp with streak
        pen = 1.15 + 0.55 * min(n, 5)
        self._adjust_action_bias("harvest_income_report", -pen, reason="zero_total_zero_sales", streak=n)
        self._adjust_campaign_delta("cmp_revenue_intel", -0.06 - 0.03 * min(n, 4), "repeated_zero_harvest")
        # Shift emphasis toward execution / artifacts
        self._adjust_campaign_delta("cmp_execution", 0.04 + 0.02 * min(n, 3), "compensate_for_zero_revenue_reads")
        self._save_runtime()

    def feedback_income_modules_pulse(self, *, all_zero: bool, same_signature: bool) -> None:
        self.reload()
        if not self.enabled:
            return
        key = "income_modules_pulse"
        if not all_zero or not same_signature:
            if not all_zero:
                self._noop_streak_reset(key)
                self._adjust_campaign_delta("cmp_revenue_intel", 0.04, "income_pulse_nonzero_signal")
            self._save_runtime()
            return
        n = self._noop_streak_inc(key)
        pen = 1.05 + 0.5 * min(n, 5)
        self._adjust_action_bias(key, -pen, reason="all_zero_unchanged_signature", streak=n)
        self._adjust_campaign_delta("cmp_revenue_intel", -0.055 - 0.025 * min(n, 4), "repeated_zero_income_pulse")
        self._adjust_campaign_delta("cmp_execution", 0.035 + 0.015 * min(n, 3), "prefer_artifact_work_over_admin_pulse")
        self._save_runtime()

    def feedback_work_on_objective(self, *, state_changed: bool, tasks_created: int, submitted: int) -> None:
        self.reload()
        if not self.enabled:
            return
        key = "work_on_objective"
        if state_changed or tasks_created > 0 or submitted > 0:
            self._noop_streak_reset(key)
            self._adjust_campaign_delta("cmp_planning", 0.05, "objective_state_advanced")
            biases = self._runtime.setdefault("action_priority_bias", {})
            cur = float(biases.get(key, 0) or 0)
            if cur < 0:
                biases[key] = round(max(_ACTION_BIAS_MIN, cur * 0.5 + 0.4), 4)
            self._save_runtime()
            return
        n = self._noop_streak_inc(key)
        pen = 1.35 + 0.65 * min(n, 5)
        self._adjust_action_bias(key, -pen, reason="tasks_created=0_submitted=0_changed=False", streak=n)
        self._adjust_campaign_delta("cmp_planning", -0.05 - 0.03 * min(n, 4), "objective_work_no_progress")
        self._adjust_campaign_delta("cmp_execution", 0.05 + 0.02 * min(n, 4), "shift_toward_self_task_artifacts")
        self._save_runtime()

    def feedback_self_task_artifact_reward(
        self,
        *,
        archetype: str,
        success: bool,
        useful: bool,
        objective_advanced: bool,
    ) -> None:
        """Strong up-rank for saved artifacts that advance objectives."""
        self.reload()
        if not self.enabled or not success or not useful:
            return
        mom = float(self._runtime.get("execute_self_task_momentum", 0) or 0)
        add_m = 1.35 if objective_advanced else 0.85
        self._runtime["execute_self_task_momentum"] = round(min(_MOMENTUM_MAX, mom + add_m), 4)
        biases = self._runtime.setdefault("action_priority_bias", {})
        cur = float(biases.get("execute_self_task", 0) or 0)
        biases["execute_self_task"] = round(
            max(_ACTION_BIAS_MIN, min(_ACTION_BIAS_MAX, cur + (1.1 if objective_advanced else 0.75))),
            4,
        )
        arch = self._runtime.setdefault("archetype_mission_bias", {})
        acur = float(arch.get(archetype, 0) or 0)
        arch[archetype] = round(
            max(_ARCH_BIAS_MIN, min(_ARCH_BIAS_MAX, acur + (0.85 if objective_advanced else 0.55))),
            4,
        )
        cadj = 0.09 if objective_advanced else 0.06
        self._adjust_campaign_delta("cmp_execution", cadj, f"useful_artifact arch={archetype[:40]} adv={objective_advanced}")
        self._adjust_campaign_delta("cmp_revenue_intel", -0.02, "rebalance_after_strong_execution_signal")
        logger.info(
            "[MissionDirector] artifact_reward_applied archetype=%s momentum=%.2f exec_bias=%.2f arch_bias=%.2f useful=%s adv=%s",
            archetype[:48],
            self._runtime["execute_self_task_momentum"],
            biases["execute_self_task"],
            arch[archetype],
            useful,
            objective_advanced,
        )
        self._save_runtime()

    def apply_governance(
        self,
        candidates: List[Dict[str, Any]],
        recent_actions: List[str],
    ) -> List[Dict[str, Any]]:
        if not self.enabled or not candidates:
            return candidates
        self.reload()
        self._decay_feedback_state()
        primary = self.primary_campaign()
        if primary:
            eff = self._effective_campaign_priority(primary)
            logger.info(
                "[MissionDirector] primary_campaign id=%s title=%s base_priority=%.2f effective=%.2f",
                primary.get("id"),
                str(primary.get("title", ""))[:70],
                float(primary.get("current_priority", 0) or 0),
                eff,
            )
        else:
            logger.info("[MissionDirector] primary_campaign none (no active campaigns)")

        out: List[Dict[str, Any]] = []
        arch_biases = self._runtime.get("archetype_mission_bias") or {}
        for c in candidates:
            nc = dict(c)
            delta, br = self.score_candidate(nc, recent_actions, primary=primary)
            drift_d, drift_msg = self.drift_adjustment(nc, recent_actions, primary=primary)
            total = float(nc.get("priority_score", 0) or 0) + delta + drift_d
            act = str(nc.get("action") or "")
            apb = float((self._runtime.get("action_priority_bias") or {}).get(act, 0) or 0)
            mom = 0.0
            if act == "execute_self_task":
                mom = float(self._runtime.get("execute_self_task_momentum", 0) or 0)
            arch_bonus = 0.0
            if act == "execute_self_task" and arch_biases:
                arch_bonus = sum(float(v) for v in arch_biases.values()) / max(1, len(arch_biases)) * 0.35
            fb = apb + mom + arch_bonus
            total += fb
            nc["priority_score"] = total
            nc["_mission_governance"] = {
                "score_delta": round(delta, 4),
                "drift_delta": round(drift_d, 4),
                "feedback_bias": round(fb, 4),
                "breakdown": {k: round(v, 4) if isinstance(v, float) else v for k, v in br.items()},
            }
            if drift_msg:
                nc["_mission_drift"] = drift_msg
                logger.info(
                    "[MissionDirector] drift_downrank action=%s deltas=(gov=%.2f drift=%.2f) reasons=%s",
                    nc.get("action"),
                    delta,
                    drift_d,
                    drift_msg,
                )
            out.append(nc)
        self._save_runtime()
        return out

    def record_campaign_progress(self, campaign_id: str, note: str, *, advance: bool = True) -> None:
        self.reload()
        c = self._campaign_by_id(campaign_id)
        if not c:
            return
        c.setdefault("progress_log", []).append({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "note": note[:500]})
        if advance:
            c["last_progress_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        # Persist into config file is heavy; store highlights in runtime state
        self._runtime.setdefault("campaign_progress", {})[campaign_id] = {
            "last_note": note[:300],
            "last_progress_at": c.get("last_progress_at"),
        }
        self._save_runtime()
        logger.info("[MissionDirector] campaign_progress id=%s note=%s", campaign_id, note[:120])

    def append_artifact_record(self, record: Dict[str, Any]) -> None:
        self.reload()
        arts = self._runtime.setdefault("last_artifacts", [])
        arts.append(record)
        self._runtime["last_artifacts"] = arts[-30:]
        self._save_runtime()

    def fingerprint_action(self, action: str) -> None:
        self.reload()
        fp = self._runtime.setdefault("recent_action_fingerprints", [])
        fp.append({"t": time.time(), "action": action})
        self._runtime["recent_action_fingerprints"] = fp[-40:]
        self._save_runtime()


def record_self_task_artifact_outcome(
    *,
    task: Dict[str, Any],
    success: bool,
    useful: bool,
    archetype: str,
    execution_artifact: Optional[str],
    objective_advanced: Optional[bool] = None,
) -> None:
    """Called from SelfTaskQueue.complete — no guardian reference required."""
    try:
        store = MissionAutonomyStore()
        if not store.enabled:
            return
        tid = str(task.get("task_id") or "")
        adv = bool(objective_advanced) if objective_advanced is not None else bool(task.get("objective_advanced"))
        outcome_cls = "success_useful" if success and useful else ("success" if success else "failed")
        review = str(task.get("outcome_detail") or task.get("execution_reason") or "")[:400]
        rec = {
            "task_id": tid,
            "archetype": archetype,
            "success": success,
            "useful": useful,
            "objective_advanced": adv,
            "outcome_class": outcome_cls,
            "execution_artifact": (execution_artifact or task.get("execution_artifact") or "")[:300],
            "review": review,
            "next_step": "continue_primary_campaign" if useful else "reassess_blockers",
        }
        store.append_artifact_record(rec)
        logger.info(
            "[MissionDirector] artifact_complete task=%s class=%s useful=%s artifact=%s adv=%s",
            tid,
            outcome_cls,
            useful,
            bool(execution_artifact or task.get("execution_artifact")),
            adv,
        )
        if success and useful:
            store.feedback_self_task_artifact_reward(
                archetype=archetype,
                success=success,
                useful=useful,
                objective_advanced=adv,
            )
            store.record_campaign_progress("cmp_execution", f"self_task {tid} ({archetype}) useful artifact", advance=True)
        elif not success:
            store.record_campaign_progress("cmp_execution", f"self_task {tid} failed: {review[:80]}", advance=False)
    except Exception as e:
        logger.debug("[MissionDirector] artifact outcome hook: %s", e)


def mission_autonomy_feedback_harvest(*, nonzero: bool) -> None:
    try:
        MissionAutonomyStore().feedback_harvest_income_report(nonzero=nonzero)
    except Exception as e:
        logger.debug("[MissionDirector] feedback_harvest: %s", e)


def mission_autonomy_feedback_income_pulse(*, all_zero: bool, same_signature: bool) -> None:
    try:
        MissionAutonomyStore().feedback_income_modules_pulse(all_zero=all_zero, same_signature=same_signature)
    except Exception as e:
        logger.debug("[MissionDirector] feedback_income_pulse: %s", e)


def mission_autonomy_feedback_work_objective(*, state_changed: bool, tasks_created: int, submitted: int) -> None:
    try:
        MissionAutonomyStore().feedback_work_on_objective(
            state_changed=state_changed,
            tasks_created=tasks_created,
            submitted=submitted,
        )
    except Exception as e:
        logger.debug("[MissionDirector] feedback_work_objective: %s", e)


def log_selected_action(action: str, reason: str, mission_meta: Optional[Dict[str, Any]] = None) -> None:
    try:
        store = MissionAutonomyStore()
        if not store.enabled:
            return
        store.fingerprint_action(action)
        pc = store.primary_campaign()
        pid = pc.get("id") if pc else "-"
        mm = ""
        if mission_meta and isinstance(mission_meta, dict):
            mm = f" mission_delta={mission_meta.get('score_delta')} drift={mission_meta.get('drift_delta')}"
        logger.info(
            "[MissionDirector] selected action=%s campaign=%s because=%s%s",
            action,
            pid,
            (reason or "")[:160],
            mm,
        )
    except Exception as e:
        logger.debug("[MissionDirector] log_selected: %s", e)
