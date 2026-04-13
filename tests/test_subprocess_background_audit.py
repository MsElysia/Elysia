"""
SubprocessRunner Background Audit Tests
======================================
Tests for append-only audit log for background subprocess launches.
"""

import pytest
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

try:
    from project_guardian.subprocess_runner import SubprocessRunner
    from project_guardian.external import TrustDeniedError, TrustReviewRequiredError
    from project_guardian.trust import TrustMatrix, TrustDecision, SUBPROCESS_EXECUTION
    from project_guardian.review_queue import ReviewQueue
    from project_guardian.approval_store import ApprovalStore
    from project_guardian.memory import MemoryCore
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    pytestmark = pytest.mark.skip("Required modules not available")


class TestSubprocessBackgroundAudit:
    """Test SubprocessRunner background audit logging"""
    
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
    def tmp_reports_dir(self, tmp_path):
        """Create temporary REPORTS directory"""
        reports_dir = tmp_path / "REPORTS"
        reports_dir.mkdir()
        return reports_dir
    
    @pytest.fixture
    def subprocess_runner(self, memory, trust_matrix, review_queue, approval_store, tmp_reports_dir):
        """Create SubprocessRunner instance with temporary reports directory"""
        return SubprocessRunner(
            memory,
            trust_matrix,
            review_queue,
            approval_store,
            reports_dir=str(tmp_reports_dir)
        )
    
    def test_background_launch_writes_audit_line(self, subprocess_runner, tmp_reports_dir):
        """Verify background launch writes audit line"""
        # Mock subprocess.Popen
        mock_process = MagicMock()
        mock_process.pid = 1234
        mock_process.poll = Mock(return_value=None)  # Still running
        
        with patch('subprocess.Popen', return_value=mock_process):
            result = subprocess_runner.run_command_background(
                command=["echo", "test"],
                caller_identity="TestCaller",
                task_id="TASK-001",
                request_id=None
            )
        
        # Verify process started
        assert result["pid"] == 1234
        assert result["started"] == True
        
        # Verify audit log file exists
        audit_path = tmp_reports_dir / "subprocess_background.jsonl"
        assert audit_path.exists()
        
        # Read and parse last line
        with open(audit_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) > 0
            last_line = lines[-1].strip()
        
        # Parse JSON
        audit_record = json.loads(last_line)
        
        # Verify required fields
        assert "ts" in audit_record
        assert audit_record["pid"] == 1234
        assert audit_record["command"] == ["echo", "test"]
        assert audit_record["caller_identity"] == "TestCaller"
        assert audit_record["task_id"] == "TASK-001"
        assert audit_record["request_id"] is None
        assert audit_record["action"] == SUBPROCESS_EXECUTION
        assert audit_record["decision"] == "allow"
        assert audit_record["notes"] == "background"
        assert audit_record["timeout_s"] is None
    
    def test_review_does_not_write_audit(self, subprocess_runner, tmp_reports_dir):
        """Verify review decision does not write audit line"""
        # Mock TrustMatrix to return review
        subprocess_runner.trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="review",
            reason_code="REVIEW_REQUIRED",
            message="Test review",
            risk_score=0.6
        ))
        
        audit_path = tmp_reports_dir / "subprocess_background.jsonl"
        
        with pytest.raises(TrustReviewRequiredError):
            subprocess_runner.run_command_background(
                command=["echo", "test"],
                caller_identity="TestCaller",
                task_id="TASK-001"
            )
        
        # Verify audit log file does not exist or is empty
        if audit_path.exists():
            with open(audit_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                assert content == ""  # Empty file
        else:
            assert True  # File not created (also acceptable)
    
    def test_deny_does_not_write_audit(self, subprocess_runner, tmp_reports_dir):
        """Verify deny decision does not write audit line"""
        # Mock TrustMatrix to return deny
        subprocess_runner.trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="deny",
            reason_code="DENIED",
            message="Test deny",
            risk_score=0.9
        ))
        
        audit_path = tmp_reports_dir / "subprocess_background.jsonl"
        
        with pytest.raises(TrustDeniedError):
            subprocess_runner.run_command_background(
                command=["echo", "test"],
                caller_identity="TestCaller",
                task_id="TASK-001"
            )
        
        # Verify audit log file does not exist or is empty
        if audit_path.exists():
            with open(audit_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                assert content == ""  # Empty file
        else:
            assert True  # File not created (also acceptable)
    
    def test_redaction_applies_to_command_args(self, subprocess_runner, tmp_reports_dir):
        """Verify sensitive command arguments are redacted"""
        # Mock subprocess.Popen
        mock_process = MagicMock()
        mock_process.pid = 5678
        mock_process.poll = Mock(return_value=None)
        
        with patch('subprocess.Popen', return_value=mock_process):
            subprocess_runner.run_command_background(
                command=["curl", "-H", "Authorization: Bearer token=abc123", "https://api.example.com"],
                caller_identity="TestCaller",
                task_id="TASK-001"
            )
        
        # Read audit log
        audit_path = tmp_reports_dir / "subprocess_background.jsonl"
        with open(audit_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            last_line = lines[-1].strip()
        
        audit_record = json.loads(last_line)
        
        # Verify sensitive arg is redacted
        command = audit_record["command"]
        assert "***REDACTED***" in command
        # Original sensitive arg should not appear
        assert "token=abc123" not in str(command)
    
    def test_replay_approved_writes_audit_with_request_id(self, subprocess_runner, tmp_reports_dir, approval_store):
        """Verify replay-approved background launch writes audit with request_id"""
        request_id = "test-request-123"
        context = {
            "component": "SubprocessRunner",
            "action": SUBPROCESS_EXECUTION,
            "target": "echo",
            "args": 1,
            "background": True,
            "caller_identity": "TestCaller",
            "task_id": "TASK-001"
        }
        
        # Pre-approve the request
        approval_store.approve(request_id, context, approver="test", notes="Test approval")
        
        # Mock subprocess.Popen
        mock_process = MagicMock()
        mock_process.pid = 9999
        mock_process.poll = Mock(return_value=None)
        
        with patch('subprocess.Popen', return_value=mock_process):
            result = subprocess_runner.run_command_background(
                command=["echo", "test"],
                caller_identity="TestCaller",
                task_id="TASK-001",
                request_id=request_id
            )
        
        # Verify audit log
        audit_path = tmp_reports_dir / "subprocess_background.jsonl"
        with open(audit_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            last_line = lines[-1].strip()
        
        audit_record = json.loads(last_line)
        
        # Verify request_id is included
        assert audit_record["request_id"] == request_id
        assert audit_record["decision"] == "allow"
        assert audit_record["pid"] == 9999
    
    def test_audit_log_append_only(self, subprocess_runner, tmp_reports_dir):
        """Verify multiple launches append to log (not overwrite)"""
        # Mock subprocess.Popen
        mock_process1 = MagicMock()
        mock_process1.pid = 1111
        mock_process1.poll = Mock(return_value=None)
        
        mock_process2 = MagicMock()
        mock_process2.pid = 2222
        mock_process2.poll = Mock(return_value=None)
        
        with patch('subprocess.Popen', side_effect=[mock_process1, mock_process2]):
            subprocess_runner.run_command_background(
                command=["echo", "first"],
                caller_identity="TestCaller",
                task_id="TASK-001"
            )
            
            subprocess_runner.run_command_background(
                command=["echo", "second"],
                caller_identity="TestCaller",
                task_id="TASK-002"
            )
        
        # Verify audit log has 2 lines
        audit_path = tmp_reports_dir / "subprocess_background.jsonl"
        with open(audit_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        assert len(lines) == 2
        
        # Verify both records
        record1 = json.loads(lines[0].strip())
        record2 = json.loads(lines[1].strip())
        
        assert record1["pid"] == 1111
        assert record2["pid"] == 2222
        assert record1["command"] == ["echo", "first"]
        assert record2["command"] == ["echo", "second"]
    
    def test_audit_write_failure_does_not_crash(self, subprocess_runner, tmp_reports_dir):
        """Verify audit write failure does not crash subprocess call"""
        # Mock subprocess.Popen
        mock_process = MagicMock()
        mock_process.pid = 3333
        mock_process.poll = Mock(return_value=None)
        
        # Mock file write to raise exception
        with patch('subprocess.Popen', return_value=mock_process):
            with patch('builtins.open', side_effect=IOError("Disk full")):
                # Should not raise exception
                result = subprocess_runner.run_command_background(
                    command=["echo", "test"],
                    caller_identity="TestCaller",
                    task_id="TASK-001"
                )
        
        # Process should still start successfully
        assert result["pid"] == 3333
        assert result["started"] == True
    
    def test_audit_includes_cwd(self, subprocess_runner, tmp_reports_dir):
        """Verify audit record includes current working directory"""
        # Mock subprocess.Popen
        mock_process = MagicMock()
        mock_process.pid = 4444
        mock_process.poll = Mock(return_value=None)
        
        with patch('subprocess.Popen', return_value=mock_process):
            with patch('os.getcwd', return_value="/test/directory"):
                subprocess_runner.run_command_background(
                    command=["echo", "test"],
                    caller_identity="TestCaller",
                    task_id="TASK-001"
                )
        
        # Verify audit log
        audit_path = tmp_reports_dir / "subprocess_background.jsonl"
        with open(audit_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            last_line = lines[-1].strip()
        
        audit_record = json.loads(last_line)
        assert audit_record["cwd"] == "/test/directory"
    
    def test_redaction_keywords(self, subprocess_runner, tmp_reports_dir):
        """Verify various sensitive keywords trigger redaction"""
        # Mock subprocess.Popen
        mock_process = MagicMock()
        mock_process.pid = 5555
        mock_process.poll = Mock(return_value=None)
        
        test_cases = [
            (["cmd", "--token=secret123"], ["cmd", "***REDACTED***"]),
            (["cmd", "--api_key=abc"], ["cmd", "***REDACTED***"]),
            (["cmd", "--password=xyz"], ["cmd", "***REDACTED***"]),
            (["cmd", "--secret=value"], ["cmd", "***REDACTED***"]),
            (["cmd", "--auth=token"], ["cmd", "***REDACTED***"]),
            (["cmd", "normal_arg"], ["cmd", "normal_arg"]),  # Should not be redacted
        ]
        
        for command, expected_redacted in test_cases:
            with patch('subprocess.Popen', return_value=mock_process):
                subprocess_runner.run_command_background(
                    command=command,
                    caller_identity="TestCaller",
                    task_id="TASK-001"
                )
            
            # Read last audit record
            audit_path = tmp_reports_dir / "subprocess_background.jsonl"
            with open(audit_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                last_line = lines[-1].strip()
            
            audit_record = json.loads(last_line)
            assert audit_record["command"] == expected_redacted
