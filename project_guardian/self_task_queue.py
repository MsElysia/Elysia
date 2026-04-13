# project_guardian/self_task_queue.py
# Persistent bounded queue for self-generated structured tasks.

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .self_task_execution_outcome import is_execution_stage_archetype

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = PROJECT_ROOT / "data" / "self_task_queue.json"

# Strong/useful but non-advancing: suppress after repeated runs (see complete()).
USEFUL_NONADV_SUPPRESSION_ARCHETYPES = frozenset({
    "summarize_monetizable_directions_from_learning",
    "create_small_dry_run_offer_ideas",
    "generate_execution_plan",
    "rank_top_opportunities",
})


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SelfTaskQueue:
    """File-backed queue: pending → in_progress → completed/failed. Dedupe + TTL + cap."""

    def __init__(self, storage_path: Optional[Path] = None, max_size: int = 24) -> None:
        self.path = Path(storage_path) if storage_path else DEFAULT_PATH
        self.max_size = max(4, int(max_size))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"tasks": [], "dedupe_last_ts": {}, "archetype_bias": {}, "updated_at": _iso()}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.debug("self_task_queue load: %s", e)
            return {"tasks": [], "dedupe_last_ts": {}, "archetype_bias": {}, "updated_at": _iso()}

    def _save(self) -> None:
        self._data["updated_at"] = _iso()
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug("self_task_queue save: %s", e)

    def dedupe_recent(self, key: str, cooldown_sec: float) -> bool:
        """True if key should be skipped (still in cooldown)."""
        last = float(self._data.get("dedupe_last_ts", {}).get(key, 0) or 0)
        return (time.time() - last) < float(cooldown_sec)

    def touch_dedupe(self, key: str) -> None:
        self._data.setdefault("dedupe_last_ts", {})[key] = time.time()
        self._save()

    def archetype_multiplier(self, archetype: str) -> float:
        b = float(self._data.get("archetype_bias", {}).get(archetype, 0.0) or 0.0)
        return max(0.35, min(1.35, 1.0 + b))

    def archetype_suppression_factor(self, archetype: str) -> float:
        now = time.time()
        until = float((self._data.get("archetype_suppress_until") or {}).get(archetype, 0) or 0)
        if now < until:
            return 0.28
        return 1.0

    def adjust_archetype(self, archetype: str, delta: float) -> None:
        ab = self._data.setdefault("archetype_bias", {})
        cur = float(ab.get(archetype, 0.0) or 0.0)
        ab[archetype] = max(-0.5, min(0.5, cur + delta))
        self._save()

    def enqueue(self, task: Dict[str, Any], *, dedupe_key: str, cooldown_sec: float) -> bool:
        if self.dedupe_recent(dedupe_key, cooldown_sec):
            return False
        tasks: List[Dict[str, Any]] = self._data.setdefault("tasks", [])
        # drop duplicate pending by dedupe_key
        for t in tasks:
            if t.get("status") == "pending" and t.get("dedupe_key") == dedupe_key:
                return False
        while len([x for x in tasks if x.get("status") == "pending"]) >= self.max_size:
            self._drop_oldest_pending(tasks)
        tid = task.get("task_id") or f"st_{uuid.uuid4().hex[:12]}"
        task["task_id"] = tid
        task.setdefault("status", "pending")
        task.setdefault("created_at", _iso())
        task.setdefault("updated_at", _iso())
        task["dedupe_key"] = dedupe_key
        tasks.append(task)
        self.touch_dedupe(dedupe_key)
        self._trim_completed(tasks)
        self._save()
        logger.info("[SelfTask] enqueued %s (%s)", tid, task.get("title", "")[:60])
        return True

    def _drop_oldest_pending(self, tasks: List[Dict[str, Any]]) -> None:
        pend = [(i, t) for i, t in enumerate(tasks) if t.get("status") == "pending"]
        if not pend:
            return
        pend.sort(key=lambda x: x[1].get("created_at") or "")
        idx = pend[0][0]
        tasks[idx]["status"] = "failed"
        tasks[idx]["last_outcome"] = "expired_cap"
        tasks[idx]["updated_at"] = _iso()

    def _trim_completed(self, tasks: List[Dict[str, Any]], keep: int = 40) -> None:
        done = [t for t in tasks if t.get("status") in ("completed", "failed")]
        if len(done) <= keep:
            return
        done.sort(key=lambda x: x.get("completed_at") or x.get("updated_at") or "")
        drop_keys = {t["task_id"] for t in done[: max(0, len(done) - keep)]}
        self._data["tasks"] = [t for t in tasks if t.get("task_id") not in drop_keys]

    def expire_stale(
        self,
        *,
        ttl_sec: float,
        max_priority: float,
    ) -> int:
        now = time.time()
        n = 0
        for t in self._data.get("tasks", []):
            if t.get("status") != "pending":
                continue
            try:
                created = t.get("created_at") or ""
                ts = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
            except Exception:
                ts = now
            if (now - ts) > ttl_sec and float(t.get("priority", 0.5) or 0) <= max_priority:
                t["status"] = "failed"
                t["last_outcome"] = "stale_expired"
                t["updated_at"] = _iso()
                n += 1
        if n:
            self._save()
        return n

    def list_pending_sorted(
        self,
        objective_store: Optional[Any] = None,
        portfolio_tracker: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        pend = [t for t in self._data.get("tasks", []) if t.get("status") == "pending"]

        def sort_key(x: Dict[str, Any]) -> Tuple[float, str]:
            arch = str(x.get("archetype", ""))
            base = (
                -float(x.get("priority", 0) or 0)
                * self.archetype_multiplier(arch)
                * self.archetype_suppression_factor(arch)
            )
            if objective_store is not None and hasattr(objective_store, "sort_key_boost"):
                base += float(objective_store.sort_key_boost(x))
            if portfolio_tracker is not None and hasattr(portfolio_tracker, "sort_pressure"):
                base += float(portfolio_tracker.sort_pressure(x))
            return (base, x.get("created_at") or "")

        pend.sort(key=sort_key)
        return pend

    def get_by_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        for t in self._data.get("tasks", []):
            if t.get("task_id") == task_id:
                return t
        return None

    def claim(self, task_id: str) -> Optional[Dict[str, Any]]:
        t = self.get_by_id(task_id)
        if not t or t.get("status") != "pending":
            return None
        t["status"] = "in_progress"
        t["started_at"] = _iso()
        t["updated_at"] = _iso()
        self._save()
        return t

    def complete(
        self,
        task_id: str,
        *,
        success: bool,
        useful: bool,
        detail: str = "",
        execution_tier: str = "strong",
        objective_advanced: Optional[bool] = None,
        advancement_score: Optional[float] = None,
        advancement_reason: str = "",
        operator_ready: Optional[bool] = None,
        execution_ready: Optional[bool] = None,
        execution_attempted: Optional[bool] = None,
        execution_outcome: Optional[str] = None,
        execution_reason: str = "",
        execution_artifact: Optional[str] = None,
        execution_followup_needed: Optional[bool] = None,
        value_verified: Optional[bool] = None,
        value_score: Optional[float] = None,
        value_reason: str = "",
        value_type: str = "none",
        cycle_best_choice_verified: Optional[bool] = None,
        cycle_choice_score: Optional[float] = None,
        cycle_choice_reason: str = "",
        cycle_opportunity_cost: str = "low",
        higher_priority_task_skipped: Optional[bool] = None,
        portfolio_balance_score: Optional[float] = None,
        portfolio_reason: str = "",
    ) -> None:
        t = self.get_by_id(task_id)
        if not t:
            return
        tier = (execution_tier or "strong").lower()
        arch = str(t.get("archetype") or "unknown")
        adv = bool(objective_advanced) if objective_advanced is not None else False
        if adv:
            self._data.setdefault("archetype_useful_nonadv_streak", {}).pop(arch, None)
            self._data.setdefault("archetype_suppress_until", {}).pop(arch, None)
        op_ready = bool(operator_ready) if operator_ready is not None else False
        ex_ready = bool(execution_ready) if execution_ready is not None else False
        ex_att = bool(execution_attempted) if execution_attempted is not None else False
        ex_out = (execution_outcome or "none").strip().lower()
        ex_follow = bool(execution_followup_needed) if execution_followup_needed is not None else False
        exec_stage = is_execution_stage_archetype(arch)
        t["completed_at"] = _iso()
        t["updated_at"] = _iso()
        t["outcome_detail"] = (detail or "")[:500]
        t["useful"] = useful
        t["execution_tier"] = tier
        t["objective_advanced"] = adv
        t["operator_ready"] = op_ready
        t["execution_ready"] = ex_ready
        t["execution_attempted"] = ex_att
        t["execution_outcome"] = ex_out
        if execution_reason:
            t["execution_reason"] = (execution_reason or "")[:500]
        if execution_artifact:
            t["execution_artifact"] = str(execution_artifact)[:500]
        t["execution_followup_needed"] = ex_follow
        if advancement_score is not None:
            t["advancement_score"] = float(advancement_score)
        if advancement_reason:
            t["advancement_reason"] = (advancement_reason or "")[:500]

        streak = self._data.setdefault("archetype_non_advance_streak", {})
        adv_not_ready = self._data.setdefault("archetype_advanced_not_ready_streak", {})
        succ_no_val = self._data.setdefault("archetype_success_no_value_streak", {})
        vv = bool(value_verified) if value_verified is not None else False
        if value_score is not None:
            t["value_score"] = float(value_score)
        if value_reason:
            t["value_reason"] = (value_reason or "")[:500]
        t["value_type"] = (value_type or "none")[:64]
        t["value_verified"] = vv
        cbv = True
        coc = (cycle_opportunity_cost or "low").strip().lower()
        if cycle_best_choice_verified is not None:
            cbv = bool(cycle_best_choice_verified)
        if cycle_choice_score is not None:
            t["cycle_choice_score"] = float(cycle_choice_score)
        if cycle_choice_reason:
            t["cycle_choice_reason"] = (cycle_choice_reason or "")[:500]
        t["cycle_opportunity_cost"] = coc[:16]
        if higher_priority_task_skipped is not None:
            t["higher_priority_task_skipped"] = bool(higher_priority_task_skipped)
        if cycle_best_choice_verified is not None:
            t["cycle_best_choice_verified"] = cbv
        pbs: Optional[float] = None
        if portfolio_balance_score is not None:
            pbs = float(portfolio_balance_score)
            t["portfolio_balance_score"] = pbs
        if portfolio_reason:
            t["portfolio_reason"] = (portfolio_reason or "")[:500]

        if tier == "failed":
            t["status"] = "failed"
            t["last_outcome"] = "failed"
            self.adjust_archetype(arch, -0.05)
            adv_not_ready[arch] = 0
            succ_no_val[arch] = 0
        elif tier == "weak":
            t["status"] = "completed"
            t["last_outcome"] = "weak_success"
            if adv:
                streak[arch] = 0
                if not op_ready:
                    adv_not_ready[arch] = int(adv_not_ready.get(arch, 0) or 0) + 1
                else:
                    adv_not_ready[arch] = 0
                mild = min(0.08, int(adv_not_ready.get(arch, 0) or 0) * 0.015)
                if op_ready:
                    self.adjust_archetype(arch, 0.025 if useful else 0.015)
                else:
                    self.adjust_archetype(arch, (0.012 if useful else 0.008) - mild)
            else:
                n = int(streak.get(arch, 0) or 0) + 1
                streak[arch] = n
                adv_not_ready[arch] = 0
                extra = min(0.12, n * 0.03)
                self.adjust_archetype(arch, (-0.06 if useful else -0.08) - extra)
        else:
            t["status"] = "completed" if success else "failed"
            if success:
                if exec_stage and ex_out not in ("none", ""):
                    streak[arch] = 0
                    adv_not_ready[arch] = 0
                    if ex_out == "succeeded" and vv:
                        succ_no_val[arch] = 0
                        base_sv = 0.09 if useful else 0.07
                        if cycle_best_choice_verified is not None:
                            if cbv:
                                base_sv += 0.02
                            else:
                                base_sv -= 0.045 if coc == "high" else (0.028 if coc == "medium" else 0.016)
                        self.adjust_archetype(arch, base_sv)
                        t["last_outcome"] = "execution_succeeded_value"
                    elif ex_out == "succeeded" and not vv:
                        succ_no_val[arch] = int(succ_no_val.get(arch, 0) or 0) + 1
                        nv_pen = min(0.12, int(succ_no_val.get(arch, 0) or 0) * 0.025)
                        base_nv = (0.035 if useful else 0.025) - nv_pen
                        if cycle_best_choice_verified is not None and not cbv:
                            base_nv -= 0.055 if coc == "high" else (0.032 if coc == "medium" else 0.018)
                        self.adjust_archetype(arch, base_nv)
                        t["last_outcome"] = "execution_succeeded_no_value"
                    elif ex_out == "partial" and vv:
                        succ_no_val[arch] = 0
                        base_pv = 0.05 if useful else 0.035
                        if cycle_best_choice_verified is not None:
                            if cbv:
                                base_pv += 0.012
                            else:
                                base_pv -= 0.022 if coc == "high" else 0.014
                        self.adjust_archetype(arch, base_pv)
                        t["last_outcome"] = "execution_partial_value"
                    elif ex_out == "partial" and not vv:
                        succ_no_val[arch] = int(succ_no_val.get(arch, 0) or 0) + 1
                        nv_pen = min(0.1, int(succ_no_val.get(arch, 0) or 0) * 0.02)
                        base_pnv = -0.025 - nv_pen
                        if cycle_best_choice_verified is not None and not cbv:
                            base_pnv -= 0.04 if coc == "high" else 0.025
                        self.adjust_archetype(arch, base_pnv)
                        t["last_outcome"] = "execution_partial_no_value"
                    elif ex_out == "readiness_only":
                        succ_no_val[arch] = 0
                        self.adjust_archetype(arch, 0.02)
                        t["last_outcome"] = "execution_readiness_only"
                    elif ex_out == "failed":
                        succ_no_val[arch] = 0
                        self.adjust_archetype(arch, -0.06)
                        t["last_outcome"] = "execution_failed"
                    else:
                        succ_no_val[arch] = 0
                        self.adjust_archetype(arch, 0.0)
                        t["last_outcome"] = "strong_success" if useful else "ok"
                elif exec_stage and ex_ready and not ex_att:
                    self.adjust_archetype(arch, 0.0)
                    streak[arch] = 0
                    t["last_outcome"] = "execution_ready_no_attempt"
                elif adv:
                    streak[arch] = 0
                    if not op_ready:
                        adv_not_ready[arch] = int(adv_not_ready.get(arch, 0) or 0) + 1
                    else:
                        adv_not_ready[arch] = 0
                    mild = min(0.06, int(adv_not_ready.get(arch, 0) or 0) * 0.012)
                    if op_ready:
                        if useful:
                            adj_a = 0.055 if ex_ready else 0.05
                        else:
                            adj_a = 0.028
                        if cycle_best_choice_verified is not None:
                            if vv and cbv:
                                adj_a += 0.012
                            elif vv and not cbv:
                                adj_a -= 0.024 if coc == "high" else (0.014 if coc == "medium" else 0.008)
                            elif not vv and not cbv:
                                adj_a -= 0.045 if coc == "high" else 0.028
                        self.adjust_archetype(arch, adj_a)
                        t["last_outcome"] = "strong_success" if useful else "ok"
                    else:
                        if useful:
                            adj_b = 0.022 - mild
                        else:
                            adj_b = 0.01 - mild
                        if cycle_best_choice_verified is not None and not cbv:
                            adj_b -= 0.02 if coc == "high" else 0.012
                        self.adjust_archetype(arch, adj_b)
                        t["last_outcome"] = "strong_success" if useful else "ok"
                else:
                    n = int(streak.get(arch, 0) or 0) + 1
                    streak[arch] = n
                    adv_not_ready[arch] = 0
                    extra = min(0.12, n * 0.03)
                    self.adjust_archetype(arch, -0.03 - extra)
                    t["last_outcome"] = "strong_non_advancing" if useful else "ok"
                    uns = self._data.setdefault("archetype_useful_nonadv_streak", {})
                    if useful and arch in USEFUL_NONADV_SUPPRESSION_ARCHETYPES:
                        uns[arch] = int(uns.get(arch, 0) or 0) + 1
                        if uns[arch] >= 3:
                            self._data.setdefault("archetype_suppress_until", {})[arch] = time.time() + 900.0
                            self.adjust_archetype(arch, -0.28)
                            logger.warning(
                                "[SelfTask] Archetype suppression 900s arch=%s useful_nonadv_streak=%s "
                                "(heavy downrank pending queue)",
                                arch,
                                uns[arch],
                            )
                    elif arch in USEFUL_NONADV_SUPPRESSION_ARCHETYPES:
                        uns[arch] = 0
            else:
                t["last_outcome"] = "failed"
                self.adjust_archetype(arch, -0.05)
                adv_not_ready[arch] = 0
        pf_suf = 0.0
        if pbs is not None and tier != "failed" and success:
            if pbs >= 0.8 and vv and cbv:
                pf_suf = 0.018
            elif pbs >= 0.65 and vv and cbv:
                pf_suf = 0.008
            elif pbs < 0.38:
                pf_suf = -0.036 if (not vv or not cbv) else -0.022
            elif pbs < 0.55:
                pf_suf = -0.017 if (vv and cbv) else -0.024
        if pf_suf != 0:
            self.adjust_archetype(arch, pf_suf)
        self._save()
        logger.info(
            "[SelfTask] finished %s tier=%s success=%s useful=%s adv=%s op_ready=%s arch=%s",
            task_id,
            tier,
            success,
            useful,
            adv,
            op_ready,
            arch,
        )
        try:
            from .mission_autonomy import record_self_task_artifact_outcome

            record_self_task_artifact_outcome(
                task=t,
                success=success,
                useful=useful,
                archetype=arch,
                execution_artifact=execution_artifact,
                objective_advanced=adv,
            )
        except Exception as _e_ma:
            logger.debug("[MissionDirector] self_task artifact hook: %s", _e_ma)

    def release_stale_in_progress(self, max_sec: float = 1800) -> None:
        now = time.time()
        for t in self._data.get("tasks", []):
            if t.get("status") != "in_progress":
                continue
            try:
                st = t.get("started_at") or ""
                ts = datetime.fromisoformat(st.replace("Z", "+00:00")).timestamp()
            except Exception:
                ts = now
            if now - ts > max_sec:
                t["status"] = "pending"
                t["started_at"] = None
                t["updated_at"] = _iso()
        self._save()
