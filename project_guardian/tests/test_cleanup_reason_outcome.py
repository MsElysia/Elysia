# project_guardian/tests/test_cleanup_reason_outcome.py
# Regression tests for cleanup reason/outcome model and single-terminal outcome

import pytest
import json
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from project_guardian.monitoring import (
    SystemMonitor,
    CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE,
    CLEANUP_REASON_MEMORY_COUNT_THRESHOLD,
    CLEANUP_OUTCOME_SKIPPED_BELOW_THRESHOLD,
    CLEANUP_OUTCOME_SKIPPED_COOLDOWN,
    CLEANUP_OUTCOME_SKIPPED_SMALL_DELTA,
    CLEANUP_OUTCOME_SKIPPED_QUIET_ZONE,
    CLEANUP_OUTCOME_PARTIAL_RECLAIM,
    CLEANUP_OUTCOME_CONSOLIDATED,
    CLEANUP_OUTCOME_FAILED,
    _PRESSURE_CONSOLIDATION_MIN_COUNT,
    _PRESSURE_EMERGENCY_MIN_COUNT,
    _compute_pressure_emergency_target,
    _effective_pressure_emergency_floor,
    _load_memory_pressure_config,
)


@pytest.fixture
def minimal_memory(tmp_path):
    """MemoryCore with a few items (below threshold)."""
    from project_guardian.memory import MemoryCore
    mem_path = tmp_path / "mem.json"
    data = [
        {"time": "2025-01-01", "thought": f"x{i}", "category": "g", "priority": 0.5, "metadata": {}}
        for i in range(50)
    ]
    mem_path.write_text(json.dumps(data), encoding="utf-8")
    return MemoryCore(filepath=str(mem_path), lazy_load=False)


@pytest.fixture
def mock_guardian(minimal_memory):
    """Minimal guardian mock with config."""
    class MockGuardian:
        config = {"memory_cleanup_threshold": 3500}
        memory = None
        web_reader = None
        proposal_system = None
    g = MockGuardian()
    g.memory = minimal_memory
    return g


@pytest.fixture
def system_monitor(minimal_memory, mock_guardian):
    """SystemMonitor with real memory and mock guardian."""
    return SystemMonitor(minimal_memory, mock_guardian)


