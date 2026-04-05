#!/usr/bin/env python3
"""Elysia subroutine: Initialize integrated modules (TrustEval, FractalMind, Harvest, etc.)."""
import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


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

    # Harvest Engine
    try:
        from harvest_engine import HarvestEngine
        modules["harvest_engine"] = HarvestEngine(
            gumroad_token=os.environ.get("GUMROAD_ACCESS_TOKEN"),
            stripe_key=os.environ.get("STRIPE_SECRET_KEY"),
        )
        logger.info("  [OK] Harvest Engine initialized")
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

    logger.info(f"  [OK] {len(modules)} modules initialized")
    return modules
