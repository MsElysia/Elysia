"""
Apply Mutation Task Tests
==========================
Tests for APPLY_MUTATION task type execution in GuardianCore.
Verifies contract validation, payload validation, and mutation execution flows.
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch

from project_guardian.core import GuardianCore
from project_guardian.mutation import MutationDeniedError, MutationReviewRequiredError, MutationApplyError, MutationResult
from project_guardian.trust import TrustMatrix, TrustDecision, GOVERNANCE_MUTATION


class TestInvalidContract:
    """Test that invalid contracts return structured error"""
    
    def test_bad_mutation_file_path_returns_error(self, tmp_path):
        """Verify bad MUTATION_FILE path returns TASK_CONTRACT_INVALID"""
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-0001\n")
        
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        task_file = tasks_dir / "TASK-0001.md"
        task_file.write_text("TASK_TYPE: APPLY_MUTATION\nMUTATION_FILE: ../invalid.json\nALLOW_GOVERNANCE_MUTATION: false\n")
        
        mutations_dir = tmp_path / "MUTATIONS"
        mutations_dir.mkdir()
        
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(config=config, control_path=control_file, tasks_dir=tasks_dir, mutations_dir=mutations_dir)
        
        result = core.run_once()
        
        assert result["status"] == "error", f"Status should be 'error', got {result.get('status')}"
        assert result["code"] == "TASK_CONTRACT_INVALID", f"Code should be 'TASK_CONTRACT_INVALID', got {result.get('code')}"
        assert ".." in result.get("detail", ""), "Detail should mention .. segments"
    
    def test_mutation_file_not_under_mutations_returns_error(self, tmp_path):
        """Verify MUTATION_FILE not under MUTATIONS/ returns error"""
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-0001\n")
        
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        task_file = tasks_dir / "TASK-0001.md"
        task_file.write_text("TASK_TYPE: APPLY_MUTATION\nMUTATION_FILE: other/test.json\nALLOW_GOVERNANCE_MUTATION: false\n")
        
        mutations_dir = tmp_path / "MUTATIONS"
        mutations_dir.mkdir()
        
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(config=config, control_path=control_file, tasks_dir=tasks_dir, mutations_dir=mutations_dir)
        
        result = core.run_once()
        
        assert result["status"] == "error", f"Status should be 'error', got {result.get('status')}"
        assert result["code"] == "TASK_CONTRACT_INVALID", f"Code should be 'TASK_CONTRACT_INVALID', got {result.get('code')}"
        assert "MUTATIONS/" in result.get("detail", ""), "Detail should mention MUTATIONS/"


class TestInvalidPayload:
    """Test that invalid payloads return structured error"""
    
    def test_touched_paths_mismatch_returns_error(self, tmp_path):
        """Verify touched_paths mismatch with changes returns MUTATION_PAYLOAD_INVALID"""
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-0001\n")
        
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        task_file = tasks_dir / "TASK-0001.md"
        task_file.write_text("TASK_TYPE: APPLY_MUTATION\nMUTATION_FILE: MUTATIONS/test.json\nALLOW_GOVERNANCE_MUTATION: false\n")
        
        mutations_dir = tmp_path / "MUTATIONS"
        mutations_dir.mkdir()
        payload_file = mutations_dir / "test.json"
        payload = {
            "touched_paths": ["file1.py", "file2.py"],
            "changes": [
                {"path": "file1.py", "content": "print('test')\n"}
            ],
            "summary": "Test"
        }
        payload_file.write_text(json.dumps(payload))
        
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(config=config, control_path=control_file, tasks_dir=tasks_dir, mutations_dir=mutations_dir)
        
        result = core.run_once()
        
        assert result["status"] == "error", f"Status should be 'error', got {result.get('status')}"
        assert result["code"] == "MUTATION_PAYLOAD_INVALID", f"Code should be 'MUTATION_PAYLOAD_INVALID', got {result.get('code')}"
        assert "touched_paths" in result.get("detail", "").lower(), "Detail should mention touched_paths mismatch"


class TestProtectedPathWithoutOverride:
    """Test that protected paths without override are denied"""
    
    def test_protected_path_without_override_returns_denied(self, tmp_path):
        """Verify protected path without override returns status=='denied'"""
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-0001\n")
        
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        task_file = tasks_dir / "TASK-0001.md"
        task_file.write_text("TASK_TYPE: APPLY_MUTATION\nMUTATION_FILE: MUTATIONS/test.json\nALLOW_GOVERNANCE_MUTATION: false\n")
        
        mutations_dir = tmp_path / "MUTATIONS"
        mutations_dir.mkdir()
        payload_file = mutations_dir / "test.json"
        payload = {
            "touched_paths": ["CONTROL.md"],
            "changes": [
                {"path": "CONTROL.md", "content": "CURRENT_TASK: NONE\n"}
            ],
            "summary": "Test"
        }
        payload_file.write_text(json.dumps(payload))
        
        # Create test CONTROL.md file
        test_control = tmp_path / "CONTROL.md"
        test_control.write_text("CURRENT_TASK: TASK-0001\n")
        
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(config=config, control_path=control_file, tasks_dir=tasks_dir, mutations_dir=mutations_dir)
        
        result = core.run_once()
        
        assert result["status"] == "denied", f"Status should be 'denied', got {result.get('status')}"
        assert result["code"] == "MUTATION_DENIED", f"Code should be 'MUTATION_DENIED', got {result.get('code')}"
        assert "reason_code" in result, "Result should have reason_code"


class TestReviewFlow:
    """Test that review flow works correctly"""
    
    def test_review_flow_returns_needs_review(self, tmp_path):
        """Verify review decision returns status=='needs_review' with request_id"""
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-0001\n")
        
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        task_file = tasks_dir / "TASK-0001.md"
        task_file.write_text("TASK_TYPE: APPLY_MUTATION\nMUTATION_FILE: MUTATIONS/test.json\nALLOW_GOVERNANCE_MUTATION: true\n")
        
        mutations_dir = tmp_path / "MUTATIONS"
        mutations_dir.mkdir()
        payload_file = mutations_dir / "test.json"
        payload = {
            "touched_paths": ["CONTROL.md"],
            "changes": [
                {"path": "CONTROL.md", "content": "CURRENT_TASK: NONE\n"}
            ],
            "summary": "Test"
        }
        payload_file.write_text(json.dumps(payload))
        
        # Create test CONTROL.md file
        test_control = tmp_path / "CONTROL.md"
        test_control.write_text("CURRENT_TASK: TASK-0001\n")
        
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(config=config, control_path=control_file, tasks_dir=tasks_dir, mutations_dir=mutations_dir)
        
        # Mock TrustMatrix to return review decision
        review_decision = TrustDecision(
            allowed=False,
            decision="review",
            reason_code="BORDERLINE_TRUST_GOVERNANCE_MUTATION",
            message="Borderline trust",
            risk_score=0.85
        )
        core.trust.validate_trust_for_action = Mock(return_value=review_decision)
        
        result = core.run_once()
        
        assert result["status"] == "needs_review", f"Status should be 'needs_review', got {result.get('status')}"
        assert result["outcome"] == "mutation_review_required", f"Outcome should be 'mutation_review_required', got {result.get('outcome')}"
        assert "request_id" in result, "Result should have request_id"
        assert result["request_id"] is not None, "request_id should not be None"
        
        # Verify request was enqueued
        pending = core.mutation.review_queue.list_pending()
        assert len(pending) >= 1, "Review request should be enqueued"


class TestApprovalReplay:
    """Test that approval replay works correctly"""
    
    def test_approval_replay_applies_mutation(self, tmp_path):
        """Verify approved request_id allows mutation to proceed"""
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-0001\n")
        
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        
        mutations_dir = tmp_path / "MUTATIONS"
        mutations_dir.mkdir()
        payload_file = mutations_dir / "test.json"
        payload = {
            "touched_paths": ["test.py"],
            "changes": [
                {"path": "test.py", "content": "print('new')\n"}
            ],
            "summary": "Test mutation"
        }
        payload_file.write_text(json.dumps(payload))
        
        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('old')\n")
        
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(config=config, control_path=control_file, tasks_dir=tasks_dir, mutations_dir=mutations_dir)
        
        # Create and approve a request
        context = {
            "component": "MutationEngine",
            "action": GOVERNANCE_MUTATION,
            "touched_paths": sorted(["test.py"]),
            "override_flag": False,
            "caller_identity": "GuardianCore",
            "task_id": "TASK-0001"
        }
        request_id = core.mutation.review_queue.enqueue("MutationEngine", GOVERNANCE_MUTATION, context)
        core.mutation.approval_store.approve(request_id, context=context)
        
        # Create task with REQUEST_ID
        task_file = tasks_dir / "TASK-0001.md"
        task_file.write_text(f"TASK_TYPE: APPLY_MUTATION\nMUTATION_FILE: MUTATIONS/test.json\nALLOW_GOVERNANCE_MUTATION: false\nREQUEST_ID: {request_id}\n")
        
        result = core.run_once()
        
        assert result["status"] == "ok", f"Status should be 'ok', got {result.get('status')}"
        assert result["outcome"] == "mutation_applied", f"Outcome should be 'mutation_applied', got {result.get('outcome')}"
        assert len(result["changed_files"]) == 1, "Should have one changed file"
        assert result["changed_files"][0].endswith("test.py"), "Changed file should be test.py"
        
        # Verify file was modified
        assert test_file.read_text() == "print('new')\n", "File should be modified"


class TestPathSafety:
    """Test that path safety validation works"""
    
    def test_path_with_dotdot_returns_error(self, tmp_path):
        """Verify paths with .. are rejected"""
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-0001\n")
        
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        task_file = tasks_dir / "TASK-0001.md"
        task_file.write_text("TASK_TYPE: APPLY_MUTATION\nMUTATION_FILE: MUTATIONS/test.json\nALLOW_GOVERNANCE_MUTATION: false\n")
        
        mutations_dir = tmp_path / "MUTATIONS"
        mutations_dir.mkdir()
        payload_file = mutations_dir / "test.json"
        payload = {
            "touched_paths": ["../outside.py"],
            "changes": [
                {"path": "../outside.py", "content": "print('test')\n"}
            ],
            "summary": "Test"
        }
        payload_file.write_text(json.dumps(payload))
        
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(config=config, control_path=control_file, tasks_dir=tasks_dir, mutations_dir=mutations_dir)
        
        result = core.run_once()
        
        assert result["status"] == "error", f"Status should be 'error', got {result.get('status')}"
        assert result["code"] == "MUTATION_PAYLOAD_INVALID", f"Code should be 'MUTATION_PAYLOAD_INVALID', got {result.get('code')}"
        assert ".." in result.get("detail", ""), "Detail should mention .."
