# project_guardian/multi_api_router.py
# Lightweight API provider selection for orchestration (no heavy deps).

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

_last_quota_related_route_log_ts: float = 0.0
_last_router_reasoning_quota_skip_ts: float = 0.0
_last_reasoning_quota_gate_diag_ts: float = 0.0

if TYPE_CHECKING:
    from .capability_registry import CapabilityRegistry


def select_best_api(
    task_type: str,
    cost_sensitivity: str = "medium",
    quality_requirement: str = "medium",
    *,
    registry: Optional["CapabilityRegistry"] = None,
    reserve_slot: bool = False,
) -> Dict[str, Any]:
    """
    Pick a provider for task_type: embedding | reasoning | simple | chat | unknown.
    Respects missing keys, optional per-cycle budget (reserve_slot), and cooldowns on registry.
    """
    task_type = (task_type or "unknown").lower().strip()
    cost_sensitivity = (cost_sensitivity or "medium").lower()
    quality_requirement = (quality_requirement or "medium").lower()

    from .cloud_api_state import (
        anthropic_key_loaded,
        any_llm_cloud_key_loaded,
        chat_completion_route_reason_code,
        embedding_route_reason_code,
        human_openai_routing_message,
        openrouter_key_loaded,
        openai_usable_for_routing,
        openai_routing_block_reason,
    )

    has_openai = openai_usable_for_routing()
    try:
        from .openai_degraded import openai_insufficient_quota_reasoning_blocked

        if openai_insufficient_quota_reasoning_blocked():
            has_openai = False
    except Exception:
        has_openai = False
    has_anthropic = anthropic_key_loaded()
    has_or_base = openrouter_key_loaded()
    has_or = has_or_base

    rejected: List[Dict[str, str]] = []
    if not has_openai:
        br = openai_routing_block_reason()
        why = human_openai_routing_message(br)
        rejected.append({"provider": "openai", "why": why})
    if not has_anthropic:
        rejected.append({"provider": "anthropic", "why": "Anthropic key not loaded (APIKeyManager / env)"})
    if not has_or_base:
        rejected.append({"provider": "openrouter", "why": "OpenRouter key not loaded (APIKeyManager / env)"})

    def _cooled(name: str) -> bool:
        if registry is None:
            return False
        return registry.is_api_in_cooldown(name)

    if has_openai and _cooled("openai"):
        rejected.append({"provider": "openai", "why": "cooldown after failures"})
        has_openai = False
    if has_anthropic and _cooled("anthropic"):
        rejected.append({"provider": "anthropic", "why": "cooldown after failures"})
        has_anthropic = False
    if has_or and _cooled("openrouter"):
        rejected.append({"provider": "openrouter", "why": "cooldown after failures"})
        has_or = False

    if reserve_slot and registry is not None and not registry.try_consume_api_slot():
        out = {
            "chosen": "local_mistral",
            "reason": "API budget exhausted for this decision cycle; use local Mistral",
            "rejected": rejected + [{"provider": "cloud", "why": "per_cycle_cap"}],
            "alternatives_considered": ["openai", "anthropic", "local_mistral"],
        }
        log_api_routing_decision(task_type, out)
        return out

    # Trivial / cheap → local when quality bar is low
    if task_type == "simple" and cost_sensitivity in ("high", "max") and quality_requirement in ("low", "medium"):
        out = {
            "chosen": "local_mistral",
            "reason": "simple task + cost-sensitive → local",
            "rejected": rejected,
            "alternatives_considered": [p for p in ("openai", "anthropic") if p not in {x["provider"] for x in rejected if x["provider"] in ("openai", "anthropic")}],
        }
        log_api_routing_decision(task_type, out)
        return out

    chosen = None
    reason = ""

    if task_type == "embedding":
        from .cloud_api_state import openai_key_loaded
        from .openai_degraded import skip_openai_embeddings

        oa_embed_ok = bool(openai_key_loaded() and not skip_openai_embeddings())
        if oa_embed_ok:
            chosen, reason = "openai", "embedding workloads → OpenAI when embed route not deferred"
        elif has_anthropic:
            chosen, reason = "anthropic", "fallback: Anthropic when OpenAI unavailable"
        else:
            chosen, reason = "local_mistral", embedding_route_reason_code()

    elif task_type in ("reasoning", "longform", "planning"):
        # Quota block must never be wiped by unrelated import/call failures below.
        quota_reasoning_block_read = False
        try:
            from .openai_degraded import (
                openai_insufficient_quota_block_until_epoch,
                openai_insufficient_quota_reasoning_blocked,
            )

            quota_reasoning_block_read = bool(openai_insufficient_quota_reasoning_blocked())
            if quota_reasoning_block_read:
                global _last_router_reasoning_quota_skip_ts
                now_q = time.time()
                if now_q - _last_router_reasoning_quota_skip_ts >= 45.0:
                    _last_router_reasoning_quota_skip_ts = now_q
                    until = openai_insufficient_quota_block_until_epoch()
                    logger.info(
                        "[APIRouter] reasoning selection skips OpenAI (insufficient_quota block active_until_epoch=%.0f)",
                        until,
                    )
        except Exception:
            pass

        oa_key = False
        oa_short_deg = False
        oa_reasoning_long = False
        try:
            from .cloud_api_state import openai_key_loaded
            from .openai_degraded import (
                is_openai_degraded_active,
                openai_reasoning_long_cooldown_active,
            )

            oa_key = bool(openai_key_loaded())
            oa_short_deg = bool(oa_key and is_openai_degraded_active())
            oa_reasoning_long = bool(oa_key and openai_reasoning_long_cooldown_active())
        except Exception:
            oa_key = oa_short_deg = oa_reasoning_long = False
        oa_quota_hard = bool(oa_key and quota_reasoning_block_read)
        can_pick_openai_reasoning = bool(has_openai and not oa_reasoning_long and not oa_quota_hard)
        if quality_requirement in ("high", "max") and has_anthropic:
            chosen, reason = "anthropic", "high quality reasoning → Anthropic preferred"
        elif oa_quota_hard and has_or:
            chosen, reason = "openrouter", "openai_quota_block_prefer_openrouter"
        elif oa_quota_hard:
            chosen, reason = "local_mistral", "openai_insufficient_quota_blocked"
        elif oa_short_deg and has_or:
            chosen, reason = "openrouter", "openai_recently_degraded_prefer_openrouter"
        elif oa_reasoning_long and has_or:
            chosen, reason = "openrouter", "openai_reasoning_long_cooldown_active"
        elif can_pick_openai_reasoning:
            chosen, reason = "openai", "reasoning/longform → OpenAI"
        elif has_anthropic:
            chosen, reason = "anthropic", "reasoning → Anthropic"
        elif has_or:
            chosen, reason = "openrouter", "openrouter_available_reasoning_only"
        else:
            rc = (
                chat_completion_route_reason_code()
                if any_llm_cloud_key_loaded()
                else "no_cloud_keys_loaded"
            )
            if oa_quota_hard and oa_key:
                rc = "openai_insufficient_quota_blocked"
            elif oa_reasoning_long and oa_key:
                rc = "openai_reasoning_long_cooldown_active"
            chosen, reason = "local_mistral", rc

    elif task_type == "simple":
        if has_openai:
            chosen, reason = "openai", "simple task → cheaper/smaller cloud route (OpenAI default)"
        elif has_anthropic:
            chosen, reason = "anthropic", "simple task → Anthropic (only cloud available)"
        elif has_or:
            chosen, reason = "openrouter", "openrouter_available_reasoning_only"
        else:
            chosen, reason = (
                "local_mistral",
                chat_completion_route_reason_code()
                if any_llm_cloud_key_loaded()
                else "no_cloud_keys_loaded",
            )

    else:
        if has_openai:
            chosen, reason = "openai", "general/default cloud route"
        elif has_anthropic:
            chosen, reason = "anthropic", "general/default cloud route"
        elif has_or:
            chosen, reason = "openrouter", "openrouter_available_reasoning_only"
        else:
            chosen, reason = (
                "local_mistral",
                chat_completion_route_reason_code()
                if any_llm_cloud_key_loaded()
                else "no_cloud_keys_loaded",
            )

    # Defense in depth: never emit reasoning/longform → OpenAI while insufficient_quota block is active.
    if chosen == "openai" and task_type in ("reasoning", "longform", "planning"):
        try:
            from .cloud_api_state import openai_key_loaded, openrouter_key_loaded
            from .openai_degraded import openai_insufficient_quota_reasoning_blocked

            if openai_key_loaded() and openai_insufficient_quota_reasoning_blocked():
                if openrouter_key_loaded():
                    chosen, reason = "openrouter", "openai_quota_block_prefer_openrouter"
                else:
                    chosen, reason = "local_mistral", "openai_insufficient_quota_blocked"
        except Exception:
            pass

    out = {
        "chosen": chosen,
        "reason": reason,
        "rejected": rejected,
        "alternatives_considered": [
            x for x in ("openai", "anthropic", "openrouter", "local_mistral") if x != chosen
        ],
        "task_type": task_type,
    }
    if task_type in ("reasoning", "longform", "planning"):
        global _last_reasoning_quota_gate_diag_ts
        _now_gate = time.time()
        if _now_gate - _last_reasoning_quota_gate_diag_ts >= 90.0:
            _last_reasoning_quota_gate_diag_ts = _now_gate
            try:
                from .openai_degraded import (
                    openai_insufficient_quota_block_until_epoch,
                    openai_insufficient_quota_reasoning_blocked,
                )

                _blocked = openai_insufficient_quota_reasoning_blocked()
                _until = openai_insufficient_quota_block_until_epoch()
                logger.info(
                    "[APIRouter] reasoning_quota_gate block_active=%s block_until_epoch=%.0f chosen=%s reason=%s",
                    _blocked,
                    _until,
                    out.get("chosen"),
                    str(out.get("reason") or "")[:100],
                )
            except Exception:
                pass
    log_api_routing_decision(task_type, out)
    return out


