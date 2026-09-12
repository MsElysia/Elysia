#!/usr/bin/env python3
"""Elysia subroutine: Initialize Guardian Core (singleton)."""
import os
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Literal

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


@dataclass(frozen=True)
class GuardianBootstrapAudit:
    """Pure configuration preview for Issue #23 audit/inspection bootstrap.

    This object describes *intended* normalized Guardian config defaults only.
    It does **not** construct GuardianCore, start monitoring/ElysiaLoop/UI,
    schedule probes, touch providers/network, or prove live runtime wiring.
    """

    config: Dict[str, Any]
    mode: Literal["audit"] = "audit"
    runtime_constructed: bool = False
    runtime_wiring_verified: bool = False
    limitation: str = (
        "descriptor_only: architecture/configuration preview; "
        "does not prove live runtime wiring or capability reachability"
    )


def _normalize_config(config: Optional[Dict[str, Any]], *, use_environment: bool) -> Dict[str, Any]:
    cfg = config or {}
    # Resource limits: config first, then env (ELYSIA_MEMORY_LIMIT=0.9), then default
    res_cfg = cfg.get("resource_limits", {})
    memory_limit = res_cfg.get("memory_limit")
    if memory_limit is None:
        memory_limit = (_parse_resource_limit("ELYSIA_MEMORY_LIMIT", 0.92) if use_environment else 0.92)
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
            memory_cleanup_threshold = int((os.environ.get("ELYSIA_MEMORY_CLEANUP_THRESHOLD", "3500") if use_environment else "3500"))
        except (ValueError, TypeError):
            memory_cleanup_threshold = 3500

    # memory_filepath is canonical; memory_file is legacy alias
    _mem = cfg.get("memory_filepath") or cfg.get("memory_file")
    guardian_config = {
        "defer_heavy_startup": cfg.get("defer_heavy_startup", True),
        "trust_file": cfg.get("trust_file", "enhanced_trust.json"),
        "tasks_file": cfg.get("tasks_file", "enhanced_tasks.json"),
        "memory_cleanup_threshold": memory_cleanup_threshold,
        "enable_background_services": cfg.get("enable_background_services", True),
        "enable_resource_monitoring": cfg.get("enable_resource_monitoring", True),
        "enable_runtime_health_monitoring": cfg.get("enable_runtime_health_monitoring", True),
        "enable_upstream_routing_live_probes": cfg.get("enable_upstream_routing_live_probes", True),
        "resource_limits": {
            "memory_limit": memory_limit,
            "cpu_limit": res_cfg.get("cpu_limit", (_parse_resource_limit("ELYSIA_CPU_LIMIT", 0.9) if use_environment else 0.9)),
            "disk_limit": res_cfg.get("disk_limit", 0.9),
        },
        "ui_config": ui_config,
    }
    if _mem is not None:
        guardian_config["memory_filepath"] = _mem
    if not guardian_config["enable_background_services"]:
        guardian_config["enable_resource_monitoring"] = False
        guardian_config["enable_runtime_health_monitoring"] = False
        guardian_config["enable_upstream_routing_live_probes"] = False
        guardian_config["ui_config"]["auto_start"] = False
    return guardian_config


def describe_guardian_bootstrap(config: Optional[Dict[str, Any]] = None) -> GuardianBootstrapAudit:
    """Public audit/inspection entrypoint: configuration descriptor only.

    Equivalent to ``init_guardian_core(..., mode=\"audit\")``. Prefer this name
    when the caller intends inspection rather than activation.
    """
    return init_guardian_core(config, mode="audit")


def init_guardian_core(config: Optional[Dict[str, Any]] = None, *, mode: Literal["audit", "operational"]) -> Any:
    """Authoritative Guardian bootstrap boundary (Issue #23).

    ``mode`` is required and keyword-only — callers must choose explicitly:

    * ``audit`` — pure config descriptor (`GuardianBootstrapAudit`). Never
      imports/constructs GuardianCore, never starts monitoring/loop/UI/probes,
      never reads activation-related env overrides. Does **not** prove live
      runtime wiring.
    * ``operational`` — existing active bootstrap via singleton. May start
      background services when config allows. Opt out with
      ``enable_background_services=False`` (forces monitoring/probes/UI
      auto-start off at normalize time).

    Lower-level ``get_guardian_core`` / ``GuardianCore.__init__`` remain capable
    of activation when called directly; they are **not** the audit path.
    """
    if mode not in ("audit", "operational"):
        raise ValueError("mode must be 'audit' or 'operational'")
    if mode == "audit":
        # No project_guardian imports: keep audit free of construction side effects.
        return GuardianBootstrapAudit(_normalize_config(config, use_environment=False))

    logger.info("[1/5] Initializing Guardian Core...")
    try:
        from project_guardian.guardian_singleton import get_guardian_core, ensure_monitoring_started
        guardian_config = _normalize_config(config, use_environment=True)
        memory_limit = guardian_config["resource_limits"]["memory_limit"]
        guardian = get_guardian_core(config=guardian_config)
        if guardian:
            if guardian_config["enable_background_services"]:
                ensure_monitoring_started(guardian)
            logger.info("  [OK] Guardian Core initialized (singleton)")
            if memory_limit != 0.8:
                logger.info(f"  [Config] Memory limit: {memory_limit:.0%} (set via config or ELYSIA_MEMORY_LIMIT)")
            if guardian_config["enable_upstream_routing_live_probes"]:
                try:
                    from project_guardian.diagnostics.upstream_routing_live_probe import (
                        schedule_upstream_routing_live_probes,
                    )

                    schedule_upstream_routing_live_probes(guardian)
                except Exception as _diag_e:
                    logger.debug("upstream_routing_live_probe schedule: %s", _diag_e)
            return guardian
        logger.error("  [FAIL] Guardian Core initialization returned None")
        return None
    except Exception as e:
        logger.error(f"  [FAIL] Guardian Core failed: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return None
