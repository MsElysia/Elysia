# project_guardian/self_task_portfolio.py
# Rolling portfolio balance across autonomous self-task cycles.

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "self_task_portfolio.json"
DATA_PATH = PROJECT_ROOT / "data" / "self_task_portfolio.json"

DEFAULT_TARGETS: Dict[str, Any] = {
    "window_size": 16,
    "pressure_strength": 0.09,
    "domination_run_penalty": 0.06,
    "soft_targets": {
        "revenue": {"max_share": 0.42, "min_share": 0.0},
        "execution": {"max_share": 0.55, "min_share": 0.1},
        "research": {"max_share": 0.38, "min_share": 0.0},
        "operator_support": {"max_share": 0.5, "min_share": 0.08},
        "maintenance": {"max_share": 0.32, "min_share": 0.0},
        "capability_tooling": {"max_share": 0.4, "min_share": 0.0},
        "learning": {"max_share": 0.35, "min_share": 0.0},
        "internal": {"max_share": 0.55, "min_share": 0.0},
    },
    "combined_min": {"execution_operator": 0.14},
}


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def infer_portfolio_category(archetype: str, task: Optional[Dict[str, Any]] = None) -> str:
    a = (archetype or "").lower()
    tk = str((task or {}).get("task_kind") or "")
    vt = str((task or {}).get("value_tier") or "")

    if any(
        x in a
        for x in (
            "learning_recent_digest",
            "learning_operator_digest",
            "summarize_recent_learning",
        )
    ):
        return "learning"
    if "harvest" in a or "research_brief" in a or "readonly_snapshot" in a:
        return "research"
    if "execute_best" in a or "generate_execution_plan" in a or ("rank_top" in a and "opportunit" in a):
        return "execution"
    if "revenue" in a or "shortlist" in a or "offer_ideas" in a or "monetization" in a or "finance_revenue" in a:
        return "revenue"
    if "diagnostic" in a or "idle_pulse" in a or "validate_tool" in a or "repair_tool" in a or "repair_registry" in a:
        return "maintenance"
    if "capability_gap" in a or "tool_registry" in a or "underused" in a or "compare_underused" in a:
        return "capability_tooling"
    if "operator" in a or vt == "high" and tk in ("generation", "execution"):
        return "operator_support"
    return "internal"


def _load_config() -> Dict[str, Any]:
    cfg = dict(DEFAULT_TARGETS)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            if isinstance(user, dict):
                cfg.update({k: v for k, v in user.items() if k in cfg or k == "soft_targets" or k == "combined_min"})
                if isinstance(user.get("soft_targets"), dict):
                    cfg["soft_targets"] = {**cfg["soft_targets"], **user["soft_targets"]}
                if isinstance(user.get("combined_min"), dict):
                    cfg["combined_min"] = {**cfg.get("combined_min", {}), **user["combined_min"]}
        except Exception as e:
            logger.debug("portfolio config load: %s", e)
    return cfg