def log_api_routing_decision(task_type: str, decision: Dict[str, Any]) -> None:
    global _last_quota_related_route_log_ts
    try:
        reason_full = str(decision.get("reason") or "")
        chosen = decision.get("chosen")
        rl = reason_full.lower()
        if (
            task_type in ("reasoning", "longform", "planning")
            and chosen != "openai"
            and (
                "quota" in rl
                or "insufficient" in rl
                or "openai_insufficient" in rl
                or "openai_quota_block" in rl
            )
        ):
            try:
                win = float(os.environ.get("ELYSIA_QUOTA_ROUTE_LOG_MIN_SEC", "120"))
            except ValueError:
                win = 120.0
            now = time.time()
            if now - _last_quota_related_route_log_ts < max(30.0, win):
                return
            _last_quota_related_route_log_ts = now
            logger.info(
                "[APIRouter] reasoning openai skipped (quota block): chosen=%s reason=%s",
                chosen,
                reason_full[:180],
            )
            return
        logger.info(
            "[APIRouter] task_type=%s chosen=%s reason=%s unavailable_providers=%s",
            task_type,
            decision.get("chosen"),
            reason_full[:180],
            len(decision.get("rejected") or []),
        )
    except Exception:
        pass


def evaluate_api_vs_local(
    task_description: str,
    *,
    registry: Optional["CapabilityRegistry"] = None,
) -> Dict[str, Any]:
    """
    Heuristic: should a cloud API beat local Mistral for this text?
    Used by orchestration prompts; does not call the network.
    """
    text = (task_description or "").lower()
    trivial = len(text.split()) <= 4 and len(text) < 48
    if trivial:
        return {"use_api": False, "reason": "trivial task — skip API", "task_class": "trivial"}

    if any(
        k in text
        for k in (
            "financial",
            "revenue",
            "income",
            "budget",
            "profit",
            "wallet",
            "invoice",
            "cash flow",
        )
    ):
        r = select_best_api("reasoning", quality_requirement="medium", registry=registry, reserve_slot=False)
        return {
            "use_api": r.get("chosen") not in (None, "local_mistral"),
            "reason": r.get("reason", ""),
            "routing": r,
            "task_class": "financial",
        }
    if any(k in text for k in ("http://", "https://", "website", "web page", "web site", "browser")):
        r = select_best_api("reasoning", quality_requirement="medium", registry=registry, reserve_slot=False)
        return {
            "use_api": r.get("chosen") not in (None, "local_mistral"),
            "reason": r.get("reason", ""),
            "routing": r,
            "task_class": "web",
        }

    if any(k in text for k in ("embed", "embedding", "vector", "semantic")):
        r = select_best_api("embedding", registry=registry, reserve_slot=False)
        return {
            "use_api": r.get("chosen") not in (None, "local_mistral"),
            "reason": r.get("reason", ""),
            "routing": r,
            "task_class": "embedding",
        }
    if any(k in text for k in ("plan", "reason", "prove", "architecture", "long", "essay")):
        r = select_best_api("reasoning", quality_requirement="high", registry=registry, reserve_slot=False)
        return {
            "use_api": r.get("chosen") not in (None, "local_mistral"),
            "reason": r.get("reason", ""),
            "routing": r,
            "task_class": "reasoning",
        }
    r = select_best_api("simple", cost_sensitivity="high", registry=registry, reserve_slot=False)
    return {
        "use_api": r.get("chosen") not in (None, "local_mistral"),
        "reason": r.get("reason", ""),
        "routing": r,
        "task_class": "general",
    }
