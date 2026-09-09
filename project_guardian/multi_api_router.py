# project_guardian/multi_api_router.py
# Lightweight API provider selection for orchestration (no heavy deps).

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

# Routing intent (operator chat vs autonomy vs context pipeline) lives across multi_api_router,
# unified_llm_route.decide_chat_llm_backend, planner_readiness gates, and context_pipeline/runner.
# Provider set here is OpenAI, Anthropic, OpenRouter, and local Ollama only. Cohere / HuggingFace /
# Replicate keys are loaded for AskAI, income launcher, tool discovery, etc., but are not candidates
# in select_best_api today (no unified chat completion adapter path for them in this router).
# - Paid-first (use subscribed APIs): set ``ELYSIA_USE_CLOUD_LLM_FIRST=1`` (alias:
#   ``ELYSIA_MAXIMIZE_PAID_API_USAGE=1``). This disables local-first routing so reasoning/simple
#   prefer cloud when keys allow (OpenAI default, then Anthropic/OpenRouter per rules below).
# - Time-bounded burn-down (no provider billing API): ``ELYSIA_CLOUD_CREDIT_USE_DEADLINE=YYYY-MM-DD``
#   or ISO datetime — until that instant (UTC, end-of-day for date-only), cloud-first routing is
#   treated as enabled so prepaid / expiring credits get used. Remove or set a past date to stop.
# - Free-first (minimize paid): config ``prefer_local_reasoning_when_planner_ready`` (default true)
#   and env ``ELYSIA_MAXIMIZE_FREE_TOKENS`` route reasoning/longform/planning to local Ollama when
#   planner readiness is ``ready`` and local inference is staged usable. **This is the opposite of
#   "maximize API key usage"** — it saves cloud quota.
# - OpenRouter-before-OpenAI (optional): ``ELYSIA_PREFER_OPENROUTER_LLM=1`` picks OpenRouter for
#   reasoning/longform/planning and simple when an OpenRouter key is loaded (still respects cooldowns).
# - require_autonomy_safe=True: clamp to autonomy-safe providers (planner_readiness).
# - Context pipeline may skip local packets under memory_pressure_high and use online structured models
#   independently — that path does not pass through this module's reasoning preference.

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MISTRAL_DECIDER_PATH = _PROJECT_ROOT / "config" / "mistral_decider.json"

_last_quota_related_route_log_ts: float = 0.0
_last_router_reasoning_quota_skip_ts: float = 0.0
_last_reasoning_quota_gate_diag_ts: float = 0.0

_LOCAL_ONLY_TASK_TYPES = frozenset({
    "context_structuring",
    "context_compression",
    "prompt_packet",
})
_REASONING_TASK_TYPES = frozenset({
    "reasoning",
    "longform",
    "planning",
})

if TYPE_CHECKING:
    from .capability_registry import CapabilityRegistry


