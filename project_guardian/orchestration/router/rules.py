# project_guardian/orchestration/router/rules.py
from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..types import RouteDecision, TaskRequest

if TYPE_CHECKING:
    from ..telemetry.sqlite_store import TelemetrySqliteStore
from .task_types import CRITIQUE, TASK_TYPES

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "llm_router.yaml"

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

_DEFAULT_YAML = """
orchestration:
  enabled: true
  sqlite_path: data/orchestration_telemetry.db
defaults:
  pipeline: serial_plan_execute_review
  planner_model: ollama:mistral:7b
  executor_model: ollama:mistral:7b
  reviewer_model: openai:gpt-4.1-mini
routes:
  reasoning:
    pipeline: serial_plan_execute_review
    planner_model: ollama:mistral:7b
    executor_model: openai:gpt-4.1-mini
    reviewer_model: ollama:mistral:7b
  coding:
    pipeline: serial_plan_execute_review
    planner_model: ollama:mistral:7b
    executor_model: openai:gpt-4.1-mini
    reviewer_model: ollama:mistral:7b
  summarization:
    pipeline: serial_plan_execute_review
    planner_model: ollama:mistral:7b
    executor_model: ollama:mistral:7b
    reviewer_model: openai:gpt-4.1-mini
  critique:
    pipeline: parallel_compare_and_judge
    planner_model: ollama:mistral:7b
    fanout_models:
      - ollama:mistral:7b
      - openai:gpt-4.1-mini
    judge_model: openai:gpt-4.1-mini
  memory_compression:
    pipeline: serial_plan_execute_review
    planner_model: ollama:mistral:7b
    executor_model: ollama:mistral:7b
    reviewer_model: openai:gpt-4.1-mini
  tool_selection:
    pipeline: serial_plan_execute_review
    planner_model: ollama:mistral:7b
    executor_model: ollama:mistral:7b
    reviewer_model: openai:gpt-4.1-mini
  bounded_action:
    pipeline: serial_plan_execute_review
    planner_model: ollama:mistral:7b
    executor_model: ollama:mistral:7b
    reviewer_model: openai:gpt-4.1-mini
"""


def _load_yaml() -> Dict[str, Any]:
    if yaml is None:
        logger.warning("PyYAML not installed; using embedded llm_router defaults")
        return {}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning("llm_router.yaml load failed: %s; using embedded defaults", e)
    return yaml.safe_load(_DEFAULT_YAML) or {}


def parse_model_ref(ref: str) -> tuple[str, str]:
    s = (ref or "").strip()
    if not s:
        return "ollama", "mistral:7b"
    if ":" not in s:
        return "ollama", s
    prov, rest = s.split(":", 1)
    prov_l = prov.lower()
    if prov_l in ("ollama", "openai"):
        return prov_l, rest.strip()
    return "ollama", s


def _openai_available() -> bool:
    """OpenAI key present and not in degraded cooldown (same source as multi_api_router)."""
    try:
        from ...cloud_api_state import openai_usable_for_routing

        return openai_usable_for_routing()
    except Exception:
        return False


def _fallback_local(model_ref: str, planner_ref: str) -> str:
    prov, _ = parse_model_ref(model_ref)
    if prov == "openai":
        _, m = parse_model_ref(planner_ref)
        return f"ollama:{m}"
    return model_ref


def _resolve_reviewer(executor: str, reviewer: Optional[str], planner: str) -> Optional[str]:
    """Reviewer must not be the same provider+model as executor; None => deterministic-only review."""
    er = parse_model_ref(executor)
    if not reviewer:
        if er[0] == "openai" and _openai_available():
            return planner
        if er[0] == "ollama" and _openai_available():
            return "openai:gpt-4.1-mini"
        return None
    rr = parse_model_ref(reviewer)
    if rr == er:
        if _openai_available() and er[0] == "ollama":
            return "openai:gpt-4.1-mini"
        if er[0] == "openai":
            return planner if parse_model_ref(planner) != er else None
        return None
    return reviewer


