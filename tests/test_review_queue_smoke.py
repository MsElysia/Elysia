"""
ReviewQueue Smoke Tests
=======================
Behavioral tests for ReviewQueue durability, correctness, and append-only semantics.
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

from project_guardian.review_queue import ReviewQueue, ReviewRequest
from project_guardian.trust import NETWORK_ACCESS


class TestAppendOnlyIntegrity:
    """Test A1: Append-only integrity - JSONL grows, earlier lines unchanged"""
    
    def test_enqueue_preserves_existing_lines(self):
        """Verify enqueueing preserves existing JSONL lines"""
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            queue = ReviewQueue(queue_file=queue_file)
            
            # Enqueue first request
            request_id_1 = queue.enqueue(
                component="WebReader",
                action=NETWORK_ACCESS,
                context={"target": "example.com", "method": "GET"}
            )
            
            # Read file content after first enqueue
            with open(queue_file, 'r', encoding='utf-8') as f:
                content_after_first = f.read()
            
            # Enqueue second request
            request_id_2 = queue.enqueue(
                component="FileWriter",
                action="file_write",
                context={"target": "test.txt", "mode": "w"}
            )
            
            # Read file content after second enqueue
            with open(queue_file, 'r', encoding='utf-8') as f:
                content_after_second = f.read()
            
            # Verify first line is still present
            assert content_after_first in content_after_second, \
                "First enqueued request should still be in file"
            
            # Verify file grew (second line added)
            lines_after_first = content_after_first.strip().split('\n')
            lines_after_second = content_after_second.strip().split('\n')
            assert len(lines_after_second) == len(lines_after_first) + 1, \
                f"File should have grown by 1 line, got {len(lines_after_second)} vs {len(lines_after_first)}"
            
            # Verify first line content unchanged
            first_line_after_first = lines_after_first[0] if lines_after_first else ""
            first_line_after_second = lines_after_second[0] if lines_after_second else ""
            assert first_line_after_first == first_line_after_second, \
                "First line should be unchanged after second enqueue"
    
    def test_multiple_enqueues_grow_file(self):
        """Verify multiple enqueues grow JSONL file correctly"""
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            queue = ReviewQueue(queue_file=queue_file)
            
            # Enqueue 3 requests
            request_ids = []
            for i in range(3):
                request_id = queue.enqueue(
                    component=f"Component{i}",
                    action=NETWORK_ACCESS,
                    context={"target": f"example{i}.com", "method": "GET"}
                )
                request_ids.append(request_id)
            
            # Verify file has 3 lines
            with open(queue_file, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
            
            assert len(lines) == 3, f"File should have 3 lines, got {len(lines)}"
            
            # Verify all request IDs are in file
            file_content = '\n'.join(lines)
            for req_id in request_ids:
                assert req_id in file_content, f"Request ID {req_id} should be in file"
            
            # Verify all lines are valid JSON
            for line in lines:
                try:
                    data = json.loads(line)
                    assert 'request_id' in data, "Each line should have request_id"
                except json.JSONDecodeError as e:
                    pytest.fail(f"Invalid JSON in line: {line}. Error: {e}")


class TestLatestStateCorrectness:
    """Test A2: Latest-state correctness - get_request() returns latest status"""
    
    def test_get_request_returns_latest_status(self):
        """Verify get_request() returns latest status after updates (monotonic transitions)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            queue = ReviewQueue(queue_file=queue_file)
            
            # Enqueue request
            request_id = queue.enqueue(
                component="WebReader",
                action=NETWORK_ACCESS,
                context={"target": "example.com"}
            )
            
            # Verify initial status is pending
            req = queue.get_request(request_id)
            assert req is not None, "Request should be found"
            assert req.status == "pending", "Initial status should be pending"
            
            # Update to approved
            result = queue.update_status(request_id, "approved", approver="human", notes="Approved")
            assert result is True, "Approval should succeed"
            
            # Verify latest status is approved
            req = queue.get_request(request_id)
            assert req.status == "approved", "Latest status should be approved"
            
            # Try to update to denied (should fail - monotonic policy prevents reversal)
            result = queue.update_status(request_id, "denied", approver="human", notes="Actually denied")
            assert result is False, "Reversal should be rejected (monotonic policy)"
            
            # Verify latest status is still approved (reversal was rejected)
            req = queue.get_request(request_id)
            assert req.status == "approved", "Status should remain approved (reversal rejected)"
    
    def test_status_transitions_monotonic(self):
        """
        Test that status transitions are monotonic (pending → approved/denied only).
        
        Policy: Once approved or denied, status cannot be changed (monotonic enforcement).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            queue = ReviewQueue(queue_file=queue_file)
            
            # Enqueue request
            request_id = queue.enqueue(
                component="WebReader",
                action=NETWORK_ACCESS,
                context={"target": "example.com"}
            )
            
            # Approve
            result = queue.update_status(request_id, "approved", approver="human")
            assert result is True, "Approval should succeed"
            
            # Verify status is approved
            req = queue.get_request(request_id)
            assert req.status == "approved", "Status should be approved"
            
            # Try to deny (should fail - already approved, monotonic policy)
            result = queue.update_status(request_id, "denied", approver="human")
            assert result is False, "Reversal should be rejected (monotonic policy)"
            
            # Verify status is still approved (not changed)
            req = queue.get_request(request_id)
            assert req.status == "approved", "Status should remain approved (reversal rejected)"
            
            # Test: pending → denied → approved (should also fail)
            request_id_2 = queue.enqueue(
                component="FileWriter",
                action="file_write",
                context={"target": "test.txt"}
            )
            
            # Deny
            result = queue.update_status(request_id_2, "denied", approver="human")
            assert result is True, "Denial should succeed"
            
            # Try to approve (should fail - already denied, monotonic policy)
            result = queue.update_status(request_id_2, "approved", approver="human")
            assert result is False, "Reversal should be rejected (monotonic policy)"
            
            # Verify status is still denied
            req = queue.get_request(request_id_2)
            assert req.status == "denied", "Status should remain denied (reversal rejected)"


class TestRestartTolerance:
    """Test A3: Restart tolerance - re-instantiation preserves state"""
    
    def test_restart_preserves_pending_requests(self):
        """Verify re-instantiation preserves pending requests"""
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            
            # First instance: enqueue requests
            queue1 = ReviewQueue(queue_file=queue_file)
            request_id_1 = queue1.enqueue(
                component="WebReader",
                action=NETWORK_ACCESS,
                context={"target": "example.com"}
            )
            request_id_2 = queue1.enqueue(
                component="FileWriter",
                action="file_write",
                context={"target": "test.txt"}
            )
            
            # Approve one (should not appear in pending)
            queue1.update_status(request_id_1, "approved", approver="human")
            
            # Second instance (simulates restart)
            queue2 = ReviewQueue(queue_file=queue_file)
            
            # Verify pending list is correct
            pending = queue2.list_pending()
            pending_ids = [req.request_id for req in pending]
            
            assert request_id_2 in pending_ids, "Pending request should be in list"
            assert request_id_1 not in pending_ids, "Approved request should NOT be in pending list"
            assert len(pending) == 1, f"Should have 1 pending request, got {len(pending)}"
    
    def test_restart_preserves_all_requests(self):
        """Verify re-instantiation preserves all requests (not just pending)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            
            # First instance: enqueue and update
            queue1 = ReviewQueue(queue_file=queue_file)
            request_id = queue1.enqueue(
                component="WebReader",
                action=NETWORK_ACCESS,
                context={"target": "example.com"}
            )
            queue1.update_status(request_id, "approved", approver="human", notes="Test")
            
            # Second instance (simulates restart)
            queue2 = ReviewQueue(queue_file=queue_file)
            
            # Verify get_request still works
            req = queue2.get_request(request_id)
            assert req is not None, "Request should be retrievable after restart"
            assert req.status == "approved", "Status should be preserved"
            assert req.request_id == request_id, "Request ID should match"


