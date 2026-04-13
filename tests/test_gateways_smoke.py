"""
Gateways Smoke Tests
====================
Behavioral tests for WebReader, FileWriter, and SubprocessRunner gateways.
Verifies allow/deny/review/replay paths and context safety.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from project_guardian.external import WebReader, TrustDeniedError, TrustReviewRequiredError
from project_guardian.file_writer import FileWriter
from project_guardian.subprocess_runner import SubprocessRunner
from project_guardian.trust import TrustMatrix, TrustDecision, NETWORK_ACCESS, FILE_WRITE, SUBPROCESS_EXECUTION
from project_guardian.memory import MemoryCore
from project_guardian.review_queue import ReviewQueue
from project_guardian.approval_store import ApprovalStore


class TestWebReaderDenyPath:
    """Test A1: WebReader deny path - no network call attempted"""
    
    def test_deny_raises_exception_no_network_call(self):
        """Verify deny decision raises TrustDeniedError and no network call is made"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        # Mock trust to return deny decision
        deny_decision = TrustDecision(
            allowed=False,
            decision="deny",
            reason_code="INSUFFICIENT_TRUST_NETWORK_ACCESS",
            message="Insufficient trust",
            risk_score=0.9
        )
        trust.validate_trust_for_action = Mock(return_value=deny_decision)
        
        reader = WebReader(memory, trust_matrix=trust, review_queue=None, approval_store=None)
        
        # Patch requests.Session.get to ensure it's never called
        with patch.object(reader.session, 'get') as mock_get:
            with pytest.raises(TrustDeniedError) as exc_info:
                reader.fetch("https://example.com", caller_identity="test", task_id="test")
            
            # Verify exception details
            assert exc_info.value.reason == "INSUFFICIENT_TRUST_NETWORK_ACCESS"
            assert exc_info.value.action == NETWORK_ACCESS
            
            # Verify network call was NOT made
            mock_get.assert_not_called()


class TestWebReaderReviewPath:
    """Test A2: WebReader review path - enqueues request and raises TrustReviewRequiredError"""
    
    def test_review_enqueues_request_and_raises_exception(self):
        """Verify review decision enqueues request and raises TrustReviewRequiredError"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            store_file = Path(tmpdir) / "approval_store.json"
            
            review_queue = ReviewQueue(queue_file=queue_file)
            approval_store = ApprovalStore(store_file=store_file)
            
            reader = WebReader(memory, trust_matrix=trust, review_queue=review_queue, approval_store=approval_store)
            
            # Mock trust to return review decision
            review_decision = TrustDecision(
                allowed=False,
                decision="review",
                reason_code="BORDERLINE_TRUST_NETWORK_ACCESS",
                message="Borderline trust",
                risk_score=0.75
            )
            trust.validate_trust_for_action = Mock(return_value=review_decision)
            
            # Patch network call to ensure it's never made
            with patch.object(reader.session, 'get') as mock_get:
                with pytest.raises(TrustReviewRequiredError) as exc_info:
                    reader.fetch("https://example.com", caller_identity="test", task_id="test")
                
                # Verify exception has request_id
                assert exc_info.value.request_id is not None
                assert len(exc_info.value.request_id) > 0
                
                # Verify request was enqueued
                pending = review_queue.list_pending()
                assert len(pending) == 1, "Review request should be enqueued"
                assert pending[0].request_id == exc_info.value.request_id
                assert pending[0].component == "WebReader"
                assert pending[0].action == NETWORK_ACCESS
                
                # Verify network call was NOT made
                mock_get.assert_not_called()


class TestWebReaderApprovalReplay:
    """Test A3: WebReader approval replay - bypasses review with approved request_id"""
    
    def test_approved_replay_bypasses_review(self):
        """Verify approved request_id bypasses review and proceeds to network call"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            store_file = Path(tmpdir) / "approval_store.json"
            
            review_queue = ReviewQueue(queue_file=queue_file)
            approval_store = ApprovalStore(store_file=store_file)
            
            reader = WebReader(memory, trust_matrix=trust, review_queue=review_queue, approval_store=approval_store)
            
            # Create and approve a request
            context = {
                "component": "WebReader",
                "action": NETWORK_ACCESS,
                "target": "example.com",
                "method": "GET",
                "caller_identity": "test",
                "task_id": "test"
            }
            request_id = review_queue.enqueue("WebReader", NETWORK_ACCESS, context)
            approval_store.approve(request_id, context=context)
            
            # Mock network call (do not hit real internet)
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "<html>test content</html>"
            mock_response.content = b"<html>test content</html>"
            
            with patch.object(reader.session, 'get', return_value=mock_response):
                # Call fetch with approved request_id
                result = reader.fetch("https://example.com", caller_identity="test", task_id="test", request_id=request_id)
                
                # Verify result is returned (network call was made)
                assert result is not None
                assert "test content" in result
                
                # Verify network call was made (bypassed review)
                reader.session.get.assert_called_once_with("https://example.com", timeout=10)