class RulesRouter:
    """YAML rules + light governance metadata; no ML router."""

    def __init__(
        self,
        raw: Optional[Dict[str, Any]] = None,
        telemetry_store: Optional["TelemetrySqliteStore"] = None,
    ) -> None:
        self._raw = raw if raw is not None else _load_yaml()
        if not self._raw and yaml is not None:
            self._raw = yaml.safe_load(_DEFAULT_YAML) or {}
        self._telemetry_store = telemetry_store

    def reload(self) -> None:
        self._raw = _load_yaml()
        if not self._raw and yaml is not None:
            self._raw = yaml.safe_load(_DEFAULT_YAML) or {}

    async def resolve(self, request: TaskRequest) -> RouteDecision:
        orch = (self._raw.get("orchestration") or {}) if isinstance(self._raw, dict) else {}
        if not orch.get("enabled", True):
            from ...ollama_model_config import ollama_provider_ref

            om = ollama_provider_ref()
            return RouteDecision(
                pipeline_id="serial_plan_execute_review",
                planner_model=om,
                executor_model=om,
                reviewer_model=None,
                reason="orchestration_disabled_in_yaml",
            )

        defaults = copy.deepcopy(self._raw.get("defaults") or {})
        routes = self._raw.get("routes") or {}
        meta_pre = request.metadata or {}
        tt = request.task_type if request.task_type in TASK_TYPES else "reasoning"
        if meta_pre.get("prefer_bounded_action") and tt == "reasoning":
            tt = "bounded_action"
        row = copy.deepcopy(routes.get(tt) or {})

        def _merge(key: str) -> Any:
            return row.get(key) if key in row else defaults.get(key)

        from ...ollama_model_config import ollama_provider_ref

        _ollama_default = ollama_provider_ref()

        def _coerce_ollama_ref(ref: Optional[str]) -> str:
            if not ref:
                return _ollama_default
            p, _m = parse_model_ref(ref)
            return _ollama_default if p == "ollama" else ref

        pipeline = _merge("pipeline") or "serial_plan_execute_review"
        planner = _coerce_ollama_ref(_merge("planner_model") or _ollama_default)
        executor = _coerce_ollama_ref(_merge("executor_model") or planner)
        reviewer_raw = _merge("reviewer_model")
        reviewer: Optional[str] = _coerce_ollama_ref(str(reviewer_raw)) if reviewer_raw else None
        fanout = list(row.get("fanout_models") or defaults.get("fanout_models") or [])
        fanout = [_coerce_ollama_ref(x) for x in fanout]
        judge_m = row.get("judge_model") or defaults.get("judge_model")
        if judge_m:
            judge_m = _coerce_ollama_ref(judge_m)

        reasons: List[str] = []

        meta = request.metadata or {}
        hints = meta.get("governance_hints") or []
        if isinstance(hints, str):
            hints = [hints]
        hints_set = {str(h).strip() for h in hints if h}

        high_stakes = bool(meta.get("high_stakes"))
        uncertainty = str((request.context or {}).get("uncertainty_level") or "").lower()

        if tt == CRITIQUE:
            pipeline = "parallel_compare_and_judge"
            reasons.append("task_type_critique")

        if high_stakes or "escalate_reasoning" in hints_set:
            pipeline = "parallel_compare_and_judge"
            reasons.append("governance_escalate_or_high_stakes")

        if uncertainty == "high" and tt == "reasoning":
            pipeline = "parallel_compare_and_judge"
            reasons.append("ambiguous_reasoning_uncertainty_high")

        if "low_confidence_local" in hints_set or "repeated_low_value_local" in hints_set:
            if _openai_available():
                executor = "openai:gpt-4.1-mini"
                reasons.append("governance_cloud_executor")
            else:
                try:
                    from ...cloud_api_state import openai_key_loaded, openai_routing_block_reason

                    br = openai_routing_block_reason()
                    if br == "openai_policy_disabled":
                        reasons.append("governance_openai_policy_skip_cloud_executor")
                    elif br == "openai_insufficient_quota_blocked":
                        reasons.append("governance_openai_insufficient_quota_skip_cloud_executor")
                    elif openai_key_loaded():
                        reasons.append("governance_openai_degraded_skip_cloud_executor")
                    else:
                        reasons.append("governance_hint_no_openai_key")
                except Exception:
                    reasons.append("governance_hint_no_openai_key")

        if pipeline == "parallel_compare_and_judge" and len(fanout) < 2:
            fanout = [_ollama_default, "openai:gpt-4.1-mini"]
            reasons.append("fanout_defaulted")

        if not _openai_available():
            executor = _fallback_local(executor, planner)
            judge_m = None if parse_model_ref(judge_m or "")[0] == "openai" else judge_m
            fanout = [_fallback_local(m, planner) for m in fanout]
            fanout = list(dict.fromkeys(fanout))
            while len(fanout) < 2:
                fanout.append(planner)
            reasons.append("openai_unavailable_local_fallback")

        reviewer = _resolve_reviewer(executor, reviewer, planner)

        reason = "; ".join(reasons) if reasons else "yaml_defaults"
        decision = RouteDecision(
            pipeline_id=pipeline,
            planner_model=planner,
            executor_model=executor,
            reviewer_model=reviewer,
            fanout_models=fanout[:2] if pipeline == "parallel_compare_and_judge" else [],
            judge_model=judge_m if _openai_available() else None,
            reason=reason,
        )
        if self._telemetry_store is not None:
            from .policy import adapt_route_from_telemetry

            decision = await adapt_route_from_telemetry(
                base=decision,
                request=request,
                telemetry=self._telemetry_store,
                effective_task_type=tt,
            )
        return decision
