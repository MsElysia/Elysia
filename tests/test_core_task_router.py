"""
GuardianCore Task Router Tests
===============================
Tests for CONTROL.md integration and task routing in GuardianCore.
Verifies structured results from run_once() and task contract loading.
"""

import pytest
import tempfile
from pathlib import Path

from project_guardian.core import GuardianCore


class TestRunOnceIdleWhenNone:
    """Test that run_once() returns idle status when CURRENT_TASK is NONE"""
    
    def test_run_once_idle_when_none(self, tmp_path):
        """Verify run_once returns {status:"idle"} when CONTROL.md has CURRENT_TASK: NONE"""
        # Create temp CONTROL.md with NONE
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: NONE\n")
        
        # Create temp TASKS directory
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        
        # Initialize Core with temp paths
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(config=config, control_path=control_file, tasks_dir=tasks_dir)
        
        # Call run_once()
        result = core.run_once()
        
        # Verify result structure
        assert isinstance(result, dict), "run_once() should return dict"
        assert result["status"] == "idle", f"Status should be 'idle', got {result.get('status')}"
        assert result["current_task"] is None, "current_task should be None when NONE"
        assert "timestamp" in result, "Result should have timestamp"


class TestRunOnceErrorWhenControlMissing:
    """Test that run_once() returns error when CONTROL.md is missing"""
    
    def test_run_once_error_when_control_missing(self, tmp_path):
        """Verify run_once returns {status:"error", code:"CONTROL_MISSING"} when CONTROL.md is missing"""
        # Create temp TASKS directory (but no CONTROL.md)
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        
        # Initialize Core with temp paths (CONTROL.md doesn't exist)
        control_file = tmp_path / "CONTROL.md"  # File doesn't exist
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(config=config, control_path=control_file, tasks_dir=tasks_dir)
        
        # Call run_once()
        result = core.run_once()
        
        # Verify result structure
        assert isinstance(result, dict), "run_once() should return dict"
        assert result["status"] == "error", f"Status should be 'error', got {result.get('status')}"
        assert result["code"] == "CONTROL_MISSING", f"Code should be 'CONTROL_MISSING', got {result.get('code')}"
        assert "detail" in result, "Result should have detail"


class TestRunOnceErrorWhenTaskMissing:
    """Test that run_once() returns error when task file is missing"""
    
    def test_run_once_error_when_task_missing(self, tmp_path):
        """Verify run_once returns {status:"error", code:"TASK_NOT_FOUND"} when task file is missing"""
        # Create temp CONTROL.md pointing to non-existent task
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-9999\n")
        
        # Create temp TASKS directory (but no TASK-9999.md)
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        
        # Initialize Core with temp paths
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(config=config, control_path=control_file, tasks_dir=tasks_dir)
        
        # Call run_once()
        result = core.run_once()
        
        # Verify result structure
        assert isinstance(result, dict), "run_once() should return dict"
        assert result["status"] == "error", f"Status should be 'error', got {result.get('status')}"
        assert result["code"] == "TASK_NOT_FOUND", f"Code should be 'TASK_NOT_FOUND', got {result.get('code')}"
        assert result["current_task"] == "TASK-9999", f"current_task should be TASK-9999, got {result.get('current_task')}"
        assert "detail" in result, "Result should have detail"


class TestRunOnceReadyWhenTaskPresent:
    """Test that run_once() returns ready status when task file exists"""
    
    def test_run_once_ready_when_task_present(self, tmp_path):
        """Verify run_once returns {status:"ready"} with contract_hash and contract_preview when task exists"""
        # Create temp CONTROL.md pointing to TASK-0001
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-0001\n")
        
        # Create temp TASKS directory and TASK-0001.md
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        task_file = tasks_dir / "TASK-0001.md"
        task_content = """# TASK-0001 — Test Task

## Goal
Test task for router verification.

## Scope
- test_file.py

## Acceptance
- Test passes
"""
        task_file.write_text(task_content)
        
        # Initialize Core with temp paths
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(config=config, control_path=control_file, tasks_dir=tasks_dir)
        
        # Call run_once()
        result = core.run_once()
        
        # Verify result structure
        assert isinstance(result, dict), "run_once() should return dict"
        assert result["status"] == "ready", f"Status should be 'ready', got {result.get('status')}"
        assert result["current_task"] == "TASK-0001", f"current_task should be TASK-0001, got {result.get('current_task')}"
        assert "contract_hash" in result, "Result should have contract_hash"
        assert "contract_preview" in result, "Result should have contract_preview"
        
        # Verify contract_hash is a valid SHA256 hash (64 hex chars)
        contract_hash = result["contract_hash"]
        assert len(contract_hash) == 64, f"contract_hash should be 64 chars, got {len(contract_hash)}"
        assert all(c in '0123456789abcdef' for c in contract_hash), "contract_hash should be hex"
        
        # Verify contract_preview contains task content
        contract_preview = result["contract_preview"]
        assert "TASK-0001" in contract_preview, "contract_preview should contain task ID"
        assert "Goal" in contract_preview, "contract_preview should contain task content"


class TestLoadTaskContract:
    """Test load_task_contract() method directly"""
    
    def test_load_task_contract_success(self, tmp_path):
        """Verify load_task_contract() returns ready status when task exists"""
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        task_file = tasks_dir / "TASK-0001.md"
        task_content = "# TASK-0001\nTest content"
        task_file.write_text(task_content)
        
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(config=config, tasks_dir=tasks_dir)
        
        result = core.load_task_contract("TASK-0001")
        
        assert result["status"] == "ready", f"Status should be 'ready', got {result.get('status')}"
        assert result["task_id"] == "TASK-0001", f"task_id should be TASK-0001, got {result.get('task_id')}"
        assert "contract_hash" in result, "Result should have contract_hash"
        assert "contract_preview" in result, "Result should have contract_preview"
    
    def test_load_task_contract_not_found(self, tmp_path):
        """Verify load_task_contract() returns error when task file is missing"""
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        # No task file created
        
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(config=config, tasks_dir=tasks_dir)
        
        result = core.load_task_contract("TASK-9999")
        
        assert result["status"] == "error", f"Status should be 'error', got {result.get('status')}"
        assert result["code"] == "TASK_NOT_FOUND", f"Code should be 'TASK_NOT_FOUND', got {result.get('code')}"
        assert result["task_id"] == "TASK-9999", f"task_id should be TASK-9999, got {result.get('task_id')}"


class TestReadControlTask:
    """Test _read_control_task() method directly"""
    
    def test_read_control_task_none(self, tmp_path):
        """Verify _read_control_task() returns None when CURRENT_TASK is NONE"""
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: NONE\n")
        
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(config=config, control_path=control_file)
        
        result = core._read_control_task()
        
        assert result is None, f"_read_control_task() should return None for NONE, got {result}"
    
    def test_read_control_task_valid(self, tmp_path):
        """Verify _read_control_task() returns task ID when CURRENT_TASK is set"""
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-0001\n")
        
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(config=config, control_path=control_file)
        
        result = core._read_control_task()
        
        assert result == "TASK-0001", f"_read_control_task() should return TASK-0001, got {result}"
    
    def test_read_control_task_missing_file(self, tmp_path):
        """Verify _read_control_task() returns None when CONTROL.md is missing"""
        control_file = tmp_path / "CONTROL.md"  # File doesn't exist
        
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(config=config, control_path=control_file)
        
        result = core._read_control_task()
        
        assert result is None, f"_read_control_task() should return None when file missing, got {result}"
