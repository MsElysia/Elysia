"""Lifecycle bookkeeping belongs in logs, not seeded long-term memory."""
import json
import logging
import socket
from pathlib import Path
from unittest.mock import Mock

import pytest

from project_guardian.core import GuardianCore
from project_guardian.memory import MemoryCore
from project_guardian.monitoring import SystemMonitor
from project_guardian.tasks import TaskEngine
from project_guardian.trust import TrustMatrix
from project_guardian.consensus import ConsensusEngine
from project_guardian.adversarial_self_learning import (
    trigger_adversarial_on_event, TRIGGER_STARTUP_WARNINGS,
)


def test_lifecycle_logs_all_32_events_without_memory_writes(tmp_path, monkeypatch):
    """Real lifecycle methods/components; no providers, background work or live data."""
    path = tmp_path / "user_memory.json"
    seed = [{"time": "2020-01-01", "thought": f"seeded user memory {i}",
             "category": "user", "priority": 0.9, "metadata": {"source_id": i}}
            for i in range(4200)]
    path.write_text(json.dumps(seed), encoding="utf-8")
    before = path.read_bytes()
    attempts = []
    def no_network(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("no network allowed")
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    monkeypatch.setattr("project_guardian.monitoring.threading.Thread", Mock())
    monkeypatch.setattr("project_guardian.startup_runtime_guard._guardian_ref", None)
    monkeypatch.setattr("project_guardian.trust.EXTRACTED_MODULES_AVAILABLE", True)
    monkeypatch.setattr("project_guardian.trust.TrustConsultationSystem", Mock())
    monkeypatch.setattr("project_guardian.trust.AdversarialAISelfImprovement", Mock())
    monkeypatch.setattr("project_guardian.consensus.DECISION_LAYER_AVAILABLE", True)
    monkeypatch.setattr("project_guardian.consensus.DecisionMakingLayer", Mock())

    log = tmp_path / "lifecycle.log"
    handler = logging.FileHandler(log, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    old_level = root.level
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    try:
        memory = MemoryCore(str(path), enable_timeline_logging=False)
        remember = Mock(wraps=memory.remember)
        monkeypatch.setattr(memory, "remember", remember)
        core = GuardianCore.__new__(GuardianCore)
        core.memory = memory
        core.config = {}
        core._load_autonomy_config = lambda: {"enabled": False}
        core.trust = TrustMatrix(memory)
        core.consensus = ConsensusEngine(memory)
        core.tasks = TaskEngine(memory)
        core.monitor = SystemMonitor(memory, core)
        core._defer_heavy_startup = False
        core._want_mistral_planner_startup_probe = lambda: False
        core._init_runtime_health_monitoring = Mock()
        core._verify_startup = lambda: trigger_adversarial_on_event(
            core, TRIGGER_STARTUP_WARNINGS, {"warnings": 1})
        core.stop_ui_panel = Mock()
        core.elysia_loop = Mock()
        core.resource_monitor = Mock()
        core.runtime_health = Mock()
        monkeypatch.setattr("project_guardian.guardian_singleton.ensure_monitoring_started",
                            lambda g: g.monitor.start_monitoring())
        core._register_core_agents()
        core._initialize_system()
        core.shutdown()
        handler.flush()
        assert path.read_bytes() == before
        assert memory.get_memory_count() == 4200
        remember.assert_not_called()
        assert not attempts
        assert core._adversarial_last_run["memory_entries_written"] == 0
        assert core._adversarial_last_run["findings_count"] == 1
        assert len(core.tasks.task_history) == 2
        assert core.trust.get_trust("memory_core") == 0.95
    finally:
        root.removeHandler(handler)
        handler.close()
        root.setLevel(old_level)

    text = log.read_text(encoding="utf-8")
    expected = {
        "[Guardian Trust] Trust Consultation System initialized": 1,
        "[Guardian Trust] Adversarial AI Self-Improvement System initialized": 1,
        "[Guardian Consensus] Decision Making Layer initialized": 1,
        "[Guardian Consensus] Registered agent:": 10,
        "[Guardian Core] System initialized": 1,
        "[Guardian Task] Created:": 2,
        "(+0.": 3,
        "[Heartbeat] Started monitoring": 1,
        "[SystemMonitor] Monitoring started": 1,
        "[Adversarial Finding] startup_configuration_weakness": 1,
        "[Guardian Core] System shutdown initiated": 1,
        "[Guardian Task] Completed:": 2,
        "[Guardian Consensus] Cleared all 0 votes": 1,
        "[Heartbeat] Stopped monitoring": 1,
        "[SystemMonitor] Monitoring stopped": 1,
        "[Guardian Trust Decay]": 3,
        "[Guardian Core] System shutdown complete": 1,
    }
    assert sum(expected.values()) == 32
    for message, count in expected.items():
        assert text.count(message) == count, message


def test_explicit_memory_write_and_consolidation_remain_available(tmp_path):
    path = tmp_path / "explicit.json"
    memory = MemoryCore(str(path), enable_timeline_logging=False)
    memory.remember("Explicitly requested long-term user memory", category="user", priority=0.9)
    assert json.loads(path.read_text())[0]["thought"] == "Explicitly requested long-term user memory"
    result = memory.consolidate(max_memories=1)
    assert result["action"] == "no_action_needed"
    assert len(json.loads(path.read_text())) == 1


def test_voice_engine_init_error_is_log_only_and_preserves_seeded_memory(
    tmp_path, monkeypatch, caplog
):
    """Reproduce Issue #123 with the actual VoiceThread and durable MemoryCore."""
    from types import SimpleNamespace
    import project_guardian.external as external

    path = tmp_path / "voice-user-memory.json"
    seed = [
        {"time": "2020-01-01", "thought": f"fictional memory {i}",
         "category": "user", "priority": 0.5, "metadata": {"source_id": i}}
        for i in range(4200)
    ]
    path.write_text(json.dumps(seed), encoding="utf-8")
    before = path.read_bytes()
    memory = MemoryCore(str(path), enable_timeline_logging=False)
    remember = Mock(wraps=memory.remember)
    monkeypatch.setattr(memory, "remember", remember)
    monkeypatch.setattr(
        external, "pyttsx3",
        SimpleNamespace(init=Mock(side_effect=RuntimeError("synthetic voice failure")))
    )

    with caplog.at_level(logging.WARNING, logger="project_guardian.external"):
        first = external.VoiceThread(memory)
        second = external.VoiceThread(memory)

    assert first.engine is None and second.engine is None
    remember.assert_not_called()
    assert path.read_bytes() == before
    assert memory.get_memory_count() == 4200
    warnings = [
        record for record in caplog.records
        if record.name == "project_guardian.external"
        and "Failed to initialize: synthetic voice failure" in record.getMessage()
    ]
    assert len(warnings) == 2


def test_voice_engine_success_retains_explicit_mode_memory_behavior(
    tmp_path, monkeypatch
):
    """Diagnostic fencing does not disable explicitly requested voice actions."""
    from types import SimpleNamespace
    import project_guardian.external as external

    path = tmp_path / "voice-explicit-memory.json"
    memory = MemoryCore(str(path), enable_timeline_logging=False)
    engine = Mock()
    engine.getProperty.return_value = []
    monkeypatch.setattr(external, "pyttsx3", SimpleNamespace(init=lambda: engine))
    voice = external.VoiceThread(memory)
    assert voice.engine is engine
    assert memory.get_memory_count() == 0
    voice.set_mode("sharp_analyst")
    assert voice.mode == "sharp_analyst"
    assert memory.get_memory_count() == 1
    assert "Mode changed to: sharp_analyst" in json.loads(path.read_text())[0]["thought"]
