# project_guardian/approval_store.py
# Approval Store for review request approvals
# File-backed JSON map: request_id -> approval record

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class ApprovalRecord:
    """
    Approval record for a review request.
    """
    request_id: str
    approved: bool
    timestamp: str
    approver: str
    notes: str
    context_hash: str  # Hash of context to prevent reuse
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ApprovalRecord':
        """Create from dictionary"""
        return cls(**data)


class ApprovalStore:
    """
    File-backed approval store.
    Maps request_id to approval records.
    """
    
    def __init__(self, store_file: Optional[Path] = None):
        """
        Initialize approval store.
        
        Args:
            store_file: Path to JSON file (default: REPORTS/approval_store.json)
        """
        if store_file is None:
            project_root = Path(__file__).parent.parent
            store_file = project_root / "REPORTS" / "approval_store.json"
        
        self.store_file = Path(store_file)
        self.store_file.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_store(self) -> Dict[str, Dict[str, Any]]:
        """Load approval store from file"""
        if not self.store_file.exists():
            return {}
        
        try:
            with open(self.store_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    
    def _save_store(self, store: Dict[str, Dict[str, Any]]) -> None:
        """
        Save approval store to file using atomic write.
        
        Atomic write pattern: write to .tmp file, then os.replace() to target.
        This ensures no partial files on crash.
        
        Note: Single-writer assumption - no file locking implemented.
        For multi-writer scenarios, add file locking (e.g., fcntl on Unix, msvcrt on Windows).
        """
        tmp_file = self.store_file.with_suffix('.tmp')
        
        # Write to temporary file
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(store, f, indent=2)
        
        # Atomic replace: tmp -> target (POSIX-compliant, works on Windows too)
        os.replace(tmp_file, self.store_file)
    
    def _hash_context(self, context: Dict[str, Any]) -> str:
        """Create a hash of context for matching"""
        import hashlib
        # Sort keys for consistent hashing
        context_str = json.dumps(context, sort_keys=True)
        return hashlib.sha256(context_str.encode('utf-8')).hexdigest()[:16]
    
    def approve(
        self,
        request_id: str,
        approver: str = "human",
        notes: str = "",
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Approve a review request.
        
        Args:
            request_id: Request ID to approve
            approver: Who approved (default: "human")
            notes: Optional notes
            context: Context from the request (for hash matching)
            
        Returns:
            True if approved, False if already exists
        """
        store = self._load_store()
        
        if request_id in store:
            # Already exists
            return False
        
        context_hash = self._hash_context(context or {})
        
        record = ApprovalRecord(
            request_id=request_id,
            approved=True,
            timestamp=datetime.utcnow().isoformat(),
            approver=approver,
            notes=notes,
            context_hash=context_hash
        )
        
        store[request_id] = record.to_dict()
        self._save_store(store)
        
        return True
    
    def deny(
        self,
        request_id: str,
        approver: str = "human",
        notes: str = ""
    ) -> bool:
        """
        Deny a review request.
        
        Args:
            request_id: Request ID to deny
            approver: Who denied (default: "human")
            notes: Optional notes
            
        Returns:
            True if denied, False if already exists
        """
        store = self._load_store()
        
        if request_id in store:
            return False
        
        record = ApprovalRecord(
            request_id=request_id,
            approved=False,
            timestamp=datetime.utcnow().isoformat(),
            approver=approver,
            notes=notes,
            context_hash=""  # No context hash for denials
        )
        
        store[request_id] = record.to_dict()
        self._save_store(store)
        
        return True
    
    def is_approved(self, request_id: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Check if a request is approved and context matches.
        
        Args:
            request_id: Request ID to check
            context: Context to verify matches approved context
            
        Returns:
            True if approved and context matches, False otherwise
        """
        store = self._load_store()
        
        if request_id not in store:
            return False
        
        record_data = store[request_id]
        record = ApprovalRecord.from_dict(record_data)
        
        if not record.approved:
            return False
        
        # Verify context matches (prevent token reuse)
        if context is not None:
            context_hash = self._hash_context(context)
            if context_hash != record.context_hash:
                # Context mismatch - approval doesn't apply
                return False
        
        return True
    
    def get_approval(self, request_id: str) -> Optional[ApprovalRecord]:
        """
        Get approval record for a request.
        
        Args:
            request_id: Request ID to look up
            
        Returns:
            ApprovalRecord or None if not found
        """
        store = self._load_store()
        
        if request_id not in store:
            return None
        
        return ApprovalRecord.from_dict(store[request_id])
