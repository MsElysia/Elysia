"""Offline regressions for the maintenance boundary, using only synthetic records.

Diagnostic routing is covered separately; these tests isolate maintenance paths.
"""
import json
import socket
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from project_guardian.core import GuardianCore
from project_guardian.memory import MemoryCore
from project_guardian.monitoring import Heartbeat, SystemMonitor


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    attempts = []
    def denied(*args, **kwargs):
        attempts.append("network")
        raise AssertionError("network is forbidden in maintenance tests")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(threading.Thread, "start", Mock())
    yield
    assert attempts == [], "a component attempted network access, even if it caught the denial"


@pytest.fixture
def memory(tmp_path):
    path = tmp_path / "synthetic.json"
    path.write_text(json.dumps([
        {"time": "2020-01-01", "thought": f"synthetic-{i}",
         "priority": 0.5, "category": "fixture", "metadata": {"source_id": i}}
        for i in range(4200)
    ]), encoding="utf-8")
    return MemoryCore(str(path), enable_timeline_logging=False)


def prepared_core(memory, monkeypatch):
    core = GuardianCore.__new__(GuardianCore)
    core.memory = memory
    core.config = {"memory_cleanup_threshold": 1000}
    core.tasks = Mock()
    core.trust = Mock()
    core._deferred_init_lock = threading.Lock()
    core._resource_monitor_startup_deferred = False
    core.deferred_init_started = False
    core.deferred_init_running = False
    core.deferred_init_complete = False
    core.deferred_init_failed = False
    core._planner_startup_probe_pending = False
    core._want_mistral_planner_startup_probe = Mock(return_value=False)
    core._verify_startup = Mock()
    core._init_runtime_health_monitoring = Mock()
    core.rebuild_vector_memory_if_pending = Mock(return_value={"skipped": True})
    monkeypatch.setattr("project_guardian.guardian_singleton.ensure_monitoring_started", Mock())
    return core


@pytest.mark.parametrize("deferred", [False, True])
def test_startup_phases_do_not_consolidate(memory, monkeypatch, deferred):
    from pathlib import Path
    path = Path(memory.filepath)
    before = path.read_bytes()
    core = prepared_core(memory, monkeypatch)
    core._defer_heavy_startup = deferred
    monkeypatch.setattr(memory, "remember", Mock())  # independent diagnostic writes
    consolidate = Mock(wraps=memory.consolidate)
    monkeypatch.setattr(memory, "consolidate", consolidate)
    core._initialize_system()
    if deferred:
        core.start_deferred_initialization()
    assert core.deferred_init_complete
    consolidate.assert_not_called()
    assert path.read_bytes() == before


def test_registered_resource_callback_cannot_trim_store(memory, monkeypatch, tmp_path):
    """Capture the actual callback registered by GuardianCore.__init__."""
    from pathlib import Path
    import project_guardian.core as module
    before = Path(memory.filepath).read_bytes()
    for name in ("TrustMatrix", "MutationEngine", "DevilsAdvocate", "RollbackEngine",
                 "TaskEngine", "ConsensusEngine", "SelfReflector", "TimelineMemory",
                 "SecurityAuditor"):
        monkeypatch.setattr(module, name, Mock())
    monkeypatch.setattr(module, "__file__", str(tmp_path / "project_guardian" / "core.py"))
    monkeypatch.setattr(GuardianCore, "_load_api_keys_from_folder", Mock())
    monkeypatch.setattr(GuardianCore, "_validate_configuration", Mock())
    monkeypatch.setattr(module, "MemoryCore", Mock(return_value=memory))
    monkeypatch.setattr("project_guardian.planner_readiness.bind_guardian_for_startup_gates", Mock())
    monkeypatch.setattr("project_guardian.startup_runtime_guard.bind_guardian_for_runtime_guard", Mock())
    callbacks = []
    class Captured(Exception):
        pass
    def register(kind, callback):
        callbacks.append(callback)
        raise Captured()
    resource = Mock()
    resource.register_callback.side_effect = register
    monkeypatch.setattr(module, "ResourceMonitor", Mock(return_value=resource))
    with pytest.raises(Captured):
        GuardianCore({"memory_filepath": memory.filepath,
                      "enable_vector_memory": False, "_test_skip_external_storage": True},
                     allow_multiple=True)
    assert len(callbacks) == 1
    callbacks[0]({"usage_percent": 0.99})
    assert Path(memory.filepath).read_bytes() == before


@pytest.mark.parametrize("with_monitor", [False, True])
def test_heartbeat_cannot_trim_store(memory, monkeypatch, with_monitor):
    from pathlib import Path
    before = Path(memory.filepath).read_bytes()
    monkeypatch.setattr(memory, "remember", Mock())
    guardian = SimpleNamespace(_load_autonomy_config=lambda: {"enabled": False},
                               run_autonomous_cycle=Mock())
    monitor = SystemMonitor(memory, guardian) if with_monitor else None
    beat = monitor.heartbeat if monitor else Heartbeat(memory)
    beat.running = True
    def stop(_):
        beat.running = False
    monkeypatch.setattr("project_guardian.monitoring.time.sleep", stop)
    beat._beat()
    assert Path(memory.filepath).read_bytes() == before
    guardian.run_autonomous_cycle.assert_not_called()


def test_explicit_maintenance_remains_available(memory):
    from pathlib import Path
    monitor = SystemMonitor(memory, SimpleNamespace(config={}))
    result = monitor._perform_cleanup(1000, reason="manual")
    assert result["action_taken"] is True
    assert len(json.loads(Path(memory.filepath).read_text())) < 4200


def test_runtime_health_check_observes_without_consolidating(memory):
    from pathlib import Path
    from project_guardian.runtime_health import create_guardian_health_checks, HealthStatus
    before = Path(memory.filepath).read_bytes()
    guardian = SimpleNamespace(memory=memory, config={"memory_cleanup_threshold": 1000})
    result = create_guardian_health_checks(guardian)["memory_count"]()
    assert result.status is HealthStatus.WARNING
    assert result.details["count"] == 4200
    assert Path(memory.filepath).read_bytes() == before


def test_startup_diagnostic_goes_to_log_not_memory(memory, monkeypatch, caplog):
    core = prepared_core(memory, monkeypatch)
    core._defer_heavy_startup = True
    before = memory.get_memory_count()
    with caplog.at_level("INFO"):
        core._initialize_system()
    assert memory.get_memory_count() == before
    assert "[Guardian Core] System initialized" in caplog.text
