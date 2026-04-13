#!/usr/bin/env python3
"""
Elysia Configuration
====================
Single place for Elysia paths, ports, limits, and settings.
Overridable via environment variables.
"""
import json
import os
import string
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

# Project root
PROJECT_ROOT = Path(__file__).parent

# Marker file on thumb drive root to identify "Elysia memory" drive (so letter can vary)
ELYSIA_MEMORY_DRIVE_MARKER = "ELYSIA_MEMORY"

# Status API
STATUS_HOST = os.environ.get("ELYSIA_STATUS_HOST", "127.0.0.1")
STATUS_PORT = int(os.environ.get("ELYSIA_STATUS_PORT", "8888"))
# Optional: when set, require Authorization: Bearer <token> for /chat and /v1/chat/completions
API_TOKEN = os.environ.get("ELYSIA_API_TOKEN", "").strip() or None

# Log file
LOG_FILE = PROJECT_ROOT / "elysia_unified.log"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT = 5

# USB memory policy (env ELYSIA_USB_MEMORY_POLICY). Default / recommended production: failover (unset or "failover").
USB_MEMORY_POLICY_HELP = (
    "ELYSIA_USB_MEMORY_POLICY — recommended: failover (default). "
    "failover: one active ElysiaMemory root (primary USB, else secondary, else ~/ElysiaMemory). "
    "mirror: only guardian_memory.json is copied to the secondary USB after MemoryCore JSON saves; "
    "trust/tasks/vectors are not mirrored. "
    "split: archive/backup path (get_backup_path / sync_to_backup) prefers secondary …/archive when "
    "that volume is usable; active memory/trust/tasks JSON files stay on the active root only."
)


def _parse_float_env(name: str, default: float) -> float:
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        v = float(val)
        if 0.0 <= v <= 1.0:
            return v
    except (ValueError, TypeError):
        pass
    return default


def _discover_elysia_marker_drives() -> list[str]:
    """All drive letters (Windows) whose root has ELYSIA_MEMORY / .elysia_memory; sorted."""
    found: list[str] = []
    if os.name != "nt":
        candidates = ["/media", "/mnt", "/Volumes"]
        for candidate in candidates:
            root = Path(candidate)
            if not root.exists():
                continue
            marker = root / ELYSIA_MEMORY_DRIVE_MARKER
            alt = root / ".elysia_memory"
            if marker.exists() or alt.exists():
                found.append(str(root))
        return sorted(found)

    for letter in string.ascii_uppercase:
        if letter in "AB":
            continue
        root = Path(f"{letter}:\\")
        if not root.exists():
            continue
        marker = root / ELYSIA_MEMORY_DRIVE_MARKER
        alt = root / ".elysia_memory"
        if marker.exists() or alt.exists():
            found.append(f"{letter}:")
    return sorted(found, key=lambda x: x[0])


