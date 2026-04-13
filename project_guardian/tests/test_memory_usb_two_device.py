# Tests: two-USB memory policy parsing and MemoryStorageConfig (local fallback paths).

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_project_root = Path(__file__).resolve().parent.parent.parent
_core = _project_root / "core_modules" / "elysia_core_comprehensive"
if str(_core) not in sys.path:
    sys.path.insert(0, str(_core))

from memory_storage_config import MemoryStorageConfig, MemoryUsbPolicy  # noqa: E402


def test_memory_usb_policy_from_env() -> None:
    assert MemoryUsbPolicy.from_env("mirror") is MemoryUsbPolicy.MIRROR
    assert MemoryUsbPolicy.from_env("split") is MemoryUsbPolicy.SPLIT
    assert MemoryUsbPolicy.from_env("failover") is MemoryUsbPolicy.FAILOVER
    assert MemoryUsbPolicy.from_env("bogus") is MemoryUsbPolicy.FAILOVER


def test_failover_uses_local_when_no_usb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MemoryStorageConfig, "_is_root_usable", lambda self, root: False)
    monkeypatch.setattr(MemoryStorageConfig, "_drive_exists", lambda self, d: False)
    cfg = MemoryStorageConfig(
        primary_drive="Z:",
        secondary_drive="Y:",
        policy=MemoryUsbPolicy.FAILOVER,
        fallback_local=True,
    )
    assert cfg.storage_path == Path.home() / "ElysiaMemory"
    assert cfg.get_config()["usb_storage_degraded"] is True
    notes = cfg.get_config()["usb_degraded_notes"]
    assert any("no writable USB" in n for n in notes)


def test_split_sets_archive_under_active_when_secondary_bad(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def usable(self, root: Path) -> bool:
        return "primary_usb" in str(root)

    monkeypatch.setattr(MemoryStorageConfig, "_is_root_usable", usable)
    monkeypatch.setattr(MemoryStorageConfig, "_drive_exists", lambda self, d: True)
    cfg = MemoryStorageConfig(
        primary_drive=str(tmp_path / "primary_usb"),
        secondary_drive=str(tmp_path / "missing_secondary"),
        policy=MemoryUsbPolicy.SPLIT,
        fallback_local=False,
    )
    assert "primary_usb" in str(cfg.storage_path)
    assert cfg.get_backup_path().parent.name in ("archive", "primary_usb") or "archive" in str(
        cfg.get_backup_path()
    )