class TestWebReaderContextSafety:
    """Test A4: WebReader context safety - only domain/target stored, no sensitive data"""
    
    def test_context_contains_only_domain_not_full_url(self):
        """Verify stored context contains only domain, not full URL or query string"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            store_file = Path(tmpdir) / "approval_store.json"
            
            review_queue = ReviewQueue(queue_file=queue_file)
            approval_store = ApprovalStore(store_file=store_file)
            
            reader = WebReader(memory, trust_matrix=trust, review_queue=review_queue, approval_store=approval_store)
            
            # Mock trust to return review decision
            review_decision = TrustDecision(
                allowed=False,
                decision="review",
                reason_code="BORDERLINE_TRUST_NETWORK_ACCESS",
                message="Borderline trust",
                risk_score=0.75
            )
            trust.validate_trust_for_action = Mock(return_value=review_decision)
            
            # Call with URL containing query string and sensitive data
            sensitive_url = "https://example.com/path?token=secret123&api_key=abc456"
            
            with patch.object(reader.session, 'get'):
                with pytest.raises(TrustReviewRequiredError):
                    reader.fetch(sensitive_url, caller_identity="test", task_id="test")
            
            # Verify stored context contains only domain
            pending = review_queue.list_pending()
            assert len(pending) == 1, "Review request should be enqueued"
            
            stored_context = pending[0].context
            assert stored_context["target"] == "example.com", \
                f"Context should contain only domain, got {stored_context.get('target')}"
            assert "token" not in stored_context, "Context should not contain query params"
            assert "api_key" not in stored_context, "Context should not contain sensitive data"
            assert "path" not in stored_context, "Context should not contain URL path"
            assert stored_context["method"] == "GET", "Context should contain method"


class TestFileWriterDenyPath:
    """Test B1: FileWriter deny path - no write happens"""
    
    def test_deny_raises_exception_no_write(self):
        """Verify deny decision raises TrustDeniedError and no file write occurs"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        # Mock trust to return deny decision
        deny_decision = TrustDecision(
            allowed=False,
            decision="deny",
            reason_code="INSUFFICIENT_TRUST_FILE_WRITE",
            message="Insufficient trust",
            risk_score=0.8
        )
        trust.validate_trust_for_action = Mock(return_value=deny_decision)
        
        writer = FileWriter(memory, trust_matrix=trust, review_queue=None, approval_store=None)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            
            # Verify file doesn't exist before
            assert not test_file.exists()
            
            with pytest.raises(TrustDeniedError) as exc_info:
                writer.write_file(str(test_file), "test content", caller_identity="test", task_id="test")
            
            # Verify exception details
            assert exc_info.value.reason == "INSUFFICIENT_TRUST_FILE_WRITE"
            assert exc_info.value.action == FILE_WRITE
            
            # Verify file was NOT written
            assert not test_file.exists(), "File should not be written on deny"


