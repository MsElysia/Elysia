#!/usr/bin/env python3
"""Elysia subroutine: Initialize Guardian Core (singleton)."""
import os
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _parse_resource_limit(env_var: str, default: float) -> float:
    """Parse limit from env (0.0-1.0). E.g. ELYSIA_MEMORY_LIMIT=0.9 for 90%."""
    val = os.environ.get(env_var)
    if val is None:
        return default
    try:
        v = float(val)
        if 0.0 <= v <= 1.0:
            return v
    except (ValueError, TypeError):
        pass
    return default


def init_guardian_core(config: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    """
    Initialize Project Guardian Core (singleton).
    Must run before Architect (WebScout needs web_reader from Guardian).
    Returns GuardianCore instance or None on failure.
    """
    logger.info("[1/5] Initializing Guardian Core...")
    try:
        from project_guardian.guardian_singleton import get_guardian_core, ensure_monitoring_started
        cfg = config or {}
        # Resource limits: config first, then env (ELYSIA_MEMORY_LIMIT=0.9), then default
        res_cfg = cfg.get("resource_limits", {})
        memory_limit = res_cfg.get("memory_limit")
        if memory_limit is None:
            memory_limit = _parse_resource_limit("ELYSIA_MEMORY_LIMIT", 0.92)
        # UI Control Panel / dashboard (enabled by default; override via cfg["ui_config"])
        _ui_cfg = cfg.get("ui_config", {})
        ui_config = {
            "enabled": _ui_cfg.get("enabled", True),
            "auto_start": _ui_cfg.get("auto_start", True),
            "host": _ui_cfg.get("host", "127.0.0.1"),
            "port": _ui_cfg.get("port", 5000),
            "debug": _ui_cfg.get("debug", False),
        }
        # Memory cleanup: trigger when memory_log exceeds this count (default 3500)
        memory_cleanup_threshold = cfg.get("memory_cleanup_threshold")
        if memory_cleanup_threshold is None:
            try:
                memory_cleanup_threshold = int(os.environ.get("ELYSIA_MEMORY_CLEANUP_THRESHOLD", "3500"))
            except (ValueError, TypeError):
                memory_cleanup_threshold = 3500

        # memory_filepath is canonical; memory_file is legacy alias
        _mem = cfg.get("memory_filepath") or cfg.get("memory_file")
        guardian_config = {
            "defer_heavy_startup": cfg.get("defer_heavy_startup", True),
            "trust_file": cfg.get("trust_file", "enhanced_trust.json"),
            "tasks_file": cfg.get("tasks_file", "enhanced_tasks.json"),
            "memory_cleanup_threshold": memory_cleanup_threshold,
            "enable_resource_monitoring": True,
            "enable_runtime_health_monitoring": True,
            "resource_limits": {
                "memory_limit": memory_limit,
                "cpu_limit": res_cfg.get("cpu_limit") or _parse_resource_limit("ELYSIA_CPU_LIMIT", 0.9),
                "disk_limit": res_cfg.get("disk_limit", 0.9),
            },
            "ui_config": ui_config,
        }
        if _mem is not None:
            guardian_config["memory_filepath"] = _mem
        guardian = get_guardian_core(config=guardian_config)
        if guardian:
            ensure_monitoring_started(guardian)
            logger.info("  [OK] Guardian Core initialized (singleton)")
            if memory_limit != 0.8:
                logger.info(f"  [Config] Memory limit: {memory_limit:.0%} (set via config or ELYSIA_MEMORY_LIMIT)")
            try:
                from project_guardian.diagnostics.upstream_routing_live_probe import (
                    schedule_upstream_routing_live_probes,
                )

                schedule_upstream_routing_live_probes(guardian)
            except Exception as _diag_e:
                logger.debug("upstream_routing_live_probe schedule: %s", _diag_e)
            return guardian
        else:
            logger.error("  [FAIL] Guardian Core initialization returned None")
            return None
    except Exception as e:
        logger.error(f"  [FAIL] Guardian Core failed: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return None
