"""
Deterministic intercepted tests for contained Windows browser-memory startup.

Does not bind the dashboard, exercise legacy autonomy routes against real
components, load personal memory/credentials, or activate providers.
"""

from __future__ import annotations

import builtins
import os
import threading
from pathlib import Path
from typing import Any, List, Set
from unittest import mock

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(_ROOT))


class _WriteInterceptor:
    """Record filesystem write destinations; classify containment violations."""

    def __init__(self, allowed_root: Path):
        self.allowed_root = allowed_root.resolve()
        self.writes: List[Path] = []
        self.violations: List[str] = []
        self._orig_open = builtins.open
        self._orig_path_write_text = Path.write_text
        self._orig_path_write_bytes = Path.write_bytes
        self._orig_path_mkdir = Path.mkdir
        self._orig_path_touch = Path.touch
        self._orig_path_open = Path.open
        self._orig_replace = os.replace

    def _normalize(self, path: Any) -> Path:
        return Path(path).resolve()

    def _is_allowed(self, path: Path) -> bool:
        try:
            path.relative_to(self.allowed_root)
            return True
        except ValueError:
            return False

    def _record_write(self, path: Any, via: str) -> None:
        p = self._normalize(path)
        self.writes.append(p)
        if not self._is_allowed(p):
            self.violations.append(f"{via}:{p}")

    def install(self):
        tracker = self
        orig_open = self._orig_open
        orig_write_text = self._orig_path_write_text
        orig_write_bytes = self._orig_path_write_bytes
        orig_mkdir = self._orig_path_mkdir
        orig_touch = self._orig_path_touch
        orig_path_open = self._orig_path_open
        orig_replace = self._orig_replace

        def open_hook(file, mode="r", *args, **kwargs):
            mode_s = str(mode)
            if any(c in mode_s for c in "wax") or ("+" in mode_s):
                tracker._record_write(file, f"open[{mode_s}]")
            return orig_open(file, mode, *args, **kwargs)

        def write_text_hook(path_self, data, *args, **kwargs):
            tracker._record_write(path_self, "Path.write_text")
            return orig_write_text(path_self, data, *args, **kwargs)

        def write_bytes_hook(path_self, data, *args, **kwargs):
            tracker._record_write(path_self, "Path.write_bytes")
            return orig_write_bytes(path_self, data, *args, **kwargs)

        def mkdir_hook(path_self, *args, **kwargs):
            tracker._record_write(path_self, "Path.mkdir")
            return orig_mkdir(path_self, *args, **kwargs)

        def touch_hook(path_self, *args, **kwargs):
            tracker._record_write(path_self, "Path.touch")
            return orig_touch(path_self, *args, **kwargs)

        def path_open_hook(path_self, mode="r", *args, **kwargs):
            if any(c in str(mode) for c in "wax") or ("+" in str(mode)):
                tracker._record_write(path_self, f"Path.open[{mode}]")
            return orig_path_open(path_self, mode, *args, **kwargs)

        def replace_hook(src, dst, *args, **kwargs):
            tracker._record_write(dst, "os.replace")
            return orig_replace(src, dst, *args, **kwargs)

        builtins.open = open_hook  # type: ignore[assignment]
        Path.write_text = write_text_hook  # type: ignore[method-assign,assignment]
        Path.write_bytes = write_bytes_hook  # type: ignore[method-assign,assignment]
        Path.mkdir = mkdir_hook  # type: ignore[method-assign,assignment]
        Path.touch = touch_hook  # type: ignore[method-assign,assignment]
        Path.open = path_open_hook  # type: ignore[method-assign,assignment]
        os.replace = replace_hook  # type: ignore[assignment]

    def uninstall(self):
        builtins.open = self._orig_open
        Path.write_text = self._orig_path_write_text  # type: ignore[method-assign]
        Path.write_bytes = self._orig_path_write_bytes  # type: ignore[method-assign]
        Path.mkdir = self._orig_path_mkdir  # type: ignore[method-assign]
        Path.touch = self._orig_path_touch  # type: ignore[method-assign]
        Path.open = self._orig_path_open  # type: ignore[method-assign]
        os.replace = self._orig_replace