class TestFileWriterReviewPath:
    """Test B2: FileWriter review path - enqueues request and raises TrustReviewRequiredError"""
    
    def test_review_enqueues_request_and_raises_exception(self):
        """Verify review decision enqueues request and raises TrustReviewRequiredError"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            store_file = Path(tmpdir) / "approval_store.json"
            test_file = Path(tmpdir) / "test.txt"
            
            review_queue = ReviewQueue(queue_file=queue_file)
            approval_store = ApprovalStore(store_file=store_file)
            
            writer = FileWriter(memory, trust_matrix=trust, review_queue=review_queue, approval_store=approval_store)
            
            # Mock trust to return review decision
            review_decision = TrustDecision(
                allowed=False,
                decision="review",
                reason_code="BORDERLINE_TRUST_FILE_WRITE",
                message="Borderline trust",
                risk_score=0.6
            )
            trust.validate_trust_for_action = Mock(return_value=review_decision)
            
            with pytest.raises(TrustReviewRequiredError) as exc_info:
                writer.write_file(str(test_file), "test content", caller_identity="test", task_id="test")
            
            # Verify exception has request_id
            assert exc_info.value.request_id is not None
            
            # Verify request was enqueued
            pending = review_queue.list_pending()
            assert len(pending) == 1, "Review request should be enqueued"
            assert pending[0].request_id == exc_info.value.request_id
            assert pending[0].component == "FileWriter"
            assert pending[0].action == FILE_WRITE
            
            # Verify file was NOT written
            assert not test_file.exists(), "File should not be written on review"


class TestFileWriterApprovalReplay:
    """Test B3: FileWriter approval replay - approved request_id allows write"""
    
    def test_approved_replay_allows_write(self):
        """Verify approved request_id allows write to temp file"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            store_file = Path(tmpdir) / "approval_store.json"
            test_file = Path(tmpdir) / "test.txt"
            
            review_queue = ReviewQueue(queue_file=queue_file)
            approval_store = ApprovalStore(store_file=store_file)
            
            writer = FileWriter(memory, trust_matrix=trust, review_queue=review_queue, approval_store=approval_store)
            
            # Create and approve a request
            context = {
                "component": "FileWriter",
                "action": FILE_WRITE,
                "target": "test.txt",
                "mode": "w",
                "caller_identity": "test",
                "task_id": "test"
            }
            request_id = review_queue.enqueue("FileWriter", FILE_WRITE, context)
            approval_store.approve(request_id, context=context)
            
            # Call write_file with approved request_id
            result = writer.write_file(str(test_file), "test content", mode="w", caller_identity="test", task_id="test", request_id=request_id)
            
            # Verify file was written
            assert test_file.exists(), "File should be written on approved replay"
            assert test_file.read_text(encoding='utf-8') == "test content", "File content should match"
            
            # Verify result message
            assert "Successfully wrote" in result


class TestFileWriterModeRestrictions:
    """Test B4: FileWriter mode restrictions - only allowed modes"""
    
    def test_allowed_modes_work(self):
        """Verify allowed modes (w/a/wb/ab) work"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        # Mock trust to return allow decision
        allow_decision = TrustDecision(
            allowed=True,
            decision="allow",
            reason_code="ALLOWED_FILE_WRITE",
            message="Allowed",
            risk_score=0.3
        )
        trust.validate_trust_for_action = Mock(return_value=allow_decision)
        
        writer = FileWriter(memory, trust_matrix=trust, review_queue=None, approval_store=None)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Test "w" mode
            test_file_w = Path(tmpdir) / "test_w.txt"
            writer.write_file(str(test_file_w), "content", mode="w")
            assert test_file_w.exists()
            
            # Test "a" mode
            test_file_a = Path(tmpdir) / "test_a.txt"
            writer.write_file(str(test_file_a), "content", mode="a")
            assert test_file_a.exists()
            
            # Test "wb" mode (binary)
            test_file_wb = Path(tmpdir) / "test_wb.bin"
            writer.write_file(str(test_file_wb), "content", mode="wb")
            assert test_file_wb.exists()
            
            # Test "ab" mode (binary append)
            test_file_ab = Path(tmpdir) / "test_ab.bin"
            writer.write_file(str(test_file_ab), "content", mode="ab")
            assert test_file_ab.exists()
    
    def test_invalid_mode_raises_error(self):
        """Verify invalid mode raises ValueError"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        # Mock trust to return allow decision
        allow_decision = TrustDecision(
            allowed=True,
            decision="allow",
            reason_code="ALLOWED_FILE_WRITE",
            message="Allowed",
            risk_score=0.3
        )
        trust.validate_trust_for_action = Mock(return_value=allow_decision)
        
        writer = FileWriter(memory, trust_matrix=trust, review_queue=None, approval_store=None)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            
            # Invalid mode should raise ValueError
            with pytest.raises(ValueError) as exc_info:
                writer.write_file(str(test_file), "content", mode="x")  # Invalid mode
            
            assert "Invalid mode" in str(exc_info.value)


