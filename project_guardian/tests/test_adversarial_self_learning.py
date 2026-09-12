# project_guardian/tests/test_adversarial_self_learning.py
# Regression tests for adversarial self-learning central loop

import pytest
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from project_guardian.adversarial_self_learning import (
    run_adversarial_cycle,
    get_adversarial_status,
    get_execution_policy_effect,
    get_active_gates,
    apply_execution_policy_to_candidates,
    FINDING_TYPE_DEGRADED_VECTOR,
    FINDING_TYPE_CLEANUP_ANOMALY,
    _analyze_cleanup_anomalies,
    _apply_findings,
    _make_finding,
)


@pytest.fixture
def mock_guardian_with_errors(tmp_path):
    """Guardian mock with repeated error memories."""
    from project_guardian.memory import MemoryCore
    mem_path = tmp_path / "adv_mem.json"
    data = [
        {"time": "2025-01-01T12:00:00", "thought": "[Error] Connection failed", "category": "error", "priority": 0.9, "metadata": {}},
        {"time": "2025-01-01T12:01:00", "thought": "[Error] Connection failed", "category": "error", "priority": 0.9, "metadata": {}},
        {"time": "2025-01-01T12:02:00", "thought": "[Error] Connection failed", "category": "error", "priority": 0.9, "metadata": {}},
    ]
    mem_path.write_text(json.dumps(data), encoding="utf-8")
    mem = MemoryCore(filepath=str(mem_path), lazy_load=False)
    class MockG:
        memory = None
        tasks = None
    g = MockG()
    g.memory = mem
    g.tasks = None
    return g


@pytest.fixture
def mock_guardian_with_tasks(tmp_path):
    """Guardian mock with TaskEngine for task creation."""
    from project_guardian.memory import MemoryCore
    from project_guardian.tasks import TaskEngine
    mem_path = tmp_path / "adv_mem.json"
    mem_path.write_text("[]", encoding="utf-8")
    mem = MemoryCore(filepath=str(mem_path), lazy_load=False)
    tasks = TaskEngine(mem)
    class MockG:
        memory = None
        tasks = None
    g = MockG()
    g.memory = mem
    g.tasks = tasks
    return g


class TestAdversarialSelfLearning:
    """Adversarial self-learning central loop."""

    def test_run_detects_repeated_failures(self, mock_guardian_with_errors):
        """Repeated errors produce weakness finding."""
        result = run_adversarial_cycle(mock_guardian_with_errors)
        assert result["findings_count"] >= 1
        assert result["top_weakness"] is not None
        assert "Repeated failure" in result["top_weakness"] or "repeated" in result["top_weakness"].lower()
        assert result["memory_entries_written"] >= 1

    def test_status_after_run(self, mock_guardian_with_errors):
        """get_adversarial_status returns last run info."""
        run_adversarial_cycle(mock_guardian_with_errors)
        status = get_adversarial_status(mock_guardian_with_errors)
        assert status["last_run"] is not None
        assert status["findings_count"] >= 1
        assert status["top_weakness"] is not None

    def test_high_priority_creates_task(self, mock_guardian_with_tasks):
        """High-priority findings create follow-up tasks."""
        # Add repeated errors to trigger high-priority finding
        for _ in range(3):
            mock_guardian_with_tasks.memory.remember(
                "[Error] Same error again",
                category="error",
                priority=0.9,
            )
        result = run_adversarial_cycle(mock_guardian_with_tasks)
        # May or may not create task depending on priority threshold
        assert result["findings_count"] >= 1
        if result["tasks_created"] > 0:
            active = mock_guardian_with_tasks.tasks.get_active_tasks()
            adv_tasks = [t for t in active if t.get("category") == "adversarial"]
            assert len(adv_tasks) >= 1


class TestAdversarialGating:
    """Execution policy gating: degraded_vector gates consider_learning behind rebuild_vector."""

    @pytest.fixture
    def mock_guardian_with_degraded_vector(self, tmp_path):
        """Guardian mock with degraded_vector_state finding (high severity)."""
        from project_guardian.memory import MemoryCore
        mem_path = tmp_path / "adv_mem.json"
        mem_path.write_text("[]", encoding="utf-8")
        mem = MemoryCore(filepath=str(mem_path), lazy_load=False)
        g = type("MockG", (), {"memory": mem, "tasks": None})()
        g._adversarial_registry = {
            "unresolved": ["adv_degraded001"],
            "findings_by_id": {
                "adv_degraded001": {
                    "finding_id": "adv_degraded001",
                    "type": FINDING_TYPE_DEGRADED_VECTOR,
                    "severity": "high",
                    "source": "operational_state",
                    "evidence": {"vector_degraded": True, "vector_rebuild_pending": True},
                    "state": "open",
                    "resolved": False,
                },
            },
            "dedup_key_to_id": {},
            "trigger_throttle": {},
        }
        return g

    def test_degraded_vector_gates_consider_learning_when_rebuild_available(
        self, mock_guardian_with_degraded_vector
    ):
        """
        When degraded_vector_state finding is active and rebuild_vector is a candidate,
        consider_learning must be gated out (removed); rebuild_vector remains.
        """
        g = mock_guardian_with_degraded_vector
        policy = get_execution_policy_effect(g)
        assert "consider_learning" in policy["gate_actions"]
        assert policy["gate_actions"]["consider_learning"] == "rebuild_vector"

        candidates = [
            {"action": "consider_learning", "source": "introspection", "priority_score": 5},
            {"action": "rebuild_vector", "source": "operational_state", "priority_score": 8},
        ]
        filtered, gated_out = apply_execution_policy_to_candidates(candidates, policy)

        assert ("consider_learning", "gated_by:rebuild_vector") in gated_out
        actions = [c["action"] for c in filtered]
        assert "consider_learning" not in actions
        assert "rebuild_vector" in actions
        assert len(filtered) == 1
        assert filtered[0]["action"] == "rebuild_vector"

    def test_active_gates_in_status(self, mock_guardian_with_degraded_vector):
        """active_gates appears in adversarial status when gates are active."""
        g = mock_guardian_with_degraded_vector
        gates = get_active_gates(g)
        assert "consider_learning" in gates
        assert gates["consider_learning"] == "rebuild_vector"

        status = get_adversarial_status(g)
        assert "active_gates" in status
        assert status["active_gates"].get("consider_learning") == "rebuild_vector"


