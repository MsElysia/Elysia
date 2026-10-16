"""Issue 91: observation must not grant long-term-memory write authority."""
import hashlib
import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from project_guardian.memory import MemoryCore
from project_guardian.monitoring import SystemMonitor
from project_guardian.adversarial_self_learning import (
    trigger_adversarial_on_event, TRIGGER_CLEANUP_ANOMALY,
    get_adversarial_status, run_adversarial_cycle,
)


@pytest.mark.parametrize("degraded", [False, True])
def test_first_heartbeat_and_reopen_preserve_memory(tmp_path, monkeypatch, caplog, degraded):
    path = tmp_path / "memory.json"
    rows = [{"time": "2020-01-01", "thought": f"User fact {i}",
             "category": "user", "priority": 0.9, "metadata": {}}
            for i in range(4198)]
    rows += [{"time": "2020-01-01", "thought": "[Error] Synthetic connection failed",
              "category": "error", "priority": 0.9, "metadata": {}} for _ in range(2)]
    path.write_text(json.dumps(rows), encoding="utf-8")
    before = path.read_bytes()
    monkeypatch.setattr("project_guardian.monitoring.threading.Thread.start", Mock())
    monkeypatch.setattr("project_guardian.adversarial_self_learning._write_policy_recommendation", Mock())
    caplog.set_level(logging.INFO)
    for _ in range(2):
        memory = MemoryCore(str(path), enable_timeline_logging=False)
        guardian = SimpleNamespace(memory=memory, tasks=None,
            _load_autonomy_config=lambda: {"enabled": False},
            run_autonomous_cycle=Mock(),
            get_startup_operational_state=lambda: {"vector_degraded": degraded})
        monitor = SystemMonitor(memory, guardian)
        beat = monitor.heartbeat
        beat.running = True
        monkeypatch.setattr("project_guardian.monitoring.time.sleep",
                            lambda _: setattr(beat, "running", False))
        beat._beat()  # Actual first heartbeat, including both event detectors.
        assert path.read_bytes() == before
        assert len(json.loads(path.read_bytes())) == 4200
        assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(before).digest()
        guardian.run_autonomous_cycle.assert_not_called()
        types = {f["type"] for f in guardian._adversarial_registry["findings_by_id"].values()}
        assert "repeated_failure" in types
        if degraded:
            assert "degraded_vector_state" in types
            assert "degraded_vector_state" in caplog.text
        assert get_adversarial_status(guardian)["memory_entries_written"] == 0
        assert "[Adversarial Finding] repeated_failure" in caplog.text
        # A third event type proves the boundary is independent of finding strings.
        result = trigger_adversarial_on_event(guardian, TRIGGER_CLEANUP_ANOMALY, {"skip_count": 3})
        assert result["findings_count"] >= 1
        assert result["memory_entries_written"] == 0
        assert path.read_bytes() == before


def test_explicit_analysis_can_persist_with_autonomy_disabled(tmp_path):
    path = tmp_path / "explicit.json"
    memory = MemoryCore(str(path), enable_timeline_logging=False)
    for _ in range(2):
        memory.remember("[Error] Explicit synthetic error", category="error", priority=0.9)
    guardian = SimpleNamespace(memory=memory, tasks=None,
                               _load_autonomy_config=lambda: {"enabled": False})
    result = run_adversarial_cycle(guardian)
    assert result["memory_entries_written"] == 1
    rows = json.loads(path.read_text(encoding="utf-8"))
    assert len(rows) == 3
    assert rows[-1]["category"] == "adversarial_finding"


def test_shutdown_completion_logs_without_memory_append(caplog):
    """The production shutdown callback must not call memory.remember."""
    import inspect
    import textwrap
    from project_guardian.core import GuardianCore
    import project_guardian.core as core_module

    init_source = inspect.getsource(GuardianCore.__init__)
    start = init_source.index("def _on_adversarial_task_complete")
    end = init_source.index("self.tasks._on_task_complete", start)
    function_source = textwrap.dedent(init_source[start:end]).replace(
        "def _on_adversarial_task_complete(task_id: int, task: Dict) -> None:",
        "def _on_adversarial_task_complete(self, task_id, task):",
        1,
    )
    namespace = {
        "__name__": "project_guardian.core",
        "__package__": "project_guardian",
        "logger": core_module.logger,
        "Dict": dict,
        "record_task_completed": core_module.record_task_completed,
    }
    exec(function_source, namespace)
    calls = []

    class MemorySpy:
        def remember(self, thought, **kwargs):
            calls.append(thought)

    guardian = SimpleNamespace(
        memory=MemorySpy(),
        _adversarial_registry={
            "findings_by_id": {"fid-1": {"created_task_ids": [7], "state": "open"}},
        },
    )
    caplog.set_level(logging.INFO)
    namespace["_on_adversarial_task_complete"](
        guardian, 7, {"category": "adversarial", "id": 7}
    )
    assert calls == []
    assert "task_completed_unverified" in caplog.text
    assert guardian._adversarial_registry["findings_by_id"]["fid-1"]["state"] == "task_completed_unverified"
