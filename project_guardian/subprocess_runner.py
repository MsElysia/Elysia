# project_guardian/subprocess_runner.py
# Subprocess Runner Gateway for Project Guardian
# All subprocess execution must go through this gateway

import subprocess
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from .memory import MemoryCore
from .trust import TrustMatrix, TrustDecision, SUBPROCESS_EXECUTION
from .external import TrustDeniedError, TrustReviewRequiredError
from .review_queue import ReviewQueue
from .approval_store import ApprovalStore


class SubprocessRunner:
    """
    Gateway for subprocess execution.
    All subprocess calls must be gated through TrustMatrix.
    
    By default, subprocess execution is denied unless explicitly approved.
    """
    
    def __init__(
        self,
        memory: MemoryCore,
        trust_matrix: Optional[TrustMatrix] = None,
        review_queue: Optional[ReviewQueue] = None,
        approval_store: Optional[ApprovalStore] = None,
        reports_dir: Optional[str] = None
    ):
        self.memory = memory
        self.trust_matrix = trust_matrix
        self.review_queue = review_queue
        self.approval_store = approval_store
        # Audit log path (can be overridden for testing)
        self.reports_dir = Path(reports_dir) if reports_dir else Path("REPORTS")
    
    def _get_audit_log_path(self) -> Path:
        """Get path to background subprocess audit log file."""
        return self.reports_dir / "subprocess_background.jsonl"
    
    def _redact_command_args(self, command: List[str]) -> List[str]:
        """
        Redact sensitive command arguments.
        
        Args:
            command: Command and arguments list
            
        Returns:
            Command list with sensitive args redacted
        """
        sensitive_keywords = ["token", "key", "secret", "password", "api_key", "auth"]
        redacted = []
        
        for arg in command:
            arg_lower = arg.lower()
            # Check if arg contains sensitive keyword
            if any(keyword in arg_lower for keyword in sensitive_keywords):
                redacted.append("***REDACTED***")
            else:
                redacted.append(arg)
        
        return redacted
    
    def _append_audit_log(
        self,
        pid: int,
        command: List[str],
        cwd: Optional[str],
        caller_identity: Optional[str],
        task_id: Optional[str],
        request_id: Optional[str]
    ):
        """
        Append audit log entry for background subprocess launch.
        
        Args:
            pid: Process ID
            command: Command and arguments (will be redacted)
            cwd: Current working directory (if available)
            caller_identity: Caller identity
            task_id: Task ID
            request_id: Request ID (if replay-approved)
        """
        try:
            # Ensure REPORTS directory exists
            self.reports_dir.mkdir(parents=True, exist_ok=True)
            
            audit_path = self._get_audit_log_path()
            
            # Redact sensitive command arguments
            redacted_command = self._redact_command_args(command)
            
            # Build audit record
            audit_record = {
                "ts": datetime.utcnow().isoformat() + "Z",
                "pid": pid,
                "command": redacted_command,
                "cwd": cwd,
                "timeout_s": None,  # Background processes have no timeout
                "caller_identity": caller_identity or "unknown",
                "task_id": task_id or "unknown",
                "request_id": request_id,
                "action": SUBPROCESS_EXECUTION if isinstance(SUBPROCESS_EXECUTION, str) else str(SUBPROCESS_EXECUTION),
                "decision": "allow",  # Background runs only occur when allowed or replay-approved
                "notes": "background"
            }
            
            # Append JSON line (atomic write)
            with open(audit_path, "a", encoding="utf-8") as f:
                json.dump(audit_record, f)
                f.write("\n")
                f.flush()  # Ensure written to disk
            
        except Exception as e:
            # Best-effort logging - do not crash subprocess call
            try:
                self.memory.remember(
                    f"[SubprocessRunner] Failed to write audit log: {str(e)}",
                    category="error",
                    priority=0.5
                )
            except Exception:
                pass  # Silently continue if even memory logging fails
    
    def run_command(
        self,
        command: List[str],
        caller_identity: Optional[str] = None,
        task_id: Optional[str] = None,
        request_id: Optional[str] = None,
        timeout: Optional[int] = 30
    ) -> Dict[str, Any]:
        """
        Run a subprocess command with TrustMatrix gating.
        
        Args:
            command: Command and arguments as list
            caller_identity: Identity of caller (for audit)
            task_id: Task ID if available (for audit)
            request_id: Optional request ID for approval replay
            timeout: Timeout in seconds (default: 30)
            
        Returns:
            Dict with stdout, stderr, returncode
            
        Raises:
            TrustDeniedError: If TrustMatrix denies the command
            TrustReviewRequiredError: If TrustMatrix requires review
        """
        if self.trust_matrix is None:
            raise TrustDeniedError(
                component="SubprocessRunner",
                action=SUBPROCESS_EXECUTION,
                target=" ".join(command),
                reason="TrustMatrix not available",
                context={"caller": caller_identity or "unknown", "task_id": task_id or "unknown"}
            )
        
        # Build context for trust gate
        gate_context = {
            "component": "SubprocessRunner",
            "action": SUBPROCESS_EXECUTION,
            "target": command[0] if command else "unknown",  # Just command name
            "args": len(command) - 1,  # Number of arguments (not the args themselves)
            "caller_identity": caller_identity or "unknown",
            "task_id": task_id or "unknown"
        }
        
        # Check for replay: if request_id provided and approved, bypass review
        approved_replay = False
        if request_id and self.approval_store:
            if self.approval_store.is_approved(request_id, context=gate_context):
                # Approved request with matching context - proceed (skip gate check)
                self.memory.remember(
                    f"[SubprocessRunner] Using approved request {request_id} for {' '.join(command)}",
                    category="governance",
                    priority=0.7
                )
                approved_replay = True
                # Proceed directly to subprocess execution (skip gate check below)
            else:
                # Request ID provided but not approved or context mismatch
                raise TrustDeniedError(
                    component="SubprocessRunner",
                    action=SUBPROCESS_EXECUTION,
                    target=" ".join(command),
                    reason="APPROVAL_NOT_FOUND_OR_CONTEXT_MISMATCH",
                    context=gate_context
                )
        
        # Normal gate check - subprocess requires high trust (only if no approved request_id)
        if not approved_replay:
            decision = self.trust_matrix.validate_trust_for_action("SubprocessRunner", SUBPROCESS_EXECUTION, context=gate_context)
            
            if decision.decision == "deny":
                raise TrustDeniedError(
                    component="SubprocessRunner",
                    action=SUBPROCESS_EXECUTION,
                    target=" ".join(command),
                    reason=decision.reason_code,
                    context={**gate_context, "risk_score": decision.risk_score}
                )
            elif decision.decision == "review":
                # Enqueue review request
                if self.review_queue:
                    review_request_id = self.review_queue.enqueue(
                        component="SubprocessRunner",
                        action=SUBPROCESS_EXECUTION,
                        context=gate_context
                    )
                    
                    summary = f"Subprocess execution {' '.join(command)} requires review (risk: {decision.risk_score:.2f})"
                    error_msg = f"[SubprocessRunner] Review request created: {review_request_id} - {summary}"
                    self.memory.remember(error_msg, category="governance", priority=0.8)
                    
                    raise TrustReviewRequiredError(
                        request_id=review_request_id,
                        component="SubprocessRunner",
                        action=SUBPROCESS_EXECUTION,
                        target=" ".join(command),
                        summary=summary,
                        context={**gate_context, "risk_score": decision.risk_score}
                    )
                else:
                    # No review queue - treat as deny
                    raise TrustDeniedError(
                        component="SubprocessRunner",
                        action=SUBPROCESS_EXECUTION,
                        target=" ".join(command),
                        reason=decision.reason_code,
                        context={**gate_context, "risk_score": decision.risk_score}
                    )
        
        # Trust approved - proceed with subprocess execution
        import subprocess
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout  # Use provided timeout (default: 30 seconds)
            )
            
            self.memory.remember(
                f"[SubprocessRunner] Executed: {' '.join(command)} (returncode: {result.returncode})",
                category="subprocess",
                priority=0.7
            )
            
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "success": result.returncode == 0
            }
            
        except subprocess.TimeoutExpired:
            error_msg = f"[SubprocessRunner] Command timed out: {' '.join(command)}"
            self.memory.remember(error_msg, category="error", priority=0.8)
            raise TrustDeniedError(
                component="SubprocessRunner",
                action=SUBPROCESS_EXECUTION,
                target=" ".join(command),
                reason="COMMAND_TIMEOUT",
                context=gate_context
            )
        except Exception as e:
            error_msg = f"[SubprocessRunner] Error executing command: {str(e)}"
            self.memory.remember(error_msg, category="error", priority=0.8)
            raise
    
    def run_command_background(
        self,
        command: List[str],
        caller_identity: Optional[str] = None,
        task_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run a subprocess command in background (non-blocking) with TrustMatrix gating.
        
        Args:
            command: Command and arguments as list
            caller_identity: Identity of caller (for audit)
            task_id: Task ID if available (for audit)
            request_id: Optional request ID for approval replay
        
        Returns:
            Dict with pid, started (bool), command
        
        Raises:
            TrustDeniedError: If TrustMatrix denies the command
            TrustReviewRequiredError: If TrustMatrix requires review
        """
        if self.trust_matrix is None:
            raise TrustDeniedError(
                component="SubprocessRunner",
                action=SUBPROCESS_EXECUTION,
                target=" ".join(command),
                reason="TrustMatrix not available",
                context={"caller": caller_identity or "unknown", "task_id": task_id or "unknown", "background": True}
            )
        
        # Build context for trust gate (background mode requires higher trust)
        gate_context = {
            "component": "SubprocessRunner",
            "action": SUBPROCESS_EXECUTION,
            "target": command[0] if command else "unknown",  # Just command name
            "args": len(command) - 1,  # Number of arguments
            "background": True,  # Background execution flag
            "caller_identity": caller_identity or "unknown",
            "task_id": task_id or "unknown"
        }
        
        # Check for replay: if request_id provided and approved, bypass review
        approved_replay = False
        if request_id and self.approval_store:
            if self.approval_store.is_approved(request_id, context=gate_context):
                # Approved request with matching context - proceed (skip gate check)
                self.memory.remember(
                    f"[SubprocessRunner] Using approved request {request_id} for background {' '.join(command)}",
                    category="governance",
                    priority=0.7
                )
                approved_replay = True
            else:
                # Request ID provided but not approved or context mismatch
                raise TrustDeniedError(
                    component="SubprocessRunner",
                    action=SUBPROCESS_EXECUTION,
                    target=" ".join(command),
                    reason="APPROVAL_NOT_FOUND_OR_CONTEXT_MISMATCH",
                    context=gate_context
                )
        
        # Normal gate check - background subprocess requires high trust (only if no approved request_id)
        if not approved_replay:
            component_name = "SubprocessRunner"
            
            decision = self.trust_matrix.validate_trust_for_action(component_name, SUBPROCESS_EXECUTION, context=gate_context)
            
            if decision.decision == "deny":
                # Trust gate denied - raise explicit exception
                error_msg = f"[SubprocessRunner] Trust gate DENIED for background {' '.join(command)} - {decision.message}"
                self.memory.remember(error_msg, category="governance", priority=0.9)
                
                raise TrustDeniedError(
                    component=component_name,
                    action=SUBPROCESS_EXECUTION,
                    target=" ".join(command),
                    reason=decision.reason_code,
                    context={**gate_context, "risk_score": decision.risk_score}
                )
            elif decision.decision == "review":
                # Borderline trust - enqueue review request
                if self.review_queue:
                    review_request_id = self.review_queue.enqueue(
                        component=component_name,
                        action=SUBPROCESS_EXECUTION,
                        context=gate_context
                    )
                    
                    summary = f"Background subprocess {' '.join(command)} requires review (trust: {decision.risk_score:.2f})"
                    error_msg = f"[SubprocessRunner] Review request created: {review_request_id} - {summary}"
                    self.memory.remember(error_msg, category="governance", priority=0.8)
                    
                    raise TrustReviewRequiredError(
                        request_id=review_request_id,
                        component=component_name,
                        action=SUBPROCESS_EXECUTION,
                        target=" ".join(command),
                        summary=summary,
                        context={**gate_context, "risk_score": decision.risk_score}
                    )
                else:
                    # No review queue - treat as deny
                    raise TrustDeniedError(
                        component=component_name,
                        action=SUBPROCESS_EXECUTION,
                        target=" ".join(command),
                        reason=decision.reason_code,
                        context={**gate_context, "risk_score": decision.risk_score}
                    )
        
        # Gate approved - proceed with background subprocess execution
        try:
            # Start process in background (non-blocking)
            # STRICTLY FORBIDDEN: shell=True
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,  # STRICTLY FORBIDDEN: shell=True
                text=True
            )
            
            pid = process.pid
            started = process.poll() is None  # True if still running
            
            # Get current working directory (best effort)
            try:
                cwd = os.getcwd()
            except Exception:
                cwd = None
            
            # Append audit log (best effort - do not crash on failure)
            self._append_audit_log(
                pid=pid,
                command=command,
                cwd=cwd,
                caller_identity=caller_identity,
                task_id=task_id,
                request_id=request_id
            )
            
            self.memory.remember(
                f"[SubprocessRunner] Started background process {pid}: {' '.join(command)}",
                category="external",
                priority=0.7
            )
            
            return {
                "pid": pid,
                "started": started,
                "command": " ".join(command)
            }
            
        except FileNotFoundError:
            error_msg = f"[SubprocessRunner] Command not found: {command[0]}"
            self.memory.remember(error_msg, category="error", priority=0.8)
            raise TrustDeniedError(
                component="SubprocessRunner",
                action=SUBPROCESS_EXECUTION,
                target=" ".join(command),
                reason="COMMAND_NOT_FOUND",
                context=gate_context
            )
        except Exception as e:
            error_msg = f"[SubprocessRunner Error] Background {' '.join(command)}: {str(e)}"
            self.memory.remember(error_msg, category="error", priority=0.7)
            raise
