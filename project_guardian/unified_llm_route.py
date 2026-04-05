# project_guardian/unified_llm_route.py
# Single routing decision for chat-style LLM calls: local Ollama vs cloud APIs.

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

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


def decide_chat_llm_backend(user_text: str, *, registry: Any = None) -> Tuple[str, str]:
    """
    Returns (backend, reason) where backend is:
    openai | openrouter | ollama
    All chat completions should consult this before calling a provider.
    """
    from .cloud_api_state import (
        any_llm_cloud_key_loaded,
        chat_completion_route_reason_code,
        openai_key_loaded,
        openai_usable_for_routing,
        openrouter_key_loaded,
    )
    from .multi_api_router import evaluate_api_vs_local, select_best_api

    text = (user_text or "").strip()
    ev = evaluate_api_vs_local(text[:2000], registry=registry)
    has_openai_key = openai_key_loaded()
    has_openai = openai_usable_for_routing()
    has_or = openrouter_key_loaded()

    if registry is not None and hasattr(registry, "is_api_in_cooldown"):
        if registry.is_api_in_cooldown("openai"):
            has_openai = False
        if registry.is_api_in_cooldown("openrouter"):
            has_or = False

    task_kind = "reasoning" if len(text) > 600 else "simple"
    try:
        from .openai_degraded import openai_insufficient_quota_reasoning_blocked

        _oa_quota_reasoning = bool(openai_insufficient_quota_reasoning_blocked())
    except Exception:
        _oa_quota_reasoning = True
    # insufficient_quota block must disable OpenAI for all chat lengths (usable() should too; this is defense in depth).
    if _oa_quota_reasoning:
        has_openai = False

    r = select_best_api(task_kind, registry=registry, reserve_slot=False)
    chosen = r.get("chosen") or "local_mistral"
    reason_from_router = str(r.get("reason") or "")
    rl = reason_from_router.lower()
    if chosen == "local_mistral" and (
        "insufficient_quota" in rl or "openai_insufficient" in rl or "quota_block" in rl
    ):
        has_openai = False

    if not ev.get("use_api"):
        if has_openai_key or has_or:
            return "ollama", (ev.get("reason") or "heuristic: local suffices")[:200]

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
) -> Tuple[str, str, Dict[str, Any]]:
    """
    Run one chat completion with unified backend selection + optional capability preamble + usage log hook data.
    Returns (reply, error, meta) meta includes backend, reason, latency_ms.

    module_name / agent_name select the Guardian prompt stack for every backend (Ollama, OpenAI, OpenRouter).
    """
    from .llm.prompted_call import log_prompted_call, prepare_prompted_messages, require_prompt_profile

    _mod, _ag, _ = require_prompt_profile(
        module_name, agent_name, caller="unified_chat_completion", allow_legacy=False
    )

    user_text = ""
    for m in reversed(messages):
        if (m.get("role") or "").lower() == "user":
            user_text = str(m.get("content") or "")[:8000]
            break

    # Orchestration capability registry (ranked tools/modules for chat), not the prompt registry.
    orch_registry = getattr(guardian, "_orchestration_registry", None) if guardian else None
    decider_cfg = _load_decider_cfg()
    if orch_registry is not None and hasattr(orch_registry, "reset_chat_api_budget"):
        orch_registry.reset_chat_api_budget(int(decider_cfg.get("chat_max_api_calls_per_turn", 8)))

    t0 = time.perf_counter()
    meta: Dict[str, Any] = {"backend": "unknown", "reason": "", "latency_ms": 0.0}

    if guardian and decider_cfg.get("chat_tool_first_capability", True):
        hit = try_chat_capability_execute(user_text, guardian)
        if hit:
            reply, extra = hit
            meta.update(extra)
            meta["backend"] = "capability"
            meta["reason"] = "chat_tool_first_execute"
            meta["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            logger.info(
                "[UnifiedLLM] backend=capability latency_ms=%.1f",
                meta["latency_ms"],
            )
            return reply, "", meta

    msgs = list(messages)
    if guardian and not skip_capability_preamble:
        try:
            chat_pre = bool(decider_cfg.get("chat_capability_preamble", True))
            if chat_pre:
                pre = build_chat_capability_preamble(user_text, guardian)
                if pre:
                    msgs = [{"role": "system", "content": pre}] + msgs
        except Exception:
            pass

    primary, reason = decide_chat_llm_backend(user_text, registry=orch_registry)
    meta["backend"] = primary
    meta["reason"] = reason

    order: List[str] = []
    seen = set()

    def _add(b: str) -> None:
        if b not in seen:
            order.append(b)
            seen.add(b)

    _add(primary)
    for fb in ("openai", "openrouter", "ollama"):
        _add(fb)

    task_kind = "reasoning" if len(user_text) > 600 else "simple"
    try:
        from .openai_degraded import (
            openai_insufficient_quota_reasoning_blocked,
            openai_reasoning_long_cooldown_active,
        )

        if task_kind == "reasoning" and openai_reasoning_long_cooldown_active():
            order = [x for x in order if x != "openai"]
        if task_kind == "reasoning" and openai_insufficient_quota_reasoning_blocked():
            global _last_unified_quota_skip_log_ts
            had_openai = "openai" in order
            order = [x for x in order if x != "openai"]
            if had_openai:
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

    reply, err = "", ""

    # One prep for all cloud attempts: same msgs as Ollama sees (capability preamble + thread), plus prompt stack.
    _cloud_prep_cache: Optional[Dict[str, Any]] = None

    def _cloud_prompt_bundle() -> Dict[str, Any]:
        nonlocal _cloud_prep_cache
        if _cloud_prep_cache is None:
            _cloud_prep_cache = prepare_prompted_messages(
                list(msgs),
                module_name=_mod,
                agent_name=_ag,
                task_text=_UNIFIED_CHAT_TASK_TEXT,
                caller="unified_chat_completion.cloud",
            )
        return _cloud_prep_cache

    def _run_ollama() -> Tuple[str, str]:
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
                ),
                "",
            )
        except Exception as e:
            return "", str(e)

    for b in order:
        if b in ("openai", "openrouter"):
            if orch_registry is not None and not orch_registry.try_consume_chat_api_slot():
                logger.info("[UnifiedLLM] skipping %s (chat API budget exhausted)", b)
                meta["chat_api_budget_exhausted"] = True
                continue
        try:
            if b == "ollama":
                reply, err = _run_ollama()
            elif b == "openrouter":
                cp = _cloud_prompt_bundle()
                log_prompted_call(
                    module_name=_mod,
                    agent_name=_ag,
                    task_type="unified_chat",
                    provider="openrouter",
                    model=_CLOUD_MODEL_LOG_OPENROUTER,
                    bundle_meta=cp["meta"],
                    prompt_length=len(cp["system_text"]),
                    legacy_prompt_path=False,
                )
                reply, err = cloud_openrouter_call(cp["messages"], max_tokens)
            else:
                cp = _cloud_prompt_bundle()
                log_prompted_call(
                    module_name=_mod,
                    agent_name=_ag,
                    task_type="unified_chat",
                    provider="openai",
                    model=_CLOUD_MODEL_LOG_OPENAI,
                    bundle_meta=cp["meta"],
                    prompt_length=len(cp["system_text"]),
                    legacy_prompt_path=False,
                )
                reply, err = cloud_openai_call(cp["messages"], max_tokens)
        except Exception as e:
            err = str(e)
            reply = ""
            if b in ("openai", "openrouter") and orch_registry is not None:
                orch_registry.note_api_failure(b)
            logger.warning("[UnifiedLLM] provider %s raised: %s", b, e)
            continue

        if err:
            if b in ("openai", "openrouter") and orch_registry is not None:
                orch_registry.note_api_failure(b)
            if b == "openai" and err and (
                "429" in err or "insufficient_quota" in err.lower() or "rate" in err.lower()
            ):
                try:
                    from .openai_degraded import note_openai_rate_limit, note_openai_reasoning_rate_limit

                    note_openai_rate_limit(err[:400], 429, detail=err)
                    note_openai_reasoning_rate_limit(err[:400], status_code=429, context="unified_llm_openai")
                except Exception:
                    pass
            continue

        if reply:
            meta["backend"] = b
            if b == "openai":
                try:
                    from .openai_degraded import note_openai_reasoning_success_clear_streak

                    note_openai_reasoning_success_clear_streak(
                        clear_insufficient_quota_block=(
                            task_kind == "reasoning"
                            and os.environ.get("ELYSIA_CLEAR_INSUFFICIENT_QUOTA_ON_OA_SUCCESS", "")
                            .strip()
                            .lower()
                            in ("1", "true", "yes")
                        ),
                    )
                except Exception:
                    pass
            if b != primary:
                meta["fallback_from"] = primary
                meta["reason"] = f"{reason[:120]} → fallback {b}"
            break

    meta["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    logger.info(
        "[UnifiedLLM] backend=%s latency_ms=%.1f reason=%s",
        meta.get("backend"),
        meta["latency_ms"],
        (meta.get("reason") or "")[:120],
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
                    "fallback_from": meta.get("fallback_from"),
                },
            )
        except Exception as le:
            logger.debug("unified chat usage log: %s", le)

    return reply, err, meta
