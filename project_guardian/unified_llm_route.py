# project_guardian/unified_llm_route.py
# Single routing decision for chat-style LLM calls: local Ollama vs cloud APIs.
#
# Primary backend comes from multi_api_router.select_best_api (same flags as ELYSIA_USE_CLOUD_LLM_FIRST,
# ELYSIA_MAXIMIZE_FREE_TOKENS, ELYSIA_PREFER_OPENROUTER_LLM, etc.). We do not apply a second
# evaluate_api_vs_local downgrade after the router — that previously forced Ollama on short prompts
# even when the router had already chosen a cloud provider.

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .module_prompt_registry import (
    structured_messages_for_llm_call,
    structured_reply_text,
    validate_module_llm_output,
)

logger = logging.getLogger(__name__)

_last_unified_quota_skip_log_ts: float = 0.0

DECIDER_PATH = Path(__file__).resolve().parent.parent / "config" / "mistral_decider.json"

# Task line must stay aligned with MistralEngine.complete_chat (local Ollama path).
_UNIFIED_CHAT_TASK_TEXT = (
    "Unified chat completion: respond as the assistant to the conversation thread."
)

# Log-only model labels for cloud paths (match elysia.py transport defaults; not used for routing).
_CLOUD_MODEL_LOG_OPENAI = "gpt-4o-mini"
_CLOUD_MODEL_LOG_OPENROUTER = "openai/gpt-3.5-turbo"

# Public aliases (elysia fallback + tests; keep in sync with MistralEngine.complete_chat).
UNIFIED_CHAT_PROMPT_TASK_TEXT = _UNIFIED_CHAT_TASK_TEXT
CLOUD_MODEL_LOG_OPENAI = _CLOUD_MODEL_LOG_OPENAI
CLOUD_MODEL_LOG_OPENROUTER = _CLOUD_MODEL_LOG_OPENROUTER

_LOCAL_ONLY_ROUTER_TASK_TYPES = frozenset({
    "context_structuring",
    "context_compression",
    "prompt_packet",
})
_REASONING_ROUTER_TASK_TYPES = frozenset({
    "reasoning",
    "planning",
    "longform",
})

# Self-build RAG skip reasons logged at DEBUG only (high-volume / expected paths).
_SELFBUILD_RAG_SKIP_LOG_DEBUG = frozenset({
    "disabled",
    "route_task_ineligible",
    "structured_skip_preamble",
    "task_type_excluded",
    "query_too_short",
})

_CHAT_TOOL_FIRST_EXECUTE_DENYLIST = frozenset({
    # Generic chat transport, not a domain tool. Executing it before unified chat
    # re-enters this router and can recurse through capability selection.
    "elysia_builtin_llm",
})


def _normalize_chat_router_task_type(
    user_text: str,
    *,
    task_type: Optional[str] = None,
) -> str:
    """Resolve a router task type from explicit prompt metadata before falling back to chat heuristics."""
    raw = str(task_type or "").strip().lower().replace("-", "_")
    if raw:
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
    return "reasoning" if len((user_text or "").strip()) > 600 else "simple"


def _cloud_fallback_allowed_for_router_task(task_type: str) -> bool:
    """Structured local-only tasks must not fail over to cloud transports."""
    return task_type not in _LOCAL_ONLY_ROUTER_TASK_TYPES


def _chat_backend_currently_allowed(
    backend: str,
    *,
    task_type: str,
    registry: Any = None,
) -> bool:
    """Current runtime gate for fallback ordering so blocked providers are not retried later in the same call."""
    if backend == "ollama":
        return True
    if backend == "openrouter":
        try:
            from .cloud_api_state import openrouter_key_loaded

            if not openrouter_key_loaded():
                return False
        except Exception:
            return False
        return not (
            registry is not None
            and hasattr(registry, "is_api_in_cooldown")
            and registry.is_api_in_cooldown("openrouter")
        )
    if backend == "openai":
        try:
            from .cloud_api_state import openai_usable_for_routing

            if not openai_usable_for_routing(allow_quota_reprobe=True):
                return False
        except Exception:
            return False
        if registry is not None and hasattr(registry, "is_api_in_cooldown") and registry.is_api_in_cooldown("openai"):
            return False
        if task_type in _REASONING_ROUTER_TASK_TYPES:
            try:
                from .openai_degraded import (
                    openai_insufficient_quota_reasoning_blocked,
                    openai_reasoning_long_cooldown_active,
                )

                if (
                    openai_insufficient_quota_reasoning_blocked(allow_reprobe=True)
                    or openai_reasoning_long_cooldown_active()
                ):
                    return False
            except Exception:
                return False
        return True
    return False


