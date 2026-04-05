# project_guardian/self_task_objectives.py
# Lightweight objectives linking self-tasks into coherent progress.

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = PROJECT_ROOT / "data" / "self_task_objectives.json"


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ObjectiveStore:
    """Persistent objectives: active chains for self-tasking."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self.path = Path(storage_path) if storage_path else DEFAULT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"objectives": [], "updated_at": _iso()}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.debug("objective_store load: %s", e)
            return {"objectives": [], "updated_at": _iso()}

    def _save(self) -> None:
        self._data["updated_at"] = _iso()
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug("objective_store save: %s", e)

    def list_all(self) -> List[Dict[str, Any]]:
        return list(self._data.get("objectives", []))

    def get(self, objective_id: str) -> Optional[Dict[str, Any]]:
        for o in self._data.get("objectives", []):
            if o.get("objective_id") == objective_id:
                return o
        return None

    def is_active(self, objective_id: Optional[str]) -> bool:
        if not objective_id:
            return False
        o = self.get(objective_id)
        return bool(o and str(o.get("status", "")).lower() == "active")

    def ensure_minimum_active(self, guardian: Any) -> str:
        """At least one active objective; sync planner if possible; else default."""
        self.sync_from_longterm_planner(guardian)
        for o in self._data.get("objectives", []):
            if str(o.get("status", "")).lower() == "active":
                return str(o["objective_id"])
        oid = f"obj_default_{uuid.uuid4().hex[:10]}"
        self._data.setdefault("objectives", []).append(
            {
                "objective_id": oid,
                "title": "Operator value & actionable outputs",
                "goal": "Produce revenue ideas, research briefs, improvement proposals, and capability insights for the operator.",
                "status": "active",
                "priority": 0.62,
                "progress": 0.0,
                "related_tasks": [],
                "source": "auto_default",
                "objective_type": "operator_support",
                "artifact_count": 0,
                "operator_ready": False,
                "execution_ready": False,
                "created_at": _iso(),
            }
        )
        self._save()
        logger.info("[Objectives] created default active objective %s", oid)
        return oid

    def sync_from_longterm_planner(self, guardian: Any) -> None:
        mods = getattr(guardian, "_modules", None) or {}
        planner = mods.get("longterm_planner")
        if not planner:
            return
        try:
            active_list = []
            if hasattr(planner, "list_active_objectives"):
                active_list = planner.list_active_objectives() or []
            elif hasattr(planner, "objectives"):
                raw = planner.objectives
                seq = list(raw.values()) if isinstance(raw, dict) else (list(raw) if isinstance(raw, list) else [])
                for o in seq:
                    st = getattr(o, "status", "") if not isinstance(o, dict) else o.get("status", "")
                    if "active" in str(st).lower():
                        active_list.append(o)
            by_id = {str(o.get("objective_id", o)): o for o in self._data.get("objectives", []) if o.get("source") == "longterm_planner"}
            for obj in active_list[:5]:
                if isinstance(obj, dict):
                    oid = str(obj.get("objective_id") or obj.get("id") or uuid.uuid4().hex[:12])
                    title = str(obj.get("name", "Planner objective"))[:200]
                    goal = str(obj.get("description", title))[:500]
                else:
                    oid = str(getattr(obj, "objective_id", None) or getattr(obj, "id", "") or uuid.uuid4().hex[:12])
                    title = str(getattr(obj, "name", "Planner objective"))[:200]
                    goal = title
                if not oid:
                    continue
                if oid in by_id:
                    continue
                self._data.setdefault("objectives", []).append(
                    {
                        "objective_id": oid,
                        "title": title,
                        "goal": goal,
                        "status": "active",
                        "priority": 0.65,
                        "progress": 0.0,
                        "related_tasks": [],
                        "source": "longterm_planner",
                        "objective_type": "research_and_intelligence",
                        "artifact_count": 0,
                        "operator_ready": False,
                        "execution_ready": False,
                        "created_at": _iso(),
                    }
                )
                logger.info("[Objectives] synced planner objective %s", oid)
            self._save()
        except Exception as e:
            logger.debug("sync_from_longterm_planner: %s", e)

    def create_lightweight(
        self,
        *,
        title: str,
        goal: str,
        priority: float = 0.5,
        objective_type: str = "maintenance",
    ) -> str:
        oid = f"obj_{uuid.uuid4().hex[:12]}"
        self._data.setdefault("objectives", []).append(
            {
                "objective_id": oid,
                "title": (title or "Objective")[:200],
                "goal": (goal or "")[:800],
                "status": "active",
                "priority": max(0.0, min(1.0, float(priority))),
                "progress": 0.0,
                "related_tasks": [],
                "source": "self_task_generator",
                "objective_type": objective_type,
                "artifact_count": 0,
                "operator_ready": False,
                "execution_ready": False,
                "created_at": _iso(),
            }
        )
        self._save()
        return oid

    def ensure_typed_objective(
        self,
        objective_type: str,
        *,
        title: str,
        goal: str,
        priority: float = 0.64,
    ) -> str:
        """Reuse an active objective of this type, or create one."""
        for o in self._data.get("objectives", []):
            if str(o.get("status", "")).lower() == "active" and o.get("objective_type") == objective_type:
                return str(o["objective_id"])
        return self.create_lightweight(
            title=title, goal=goal, priority=priority, objective_type=objective_type
        )

    def link_task(self, objective_id: str, task_id: str) -> None:
        o = self.get(objective_id)
        if not o:
            return
        rt = list(o.get("related_tasks") or [])
        if task_id not in rt:
            rt.append(task_id)
            o["related_tasks"] = rt[-80:]
        o["updated_at"] = _iso()
        self._save()

    def _maybe_complete_objective(self, o: Dict[str, Any]) -> None:
        if str(o.get("status", "")).lower() != "active":
            return
        op_r = bool(o.get("operator_ready"))
        val_ok = bool(o.get("value_verified"))
        ex_done = bool(o.get("execution_completed"))
        ot = str(o.get("objective_type") or "").lower()
        maint = "maintenance" in ot or ot in ("tooling", "system_improvement")
        blocker_gone = bool(o.get("blocker_removed"))
        if maint and blocker_gone:
            o["status"] = "completed"
            o["completed_at"] = _iso()
            return
        if op_r and ex_done and val_ok:
            o["status"] = "completed"
            o["completed_at"] = _iso()

    def apply_post_execution_objective(
        self,
        objective_id: Optional[str],
        *,
        archetype: str,
        exec_result: Dict[str, Any],
        value_result: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not objective_id:
            return
        o = self.get(objective_id)
        if not o or str(o.get("status", "")).lower() != "active":
            return
        vr = value_result or {}
        le = {
            "execution_attempted": exec_result.get("execution_attempted"),
            "execution_outcome": exec_result.get("execution_outcome"),
            "execution_reason": (str(exec_result.get("execution_reason") or ""))[:500],
            "execution_artifact": exec_result.get("execution_artifact"),
            "execution_followup_needed": exec_result.get("execution_followup_needed"),
            "value_verified": bool(vr.get("value_verified")),
            "value_score": vr.get("value_score"),
            "value_reason": (str(vr.get("value_reason") or ""))[:500],
            "value_type": str(vr.get("value_type") or "none"),
            "archetype": archetype,
            "updated_at": _iso(),
        }
        o["last_execution"] = le
        o["value_verified"] = bool(vr.get("value_verified"))
        o["last_value"] = {
            "value_score": vr.get("value_score"),
            "value_reason": (str(vr.get("value_reason") or ""))[:500],
            "value_type": str(vr.get("value_type") or "none"),
            "updated_at": _iso(),
        }
        if vr.get("blocker_removed"):
            o["blocker_removed"] = True
        if str(exec_result.get("execution_outcome") or "").lower() == "succeeded":
            cur = float(o.get("progress", 0.0) or 0.0)
            o["progress"] = min(1.0, cur + 0.12)
            o["execution_completed"] = not bool(exec_result.get("execution_followup_needed"))
        o["updated_at"] = _iso()
        self._maybe_complete_objective(o)
        self._save()

    def record_strong_artifact(self, objective_id: Optional[str]) -> None:
        if not objective_id:
            return
        o = self.get(objective_id)
        if not o or str(o.get("status", "")).lower() != "active":
            return
        o["artifact_count"] = int(o.get("artifact_count", 0) or 0) + 1
        o["updated_at"] = _iso()
        self._maybe_complete_objective(o)
        self._save()

    def bump_progress(self, objective_id: Optional[str], delta: float, *, real_outcome: bool) -> None:
        if not objective_id or not real_outcome:
            return
        o = self.get(objective_id)
        if not o or str(o.get("status", "")).lower() != "active":
            return
        cur = float(o.get("progress", 0.0) or 0.0)
        o["progress"] = max(0.0, min(1.0, cur + max(0.0, float(delta))))
        o["updated_at"] = _iso()
        self._maybe_complete_objective(o)
        self._save()

    def sort_key_boost(self, task: Dict[str, Any]) -> float:
        """Lower is better for min-heap style sort (we negate in queue)."""
        oid = task.get("objective_id")
        bonus = 0.0
        if oid and self.is_active(oid):
            o = self.get(oid) or {}
            bonus -= 0.25 * float(o.get("priority", 0.5) or 0.5)
            bonus -= 0.35 * float(o.get("progress", 0.0) or 0.0)
            rt = len(o.get("related_tasks") or [])
            if rt >= 2:
                bonus -= 0.12 * min(3, rt)
            ot = str(o.get("objective_type") or "")
            otl = ot.lower()
            if o.get("execution_ready"):
                bonus -= 0.2
            elif o.get("operator_ready"):
                bonus -= 0.12
            if "maintenance" in otl or otl == "tooling":
                bonus += 0.06 if not o.get("blocker_removed") else -0.06
            if ot in ("revenue_generation", "research_and_intelligence", "operator_support"):
                bonus -= 0.12
            if ot == "system_improvement":
                bonus -= 0.08
        else:
            bonus += 0.18
        vt = str(task.get("value_tier") or "internal")
        if vt == "high":
            bonus -= 0.22
        elif vt == "internal":
            bonus += 0.04
        if task.get("unlocks_task_kind"):
            bonus -= 0.14
        elif vt == "internal":
            pass
        tk = task.get("task_kind") or "snapshot"
        if tk in ("snapshot", "diagnostic", "monitoring"):
            bonus += 0.12
            if vt == "internal" and not (task.get("unlocks_task_kind") or task.get("unlocks_archetype")):
                bonus += 0.1
        if tk in ("transform", "generation", "improvement", "execution"):
            bonus -= 0.1
        if task.get("produces_artifact") or task.get("output_contract_id"):
            bonus -= 0.08
        arch_l = str(task.get("archetype") or "").lower()
        if "diagnostic" in arch_l or arch_l.endswith("_diagnostic_retry"):
            bonus += 0.12
        if arch_l.startswith("validate_") or arch_l.endswith("_snapshot") or "idle_pulse" in arch_l:
            if not task.get("unlocks_task_kind"):
                bonus += 0.06
        return bonus
