"""Issue #23 adversarial tests: construct must not activate.

Proves GuardianCore / get_guardian_core construct-only behavior, explicit
activate() / activate_guardian_core(), config gating, singleton conflict, and
reset hygiene. Uses heavy mocks / worktree stubs so live providers are never
required.

Marked ``no_guardian_core`` so root conftest skips its GuardianCore reset
until we import (and reset ourselves).
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.no_guardian_core

_REPO = Path(__file__).resolve().parents[1]
_STUB_DIR = _REPO / "tests" / "_stubs"

# Missing optional deps — MagicMock before any project_guardian import.
_OPTIONAL_DEPS = (
    "requests",
    "openai",
    "pyttsx3",
    "flask",
    "flask_socketio",
    "flask_cors",
    "psutil",
    "faiss",
    "sentence_transformers",
    "numpy",
    "PIL",
    "cv2",
    "bs4",
    "aiohttp",
    "httpx",
    "yaml",
    "dotenv",
    "tiktoken",
    "anthropic",
)


class _ActivationForbidden(AssertionError):
    pass


def _fail(*_a, **_k):
    raise _ActivationForbidden("operational side effect during construct/inspect")


def _purge_project_guardian_modules() -> None:
    for name in list(sys.modules):
        if name == "project_guardian" or name.startswith("project_guardian."):
            del sys.modules[name]


def _install_import_stubs() -> None:
    """Install worktree openai/requests stubs + MagicMock for other optionals."""
    if str(_STUB_DIR) not in sys.path:
        sys.path.insert(0, str(_STUB_DIR))
    if str(_REPO) not in sys.path:
        sys.path.insert(0, str(_REPO))
    for name in _OPTIONAL_DEPS:
        if name in ("openai", "requests"):
            continue
        if name not in sys.modules:
            m = MagicMock()
            m.__name__ = name
            m.__path__ = []
            sys.modules[name] = m
    for mod in ("openai", "requests"):
        path = _STUB_DIR / f"{mod}.py"
        spec = importlib.util.spec_from_file_location(mod, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[mod] = module


_install_import_stubs()


class _FakeCore:
    """Lightweight stand-in mirroring activate flags for singleton tests."""

    def __init__(self, config=None):
        self.config = dict(config or {})
        self._activated = False
        self._running = False
        self.monitor_starts = 0
        self.ui_starts = 0

    def activate(self, *, start_ui=None):
        if self._activated and self._running:
            if start_ui is True and bool(self.config.get("enable_background_services", True)):
                ui_cfg = self.config.get("ui_config", {}) or {}
                if ui_cfg.get("enabled", False):
                    self.ui_starts += 1
            return True
        bg = bool(self.config.get("enable_background_services", True))
        if bg:
            self.monitor_starts += 1
            ui_cfg = self.config.get("ui_config", {}) or {}
            want_ui = False
            if start_ui is True:
                want_ui = True
            elif start_ui is False:
                want_ui = False
            else:
                want_ui = bool(ui_cfg.get("auto_start", False)) and bool(
                    ui_cfg.get("enabled", False)
                )
            if want_ui:
                self.ui_starts += 1
        self._activated = True
        self._running = True
        return True


def test_activate_guardian_core_wraps_instance_activate():
    from project_guardian.guardian_singleton import activate_guardian_core

    core = _FakeCore({"enable_background_services": True})
    assert activate_guardian_core(core) is True
    assert core.monitor_starts == 1
    assert activate_guardian_core(core) is True
    assert core._activated and core._running


def test_activate_respects_background_services_false():
    from project_guardian.guardian_singleton import activate_guardian_core

    core = _FakeCore({"enable_background_services": False})
    assert activate_guardian_core(core) is True
    assert core.monitor_starts == 0
    assert core.ui_starts == 0
    assert core._activated is True


def test_activate_ui_auto_start_false_unless_start_ui_true():
    from project_guardian.guardian_singleton import activate_guardian_core

    core = _FakeCore(
        {
            "enable_background_services": True,
            "ui_config": {"enabled": True, "auto_start": False},
        }
    )
    activate_guardian_core(core)
    assert core.ui_starts == 0
    activate_guardian_core(core, start_ui=True)
    assert core.ui_starts == 1


def test_reset_singleton_clears_activation_flags():
    import project_guardian.guardian_singleton as singleton

    fake = _FakeCore({"enable_background_services": True})
    fake.activate()
    singleton._guardian_core_instance = fake
    singleton._monitoring_started = True
    singleton.reset_singleton()
    assert singleton._guardian_core_instance is None
    assert singleton._monitoring_started is False
    assert fake._activated is False
    assert fake._running is False


def test_construct_inspect_activate_conflict_on_disable_flags():
    """Inspection request against already-active singleton reports conflict."""
    import project_guardian.guardian_singleton as singleton

    active = _FakeCore(
        {
            "enable_background_services": True,
            "enable_resource_monitoring": True,
            "ui_config": {"enabled": True, "auto_start": True},
        }
    )
    active.activate()
    singleton._guardian_core_instance = active
    singleton._monitoring_started = True

    with patch.object(singleton, "_guardian_core_class", side_effect=_fail):
        with pytest.raises(ValueError, match="enable_background_services"):
            singleton.get_guardian_core(
                config={"enable_background_services": False}
            )
        with pytest.raises(ValueError, match="ui_config.auto_start"):
            singleton.get_guardian_core(
                config={"ui_config": {"auto_start": False}}
            )
    got = singleton.get_guardian_core(config={"enable_background_services": True})
    assert got is active
    singleton.reset_singleton()


def test_construct_inspect_reset_construct_twice_no_leaked_activation():
    import project_guardian.guardian_singleton as singleton

    class _GC:
        _any_instance_initialized = False

        def __init__(self, **kwargs):
            cfg = kwargs.get("config") or {}
            self.config = dict(cfg)
            self._activated = False
            self._running = False

        def activate(self, *, start_ui=None):
            self._activated = True
            self._running = True
            return True

    with patch.object(singleton, "_guardian_core_class", return_value=_GC):
        singleton.reset_singleton()
        a = singleton.get_guardian_core(config={"enable_background_services": True})
        assert a is not None
        assert a._activated is False
        b = singleton.get_guardian_core(config={"enable_background_services": True})
        assert b is a
        singleton.reset_singleton()
        c = singleton.get_guardian_core(config={"enable_background_services": True})
        assert c is not None
        assert c is not a
        assert c._activated is False
        assert getattr(c, "_running", False) is False
        singleton.reset_singleton()
        d = singleton.get_guardian_core(config={"enable_background_services": True})
        assert d is not None
        assert d._activated is False
        singleton.reset_singleton()


def _minimal_config(tmp_path: Path) -> dict:
    mem = tmp_path / "mem.json"
    mem.write_text("[]", encoding="utf-8")
    eai_cfg = tmp_path / "eai_safety.json"
    eai_cfg.write_text('{"enabled": false}', encoding="utf-8")
    return {
        "memory_filepath": str(mem),
        "storage_path": str(tmp_path),
        "defer_heavy_startup": True,
        "_test_skip_external_storage": True,
        "enable_vector_memory": False,
        "enable_resource_monitoring": True,
        "enable_runtime_health_monitoring": True,
        "enable_background_services": True,
        # Tip lineage: EAI/guardian-layer init interacts poorly with Thread mocks.
        "enable_guardian_layer": False,
        "eai_safety_config_path": str(eai_cfg),
        "prompt_evolver_path": str(tmp_path / "prompt_evolver.json"),
        "ui_config": {
            "enabled": True,
            "auto_start": False,
            "host": "127.0.0.1",
            "port": 5099,
        },
    }


@pytest.fixture
def guardian_core_ready(tmp_path):
    """Import GuardianCore with stubs; reset singleton around the test."""
    _install_import_stubs()
    _purge_project_guardian_modules()
    _install_import_stubs()
    from project_guardian.core import GuardianCore
    from project_guardian.guardian_singleton import reset_singleton
    import project_guardian.guardian_singleton as singleton

    reset_singleton()
    GuardianCore._any_instance_initialized = False
    singleton._monitoring_started = False
    yield GuardianCore, singleton, _minimal_config(tmp_path)
    reset_singleton()
    GuardianCore._any_instance_initialized = False
    singleton._monitoring_started = False
    _purge_project_guardian_modules()


def test_real_construct_starts_zero_operational_surfaces(guardian_core_ready):
    GuardianCore, singleton, cfg = guardian_core_ready
    starts = {
        "resource": 0,
        "system": 0,
        "loop": 0,
        "prompt": 0,
        "ui": 0,
        "probe": 0,
        "health": 0,
    }

    def _count(key):
        def _inner(*_a, **_k):
            starts[key] += 1
            return {} if key == "probe" else None

        return _inner

    RealThread = __import__("threading").Thread

    class CountingThread(RealThread):
        def start(self):
            # Count but do not run operational thread bodies. Still start a real
            # no-op thread so tip code paths that join() do not hang forever.
            self._target = lambda *a, **k: None
            self._args = ()
            self._kwargs = {}
            return RealThread.start(self)

    with patch(
        "project_guardian.resource_limits.ResourceMonitor.start_monitoring",
        side_effect=_count("resource"),
    ), patch(
        "project_guardian.monitoring.SystemMonitor.start_monitoring",
        side_effect=_count("system"),
    ), patch(
        "project_guardian.elysia_loop_core.ElysiaLoopCore.start",
        side_effect=_count("loop"),
    ), patch(
        "project_guardian.prompt_evolver.AutoPromptEvolutionScheduler.start",
        side_effect=_count("prompt"),
    ), patch(
        "project_guardian.core.UIControlPanel.start", side_effect=_count("ui")
    ), patch(
        "project_guardian.planner_readiness.run_startup_planner_probe",
        side_effect=_count("probe"),
    ), patch(
        "project_guardian.runtime_health.RuntimeHealthMonitor.start_monitoring",
        side_effect=_count("health"),
    ), patch("socket.socket", side_effect=_fail), patch(
        "subprocess.Popen", side_effect=_fail
    ), patch("subprocess.run", side_effect=_fail), patch(
        "threading.Thread", CountingThread
    ):
        core = GuardianCore(cfg, allow_multiple=True)
        assert core._running is False
        assert getattr(core, "_activated", False) is False
        assert starts["resource"] == 0
        assert starts["system"] == 0
        assert starts["loop"] == 0
        assert starts["prompt"] == 0
        assert starts["ui"] == 0
        assert starts["probe"] == 0
        assert starts["health"] == 0
        core.shutdown()


def test_real_activate_starts_authorized_once_idempotent(guardian_core_ready):
    GuardianCore, singleton, cfg = guardian_core_ready
    cfg["enable_resource_monitoring"] = False
    monitor_calls: list = []
    ui_calls: list = []
    health_calls: list = []

    from project_guardian.guardian_singleton import activate_guardian_core

    with patch(
        "project_guardian.monitoring.SystemMonitor.start_monitoring",
        side_effect=lambda *a, **k: monitor_calls.append(1),
    ), patch(
        "project_guardian.prompt_evolver.AutoPromptEvolutionScheduler.start",
        MagicMock(),
    ), patch(
        "project_guardian.elysia_loop_core.ElysiaLoopCore.start", MagicMock()
    ), patch(
        "project_guardian.planner_readiness.run_startup_planner_probe",
        return_value={},
    ), patch(
        "project_guardian.runtime_health.RuntimeHealthMonitor.start_monitoring",
        side_effect=lambda *a, **k: health_calls.append(1),
    ), patch(
        "project_guardian.core.GuardianCore.start_ui_panel",
        side_effect=lambda *a, **k: ui_calls.append(1),
    ):
        singleton._monitoring_started = False
        core = GuardianCore(cfg, allow_multiple=True)
        assert monitor_calls == []
        assert health_calls == []

        assert activate_guardian_core(core) is True
        assert core._activated is True
        assert core._running is True
        assert len(monitor_calls) >= 1
        first = len(monitor_calls)
        health_first = len(health_calls)

        assert activate_guardian_core(core) is True
        assert len(monitor_calls) == first
        assert len(health_calls) == health_first
        assert ui_calls == []

        activate_guardian_core(core, start_ui=True)
        assert len(ui_calls) == 1
        core.shutdown()


def test_real_activate_bg_false_skips_monitoring(guardian_core_ready):
    GuardianCore, singleton, cfg = guardian_core_ready
    cfg["enable_background_services"] = False
    cfg["enable_resource_monitoring"] = False
    cfg["enable_runtime_health_monitoring"] = False
    monitor_calls: list = []

    with patch(
        "project_guardian.monitoring.SystemMonitor.start_monitoring",
        side_effect=lambda *a, **k: monitor_calls.append(1),
    ), patch(
        "project_guardian.runtime_health.RuntimeHealthMonitor.start_monitoring",
        side_effect=_fail,
    ), patch(
        "project_guardian.planner_readiness.run_startup_planner_probe",
        side_effect=_fail,
    ):
        core = GuardianCore(cfg, allow_multiple=True)
        assert core.activate() is True
        assert monitor_calls == []
        assert core._activated is True
        core.shutdown()


def test_real_ui_auto_start_false_no_ui_on_activate(guardian_core_ready):
    GuardianCore, singleton, cfg = guardian_core_ready
    cfg["enable_resource_monitoring"] = False
    ui_calls: list = []

    with patch(
        "project_guardian.monitoring.SystemMonitor.start_monitoring", MagicMock()
    ), patch(
        "project_guardian.prompt_evolver.AutoPromptEvolutionScheduler.start",
        MagicMock(),
    ), patch(
        "project_guardian.runtime_health.RuntimeHealthMonitor.start_monitoring",
        MagicMock(),
    ), patch(
        "project_guardian.planner_readiness.run_startup_planner_probe",
        return_value={},
    ), patch(
        "project_guardian.core.GuardianCore.start_ui_panel",
        side_effect=lambda *a, **k: ui_calls.append(1),
    ):
        singleton._monitoring_started = False
        core = GuardianCore(cfg, allow_multiple=True)
        core.activate()
        assert ui_calls == []
        core.activate(start_ui=True)
        assert len(ui_calls) == 1
        core.shutdown()
