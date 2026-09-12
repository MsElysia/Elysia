"""
GuardianCore Task Router Tests
===============================
Tests for CONTROL.md integration and task routing in GuardianCore.
Verifies structured results from run_once() and task contract loading.
"""

import pytest
from pathlib import Path

from project_guardian.core import GuardianCore
from tests.guardian_core_test_helpers import (
    minimal_guardian_core_test_config,
    write_task_contract_file,
)


class TestRunOnceIdleWhenNone:
    """Test that run_once() returns idle status when CURRENT_TASK is NONE"""

    def test_run_once_idle_when_none(self, tmp_path):
        """Verify run_once returns {status:"idle"} when CONTROL.md has CURRENT_TASK: NONE"""
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: NONE\n", encoding="utf-8")

        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()

        core = GuardianCore(
            config=minimal_guardian_core_test_config(),
            control_path=control_file,
            tasks_dir=tasks_dir,
        )

        result = core.run_once()

        assert isinstance(result, dict), "run_once() should return dict"
        assert result["status"] == "idle", f"Status should be 'idle', got {result.get('status')}"
        assert result["current_task"] is None, "current_task should be None when NONE"
        assert "timestamp" in result, "Result should have timestamp"


class TestRunOnceErrorWhenControlMissing:
    """Test that run_once() returns error when CONTROL.md is missing"""

    def test_run_once_error_when_control_missing(self, tmp_path):
        """Verify run_once returns {status:"error", code:"CONTROL_MISSING"} when CONTROL.md is missing"""
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()

        control_file = tmp_path / "CONTROL.md"
        core = GuardianCore(
            config=minimal_guardian_core_test_config(),
            control_path=control_file,
            tasks_dir=tasks_dir,
        )

        result = core.run_once()

        assert isinstance(result, dict), "run_once() should return dict"
        assert result["status"] == "error", f"Status should be 'error', got {result.get('status')}"
        assert result["code"] == "CONTROL_MISSING", f"Code should be 'CONTROL_MISSING', got {result.get('code')}"
        assert "detail" in result, "Result should have detail"


class TestRunOnceErrorWhenTaskMissing:
    """Test that run_once() returns error when task file is missing"""

    def test_run_once_error_when_task_missing(self, tmp_path):
        """Verify run_once returns {status:"error", code:"TASK_NOT_FOUND"} when task file is missing"""
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-9999\n", encoding="utf-8")

        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()

        core = GuardianCore(
            config=minimal_guardian_core_test_config(),
            control_path=control_file,
            tasks_dir=tasks_dir,
        )

        result = core.run_once()

        assert isinstance(result, dict), "run_once() should return dict"
        assert result["status"] == "error", f"Status should be 'error', got {result.get('status')}"
        assert result["code"] == "TASK_NOT_FOUND", f"Code should be 'TASK_NOT_FOUND', got {result.get('code')}"
        assert result["current_task"] == "TASK-9999", f"current_task should be TASK-9999, got {result.get('current_task')}"
        assert "detail" in result, "Result should have detail"


class TestTaskContractReadyWhenTaskPresent:
    """Test load_task_contract() ready path when a valid task file exists"""

    def test_load_task_contract_ready_when_task_present(self, tmp_path):
        """Verify load_task_contract returns ready with hash/preview for a valid contract."""
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        task_file = tasks_dir / "TASK-0001.md"
        task_content = """# TASK-0001 - Test Task

TASK_TYPE: CLEAR_CURRENT_TASK

## Goal
Test task for router verification.

## Scope
- test_file.py

## Acceptance
- Test passes
"""
        write_task_contract_file(task_file, task_content)

        core = GuardianCore(
            config=minimal_guardian_core_test_config(),
            tasks_dir=tasks_dir,
        )

        result = core.load_task_contract("TASK-0001")

        assert result["status"] == "ready", f"Status should be 'ready', got {result}"
        assert result["task_id"] == "TASK-0001"
        assert result["task_type"] == "CLEAR_CURRENT_TASK"
        assert "contract_hash" in result
        assert "contract_preview" in result

        contract_hash = result["contract_hash"]
        assert len(contract_hash) == 64
        assert all(c in "0123456789abcdef" for c in contract_hash)

        contract_preview = result["contract_preview"]
        assert "TASK-0001" in contract_preview
        assert "Goal" in contract_preview


