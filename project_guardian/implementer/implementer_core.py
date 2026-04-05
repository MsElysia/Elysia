"""
ImplementerCore - Main coordinator for the Implementer Agent
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from .planner import Planner
from .task_runner import TaskRunner, Guardrails
from .reporter import Reporter
from .repo_adapter import RepoAdapter, RepoConfig
from .codegen_client import CodeGenClient
from .test_runner import TestRunner
from .data_models import ImplementationResult

logger = logging.getLogger(__name__)


class ImplementerCore:
    """
    Main coordinator for the Implementer Agent.
    Orchestrates planning, execution, and reporting.
    """
    
    def __init__(self,
                 proposals_root: Path,
                 repo_root: Path,
                 api_manager=None,
                 repo_config: Optional[RepoConfig] = None,
                 guardrails: Optional[Guardrails] = None):
        """
        Initialize ImplementerCore.
        
        Args:
            proposals_root: Root directory for proposals
            repo_root: Root of codebase to modify
            api_manager: API key manager for LLM access
            repo_config: Configuration for repo operations
            guardrails: Safety guardrails
        """
        self.proposals_root = Path(proposals_root)
        self.repo_root = Path(repo_root)
        
        # Initialize components
        if repo_config is None:
            repo_config = RepoConfig(
                repo_root=repo_root,
                allowed_directories=[],  # Empty = no restrictions (should be configured)
                auto_commit=False
            )
        
        if guardrails is None:
            guardrails = Guardrails(
                halt_on_first_failure=True,
                dry_run=False
            )
        
        self.repo_adapter = RepoAdapter(repo_config)
        self.codegen_client = CodeGenClient(api_manager)
        self.test_runner = TestRunner(repo_root)
        self.task_runner = TaskRunner(
            self.repo_adapter,
            self.codegen_client,
            self.test_runner,
            guardrails
        )
        self.planner = Planner(api_manager)
        self.reporter = Reporter(proposals_root)
        
        logger.info("ImplementerCore initialized")
    
    def implement_proposal(self, proposal_id: str, actor: str = "implementer_agent") -> ImplementationResult:
        """
        Implement a single proposal.
        
        Args:
            proposal_id: ID of proposal to implement
            actor: Who is triggering the implementation
        
        Returns:
            ImplementationResult
        """
        # Load proposal
        proposal = self._load_proposal(proposal_id)
        
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        
        # Hard gate: only approved proposals
        status = proposal.get("status")
        if status != "approved":
            raise ValueError(f"Proposal {proposal_id} is not approved (status: {status})")
        
        logger.info(f"Starting implementation of proposal {proposal_id}")
        
        # Mark as in implementation
        self.reporter.mark_status(
            proposal,
            "in_implementation",
            actor,
            "Implementation started"
        )
        
        try:
            # Create work branch
            branch_name = self.repo_adapter.create_work_branch(proposal_id)
            logger.info(f"Created branch: {branch_name}")
            
            # Build plan
            plan = self.planner.build_plan(proposal)
            logger.info(f"Built plan with {len(plan.steps)} steps")
            
            # Build task graph
            task_graph = self.planner.build_task_graph(plan)
            logger.info(f"Built task graph with {len(task_graph.tasks)} tasks")
            
            # Execute tasks
            result = self.task_runner.execute(task_graph, proposal)
            result.branch_name = branch_name
            
            # Record result
            self.reporter.record_implementation_result(proposal, result, actor)
            
            logger.info(f"Implementation complete: {result.status.value}")
            return result
        
        except Exception as e:
            logger.error(f"Implementation failed: {e}")
            
            # Mark as failed
            try:
                self.reporter.mark_status(
                    proposal,
                    "implementation_failed",
                    actor,
                    f"Implementation failed: {str(e)}"
                )
            except Exception as report_error:
                logger.error(f"Failed to update proposal status: {report_error}")
            
            # Return failure result
            from .data_models import ImplementationStatus
            return ImplementationResult(
                proposal_id=proposal_id,
                status=ImplementationStatus.IMPLEMENTATION_FAILED,
                error=str(e)
            )
    
    def list_approved_proposals(self, domain_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all approved proposals ready for implementation.
        
        Args:
            domain_filter: Optional domain to filter by
        
        Returns:
            List of proposal metadata dicts
        """
        proposals = []
        
        for proposal_dir in self.proposals_root.iterdir():
            if not proposal_dir.is_dir():
                continue
            
            metadata_path = proposal_dir / "metadata.json"
            if not metadata_path.exists():
                continue
            
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    proposal = json.load(f)
                
                if proposal.get("status") != "approved":
                    continue
                
                if domain_filter and proposal.get("domain") != domain_filter:
                    continue
                
                proposals.append(proposal)
            
            except Exception as e:
                logger.warning(f"Failed to load proposal {proposal_dir.name}: {e}")
        
        return proposals
    
    def _load_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Load proposal metadata"""
        proposal_path = self.proposals_root / proposal_id
        metadata_path = proposal_path / "metadata.json"
        
        if not metadata_path.exists():
            return None
        
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                import json
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load proposal {proposal_id}: {e}")
            return None