def find_elysia_memory_drives() -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve primary and optional secondary Elysia USB roots (drive letters like 'F:').

    - ELYSIA_THUMB_DRIVE: primary override when present and the drive exists.
    - ELYSIA_THUMB_DRIVE_SECONDARY: secondary override when present and the drive exists.
    - ELYSIA_USB_MEMORY_POLICY: failover (default), mirror, or split — see USB_MEMORY_POLICY_HELP.
    - If not set, scans for ELYSIA_MEMORY marker volumes: first discovery = primary,
      next distinct letter = secondary (two-stick auto-pairing).

    Returns (primary, secondary). secondary may be None (single-volume / legacy).
    """
    discovered = _discover_elysia_marker_drives()

    primary: Optional[str] = None
    raw_p = os.environ.get("ELYSIA_THUMB_DRIVE", "").strip().upper()
    if raw_p:
        if len(raw_p) == 1:
            raw_p = raw_p + ":"
        root = Path(raw_p) / ""
        if root.exists():
            primary = raw_p
    elif discovered:
        primary = discovered[0]

    secondary: Optional[str] = None
    raw_s = os.environ.get("ELYSIA_THUMB_DRIVE_SECONDARY", "").strip().upper()
    if raw_s:
        if len(raw_s) == 1:
            raw_s = raw_s + ":"
        root_s = Path(raw_s) / ""
        if root_s.exists() and raw_s != primary:
            secondary = raw_s

    if secondary is None and discovered:
        for d in discovered:
            if primary is None or d != primary:
                secondary = d
                break

    return primary, secondary


def find_elysia_memory_drive() -> Optional[str]:
    """
    Find a thumb drive intended for Elysia memory storage (first of two if auto-discovered).
    - ELYSIA_THUMB_DRIVE env: use this letter (e.g. F:) if the drive exists.
    - Else: first drive whose root contains ELYSIA_MEMORY or .elysia_memory.
    """
    p, _ = find_elysia_memory_drives()
    return p


def get_storage_paths() -> Dict[str, Any]:
    """Get memory/trust/tasks file paths. Uses memory_storage_config if available.

    Two-USB behavior is controlled by ELYSIA_USB_MEMORY_POLICY; see USB_MEMORY_POLICY_HELP
    in this module for operator guidance (failover recommended for production).
    """
    base = {
        "memory_file": str(PROJECT_ROOT / "guardian_memory.json"),
        "trust_file": str(PROJECT_ROOT / "enhanced_trust.json"),
        "tasks_file": str(PROJECT_ROOT / "enhanced_tasks.json"),
        "storage_path": str(PROJECT_ROOT),
        "thumb_drive_available": False,
    }
    try:
        from memory_storage_config import (
            MemoryStorageConfig,
            MemoryUsbPolicy,
            register_active_memory_storage_config,
        )

        register_active_memory_storage_config(None)
        primary, secondary = find_elysia_memory_drives()
        primary_letter = primary or "F:"
        policy = MemoryUsbPolicy.from_env()
        storage = MemoryStorageConfig(
            primary_drive=primary_letter,
            secondary_drive=secondary,
            policy=policy,
            fallback_local=True,
        )
        register_active_memory_storage_config(storage)
        base.update(
            {
                "memory_file": str(storage.get_memory_file_path()),
                "trust_file": str(storage.get_trust_file_path()),
                "tasks_file": str(storage.get_tasks_file_path()),
            }
        )
        cfg = storage.get_config()
        base["storage_path"] = cfg.get("storage_path", base["storage_path"])
        base["thumb_drive_available"] = cfg.get("thumb_drive_available", False)
        for k in (
            "usb_memory_policy",
            "usb_primary_drive",
            "usb_secondary_drive",
            "usb_primary_root",
            "usb_secondary_root",
            "usb_primary_available",
            "usb_secondary_available",
            "usb_active_write_targets",
            "usb_archive_root",
            "usb_storage_degraded",
            "usb_degraded_notes",
        ):
            if k in cfg:
                base[k] = cfg[k]
    except Exception:
        try:
            from memory_storage_config import register_active_memory_storage_config

            register_active_memory_storage_config(None)
        except Exception:
            pass
    return base


def get_resource_limits() -> Dict[str, Any]:
    """Get resource limit config. Env: ELYSIA_MEMORY_LIMIT, ELYSIA_CPU_LIMIT."""
    return {
        "memory_limit": _parse_float_env("ELYSIA_MEMORY_LIMIT", 0.92),
        "cpu_limit": _parse_float_env("ELYSIA_CPU_LIMIT", 0.95),
        "disk_limit": 0.9,
    }


def get_hestia_config() -> Dict[str, str]:
    """Get Hestia bridge config."""
    return {
        "hestia_path": os.environ.get("ELYSIA_HESTIA_PATH", r"C:\Users\mrnat\Hestia"),
        "api_url": os.environ.get("ELYSIA_HESTIA_API", "http://localhost:8501"),
    }


def get_auto_learning_config() -> Dict[str, Any]:
    """Auto-learning: gather AI, income, ChatGPT chatlogs, etc. Store on thumb drive."""
    interval = float(os.environ.get("ELYSIA_LEARNING_INTERVAL_HOURS", "6"))
    enabled = os.environ.get("ELYSIA_AUTO_LEARNING", "true").lower() in ("1", "true", "yes")
    max_chat = int(os.environ.get("ELYSIA_LEARNING_MAX_CHATLOGS", "20"))
    return {
        "enabled": enabled,
        "interval_hours": max(1, min(24, interval)),
        "max_chatlogs": max(5, min(100, max_chat)),
    }


def get_elysia_config() -> Dict[str, Any]:
    """
    Build full Elysia config from centralized settings.
    Use this in elysia.py main() and elysia_interface.
    Canonical key: memory_filepath. memory_file kept for legacy compatibility.
    """
    paths = get_storage_paths()
    memory_path = paths["memory_file"]
    out = {
        "memory_filepath": memory_path,
        "memory_file": memory_path,  # legacy alias
        "trust_file": paths["trust_file"],
        "tasks_file": paths["tasks_file"],
        "storage_path": paths.get("storage_path"),
        "thumb_drive_available": paths.get("thumb_drive_available", False),
        "hestia": get_hestia_config(),
        "resource_limits": get_resource_limits(),
        "auto_learning": get_auto_learning_config(),
    }
    for k in (
        "usb_memory_policy",
        "usb_primary_drive",
        "usb_secondary_drive",
        "usb_primary_root",
        "usb_secondary_root",
        "usb_primary_available",
        "usb_secondary_available",
        "usb_active_write_targets",
        "usb_archive_root",
        "usb_storage_degraded",
        "usb_degraded_notes",
    ):
        if k in paths:
            out[k] = paths[k]
    return out


def get_status_url() -> str:
    """Full status API URL."""
    return f"http://{STATUS_HOST}:{STATUS_PORT}"


# Single-backend lock file (elysia.py only; lightweight PID + status URL)
BACKEND_LOCK_PATH = PROJECT_ROOT / ".elysia_backend.lock"


def _pid_is_running(pid: int) -> bool:
    """Best-effort: True if process `pid` appears to exist (Windows + POSIX)."""
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes

            k = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if h:
                k.CloseHandle(h)
                return True
            return False
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, OSError, AttributeError, TypeError, ValueError):
        return False


def probe_backend_alive(timeout: float = 2.0) -> bool:
    """
    True if an Elysia backend is already serving GET /status with a normal payload.
    Used to skip a second heavy boot and attach the interface instead.
    """
    try:
        import urllib.request

        req = urllib.request.Request(f"{get_status_url()}/status")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if getattr(r, "status", 200) != 200:
                return False
            body = r.read().decode("utf-8", errors="replace")
        data = json.loads(body)
        if not isinstance(data, dict):
            return False
        if data.get("error") and not data.get("uptime") and data.get("system") is None:
            return False
        return bool(
            "uptime" in data
            or data.get("system")
            or "components" in data
            or "running" in data
        )
    except Exception:
        return False


def try_acquire_backend_lock() -> Tuple[bool, str]:
    """
    Exclusive backend-instance lock (create before heavy UnifiedElysiaSystem init).
    Returns (True, "") on success, or (False, human detail) if another live backend holds it.
    """
    lock = BACKEND_LOCK_PATH
    while True:
        try:
            with open(lock, "x", encoding="utf-8") as f:
                f.write(f"{os.getpid()}\n{get_status_url()}\n")
            return True, ""
        except FileExistsError:
            pass
        except OSError as e:
            return False, f"Could not create backend lock file: {e}"
        raw = []
        try:
            raw = lock.read_text(encoding="utf-8", errors="replace").strip().split("\n")
            pid = int(raw[0]) if raw and raw[0].strip().isdigit() else -1
        except Exception:
            pid = -1
        url_line = (raw[1] if len(raw) > 1 else "").strip() or get_status_url()
        if pid > 0 and _pid_is_running(pid):
            return (
                False,
                f"Existing backend process PID {pid}. Status API: {url_line}/status",
            )
        try:
            lock.unlink(missing_ok=True)
        except OSError:
            return False, f"Remove stale lock manually: {lock}"


def release_backend_lock() -> None:
    """Remove backend lock if it belongs to this process."""
    try:
        lock = BACKEND_LOCK_PATH
        if not lock.is_file():
            return
        raw = lock.read_text(encoding="utf-8", errors="replace").strip().split("\n")
        if raw and raw[0].strip().isdigit() and int(raw[0]) == os.getpid():
            lock.unlink(missing_ok=True)
    except Exception:
        pass


def launch_attach_interface_standalone() -> None:
    """Run elysia_interface.py in attach-only mode (same interpreter)."""
    import runpy
    import sys

    iface = (PROJECT_ROOT / "elysia_interface.py").resolve()
    path = str(iface)
    saved = sys.argv[:]
    try:
        sys.argv = [path, "--attach-only"]
        runpy.run_path(path, run_name="__main__")
    finally:
        sys.argv = saved
