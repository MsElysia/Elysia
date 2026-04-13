"""
MutationEngine Smoke Tests
==========================
Behavioral tests for MutationEngine deny/review/replay/success paths.
Verifies governance gating, ReviewQueue integration, and approval replay.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from project_guardian.mutation import (
    MutationEngine, 
    MutationDeniedError, 
    MutationReviewRequiredError, 
    MutationApplyError,
    MutationResult
)
from project_guardian.trust import TrustMatrix, TrustDecision, GOVERNANCE_MUTATION
from project_guardian.memory import MemoryCore
from project_guardian.review_queue import ReviewQueue
from project_guardian.approval_store import ApprovalStore


class TestProtectedPathDenied:
    """Test A: Protected path denied - raises MutationDeniedError"""
    
    def test_protected_path_without_override_raises_exception(self):
        """Verify mutation touching CONTROL.md without override raises MutationDeniedError"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        mutation = MutationEngine(memory, trust_matrix=trust)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file that looks like CONTROL.md
            test_file = Path(tmpdir) / "CONTROL.md"
            test_file.write_text("CURRENT_TASK: NONE\n")
            
            # Attempt mutation without override
            with pytest.raises(MutationDeniedError) as exc_info:
                mutation.apply(
                    str(test_file),
                    "CURRENT_TASK: TASK-0001\n",
                    origin="test",
                    allow_governance_mutation=False
                )
            
            # Verify exception details
            assert exc_info.value.filename == str(test_file)
            assert exc_info.value.reason == "PROTECTED_PATH_WITHOUT_OVERRIDE"
            
            # Verify file was NOT modified
            assert test_file.read_text() == "CURRENT_TASK: NONE\n", "File should not be modified on deny"


class TestProtectedPathReview:
    """Test B: Protected path review - enqueues request and raises MutationReviewRequiredError"""
    
    def test_review_decision_enqueues_request_and_raises_exception(self):
        """Verify review decision enqueues request and raises MutationReviewRequiredError"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            store_file = Path(tmpdir) / "approval_store.json"
            
            review_queue = ReviewQueue(queue_file=queue_file, memory=memory)
            approval_store = ApprovalStore(store_file=store_file)
            
            mutation = MutationEngine(
                memory, 
                trust_matrix=trust,
                review_queue=review_queue,
                approval_store=approval_store
            )
            
            # Mock trust to return review decision
            review_decision = TrustDecision(
                allowed=False,
                decision="review",
                reason_code="BORDERLINE_TRUST_GOVERNANCE_MUTATION",
                message="Borderline trust",
                risk_score=0.85
            )
            trust.validate_trust_for_action = Mock(return_value=review_decision)
            
            test_file = Path(tmpdir) / "CONTROL.md"
            test_file.write_text("CURRENT_TASK: NONE\n")
            
            # Attempt mutation with override
            with pytest.raises(MutationReviewRequiredError) as exc_info:
                mutation.apply(
                    str(test_file),
                    "CURRENT_TASK: TASK-0001\n",
                    origin="test",
                    allow_governance_mutation=True
                )
            
            # Verify exception has request_id
            assert exc_info.value.request_id is not None
            assert len(exc_info.value.request_id) > 0
            
            # Verify request was enqueued
            pending = review_queue.list_pending()
            assert len(pending) == 1, "Review request should be enqueued"
            assert pending[0].request_id == exc_info.value.request_id
            assert pending[0].component == "MutationEngine"
            assert pending[0].action == GOVERNANCE_MUTATION
            
            # Verify file was NOT modified
            assert test_file.read_text() == "CURRENT_TASK: NONE\n", "File should not be modified on review"


class TestApprovalReplay:
    """Test C: Approval replay works - approved request_id bypasses review"""
    
    def test_approved_replay_bypasses_review_and_succeeds(self):
        """Verify approved request_id bypasses review and mutation succeeds"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            store_file = Path(tmpdir) / "approval_store.json"
            
            review_queue = ReviewQueue(queue_file=queue_file, memory=memory)
            approval_store = ApprovalStore(store_file=store_file)
            
            mutation = MutationEngine(
                memory, 
                trust_matrix=trust,
                review_queue=review_queue,
                approval_store=approval_store
            )
            
            # Create and approve a request
            context = {
                "component": "MutationEngine",
                "action": GOVERNANCE_MUTATION,
                "touched_paths": sorted(["CONTROL.md"]),  # Sorted for deterministic hashing
                "override_flag": True,
                "caller_identity": "test",
                "task_id": "test"
            }
            request_id = review_queue.enqueue("MutationEngine", GOVERNANCE_MUTATION, context)
            approval_store.approve(request_id, context=context)
            
            test_file = Path(tmpdir) / "CONTROL.md"
            test_file.write_text("CURRENT_TASK: NONE\n")
            
            # Call apply with approved request_id
            result = mutation.apply(
                str(test_file),
                "CURRENT_TASK: TASK-0001\n",
                origin="test",
                allow_governance_mutation=True,
                request_id=request_id,
                caller_identity="test",
                task_id="test"
            )
            
            # Verify result is MutationResult
            assert isinstance(result, MutationResult), "Result should be MutationResult"
            assert result.ok is True, "Mutation should succeed"
            assert len(result.changed_files) == 1, "Should have one changed file"
            assert result.changed_files[0] == str(test_file), "Changed file should match"
            assert len(result.backup_paths) == 1, "Should have one backup"
            
            # Verify file was modified
            assert test_file.read_text() == "CURRENT_TASK: TASK-0001\n", "File should be modified on success"
            
            # Verify backup exists
            backup_path = Path(result.backup_paths[0])
            assert backup_path.exists(), "Backup should exist"
            assert backup_path.read_text() == "CURRENT_TASK: NONE\n", "Backup should contain original content"