def test_bad_learning_session_skips_finding_when_duplicate_saturated(tmp_path):
    """Duplicate-heavy rejections should not open a noisy-learning adversarial finding."""
    from project_guardian.memory import MemoryCore
    from project_guardian.adversarial_self_learning import (
        trigger_adversarial_on_event,
        TRIGGER_BAD_LEARNING_SESSION,
    )

    mem_path = tmp_path / "m.json"
    mem_path.write_text("[]", encoding="utf-8")
    mem = MemoryCore(filepath=str(mem_path), lazy_load=False)

    class G:
        memory = mem

    g = G()
    ctx = {
        "fetched": 10,
        "rejected": 9,
        "admitted": 0,
        "cross_session_duplicates": 8,
        "rejection_breakdown": {"cross_session_duplicate": 8, "too_short": 1},
    }
    assert trigger_adversarial_on_event(g, TRIGGER_BAD_LEARNING_SESSION, ctx) is None


def test_bad_learning_session_still_triggers_when_not_duplicate_saturated(tmp_path):
    from project_guardian.memory import MemoryCore
    from project_guardian.adversarial_self_learning import (
        trigger_adversarial_on_event,
        TRIGGER_BAD_LEARNING_SESSION,
    )

    mem_path = tmp_path / "m2.json"
    mem_path.write_text("[]", encoding="utf-8")
    mem = MemoryCore(filepath=str(mem_path), lazy_load=False)

    class G:
        memory = mem

    g = G()
    ctx = {
        "fetched": 6,
        "rejected": 6,
        "admitted": 0,
        "cross_session_duplicates": 1,
        "rejection_breakdown": {"too_short": 6},
    }
    out = trigger_adversarial_on_event(g, TRIGGER_BAD_LEARNING_SESSION, ctx)
    assert out is not None


def test_cleanup_anomaly_dedups_when_skip_count_changes(mock_guardian_with_tasks):
    """A recurring cleanup pressure anomaly should update one finding/task."""
    f1 = _make_finding(
        type=FINDING_TYPE_CLEANUP_ANOMALY,
        severity="medium",
        source="memory",
        evidence={"skip_count": 3},
        recommended_action="review_cleanup_threshold",
        auto_actionable=True,
        summary="Multiple cleanup skips (3); memory pressure or threshold mismatch",
    )
    first = _apply_findings(mock_guardian_with_tasks, [f1], "periodic")
    assert first["tasks_created"] == 1

    f2 = _make_finding(
        type=FINDING_TYPE_CLEANUP_ANOMALY,
        severity="medium",
        source="memory",
        evidence={"skip_count": 4},
        recommended_action="review_cleanup_threshold",
        auto_actionable=True,
        summary="Multiple cleanup skips (4); memory pressure or threshold mismatch",
    )
    second = _apply_findings(mock_guardian_with_tasks, [f2], "periodic")
    assert second["tasks_created"] == 0

    adv_tasks = mock_guardian_with_tasks.tasks.get_active_tasks(category="adversarial")
    assert len(adv_tasks) == 1
    assert "review_cleanup_threshold" in adv_tasks[0]["name"]


def test_cleanup_anomaly_ignores_recent_successful_pressure_cleanup():
    """Older skip lines should not reopen the anomaly after the latest cleanup succeeded."""
    memories = [
        {
            "time": "2026-04-29T18:30:00",
            "category": "monitoring",
            "thought": "[Auto-Cleanup #302] Pressure emergency cleanup: reason=system_memory_pressure, outcome=consolidated, path=pressure_emergency_cleanup, memory=904->900",
        },
        {
            "time": "2026-04-29T18:29:00",
            "category": "monitoring",
            "thought": "Skipped: reason=system_memory_pressure outcome=skipped_below_threshold system_memory=95.1% memory_count=900 below threshold=3500",
        },
        {
            "time": "2026-04-29T18:28:00",
            "category": "monitoring",
            "thought": "Pressure emergency cleanup skipped: reason=system_memory_pressure outcome=skipped_small_delta memory=901 target=900",
        },
        {
            "time": "2026-04-29T18:27:00",
            "category": "monitoring",
            "thought": "Cleanup no-op: memory pressure stayed high but no memory trim was available",
        },
    ]

    assert _analyze_cleanup_anomalies(memories) == []