class PortfolioCycleTracker:
    """Rolling window of completed self-task cycles + soft target pressure."""

    def __init__(self, data_path: Optional[Path] = None) -> None:
        self.data_path = Path(data_path) if data_path else DATA_PATH
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self.cfg = _load_config()
        self._data = self._load_data()

    def _load_data(self) -> Dict[str, Any]:
        if not self.data_path.exists():
            return {"events": [], "updated_at": _iso()}
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.debug("portfolio data load: %s", e)
            return {"events": [], "updated_at": _iso()}

    def _save_data(self) -> None:
        self._data["updated_at"] = _iso()
        try:
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug("portfolio data save: %s", e)

    def _window_events(self) -> List[Dict[str, Any]]:
        n = max(4, min(32, int(self.cfg.get("window_size", 16) or 16)))
        ev = self._data.get("events") or []
        if not isinstance(ev, list):
            return []
        return ev[-n:]

    def window_stats(self) -> Dict[str, Any]:
        """Counts, share, averages per category for current window."""
        ev = self._window_events()
        if not ev:
            return {"total": 0, "by_category": {}}
        cats = [str(e.get("category") or "internal") for e in ev]
        c = Counter(cats)
        total = len(cats)
        by_cat: Dict[str, Any] = {}
        for cat, cnt in c.items():
            rows = [e for e in ev if str(e.get("category")) == cat]
            vs = [float(e.get("value_score") or 0) for e in rows]
            cs = [float(e.get("cycle_choice_score") or 0) for e in rows]
            by_cat[cat] = {
                "count": cnt,
                "share": round(cnt / total, 4),
                "avg_value_score": round(sum(vs) / max(1, len(vs)), 4),
                "avg_cycle_choice_score": round(sum(cs) / max(1, len(cs)), 4),
            }
        return {"total": total, "by_category": by_cat}

    def sort_pressure(self, task: Dict[str, Any]) -> float:
        """
        Add to queue sort_key (higher = worse / later). Uses window *before* next completion.
        """
        cat = infer_portfolio_category(str(task.get("archetype") or ""), task)
        stats = self.window_stats()
        total = int(stats.get("total") or 0)
        if total < 3:
            return 0.0
        by_cat = stats.get("by_category") or {}
        row = by_cat.get(cat) or {"share": 0.0}
        share = float(row.get("share") or 0.0)
        st = (self.cfg.get("soft_targets") or {}).get(cat) or {}
        mx = float(st.get("max_share") or 1.0)
        mn = float(st.get("min_share") or 0.0)
        ps = float(self.cfg.get("pressure_strength") or 0.09)

        pressure = 0.0
        if mx < 1.0 and share > mx * 0.85:
            excess = max(0.0, share - mx)
            pressure += min(0.22, ps + excess * 1.8)
        if mn > 0 and share < mn * 0.65:
            pressure -= min(0.14, ps * 0.9 + (mn - share))

        # Revenue ideation heavy without execution: nudge revenue archetypes down
        exec_share = float((by_cat.get("execution") or {}).get("share") or 0.0)
        rev_share = float((by_cat.get("revenue") or {}).get("share") or 0.0)
        if cat == "revenue" and rev_share > 0.28 and exec_share < 0.08:
            pressure += ps * 0.75

        # Boost execution when underrepresented
        if cat == "execution" and exec_share < float((self.cfg.get("soft_targets") or {}).get("execution", {}).get("min_share", 0.1) or 0.1) * 0.7:
            pressure -= ps * 0.85

        # Maintenance: extra downweight if dominating
        if cat == "maintenance":
            mshare = float((by_cat.get("maintenance") or {}).get("share") or 0.0)
            if mshare > 0.38:
                pressure += ps * 1.1

        return max(-0.18, min(0.28, pressure))

    def record_and_score_event(
        self,
        *,
        archetype: str,
        task: Optional[Dict[str, Any]],
        success: bool,
        tier: str,
        value_verified: bool,
        value_score: float,
        cycle_best_choice_verified: bool,
        cycle_choice_score: float,
        blocker_removed: bool,
    ) -> Dict[str, Any]:
        """Append one cycle, return portfolio_balance_score + reason + category_stats."""
        cat = infer_portfolio_category(archetype, task)
        ev = self._data.setdefault("events", [])
        if not isinstance(ev, list):
            self._data["events"] = []
            ev = self._data["events"]

        event = {
            "category": cat,
            "archetype": archetype[:120],
            "success": bool(success),
            "tier": tier,
            "value_verified": bool(value_verified),
            "value_score": float(value_score),
            "cycle_best_choice_verified": bool(cycle_best_choice_verified),
            "cycle_choice_score": float(cycle_choice_score),
            "blocker_removed": bool(blocker_removed),
            "ts": _iso(),
        }
        ev.append(event)
        n = max(4, min(48, int(self.cfg.get("window_size", 16) or 16) * 2))
        if len(ev) > n:
            self._data["events"] = ev[-n:]
        self._save_data()

        score, reason = self._compute_balance_score(cat, event)
        return {
            "portfolio_balance_score": score,
            "portfolio_reason": reason,
            "portfolio_category": cat,
            "portfolio_window_stats": self.window_stats(),
        }

    def _compute_balance_score(self, event_cat: str, last_event: Dict[str, Any]) -> Tuple[float, str]:
        stats = self.window_stats()
        by_cat = stats.get("by_category") or {}
        total = max(1, int(stats.get("total") or 1))
        soft = self.cfg.get("soft_targets") or {}
        combined_min = float((self.cfg.get("combined_min") or {}).get("execution_operator") or 0.14)

        row = by_cat.get(event_cat) or {}
        share = float(row.get("share") or 0.0)

        st = soft.get(event_cat) or {}
        mx = float(st.get("max_share") or 1.0)
        mn = float(st.get("min_share") or 0.0)

        base = 0.82
        reasons: List[str] = []

        if mx < 1.0 and share > mx:
            over = share - mx
            base -= min(0.5, 0.35 + over * 1.4)
            reasons.append(f"over_target_share_{event_cat}")
        elif mx < 1.0 and share > mx * 0.92:
            base -= 0.08
            reasons.append(f"near_max_{event_cat}")

        if mn > 0 and share < mn and last_event.get("value_verified"):
            base += min(0.12, (mn - share) * 0.6)
            reasons.append("helping_underrepresented_category")

        exec_s = float((by_cat.get("execution") or {}).get("share") or 0.0)
        op_s = float((by_cat.get("operator_support") or {}).get("share") or 0.0)
        if exec_s + op_s < combined_min and event_cat in ("execution", "operator_support"):
            base += 0.1
            reasons.append("supports_execution_operator_floor")

        if event_cat == "maintenance" and last_event.get("blocker_removed"):
            base += 0.12
            reasons.append("maintenance_unblocked_work")

        if event_cat == "maintenance" and not last_event.get("blocker_removed"):
            mshare = float((by_cat.get("maintenance") or {}).get("share") or 0.0)
            if mshare > 0.36:
                base -= 0.14
                reasons.append("maintenance_cluster_without_unblock")

        # Repeated same category run
        evs = self._window_events()
        if len(evs) >= 4:
            tail = [str(e.get("category")) for e in evs[-4:]]
            if len(set(tail)) == 1 and tail[0] == event_cat and event_cat in ("revenue", "maintenance", "learning"):
                pen = float(self.cfg.get("domination_run_penalty") or 0.06)
                base -= pen
                reasons.append(f"four_cycle_domination_{event_cat}")

        # Revenue without execution path mix
        rev_s = float((by_cat.get("revenue") or {}).get("share") or 0.0)
        if event_cat == "revenue" and rev_s > 0.35 and exec_s < 0.09:
            base -= 0.1
            reasons.append("revenue_ideation_without_execution_mix")

        base = max(0.12, min(1.0, base))
        reason = "; ".join(reasons) if reasons else "within_soft_portfolio_targets"
        return round(base, 4), reason[:400]