@pytest.fixture
def disposable(tmp_path, monkeypatch):
    root = tmp_path / "disposable"
    root.mkdir()
    temp = root / "temp"
    temp.mkdir()
    monkeypatch.setenv("TEMP", str(temp))
    monkeypatch.setenv("TMP", str(temp))
    monkeypatch.setenv("TMPDIR", str(temp))
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setenv("ELYSIA_AUTO_LEARNING", "false")
    monkeypatch.delenv("ELYSIA_THUMB_DRIVE", raising=False)
    monkeypatch.delenv("ELYSIA_THUMB_DRIVE_SECONDARY", raising=False)
    for key in (
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "SMTP_PASSWORD",
        "ELYSIA_SMTP_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)
    return root


@pytest.fixture
def reset_guardian():
    yield
    try:
        from project_guardian.guardian_singleton import reset_singleton

        reset_singleton()
    except Exception:
        pass
    try:
        from project_guardian.core import GuardianCore

        GuardianCore._any_instance_initialized = False
    except Exception:
        pass


class TestContainedStartupConfig:
    def test_build_config_points_only_at_disposable(self, disposable):
        from project_guardian.contained_startup import build_contained_startup_config

        cfg = build_contained_startup_config(disposable)
        root = disposable.resolve()
        for key in (
            "memory_filepath",
            "trust_file",
            "tasks_file",
            "storage_path",
            "control_path",
            "tasks_dir",
            "mutations_dir",
            "review_queue_file",
            "approval_store_file",
            "prompt_evolver_path",
        ):
            assert Path(cfg[key]).resolve().is_relative_to(root)
        assert Path(cfg["snapshot_config"]["snapshot_dir"]).resolve().is_relative_to(root)
        assert Path(cfg["guardian_layer_config"]["config_path"]).resolve().is_relative_to(root)
        assert cfg["_skip_api_key_load"] is True
        assert cfg["_test_skip_external_storage"] is True
        assert cfg["use_external_storage"] is False
        assert cfg["enable_vector_memory"] is False
        assert cfg["enable_resource_monitoring"] is False
        assert cfg["start_background_workers"] is False
        assert cfg["autonomy_config"]["enabled"] is False
        assert cfg["auto_learning"]["enabled"] is False
        assert cfg["ui_config"]["auto_start"] is False


class TestContainedStartupIntercepted:
    def test_writes_stay_in_disposable_and_features_disabled(
        self, disposable, reset_guardian, monkeypatch
    ):
        from project_guardian.contained_startup import start_contained_guardian
        from project_guardian.guardian_singleton import reset_singleton

        # Plant a fake credential env and a bait personal memory outside disposable.
        monkeypatch.setenv("OPENAI_API_KEY", "should-not-survive-scrub")
        personal = _ROOT / "guardian_memory.json"
        bait_hash = None
        if personal.exists():
            bait_hash = personal.stat().st_mtime_ns

        tracker = _WriteInterceptor(disposable)
        smtp_calls: List[Any] = []
        threads_before = {t.name for t in threading.enumerate()}

        guardian = None
        try:
            tracker.install()
            with mock.patch(
                "smtplib.SMTP",
                side_effect=lambda *a, **k: smtp_calls.append((a, k)) or (_ for _ in ()).throw(
                    AssertionError("SMTP must not connect during contained startup")
                ),
            ):
                with mock.patch(
                    "smtplib.SMTP_SSL",
                    side_effect=lambda *a, **k: smtp_calls.append((a, k)) or (_ for _ in ()).throw(
                        AssertionError("SMTP_SSL must not connect during contained startup")
                    ),
                ):
                    guardian, cfg = start_contained_guardian(
                        disposable, ui_enabled=False, ui_auto_start=False
                    )
        finally:
            tracker.uninstall()

        assert guardian is not None
        assert tracker.violations == [], tracker.violations
        assert smtp_calls == []
        assert os.environ.get("OPENAI_API_KEY") is None

        # No personal memory loaded: disposable store empty/distinct; personal file untouched.
        mem_path = Path(cfg["memory_filepath"])
        assert mem_path.resolve().is_relative_to(disposable.resolve())
        assert str(guardian.config.get("memory_filepath")) == str(mem_path)
        if bait_hash is not None:
            assert personal.stat().st_mtime_ns == bait_hash

        auto = guardian._load_autonomy_config()
        assert auto.get("enabled") is False
        assert guardian.config.get("auto_learning", {}).get("enabled") is False
        assert guardian.config.get("enable_vector_memory") is False
        assert guardian.config.get("_test_skip_external_storage") is True
        assert guardian.config.get("use_external_storage") is False
        assert getattr(guardian, "ui_panel", None) is None

        # Privileged background workers should not have been started by init path.
        assert guardian.config.get("start_background_workers") is False
        monitor = getattr(guardian, "monitor", None)
        if monitor is not None:
            assert not bool(getattr(monitor, "monitoring_active", False))
        loop = getattr(guardian, "elysia_loop", None)
        if loop is not None:
            assert not bool(getattr(loop, "_running", False))
        sched = getattr(guardian, "prompt_evolution_scheduler", None)
        if sched is not None:
            assert not bool(getattr(sched, "_running", False) or getattr(sched, "running", False))

        new_threads = [
            t.name
            for t in threading.enumerate()
            if t.name not in threads_before and t.is_alive()
        ]
        # Allow benign helper names; forbid known autonomy/monitor workers.
        forbidden = {"ElysiaLoop", "SystemMonitor", "ResourceMonitor", "PromptEvolution"}
        assert not (forbidden & set(new_threads)), new_threads

        if hasattr(guardian, "shutdown"):
            guardian.shutdown()
        reset_singleton()

    def test_startup_failure_produces_diagnostics(self, disposable, reset_guardian):
        from project_guardian.contained_startup import (
            ContainedStartupError,
            start_contained_guardian,
        )

        missing = disposable / "does-not-exist-yet"
        # Parent exists but target path deliberately unusable: pass a file as root.
        bait = disposable / "not_a_dir"
        bait.write_text("x", encoding="utf-8")
        with pytest.raises(ContainedStartupError) as exc:
            start_contained_guardian(bait, ui_enabled=False)
        msg = str(exc.value)
        low = msg.lower()
        assert (
            "writable" in low
            or "exist" in low
            or "failed" in low
            or "directory" in low
        ), msg

    def test_init_guardian_core_forwards_containment_flags(
        self, disposable, reset_guardian
    ):
        from elysia_sub_guardian import init_guardian_core
        from project_guardian.contained_startup import build_contained_startup_config
        from project_guardian.guardian_singleton import reset_singleton

        cfg = build_contained_startup_config(disposable)
        g = init_guardian_core(config=cfg)
        assert g is not None
        assert g.config.get("_skip_api_key_load") is True
        assert g.config.get("_test_skip_external_storage") is True
        assert g.config.get("enable_resource_monitoring") is False
        assert g.config.get("autonomy_config", {}).get("enabled") is False
        assert Path(g.config["memory_filepath"]).resolve().is_relative_to(disposable.resolve())
        assert Path(g.config["review_queue_file"]).resolve().is_relative_to(
            disposable.resolve()
        )
        if hasattr(g, "shutdown"):
            g.shutdown()
        reset_singleton()
