"""
Memory Storage Configuration
============================
Configures Elysia removable (USB) memory: primary + optional secondary volume,
with explicit policy (failover / mirror / split).

Operator summary (see project-root elysia_config.USB_MEMORY_POLICY_HELP for full text):
- **failover** (default, recommended): single active ElysiaMemory root.
- **mirror**: only guardian_memory.json is mirrored to the secondary USB after MemoryCore saves.
- **split**: archive/backup directory targets secondary …/archive when available; active JSON stays on active root.

Implementation note (default policy):
- Default is **failover**: one canonical write root (primary USB, else secondary, else local).
  Full dual-write on every subsystem would require hooks across trust/tasks/vectors; mirror
  mode therefore replicates **guardian_memory.json** after MemoryCore saves only, plus
  split-mode archive/backup routing below.
"""

from __future__ import annotations

import logging
import os
import shutil
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Set by get_storage_paths() in elysia_config when MemoryStorageConfig is constructed.
_ACTIVE_CONFIG: Optional["MemoryStorageConfig"] = None


class MemoryUsbPolicy(str, Enum):
    """How to use two USB memory roots (ElysiaMemory on each volume)."""

    FAILOVER = "failover"
    MIRROR = "mirror"
    SPLIT = "split"

    @classmethod
    def from_env(cls, raw: Optional[str] = None) -> "MemoryUsbPolicy":
        v = (raw if raw is not None else os.environ.get("ELYSIA_USB_MEMORY_POLICY", "failover"))
        v = (v or "failover").strip().lower()
        for m in cls:
            if m.value == v:
                return m
        logger.warning("Unknown ELYSIA_USB_MEMORY_POLICY=%r — using failover", v)
        return cls.FAILOVER


def register_active_memory_storage_config(cfg: Optional["MemoryStorageConfig"]) -> None:
    """Called from elysia_config.get_storage_paths; used for post-save USB mirror."""
    global _ACTIVE_CONFIG
    _ACTIVE_CONFIG = cfg


def notify_usb_persist_mirror(filepath: str) -> None:
    """Best-effort: mirror guardian_memory.json to secondary USB when policy=mirror."""
    if _ACTIVE_CONFIG is None:
        return
    try:
        _ACTIVE_CONFIG.replicate_file_to_mirrors(filepath)
    except Exception as e:
        logger.debug("notify_usb_persist_mirror: %s", e)


