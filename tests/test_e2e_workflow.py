"""
End-to-End Workflow Tests
==========================
Tests for complete workflow: task → review → approval → replay → success.
Verifies preflight prevents partial applies and full workflow works end-to-end.
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock

from project_guardian.core import GuardianCore
from project_guardian.trust import TrustMatrix, TrustDecision, GOVERNANCE_MUTATION
from project_guardian.memory import MemoryCore


class TestReviewApproveReplaySuccess:
    """Test 1: Review → approve → replay → success (single file)"""
    
    def test_review_approve_replay_success_workflow(self, tmp_path):
        """Verify complete workflow: review → approve → replay → success"""
        # Setup temp directories
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-0001\n")
        
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        
        mutations_dir = tmp_path / "MUTATIONS"
        mutations_dir.mkdir()
        
        reports_dir = tmp_path / "REPORTS"
        reports_dir.mkdir()
        
        # Create task file
        task_file = tasks_dir / "TASK-0001.md"
        task_file.write_text("TASK_TYPE: APPLY_MUTATION\nMUTATION_FILE: MUTATIONS/test.json\nALLOW_GOVERNANCE_MUTATION: true\n")
        
        # Create mutation payload
        payload_file = mutations_dir / "test.json"
        test_file_path = "test.py"
        payload = {
            "touched_paths": [test_file_path],
            "changes": [
                {"path": test_file_path, "content": "print('new')\n"}
            ],
            "summary": "Test mutation"
        }
        payload_file.write_text(json.dumps(payload))
        
        # Create test file
        test_file = tmp_path / test_file_path
        test_file.write_text("print('old')\n")
        
        # Initialize Core
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(
            config=config,
            control_path=control_file,
            tasks_dir=tasks_dir,
            mutations_dir=mutations_dir
        )
        
        # Force TrustMatrix to return review decision initially
        review_decision = TrustDecision(
            allowed=False,
            decision="review",
            reason_code="BORDERLINE_TRUST_GOVERNANCE_MUTATION",
            message="Borderline trust",
            risk_score=0.85
        )
        core.trust.validate_trust_for_action = Mock(return_value=review_decision)
        
        # Step 1: Run once - should trigger review
        result1 = core.run_once()
        
        assert result1["status"] == "needs_review", f"First run should return needs_review, got {result1.get('status')}"
        assert "request_id" in result1, "Result should have request_id"
        request_id = result1["request_id"]
        
        # Verify review queue contains entry
        pending = core.mutation.review_queue.list_pending()
        assert len(pending) >= 1, "Review request should be enqueued"
        
        # Verify target file is unchanged
        assert test_file.read_text() == "print('old')\n", "File should be unchanged after review decision"
        
        # Step 2: Approve request_id with matching context
        context = {
            "component": "MutationEngine",
            "action": GOVERNANCE_MUTATION,
            "touched_paths": sorted([test_file_path]),
            "override_flag": True,
            "caller_identity": "GuardianCore",
            "task_id": "TASK-0001"
        }
        core.mutation.approval_store.approve(request_id, context=context)
        
        # Step 3: Update task file with REQUEST_ID
        task_file.write_text(f"TASK_TYPE: APPLY_MUTATION\nMUTATION_FILE: MUTATIONS/test.json\nALLOW_GOVERNANCE_MUTATION: true\nREQUEST_ID: {request_id}\n")
        
        # Step 4: Run once again - should succeed with replay
        result2 = core.run_once()
        
        assert result2["status"] == "ok", f"Second run should return ok, got {result2.get('status')}"
        assert result2["outcome"] == "mutation_applied", f"Outcome should be mutation_applied, got {result2.get('outcome')}"
        assert len(result2["changed_files"]) == 1, "Should have one changed file"
        assert len(result2["backup_paths"]) == 1, "Should have one backup"
        assert "summary" in result2, "Result should have summary"
        
        # Verify file content changed
        assert test_file.read_text() == "print('new')\n", "File should be modified after approval replay"
        
        # Verify backup exists
        backup_path = Path(result2["backup_paths"][0])
        assert backup_path.exists(), "Backup should exist"
        assert backup_path.read_text() == "print('old')\n", "Backup should contain original content"


class TestPreflightPreventsPartialApply:
    """Test 2: Preflight prevents partial apply (two files, second would trigger review/deny)"""
    
    def test_preflight_prevents_partial_apply(self, tmp_path):
        """Verify preflight prevents partial apply when second file would trigger review"""
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-0001\n")
        
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        
        mutations_dir = tmp_path / "MUTATIONS"
        mutations_dir.mkdir()
        
        reports_dir = tmp_path / "REPORTS"
        reports_dir.mkdir()
        
        # Create task file
        task_file = tasks_dir / "TASK-0001.md"
        task_file.write_text("TASK_TYPE: APPLY_MUTATION\nMUTATION_FILE: MUTATIONS/test.json\nALLOW_GOVERNANCE_MUTATION: true\n")
        
        # Create mutation payload with two files
        payload_file = mutations_dir / "test.json"
        file_a_path = "file_a.py"
        file_b_path = "CONTROL.md"  # Protected file
        payload = {
            "touched_paths": [file_a_path, file_b_path],
            "changes": [
                {"path": file_a_path, "content": "print('a')\n"},
                {"path": file_b_path, "content": "CURRENT_TASK: NONE\n"}
            ],
            "summary": "Test mutation"
        }
        payload_file.write_text(json.dumps(payload))
        
        # Create test files
        file_a = tmp_path / file_a_path
        file_a.write_text("print('old_a')\n")
        
        file_b = tmp_path / file_b_path
        file_b.write_text("CURRENT_TASK: TASK-0001\n")
        
        # Initialize Core
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(
            config=config,
            control_path=control_file,
            tasks_dir=tasks_dir,
            mutations_dir=mutations_dir
        )
        
        # Force TrustMatrix to return review decision for governance mutation
        review_decision = TrustDecision(
            allowed=False,
            decision="review",
            reason_code="BORDERLINE_TRUST_GOVERNANCE_MUTATION",
            message="Borderline trust",
            risk_score=0.85
        )
        core.trust.validate_trust_for_action = Mock(return_value=review_decision)
        
        # Run once - should trigger review (preflight should catch this before any writes)
        result = core.run_once()
        
        assert result["status"] == "needs_review", f"Status should be needs_review, got {result.get('status')}"
        assert "request_id" in result, "Result should have request_id"
        
        # Verify NEITHER file changed (preflight prevented partial apply)
        assert file_a.read_text() == "print('old_a')\n", "File A should be unchanged (preflight prevented apply)"
        assert file_b.read_text() == "CURRENT_TASK: TASK-0001\n", "File B should be unchanged (preflight prevented apply)"


class TestProtectedPathWithoutOverride:
    """Test 3: Protected path without override denied without writes"""
    
    def test_protected_path_without_override_denied_no_writes(self, tmp_path):
        """Verify protected path without override is denied without any writes"""
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-0001\n")
        
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        
        mutations_dir = tmp_path / "MUTATIONS"
        mutations_dir.mkdir()
        
        reports_dir = tmp_path / "REPORTS"
        reports_dir.mkdir()
        
        # Create task file with ALLOW_GOVERNANCE_MUTATION: false
        task_file = tasks_dir / "TASK-0001.md"
        task_file.write_text("TASK_TYPE: APPLY_MUTATION\nMUTATION_FILE: MUTATIONS/test.json\nALLOW_GOVERNANCE_MUTATION: false\n")
        
        # Create mutation payload touching CONTROL.md (protected)
        payload_file = mutations_dir / "test.json"
        payload = {
            "touched_paths": ["CONTROL.md"],
            "changes": [
                {"path": "CONTROL.md", "content": "CURRENT_TASK: NONE\n"}
            ],
            "summary": "Test mutation"
        }
        payload_file.write_text(json.dumps(payload))
        
        # Create test CONTROL.md file
        test_control = tmp_path / "CONTROL.md"
        test_control.write_text("CURRENT_TASK: TASK-0001\n")
        
        # Initialize Core
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(
            config=config,
            control_path=control_file,
            tasks_dir=tasks_dir,
            mutations_dir=mutations_dir
        )
        
        # Run once - should be denied immediately (preflight)
        result = core.run_once()
        
        assert result["status"] == "denied", f"Status should be denied, got {result.get('status')}"
        assert result["code"] == "MUTATION_DENIED", f"Code should be MUTATION_DENIED, got {result.get('code')}"
        assert result["reason_code"] == "PROTECTED_PATH_WITHOUT_OVERRIDE", \
            f"Reason code should be PROTECTED_PATH_WITHOUT_OVERRIDE, got {result.get('reason_code')}"
        
        # Verify CONTROL.md is unchanged (no writes occurred)
        assert test_control.read_text() == "CURRENT_TASK: TASK-0001\n", \
            "CONTROL.md should be unchanged (preflight denied without writes)"
        
        # Verify no backup files were created
        backup_dir = tmp_path / "guardian_backups"
        if backup_dir.exists():
            backups = list(backup_dir.glob("*"))
            assert len(backups) == 0, "No backup files should be created on denial"


class TestPreflightWithMultipleFiles:
    """Test that preflight works correctly with multiple files"""
    
    def test_preflight_allows_all_files_when_approved(self, tmp_path):
        """Verify preflight allows all files to be applied when approved"""
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-0001\n")
        
        tasks_dir = tmp_path / "TASKS"
        tasks_dir.mkdir()
        
        mutations_dir = tmp_path / "MUTATIONS"
        mutations_dir.mkdir()
        
        reports_dir = tmp_path / "REPORTS"
        reports_dir.mkdir()
        
        # Create task file
        task_file = tasks_dir / "TASK-0001.md"
        task_file.write_text("TASK_TYPE: APPLY_MUTATION\nMUTATION_FILE: MUTATIONS/test.json\nALLOW_GOVERNANCE_MUTATION: false\n")
        
        # Create mutation payload with two safe files
        payload_file = mutations_dir / "test.json"
        file_a_path = "file_a.py"
        file_b_path = "file_b.py"
        payload = {
            "touched_paths": [file_a_path, file_b_path],
            "changes": [
                {"path": file_a_path, "content": "print('a')\n"},
                {"path": file_b_path, "content": "print('b')\n"}
            ],
            "summary": "Test mutation"
        }
        payload_file.write_text(json.dumps(payload))
        
        # Create test files
        file_a = tmp_path / file_a_path
        file_a.write_text("print('old_a')\n")
        
        file_b = tmp_path / file_b_path
        file_b.write_text("print('old_b')\n")
        
        # Initialize Core
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        core = GuardianCore(
            config=config,
            control_path=control_file,
            tasks_dir=tasks_dir,
            mutations_dir=mutations_dir
        )
        
        # Run once - should succeed (both files are safe, no governance override needed)
        result = core.run_once()
        
        assert result["status"] == "ok", f"Status should be ok, got {result.get('status')}"
        assert result["outcome"] == "mutation_applied", f"Outcome should be mutation_applied, got {result.get('outcome')}"
        assert len(result["changed_files"]) == 2, "Should have two changed files"
        
        # Verify both files changed
        assert file_a.read_text() == "print('a')\n", "File A should be modified"
        assert file_b.read_text() == "print('b')\n", "File B should be modified"
