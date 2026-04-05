# project_guardian/startup_runtime_guard.py
"""Startup-age helpers: memory-thin mode, early Ollama budget, ST deferral (no new architecture)."""
from __future__ import annotations

import datetime
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_guardian_ref: Any = None
_last_thin_state: Optional[bool] = None


def bind_guardian_for_runtime_guard(core: Any) -> None:
    global _guardian_ref
    _guardian_ref = core


def startup_age_sec(core: Optional[Any] = None) -> Optional[float]:
    """Seconds since Guardian `start_time`, or None if no core is bound."""
    g = core if core is not None else _guardian_ref
    if g is None or not hasattr(g, "start_time"):
        return None
    return (datetime.datetime.now() - g.start_time).total_seconds()


def _thin_max_wall_sec() -> float:
    try:
        return max(60.0, float(os.environ.get("ELYSIA_STARTUP_THIN_MAX_SEC", "3600")))
    except ValueError:
        return 3600.0


def startup_memory_thin_mode_active(core: Optional[Any] = None) -> bool:
    """
    While True: prefer skipping non-essential remembers and defer heavy local embedding (ST).
    Ends when operational state is stable (memory loaded, dashboard ready if UI exists, defer complete).

    Uses only direct Guardian attributes — must NOT call get_startup_operational_state() (that would recurse).
    """
    g = core if core is not None else _guardian_ref
    if g is None:
        return False
    age = startup_age_sec(g)
    if age is not None and age >= _thin_max_wall_sec():
        return False
    if getattr(g, "deferred_init_running", False):
        return True
    mem = getattr(g, "memory", None)
    memory_loaded = False
    if mem is not None and hasattr(mem, "get_memory_state"):
        try:
            st = mem.get_memory_state(load_if_needed=False)
            memory_loaded = bool(st.get("memory_loaded", st.get("json_loaded", False)))
        except Exception:
            memory_loaded = False
    if not memory_loaded:
        return True
    panel = getattr(g, "ui_panel", None)
    if panel is not None and hasattr(panel, "is_ready"):
        try:
            if not bool(panel.is_ready()):
                return True
        except Exception:
            return True
    if getattr(g, "_defer_heavy_startup", False):
        if not getattr(g, "deferred_init_complete", True) or getattr(g, "deferred_init_failed", False):
            return True
    return False


def observe_memory_thin_transition(core: Optional[Any] = None) -> None:
    """Log once when memory-thin mode turns off (status polling is fine)."""
    global _last_thin_state
    g = core if core is not None else _guardian_ref
    if g is None:
        return
    cur = startup_memory_thin_mode_active(g)
    if _last_thin_state is True and cur is False:
        logger.info(
            "[Startup] memory-thin mode OFF (operational); routine remembers / ST embed path enabled"
        )
    _last_thin_state = cur


def should_defer_vector_add_during_startup(category: str, priority: float, thought: str) -> bool:
    """
    While memory-thin / pre-operational: skip FAISS loads and vector rows for routine
    low-priority autonomy-style lines (JSON may still be written).
    """
    if not startup_memory_thin_mode_active():
        return False
    try:
        from .memory_noise import thought_indicates_important_memory

        if thought_indicates_important_memory(thought or ""):
            return False
    except Exception:
        pass
    cat = (category or "").lower().strip()
    if cat not in ("autonomy", "exploration", "monitoring", "introspection", "learning"):
        return False
    if float(priority or 0) >= 0.74:
        return False
    th = (thought or "").strip()
    if th.startswith("[Startup]") or th.lower().startswith("[guardian"):
        return False
    return True


def should_skip_nonessential_remember(category: str, priority: float, thought: str) -> bool:
    if not startup_memory_thin_mode_active():
        return False
    cat = (category or "general").lower().strip()
    pr = float(priority or 0)
    if cat in ("error", "safety", "critical"):
        return False
    if pr >= 0.88:
        return False
    th = thought or ""
    if th.startswith("[Startup]") or "startup failed" in th.lower()[:120]:
        return False
    if "Guardian Core" in th and "Created task" in th:
        return False
    if cat in ("autonomy", "exploration", "introspection") and pr < 0.78:
        return True
    if cat == "learning" and pr < 0.65:
        return True
    if pr < 0.55 and len(th) < 220:
        return True
    return False


def defer_sentence_transformers_for_embed() -> bool:
    """True → use hash embedding path instead of loading SentenceTransformer."""
    g = _guardian_ref
    if g is None:
        return False
    if startup_memory_thin_mode_active(g):
        return True
    try:
        from .openai_degraded import embedding_long_cooldown_active

        if embedding_long_cooldown_active():
            try:
                defer_sec = float(os.environ.get("ELYSIA_ST_DEFER_WHEN_OA_EMBED_LONG_SEC", "180"))
            except ValueError:
                defer_sec = 180.0
            _age = startup_age_sec(g)
            if _age is not None and _age < defer_sec:
                return True
    except Exception:
        pass
    return False


def embedding_fallback_loaded_status() -> bool:
    """True if shared VectorMemory has loaded the sentence-transformers model."""
    g = _guardian_ref
    if g is None:
        return False
    mem = getattr(g, "memory", None)
    vm = getattr(mem, "vector_memory", None) if mem else None
    if vm is None:
        return False
    return getattr(vm, "_sentence_transformer_model", None) is not None


def early_runtime_budget_active(core: Optional[Any] = None) -> bool:
    """First N seconds after Guardian boot: tighter Ollama timeouts + boot action downrank."""
    g = core if core is not None else _guardian_ref
    if g is None:
        return False
    age = startup_age_sec(g)
    if age is None:
        return False
    try:
        window = float(os.environ.get("ELYSIA_EARLY_RUNTIME_BUDGET_SEC", "300"))
    except ValueError:
        window = 300.0
    return age < max(30.0, window)
