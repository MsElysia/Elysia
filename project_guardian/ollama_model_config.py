# project_guardian/ollama_model_config.py
"""Single canonical Ollama model name for health checks, MistralEngine, and orchestration adapters."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MISTRAL_DECIDER_PATH = _PROJECT_ROOT / "config" / "mistral_decider.json"
_LOGGED_ONCE = False
# Set by planner startup when exactly one installed variant matches configured base name.
_effective_override: Optional[str] = None
# Increments on each decider pick when ``ollama_model_pick_index_mode`` is ``process_monotonic``.
_pick_monotonic_seq: int = 0


def set_effective_ollama_model_from_planner(tag: str) -> None:
    """Session-only exact tag when config name is wrong but a single installed variant exists."""
    global _effective_override
    t = (tag or "").strip()
    _effective_override = t if t else None


def _decider_cfg() -> Dict[str, Any]:
    if not _MISTRAL_DECIDER_PATH.exists():
        return {}
    try:
        with open(_MISTRAL_DECIDER_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except Exception as e:
        logger.debug("ollama_model_config: mistral_decider read: %s", e)
        return {}


def _read_decider_model() -> Optional[str]:
    d = _decider_cfg()
    m = (d.get("mistral_decider_model") or d.get("ollama_model") or "").strip()
    return m or None


def get_ollama_model_pool() -> List[str]:
    """
    Ordered list of local Ollama model tags for autonomy / decider use.
    When ``ollama_model_pool`` is absent, falls back to a single-tag list from
    ``mistral_decider_model`` / ``ollama_model`` / default.
    """
    cfg = _decider_cfg()
    pool = cfg.get("ollama_model_pool")
    if isinstance(pool, list) and pool:
        out = [str(x).strip() for x in pool if str(x).strip()]
        if out:
            return out
    m = (cfg.get("mistral_decider_model") or cfg.get("ollama_model") or "mistral:7b").strip()
    return [m] if m else ["mistral:7b"]


def pick_ollama_model_for_decider(*, decision_cycle: int) -> str:
    """
    Pick which Ollama tag to use for this autonomy decision (Elysia "chooses" within the pool).

    - If ``ELYSIA_OLLAMA_MODEL`` or ``OLLAMA_MODEL`` is set, that single tag always wins.
    - If ``ollama_model_pool`` has one tag, returns it.
    - If multiple tags: ``ollama_model_pick_strategy`` in ``mistral_decider.json``:
        - ``round_robin`` (default): ``pool[cycle % len(pool)]`` unless
          ``ollama_model_pick_index_mode`` is ``process_monotonic``, then a process-wide
          counter advances on **every** pick so the pool keeps rotating across runs of the decider.
        - ``alternate_stagnation``: first half of each 8-cycle window uses ``pool[0]``,
          second half uses ``pool[1]`` (or last entry if only one secondary).
        - ``random``: uniform random among pool.

    ``decision_cycle`` should be the current Mistral/autonomy decision index (1-based ok).
    """
    for env in ("ELYSIA_OLLAMA_MODEL", "OLLAMA_MODEL"):
        v = (os.environ.get(env) or "").strip()
        if v:
            return v
    cfg = _decider_cfg()
    pool = get_ollama_model_pool()
    if len(pool) <= 1:
        chosen = pool[0]
        if _effective_override:
            return _effective_override
        return chosen
    strat = str(cfg.get("ollama_model_pick_strategy") or "round_robin").strip().lower()
    c = max(0, int(decision_cycle or 0))
    if strat == "random":
        import random

        chosen = random.choice(pool)
    elif strat == "alternate_stagnation":
        phase = c % 8
        if phase < 4:
            chosen = pool[0]
        else:
            chosen = pool[min(1, len(pool) - 1)]
    else:
        index_mode = str(cfg.get("ollama_model_pick_index_mode") or "decision_cycle").strip().lower()
        if index_mode == "process_monotonic":
            global _pick_monotonic_seq
            _pick_monotonic_seq += 1
            chosen = pool[(_pick_monotonic_seq - 1) % len(pool)]
        else:
            chosen = pool[c % len(pool)]
    if _effective_override:
        return _effective_override
    return chosen


def get_canonical_ollama_model(*, log_once: bool = True) -> str:
    """
    Resolution order (first non-empty wins):
    1. ELYSIA_OLLAMA_MODEL
    2. OLLAMA_MODEL
    3. config/mistral_decider.json → first entry of ``ollama_model_pool`` if set, else
       ``mistral_decider_model`` / ``ollama_model``
    4. default "mistral:7b" (exact Ollama tag)
    5. planner session override (single exact installed variant) when set

    Multi-model rotation for the autonomy decider uses ``pick_ollama_model_for_decider``;
    this function stays stable for health checks, broker keys, and status.
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
        pool = get_ollama_model_pool()
        model = (pool[0] if pool else (_read_decider_model() or "mistral:7b")).strip()
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
    global _LOGGED_ONCE, _effective_override, _pick_monotonic_seq
    _LOGGED_ONCE = False
    _effective_override = None
    _pick_monotonic_seq = 0
