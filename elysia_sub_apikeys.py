#!/usr/bin/env python3
"""
Elysia subroutine: Load API keys into environment.

Must run first so APIManager and MultiAPIRouter can use keys for parallel AI.
Keys: OPENAI, OPENROUTER, COHERE, HUGGINGFACE, REPLICATE, ALPHA_VANTAGE.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def load_api_keys() -> Optional[dict]:
    """
    Load API keys from API keys folder into environment variables.
    Returns dict of loaded key names, or None on failure.
    """
    logger.info("[0/5] Loading API Keys...")
    try:
        from load_api_keys import load_api_keys as _load
        keys_loaded = _load()
        if keys_loaded:
            count = len([k for k in keys_loaded.values() if k == "Loaded"])
            logger.info(f"  [OK] Loaded {count} API keys")
            return keys_loaded
        else:
            logger.warning("  [WARN] No API keys loaded")
            return None
    except Exception as e:
        logger.warning(f"  [WARN] Could not load API keys: {e}")
        return None
