#!/usr/bin/env python3
"""Elysia subroutine: Initialize integrated modules (TrustEval, FractalMind, Harvest, etc.)."""
import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def build_harvest_engine_from_current_keys() -> Tuple[Any, Optional[str], Optional[str]]:
    """
    Construct HarvestEngine from resolve_gumroad_access_token / resolve_stripe_secret_key.
    Used at boot and after Control Panel saves income keys (no process restart).
    """
    from harvest_engine import HarvestEngine

    from project_guardian.api_key_manager import resolve_gumroad_access_token, resolve_stripe_secret_key

    gumroad_token = resolve_gumroad_access_token()
    stripe_key = resolve_stripe_secret_key()
    eng = HarvestEngine(gumroad_token=gumroad_token, stripe_key=stripe_key)
    return eng, gumroad_token, stripe_key


def refresh_harvest_engine_in_modules(modules: Dict[str, Any]) -> Dict[str, Any]:
    """
    Replace modules[\"harvest_engine\"] after API keys change. GuardianCore shares this dict via wire_modules.
    """
    if not isinstance(modules, dict):
        return {"ok": False, "reason": "invalid_modules"}
    try:
        eng, g, s = build_harvest_engine_from_current_keys()
        modules["harvest_engine"] = eng
        logger.info(
            "[Income] Harvest Engine refreshed in-process — gumroad=%s stripe=%s",
            "ok" if g else "skipped",
            "ok" if s else "skipped",
        )
        return {"ok": True, "gumroad_bound": bool(g), "stripe_bound": bool(s)}
    except Exception as e:
        logger.warning("refresh_harvest_engine_in_modules failed: %s", e)
        return {"ok": False, "error": str(e)}


class WebScoutModuleSurface:
    """Quota-limited facade around ElysiaWebScout for runtime integration."""

    def __init__(self, scout: Any, max_sources_per_query: int):
        self.webscout = scout
        self.max_sources_per_query = max(1, int(max_sources_per_query))

    def conduct_web_research(self, query: str, max_sources: Optional[int] = None):
        requested = self.max_sources_per_query if max_sources is None else int(max_sources)
        capped = max(1, min(requested, self.max_sources_per_query))
        return self.webscout.conduct_web_research(query=query, max_sources=capped)

    def list_proposals(self, status_filter: Optional[str] = None):
        return self.webscout.list_proposals(status_filter=status_filter)

    def get_status(self) -> Dict[str, Any]:
        status: Dict[str, Any] = {"max_sources_per_query": self.max_sources_per_query}
        if hasattr(self.webscout, "get_brave_search_usage"):
            status["brave_search_usage"] = self.webscout.get_brave_search_usage()
        if hasattr(self.webscout, "get_tavily_usage"):
            status["tavily_usage"] = self.webscout.get_tavily_usage()
        return status


