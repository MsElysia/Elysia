#!/usr/bin/env python3
"""Elysia subroutine: Initialize Elysia Runtime Loop."""
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def init_runtime_loop() -> Optional[Any]:
    """
    Initialize Elysia Runtime Loop.
    Tries ElysiaRuntimeLoop first, then falls back to project_guardian RuntimeLoop.
    Returns runtime loop instance or None on failure.
    """
    logger.info("[3/5] Initializing Elysia Runtime Loop...")
    try:
        from elysia_runtime_loop import ElysiaRuntimeLoop
        runtime_loop = ElysiaRuntimeLoop()
        logger.info("  [OK] ElysiaRuntimeLoop initialized")
        return runtime_loop
    except Exception as e:
        logger.debug(f"  ElysiaRuntimeLoop not available: {e}")

    try:
        from project_guardian.runtime_loop_core import RuntimeLoop
        runtime_loop = RuntimeLoop()
        logger.info("  [OK] RuntimeLoop (project_guardian) initialized")
        return runtime_loop
    except Exception as e:
        logger.warning(f"  [WARN] Runtime Loop failed (both attempts): {e}")
        return None
