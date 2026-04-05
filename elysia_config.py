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


def find_elysia_memory_drive() -> Optional[str]:
    """
    Find a thumb drive intended for Elysia memory storage.
    - ELYSIA_THUMB_DRIVE env: use this letter (e.g. F:) if the drive exists.
    - Else: look for a drive whose root contains the marker file ELYSIA_MEMORY
      (so the same stick works on any PC regardless of drive letter).
    - Candidate letters: D:, E:, F:, G:, H: (or all removable letters on Windows).
    Returns drive letter like "F:" or None.
    """
    # Explicit override
    env_drive = os.environ.get("ELYSIA_THUMB_DRIVE", "").strip().upper()
    if env_drive:
        if len(env_drive) == 1:
            env_drive = env_drive + ":"
        root = Path(env_drive) / ""
        if root.exists():
            return env_drive
        # Env set but drive missing - don't scan, caller will use fallback
        return None

    # No env: look for marker file on candidate drives
    if os.name == "nt":
        candidates = [f"{d}:\\" for d in string.ascii_uppercase if d not in "AB"]  # skip A:, B:
    else:
        # Linux/mac: common mount points
        candidates = ["/media", "/mnt", "/Volumes"]
    for candidate in candidates:
        root = Path(candidate)
        if not root.exists():
            continue
        marker = root / ELYSIA_MEMORY_DRIVE_MARKER
        alt = root / ".elysia_memory"
        if marker.exists() or alt.exists():
            if os.name == "nt" and candidate.endswith("\\"):
                return candidate[0] + ":"
            return candidate
    return None


def get_storage_paths() -> Dict[str, Any]:
    """Get memory/trust/tasks file paths. Uses memory_storage_config if available."""
    base = {
        "memory_file": str(PROJECT_ROOT / "guardian_memory.json"),
        "trust_file": str(PROJECT_ROOT / "enhanced_trust.json"),
        "tasks_file": str(PROJECT_ROOT / "enhanced_tasks.json"),
        "storage_path": str(PROJECT_ROOT),
        "thumb_drive_available": False,
    }
    try:
        from memory_storage_config import MemoryStorageConfig
        thumb = find_elysia_memory_drive() or "F:"  # prefer detected drive, else default F:
        storage = MemoryStorageConfig(thumb_drive=thumb, fallback_local=True)
        base.update({
            "memory_file": str(storage.get_memory_file_path()),
            "trust_file": str(storage.get_trust_file_path()),
            "tasks_file": str(storage.get_tasks_file_path()),
        })
        cfg = storage.get_config()
        base["storage_path"] = cfg.get("storage_path", base["storage_path"])
        base["thumb_drive_available"] = cfg.get("thumb_drive_available", False)
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
    return {
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