class TestRunOnceMissingTaskType:
    """run_once() surfaces contract validation errors (does not return legacy ready)."""

    def test_run_once_error_when_task_type_missing(self, tmp_path):
        """Missing TASK_TYPE returns TASK_TYPE_INVALID via run_once (no execution)."""
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-0001\n", encoding="utf-8")

        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        task_file = tasks_dir / "TASK-0001.md"
        write_task_contract_file(
            task_file,
            "# TASK-0001 - Test Task\n\n## Goal\nRouter test without TASK_TYPE.\n",
        )

        core = GuardianCore(
            config=minimal_guardian_core_test_config(),
            control_path=control_file,
            tasks_dir=tasks_dir,
        )

        result = core.run_once()

        assert result["status"] == "error"
        assert result["code"] == "TASK_TYPE_INVALID"
        assert result["current_task"] == "TASK-0001"
        assert "TASK_TYPE" in result.get("detail", "")


class TestLoadTaskContract:
    """Test load_task_contract() method directly"""

    def test_load_task_contract_success(self, tmp_path):
        """Verify load_task_contract() returns ready when TASK_TYPE is present."""
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        task_file = tasks_dir / "TASK-0001.md"
        write_task_contract_file(
            task_file,
            "TASK_TYPE: CLEAR_CURRENT_TASK\n# TASK-0001\nTest content\n",
        )

        core = GuardianCore(
            config=minimal_guardian_core_test_config(),
            tasks_dir=tasks_dir,
        )

        result = core.load_task_contract("TASK-0001")

        assert result["status"] == "ready", f"Status should be 'ready', got {result.get('status')}"
        assert result["task_id"] == "TASK-0001"
        assert result["task_type"] == "CLEAR_CURRENT_TASK"
        assert "contract_hash" in result
        assert "contract_preview" in result

    def test_load_task_contract_not_found(self, tmp_path):
        """Verify load_task_contract() returns error when task file is missing"""
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()

        core = GuardianCore(
            config=minimal_guardian_core_test_config(),
            tasks_dir=tasks_dir,
        )

        result = core.load_task_contract("TASK-9999")

        assert result["status"] == "error", f"Status should be 'error', got {result.get('status')}"
        assert result["code"] == "TASK_NOT_FOUND", f"Code should be 'TASK_NOT_FOUND', got {result.get('code')}"
        assert result["task_id"] == "TASK-9999"

    def test_load_task_contract_missing_task_type(self, tmp_path):
        """Verify missing TASK_TYPE returns TASK_TYPE_INVALID (controlled error)."""
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        task_file = tasks_dir / "TASK-0001.md"
        write_task_contract_file(task_file, "# TASK-0001\nNo directive\n")

        core = GuardianCore(
            config=minimal_guardian_core_test_config(),
            tasks_dir=tasks_dir,
        )

        result = core.load_task_contract("TASK-0001")

        assert result["status"] == "error"
        assert result["code"] == "TASK_TYPE_INVALID"
        assert "Missing TASK_TYPE" in result.get("detail", "")


class TestReadControlTask:
    """Test _read_control_task() method directly"""

    def test_read_control_task_none(self, tmp_path):
        """Verify _read_control_task() returns None when CURRENT_TASK is NONE"""
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: NONE\n", encoding="utf-8")

        core = GuardianCore(
            config=minimal_guardian_core_test_config(),
            control_path=control_file,
        )

        result = core._read_control_task()

        assert result is None, f"_read_control_task() should return None for NONE, got {result}"

    def test_read_control_task_valid(self, tmp_path):
        """Verify _read_control_task() returns task ID when CURRENT_TASK is set"""
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-0001\n", encoding="utf-8")

        core = GuardianCore(
            config=minimal_guardian_core_test_config(),
            control_path=control_file,
        )

        result = core._read_control_task()

        assert result == "TASK-0001", f"_read_control_task() should return TASK-0001, got {result}"

    def test_read_control_task_missing_file(self, tmp_path):
        """Verify _read_control_task() returns None when CONTROL.md is missing"""
        control_file = tmp_path / "CONTROL.md"

        core = GuardianCore(
            config=minimal_guardian_core_test_config(),
            control_path=control_file,
        )

        result = core._read_control_task()

        assert result is None, f"_read_control_task() should return None when file missing, got {result}"