class TestCleanupReasonOutcome:
    """Cleanup reason/outcome model and single-terminal outcome."""

    def test_system_health_reflects_host_ram_pressure(self, system_monitor, monkeypatch):
        """Host RAM pressure should prevent a misleading HEALTHY status."""
        monkeypatch.setattr(
            "project_guardian.monitoring._system_memory_pressure_fraction",
            lambda: 0.96,
        )

        health = system_monitor.get_system_health()

        assert health["status"] == "critical"
        assert health["health_score"] <= 0.4
        assert health["heartbeat"]["system_memory_percent"] == 96.0

    def test_effective_pressure_emergency_floor_clamps_aggressive_config(self):
        """Emergency floor should honor a safe fraction clamp even with aggressive config values."""
        aggressive_cfg = {
            "pressure_emergency_min_count": 25,
            "pressure_emergency_floor_fraction": 0.9,
        }
        assert _effective_pressure_emergency_floor(1000, aggressive_cfg) == 900
        assert _effective_pressure_emergency_floor(1750, aggressive_cfg) == 1575

    def test_pressure_emergency_target_is_proportional_and_bounded(self):
        """Emergency target should trim proportionally while staying above effective floor."""
        cfg = {
            "pressure_emergency_trim_ratio": 0.15,
            "pressure_emergency_min_count": 900,
            "pressure_emergency_floor_fraction": 0.9,
        }
        floor = _effective_pressure_emergency_floor(1000, cfg)
        assert floor == 900
        assert _compute_pressure_emergency_target(2000, floor, cfg) == 1700
        # Near floor: bounded and does not undercut effective floor.
        assert _compute_pressure_emergency_target(930, floor, cfg) == 900

    def test_pressure_below_threshold_outcome_skipped_below_threshold(
        self, system_monitor, minimal_memory
    ):
        """Below-threshold pressure path should only emergency-trim when count exceeds safe effective floor."""
        # Memory has 50 items, threshold 3500.
        # Effective floor clamp should prevent emergency over-trim at this low count.
        result = system_monitor._perform_cleanup(
            memory_threshold=1750,
            reason=CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE,
            system_memory_percent=0.92,
            consolidation_threshold=3500,
        )
        emergency_floor = _effective_pressure_emergency_floor(
            1750,
            pressure_cfg=_load_memory_pressure_config(),
        )
        assert result["attempted"] is True
        if 50 > emergency_floor:
            assert result["outcome"] == CLEANUP_OUTCOME_CONSOLIDATED
            assert result["action_taken"] is True
            assert result.get("cleanup_path") == "pressure_emergency_cleanup"
        else:
            assert result["outcome"] == CLEANUP_OUTCOME_SKIPPED_BELOW_THRESHOLD
            assert result["action_taken"] is False
            assert result["no_op_reason"] == "memory_count_below_threshold"
            assert result.get("trim_policy", {}).get("source") == "config_memory_pressure"
            assert result.get("trim_policy", {}).get("trigger_threshold") is not None
        assert result["cooldown_active"] is False

    def test_pressure_emergency_cleanup_runs_when_count_below_consolidation_threshold(
        self, tmp_path
    ):
        """When count is above effective floor, pressure path can still emergency-consolidate."""
        from project_guardian.memory import MemoryCore

        mem_path = tmp_path / "pressure_emergency.json"
        trim_target = 1000
        emergency_floor = _effective_pressure_emergency_floor(
            trim_target,
            pressure_cfg=_load_memory_pressure_config(),
        )
        # Keep below consolidation_threshold but above effective floor.
        n = emergency_floor + 50
        now_iso = "2025-01-15"
        data = [
            {"time": now_iso, "thought": f"x{i}", "category": "g", "priority": 0.5, "metadata": {}}
            for i in range(n)
        ]
        mem_path.write_text(json.dumps(data), encoding="utf-8")
        mem = MemoryCore(filepath=str(mem_path), lazy_load=False)

        class MockG:
            config = {}
            memory = None
            web_reader = None
            proposal_system = None

        g = MockG()
        g.memory = mem
        mon = SystemMonitor(mem, g)

        result = mon._perform_cleanup(
            memory_threshold=trim_target,
            reason=CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE,
            system_memory_percent=0.82,  # non-critical (so skip_thresh uses consolidation_threshold)
            consolidation_threshold=3500,
        )

        assert result["action_taken"] is True
        assert result.get("cleanup_path") == "pressure_emergency_cleanup"
        expected_target = _compute_pressure_emergency_target(
            n,
            emergency_floor,
            pressure_cfg=_load_memory_pressure_config(),
        )
        assert result["trim_policy"]["trim_target"] == expected_target
        assert result["memory_after"] <= expected_target

    def test_pressure_critical_low_count_uses_effective_floor_clamp(self, tmp_path):
        """Critical pressure uses a safe floor close to pressure trim target, not raw config min."""
        from project_guardian.memory import MemoryCore

        mem_path = tmp_path / "pressure_critical_low_count.json"
        trim_target = 1000
        emergency_floor = _effective_pressure_emergency_floor(
            trim_target,
            pressure_cfg=_load_memory_pressure_config(),
        )
        n = emergency_floor + 7
        data = [
            {"time": "2025-01-15", "thought": f"x{i}", "category": "g", "priority": 0.5, "metadata": {}}
            for i in range(n)
        ]
        mem_path.write_text(json.dumps(data), encoding="utf-8")
        mem = MemoryCore(filepath=str(mem_path), lazy_load=False)

        class MockG:
            config = {}
            memory = None
            web_reader = None
            proposal_system = None

        g = MockG()
        g.memory = mem
        mon = SystemMonitor(mem, g)

        result = mon._perform_cleanup(
            memory_threshold=trim_target,
            reason=CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE,
            system_memory_percent=0.96,  # critical pressure
            consolidation_threshold=3500,
        )

        assert result.get("cleanup_path") == "pressure_emergency_cleanup"
        assert result["action_taken"] is True
        expected_target = _compute_pressure_emergency_target(
            n,
            emergency_floor,
            pressure_cfg=_load_memory_pressure_config(),
        )
        assert result["trim_policy"]["trim_target"] == expected_target
        assert result["memory_after"] <= expected_target
        assert emergency_floor > _PRESSURE_EMERGENCY_MIN_COUNT

    def test_cooldown_on_later_attempt_outcome_skipped_cooldown(
        self, system_monitor, minimal_memory
    ):
        """Later attempt during cooldown => outcome=skipped_cooldown."""
        # Force cooldown state
        system_monitor._pressure_no_op_cooldown_until = time.time() + 600
        result = system_monitor._perform_cleanup(
            memory_threshold=1750,
            reason=CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE,
            system_memory_percent=0.93,
            consolidation_threshold=3500,
        )
        assert result["outcome"] == CLEANUP_OUTCOME_SKIPPED_COOLDOWN
        assert result["cooldown_active"] is True
        assert result["attempted"] is True

    def test_one_attempt_one_outcome(self, system_monitor):
        """One cleanup attempt produces exactly one terminal outcome."""
        result = system_monitor._perform_cleanup(
            memory_threshold=1750,
            reason=CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE,
            system_memory_percent=0.92,
            consolidation_threshold=3500,
        )
        assert result["outcome"] in (
            CLEANUP_OUTCOME_SKIPPED_BELOW_THRESHOLD,
            CLEANUP_OUTCOME_SKIPPED_SMALL_DELTA,
            CLEANUP_OUTCOME_PARTIAL_RECLAIM,
            CLEANUP_OUTCOME_CONSOLIDATED,
        )
        assert result["cleanup_id"] > 0
        # Outcome is single-valued
        valid_outcomes = {
            CLEANUP_OUTCOME_SKIPPED_COOLDOWN,
            CLEANUP_OUTCOME_SKIPPED_BELOW_THRESHOLD,
            CLEANUP_OUTCOME_SKIPPED_SMALL_DELTA,
            CLEANUP_OUTCOME_PARTIAL_RECLAIM,
            CLEANUP_OUTCOME_CONSOLIDATED,
            CLEANUP_OUTCOME_FAILED,
        }
        assert result["outcome"] in valid_outcomes

    def test_no_op_does_not_report_as_successful_cleanup(self, system_monitor):
        """No-op attempts have action_taken=False, not success."""
        result = system_monitor._perform_cleanup(
            memory_threshold=1750,
            reason=CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE,
            system_memory_percent=0.92,
            consolidation_threshold=3500,
        )
        if result["outcome"] == CLEANUP_OUTCOME_SKIPPED_BELOW_THRESHOLD:
            assert result["action_taken"] is False
        # Partial reclaim would have action_taken=True from caches

    def test_count_threshold_can_consolidate(self, tmp_path, minimal_memory):
        """Count-threshold cleanup with count above threshold can consolidate."""
        from project_guardian.memory import MemoryCore
        # Create memory with 100 items, threshold 50
        mem_path = tmp_path / "many.json"
        data = [
            {"time": "2025-01-01", "thought": f"x{i}", "category": "g", "priority": 0.5, "metadata": {}}
            for i in range(100)
        ]
        mem_path.write_text(json.dumps(data), encoding="utf-8")
        mem = MemoryCore(filepath=str(mem_path), lazy_load=False)
        class MockG:
            config = {}
            memory = None
            web_reader = None
            proposal_system = None
        g = MockG()
        g.memory = mem
        mon = SystemMonitor(mem, g)
        result = mon._perform_cleanup(
            memory_threshold=50,
            reason=CLEANUP_REASON_MEMORY_COUNT_THRESHOLD,
        )
        assert result["outcome"] == CLEANUP_OUTCOME_CONSOLIDATED
        assert result["action_taken"] is True
        assert result["memory_after"] <= 50

    def test_pressure_critical_runs_consolidation_when_count_above_min(self, tmp_path):
        """When system RAM >= 85% and guardian count > 1000, run consolidation (not skip to light reclaim)."""
        from project_guardian.memory import MemoryCore
        mem_path = tmp_path / "pressure.json"
        data = [
            {"time": "2025-01-01", "thought": f"x{i}", "category": "g", "priority": 0.5, "metadata": {}}
            for i in range(2000)
        ]
        mem_path.write_text(json.dumps(data), encoding="utf-8")
        mem = MemoryCore(filepath=str(mem_path), lazy_load=False)
        class MockG:
            config = {}
            memory = None
            web_reader = None
            proposal_system = None
        g = MockG()
        g.memory = mem
        mon = SystemMonitor(mem, g)
        result = mon._perform_cleanup(
            memory_threshold=1750,
            reason=CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE,
            system_memory_percent=0.92,
            consolidation_threshold=3500,
        )
        assert result["outcome"] == CLEANUP_OUTCOME_CONSOLIDATED
        assert result["action_taken"] is True
        assert result["memory_after"] <= 1750

    def test_pressure_small_delta_skips_consolidation(self, tmp_path):
        """When memory_count - trim_target < min_trim_delta, outcome=skipped_small_delta (avoid thrash)."""
        from project_guardian.memory import MemoryCore
        # 1770 memories, trim_target 1750 -> delta 20 < 25
        mem_path = tmp_path / "near_floor.json"
        data = [
            {"time": "2025-01-01", "thought": f"x{i}", "category": "g", "priority": 0.5, "metadata": {}}
            for i in range(1770)
        ]
        mem_path.write_text(json.dumps(data), encoding="utf-8")
        mem = MemoryCore(filepath=str(mem_path), lazy_load=False)
        class MockG:
            config = {}
            memory = None
            web_reader = None
            proposal_system = None
        g = MockG()
        g.memory = mem
        mon = SystemMonitor(mem, g)
        result = mon._perform_cleanup(
            memory_threshold=1750,
            reason=CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE,
            system_memory_percent=0.92,
            consolidation_threshold=3500,
        )
        assert result["outcome"] == CLEANUP_OUTCOME_SKIPPED_SMALL_DELTA
        assert result["action_taken"] is False
        assert result["trim_policy"] is not None
        assert result["trim_policy"]["trim_target"] == 1750
        assert result["trim_policy"]["min_trim_delta"] == 25

    def test_pressure_critical_bypasses_small_delta_wait(self, tmp_path):
        """Critical host RAM should not wait several cycles before a small-delta pressure cleanup."""
        from project_guardian.memory import MemoryCore

        mem_path = tmp_path / "critical_small_delta.json"
        data = [
            {"time": "2025-01-01", "thought": f"x{i}", "category": "g", "priority": 0.5, "metadata": {}}
            for i in range(1020)
        ]
        mem_path.write_text(json.dumps(data), encoding="utf-8")
        mem = MemoryCore(filepath=str(mem_path), lazy_load=False)

        class MockG:
            config = {}
            memory = None
            web_reader = None
            proposal_system = None

        g = MockG()
        g.memory = mem
        mon = SystemMonitor(mem, g)

        result = mon._perform_cleanup(
            memory_threshold=1000,
            reason=CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE,
            system_memory_percent=0.97,
            consolidation_threshold=3500,
        )

        assert result["outcome"] == CLEANUP_OUTCOME_CONSOLIDATED
        assert result["action_taken"] is True
        assert result["force_cleanup_bypass_delta"] is True
        assert result["force_cleanup_reason"] == "critical_memory_pressure"
        assert result["memory_after"] <= 1000

    def test_pressure_quiet_zone_skips_noncritical_but_not_critical(self, tmp_path):
        """Quiet zone remains gentle below critical RAM and yields under critical pressure."""
        from project_guardian.memory import MemoryCore

        def make_monitor(path_name: str):
            mem_path = tmp_path / path_name
            data = [
                {"time": "2025-01-01", "thought": f"x{i}", "category": "g", "priority": 0.5, "metadata": {}}
                for i in range(930)
            ]
            mem_path.write_text(json.dumps(data), encoding="utf-8")
            mem = MemoryCore(filepath=str(mem_path), lazy_load=False)

            class MockG:
                config = {}
                memory = None
                web_reader = None
                proposal_system = None

            g = MockG()
            g.memory = mem
            mon = SystemMonitor(mem, g)
            mon._post_cleanup_quiet_until = time.time() + 300
            return mon

        noncritical = make_monitor("quiet_noncritical.json")
        skipped = noncritical._perform_cleanup(
            memory_threshold=1000,
            reason=CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE,
            system_memory_percent=0.90,
            consolidation_threshold=3500,
        )
        assert skipped["outcome"] == CLEANUP_OUTCOME_SKIPPED_QUIET_ZONE

        critical = make_monitor("quiet_critical.json")
        result = critical._perform_cleanup(
            memory_threshold=1000,
            reason=CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE,
            system_memory_percent=0.97,
            consolidation_threshold=3500,
        )
        assert result["outcome"] == CLEANUP_OUTCOME_CONSOLIDATED
        assert result.get("cleanup_path") == "pressure_emergency_cleanup"
        assert result["memory_after"] <= 900