class TestCorruptionHandling:
    """Test A4: Corruption handling - invalid JSON lines are skipped"""
    
    def test_invalid_json_line_is_skipped(self):
        """Verify invalid JSON lines are skipped without crashing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            
            # Write valid request
            queue = ReviewQueue(queue_file=queue_file)
            request_id = queue.enqueue(
                component="WebReader",
                action=NETWORK_ACCESS,
                context={"target": "example.com"}
            )
            
            # Append invalid JSON line manually
            with open(queue_file, 'a', encoding='utf-8') as f:
                f.write("invalid json line { not valid\n")
            
            # Append another valid request
            request_id_2 = queue.enqueue(
                component="FileWriter",
                action="file_write",
                context={"target": "test.txt"}
            )
            
            # Verify list_pending skips invalid line
            pending = queue.list_pending()
            pending_ids = [req.request_id for req in pending]
            
            assert request_id in pending_ids, "Valid request before corruption should be in list"
            assert request_id_2 in pending_ids, "Valid request after corruption should be in list"
            assert len(pending) == 2, f"Should have 2 pending requests, got {len(pending)}"
            
            # Verify get_request handles corruption
            req = queue.get_request(request_id)
            assert req is not None, "get_request should work despite corruption"
            assert req.request_id == request_id, "Should retrieve correct request"
    
    def test_empty_lines_are_skipped(self):
        """Verify empty lines in JSONL are skipped"""
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            
            queue = ReviewQueue(queue_file=queue_file)
            request_id = queue.enqueue(
                component="WebReader",
                action=NETWORK_ACCESS,
                context={"target": "example.com"}
            )
            
            # Append empty lines manually
            with open(queue_file, 'a', encoding='utf-8') as f:
                f.write("\n\n")
            
            # Verify list_pending works
            pending = queue.list_pending()
            assert len(pending) == 1, "Should have 1 pending request despite empty lines"
            assert pending[0].request_id == request_id, "Should retrieve correct request"


class TestConcurrentAppendSafety:
    """Test that append operations are safe (atomic at OS level)"""
    
    def test_concurrent_appends_dont_corrupt(self):
        """Verify multiple appends don't corrupt file (simulate concurrent writes)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "review_queue.jsonl"
            queue = ReviewQueue(queue_file=queue_file)
            
            # Enqueue multiple requests rapidly
            request_ids = []
            for i in range(10):
                request_id = queue.enqueue(
                    component=f"Component{i}",
                    action=NETWORK_ACCESS,
                    context={"target": f"example{i}.com"}
                )
                request_ids.append(request_id)
            
            # Verify all requests are readable
            with open(queue_file, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
            
            assert len(lines) == 10, f"Should have 10 lines, got {len(lines)}"
            
            # Verify all lines are valid JSON
            for line in lines:
                try:
                    data = json.loads(line)
                    assert 'request_id' in data, "Each line should have request_id"
                except json.JSONDecodeError as e:
                    pytest.fail(f"Invalid JSON in line: {line}. Error: {e}")
            
            # Verify all request IDs are retrievable
            for req_id in request_ids:
                req = queue.get_request(req_id)
                assert req is not None, f"Request {req_id} should be retrievable"
                assert req.request_id == req_id, f"Request ID should match"
