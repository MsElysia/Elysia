#!/usr/bin/env python3
"""Elysia subroutine: Initialize Architect-Core."""
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def init_architect_core() -> Optional[Any]:
    """
    Initialize Architect-Core system.
    Guardian must be initialized first (WebScout needs web_reader from Guardian).
    Returns ArchitectCore instance or None on failure.
    """
    logger.info("[2/5] Initializing Architect-Core...")
    try:
        from architect_core import ArchitectCore
        architect = ArchitectCore()
        logger.info("  [OK] Architect-Core initialized")
        return architect
    except Exception as e:
        logger.error(f"  [FAIL] Architect-Core failed: {e}")
        return None
