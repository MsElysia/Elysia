"""
Contained Windows browser-memory acceptance startup.

Builds an explicit Guardian/Elysia configuration whose durable writes stay under
a disposable root, with providers, autonomy, learning, SMTP usage, external
storage, and background workers disabled via existing config keys.

Does not retarget the desktop launcher, load personal memory/credentials, or
start the dashboard unless the caller enables ui_config.auto_start.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

# One-shot operator consent for replacing an unreadable primary memory store
# with the latest readable snapshot. Lives beside the store under the
# disposable root; it is renamed (never silently reused) by the launch that
# sees it, whatever the outcome.
RESTORE_MARKER_NAME = "RESTORE_MEMORY_FROM_SNAPSHOT"

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


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _rename_unique(path: Path, suffix: str) -> str:
    """Rename ``path`` to ``<path>.<suffix>-<UTC stamp>[.n]`` and return the new name."""
    base = f"{path}.{suffix}-{_utc_stamp()}"
    target = Path(base)
    n = 1
    while target.exists():
        target = Path(f"{base}.{n}")
        n += 1
    os.replace(path, target)
    return str(target)


def _primary_content_readable(memory_filepath: str) -> Tuple[bool, Optional[str]]:
    """Independent check of the primary bytes, using MemoryCore.load()'s own rule.

    Distinguishes a store whose *content* is unreadable (restore is meaningful)
    from a fence raised for another reason, e.g. the sidecar lock being held by
    another process (restore would clobber a healthy store).
    """
    try:
        with open(memory_filepath, "rb") as handle:
            decoded = json.loads(handle.read().decode("utf-8"))
    except FileNotFoundError:
        return True, None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"[:200]
    if not isinstance(decoded, list) or any(not isinstance(x, dict) for x in decoded):
        return False, "ValueError: memory history must be a JSON list of records"
    return True, None


def _snapshot_manager(config: Dict[str, Any]):
    from project_guardian.memory_snapshot import MemorySnapshot

    snapshot_config = config.get("snapshot_config") or {}
    return MemorySnapshot(
        snapshot_dir=snapshot_config.get("snapshot_dir", "memory/snapshots"),
        backup_shards=int(snapshot_config.get("backup_shards", 3)),
        retention_days=int(snapshot_config.get("retention_days", 30)),
    )


def _describe_snapshot(path: Optional[str]) -> Dict[str, Any]:
    info: Dict[str, Any] = {"path": path, "memory_count": None, "timestamp": None}
    if not path:
        return info
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        memories = data.get("memories") if isinstance(data, dict) else None
        info["memory_count"] = len(memories) if isinstance(memories, list) else None
        info["timestamp"] = data.get("timestamp") if isinstance(data, dict) else None
    except Exception:
        pass
    return info


def preflight_memory_store(config: Dict[str, Any]) -> Dict[str, Any]:
    """Make sure the primary memory store can carry a GuardianCore boot.

    GuardianCore writes startup diagnostics through ``MemoryCore.remember`` while
    constructing itself; on a fenced (unreadable) primary that raises, so the
    application cannot start and the operator can never reach the in-app
    restore. This runs first and reports one of:

    * ``readable`` -- nothing touched.
    * ``restored`` -- the primary content was unreadable, a readable snapshot
      exists, and the operator consented by creating ``RESTORE_MARKER_NAME``
      beside the store. The restore keeps the unreadable bytes as a
      ``.pre-restore.`` sidecar (``MemorySnapshot.restore_from_snapshot``).

    Otherwise ``ContainedStartupError`` names the store, the load error, the
    newest readable snapshot (if any) and the exact opt-in, and leaves every
    file as it was. Nothing is restored automatically: a fence that is not a
    content problem (for example the sidecar lock held by another process)
    never triggers a restore and leaves the marker alone. Otherwise the marker
    is consumed (renamed) by the launch that evaluates it, whatever the result.
    """
    from project_guardian.memory import MemoryCore

    memory_filepath = str(config.get("memory_filepath") or config.get("memory_file") or "")
    if not memory_filepath:
        raise ContainedStartupError("Contained config has no memory_filepath; cannot check the memory store.")
    marker = Path(memory_filepath).parent / RESTORE_MARKER_NAME
    report: Dict[str, Any] = {
        "status": None,
        "memory_filepath": memory_filepath,
        "memory_count": None,
        "load_error": None,
        "snapshot": None,
        "restore": None,
        "preserved_original": None,
        "marker": None,
    }

    probe = MemoryCore(memory_filepath, enable_timeline_logging=False)
    if not probe.persistence_blocked:
        report["status"] = "readable"
        report["memory_count"] = len(probe.memory_log)
        if marker.exists():
            report["marker"] = _rename_unique(marker, "ignored")
            logger.warning(
                "Memory restore marker %s found but %s is readable (%d memories); marker renamed to %s and ignored",
                marker, memory_filepath, len(probe.memory_log), report["marker"],
            )
        return report

    report["load_error"] = probe.last_load_error
    content_ok, content_error = _primary_content_readable(memory_filepath)
    if content_ok:
        raise ContainedStartupError(
            f"Memory store {memory_filepath} could not be loaded ({probe.last_load_error}) although its "
            "content parses. This is not corruption (another process may hold the store lock); "
            "no restore was attempted and nothing was changed. Stop the other Elysia process and relaunch."
        )

    manager = _snapshot_manager(config)
    latest = manager.get_latest_snapshot() or manager.get_latest_daily_snapshot()
    report["snapshot"] = _describe_snapshot(latest)
    consent = marker.exists()
    if consent:
        report["marker"] = _rename_unique(marker, "consumed")

    if not consent:
        if latest:
            snap = report["snapshot"]
            how = (
                f"The newest readable snapshot is {latest} ({snap['memory_count']} memories, "
                f"taken {snap['timestamp']}). To replace the unreadable store with it, create an empty "
                f"file named {RESTORE_MARKER_NAME} at {marker} and relaunch; the unreadable bytes are kept "
                f"beside the store as {Path(memory_filepath).name}.pre-restore.<stamp>."
            )
        else:
            how = (
                f"No readable snapshot exists under {manager.snapshot_dir}, so nothing can be restored "
                "automatically. Repair or replace the store by hand; the original is left in place."
            )
        raise ContainedStartupError(
            f"Memory store {memory_filepath} is unreadable ({content_error}); the application cannot "
            f"start on it and no file was changed. {how}"
        )

    if not latest:
        raise ContainedStartupError(
            f"Memory store {memory_filepath} is unreadable ({content_error}) and {RESTORE_MARKER_NAME} was "
            f"present (renamed to {report['marker']}), but no readable snapshot exists under "
            f"{manager.snapshot_dir}. Nothing was changed."
        )

    restored = manager.restore_from_snapshot(latest, probe)
    report["restore"] = dict(manager.last_restore_report)
    report["preserved_original"] = report["restore"].get("preserved_original")
    if not restored or probe.persistence_blocked:
        raise ContainedStartupError(
            f"Memory store {memory_filepath} is unreadable ({content_error}); restore from {latest} failed "
            f"({report['restore'].get('error')}). Marker renamed to {report['marker']}; original store "
            f"{'kept at ' + str(report['preserved_original']) if report['preserved_original'] else 'left in place'}."
        )
    report["status"] = "restored"
    report["memory_count"] = len(probe.memory_log)
    logger.warning(
        "Memory store %s was unreadable (%s); restored %d memories from %s on operator request. "
        "Unreadable original kept at %s.",
        memory_filepath, content_error, report["memory_count"],
        report["restore"].get("source_path") or latest, report["preserved_original"],
    )
    return report


def snapshot_memory_on_startup(guardian: Any) -> Dict[str, Any]:
    """Take a memory snapshot after a healthy boot and apply the configured retention.

    This is the only routine producer of snapshots in the contained
    application; without it the recovery path has nothing to restore from.
    A failure here is reported, never raised: it must not stop a boot that
    already has a readable store.
    """
    report: Dict[str, Any] = {"path": None, "persisted": False, "skipped": None, "removed_old": 0, "error": None}
    manager = getattr(guardian, "memory_snapshot", None)
    create = getattr(guardian, "create_memory_snapshot", None)
    if manager is None or not callable(create):
        report["skipped"] = "guardian has no memory snapshot support"
        return report
    memory = getattr(guardian, "memory", None)
    json_memory = getattr(memory, "json_memory", memory)
    if getattr(json_memory, "persistence_blocked", False):
        report["skipped"] = f"memory store fenced: {getattr(json_memory, 'last_load_error', None)}"
        logger.warning("Startup snapshot skipped; %s", report["skipped"])
        return report
    try:
        path = create()
        last = dict(getattr(manager, "last_snapshot_report", {}) or {})
        report["path"] = path or None
        report["persisted"] = bool(path) and bool(last.get("persisted", bool(path)))
        report["error"] = last.get("error")
        if report["persisted"]:
            report["removed_old"] = int(manager.cleanup_old_snapshots() or 0)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"[:200]
    if report["persisted"]:
        logger.info("Startup memory snapshot written: %s (expired %d old)", report["path"], report["removed_old"])
    else:
        logger.warning("Startup memory snapshot not written: %s", report["error"])
    return report


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

    # A fenced primary would make GuardianCore's own startup writes raise deep
    # inside construction; check (and, only on explicit request, recover) first.
    config["memory_preflight"] = preflight_memory_store(config)

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

    config["startup_snapshot"] = snapshot_memory_on_startup(guardian)

    return guardian, config


def list_active_non_main_threads() -> List[str]:
    """Names of non-main threads still alive (for worker-start checks)."""
    main = threading.main_thread()
    return [t.name for t in threading.enumerate() if t is not main and t.is_alive()]