def _maximize_free_tokens_enabled() -> bool:
    """
    Umbrella env: treat as prefer-local-when-ready for reasoning and (when configured) simple routes.

    ELYSIA_MAXIMIZE_FREE_TOKENS=1/true enables the same preference as turning on
    prefer_local_reasoning_when_planner_ready without editing JSON.
    """
    raw = (os.environ.get("ELYSIA_MAXIMIZE_FREE_TOKENS") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _is_trivial_chat_preview(text: str) -> bool:
    """Short generic chat (same rule as :func:`evaluate_api_vs_local` trivial branch)."""
    t = (text or "").lower().strip()
    if not t:
        return False
    return len(t.split()) <= 4 and len(t) < 48


def _use_cloud_llm_first_enabled() -> bool:
    """
    Operator opt-in: prefer cloud LLMs (paid/subscribed keys) over local Ollama when the router allows.

    Disables local-first reasoning and local-first simple routing, and aligns context_pipeline
    paid-reservation (see :func:`pipeline_maximize_free_tokens`).

    ELYSIA_USE_CLOUD_LLM_FIRST=1 or ELYSIA_MAXIMIZE_PAID_API_USAGE=1 (aliases).

    ELYSIA_CLOUD_CREDIT_USE_DEADLINE: optional ISO date ``YYYY-MM-DD`` or datetime (``...Z`` or offset).
    While wall-clock is before that deadline (inclusive end-of-day for date-only), behaves like
    cloud-first so prepaid credits are consumed. Does not read balances from provider APIs.
    """
    for name in ("ELYSIA_USE_CLOUD_LLM_FIRST", "ELYSIA_MAXIMIZE_PAID_API_USAGE", "ELYSIA_CLOUD_FIRST_LLM"):
        raw = (os.environ.get(name) or "").strip().lower()
        if raw in ("1", "true", "yes", "on"):
            return True
    if _cloud_credit_use_deadline_active():
        return True
    return False


def _cloud_credit_use_deadline_active() -> bool:
    """True when ELYSIA_CLOUD_CREDIT_USE_DEADLINE is set and now is before that deadline (UTC)."""
    raw = (os.environ.get("ELYSIA_CLOUD_CREDIT_USE_DEADLINE") or "").strip()
    if not raw:
        return False
    try:
        from datetime import datetime, timezone

        s = raw.replace("Z", "+00:00")
        # Date-only: burn through end of that calendar day in UTC.
        if len(s) == 10 and s[4:5] == "-" and s[7:8] == "-":
            dt = datetime.fromisoformat(s + "T23:59:59+00:00")
        else:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(timezone.utc)
        return datetime.now(timezone.utc) <= dt
    except Exception:
        logger.warning("[APIRouter] ELYSIA_CLOUD_CREDIT_USE_DEADLINE invalid or unparsable: %r", raw[:120])
        return False


def pipeline_maximize_free_tokens(cfg: Optional[Dict[str, Any]] = None) -> bool:
    """
    Context pipeline online-reasoning gate: return True to apply reserve-paid / local-first thresholds
    (``ELYSIA_MAXIMIZE_FREE_TOKENS`` or ``cfg['maximize_free_tokens']``).

    Returns False when cloud-first env is set (``ELYSIA_USE_CLOUD_LLM_FIRST`` and aliases), matching
    :func:`_use_cloud_llm_first_enabled` / chat routing.
    """
    if _use_cloud_llm_first_enabled():
        return False
    merged = cfg if isinstance(cfg, dict) else {}
    if _maximize_free_tokens_enabled():
        return True
    return bool(merged.get("maximize_free_tokens", False))


def _prefer_openrouter_llm_enabled() -> bool:
    """
    Prefer OpenRouter over OpenAI for routed simple/reasoning/longform/planning when OpenRouter is loaded.

    Does not override Anthropic high-quality paths, quota/degraded OpenRouter fallbacks, or local-first
    when that remains enabled.

    ELYSIA_PREFER_OPENROUTER_LLM=1 or ELYSIA_OPENROUTER_FIRST_LLM=1.
    """
    for name in ("ELYSIA_PREFER_OPENROUTER_LLM", "ELYSIA_OPENROUTER_FIRST_LLM"):
        raw = (os.environ.get(name) or "").strip().lower()
        if raw in ("1", "true", "yes", "on"):
            return True
    return False


def _prefer_local_reasoning_when_planner_ready_enabled() -> bool:
    """
    Prefer Ollama for reasoning/longform when planner gates say local is usable.

    Precedence: ELYSIA_USE_CLOUD_LLM_FIRST (disables local-first) → ELYSIA_MAXIMIZE_FREE_TOKENS →
    ELYSIA_PREFER_LOCAL_REASONING_WHEN_READY → config/mistral_decider.json
    ``prefer_local_reasoning_when_planner_ready`` (default true in repo config).
    """
    if _use_cloud_llm_first_enabled():
        return False
    if _maximize_free_tokens_enabled():
        return True
    raw = (os.environ.get("ELYSIA_PREFER_LOCAL_REASONING_WHEN_READY") or "").strip()
    if raw:
        return raw.lower() in ("1", "true", "yes", "on")
    try:
        if _MISTRAL_DECIDER_PATH.exists():
            with open(_MISTRAL_DECIDER_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if isinstance(cfg, dict):
                # Default True when key absent (maximize free local inference).
                if "prefer_local_reasoning_when_planner_ready" not in cfg:
                    return True
                return bool(cfg.get("prefer_local_reasoning_when_planner_ready"))
    except Exception:
        pass
    return False


def _prefer_local_simple_when_planner_ready_enabled() -> bool:
    """
    Optional: route task_type=simple to local Ollama when staged usable (saves paid mini/chat tokens).

    ELYSIA_MAXIMIZE_FREE_TOKENS enables this together with local readiness checks.
    ELYSIA_PREFER_LOCAL_SIMPLE_WHEN_READY overrides config ``prefer_local_simple_when_planner_ready``.
    """
    if _use_cloud_llm_first_enabled():
        return False
    if _maximize_free_tokens_enabled():
        return True
    raw = (os.environ.get("ELYSIA_PREFER_LOCAL_SIMPLE_WHEN_READY") or "").strip()
    if raw:
        return raw.lower() in ("1", "true", "yes", "on")
    try:
        if _MISTRAL_DECIDER_PATH.exists():
            with open(_MISTRAL_DECIDER_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if isinstance(cfg, dict):
                return bool(cfg.get("prefer_local_simple_when_planner_ready", False))
    except Exception:
        pass
    return False


def _prefer_local_simple_route_active() -> bool:
    """True when simple→local is enabled and local Ollama is staged usable."""
    if not _prefer_local_simple_when_planner_ready_enabled():
        return False
    try:
        from .planner_readiness import compute_readiness_label, local_planner_reasoning_truth_snapshot

        if compute_readiness_label() != "ready":
            return False
        snap = local_planner_reasoning_truth_snapshot()
        return bool(snap.get("usable"))
    except Exception:
        return False


def _prefer_local_reasoning_route_active() -> bool:
    """True when opt-in is on, planner label is ready, and local Ollama is staged usable."""
    if not _prefer_local_reasoning_when_planner_ready_enabled():
        return False
    try:
        from .planner_readiness import compute_readiness_label, local_planner_reasoning_truth_snapshot

        if compute_readiness_label() != "ready":
            return False
        snap = local_planner_reasoning_truth_snapshot()
        return bool(snap.get("usable"))
    except Exception:
        return False


def _normalize_api_router_task_type(task_type: str) -> str:
    """Map call-site aliases onto the canonical provider router task types."""
    raw = (task_type or "unknown").lower().strip().replace("-", "_")
    if raw in ("prompt_packet", "context_packet", "context_structuring", "context_pipeline"):
        return "prompt_packet"
    if raw in ("context_compression", "memory_condense", "compress_with_llm"):
        return "context_compression"
    if raw in ("planning", "decide_next_action", "suggest_learning_targets"):
        return "planning"
    if raw in ("reasoning", "analysis", "architecture"):
        return "reasoning"
    if raw in ("longform", "essay", "report"):
        return "longform"
    if raw in ("simple", "chat", "conversation", "unified_chat", "elysia_cloud_fallback"):
        return "simple"
    if raw in ("embedding", "embed", "semantic", "vector"):
        return "embedding"
    return raw or "unknown"


def select_best_api(
    task_type: str,
    cost_sensitivity: str = "medium",
    quality_requirement: str = "medium",
    *,
    registry: Optional["CapabilityRegistry"] = None,
    reserve_slot: bool = False,
    log_decision: bool = True,
    record_meter: bool = True,
    require_autonomy_safe: bool = False,
    prompt_preview: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Pick a provider for task_type: embedding | reasoning | simple | chat | unknown.
    Respects missing keys, optional per-cycle budget (reserve_slot), and cooldowns on registry.

    Callers may pass task aliases (for example ``memory_condense`` or ``decide_next_action``);
    these are normalized to the router's canonical task classes before provider selection.

    ``prompt_preview`` (optional): when ``task_type`` resolves to ``simple`` and this text matches
    the trivial short-chat rule, prefer ``local_mistral`` unless cloud-first or OpenRouter-first
    env is set (aligns unified chat with prior ``evaluate_api_vs_local`` savings, in-router).

    When ``require_autonomy_safe`` is True for reasoning/longform/planning, the chosen provider is
    clamped to autonomy-safe capability paths (see planner_readiness.clamp_api_router_choice_to_autonomy_safe).

    Local-first reasoning: when ``prefer_local_reasoning_when_planner_ready`` is enabled (default in
    config; see ``ELYSIA_MAXIMIZE_FREE_TOKENS``, ``ELYSIA_PREFER_LOCAL_REASONING_WHEN_READY``),
    reasoning/longform/planning may pick ``local_mistral`` instead of OpenAI if planner readiness is
    ``ready`` and local Ollama is staged usable. Set ``ELYSIA_USE_CLOUD_LLM_FIRST=1``, set
    prefer_local_reasoning_when_planner_ready=false in mistral_decider.json, or unset local Ollama
    to restore cloud-first reasoning when keys allow.
    """
    task_type = _normalize_api_router_task_type(task_type)
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

    has_openai = openai_usable_for_routing(allow_quota_reprobe=True)
    try:
        from .openai_degraded import openai_insufficient_quota_reasoning_blocked

        if openai_insufficient_quota_reasoning_blocked(allow_reprobe=True):
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
        if log_decision:
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

    elif task_type in _REASONING_TASK_TYPES:
        # Quota block must never be wiped by unrelated import/call failures below.
        quota_reasoning_block_read = False
        try:
            from .openai_degraded import (
                openai_insufficient_quota_block_until_epoch,
                openai_insufficient_quota_reasoning_blocked,
            )

            quota_reasoning_block_read = bool(openai_insufficient_quota_reasoning_blocked(allow_reprobe=True))
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
        elif can_pick_openai_reasoning and _prefer_local_reasoning_route_active():
            chosen, reason = "local_mistral", "prefer_local_reasoning_when_planner_ready"
        elif can_pick_openai_reasoning:
            if _prefer_openrouter_llm_enabled() and has_or:
                chosen, reason = "openrouter", "reasoning/longform → OpenRouter (ELYSIA_PREFER_OPENROUTER_LLM)"
            else:
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

    elif task_type in _LOCAL_ONLY_TASK_TYPES:
        out = {
            "chosen": "local_mistral",
            "reason": "structured compression / prompt packet -> local Ollama (compress; no raw upstream)",
            "rejected": rejected,
            "alternatives_considered": ["openai", "anthropic", "openrouter"],
            "task_type": task_type,
        }
        if log_decision:
            log_api_routing_decision(task_type, out)
        return out

    elif task_type == "simple":
        # Cost-sensitive default: prefer local for simple — but only after paid-first / OpenRouter-first
        # overrides. Previously this ran before the simple branch, so capability_registry's
        # cost_sensitivity="high" snapshot always skipped OpenRouter and ELYSIA_USE_CLOUD_LLM_FIRST.
        if (
            cost_sensitivity in ("high", "max")
            and quality_requirement in ("low", "medium")
            and not _use_cloud_llm_first_enabled()
            and not (_prefer_openrouter_llm_enabled() and has_or)
        ):
            out = {
                "chosen": "local_mistral",
                "reason": "simple task + cost-sensitive → local",
                "rejected": rejected,
                "alternatives_considered": [
                    p
                    for p in ("openai", "anthropic", "openrouter")
                    if p not in {x["provider"] for x in rejected if x["provider"] in ("openai", "anthropic", "openrouter")}
                ],
            }
            if log_decision:
                log_api_routing_decision(task_type, out)
            return out

        pv = (prompt_preview or "").strip()
        if (
            pv
            and _is_trivial_chat_preview(pv)
            and not _use_cloud_llm_first_enabled()
            and not _prefer_openrouter_llm_enabled()
        ):
            chosen, reason = "local_mistral", "simple trivial prompt → local (router; free-first)"
        elif _prefer_local_simple_route_active():
            chosen, reason = (
                "local_mistral",
                "simple → local (free-first: prefer_local_simple / ELYSIA_MAXIMIZE_FREE_TOKENS)",
            )
        elif _prefer_openrouter_llm_enabled() and has_or:
            chosen, reason = "openrouter", "simple task → OpenRouter (ELYSIA_PREFER_OPENROUTER_LLM)"
        elif has_openai:
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
        if _prefer_openrouter_llm_enabled() and has_or:
            chosen, reason = "openrouter", "general/default → OpenRouter (ELYSIA_PREFER_OPENROUTER_LLM)"
        elif has_openai:
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
    if chosen == "openai" and task_type in _REASONING_TASK_TYPES:
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

    if require_autonomy_safe and task_type in _REASONING_TASK_TYPES:
        try:
            from .planner_readiness import clamp_api_router_choice_to_autonomy_safe

            _router_chosen = chosen
            chosen, reason = clamp_api_router_choice_to_autonomy_safe(
                chosen, reason, router_chosen=_router_chosen
            )
        except Exception as e:
            logger.debug("select_best_api require_autonomy_safe: %s", e)

    out = {
        "chosen": chosen,
        "reason": reason,
        "rejected": rejected,
        "alternatives_considered": [
            x for x in ("openai", "anthropic", "openrouter", "local_mistral") if x != chosen
        ],
        "task_type": task_type,
    }
    if task_type in _REASONING_TASK_TYPES:
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
    if log_decision:
        log_api_routing_decision(task_type, out)
    if record_meter:
        try:
            from .api_usage_meter import record_router_choice

            record_router_choice(str(out.get("chosen") or ""), task_type=task_type)
        except Exception:
            pass
    return out


def reasoning_provider_label_from_api_router(*, registry: Optional["CapabilityRegistry"] = None) -> str:
    """
    Same provider choice as select_best_api('reasoning', quality_requirement='medium', …) for
    runtime snapshots (no extra routing log noise).
    """
    r = select_best_api(
        "reasoning",
        quality_requirement="medium",
        registry=registry,
        reserve_slot=False,
        log_decision=False,
        record_meter=False,
        require_autonomy_safe=False,
    )
    raw = str(r.get("chosen") or "").strip().lower() or "local_mistral"
    if raw == "local_mistral":
        return "local"
    if raw in ("openai", "openrouter", "anthropic"):
        return raw
    return "local"


def log_api_routing_decision(task_type: str, decision: Dict[str, Any]) -> None:
    global _last_quota_related_route_log_ts
    try:
        reason_full = str(decision.get("reason") or "")
        chosen = decision.get("chosen")
        rl = reason_full.lower()
        if (
            task_type in _REASONING_TASK_TYPES
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

    if any(k in text for k in ("prompt packet", "context pipeline", "distilled context", "ingestion_normalizer")):
        r = select_best_api("context_structuring", registry=registry, reserve_slot=False, record_meter=False)
        return {
            "use_api": False,
            "reason": "context pipeline compression is local-first",
            "routing": r,
            "task_class": "context_structuring",
        }

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
        r = select_best_api(
            "reasoning", quality_requirement="medium", registry=registry, reserve_slot=False, record_meter=False
        )
        return {
            "use_api": r.get("chosen") not in (None, "local_mistral"),
            "reason": r.get("reason", ""),
            "routing": r,
            "task_class": "financial",
        }
    if any(k in text for k in ("http://", "https://", "website", "web page", "web site", "browser")):
        r = select_best_api(
            "reasoning", quality_requirement="medium", registry=registry, reserve_slot=False, record_meter=False
        )
        return {
            "use_api": r.get("chosen") not in (None, "local_mistral"),
            "reason": r.get("reason", ""),
            "routing": r,
            "task_class": "web",
        }

    if any(k in text for k in ("embed", "embedding", "vector", "semantic")):
        r = select_best_api("embedding", registry=registry, reserve_slot=False, record_meter=False)
        return {
            "use_api": r.get("chosen") not in (None, "local_mistral"),
            "reason": r.get("reason", ""),
            "routing": r,
            "task_class": "embedding",
        }
    if any(k in text for k in ("plan", "reason", "prove", "architecture", "long", "essay")):
        r = select_best_api(
            "reasoning", quality_requirement="high", registry=registry, reserve_slot=False, record_meter=False
        )
        return {
            "use_api": r.get("chosen") not in (None, "local_mistral"),
            "reason": r.get("reason", ""),
            "routing": r,
            "task_class": "reasoning",
        }
    r = select_best_api("simple", cost_sensitivity="high", registry=registry, reserve_slot=False, record_meter=False)
    return {
        "use_api": r.get("chosen") not in (None, "local_mistral"),
        "reason": r.get("reason", ""),
        "routing": r,
        "task_class": "general",
    }
