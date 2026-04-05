# project_guardian/mutation.py
# Safe Code Mutation Engine for Project Guardian

import os
import re
import json
import datetime
import logging
import openai
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)
from dataclasses import dataclass
from .memory import MemoryCore
from .trust import TrustMatrix, TrustDecision, GOVERNANCE_MUTATION
from .review_queue import ReviewQueue
from .approval_store import ApprovalStore


# Exception types for mutation outcomes
class MutationDeniedError(Exception):
    """Exception raised when mutation is denied (protected path without override or trust denied)."""
    def __init__(self, filename: str, reason: str, context: Optional[Dict[str, Any]] = None):
        self.filename = filename
        self.reason = reason
        self.context = context or {}
        message = f"Mutation denied: {filename}. Reason: {reason}"
        super().__init__(message)


class MutationReviewRequiredError(Exception):
    """Exception raised when mutation requires review before proceeding."""
    def __init__(self, request_id: str, filename: str, summary: str, context: Optional[Dict[str, Any]] = None):
        self.request_id = request_id
        self.filename = filename
        self.summary = summary
        self.context = context or {}
        message = f"Mutation requires review: {filename}. Request ID: {request_id}. {summary}"
        super().__init__(message)


class MutationApplyError(Exception):
    """Exception raised when mutation application fails unexpectedly."""
    def __init__(self, filename: str, error: str, context: Optional[Dict[str, Any]] = None):
        self.filename = filename
        self.error = error
        self.context = context or {}
        message = f"Mutation apply failed: {filename}. Error: {error}"
        super().__init__(message)


@dataclass
class MutationResult:
    """Structured result from mutation application."""
    ok: bool
    changed_files: List[str]
    backup_paths: List[str]
    summary: str


def load_mutation_autonomy_config() -> Dict[str, Any]:
    """Load config/mutation_autonomy.json (OpenAI path when Mistral selects consider_mutation)."""
    path = Path(__file__).resolve().parent.parent / "config" / "mutation_autonomy.json"
    default: Dict[str, Any] = {
        "enabled": False,
        "openai_model": "gpt-4o-mini",
        "target_files": [],
        "max_input_chars": 60000,
        "max_output_tokens": 4096,
        "instruction_template": (
            "Minimal safe improvement only. Output the COMPLETE file. "
            "No subprocess, os.system, eval, exec, or network calls."
        ),
    }
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            out = {**default, **data}
            if not isinstance(out.get("target_files"), list):
                out["target_files"] = list(default["target_files"])
            return out
    except Exception as e:
        logger.debug("mutation_autonomy.json: %s", e)
    return default


# Protected governance paths - cannot be mutated without explicit override
PROTECTED_GOVERNANCE_PATHS = [
    "CONTROL.md",
    "SPEC.md",
    "CHANGELOG.md",
    "project_guardian/core.py",
    "project_guardian/trust.py",
    "project_guardian/mutation.py",
    "project_guardian/safety.py",
    "project_guardian/consensus.py",
]

# Protected directories - any file in these directories is protected
PROTECTED_DIRECTORIES = [
    "TASKS/",
    "REPORTS/",
    "scripts/",
    "tests/",
]

