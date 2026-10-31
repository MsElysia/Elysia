"""
Contained Windows browser-memory acceptance startup.

Builds an explicit Guardian/Elysia configuration whose durable writes stay under
a disposable root, with providers, autonomy, learning, SMTP usage, external
storage, and background workers disabled via existing config keys.

Does not retarget the desktop launcher, load personal memory/credentials, or
start the dashboard unless the caller enables ui_config.auto_start.
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

_PROVIDER_ENV_VARS = (
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "COHERE_API_KEY",
    "HUGGINGFACE_API_KEY",
    "REPLICATE_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
    "BRAVE_SEARCH_API_KEY",
    "GUMROAD_ACCESS_TOKEN",
    "STRIPE_SECRET_KEY",
    "STRIPE_PUBLISHABLE_KEY",
    "ANTHROPIC_API_KEY",
    "SMTP_PASSWORD",
    "ELYSIA_SMTP_PASSWORD",
)


class ContainedStartupError(RuntimeError):
    """Raised when contained startup cannot proceed with useful diagnostics."""


def _as_path(root: Path | str) -> Path:
    return Path(root).expanduser().resolve()


def build_contained_startup_config(
    disposable_root: Path | str,
    *,
    ui_enabled: bool = False,
    ui_auto_start: bool = False,
    ui_host: str = "127.0.0.1",
    ui_port: int = 5000,
) -> Dict[str, Any]:
    """
    Return a GuardianCore/init_guardian_core config that keeps writes local.

    Does not call get_elysia_config()/USB discovery. Paths are absolute under
    disposable_root. Personal project memory and API key folders are not used.
    """
    root = _as_path(disposable_root)
    memory_dir = root / "memory"
    data_dir = root / "data"
    reports_dir = root / "REPORTS"
    tasks_dir = root / "TASKS"
    mutations_dir = root / "MUTATIONS"
    snapshots_dir = root / "memory" / "snapshots"
    for d in (memory_dir, data_dir, reports_dir, tasks_dir, mutations_dir, snapshots_dir):
        d.mkdir(parents=True, exist_ok=True)

    memory_filepath = memory_dir / "guardian_memory.json"
    if not memory_filepath.exists():
        memory_filepath.write_text("[]", encoding="utf-8")

    control_path = root / "CONTROL.md"
    if not control_path.exists():
        control_path.write_text(
            "# Contained acceptance CONTROL\n\nDisposable workspace. Not production.\n",
            encoding="utf-8",
        )

    return {
        "contained_startup": True,
        "disposable_root": str(root),
        "memory_filepath": str(memory_filepath),
        "memory_file": str(memory_filepath),
        "trust_file": str(data_dir / "enhanced_trust.json"),
        "tasks_file": str(data_dir / "enhanced_tasks.json"),
        "storage_path": str(root),
        "control_path": str(control_path),
        "tasks_dir": str(tasks_dir),
        "mutations_dir": str(mutations_dir),
        "review_queue_file": str(reports_dir / "review_queue.jsonl"),
        "approval_store_file": str(reports_dir / "approval_store.json"),
        "prompt_evolver_path": str(data_dir / "prompt_evolver.json"),
        "timeline_db_path": str(data_dir / "elysia_timeline.db"),
        "trust_policy_path": str(data_dir / "trust_policies.json"),
        "trust_audit_path": str(data_dir / "trust_audit_log.json"),
        "trust_escalation_path": str(data_dir / "escalation_queue.json"),
        "capability_data_dir": str(data_dir),
        "eai_lineage_registry_path": str(data_dir / "eai_lineage_registry.json"),
        "eai_audit_log_path": str(data_dir / "eai_assessments.jsonl"),
        "eai_alert_state_path": str(data_dir / "eai_alert_state.json"),
        "enable_eai_safety": False,
        "snapshot_config": {
            "snapshot_dir": str(snapshots_dir),
            "backup_shards": 1,
            "retention_days": 1,
        },
        "guardian_layer_config": {
            "enabled": True,
            "config_path": str(data_dir / "guardian.json"),
            "rebuild_log_path": str(data_dir / "guardian_rebuild.log"),
        },
        "defer_heavy_startup": True,
        "enable_vector_memory": False,
        "use_external_storage": False,
        "_test_skip_external_storage": True,
        "_skip_api_key_load": True,
        "_force_new_guardian": True,
        "enable_resource_monitoring": False,
        "enable_runtime_health_monitoring": False,
        "start_background_workers": False,
        "auto_learning": {
            "enabled": False,
            "interval_hours": 24,
            "max_chatlogs": 0,
        },
        "autonomy_config": {
            "enabled": False,
            "interval_seconds": 3600,
            "use_mistral_decision_engine": False,
            "allowed_actions": [],
            "self_generated_tasks": False,
            "max_actions_per_hour": 0,
            "idle_capability_probe": False,
            "allow_dynamic_capability_actions": False,
            "enable_moltbook_direction_guidance": False,
            "enable_chatlog_direction_guidance": False,
        },
        "ui_config": {
            "enabled": bool(ui_enabled),
            "auto_start": bool(ui_auto_start and ui_enabled),
            "host": ui_host,
            "port": int(ui_port),
            "debug": False,
        },
        "resource_limits": {
            "memory_limit": 0.95,
            "cpu_limit": 0.95,
            "disk_limit": 0.95,
            "disk_path": str(root),
        },
        "thumb_drive_available": False,
    }


@contextmanager
def scrub_provider_env(*, restore: bool = False) -> Iterator[Dict[str, Optional[str]]]:
    """Remove provider/credential env vars in this process only.

    Contained acceptance keeps them cleared for process lifetime (restore=False).
    """
    saved: Dict[str, Optional[str]] = {}
    for name in _PROVIDER_ENV_VARS:
        saved[name] = os.environ.pop(name, None)
    try:
        yield saved
    finally:
        if restore:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def scrub_provider_env_inplace() -> Dict[str, Optional[str]]:
    """Clear provider env for the remainder of this process; return prior values."""
    saved: Dict[str, Optional[str]] = {}
    for name in _PROVIDER_ENV_VARS:
        saved[name] = os.environ.pop(name, None)
    return saved


def start_contained_guardian(
    disposable_root: Path | str,
    *,
    ui_enabled: bool = False,
    ui_auto_start: bool = False,
    ui_host: str = "127.0.0.1",
    ui_port: int = 5000,
) -> Tuple[Any, Dict[str, Any]]:
    """
    Start a real GuardianCore through init_guardian_core with contained config.

    Returns (guardian, config). Does not start the dashboard unless ui_auto_start
    is True. Caller should shut down / reset singleton when finished.
    """
    root = _as_path(disposable_root)
    if not root.exists():
        raise ContainedStartupError(
            f"Disposable root does not exist: {root}. "
            "Create it or pass a writable path under the acceptance workspace."
        )
    if not root.is_dir():
        raise ContainedStartupError(
            f"Disposable root must be a directory, got non-directory path: {root}."
        )
    if not os.access(root, os.W_OK):
        raise ContainedStartupError(
            f"Disposable root is not writable: {root}."
        )

    config = build_contained_startup_config(
        root,
        ui_enabled=ui_enabled,
        ui_auto_start=ui_auto_start,
        ui_host=ui_host,
        ui_port=ui_port,
    )

    # Avoid USB / ~/ElysiaMemory discovery for this process.
    os.environ.pop("ELYSIA_THUMB_DRIVE", None)
    os.environ.pop("ELYSIA_THUMB_DRIVE_SECONDARY", None)
    os.environ["ELYSIA_AUTO_LEARNING"] = "false"
    scrub_provider_env_inplace()

    try:
        from project_guardian.guardian_singleton import reset_singleton

        reset_singleton()
    except Exception as e:
        logger.debug("singleton reset before contained start: %s", e)

    from elysia_sub_guardian import init_guardian_core

    try:
        guardian = init_guardian_core(config=config)
    except Exception as e:
        raise ContainedStartupError(
            f"Contained GuardianCore startup failed: {type(e).__name__}: {e}"
        ) from e

    if guardian is None:
        raise ContainedStartupError(
            "init_guardian_core returned None. Check logs above for the Guardian "
            "initialization failure; contained config was not applied to a live core."
        )

    # Hard assertions for containment invariants the caller can trust.
    resolved = str(getattr(guardian, "config", {}).get("memory_filepath") or "")
    try:
        Path(resolved).resolve().relative_to(root)
    except Exception:
        raise ContainedStartupError(
            f"Resolved memory_filepath escaped disposable root: {resolved!r} "
            f"(root={root})"
        )
    auto = guardian._load_autonomy_config() if hasattr(guardian, "_load_autonomy_config") else {}
    if auto.get("enabled", True):
        raise ContainedStartupError(
            f"Autonomy remained enabled after contained startup: {auto!r}"
        )
    present = [v for v in _PROVIDER_ENV_VARS if os.environ.get(v)]
    if present:
        raise ContainedStartupError(
            f"Provider credential env vars still present after scrub: {present}"
        )

    return guardian, config


def list_active_non_main_threads() -> List[str]:
    """Names of non-main threads still alive (for worker-start checks)."""
    main = threading.main_thread()
    return [t.name for t in threading.enumerate() if t is not main and t.is_alive()]