def _load_decider_cfg() -> Dict[str, Any]:
    if not DECIDER_PATH.exists():
        return {}
    try:
        with open(DECIDER_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _format_capability_payload(body: Any) -> str:
    if body is None:
        return "(no payload)"
    if isinstance(body, (dict, list)):
        try:
            return json.dumps(body, ensure_ascii=False, indent=2)[:6000]
        except Exception:
            return str(body)[:6000]
    return str(body)[:6000]


def build_chat_capability_preamble(user_text: str, guardian: Any) -> str:
    """If registry ranks internal capabilities above generic chat, prepend guidance."""
    if not guardian or not hasattr(guardian, "_orchestration_registry"):
        return ""
    try:
        reg = guardian._orchestration_registry
        snap = reg.refresh_if_due(guardian, min_interval_sec=15.0)
        ranked = reg.get_relevant_capabilities(user_text[:1500], guardian, snapshot=snap, top_k=8)
        if not ranked:
            return ""
        top = ranked[0]
        ms = float(top.get("match_score") or 0)
        if ms < 1.8:
            return ""
        lines = [
            "[Orchestration] Before answering, the system recommends considering these capabilities "
            f"(do not claim you executed them; user may trigger via Elysia autonomy/UI):",
            f"- {top.get('name')} ({top.get('type')}): {str(top.get('description') or '')[:180]}",
            f"- suggested autonomy action: {top.get('suggested_action', '')}",
        ]
        if len(ranked) > 1:
            t2 = ranked[1]
            lines.append(f"- also: {t2.get('name')} → {t2.get('suggested_action', '')}")
        lines.append(
            "Then answer the user helpfully. If the task clearly requires a tool/module not available in chat, say so briefly."
        )
        return "\n".join(lines)
    except Exception as e:
        logger.debug("chat capability preamble: %s", e)
        return ""


def _finalize_autonomy_safe_route_meta(meta: Dict[str, Any]) -> None:
    """Ensure autonomy-safe completions expose consistent observability keys (no routing logic)."""
    if not meta.get("autonomy_reasoning_safe_required"):
        return
    meta["autonomy_reasoning_actual_backend"] = meta.get("backend")


def try_chat_capability_execute(user_text: str, guardian: Any) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    High-confidence match → run execute_capability before any LLM.
    Returns (reply, meta_extra) or None to fall back to LLM.
    """
    if not guardian or not hasattr(guardian, "_orchestration_registry"):
        return None
    cfg = _load_decider_cfg()
    if not cfg.get("chat_tool_first_capability", True):
        return None
    thr = float(cfg.get("chat_capability_execute_threshold", 3.0))
    reg = guardian._orchestration_registry
    try:
        snap = reg.refresh_if_due(guardian, min_interval_sec=15.0)
        ranked = reg.get_relevant_capabilities(user_text[:1500], guardian, snapshot=snap, top_k=8)
        if not ranked:
            return None
        top = ranked[0]
        ms = float(top.get("match_score") or 0)
        if ms < thr:
            return None
        kind = top.get("type")
        if kind not in ("tool", "module"):
            return None
        if kind == "tool" and str(top.get("name") or "").strip().lower() in _CHAT_TOOL_FIRST_EXECUTE_DENYLIST:
            return None
        if top.get("health") == "no_key":
            return None
        from .capability_execution import execute_capability_kind, infer_chat_capability_input

        inp = infer_chat_capability_input(user_text, top)
        t1 = time.perf_counter()
        ex = execute_capability_kind(guardian, str(kind), str(top.get("name") or ""), inp)
        lat = round((time.perf_counter() - t1) * 1000, 2)
        ok = bool(ex.get("success"))
        cid = f"chat_exec:{kind}:{top.get('name')}"
        try:
            reg.log_capability_usage(
                task=user_text[:500],
                capability_id=cid,
                capability_type="chat_capability",
                success=ok,
                quality=0.88 if ok else 0.22,
                latency_ms=lat,
                extra={"match_score": ms, "error": ex.get("error")},
            )
        except Exception as le:
            logger.debug("chat capability usage log: %s", le)
        logger.info(
            "[UnifiedLLM] chat_capability_execute kind=%s name=%s success=%s match_score=%.2f latency_ms=%.1f",
            kind,
            top.get("name"),
            ok,
            ms,
            lat,
        )
        if not ok:
            return None
        reply = (
            f"[Capability executed: {top.get('name')} ({kind})]\n"
            f"{_format_capability_payload(ex.get('result'))}"
        )
        return reply, {
            "chat_capability": top.get("name"),
            "chat_capability_kind": kind,
            "exec_latency_ms": lat,
            "match_score": ms,
        }
    except Exception as e:
        logger.debug("try_chat_capability_execute: %s", e)
        return None


def decide_chat_llm_backend(
    user_text: str,
    *,
    registry: Any = None,
    require_autonomy_safe: bool = False,
    task_type: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Returns (backend, reason) where backend is:
    openai | openrouter | ollama
    All chat completions should consult this before calling a provider.

    ``task_type`` can provide an explicit structured workload hint (for example memory condensation
    or planning) so short helper prompts do not get misrouted as generic chat.

    When ``require_autonomy_safe`` is True, reasoning/simple routing consults select_best_api with
    autonomy-safe clamping for internal/autonomy-originated calls.

    The API router is the single source of truth for cloud vs local; there is no post-router
    ``evaluate_api_vs_local`` downgrade (short prompts still use whatever ``select_best_api`` returns).
    """
    from .cloud_api_state import (
        any_llm_cloud_key_loaded,
        chat_completion_route_reason_code,
        openai_key_loaded,
        openai_usable_for_routing,
        openrouter_key_loaded,
    )
    from .multi_api_router import select_best_api

    text = (user_text or "").strip()
    task_kind = _normalize_chat_router_task_type(text, task_type=task_type)
    if task_kind in _LOCAL_ONLY_ROUTER_TASK_TYPES:
        return "ollama", f"{task_kind}_local_only"

    has_openai_key = openai_key_loaded()
    has_openai = openai_usable_for_routing(allow_quota_reprobe=True)
    has_or = openrouter_key_loaded()

    if registry is not None and hasattr(registry, "is_api_in_cooldown"):
        if registry.is_api_in_cooldown("openai"):
            has_openai = False
        if registry.is_api_in_cooldown("openrouter"):
            has_or = False

    try:
        from .openai_degraded import openai_insufficient_quota_reasoning_blocked

        _oa_quota_reasoning = bool(openai_insufficient_quota_reasoning_blocked(allow_reprobe=True))
    except Exception:
        _oa_quota_reasoning = True
    # insufficient_quota block must disable OpenAI for all chat lengths (usable() should too; this is defense in depth).
    if _oa_quota_reasoning:
        has_openai = False

    r = select_best_api(
        task_kind,
        registry=registry,
        reserve_slot=False,
        log_decision=not require_autonomy_safe,
        require_autonomy_safe=require_autonomy_safe,
        prompt_preview=text[:2000],
    )
    chosen = r.get("chosen") or "local_mistral"
    reason_from_router = str(r.get("reason") or "")
    rl = reason_from_router.lower()
    if chosen == "local_mistral" and (
        "insufficient_quota" in rl or "openai_insufficient" in rl or "quota_block" in rl
    ):
        has_openai = False

    if chosen == "local_mistral":
        return "ollama", str(r.get("reason") or "api_router_local")[:220]

    if chosen == "openrouter" and has_or:
        return "openrouter", str(r.get("reason") or "openrouter_available_reasoning_only")

    if chosen in ("openai", "anthropic") and has_openai:
        return "openai", str(r.get("reason") or "cloud routing")
    if chosen == "anthropic" and not has_openai and has_or:
        return "openrouter", "anthropic preferred but using OpenRouter"
    if has_openai:
        return "openai", str(r.get("reason") or "cloud default")
    if has_or:
        return "openrouter", str(r.get("reason") or "openrouter_available_openai_blocked")
    if any_llm_cloud_key_loaded():
        return "ollama", chat_completion_route_reason_code()
    return "ollama", "no_cloud_keys_loaded"


def compute_unified_chat_provider_order(
    route_task_type: str,
    primary: str,
    *,
    registry: Any = None,
    require_autonomy_safe_reasoning: bool = False,
    log_quota_skip: bool = False,
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Same try-order as :func:`unified_chat_completion` (Ollama vs cloud fallbacks).

    Used by the Control Panel routing matrix and kept in sync with the live path.
    """
    order: List[str] = []
    seen = set()

    def _add(b: str) -> None:
        if b not in seen:
            order.append(b)
            seen.add(b)

    extras: Dict[str, Any] = {
        "cloud_fallback_allowed": _cloud_fallback_allowed_for_router_task(route_task_type),
        "fallback_restricted_to_local": False,
    }
    if not extras["cloud_fallback_allowed"]:
        _add("ollama")
        if primary != "ollama":
            extras["fallback_restricted_to_local"] = True
    else:
        _add(primary)
        if require_autonomy_safe_reasoning:
            from .planner_readiness import autonomy_safe_cloud_backend_order

            for fb in autonomy_safe_cloud_backend_order():
                if _chat_backend_currently_allowed(fb, task_type=route_task_type, registry=registry):
                    _add(fb)
            _add("ollama")
        else:
            for fb in ("openai", "openrouter", "ollama"):
                if _chat_backend_currently_allowed(fb, task_type=route_task_type, registry=registry):
                    _add(fb)

    task_kind = route_task_type
    try:
        from .openai_degraded import (
            openai_insufficient_quota_reasoning_blocked,
            openai_reasoning_long_cooldown_active,
        )

        if task_kind in _REASONING_ROUTER_TASK_TYPES and openai_reasoning_long_cooldown_active():
            order = [x for x in order if x != "openai"]
        if task_kind in _REASONING_ROUTER_TASK_TYPES and openai_insufficient_quota_reasoning_blocked():
            global _last_unified_quota_skip_log_ts
            had_openai = "openai" in order
            order = [x for x in order if x != "openai"]
            if had_openai and log_quota_skip:
                try:
                    win = float(os.environ.get("ELYSIA_QUOTA_ROUTE_LOG_MIN_SEC", "120"))
                except ValueError:
                    win = 120.0
                now = time.time()
                if now - _last_unified_quota_skip_log_ts >= max(30.0, win):
                    _last_unified_quota_skip_log_ts = now
                    logger.info(
                        "[UnifiedLLM] openai omitted from provider order (insufficient_quota reasoning block active)"
                    )
    except Exception:
        pass

    return order, extras


def snapshot_unified_chat_provider_order(
    *,
    user_text: str,
    task_type: Optional[str] = None,
    registry: Any = None,
    require_autonomy_safe_reasoning: bool = False,
    log_quota_skip: bool = False,
) -> Dict[str, Any]:
    """One routing snapshot: normalized task class, primary pick, gated try-order, per-backend gates."""
    route_task_type = _normalize_chat_router_task_type(user_text, task_type=task_type)
    primary, reason = decide_chat_llm_backend(
        user_text,
        registry=registry,
        require_autonomy_safe=require_autonomy_safe_reasoning,
        task_type=task_type,
    )
    order, extras = compute_unified_chat_provider_order(
        route_task_type,
        primary,
        registry=registry,
        require_autonomy_safe_reasoning=require_autonomy_safe_reasoning,
        log_quota_skip=log_quota_skip,
    )
    gates = {
        "ollama": _chat_backend_currently_allowed("ollama", task_type=route_task_type, registry=registry),
        "openai": _chat_backend_currently_allowed("openai", task_type=route_task_type, registry=registry),
        "openrouter": _chat_backend_currently_allowed("openrouter", task_type=route_task_type, registry=registry),
    }
    out: Dict[str, Any] = {
        "route_task_type": route_task_type,
        "primary": primary,
        "primary_reason": reason,
        "try_order": order,
        "backend_gates": gates,
    }
    out.update(extras)
    return out


def unified_chat_completion(
    *,
    messages: List[Dict[str, str]],
    max_tokens: int,
    guardian: Optional[Any],
    cloud_openai_call: Callable[[List[Dict[str, str]], int], Tuple[str, str]],
    cloud_openrouter_call: Callable[[List[Dict[str, str]], int], Tuple[str, str]],
    mistral_model: Optional[str] = None,
    skip_capability_preamble: bool = False,
    module_name: str,
    agent_name: Optional[str] = None,
    prompt_extra: Optional[Dict[str, Any]] = None,
    require_autonomy_safe_reasoning: bool = False,
    structured_role: Optional[str] = None,
) -> Tuple[str, str, Dict[str, Any]]:
    """
    Run one chat completion with unified backend selection + optional capability preamble + usage log hook data.
    Returns (reply, error, meta) meta includes backend, reason, latency_ms.

    module_name / agent_name select the Guardian prompt stack for every backend (Ollama, OpenAI, OpenRouter).

    When ``prompt_extra`` is set (e.g. memory condensation), it may include ``task_text``, ``context``,
    ``output_schema``, and ``task_type`` for :func:`prepare_prompted_messages`. Structured tasks should
    pass ``prompt_extra`` and ``skip_capability_preamble=True`` so chat capability routing does not hijack the turn.

    ``require_autonomy_safe_reasoning`` restricts reasoning routing to autonomy-safe cloud providers
    (internal/autonomy-originated workloads only; default off for operator chat).
    """
    from .llm.prompted_call import (
        log_prompted_call,
        prepare_prompted_messages,
        prompt_payload_fingerprint,
        require_prompt_profile,
    )

    _mod, _ag, _ = require_prompt_profile(
        module_name, agent_name, caller="unified_chat_completion", allow_legacy=False
    )

    user_text = ""
    for m in reversed(messages):
        if (m.get("role") or "").lower() == "user":
            user_text = str(m.get("content") or "")[:8000]
            break

    pe = prompt_extra or {}
    route_task_type = _normalize_chat_router_task_type(user_text, task_type=pe.get("task_type"))
    llm_call_id = f"ullm_{uuid.uuid4().hex[:12]}"

    # Orchestration capability registry (ranked tools/modules for chat), not the prompt registry.
    orch_registry = getattr(guardian, "_orchestration_registry", None) if guardian else None
    decider_cfg = _load_decider_cfg()
    if orch_registry is not None and hasattr(orch_registry, "reset_chat_api_budget"):
        orch_registry.reset_chat_api_budget(int(decider_cfg.get("chat_max_api_calls_per_turn", 8)))

    t0 = time.perf_counter()
    meta: Dict[str, Any] = {
        "backend": "unknown",
        "reason": "",
        "latency_ms": 0.0,
        "llm_call_id": llm_call_id,
        "route_task_type": route_task_type,
    }

    # Structured prompt_extra paths must not run chat tool-first capability execute.
    if prompt_extra is None and guardian and decider_cfg.get("chat_tool_first_capability", True):
        hit = try_chat_capability_execute(user_text, guardian)
        if hit:
            reply, extra = hit
            meta.update(extra)
            meta["backend"] = "capability"
            meta["reason"] = "chat_tool_first_execute"
            meta["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            logger.info(
                "[UnifiedLLM] call_id=%s backend=capability latency_ms=%.1f",
                llm_call_id,
                meta["latency_ms"],
            )
            try:
                from .llm_trace_jsonl import append_unified_chat_trace

                append_unified_chat_trace(
                    reply=reply,
                    err="",
                    meta=meta,
                    module_name=_mod,
                    agent_name=_ag,
                    route_task_type=route_task_type,
                    require_autonomy_safe_reasoning=require_autonomy_safe_reasoning,
                    user_text=user_text,
                )
            except Exception:
                pass
            return reply, "", meta

    msgs = list(messages)
    _structured_ctx: Optional[Tuple[str, Optional[str], Optional[str]]] = None
    if structured_role:
        msgs, triple = structured_messages_for_llm_call(msgs, pe, structured_role)
        if not triple[0]:
            return "", "structured_role_parse_error", {
                "backend": "none",
                "reason": "invalid_structured_role",
                "llm_call_id": llm_call_id,
                "route_task_type": route_task_type,
            }
        _structured_ctx = triple
    if guardian and not skip_capability_preamble:
        try:
            chat_pre = bool(decider_cfg.get("chat_capability_preamble", True))
            if chat_pre:
                pre = build_chat_capability_preamble(user_text, guardian)
                if pre:
                    msgs = [{"role": "system", "content": pre}] + msgs
        except Exception:
            pass
    if guardian and not skip_capability_preamble:
        try:
            pipe_pre = build_chat_context_pipeline_prefix(guardian, user_text)
            if pipe_pre:
                msgs = [{"role": "system", "content": pipe_pre}] + msgs
        except Exception:
            pass

    if guardian:
        try:
            from .local_ai_selfbuild_retrieve import maybe_prepend_selfbuild_rag_system_message

            msgs, sb_rag_meta = maybe_prepend_selfbuild_rag_system_message(
                msgs,
                user_text=user_text,
                guardian=guardian,
                require_autonomy_safe_reasoning=require_autonomy_safe_reasoning,
                route_task_type=route_task_type,
                skip_capability_preamble=skip_capability_preamble,
                prompt_extra=prompt_extra,
            )
            meta["selfbuild_rag"] = sb_rag_meta
            sk = str(sb_rag_meta.get("skip") or "")
            if sb_rag_meta.get("applied"):
                logger.info(
                    "[UnifiedLLM] selfbuild_rag applied chunks=%s max_sim=%s embed_ms=%s total_ms=%s",
                    sb_rag_meta.get("chunks"),
                    sb_rag_meta.get("max_sim"),
                    sb_rag_meta.get("embed_ms"),
                    sb_rag_meta.get("total_ms"),
                )
            elif sk in _SELFBUILD_RAG_SKIP_LOG_DEBUG:
                logger.debug(
                    "[UnifiedLLM] selfbuild_rag skipped skip=%s route_task=%s",
                    sk,
                    route_task_type,
                )
            elif sk:
                logger.info(
                    "[UnifiedLLM] selfbuild_rag skipped skip=%s route_task=%s",
                    sk,
                    route_task_type,
                )
        except Exception as e:
            logger.debug("[UnifiedLLM] selfbuild_rag_prefix: %s", e)

    primary, reason = decide_chat_llm_backend(
        user_text,
        registry=orch_registry,
        require_autonomy_safe=require_autonomy_safe_reasoning,
        task_type=route_task_type,
    )
    meta["backend"] = primary
    meta["reason"] = reason
    meta["router_primary"] = primary
    meta["router_reason"] = reason
    if require_autonomy_safe_reasoning:
        try:
            from .planner_readiness import select_autonomy_safe_reasoning_route

            _ar = select_autonomy_safe_reasoning_route()
            meta["autonomy_reasoning_provider"] = _ar.get("provider")
            meta["autonomy_reasoning_safe_required"] = True
            meta["autonomy_reasoning_block_reason"] = _ar.get("block_reason")
        except Exception:
            meta["autonomy_reasoning_safe_required"] = True

    order, _order_extras = compute_unified_chat_provider_order(
        route_task_type,
        primary,
        registry=orch_registry,
        require_autonomy_safe_reasoning=require_autonomy_safe_reasoning,
        log_quota_skip=True,
    )
    if _order_extras.get("fallback_restricted_to_local"):
        meta["fallback_restricted_to_local"] = True
    meta["provider_order"] = list(order)

    reply, err = "", ""

    _log_task_type = str(pe.get("task_type") or "unified_chat")

    def _resolved_task_text() -> str:
        if pe.get("task_text") is not None:
            return str(pe["task_text"])
        return _UNIFIED_CHAT_TASK_TEXT

    # One prep for all cloud attempts: same msgs as Ollama sees (capability preamble + thread), plus prompt stack.
    _cloud_prep_cache: Optional[Dict[str, Any]] = None

    def _cloud_prompt_bundle() -> Dict[str, Any]:
        nonlocal _cloud_prep_cache
        if _cloud_prep_cache is None:
            _cloud_prep_cache = prepare_prompted_messages(
                list(msgs),
                module_name=_mod,
                agent_name=_ag,
                task_text=_resolved_task_text(),
                context=pe.get("context"),
                output_schema=pe.get("output_schema"),
                caller="unified_chat_completion.cloud",
            )
        return _cloud_prep_cache

    def _run_ollama(attempt_index: int) -> Tuple[str, str]:
        from .mistral_engine import MistralEngine
        from .ollama_model_config import get_canonical_ollama_model

        m = (mistral_model or "").strip() or get_canonical_ollama_model(log_once=False)
        eng = MistralEngine(model=m)
        try:
            return (
                eng.complete_chat(
                    msgs,
                    max_tokens=max_tokens,
                    module_name=_mod,
                    agent_name=_ag,
                    task_text=pe.get("task_text"),
                    context=pe.get("context"),
                    output_schema=pe.get("output_schema"),
                    task_type=_log_task_type,
                    call_id=llm_call_id,
                    route_task_type=route_task_type,
                    attempt_index=attempt_index,
                    fallback_from=primary if "ollama" != primary else None,
                ),
                "",
            )
        except Exception as e:
            return "", str(e)

    for attempt_index, b in enumerate(order, start=1):
        attempted = list(meta.get("attempted_backends") or [])
        attempted.append(b)
        meta["attempted_backends"] = attempted
        if b in ("openai", "openrouter"):
            if orch_registry is not None and not orch_registry.try_consume_chat_api_slot():
                logger.info("[UnifiedLLM] call_id=%s skipping %s (chat API budget exhausted)", llm_call_id, b)
                meta["chat_api_budget_exhausted"] = True
                continue
            try:
                from .unified_api_budget import can_spend, effective_cloud_chat_preflight, enabled as _ub_on

                if _ub_on() and not can_spend(effective_cloud_chat_preflight(b, max_tokens)):
                    logger.info(
                        "[UnifiedBudget] skipping %s — period token-equivalent budget exhausted (preflight)",
                        b,
                    )
                    meta["unified_budget_exhausted"] = True
                    continue
            except Exception:
                pass
        try:
            if b == "ollama":
                reply, err = _run_ollama(attempt_index)
            elif b == "openrouter":
                cp = _cloud_prompt_bundle()
                log_prompted_call(
                    module_name=_mod,
                    agent_name=_ag,
                    task_type=_log_task_type,
                    provider="openrouter",
                    model=_CLOUD_MODEL_LOG_OPENROUTER,
                    bundle_meta=cp["meta"],
                    prompt_length=len(cp["system_text"]),
                    legacy_prompt_path=False,
                    call_id=llm_call_id,
                    route_task_type=route_task_type,
                    attempt_index=attempt_index,
                    fallback_from=primary if b != primary else None,
                    prompt_hash=prompt_payload_fingerprint(cp["messages"]),
                )
                reply, err = cloud_openrouter_call(cp["messages"], max_tokens)
            else:
                cp = _cloud_prompt_bundle()
                log_prompted_call(
                    module_name=_mod,
                    agent_name=_ag,
                    task_type=_log_task_type,
                    provider="openai",
                    model=_CLOUD_MODEL_LOG_OPENAI,
                    bundle_meta=cp["meta"],
                    prompt_length=len(cp["system_text"]),
                    legacy_prompt_path=False,
                    call_id=llm_call_id,
                    route_task_type=route_task_type,
                    attempt_index=attempt_index,
                    fallback_from=primary if b != primary else None,
                    prompt_hash=prompt_payload_fingerprint(cp["messages"]),
                )
                reply, err = cloud_openai_call(cp["messages"], max_tokens)
        except Exception as e:
            err = str(e)
            reply = ""
            if b in ("openai", "openrouter") and orch_registry is not None:
                orch_registry.note_api_failure(b)
            logger.warning("[UnifiedLLM] call_id=%s provider %s raised: %s", llm_call_id, b, e)
            if b == "openai":
                try:
                    from .openai_degraded import note_openai_transport_failure

                    note_openai_transport_failure(e, context="unified_llm_openai_raised")
                except Exception:
                    pass
            try:
                from .api_usage_meter import record_transport

                _mc = {"openai": "openai_chat", "openrouter": "openrouter_chat", "ollama": "ollama_chat"}.get(
                    b, str(b)
                )
                record_transport(_mc, False, detail=str(e)[:200])
            except Exception:
                pass
            continue

        if err:
            if b in ("openai", "openrouter") and orch_registry is not None:
                orch_registry.note_api_failure(b)
            # Live path returns (reply, err) without raising — must record 429/quota here or the
            # insufficient_quota reasoning block never arms and select_best_api keeps choosing OpenAI.
            if b == "openai" and err:
                try:
                    from .openai_degraded import note_openai_transport_failure

                    note_openai_transport_failure(RuntimeError(err), context="unified_llm_openai")
                except Exception:
                    pass
            try:
                from .api_usage_meter import record_transport

                _mc = {"openai": "openai_chat", "openrouter": "openrouter_chat", "ollama": "ollama_chat"}.get(
                    b, str(b)
                )
                record_transport(_mc, False, detail=str(err)[:200])
            except Exception:
                pass
            continue

        if reply:
            if _structured_ctx is not None:
                v = validate_module_llm_output(_structured_ctx[0], _structured_ctx[1], _structured_ctx[2], reply)
                if not v.get("valid"):
                    err = "structured_output_validation_failed: " + ",".join(v.get("errors") or [])[:240]
                    meta["structured_output_valid"] = False
                    meta["structured_validation_errors"] = v.get("errors") or []
                    reply = ""
                    continue
                meta["structured_output_valid"] = True
                meta["structured_envelope"] = v
                reply = structured_reply_text(v)
            meta["backend"] = b
            try:
                from .api_usage_meter import record_transport

                _mc = {"openai": "openai_chat", "openrouter": "openrouter_chat", "ollama": "ollama_chat"}.get(
                    b, str(b)
                )
                record_transport(_mc, True)
            except Exception:
                pass
            if b == "openai":
                try:
                    from .openai_degraded import (
                        note_openai_reasoning_success_clear_streak,
                        openai_insufficient_quota_block_until_epoch,
                    )

                    clear_quota_block = bool(openai_insufficient_quota_block_until_epoch() > 0)
                    note_openai_reasoning_success_clear_streak(
                        clear_insufficient_quota_block=(
                            clear_quota_block
                            or (
                                route_task_type in _REASONING_ROUTER_TASK_TYPES
                                and os.environ.get("ELYSIA_CLEAR_INSUFFICIENT_QUOTA_ON_OA_SUCCESS", "")
                                .strip()
                                .lower()
                                in ("1", "true", "yes")
                            )
                        ),
                    )
                except Exception:
                    pass
            if b != primary:
                meta["fallback_from"] = primary
                meta["reason"] = f"fallback_success:{b}"
            break

    meta["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    _fb = meta.get("fallback_from")
    if _fb:
        logger.info(
            "[UnifiedLLM] call_id=%s backend=%s latency_ms=%.1f fallback_from=%s router_primary=%s router_reason=%s",
            llm_call_id,
            meta.get("backend"),
            meta["latency_ms"],
            _fb,
            meta.get("router_primary"),
            (meta.get("router_reason") or "")[:160],
        )
    else:
        logger.info(
            "[UnifiedLLM] call_id=%s backend=%s latency_ms=%.1f reason=%s",
            llm_call_id,
            meta.get("backend"),
            meta["latency_ms"],
            (meta.get("router_reason") or meta.get("reason") or "")[:160],
        )

    if orch_registry is not None and hasattr(orch_registry, "log_capability_usage") and meta.get("backend") != "capability":
        try:
            orch_registry.log_capability_usage(
                task=user_text[:500],
                capability_id=f"llm_chat:{meta.get('backend')}",
                capability_type="llm_chat",
                success=bool(reply) and not err,
                quality=0.85 if reply and not err else 0.2,
                latency_ms=float(meta["latency_ms"]),
                extra={
                    "api_provider": meta.get("backend"),
                    "route_reason": meta.get("reason"),
                    "router_primary": meta.get("router_primary"),
                    "router_reason": meta.get("router_reason"),
                    "fallback_from": meta.get("fallback_from"),
                    "selfbuild_rag": meta.get("selfbuild_rag"),
                },
            )
        except Exception as le:
            logger.debug("unified chat usage log: %s", le)

    if require_autonomy_safe_reasoning:
        _finalize_autonomy_safe_route_meta(meta)

    try:
        from .llm_trace_jsonl import append_unified_chat_trace

        append_unified_chat_trace(
            reply=reply,
            err=err,
            meta=meta,
            module_name=_mod,
            agent_name=_ag,
            route_task_type=route_task_type,
            require_autonomy_safe_reasoning=require_autonomy_safe_reasoning,
            user_text=user_text,
        )
    except Exception:
        pass

    return reply, err, meta


def unified_autonomy_chat_completion(
    *,
    messages: List[Dict[str, str]],
    max_tokens: int,
    guardian: Optional[Any],
    cloud_openai_call: Callable[[List[Dict[str, str]], int], Tuple[str, str]],
    cloud_openrouter_call: Callable[[List[Dict[str, str]], int], Tuple[str, str]],
    mistral_model: Optional[str] = None,
    skip_capability_preamble: bool = False,
    module_name: str,
    agent_name: Optional[str] = None,
    prompt_extra: Optional[Dict[str, Any]] = None,
    structured_role: Optional[str] = None,
) -> Tuple[str, str, Dict[str, Any]]:
    """
    Internal / autonomy-originated unified chat: delegates to :func:`unified_chat_completion` with
    ``require_autonomy_safe_reasoning=True``. Prefer this for new autonomy call sites to avoid omitting the flag.
    """
    return unified_chat_completion(
        messages=messages,
        max_tokens=max_tokens,
        guardian=guardian,
        cloud_openai_call=cloud_openai_call,
        cloud_openrouter_call=cloud_openrouter_call,
        mistral_model=mistral_model,
        skip_capability_preamble=skip_capability_preamble,
        module_name=module_name,
        agent_name=agent_name,
        prompt_extra=prompt_extra,
        require_autonomy_safe_reasoning=True,
        structured_role=structured_role,
    )


def build_chat_context_pipeline_prefix(guardian: Any, user_text: str) -> str:
    """
    When ELYSIA_UNIFIED_CHAT_PIPELINE=1, run a lightweight context_pipeline retrieval (no online call)
    and return a short system prefix so unified chat does not rely on raw logs/memory dumps.
    """
    if os.environ.get("ELYSIA_UNIFIED_CHAT_PIPELINE", "").strip().lower() not in ("1", "true", "yes", "on"):
        return ""
    if not guardian:
        return ""
    try:
        from .context_pipeline.runner import run_context_pipeline_for_decider

        sid = f"chat_{int(time.time())}"
        pipe = run_context_pipeline_for_decider(
            guardian,
            active_goal=(user_text or "")[:1200],
            session_id=sid,
            decider_cfg={"use_context_pipeline": True},
        )
        inj = (pipe.get("planner_injection") or "").strip() if isinstance(pipe, dict) else ""
        if not inj:
            return ""
        logger.info("[UnifiedLLM] chat_context_pipeline_prefix chars=%s", min(len(inj), 4000))
        return "[ContextPipeline]\n" + inj[:6000]
    except Exception as e:
        logger.debug("build_chat_context_pipeline_prefix: %s", e)
        return ""