class MemoryStorageConfig:
    """
    Manages memory storage for Elysia: primary USB, optional secondary USB, local fallback.
    """

    def __init__(
        self,
        primary_drive: str = "F:",
        secondary_drive: Optional[str] = None,
        policy: MemoryUsbPolicy | str = MemoryUsbPolicy.FAILOVER,
        fallback_local: bool = True,
    ):
        if isinstance(policy, str):
            policy = MemoryUsbPolicy.from_env(policy)
        self.policy: MemoryUsbPolicy = policy
        self.fallback_local = fallback_local
        self.primary_drive = self._normalize_drive(primary_drive)
        self.secondary_drive = self._normalize_drive(secondary_drive) if secondary_drive else None

        self.primary_root = self._elysia_root(self.primary_drive)
        self.secondary_root: Optional[Path] = (
            self._elysia_root(self.secondary_drive) if self.secondary_drive else None
        )

        self.primary_available = self._is_root_usable(self.primary_root)
        self.secondary_available = (
            self._is_root_usable(self.secondary_root) if self.secondary_root else False
        )

        self._mirror_destination_roots: List[Path] = []
        self._archive_root: Optional[Path] = None
        self.storage_path = Path()
        self._degraded_notes: List[str] = []

        self.storage_path = self._determine_storage_path()
        self._usb_storage_degraded = bool(self._degraded_notes)

        logger.info("Memory storage configured: %s", self.storage_path)
        if self._degraded_notes:
            for line in self._degraded_notes:
                logger.warning("[USBMemory] %s", line)

    @staticmethod
    def _normalize_drive(drive: str) -> str:
        d = drive.strip().rstrip("\\/").upper()
        if len(d) == 1 and d.isalpha():
            return f"{d}:"
        if len(d) == 2 and d[1] == ":":
            return d
        return drive.strip()

    @staticmethod
    def _elysia_root(drive: str) -> Path:
        d = MemoryStorageConfig._normalize_drive(drive)
        return Path(f"{d}/ElysiaMemory")

    def _drive_exists(self, drive: str) -> bool:
        try:
            p = Path(MemoryStorageConfig._normalize_drive(drive))
            return p.exists() and p.is_dir()
        except OSError:
            return False

    def _is_root_usable(self, root: Path) -> bool:
        """True if drive exists and ElysiaMemory can be created and is writable."""
        try:
            parent = root.parent
            if not parent.exists() or not parent.is_dir():
                return False
            root.mkdir(parents=True, exist_ok=True)
            test = root / ".elysia_test"
            test.write_text("test", encoding="utf-8")
            test.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def _determine_storage_path(self) -> Path:
        p_root, s_root = self.primary_root, self.secondary_root
        p_ok, s_ok = self.primary_available, self.secondary_available

        if self.policy == MemoryUsbPolicy.SPLIT:
            return self._path_for_split(p_root, s_root, p_ok, s_ok)
        if self.policy == MemoryUsbPolicy.MIRROR:
            return self._path_for_mirror(p_root, s_root, p_ok, s_ok)
        return self._path_for_failover(p_root, s_root, p_ok, s_ok)

    def _path_for_failover(
        self,
        p_root: Path,
        s_root: Optional[Path],
        p_ok: bool,
        s_ok: bool,
    ) -> Path:
        if p_ok:
            if self.secondary_drive and not self._drive_exists(self.secondary_drive):
                self._degraded_notes.append(
                    "failover: secondary USB configured but not present; using primary only."
                )
            elif self.secondary_drive and not s_ok:
                self._degraded_notes.append(
                    "failover: secondary volume present but not writable; using primary only."
                )
            return p_root
        if p_root and not p_ok:
            self._degraded_notes.append(
                "failover: primary USB not available or not writable; trying secondary."
            )
        if s_root and s_ok:
            self._degraded_notes.append(
                "failover: using secondary USB as active storage (primary missing or failed)."
            )
            return s_root
        if s_root and not s_ok and self.secondary_drive and self._drive_exists(self.secondary_drive):
            self._degraded_notes.append(
                "failover: secondary present but not writable; falling back to local."
            )
        if self.fallback_local:
            self._degraded_notes.append(
                "failover: no writable USB root; using local fallback (see log)."
            )
            return self._get_local_fallback()
        return Path("elysia_memory")

    def _path_for_mirror(
        self,
        p_root: Path,
        s_root: Optional[Path],
        p_ok: bool,
        s_ok: bool,
    ) -> Path:
        # Canonical writes go to primary when possible; secondary receives copies of guardian_memory.json.
        if p_ok and s_ok:
            self._mirror_destination_roots = [s_root]
            return p_root
        if p_ok and not s_ok:
            self._degraded_notes.append(
                "mirror: secondary missing or not writable; writing primary only (no mirror copy)."
            )
            return p_root
        if not p_ok and s_ok:
            self._degraded_notes.append(
                "mirror: primary missing or not writable; using secondary as single active root (no mirror)."
            )
            return s_root
        self._degraded_notes.append(
            "mirror: neither USB root writable; using local fallback (no mirror)."
        )
        if self.fallback_local:
            return self._get_local_fallback()
        return Path("elysia_memory")

    def _path_for_split(
        self,
        p_root: Path,
        s_root: Optional[Path],
        p_ok: bool,
        s_ok: bool,
    ) -> Path:
        # Active memory/trust/tasks: prefer primary USB; else same failover as failover policy.
        active = p_root if p_ok else None
        if active is None and s_ok:
            self._degraded_notes.append(
                "split: primary USB not available; active data on secondary (archive path adjusted)."
            )
            active = s_root
        if active is None:
            self._degraded_notes.append(
                "split: no USB root writable for active data; using local fallback."
            )
            if self.fallback_local:
                active = self._get_local_fallback()
            else:
                active = Path("elysia_memory")

        # Archive / checkpoints: secondary when available; else folder under active storage.
        if self.policy == MemoryUsbPolicy.SPLIT and s_ok and s_root is not None:
            ar = s_root / "archive"
            try:
                ar.mkdir(parents=True, exist_ok=True)
                self._archive_root = ar
            except Exception:
                self._archive_root = active / "archive"
                self._degraded_notes.append(
                    "split: could not create secondary archive root; using active/archive."
                )
        else:
            if self.secondary_drive and not s_ok:
                self._degraded_notes.append(
                    "split: secondary USB missing or not writable; archive under active storage."
                )
            self._archive_root = active / "archive"
            try:
                self._archive_root.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

        return active

    def _get_local_fallback(self) -> Path:
        local_path = Path.home() / "ElysiaMemory"
        local_path.mkdir(parents=True, exist_ok=True)
        logger.info("Using local fallback storage: %s", local_path)
        return local_path

    def replicate_file_to_mirrors(self, filepath: str) -> None:
        """Copy a file into each mirror root (same basename)."""
        if self.policy != MemoryUsbPolicy.MIRROR or not self._mirror_destination_roots:
            return
        src = Path(filepath)
        if not src.is_file():
            return
        for root in self._mirror_destination_roots:
            dest = root / src.name
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
            except Exception as e:
                logger.warning("[USBMemory] mirror copy failed -> %s: %s", dest, e)

    def get_memory_file_path(self, filename: str = "guardian_memory.json") -> Path:
        return self.storage_path / filename

    def get_trust_file_path(self, filename: str = "enhanced_trust.json") -> Path:
        return self.storage_path / filename

    def get_tasks_file_path(self, filename: str = "enhanced_tasks.json") -> Path:
        return self.storage_path / filename

    def get_backup_path(self) -> Path:
        if self.policy == MemoryUsbPolicy.SPLIT and self._archive_root is not None:
            backup_path = self._archive_root / "backups"
        else:
            backup_path = self.storage_path / "backups"
        backup_path.mkdir(parents=True, exist_ok=True)
        return backup_path

    def get_config(self) -> Dict[str, Any]:
        thumb_any = self.primary_available or self.secondary_available
        active_writes = [str(self.storage_path)]
        if self.policy == MemoryUsbPolicy.MIRROR and self._mirror_destination_roots:
            active_writes.extend(str(p) for p in self._mirror_destination_roots)

        return {
            "storage_path": str(self.storage_path),
            "thumb_drive": self.primary_drive,
            "thumb_drive_available": thumb_any,
            "fallback_local": self.fallback_local,
            "memory_file": str(self.get_memory_file_path()),
            "trust_file": str(self.get_trust_file_path()),
            "tasks_file": str(self.get_tasks_file_path()),
            # Two-USB diagnostics (explicit)
            "usb_memory_policy": self.policy.value,
            "usb_primary_drive": self.primary_drive,
            "usb_secondary_drive": self.secondary_drive,
            "usb_primary_root": str(self.primary_root),
            "usb_secondary_root": str(self.secondary_root) if self.secondary_root else "",
            "usb_primary_available": self.primary_available,
            "usb_secondary_available": self.secondary_available,
            "usb_active_write_targets": active_writes,
            "usb_archive_root": str(self._archive_root) if self._archive_root else "",
            "usb_storage_degraded": self._usb_storage_degraded,
            "usb_degraded_notes": list(self._degraded_notes),
        }

    def sync_to_backup(self) -> bool:
        """Sync memory files to backup location (respects split archive root)."""
        try:
            backup_path = self.get_backup_path()
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            for file_type in ["memory", "trust", "tasks"]:
                source_file = getattr(self, f"get_{file_type}_file_path")()
                if source_file.exists():
                    backup_file = backup_path / f"{file_type}_{timestamp}.json"
                    shutil.copy2(source_file, backup_file)

            logger.info("Backed up memory files to %s", backup_path)
            return True
        except Exception as e:
            logger.error("Backup failed: %s", e)
            return False


if __name__ == "__main__":
    config = MemoryStorageConfig(primary_drive="F:", secondary_drive="G:")
    for key, value in config.get_config().items():
        print(f"  {key}: {value}")
