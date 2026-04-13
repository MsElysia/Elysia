"""
No Side-Effects Tests: Task Engine (APPLY_MUTATION)
====================================================
Tests that deny/review decisions for APPLY_MUTATION tasks create no side-effects.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

try:
    from project_guardian.core import GuardianCore
    from project_guardian.trust import TrustMatrix, TrustDecision, GOVERNANCE_MUTATION
    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False
    pytestmark = pytest.mark.skip("Required modules not available")


class TestNoSideEffectsTaskEngine:
    """Test that APPLY_MUTATION deny/review decisions create no side-effects"""
    
    @pytest.fixture
    def tmp_project(self, tmp_path):
        """Create temporary project structure"""
        # Create directories
        (tmp_path / "TASKS").mkdir()
        (tmp_path / "MUTATIONS").mkdir()
        (tmp_path / "REPORTS").mkdir()
        (tmp_path / "project_guardian").mkdir()
        
        # Create CONTROL.md
        control_file = tmp_path / "CONTROL.md"
        control_file.write_text("CURRENT_TASK: TASK-0001\n")
        
        return tmp_path
    
    def test_task_apply_mutation_review_no_side_effects(self, tmp_project):
        """Verify APPLY_MUTATION review does not write or create backups"""
        # Create task file
        task_file = tmp_project / "TASKS" / "TASK-0001.md"
        task_file.write_text("""TASK_TYPE: APPLY_MUTATION
MUTATION_FILE: MUTATIONS/test.json
ALLOW_GOVERNANCE_MUTATION: true
""")
        
        # Create mutation payload with protected path
        payload_file = tmp_project / "MUTATIONS" / "test.json"
        payload = {
            "touched_paths": ["CONTROL.md"],
            "changes": [
                {"path": "CONTROL.md", "content": "CURRENT_TASK: NONE\n"}
            ],
            "summary": "Test mutation"
        }
        payload_file.write_text(json.dumps(payload))
        
        # Create target file
        target_file = tmp_project / "CONTROL.md"
        target_file.write_text("CURRENT_TASK: TASK-0001\n")
        original_content = target_file.read_text()
        
        # Create backup directory (should remain empty)
        backup_dir = tmp_project / "guardian_backups"
        
        # Initialize Core with minimal config
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        
        core = GuardianCore(
            config=config,
            control_path=tmp_project / "CONTROL.md",
            tasks_dir=tmp_project / "TASKS",
            mutations_dir=tmp_project / "MUTATIONS"
        )
        
        # Mock TrustMatrix to return review
        core.trust.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="review",
            reason_code="REVIEW_REQUIRED",
            message="Test review",
            risk_score=0.6
        ))
        
        # Execute run_once
        result = core.run_once()
        
        # Verify review required
        assert result.get("status") == "needs_review"
        assert "request_id" in result
        
        # Verify target file unchanged
        assert target_file.read_text() == original_content
        
        # Verify no backup files created
        if backup_dir.exists():
            backups = list(backup_dir.rglob("*.bak.*"))
            assert len(backups) == 0
        else:
            assert True  # Backup directory not created (also acceptable)
    
    def test_task_apply_mutation_denied_no_side_effects(self, tmp_project):
        """Verify APPLY_MUTATION deny does not write or create backups"""
        # Create task file
        task_file = tmp_project / "TASKS" / "TASK-0001.md"
        task_file.write_text("""TASK_TYPE: APPLY_MUTATION
MUTATION_FILE: MUTATIONS/test.json
ALLOW_GOVERNANCE_MUTATION: true
""")
        
        # Create mutation payload with invalid path (traversal)
        payload_file = tmp_project / "MUTATIONS" / "test.json"
        payload = {
            "touched_paths": ["../evil.txt"],
            "changes": [
                {"path": "../evil.txt", "content": "malicious content"}
            ],
            "summary": "Test mutation"
        }
        payload_file.write_text(json.dumps(payload))
        
        # Create a safe file
        safe_file = tmp_project / "safe.txt"
        safe_file.write_text("original")
        original_content = safe_file.read_text()
        
        # Create backup directory (should remain empty)
        backup_dir = tmp_project / "guardian_backups"
        
        # Initialize Core with minimal config
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        
        core = GuardianCore(
            config=config,
            control_path=tmp_project / "CONTROL.md",
            tasks_dir=tmp_project / "TASKS",
            mutations_dir=tmp_project / "MUTATIONS"
        )
        
        # Execute run_once (should deny due to invalid path)
        result = core.run_once()
        
        # Verify denial
        assert result.get("status") == "denied"
        assert result.get("reason_code") == "PATH_TRAVERSAL_BLOCKED"
        
        # Verify safe file unchanged
        assert safe_file.read_text() == original_content
        
        # Verify no backup files created
        if backup_dir.exists():
            backups = list(backup_dir.rglob("*.bak.*"))
            assert len(backups) == 0
        else:
            assert True  # Backup directory not created (also acceptable)
    
    def test_task_apply_mutation_trust_deny_no_side_effects(self, tmp_project):
        """Verify APPLY_MUTATION trust deny does not write or create backups"""
        # Create task file
        task_file = tmp_project / "TASKS" / "TASK-0001.md"
        task_file.write_text("""TASK_TYPE: APPLY_MUTATION
MUTATION_FILE: MUTATIONS/test.json
ALLOW_GOVERNANCE_MUTATION: true
""")
        
        # Create mutation payload with protected path
        payload_file = tmp_project / "MUTATIONS" / "test.json"
        payload = {
            "touched_paths": ["CONTROL.md"],
            "changes": [
                {"path": "CONTROL.md", "content": "CURRENT_TASK: NONE\n"}
            ],
            "summary": "Test mutation"
        }
        payload_file.write_text(json.dumps(payload))
        
        # Create target file
        target_file = tmp_project / "CONTROL.md"
        target_file.write_text("CURRENT_TASK: TASK-0001\n")
        original_content = target_file.read_text()
        
        # Create backup directory (should remain empty)
        backup_dir = tmp_project / "guardian_backups"
        
        # Initialize Core with minimal config
        config = {
            "enable_vector_memory": False,
            "enable_resource_monitoring": False,
        }
        
        core = GuardianCore(
            config=config,
            control_path=tmp_project / "CONTROL.md",
            tasks_dir=tmp_project / "TASKS",
            mutations_dir=tmp_project / "MUTATIONS"
        )
        
        # Mock TrustMatrix to return deny
        core.trust.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="deny",
            reason_code="DENIED",
            message="Test deny",
            risk_score=0.9
        ))
        
        # Execute run_once
        result = core.run_once()
        
        # Verify denial
        assert result.get("status") == "denied"
        assert result.get("reason_code") == "DENIED"
        
        # Verify target file unchanged
        assert target_file.read_text() == original_content
        
        # Verify no backup files created
        if backup_dir.exists():
            backups = list(backup_dir.rglob("*.bak.*"))
            assert len(backups) == 0
        else:
            assert True  # Backup directory not created (also acceptable)
