# project_guardian/review_queue.py
# Review Queue for TrustMatrix "review" decisions
# Durable, append-only queue for review requests

import json
import uuid
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass, asdict

if TYPE_CHECKING:
    from .memory import MemoryCore


@dataclass
class ReviewRequest:
    """
    Review request schema for TrustMatrix "review" decisions.
    """
    request_id: str
    component: str
    action: str
    context: Dict[str, Any]
    created_at: str
    status: str  # "pending", "approved", "denied"
    
    def __post_init__(self):
        """Validate request"""
        if self.status not in ["pending", "approved", "denied"]:
            raise ValueError(f"Invalid status: {self.status}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReviewRequest':
        """Create from dictionary"""
        return cls(**data)


class ReviewQueue:
    """
    File-backed review queue (append-only JSONL).
    Stores review requests for TrustMatrix "review" decisions.
    
    Status Transition Policy:
    - Monotonic transitions only: pending → approved | denied
    - Once approved or denied, status cannot be changed
    - If reconsideration is needed, create a new request_id
    """
    
    def __init__(self, queue_file: Optional[Path] = None, memory: Optional[Any] = None):
        """
        Initialize review queue.
        
        Args:
            queue_file: Path to JSONL file (default: REPORTS/review_queue.jsonl)
        """
        if queue_file is None:
            project_root = Path(__file__).parent.parent
            queue_file = project_root / "REPORTS" / "review_queue.jsonl"
        
        self.queue_file = Path(queue_file)
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        self.memory = memory  # Optional MemoryCore for logging status reversal attempts
    
    def enqueue(self, component: str, action: str, context: Dict[str, Any]) -> str:
        """
        Enqueue a review request.
        
        Args:
            component: Component name (e.g., "WebReader")
            action: Action type (e.g., "network_access")
            context: Context dict (target, caller, task_id, etc.)
            
        Returns:
            request_id (UUID string)
        """
        request_id = str(uuid.uuid4())
        
        request = ReviewRequest(
            request_id=request_id,
            component=component,
            action=action,
            context=context,
            created_at=datetime.utcnow().isoformat(),
            status="pending"
        )
        
        # Append to JSONL file (append-only)
        with open(self.queue_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(request.to_dict()) + '\n')
        
        return request_id
    
    def list_pending(self) -> List[ReviewRequest]:
        """
        List all pending review requests.
        
        Returns:
            List of ReviewRequest objects with status="pending"
        """
        if not self.queue_file.exists():
            return []
        
        pending = []
        
        with open(self.queue_file, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    request = ReviewRequest.from_dict(data)
                    if request.status == "pending":
                        pending.append(request)
                except (json.JSONDecodeError, ValueError):
                    # Skip malformed lines
                    continue
        
        return pending
    
    def get_request(self, request_id: str) -> Optional[ReviewRequest]:
        """
        Get a specific review request by ID.
        
        Returns the LATEST matching record (last occurrence in JSONL).
        This ensures status updates (approved/denied) are reflected correctly.
        
        Args:
            request_id: Request ID to look up
            
        Returns:
            ReviewRequest or None if not found
        """
        if not self.queue_file.exists():
            return None
        
        latest_request = None
        
        # Read entire file and find latest matching request_id
        # (JSONL append-only design means latest is last occurrence)
        with open(self.queue_file, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    request = ReviewRequest.from_dict(data)
                    if request.request_id == request_id:
                        latest_request = request  # Keep overwriting to get latest
                except (json.JSONDecodeError, ValueError):
                    continue
        
        return latest_request
    
    def update_status(self, request_id: str, status: str, approver: str = "system", notes: str = "") -> bool:
        """
        Update request status (approved/denied).
        
        Note: This is a simple implementation that appends a new line with updated status.
        For production, you'd want to update in-place or use a proper database.
        
        **Status Transition Policy:**
        - Current implementation allows status reversals (approved → denied, denied → approved)
        - get_request() returns the latest status (last occurrence in JSONL)
        - For monotonic transitions (pending → approved/denied only, no reversals),
          add a check here to reject transitions from approved/denied back to pending or to each other.
        
        Args:
            request_id: Request ID to update
            status: New status ("approved" or "denied")
            approver: Who approved/denied
            notes: Optional notes
            
        Returns:
            True if updated, False if request not found
        """
        request = self.get_request(request_id)
        if not request:
            return False
        
        # Enforce monotonic transitions: pending → approved/denied only
        # Once approved or denied, status cannot be changed (prevents audit trail ambiguity)
        # If reconsideration is needed, create a new request_id instead
        if request.status in ["approved", "denied"]:
            # Already finalized - cannot change
            # Log the attempt for audit trail (if memory available)
            if self.memory:
                self.memory.remember(
                    f"[ReviewQueue] Attempted status reversal for {request_id}: {request.status} → {status} (rejected - monotonic policy)",
                    category="governance",
                    priority=0.7
                )
            return False
        
        # Update status (only if currently pending)
        request.status = status
        
        # Append updated request (append-only design)
        # get_request() returns latest occurrence, so this works correctly
        # Note: JSONL append is atomic at OS level (single write operation)
        with open(self.queue_file, 'a', encoding='utf-8') as f:
            updated_data = request.to_dict()
            updated_data['approver'] = approver
            updated_data['notes'] = notes
            updated_data['updated_at'] = datetime.utcnow().isoformat()
            f.write(json.dumps(updated_data) + '\n')
        
        return True
