import json
import logging

import project_guardian.adversarial_self_learning as adversarial
import project_guardian.monitoring as monitoring
from project_guardian.memory import MemoryCore
from project_guardian.monitoring import Heartbeat


class _Guardian:
    def __init__(self, memory, *, vector_degraded=False):
        self.memory = memory
        self.tasks = None
        self._vector_degraded = vector_degraded

    def _load_autonomy_config(self):
        return {"enabled": False}

    def get_startup_operational_state(self):
        return {
            "vector_degraded": self._vector_degraded,
            "vector_rebuild_pending": False,
        }


class _Monitor:
    def __init__(self, guardian):
        self.guardian = guardian
        self.diagnostics = []

    def _queue_or_write_memory(self, thought, **kwargs):
        # Startup/heartbeat diagnostics are log-only on the startup-safety path.
        self.diagnostics.append((thought, kwargs))

    def _perform_cleanup(self, *args, **kwargs):
        raise AssertionError("cleanup must not run in this bounded heartbeat regression")

    def _perform_light_cleanup(self):
        return None


def _run_one_heartbeat_then_graceful_stop(monkeypatch, memory, *, vector_degraded=False):
    guardian = _Guardian(memory, vector_degraded=vector_degraded)
    monitor = _Monitor(guardian)
    heartbeat = Heartbeat(memory, interval=1, system_monitor=monitor)
    heartbeat._high_water = 10000
    heartbeat._low_water = 8000
    heartbeat.running = True

    def stop_after_first_iteration(_interval):
        heartbeat.running = False

    monkeypatch.setattr(monitoring.time, "sleep", stop_after_first_iteration)
    heartbeat._beat()
    heartbeat.stop()
    return guardian, monitor


def _seed_duplicate_error_file(path, total=4200):
    rows = [
        {
            "time": f"2026-09-29T00:00:{i % 60:02d}",
            "thought": f"fixture {i}",
            "category": "fixture",
            "priority": 0.5,
            "metadata": {},
        }
        for i in range(total - 2)
    ]
    rows.extend(
        [
            {
                "time": "2026-09-29T01:00:00",
                "thought": "repeated startup failure: synthetic",
                "category": "error",
                "priority": 0.9,
                "metadata": {},
            },
            {
                "time": "2026-09-29T01:00:01",
                "thought": "repeated startup failure: synthetic",
                "category": "error",
                "priority": 0.9,
                "metadata": {},
            },
        ]
    )
    path.write_text(json.dumps(rows), encoding="utf-8")


def test_disabled_autonomy_duplicate_error_first_heartbeat_reopen_is_byte_stable(
    tmp_path, monkeypatch, caplog
):
    memory_path = tmp_path / "guardian_memory.json"
    _seed_duplicate_error_file(memory_path)
    baseline = memory_path.read_bytes()

    monkeypatch.setattr(adversarial, "_write_policy_recommendation", lambda finding: None)
    caplog.set_level(logging.INFO, logger=adversarial.__name__)

    first_memory = MemoryCore(filepath=str(memory_path), lazy_load=False)
    first_guardian, _ = _run_one_heartbeat_then_graceful_stop(
        monkeypatch, first_memory
    )

    assert first_memory.get_memory_count() == 4200
    assert memory_path.read_bytes() == baseline
    first_status = adversarial.get_adversarial_status(first_guardian)
    assert first_status["unresolved_findings_count"] >= 1
    assert first_status["memory_entries_written"] == 0

    reopened_memory = MemoryCore(filepath=str(memory_path), lazy_load=False)
    reopened_guardian, _ = _run_one_heartbeat_then_graceful_stop(
        monkeypatch, reopened_memory
    )

    assert reopened_memory.get_memory_count() == 4200
    assert memory_path.read_bytes() == baseline
    reopened_status = adversarial.get_adversarial_status(reopened_guardian)
    assert reopened_status["unresolved_findings_count"] >= 1
    assert reopened_status["memory_entries_written"] == 0
    assert any(
        "long-term memory persistence suppressed" in record.getMessage()
        for record in caplog.records
    )


def test_disabled_autonomy_degraded_vector_heartbeat_keeps_registry_without_memory_append(
    tmp_path, monkeypatch
):
    memory_path = tmp_path / "guardian_memory.json"
    memory_path.write_text("[]", encoding="utf-8")
    baseline = memory_path.read_bytes()

    monkeypatch.setattr(adversarial, "_write_policy_recommendation", lambda finding: None)

    memory = MemoryCore(filepath=str(memory_path), lazy_load=False)
    guardian, _ = _run_one_heartbeat_then_graceful_stop(
        monkeypatch, memory, vector_degraded=True
    )

    assert memory_path.read_bytes() == baseline
    status = adversarial.get_adversarial_status(guardian)
    assert status["unresolved_findings_count"] >= 1
    assert status["top_type"] == adversarial.FINDING_TYPE_DEGRADED_VECTOR
    assert status["memory_entries_written"] == 0


def test_explicit_adversarial_cycle_still_persists_when_autonomy_disabled(
    tmp_path, monkeypatch
):
    memory_path = tmp_path / "guardian_memory.json"
    _seed_duplicate_error_file(memory_path, total=3)
    baseline = memory_path.read_bytes()

    monkeypatch.setattr(adversarial, "_write_policy_recommendation", lambda finding: None)

    memory = MemoryCore(filepath=str(memory_path), lazy_load=False)
    guardian = _Guardian(memory)
    result = adversarial.run_adversarial_cycle(guardian)

    assert result["findings_count"] >= 1
    assert result["memory_entries_written"] >= 1
    assert memory_path.read_bytes() != baseline
    assert any(
        item.get("category") == "adversarial_finding"
        for item in memory.memory_log
    )