def init_integrated_modules(
    architect: Optional[Any],
    guardian: Optional[Any],
    runtime_loop: Optional[Any],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Initialize all integrated modules (Hestia, TrustEval, FractalMind, Harvest, etc.).
    Returns dict of module_name -> module_instance.
    """
    logger.info("[4/5] Initializing Integrated Modules...")
    modules = {}
    config = config or {}

    # Hestia Bridge (Real Estate Platform)
    try:
        from hestia_bridge import HestiaBridge
        hestia_config = config.get("hestia", {})
        if hestia_config:
            modules["hestia_bridge"] = HestiaBridge(hestia_config)
            if modules["hestia_bridge"].check_hestia_running():
                logger.info("  [OK] Hestia is running and connected")
            else:
                logger.info("  [WARN] Hestia not running (can start manually)")
    except Exception as e:
        logger.warning(f"  [WARN] Hestia Bridge failed: {e}")

    # TrustEvalContent: use GuardianCore's instance as single source of truth when available
    try:
        if guardian and getattr(guardian, "trust_eval_content", None):
            modules["trust_eval_content"] = guardian.trust_eval_content
            logger.info("  [OK] TrustEvalContent using GuardianCore instance")
        else:
            from project_guardian.trust_eval_content import TrustEvalContent
            policy = architect.policy_architect if architect else None
            modules["trust_eval_content"] = TrustEvalContent(
                audit_logger=guardian.memory if guardian else None,
                policy_manager=policy,
            )
            logger.info("  [OK] TrustEvalContent initialized")
    except Exception as e:
        logger.warning(f"  [WARN] TrustEvalContent failed: {e}")

    # FractalMind
    try:
        from fractalmind import FractalMind
        api_key = os.environ.get("OPENAI_API_KEY")
        modules["fractalmind"] = FractalMind(api_key=api_key)
        logger.info("  [OK] FractalMind initialized")
    except Exception as e:
        logger.warning(f"  [WARN] FractalMind failed: {e}")

    # Harvest Engine (Gumroad / Stripe — tokens from APIKeyManager: env, config/api_keys.json, API keys folder)
    try:
        modules["harvest_engine"], gumroad_token, stripe_key = build_harvest_engine_from_current_keys()
        logger.info(
            "  [OK] Harvest Engine initialized — Income gumroad=%s stripe=%s",
            "ok" if gumroad_token else "skipped",
            "ok" if stripe_key else "skipped",
        )
    except Exception as e:
        logger.warning(f"  [WARN] Harvest Engine failed: {e}")

    # Identity Mutation Verifier
    try:
        from identity_mutation_verifier import IdentityMutationVerifier
        modules["identity_verifier"] = IdentityMutationVerifier()
        logger.info("  [OK] Identity Mutation Verifier initialized")
    except Exception as e:
        logger.warning(f"  [WARN] Identity Mutation Verifier failed: {e}")

    # AI Tool Registry
    try:
        from ai_tool_registry import ToolRegistry, TaskRouter
        modules["tool_registry"] = ToolRegistry()
        if hasattr(modules["tool_registry"], "ensure_minimal_builtin_tools"):
            modules["tool_registry"].ensure_minimal_builtin_tools()
        modules["task_router"] = TaskRouter(modules["tool_registry"])
        logger.info("  [OK] AI Tool Registry initialized")
    except Exception as e:
        logger.warning(f"  [WARN] AI Tool Registry failed: {e}")

    # Long Term Planner
    try:
        from longterm_planner import LongTermPlanner
        prompt_evolver = getattr(guardian, "prompt_evolver", None) if guardian else None
        modules["longterm_planner"] = LongTermPlanner(
            runtime_loop=runtime_loop,
            prompt_evolver=prompt_evolver,
        )
        logger.info("  [OK] Long Term Planner initialized")
    except Exception as e:
        logger.warning(f"  [WARN] Long Term Planner failed: {e}")

    if config.get("enable_webscout_agent", False):
        try:
            from project_guardian.webscout_agent import ElysiaWebScout

            proposals_root = Path(config.get("webscout_proposals_root", "proposals"))
            max_sources = int(config.get("webscout_max_sources", 3))
            hard_cap = int(config.get("webscout_hard_cap", 5))
            max_sources = max(1, min(max_sources, max(1, hard_cap)))
            web_reader = getattr(guardian, "web_reader", None) if guardian else None
            scout = ElysiaWebScout(
                web_reader=web_reader,
                proposals_root=proposals_root,
                require_api_keys=bool(config.get("webscout_require_api_keys", False)),
            )
            modules["webscout_agent"] = WebScoutModuleSurface(
                scout=scout,
                max_sources_per_query=max_sources,
            )
            logger.info("  [OK] WebScout Agent initialized (max_sources_per_query=%s)", max_sources)
        except Exception as e:
            logger.warning(f"  [WARN] WebScout Agent failed: {e}")

    logger.info(f"  [OK] {len(modules)} modules initialized")
    return modules