class TestCoreDecisionSemantics:
    """Test D: Core uses decision semantics - branches on decision.decision not truthiness"""
    
    def test_core_uses_decision_semantics(self):
        """Verify Core branches on decision.decision not truthiness"""
        from project_guardian.core import GuardianCore
        
        memory = MemoryCore()
        core = GuardianCore(config={})
        
        # Mock trust to return deny decision
        deny_decision = TrustDecision(
            allowed=False,
            decision="deny",
            reason_code="INSUFFICIENT_TRUST_MUTATION",
            message="Insufficient trust",
            risk_score=0.9
        )
        core.trust.validate_trust_for_action = Mock(return_value=deny_decision)
        
        # Call propose_mutation (should handle deny decision correctly)
        result = core.propose_mutation("test.py", "print('test')", require_consensus=False)
        
        # Verify result indicates denial (not success)
        assert "blocked" in result.lower() or "denied" in result.lower(), \
            "Core should handle deny decision correctly (not treat as truthy)"
        
        # Verify trust.validate_trust_for_action was called (not treated as bool)
        core.trust.validate_trust_for_action.assert_called_once()
        call_args = core.trust.validate_trust_for_action.call_args
        assert call_args[0][0] == "mutation_engine", "Component should be mutation_engine"
        assert call_args[0][1] in ["mutation", GOVERNANCE_MUTATION], "Action should be mutation or GOVERNANCE_MUTATION"


class TestNonProtectedPathSuccess:
    """Test that non-protected paths succeed without governance gating"""
    
    def test_non_protected_path_succeeds(self):
        """Verify mutation to non-protected file succeeds without governance gating"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        mutation = MutationEngine(memory, trust_matrix=trust)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("print('old')\n")
            
            # Apply mutation (non-protected path, no override needed)
            result = mutation.apply(
                str(test_file),
                "print('new')\n",
                origin="test"
            )
            
            # Verify result is MutationResult
            assert isinstance(result, MutationResult), "Result should be MutationResult"
            assert result.ok is True, "Mutation should succeed"
            assert len(result.changed_files) == 1, "Should have one changed file"
            
            # Verify file was modified
            assert test_file.read_text() == "print('new')\n", "File should be modified"
            
            # Verify backup exists
            backup_path = Path(result.backup_paths[0])
            assert backup_path.exists(), "Backup should exist"
            assert backup_path.read_text() == "print('old')\n", "Backup should contain original content"


class TestReviewWithGptDisabled:
    """Test that review_with_gpt() is disabled and always rejects"""
    
    def test_review_with_gpt_always_rejects(self):
        """Verify review_with_gpt() always returns 'reject' (disabled)"""
        memory = MemoryCore()
        mutation = MutationEngine(memory)
        
        # Call review_with_gpt (should always reject)
        result = mutation.review_with_gpt("print('test')", "test.py")
        
        # Verify it always rejects
        assert result == "reject", "review_with_gpt() should always reject (disabled)"
        
        # Verify memory was logged
        # (We can't easily check memory contents, but the method should log)


class TestContextMismatchReplay:
    """Test that approval replay fails on context mismatch"""
    
    def test_context_mismatch_rejects_replay(self):
        """Verify approval replay fails if context doesn't match"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            store_file = Path(tmpdir) / "approval_store.json"
            
            review_queue = ReviewQueue(queue_file=queue_file, memory=memory)
            approval_store = ApprovalStore(store_file=store_file)
            
            mutation = MutationEngine(
                memory, 
                trust_matrix=trust,
                review_queue=review_queue,
                approval_store=approval_store
            )
            
            # Create and approve a request for CONTROL.md
            context_control = {
                "component": "MutationEngine",
                "action": GOVERNANCE_MUTATION,
                "touched_paths": sorted(["CONTROL.md"]),
                "override_flag": True,
                "caller_identity": "test",
                "task_id": "test"
            }
            request_id = review_queue.enqueue("MutationEngine", GOVERNANCE_MUTATION, context_control)
            approval_store.approve(request_id, context=context_control)
            
            # Try to use same request_id for different file (SPEC.md)
            test_file = Path(tmpdir) / "SPEC.md"
            test_file.write_text("OLD\n")
            
            # Should raise MutationDeniedError (context mismatch)
            with pytest.raises(MutationDeniedError) as exc_info:
                mutation.apply(
                    str(test_file),  # Different file
                    "NEW\n",
                    origin="test",
                    allow_governance_mutation=True,
                    request_id=request_id,  # Same request_id but different context
                    caller_identity="test",
                    task_id="test"
                )
            
            # Verify exception reason
            assert exc_info.value.reason == "APPROVAL_NOT_FOUND_OR_CONTEXT_MISMATCH", \
                "Context mismatch should be detected"
            
            # Verify file was NOT modified
            assert test_file.read_text() == "OLD\n", "File should not be modified on context mismatch"
