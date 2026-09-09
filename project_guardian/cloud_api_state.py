# project_guardian/cloud_api_state.py
"""
Unified view of cloud API credential availability vs routing degradation.

- Keys loaded: from the same sources as APIKeyManager (env + config/api_keys.json + API keys folder).
- Usable for routing: keys loaded AND not policy-disabled AND OpenAI not in global degraded cooldown (429/quota).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_cached: Optional[Dict[str, Any]] = None


def _snapshot_from_key_manager() -> Dict[str, Any]:
    try:
        from .api_key_manager import get_api_key_manager

        mgr = get_api_key_manager()
        mgr.load_keys()
        k = mgr.keys
        return {
            "openai": bool((k.openai or "").strip()),
            "openrouter": bool((k.openrouter or "").strip()),
            "anthropic": bool((k.anthropic or "").strip()),
            "huggingface": bool((k.huggingface or "").strip()),
            "cohere": bool((k.cohere or "").strip()),
            "source": "api_key_manager",
        }
    except Exception as e:
        logger.debug("cloud_api_state: key manager: %s", e)
        return {
            "openai": False,
            "openrouter": False,
            "anthropic": False,
            "huggingface": False,
            "cohere": False,
            "source": "none",
        }


def cloud_credentials_snapshot(refresh: bool = False) -> Dict[str, Any]:
    """Which provider keys are present (independent of degraded cooldown)."""
    global _cached
    if _cached is None or refresh:
        _cached = _snapshot_from_key_manager()
    return dict(_cached)


def any_llm_cloud_key_loaded() -> bool:
    s = cloud_credentials_snapshot()
    return bool(
        s.get("openai")
        or s.get("openrouter")
        or s.get("anthropic")
        or s.get("huggingface")
        or s.get("cohere")
    )


def openai_key_loaded() -> bool:
    return bool(cloud_credentials_snapshot().get("openai"))


def openrouter_key_loaded() -> bool:
    return bool(cloud_credentials_snapshot().get("openrouter"))


def openrouter_routing_disabled_by_policy() -> bool:
    v = (os.environ.get("ELYSIA_DISABLE_OPENROUTER_ROUTING") or "").strip().lower()
    return v in ("1", "true", "yes")


def anthropic_routing_disabled_by_policy() -> bool:
    v = (os.environ.get("ELYSIA_DISABLE_ANTHROPIC_ROUTING") or "").strip().lower()
    return v in ("1", "true", "yes")


def openrouter_ready_for_reasoning() -> bool:
    """Backward-compatible: key present (does not assert routability or policy). Prefer openrouter_usable_for_reasoning()."""
    return openrouter_key_loaded()


def openrouter_usable_for_reasoning() -> bool:
    """Key present and not policy-disabled — counts toward capability sufficiency."""
    if not openrouter_key_loaded():
        return False
    if openrouter_routing_disabled_by_policy():
        return False
    return True


def anthropic_usable_for_reasoning() -> bool:
    """
    Conservative: key + policy allow is not enough for unified reasoning sufficiency.
    Requires ELYSIA_ANTHROPIC_REASONING_TRUST=1 so operators explicitly opt in (no live probe here).
    """
    if not anthropic_key_loaded():
        return False
    if anthropic_routing_disabled_by_policy():
        return False
    v = (os.environ.get("ELYSIA_ANTHROPIC_REASONING_TRUST") or "").strip().lower()
    return v in ("1", "true", "yes")


def _compact_openai_blocked_reason(code: Optional[str]) -> Optional[str]:
    """Stable short codes for operator snapshots (usable → caller passes None)."""
    if not code or code == "openai_ok":
        return None
    m = {
        "openai_policy_disabled": "policy_disabled",
        "openai_key_missing": "not_configured",
        "openai_insufficient_quota_blocked": "quota",
        "openai_degraded_cooldown": "cooldown",
        "openai_guard_state_unreadable": "not_routable",
    }
    return m.get(code, "not_routable")


def provider_reasoning_truth_snapshot(*, refresh: bool = False) -> Dict[str, Any]:
    """
    Per-provider configured / routable / usable for reasoning (compact, no network I/O).
    - configured: API key present
    - routable: configured and not blocked by policy from appearing on routes
    - usable: routable and not degraded / quota-blocked (OpenAI) or explicit trust (Anthropic)
    - autonomy_safe: same as usable here — stricter than raw API-router selectability (router may still
      consider Anthropic from key alone; usable/autonomy_safe require trust + policy for Anthropic).
    - blocked_reason: short stable token when not usable (see _compact_openai_blocked_reason)
    """
    s = cloud_credentials_snapshot(refresh=refresh)
    oa_cfg = bool(s.get("openai"))
    oa_routable = oa_cfg and not openai_routing_disabled_by_policy()
    oa_use = bool(openai_usable_for_routing())
    oa_br = None if oa_use else _compact_openai_blocked_reason(openai_routing_block_reason())

    or_cfg = bool(s.get("openrouter"))
    or_routable = or_cfg and not openrouter_routing_disabled_by_policy()
    or_use = bool(openrouter_usable_for_reasoning())
    if or_use:
        or_br = None
    elif not or_cfg:
        or_br = "not_configured"
    elif openrouter_routing_disabled_by_policy():
        or_br = "policy_disabled"
    else:
        or_br = "not_routable"

    an_cfg = bool(s.get("anthropic"))
    an_routable = an_cfg and not anthropic_routing_disabled_by_policy()
    an_use = bool(anthropic_usable_for_reasoning())
    if an_use:
        an_br = None
    elif not an_cfg:
        an_br = "not_configured"
    elif anthropic_routing_disabled_by_policy():
        an_br = "policy_disabled"
    else:
        an_br = "not_routable"

    return {
        "openai": {
            "configured": oa_cfg,
            "routable": oa_routable,
            "usable": oa_use,
            "autonomy_safe": bool(oa_use),
            "blocked_reason": oa_br,
        },
        "openrouter": {
            "configured": or_cfg,
            "routable": or_routable,
            "usable": or_use,
            "autonomy_safe": bool(or_use),
            "blocked_reason": or_br,
        },
        "anthropic": {
            "configured": an_cfg,
            "routable": an_routable,
            "usable": an_use,
            "autonomy_safe": bool(an_use),
            "blocked_reason": an_br,
        },
    }


def capability_reasoning_snapshot() -> Dict[str, Any]:
    """
    Capability-level view (local staged planner + cloud keys), for dashboards.
    Does not call remote providers.
    """
    try:
        from .planner_readiness import build_runtime_decision_status_dict

        return build_runtime_decision_status_dict(None)
    except Exception:
        return {}


def anthropic_key_loaded() -> bool:
    return bool(cloud_credentials_snapshot().get("anthropic"))


def huggingface_key_loaded() -> bool:
    return bool(cloud_credentials_snapshot().get("huggingface"))


def cohere_key_loaded() -> bool:
    return bool(cloud_credentials_snapshot().get("cohere"))


def openai_routing_disabled_by_policy() -> bool:
    v = (os.environ.get("ELYSIA_DISABLE_OPENAI_ROUTING") or "").strip().lower()
    return v in ("1", "true", "yes")


def openai_usable_for_routing(*, allow_quota_reprobe: bool = False) -> bool:
    """Key present, policy allows, not in openai_degraded cooldown, not in insufficient_quota reasoning block."""
    if openai_routing_disabled_by_policy():
        return False
    if not openai_key_loaded():
        return False
    try:
        from .openai_degraded import (
            is_openai_degraded_active,
            openai_insufficient_quota_reasoning_blocked,
        )

        if openai_insufficient_quota_reasoning_blocked(allow_reprobe=allow_quota_reprobe):
            return False
        if is_openai_degraded_active():
            return False
    except Exception as e:
        logger.debug("openai_usable_for_routing: degraded read failed (%s); fail closed", e)
        return False
    return True


def openai_routing_block_reason() -> str:
    """Why OpenAI is not used for routing (for logs; avoid false 'no cloud keys')."""
    if openai_routing_disabled_by_policy():
        return "openai_policy_disabled"
    if not openai_key_loaded():
        return "openai_key_missing"
    try:
        from .openai_degraded import (
            is_openai_degraded_active,
            openai_insufficient_quota_reasoning_blocked,
        )

        if openai_insufficient_quota_reasoning_blocked():
            return "openai_insufficient_quota_blocked"
        if is_openai_degraded_active():
            return "openai_degraded_cooldown"
    except Exception as e:
        logger.debug("openai_routing_block_reason: degraded read failed (%s)", e)
        return "openai_guard_state_unreadable"
    return "openai_ok"


def human_openai_routing_message(block_reason: str) -> str:
    """User-facing / log string for OpenAI routing state (never conflate with missing key)."""
    if block_reason == "openai_policy_disabled":
        return "OpenAI routing disabled by policy (ELYSIA_DISABLE_OPENAI_ROUTING); key may still be loaded"
    if block_reason == "openai_key_missing":
        return "OpenAI key not loaded (APIKeyManager / env)"
    if block_reason == "openai_degraded_cooldown":
        return "OpenAI key loaded; temporarily unusable (degraded / 429 cooldown)"
    if block_reason == "openai_insufficient_quota_blocked":
        return "OpenAI key loaded; insufficient_quota block active (reasoning/chat routes skip OpenAI until expiry or verified reasoning success)"
    if block_reason == "openai_guard_state_unreadable":
        return "OpenAI key loaded; could not read quota/degraded guard — routing treats OpenAI as unavailable"
    return "OpenAI usable for routing"


def usable_cloud_routing_snapshot(*, refresh: bool = False) -> Dict[str, Any]:
    """Single object for routers: per-provider loaded vs usable vs reason."""
    s = cloud_credentials_snapshot(refresh=refresh)
    oa_br = openai_routing_block_reason()
    return {
        "openai": {
            "key_loaded": bool(s.get("openai")),
            "usable_for_routing": openai_usable_for_routing(),
            "routing_block_reason": oa_br,
            "routing_block_message": human_openai_routing_message(oa_br),
            "policy_disables_routing": openai_routing_disabled_by_policy(),
        },
        "openrouter": {
            "key_loaded": bool(s.get("openrouter")),
            "routable": bool(s.get("openrouter")) and not openrouter_routing_disabled_by_policy(),
            "usable_for_reasoning": openrouter_usable_for_reasoning(),
        },
        "anthropic": {
            "key_loaded": bool(s.get("anthropic")),
            "routable": bool(s.get("anthropic")) and not anthropic_routing_disabled_by_policy(),
            "usable_for_reasoning": anthropic_usable_for_reasoning(),
        },
        "huggingface": {"key_loaded": bool(s.get("huggingface"))},
        "cohere": {"key_loaded": bool(s.get("cohere"))},
        "any_llm_key_loaded": any_llm_cloud_key_loaded(),
        "source": s.get("source"),
    }


def chat_completion_route_reason_code() -> str:
    """
    Machine-readable reason when unified chat falls back to local Ollama
    while some cloud credential exists (never collapse to a generic 'no keys').
    """
    s = cloud_credentials_snapshot(refresh=True)
    if not any_llm_cloud_key_loaded():
        return "no_cloud_keys_loaded"
    if openai_routing_disabled_by_policy() and bool(s.get("openai")):
        return "cloud_keys_loaded_but_openai_routing_disabled"
    if bool(s.get("openai")):
        try:
            from .openai_degraded import (
                is_openai_degraded_active,
                openai_insufficient_quota_reasoning_blocked,
            )

            if openai_insufficient_quota_reasoning_blocked():
                return "openai_insufficient_quota_blocked"
            if is_openai_degraded_active():
                return "openai_loaded_but_degraded"
        except Exception:
            return "openai_guard_state_unreadable"
    oa_ld = bool(s.get("openai"))
    or_ld = bool(s.get("openrouter"))
    if not oa_ld and not or_ld:
        return "cloud_loaded_no_openai_openrouter_for_chat"
    return "cloud_loaded_no_chat_route_enabled"


def embedding_route_reason_code() -> str:
    """Why embedding selection fell back to local (OpenAI is the primary cloud embed route here)."""
    s = cloud_credentials_snapshot(refresh=True)
    try:
        from .openai_degraded import openai_embedding_in_long_backoff

        if bool(s.get("openai")) and openai_embedding_in_long_backoff():
            return "openai_embedding_long_cooldown_active"
    except Exception:
        pass
    if openai_usable_for_routing():
        return "openai_embedding_available"
    if bool(s.get("openai")):
        br = openai_routing_block_reason()
        if br == "openai_policy_disabled":
            return "cloud_keys_loaded_but_openai_routing_disabled"
        if br == "openai_degraded_cooldown":
            return "openai_loaded_but_degraded"
    if any_llm_cloud_key_loaded():
        return "cloud_loaded_no_embedding_provider_enabled"
    return "no_cloud_keys_loaded"


def format_chat_route_reason_for_logs(code: str) -> str:
    """Human-readable expansion for logs (same codes as chat_completion_route_reason_code)."""
    m = {
        "no_cloud_keys_loaded": "no_cloud_keys_loaded — APIKeyManager loaded none of openai/openrouter/anthropic/huggingface/cohere",
        "cloud_keys_loaded_but_openai_routing_disabled": "cloud_keys_loaded_but_openai_routing_disabled — ELYSIA_DISABLE_OPENAI_ROUTING",
        "openai_loaded_but_degraded": "openai_loaded_but_degraded — quota/429 cooldown active",
        "openai_available": "openai_available",
        "openrouter_available_reasoning_only": "openrouter_available_reasoning_only — use OpenRouter for chat when OpenAI blocked/missing",
        "openrouter_available_openai_blocked": "openrouter_available_openai_blocked — OpenAI key present but not usable for routing",
        "cloud_loaded_no_openai_openrouter_for_chat": "cloud_loaded_no_openai_openrouter_for_chat — only HF/cohere/anthropic-style keys (no OpenAI-compat chat route in unified stack)",
        "cloud_loaded_no_chat_route_enabled": "cloud_loaded_no_chat_route_enabled — keys present but no usable chat path",
        "cloud_loaded_no_embedding_provider_enabled": "cloud_loaded_no_embedding_provider_enabled — no OpenAI route for embeddings",
        "openai_embedding_long_cooldown_active": "openai_embedding_long_cooldown_active — repeated 429s; hour-scale local embed only",
        "openai_reasoning_long_cooldown_active": "openai_reasoning_long_cooldown_active — repeated reasoning 429s; long OpenAI skip for reasoning routes",
        "openai_recently_degraded_prefer_openrouter": "openai_recently_degraded_prefer_openrouter — short 429 cooldown; prefer OpenRouter for reasoning",
        "openai_insufficient_quota_blocked": "openai_insufficient_quota_blocked — insufficient_quota on reasoning/chat; OpenAI skipped for reasoning routes",
        "openai_quota_block_prefer_openrouter": "openai_quota_block_prefer_openrouter — quota block active; routing reasoning to OpenRouter",
    }
    return m.get(code, code)
