"""
MutationEngine Path Safety Tests
================================
Tests for path traversal prevention and repo-root enforcement in MutationEngine.
"""

import pytest
import sys
import os
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

try:
    from project_guardian.mutation import MutationEngine, MutationDeniedError, MutationReviewRequiredError
    from project_guardian.trust import TrustMatrix, TrustDecision, GOVERNANCE_MUTATION
    from project_guardian.review_queue import ReviewQueue
    from project_guardian.approval_store import ApprovalStore
    from project_guardian.memory import MemoryCore
    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False
    pytestmark = pytest.mark.skip("Required modules not available")


class TestMutationPathSafety:
    """Test MutationEngine path safety validation"""
    
    @pytest.fixture
    def memory(self):
        """Create MemoryCore instance"""
        return MemoryCore()
    
    @pytest.fixture
    def trust_matrix(self):
        """Create TrustMatrix that allows all actions"""
        trust = TrustMatrix()
        trust.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=True,
            decision="allow",
            reason_code="ALLOWED",
            message="Test allow",
            risk_score=0.1
        ))
        return trust
    
    @pytest.fixture
    def review_queue(self):
        """Create ReviewQueue"""
        return ReviewQueue()
    
    @pytest.fixture
    def approval_store(self):
        """Create ApprovalStore"""
        return ApprovalStore()
    
    @pytest.fixture
    def mutation_engine(self, memory, trust_matrix, review_queue, approval_store, tmp_path):
        """Create MutationEngine instance with temporary repo root"""
        return MutationEngine(
            memory,
            trust_matrix=trust_matrix,
            review_queue=review_queue,
            approval_store=approval_store,
            repo_root=tmp_path
        )
    
    def test_blocks_absolute_path_posix(self, mutation_engine, tmp_path):
        """Verify absolute paths are blocked (POSIX)"""
        if sys.platform == "win32":
            pytest.skip("POSIX-specific test")
        
        # Try to mutate /etc/passwd
        with pytest.raises(MutationDeniedError) as exc_info:
            mutation_engine.apply(
                filename="/etc/passwd",
                new_code="test",
                caller_identity="TestCaller",
                task_id="TASK-001"
            )
        
        assert exc_info.value.reason == "PATH_TRAVERSAL_BLOCKED"
        assert "absolute_path_rejected" in str(exc_info.value.context.get("reason", ""))
    
    def test_blocks_absolute_path_windows(self, mutation_engine, tmp_path):
        """Verify absolute paths are blocked (Windows)"""
        if sys.platform != "win32":
            pytest.skip("Windows-specific test")
        
        # Try to mutate Windows system file
        windows_path = r"C:\Windows\system32\drivers\etc\hosts"
        with pytest.raises(MutationDeniedError) as exc_info:
            mutation_engine.apply(
                filename=windows_path,
                new_code="test",
                caller_identity="TestCaller",
                task_id="TASK-001"
            )
        
        assert exc_info.value.reason == "PATH_TRAVERSAL_BLOCKED"
        assert "absolute_path_rejected" in str(exc_info.value.context.get("reason", ""))
    
    def test_blocks_traversal_simple(self, mutation_engine, tmp_path):
        """Verify simple traversal (../outside.txt) is blocked"""
        with pytest.raises(MutationDeniedError) as exc_info:
            mutation_engine.apply(
                filename="../outside.txt",
                new_code="test",
                caller_identity="TestCaller",
                task_id="TASK-001"
            )
        
        assert exc_info.value.reason == "PATH_TRAVERSAL_BLOCKED"
        assert "traversal_detected" in str(exc_info.value.context.get("reason", ""))
    
    def test_blocks_traversal_nested(self, mutation_engine, tmp_path):
        """Verify nested traversal (a/../outside.txt) is blocked"""
        # Create a subdirectory
        subdir = tmp_path / "a"
        subdir.mkdir()
        
        with pytest.raises(MutationDeniedError) as exc_info:
            mutation_engine.apply(
                filename="a/../outside.txt",
                new_code="test",
                caller_identity="TestCaller",
                task_id="TASK-001"
            )
        
        assert exc_info.value.reason == "PATH_TRAVERSAL_BLOCKED"
        assert "traversal_detected" in str(exc_info.value.context.get("reason", ""))
    
    @pytest.mark.skipif(not hasattr(os, 'symlink'), reason="Symlinks not supported on this platform")
    def test_blocks_symlink_escape(self, mutation_engine, tmp_path, tmp_path_factory):
        """Verify paths that escape via symlink are blocked"""
        # Create a directory outside repo
        outside_dir = tmp_path_factory.mktemp("outside")
        outside_file = outside_dir / "target.txt"
        outside_file.write_text("original content")
        
        # Create symlink inside repo pointing outside
        symlink_path = tmp_path / "link_to_outside"
        try:
            os.symlink(str(outside_dir), str(symlink_path))
        except (OSError, NotImplementedError):
            pytest.skip("Symlink creation not supported")
        
        # Try to mutate through symlink
        with pytest.raises(MutationDeniedError) as exc_info:
            mutation_engine.apply(
                filename="link_to_outside/target.txt",
                new_code="malicious content",
                caller_identity="TestCaller",
                task_id="TASK-001"
            )
        
        assert exc_info.value.reason == "PATH_TRAVERSAL_BLOCKED"
        assert "path_outside_repo_root" in str(exc_info.value.context.get("reason", ""))
        
        # Verify outside file was not modified
        assert outside_file.read_text() == "original content"
    
    def test_denies_before_writing_anything(self, mutation_engine, tmp_path):
        """Verify invalid path causes denial before any writes/backups"""
        # Create a valid file
        valid_file = tmp_path / "valid.py"
        valid_file.write_text("original content")
        
        # Create backup directory (should remain empty)
        backup_dir = tmp_path / "guardian_backups"
        
        # Try to apply mutation with invalid path (absolute)
        invalid_path = "/etc/passwd" if sys.platform != "win32" else r"C:\Windows\system32\hosts"
        
        with pytest.raises(MutationDeniedError):
            mutation_engine.apply(
                filename=invalid_path,
                new_code="malicious content",
                caller_identity="TestCaller",
                task_id="TASK-001"
            )
        
        # Verify valid file was not changed
        assert valid_file.read_text() == "original content"
        
        # Verify no backups were created
        if backup_dir.exists():
            backups = list(backup_dir.rglob("*.bak.*"))
            assert len(backups) == 0
    
    def test_denies_before_writing_mixed_batch(self, mutation_engine, tmp_path):
        """Verify mixed batch (valid + invalid) denies before writing valid file"""
        # Create a valid file
        valid_file = tmp_path / "valid.py"
        valid_file.write_text("original content")
        
        # Create backup directory
        backup_dir = tmp_path / "guardian_backups"
        
        # This test simulates what Core's preflight should catch
        # We test MutationEngine.apply() directly with invalid path
        invalid_path = "../outside.txt"
        
        with pytest.raises(MutationDeniedError):
            mutation_engine.apply(
                filename=invalid_path,
                new_code="malicious content",
                caller_identity="TestCaller",
                task_id="TASK-001"
            )
        
        # Verify valid file was not changed
        assert valid_file.read_text() == "original content"
        
        # Verify no backups were created
        if backup_dir.exists():
            backups = list(backup_dir.rglob("*.bak.*"))
            assert len(backups) == 0
    
    def test_allows_safe_path(self, mutation_engine, tmp_path):
        """Verify safe relative paths are allowed"""
        # Create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text("original content")
        
        # Apply mutation
        result = mutation_engine.apply(
            filename="test.py",
            new_code="new content",
            caller_identity="TestCaller",
            task_id="TASK-001"
        )
        
        # Verify mutation succeeded
        assert result.ok == True
        assert "test.py" in result.changed_files
        assert len(result.backup_paths) == 1
        
        # Verify file was changed
        assert test_file.read_text() == "new content"
        
        # Verify backup was created
        backup_dir = tmp_path / "guardian_backups"
        assert backup_dir.exists()
        backups = list(backup_dir.rglob("*.bak.*"))
        assert len(backups) == 1
        
        # Verify backup content
        backup_file = backups[0]
        assert backup_file.read_text() == "original content"
    
    def test_blocks_writing_to_directory(self, mutation_engine, tmp_path):
        """Verify writing directly to a directory is blocked"""
        # Create a directory
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        
        with pytest.raises(MutationDeniedError) as exc_info:
            mutation_engine.apply(
                filename="test_dir",
                new_code="test",
                caller_identity="TestCaller",
                task_id="TASK-001"
            )
        
        assert exc_info.value.reason == "PATH_IS_DIRECTORY"
        assert "target_is_directory" in str(exc_info.value.context.get("reason", ""))
    
    def test_validation_occurs_before_governance_check(self, memory, review_queue, approval_store, tmp_path):
        """Verify path validation occurs before governance/protection checks"""
        trust_matrix = Mock(spec=TrustMatrix)
        trust_matrix.validate_trust_for_action = Mock()
        
        mutation_engine = MutationEngine(
            memory,
            trust_matrix=trust_matrix,
            review_queue=review_queue,
            approval_store=approval_store,
            repo_root=tmp_path
        )
        
        # Try to mutate absolute path (should fail before governance check)
        with pytest.raises(MutationDeniedError) as exc_info:
            mutation_engine.apply(
                filename="/etc/passwd" if sys.platform != "win32" else r"C:\Windows\system32\hosts",
                new_code="test",
                allow_governance_mutation=True,  # Even with override, path validation should block
                caller_identity="TestCaller",
                task_id="TASK-001"
            )
        
        # Verify TrustMatrix was not called (path validation failed first)
        trust_matrix.validate_trust_for_action.assert_not_called()
        assert exc_info.value.reason == "PATH_TRAVERSAL_BLOCKED"
    
    def test_normalized_paths_in_context(self, mutation_engine, tmp_path):
        """Verify normalized relative paths are used in context"""
        # Create a test file
        test_file = tmp_path / "subdir" / "test.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("original")
        
        # Mock TrustMatrix to capture context
        captured_context = {}
        
        def capture_context(component, action, context):
            captured_context.update(context)
            return TrustDecision(
                allowed=True,
                decision="allow",
                reason_code="ALLOWED",
                message="Test allow",
                risk_score=0.1
            )
        
        mutation_engine.trust_matrix.validate_trust_for_action = Mock(side_effect=capture_context)
        
        # Apply mutation to protected file (requires governance)
        result = mutation_engine.apply(
            filename="CONTROL.md",
            new_code="CURRENT_TASK: NONE",
            allow_governance_mutation=True,
            caller_identity="TestCaller",
            task_id="TASK-001"
        )
        
        # Verify context uses normalized relative path
        assert "touched_paths" in captured_context
        touched_paths = captured_context["touched_paths"]
        assert len(touched_paths) == 1
        # Path should be normalized (not absolute, not with ..)
        assert not Path(touched_paths[0]).is_absolute()
        assert ".." not in touched_paths[0]
        assert touched_paths[0] == "CONTROL.md"
