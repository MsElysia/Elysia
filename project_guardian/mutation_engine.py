# project_guardian/mutation_engine.py
# MutationEngine: Self-Modification and Code Evolution
# Based on Conversation 3 (elysia 4 sub a) and Part 3 designs

import logging
import json
import ast
import inspect
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from threading import Lock, RLock
import uuid

try:
    from .runtime_loop_core import RuntimeLoop
    from .trust_eval_action import TrustEvalAction
    from .ask_ai import AskAI, AIProvider
    from .mutation import MutationEngine as SafeMutationEngine
except ImportError:
    from runtime_loop_core import RuntimeLoop
    from trust_eval_action import TrustEvalAction
    try:
        from ask_ai import AskAI, AIProvider
    except ImportError:
        AskAI = None
        AIProvider = None
    try:
        from mutation import MutationEngine as SafeMutationEngine
    except ImportError:
        SafeMutationEngine = None

logger = logging.getLogger(__name__)


class MutationStatus(Enum):
    """Mutation status levels."""
    PROPOSED = "proposed"
    PENDING = "proposed"  # Backward-compatible alias
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"


@dataclass
class MutationProposal:
    """A mutation proposal."""
    mutation_id: str
    target_module: str
    mutation_type: str  # "optimization", "bug_fix", "feature_add", "refactor"
    description: str
    proposed_code: str
    original_code: Optional[str] = None
    status: MutationStatus = MutationStatus.PROPOSED
    confidence: float = 0.5  # 0.0-1.0
    created_at: datetime = field(default_factory=datetime.now)
    reviewed_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    reviewer: Optional[str] = None
    review_notes: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mutation_id": self.mutation_id,
            "target_module": self.target_module,
            "mutation_type": self.mutation_type,
            "description": self.description,
            "proposed_code": self.proposed_code,
            "original_code": self.original_code,
            "status": self.status.value,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "reviewer": self.reviewer,
            "review_notes": self.review_notes,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MutationProposal":
        """Create MutationProposal from dictionary."""
        return cls(
            mutation_id=data["mutation_id"],
            target_module=data["target_module"],
            mutation_type=data["mutation_type"],
            description=data["description"],
            proposed_code=data["proposed_code"],
            original_code=data.get("original_code"),
            status=MutationStatus(data.get("status", "proposed")),
            confidence=data.get("confidence", 0.5),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            reviewed_at=datetime.fromisoformat(data["reviewed_at"]) if data.get("reviewed_at") else None,
            applied_at=datetime.fromisoformat(data["applied_at"]) if data.get("applied_at") else None,
            reviewer=data.get("reviewer"),
            review_notes=data.get("review_notes"),
            metadata=data.get("metadata", {})
        )


