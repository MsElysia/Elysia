# project_guardian/ollama_model_config.py
"""Single canonical Ollama model name for health checks, MistralEngine, and orchestration adapters."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MISTRAL_DECIDER_PATH = _PROJECT_ROOT / "config" / "mistral_decider.json"
_LOGGED_ONCE = False
# Set by planner startup when exactly one installed variant matches configured base name.
_effective_override: Optional[str] = None


def set_effective_ollama_model_from_planner(tag: str) -> None:
    """Session-only exact tag when config name is wrong but a single installed variant exists."""
    global _effective_override
    t = (tag or "").strip()
    _effective_override = t if t else None


def _read_decider_model() -> Optional[str]:
    if not _MISTRAL_DECIDER_PATH.exists():
        return None
    try:
        with open(_MISTRAL_DECIDER_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        m = (cfg.get("mistral_decider_model") or cfg.get("ollama_model") or "").strip()
        return m or None
    except Exception as e:
        logger.debug("ollama_model_config: mistral_decider read: %s", e)
        return None


def get_canonical_ollama_model(*, log_once: bool = True) -> str:
    """
    Resolution order (first non-empty wins):
    1. ELYSIA_OLLAMA_MODEL
    2. OLLAMA_MODEL
    3. config/mistral_decider.json → mistral_decider_model | ollama_model
    4. default "mistral:7b" (exact Ollama tag)
    5. planner session override (single exact installed variant) when set
    """
    global _LOGGED_ONCE
    from_env = False
    model = ""
    for env in ("ELYSIA_OLLAMA_MODEL", "OLLAMA_MODEL"):
        v = (os.environ.get(env) or "").strip()
        if v:
            model = v
            from_env = True
            break
    if not model:
        model = (_read_decider_model() or "mistral:7b").strip()
    if not model:
        model = "mistral:7b"
    if _effective_override and not from_env:
        model = _effective_override
    if log_once and not _LOGGED_ONCE:
        _LOGGED_ONCE = True
        logger.debug(
            "[Ollama] Canonical local model name: %s (override with ELYSIA_OLLAMA_MODEL; startup logs final tag)",
            model,
        )
    return model


def ollama_provider_ref(*, log_once: bool = False) -> str:
    """Stable model ref for YAML defaults and broker cache keys: ollama:<canonical>."""
    return f"ollama:{get_canonical_ollama_model(log_once=log_once)}"


def reset_log_flag_for_tests() -> None:
    global _LOGGED_ONCE, _effective_override
    _LOGGED_ONCE = False
    _effective_override = None
