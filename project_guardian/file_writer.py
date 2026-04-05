# project_guardian/file_writer.py
# File Writer Gateway for Project Guardian
# All filesystem write operations must go through this gateway

import os
from typing import Optional, Dict, Any
from pathlib import Path
from .memory import MemoryCore
from .trust import TrustMatrix, TrustDecision, FILE_WRITE
from .external import TrustDeniedError, TrustReviewRequiredError
from .review_queue import ReviewQueue
from .approval_store import ApprovalStore


class FileWriter:
    """
    Gateway for filesystem write operations.
    All file writes must be gated through TrustMatrix.
    """
    
    def __init__(
        self,
        memory: MemoryCore,
        trust_matrix: Optional[TrustMatrix] = None,
        review_queue: Optional[ReviewQueue] = None,
        approval_store: Optional[ApprovalStore] = None,
        repo_root: Optional[Path] = None
    ):
        self.memory = memory
        self.trust_matrix = trust_matrix
        self.review_queue = review_queue
        self.approval_store = approval_store
        
        # Determine repo root
        if repo_root is None:
            # Compute from file location: go up from project_guardian/file_writer.py to project root
            # Path(__file__) = project_guardian/file_writer.py
            # .parent = project_guardian/
            # .parent = project root
            self.repo_root = Path(__file__).resolve().parent.parent
        else:
            self.repo_root = Path(repo_root).resolve()
    
    def _validate_path_safety(self, file_path: str) -> Path:
        """
        Validate that file_path is safe (no traversal, within repo root).
        
        Args:
            file_path: Path to validate (str or Path-like)
            
        Returns:
            Resolved Path object within repo root
            
        Raises:
            TrustDeniedError: If path is unsafe (absolute, traversal, outside repo root)
        """
        path = Path(file_path)
        
        # Reject absolute paths
        if path.is_absolute():
            raise TrustDeniedError(
                component="FileWriter",
                action=FILE_WRITE,
                target=file_path,
                reason="PATH_TRAVERSAL_BLOCKED",
                context={
                    "original_path": str(file_path),
                    "resolved_path": str(path),
                    "repo_root": str(self.repo_root),
                    "reason": "absolute_path_rejected"
                }
            )
        
        # Reject paths containing '..' (traversal)
        path_parts = path.parts
        if ".." in path_parts:
            raise TrustDeniedError(
                component="FileWriter",
                action=FILE_WRITE,
                target=file_path,
                reason="PATH_TRAVERSAL_BLOCKED",
                context={
                    "original_path": str(file_path),
                    "resolved_path": str(path),
                    "repo_root": str(self.repo_root),
                    "reason": "traversal_detected"
                }
            )
        
        # Resolve candidate path relative to repo root
        candidate = (self.repo_root / path).resolve()
        
        # Check if resolved path is within repo root
        # candidate must be equal to repo_root or have repo_root as a parent
        try:
            candidate.relative_to(self.repo_root)
        except ValueError:
            # Path is not relative to repo_root (escapes)
            raise TrustDeniedError(
                component="FileWriter",
                action=FILE_WRITE,
                target=file_path,
                reason="PATH_TRAVERSAL_BLOCKED",
                context={
                    "original_path": str(file_path),
                    "resolved_path": str(candidate),
                    "repo_root": str(self.repo_root),
                    "reason": "path_outside_repo_root"
                }
            )
        
        # Reject writing directly to directories (path ends with separator or is a directory)
        if candidate.exists() and candidate.is_dir():
            raise TrustDeniedError(
                component="FileWriter",
                action=FILE_WRITE,
                target=file_path,
                reason="PATH_TRAVERSAL_BLOCKED",
                context={
                    "original_path": str(file_path),
                    "resolved_path": str(candidate),
                    "repo_root": str(self.repo_root),
                    "reason": "target_is_directory"
                }
            )
        
        return candidate
    
    def write_file(
        self,
        file_path: str,
        content: str,
        mode: str = "w",
        caller_identity: Optional[str] = None,
        task_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> str:
        """
        Write content to a file with TrustMatrix gating.
        
        Args:
            file_path: Path to file (must be relative, within repo root)
            content: Content to write
            mode: Write mode ("w", "a", "wb", "ab")
            caller_identity: Identity of caller (for audit)
            task_id: Task ID if available (for audit)
            request_id: Optional request ID for approval replay
            
        Returns:
            Success message
            
        Raises:
            TrustDeniedError: If path is unsafe or TrustMatrix denies the write
            TrustReviewRequiredError: If TrustMatrix requires review
        """
        # STEP 1: Validate path safety (before TrustMatrix gating)
        resolved_path = self._validate_path_safety(file_path)
        
        # Compute relative path from repo root for context (safe, no traversal)
        try:
            relative_path = resolved_path.relative_to(self.repo_root)
        except ValueError:
            # Should not happen after validation, but defensive
            relative_path = Path(file_path)
        
        if self.trust_matrix is None:
            raise TrustDeniedError(
                component="FileWriter",
                action=FILE_WRITE,
                target=str(relative_path),
                reason="TrustMatrix not available",
                context={"caller": caller_identity or "unknown", "task_id": task_id or "unknown"}
            )
        
        # STEP 2: Build context for trust gate (after path validation)
        # Use relative path (not absolute) for context
        gate_context = {
            "component": "FileWriter",
            "action": FILE_WRITE,
            "target": str(relative_path),  # Relative path from repo root
            "mode": mode,
            "bytes": len(content.encode('utf-8')) if isinstance(content, str) else len(content),
            "allow_overwrite": resolved_path.exists(),  # True if file exists
            "caller_identity": caller_identity or "unknown",
            "task_id": task_id or "unknown"
        }
        
        # Check for replay: if request_id provided and approved, bypass review
        approved_replay = False
        if request_id and self.approval_store:
            if self.approval_store.is_approved(request_id, context=gate_context):
                # Approved request with matching context - proceed (skip gate check)
                self.memory.remember(
                    f"[FileWriter] Using approved request {request_id} for {file_path}",
                    category="governance",
                    priority=0.7
                )
                approved_replay = True
                # Proceed directly to file write (skip gate check below)
            else:
                # Request ID provided but not approved or context mismatch
                raise TrustDeniedError(
                    component="FileWriter",
                    action=FILE_WRITE,
                    target=file_path,
                    reason="APPROVAL_NOT_FOUND_OR_CONTEXT_MISMATCH",
                    context=gate_context
                )
        
        # Normal gate check (only if no approved request_id)
        if not approved_replay:
            decision = self.trust_matrix.validate_trust_for_action("FileWriter", FILE_WRITE, context=gate_context)
            
            if decision.decision == "deny":
                raise TrustDeniedError(
                    component="FileWriter",
                    action=FILE_WRITE,
                    target=file_path,
                    reason=decision.reason_code,
                    context={**gate_context, "risk_score": decision.risk_score}
                )
            elif decision.decision == "review":
                # Enqueue review request
                if self.review_queue:
                    review_request_id = self.review_queue.enqueue(
                        component="FileWriter",
                        action=FILE_WRITE,
                        context=gate_context
                    )
                    
                    summary = f"File write to {file_path} requires review (risk: {decision.risk_score:.2f})"
                    error_msg = f"[FileWriter] Review request created: {review_request_id} - {summary}"
                    self.memory.remember(error_msg, category="governance", priority=0.8)
                    
                    raise TrustReviewRequiredError(
                        request_id=review_request_id,
                        component="FileWriter",
                        action=FILE_WRITE,
                        target=file_path,
                        summary=summary,
                        context={**gate_context, "risk_score": decision.risk_score}
                    )
                else:
                    # No review queue - treat as deny
                    raise TrustDeniedError(
                        component="FileWriter",
                        action=FILE_WRITE,
                        target=file_path,
                        reason=decision.reason_code,
                        context={**gate_context, "risk_score": decision.risk_score}
                    )
        
        # STEP 3: Trust approved - proceed with atomic write
        try:
            # Ensure parent directory exists
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Atomic write: write to temp file then replace
            temp_path = resolved_path.with_suffix(resolved_path.suffix + '.tmp')
            
            try:
                if mode in ("w", "a"):
                    if mode == "w":
                        temp_path.write_text(content, encoding='utf-8')
                    else:  # append mode
                        if resolved_path.exists():
                            existing = resolved_path.read_text(encoding='utf-8')
                            temp_path.write_text(existing + content, encoding='utf-8')
                        else:
                            temp_path.write_text(content, encoding='utf-8')
                elif mode in ("wb", "ab"):
                    content_bytes = content.encode('utf-8') if isinstance(content, str) else content
                    if mode == "wb":
                        temp_path.write_bytes(content_bytes)
                    else:  # append mode
                        if resolved_path.exists():
                            existing = resolved_path.read_bytes()
                            temp_path.write_bytes(existing + content_bytes)
                        else:
                            temp_path.write_bytes(content_bytes)
                else:
                    raise ValueError(f"Invalid mode: {mode}")
                
                # Atomic replace
                os.replace(temp_path, resolved_path)
                
            except Exception as e:
                # Clean up temp file on error
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
                raise
            
            self.memory.remember(
                f"[FileWriter] Wrote {str(relative_path)} ({mode})",
                category="file_operation",
                priority=0.6
            )
            
            return f"[FileWriter] Successfully wrote {str(relative_path)}"
            
        except Exception as e:
            error_msg = f"[FileWriter] Error writing {str(relative_path)}: {str(e)}"
            self.memory.remember(error_msg, category="error", priority=0.7)
            raise