class MutationEngine:
    """
    Self-modification and code evolution system.
    Proposes, reviews, and applies code mutations with safety checks.
    """
    
    def __init__(
        self,
        runtime_loop: Optional[RuntimeLoop] = None,
        trust_eval: Optional[TrustEvalAction] = None,
        ask_ai: Optional[AskAI] = None,
        storage_path: str = "data/mutations.json",
        live_mutation_engine: Optional[Any] = None,
        repo_root: Optional[str] = None,
    ):
        self.runtime_loop = runtime_loop
        self.trust_eval = trust_eval
        self.ask_ai = ask_ai
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.live_mutation_engine = live_mutation_engine
        self.repo_root = Path(repo_root).resolve() if repo_root else self._infer_repo_root()
        
        # Thread-safe storage (use RLock for reentrant locking)
        self._lock = RLock()
        self.proposals: Dict[str, MutationProposal] = {}
        
        # Mutation policies
        self.min_confidence_threshold: float = 0.7
        self.require_trust_approval: bool = True
        self.auto_rollback_on_error: bool = True
        
        self.load()

    def _infer_repo_root(self) -> Path:
        """Infer a reasonable repo root from storage location."""
        storage_parent = self.storage_path.resolve().parent
        if storage_parent.name.lower() == "data":
            return storage_parent.parent
        return storage_parent

    def _resolve_target_path(self, target_module: str) -> Path:
        """Resolve a proposal target path under the configured repo root."""
        candidate = Path(target_module)
        resolved = candidate.resolve() if candidate.is_absolute() else (self.repo_root / candidate).resolve()

        try:
            resolved.relative_to(self.repo_root)
        except ValueError as e:
            raise ValueError(f"Mutation target escapes repo root: {target_module}") from e

        return resolved

    def _direct_apply_mutation(self, mutation_id: str, proposal: MutationProposal) -> Dict[str, Any]:
        """Apply a mutation directly to the working tree when no safe backend is wired."""
        target_path = self._resolve_target_path(proposal.target_module)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        current_code = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
        backup_paths: List[str] = []
        if target_path.exists():
            backup_path = target_path.with_suffix(target_path.suffix + f".{mutation_id}.bak")
            backup_path.write_text(current_code, encoding="utf-8")
            backup_paths.append(str(backup_path))

        proposal.original_code = proposal.original_code if proposal.original_code is not None else current_code
        target_path.write_text(proposal.proposed_code, encoding="utf-8")

        return {
            "changed_files": [str(target_path)],
            "backup_paths": backup_paths,
            "summary": f"Applied mutation directly to {proposal.target_module}",
        }

    def _direct_rollback_mutation(self, mutation_id: str, proposal: MutationProposal) -> Dict[str, Any]:
        """Rollback a mutation directly using original code or stored backups."""
        target_path = self._resolve_target_path(proposal.target_module)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        restore_code = proposal.original_code
        if restore_code is None:
            backup_paths = proposal.metadata.get("backup_paths") or []
            for backup_path in backup_paths:
                backup = Path(str(backup_path))
                if backup.exists():
                    restore_code = backup.read_text(encoding="utf-8")
                    break

        if restore_code is None:
            raise ValueError(f"Original code not available for mutation {mutation_id}")

        target_path.write_text(restore_code, encoding="utf-8")
        return {
            "changed_files": [str(target_path)],
            "backup_paths": list(proposal.metadata.get("backup_paths") or []),
            "summary": f"Rolled back mutation for {proposal.target_module}",
        }

    def _apply_with_backend(self, mutation_id: str, proposal: MutationProposal) -> Dict[str, Any]:
        """Apply a mutation using the wired live mutation backend when available."""
        if self.live_mutation_engine is None:
            return self._direct_apply_mutation(mutation_id, proposal)

        target_path = self._resolve_target_path(proposal.target_module)
        if proposal.original_code is None and target_path.exists():
            proposal.original_code = target_path.read_text(encoding="utf-8")

        result = self.live_mutation_engine.apply(
            proposal.target_module,
            proposal.proposed_code,
            origin="legacy_mutation_engine",
            allow_governance_mutation=bool(proposal.metadata.get("allow_governance_mutation", False)),
            request_id=proposal.metadata.get("request_id"),
            caller_identity=proposal.reviewer or "legacy_mutation_engine",
            task_id=mutation_id,
        )
        return {
            "changed_files": list(result.changed_files),
            "backup_paths": list(result.backup_paths),
            "summary": result.summary,
        }

    def _rollback_with_backend(self, mutation_id: str, proposal: MutationProposal) -> Dict[str, Any]:
        """Rollback a mutation using the live mutation backend when available."""
        if self.live_mutation_engine is None:
            return self._direct_rollback_mutation(mutation_id, proposal)

        if proposal.original_code is None:
            raise ValueError(f"Original code not available for mutation {mutation_id}")

        result = self.live_mutation_engine.apply(
            proposal.target_module,
            proposal.original_code,
            origin="legacy_mutation_engine.rollback",
            allow_governance_mutation=bool(proposal.metadata.get("allow_governance_mutation", False)),
            request_id=proposal.metadata.get("request_id"),
            caller_identity="legacy_mutation_engine.rollback",
            task_id=mutation_id,
        )
        return {
            "changed_files": list(result.changed_files),
            "backup_paths": list(result.backup_paths),
            "summary": result.summary,
        }
    
    def propose_mutation(
        self,
        target_module: str,
        mutation_type: str,
        description: str,
        proposed_code: str,
        original_code: Optional[str] = None,
        confidence: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Propose a code mutation.
        
        Args:
            target_module: Module to mutate
            mutation_type: Type of mutation
            description: Description of the mutation
            proposed_code: New code to apply
            original_code: Original code (for rollback)
            confidence: Confidence score (0.0-1.0)
            metadata: Optional metadata
            
        Returns:
            Mutation ID
        """
        mutation_id = str(uuid.uuid4())
        
        proposal = MutationProposal(
            mutation_id=mutation_id,
            target_module=target_module,
            mutation_type=mutation_type,
            description=description,
            proposed_code=proposed_code,
            original_code=original_code,
            confidence=confidence,
            metadata=metadata or {}
        )
        
        with self._lock:
            self.proposals[mutation_id] = proposal
            self.save()
        
        logger.info(f"Proposed mutation {mutation_id} for {target_module}: {description}")
        return mutation_id
    
    def validate_code(self, code: str) -> Dict[str, Any]:
        """
        Validate that proposed code is syntactically correct.
        
        Args:
            code: Code to validate
            
        Returns:
            Validation result dictionary
        """
        try:
            # Try to parse the code
            ast.parse(code)
            return {
                "valid": True,
                "errors": []
            }
        except SyntaxError as e:
            return {
                "valid": False,
                "errors": [{
                    "type": "SyntaxError",
                    "message": str(e),
                    "line": e.lineno,
                    "offset": e.offset
                }]
            }
        except Exception as e:
            return {
                "valid": False,
                "errors": [{
                    "type": type(e).__name__,
                    "message": str(e)
                }]
            }
    
    def evaluate_mutation(self, mutation_id: str) -> Dict[str, Any]:
        """
        Evaluate a mutation proposal for safety and quality.
        
        Args:
            mutation_id: Mutation ID
            
        Returns:
            Evaluation result
        """
        proposal = self.proposals.get(mutation_id)
        if not proposal:
            return {
                "success": False,
                "error": "Mutation not found"
            }
        
        # Validate code
        validation = self.validate_code(proposal.proposed_code)
        if not validation["valid"]:
            return {
                "success": False,
                "errors": validation["errors"],
                "recommendation": "reject"
            }
        
        # Check confidence threshold
        if proposal.confidence < self.min_confidence_threshold:
            return {
                "success": False,
                "error": f"Confidence {proposal.confidence:.2f} below threshold {self.min_confidence_threshold}",
                "recommendation": "reject"
            }
        
        # Check trust evaluation if enabled
        if self.trust_eval and self.require_trust_approval:
            try:
                # Evaluate mutation action
                trust_result = self.trust_eval.evaluate_action(
                    action_type="code_modification",
                    target=proposal.target_module,
                    metadata={
                        "mutation_type": proposal.mutation_type,
                        "mutation_id": mutation_id
                    }
                )
                
                if not trust_result.get("approved", False):
                    return {
                        "success": False,
                        "error": "Trust evaluation failed",
                        "trust_result": trust_result,
                        "recommendation": "reject"
                    }
            except Exception as e:
                logger.warning(f"Trust evaluation error: {e}")
                # Continue without trust check if it fails
        
        # Basic heuristics
        issues = []
        
        # Check for dangerous patterns
        dangerous_patterns = [
            "import os.system",
            "eval(",
            "exec(",
            "__import__",
            "open('/etc/",
            "rm -rf"
        ]
        
        for pattern in dangerous_patterns:
            if pattern in proposal.proposed_code:
                issues.append(f"Potentially dangerous pattern: {pattern}")
        
        # Check code size (very large changes might be risky)
        if len(proposal.proposed_code) > 100000:  # 100KB
            issues.append("Very large code change - may be risky")
        
        # Enhanced AI-based code analysis if available
        if self.ask_ai and not issues:
            try:
                import asyncio
                ai_analysis = asyncio.run(self._ai_code_analysis(proposal))
                if ai_analysis:
                    issues.extend(ai_analysis.get("issues", []))
                    if ai_analysis.get("suggested_improvements"):
                        result["ai_suggestions"] = ai_analysis["suggested_improvements"]
            except Exception as e:
                logger.debug(f"AI code analysis failed: {e}")
        
        recommendation = "approve" if not issues else "review"
        
        return {
            "success": True,
            "valid": True,
            "confidence": proposal.confidence,
            "issues": issues,
            "recommendation": recommendation,
            "safe": len(issues) == 0
        }
    
    def review_mutation(
        self,
        mutation_id: str,
        approved: bool,
        reviewer: str = "system",
        notes: Optional[str] = None
    ) -> bool:
        """
        Review a mutation proposal.
        
        Args:
            mutation_id: Mutation ID
            approved: Whether mutation is approved
            reviewer: Reviewer name
            notes: Optional review notes
            
        Returns:
            True if successful
        """
        with self._lock:
            proposal = self.proposals.get(mutation_id)
            if not proposal:
                logger.error(f"Mutation {mutation_id} not found")
                return False
            
            proposal.status = MutationStatus.APPROVED if approved else MutationStatus.REJECTED
            proposal.reviewed_at = datetime.now()
            proposal.reviewer = reviewer
            proposal.review_notes = notes
            self.save()
        
        logger.info(f"Mutation {mutation_id} {'approved' if approved else 'rejected'} by {reviewer}")
        return True
    
    def apply_mutation(self, mutation_id: str) -> bool:
        """
        Apply an approved mutation to the working tree.
        
        Args:
            mutation_id: Mutation ID
            
        Returns:
            True if successful
        """
        with self._lock:
            proposal = self.proposals.get(mutation_id)
            if not proposal:
                logger.error(f"Mutation {mutation_id} not found")
                return False
            
            if proposal.status != MutationStatus.APPROVED:
                logger.warning(f"Mutation {mutation_id} is not approved (status: {proposal.status.value})")
                return False

        with self._lock:
            proposal.review_notes = proposal.review_notes

        try:
            apply_result = self._apply_with_backend(mutation_id, proposal)
        except Exception as e:
            logger.error(f"Failed to apply mutation {mutation_id}: {e}", exc_info=True)
            return False

        with self._lock:
            proposal.status = MutationStatus.APPLIED
            proposal.applied_at = datetime.now()
            proposal.metadata["changed_files"] = list(apply_result.get("changed_files") or [])
            proposal.metadata["backup_paths"] = list(apply_result.get("backup_paths") or [])
            proposal.metadata["apply_summary"] = str(apply_result.get("summary") or "")
            self.save()
        
        logger.info(f"Mutation {mutation_id} applied to {proposal.target_module}")
        return True
    
    async def _ai_code_analysis(
        self,
        proposal: MutationProposal
    ) -> Optional[Dict[str, Any]]:
        """
        Use AI to analyze code quality and safety.
        
        Args:
            proposal: Mutation proposal
            
        Returns:
            Analysis result with issues and suggestions
        """
        if not self.ask_ai:
            return None
        
        prompt = f"""Analyze this code mutation for safety and quality:

Mutation Type: {proposal.mutation_type}
Target Module: {proposal.target_module}
Description: {proposal.description}

Code:
```python
{proposal.proposed_code}
```

Check for:
1. Security vulnerabilities
2. Code quality issues
3. Potential bugs
4. Performance problems
5. Best practice violations

Return JSON: {{"issues": ["issue1", "issue2"], "suggested_improvements": ["suggestion1"]}}"""

        try:
            response = await self.ask_ai.ask_async(
                prompt=prompt,
                provider=AIProvider.OPENAI,
                temperature=0.3,
                max_tokens=1000
            )
            
            if response.success:
                import json
                import re
                
                # Extract JSON
                content = response.content.strip()
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))
        except Exception as e:
            logger.debug(f"AI code analysis error: {e}")
        
        return None
    
    def rollback_mutation(self, mutation_id: str) -> bool:
        """
        Rollback an applied mutation.
        
        Args:
            mutation_id: Mutation ID
            
        Returns:
            True if successful
        """
        with self._lock:
            proposal = self.proposals.get(mutation_id)
            if not proposal:
                logger.error(f"Mutation {mutation_id} not found")
                return False
            
            if proposal.status != MutationStatus.APPLIED:
                logger.warning(f"Mutation {mutation_id} is not applied (status: {proposal.status.value})")
                return False
            
            if not proposal.original_code and not proposal.metadata.get("backup_paths"):
                logger.error(f"Original code not available for mutation {mutation_id}")
                return False

        try:
            rollback_result = self._rollback_with_backend(mutation_id, proposal)
        except Exception as e:
            logger.error(f"Failed to rollback mutation {mutation_id}: {e}", exc_info=True)
            return False

        with self._lock:
            proposal.status = MutationStatus.ROLLED_BACK
            proposal.metadata["rollback_summary"] = str(rollback_result.get("summary") or "")
            self.save()
        
        logger.info(f"Mutation {mutation_id} rolled back")
        return True
    
    def get_mutation(self, mutation_id: str) -> Optional[MutationProposal]:
        """Get a mutation proposal."""
        with self._lock:
            return self.proposals.get(mutation_id)

    def get_proposal(self, mutation_id: str) -> Optional[MutationProposal]:
        """Compatibility alias for older mutation-review integrations."""
        return self.get_mutation(mutation_id)

    def approve_proposal(
        self,
        mutation_id: str,
        reviewer: str = "system",
        notes: Optional[str] = None,
    ) -> bool:
        """Compatibility alias for approving a proposal before apply."""
        return self.review_mutation(
            mutation_id,
            approved=True,
            reviewer=reviewer,
            notes=notes,
        )
    
    def list_mutations(
        self,
        status: Optional[MutationStatus] = None,
        target_module: Optional[str] = None
    ) -> List[MutationProposal]:
        """List mutations, optionally filtered."""
        with self._lock:
            mutations = list(self.proposals.values())
            
            if status:
                mutations = [m for m in mutations if m.status == status]
            
            if target_module:
                mutations = [m for m in mutations if m.target_module == target_module]
            
            return mutations

    def get_all_proposals(self) -> List[MutationProposal]:
        """Compatibility alias for older API surfaces."""
        return self.list_mutations()

    def get_recent_mutations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the most recent mutations for older adapter surfaces."""
        with self._lock:
            ordered = sorted(
                self.proposals.values(),
                key=lambda proposal: proposal.created_at,
                reverse=True,
            )
            return [proposal.to_dict() for proposal in ordered[:limit]]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get mutation engine statistics."""
        with self._lock:
            status_counts = {}
            for mutation in self.proposals.values():
                status = mutation.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "total_mutations": len(self.proposals),
                "status_distribution": status_counts,
                "approved_count": len([m for m in self.proposals.values() if m.status == MutationStatus.APPROVED]),
                "applied_count": len([m for m in self.proposals.values() if m.status == MutationStatus.APPLIED])
            }
    
    def save(self):
        """Save mutations to disk."""
        with self._lock:
            data = {
                "mutations": {
                    mutation_id: proposal.to_dict()
                    for mutation_id, proposal in self.proposals.items()
                },
                "updated_at": datetime.now().isoformat()
            }
            
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
    
    def load(self):
        """Load mutations from disk."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                for mutation_id, mutation_data in data.get("mutations", {}).items():
                    proposal = MutationProposal.from_dict(mutation_data)
                    self.proposals[mutation_id] = proposal
            
            logger.info(f"Loaded {len(self.proposals)} mutation proposals")
        except Exception as e:
            logger.error(f"Error loading mutations: {e}")


if __name__ == "__main__":
    import os
    import sys
    import tempfile

    fd, storage_path = tempfile.mkstemp(suffix="_mutations.json")
    os.close(fd)
    with open(storage_path, "w", encoding="utf-8") as f:
        f.write('{"mutations":{}}')
    try:
        engine = MutationEngine(storage_path=storage_path)

        mutation_id = engine.propose_mutation(
            target_module="example_module",
            mutation_type="optimization",
            description="Optimize loop performance",
            proposed_code="""
def optimized_function():
    # Optimized version
    result = []
    for i in range(100):
        result.append(i * 2)
    return result
""",
            confidence=0.8,
        )

        evaluation = engine.evaluate_mutation(mutation_id)
        print(f"Evaluation: {evaluation}")

        if evaluation.get("recommendation") == "approve":
            engine.review_mutation(mutation_id, approved=True, reviewer="system")

        stats = engine.get_statistics()
        print(f"Statistics: {stats}")
    finally:
        if os.path.exists(storage_path):
            os.unlink(storage_path)
    sys.exit(0)