class MutationEngine:
    """
    Safe code mutation engine with backup creation and governance gating.
    Enables Project Guardian to safely evolve its own code.
    """
    
    def __init__(
        self, 
        memory: MemoryCore, 
        api_key: Optional[str] = None, 
        trust_matrix: Optional[TrustMatrix] = None,
        review_queue: Optional[ReviewQueue] = None,
        approval_store: Optional[ApprovalStore] = None,
        repo_root: Optional[Path] = None
    ):
        self.memory = memory
        self.trust_matrix = trust_matrix  # TrustMatrix instance for override authorization
        self.review_queue = review_queue  # ReviewQueue for review requests
        self.approval_store = approval_store  # ApprovalStore for replay approvals
        self.mutation_log: List[Dict[str, Any]] = []
        self.last_origin: Optional[str] = None
        
        # Determine repo root
        if repo_root is None:
            # Compute from file location: go up from project_guardian/mutation.py to project root
            # Path(__file__) = project_guardian/mutation.py
            # .parent = project_guardian/
            # .parent = project root
            self.repo_root = Path(__file__).resolve().parent.parent
        else:
            self.repo_root = Path(repo_root).resolve()
        
        # Initialize OpenAI if API key provided (deprecated - review_with_gpt is disabled)
        if api_key:
            openai.api_key = api_key
        elif os.getenv("OPENAI_API_KEY"):
            openai.api_key = os.getenv("OPENAI_API_KEY")
    
    def _validate_and_resolve_path(self, rel_path: str) -> tuple[Path, str]:
        """
        Validate and resolve a relative path to ensure it's safe (no traversal, within repo root).
        
        Args:
            rel_path: Relative path to validate
            
        Returns:
            Tuple of (resolved_path, normalized_rel_path_from_repo_root)
            
        Raises:
            MutationDeniedError: If path is unsafe (absolute, traversal, outside repo root, is directory)
        """
        path = Path(rel_path)
        
        # Reject absolute paths
        if path.is_absolute():
            raise MutationDeniedError(
                filename=rel_path,
                reason="PATH_TRAVERSAL_BLOCKED",
                context={
                    "path": str(rel_path),
                    "repo_root": str(self.repo_root),
                    "resolved": str(path),
                    "reason": "absolute_path_rejected"
                }
            )
        
        # Reject paths containing '..' (traversal)
        path_parts = path.parts
        if ".." in path_parts:
            raise MutationDeniedError(
                filename=rel_path,
                reason="PATH_TRAVERSAL_BLOCKED",
                context={
                    "path": str(rel_path),
                    "repo_root": str(self.repo_root),
                    "resolved": str(path),
                    "reason": "traversal_detected"
                }
            )
        
        # Resolve candidate path relative to repo root
        candidate = (self.repo_root / path).resolve()
        
        # Check if resolved path is within repo root
        try:
            normalized_rel = candidate.relative_to(self.repo_root)
        except ValueError:
            # Path is not relative to repo_root (escapes)
            raise MutationDeniedError(
                filename=rel_path,
                reason="PATH_TRAVERSAL_BLOCKED",
                context={
                    "path": str(rel_path),
                    "repo_root": str(self.repo_root),
                    "resolved": str(candidate),
                    "reason": "path_outside_repo_root"
                }
            )
        
        # Reject writing directly to directories (path exists and is a directory)
        if candidate.exists() and candidate.is_dir():
            raise MutationDeniedError(
                filename=rel_path,
                reason="PATH_IS_DIRECTORY",
                context={
                    "path": str(rel_path),
                    "repo_root": str(self.repo_root),
                    "resolved": str(candidate),
                    "reason": "target_is_directory"
                }
            )
        
        return candidate, str(normalized_rel)
    
    def _is_protected_path(self, filename: str) -> bool:
        """
        Check if a file path is protected from mutation.
        
        Args:
            filename: File path to check
            
        Returns:
            True if path is protected
        """
        # Normalize path for comparison
        normalized = filename.replace("\\", "/")
        
        # Check exact matches in protected paths
        for protected in PROTECTED_GOVERNANCE_PATHS:
            if normalized.endswith(protected) or normalized == protected:
                return True
        
        # Check if file is in protected directory
        for protected_dir in PROTECTED_DIRECTORIES:
            if normalized.startswith(protected_dir):
                return True
        
        return False
            
    def apply(
        self, 
        filename: str, 
        new_code: str, 
        origin: Optional[str] = None, 
        allow_governance_mutation: bool = False,
        request_id: Optional[str] = None,
        caller_identity: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> MutationResult:
        """
        Apply a code mutation with automatic backup.
        
        Args:
            filename: Target file to modify
            new_code: New code content
            origin: Source of the mutation
            allow_governance_mutation: If True, allows mutation of governance files (requires TrustMatrix approval)
            request_id: Optional approved request_id for replay
            caller_identity: Identity of caller (for audit)
            task_id: Task ID if available (for audit)
            
        Returns:
            MutationResult with ok, changed_files, backup_paths, summary
            
        Raises:
            MutationDeniedError: If mutation is denied (protected path without override or trust denied)
            MutationReviewRequiredError: If mutation requires review
            MutationApplyError: If mutation application fails unexpectedly
        """
        # STEP 1: Validate path safety (before any other checks or writes)
        try:
            resolved_path, normalized_rel_path = self._validate_and_resolve_path(filename)
        except MutationDeniedError:
            # Re-raise path validation errors
            raise
        
        # GOVERNANCE PROTECTION: Check if target is a protected governance file
        # Use normalized relative path for protection check
        is_protected = self._is_protected_path(normalized_rel_path)
        
        if is_protected:
            if not allow_governance_mutation:
                # Reject: governance file mutation without override
                error_msg = f"[Guardian Mutation] REJECTED: {filename} is a protected governance file. Use allow_governance_mutation=True with TrustMatrix approval to override."
                self.memory.remember(error_msg, category="governance", priority=0.9)
                raise MutationDeniedError(
                    filename=filename,
                    reason="PROTECTED_PATH_WITHOUT_OVERRIDE",
                    context={"caller": origin or "unknown", "task_id": task_id or "unknown"}
                )
            
            # Override flag present - require TrustMatrix approval
            if self.trust_matrix is None:
                error_msg = f"[Guardian Mutation] REJECTED: {filename} requires TrustMatrix approval but TrustMatrix not available."
                self.memory.remember(error_msg, category="governance", priority=0.9)
                raise MutationDeniedError(
                    filename=filename,
                    reason="TRUST_MATRIX_NOT_AVAILABLE",
                    context={"caller": origin or "unknown", "task_id": task_id or "unknown"}
                )
            
            # Build context for trust gate decision (no sensitive content)
            # Use normalized relative path (not absolute, not original)
            touched_paths = sorted([normalized_rel_path])
            gate_context = {
                "component": "MutationEngine",
                "action": GOVERNANCE_MUTATION,
                "touched_paths": touched_paths,
                "override_flag": True,
                "caller_identity": caller_identity or origin or "unknown",
                "task_id": task_id or "unknown"
            }
            
            # Check for replay: if request_id provided and approved, bypass review
            approved_replay = False
            if request_id and self.approval_store:
                if self.approval_store.is_approved(request_id, context=gate_context):
                    # Approved request with matching context - proceed (skip gate check)
                    self.memory.remember(
                        f"[MutationEngine] Using approved request {request_id} for {filename}",
                        category="governance",
                        priority=0.7
                    )
                    approved_replay = True
                    # Proceed directly to mutation (skip gate check below)
                else:
                    # Request ID provided but not approved or context mismatch
                    raise MutationDeniedError(
                        filename=filename,
                        reason="APPROVAL_NOT_FOUND_OR_CONTEXT_MISMATCH",
                        context=gate_context
                    )
            
            # Normal gate check (only if no approved request_id)
            if not approved_replay:
                component_name = "MutationEngine"
                decision = self.trust_matrix.validate_trust_for_action(component_name, GOVERNANCE_MUTATION, context=gate_context)
                
                if decision.decision == "deny":
                    # TrustMatrix denied
                    error_msg = f"[Guardian Mutation] REJECTED: {filename} mutation denied - {decision.message}"
                    self.memory.remember(error_msg, category="governance", priority=0.9)
                    raise MutationDeniedError(
                        filename=filename,
                        reason=decision.reason_code,
                        context={**gate_context, "risk_score": decision.risk_score}
                    )
                elif decision.decision == "review":
                    # Borderline trust - enqueue review request
                    if self.review_queue:
                        review_request_id = self.review_queue.enqueue(
                            component=component_name,
                            action=GOVERNANCE_MUTATION,
                            context=gate_context
                        )
                        
                        summary = f"Governance mutation to {filename} requires review (trust: {decision.risk_score:.2f})"
                        error_msg = f"[MutationEngine] Review request created: {review_request_id} - {summary}"
                        self.memory.remember(error_msg, category="governance", priority=0.8)
                        
                        raise MutationReviewRequiredError(
                            request_id=review_request_id,
                            filename=filename,
                            summary=summary,
                            context={**gate_context, "risk_score": decision.risk_score}
                        )
                    else:
                        # No review queue - treat as deny
                        raise MutationDeniedError(
                            filename=filename,
                            reason=decision.reason_code,
                            context={**gate_context, "risk_score": decision.risk_score}
                        )
                
                # TrustMatrix approved - proceed with governance mutation
                self.memory.remember(
                    f"[Guardian Mutation] APPROVED: {filename} mutation with governance override and TrustMatrix approval",
                    category="governance",
                    priority=0.9
                )
        
        # Apply mutation (protected or not)
        # Use resolved_path (absolute, validated) for file operations
        try:
            # Read existing code (use resolved_path)
            if resolved_path.exists():
                with open(resolved_path, "r", encoding="utf-8") as f:
                    old_code = f.read()
            else:
                old_code = ""
                
            # Create backup directory (within repo root)
            backup_dir = self.repo_root / "guardian_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Create backup (use normalized relative path for backup name)
            backup_name = f"guardian_backups/{normalized_rel_path}.bak.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_path = self.repo_root / backup_name
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            with open(backup_path, "w", encoding="utf-8") as backup:
                backup.write(old_code)
                
            # Ensure parent directory exists for target file
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Apply mutation (use resolved_path)
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(new_code)
                
            # Log mutation (use normalized relative path for logging)
            mutation_entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "filename": normalized_rel_path,
                "origin": origin,
                "backup": backup_name,
                "diff": self._compute_diff(old_code, new_code)
            }
            self.mutation_log.append(mutation_entry)
            self.last_origin = origin
            
            summary = f"[Guardian Mutation] {normalized_rel_path} updated from {origin or 'unknown'}."
            self.memory.remember(summary, category="mutation", priority=0.8)
            
            # Return structured result (use normalized relative path)
            return MutationResult(
                ok=True,
                changed_files=[normalized_rel_path],
                backup_paths=[backup_name],
                summary=summary
            )
            
        except MutationDeniedError:
            # Re-raise denial errors
            raise
        except MutationReviewRequiredError:
            # Re-raise review errors
            raise
        except Exception as e:
            # Unexpected failure
            error_msg = f"[Guardian Mutation Error] {str(e)}"
            self.memory.remember(error_msg, category="error", priority=0.9)
            raise MutationApplyError(
                filename=filename,
                error=str(e),
                context={"origin": origin or "unknown", "task_id": task_id or "unknown"}
            )

    def generate_mutation_with_openai(
        self,
        rel_path: str,
        instruction: str,
        *,
        module_name: str,
        agent_name: Optional[str] = None,
        model: str = "gpt-4o-mini",
        max_output_tokens: int = 4096,
        max_input_chars: int = 60000,
    ) -> Optional[str]:
        """
        Ask OpenAI for full replacement file contents. Used when Mistral routes to consider_mutation.
        Requires OPENAI_API_KEY. Respects protected paths and path validation.
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.info("[Mutation OpenAI] OPENAI_API_KEY not set; skip generation")
            return None
        try:
            resolved_path, normalized_rel_path = self._validate_and_resolve_path(rel_path)
        except MutationDeniedError as e:
            logger.warning("[Mutation OpenAI] path denied %s: %s", rel_path, e.reason)
            return None
        if self._is_protected_path(normalized_rel_path):
            logger.warning("[Mutation OpenAI] protected path rejected: %s", normalized_rel_path)
            return None
        try:
            current = (
                resolved_path.read_text(encoding="utf-8", errors="replace")
                if resolved_path.exists()
                else ""
            )
        except Exception as e:
            logger.warning("[Mutation OpenAI] read failed %s: %s", rel_path, e)
            return None
        current = current[:max_input_chars]
        from .llm.prompted_call import log_prompted_call, prepare_prompted_bundle, require_prompt_profile

        mod, ag, _ = require_prompt_profile(
            module_name, agent_name, caller="MutationEngine.generate_mutation_with_openai", allow_legacy=False
        )

        _mut_bundle = prepare_prompted_bundle(
            module_name=mod,
            agent_name=ag,
            task_text="Apply the task to the file at the given path; output only the complete updated source.",
            extra_rules=[
                "Output ONLY the complete updated file source code; no markdown fences or commentary before/after.",
                "Do not use os.system, subprocess, eval, exec, __import__ tricks, or network I/O.",
                "Preserve existing behavior unless the task asks for a small documentation or clarity improvement.",
            ],
            caller="MutationEngine.generate_mutation_with_openai",
        )
        sys_prompt = _mut_bundle["prompt_text"]
        log_prompted_call(
            module_name=mod,
            agent_name=ag,
            task_type="mutation_openai",
            provider="openai",
            model=model,
            bundle_meta=_mut_bundle["meta"],
            prompt_length=len(sys_prompt),
            legacy_prompt_path=False,
        )
        user_prompt = (
            f"Relative path: {normalized_rel_path}\n\n--- CURRENT FILE ---\n{current}\n\n--- TASK ---\n{instruction}"
        )
        try:
            client = openai.OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_output_tokens,
                temperature=0.2,
            )
            out = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning("[Mutation OpenAI] API error: %s", e)
            return None
        if out.startswith("```"):
            out = re.sub(r"^```\w*\n?", "", out)
            out = re.sub(r"\n?```\s*$", "", out).strip()
        if len(out) < 10:
            return None
        return out

    def review_with_gpt(self, new_code: str, filename: str) -> str:
        """
        DEPRECATED/DISABLED: Review mutation with GPT-4 for safety and quality.
        
        This method is disabled because it bypasses TrustMatrix/ReviewQueue governance.
        It performs direct network calls (OpenAI API) without going through WebReader gateway.
        
        If GPT review is needed in the future, it must:
        1. Route through WebReader gateway (or a new AI gateway)
        2. Require TrustMatrix gating + review queue
        3. Follow the same allow/deny/review/replay pattern as other gateways
        
        Args:
            new_code: Proposed code changes
            filename: Target file name
            
        Returns:
            'reject' (always rejects, as method is disabled)
        """
        # DEPRECATED: This method bypasses governance. Always reject.
        self.memory.remember(
            f"[Guardian Mutation] review_with_gpt() called but is disabled (bypasses governance). Rejecting mutation to {filename}.",
            category="governance",
            priority=0.9
        )
        return "reject"
            
    def propose_mutation(
        self,
        filename: str,
        new_code: str,
        require_review: bool = False,  # Changed default to False (review_with_gpt is disabled)
        allow_governance_mutation: bool = False,
        request_id: Optional[str] = None,
        caller_identity: Optional[str] = None,
        task_id: Optional[str] = None,
        danger_profile: str = "full",
    ) -> MutationResult:
        """
        Propose a mutation with safety checks.
        
        Args:
            filename: Target file
            new_code: Proposed code
            require_review: Whether to require GPT review (DEPRECATED - review_with_gpt is disabled)
            allow_governance_mutation: If True, allows mutation of governance files
            request_id: Optional approved request_id for replay
            caller_identity: Identity of caller (for audit)
            task_id: Task ID if available (for audit)
            
        Returns:
            MutationResult with ok, changed_files, backup_paths, summary
            
        Raises:
            MutationDeniedError: If mutation is denied
            MutationReviewRequiredError: If mutation requires review
            MutationApplyError: If mutation application fails
        """
        self.memory.remember(f"[Guardian Mutation Proposed] {filename}", category="mutation", priority=0.7)
        
        # Basic safety check
        if self._contains_dangerous_patterns(new_code, profile=danger_profile):
            rejection = "[Guardian Safety] Mutation rejected - contains dangerous patterns."
            self.memory.remember(rejection, category="safety", priority=0.9)
            raise MutationDeniedError(
                filename=filename,
                reason="DANGEROUS_PATTERNS_DETECTED",
                context={"caller": caller_identity or "unknown", "task_id": task_id or "unknown"}
            )
            
        # GPT review if required (DEPRECATED - review_with_gpt is disabled)
        if require_review:
            review = self.review_with_gpt(new_code, filename)
            if review != "approve":
                rejection = f"[Guardian GPT Review] Mutation rejected: {review}"
                self.memory.remember(rejection, category="safety", priority=0.9)
                raise MutationDeniedError(
                    filename=filename,
                    reason="GPT_REVIEW_REJECTED",
                    context={"caller": caller_identity or "unknown", "task_id": task_id or "unknown"}
                )
                
        return self.apply(
            filename, 
            new_code, 
            origin="propose_mutation",
            allow_governance_mutation=allow_governance_mutation,
            request_id=request_id,
            caller_identity=caller_identity,
            task_id=task_id
        )
        
    def approve_last(self) -> str:
        """
        Approve the last proposed mutation.
        
        DEPRECATED: This method is legacy. Mutations are now approved via ReviewQueue/ApprovalStore.
        
        Returns:
            Status message
        """
        if not self.mutation_log:
            return "[Guardian Mutation] No pending mutations to approve."
            
        last_mutation = self.mutation_log[-1]
        self.memory.remember(f"[Guardian Mutation Approved] {last_mutation['filename']}", 
                           category="mutation", priority=0.8)
        return f"[Guardian Mutation] Approved: {last_mutation['filename']}"
        
    def _compute_diff(self, old_code: str, new_code: str) -> List[str]:
        """
        Compute a simple diff between old and new code.
        
        Args:
            old_code: Original code
            new_code: New code
            
        Returns:
            List of changed lines
        """
        old_lines = old_code.split('\n')
        new_lines = new_code.split('\n')
        
        diff = []
        for i, (old_line, new_line) in enumerate(zip(old_lines, new_lines)):
            if old_line != new_line:
                diff.append(f"Line {i+1}: {old_line} -> {new_line}")
                
        return diff
        
    def _contains_dangerous_patterns(self, code: str, profile: str = "full") -> bool:
        """
        Check for dangerous patterns in code.

        profile "llm_assisted" is for OpenAI-produced patches where normal Python
        (open, import os) must be allowed.
        """
        code_lower = code.lower()
        if profile == "llm_assisted":
            dangerous_patterns = [
                "os.system(",
                "subprocess.call(",
                "subprocess.run(",
                "subprocess.popen(",
                "eval(",
                "exec(",
                "ctypes.windll",
                "pickle.loads(",
                "__import__(\"ctypes\")",
                "rm -rf",
                "del /s",
                "format c:",
            ]
        else:
            dangerous_patterns = [
                "os.system(", "subprocess.call(", "subprocess.run(",
                "exec(", "eval(", "compile(",
                "open(", "file(",
                "import os", "import subprocess",
                "password", "secret", "token", "key",
                "rm -rf", "del /s", "format c:"
            ]
        for pattern in dangerous_patterns:
            if pattern in code_lower:
                return True
        return False
        
    def get_mutation_history(self) -> List[Dict[str, Any]]:
        """
        Get mutation history.
        
        Returns:
            List of mutation entries
        """
        return self.mutation_log.copy()
        
    def get_mutation_stats(self) -> Dict[str, Any]:
        """
        Get mutation statistics.
        
        Returns:
            Dictionary with mutation statistics
        """
        origins = {}
        for mutation in self.mutation_log:
            origin = mutation.get("origin", "unknown")
            origins[origin] = origins.get(origin, 0) + 1
            
        return {
            "total_mutations": len(self.mutation_log),
            "origins": origins,
            "latest_mutation": self.mutation_log[-1] if self.mutation_log else None
        } 