class TestSubprocessRunnerDenyPath:
    """Test C1: SubprocessRunner deny path - no subprocess run"""
    
    def test_deny_raises_exception_no_subprocess(self):
        """Verify deny decision raises TrustDeniedError and no subprocess is executed"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        # Mock trust to return deny decision
        deny_decision = TrustDecision(
            allowed=False,
            decision="deny",
            reason_code="INSUFFICIENT_TRUST_SUBPROCESS_EXECUTION",
            message="Insufficient trust",
            risk_score=0.95
        )
        trust.validate_trust_for_action = Mock(return_value=deny_decision)
        
        runner = SubprocessRunner(memory, trust_matrix=trust, review_queue=None, approval_store=None)
        
        # Patch subprocess.run to ensure it's never called
        with patch('subprocess.run') as mock_subprocess:
            with pytest.raises(TrustDeniedError) as exc_info:
                runner.run_command(["echo", "test"], caller_identity="test", task_id="test")
            
            # Verify exception details
            assert exc_info.value.reason == "INSUFFICIENT_TRUST_SUBPROCESS_EXECUTION"
            assert exc_info.value.action == SUBPROCESS_EXECUTION
            
            # Verify subprocess was NOT called
            mock_subprocess.assert_not_called()


class TestSubprocessRunnerReviewPath:
    """Test C2: SubprocessRunner review path - enqueues request and raises TrustReviewRequiredError"""
    
    def test_review_enqueues_request_and_raises_exception(self):
        """Verify review decision enqueues request and raises TrustReviewRequiredError"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            store_file = Path(tmpdir) / "approval_store.json"
            
            review_queue = ReviewQueue(queue_file=queue_file)
            approval_store = ApprovalStore(store_file=store_file)
            
            runner = SubprocessRunner(memory, trust_matrix=trust, review_queue=review_queue, approval_store=approval_store)
            
            # Mock trust to return review decision
            review_decision = TrustDecision(
                allowed=False,
                decision="review",
                reason_code="BORDERLINE_TRUST_SUBPROCESS_EXECUTION",
                message="Borderline trust",
                risk_score=0.85
            )
            trust.validate_trust_for_action = Mock(return_value=review_decision)
            
            # Patch subprocess.run to ensure it's never called
            with patch('subprocess.run') as mock_subprocess:
                with pytest.raises(TrustReviewRequiredError) as exc_info:
                    runner.run_command(["echo", "test"], caller_identity="test", task_id="test")
                
                # Verify exception has request_id
                assert exc_info.value.request_id is not None
                
                # Verify request was enqueued
                pending = review_queue.list_pending()
                assert len(pending) == 1, "Review request should be enqueued"
                assert pending[0].request_id == exc_info.value.request_id
                assert pending[0].component == "SubprocessRunner"
                assert pending[0].action == SUBPROCESS_EXECUTION
                
                # Verify subprocess was NOT called
                mock_subprocess.assert_not_called()


