#!/usr/bin/env python3
"""Elysia subroutine: Initialize Guardian Core (singleton)."""
import os
import logging
from pathlib import Path
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
        # Defaults preserve historical desktop boot; explicit cfg values win so
        # contained/acceptance configs can disable monitoring, vector memory,
        # external storage, and API-key loading without being stripped here.
        enable_resource_monitoring = bool(cfg.get("enable_resource_monitoring", True))
        enable_runtime_health_monitoring = bool(
            cfg.get("enable_runtime_health_monitoring", True)
        )
        start_background = bool(
            cfg.get(
                "start_background_workers",
                enable_resource_monitoring or enable_runtime_health_monitoring,
            )
        )
        guardian_config = {
            "defer_heavy_startup": cfg.get("defer_heavy_startup", True),
            "trust_file": cfg.get("trust_file", "enhanced_trust.json"),
            "tasks_file": cfg.get("tasks_file", "enhanced_tasks.json"),
            "memory_cleanup_threshold": memory_cleanup_threshold,
            "enable_resource_monitoring": enable_resource_monitoring,
            "enable_runtime_health_monitoring": enable_runtime_health_monitoring,
            "start_background_workers": start_background,
            "enable_vector_memory": cfg.get("enable_vector_memory", True),
            "use_external_storage": cfg.get("use_external_storage", False),
            "_test_skip_external_storage": cfg.get("_test_skip_external_storage", False),
            "_skip_api_key_load": cfg.get("_skip_api_key_load", False),
            "enable_guardian_layer": cfg.get("enable_guardian_layer", True),
            "resource_limits": {
                "memory_limit": memory_limit,
                "cpu_limit": res_cfg.get("cpu_limit") or _parse_resource_limit("ELYSIA_CPU_LIMIT", 0.9),
                "disk_limit": res_cfg.get("disk_limit", 0.9),
            },
            "ui_config": ui_config,
        }
        if _mem is not None:
            guardian_config["memory_filepath"] = _mem
        # Forward optional containment / path overrides when present.
        for key in (
            "storage_path",
            "review_queue_file",
            "approval_store_file",
            "prompt_evolver_path",
            "timeline_db_path",
            "trust_policy_path",
            "trust_audit_path",
            "trust_escalation_path",
            "capability_data_dir",
            "snapshot_config",
            "guardian_layer_config",
            "guardian_layer_config_path",
            "guardian_layer_rebuild_log_path",
            "autonomy_config",
            "auto_learning",
            "eai_safety_config_path",
            "enable_eai_safety",
            "eai_lineage_registry_path",
            "eai_audit_log_path",
            "eai_alert_state_path",
            "config_path",
            "vector_memory_config",
            "contained_startup",
            "disposable_root",
        ):
            if key in cfg:
                guardian_config[key] = cfg[key]
        control_path = cfg.get("control_path")
        tasks_dir = cfg.get("tasks_dir")
        mutations_dir = cfg.get("mutations_dir")
        guardian = get_guardian_core(
            config=guardian_config,
            control_path=Path(control_path) if control_path else None,
            tasks_dir=Path(tasks_dir) if tasks_dir else None,
            mutations_dir=Path(mutations_dir) if mutations_dir else None,
            force_new=bool(cfg.get("_force_new_guardian", False)),
        )
        if guardian:
            if start_background:
                ensure_monitoring_started(guardian)
            else:
                logger.info("  [Config] Skipping monitoring/background workers (contained startup)")
            logger.info("  [OK] Guardian Core initialized (singleton)")
            if memory_limit != 0.8:
                logger.info(f"  [Config] Memory limit: {memory_limit:.0%} (set via config or ELYSIA_MEMORY_LIMIT)")
            if start_background:
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
