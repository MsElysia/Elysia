"""
Tests for Review Queue and Approval Store
"""

import pytest
import json
import tempfile
from pathlib import Path
from project_guardian.review_queue import ReviewQueue, ReviewRequest
from project_guardian.trust import NETWORK_ACCESS
from project_guardian.approval_store import ApprovalStore, ApprovalRecord
from project_guardian.external import TrustReviewRequiredError, TrustDeniedError


def test_review_queue_enqueue():
    """Test enqueueing a review request"""
    with tempfile.TemporaryDirectory() as tmpdir:
        queue_file = Path(tmpdir) / "review_queue.jsonl"
        queue = ReviewQueue(queue_file=queue_file)
        
        request_id = queue.enqueue(
            component="WebReader",
            action=NETWORK_ACCESS,
            context={"target": "example.com", "method": "GET"}
        )
        
        assert request_id is not None
        assert len(request_id) == 36  # UUID format
        
        # Verify request was written
        assert queue_file.exists()
        
        # Read back
        pending = queue.list_pending()
        assert len(pending) == 1
        assert pending[0].request_id == request_id
        assert pending[0].component == "WebReader"
        assert pending[0].action == NETWORK_ACCESS
        assert pending[0].status == "pending"


def test_approval_store_approve():
    """Test approving a request"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_file = Path(tmpdir) / "approval_store.json"
        store = ApprovalStore(store_file=store_file)
        
        context = {"target": "example.com", "method": "GET"}
        approved = store.approve(
            request_id="test-123",
            approver="human",
            notes="Approved for testing",
            context=context
        )
        
        assert approved is True
        
        # Verify approval
        assert store.is_approved("test-123", context=context) is True
        
        # Context mismatch should fail
        wrong_context = {"target": "other.com", "method": "GET"}
        assert store.is_approved("test-123", context=wrong_context) is False


def test_approval_context_mismatch():
    """Test that approval doesn't work with modified context"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_file = Path(tmpdir) / "approval_store.json"
        store = ApprovalStore(store_file=store_file)
        
        original_context = {"target": "example.com", "method": "GET", "caller": "test"}
        
        # Approve with original context
        store.approve("test-123", context=original_context)
        
        # Modified context should not be approved
        modified_context = {"target": "malicious.com", "method": "GET", "caller": "test"}
        assert store.is_approved("test-123", context=modified_context) is False
        
        # Original context should still be approved
        assert store.is_approved("test-123", context=original_context) is True


def test_review_workflow():
    """Test complete review workflow: enqueue -> approve -> replay"""
    with tempfile.TemporaryDirectory() as tmpdir:
        queue_file = Path(tmpdir) / "review_queue.jsonl"
        store_file = Path(tmpdir) / "approval_store.json"
        
        queue = ReviewQueue(queue_file=queue_file)
        store = ApprovalStore(store_file=store_file)
        
        # Step 1: Create review request
        context = {"target": "example.com", "method": "GET", "caller": "test"}
        request_id = queue.enqueue(
            component="WebReader",
            action=NETWORK_ACCESS,
            context=context
        )
        
        # Step 2: Verify pending
        pending = queue.list_pending()
        assert len(pending) == 1
        assert pending[0].request_id == request_id
        
        # Step 3: Approve
        approved = store.approve(request_id, context=context)
        assert approved is True
        
        # Step 4: Verify approval works for same context
        assert store.is_approved(request_id, context=context) is True
        
        # Step 5: Verify approval doesn't work for different context
        different_context = {"target": "other.com", "method": "GET", "caller": "test"}
        assert store.is_approved(request_id, context=different_context) is False