class TestSubprocessRunnerApprovalReplay:
    """Test C3: SubprocessRunner approval replay - approved request_id allows subprocess.run"""
    
    def test_approved_replay_allows_subprocess(self):
        """Verify approved request_id allows subprocess.run to be called (but patch it)"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            store_file = Path(tmpdir) / "approval_store.json"
            
            review_queue = ReviewQueue(queue_file=queue_file)
            approval_store = ApprovalStore(store_file=store_file)
            
            runner = SubprocessRunner(memory, trust_matrix=trust, review_queue=review_queue, approval_store=approval_store)
            
            # Create and approve a request
            context = {
                "component": "SubprocessRunner",
                "action": SUBPROCESS_EXECUTION,
                "target": "echo",
                "args": 1,
                "caller_identity": "test",
                "task_id": "test"
            }
            request_id = review_queue.enqueue("SubprocessRunner", SUBPROCESS_EXECUTION, context)
            approval_store.approve(request_id, context=context)
            
            # Mock subprocess.run (do not execute real commands)
            mock_result = Mock()
            mock_result.stdout = "test output"
            mock_result.stderr = ""
            mock_result.returncode = 0
            
            with patch('subprocess.run', return_value=mock_result) as mock_subprocess:
                # Call run_command with approved request_id
                result = runner.run_command(["echo", "test"], caller_identity="test", task_id="test", request_id=request_id)
                
                # Verify result
                assert result["stdout"] == "test output"
                assert result["returncode"] == 0
                assert result["success"] is True
                
                # Verify subprocess.run was called (bypassed review)
                mock_subprocess.assert_called_once()
                call_args = mock_subprocess.call_args
                assert call_args[0][0] == ["echo", "test"], "Command should match"
                assert call_args[1]["timeout"] == 30, "Timeout should be 30 seconds"


class TestSubprocessRunnerTimeout:
    """Test C4: SubprocessRunner timeout behavior - raises TrustDeniedError with SUBPROCESS_EXECUTION"""
    
    def test_timeout_raises_trust_denied_error(self):
        """Verify timeout raises TrustDeniedError with SUBPROCESS_EXECUTION constant"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        # Mock trust to return allow decision
        allow_decision = TrustDecision(
            allowed=True,
            decision="allow",
            reason_code="ALLOWED_SUBPROCESS_EXECUTION",
            message="Allowed",
            risk_score=0.2
        )
        trust.validate_trust_for_action = Mock(return_value=allow_decision)
        
        runner = SubprocessRunner(memory, trust_matrix=trust, review_queue=None, approval_store=None)
        
        # Mock subprocess.run to raise TimeoutExpired
        import subprocess
        timeout_exception = subprocess.TimeoutExpired(cmd=["sleep", "100"], timeout=30)
        
        with patch('subprocess.run', side_effect=timeout_exception):
            with pytest.raises(TrustDeniedError) as exc_info:
                runner.run_command(["sleep", "100"], caller_identity="test", task_id="test")
            
            # Verify exception uses SUBPROCESS_EXECUTION constant
            assert exc_info.value.action == SUBPROCESS_EXECUTION, \
                f"Timeout should use SUBPROCESS_EXECUTION constant, got {exc_info.value.action}"
            assert exc_info.value.reason == "COMMAND_TIMEOUT", \
                f"Timeout reason should be COMMAND_TIMEOUT, got {exc_info.value.reason}"


class TestSubprocessRunnerForbiddenPatterns:
    """Test that SubprocessRunner forbids dangerous patterns"""
    
    def test_shell_true_not_allowed(self):
        """Verify subprocess.run is called without shell=True (forbidden)"""
        memory = MemoryCore()
        trust = TrustMatrix(memory)
        
        # Mock trust to return allow decision
        allow_decision = TrustDecision(
            allowed=True,
            decision="allow",
            reason_code="ALLOWED_SUBPROCESS_EXECUTION",
            message="Allowed",
            risk_score=0.2
        )
        trust.validate_trust_for_action = Mock(return_value=allow_decision)
        
        runner = SubprocessRunner(memory, trust_matrix=trust, review_queue=None, approval_store=None)
        
        # Mock subprocess.run
        mock_result = Mock()
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_result.returncode = 0
        
        with patch('subprocess.run', return_value=mock_result) as mock_subprocess:
            runner.run_command(["echo", "test"], caller_identity="test", task_id="test")
            
            # Verify shell=True is NOT used (forbidden)
            call_kwargs = mock_subprocess.call_args[1]
            assert call_kwargs.get("shell") != True, \
                "subprocess.run should NOT use shell=True (forbidden for security)"
            
            # Verify timeout is set
            assert call_kwargs.get("timeout") == 30, "Timeout should be 30 seconds"
